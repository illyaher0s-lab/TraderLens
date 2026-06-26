# TraderLens Contracts Documentation

**Schema Version**: 1.0  
**Last Updated**: 2026-06-22  
**Status**: M2 Freeze Target

---

## Overview

TraderLens contracts are the stable data interchange protocol between:
- `strategy_core` (deterministic trading logic)
- `backend/scripts` (export, validation, suite runner)
- `tests` (golden cases, integration tests)
- Future modules (Web UI, Evidence Agent, Signal Board)

All contracts are Pydantic models with strict validation (`extra="forbid"`).

---

## Stability Tiers

### STABLE (M2 freeze target)

Contracts used in production code. After M2 closeout:
- **Additive changes allowed**: new optional fields, new enum values
- **Breaking changes require**: schema version bump + migration path
- **Serialization guaranteed**: JSON/CSV structure locked

**Stable contracts**: 25 models in `contracts/stable.py`

### DRAFT

Contracts defined but not yet implemented. Subject to change without migration.

**Draft contracts**: 11 models in `contracts/draft.py`

### RESERVED

Fields/contracts reserved for future milestones (M3+).

---

## Import Rules (M2)

### New code (recommended)

```python
# Import stable contracts directly
from contracts.stable import StrategyConfig, BacktestResult, Trade

# Import draft contracts (research/execution tracking)
from contracts.draft import EvidenceOutput, TradePlan

# Import schema version for serialization
from contracts import SCHEMA_VERSION
```

### Legacy code (backward compatible)

```python
# Old import path still works (compatibility layer)
from backend.app.contracts import StrategyConfig, BacktestResult
```

**Migration path**: `strategy_core` will be migrated to use `contracts.stable` directly (no `backend.app` dependency).

---

## Contract Categories

### 1. Market Data Contracts

| Contract | Stability | Purpose |
|----------|-----------|---------|
| `StockIdentity` | STABLE | Stock metadata (symbol, exchange, list_date, industry) |
| `DailyBar` | STABLE | OHLCV bar with adj_factor; validates low ≤ open, close ≤ high |
| `DailyStatus` | STABLE | Trading status (suspended, limit_up, limit_down, ST) |

**Validators**:
- `DailyBar`: prices ordered, all ≥ 0
- `DailyStatus`: cannot be both limit_up and limit_down

**Used by**: data sources, signal generation, fill simulator

---

### 2. Strategy Configuration Contracts

| Contract | Stability | Purpose |
|----------|-----------|---------|
| `StrategyConfig` | STABLE | Complete strategy definition (entry/exit rules, universe, risk filters, backtest config) |
| `UniverseConfig` | STABLE | Stock selection (static_list or sector_plus_filters) |
| `RuleGroup` | STABLE | Entry/exit rules with AND/OR logic |
| `FillModel` | STABLE | Fill simulation parameters (T+1, commission, stamp_tax, lot_size) |
| `BacktestConfig` | STABLE | Backtest parameters (capital, date range, sample split, benchmark) |
| `PrototypeGateConfig` | STABLE | Gate thresholds (min_trades, min_win_rate, etc.) |

**Key decisions**:
- `StrategyConfig` is the primary input contract for `strategy_core`
- All strategy execution derives from this configuration
- `PrototypeGateConfig.enabled` defaults to `False` (explicit opt-in)

**Validators**:
- `SampleSplit`: OOS start > IS end (no overlap)
- `BacktestConfig`: sample split falls within backtest range
- `Order`: intended_execution_date > signal_date (T+1)

---

### 3. Execution Artifacts

| Contract | Stability | Purpose |
|----------|-----------|---------|
| `Signal` | STABLE | Trading signal (entry/exit/hold) with triggered_rules |
| `Order` | STABLE | Order intent with fill status (planned/filled/rejected) |
| `OrderGenerationEvent` | STABLE | Audit record for order generation (T+1 violations, conflicts) |
| `Trade` | STABLE | Executed trade with transaction cost breakdown |
| `FrozenLot` | STABLE | T+1 frozen shares (unlock_date tracking) |

**Key field decisions (M2)**:
- `Trade.trade_date`: **always set** (not optional). Rejected orders don't create Trade records.
- `Order.actual_execution_date`: optional (set by fill simulator after fill)
- `Order.status`: `planned` → `filled` or `rejected`

**Used by**: backtest engine, fill simulator, order generation

---

### 4. Backtest Output Contracts

| Contract | Stability | Purpose |
|----------|-----------|---------|
| `BacktestResult` | STABLE | Complete backtest output (trades, daily_values, rejected_orders, round_trips, gate_result) |
| `BacktestMetrics` | STABLE | Performance metrics (total_return, max_drawdown, sharpe_ratio, win_rate, profit_factor) |
| `RoundTrip` | STABLE | Completed buy→sell pair (FIFO matched) with realized_pnl and holding_days |
| `DailyPortfolioValue` | STABLE | Daily snapshot (cash, market_value, total_value) |
| `PrototypeGateResult` | STABLE | Gate evaluation (status, failed_checks, warning_checks, recommendation) |

**Key semantics**:
- `BacktestResult` is the primary output contract for `strategy_core`
- All exports (CSV, JSON, PNG) derive from `BacktestResult`
- `RoundTrip.matched_quantity`: portion matched in this round-trip (not original trade quantity)
- `BacktestMetrics.closed_lot_win_rate`: winning matched segments / total matched segments (FIFO)
- `PrototypeGateResult.recommendation`: advisory only, does NOT modify `strategy.status`

---

### 5. Draft Contracts (Not Implemented)

| Contract | Stability | Reserved For |
|----------|-----------|--------------|
| `EvidenceOutput` | DRAFT | Evidence Agent (M3+) |
| `HypothesisDraft` | DRAFT | Serenity / Hypothesis Builder (M3+) |
| `TradePlan` | DRAFT | Signal Board / Action Plan (M3+) |
| `ExecutionLog` | DRAFT | Live execution tracking (M3+) |
| `ForwardCandidate` | DRAFT | Forward-looking research pipeline (M3+) |
| `BacktestTask` | DRAFT | M2 task abstraction discussion |
| `AuditLog` | DRAFT | M2 audit abstraction discussion |

**M2 decision pending**: Should `BacktestTask` / `AuditLog` be promoted to stable, or replaced with different abstractions?

---

## Serialization Guarantees (M2)

### JSON Export

All stable contracts support deterministic JSON serialization:

```python
from contracts.stable import BacktestResult
from contracts import SCHEMA_VERSION

result: BacktestResult = ...
output = {
    "schema_version": SCHEMA_VERSION,
    "generated_at": datetime.now().isoformat(),
    "result": result.model_dump(mode="json")
}
```

**Key order**: Deterministic (Pydantic default field order).

**Missing values**: `null` for `Optional` fields, empty list `[]` for `list` defaults.

### CSV Export

Flattened contracts (Trade, RoundTrip, DailyPortfolioValue) support CSV:

```python
# trades.csv columns (locked in M2)
trade_id, order_id, symbol, direction, quantity, price, trade_date,
gross_amount, commission, stamp_duty, transfer_fee, total_fee, net_cash_flow, cost

# round_trips.csv columns (locked in M2)
symbol, buy_date, sell_date, holding_days, quantity, buy_price, sell_price,
buy_cost, sell_proceeds, realized_pnl, return_pct
```

**Column order**: Locked after M2. New fields must be appended.

**Decimal preservation**: Use `float_format='%.10f'` for pandas export.

---

## Extension Policy (M2)

### Top-level fields: STRICT

Unknown top-level fields are **rejected** (`extra="forbid"`).

```python
# ✓ OK
config = StrategyConfig(..., audit=AuditSnapshot(...))

# ✗ REJECTED
config = StrategyConfig(..., my_custom_field="value")
# ValidationError: Extra inputs are not permitted
```

### Extension field: `meta`

Reserved for future extension:

```python
# Reserved (not yet implemented in M2)
class StrategyConfig(ContractModel):
    ...
    meta: dict[str, Any] | None = None  # Optional extension point
```

**M2 decision**: Not added yet. Will be added if needed for external integrations.

### Draft fields in stable contracts

Draft fields (e.g., `HypothesisSourceSnapshot.llm_model`) are **optional** and **nullable**.

Code must not assume they are populated.

---

## Validation Rules

### Field-level validators

- **Prices**: `ge=0` (all prices non-negative)
- **Quantities**: `gt=0` (quantities strictly positive)
- **Ratios**: `ge=0, le=1` (percentages 0-100%)
- **Dates**: `start <= end` (date ranges)

### Model-level validators

- `DailyBar.prices_are_ordered()`: low ≤ open, close ≤ high
- `SampleSplit.oos_starts_after_in_sample()`: no IS/OOS overlap
- `BacktestConfig.date_ranges_are_consistent()`: sample split within backtest range
- `Order.intended_execution_after_signal()`: T+1 constraint

### Semantic validators

Strategy semantic validation happens in `strategy_core/validator.py`, not in contracts.

Examples:
- Unsupported rule types (`relative_strength`) → `NotImplementedError`
- Unsupported universe types (`sector_plus_filters` without data layer) → `NotImplementedError`

**Separation of concerns**: Contracts validate data shape; validator validates strategy semantics.

---

## M2 Contract Changes

### Tightened fields

| Contract | Field | Before | After | Reason |
|----------|-------|--------|-------|--------|
| `Trade` | `trade_date` | `date \| None` | `date` | Fill simulator always sets it; rejected orders don't create Trade |

### Added fields

None (M2 focused on documentation and stability tier classification).

### Removed fields

None (backward compatibility preserved).

---

## Contract Ownership (M2)

### Current state (M1)

- Contracts defined in `backend/app/contracts.py`
- `strategy_core` imports from `backend.app.contracts`
- Circular dependency risk: `strategy_core` depends on `backend`

### M2 target

- Contracts moved to shared `contracts/` package
- `strategy_core` imports from `contracts.stable` (no backend dependency)
- `backend/app/contracts.py` becomes compatibility layer (re-export only)

### Migration plan

1. ✅ Create `contracts/stable.py` and `contracts/draft.py`
2. ✅ Add backward-compatible re-export in `backend/app/contracts.py`
3. ⏳ Update `strategy_core` imports to use `contracts.stable`
4. ⏳ Update `backend/scripts` imports to use `contracts.stable`
5. ⏳ Update tests to use `contracts.stable`
6. ⏳ Remove `backend/app/contracts.py` after migration complete

---

## Testing Contract Stability

### Serialization round-trip test

```python
def test_contract_serialization_round_trip():
    """Verify contracts can be serialized and deserialized without loss."""
    original = BacktestResult(...)
    
    # JSON round-trip
    json_str = original.model_dump_json()
    restored = BacktestResult.model_validate_json(json_str)
    
    assert restored == original
```

### Schema version test

```python
def test_schema_version_recorded():
    """Verify schema version is recorded in exports."""
    from contracts import SCHEMA_VERSION
    
    assert SCHEMA_VERSION == "1.0"
```

### Backward compatibility test

```python
def test_backward_compatible_import():
    """Verify old import path still works."""
    from backend.app.contracts import StrategyConfig
    from contracts.stable import StrategyConfig as NewStrategyConfig
    
    assert StrategyConfig is NewStrategyConfig
```

---

## Next Steps (M2)

1. ✅ Create shared contracts package
2. ✅ Separate stable/draft contracts
3. ✅ Add stability tier documentation
4. ⏳ Migrate `strategy_core` imports
5. ⏳ Add serialization tests
6. ⏳ Lock CSV column order in export schema doc
7. ⏳ Add `schema_version` to all export files

After M2 closeout:
- Contracts marked STABLE are locked
- Breaking changes require schema version bump (1.0 → 2.0)
- Additive changes allowed (new optional fields)

---

## FAQ

**Q: Can I add a new field to `StrategyConfig`?**

A: After M2 freeze, only additive changes allowed:
- New **optional** field → OK (patch version)
- New **required** field → breaking change (major version bump)

**Q: What if I need to store custom metadata?**

A: Use `meta` field (reserved for M2+) or add to audit layer, not core contracts.

**Q: Can I change `Trade.trade_date` to optional again?**

A: No (breaking change). Create new contract version (`TradeV2`) if semantics change.

**Q: When will draft contracts be promoted to stable?**

A: When the feature is implemented and tested (M3+ for research contracts).

**Q: Why not use `TypedDict` instead of Pydantic?**

A: Pydantic provides:
- Runtime validation (fail-loud on invalid data)
- Serialization/deserialization (`model_dump`, `model_validate`)
- JSON schema generation (for external tools)
- Clear error messages (field-level validation errors)
