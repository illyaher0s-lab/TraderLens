# C1 Signal Board Admission Enforcement Verification

**Purpose:** Record C1 acceptance state, guarantees, non-guarantees, tests, and known boundaries.

**Status:** C1 completed and verified. C1 enforces Signal Board display-layer admission filtering. It is not UI completion, live trading readiness, or profit proof.

---

## Accepted Commits

| Task | Commit | Description |
|------|--------|-------------|
| C1 Task 1 | `dc1e44e` | test: identify Signal Board admission display risk |
| C1 Task 2 | `9e8199f` | feat: add C admission metadata to PlannedSignal and SignalBoardDB |
| C1 Task 3 | `48bdf6e` | feat: filter Signal Board results by C admission status |
| C1 Task 4 | `eab2aaf` | test: block Signal Board admission bypasses |
| C1 Task 5 | `359abd1` | docs: Signal Board admission enforcement verification |
| C1 Test Fix | `298b70c` | fix: update test helpers with C1 admission metadata |
| C1 Doc Update | `b41d366` | docs: update C1 verification with final commit hashes |
| C1 API Fix | `66a8287` | fix: remove include_missing_admission from public API, enforce admission filter |
| C1 Final Doc | `289a3c7` | docs: update C1 verification - API does not expose audit mode to users |

---

## What C1 Proves

- `PlannedSignal` records C admission metadata: `strategy_revision_id`, `lifecycle_state_at_generation`, and `admission_source`.
- `SignalBoardDB` stores admission metadata and filters list results to `lifecycle_state_at_generation == "prototype_passed"` by default.
- Public Signal Board API list endpoints do not expose `include_missing_admission`.
- Old or missing-admission signals are hidden from public list results by default.
- Candidate, draft, rejected, and needs-review signals are hidden from public list results.
- Admission filtering is deterministic and has no LLM, broker, or live-trading dependency.

---

## What C1 Does Not Prove

- C1 does not redesign or complete the Signal Board UI.
- C1 does not generate signals; signal generation remains in `backend/scripts/generate_planned_signals.py`.
- C1 does not create action plans or buy/sell recommendations.
- C1 does not enable live trading.
- C1 does not guarantee future profit.
- C1 does not backfill admission metadata for old signals.

---

## Known Boundaries

- DB-layer audit mode remains available through `include_missing_admission=True` for internal code and tests only.
- Public API list endpoints always enforce admission filtering and do not expose audit mode.
- C1 list filtering does not by itself prove that every future Signal Board endpoint is filtered. Direct detail lookup is a C2 review item.
- Manual raw DB writes are outside C1's runtime protection. Public paths must continue to go through C0/C1 gates.

---

## Test Record

Recorded from final C1 report on 2026-06-28:

- C1 focused tests: 17 passed, 1 warning.
- C0 regression: 11 passed.
- B6 regression: 26 passed, 4 subtests passed.
- B5 regression: 112 passed.
- B4 regression: 131 passed.
- Full pytest: 1368 passed, 2 skipped, 3 warnings, 28 subtests passed.

Mandatory commands for future C1 changes:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_c1_signal_board_admission_risk.py tests/test_c1_admission_bypass.py -q
.venv\Scripts\python.exe -m pytest tests/test_c0_admission_boundary.py tests/test_c0_anti_bypass.py -q
.venv\Scripts\python.exe -m pytest tests/test_b6_validation_flow.py tests/test_b6_c_admission_gate.py tests/test_b6_no_shortcuts.py -q
.venv\Scripts\python.exe -m unittest tests.test_b5_oos_budget tests.test_b5_oos_controller tests.test_b5_report_builder tests.test_b5_cost_stress tests.test_b5_control_comparison tests.test_b5_gate_v2 tests.test_b5_gate_explanation tests.test_b5_promotion_boundary tests.test_b5_vertical_flow tests.test_b5_compatibility -v
.venv\Scripts\python.exe -m unittest discover -s tests -p "test_b4*.py" -v
.venv\Scripts\python.exe -m pytest tests/ -x --tb=short -q
```

---

## Review Rule

Any future change touching these files is a C1 regression risk:

- `contracts/signal_board.py`
- `backend/db/signal_board.py`
- `backend/api/signal_board.py`
- `backend/scripts/generate_planned_signals.py`
- `tests/test_c1_signal_board_admission_risk.py`
- `tests/test_c1_admission_bypass.py`

Protected files for C1 scope:

- `backend/services/strategy_promotion_reducer.py`
- `backend/services/c_admission_gate.py`
- `backend/db/strategy.py`
- `contracts/strategy.py`

---

## Next Work

C2 should review user-facing Signal Board decision boundaries:

- Direct detail lookup must not show unadmitted signals.
- Frontend types should include C1 admission metadata.
- Signal Board copy must say planned signal, not buy/sell advice.
- Signal Board copy must not claim profit, live-trading readiness, or auto-execution.
