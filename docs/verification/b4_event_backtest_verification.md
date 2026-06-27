# B4 Event-Driven Backtest Verification Record

**Purpose**: Record B4 Task 1-11 acceptance state, guarantees, known boundaries, and promotion blocks.

**Status**: B4 completed and verified. Does NOT imply strategy profitability, Gate pass, promotion, or production readiness.

---

## 1. B4 Final Accepted Commit List

| Task | Commit | Description |
|------|--------|-------------|
| **B3 (prerequisite)** | `51eb286` | Protocol snapshot + data snapshot + point-in-time membership |
| **B4 Task 1-4** | `d63e94c` | test: complete B4 time cursor coverage |
| **B4 Task 5** | `3db8196` | fix: enforce cursor-bound event loop reads |
| **B4 Task 6** | `1aa3057` | fix: guarantee event loop rejected order coverage |
| **B4 Task 7** | `f7eb491` | fix: route rank guard through signal path |
| **B4 Task 8** | `e8d4ced` | fix: reject invalid adjustment modes |
| **B4 Task 9** | `b105dac` | feat: add delisting and long suspension liquidation policy |
| **B4 Task 10** | `5854bfc` | fix: lock formal B4 qualification metadata tests |
| **B4 Task 11** | `7c17fca` | fix: use AST extraction for B4 boundary scan |

**Verification Date**: 2026-06-27  
**Total B4 Test Coverage**: 131 tests (all passing)  
**Full Test Suite**: 1198 tests (all passing)

---

## 2. What B4 Now Guarantees

B4 has locked down the following correctness boundaries:

### 2.1 Time Cursor & Future Data Guard
- **T-day signal / T+1 execution separation**: Signal phase (T日) can only read data `<= T`; execution phase (T+1日) can read `<= T+1`.
- **Cursor-bound reads in event loop**: `run_event_backtest()` uses `CursorBoundDataView` that wraps all data access through `BacktestTimeCursor`.
- **Future data hard block**: Any attempt to read `T+1` data during `T` signal phase raises `FutureDataAccessError` (blocking failure, not degraded success).
- **Read trace audit**: All data reads are recorded in `BacktestCursorState.read_trace` for post-run verification.
- **Immutable contracts**: `BacktestCursorState`, `OrderIntentRecord`, `FillRecord`, `EventBacktestResult` are frozen (Pydantic `frozen=True`).

### 2.2 A-Share Fill Constraints (Task 6)
- **T+1 restriction**: Cannot sell same-day purchased stock (enforced via `FrozenLot.purchase_date`).
- **Limit up/down**: Blocks buy at limit-up, sell at limit-down.
- **Suspension**: Blocks both buy and sell when `daily_status.is_suspended == True`.
- **Lot size**: Buy quantity rounds down to 100-share lots; orders below 100 shares rejected.
- **Transaction costs**: Commission (万三, min 5 RMB) + stamp tax (千一, sell only).
- **Slippage**: Applied to fill price (configurable via `FillModel.slippage_bps`).
- **Liquidity check**: Partial fill or rejection when order exceeds available volume.
- **Rejected orders**: Recorded in `EventBacktestResult.rejected_orders` with reason.
- **Cash/position non-negative**: Portfolio cash and position quantity cannot go negative.

### 2.3 Normalization & Ranking Guards (Task 7)
- **Rolling normalization only**: MA conditions use `[T-window+1, ..., T]` data; full-sample mean/std/percentile are hard blocked.
- **Cross-sectional rank uses T-visible universe**: `cross_section_rank()` filters universe by `as_of_date <= current_date` before ranking.
- **Deterministic tie-breaker**: Rank uses stable sort on `(value, symbol)` to ensure reproducible results regardless of input order.
- **Cursor-bound rank reads**: `_evaluate_rank_condition()` routes through `CursorBoundDataView` to block future reads.

### 2.4 Adjustment Snapshot Guards (Task 8)
- **Adjustment factor snapshot date guard**: Factor snapshot dated after `current_date` is a future data violation.
- **Factor fingerprint match**: Adjustment factor source must match `B3 DataSnapshotManifest.adjustment_factor_fingerprint`.
- **Single adjustment mode lock**: First `get_bar()` call locks adjustment mode (`raw`/`qfq`/`hfq`); mixing modes is hard rejected.
- **Read trace records adjustment mode**: Each bar read records the adjustment mode used.

### 2.5 Delisting & Liquidation Policy (Task 9)
- **Delisting detection**: Tracks `daily_status.is_delisted` and forces liquidation.
- **Long suspension liquidation**: Suspensions exceeding threshold trigger forced liquidation with penalty.
- **Penalty policy**: System baseline penalty (default 20%) cannot be lowered at runtime.
- **Liquidation impact tracking**: `EventBacktestResult.liquidation_impact` records loss from penalty.
- **Insufficient liquidation**: Missing delisting status or last tradable price marks result as degraded/insufficient.
- **Portfolio application**: Applying insufficient liquidation raises `ValueError`.

### 2.6 B3 Protocol Integration (Task 10)
- **Protocol snapshot required**: `run_event_backtest()` requires `protocol_snapshot_id` (B3 frozen protocol).
- **Data snapshot hash required**: `run_event_backtest()` requires `data_snapshot_hash` (B3 data fingerprint).
- **Point-in-time membership binding**: Only `PointInTimeMembershipSnapshot` is accepted; `ForwardWatchlistSnapshot` and static symbol lists are rejected.
- **Frozen protocol immutability**: B3 `ResearchProtocolSnapshot` is read-only; mutation attempts raise `FrozenInstanceError`.
- **Duck-typing rejection**: Fake protocol/manifest/universe objects (even with all attributes) are rejected via `isinstance()` checks.
- **Metadata recorded in result**: `EventBacktestResult` includes `protocol_snapshot_id`, `data_snapshot_hash`, and `frozen_at`.

### 2.7 Compatibility Boundaries (Task 11)
- **No LLM**: B4 files must not import `openai`/`anthropic`/`langchain` or call LLM APIs.
- **No Gate**: B4 must not create `PrototypeGateResult`, `GateVerdict`, or call `evaluate_prototype_gate()`.
- **No promotion**: B4 must not create `StrategyPromotionRecord` or write `prototype_passed` state.
- **No Signal Board**: B4 must not depend on `ImmutableBacktestReport`, `SignalBoard`, or `ActionPlan`.
- **No forbidden DB/contracts**: B4 must not import `backend.db.research`, `backend.db.strategy`, `contracts.draft`, or modify B3 frozen objects.
- **Forbidden file protection**: Git diff helper rejects commits modifying `contracts/stable.py`, `backend/db/research.py`, `strategy_core/prototype_gate.py`, etc.
- **AST-based boundary scan**: `backtest_engine.py` uses AST extraction to scan only `run_event_backtest()`, excluding legacy `run_backtest()` with Gate.

### 2.8 Canary Qualification System
- **7 Canary strategies**: Attempt future bar, future status, future financial, future membership, future adjustment, full-sample normalization, and full-sample percentile.
- **Qualification pass criteria**: All Canaries must be **blocked** (raise `FutureDataAccessError`). If any Canary completes normally, qualification fails.
- **Backtest engine qualification result**: `BacktestEngineQualificationResult` is frozen and does not include Gate verdict or promotion fields.

---

## 3. What B4 Does NOT Guarantee

B4 is a **backtest correctness and future-data guard layer**. It does NOT:

1. **Prove strategy profitability**: B4 ensures time-correctness, not alpha. A strategy passing B4 may still lose money.
2. **Approve promotion to `prototype_passed`**: B4 has no Gate logic. Promotion decisions belong to future OOS validation (B5).
3. **Perform formal OOS validation**: B4 runs backtest on configured date range; it does not enforce sample split or OOS budget.
4. **Create Gate result**: `EventBacktestResult` does not have `prototype_gate_result`, `gate_verdict`, or `promotion_record` fields.
5. **Replace B5 OOS budget/cache/Gate work**: B4 is a prerequisite for B5, not a substitute.
6. **Solve all dynamic universe construction**: B4 validates that given a correct T-visible universe, the event loop uses it correctly. Dynamic universe construction beyond B3/PIT snapshot binding is not fully solved by B4 alone.
7. **Enable live trading**: B4 is offline backtest verification. Production readiness requires additional validation (broker integration, order execution, risk controls).

---

## 4. Known Boundaries & Future Work

### 4.1 Task 7 Known Boundary (Normalization & Ranking)
**What Task 7 guarantees**:
- Given a correct T-visible universe, `rank_condition` only ranks that universe and uses cursor-bound T-date reads.
- Rolling normalization (MA conditions) uses only `[T-window+1, ..., T]` data.
- Full-sample normalization is hard blocked.

**What Task 7 does NOT solve**:
- Dynamic point-in-time universe construction **inside** the event loop is not fully solved by Task 7 alone.
- Task 10 (B3/PIT binding) reduces this risk by requiring frozen `PointInTimeMembershipSnapshot`, but future universe-builder work must preserve this boundary.
- Example: If `build_universe()` reads future membership data outside cursor control, Task 7's rank guard will not catch it (because it only guards the rank computation, not the universe construction upstream).

**Mitigation**:
- Task 10 enforces `PointInTimeMembershipSnapshot` with `as_of_date` checks, reducing (but not eliminating) dynamic universe risk.
- Future work: Wrap `build_universe()` to use cursor-bound membership reads.

---

### 4.2 Task 11 Known Boundary (Compatibility Scan)
**What Task 11 guarantees**:
- AST-based extraction of `run_event_backtest()` excludes legacy `run_backtest()` code.
- Keyword scan catches explicit imports (`from strategy_core.prototype_gate`) and forbidden keywords (`PrototypeGateResult`, `openai`, `anthropic`).
- Git diff helper catches modifications to forbidden tracked files (`contracts/stable.py`, `backend/db/research.py`, etc.).

**What Task 11 does NOT catch**:
- Obfuscated imports: `__import__("strategy_core.prototype_gate")` or dynamic `importlib.import_module()`.
- Indirect keyword references: `getattr(module, "PrototypeGateResult")`.
- Untracked files: Git diff only checks tracked files; new untracked files with forbidden code are not caught (but will fail functional tests).

**Mitigation**:
- Task 11 is a **boundary regression guard**, not a formal proof against all possible obfuscation.
- Functional tests (Task 1-10) are the primary defense: if B4 code calls LLM/Gate, those tests will fail.
- Code review must flag suspicious dynamic imports.

---

### 4.3 B4 Overall Boundary
**B4 scope**:
- Backtest correctness: T-day signal semantics, A-share constraints, future data guard, adjustment/delisting/liquidation logic.
- Compatibility boundaries: No LLM, no Gate, no promotion, no Signal Board.

**Out of B4 scope**:
- **Profitability validation**: Belongs to B5/OOS.
- **Production deployment**: Requires broker integration, order execution, risk controls (not B4 responsibility).
- **Dynamic universe construction**: B3/PIT binding reduces risk, but full solution requires future work.
- **Strategy parameter optimization**: B4 runs fixed config; hyperparameter search belongs to separate tooling.

---

## 5. Test Command Record

### 5.1 Combined B4 Test Suite
```powershell
.venv\Scripts\python.exe -m unittest tests.test_b4_time_cursor tests.test_b4_future_data_guard tests.test_b4_canary_qualification tests.test_b4_event_backtest_loop tests.test_b4_ashare_fill_constraints tests.test_b4_normalization_guard tests.test_b4_adjustment_snapshot tests.test_b4_delisting_liquidation tests.test_b4_b3_integration tests.test_b4_compatibility -v
```

**Result** (2026-06-27):
```
Ran 131 tests in 2.986s

OK
```

### 5.2 Full Test Suite
```powershell
.venv\Scripts\python.exe -m pytest tests/ -x --tb=short -q
```

**Result** (2026-06-27):
```
1198 passed, 2 skipped, 3 warnings, 24 subtests passed in 44.21s
```

**Interpretation**:
- All 131 B4-specific tests pass.
- All 1198 tests in the full suite pass (B4 does not break existing functionality).
- 2 skipped tests are unrelated to B4 (pre-existing).
- 3 warnings are deprecation warnings (FastAPI `on_event`, unrelated to B4).

---

## 6. Promotion Block

**B4 completion alone must NOT create or imply**:

1. **`prototype_passed` status**: B4 has no Gate logic. Strategies passing B4 are **NOT** automatically promoted.
2. **`StrategyPromotionRecord`**: B4 does not write promotion records or trigger promotion workflows.
3. **Gate pass**: `EventBacktestResult` does not include `prototype_gate_result`, `gate_verdict`, or `promotion_record` fields.
4. **Production readiness**: B4 is offline backtest verification. Production deployment requires additional validation (broker integration, order execution, risk controls).
5. **Live trading readiness**: B4 does not test real broker API, order routing, or execution latency. It is a correctness layer, not an execution layer.

**Explicit forbidden actions**:
- Do NOT interpret B4 completion as strategy approval.
- Do NOT use B4 results to generate buy/sell recommendations for users.
- Do NOT bypass OOS validation (B5) based on B4 pass.
- Do NOT promote strategies to `prototype_passed` without formal Gate evaluation.

---

## 7. Review Rule

### 7.1 Mandatory Review Triggers
Any future change touching the following must be reviewed as a **B4 regression risk**:

**B4 Core Files**:
- `backend/services/backtest_time_cursor.py`
- `backend/services/future_data_guard.py`
- `backend/services/backtest_engine_qualification.py`
- `backend/services/b4_protocol_types.py`
- `backend/services/canary_strategies.py`
- `strategy_core/backtest_engine.py` (especially `run_event_backtest`)
- `strategy_core/cursor_bound_data_view.py`

**Signal & Execution Path**:
- `strategy_core/signals.py` (especially `generate_signals`, `generate_exit_signals`, ranking/normalization helpers)
- `strategy_core/orders.py`
- `strategy_core/position_sizer.py`
- `strategy_core/fill_simulator.py`
- `strategy_core/transaction_costs.py`

**Data & Adjustment**:
- `strategy_core/trading_calendar.py`
- Any code reading adjustment factors, delisting status, or suspension data

**B3 Integration**:
- `contracts/stable.py` (ResearchProtocolSnapshot, DataSnapshotManifest)
- `contracts/research.py` (PointInTimeMembershipSnapshot)
- `backend/app/golden_cases.py` (GoldenCaseDataSource)

**B4 Test Files**:
- All `tests/test_b4_*.py` files

### 7.2 Mandatory Test Commands
Before merging any change touching B4 files:

```powershell
# Step 1: Run full B4 suite
.venv\Scripts\python.exe -m unittest tests.test_b4_time_cursor tests.test_b4_future_data_guard tests.test_b4_canary_qualification tests.test_b4_event_backtest_loop tests.test_b4_ashare_fill_constraints tests.test_b4_normalization_guard tests.test_b4_adjustment_snapshot tests.test_b4_delisting_liquidation tests.test_b4_b3_integration tests.test_b4_compatibility -v

# Step 2: Run full test suite (ensure no regression in other modules)
.venv\Scripts\python.exe -m pytest tests/ -x --tb=short -q
```

**Pass criteria**:
- All 131 B4 tests must pass.
- All 1198+ tests in full suite must pass.
- No new `FutureDataAccessError` in unexpected places.
- No new violations in compatibility scan.

### 7.3 Forbidden Modifications
The following files are **protected** and must not be modified by B4 or future work touching B4:

- `contracts/stable.py` (B3 frozen contracts)
- `contracts/draft.py` (Strategy draft contracts)
- `contracts/research.py` (Research protocol contracts, read-only for B4)
- `contracts/strategy.py` (Strategy contracts, read-only for B4)
- `backend/db/research.py` (Research DB, no direct access from B4)
- `backend/db/strategy.py` (Strategy DB, no direct access from B4)
- `strategy_core/prototype_gate.py` (Gate logic, excluded from B4 boundary)

If B4 work requires changes to these files, it is a **scope violation** and must be escalated.

---

## 8. Verification Checklist

- [x] All 8 B4 Task commits recorded
- [x] B3 prerequisite commit recorded
- [x] B4 guarantees documented (time cursor, fill constraints, normalization, adjustment, delisting, B3 integration, compatibility)
- [x] B4 non-guarantees documented (no profitability proof, no Gate, no promotion, no OOS, no live trading)
- [x] Known boundaries documented (Task 7 universe construction, Task 11 obfuscation limits, B4 overall scope)
- [x] Promotion block documented (no `prototype_passed`, no Gate pass, no production readiness)
- [x] Review rule documented (mandatory triggers, test commands, forbidden modifications)
- [x] Test results recorded (131 B4 tests pass, 1198 full tests pass)
- [x] No forbidden keywords in doc (no claim of profitability, Gate pass, or production readiness)

---

## 9. Next Steps (Out of B4 Scope)

The following are **explicitly out of B4 scope** and belong to future work:

1. **B5: OOS Validation & Gate Logic**
   - Sample split enforcement (in-sample vs out-of-sample)
   - OOS budget tracking (prevent over-fitting)
   - Formal Gate evaluation (`PrototypeGateResult` with verdict)
   - Strategy promotion to `prototype_passed`

2. **Signal Board & Action Plan**
   - `ImmutableBacktestReport` creation
   - User-facing signal board UI
   - Action plan generation and review workflow

3. **Production Deployment**
   - Broker API integration
   - Order execution and routing
   - Risk controls and position limits
   - Real-time market data feed

4. **Dynamic Universe Construction**
   - Cursor-bound `build_universe()` implementation
   - Point-in-time universe membership validation beyond B3 snapshot

5. **Hyperparameter Optimization**
   - Grid search / Bayesian optimization
   - Walk-forward analysis
   - Multi-objective optimization (return vs drawdown vs Sharpe)

---

**Document Owner**: Orion  
**Last Updated**: 2026-06-27  
**Version**: 1.0
