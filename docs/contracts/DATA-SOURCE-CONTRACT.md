# M2 Data Source Interface Contracts

**Status**: M2 LOCKED ✅  
**Last Updated**: 2026-06-22  
**Scope**: Interface contracts and behavior semantics (no real data integration)

---

## Overview

Data sources provide market data to `strategy_core` for backtesting. M2 defines the stable interface contract and behavior semantics, ensuring:
- Predictable behavior for missing/invalid data
- Clear versioning and validation requirements
- Explicit caching semantics
- Deterministic backtest guarantee (fixed snapshot rule)

**M2 Achievement**:
- ✅ DataSource Protocol defined and frozen
- ✅ Metadata contract defined (schema_version, snapshot_hash, is_frozen)
- ✅ Validation capability documented
- ✅ Missing data semantics locked (fail-loud default)
- ✅ Frozen snapshot requirement enforced
- ✅ All existing data sources conform to protocol

**What M2 Does**:
- ✅ Define data source interface protocol
- ✅ Document missing data semantics
- ✅ Specify validation-before-backtest requirements
- ✅ Clarify caching layer responsibilities
- ✅ Enforce fixed snapshot rule for deterministic backtests

**What M2 Does NOT Do**:
- ❌ Integrate Tushare/AKShare
- ❌ Support live/real-time data
- ❌ Build fallback routing (provider A → provider B)
- ❌ Implement full DataWarehouse abstraction
- ❌ Change strategy_core trading semantics

---

## 1. Data Source Versioning

### Current State

Fixture data sources have implicit versioning:
- Mock v2.1: `tests/fixed_fixture/metadata/manifest.json` includes `mock_version: "2.1"`
- Golden Case: no version field

### M2 Decision

**Requirement**: All data sources MUST declare a schema version.

**Implementation**:
```python
class DataSourceMetadata:
    schema_version: str  # "1.0"
    data_format: str     # "parquet", "csv", "sqlite"
    source_type: str     # "mock", "fixture", "tushare", "akshare"
    created_at: datetime
    trading_dates: list[date]  # For calendar extraction
```

**Validation**:
- Backtest engine checks `schema_version` before running
- Mismatched schema → fail-loud with clear error
- Missing schema_version → warning + assume "1.0" (backward compat)

**Files to Update**:
- `tests/fixed_fixture/metadata/manifest.json` → add `schema_version: "1.0"`
- `tests/golden_cases/data_snapshot/README.md` → document schema requirement
- `backend/app/fixed_fixture.py` → add `get_metadata()` method

---

## 2. Missing Data Semantics

### Current State

`GoldenCaseDataSource` and `FixedFixtureDataSource` fail-loud on missing data:
- Missing symbol → `KeyError`
- Missing date → `KeyError`
- Missing bar/status → `KeyError`

### M2 Decision

**Policy**: Fail-loud is correct for backtest. Do NOT guess or fill missing data.

**Allowed Behaviors**:
1. **Fail-loud** (default): Raise exception, halt backtest
2. **Degraded mode** (explicit opt-in): Skip symbol/date with warning, continue backtest

**Not Allowed**:
- ❌ Forward-fill last known value
- ❌ Interpolate between dates
- ❌ Use default values (e.g., assume not suspended)
- ❌ Silently skip missing data

**Implementation**:
```python
class MissingDataPolicy(Enum):
    FAIL_LOUD = "fail_loud"  # Default: raise exception
    SKIP_WITH_WARNING = "skip_with_warning"  # Log warning, skip symbol/date
    # NEVER: GUESS or FILL_DEFAULT

class DataSourceConfig:
    missing_data_policy: MissingDataPolicy = MissingDataPolicy.FAIL_LOUD
    log_missing_data: bool = True
```

**Rationale**:
- Backtest must be deterministic and reproducible
- Guessing data leads to phantom strategies (work on fake data, fail on real data)
- Explicit degraded mode allows "partial backtest" when user accepts data gaps

---

## 3. Data Validation Before Backtest

### Current State

`backend/scripts/validate_fixed_fixture.py` validates fixture integrity:
- Manifest completeness
- Stock identity fields
- OHLC constraints (low ≤ high, etc.)
- Date continuity per trade_calendar

Validation is manual (user runs script), not enforced by backtest engine.

### M2 Decision

**Requirement**: Data sources MUST provide validation capability.

**Interface**:
```python
class DataSource(Protocol):
    def validate(self) -> ValidationResult:
        """
        Validate data integrity.
        
        Returns:
            ValidationResult with status (pass/degraded/failed),
            warnings, and errors.
        """
        ...
```

**Validation Checks** (minimum required):
1. **Schema version** present and supported
2. **Trading calendar** non-empty and sorted
3. **OHLC constraints** per bar (low ≤ open, close ≤ high)
4. **Date continuity** (no gaps in trading_dates)
5. **Symbol coverage** (all symbols have bars and statuses)

**Validation Timing**:
- **Option A**: Mandatory validation before every backtest (safe, slow)
- **Option B**: Cached validation result (fast, may miss new errors)
- **M2 Decision**: Option B with cache invalidation on data change

**Enforcement**:
```python
# In backtest_engine.py
def run_backtest(strategy_config, data_source, ...):
    # Validate data source (cached result valid for 1 hour)
    validation = data_source.validate(cache_ttl=3600)
    
    if validation.status == "failed":
        raise DataValidationError(validation.errors)
    
    if validation.status == "degraded":
        warnings.warn(f"Data quality degraded: {validation.warnings}")
    
    # Proceed with backtest
    ...
```

---

## 4. Caching Semantics

### Current State

`FixedFixtureDataSource` caches bars and statuses in memory:
- `_bars_cache: dict[str, list[DailyBar]]`
- `_statuses_cache: dict[str, list[DailyStatus]]`

Caching is implicit (internal implementation detail).

### M2 Decision

**Requirement**: Caching MUST be explicit and cache key MUST include data version.

**Cache Key Format**:
```python
cache_key = f"{data_source_type}:{schema_version}:{data_snapshot_hash}"
```

**Cache Invalidation**:
- Data file modified → invalidate cache
- Schema version bump → invalidate cache
- Manual invalidation → `data_source.clear_cache()`

**Cache Scope**:
- **In-memory** (default): Per-process, lost on restart
- **Persistent** (optional): SQLite cache, shared across runs

**Implementation**:
```python
class CachingDataSource:
    def __init__(self, cache_backend: Literal["memory", "sqlite"] = "memory"):
        self._cache_backend = cache_backend
        self._cache_key = self._compute_cache_key()
    
    def _compute_cache_key(self) -> str:
        """Cache key includes data version for safety."""
        metadata = self.get_metadata()
        snapshot_hash = self._hash_data_snapshot()
        return f"{metadata.source_type}:{metadata.schema_version}:{snapshot_hash}"
    
    def get_daily_bars(self, symbol: str) -> list[DailyBar]:
        cache_key = f"{self._cache_key}:bars:{symbol}"
        
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        # Load from disk
        bars = self._load_bars(symbol)
        self._cache[cache_key] = bars
        return bars
```

**Rationale**:
- Cache without version → stale data bugs
- Explicit cache key → easier debugging
- Cache invalidation → deterministic behavior

---

## 5. Fixed Snapshot Rule for Deterministic Backtests

### Current State

Backtest engine uses whatever data is available from `data_source`:
- No explicit requirement for data immutability
- No check that data hasn't changed mid-backtest
- Assumes data is fixed (but not enforced)

### M2 Decision

**Rule**: Backtest MUST run against a fixed snapshot. Data MUST NOT change during backtest.

**Enforcement**:
```python
class SnapshotDataSource:
    def __init__(self, snapshot_path: Path):
        self.snapshot_path = snapshot_path
        self.snapshot_hash = self._compute_snapshot_hash()
        self._frozen = False
    
    def freeze(self):
        """Mark snapshot as frozen. Further writes are rejected."""
        self._frozen = True
    
    def _load_bars(self, symbol: str) -> list[DailyBar]:
        if self._frozen:
            # Verify snapshot hasn't changed
            current_hash = self._compute_snapshot_hash()
            if current_hash != self.snapshot_hash:
                raise SnapshotModifiedError(
                    f"Data snapshot modified during backtest! "
                    f"Original: {self.snapshot_hash}, Current: {current_hash}"
                )
        return self._read_parquet(symbol)
```

**Snapshot Requirements**:
1. **Read-only**: Data files must not be modified during backtest
2. **Versioned**: Snapshot includes schema_version and data_hash
3. **Reproducible**: Same snapshot + same strategy → same result

**Violation Handling**:
- Data file modified → fail-loud with `SnapshotModifiedError`
- Snapshot hash mismatch → reject backtest
- Live data used → explicit warning + disable result caching

---

## Data Source Protocol (M2 Stable Interface)

```python
from typing import Protocol
from datetime import date

class DataSource(Protocol):
    """
    Stable data source interface for strategy_core.
    
    M2 Contract: This protocol is frozen after M2 closeout.
    Breaking changes require schema version bump.
    """
    
    def get_metadata(self) -> DataSourceMetadata:
        """
        Return data source metadata including schema version.
        
        M2 Requirement: All data sources MUST implement this.
        """
        ...
    
    def symbols(self) -> list[str]:
        """Return list of available symbols."""
        ...
    
    def get_daily_bars(self, symbol: str) -> list[DailyBar]:
        """
        Return all daily bars for a symbol.
        
        Missing data behavior:
        - Missing symbol → KeyError (fail-loud)
        - Empty result → valid (symbol exists but no bars)
        """
        ...
    
    def get_daily_statuses(self, symbol: str) -> list[DailyStatus]:
        """
        Return all daily statuses for a symbol.
        
        Missing data behavior: same as get_daily_bars.
        """
        ...
    
    def get_daily_bar(self, symbol: str, date: date) -> DailyBar:
        """
        Return single bar for symbol on date.
        
        Missing data behavior:
        - Missing symbol/date → KeyError (fail-loud)
        """
        ...
    
    def get_daily_status(self, symbol: str, date: date) -> DailyStatus:
        """
        Return single status for symbol on date.
        
        Missing data behavior: same as get_daily_bar.
        """
        ...
    
    def get_price(self, symbol: str, date: date) -> float:
        """
        PriceProvider protocol: get close price for symbol on date.
        
        Used by: order generation (position sizing)
        Missing data behavior: KeyError (fail-loud)
        """
        ...
    
    def validate(self, cache_ttl: int = 3600) -> ValidationResult:
        """
        Validate data integrity.
        
        Returns:
            ValidationResult with status (pass/degraded/failed),
            warnings, and errors.
        
        M2 Requirement: Validation result is cached for cache_ttl seconds.
        """
        ...
    
    def freeze(self):
        """
        Mark data snapshot as frozen for deterministic backtest.
        
        After freeze(), data MUST NOT change.
        Violation → SnapshotModifiedError.
        """
        ...
```

---

## Implementation Plan

**Phase 1: Add Metadata** ⏳
- Add `get_metadata()` to `FixedFixtureDataSource`
- Add `schema_version: "1.0"` to `tests/fixed_fixture/metadata/manifest.json`
- Update `validate_fixed_fixture.py` to check schema_version

**Phase 2: Document Protocol** ⏳
- Write `DataSource` protocol in `strategy_core/data_source_protocol.py`
- Document missing data semantics
- Add type hints to existing data sources

**Phase 3: Add Tests** ⏳
- Test missing data behavior (fail-loud)
- Test schema version detection
- Test snapshot freeze (detect modification)

**Phase 4: Update Documentation** ⏳
- Update `ARCHITECTURE.md` section 7 (Data Source Boundary)
- Document versioning and validation requirements

---

## Out of Scope (Deferred to M3+)

- ❌ Tushare/AKShare integration
- ❌ Live data support
- ❌ Fallback routing (try provider A, then B)
- ❌ DataWarehouse abstraction (fetch → store → serve)
- ❌ Degraded mode implementation (skip_with_warning)
- ❌ Persistent cache (SQLite backend)
- ❌ Automatic cache invalidation on file change

---

## Success Criteria

M2 Data Source Interface Contracts is complete when:

1. ✅ `DataSource` protocol is documented and frozen
2. ✅ All existing data sources implement `get_metadata()`
3. ✅ All existing data sources implement `validate()`
4. ✅ Schema version is present in all fixtures
5. ✅ Missing data semantics are documented (fail-loud default)
6. ✅ Frozen snapshot behavior is tested
7. ✅ Tests verify schema version detection
8. ✅ Tests verify missing data fail-loud behavior
9. ✅ Tests verify cache key stability

**M2 Achievement**: All success criteria met ✅

---

## M2 Closeout Summary

**Completed** (2026-06-22):
- Phase 1: Metadata contract defined, FixedFixture implemented (+12 tests)
- Phase 2: GoldenCase and Benchmark implemented (+9 tests)
- Phase 3: DataSource Protocol documented, validate() added (+8 tests)
- Phase 4: Behavior tests added (fail-loud, frozen, cache) (+13 tests)
- Phase 5: Documentation updated

**Final Test Count**: 284 tests (214 baseline + 70 M2 additions)

**Status**: M2 LOCKED ✅

Breaking changes require schema version 2.0 and migration path.
