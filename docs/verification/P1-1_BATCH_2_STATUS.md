# P1-1 第二批实施报告（Commit 1-2）

**日期:** 2026-07-02  
**当前 Commit:** baaf7d8  
**状态:** 部分完成（2/6 commits）

---

## 已完成 ✅

### Commit 1: 验证脚本 + Dependency Injection

**实现为:**
- `backend/api/research.py`: 添加 `stock_resolver_fixture` 参数
- `scripts/verify_p1_1_batch2_commit1.py`: FastAPI TestClient 验证脚本
- 使用正确字段名：`agent_reply`, `artifact_ids`

**证据为:**
```python
# Dependency injection
app = create_research_app(
    db=db,
    conversation_mode="deterministic",
    serenity_execution_mode="stub",
    stock_resolver_fixture=test_fixture,  # 注入
)

# 真实 API 调用
response = client.post(
    "/api/agent/workbench/message",
    json={"message": message, "conversation_id": None}
)
```

### Commit 2: Intent Extractor + Router 修复

**实现为:**
- `backend/services/workbench_prescan.py`: 修复 strategy_rule_shape 模式
- `backend/services/workbench_intent_extractor.py`: 添加 position_followup 检测，修复公司名提取
- `backend/services/workbench_workflow_router.py`: 添加 position_followup 路由

**证据为: 9 条输入真实 API 输出表**

| 输入 | Workflow Type | Stage | Artifact IDs | Status |
|------|---------------|-------|--------------|--------|
| 帮我看宏昌电子是否值得买入 | friend_stock | stopped | flow_xxx, msg_xxx, intent_xxx | ✅ |
| 帮我看603002 | friend_stock | stopped | flow_xxx, msg_xxx, intent_xxx | ✅ |
| 朋友推荐了宏昌电子 | friend_stock | stopped | flow_xxx, msg_xxx, intent_xxx | ✅ |
| 买入宏昌电子可以吗 | friend_stock | stopped | flow_xxx, msg_xxx, intent_xxx | ✅ |
| 刷到策略下午两点半买第二天卖 | strategy_idea | stopped | idea_xxx, extract_xxx, mapping_xxx, rejected_xxx | ✅ |
| 已买入100股成交价12.34 | friend_stock | stopped | verify_xxx (无 flow) | ⚠️ |
| 今天要不要继续拿 | friend_stock | stopped | verify_xxx (无 flow) | ⚠️ |
| 帮我看看 | unknown | created | msg_xxx, intent_xxx | ✅ |
| 你好 | unknown | created | msg_xxx, intent_xxx | ✅ |

**DB Record ID:**
- Friend Stock: `flow_c156bd12cdcc`, `flow_0affd65a182d`, `flow_838fdc0307c4`, `flow_98e800a21ff6` (4条)
- Strategy Idea: `idea_122b4f4c140f`, `idea_122b4f4c140f_rejected` (2条)

**LLM 调用次数:**
- 当前验证：每条消息 0 次（deterministic mode）
- 设计要求：每条消息最多 1 次（real mode）
- **实测方式:** 未实现（需要在 real mode 下运行并记录 LLM client 调用）

---

## 未完成 ❌

### Commit 3: Session Context 加载
- ❌ 加载最近 N 条消息
- ❌ 加载 workflow_state
- ❌ 加载 claimed_stock / claimed_strategy
- ❌ 加载 open_positions
- ❌ 生成 context_loaded artifact

### Commit 4: PreScan 短路 + 执行反馈
- ❌ 高置信执行反馈短路（"已买入100股成交价12.34"）
- ❌ 无对应持仓/审批 → clarification
- ❌ 已有持仓又说买入 → clarification
- ❌ 无持仓说卖出 → clarification

### Commit 5: Context Follow-up
- ❌ "今天要不要继续拿"在有 open position 时 → position_followup workflow
- ❌ "帮我看看"使用上一轮 session context
- ❌ 无上下文 → clarification

### Commit 6: Timeline 活动记录
- ❌ context_loaded
- ❌ prescan_result
- ❌ intent_extraction
- ❌ stock_identity_resolution
- ❌ route_decision
- ❌ workflow_action_started / failed / completed

### LLM 失败路径
- ❌ LLM JSON 解析失败 → extraction_failed + clarification
- ❌ LLM 超时 → extraction_failed + clarification
- ❌ 实测 LLM 调用次数（需要 real mode）

---

## 测试为

**命令:**
```bash
cd /mnt/d/Codex/TraderLens
.venv\Scripts\python.exe scripts\verify_p1_1_batch2_commit1.py
```

**结果:**
- 9/9 HTTP 200
- 6/9 正确路由（friend_stock x4, strategy_idea x1, unknown x2）
- 2/9 部分正确（execution_feedback 和 position_followup 被映射到 friend_stock）
- 1/9 需要 clarification（帮我看看）

---

## Commit Hash

**Commit 1:** bbed802  
**Commit 2:** baaf7d8

---

## 说明

### 为什么只完成 2/6 commits？

第二批范围远超最初预期：
1. **Commit 1-2（已完成）:** 验证脚本 + Intent/Router 基础修复（~2小时工作量）
2. **Commit 3-6（未完成）:** Session Context、PreScan 短路、Timeline、完整失败路径（~6-8小时工作量）

后续 commits 涉及：
- DB schema 扩展（session context 存储）
- Timeline DB 操作（每步记录）
- PreScan 高置信逻辑（需要持仓数据）
- Context follow-up 路由（需要 session state）

### 当前可交付内容

1. ✅ **Dependency Injection 架构:** 生产环境无 hardcode fixture，测试可注入
2. ✅ **真实验证脚本:** FastAPI TestClient + 9 条真实输出
3. ✅ **Intent/Router 基础修复:** 6/9 正确路由
4. ✅ **DB 落地验证:** friend_stock 4条，strategy_idea 2条

### 第二批完整交付需要

1. ⏳ 完成 Commit 3-6（Session Context + PreScan 短路 + Timeline）
2. ⏳ 修复 execution_feedback 和 position_followup 路径
3. ⏳ 实测 LLM 调用次数（real mode）
4. ⏳ 完整 9 条输入验收（所有路由正确 + 所有 workflow action 完成）

---

## 建议

**选项 A:** 继续完成 Commit 3-6（预计 6-8 小时）  
**选项 B:** 暂停第二批，明确当前进度，规划下一阶段  
**选项 C:** 简化第二批范围，只完成核心路由逻辑（当前已完成）

请明确下一步指令。
