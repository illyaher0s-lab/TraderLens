"""北交所历史映射与缺口证据审计 - 单次扫描版."""
import json, sys, time
from pathlib import Path
from collections import defaultdict
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.sw2021_pit_qualification_core import build_events, step_active, eligible_codes_independent

BJ_CUTOFF = 20211115

def bucket_gap(code, date):
    """Pure: (code, date) -> bucket name."""
    if code.endswith(".BJ"):
        return "bj_pre" if date < BJ_CUTOFF else "bj_post"
    if code.endswith((".SH", ".SZ")):
        return "shsz"
    return "other"

def run_audit():
    root = Path(__file__).parent.parent
    formal = root / "data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal"
    sw_dir = formal / "sw_l1_membership"
    vendor_dir = root / "data/pit/vendor_daily_snapshot/vendor_8e64285ae2fdea2e"
    
    sw_univ = json.loads((sw_dir / "sw2021_universe_candidate.json").read_text())
    vendor_life = json.loads((vendor_dir / "security_lifecycle_candidate.json").read_text())
    
    stocks = pd.concat([pd.read_parquet(formal / "stock_basic" / f"list_status={s}" / "part.parquet", columns=["ts_code","list_date","delist_date"]) for s in ["L","D","P"]], ignore_index=True)
    life = stocks.set_index("ts_code")
    for c in vendor_life["codes"]:
        life.loc[c["ts_code"]] = [c["list_date"], c["delist_date"]]
    life["list_date"] = pd.to_numeric(life["list_date"]).fillna(99991231).astype(int)
    life["delist_date"] = pd.to_numeric(life["delist_date"]).fillna(99991231).astype(int)
    
    sw21_manifest = json.loads((sw_dir / "manifest.json").read_text())
    sw21 = pd.concat([pd.read_parquet(sw_dir / p["name"]) for p in sw21_manifest["partitions"] if p["src"]=="SW2021"])
    sw21["in_date"] = sw21["in_date"].astype(int)
    sw21["out_date"] = sw21["out_date"].fillna(99991231).astype(int)
    
    cal = pd.read_parquet(formal / "trade_cal/part.parquet")
    days = sorted(cal[cal["is_open"].astype(int)==1]["cal_date"].astype(int).tolist())
    starts, ends = build_events(sw21, days)
    
    # ponytail: single pass, all evidence
    stk_gaps, db_gaps = [], []
    bj_daily_first, bj_daily_last, bj_daily_pre, bj_daily_post = {}, {}, set(), set()
    focus_stk, focus_db = defaultdict(list), defaultdict(list)
    focus_codes = ["001914.SZ", "300216.SZ", "002604.SZ", "000939.SZ", "000760.SZ"]
    
    active = {}
    for i, d in enumerate(days):
        active = step_active(active, ends, starts, i)
        
        # Expected universe independent of daily rows
        expected, _, _, _, _ = eligible_codes_independent(life, active, d)
        
        # Check if daily partition exists (for progress tracking)
        daily_p = formal / "daily" / f"trade_date={d}" / "part.parquet"
        if not daily_p.exists(): continue
        
        # Track BJ daily presence (from actual daily rows)
        daily_codes = set(pd.read_parquet(daily_p, columns=["ts_code"])["ts_code"])
        
        # ponytail: track BJ daily presence
        for code in daily_codes:
            if code.endswith(".BJ"):
                bj_daily_first.setdefault(code, d)
                bj_daily_last[code] = d
                (bj_daily_pre if d < BJ_CUTOFF else bj_daily_post).add(code)
        
        for iface, gaps_list in [("stk_limit", stk_gaps), ("daily_basic", db_gaps)]:
            p = formal / iface / f"trade_date={d}" / "part.parquet"
            if not p.exists(): continue
            codes = set(pd.read_parquet(p, columns=["ts_code"])["ts_code"])
            for code in expected - codes:
                gaps_list.append((code, d))
                if code in focus_codes:
                    (focus_stk if iface == "stk_limit" else focus_db)[code].append(d)
    
    # ponytail: buckets
    stk_buckets = defaultdict(list)
    for g in stk_gaps:
        stk_buckets[bucket_gap(g[0], g[1])].append(g)
    db_buckets = defaultdict(list)
    for g in db_gaps:
        db_buckets[bucket_gap(g[0], g[1])].append(g)
    union_gaps = set(stk_gaps) | set(db_gaps)
    union_buckets = defaultdict(list)
    for g in union_gaps:
        union_buckets[bucket_gap(g[0], g[1])].append(g)
    
    # ponytail: BJ evidence (all codes, no top-N)
    bj_codes = {g[0] for g in union_gaps if g[0].endswith(".BJ")}
    bj_evidence = {}
    for code in sorted(bj_codes):
        gap_dates = sorted({g[1] for g in union_gaps if g[0] == code})
        bj_evidence[code] = {
            "daily_first": bj_daily_first.get(code),
            "daily_last": bj_daily_last.get(code),
            "gap_first": min(gap_dates) if gap_dates else None,
            "gap_last": max(gap_dates) if gap_dates else None,
            "has_daily_pre_cutoff": code in bj_daily_pre,
            "has_daily_post_cutoff": code in bj_daily_post,
            "has_gap_post_cutoff": any(d >= BJ_CUTOFF for d in gap_dates),
            "lifecycle_exists": code in life.index,
            "lifecycle_list_date": int(life.loc[code, "list_date"]) if code in life.index else None
        }
    
    # ponytail: focus + sparse events
    focus_evidence = {}
    for code in focus_codes:
        stk_dates = focus_stk.get(code, [])
        db_dates = focus_db.get(code, [])
        focus_evidence[code] = {
            "in_stk_limit_gaps": len(stk_dates) > 0,
            "in_daily_basic_gaps": len(db_dates) > 0,
            "stk_gap_count": len(stk_dates),
            "db_gap_count": len(db_dates),
            "lifecycle_exists": code in life.index
        }
    
    def bucket_stats(bucket):
        return {"stock_days": len(bucket), "unique_codes": len({g[0] for g in bucket}), "first_date": min((g[1] for g in bucket), default=None), "last_date": max((g[1] for g in bucket), default=None)}
    
    result = {
        "scope_hash": "fa4e3fd8f98d8758",
        "bj_cutoff_date": BJ_CUTOFF,
        "stk_limit_buckets": {k: bucket_stats(v) for k, v in stk_buckets.items()},
        "daily_basic_buckets": {k: bucket_stats(v) for k, v in db_buckets.items()},
        "union_buckets": {k: bucket_stats(v) for k, v in union_buckets.items()},
        "bj_code_evidence": bj_evidence,
        "focus_code_evidence": focus_evidence
    }
    
    (root / "docs/verification/bj_history_mapping_audit.json").write_text(json.dumps(result, indent=2))
    
    doc = f"""# 北交所历史映射与缺口证据审计

**Scope:** {result['scope_hash']}  
**Cutoff:** {BJ_CUTOFF}  
**Key:** (ts_code, trade_date)

## stk_limit 分桶
- .BJ pre: {result['stk_limit_buckets'].get('bj_pre', {}).get('stock_days', 0)} stock-days
- .BJ post: {result['stk_limit_buckets'].get('bj_post', {}).get('stock_days', 0)} stock-days
- .SH/.SZ: {result['stk_limit_buckets'].get('shsz', {}).get('stock_days', 0)} stock-days

## daily_basic 分桶
- .BJ pre: {result['daily_basic_buckets'].get('bj_pre', {}).get('stock_days', 0)} stock-days
- .BJ post: {result['daily_basic_buckets'].get('bj_post', {}).get('stock_days', 0)} stock-days
- .SH/.SZ: {result['daily_basic_buckets'].get('shsz', {}).get('stock_days', 0)} stock-days

## 并集分桶
- .BJ pre: {result['union_buckets'].get('bj_pre', {}).get('stock_days', 0)} stock-days
- .BJ post: {result['union_buckets'].get('bj_post', {}).get('stock_days', 0)} stock-days
- .SH/.SZ: {result['union_buckets'].get('shsz', {}).get('stock_days', 0)} stock-days

全部 {len(bj_evidence)} 个 .BJ 代码已输出。是否变更 universe 不属于本次审计决策范围。
"""
    (root / "docs/verification/BJ_HISTORY_MAPPING_AUDIT.md").write_text(doc)
    return result

if __name__ == "__main__":
    start = time.time()
    result = run_audit()
    elapsed = time.time() - start
    print(json.dumps(result, indent=2))
    print(f"\nElapsed: {elapsed:.1f}s", file=sys.stderr)
