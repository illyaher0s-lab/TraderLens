# TraderLens CSV Export Schema

**Schema Version**: 1.0  
**Status**: M2 LOCKED  
**Last Updated**: 2026-06-22

---

## Overview

TraderLens exports backtest results to CSV files for external analysis.
This document defines the locked column order and semantics for M2.

**Stability guarantee**:
- Column order is **frozen** (M2 locked)
- Column rename is a **breaking change** (requires schema version bump)
- Column removal is a **breaking change**
- Column reorder is a **breaking change**
- Adding columns is allowed **only by appending at the end**

**Missing value policy**:
- Optional numeric fields: empty string `""`
- Optional text fields: empty string `""`
- Required fields: never empty

**Numeric precision**:
- Prices/amounts: 2 decimal places (cents)
- Percentages: 2 decimal places
- Dates: ISO format `YYYY-MM-DD`

---

## 1. trades.csv

**Purpose**: All executed trades with transaction cost breakdown.

**Column count**: 13

**Column order** (M2 LOCKED):

| # | Column | Type | Nullable | Description |
|---|--------|------|----------|-------------|
| 1 | `trade_id` | string | No | Unique trade identifier |
| 2 | `order_id` | string | No | Source order ID |
| 3 | `symbol` | string | No | Stock symbol (e.g., `600519.SH`) |
| 4 | `direction` | string | No | `buy` or `sell` |
| 5 | `quantity` | int | No | Share quantity (always positive) |
| 6 | `price` | decimal(2) | No | Execution price per share |
| 7 | `trade_date` | date | No | Trade execution date (`YYYY-MM-DD`) |
| 8 | `gross_amount` | decimal(2) | No | `price * quantity` |
| 9 | `commission` | decimal(2) | No | Commission fee (both buy/sell) |
| 10 | `stamp_duty` | decimal(2) | No | Stamp duty (sell only, 0 for buy) |
| 11 | `transfer_fee` | decimal(2) | No | Transfer fee (currently always 0) |
| 12 | `total_fee` | decimal(2) | No | `commission + stamp_duty + transfer_fee` |
| 13 | `net_cash_flow` | decimal(2) | No | Net cash flow (negative for buy, positive for sell) |

**Example**:
```csv
trade_id,order_id,symbol,direction,quantity,price,trade_date,gross_amount,commission,stamp_duty,transfer_fee,total_fee,net_cash_flow
T001,O001,600519.SH,buy,100,150.50,2023-06-15,15050.00,5.00,0.00,0.00,5.00,-15055.00
T002,O002,600519.SH,sell,100,155.00,2023-06-20,15500.00,5.00,15.50,0.00,20.50,15479.50
```

**Change policy**:
- ✅ Append new column at end (e.g., `slippage`)
- ❌ Rename `trade_id` to `id`
- ❌ Reorder columns
- ❌ Remove `transfer_fee` (even if always 0)

---

## 2. round_trips.csv

**Purpose**: Completed buy→sell pairs with FIFO lot matching and realized PnL.

**Column count**: 11

**Column order** (M2 LOCKED):

| # | Column | Type | Nullable | Description |
|---|--------|------|----------|-------------|
| 1 | `symbol` | string | No | Stock symbol |
| 2 | `buy_date` | date | No | Buy trade date |
| 3 | `sell_date` | date | No | Sell trade date |
| 4 | `holding_days` | int | No | `sell_date - buy_date` (calendar days) |
| 5 | `quantity` | int | No | Matched quantity (not original trade quantity) |
| 6 | `buy_price` | decimal(2) | No | Buy price per share |
| 7 | `sell_price` | decimal(2) | No | Sell price per share |
| 8 | `buy_cost` | decimal(2) | No | Total cost for matched quantity (including proportional commission) |
| 9 | `sell_proceeds` | decimal(2) | No | Net proceeds for matched quantity (after proportional fees) |
| 10 | `realized_pnl` | decimal(2) | No | `sell_proceeds - buy_cost` |
| 11 | `return_pct` | decimal(2) | No | `(realized_pnl / buy_cost) * 100` |

**Example**:
```csv
symbol,buy_date,sell_date,holding_days,quantity,buy_price,sell_price,buy_cost,sell_proceeds,realized_pnl,return_pct
600519.SH,2023-06-15,2023-06-20,5,100,150.50,155.00,15055.00,15479.50,424.50,2.82
```

**Notes**:
- `quantity` is the matched portion, not the original trade quantity
- One sell trade may generate multiple round trips if it closes multiple buy lots
- `holding_days` is calendar days, not trading days

---

## 3. equity_curve.csv

**Purpose**: Daily portfolio snapshots with cumulative return.

**Column count**: 5

**Column order** (M2 LOCKED):

| # | Column | Type | Nullable | Description |
|---|--------|------|----------|-------------|
| 1 | `date` | date | No | Trading date |
| 2 | `cash` | decimal(2) | No | Available cash |
| 3 | `market_value` | decimal(2) | No | Total market value of positions |
| 4 | `total_value` | decimal(2) | No | `cash + market_value` |
| 5 | `return_from_start_pct` | decimal(2) | No | `((total_value - initial_capital) / initial_capital) * 100` |

**Example**:
```csv
date,cash,market_value,total_value,return_from_start_pct
2023-06-15,84945.00,15055.00,100000.00,0.00
2023-06-16,84945.00,15200.00,100145.00,0.15
2023-06-17,84945.00,14900.00,99845.00,-0.16
```

**Notes**:
- `return_from_start_pct` is cumulative return from initial capital
- Not reset at IS/OOS split (continuous capital)

---

## 4. order_generation_events.csv

**Purpose**: Audit trail for order generation process, including T+1 violations and rejections.

**Column count**: 9

**Column order** (M2 LOCKED):

| # | Column | Type | Nullable | Description |
|---|--------|------|----------|-------------|
| 1 | `event_type` | string | No | Event type: `no_position_to_exit`, `t1_frozen`, `partial_exit_due_to_t1_freeze`, `signal_conflict`, `zero_quantity` |
| 2 | `symbol` | string | No | Stock symbol |
| 3 | `signal_id` | string | Yes | Source signal ID (empty if not applicable) |
| 4 | `intended_execution_date` | date | No | Planned execution date |
| 5 | `reason` | string | No | Human-readable reason |
| 6 | `requested_quantity` | int | Yes | Requested quantity (empty if not applicable) |
| 7 | `generated_quantity` | int | Yes | Generated quantity (empty if not applicable) |
| 8 | `sellable_quantity` | int | Yes | Sellable quantity after T+1 check (empty if not applicable) |
| 9 | `total_quantity` | int | Yes | Total position quantity (empty if not applicable) |

**Example**:
```csv
event_type,symbol,signal_id,intended_execution_date,reason,requested_quantity,generated_quantity,sellable_quantity,total_quantity
t1_frozen,600519.SH,S001,2023-06-16,T+1 freeze: bought on 2023-06-15,100,,0,100
partial_exit_due_to_t1_freeze,601318.SH,S002,2023-06-17,Partial T+1: 50/150 sellable,150,50,50,150
no_position_to_exit,300750.SZ,S003,2023-06-18,No position to exit,,,0,0
```

**Notes**:
- This is an **audit file**, not a regular export
- Optional fields use empty string `""` when not applicable
- Critical for debugging T+1 freeze logic and exit rejections
- Used by M2 Audit Requirements to answer "why was this exit rejected?"

---

## CSV Generation Code

CSV files are generated by `backend/scripts/export_backtest_result.py`.

**Column order is defined in code**:
- `trades.csv`: Lines 172-176
- `round_trips.csv`: Lines 212-216
- `equity_curve.csv`: Lines 241-243
- `order_generation_events.csv`: Lines 264-268

**Tests verify column order**:
- `tests/test_csv_schema_stability.py` (to be added)

---

## Schema Version Detection

CSV files do not contain schema version field (they are flat data).

Schema version is recorded in the export directory's `metadata.json` or `metrics.json` file:

```json
{
  "schema_version": "1.0",
  "generated_at": "2026-06-22T12:00:00",
  "csv_files": ["trades.csv", "round_trips.csv", "equity_curve.csv"]
}
```

External tools should:
1. Read `schema_version` from `metrics.json` or `metadata.json`
2. Verify schema version matches expected version
3. Read CSV files with locked column order

---

## Breaking Changes (Requires Schema v2.0)

The following changes require schema version bump and migration:
- Rename any column
- Remove any column
- Reorder columns
- Change column semantics (e.g., `holding_days` from calendar to trading days)
- Change missing value representation (e.g., `""` to `null`)

---

## Additive Changes (Allowed in Schema v1.x)

The following changes are allowed without breaking compatibility:
- Append new column at end
- Add new CSV file (e.g., `signals.csv`)
- Add new optional field to JSON metadata

---

## External Tool Integration

Example: Reading `trades.csv` with pandas:

```python
import pandas as pd

# Read with explicit column order
df = pd.read_csv("trades.csv")

# Verify schema version from metadata
with open("metrics.json") as f:
    meta = json.load(f)
    assert meta["schema_version"] == "1.0", "Unsupported schema version"

# Use locked column names
assert list(df.columns) == [
    "trade_id", "order_id", "symbol", "direction", "quantity", "price",
    "trade_date", "gross_amount", "commission", "stamp_duty", "transfer_fee",
    "total_fee", "net_cash_flow"
], "Column order mismatch"
```

---

## FAQ

**Q: Why lock column order instead of using pandas automatic column mapping?**

A: External tools (Excel, BI tools, shell scripts) rely on column position. Changing order breaks `cut`, `awk`, and Excel macros.

**Q: Why empty string `""` instead of `null` for missing values?**

A: CSV standard doesn't have `null`. Empty string is clearer than implicit `NaN` and works consistently across tools.

**Q: Can I add a column in the middle?**

A: No. Append at the end only. Inserting columns breaks positional tools and tests.

**Q: What if I need to change `holding_days` to trading days?**

A: That's a semantic change. Add new column `holding_trading_days`, mark `holding_days` as deprecated, bump schema to v2.0 when removing old column.

**Q: Why is `transfer_fee` always 0 but still in the schema?**

A: Reserved for future implementation. Removing it later would be a breaking change. Keeping it costs one column.
