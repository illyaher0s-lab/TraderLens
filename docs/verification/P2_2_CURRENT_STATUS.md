# P2-2 Friend Stock to Observation - Current Status Report

**Date**: 2026-07-06  
**Status**: ⚠️ BLOCKED - Business Logic Gap  
**Branch**: `feat/p2-1-observation-pool-page`

---

## Executive Summary

P2-2 验收脚本已创建并运行，但发现 **friend_stock → observation pool 自动创建 position 的业务逻辑尚未实现**。

当前状态：
- ✅ 验收脚本基础设施完整（端口管理、Playwright、证据生成）
- ✅ Backend 和 Frontend 正常启动
- ✅ Workbench 可以接受并处理"帮我看看宏昌电子并加入观察池"的请求
- ❌ Backend 返回 `flow_*` (研究流程) 而不是 `pos_*` (position)
- ❌ 无法验证 position 写入 DB
- ❌ 无法验证 /api/observations 返回
- ❌ 无法验证 /observations 页面显示

---

## 验收尝试记录

### Run 1: P2RUN_20260706_162856
**输入**: 两句话模式
1. "帮我看看宏昌电子（603002），备注 P2RUN_20260706_162856"
2. "加入观察"

**结果**: 第二句超时（UI 状态问题）

### Run 2: P2RUN_20260706_163039
**输入**: 两句话模式 + 页面刷新
1. "帮我看看宏昌电子（603002），备注 P2RUN_20260706_163039"
2. "把宏昌电子加入观察池"

**结果**: 
- 第二句返回 200
- artifact_ids: `['clarify_3191b5c6', ...]`
- 说明：Backend 返回澄清请求，未创建 position

### Run 3: P2RUN_20260706_163149
**输入**: 单句话模式
- "帮我看看宏昌电子（603002）并加入观察池，备注 P2RUN_20260706_163149"

**结果**: 
- 返回 200
- artifact_ids: `['clarify_b7846c74', ...]`
- 说明：仍然返回澄清，未创建 position

### Run 4: P2RUN_20260706_163258
**输入**: 单句话模式（同 Run 3）

**结果**: 
- 返回 200
- artifact_ids: `['flow_40f6c5ae61da', 'msg_...', 'intent_sess_...']`
- 说明：Backend 创建了研究流程（`flow_*`），但未创建 position（`pos_*`）

---

## 技术分析

### Backend 返回内容

```json
{
  "conversation_id": "...",
  "workflow_type": "...",
  "stage": "...",
  "agent_reply": "...",
  "approval_card": "...",
  "artifact_ids": [
    "flow_40f6c5ae61da",    // 研究流程 artifact
    "msg_98d39b9234cb",     // 消息 artifact
    "msg_1b53d27a33a5",     // 消息 artifact
    "intent_sess_9883ddad2891"  // 意图 session artifact
  ],
  "next_required_user_action": "..."
}
```

### 缺失的 Artifact

预期应有：
- `pos_*` (observation_position artifact)
- 写入 `observation_positions` 表

实际返回：
- `flow_*` (friend_stock_flow artifact)
- 未创建 position

---

## 业务逻辑缺口

根据 `docs/superpowers/specs/2026-07-02-agent-entry-design-freeze.md`：

**Friend Stock Flow** 设计为：
1. 用户："帮我看看宏昌电子"
2. Agent 触发 `friend_stock_flow`（研究/推荐）
3. 返回研究结果

**Add to Observation** 设计为：
1. Friend stock flow 完成后
2. 用户明确表达"加入观察"
3. Agent 创建 `observation_position`

**当前状态**：
- Friend stock flow 可以触发（返回 `flow_*`）
- **Add to observation 逻辑未实现**（无论单句还是多句，都不创建 `pos_*`）

---

## 对比：已实现的 Execution Feedback 流程

P2-1A/B/C/D 验收的是 **execution_feedback** 流程：

**输入**: "已买入宏昌电子（603002）100 股，成交价 12.34"

**Backend 行为**:
1. route_decision 识别为 `execution_feedback`
2. 创建 `execution_observation_log`
3. 创建 `observation_position`
4. 返回 `pos_*` artifact

**成功标准**: ✅ 全部通过（P2-1A exit code 0）

---

## 实现 Gap

要让 P2-2 验收通过，需要实现：

### 1. Router 识别"加入观察"意图

**当前**: 
- "帮我看看 X 并加入观察池" → 触发 `friend_stock_flow`
- "加入观察" → 触发 `clarify`

**需要**:
- "加入观察" + context (之前研究过 X) → 触发 `add_to_observation`

### 2. Add to Observation Handler

**当前**: 不存在

**需要**:
```python
async def handle_add_to_observation(
    context: SessionContext,
    stock_info: StockIdentity
) -> WorkbenchResponse:
    # 创建 observation_position
    position = create_observation_position(
        symbol=stock_info.symbol,
        name=stock_info.name,
        entry_thesis=f"用户主动加入观察：{user_message}",
        ...
    )
    
    # 返回 pos_* artifact
    return {
        "artifact_ids": [f"pos_{position.position_id}", ...],
        ...
    }
```

### 3. Session Context 支持

**当前**: 可能不完整

**需要**:
- Friend stock flow 完成后，context 记住研究的股票
- 后续"加入观察"可以引用 context 中的股票

---

## 验收脚本状态

**脚本路径**: `scripts/verify_p2_2_friend_stock_to_observation.py`

**当前能力**:
- ✅ 自动启动 backend/frontend
- ✅ 端口自动清理
- ✅ Playwright 输入和交互
- ✅ Run ID 数据隔离
- ✅ 证据文件生成框架

**阻塞点**:
- ❌ Backend 不返回 `pos_*`
- ❌ 无法继续验证后续链路

**Exit Code**: 1 (失败)

---

## 建议

### 选项 A: 实现 Add to Observation 逻辑

**工作量**: 中等
1. 在 `workbench_router.py` 添加 `add_to_observation` 识别
2. 创建 `add_to_observation_handler.py`
3. 复用 `observation_position` DB 层
4. 确保 session context 传递股票信息

**验收**: 修改后重新运行 P2-2 脚本，期望 exit code 0

### 选项 B: 调整 P2-2 验收范围

**工作量**: 小
1. P2-2 验收仅验证 friend_stock flow 触发
2. 不验证 position 创建
3. 标记为"部分实现"

**验收**: 修改脚本接受 `flow_*` 作为成功标准

### 选项 C: 先验证已有流程

**工作量**: 最小
1. P2-2 改为验证 execution_feedback → observation（已实现）
2. Friend stock → observation 等业务逻辑补齐后再验证

**验收**: 复用 P2-1A 的成功模式

---

## 当前建议

推荐 **选项 A**，理由：
1. P2-2 是核心业务闭环，必须打通
2. 验收脚本已就绪，只差业务逻辑
3. 工作量可控（复用现有 DB 层）
4. 一旦实现，立即可验收

---

## 下一步

等待决策：
- [ ] 实现 Add to Observation 逻辑
- [ ] 调整 P2-2 验收范围
- [ ] 改为验证已有流程

验收脚本已 committed，等待业务逻辑补齐后重新运行。

**Commit**: (pending) feat(P2-2): verify friend stock to observation runtime loop
