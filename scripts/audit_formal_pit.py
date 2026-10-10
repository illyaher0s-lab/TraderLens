#!/usr/bin/env python3
"""Formal PIT Interface Audit - read-only probe, no writes to data/pit/."""
import hashlib
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

# Load env
env_file = Path(__file__).parent.parent / ".env.local"
for line in env_file.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ[k] = v

sys.path.insert(0, str(Path(__file__).parent.parent))
from backend.app.tushare.config import TushareConfig
from backend.app.tushare.tushare_client import TushareClient

config = TushareConfig.from_env()
client = TushareClient(config)

audit = {"audit_date": str(date.today()), "interfaces": {}}

# Step 1: Get trading days
cal = client.pro.trade_cal(exchange="SSE", start_date="20160104", end_date=date.today().strftime("%Y%m%d"))
# ponytail: sort ascending
tdays = sorted(cal[cal["is_open"] == 1]["cal_date"].astype(str).tolist())
checkpoints = {}
for y in [2016, 2020, 2025]:
    for d in tdays:
        if d.startswith(str(y)):
            checkpoints[y] = d
            break
checkpoints["recent"] = tdays[-1] if tdays else None
audit["trading_day_checkpoints"] = checkpoints

# Step 2: Audit each interface
interfaces = [
    ("trade_cal", lambda: client.pro.trade_cal(exchange="SSE", start_date="20160104", end_date="20261231"), 
     ["cal_date", "is_open", "pretrade_date"]),
    ("stock_basic_L", lambda: client.pro.stock_basic(exchange="", list_status="L", fields="ts_code,symbol,name,market,exchange,list_status,list_date,delist_date"), 
     ["ts_code", "symbol", "name", "market", "exchange", "list_status", "list_date", "delist_date"]),
    ("stock_basic_D", lambda: client.pro.stock_basic(exchange="", list_status="D", fields="ts_code,symbol,name,market,exchange,list_status,list_date,delist_date"), 
     ["ts_code", "symbol", "name", "market", "exchange", "list_status", "list_date", "delist_date"]),
    ("stock_basic_P", lambda: client.pro.stock_basic(exchange="", list_status="P", fields="ts_code,symbol,name,market,exchange,list_status,list_date,delist_date"), 
     ["ts_code", "symbol", "name", "market", "exchange", "list_status", "list_date", "delist_date"]),
    ("stock_st_20161230", lambda: client.pro.stock_st(trade_date="20161230"), 
     ["ts_code", "name", "trade_date", "type"]),
    ("stock_st_recent", lambda: client.pro.stock_st(trade_date=checkpoints.get("recent", "20260710")), 
     ["ts_code", "name", "trade_date", "type"]),
    ("daily_sample", lambda: client.pro.daily(trade_date=checkpoints.get(2020, "20201231")), 
     ["ts_code", "trade_date", "open", "high", "low", "close", "vol", "amount"]),
    ("daily_basic_sample", lambda: client.pro.daily_basic(trade_date=checkpoints.get(2020, "20201231")), 
     ["ts_code", "trade_date", "turnover_rate", "total_mv", "circ_mv"]),
    ("index_daily_000300", lambda: client.pro.index_daily(ts_code="000300.SH", start_date="20160104", end_date="20161231"), 
     ["ts_code", "trade_date", "close", "vol", "amount"]),
    ("index_member_all_Y", lambda: client.pro.index_member_all(ts_code="600000.SH", is_new="Y"), 
     ["l1_code", "l1_name", "ts_code", "in_date", "out_date", "is_new"]),
    ("index_member_all_N", lambda: client.pro.index_member_all(ts_code="688001.SH", is_new="N"), 
     ["l1_code", "l1_name", "ts_code", "in_date", "out_date", "is_new"]),
]

for name, fn, req_fields in interfaces:
    try:
        df = fn()
        actual_cols = list(df.columns) if len(df) > 0 else []
        result = {
            "rows": len(df),
            "required_fields": req_fields,
            "actual_fields": actual_cols,
            "missing_fields": [f for f in req_fields if f not in actual_cols],
            "hash": hashlib.sha256(str(df.values).encode()).hexdigest()[:16] if len(df) > 0 else "empty",
        }
        if len(df) > 0:
            for col in ["trade_date", "cal_date", "imp_date", "list_date", "in_date"]:
                if col in df.columns:
                    result["date_range"] = f"{df[col].min()}-{df[col].max()}"
                    break
        audit["interfaces"][name] = result
    except Exception as e:
        audit["interfaces"][name] = {"error": str(e)[:200]}

# Write audit
output = Path(__file__).parent.parent / "docs/verification/formal_pit_interface_audit.json"
output.parent.mkdir(parents=True, exist_ok=True)
with open(output, "w") as f:
    json.dump(audit, f, indent=2)

print(json.dumps(audit, indent=2))
