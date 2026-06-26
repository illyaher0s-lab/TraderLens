# M2 Contracts Stability Review - CLOSED

**Last Updated**: 2026-06-22  
**Status**: CLOSED ✅  
**Final Test Count**: Part of M2 total: 299 tests (214 baseline + 85 M2), 1 skipped

---

## M2 Final Closeout Summary

**Completion Date**: 2026-06-22

M2 Contracts Stability Review is complete and closed as part of M2 milestone closeout.

### M2 Complete Achievement

**Three Major Areas**:
1. ✅ Contracts Stability Review (+28 tests)
2. ✅ Data Source Interface (+42 tests)  
3. ✅ Task Execution Boundaries (+15 tests)

**Total M2 Growth**: +85 tests (39.7% from M1 baseline)

### Contracts Achievement

**Phase 1-8 Completed**:
- Phase 1-7: Contract architecture, migration, documentation
- Phase 8: Serialization tests (14 tests)
- Phase 9: CSV schema lock (9 tests)  
- Phase 10: schema_version export (5 tests)

**Final Contracts Deliverables**:
- 25 stable contracts (M2 LOCKED)
- 11 draft contracts (reserved for M3+)
- CSV schema fully locked (4 files)
- Schema version 1.0 in all JSON exports
- strategy_core fully decoupled from backend.app
- Backward compatibility layer preserved

---

## Contracts Explicitly NOT Included (M2 Decision)

**Intentionally deferred** (not missing, explicitly out of scope):
- ❌ signals.csv export (no current consumer)
- ❌ positions_daily.csv export (replay not required for M2)
- ❌ backtest_summary.txt (JSON exports sufficient)
- ❌ Large backtest pagination/compression (no scale issue yet)
- ❌ backend/scripts migration to new imports (backward compatibility layer works)

**Rationale**: M2 focused on core backtest pipeline contracts. Export expansion deferred to M3+ based on actual need.

---

## M2 Contracts - No Further Changes

**M2 is CLOSED**. No further changes to:
- Contract definitions (stable/draft/reserved)
- CSV schema (locked column order)
- Export format (schema version 1.0)
- Serialization behavior

Breaking changes require M3 and schema version 2.0.

---

## Next Milestone: M3

See `docs/design/M3-PLANNING.md` for M3 scope discussion.

Contracts remain stable; M3 will focus on:
- Async execution (optional)
- Real data integration (optional)
- Research modules (Evidence, Serenity)
- Live execution (if needed)

## Completed (2026-06-22)

### Phase 1: Contract Package Architecture ✅

Created shared `contracts/` package with three modules:
- `contracts/__init__.py`: Package exports + schema version
- `contracts/stable.py`: 25 stable contracts (M2 freeze target)
- `contracts/draft.py`: 11 draft contracts (reserved for M3+)

**Design decisions**:
- Stability tiers: STABLE (production) / DRAFT (not implemented) / RESERVED (future)
- Schema version: `1.0` (M2 freeze target)
- Base class: `ContractModel(BaseModel)` with `extra="forbid"`
- Import isolation: `strategy_core` will import from `contracts.stable` (no `backend.app` dependency)

### Phase 2: Stable Contracts (25 models) ✅

**Market Data** (3):
- `StockIdentity`, `DailyBar`, `DailyStatus`

**Strategy Configuration** (13):
- `StrategyConfig`, `UniverseConfig`, `RuleGroup`, `RiskFilters`, `RebalanceConfig`
- `FillModel`, `FillHandling`, `BacktestConfig`, `BenchmarkConfig`, `SampleSplit`
- `DataRange`, `HypothesisSourceSnapshot`, `AuditSnapshot`

**Execution Artifacts** (5):
- `Signal`, `Order`, `OrderGenerationEvent`, `OrderGenerationResult`, `FrozenLot`, `Trade`

**Backtest Output** (5):
- `BacktestResult`, `BacktestMetrics`, `RoundTrip`, `DailyPortfolioValue`
- `PrototypeGateConfig`, `PrototypeGateResult`

### Phase 3: Draft Contracts (11 models) ✅

**Research** (5):
- `EvidenceItem`, `EvidenceOutput`, `KillCriteria`, `KillCriteriaSnapshot`, `HypothesisDraft`

**Execution Tracking** (3):
- `PositionPlan`, `InvalidCondition`, `TradePlan`, `ExecutionLog`

**Forward Pipeline** (1):
- `ForwardCandidate`

**Task Abstractions** (3):
- `BacktestTask`, `BacktestReport`, `AuditLog` (M2 boundary discussion)

### Phase 4: Field Tightening ✅

**Changed**:
- `Trade.trade_date`: `date | None` → `date` (always set by fill simulator)

**Rationale**: Rejected orders don't create `Trade` records; rejection reason goes to `Order.rejection_reason`.

### Phase 5: Backward Compatibility Layer ✅

Maintained `backend/app/contracts.py` as re-export layer:
- Old imports still work: `from backend.app.contracts import StrategyConfig`
- New imports recommended: `from contracts.stable import StrategyConfig`
- Will be removed after backend/scripts migration complete

**Verification**:
- ✅ Old import path works
- ✅ New import path works
- ✅ 214 tests pass (1 skipped)

### Phase 6: Documentation ✅

Created `docs/contracts/M2-CONTRACTS.md`:
- Contract categories and stability tiers
- Import rules (old vs new paths)
- Serialization guarantees (JSON key order, CSV column order)
- Extension policy (strict top-level, reserved `meta` field)
- Validation rules (field-level, model-level, semantic)
- M2 contract changes (tightened fields)
- Contract ownership and migration plan
- Testing guidelines
- FAQ

### Phase 7: strategy_core Import Migration ✅

**Migration complete**: All 11 `strategy_core` files migrated from `backend.app.contracts` to `contracts.stable`.

**Migrated files**:

**Batch 1 - Parse & Validate** (4 files):
- `strategy_core/dsl_parser.py`: `StrategyConfig`
- `strategy_core/validator.py`: `StrategyConfig`
- `strategy_core/universe_builder.py`: `StrategyConfig`
- `strategy_core/signals.py`: `DailyBar`, `Signal`, `StrategyConfig`

**Batch 2 - Execution** (3 files):
- `strategy_core/orders.py`: `Order`, `OrderGenerationEvent`, `OrderGenerationResult`, `Signal`
- `strategy_core/portfolio.py`: `FrozenLot`
- `strategy_core/fill_simulator.py`: `Order`

**Batch 3 - Results** (4 files):
- `strategy_core/lot_matching.py`: `Trade`, `RoundTrip`
- `strategy_core/metrics.py`: `BacktestMetrics`, `DailyPortfolioValue`, `Trade`
- `strategy_core/prototype_gate.py`: `PrototypeGateConfig`, `PrototypeGateResult`, `BacktestMetrics`, `DailyPortfolioValue`, `Trade`
- `strategy_core/backtest_engine.py`: `BacktestResult`, `DailyPortfolioValue`, `Trade`, `StrategyConfig`

**Verification**:
- ✅ No remaining `from backend.app.contracts import` in `strategy_core/`
- ✅ All module-specific tests pass (91 tests across batches)
- ✅ Full test suite passes (214 tests, 1 skipped)
- ✅ `strategy_core` now has zero dependency on `backend.app`

**Migration strategy**:
- Batch migration by module dependency (parse → execution → results)
- Verified tests after each batch (incremental validation)
- No breaking changes to contract semantics
- Backward compatibility layer preserved for `backend/scripts` and tests

### Phase 8: Contract Serialization Tests ✅

**Test coverage complete**: 14 tests covering core backtest artifacts.

**Test file**: `tests/test_contract_serialization.py`

**Test suites**:

1. **JSON Round-Trip** (4 tests):
   - `Trade`: complete transaction record with cost breakdown
   - `RoundTrip`: completed buy→sell pair with realized PnL
   - `DailyPortfolioValue`: daily portfolio snapshot
   - `BacktestMetrics`: performance summary

2. **Date/Datetime Format** (2 tests):
   - `date` fields serialize to ISO format (`YYYY-MM-DD`)
   - `datetime` fields serialize to ISO format with timezone

3. **Decimal/Float Precision** (2 tests):
   - Return/drawdown/sharpe preserve 6 decimal places
   - PnL fields preserve 2 decimal places (cents)

4. **Backward Compatibility** (2 tests):
   - Old import path (`backend.app.contracts`) points to same classes
   - Instances from old path are identical to new path

5. **Deterministic Serialization** (2 tests):
   - Same object produces same JSON string (stable for hashing)
   - Dict mode preserves field order (Pydantic default)

6. **Schema Version** (2 tests):
   - `SCHEMA_VERSION` constant is defined and accessible
   - Export-level metadata includes `schema_version` (not per-model)

**Verification**:
- ✅ All 14 serialization tests pass
- ✅ Full test suite passes (228 tests, 1 skipped)
- ✅ Core contracts (Trade, RoundTrip, Metrics, DailyPortfolioValue) validated
- ✅ JSON round-trip is lossless for financial data
- ✅ Date/datetime formats are ISO-compliant
- ✅ Float precision policy is documented (6 decimals for ratios, 2 for PnL)
- ✅ Backward compatibility confirmed (old import = new import)
- ✅ Deterministic serialization enables content hashing

**Design decisions validated**:
- Schema version at export level, not per-model (Trade doesn't need `schema_version` field)
- Pydantic default serialization is deterministic (field order stable)
- Float precision sufficient for financial use cases (6 decimals for metrics, 2 for PnL)
- Backward compatibility layer works correctly (old imports resolve to new classes)

---

## Next Steps (Serialization & Schema Lock Phase)

### 1. Add serialization tests ⏳

**Priority: HIGH** (validates M2 freeze target)

New test file: `tests/test_contract_serialization.py`

**Test coverage**:
- JSON round-trip (serialize + deserialize = identity)
- Schema version recording
- Backward compatibility (old import = new import)
- CSV column order stability
- Missing value semantics (`null` vs `[]`)

**Acceptance**:
- All stable contracts pass round-trip test
- Schema version `1.0` recorded in test
- No data loss or type coercion in JSON serialization

### 2. Lock CSV schema ⏳

**Priority: HIGH** (blocks export format finalization)

Document locked column order in `docs/contracts/CSV-SCHEMA.md`:
- `trades.csv`: 13 columns (trade_id → cost)
- `round_trips.csv`: 11 columns (symbol → return_pct)
- `equity_curve.csv`: 4 columns (date → return_pct)
- `order_generation_events.csv`: 8 columns

**Rule**: New fields must be appended (no reordering).

**Verification**:
- Read current export code and document actual column order
- Add test to verify column order doesn't change
- Mark as locked in schema doc

### 3. Add schema_version to exports ⏳

**Priority: MEDIUM** (enables version detection in external tools)

Update export files to include schema version:

```json
{
  "schema_version": "1.0",
  "generated_at": "2026-06-22T12:00:00",
  "data_source": "fixed_fixture",
  "strategy_id": "strategy_001",
  ...
}
```

**Files to update**:
- `backend/scripts/export_backtest_result.py`: wrap `metrics.json` output
- Suite summary: add `schema_version` field
- Backtest result exports: add metadata wrapper

**Verification**:
- All exports include `schema_version: "1.0"`
- Old exports without version can be detected (missing field)

### 4. Document backend/scripts import status ⏳

**Priority: LOW** (backward compatibility layer works, not urgent)

Survey which `backend/scripts` files still use `backend.app.contracts`:
- `export_backtest_result.py`
- `compare_backtests.py`
- `run_strategy_suite.py`
- `validate_fixed_fixture.py`
- Others?

**Decision**: Keep old imports in `backend/scripts` for now (M2 focus is `strategy_core`).

Optional migration can happen in M3 or when adding new scripts.

---

## Design Decisions Log

### Decision 1: Shared contracts package (not strategy_core/contracts)

**Option A**: Move contracts to `strategy_core/contracts.py`
**Option B**: Create shared `contracts/` package

**Chosen**: Option B

**Reason**: 
- `strategy_core` is execution core, not contract owner
- `backend/scripts`, `tests`, future `web` all need contracts
- Shared package avoids circular dependencies
- Clear separation: `contracts/` = data shape, `strategy_core/` = trading logic

### Decision 2: Tighten Trade.trade_date (optional → required)

**Option A**: Keep `trade_date: date | None` (loose)
**Option B**: Make `trade_date: date` (strict)

**Chosen**: Option B

**Reason**:
- Fill simulator always sets `trade_date` after successful fill
- Rejected orders don't create `Trade` records (rejection → `Order.rejection_reason`)
- Optional field without clear "when is it None" semantics is technical debt
- Tighter contracts = easier debugging

### Decision 3: Backward compatibility layer (not immediate breaking change)

**Option A**: Remove `backend/app/contracts.py` immediately
**Option B**: Keep as re-export layer during migration

**Chosen**: Option B

**Reason**:
- 11 files in `strategy_core` import from `backend.app.contracts`
- Migration can be done incrementally (1-2 files at a time)
- Tests continue to pass during migration
- Can verify each file independently

### Decision 4: Stability tier classification (not version suffixes)

**Option A**: Use version suffixes (`StrategyConfigV1`, `StrategyConfigV2`)
**Option B**: Use stability tiers (STABLE/DRAFT/RESERVED) + schema version

**Chosen**: Option B

**Reason**:
- Version suffixes clutter imports (`from contracts import StrategyConfigV1, TradeV1, ...`)
- Stability tier communicates intent (production-ready vs experimental)
- Schema version applies to entire contract set (not individual models)
- Easier migration path (bump schema version, not rename every contract)

---

## Open Questions (M2)

1. **Extension field `meta`**: Should we add `meta: dict[str, Any] | None = None` to stable contracts now, or wait until needed?
   - Pro: Future-proof for external integrations
   - Con: Encourages loose data instead of explicit fields
   - **Recommendation**: Wait until concrete use case

2. **Draft contract promotion**: When should `BacktestTask` / `AuditLog` be promoted to stable?
   - Currently: defined but not implemented
   - M2 Task Execution Boundaries discussion will decide
   - **Recommendation**: Keep draft until task abstraction is finalized

3. **CSV null semantics**: How should missing optional fields be represented in CSV?
   - Option A: Empty string `""`
   - Option B: Literal `"null"`
   - Option C: Omit column entirely
   - **Recommendation**: Document in CSV-SCHEMA.md (currently using pandas default)

---

## Verification Checklist

- ✅ `contracts/` package created
- ✅ 25 stable contracts in `contracts/stable.py`
- ✅ 11 draft contracts in `contracts/draft.py`
- ✅ Backward compatibility layer in `backend/app/contracts.py`
- ✅ Documentation in `docs/contracts/M2-CONTRACTS.md`
- ✅ Schema version `1.0` defined
- ✅ Old import path works
- ✅ New import path works
- ✅ 214 tests pass
- ⏳ `strategy_core` imports migrated
- ⏳ Serialization tests added
- ⏳ CSV schema locked
- ⏳ `schema_version` added to exports

---

## Next Session Goals

1. Migrate 1-2 `strategy_core` files to new import path
2. Verify tests still pass
3. Migrate remaining files
4. Add serialization round-trip tests
5. Document CSV column order lock

Estimated time: 1-2 hours
