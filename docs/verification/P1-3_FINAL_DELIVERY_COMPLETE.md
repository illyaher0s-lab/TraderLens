# P1-3 Workbench 状态诚实化 - 最终交付（补充修复）

## 任务目标

修复 P1-3 Test 3 blocker：第三轮"帮我看看"必须承接上一轮已验证股票，路由到 friend_stock，而不是 unknown/stopped。

## 根因分析

**原始问题：** Test 3 路由到 `unknown`，`route_reason` 显示"路由为股票研究工作流，但缺少公司名代码（需要 session context 或用户明确）"。

**深入调查发现：**
1. Test 1 本身就失败了 —— `workflow_state: waiting_for_clarification`，`route_reason: 找到多个匹配：3个候选`
2. Stock identity resolver 返回 `status: ambiguous`，导致 handler 没有创建 `friend_stock_flow`
3. Test 3 无法从 timeline 读取 `friend_stock_flow`，claimed_stock 继承失败

**根本原因：** `StockIdentityResolver._resolve_with_fixture()` 的 company_name 查找逻辑缺陷：
- 遍历所有 fixture 条目，匹配 `company_name` 值
- 测试 fixture 有三个条目（"宏昌电子"、"603002.SH"、"603002"），所有条目的 `company_name` 都是"宏昌电子"
- 搜索"宏昌电子"时匹配到 3 个条目，返回 `ambiguous`

## 修复实现

### backend/services/stock_identity_resolver.py

**修改：** Line 152-165 添加直接 key lookup 优先路径

```python
# Try company name
if company_name:
    # First try direct key lookup
    if company_name in self.test_fixture:
        identity = self.test_fixture[company_name]
        return StockIdentityResolution(
            status="verified",
            ticker=identity["ticker"],
            company_name=identity["company_name"],
            exchange=identity["exchange"],
            list_status=identity.get("list_status", "L"),
            data_source="deterministic_fixture",
        )
    
    # Then search by company name in fixture values
    matches = []
    for ticker, identity in self.test_fixture.items():
        if identity["company_name"] == company_name:
            matches.append(identity)
```

**逻辑：**
1. 先尝试按 `company_name` 作为 fixture 的 key 直接查找（O(1)）
2. 如果找到，立即返回 `verified`
3. 否则再遍历所有 fixture values 查找匹配的 `company_name`（O(n)）

**效果：**
- "宏昌电子" → 直接查找 `fixture["宏昌电子"]` → 返回 `verified`，不再遍历其他条目
- "603002.SH" → 直接查找 `fixture["603002.SH"]` → 返回 `verified`
- 避免 ambiguous 误判

### scripts/verify_p1_3_browser_with_fixture.py

**修改：** 移除 fixture 中多余的 `status` 字段（不影响逻辑，只是清理）

## 验收结果

### A. API 证据

**Test 1: 朋友推荐了宏昌电子 ✅**
```
conversation_id: sess_16a8765b6cfb
workflow_type: friend_stock
stage: created

Artifact types (11):
  1. context_loaded
  2. prescan_result
  3. intent_extraction
  4. stock_identity_resolution
  5. workflow_route_decision
  6. workflow_action_started
  7. friend_stock_flow ← 关键
  8. workflow_action_completed
  9. user_message
  10. agent_message
  11. workflow_intent
```

**验证：**
- `stock_identity.status: verified` ✅
- `route_decision.workflow_kind: friend_stock` ✅
- `workflow_state: created` (不是 `waiting_for_clarification`) ✅
- 创建了 `friend_stock_flow` artifact ✅

---

**Test 2: 刷到策略下午两点半买第二天卖 ✅**
```
conversation_id: sess_16a8765b6cfb (same session)
workflow_type: strategy_idea
stage: created

Artifact types (24，第12-24为第二轮):
  12. context_loaded
  13. prescan_result
  14. intent_extraction
  15. workflow_route_decision
  16. workflow_action_started
  17. strategy_idea
  18. strategy_idea_extraction
  19. strategy_template_mapping
  20. strategy_idea_rejected ← 关键
  21. workflow_action_completed
  22. user_message
  23. agent_message
  24. workflow_intent
```

**验证：**
- `route_decision.workflow_kind: strategy_idea` ✅
- `workflow_state: created` ✅
- 有 `strategy_idea_rejected` artifact ✅

---

**Test 3: 帮我看看（承接上一轮） ✅**
```
conversation_id: sess_16a8765b6cfb (same session)
workflow_type: friend_stock
stage: created

Artifact types (35，第25-35为第三轮):
  25. context_loaded
  26. prescan_result
  27. intent_extraction
  28. stock_identity_resolution ← 存在！
  29. workflow_route_decision
  30. workflow_action_started
  31. friend_stock_flow ← 存在！
  32. workflow_action_completed
  33. user_message
  34. agent_message
  35. workflow_intent
```

**验证：**
- `route_decision.workflow_kind: friend_stock` (不是 `unknown`) ✅
- `workflow_state: created` (不是 `stopped`) ✅
- 第三轮有 `stock_identity_resolution` artifact ✅
- 第三轮有 `friend_stock_flow` artifact ✅
- claimed_stock context 继承成功 ✅

**数据文件：**
- `screenshots/test1_timeline.json`
- `screenshots/test2_timeline.json`
- `screenshots/test3_timeline.json`

---

### B. 测试命令和实际输出

**命令 1: TypeScript 编译**
```bash
$ cd frontend && npx tsc -p tsconfig.json --noEmit --skipLibCheck
# Exit code: 0 ✅
```

**命令 2: 后端测试**
```bash
$ .venv/Scripts/python.exe -m pytest tests/test_v1_agent_workbench_api.py tests/test_v1_agent_workbench_db.py -q
...............................                                          [100%]
31 passed, 1 warning in 8.31s ✅
```

**命令 3: P1-3 验收脚本**
```bash
$ .venv/Scripts/python.exe scripts/verify_p1_3_browser_with_fixture.py

Test 1: Friend stock recommendation
----------------------------------------------------------------------
conversation_id: sess_16a8765b6cfb
workflow_type: friend_stock
stage: created
[OK] workflow_type: friend_stock

Test 2: Strategy idea
----------------------------------------------------------------------
conversation_id: sess_16a8765b6cfb
workflow_type: strategy_idea
stage: created
[OK] workflow_type: strategy_idea

Test 3: Context follow-up
----------------------------------------------------------------------
conversation_id: sess_16a8765b6cfb
workflow_type: friend_stock
stage: created
[OK] workflow_type: friend_stock

======================================================================
Verification complete!
```

**结果汇总：**
```
Test 1: Test 1: Friend stock recommendation
  Expected: friend_stock
  Actual: friend_stock
  Stage: created
  Result: PASS

Test 2: Test 2: Strategy idea
  Expected: strategy_idea
  Actual: strategy_idea
  Stage: created
  Result: PASS

Test 3: Test 3: Context follow-up
  Expected: friend_stock
  Actual: friend_stock
  Stage: created
  Result: PASS
```

---

### C. Git 变更

**修改文件：**
1. `backend/services/stock_identity_resolver.py` - 添加直接 key lookup 优先路径
2. `scripts/verify_p1_3_browser_with_fixture.py` - 清理 fixture 字段

**Diff 摘要：**
```diff
diff --git a/backend/services/stock_identity_resolver.py b/backend/services/stock_identity_resolver.py
@@ -151,7 +151,19 @@ class StockIdentityResolver:
         
         # Try company name
         if company_name:
-            # Search by company name in fixture values
+            # First try direct key lookup
+            if company_name in self.test_fixture:
+                identity = self.test_fixture[company_name]
+                return StockIdentityResolution(
+                    status="verified",
+                    ticker=identity["ticker"],
+                    company_name=identity["company_name"],
+                    exchange=identity["exchange"],
+                    list_status=identity.get("list_status", "L"),
+                    data_source="deterministic_fixture",
+                )
+            
+            # Then search by company name in fixture values
             matches = []
             for ticker, identity in self.test_fixture.items():
                 if identity["company_name"] == company_name:
```

**Commit hash:** a2e1c01

---

## 交付结论

**状态：PASS ✅**

### 完成项
1. ✅ 修复 StockIdentityResolver fixture 查找逻辑
2. ✅ Test 1 (friend_stock) 路由正确，创建 flow
3. ✅ Test 2 (strategy_idea) 路由正确，创建 rejected artifact
4. ✅ Test 3 (context follow-up) 路由正确，继承 claimed_stock context
5. ✅ TypeScript 编译通过
6. ✅ 后端测试全部通过 (31/31)
7. ✅ API 验收三组测试全部通过

### 关键改进
- **claimed_stock 继承逻辑** 已在 P1-1 实现（line 1253-1260 in research.py）
- **问题根源** 是 resolver 的 fixture 查找逻辑导致第一轮就失败，进而第三轮无法继承
- **修复方案** 优化 resolver 查找顺序：直接 key lookup → 遍历 values
- **验证策略** 使用 API timeline 证据链，不依赖截图

### 下一步
P1-3 Workbench 状态诚实化已完成所有验收要求，可以继续下一个任务。
