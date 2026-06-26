# B2 Hypothesis Builder Verification Record

**Status:** ✅ ACCEPTED  
**Date:** 2026-06-26  
**Accepted Commit:** `772c723 fix: B2 repair loop structured errors + validator recursive evidence check`

---

## 1. B2 Accepted Commit

```
772c723 fix: B2 repair loop structured errors + validator recursive evidence check
```

**Full commit history (B2 implementation):**
```
772c723 fix: B2 repair loop structured errors + validator recursive evidence check
11e7e5c chore: ignore .claude directory
b768810 test: protect B2 compatibility boundaries
8e11f2b test: integrate B2 builder with B1 storage
d8b3c5c feat: add bounded B2 repair loop
140f3aa feat: add B2 hypothesis builder
653118d feat: add deterministic B2 strategy validator
50ce556 test: lock B2 LLM template selection boundary
4377d79 test: add update_template coverage to B2 template library
0827ce1 docs: add B2 hypothesis builder plan
5f8e973 feat: add B2 strategy template library
```

---

## 2. B2 新增/修改文件列表

### Created Files

**Backend Services:**
- `backend/services/strategy_template_library.py` — 4 hard-coded templates, no runtime API
- `backend/services/hypothesis_builder_types.py` — LLM selection contract, builder I/O types
- `backend/services/strategy_config_validator.py` — Deterministic validator, 12+ rejection rules
- `backend/services/hypothesis_builder.py` — Main builder service, 1 LLM call normal path
- `backend/services/hypothesis_repair_loop.py` — Bounded repair (max 2), structured error passing

**Tests:**
- `tests/b2_fixtures.py` — B2 test fixtures
- `tests/test_b2_template_library.py` — Template library tests (6 tests)
- `tests/test_b2_template_selection_contract.py` — LLM contract boundary tests (9 tests)
- `tests/test_b2_strategy_config_validator.py` — Validator tests (15 tests)
- `tests/test_b2_hypothesis_builder.py` — Builder integration tests (9 tests)
- `tests/test_b2_repair_loop.py` — Repair loop tests (10 tests)
- `tests/test_b2_b1_integration.py` — B1 storage integration tests (5 tests)
- `tests/test_b2_compatibility.py` — Compatibility boundary tests (7 tests)

**Documentation:**
- `docs/superpowers/plans/2026-06-26-b2-hypothesis-builder-plan.md` — B2 implementation plan

### Modified Files

- `.gitignore` — Added `.claude/` exclusion
- None of the forbidden files were modified:
  - ✅ `contracts/stable.py` — unchanged
  - ✅ `contracts/draft.py` — unchanged
  - ✅ `contracts/research.py` — unchanged
  - ✅ `backend/db/research.py` — unchanged
  - ✅ `strategy_core/prototype_gate.py` — unchanged
  - ✅ `contracts/strategy.py` — B1 contracts unchanged (only used, not modified)

---

## 3. Focused Tests Results

**Total B2 tests:** 61 tests

| Test Suite | Tests | Status |
|------------|-------|--------|
| `test_b2_template_library` | 6 | ✅ OK |
| `test_b2_template_selection_contract` | 9 | ✅ OK |
| `test_b2_strategy_config_validator` | 15 | ✅ OK |
| `test_b2_hypothesis_builder` | 9 | ✅ OK |
| `test_b2_repair_loop` | 10 | ✅ OK |
| `test_b2_b1_integration` | 5 | ✅ OK |
| `test_b2_compatibility` | 7 | ✅ OK |

**Key boundary proofs:**
- ✅ Normal path LLM call count = 1
- ✅ Repair max attempts = 2
- ✅ LLM cannot set parameters (ValidationError on extra fields)
- ✅ Evidence event terms rejected in trade rules
- ✅ Multiple variants rejected
- ✅ Forward watchlist rejected
- ✅ Failed validation stores nothing
- ✅ StrategyDraft has no status field
- ✅ Reducer remains prototype_passed-only path (B1 unchanged)

---

## 4. Full Test Results

**Final suite:**
```
981 passed, 2 skipped, 3 warnings, 24 subtests passed in 40.40s
```

**Baseline comparison:**
- B1 baseline: 920 passed, 2 skipped
- B2 delta: +61 tests
- Frontend TypeScript: 0 errors

---

## 5. CLAUDE 复审结论摘要

**Initial Review:** needs_fix (2 issues identified)

**Issues Found:**
1. **Repair loop blind retry** — repair called with same input, validation errors not passed to LLM
2. **Validator key-only check** — Evidence terms only checked in keys, not recursively in values

**Fix Applied:** Commit `772c723`

**Re-review Result:** ACCEPTED

**Verification:**
- ✅ Repair loop now passes structured `previous_validation_errors` via `HypothesisBuilderInput`
- ✅ Validator recursively checks keys + string values in entry/exit/risk sections
- ✅ LLMTemplateSelection contract unchanged (still 3 fields only)
- ✅ +4 new tests covering fixed behaviors
- ✅ Full suite 981 passed

---

## 6. 已修复问题

### Issue 1: Repair Loop 盲重试

**Problem:**
- `HypothesisRepairLoop.run()` 失败后用相同 `input` 重试
- Validation errors 没有传递给 LLM
- 违反 B2 计划中 "repair must receive structured validation errors" 要求

**Fix:**
- 新增 `HypothesisBuilderValidationErrorContext` 轻量错误类型
- `HypothesisBuilderInput` 添加 `previous_validation_errors: tuple[HypothesisBuilderValidationErrorContext, ...]` 字段
- Repair loop 在第二次调用前将上次 `validation_errors` 转换为 context 并传递
- 新测试 `test_repair_receives_structured_validation_errors_not_blind_retry` 验证

### Issue 2: Validator 只查 key，不查 value

**Problem:**
- Evidence 禁词检查只在 flattened keys 中查找（如 `entry.announcement_filter`）
- 深层 string value 如 `entry.filter_type = "公告驱动"` 可能漏过
- 虽然模板由系统硬编码，但 validator 应作为兜底，不应只依赖模板正确

**Fix:**
- 新增 `_check_evidence_terms_recursive(obj, parent_path)` 方法
- 递归检查 entry/exit/risk 中所有：
  - dict keys（转小写匹配）
  - string values（转小写匹配）
  - list/tuple 元素
- 禁词覆盖中英文：公告、订单、客户认证、中标、合同、互动易、问询函、业绩预告、减持、announcement、disclosure、customer_certification、revenue_purity
- 新增 3 个测试：
  - `test_rejects_evidence_term_in_deep_key`
  - `test_rejects_evidence_term_in_string_value`
  - `test_rejects_evidence_term_in_exit_and_risk_values`

---

## 7. 当前保留风险

### Risk 1: 真实 LLM 尚未接入

**Status:** Known limitation, acceptable for B2

**Details:**
- B2 所有测试使用 `FakeLLMClient` 模拟 LLM 行为
- 真实 LLM 接入需要在后续阶段完成
- **契约已锁定，不得修改** `LLMTemplateSelection` 输出字段：
  - `strategy_template_id`
  - `template_selection_reason`
  - `unmapped_hypothesis_elements`
- 真实 LLM 必须遵守此契约，不得输出 entry/exit/risk 参数、status、hash、Gate、OOS、budget

**Mitigation:**
- Validator 会拒绝任何违反契约的输出
- B2 测试已证明 ValidationError 在 LLM 尝试添加禁止字段时触发

### Risk 2: Repair Loop 简化实现

**Status:** Acceptable, can be enhanced later

**Details:**
- 当前实现将 validation errors 传递给 repair input，但 LLM 如何使用这些 errors 取决于实际 LLM client 实现
- Fake LLM 只记录 `received_errors`，不基于 errors 调整行为
- 真实场景可能需要更复杂的 repair prompt engineering

**Mitigation:**
- B2 已建立 structured error passing 机制
- LLM client 实现时可扩展 error handling 逻辑，无需修改 repair loop 核心

### Risk 3: Template Library 硬编码 4 个模板

**Status:** Intentional design, acceptable

**Details:**
- 模板库当前硬编码 4 个模板，无 runtime 添加 API
- 未来扩展需要修改源码并重新部署
- 测试已证明不存在 `add_template`、`update_template`、`register_template` 方法

**Mitigation:**
- 这是 B2 设计约束，防止 LLM 或用户动态创建模板
- 模板扩展需要：code review → 测试 → 部署，保持质量控制
- 当前 4 个模板覆盖主要策略类型：theme_momentum、relative_strength、volume_breakout、trend_pullback

---

## 8. B2 边界

### LLM 只选 template

✅ **Enforced by:**
- `LLMTemplateSelection` contract with `extra="forbid"`
- Validator rejects unknown template IDs
- Tests: `test_llm_selection_accepts_only_template_id_reason_and_unmapped_elements`

### 不输出参数

✅ **Enforced by:**
- `LLMTemplateSelection` contract forbids `entry_params`, `exit_params`, `risk_params`
- Config generated deterministically from `StrategyTemplate.strategy_config_payload`
- Tests: `test_llm_selection_rejects_entry_parameters`, `test_llm_selection_rejects_exit_parameters`, `test_llm_selection_rejects_risk_parameters`

### 不写状态

✅ **Enforced by:**
- `FORBIDDEN_FIELDS` includes `status`
- Validator rejects configs with `status` field
- `StrategyDraft` has no `status` field (only `StrategyLifecycleState` has `state`)
- Tests: `test_rejects_status_hash_gate_budget_fields`, `test_builder_creates_frozen_strategy_draft_without_status`

### 不写 Gate

✅ **Enforced by:**
- `FORBIDDEN_FIELDS` includes `gate_verdict`
- B2 does not call `prototype_gate` or any Gate logic
- Tests: `test_rejects_status_hash_gate_budget_fields`, `test_b2_builder_does_not_call_strategy_core`

### 不写 OOS

✅ **Enforced by:**
- `FORBIDDEN_FIELDS` includes `oos_start`, `oos_end`, `oos_budget`
- Validator rejects OOS fields
- Tests: `test_llm_selection_rejects_oos_dates`, `test_rejects_oos_dates`

### 不接回测

✅ **Enforced by:**
- B2 does not import or call backtest engine
- B2 only generates `StrategyDraft` and `StrategyLifecycleState(state="draft")`
- Tests: `test_b2_builder_does_not_call_strategy_core`

### 不写 prototype_passed

✅ **Enforced by:**
- B1 `guard_prototype_passed_lifecycle_insert` trigger remains active
- B2 cannot bypass `StrategyPromotionReducer` (B1 only path)
- Tests: `test_b2_cannot_write_prototype_passed_directly`

---

## 9. Next Steps

**B2 交付完整，已验收通过。**

**待定：**
- B3 OOS window generation and backtest integration
- 真实 LLM client 接入（必须遵守 `LLMTemplateSelection` 契约）

**不得在 B3 中修改：**
- `LLMTemplateSelection` 输出契约
- Template library runtime API 限制
- B2 → B1 storage 路径
- A 模块、B1、stable contracts

---

**Verification completed:** 2026-06-26  
**Approved by:** ChatGPT (裁判验收)  
**Next milestone:** B3 (pending plan)
