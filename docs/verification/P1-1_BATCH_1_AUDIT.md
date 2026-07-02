# P1-1 Batch 1 Audit Report

## A. /api/agent/workbench/message 当前所有阶段

### New Session 路径（Lines 1076-1158）
1. 创建 session
2. PreScan (line 1089)
3. LLM Intent Extraction (lines 1091-1095)
4. Stock Identity Resolution (lines 1097-1102)
5. Workflow Router (lines 1104-1105)
6. Session title/state/kind 映射 (lines 1107-1122)
7. 记录 5 个 activity artifacts (lines 1124-1158):
   - context_loaded
   - prescan_result
   - intent_extraction
   - stock_identity_resolution
   - workflow_route_decision

### Existing Session 路径（Lines 1180-1274）
1. 加载 session + context (lines 1180-1195)
2. 记录 context_loaded artifact (lines 1197-1204)
3. 重新运行完整 pipeline (lines 1206-1232):
   - PreScan
   - Intent Extraction (deterministic mode)
   - Stock Identity Resolution
   - Workflow Router
4. 记录 4 个 activity artifacts (lines 1234-1274):
   - prescan_result
   - intent_extraction
   - stock_identity_resolution
   - workflow_route_decision

### **⚠️断点 1: Existing Session Handler Dispatch（Lines 1349-1355）**
```python
else:
    # Existing session - for now, use simple continuation logic
    # TODO: implement existing session handler with context
    agent_reply = "继续对话功能开发中。"
    artifact_ids = []
    next_required_user_action = "provide_more_context"
    workflow_kind = route_decision.workflow_kind  # Still use route_decision
```

**影响范围:**
- "帮我看看"（有上一轮股票上下文）→ 应进入 friend_stock handler，实际返回占位回复
- "今天要不要继续拿"（有 open_position）→ 应进入 position_followup handler，实际返回占位回复

**问题:**
- Existing session 完整运行了 pipeline（PreScan → Intent → Stock Identity → Router）
- route_decision 已产生正确裁决
- 但未调用 dispatch_handler，直接返回占位逻辑
- 导致有上下文的 follow-up 消息无法得到正确处理

### Handler Dispatch（Lines 1287-1344，仅 New Session）
1. 存储 user message (lines 1276-1285)
2. 基于 `route_decision.workflow_kind` dispatch 到 6 个 handlers (lines 1289-1344):
   - friend_stock (lines 1294-1302)
   - strategy_idea (lines 1303-1310)
   - execution_feedback (lines 1311-1319)
   - position_followup (lines 1320-1328)
   - theme_research (lines 1329-1336)
   - clarification/unknown (lines 1337-1344)
3. 设置 `workflow_type = workflow_kind` (line 1358)

### 持久化与响应（Lines 1357-1430）
1. 存储 agent message (lines 1361-1370)
2. 创建 artifact refs (lines 1372-1403)
3. 更新 session state（如有变化）(lines 1405-1410)
4. 返回响应 (lines 1412-1430)

---

## B. 所有读取 session.workflow_kind 的位置

**搜索结果:** 0 处业务逻辑读取

```bash
$ grep -n "session\.workflow_kind" backend/api/research.py
# Only comments, no business logic reads
```

**结论:** ✅ 无业务逻辑读取 `session.workflow_kind`

---

## C. 所有写 workflow_type 的位置

**搜索结果:** 1 处赋值

```bash
$ grep -n "workflow_type =" backend/api/research.py
1358:        workflow_type = workflow_kind
```

**Line 1358:**
```python
# CRITICAL: workflow_type MUST == route_decision.workflow_kind (no session.workflow_kind override)
workflow_type = workflow_kind
```

其中 `workflow_kind` 来自：
- **New session:** `workflow_kind = route_decision.workflow_kind` (line 1291)
- **Existing session:** `workflow_kind = route_decision.workflow_kind` (line 1355)

**结论:** ✅ `workflow_type` 唯一来源是 `route_decision.workflow_kind`，无覆盖操作

---

## D. 所有可能覆盖 route_decision 的位置

**搜索结果:** 0 处覆盖

```bash
$ grep -n "route_decision =" backend/api/research.py
1104:            route_decision = router.route(prescan, intent_extraction, stock_identity)
1232:            route_decision = router.route(prescan, intent_extraction, stock_identity)
```

**创建点:**
- Line 1104: New session
- Line 1232: Existing session

**使用点:**
- Line 1291: `workflow_kind = route_decision.workflow_kind` (new session)
- Line 1348: `next_required_user_action = handler_result.next_required_user_action or route_decision.next_required_user_action`
- Line 1355: `workflow_kind = route_decision.workflow_kind` (existing session)

**结论:** ✅ `route_decision` 创建后只读，未被修改

**⚠️断点 2: Existing Session 未进入 Dispatch**

虽然 `route_decision` 未被覆盖，但 existing session 路径（lines 1349-1355）直接返回占位逻辑，未进入 dispatch_handler 分支（lines 1289-1344），导致 `route_decision` 的裁决结果未被执行。

---

## E. Handler 调用的 Service + 真实构造函数签名

### **⚠️ 问题 1: handle_friend_stock - Service 初始化参数不匹配**

**Handler 代码 (backend/api/workbench_handlers.py, lines 30-31):**
```python
from backend.services.friend_stock_flow_service import FriendStockFlowService
# ...
friend_stock_service = FriendStockFlowService(
    db_conn=db_conn,
    serenity_runner=None,  # TODO: inject from DI container
)
```

**Service 真实签名 (backend/services/friend_stock_flow_service.py, lines 45-52):**
```python
def __init__(
    self,
    validator: StockPickValidator,
    serenity_runner: SerenityRunner | None,
    market_data_provider: MarketDataProvider | None = None,
):
    self.validator = validator
    self.serenity_runner = serenity_runner
    self.market_data_provider = market_data_provider
```

**不匹配点:**
- Handler 传入: `db_conn`, `serenity_runner`
- 真实签名要求: `validator`, `serenity_runner`, `market_data_provider`
- Handler 缺少 `validator` 参数
- Handler 传入的 `db_conn` 不被接受

**阻塞影响:**
- `handle_friend_stock` 调用会在运行时失败（TypeError: missing required argument 'validator'）
- 所有 friend_stock 路由的消息无法处理

---

### **⚠️ 问题 2: Handler 使用错误的 route_decision 字段**

**WorkbenchRouteDecision 真实字段 (backend/services/workbench_workflow_router.py, line 33):**
```python
class WorkbenchRouteDecision(BaseModel):
    workflow_kind: Literal[...]
    workflow_state: str
    route_reason: str  # ← 正确字段名
    next_required_user_action: str
    allowed_to_start_workflow: bool
```

**Handler 错误使用 (backend/api/workbench_handlers.py):**

**Line 47:**
```python
agent_reply = f"无法识别股票信息。{route_decision.reason}"
#                                              ^^^^^^ 错误字段
```

**Line 442:**
```python
agent_reply = f"{route_decision.reason}\n\n你好，我可以帮你：\n1. 分析朋友推荐的股票（提供股票代码或公司名）\n2. 验证策略/交易想法的技术细节\n\n请问你想了解什么？"
#               ^^^^^^^^^^^^^^^^^^^^^ 错误字段
```

**正确字段应为:** `route_decision.route_reason`

**阻塞影响:**
- 运行时 AttributeError: 'WorkbenchRouteDecision' object has no attribute 'reason'
- 影响 `handle_friend_stock` 和 `handle_clarification` 的回复生成

---

### 其他 Handlers（无 Service 初始化问题）

**handle_strategy_idea (lines 178-179):**
```python
from backend.services.strategy_idea_service import StrategyIdeaFlowService
# ...
strategy_service = StrategyIdeaFlowService()
```
✅ 匹配 — StrategyIdeaFlowService 无 `__init__` 方法，使用默认构造函数（无参数）

**handle_execution_feedback:** ✅ 无 service 调用

**handle_position_followup:** ✅ 无 service 调用

**handle_theme_research_deferred:** ✅ 无 service 调用

**handle_clarification:** ✅ 无 service 调用（但有 `route_decision.reason` 字段错误，见上）

---

## F. 文件清理项

**必须删除的文件:**
- `backend/api/research.py.backup_before_refactor`
  - 大小: 99K
  - 创建时间: Jul 2 15:07
  - 原因: backup 文件不应提交到版本库

```bash
$ ls -lh backend/api/research.py.backup_before_refactor
-rwxrwxrwx 1 legion legion 99K Jul  2 15:07 backend/api/research.py.backup_before_refactor
```

---

## 审查结论

### 单一裁决源方向

**已部分建立:**
- ✅ `route_decision` 是唯一裁决产生点
- ✅ `workflow_type` 唯一来源是 `route_decision.workflow_kind`
- ✅ 无 `session.workflow_kind` 业务逻辑读取
- ✅ 无 `route_decision` 中间覆盖

**未收口部分:**
- ❌ **Existing session dispatch 未收口** (lines 1349-1355)
  - 问题: 已运行完整 pipeline 并产生 `route_decision`，但未调用 handler
  - 影响: 有上下文的 follow-up 消息（"帮我看看"、"今天要不要继续拿"）无法得到正确处理
  - 占位逻辑: `agent_reply = "继续对话功能开发中。"`

- ❌ **Handler/Service 接线未收口**
  - 问题 1: `handle_friend_stock` 的 `FriendStockFlowService` 初始化参数不匹配
    - Handler 传入: `db_conn`, `serenity_runner`
    - 真实签名要求: `validator`, `serenity_runner`, `market_data_provider`
  - 影响: 运行时 TypeError，所有 friend_stock 路由消息无法处理

- ❌ **Handler route_decision 字段契约未收口**
  - 问题: Handler 使用 `route_decision.reason`（错误字段）
  - 正确字段: `route_decision.route_reason`
  - 位置: backend/api/workbench_handlers.py lines 47, 442
  - 影响: 运行时 AttributeError，影响 `handle_friend_stock` 和 `handle_clarification`

- ❌ **Backup 文件未清理**
  - 文件: `backend/api/research.py.backup_before_refactor`
  - 大小: 99K
  - 应删除

---

## 第二批实施前置条件

第一批审查已完成并交回。

**阻塞项（必须在第二批修复）:**
1. Existing session dispatch 收口（调用 handler 而非返回占位逻辑）
2. `handle_friend_stock` service 初始化参数修复
3. Handler `route_decision.reason` → `route_decision.route_reason` 字段修复
4. 删除 backup 文件

**验收标准（第二批交付时）:**
- 11 条用例全部路由正确
- friend_stock 和 strategy_idea 有真实 DB 记录 id
- Existing session 能正确调用 handler
- Timeline artifact 可读回 route_decision
- 工作区干净（无 backup 文件）
- Commit hash 可追溯
