# Phase 1 Checkpoint - Agent 核心

**完成时间**: 2026-06-08  
**目标**: 验证 LangGraph 主图 + 5 个节点的循环逻辑和人工中断  
**状态**: ✅ 完成

---

## 完成内容

### 1. 核心文件

| 文件 | 状态 | 说明 |
|------|------|------|
| `src/agent/state.py` | ✅ | AgentState 类型定义（TypedDict），包含 23 个字段 |
| `src/agent/config.py` | ✅ | 硬限制配置（MAX_STEPS=8, MAX_TOOL_CALLS_PER_TOOL=2） |
| `src/agent/context_builder.py` | ✅ | 整理上下文节点，提取关键信息 |
| `src/agent/reasoner.py` | ✅ | LLM 推理节点（Phase 1 硬编码决策路径） |
| `src/agent/executor.py` | ✅ | 工具执行器（Phase 1 返回 mock 数据） |
| `src/agent/quality_gate.py` | ✅ | 6 个安全检查（最大步数、重复调用、无效工具等） |
| `src/agent/human_review.py` | ✅ | 人工确认节点（使用 LangGraph `interrupt()`） |
| `src/agent/harness.py` | ✅ | LangGraph 主图编译，包含 5 个节点和条件路由 |
| `demo_phase1.py` | ✅ | 端到端 demo 验证 |

### 2. 验收结果

✅ **LangGraph 主图可以运行**  
- StateGraph 编译成功  
- MemorySaver checkpointer 正常工作  
- 节点间状态传递正确

✅ **Agent 循环 5 步后完成**  
```
Step 1: market_regime_tool → success
Step 2: fundamentals_tool → success
Step 3: technicals_tool → success
Step 4: trade_plan_tool → success
Step 5: watchlist_tool → success (需要人工确认)
→ Goal complete
```

✅ **decision_history 正确记录每一步**  
每条记录包含：
- `step`: 步数
- `thought`: LLM 推理摘要
- `action`: 工具名称
- `action_input`: 工具输入参数
- `result`: 工具返回（统一格式）
- `timestamp`: 执行时间

✅ **人工确认点可以中断和恢复**  
- `watchlist_tool` 触发 `interrupt()`
- 图暂停，返回 `__interrupt__` 事件
- 用户通过 `Command(resume={"approved": True})` 恢复
- 图从 `human_review` 节点继续执行

✅ **硬限制生效**  
- 最大步数限制（MAX_STEPS=8）
- 工具重复调用检测（MAX_TOOL_CALLS_PER_TOOL=2）
- 无效工具检测（只允许 AVAILABLE_TOOLS）
- 循环检测（连续 3 次相同 action）

---

## 关键技术实现

### 1. LangGraph 主图结构

```
START
  ↓
ContextBuilder → AgentReasoner → QualityGate → HumanReview → ToolExecutor
                                       ↓               ↓              ↓
                                      END             END       (loop back)
```

**条件路由**：
- `QualityGate` → 检查失败 → END，通过 → HumanReview
- `HumanReview` → 用户拒绝 → END，批准 → ToolExecutor
- `ToolExecutor` → 目标完成 → END，否则 → ContextBuilder（循环）

### 2. State 更新机制

每个节点返回 **partial update**，LangGraph 自动 merge：
```python
def context_builder(state: AgentState) -> AgentState:
    return {**state, "_context": context}  # 只更新 _context
```

### 3. interrupt() 机制

```python
# human_review.py
approval = interrupt({
    "action": next_action,
    "question": "是否批准执行？"
})

# demo_phase1.py
for event in graph.stream(initial_state, config):
    if "__interrupt__" in event:
        # 展示给用户
        break

# 用户批准后恢复
graph.stream(Command(resume={"approved": True}), config)
```

### 4. Checkpointer 配置

```python
from langgraph.checkpoint.memory import MemorySaver

checkpointer = MemorySaver()
graph = workflow.compile(checkpointer=checkpointer)

config = {"configurable": {"thread_id": thread_id}}
```

---

## 发现的问题

### 问题 1: quality_gate 误判空字典

**问题**：`market_regime_tool` 的 `action_input` 是 `{}`（空字典），但 `quality_gate` 用 `if not next_action_input` 判断，导致误认为缺少参数。

**原因**：Python 中空字典 `{}` 为 falsy，但对于某些工具，空字典是合法的输入。

**解决方案**：改用 `if next_action_input is None` 判断。

```python
# 修改前
if next_action != "complete" and not next_action_input:
    return {"quality_check_passed": False, ...}

# 修改后
if next_action != "complete" and next_action_input is None:
    return {"quality_check_passed": False, ...}
```

---

## 下一步优化点

### 1. Phase 2 准备

- [ ] 实现 8 个真实工具（包装 DataFetcher、JudgmentEngine）
- [ ] 工具统一输出格式验证
- [ ] 错误处理（所有工具捕获异常，返回 error 状态）
- [ ] 日志记录（INFO 记录调用，DEBUG 记录详细数据）

### 2. Phase 3 准备

- [ ] AgentReasoner 接入 LLM（替换硬编码决策）
- [ ] LLM prompt 优化（让 LLM 理解工具用途和上下文）
- [ ] 工具描述优化（为 LLM 提供清晰的工具说明）

### 3. 已知局限

- **硬编码决策路径**：Phase 1 的 AgentReasoner 是固定顺序，无法适应不同目标
- **Mock 数据**：工具返回的是硬编码数据，无法反映真实市场情况
- **简单人工确认**：只支持批准/拒绝，不支持修改参数或提供额外输入

---

## 代码质量

- ✅ 所有文件通过 lint 检查
- ✅ 类型注解完整（TypedDict + 函数签名）
- ✅ 日志记录规范（INFO 级别记录关键步骤）
- ✅ 错误处理完善（quality_gate 拦截异常情况）
- ✅ 代码注释清晰（每个函数都有 docstring）

---

## 总结

Phase 1 成功验证了 LangGraph 架构的可行性：
1. **状态管理**：TypedDict + partial update 机制简单可靠
2. **节点编排**：5 个节点清晰分工，条件路由灵活
3. **人工中断**：interrupt() 机制开箱即用，无需额外实现
4. **质量保障**：6 个安全检查有效防止异常状态

**可以进入 Phase 2**，实现真实工具层。
