# Task 4A-Corrective-3 进度报告

**执行日期:** 2026-07-18  
**任务范围:** 修复 B6 终态事务与真实回归验收  
**状态:** 部分进展（30%）

---

## 执行摘要

**已完成（30%）:**
1. ✓ 复现当前失败状态（10 failed test_b6_oos_ledger_boundary, 3 skipped test_b6_validation_flow）
2. ✓ 识别根因：模板 tpl_001 未 approved，导致 B6 在模板 guard 提前阻断
3. ✓ 实施 template fixture 注入（patch list_approved_templates + get_template_by_id）
4. ✓ 进展：从 "template not found" 到 "template is candidate"

**当前阻塞（70%）:**
- ✗ 模板状态检查：测试模板被识别为 `candidate`，需要 `approved`
- ✗ B6 OOS ledger boundary tests 仍然 blocked（未到达 ledger 边界）
- ✗ 3 个 skipped B6 validation flow tests 未修复
- ✗ Task durable-state 一致性未修复
- ✗ Terminal atomicity injection tests 未实现

---

## 1. 当前状态复现

### 1.1 test_b6_oos_ledger_boundary.py

**Command:**
```bash
.venv/Scripts/python.exe -m pytest -p no:cacheprovider tests/test_b6_oos_ledger_boundary.py -q
```

**Result (before fix):**
```
10 failed in 4.06s
```

**Root cause:**
- `result.status == 'blocked'` (expected: 'completed')
- `blocking_reason: "Template tpl_001 not found in template library"`
- B6ValidationFlow 模板 guard 阻断，未到达 OOS ledger 边界

---

### 1.2 test_b6_validation_flow.py

**Command:**
```bash
.venv/Scripts/python.exe -m pytest -p no:cacheprovider tests/test_b6_validation_flow.py -q -rs
```

**Result:**
```
6 passed, 3 skipped in 0.74s
```

**Skipped tests:**
- test_b6_flow_candidate_without_human_approval_is_not_prototype_passed
- test_b6_flow_produces_report_gate_and_explanation
- test_b6_flow_reducer_error_fails_loud

**Reason:** Marked as `@unittest.skip("TODO: Requires full StrategyDB setup")`

---

## 2. 已实施修复

### 2.1 Template Fixture 注入

**File:** `tests/test_b6_oos_ledger_boundary.py`

**Changes in setUp():**
```python
# Create test template fixture
self.test_template = StrategyTemplate(
    template_id="tpl_001",
    version="v1",
    hypothesis_types=("test",),
    core_entry_rule_id="test_entry",
    supported_universe_rule_types=("point_in_time_membership",),
    sample_split_rule_ids=("fixed_ratio_70_30",),
    benchmark_rule_id="equal_weight",
    strategy_config_payload={},
    forbidden_fields=(),
    forbidden_evidence_terms=(),
    default_cost_model="base",
    default_fill_model="market_open",
    default_risk_rules={},
    market_fit="Test only",
    forbidden_market=(),
    entry_rules="Test entry",
    exit_rules="Test exit",
    risk_rules="Test risk",
    position_sizing_rules="Test sizing",
    validation_gate_profile="standard",
)

# Patch template library functions
self._original_list_approved = strategy_template_library.list_approved_templates
self._original_get_template = strategy_template_library.get_template_by_id

strategy_template_library.list_approved_templates = lambda: (self.test_template,)
strategy_template_library.get_template_by_id = lambda tid: self.test_template if tid == "tpl_001" else self._original_get_template(tid)
```

**Changes in tearDown():**
```python
# Restore original functions
strategy_template_library.list_approved_templates = self._original_list_approved
strategy_template_library.get_template_by_id = self._original_get_template
```

---

## 3. 当前阻塞问题

### 3.1 Template Status Check

**Current blocking reason:**
```
Template tpl_001 is candidate; B6/OOS/Gate/Promotion require approved template (per Task 1 section 2.3)
```

**Root cause:**
- B6ValidationFlow 中的模板治理检查不仅查找模板，还检查其状态
- `list_approved_templates()` 返回的模板仍被识别为 `candidate`
- 需要进一步调查模板状态检查逻辑

**Next steps:**
1. 检查 B6ValidationFlow 中的模板状态检查代码
2. 确定如何标记测试模板为 `approved`
3. 可能需要 patch 额外的函数或数据结构

---

## 4. 未完成工作

### 4.1 B6 OOS Ledger Boundary Tests（10 个）

**Status:** Blocked（模板 guard 阻断）

**Required fix:** 解决模板状态检查问题，使测试能够通过模板 guard 到达 ledger 边界

---

### 4.2 B6 Validation Flow Skipped Tests（3 个）

**Status:** Skipped

**Required fix:** 
- 移除 `@unittest.skip` 装饰器
- 创建完整 file-backed StrategyDB fixture
- 设置 draft/protocol/universe

---

### 4.3 Task Durable-State 一致性

**Status:** Not started

**Issue:** `get_b6_task_by_key()` 读取 payload_json，但 terminal 更新只改表列

**Required fix:**
- 选择一致方案（同步 payload_json 或以列为权威）
- 验证 create → queued, terminal success → completed, terminal failure → failed

---

### 4.4 Terminal Atomicity Injection Tests

**Status:** Not started

**Required:** 4 个 SQLite RAISE(ABORT) trigger 注入测试

---

## 5. 任务状态

**Task Status:**
- Task 3 = **not complete**
- Task 4 = **not complete**
- Task 4A-Corrective-3 = **30% 进展**
- Task 0 Step 5 = **no_validated_signal_visible_in_dom**

**Workflow Status:**
- validation_unavailable = **正确**

---

## 6. 下次会话起点

**从哪里继续:**
1. 调查 B6ValidationFlow 模板状态检查逻辑
2. 确定如何标记测试模板为 `approved`（可能需要 patch governance_map）
3. 修复 template guard 阻塞后，继续修复 OOS boundary tests
4. 修复 3 个 skipped B6 validation flow tests
5. 修复 task durable-state 一致性
6. 实现 terminal atomicity injection tests

**估算剩余时间:** 4-6 hours

---

## 结论

**已完成:** 识别并部分修复模板 fixture 注入问题（30%）。

**当前阻塞:** 模板状态检查逻辑仍将测试模板识别为 `candidate`，需要进一步调查和修复。

**验收状态:** 未完成（当前 0/5 测试套件通过）。

**关键发现:** 
- 模板治理检查不仅查找模板，还验证状态（candidate vs approved）
- 需要更深入的 template governance patch 或修改检查逻辑

**建议:** 考虑在 B6ValidationFlow 中添加测试模式或 governance bypass 选项，允许测试使用 candidate 模板。
