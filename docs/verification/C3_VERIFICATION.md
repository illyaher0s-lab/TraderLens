# C3 Action Plan Human Execution Boundary Verification

**Purpose:** Final verification that C3 Action Plan implementation enforces human execution boundary without introducing broker/order/execution scope.

**Verification Date:** 2026-06-29

**Status:** READY_FOR_REVIEW

---

## 1. Scope Summary

C3 implements the human execution boundary for admitted Signal Board planned signals.

### What C3 Covers

- Signal Board → Action Plan generation (deterministic, rule-based)
- Human execution checklist (pre-action checks, invalidation checks)
- Human decision recording (execute / partial / skip / expired)
- Decision mapping to Signal Board review_status
- Neutral user-facing language (人工处理计划, not 买卖建议)
- Required disclaimer: "不是买卖建议，不会自动交易"

### What C3 Does NOT Cover

- ❌ Execution Log (belongs to C4)
- ❌ Post-market review (belongs to C5)
- ❌ Broker integration
- ❌ Order placement
- ❌ Fill records
- ❌ Realized P&L
- ❌ Automatic trading
- ❌ Live refresh
- ❌ Strategy ranking
- ❌ Price targets
- ❌ Buy/sell recommendations

---

## 2. Commit History

C3 implementation commits (oldest to newest):

```
66c8f63 docs: C3-1 Signal Board scope audit and implementation boundary
6bd7cf1 feat: C3-2 add deterministic Action Plan builder
80cdc03 fix: C3-2 make Action Plan builder fully deterministic
fdaf2a2 feat: C3-3 add Action Plan API endpoints
74efd0c feat: C3-4 add Action Plan frontend panel
ac970f4 fix(c3): block execute/partial on blocked or expired Action Plans
```

---

## 3. Changed Files

### Contracts (new)
- `contracts/action_plan.py` - ActionPlan, ActionCheck, UserActionDecision, ExecutionWindow, ActionPlanDecisionRequest

### Services (new)
- `backend/services/action_plan_builder.py` - Deterministic Action Plan builder from PlannedSignal

### Backend API (modified)
- `backend/api/signal_board.py` - Added:
  - `GET /api/signals/{signal_id}/action-plan`
  - `POST /api/signals/{signal_id}/action-plan/decision`

### Backend DB (modified)
- `backend/db/signal_board.py` - Added:
  - `action_plan_decisions` table
  - `save_action_plan_decision()` method
  - `get_action_plan_decision()` method

### Frontend (modified)
- `frontend/lib/api-client.ts` - Added ActionPlan types and API functions
- `frontend/components/ActionPlanPanel.tsx` (new) - Action Plan UI component
- `frontend/app/signals/[signal_id]/page.tsx` - Integrated ActionPlanPanel

### Tests (new)
- `tests/test_c3_action_plan_boundary.py` - Builder and API boundary tests (34 tests)
- `tests/test_c3_action_plan_copy_boundary.py` - Copy boundary tests (13 tests)

### Verification Docs (new)
- `docs/verification/C3_SCOPE_AUDIT.md` (C3-1)
- `docs/verification/C3_VERIFICATION.md` (this document)

---

## 4. Boundary Verification

### 4.1 Admitted Signal Enforcement

**Rule:** All C3 endpoints must call `get_admitted_signal()` before operating on a signal.

**Verification:**
- ✅ `GET /api/signals/{signal_id}/action-plan` enforces admission (test: `test_get_action_plan_requires_admitted_signal`)
- ✅ `POST /api/signals/{signal_id}/action-plan/decision` enforces admission (test: `test_post_action_decision_rejects_unadmitted_direct_id`)
- ✅ Builder rejects unadmitted signals (test: `test_build_action_plan_requires_admitted_signal`)
- ✅ Draft/rejected/needs_review signals return 404 (tests: `test_get_action_plan_rejects_rejected_signal`, `test_get_action_plan_rejects_needs_review_signal`)

### 4.2 Deterministic Builder

**Rule:** Action Plan generation must be deterministic (same signal + today + now → identical output).

**Verification:**
- ✅ `action_plan_id` uses SHA256 hash of signal metadata (test: `test_builder_is_deterministic`)
- ✅ `build_action_plan()` accepts injectable `today` and `now` parameters
- ✅ Same inputs produce identical `ActionPlan.model_dump()` output
- ✅ No random UUIDs
- ✅ No LLM calls
- ✅ No external data sources

### 4.3 Action Plan Decision Persistence

**Rule:** User decisions are persisted without order/broker/fill fields.

**Verification:**
- ✅ `action_plan_decisions` table stores decision, reason, manual_notes, decided_by, decided_at
- ✅ No `order_id`, `broker`, `fill_price`, `fill_qty`, `realized_pnl` columns
- ✅ POST endpoint ignores forbidden fields if sent (test: `test_post_action_decision_does_not_accept_order_fields`)
- ✅ Decision maps to `review_status` (test: `test_post_action_decision_updates_review_status_mapping`)

### 4.4 No Execution Fields

**Rule:** ActionPlan contract must not include execution-related fields.

**Verification:**
- ✅ `ActionPlan` model has no `order_id`, `broker`, `fill_price`, `fill_quantity`, `realized_pnl` fields (test: `test_action_plan_does_not_include_order_fields`)
- ✅ `UserActionDecision` only records decision intent, not actual fills
- ✅ `action_plan_decisions` table has no execution columns

### 4.5 No Broker/Order/Fill/P&L

**Rule:** C3 code must not introduce broker, order, fill, or P&L logic.

**Verification:**
- ✅ Grep search shows `fill_price/fill_qty/realized_pnl` only in B-module backtest and test assertions
- ✅ `order_id` only in B-module backtest and dependency libraries
- ✅ `approved_for_execution` only in comments and test files
- ✅ No broker API imports in C3 files

### 4.6 Blocked/Expired Cannot Execute or Partial

**Rule:** Action Plans with blocking checks or expired freshness cannot be marked "execute" or "partial".

**Verification:**
- ✅ Evidence blocked → execute rejected (test: `test_post_action_decision_rejects_execute_on_evidence_blocked`)
- ✅ Evidence blocked → partial rejected (test: `test_post_action_decision_rejects_partial_on_evidence_blocked`)
- ✅ Expired → execute rejected (test: `test_post_action_decision_rejects_execute_on_expired`)
- ✅ Expired → partial rejected (test: `test_post_action_decision_rejects_partial_on_expired`)
- ✅ Blocked/expired → skip allowed (test: `test_post_action_decision_allows_skip_on_blocked`)
- ✅ Expired → mark expired allowed (test: `test_post_action_decision_allows_expired_on_expired_plan`)
- ✅ Frontend disables execute/partial buttons when `!canAct` (test: `test_blocked_action_plan_disables_execute_button`, `test_blocked_action_plan_disables_partial_button`)

### 4.7 Copy Boundary

**Rule:** C3 UI must use neutral language and avoid forbidden recommendation/profit phrases.

**Verification:**

**Required phrases present:**
- ✅ "人工处理计划" (panel title)
- ✅ "这是人工处理计划，不是买卖建议，不会自动交易。" (disclaimer)
- ✅ Button labels: 准备执行, 部分执行, 今日放弃, 标记过期

**Forbidden phrases absent:**
- ✅ No "推荐买入", "推荐卖出", "立即买入", "立即卖出" (only in test files)
- ✅ No "一键下单", "自动执行" (only in test files)
- ✅ No "保证盈利", "稳定盈利", "实盘可用" (only in test files)
- ✅ No "目标价", "最佳策略", "策略排名" (only in test files)

**Exception:**
- ✅ "不会自动交易" is allowed (required disclaimer phrase)

**Grep results:**
- All forbidden phrases found only in test files (`test_c2_signal_board_decision_boundary.py`, `test_c3_action_plan_copy_boundary.py`, `test_signal_board_ux_polish.py`)
- No forbidden phrases in production code

### 4.8 C0/C1/C2 Regression

**Rule:** C3 must not break existing admission gates or Signal Board functionality.

**Verification:**
- ✅ C0 admission tests pass (11 passed)
- ✅ C1 admission tests pass (17 passed)
- ✅ C2 decision boundary tests pass (35 passed, 30 subtests passed)
- ✅ No modifications to C0/C1/C2 admission gate files
- ✅ No modifications to `generate_planned_signals.py`

### 4.9 B-Module Regression

**Rule:** C3 must not break B3/B4/B5/B6 validation logic.

**Verification:**
- ✅ B4 tests pass (131 passed)
- ✅ B5 tests pass (112 passed)
- ✅ B6 tests pass (26 passed, 4 subtests passed)
- ✅ No modifications to B-module validation files
- ✅ No modifications to `StrategyPromotionReducer`

---

## 5. Test Commands and Exact Outputs

### C3 Tests

**Command:**
```powershell
.venv\Scripts\python.exe -m pytest tests/test_c3_action_plan_boundary.py -v
```

**Output:**
```
============================= test session starts =============================
platform win32 -- Python 3.11.15, pytest-9.1.1, pluggy-1.6.0
34 passed, 1 warning in 6.85s
```

**Command:**
```powershell
.venv\Scripts\python.exe -m pytest tests/test_c3_action_plan_copy_boundary.py -q
```

**Output:**
```
.............                                                            [100%]
13 passed in 0.24s
```

### C2 Regression

**Command:**
```powershell
.venv\Scripts\python.exe -m pytest tests/test_c2_signal_board_decision_boundary.py tests/test_signal_board_ux_polish.py tests/test_signal_api.py -q
```

**Output:**
```
...................................        [100%]
35 passed, 1 warning, 30 subtests passed in 3.02s
```

### C1 Regression

**Command:**
```powershell
.venv\Scripts\python.exe -m pytest tests/test_c1_signal_board_admission_risk.py tests/test_c1_admission_bypass.py -q
```

**Output:**
```
.................                                                        [100%]
17 passed, 1 warning in 1.59s
```

### C0 Regression

**Command:**
```powershell
.venv\Scripts\python.exe -m pytest tests/test_c0_admission_boundary.py tests/test_c0_anti_bypass.py -q
```

**Output:**
```
...........                                                              [100%]
11 passed in 4.89s
```

### B6 Regression

**Command:**
```powershell
.venv\Scripts\python.exe -m pytest tests/test_b6_validation_flow.py tests/test_b6_c_admission_gate.py tests/test_b6_no_shortcuts.py -q
```

**Output:**
```
..........................                                           [100%]
26 passed, 4 subtests passed in 0.92s
```

### B5 Regression

**Command:**
```powershell
.venv\Scripts\python.exe -m unittest tests.test_b5_oos_budget tests.test_b5_oos_controller tests.test_b5_report_builder tests.test_b5_cost_stress tests.test_b5_control_comparison tests.test_b5_gate_v2 tests.test_b5_gate_explanation tests.test_b5_promotion_boundary tests.test_b5_vertical_flow tests.test_b5_compatibility -v
```

**Output (last 10 lines):**
```
test_b5_uses_frozen_protocol_contracts (tests.test_b5_compatibility.TestB5Compatibility.test_b5_uses_frozen_protocol_contracts)
B5 uses frozen B3 protocol contracts. ... ok

----------------------------------------------------------------------
Ran 112 tests in 0.170s

OK
```

### B4 Regression

**Command:**
```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -p "test_b4*.py" -v
```

**Output (last 10 lines):**
```
test_strategy_cannot_bypass_cursor_to_raw_dataset (test_b4_time_cursor.TestBacktestTimeCursor.test_strategy_cannot_bypass_cursor_to_raw_dataset)
Strategy cannot access raw dataset, only via cursor API. ... ok
test_unknown_symbol_or_date_fails_loud (test_b4_time_cursor.TestBacktestTimeCursor.test_unknown_symbol_or_date_fails_loud)
Unknown symbol/date must raise explicit error, not return None. ... ok
test_validate_read_request (test_b4_time_cursor.TestBacktestTimeCursor.test_validate_read_request)
Validate BacktestReadRequest against cursor. ... ok

----------------------------------------------------------------------
Ran 131 tests in 6.223s

OK
```

### Full Test Suite

**Command:**
```powershell
.venv\Scripts\python.exe -m pytest tests/ -x --tb=short -q
```

**Output (last 10 lines):**
```
============================== warnings summary ===============================
.venv\Lib\site-packages\fastapi\testclient.py:1
  StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.

backend\app\main.py:30
  DeprecationWarning: on_event is deprecated, use lifespan event handlers instead.

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
1428 passed, 2 skipped, 3 warnings, 52 subtests passed in 91.60s (0:01:31)
```

---

## 6. Forbidden Term Search Results

### Chinese Forbidden Phrases

**Command:**
```bash
grep -r "一键下单\|自动执行\|推荐买入\|推荐卖出\|立即买入\|立即卖出" --include="*.py" --include="*.ts" --include="*.tsx" .
```

**Result:** All occurrences found only in test files:
- `tests/test_c2_signal_board_decision_boundary.py`
- `tests/test_c3_action_plan_copy_boundary.py`
- `tests/test_signal_board_ux_polish.py`

**Conclusion:** No forbidden phrases in production code. ✅

### Chinese Profit/Ranking Phrases

**Command:**
```bash
grep -r "目标价\|实盘可用\|保证盈利\|稳定盈利\|最佳策略\|策略排名" --include="*.py" --include="*.ts" --include="*.tsx" .
```

**Result:** All occurrences found only in test files:
- `tests/test_c2_signal_board_decision_boundary.py`
- `tests/test_c3_action_plan_copy_boundary.py`
- `tests/test_signal_board_ux_polish.py`

**Conclusion:** No profit/ranking phrases in production code. ✅

### Execution Fields

**Command:**
```bash
grep -r "fill_price\|fill_qty\|realized_pnl" --include="*.py" --include="*.ts" --include="*.tsx" .
```

**Result:**
- `backend/scripts/export_backtest_result.py` - B-module backtest export
- `backend/services/b4_protocol_types.py` - B4 protocol contracts
- `contracts/stable.py` - B-module contracts
- `strategy_core/` - B-module backtest engine
- `tests/test_b4_*.py` - B4 backtest tests
- `tests/test_c3_action_plan_boundary.py` - Test assertions that forbidden fields are rejected

**Conclusion:** Execution fields only in B-module and test assertions. No C3 production code uses them. ✅

### Order ID

**Command:**
```bash
grep -r "order_id" --include="*.py" --include="*.ts" --include="*.tsx" . | grep -v ".venv"
```

**Result:**
- `backend/scripts/export_backtest_result.py` - B-module backtest export
- `backend/services/b4_protocol_types.py` - B4 protocol contracts
- `contracts/stable.py` - B-module contracts
- `strategy_core/` - B-module backtest engine
- `tests/test_b4_*.py` - B4 backtest tests
- `tests/test_c3_action_plan_boundary.py` - Test assertions that order_id is rejected

**Conclusion:** `order_id` only in B-module and test assertions. No C3 production code uses it. ✅

### Approved for Execution

**Command:**
```bash
grep -r "approved_for_execution" --include="*.py" --include="*.ts" --include="*.tsx" .
```

**Result:**
- `contracts/signal_board.py` - Comment: "No 'approved_for_execution' status (M4 doesn't execute trades)"
- `tests/test_signal_model.py` - Test that rejects invalid status

**Conclusion:** `approved_for_execution` only in comments and test rejections. Not a real status. ✅

---

## 7. Git Status

**Command:**
```powershell
git status --short
```

**Output:**
```
M docs/superpowers/plans/2026-06-29-c3-action-plan-human-execution-boundary.md
```

**Note:** Plan doc was modified during reading. No untracked C3 implementation files.

---

## 8. Git Log

**Command:**
```powershell
git log --oneline -10
```

**Output:**
```
ac970f4 fix(c3): block execute/partial on blocked or expired Action Plans
74efd0c feat(c3): add Action Plan frontend panel
fdaf2a2 feat: C3-3 add Action Plan API endpoints
80cdc03 fix: C3-2 make Action Plan builder fully deterministic
6bd7cf1 feat: C3-2 add deterministic Action Plan builder
66c8f63 docs: C3-1 Signal Board scope audit and implementation boundary
9dbe4ab docs: update C2 verification with final test results and commit
f4131c0 fix: C2 add review rejection tests and expand forbidden terms
ed7748a fix: C2 enforce admission in review endpoints and expand tests
fa8fcba docs: C2 Signal Board decision boundary verification
```

---

## 9. Protected Files

### Not Touched by C3

C3 did not modify any of these protected files:

- ✅ `backend/services/c_admission_gate.py` (C0 admission gate)
- ✅ `backend/db/strategy.py` (B-module strategy DB)
- ✅ `contracts/strategy.py` (B-module frozen contracts)
- ✅ `backend/scripts/generate_planned_signals.py` (C0 signal generation)
- ✅ `backend/services/strategy_promotion_reducer.py` (B6 promotion reducer)
- ✅ All B3/B4/B5/B6 validation files
- ✅ `docs/verification/C0_VERIFICATION.md`
- ✅ `docs/verification/C1_VERIFICATION.md`
- ✅ `docs/verification/C2_VERIFICATION.md`

### Modified Files (Expected)

C3 only modified files within its scope:

- ✅ `contracts/action_plan.py` (new)
- ✅ `backend/services/action_plan_builder.py` (new)
- ✅ `backend/api/signal_board.py` (added 2 endpoints)
- ✅ `backend/db/signal_board.py` (added action_plan_decisions table)
- ✅ `frontend/lib/api-client.ts` (added ActionPlan types)
- ✅ `frontend/components/ActionPlanPanel.tsx` (new)
- ✅ `frontend/app/signals/[signal_id]/page.tsx` (integrated panel)
- ✅ `tests/test_c3_action_plan_boundary.py` (new)
- ✅ `tests/test_c3_action_plan_copy_boundary.py` (new)

---

## 10. Remaining Risks

### 10.1 Known Limitations

1. **SQLite FK not enforced by C3**
   - `action_plan_decisions.signal_id` has no database-level FK constraint
   - Admission is enforced by API calling `get_admitted_signal()` before operations
   - Risk: If direct DB write bypasses API, unadmitted signal could have decision
   - Mitigation: All access goes through API, no direct DB write exposed

2. **Forbidden fields are ignored, not rejected**
   - POST decision endpoint ignores `order_id`, `broker`, `fill_price`, etc. if sent
   - Does not return 400 for forbidden fields
   - Risk: Silent ignoring could hide API misuse
   - Mitigation: Test verifies fields are not stored; frontend does not send them

3. **Latest decision wins (not append-only ledger)**
   - `action_plan_decisions` table stores one latest decision per signal
   - Overwriting previous decision loses history
   - Risk: Cannot audit decision changes over time
   - Mitigation: C3 scope is human intent recording, not full audit trail; C4 Execution Log will have full history

4. **Freshness MVP uses date arithmetic, not trading calendar**
   - Stale/expired calculated by `intended_date + 1/2 days`, not trading days
   - Weekend/holiday logic not implemented
   - Risk: Signal intended for Friday marked expired on Monday (skips weekend)
   - Mitigation: Documented as MVP limitation; future enhancement when trading calendar integrated

### 10.2 Out of Scope (Deferred to C4/C5)

These are explicitly NOT in C3 scope:

- ❌ Execution Log (C4)
- ❌ Actual fill records (C4)
- ❌ Broker integration (C4)
- ❌ Post-market review (C5)
- ❌ Realized P&L calculation (C4)
- ❌ Live trading (not in MVP scope at all)
- ❌ Real-time refresh (future enhancement)
- ❌ Strategy ranking (future enhancement)

### 10.3 Frontend-Only Risks

1. **User might interpret "准备执行" as automatic execution**
   - Mitigation: Required disclaimer "不会自动交易" displayed on every Action Plan panel
   - Mitigation: No "execute now" or "auto-trade" language used

2. **User might miss blocking conditions**
   - Mitigation: Execute/partial buttons disabled when `!canAct`
   - Mitigation: Blocking notice displayed prominently in red when conditions exist

3. **User might interpret Action Plan as profit guarantee**
   - Mitigation: Neutral language (入场/离场/处理/放弃, not 买入/卖出建议)
   - Mitigation: Required disclaimer "不是买卖建议"

---

## 11. Summary

### Implementation Scope

C3 implemented:
- ✅ Deterministic Action Plan builder (rule-based, no LLM)
- ✅ Pre-action checks (6 checks: admission, freshness, evidence, risk, snapshot, revision)
- ✅ Invalidation checks (4 checks: expired signal, blocked evidence, ignored/expired review)
- ✅ User decision recording (execute/partial/skip/expired)
- ✅ Decision mapping to Signal Board review_status
- ✅ Admission enforcement on all C3 endpoints
- ✅ API guardrails (reason required for skip/partial/expired, execute/partial blocked on expired/blocked)
- ✅ Frontend Action Plan panel with blocking UI
- ✅ Neutral copy boundary (人工处理计划, not 买卖建议)
- ✅ Required disclaimer (不是买卖建议，不会自动交易)

C3 did NOT implement (scope violations prevented):
- ❌ Execution Log
- ❌ Broker/order/fill fields
- ❌ Realized P&L
- ❌ Automatic trading
- ❌ Buy/sell recommendations
- ❌ Profit guarantees
- ❌ Strategy ranking
- ❌ Live refresh

### Boundary Enforcement

All boundaries verified:
- ✅ Admission enforcement (unadmitted signals → 404)
- ✅ Deterministic builder (same input → identical output)
- ✅ No execution fields (no order_id/broker/fill_price/realized_pnl)
- ✅ Blocked/expired cannot execute or partial (API rejects, frontend disables)
- ✅ Copy boundary (forbidden phrases only in tests)
- ✅ C0/C1/C2 regression (all tests pass)
- ✅ B-module regression (all tests pass)

### Test Results

- **C3 boundary tests:** 34 passed
- **C3 copy boundary tests:** 13 passed
- **C2 regression:** 35 passed, 30 subtests passed
- **C1 regression:** 17 passed
- **C0 regression:** 11 passed
- **B6 regression:** 26 passed, 4 subtests passed
- **B5 regression:** 112 passed
- **B4 regression:** 131 passed
- **Full test suite:** 1428 passed, 2 skipped

### Forbidden Term Search

All forbidden phrases found only in test files:
- ✅ 推荐买入, 推荐卖出, 立即买入, 立即卖出, 一键下单, 自动执行
- ✅ 保证盈利, 稳定盈利, 实盘可用, 目标价, 最佳策略, 策略排名
- ✅ fill_price, fill_qty, realized_pnl, order_id, approved_for_execution

No forbidden terms in C3 production code.

### Protected Files

C3 did not modify:
- ✅ C0/C1/C2 admission gates
- ✅ B-module validation files
- ✅ Signal generation script
- ✅ Strategy DB
- ✅ StrategyPromotionReducer
- ✅ Existing verification docs

### Git State

- **Modified:** 1 file (plan doc, non-code)
- **Untracked:** 0 files
- **Working tree:** Clean (no uncommitted C3 changes)

### Remaining Risks

Known limitations documented:
1. SQLite FK not enforced (API enforces admission)
2. Forbidden fields ignored, not rejected (test verifies not stored)
3. Latest decision wins, not append-only (C4 will have full ledger)
4. Freshness MVP uses date arithmetic, not trading calendar

Out-of-scope items deferred:
- Execution Log (C4)
- Broker integration (C4)
- Post-market review (C5)
- Realized P&L (C4)

---

## 12. Status

**READY_FOR_REVIEW**

C3 Action Plan implementation complete:
- All tests pass (1428 passed, full suite)
- No scope violations detected
- All boundaries enforced
- Copy boundary verified
- Regression tests pass
- Forbidden terms absent from production code
- Protected files untouched

**Next Step:**

Ready for project review of C3 final verification.

---

**Verification Completed:** 2026-06-29
