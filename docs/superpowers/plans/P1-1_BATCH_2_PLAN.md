# P1-1 第二批实施计划

## 目标

实现 Workbench 编排链，修复 fake progress，确保每一步有真实动作或明确等待状态。

---

## 第二批要求回顾

1. **Session context:** 进入即加载最近消息/workflow_state/claimed_stock/claimed_strategy/open_positions
2. **单次 LLM 提取:** 每条消息最多 1 次 LLM 调用，输出固定契约；公司名/代码只填 claimed_ 字段，verified_ticker 只能由 Tushare 核验产生；回复用模板填充，禁止第二次 LLM 生成回复
3. **Router 确定性裁决:** friend_stock/strategy_idea/execution_feedback/position_followup/theme_research(deferred)/clarification/stopped
4. **PreScan 与 LLM 冲突以 PreScan 为准**
5. **friend_stock:** 创建 research_case（落库）+ 真实 job 或明确 failed/waiting，禁止只写 researching
6. **strategy_idea:** 创建 idea 记录 + 提取结果，无模板 → rejected/waiting，禁止只写 validating
7. **PreScan 短路:** 仅限高置信执行反馈；短路禁止静默建仓，无对应持仓/审批时降级 clarification
8. **失败路径全部实现:** LLM 不可解析JSON/超时 → extraction_failed+clarification；已有持仓又说买入 / 说卖出但无持仓 → clarification，不重复建仓/不建负仓
9. **Timeline 每步活动:** context_loaded/prescan_result/intent_extraction/stock_identity_resolution/route_decision/workflow_action_started|failed|completed

---

## 实施任务

### Task 1: 修复 workbench_message 端点

**文件:** `backend/api/research.py`

**修改点:**
1. 加载 session context（最近 5 条消息、workflow_state、claimed_stock/strategy、open_positions）
2. 使用真实 Tushare client（移除 test_fixture hardcode）
3. PreScan 短路逻辑（高置信执行反馈）
4. 单次 LLM 调用后用模板生成回复（不再调第二次 LLM）
5. friend_stock 路径：创建 research_case + 真实 job（如果有 serenity_runner）或明确 waiting
6. strategy_idea 路径：创建 idea 记录 + 提取结果
7. Timeline 记录每步活动
8. 失败路径：extraction_failed、clarification、stopped

**验证:**
- 9 条输入测试用例
- 每条输入返回 {intent, route, workflow_state}
- friend_stock 和 strategy_idea 各有一条 DB record id

### Task 2: 补充 research_case 创建逻辑

**文件:** `backend/db/agent_workbench.py`（或新增）

**功能:**
- `create_research_case(ticker, company_name, source_note)` → research_case_id
- 返回 DB record id 供验证

### Task 3: 补充 strategy_idea 创建逻辑

**文件:** `backend/db/agent_workbench.py`（或新增）

**功能:**
- `create_strategy_idea(strategy_text, extracted_rules)` → idea_id
- 返回 DB record id 供验证

### Task 4: Timeline 活动记录

**文件:** `backend/db/agent_workbench.py`

**功能:**
- `record_timeline_activity(session_id, activity_type, payload)` → activity_id
- 活动类型：context_loaded、prescan_result、intent_extraction、stock_identity_resolution、route_decision、workflow_action_started、workflow_action_failed、workflow_action_completed

### Task 5: 测试验证

**测试用例（9 条）:**
1. "帮我看宏昌电子是否值得买入"
2. "帮我看603002"
3. "朋友推荐了宏昌电子"
4. "买入宏昌电子可以吗"
5. "刷到策略下午两点半买第二天卖"
6. "已买入100股成交价12.34"
7. "今天要不要继续拿"
8. "帮我看看"
9. "你好"

**验证输出:**
- 9x3 表格：{intent, route, workflow_state}
- friend_stock 一条 DB record id
- strategy_idea 一条 DB record id
- LLM 调用次数统计

---

## 执行顺序

1. Task 1: 修复 workbench_message 端点（核心）
2. Task 2-3: 补充 DB 操作
3. Task 4: Timeline 记录
4. Task 5: 测试验证

---

## 停止条件

- 测试不通过
- 发现设计文档矛盾
- 需要用户决策参数
