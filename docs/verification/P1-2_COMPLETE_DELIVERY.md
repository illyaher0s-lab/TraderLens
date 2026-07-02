# P1-2 完整验收交付

## 证据为

### Test 1: friend_stock vs data_fault vs not_found 对照表

| Input | Fault Type | Trigger | Resolver Status | Workflow State | Created Flow | Timeline Failed |
|-------|------------|---------|-----------------|----------------|--------------|-----------------|
| 朋友推荐了宏昌电子 | success | normal_fixture | verified | created | 1 (waiting) | N/A |
| 帮我看603002 | success | normal_fixture | verified | created | 1 (waiting) | N/A |
| 买入宏昌电子可以吗 | success | normal_fixture | verified | created | 1 (waiting) | N/A |
| 帮我看999999 | **stock_not_found** | empty_fixture | **not_found** | **stopped** | **0** | N/A |
| 帮我看宏昌电子 | **data_fault** | fake_resolver_injection | **data_fault** | **stopped** | **0** | YES |

**区分验证:**
- not_found: empty fixture → resolver_status=not_found, workflow_state=stopped
- data_fault: fake resolver injection → resolver_status=data_fault, workflow_state=stopped
- **核心差异:** data_fault 是 Tushare 真实错误模拟（连接超时），not_found 是查询无结果

---

### Test 2: extraction_failed 原始表

| Input | Fault Type | Trigger | Exception Type | Workflow State | Timeline Failed | Response Readable |
|-------|------------|---------|----------------|----------------|-----------------|-------------------|
| 刷到策略下午两点半买第二天卖 | **extraction_failed** | fake_service_injection | ValueError | failed | **YES** (workflow_action_failed artifact) | **YES** (37 chars) |

**验证点:**
- ✅ workflow_action_failed artifact 存在
- ✅ response.agent_reply 可读（"策略想法处理失败：LLM extraction failed (注入失败)"）
- ✅ 不显示 validating/running

---

### Test 3: handler exception 原始表

已由 extraction_failed 覆盖（strategy service 抛异常 → handler catch → workflow_action_failed）

---

## 搜索结果: 脚本无 SKIPPED/skip/not implemented

```bash
$ grep -i "skip\|not implemented" scripts/verify_p1_2_workbench_real_actions.py
5. 无 SKIPPED 项
print("P1-2 Workbench Real Actions Verification (Complete - No Skips)")
# ========== Test 3: Failure paths (NO SKIPS) ==========
    print(f"SUCCESS: All tests passed (NO SKIPPED)")
```

**结论:** 仅注释和成功信息中提到 "No Skips"，无实际跳过的测试 ✅

---

## 测试命令 + Exit Code

**命令:**
```bash
.venv\Scripts\python.exe scripts\verify_p1_2_workbench_real_actions.py
```

**结果:**
- Exit code: **0** ✅
- SUCCESS: All tests passed (NO SKIPPED) ✅

**验证点:**
- ✅ friend_stock: status='waiting', research_output=NULL
- ✅ strategy_idea: timeline-persisted artifacts with claimed_ fields (no separate strategy DB)
- ✅ stock_not_found: workflow_state='stopped', no flow created
- ✅ data_fault: workflow_state='stopped', no flow created, resolver_status='data_fault'
- ✅ extraction_failed: workflow_action_failed artifact, response readable
- ✅ route_decision.workflow_kind == response.workflow_type for all cases
- ✅ ResearchDB.get_friend_stock_flow() returns status field

---

## Commit Hash

**6d53ecb**

```
feat: P1-2 完整验收 - 可注入测试路径(data_fault/extraction_failed), 无SKIPPED

3 files changed, 221 insertions(+), 134 deletions(-)
```

**Git status:** 干净 ✅

---

## 实现说明

### 1. 可注入测试路径实现

#### stock_resolver_override
- `create_research_app` 新增参数 `stock_resolver_override`
- 测试时注入 `FakeStockResolverWithDataFault`
- 正常生产路径不变（real → Tushare, deterministic → fixture）

#### strategy_flow_service_override
- `create_research_app` 新增参数 `strategy_flow_service_override`
- `handle_strategy_idea` 接收可选 service 参数
- 测试时注入 `FakeStrategyServiceWithExtractionFailure`

### 2. strategy_idea 口径修正

**当前实现:** P1-2 完成的是 **timeline-persisted strategy action**（artifacts 存储在 `agent_artifact_refs.content`），**不是独立策略库 DB**。

**未来工作:** 独立策略库 DB（strategy_ideas.db）在后续任务实现。

---

## 修改文件

1. `backend/api/research.py`
   - 添加 `stock_resolver_override` 参数
   - 添加 `strategy_flow_service_override` 参数
   - new/existing session 使用 override（如果提供）

2. `backend/api/workbench_handlers.py`
   - `handle_strategy_idea` 添加 `strategy_flow_service` 参数

3. `backend/db/research.py`
   - `get_friend_stock_flow()` 返回 `status` 字段

4. `scripts/verify_p1_2_workbench_real_actions.py`
   - 重写完整版，无 SKIPPED
   - 实现 FakeStockResolverWithDataFault
   - 实现 FakeStrategyServiceWithExtractionFailure
   - 所有失败路径测试
