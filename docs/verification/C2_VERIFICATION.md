# C2 Signal Board Decision Boundary Verification

**Purpose:** Record C2 acceptance state, guarantees, non-guarantees, tests, and known boundaries.

**Status:** C2 completed and verified. C2 protects Signal Board user-facing decision boundaries. NOT UI redesign, NOT live trading, NOT profit proof.

---

## Accepted Commits

| Task | Commit | Description |
|------|--------|-------------|
| C2 Task 1 | `9e561f1` | test: C2 identify Signal Board detail admission bypass |
| C2 Task 2 | `fdd5415` | feat: C2 enforce admission on Signal Board detail lookup |
| C2 Task 3 | `866ca39` | feat: C2 expose admission metadata to Signal Board frontend type |
| C2 Task 4 | `295aa3b` | feat: C2 lock Signal Board user-facing decision boundary |
| C2 Task 5 | `fa8fcba` | docs: C2 Signal Board decision boundary verification |
| C2 Fix | `ed7748a` | fix: C2 enforce admission in review endpoints and expand tests |
| C2 Fix | `f4131c0` | fix: C2 add review rejection tests and expand forbidden terms |

---

## What C2 Proves

- Direct signal detail lookup cannot show unadmitted signals.
- Review endpoints (POST /api/signals/{id}/review) enforce admission before allowing updates.
- Batch review endpoint filters to only update admitted signals.
- Frontend signal type includes C1 admission metadata (strategy_revision_id, lifecycle_state_at_generation, admission_source).
- User-facing Signal Board copy says the output is a validated planned signal, not buy/sell advice.
- User-facing Signal Board copy does not claim future profit, live trading readiness, one-click execution, or automatic trading.
- Signal Board detail/list pages have no mojibake markers covered by tests.
- Detail API endpoint `/api/signals/{signal_id}` enforces admission filtering via `get_admitted_signal()`.
- Review API endpoints reject draft, rejected, needs_review, and legacy signals (404).

---

## What C2 Does Not Prove

- C2 does not redesign the Signal Board UI.
- C2 does not generate signals; signal generation remains in `backend/scripts/generate_planned_signals.py`.
- C2 does not create action plans or buy/sell recommendations.
- C2 does not enable live trading or broker integration.
- C2 does not guarantee future profit.
- C2 does not modify B3/B4/B5/B6 validation semantics.

---

## Test Results

### C2 Focused Tests

```powershell
.venv\Scripts\python.exe -m pytest tests/test_c2_signal_board_decision_boundary.py tests/test_signal_board_ux_polish.py tests/test_signal_api.py -q
```

**Result:**
```
35 passed, 1 warning, 30 subtests passed in 2.00s
```

### C1 Focused Tests

```powershell
.venv\Scripts\python.exe -m pytest tests/test_c1_signal_board_admission_risk.py tests/test_c1_admission_bypass.py -q
```

**Result:**
```
17 passed, 1 warning in 1.22s
```

### C0 Focused Tests

```powershell
.venv\Scripts\python.exe -m pytest tests/test_c0_admission_boundary.py tests/test_c0_anti_bypass.py -q
```

**Result:**
```
11 passed in 2.90s
```

### B6 Focused Tests

```powershell
.venv\Scripts\python.exe -m pytest tests/test_b6_validation_flow.py tests/test_b6_c_admission_gate.py tests/test_b6_no_shortcuts.py -q
```

**Result:**
```
26 passed, 4 subtests passed in 0.63s
```

### B5 Full Focused Suite

```powershell
.venv\Scripts\python.exe -m unittest tests.test_b5_oos_budget tests.test_b5_oos_controller tests.test_b5_report_builder tests.test_b5_cost_stress tests.test_b5_control_comparison tests.test_b5_gate_v2 tests.test_b5_gate_explanation tests.test_b5_promotion_boundary tests.test_b5_vertical_flow tests.test_b5_compatibility -v
```

**Result:**
```
Ran 112 tests in 0.095s

OK
```

### B4 Regression

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -p "test_b4*.py" -v
```

**Result:**
```
Ran 131 tests in 1.186s

OK
```

### Full pytest

```powershell
.venv\Scripts\python.exe -m pytest tests/ -x --tb=short -q
```

**Result:**
```
1381 passed, 2 skipped, 3 warnings, 52 subtests passed in 57.55s
```

---

## Known Boundaries

- C2 detail lookup filter blocks unadmitted signals via `get_admitted_signal()`.
- Frontend type now includes C1 admission metadata, enabling future UI display of admission context.
- Visible copy disclaimer is enforced by automated tests covering both list and detail pages.
- C2 does not modify Signal Board list, pagination, review, strategy filter, or evidence check features.
- C2 does not touch B-module validation flow or admission gate logic.

---

## Modified Files

- `backend/db/signal_board.py` - Added `get_admitted_signal()` method
- `backend/api/signal_board.py` - Changed detail endpoint to use `get_admitted_signal()`, review endpoints enforce admission
- `frontend/lib/api-client.ts` - Added C1 admission metadata to PlannedSignal type
- `frontend/app/signals/page.tsx` - Updated disclaimer text
- `frontend/app/signals/[signal_id]/page.tsx` - Added disclaimer text
- `tests/test_signal_api.py` - Added direct ID bypass test, review endpoint admission tests (rejected/needs_review), batch review admission test
- `tests/test_c2_signal_board_decision_boundary.py` - Created C2 boundary tests, expanded forbidden terms
- `tests/test_signal_board_ux_polish.py` - Expanded prohibited terms and added mojibake check

---

## Review Rule

Any future change touching these files is a C2 regression risk:

- `backend/api/signal_board.py`
- `backend/db/signal_board.py`
- `frontend/app/signals/page.tsx`
- `frontend/app/signals/[signal_id]/page.tsx`
- `frontend/lib/api-client.ts`
- `tests/test_c2_signal_board_decision_boundary.py`
- `tests/test_signal_board_ux_polish.py`

Protected files for C2 scope (read-only):

- `contracts/signal_board.py`
- `backend/services/c_admission_gate.py`
- `backend/db/strategy.py`
- `contracts/strategy.py`

---

## Git Status

```powershell
git status --short
```

**Result:**
```
(clean)
```

---

## Verification Date

2026-06-28

---

## Next Work

C2 completes the Signal Board decision boundary layer. Future work outside C2 scope:

- Signal Board UI redesign (charts, notifications, batch review)
- Live trading integration (broker API, order execution)
- Action plan generation
- Real-time data feeds
- Strategy performance analytics beyond B-module OOS validation
