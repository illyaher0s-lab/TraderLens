# Agent Entry Design Freeze (P0-2)

**Date:** 2026-07-02  
**Status:** DESIGN_FREEZE  
**Purpose:** 冻结 Agent 输入管道设计，修复 P0-1/P0-2 fake progress 缺口

---

## Executive Summary

TraderLens V1 Workbench 当前存在 **P0 假进度缺口**：用户消息触发 `workflow_state = "researching"` 或 `"validating"`，但没有真实业务动作。

本设计文档冻结 Agent Entry 管道架构，明确：
1. **会话上下文** 必须进入管道（不能只看当前句子）
2. **单次 LLM 调用** 规则（一条消息最多一次结构化提取）
3. **PreScan/LLM/Tushare/Router 优先级** 和分工边界
4. **禁止 fake progress** 的正确定义（不是禁止长任务）
5. **Entity Resolution** 和 Tushare 的责任分工
6. **主题研究入口** 设计（本次可 deferred）

**核心原则：**
- 没有真实 job/action，不显示 running/researching/validating
- 有真实后台 job，可以超过 30 秒，但必须显示真实状态
- LLM 只做语义理解和候选提取，不做确认、决策、路由
- Tushare 是股票真实性的唯一来源
- Router 是最终裁决者

---

## 1. Agent Input Pipeline Architecture

### 1.1 Pipeline Overview

```
用户消息
  ↓
【读取 Session Context】
  - conversation_id
  - workflow_kind / workflow_state
  - 最近 N 条消息（默认 5 条）
  - 当前关联：research_case / position / strategy_idea / theme
  - Open observation positions
  ↓
【PreScan】(deterministic, no LLM)
  - 检测股票代码
  - 检测执行反馈
  - 检测策略规则形态
  - 检测问候语
  - 高置信短路：执行反馈 → 直接进 execution_feedback 路径
  ↓
【Single LLM Call】(if needed)
  - 意图理解
  - 提取公司名 / 股票代码候选 / 策略文本 / 执行反馈
  - 生成澄清草稿
  - 返回 confidence + ambiguity_reason
  ↓
【Stock Identity Resolution】(Tushare, if stock entity detected)
  - Tushare stock_basic 验证
  - 返回：verified / ambiguous / not_found / data_fault / not_applicable
  ↓
【Deterministic Router】
  - 基于 PreScan + LLM intent + Tushare identity
  - 决定 workflow_kind + workflow_state
  - 决定 next_action: real_job / waiting / clarification / failed
  ↓
【Real Workflow Action】(if allowed)
  - friend_stock: intake → research → candidate_pool
  - strategy_idea: create_idea → extract → template_mapping
  - execution_feedback: interpret → position_update
  - observation_followup: query_position → daily_signal
  - theme_research: (deferred, 返回 clarification)
  ↓
【Activity Timeline】
  - 记录所有 artifacts (不只是 intent)
  - 用户可见真实状态
```

---

## 2. Session Context (必须补的第一个洞)

### 2.1 Why Context Matters

**问题：** 当前只看单条消息，无法理解：
- "帮我看看" — 看什么？
- "今天要不要继续拿" — 拿什么？
- "买入可以吗" — 买入哪只？

**解决：** Session context 必须进管道。

### 2.2 Context Structure

```python
class SessionContext(BaseModel):
    conversation_id: str
    workflow_kind: WorkflowKind | None
    workflow_state: WorkflowState
    
    # 最近会话历史
    recent_messages: list[AgentMessage]  # 默认最近 5 条
    
    # 当前关联实体
    current_research_case: str | None  # friend_stock_flow_id
    current_theme: str | None          # theme_id
    current_position: str | None       # position_id
    current_strategy_idea: str | None  # strategy_idea_id
    
    # 开仓持仓列表（用于 "今天要不要继续拿"）
    open_positions: list[ObservationPosition]
```

### 2.3 Context Loading Rules

**加载时机：** 每次 `/api/agent/workbench/message` 调用时

**加载内容：**
1. 当前 session 的 workflow_kind / workflow_state
2. Timeline 中最近 5 条 user/agent 消息
3. Timeline 中最近一个 artifact_ref（研究案例/持仓/策略想法）
4. LiveTradeDB 中 `open` 状态的 positions

**不加载：**
- 完整 timeline（太大）
- 已关闭 positions
- 历史 rejected strategies（除非用户明确问）

---

## 3. Single LLM Call Rule (必须补的第二个洞)

### 3.1 Current Problem

当前实现可能触发多次 LLM 调用：
1. Intent extraction
2. Company name extraction
3. Clarification generation

**问题：** 串行 LLM 调用 = 慢 + token 浪费 + 不一致

### 3.2 Design Rule

**一条用户消息，最多一次 LLM 调用。**

这一次调用必须同时返回：

```python
class WorkbenchIntentExtraction(BaseModel):
    # Intent
    primary_intent: Literal[
        "stock_research",
        "theme_research",
        "strategy_idea",
        "execution_feedback",
        "position_followup",
        "review_request",
        "unknown"
    ]
    intent_candidates: list[str]  # 备选意图
    
    # Entity extraction
    extracted_company_name: str | None
    extracted_stock_codes: list[str]  # 可能多个候选
    extracted_strategy_text: str | None
    extracted_execution_feedback: str | None
    
    # Follow-up target (用于 "帮我看看")
    follow_up_target: Literal["position", "research", "strategy", "none"]
    follow_up_entity_id: str | None  # position_id / research_case_id
    
    # Clarification draft (if ambiguous)
    clarification_draft: str | None
    
    # Confidence
    confidence: Literal["high", "medium", "low"]
    ambiguity_reason: str | None
    
    # Source
    extraction_source: Literal["llm", "deterministic_fixture"]
```

### 3.3 When LLM Is Called

**LLM 调用条件：**
- PreScan 未检测到高置信执行反馈
- PreScan 未检测到完整股票代码
- 不是纯问候语

**LLM 不调用：**
- PreScan 检测到 `detected_execution_action` + 结构完整
- PreScan 检测到 `detected_stock_code` 且无歧义
- `is_plain_greeting = True`

**禁止：**
- 不能先调用 LLM 提取 intent，再调用 LLM 提取 company_name
- 不能先调用 LLM 理解，再调用 LLM 生成澄清

---

## 4. PreScan / LLM / Tushare / Router Priority (必须补的第三个洞)

### 4.1 Priority Chain

```
Priority 1: PreScan 高置信短路
  → 执行反馈完整结构 → 跳过 LLM，直接进 execution_feedback

Priority 2: PreScan 结构信号
  → 检测到股票代码 / 策略形态 / 问候语
  → 传递给 LLM（如果需要），但不做最终判断

Priority 3: LLM 语义理解
  → 提取候选实体（company_name, stock_code_candidates）
  → 提供 intent 建议
  → 不能覆盖 PreScan 高置信信号
  → 不能确认股票真实性

Priority 4: Tushare Stock Identity
  → 验证股票真实性（verified / not_found / ambiguous / data_fault）
  → 唯一可以确认股票存在的组件
  → LLM 不能覆盖 Tushare 结果

Priority 5: Router 最终裁决
  → 综合 PreScan + LLM + Tushare
  → 决定 workflow_kind + allowed_to_start_workflow
  → 决定 next_action (real_job / clarification / failed)
```

### 4.2 Component Boundaries

| Component | Can Do | Cannot Do |
|-----------|--------|-----------|
| **PreScan** | 检测结构模式（代码/反馈/策略形态） | 语义理解、确认股票存在、最终路由 |
| **LLM** | 语义理解、提取候选实体、生成澄清草稿 | 确认股票存在、买卖决策、最终路由 |
| **Tushare** | 验证股票真实性、返回公司名/交易所 | 语义理解、意图判断 |
| **Router** | 最终路由决策、workflow_kind 裁定 | 提取实体、生成澄清 |

### 4.3 Conflict Resolution Rules

**Rule 1: PreScan 高置信执行反馈 > LLM**
- PreScan 检测到 "已买入 100 股，成交价 12.34"
- → 即使 LLM 返回 `stock_research`，Router 也选 `execution_feedback`

**Rule 2: Tushare 验证结果 > LLM 提取**
- LLM 提取 `extracted_company_name = "宏昌电子"`
- Tushare 返回 `status = "not_found"`
- → Router 必须进入 clarification，不能假装股票存在

**Rule 3: Router 基于证据链，不能猜测**
- PreScan 无结构信号
- LLM 返回 `confidence = "low"`
- Tushare 返回 `not_applicable`
- → Router 必须返回 `unknown` 或 `clarification`，不能随意分配 workflow

---

## 5. Fake Progress 的正确定义 (必须补的第四个洞)

### 5.1 What Is Fake Progress

**定义：** 显示 `running` / `researching` / `validating` 状态，但没有真实后台 job 或 action。

**例子：**
```python
# ❌ WRONG (fake progress)
session.workflow_state = "researching"
agent_reply = "我会帮你调查...稍等片刻。"
# BUT: 没有调用 friend_stock_flow.run_research()
# 用户看到 "研究中"，实际什么都没发生
```

### 5.2 What Is NOT Fake Progress

**真实长任务：**
```python
# ✅ CORRECT (real long-running job)
session.workflow_state = "researching"
friend_stock_flow.run_research(flow_id)  # 真实调用
# → 可能需要 2-5 分钟（LLM + Serenity）
# → UI 显示 "研究中"，用户知道在等真实结果
```

**规则：**
- 有真实 job，可以超过 30 秒
- 必须有真实 artifact 产出（research_output / strategy_idea / execution_log）
- 不能为了 "30 秒规则" 伪造完成

### 5.3 State Transition Rules

**Allowed states:**

| State | Meaning | Must Have |
|-------|---------|-----------|
| `created` | Session 已创建，等待用户输入 | N/A |
| `waiting_for_clarification` | 需要用户澄清 | Clarification message |
| `queued` | 任务已进队列，等待执行 | Job ID or queue position |
| `researching` | 研究正在进行 | friend_stock_flow or theme research job |
| `validating` | 策略验证正在进行 | strategy_idea validation job |
| `waiting_for_approval` | 等待用户审批 | ApprovalCard |
| `completed` | 工作流结束 | Final artifact (candidate_pool / rejection / review) |
| `stopped` | 无法继续（缺少信息/数据故障） | Stop reason |

**Forbidden transitions:**
- `created` → `researching` without calling research job
- `created` → `validating` without calling validation job
- `queued` → `completed` without real artifact

---

## 6. Entity Resolution and Tushare Division (必须补的第五个洞)

### 6.1 Division of Labor

| Stage | Who | What | Output |
|-------|-----|------|--------|
| **Candidate Extraction** | PreScan / LLM | 提取候选字符串 | `["宏昌电子", "603002"]` |
| **Identity Verification** | Tushare | 确认股票真实性 | `verified` / `not_found` / `ambiguous` |
| **Routing Decision** | Router | 基于验证结果决定下一步 | `allowed_to_start_workflow` |

### 6.2 LLM Cannot Confirm Stock Existence

**LLM 可以做：**
```python
extracted_company_name = "宏昌电子"
extracted_stock_codes = ["603002"]
confidence = "high"
```

**LLM 不能做：**
```python
# ❌ WRONG
stock_verified = True  # LLM 不能确认
ticker = "603002.SH"   # LLM 不能补全后缀
```

### 6.3 Tushare Identity Resolver Responsibilities

**Tushare 必须返回：**
- `status`: verified / ambiguous / not_found / data_fault
- `ticker`: 完整代码（含后缀）
- `company_name`: 官方名称
- `exchange`: 交易所
- `fault_reason`: 如果 data_fault

**Tushare 处理场景：**
1. **Bare code:** `603002` → `603002.SH` (推断后缀)
2. **Company name:** `宏昌电子` → `603002.SH`
3. **Ambiguous:** `000001` → 返回 `ambiguous` + 候选列表
4. **Not found:** `999999` → `not_found`
5. **Data fault:** Tushare API error → `data_fault` + reason

---

## 7. Theme Research Entry (必须覆盖的第六个入口)

### 7.1 Design Requirement

**用户消息：**
```
我看到视频说存储行业最近很火，帮我研究一下
```

**Router 必须识别：** `theme_research`

**但本次可以 deferred：** 返回 clarification，不实现真实研究流程

### 7.2 Router Decision Tree (含 theme_research)

```
workflow_kind candidates:
  - friend_stock     (股票代码 verified 或 高置信股票名)
  - theme_research   (行业/赛道/主题关键词)
  - strategy_idea    (策略规则形态 + 无 verified 股票)
  - execution_feedback (执行反馈结构)
  - observation_followup ("帮我看看" + context 有 open_position)
  - unknown          (无法判断)
```

### 7.3 Theme Research Deferred Response

**如果本次不实现 theme_research：**

```python
if route_decision.workflow_kind == "theme_research":
    return {
        "workflow_state": "waiting_for_clarification",
        "agent_reply": "主题研究功能开发中，当前版本仅支持单票股票研究。请提供具体股票代码或公司名。",
        "next_required_user_action": "provide_stock_code_or_name",
        "allowed_to_start_workflow": False,
    }
```

**明确 deferred：** 设计文档必须包含 theme_research 路径，即使不实现。

---

## 8. LLM Boundaries (明确边界)

### 8.1 LLM Can Do

**语义理解：**
- 理解用户意图（问股票 / 问策略 / 提交反馈）
- 区分 "买入可以吗"（询问） vs "已买入"（反馈）

**实体提取：**
- 公司名："宏昌电子"
- 股票代码候选：["603002", "SH603002"]
- 主题关键词："存储行业"
- 策略规则文本："下午两点半买入，第二天卖出"
- 执行反馈："已买入 100 股，成交价 12.34"

**澄清草稿生成：**
- 当 `confidence = "low"` 时，生成澄清问题
- 例："您是想研究宏昌电子这只股票，还是提交买入记录？"

### 8.2 LLM Cannot Do

**确认股票真实性：**
- ❌ 不能说 "603002 是宏昌电子"
- ❌ 不能补全 "603002" → "603002.SH"
- ✅ 只能提取候选："603002"

**买卖决策：**
- ❌ 不能说 "建议买入"
- ❌ 不能说 "应该卖出"
- ✅ 只能提取用户意图："用户询问是否买入"

**策略通过/失败：**
- ❌ 不能说 "这个策略可行"
- ❌ 不能说 "这个策略有问题"
- ✅ 只能提取策略文本

**P&L 计算：**
- ❌ 不能计算盈亏
- ✅ 只能提取执行反馈

**绕过 Router：**
- ❌ 不能直接决定 workflow_kind
- ❌ 不能跳过 Tushare 验证
- ✅ 只能提供 intent 建议（Router 最终裁决）

---

## 9. Acceptance Test Cases (验收用例)

### 9.1 Test Case Matrix

| Input | Session Context Needed? | LLM Called? | Tushare Called? | Final Route | Artifacts Created |
|-------|------------------------|-------------|-----------------|-------------|-------------------|
| "宏昌电子是否值得买入" | No | Yes | Yes | `friend_stock` | `friend_stock_flow`, `research_output`, `confirmed_candidate` |
| "帮我看一下 603002" | No | No (PreScan) | Yes | `friend_stock` | Same as above |
| "朋友推荐了宏昌电子" | No | Yes | Yes | `friend_stock` | Same as above |
| "买入宏昌电子可以吗" | No | Yes | Yes | `friend_stock` | Same as above |
| "我刷到一个策略，下午两点半买入第二天卖出" | No | Yes | No | `strategy_idea` | `strategy_idea`, `extraction`, `template_mapping` or `rejection` |
| "我已经买入 100 股，成交价 12.34" | Yes (需要知道哪只股票) | No (PreScan) | No | `execution_feedback` | `execution_observation_draft` or `log` |
| "今天要不要继续拿" | Yes (需要 open_positions) | Yes | No | `observation_followup` | `daily_observation_signal` |
| "你好" | No | No (PreScan) | No | `unknown` (greeting) | `agent_message` only |
| "帮我看看" | Yes (需要知道看什么) | Yes | No | `clarification` or `observation_followup` | Clarification message |
| "我看到视频说存储行业最近很火，帮我研究一下" | No | Yes | No | `theme_research` (deferred) | Clarification (feature not implemented) |

### 9.2 Detailed Test Cases

#### Case 1: "宏昌电子是否值得买入"

**Session Context:**
- No prior context needed

**Pipeline Flow:**
1. PreScan: `has_stock_research_language = True`
2. LLM: `primary_intent = "stock_research"`, `extracted_company_name = "宏昌电子"`
3. Tushare: `status = "verified"`, `ticker = "603002.SH"`
4. Router: `workflow_kind = "friend_stock"`, `allowed_to_start_workflow = True`
5. Action: Call `friend_stock_flow.intake()` → `run_research()` → `create_candidate_pool()`

**Timeline Artifacts:**
- `user_message`
- `workflow_intent` (PreScan + LLM + Tushare + Router)
- `friend_stock_flow` (flow created)
- `research_output` (Serenity result)
- `confirmed_candidate` (if passed)
- `agent_message` (final reply)

**Expected Reply:**
```
我已经完成对宏昌电子（603002.SH）的研究。根据分析，该股票...
[显示研究结论 + 候选池状态]
```

---

#### Case 2: "我已经买入 100 股，成交价 12.34"

**Session Context:**
- REQUIRED: `current_position` or `recent_messages` 中有股票信息

**Pipeline Flow:**
1. PreScan: `detected_execution_action = "buy"` → **短路，跳过 LLM**
2. Router: `workflow_kind = "execution_feedback"`
3. Action: Call `execution_interpreter.parse_feedback()` → `observation_pool.create_position()`

**Timeline Artifacts:**
- `user_message`
- `execution_observation_draft` (待确认)
- `execution_observation_log` (确认后)
- `observation_position` (持仓记录)
- `agent_message`

**Expected Reply:**
```
已记录买入：宏昌电子 100 股，成交价 12.34 元。
持仓已进入观察池，系统将每日生成跟进信号。
```

**If Context Missing:**
```
检测到买入反馈，但无法确定股票。请补充股票代码或公司名。
```

---

#### Case 3: "今天要不要继续拿"

**Session Context:**
- REQUIRED: `open_positions` (至少一个开仓持仓)

**Pipeline Flow:**
1. PreScan: No high-confidence signal
2. LLM: `primary_intent = "position_followup"`, `follow_up_target = "position"`
3. Router: 
   - If `len(open_positions) == 1` → `observation_followup`
   - If `len(open_positions) > 1` → `clarification` (哪个持仓？)
   - If `len(open_positions) == 0` → `unknown` (无开仓持仓)
4. Action: Call `observation_pool.generate_daily_signal(position_id)`

**Timeline Artifacts:**
- `user_message`
- `daily_observation_signal`
- `agent_message`

**Expected Reply (single position):**
```
宏昌电子（603002.SH）当前持仓状态：
- 今日信号：hold (继续持有)
- 浮动盈亏：+8.5%
- 止损位：11.28 元（未触发）
```

**Expected Reply (no positions):**
```
当前无开仓持仓。如需查看历史记录，请访问观察池页面。
```

---

#### Case 4: "帮我看看"

**Session Context:**
- REQUIRED: `recent_messages` or `current_research_case` or `open_positions`

**Pipeline Flow:**
1. PreScan: No signal
2. LLM: `primary_intent = "position_followup"` or `"review_request"`, `follow_up_target = ?`
3. Router: 
   - If context has open_position → `observation_followup`
   - If context has recent research_case → provide research summary
   - Else → `clarification` ("您想看什么？")

**Timeline Artifacts:**
- `user_message`
- `agent_message` (clarification or summary)

**Expected Reply (with context):**
```
您的宏昌电子持仓今日状态：hold，浮盈 +8.5%。
```

**Expected Reply (no context):**
```
请问您想查看：
1. 开仓持仓跟进
2. 近期研究案例
3. 策略验证状态
```

---

#### Case 5: "我看到视频说存储行业最近很火，帮我研究一下"

**Session Context:**
- No context needed

**Pipeline Flow:**
1. PreScan: No stock code, no execution feedback
2. LLM: `primary_intent = "theme_research"`, `extracted_theme = "存储行业"`
3. Tushare: Not called (no stock entity)
4. Router: `workflow_kind = "theme_research"`, `allowed_to_start_workflow = False` (deferred)

**Timeline Artifacts:**
- `user_message`
- `workflow_intent`
- `agent_message` (clarification)

**Expected Reply:**
```
主题研究功能开发中，当前版本仅支持单票股票研究。
请提供具体股票代码或公司名（例如："帮我看看宏昌电子"）。
```

**Design Note:** Router 必须识别 `theme_research`，即使不实现。

---

## 10. Implementation Tasks (仍需实现的任务)

### 10.1 P0-2A: Session Context Loading

**File:** `backend/api/research.py`

**Changes:**
1. Modify `/api/agent/workbench/message` endpoint
2. Load `SessionContext` before calling pipeline
3. Pass context to `WorkbenchIntentExtractor` and `Router`

**Artifacts:**
- `SessionContext` class
- Context loader function

---

### 10.2 P0-2B: Single LLM Call Refactor

**File:** `backend/services/workbench_intent_extractor.py`

**Changes:**
1. Merge all extractions into one LLM call
2. Return `WorkbenchIntentExtraction` with all fields populated
3. Remove separate calls for company_name / clarification

**Test:**
- Verify LLM called at most once per message
- Verify all fields returned

---

### 10.3 P0-2C: Real Workflow Actions

**File:** `backend/api/research.py`

**Changes:**
1. After Router returns `allowed_to_start_workflow = True`:
   - `friend_stock`: Call `friend_stock_flow.intake()` → `run_research()` → `create_candidate_pool()`
   - `strategy_idea`: Call `strategy_idea_flow.create_idea()` → `extract()` → `map_to_template()`
   - `execution_feedback`: Call `execution_interpreter.parse()` → `observation_pool.create_position()`
2. Create timeline artifacts (not just intent)
3. Update `workflow_state` based on real job status

**Forbidden:**
- Do NOT set `workflow_state = "researching"` without calling research
- Do NOT set `workflow_state = "validating"` without calling validation

---

### 10.4 P0-2D: Activity Timeline Update

**File:** `backend/db/agent_workbench.py`

**Changes:**
1. Record all artifacts to timeline:
   - `friend_stock_flow`
   - `research_output`
   - `confirmed_candidate`
   - `strategy_idea`
   - `strategy_idea_extraction`
   - `template_mapping`
   - `rejection_registry`
   - `execution_observation_draft`
   - `execution_observation_log`
   - `observation_position`
   - `daily_observation_signal`

2. Timeline item must include:
   - `type`: artifact type
   - `artifact_id`: primary key
   - `status`: artifact status
   - `created_at`: timestamp

---

### 10.5 P0-2E: Router Priority Rules

**File:** `backend/services/workbench_workflow_router.py`

**Changes:**
1. Implement Priority Chain (Section 4.1)
2. Add conflict resolution rules (Section 4.3)
3. Handle `theme_research` (deferred response)

**Test:**
- PreScan execution feedback > LLM intent
- Tushare `not_found` > LLM extracted company
- Router returns clarification when evidence insufficient

---

## 11. Design Freeze Checklist

- [x] Session context structure defined
- [x] Single LLM call rule specified
- [x] PreScan/LLM/Tushare/Router priority chain frozen
- [x] Fake progress definition clarified
- [x] Entity resolution and Tushare division specified
- [x] Theme research entry designed (deferred)
- [x] LLM boundaries documented
- [x] Acceptance test cases defined
- [x] Implementation tasks outlined

---

**Design Frozen:** 2026-07-02  
**Next Step:** P0-2 Implementation (code + tests)

