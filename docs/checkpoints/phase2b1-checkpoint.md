# Phase 2B-1 Checkpoint: Watchlist Tool + 人工确认流程

**完成时间**: 2026-06-08  
**状态**: ✅ 完成

---

## 目标

实现 `watchlist_tool` 并验证人工确认流程：
- SQLite CRUD 操作（添加、列表、更新、查询）
- Agent 生成 trade_plan 后提出添加到观察池
- QualityGate 拦截并进入 `waiting_human` 状态
- 用户批准后写入数据库
- 用户拒绝时不写入数据库
- `decision_history` 记录人工审批结果

---

## 实现内容

### 1. 数据库初始化 (`src/core/db_init.py`)

```python
def init_database(db_path: str = "data/investment_agent.db")
def get_connection(db_path: str = "data/investment_agent.db")
```

**表结构**:
```sql
CREATE TABLE watchlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_code TEXT NOT NULL,
    stock_name TEXT,
    strategy_profile TEXT,
    status TEXT NOT NULL DEFAULT 'watching',
    entry_trigger TEXT,
    invalid_condition TEXT,
    stop_loss TEXT,
    take_profit TEXT,
    position_plan TEXT,
    reason_summary TEXT,
    risk_summary TEXT,
    source_run_id TEXT,
    next_review_date DATE,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

**索引**:
- `idx_watchlist_stock_code` on `stock_code`
- `idx_watchlist_status` on `status`

**预留表**（Phase 3）:
- `research_history` - 投研历史记录
- `backtest_results` - 回测结果

---

### 2. Watchlist Tool (`src/tools/watchlist_tool.py`)

实现 4 个函数：

#### `add_to_watchlist()`
- 添加股票到观察池（**需人工确认**）
- 从 `trade_plan` 提取：entry_trigger, stop_loss, take_profit, position_plan, reason_summary
- 生成 invalid_condition（跌破止损位）
- 返回统一格式（含 `data_refs`）

#### `list_watchlist()`
- 列出观察池（可按状态筛选）
- 支持 limit 参数

#### `update_watchlist_status()`
- 更新观察池状态（watching → triggered/invalid/archived）

#### `get_watchlist_item()`
- 获取单条观察池记录（完整字段）

---

### 3. 人工确认流程

#### 修改 `config.py`
```python
MUST_REVIEW_TOOLS = [
    "watchlist_tool",  # 统一使用工具名（而非函数名）
    "suggest_framework_update"
]
```

#### 更新 `quality_gate.py`
添加检查 7：人工确认拦截
```python
if next_action in MUST_REVIEW_TOOLS:
    return {
        **state,
        "quality_check_passed": True,
        "status": "waiting_human",
        "quality_check_message": f"工具 {next_action} 需要人工确认"
    }
```

#### 更新 `human_review.py`
在批准/拒绝后，记录到 `decision_history`：
```python
new_decision = {
    "step": len(state["decision_history"]) + 1,
    "action": f"human_review_{next_action}",
    "thought": f"用户{'批准' if approved else '拒绝'}了 {next_action}",
    "action_input": {},
    "result_summary": "批准" if approved else "拒绝"
}
```

---

### 4. Executor 更新

#### 修改 `observations` 存储格式
**之前**: 只保存 `tool_result.get("result", {})`  
**现在**: 保存完整工具返回（包含 `status`, `summary`, `signals`, `data_refs`）

```python
observations[next_action] = tool_result  # 完整工具返回
```

#### 同步更新工具调用代码
需要从完整工具返回中提取 `result`：
```python
market_regime = observations.get("market_regime_tool", {}).get("result", {})
technicals = observations.get("technicals_tool", {}).get("result", {})
trade_plan = observations.get("trade_plan_tool", {}).get("result", {})
```

#### 集成 `watchlist_tool`
```python
elif tool_name == "watchlist_tool":
    from tools.watchlist_tool import add_to_watchlist
    observations = state["observations"]
    trade_plan = observations.get("trade_plan_tool", {}).get("result", {})
    return add_to_watchlist(
        stock_code=tool_input["stock_code"],
        trade_plan=trade_plan,
        strategy_profile=tool_input.get("strategy_profile", "trend"),
        stock_name=tool_input.get("stock_name"),
        source_run_id=state.get("run_id")
    )
```

---

## 验收测试

**测试脚本**: `test_phase2b1_watchlist.py`

### ✅ Test 1: Agent 运行到 interrupt（等待人工确认）
- Agent 执行顺序：market_regime → fundamentals → technicals → trade_plan → **watchlist_tool (waiting_human)**
- QualityGate 正确拦截 `watchlist_tool`
- 状态变为 `waiting_human`
- `decision_history` 包含前 4 个工具的执行记录

### ✅ Test 2: 用户批准，Agent 继续执行并写入数据库
- 用户批准：`Command(resume={"approved": True})`
- Agent 继续执行 `watchlist_tool`
- 数据库成功写入记录（返回 `watchlist_id`）
- `decision_history` 新增 2 条记录：
  - `human_review_watchlist_tool` (result_summary: "批准")
  - `watchlist_tool` (完整工具返回)
- `observations["watchlist_tool"]` 保存完整工具返回（含 `status: success`）
- 目标标记为完成（`is_goal_complete: True`）

### ✅ Test 3: 验证数据库记录
- `list_watchlist(status="watching")` 返回 3 条记录（包含测试写入的记录）
- `get_watchlist_item(watchlist_id)` 返回完整字段：
  - `stock_code: 000001`
  - `status: watching`
  - `entry_trigger, stop_loss, take_profit` 正确
  - `reason_summary` 包含市场环境和技术面分析

### ✅ Test 4: 测试用户拒绝场景
- 新 thread 分析 `000002 万科A`
- 运行到 `waiting_human` 状态
- 记录拒绝前观察池数量
- 用户拒绝：`Command(resume={"approved": False})`
- Agent 状态变为 `failed`
- `error_message: "用户拒绝了操作"`
- 观察池数量未增加（拒绝时不写入数据库）

---

## 关键设计决策

### 1. 工具名称约定
统一使用 `{功能}_tool` 作为工具名（如 `watchlist_tool`），而不是函数名（`add_to_watchlist`）。  
**原因**: `reasoner` 的 `next_action` 是工具名，`config.py` 的 `MUST_REVIEW_TOOLS` 需要匹配。

### 2. observations 存储完整工具返回
**之前**: 只存 `result` 字段  
**现在**: 存完整工具返回（含 `status`, `summary`, `signals`, `data_refs`）

**好处**:
- 保留数据溯源信息（`data_refs`）
- 保留工具执行状态（`status`）
- 保留关键信号（`signals`）
- 便于调试和审计

**代价**: 访问实际数据时需要多一层 `.get("result")`

### 3. 人工审批记录独立条目
在 `decision_history` 中，人工审批单独记录一条：
```python
{
    "action": "human_review_watchlist_tool",
    "result_summary": "批准"
}
```

**好处**:
- 审计追溯：明确记录谁在何时批准/拒绝了什么操作
- 时间戳分离：人工审批时间 ≠ 工具执行时间
- 语义清晰：`human_review_*` 前缀区分于工具调用

### 4. 拒绝时不写入数据库
`human_review` 节点拒绝时：
- 设置 `status: failed`
- 设置 `error_message: "用户拒绝了操作"`
- 图终止（`_should_continue_after_human_review` 返回 `"end"`）
- `tool_executor` 不执行（跳过写库操作）

---

## 新增文件

```
src/
├── core/
│   └── db_init.py                  # 数据库初始化
└── tools/
    └── watchlist_tool.py           # 观察池 CRUD
```

---

## 修改文件

```
src/
├── agent/
│   ├── config.py                   # MUST_REVIEW_TOOLS 改为 "watchlist_tool"
│   ├── quality_gate.py             # 添加检查 7（人工确认拦截）
│   ├── human_review.py             # 记录审批结果到 decision_history
│   └── executor.py                 # (1) observations 存完整工具返回
                                     # (2) 集成 watchlist_tool
                                     # (3) 提取 result 时加 .get("result")
```

---

## 数据库状态

**路径**: `data/investment_agent.db`

**表**: 
- `watchlist` (已创建，有 3 条测试记录)
- `research_history` (已创建，空)
- `backtest_results` (已创建，空)

**测试数据**（`status=watching`）:
1. ID=1: 未知股票（之前测试遗留）
2. ID=2: 000001 平安银行
3. ID=3: 000001 平安银行（Test 2 写入）

---

## 下一步：Phase 2B-2

**目标**: 实现 `backtest_tool`

**依赖**:
- ✅ `cache_manager` (Phase 2A+)
- ✅ `data_fetcher` (Phase 2A)
- ✅ `watchlist_tool` (Phase 2B-1)

**实现内容**:
1. 策略回测引擎（基于交易计划）
2. 回测结果计算（总收益、夏普比率、最大回撤、胜率）
3. 保存回测结果到 `backtest_results` 表
4. 返回统一格式（含 `data_refs`）

**验收标准**:
- [ ] Agent 生成 trade_plan 后，会提出 backtest_tool
- [ ] 回测逻辑正确（入场/出场/止损/止盈触发）
- [ ] 指标计算正确（收益率、夏普比率、最大回撤、胜率）
- [ ] 结果保存到数据库
- [ ] mock 模式下能正常运行

---

## 总结

Phase 2B-1 成功实现了：
1. ✅ SQLite 观察池管理（CRUD 完整）
2. ✅ 人工确认流程（QualityGate 拦截 + HumanReview interrupt）
3. ✅ decision_history 记录审批结果
4. ✅ 拒绝时不写入数据库
5. ✅ observations 存储完整工具返回（含数据溯源信息）

**关键里程碑**: 
- Agent 首次与外部持久化存储（SQLite）交互
- 人工确认流程首次端到端验证
- 为后续工具（backtest, sector, fundamentals）提供了标准模式
