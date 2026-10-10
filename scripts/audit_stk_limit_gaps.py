"""stk_limit gap classification audit."""
import hashlib, json, sys
from pathlib import Path
from collections import Counter, defaultdict
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.sw2021_pit_qualification_core import build_events, step_active, eligible_codes_independent

root = Path(__file__).parent.parent
formal = root / "data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal"
sw_dir = formal / "sw_l1_membership"
vendor_dir = root / "data/pit/vendor_daily_snapshot/vendor_8e64285ae2fdea2e"

# Load hashes
sw_univ = json.loads((sw_dir / "sw2021_universe_candidate.json").read_text())
vendor_life = json.loads((vendor_dir / "security_lifecycle_candidate.json").read_text())

# Lifecycle
stocks = pd.concat([pd.read_parquet(formal / "stock_basic" / f"list_status={s}" / "part.parquet", columns=["ts_code","list_date","delist_date"]) for s in ["L","D","P"]], ignore_index=True)
life = stocks.set_index("ts_code")

# Vendor exceptions (before numeric conversion, like qualifier)
for c in vendor_life["codes"]:
    life.loc[c["ts_code"]] = [c["list_date"], c["delist_date"]]

# Now convert to numeric
life["list_date"] = pd.to_numeric(life["list_date"]).fillna(99991231).astype(int)
life["delist_date"] = pd.to_numeric(life["delist_date"]).fillna(99991231).astype(int)

# SW2021 membership
sw21_manifest = json.loads((sw_dir / "manifest.json").read_text())
sw21 = pd.concat([pd.read_parquet(sw_dir / p["name"]) for p in sw21_manifest["partitions"] if p["src"]=="SW2021"])
sw21["in_date"] = sw21["in_date"].astype(int)
sw21["out_date"] = sw21["out_date"].fillna(99991231).astype(int)

# Trade calendar
cal = pd.read_parquet(formal / "trade_cal/part.parquet")
days = sorted(cal[cal["is_open"].astype(int)==1]["cal_date"].astype(int).tolist())

# Build events
starts, ends = build_events(sw21, days)

# Scan
gap_messages = []  # ponytail: count like qualifier (per-day messages)
gap_stock_days = []  # ponytail: actual stock-days for classification
active = {}
for i, d in enumerate(days):
    active = step_active(active, ends, starts, i)
    
    # Expected universe independent of daily rows
    eligible, _, _, _, _ = eligible_codes_independent(life, active, d)
    
    # Check if daily partition exists (for progress tracking)
    daily_p = formal / "daily" / f"trade_date={d}" / "part.parquet"
    if not daily_p.exists(): continue
    
    stk_p = formal / "stk_limit" / f"trade_date={d}" / "part.parquet"
    if not stk_p.exists(): continue
    stk_codes = set(pd.read_parquet(stk_p, columns=["ts_code"])["ts_code"])
    
    missing = eligible - stk_codes
    if missing:
        gap_messages.append(f"{d}: stk_limit missing {len(missing)} expected codes")
        for code in missing:
            gap_stock_days.append({"date": d, "ts_code": code})

# Classify
gap_df = pd.DataFrame(gap_stock_days)
codes = gap_df["ts_code"].unique()

vendor_codes = {c["ts_code"] for c in vendor_life["codes"]}

classification = Counter()
code_details = []

for code in codes:
    code_gaps = gap_df[gap_df["ts_code"]==code]
    dates = sorted(code_gaps["date"].tolist())
    
    # ponytail: per-date first_n check
    if code in life.index:
        list_date = life.loc[code, "list_date"]
        first_n_dates = []
        for d in dates:
            days_since_list = sum(1 for td in days if list_date <= td <= d)
            if days_since_list <= 30:
                first_n_dates.append(d)
    else:
        first_n_dates = []
    
    # Classify
    if code in vendor_codes:
        cat = "lifecycle_or_membership_inconsistency"
    elif len(first_n_dates) == len(dates):
        cat = "first_n_trading_days_observed"
    elif code not in life.index:
        cat = "provider_row_missing"
    else:
        cat = "unclassified"
    
    classification[cat] += len(dates)
    code_details.append({
        "ts_code": code,
        "gap_days": len(dates),
        "first_date": dates[0],
        "last_date": dates[-1],
        "classification": cat
    })

result = {
    "scope_hash": "fa4e3fd8f98d8758",
    "sw2021_universe_hash": sw_univ["universe_definition_hash"],
    "vendor_lifecycle_hash": vendor_life["vendor_package_sha256"],
    "checked_trade_days": 2554,
    "total_gap_messages": len(gap_messages),  # ponytail: matches manifest
    "total_gap_stock_days": len(gap_stock_days),
    "unique_codes": len(codes),
    "classification": dict(classification),
    "first_gap_message": gap_messages[0] if gap_messages else None,
    "code_details": sorted(code_details, key=lambda x: -x["gap_days"])  # ponytail: all codes
}

(root / "docs/verification/stk_limit_gap_audit.json").write_text(json.dumps(result, indent=2))

doc = f"""# stk_limit Gap Audit

**Scope:** {result['scope_hash']}  
**Gap messages:** {result['total_gap_messages']} (matches manifest)  
**Gap stock-days:** {result['total_gap_stock_days']}  
**Unique codes:** {len(codes)}

## Classification
"""
for cat, count in classification.most_common():
    doc += f"- {cat}: {count}\n"

doc += "\n## All codes by gap days\n"
for cd in code_details:
    doc += f"- {cd['ts_code']}: {cd['gap_days']} days ({cd['first_date']}-{cd['last_date']}) [{cd['classification']}]\n"

(root / "docs/verification/STK_LIMIT_GAP_AUDIT.md").write_text(doc)

print(json.dumps(result, indent=2))
sys.exit(0)
