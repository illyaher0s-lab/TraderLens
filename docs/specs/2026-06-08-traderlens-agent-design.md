# TraderLens Agent 设计文档

**版本**: MVP v0.1  
**日期**: 2026-06-08  
**状态**: Draft  

---

## Part 1: 项目概述与架构变更

### 1.1 项目背景

TraderLens 是一个基于 LangGraph 的 A 股投资研究辅助系统，目标是帮助个人投资者进行：
- 投研分析：市场环境判断 + 基本面分析 + 技术面分析 + 回测验证
- 策略回测：验证交易策略的历史表现
- 观察池管理：维护待验证的交易假设库
- 复盘优化：定期回顾分析结果，优化判断框架

**核心诉求**：构建一个真正的 AI Agent，而不是披着 LangGraph 外衣的固定工作流。

---

### 1.2 架构变更：从工作流到 Agent

#### **旧架构（固定工作流）**

```
Planner → DataFetcher → MarketRegime → SectorStrength 
       → Researcher → Technician → Backtester → Strategist
```

**问题**：
- 节点执行顺序固定，Agent 无法自主决策
- Planner 生成固定 7 个子任务，缺乏动态调整能力
- 回测结果不影响下一轮判断，没有闭环反馈
- 本质上是"LLM 控制的工作流"，不是真正的 Agent

---

#### **新架构（Agent Harness + Tool Loop）**

```
User Goal
    ↓
ContextBuilder（整理上下文）
    ↓
AgentReasoner（LLM 推理：现在需要什么？）
    ↓
ToolExecutor（执行工具调用）
    ↓
QualityGate（安全检查 + 质量门）
    ├── running → ContextBuilder（继续循环）
    ├── waiting_human → HumanReview → ContextBuilder
    ├── completed → End
    └── error → End
```

**关键变化**：
1. **LangGraph 的角色变化**：
   - 不再是业务流程图，而是 Agent Harness
   - 管理循环、状态、工具调用、质量门、人工中断、checkpoint

2. **节点变成工具**：
   - Researcher、Technician、Backtester 不再是固定顺序节点
   - 改为 Agent 可调用的工具（tools），由 LLM 自主选择

3. **决策权交给 LLM**：
   - 每一步由 AgentReasoner（LLM）决定：调用哪个工具、是否继续、是否完成
   - 不再有预定义的"第 1 步做 A，第 2 步做 B"

4. **闭环反馈（第二阶段）**：
   - 回测结果可以影响策略权重
   - 复盘建议可以调整判断框架（需人工确认）
   - RAG 检索历史案例，提供上下文支持

---

### 1.3 MVP v0.1 目标与范围

#### **产品目标**
构建一个 **Goal-driven ReAct Agent Harness**，具备以下特性：
- 围绕用户目标自主选择工具
- 记录推理过程（observe → thought → action → result）
- 根据工具输出调整下一步动作
- 在生成交易计划前请求人工确认

#### **第一阶段支持的 Agent 特性**
✅ **Goal-driven（目标驱动）**
- 用户给出明确目标："分析平安银行能不能进观察池"
- Agent 持有显式 `goal` 字段，所有推理围绕目标展开

✅ **Tool-using（工具使用）**
- Agent 可以调用 8 个粗粒度工具
- 每个工具包装底层模块（DataFetcher、JudgmentEngine、BacktestEngine）

✅ **有限自主推理**
- Agent 自己决定下一步调用哪个工具
- 但有硬限制：最大步数 8、每个工具最多调用 2 次

✅ **人工确认点**
- 关键决策（加入观察池）必须人工确认
- QualityGate 检查后进入 HumanReview 节点

✅ **决策链可追溯**
- 每一步记录：`thought_summary`、`action`、`result`
- 所有推理过程存入 `decision_history`

---

#### **第一阶段暂不支持**
❌ **自动修改判断框架**
- Agent 不能自己调整 YAML 配置中的策略权重
- 只能"提出修改建议"，必须人工确认后才执行

❌ **自动调参**
- 不支持多轮回测、参数优化
- 第一版只做单次回测验证

❌ **多轮策略优化**
- Agent 不会自己发起"再回测一次"或"调整止损比例后重新验证"
- 优化建议由人工决定是否执行

❌ **完整 RAG 历史案例检索**
- `search_research_memory` 工具第一版返回空结果（占位）
- 后续接入向量数据库 + 语义检索

❌ **自动执行任何交易动作**
- Agent 只生成"观察池建议"和"交易计划"
- 不涉及真实下单、持仓管理

---

#### **第一阶段与第二阶段的关系**

| 特性 | MVP v0.1（第一阶段） | v0.2（第二阶段预留） |
|------|---------------------|---------------------|
| 架构 | Agent Harness + Tool Loop | 保持不变 |
| 工具数量 | 8 个（1 个占位） | 可扩展到 12+ |
| 自主程度 | 有限自主（硬限制） | 更高自主（软边界） |
| RAG | 占位接口 | 接入向量数据库 |
| 反馈循环 | 不支持 | 回测结果影响策略权重 |
| 复盘模块 | 简单展示 | 自动生成优化建议 |

**设计原则**：
- 第一阶段按 A（最小 ReAct Agent）落地
- 但架构为 B（带反馈循环的 Agent）预留空间
- 代码结构不需要大改，只需扩展工具和启用反馈逻辑

---

**Part 1 完成。**

---

## Part 2: AgentState 设计

### 2.1 State 结构定义

AgentState 是 LangGraph 状态机的核心数据结构，记录 Agent 的完整执行上下文。

**设计原则**：
- 不采用扁平结构（只记录结果），而是采用**分层结构**（记录决策过程）
- 真正的 Agent 核心是**决策链**，不只是工具调用结果
- 所有推理过程可追溯、可复盘、可优化

---

### 2.2 字段说明

```python
from typing import TypedDict, Literal, Optional, Any

class AgentState(TypedDict):
    """Agent 执行状态"""
    
    # ============ 基础信息 ============
    thread_id: str
    # LangGraph checkpoint 线程 ID
    # 用于恢复中断的任务
    
    run_id: str
    # 本次执行的唯一标识
    # 格式：run_20260608_143022_a3f8b2
    
    goal: str
    # 用户目标，例如：
    # "分析平安银行能不能进观察池"
    # "回测平安银行近 3 个月趋势策略表现"
    
    stock_code: Optional[str]
    # 股票代码，例如 "000001"
    # 从 goal 中解析或用户明确输入
    
    strategy_profile: Optional[str]
    # 策略类型：trend（趋势）/ growth（成长）/ value（价值）
    # 从 goal 中推断或用户指定
    
    
    # ============ 决策链（核心） ============
    decision_history: list[dict]
    # 记录每一步的推理过程
    # 格式：[
    #     {
    #         "step": 1,
    #         "thought": "当前缺少市场环境判断，需要先评估大盘趋势",
    #         "action": "evaluate_market_regime",
    #         "action_input": {"index_code": "000001"},
    #         "result": {"regime": "sideways", "confidence": 0.72}
    #     },
    #     ...
    # ]
    
    
    # ============ 观察结果（工具输出） ============
    observations: dict[str, Any]
    # 工具调用后的结果缓存
    # 格式：{
    #     "market_regime": {...},
    #     "sector_strength": {...},
    #     "fundamentals": {...},
    #     "technicals": {...},
    #     "backtest": {...},
    #     "trade_plan": {...}
    # }
    
    
    # ============ 数据引用 ============
    data_refs: dict[str, str]
    # 数据来源引用（用于追溯）
    # 格式：{
    #     "price_data": "cache/000001_price_20260608.parquet",
    #     "financial_data": "cache/000001_financial_20260608.json"
    # }
    
    
    # ============ 人工确认记录 ============
    interrupt_history: list[dict]
    # 人工中断点记录
    # 格式：[
    #     {
    #         "node": "add_to_watchlist",
    #         "reason": "需要人工确认是否加入观察池",
    #         "timestamp": "2026-06-08T14:30:22",
    #         "user_decision": "approved"
    #     }
    # ]
    
    
    # ============ 控制字段 ============
    next_action: Optional[dict]
    # Agent 推理出的下一步行动
    # 格式：{
    #     "tool": "analyze_stock_fundamentals",
    #     "input": {"stock_code": "000001", "strategy_profile": "growth"}
    # }
    
    final_answer: Optional[dict]
    # 最终输出（交易计划或观察池建议）
    # 格式：{
    #     "decision": "watchlist",
    #     "reasoning": "基本面良好但技术面偏弱，建议观察等待突破",
    #     "entry_trigger": "放量突破 20 日均线",
    #     "invalid_condition": "跌破前低支撑位"
    # }
    
    status: Literal["running", "waiting_human", "completed", "error"]
    # 当前状态：
    # - running: 正在执行
    # - waiting_human: 等待人工确认
    # - completed: 任务完成
    # - error: 执行出错
    
    error: Optional[str]
    # 错误信息（status=error 时）
```

---

### 2.3 示例

#### **初始化 State**

```python
initial_state = {
    "thread_id": "thread_20260608_143022",
    "run_id": "run_20260608_143022_a3f8b2",
    "goal": "分析平安银行能不能进观察池",
    "stock_code": "000001",
    "strategy_profile": "value",
    "decision_history": [],
    "observations": {},
    "data_refs": {},
    "interrupt_history": [],
    "next_action": None,
    "final_answer": None,
    "status": "running",
    "error": None
}
```

---

#### **执行第一步后的 State**

```python
state_after_step1 = {
    "thread_id": "thread_20260608_143022",
    "run_id": "run_20260608_143022_a3f8b2",
    "goal": "分析平安银行能不能进观察池",
    "stock_code": "000001",
    "strategy_profile": "value",
    
    # 决策链增加一条记录
    "decision_history": [
        {
            "step": 1,
            "thought": "当前缺少市场环境判断，需要先评估大盘趋势",
            "action": "evaluate_market_regime",
            "action_input": {"index_code": "000001"},
            "result": {
                "tool": "evaluate_market_regime",
                "status": "success",
                "regime": "sideways",
                "confidence": 0.72,
                "summary": "市场处于震荡状态，个股机会分化"
            }
        }
    ],
    
    # 观察结果增加市场环境
    "observations": {
        "market_regime": {
            "regime": "sideways",
            "confidence": 0.72,
            "summary": "市场处于震荡状态，个股机会分化"
        }
    },
    
    # 数据引用
    "data_refs": {
        "index_data": "cache/000001_index_20260608.parquet"
    },
    
    # 下一步行动
    "next_action": {
        "tool": "analyze_stock_fundamentals",
        "input": {"stock_code": "000001", "strategy_profile": "value"}
    },
    
    "interrupt_history": [],
    "final_answer": None,
    "status": "running",
    "error": None
}
```

---

#### **等待人工确认时的 State**

```python
state_waiting_human = {
    # ... 前面字段省略 ...
    
    "decision_history": [
        # ... 前面 6 步省略 ...
        {
            "step": 7,
            "thought": "综合分析完成，建议加入观察池。触发条件：放量突破 20 日均线",
            "action": "add_to_watchlist",
            "action_input": {
                "stock_code": "000001",
                "entry_trigger": "放量突破 20 日均线",
                "invalid_condition": "跌破前低支撑位 11.8 元"
            },
            "result": None  # 等待人工确认，暂未执行
        }
    ],
    
    "next_action": {
        "tool": "add_to_watchlist",
        "input": {
            "stock_code": "000001",
            "entry_trigger": "放量突破 20 日均线",
            "invalid_condition": "跌破前低支撑位 11.8 元"
        }
    },
    
    "interrupt_history": [
        {
            "node": "add_to_watchlist",
            "reason": "需要人工确认是否加入观察池",
            "timestamp": "2026-06-08T14:35:18",
            "user_decision": None  # 等待用户输入
        }
    ],
    
    "status": "waiting_human",  # 状态变为等待人工
    "error": None
}
```

---

**Part 2 完成。**

---

## Part 3: Agent Harness（LangGraph 节点设计）

### 3.1 主图结构

LangGraph 不再是业务流程图，而是 **Agent Harness**：管理循环、状态、工具调用、质量门、人工中断、checkpoint。

```
Start
  ↓
ContextBuilder（整理上下文）
  ↓
AgentReasoner（LLM 推理下一步）
  ↓
ToolExecutor（执行工具）
  ↓
QualityGate（安全检查 + 质量门）
  ├── running → ContextBuilder（继续循环）
  ├── waiting_human → HumanReview → ContextBuilder
  ├── completed → End
  └── error → End
```

**关键特性**：
- 循环图，不是流水线图
- LLM 每一轮决定下一步做什么
- QualityGate 决定路由：继续 / 人工确认 / 结束 / 出错

---

### 3.2 五个核心节点

#### **节点 1: ContextBuilder（上下文构建器）**

**职责**：整理上下文，生成给 LLM 的 prompt

**输入**：`AgentState`  
**输出**：更新 `AgentState`（添加临时字段 `_context`）

**核心逻辑**：
```python
def context_builder(state: AgentState) -> AgentState:
    """整理上下文"""
    
    # 从 State 提取关键信息
    context = {
        "goal": state["goal"],
        "stock_code": state["stock_code"],
        "strategy_profile": state["strategy_profile"],
        "completed_steps": len(state["decision_history"]),
        "available_observations": list(state["observations"].keys()),
        "last_action": state["decision_history"][-1] if state["decision_history"] else None
    }
    
    # 可选：从 RAG 检索相关历史（第一版占位）
    # history = search_research_memory(state["goal"])
    # context["related_history"] = history
    
    # 生成 LLM 可用的上下文
    state["_context"] = context  # 临时字段，传给 Reasoner
    
    return state
```

**设计要点**：
- 不直接把整个 State 传给 LLM，而是提取关键信息
- 避免上下文过长，保持 LLM 推理清晰
- 后续可扩展：RAG 检索、历史案例注入

---

#### **节点 2: AgentReasoner（推理器）**

**职责**：LLM 推理下一步做什么，只输出决策，不执行

**输入**：`AgentState`（带 `_context`）  
**输出**：更新 `next_action`、`decision_history`、`status`

**核心逻辑**：
```python
def agent_reasoner(state: AgentState) -> AgentState:
    """LLM 推理下一步行动"""
    
    from langchain.agents import create_react_agent
    
    # 构建 prompt（简化版）
    context = state["_context"]
    prompt = f"""
你是一个投资研究助手。当前目标：{context['goal']}

已完成步骤：{context['completed_steps']}
已获取观察：{', '.join(context['available_observations'])}

可用工具：
- evaluate_market_regime: 评估市场环境
- analyze_sector_strength: 分析板块强度
- analyze_stock_fundamentals: 基本面分析
- analyze_stock_technicals: 技术面分析
- run_strategy_backtest: 策略回测
- generate_trade_plan: 生成交易计划
- search_research_memory: 检索历史记录
- add_to_watchlist: 加入观察池（需人工确认）

下一步应该做什么？输出 JSON 格式：
{{
    "thought": "推理过程摘要",
    "action": "工具名称",
    "action_input": {{...}},
    "is_goal_complete": true/false
}}
"""
    
    # 调用 LLM（这里简化，实际用 LangChain Agent）
    # result = agent.invoke(prompt)
    
    # 假设返回：
    result = {
        "thought": "当前已有市场环境和技术面结果，但缺少基本面判断。",
        "action": "analyze_stock_fundamentals",
        "action_input": {"stock_code": "000001", "strategy_profile": "value"},
        "is_goal_complete": False
    }
    
    # 更新 State
    state["next_action"] = {
        "tool": result["action"],
        "input": result["action_input"]
    }
    
    # 记录到决策链
    state["decision_history"].append({
        "step": len(state["decision_history"]) + 1,
        "thought": result["thought"],
        "action": result["action"],
        "action_input": result["action_input"],
        "result": None  # 稍后 ToolExecutor 填充
    })
    
    # 如果目标完成，修改状态
    if result["is_goal_complete"]:
        state["status"] = "completed"
    
    return state
```

**设计要点**：
- 只记录 `thought_summary`，不是完整链路推理
- 输出结构化结果：`thought` + `action` + `action_input` + `is_goal_complete`
- 职责分离：Reasoner 只决策，不执行

---

#### **节点 3: ToolExecutor（工具执行器）**

**职责**：执行工具，更新观察结果

**输入**：`AgentState`（带 `next_action`）  
**输出**：更新 `observations`、`decision_history`、`data_refs`

**核心逻辑**：
```python
def tool_executor(state: AgentState) -> AgentState:
    """执行工具调用"""
    
    action = state["next_action"]
    tool_name = action["tool"]
    tool_input = action["input"]
    
    # 根据 tool_name 调用对应工具
    if tool_name == "evaluate_market_regime":
        from src.tools.market_regime_tool import evaluate_market_regime
        result = evaluate_market_regime(**tool_input)
        state["observations"]["market_regime"] = result
        
    elif tool_name == "analyze_stock_fundamentals":
        from src.tools.fundamentals_tool import analyze_stock_fundamentals
        result = analyze_stock_fundamentals(**tool_input)
        state["observations"]["fundamentals"] = result
        
    elif tool_name == "run_strategy_backtest":
        from src.tools.backtest_tool import run_strategy_backtest
        result = run_strategy_backtest(**tool_input)
        state["observations"]["backtest"] = result
        
    # ... 其他工具
    
    else:
        result = {"tool": tool_name, "status": "error", "message": f"未知工具: {tool_name}"}
    
    # 更新决策链的 result 字段
    state["decision_history"][-1]["result"] = result
    
    # 更新数据引用（如果工具返回了数据路径）
    if "data_ref" in result:
        state["data_refs"][tool_name] = result["data_ref"]
    
    return state
```

**设计要点**：
- 包装底层模块（DataFetcher、JudgmentEngine、BacktestEngine）
- 工具调用失败时返回 error 状态，不抛异常
- 自动更新 `decision_history` 和 `data_refs`

---

#### **节点 4: QualityGate（质量门）**

**职责**：安全检查 + 质量门，决定下一步路由

**输入**：`AgentState`  
**输出**：更新 `status`

**核心逻辑**：
```python
def quality_gate(state: AgentState) -> AgentState:
    """质量门检查"""
    
    # 检查 1：是否达到最大步数
    if len(state["decision_history"]) >= MAX_STEPS:
        state["status"] = "error"
        state["error"] = f"达到最大步数限制 {MAX_STEPS}"
        return state
    
    # 检查 2：是否重复调用同一工具
    recent_actions = [h["action"] for h in state["decision_history"][-3:]]
    if len(recent_actions) >= 2 and recent_actions[-1] == recent_actions[-2]:
        state["status"] = "error"
        state["error"] = f"重复调用工具 {recent_actions[-1]}"
        return state
    
    # 检查 3：单个工具调用次数是否超限
    action_counts = {}
    for h in state["decision_history"]:
        action = h["action"]
        action_counts[action] = action_counts.get(action, 0) + 1
    
    for action, count in action_counts.items():
        if count > MAX_TOOL_CALLS_PER_TOOL:
            state["status"] = "error"
            state["error"] = f"工具 {action} 调用次数超限（{count} > {MAX_TOOL_CALLS_PER_TOOL}）"
            return state
    
    # 检查 4：是否需要人工确认
    if state.get("next_action") and state["next_action"]["tool"] in MUST_REVIEW_TOOLS:
        state["status"] = "waiting_human"
        state["interrupt_history"].append({
            "node": state["next_action"]["tool"],
            "reason": "需要人工确认",
            "timestamp": datetime.now().isoformat(),
            "user_decision": None
        })
        return state
    
    # 检查 5：是否已完成
    if state["status"] == "completed":
        return state
    
    # 检查 6：上一步工具是否执行失败
    last_result = state["decision_history"][-1]["result"]
    if last_result and last_result.get("status") == "error":
        state["status"] = "error"
        state["error"] = f"工具执行失败: {last_result.get('message')}"
        return state
    
    # 默认：继续运行
    state["status"] = "running"
    return state
```

**设计要点**：
- 6 个检查点：最大步数、重复调用、单工具超限、人工确认、任务完成、工具失败
- 根据检查结果修改 `status`，决定路由
- 硬限制保证 Agent 不会无限循环

---

#### **节点 5: HumanReview（人工确认）**

**职责**：人工确认点，等待用户输入

**输入**：`AgentState`（`status == "waiting_human"`）  
**输出**：更新 `status` 和 `interrupt_history`

**核心逻辑**：
```python
def human_review(state: AgentState) -> AgentState:
    """人工确认节点"""
    
    # 这个节点在 LangGraph 里是"中断点"
    # 实际逻辑在 Streamlit UI 层处理
    # 
    # UI 会显示：
    # - 当前 next_action 的内容
    # - 让用户选择：批准 / 拒绝 / 修改
    # 
    # 用户确认后，UI 调用 graph.invoke() 继续执行
    # 这里只需要修改 status，让循环继续
    
    # 假设用户已确认（实际由 UI 更新）
    state["interrupt_history"][-1]["user_decision"] = "approved"
    state["status"] = "running"  # 继续执行
    
    return state
```

**设计要点**：
- 这个节点本身不做任何推理或执行
- 只是 LangGraph 的"中断点"，等待外部输入
- Streamlit UI 负责展示确认界面和更新 State

---

### 3.3 循环逻辑与路由

**条件路由函数**：
```python
def route_after_quality_gate(state: AgentState) -> str:
    """QualityGate 之后的路由逻辑"""
    
    status = state["status"]
    
    if status == "running":
        return "context_builder"  # 继续循环
    elif status == "waiting_human":
        return "human_review"     # 人工确认
    elif status == "completed":
        return END                 # 任务完成
    elif status == "error":
        return END                 # 出错结束
    else:
        return END                 # 未知状态，安全退出
```

**LangGraph 主图定义**（伪代码）：
```python
from langgraph.graph import StateGraph, END

graph = StateGraph(AgentState)

# 添加节点
graph.add_node("context_builder", context_builder)
graph.add_node("agent_reasoner", agent_reasoner)
graph.add_node("tool_executor", tool_executor)
graph.add_node("quality_gate", quality_gate)
graph.add_node("human_review", human_review)

# 设置入口
graph.set_entry_point("context_builder")

# 添加边
graph.add_edge("context_builder", "agent_reasoner")
graph.add_edge("agent_reasoner", "tool_executor")
graph.add_edge("tool_executor", "quality_gate")

# 条件路由
graph.add_conditional_edges(
    "quality_gate",
    route_after_quality_gate,
    {
        "context_builder": "context_builder",
        "human_review": "human_review",
        END: END
    }
)

# HumanReview 之后回到 ContextBuilder
graph.add_edge("human_review", "context_builder")

# 编译
app = graph.compile(checkpointer=MemorySaver())
```

---

### 3.4 硬限制配置

```python
# src/agent/config.py

# 最大步数限制
MAX_STEPS = 8

# 每个工具最多调用次数
MAX_TOOL_CALLS_PER_TOOL = 2

# 必须人工确认的工具
MUST_REVIEW_TOOLS = [
    "add_to_watchlist",              # 加入观察池
    "suggest_framework_update"       # 建议修改判断框架（第二阶段）
]
```

**为什么需要硬限制？**
- 防止 Agent 无限循环（例如反复调用同一工具）
- 控制成本（LLM API 调用费用）
- 保证用户体验（避免等待时间过长）
- 安全边界（第一版 Agent 能力有限，不应过度自主）

---

**Part 3 完成。**

---

## Part 4: 工具层设计

### 4.1 工具列表（8 个）

Agent 可调用的粗粒度工具，按职责分为三类：

#### **第一类：观察类工具（获取事实）**

1. `evaluate_market_regime` - 评估市场环境
2. `analyze_sector_strength` - 分析板块强度
3. `analyze_stock_fundamentals` - 基本面分析
4. `analyze_stock_technicals` - 技术面分析
5. `search_research_memory` - 检索历史记录（占位）

#### **第二类：验证类工具（检验假设）**

6. `run_strategy_backtest` - 策略回测

#### **第三类：决策类工具（生成结果）**

7. `generate_trade_plan` - 生成交易计划
8. `add_to_watchlist` - 加入观察池（需人工确认）

---

### 4.2 工具分类与职责

| 工具名称 | 分类 | 输入 | 输出 | 是否需要人工确认 |
|---------|------|------|------|-----------------|
| evaluate_market_regime | 观察类 | index_code | 市场环境 + 置信度 | 否 |
| analyze_sector_strength | 观察类 | stock_code | 板块强度 + 相对排名 | 否 |
| analyze_stock_fundamentals | 观察类 | stock_code, strategy_profile | 基本面评分 + 关键指标 | 否 |
| analyze_stock_technicals | 观察类 | stock_code | 技术面评分 + 关键信号 | 否 |
| search_research_memory | 观察类 | query, limit | 历史记录（第一版空） | 否 |
| run_strategy_backtest | 验证类 | stock_code, strategy_profile, period | 回测结果 | 否 |
| generate_trade_plan | 决策类 | stock_code, observations | 交易计划 | 否 |
| add_to_watchlist | 决策类 | stock_code, entry_trigger, invalid_condition | 成功/失败 | **是** |

---

### 4.3 工具统一输出格式

所有工具返回统一格式，方便 Agent 解析和记录：

```python
{
    "tool": str,               # 工具名称
    "status": str,             # "success" | "error"
    "message": str,            # 说明信息
    "data": dict,              # 核心数据（每个工具不同）
    "data_ref": str | None,    # 数据引用路径（可选）
    "timestamp": str           # 执行时间
}
```

**示例（基本面分析工具）**：
```python
{
    "tool": "analyze_stock_fundamentals",
    "status": "success",
    "message": "基本面分析完成",
    "data": {
        "score": 75,                    # 综合评分（0-100）
        "pe_ratio": 12.5,               # 市盈率
        "pb_ratio": 1.8,                # 市净率
        "roe": 0.15,                    # 净资产收益率
        "revenue_growth": 0.12,         # 营收增长率
        "industry_relative_rank": 0.68, # 行业相对排名
        "summary": "估值处于行业中等水平，盈利能力良好"
    },
    "data_ref": "cache/000001_financial_20260608.json",
    "timestamp": "2026-06-08T14:32:15"
}
```

---

### 4.4 工具实现方式（包装现有模块）

每个工具包装底层模块（DataFetcher、JudgmentEngine、BacktestEngine），不重复实现业务逻辑。

#### **示例 1: 基本面分析工具**

```python
# src/tools/fundamentals_tool.py

from src.core.data_fetcher import DataFetcher
from src.core.judgment_engine import JudgmentEngine
from datetime import datetime

def analyze_stock_fundamentals(stock_code: str, strategy_profile: str) -> dict:
    """
    基本面分析工具
    
    Args:
        stock_code: 股票代码
        strategy_profile: 策略类型（trend/growth/value）
    
    Returns:
        统一格式的工具输出
    """
    
    try:
        # 1. 拉取数据
        fetcher = DataFetcher()
        financial_data = fetcher.get_financial_data(stock_code)
        valuation_data = fetcher.get_valuation_data(stock_code)
        
        # 2. 调用判断引擎
        engine = JudgmentEngine()
        result = engine.evaluate_fundamentals(
            financial_data=financial_data,
            valuation_data=valuation_data,
            strategy_profile=strategy_profile
        )
        
        # 3. 返回统一格式
        return {
            "tool": "analyze_stock_fundamentals",
            "status": "success",
            "message": "基本面分析完成",
            "data": result,
            "data_ref": f"cache/{stock_code}_financial_{datetime.now().strftime('%Y%m%d')}.json",
            "timestamp": datetime.now().isoformat()
        }
    
    except Exception as e:
        return {
            "tool": "analyze_stock_fundamentals",
            "status": "error",
            "message": f"基本面分析失败: {str(e)}",
            "data": {},
            "data_ref": None,
            "timestamp": datetime.now().isoformat()
        }
```

---

#### **示例 2: 检索历史记录工具（占位）**

```python
# src/tools/research_memory_tool.py

from datetime import datetime
from uuid import uuid4

def search_research_memory(query: str, limit: int = 5) -> dict:
    """
    检索历史研究记录（第一版占位）
    
    Args:
        query: 查询关键词
        limit: 返回结果数量
    
    Returns:
        统一格式的工具输出
    """
    
    # 第一版返回空结果，但明确告知是正常占位
    return {
        "tool": "search_research_memory",
        "status": "success",
        "query": query,
        "limit": limit,
        "message": "第一版暂未接入历史研究记忆，返回空结果。",
        "data": {
            "results": []  # 空列表
        },
        "data_ref": f"memory_search_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}",
        "timestamp": datetime.now().isoformat()
    }
```

**后续接入 RAG 时**，`data.results` 单条记录格式：
```python
{
    "ref_id": "research_20260608_000001",
    "stock_code": "000001",
    "stock_name": "平安银行",
    "created_at": "2026-06-08T14:30:00",
    "strategy_profile": "value",
    "summary": "当时判断估值偏低但技术面偏弱，建议进入观察池等待放量突破。",
    "final_decision": "watchlist",
    "similarity": 0.82,
    "source_type": "research_report"
}
```

---

#### **示例 3: 加入观察池工具（需人工确认）**

```python
# src/tools/watchlist_tool.py

from src.core.watchlist_manager import WatchlistManager
from datetime import datetime

def add_to_watchlist(
    stock_code: str,
    entry_trigger: str,
    invalid_condition: str,
    stop_loss: float = None,
    take_profit: float = None
) -> dict:
    """
    加入观察池工具（需人工确认）
    
    Args:
        stock_code: 股票代码
        entry_trigger: 买入触发条件
        invalid_condition: 失效条件
        stop_loss: 止损价
        take_profit: 止盈价
    
    Returns:
        统一格式的工具输出
    """
    
    try:
        # 调用观察池管理器
        manager = WatchlistManager()
        result = manager.add_to_watchlist(
            stock_code=stock_code,
            entry_trigger=entry_trigger,
            invalid_condition=invalid_condition,
            stop_loss=stop_loss,
            take_profit=take_profit
        )
        
        return {
            "tool": "add_to_watchlist",
            "status": "success",
            "message": f"股票 {stock_code} 已加入观察池",
            "data": result,
            "data_ref": None,
            "timestamp": datetime.now().isoformat()
        }
    
    except Exception as e:
        return {
            "tool": "add_to_watchlist",
            "status": "error",
            "message": f"加入观察池失败: {str(e)}",
            "data": {},
            "data_ref": None,
            "timestamp": datetime.now().isoformat()
        }
```

---

**Part 4 完成。**

---

## Part 5: 核心模块（Core Layer）

### 5.1 保留的模块

从旧架构中保留以下模块，它们是工具层的底层实现：

- `DataFetcher` - 数据获取
- `CacheManager` - 缓存管理
- `JudgmentEngine` - 判断引擎
- `BacktestEngine` - 回测引擎

这些模块**不需要重写**，只需要确保接口清晰，方便工具包装。

---

### 5.2 DataFetcher（数据获取器）

**职责**：从多个数据源（AKShare、Tushare、BaoStock）拉取行情、财务、估值数据。

**核心方法**：
```python
# src/core/data_fetcher.py

class DataFetcher:
    """数据获取器"""
    
    def __init__(self):
        self.cache_manager = CacheManager()
    
    def get_stock_history(self, stock_code: str, days: int = 365, adjust: str = "qfq") -> dict:
        """
        获取股票历史行情
        
        Args:
            stock_code: 股票代码
            days: 获取天数
            adjust: 复权方式（qfq=前复权, hfq=后复权）
        
        Returns:
            {
                "stock_code": str,
                "dates": list[str],
                "open": list[float],
                "high": list[float],
                "low": list[float],
                "close": list[float],
                "volume": list[int],
                "adj_factor": list[float]
            }
        """
        pass
    
    def get_financial_data(self, stock_code: str) -> dict:
        """获取财务数据"""
        pass
    
    def get_valuation_data(self, stock_code: str) -> dict:
        """获取估值数据（PE/PB/PS等）"""
        pass
    
    def get_index_history(self, index_code: str, days: int = 365) -> dict:
        """获取指数历史数据"""
        pass
    
    def get_sector_data(self, stock_code: str) -> dict:
        """获取板块数据"""
        pass
```

---

### 5.3 JudgmentEngine（判断引擎）

**职责**：根据 YAML 配置，对市场环境、基本面、技术面进行评分。

**核心方法**：
```python
# src/core/judgment_engine.py

class JudgmentEngine:
    """判断引擎"""
    
    def __init__(self, config_path: str = "config/judgment_framework.yaml"):
        self.config = self.load_config(config_path)
    
    def evaluate_market_regime(self, index_data: dict) -> dict:
        """
        评估市场环境
        
        Returns:
            {
                "regime": "bull" | "bear" | "sideways",
                "confidence": float,
                "summary": str
            }
        """
        pass
    
    def evaluate_fundamentals(self, financial_data: dict, valuation_data: dict, strategy_profile: str) -> dict:
        """
        基本面评分
        
        Returns:
            {
                "score": float,           # 0-100
                "pe_ratio": float,
                "pb_ratio": float,
                "roe": float,
                "industry_relative_rank": float,
                "summary": str
            }
        """
        pass
    
    def evaluate_technicals(self, price_data: dict) -> dict:
        """
        技术面评分
        
        Returns:
            {
                "score": float,           # 0-100
                "ma_signal": str,         # "golden_cross" | "death_cross" | "neutral"
                "macd_signal": str,
                "volume_signal": str,
                "summary": str
            }
        """
        pass
```

---

### 5.4 BacktestEngine（回测引擎）

**职责**：执行策略回测，严格防未来函数。

**核心方法**：
```python
# src/core/backtest_engine.py

class BacktestEngine:
    """回测引擎"""
    
    def run_backtest(
        self,
        stock_code: str,
        strategy_config: dict,
        start_date: str,
        end_date: str,
        initial_capital: float = 100000.0
    ) -> dict:
        """
        执行回测
        
        Returns:
            {
                "strategy_name": str,
                "stock_code": str,
                "start_date": str,
                "end_date": str,
                "period_days": int,
                "equity_curve": {
                    "dates": list[str],
                    "strategy": list[float],
                    "benchmark": list[float],
                    "stock_prices": list[float]
                },
                "trades": list[dict],
                "performance": {
                    "total_return": float,
                    "annualized_return": float,
                    "sharpe_ratio": float,
                    "max_drawdown": float,
                    "win_rate": float,
                    "trades_count": int
                }
            }
        """
        pass
```

---

### 5.5 CacheManager（缓存管理器）

**职责**：管理本地缓存（文件缓存 + 内存缓存）。

**核心方法**：
```python
# src/core/cache_manager.py

class CacheManager:
    """缓存管理器"""
    
    def __init__(self, cache_dir: str = "data/cache"):
        self.cache_dir = cache_dir
        self.memory_cache = {}  # 内存缓存
    
    def get(self, key: str) -> Any:
        """从缓存读取"""
        pass
    
    def set(self, key: str, value: Any, ttl: int = 3600):
        """写入缓存"""
        pass
    
    def exists(self, key: str) -> bool:
        """检查缓存是否存在"""
        pass
    
    def clear(self, key: str = None):
        """清除缓存"""
        pass
```

---

**Part 5 完成。**

---

## Part 6: 记忆层设计（占位）

### 6.1 research_memory_tool 占位方案

第一版不接入 RAG，但预留接口：

```python
# src/memory/research_memory.py

class ResearchMemory:
    """研究记忆层（第一版占位）"""
    
    def __init__(self, db_path: str = "data/investment_agent.db"):
        self.db_path = db_path
    
    def search(self, query: str, limit: int = 5) -> list[dict]:
        """
        检索历史研究记录（第一版返回空）
        
        Args:
            query: 查询关键词
            limit: 返回结果数量
        
        Returns:
            空列表（第一版占位）
        """
        # 第一版返回空
        return []
    
    def add_record(self, record: dict):
        """
        保存研究记录到数据库
        
        Args:
            record: {
                "stock_code": str,
                "strategy_profile": str,
                "goal": str,
                "decision_history": list,
                "final_decision": str,
                "created_at": str
            }
        """
        # 第一版简单存 SQLite
        pass
```

---

### 6.2 后续 RAG 接入方案

**第二阶段**需要做的事情：

1. **向量数据库选型**：
   - 选项 A：Chroma（轻量级，适合本地部署）
   - 选项 B：Qdrant（性能更好，支持更多特性）
   - 选项 C：Weaviate（云原生，适合规模化）

2. **Embedding 模型**：
   - 中文模型：`text-embedding-3-small`（OpenAI）或 `bge-large-zh`（开源）
   - 文本拆分：按"研究记录"为单位，不拆分

3. **检索策略**：
   - 语义检索：根据 `goal` 查询相似历史案例
   - 过滤条件：`stock_code`、`strategy_profile`、`created_at`
   - 排序：相似度 + 时间衰减

4. **数据存储**：
   - SQLite 存结构化数据（stock_code、strategy_profile、final_decision）
   - 向量数据库存 embedding（goal + summary）

---

## Part 7: 文件结构

### 7.1 完整目录树

```
TraderLens/
├── config/
│   └── judgment_framework.yaml          # 判断框架配置
│
├── src/
│   ├── agent/                           # Agent 核心（Harness）
│   │   ├── __init__.py
│   │   ├── state.py                     # AgentState 定义
│   │   ├── context_builder.py          # ContextBuilder 节点
│   │   ├── reasoner.py                  # AgentReasoner 节点
│   │   ├── executor.py                  # ToolExecutor 节点
│   │   ├── quality_gate.py              # QualityGate 节点
│   │   ├── human_review.py              # HumanReview 节点
│   │   ├── harness.py                   # LangGraph 主图
│   │   └── config.py                    # 硬限制配置
│   │
│   ├── tools/                           # Agent 可调用的工具（8个）
│   │   ├── __init__.py
│   │   ├── market_regime_tool.py        # 评估市场环境
│   │   ├── sector_strength_tool.py      # 分析板块强度
│   │   ├── fundamentals_tool.py         # 基本面分析
│   │   ├── technicals_tool.py           # 技术面分析
│   │   ├── backtest_tool.py             # 策略回测
│   │   ├── trade_plan_tool.py           # 生成交易计划
│   │   ├── watchlist_tool.py            # 加入观察池
│   │   └── research_memory_tool.py      # 检索历史记录（占位）
│   │
│   ├── core/                            # 核心模块（底层实现）
│   │   ├── __init__.py
│   │   ├── data_fetcher.py              # 数据获取
│   │   ├── cache_manager.py             # 缓存管理
│   │   ├── judgment_engine.py           # 判断引擎
│   │   ├── backtest_engine.py           # 回测引擎
│   │   └── watchlist_manager.py         # 观察池管理
│   │
│   ├── memory/                          # 记忆层（为 B 预留）
│   │   ├── __init__.py
│   │   └── research_memory.py           # 第一版占位
│   │
│   └── ui/                              # Streamlit UI
│       ├── app.py                       # 主入口
│       └── pages/
│           ├── research.py              # Tab 1: 投研分析
│           ├── backtest.py              # Tab 2: 策略回测
│           ├── watchlist.py             # Tab 3: 观察池
│           ├── review.py                # Tab 4: 复盘优化
│           └── settings.py              # Tab 5: 系统配置
│
├── data/
│   ├── cache/                           # 本地缓存
│   ├── investment_agent.db              # SQLite 数据库
│   └── checkpoints.db                   # LangGraph checkpoints
│
├── tests/                               # 测试（按模块划分）
│   ├── agent/
│   ├── tools/
│   └── core/
│
├── docs/                                # 设计文档
│   └── specs/
│       └── 2026-06-08-traderlens-agent-design.md
│
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
├── AGENTS.md
└── PROJECT_STRUCTURE.md
```

---

### 7.2 关键文件说明

| 文件 | 职责 |
|------|------|
| `src/agent/harness.py` | LangGraph 主图定义，Agent 执行入口 |
| `src/agent/state.py` | AgentState 类型定义 |
| `src/agent/reasoner.py` | LLM 推理节点，调用 LangChain Agent |
| `src/agent/executor.py` | 工具执行器，根据 action 调用工具 |
| `src/agent/quality_gate.py` | 质量门，6 个安全检查 |
| `src/tools/*.py` | 8 个粗粒度工具，包装底层模块 |
| `src/core/*.py` | 底层模块，保留自旧架构 |
| `src/memory/research_memory.py` | 记忆层占位，后续接 RAG |
| `src/ui/app.py` | Streamlit 主入口，5 个 Tab |
| `config/judgment_framework.yaml` | 判断框架配置（YAML） |

---

## Part 8: MVP 实现计划

### 8.1 第一阶段范围（MVP v0.1）

**目标**：构建 Goal-driven ReAct Agent Harness

**包含功能**：
- ✅ Agent Harness（5 个节点 + 循环逻辑）
- ✅ 8 个粗粒度工具（1 个占位）
- ✅ AgentState 追溯决策链
- ✅ 硬限制（最大步数 8、单工具最多调用 2 次）
- ✅ 人工确认点（加入观察池）
- ✅ Streamlit UI（Tab 1: 投研分析）
- ✅ SQLite 存储（research_history 表）
- ✅ LangGraph checkpoint（中断恢复）

**不包含功能**：
- ❌ 自动修改判断框架
- ❌ 多轮策略优化
- ❌ RAG 历史案例检索（search_research_memory 返回空）
- ❌ Tab 2-5（策略回测、观察池、复盘、配置）

**验收标准**：
1. 用户输入："分析平安银行能不能进观察池"
2. Agent 自主调用 5-7 个工具（市场环境 → 基本面 → 技术面 → 回测 → 交易计划）
3. 生成观察池建议，人工确认后保存
4. 决策链完整记录到 SQLite

---

### 8.2 第二阶段预留（v0.2）

**扩展功能**：
- RAG 接入（向量数据库 + Embedding）
- 回测结果影响策略权重
- 复盘模块自动生成优化建议
- Tab 2-5 完整实现
- 更多工具（suggest_framework_update、compare_strategies）

**架构调整**：
- 无需大改，只需启用反馈逻辑
- `research_memory_tool` 从占位改为真实检索
- `quality_gate` 增加反馈循环检查

---

### 8.3 技术栈与依赖

#### **MVP 核心依赖**

```python
# requirements.txt

# LangGraph 和 LangChain
langgraph>=0.2.0
langchain>=0.3.0
langchain-core>=0.3.0
langchain-openai>=0.2.0       # 如果用 OpenAI
# 或
langchain-anthropic>=0.2.0    # 如果用 Claude

# 数据源
akshare>=1.14.0
tushare>=1.4.0
baostock>=0.8.9

# 数据处理
pandas>=2.1.0
numpy>=1.24.0

# 可视化
streamlit>=1.32.0
plotly>=5.18.0

# 数据库
sqlalchemy>=2.0.0

# 配置管理
pyyaml>=6.0
python-dotenv>=1.0.0

# 工具
python-dateutil>=2.8.0
pytz>=2023.3
```

#### **后续迭代依赖（第二阶段）**

```python
# RAG 相关
chromadb>=0.4.0               # 向量数据库
sentence-transformers>=2.2.0  # Embedding 模型
langchain-chroma>=0.1.0       # LangChain Chroma 集成

# 可选：更好的 Embedding
openai>=1.0.0                 # text-embedding-3-small
# 或
transformers>=4.35.0          # bge-large-zh（本地模型）
```

---

### 8.4 实现优先级

**Phase 1：Agent 核心（1-2 天）**
1. AgentState 定义
2. 5 个节点实现
3. LangGraph 主图编译
4. 简单测试（硬编码工具返回）

**Phase 2：工具层（2-3 天）**
1. 包装 DataFetcher、JudgmentEngine、BacktestEngine
2. 实现 8 个工具
3. 统一输出格式
4. 错误处理

**Phase 3：Streamlit UI（1-2 天）**
1. Tab 1 基本框架
2. 用户输入 goal
3. 实时显示决策链
4. 人工确认界面

**Phase 4：集成测试（1 天）**
1. 端到端测试
2. 修复 bug
3. 优化 prompt

---

**Part 8 完成。**

---

## 设计文档总结

本文档定义了 TraderLens 从"固定工作流"到"真正的 Agent"的完整架构变更：

1. **Part 1**：架构变更说明，MVP v0.1 目标与范围
2. **Part 2**：AgentState 设计（分层结构，记录决策链）
3. **Part 3**：Agent Harness（5 个节点 + 循环逻辑 + 硬限制）
4. **Part 4**：工具层设计（8 个粗粒度工具 + 统一输出格式）
5. **Part 5**：核心模块（保留 DataFetcher、JudgmentEngine、BacktestEngine）
6. **Part 6**：记忆层占位（第一版返回空，第二版接 RAG）
7. **Part 7**：文件结构（完整目录树 + 关键文件说明）
8. **Part 8**：MVP 实现计划（4 个 Phase，预计 5-8 天）

**下一步**：按 brainstorming skill 流程，更新相关文档（README、AGENTS.md、requirements.txt）并提交 git。

