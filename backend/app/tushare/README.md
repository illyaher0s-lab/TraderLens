# Tushare Data Source - M3.2

Real A-share data integration via Tushare API.

## Status

- ✅ M3.2 Snapshot Generation Complete
- ✅ M3.3 TushareDataSource Implementation Complete
- ✅ M3.4 Real Backtest Execution Complete

## Quick Start

### 1. Generate Frozen Snapshot (One-time)

Requires Tushare API token from https://tushare.pro/

```bash
export TUSHARE_TOKEN="your_token_here"
python backend/scripts/generate_sample_snapshot.py
```

Output: `data/tushare_snapshots/` (10 stocks × 30 days, frozen)

### 2. Run Backtest with Frozen Data

```bash
python backend/scripts/run_a_share_backtest.py \
    --snapshot-dir data/tushare_snapshots \
    --strategy examples/strategies/m3_4_tushare_real_data.yaml \
    --output output/m3_4_backtest \
    --initial-capital 100000
```

**Key**: Backtest reads ONLY frozen snapshot, never calls Tushare API.

### 3. Verify Reproducibility

```bash
python -m unittest tests.test_tushare_reproducibility -v
```

Same snapshot + same strategy = identical results (verified by hash).

See [SNAPSHOT_GUIDE.md](SNAPSHOT_GUIDE.md) for detailed instructions.

## Architecture

```
backend/app/tushare/
├── config.py                    # Configuration (token, paths, rate limits)
├── tushare_client.py            # API wrapper (proxy handling, retry logic)
├── snapshot_generator.py        # Generate frozen snapshots
└── tushare_data_source.py       # Load snapshots (implements DataSource Protocol)

data/tushare_snapshots/
├── metadata/
│   ├── manifest.json            # Snapshot metadata
│   ├── stock_list.json          # StockIdentity[]
│   └── trade_calendar.json      # Trading dates
└── data/
    ├── {symbol}_daily.parquet   # Daily bars
    └── {symbol}_status.parquet  # Daily statuses
```

## Snapshot Generation (Manual)

### Prerequisites

1. Get Tushare token from https://tushare.pro
2. Set environment variable:
   ```bash
   export TUSHARE_TOKEN='your_token_here'
   ```

### Generate Snapshot

```bash
python backend/scripts/generate_tushare_snapshot.py
```

This will:
- Fetch 10 stocks × 30 trading days from Tushare API
- Save as frozen Parquet snapshots
- Generate metadata (manifest, stock list, trade calendar)
- Compute deterministic snapshot hash
- Validate snapshot integrity

### Output

```
data/tushare_snapshots/
├── metadata/
│   ├── manifest.json          # snapshot_hash, schema_version, is_frozen=True
│   ├── stock_list.json        # 10 stocks with identity metadata
│   └── trade_calendar.json    # ~30 trading dates
└── data/
    ├── 600519.SH_daily.parquet
    ├── 600519.SH_status.parquet
    └── ... (20 files total)
```

## Snapshot Structure

### manifest.json

Required fields:
- `snapshot_hash`: Deterministic content hash
- `schema_version`: Must match contracts.SCHEMA_VERSION
- `is_frozen`: Must be `true`
- `source`: "tushare"
- `created_at`: ISO timestamp
- `stock_count`: Number of stocks
- `trading_days_count`: Number of trading days
- `stocks`: List of symbols

### stock_list.json

Array of StockIdentity:
- `symbol`: "600519.SH"
- `name`: "贵州茅台"
- `exchange`: "SSE" or "SZSE"
- `list_date`: "20010827"
- `current_status`: "listed"
- `industry`: "白酒"
- `sector`: "贵州"

### trade_calendar.json

```json
{
  "trading_dates": [
    "2023-12-01",
    "2023-12-04",
    "..."
  ]
}
```

### Parquet Files

#### {symbol}_daily.parquet

Columns:
- `date`: datetime64
- `symbol`: string
- `open`: float64
- `high`: float64
- `low`: float64
- `close`: float64
- `volume`: int64 (shares)
- `amount`: float64 (CNY)
- `adj_factor`: float64 (forward adjustment)

#### {symbol}_status.parquet

Columns:
- `date`: datetime64
- `symbol`: string
- `is_st`: bool
- `is_suspended`: bool
- `is_limit_up`: bool
- `is_limit_down`: bool
- `suspend_reason`: string | None
- `st_type`: string | None

## Design Decisions

### 1. Frozen Snapshots Only

**Decision**: Backtest ONLY reads frozen snapshots. No live API calls during backtest.

**Rationale**:
- Deterministic replay (same input → same output)
- No API rate limit issues during backtest
- Fast execution (no network latency)
- Reproducible results

### 2. Deterministic Hash

**Decision**: snapshot_hash excludes timestamps (created_at, updated_at).

**Rationale**:
- Same data content → same hash
- Enables snapshot deduplication
- Cache invalidation based on content, not time

**Included in hash**:
- Stock list (sorted by symbol)
- Trade calendar
- Parquet file contents

**Excluded from hash**:
- created_at / updated_at
- snapshot_id (human label)
- File paths

### 3. Fail-Loud on Missing Data

**Decision**: Missing data raises ValueError, no silent fallback.

**Rationale**:
- M2 DataSource Protocol requirement
- Prevents hidden data quality issues
- Forces explicit handling of incomplete data

### 4. Proxy Disabling

**Decision**: TushareClient automatically disables HTTP_PROXY on init.

**Rationale**:
- Tushare custom endpoint (http://8.163.90.143:8686/) may conflict with VPN
- User often has VPN enabled during development
- Automatic proxy disabling ensures API calls succeed

## Rate Limits

Default: 60 requests/minute (1 req/sec)

Configure in TushareConfig:
```python
config = TushareConfig(
    token="***",
    requests_per_minute=120,  # Override
    retry_attempts=3,
    retry_delay_seconds=2.0,
)
```

## Validation

### Snapshot Validation

```python
from backend.app.tushare.snapshot_generator import SnapshotGenerator
from backend.app.tushare.config import TushareConfig

config = TushareConfig.from_env()
generator = SnapshotGenerator(config)

result = generator.validate_snapshot()

print(result["status"])  # "pass", "degraded", or "failed"
print(result["errors"])
print(result["warnings"])
```

### Validation Checks

1. **manifest.json exists** and has required fields
2. **stock_list.json exists** and count matches manifest
3. **trade_calendar.json exists** and count matches manifest
4. **Parquet files exist** for all symbols (daily + status)
5. **is_frozen = True** in manifest

## Testing

### Unit Tests (Mock)

```bash
python -m unittest tests.test_tushare_snapshot_generator -v
```

Tests:
- Snapshot generation creates all files
- Manifest has required fields
- Hash is deterministic
- Validation passes for valid snapshot
- Validation fails for missing files
- Stock list structure correct
- Trade calendar sorted

### Real API Test (Manual)

```bash
export TUSHARE_TOKEN='***'
python backend/scripts/generate_tushare_snapshot.py
```

**Note**: NOT run in CI (requires real token and API access).

## M3.4 Status

**Completed**:
- ✅ Real backtest execution with TushareDataSource
- ✅ Reproducibility verification (hash-based)
- ✅ Export to M2 format (metrics/trades/round_trips/equity_curve)
- ✅ Frozen sample generation script
- ✅ Integration tests (6 tests pass)
- ✅ Documentation (SNAPSHOT_GUIDE.md)

**Test Results**:
- 3 real backtest tests pass
- 3 reproducibility tests pass
- 340 total tests pass (334 → 340)
- M2 + M3.2 + M3.3 tests remain green

**Deliverables**:
1. ✅ `run_a_share_backtest.py` - CLI backtest script
2. ✅ `generate_sample_snapshot.py` - Frozen sample generator
3. ✅ `test_tushare_real_backtest.py` - Integration tests
4. ✅ `test_tushare_reproducibility.py` - Hash verification tests
5. ✅ `SNAPSHOT_GUIDE.md` - Complete usage guide
6. ✅ Strategy YAML: `m3_4_tushare_real_data.yaml`
7. ✅ Test strategy: `test_tushare_minimal_strategy.yaml`

**Reproducibility Guarantee**:
- ✅ Same snapshot + same strategy → identical final_capital
- ✅ Same snapshot + same strategy → identical total_return
- ✅ Export files produce identical content hash (excluding timestamps)
- ✅ No Tushare API calls during backtest (frozen snapshot only)

**Key Design Decisions**:
1. **Frozen snapshot only** - Backtest reads pre-generated Parquet files, never calls Tushare API
2. **Deterministic hash** - Exclude `created_at`, `runtime`, absolute paths from hash
3. **Contract validation** - DailyBar/DailyStatus contracts enforced on load
4. **Lazy load + cache** - Parquet files loaded per-symbol on first access
5. **CI-safe** - Tests use mock client or read committed frozen sample

**CI/Test Strategy**:
- Unit tests: Mock Tushare client (no API)
- Integration tests: Read frozen sample (no API)
- Reproducibility tests: Verify hash across runs (no API)
- Real snapshot generation: Manual only (requires token)

**Frozen Sample**:
- **Location**: `data/tushare_snapshots/`
- **Content**: 10 A-share stocks × 30 trading days (Dec 2023)
- **Size**: ~4 Parquet files per symbol = 40 files + metadata
- **Committed**: Yes (for CI reproducibility)
- **Generation**: `python backend/scripts/generate_sample_snapshot.py`

**Usage**:
```bash
# Generate frozen sample (one-time, requires token)
export TUSHARE_TOKEN="your_token"
python backend/scripts/generate_sample_snapshot.py

# Run backtest (reads frozen sample, no API)
python backend/scripts/run_a_share_backtest.py \
    --snapshot-dir data/tushare_snapshots \
    --strategy examples/strategies/m3_4_tushare_real_data.yaml \
    --output output/m3_4_backtest

# Verify reproducibility
python -m unittest tests.test_tushare_reproducibility -v
```

**Next Steps (M4)**:
- Signal Board integration
- Evidence collection from real data
- Review workflow with actual A-share research

## M3.3 Status

**Completed**:
- ✅ TushareDataSource implementation (8 methods)
- ✅ Lazy load + cache for Parquet files
- ✅ Fail-loud on missing symbol/date/file
- ✅ DataSource Protocol compliance
- ✅ Contract validation (DailyBar, DailyStatus)
- ✅ Mock tests (20 tests pass)

**Test Results**:
- 20 new tests pass
- 334 total tests pass (314 → 334)
- M2 + M3.2 tests remain green

**DataSource Protocol Methods**:
1. ✅ `get_metadata()` - Returns DataSourceMetadata with is_frozen=True
2. ✅ `validate()` - Reuses M3.2 validation logic
3. ✅ `symbols()` - Returns list of symbols from snapshot
4. ✅ `get_daily_bars(symbol)` - Lazy load + cache Parquet
5. ✅ `get_daily_statuses(symbol)` - Lazy load + cache Parquet
6. ✅ `get_daily_bar(symbol, date)` - Single bar lookup
7. ✅ `get_daily_status(symbol, date)` - Single status lookup
8. ✅ `get_price(symbol, date)` - Returns close price

**Next Steps (M3.4)**:
- Run real backtest with TushareDataSource
- Verify reproducibility (same snapshot → same result)
- Export to CSV (M2 format)
- Document results

## M3.2 Status

**Completed**:
- ✅ SnapshotGenerator implementation
- ✅ Deterministic hash computation
- ✅ Manifest/metadata generation
- ✅ Validation logic
- ✅ Mock tests (8 tests pass)
- ✅ Real API generation script

**Test Results**:
- 8 new tests pass
- 314 total tests pass (306 → 314)
- M2 tests remain green

**Next Steps (M3.3)**:
- Implement TushareDataSource (load frozen snapshots)
- Implement DataSource Protocol 8 methods
- Test loading with strategy_core

## References

- M3 Boundary Discussion: `docs/design/M3-BOUNDARY-DISCUSSION.md`
- DataSource Protocol: `strategy_core/data_source_protocol.py`
- Contracts: `contracts/stable.py`
- Tushare API: https://tushare.pro/document/2
