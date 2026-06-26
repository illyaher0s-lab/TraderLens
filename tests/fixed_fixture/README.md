# 20-Stock Fixed Fixture

## Purpose

Stable, deterministic dataset for backtesting strategy validation with larger stock pool than Golden Case (5 stocks).

- **NOT** production data source
- **NOT** real-time API
- **Fixed snapshot** for reproducible testing

## Dataset Specification

- **Stock count**: 20 (10 SSE + 10 SZSE)
- **Date range**: 2023-01-01 to 2024-12-31 (2 years)
- **Frequency**: Daily
- **Adjust type**: Forward-adjusted (前复权)
- **Data source**: Tushare (offline snapshot, fetched once)

## Directory Structure

```
tests/fixed_fixture/
├── README.md
├── metadata/
│   ├── manifest.json          # Dataset metadata
│   ├── stock_list.json        # 20 stocks with identity info
│   └── trade_calendar.json    # Trading dates for 2023-2024
└── data/
    ├── {symbol}_daily.parquet        # OHLCV + amount
    └── {symbol}_status.parquet       # Daily status (suspended, limit_up/down, ST)
```

## Data Schema

### 1. Daily Bar (`{symbol}_daily.parquet`)

| Field       | Type  | Description                    |
|-------------|-------|--------------------------------|
| date        | date  | Trading date                   |
| symbol      | str   | Stock code (e.g., 000001.SZ)   |
| open        | float | Open price                     |
| high        | float | High price                     |
| low         | float | Low price                      |
| close       | float | Close price (forward-adjusted) |
| volume      | int   | Volume (shares)                |
| amount      | float | Turnover (RMB)                 |
| adj_factor  | float | Adjustment factor              |

### 2. Daily Status (`{symbol}_status.parquet`)

| Field          | Type | Description                        |
|----------------|------|------------------------------------|
| date           | date | Trading date                       |
| symbol         | str  | Stock code                         |
| is_st          | bool | ST/\*ST marking                    |
| is_suspended   | bool | Trading suspended                  |
| is_limit_up    | bool | Hit upper price limit (涨停)       |
| is_limit_down  | bool | Hit lower price limit (跌停)       |

### 3. Stock Identity (`stock_list.json`)

```json
{
  "symbol": "000001.SZ",
  "name": "平安银行",
  "exchange": "SZSE",
  "list_date": "1991-04-03",
  "delist_date": null,
  "current_status": "listed",
  "industry": "银行",
  "sector": "金融"
}
```

### 4. Trade Calendar (`trade_calendar.json`)

```json
{
  "exchange": "SSE",
  "date_range": {
    "start": "2023-01-01",
    "end": "2024-12-31"
  },
  "trading_dates": ["2023-01-03", "2023-01-04", ...]
}
```

### 5. Manifest (`manifest.json`)

```json
{
  "dataset_name": "20-stock-fixture",
  "version": "1.0.0",
  "source": "tushare",
  "fetched_at": "2026-06-21T12:00:00Z",
  "date_range": {
    "start": "2023-01-01",
    "end": "2024-12-31"
  },
  "adjust_type": "qfq",
  "schema_version": "1.0",
  "stock_count": 20,
  "trading_days_count": 487,
  "warnings": [
    "This is a fixed snapshot. NOT for production use.",
    "Data may contain gaps for suspended stocks.",
    "ST status and limit flags are sourced from Tushare daily indicators."
  ]
}
```

## Usage

```python
from backend.app.fixed_fixture import FixedFixtureDataSource

data_source = FixedFixtureDataSource()
symbols = data_source.symbols()  # Returns list of 20 stocks
bars = data_source.get_daily_bars("000001.SZ")
```

## Data Quality Requirements

1. **Completeness**: All 20 stocks must have data for every trading day in range.
2. **Consistency**: adj_factor must be consistent with adjusted prices.
3. **Status alignment**: `is_suspended=True` days must have zero volume.
4. **No forward leakage**: Status flags reflect information available at market close.

## Backtest Report Requirements

When using this fixture, BacktestResult must include:

```json
{
  "data_source": "fixed_fixture",
  "data_source_version": "1.0.0",
  "data_date_range": {
    "start": "2023-01-01",
    "end": "2024-12-31"
  }
}
```

## Validation

Run validation script to check data integrity:

```bash
python backend/scripts/validate_fixed_fixture.py
```

Checks:
- [ ] All 20 stocks have daily + status files
- [ ] Date ranges match manifest
- [ ] No missing trading days (gaps only allowed for suspended stocks)
- [ ] Status flags are boolean
- [ ] Prices are positive
- [ ] Volume/amount alignment

## Refresh Policy

This is a **frozen snapshot**. Do NOT update data files without:

1. Incrementing `version` in manifest.json
2. Recording changes in CHANGELOG.md
3. Re-running all backtest tests to ensure determinism
