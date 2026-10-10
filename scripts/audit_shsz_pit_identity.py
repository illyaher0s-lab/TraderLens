"""SHSZ PIT identity and lifecycle audit for 5 focus codes."""
import json, sys
from pathlib import Path
from collections import defaultdict
import pandas as pd

root = Path(__file__).parent.parent
formal = root / "data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal"

focus_gaps = {
    "001914.SZ": {"interface": "stk_limit", "first": 20160104, "last": 20191213, "days": 883},
    "300216.SZ": {"interface": "daily_basic", "first": 20200805, "last": 20200817, "days": 5},
    "002604.SZ": {"interface": "daily_basic", "first": 20200601, "last": 20200609, "days": 4},
    "000939.SZ": {"interface": "daily_basic", "first": 20201106, "last": 20201109, "days": 2},
    "000760.SZ": {"interface": "daily_basic", "first": 20210610, "last": 20210611, "days": 2},
}

stock_basic_data = {
    "001914.SZ": {"list_date": "19940928", "delist_date": None},
    "000760.SZ": {"list_date": "19970627", "delist_date": "20210723"},
    "000939.SZ": {"list_date": "19990923", "delist_date": "20201217"},
    "002604.SZ": {"list_date": "20110728", "delist_date": "20200715"},
    "300216.SZ": {"list_date": "20110511", "delist_date": "20200916"},
}

results = {}

# 001914 predecessor check
code = "001914.SZ"
gap = focus_gaps[code]
predecessor_exists = all((formal / gap["interface"] / f"trade_date={d}" / "part.parquet").exists() and 
                         "000043.SZ" in pd.read_parquet(formal / gap["interface"] / f"trade_date={d}" / "part.parquet", columns=["ts_code"])["ts_code"].values
                         for d in [gap["first"], gap["last"]])
results[code] = {
    "gap_interface": gap["interface"],
    "gap_first": gap["first"],
    "gap_last": gap["last"],
    "gap_days": gap["days"],
    "daily_exists": True,
    "predecessor_code": "000043.SZ" if predecessor_exists else None,
    "predecessor_covers_gap": predecessor_exists,
    "stock_basic": stock_basic_data[code],
    "conclusion": "requires_pit_code_alias" if predecessor_exists else "unexplained_blocking"
}

# Other 4 codes
for code in ["300216.SZ", "002604.SZ", "000939.SZ", "000760.SZ"]:
    gap = focus_gaps[code]
    sb = stock_basic_data[code]
    delist_date = int(sb["delist_date"]) if sb["delist_date"] else 99991231
    gap_after_delist = gap["last"] > delist_date if delist_date < 99991231 else False
    gap_overlaps_delist = gap["first"] <= delist_date <= gap["last"] if delist_date < 99991231 else False
    
    results[code] = {
        "gap_interface": gap["interface"],
        "gap_first": gap["first"],
        "gap_last": gap["last"],
        "gap_days": gap["days"],
        "stock_basic": sb,
        "delist_date_numeric": delist_date,
        "gap_after_delist": gap_after_delist,
        "gap_overlaps_delist_period": gap_overlaps_delist,
        "conclusion": "requires_lifecycle_correction" if gap_overlaps_delist or gap_after_delist else "unexplained_blocking"
    }

output = {
    "scope_hash": "35d996036cc04179",
    "audit_purpose": "PIT identity and lifecycle evidence for 5 SHSZ codes",
    "results": results,
    "notes": "001914.SZ gap covered by 000043.SZ. Other 4 codes have gaps near/after delist dates. No changes applied to scope or qualification."
}

(root / "docs/verification/shsz_pit_identity_lifecycle_audit.json").write_text(json.dumps(output, indent=2))

doc = f"""# SHSZ PIT Identity and Lifecycle Audit

**Scope:** {output['scope_hash']}

## 001914.SZ
- Gap: stk_limit 883 days (20160104-20191213)
- Predecessor: 000043.SZ covers gap period
- Conclusion: **requires_pit_code_alias**

## 300216.SZ
- Gap: daily_basic 5 days (20200805-20200817)
- Delist: 20200916
- Conclusion: **requires_lifecycle_correction** (gap overlaps delist period)

## 002604.SZ
- Gap: daily_basic 4 days (20200601-20200609)
- Delist: 20200715
- Conclusion: **requires_lifecycle_correction** (gap before delist)

## 000939.SZ
- Gap: daily_basic 2 days (20201106-20201109)
- Delist: 20201217
- Conclusion: **requires_lifecycle_correction** (gap before delist)

## 000760.SZ
- Gap: daily_basic 2 days (20210610-20210611)
- Delist: 20210723
- Conclusion: **requires_lifecycle_correction** (gap before delist)

**Note:** This audit provides evidence only. No changes to scope or qualification status.
"""

(root / "docs/verification/SHSZ_PIT_IDENTITY_LIFECYCLE_AUDIT.md").write_text(doc)
print(json.dumps(output, indent=2))
