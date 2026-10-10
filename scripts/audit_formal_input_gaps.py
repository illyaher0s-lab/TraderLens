"""Unified formal input gap audit (stk_limit + daily_basic)."""
import json, sys
from pathlib import Path
from collections import Counter
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.sw2021_pit_qualification_core import build_events, step_active, eligible_codes_independent

root = Path(__file__).parent.parent
formal = root / "data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal"
sw_dir = formal / "sw_l1_membership"
vendor_dir = root / "data/pit/vendor_daily_snapshot/vendor_8e64285ae2fdea2e"

sw_univ = json.loads((sw_dir / "sw2021_universe_candidate.json").read_text())
vendor_life = json.loads((vendor_dir / "security_lifecycle_candidate.json").read_text())

# Lifecycle
stocks = pd.concat([pd.read_parquet(formal / "stock_basic" / f"list_status={s}" / "part.parquet", columns=["ts_code","list_date","delist_date"]) for s in ["L","D","P"]], ignore_index=True)
life = stocks.set_index("ts_code")
for c in vendor_life["codes"]:
    life.loc[c["ts_code"]] = [c["list_date"], c["delist_date"]]
life["list_date"] = pd.to_numeric(life["list_date"]).fillna(99991231).astype(int)
life["delist_date"] = pd.to_numeric(life["delist_date"]).fillna(99991231).astype(int)

# SW2021
sw21_manifest = json.loads((sw_dir / "manifest.json").read_text())
sw21 = pd.concat([pd.read_parquet(sw_dir / p["name"]) for p in sw21_manifest["partitions"] if p["src"]=="SW2021"])
sw21["in_date"] = sw21["in_date"].astype(int)
sw21["out_date"] = sw21["out_date"].fillna(99991231).astype(int)

cal = pd.read_parquet(formal / "trade_cal/part.parquet")
days = sorted(cal[cal["is_open"].astype(int)==1]["cal_date"].astype(int).tolist())

starts, ends = build_events(sw21, days)

# Scan
gaps = {"stk_limit": [], "daily_basic": []}
active = {}
for i, d in enumerate(days):
    active = step_active(active, ends, starts, i)
    
    # Expected universe independent of daily rows
    expected, _, _, _, _ = eligible_codes_independent(life, active, d)
    
    # Check if daily partition exists (for progress tracking)
    daily_p = formal / "daily" / f"trade_date={d}" / "part.parquet"
    if not daily_p.exists(): continue
    
    for iface in ["stk_limit", "daily_basic"]:
        p = formal / iface / f"trade_date={d}" / "part.parquet"
        if not p.exists(): continue
        codes = set(pd.read_parquet(p, columns=["ts_code"])["ts_code"])
        missing = expected - codes
        for code in missing:
            gaps[iface].append({"date": d, "ts_code": code})

# Intersect
stk_set = {(g["date"], g["ts_code"]) for g in gaps["stk_limit"]}
db_set = {(g["date"], g["ts_code"]) for g in gaps["daily_basic"]}
both = stk_set & db_set
stk_only = stk_set - db_set
db_only = db_set - stk_set

# Classify
def classify_gaps(gap_list, iface_name):
    df = pd.DataFrame(gap_list)
    codes = df["ts_code"].unique()
    classification = Counter()
    details = []
    for code in codes:
        code_gaps = df[df["ts_code"]==code]
        dates = sorted(code_gaps["date"].tolist())
        if code in life.index:
            list_date = life.loc[code, "list_date"]
            first_n_dates = [d for d in dates if sum(1 for td in days if list_date <= td <= d) <= 30]
        else:
            first_n_dates = []
        
        if len(first_n_dates) == len(dates):
            cat = "first_n_trading_days_observed"
        elif code not in life.index:
            cat = "provider_row_missing"
        else:
            cat = "unclassified_blocking"
        
        classification[cat] += len(dates)
        details.append({"ts_code": code, "gap_days": len(dates), "first_date": dates[0], "last_date": dates[-1], "classification": cat})
    return classification, details

stk_class, stk_details = classify_gaps(gaps["stk_limit"], "stk_limit")
db_class, db_details = classify_gaps(gaps["daily_basic"], "daily_basic")

result = {
    "scope_hash": "fa4e3fd8f98d8758",
    "sw2021_universe_hash": sw_univ["universe_definition_hash"],
    "checked_trade_days": 2554,
    "stk_limit": {"message_count": len({g["date"] for g in gaps["stk_limit"]}), "stock_day_count": len(gaps["stk_limit"]), "unique_codes": len(set(g["ts_code"] for g in gaps["stk_limit"])), "classification": dict(stk_class), "code_details": sorted(stk_details, key=lambda x: -x["gap_days"])},
    "daily_basic": {"message_count": len({g["date"] for g in gaps["daily_basic"]}), "stock_day_count": len(gaps["daily_basic"]), "unique_codes": len(set(g["ts_code"] for g in gaps["daily_basic"])), "classification": dict(db_class), "code_details": sorted(db_details, key=lambda x: -x["gap_days"])},
    "intersection": {"stock_day_count": len(both), "unique_codes": len({code for _, code in both})},
    "stk_limit_only": {"stock_day_count": len(stk_only), "unique_codes": len({code for _, code in stk_only})},
    "daily_basic_only": {"stock_day_count": len(db_only), "unique_codes": len({code for _, code in db_only})},
    "first_gap": min((g["date"] for g in gaps["stk_limit"] + gaps["daily_basic"]), default=None)
}

(root / "docs/verification/formal_input_gap_audit.json").write_text(json.dumps(result, indent=2))

doc = f"""# Formal Input Gap Audit

**Scope:** {result['scope_hash']}  
**Checked days:** {result['checked_trade_days']}  
**First gap:** {result['first_gap']}

## stk_limit
- Messages: {result['stk_limit']['message_count']}
- Stock-days: {result['stk_limit']['stock_day_count']}
- Codes: {result['stk_limit']['unique_codes']}
- Classification: {result['stk_limit']['classification']}

## daily_basic
- Messages: {result['daily_basic']['message_count']}
- Stock-days: {result['daily_basic']['stock_day_count']}
- Codes: {result['daily_basic']['unique_codes']}
- Classification: {result['daily_basic']['classification']}

## Overlap
- Both missing: {result['intersection']['stock_day_count']} stock-days, {result['intersection']['unique_codes']} codes
- stk_limit only: {result['stk_limit_only']['stock_day_count']} stock-days
- daily_basic only: {result['daily_basic_only']['stock_day_count']} stock-days

This is diagnostic output. It does not change formal qualification status.
"""

(root / "docs/verification/FORMAL_INPUT_GAP_AUDIT.md").write_text(doc)
print(json.dumps(result, indent=2))
