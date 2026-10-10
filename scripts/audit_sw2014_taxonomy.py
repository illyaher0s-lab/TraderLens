"""Local full-window PIT audit for the frozen SW2014 taxonomy candidate."""
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).parent.parent
FORMAL_DIR = PROJECT_ROOT / "data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal"
SW_DIR = FORMAL_DIR / "sw_l1_membership"
PIT_RULE = "in_date <= as_of_date AND (out_date IS NULL OR out_date >= as_of_date)"


def _date_int(values: pd.Series, null_value: int | None = None) -> pd.Series:
    result = pd.to_numeric(values, errors="coerce").astype("Int64")
    return result.fillna(null_value).astype(int) if null_value is not None else result


def _load_lifecycle() -> pd.DataFrame:
    frames = [
        pd.read_parquet(FORMAL_DIR / "stock_basic" / f"list_status={status}" / "part.parquet")
        for status in "LDP"
    ]
    lifecycle = pd.concat(frames, ignore_index=True)[["ts_code", "list_date", "delist_date"]]
    if lifecycle["ts_code"].duplicated().any():
        raise ValueError("stock_basic lifecycle has duplicate ts_code")
    lifecycle["list_date"] = _date_int(lifecycle["list_date"])
    lifecycle["delist_date"] = _date_int(lifecycle["delist_date"], 99991231)
    if lifecycle["list_date"].isna().any():
        raise ValueError("stock_basic lifecycle has missing list_date")
    return lifecycle.set_index("ts_code")


def _load_sw2014(manifest: dict) -> pd.DataFrame:
    parts = [part for part in manifest["partitions"] if part["src"] == "SW2014"]
    sw2014 = pd.concat(
        [pd.read_parquet(SW_DIR / part["name"]) for part in parts], ignore_index=True
    )
    required = {"ts_code", "l1_code", "in_date", "out_date"}
    missing = required - set(sw2014.columns)
    if missing:
        raise ValueError(f"SW2014 membership missing fields: {sorted(missing)}")
    sw2014["in_date"] = _date_int(sw2014["in_date"])
    sw2014["out_date"] = _date_int(sw2014["out_date"], 99991231)
    if sw2014["in_date"].isna().any():
        raise ValueError("SW2014 membership has missing in_date")
    return sw2014, parts


def _membership_events(sw2014: pd.DataFrame, days: list[int]):
    """Build a sweep-line membership index; no daily full-table re-filtering."""
    starts: dict[int, list[tuple[str, str]]] = defaultdict(list)
    ends: dict[int, list[tuple[str, str]]] = defaultdict(list)
    day_index = pd.Index(days)
    for row in sw2014[["ts_code", "l1_code", "in_date", "out_date"]].itertuples(index=False):
        start_at = int(day_index.searchsorted(row.in_date, side="left"))
        end_at = int(day_index.searchsorted(row.out_date, side="right"))
        if start_at < len(days) and end_at > start_at:
            starts[start_at].append((row.ts_code, row.l1_code))
            if end_at < len(days):
                ends[end_at].append((row.ts_code, row.l1_code))
    return starts, ends


def run_audit() -> dict:
    manifest = json.loads((SW_DIR / "manifest.json").read_text())
    sw2014, selected_parts = _load_sw2014(manifest)
    lifecycle = _load_lifecycle()
    calendar = pd.read_parquet(FORMAL_DIR / "trade_cal" / "part.parquet")
    days = sorted(_date_int(calendar.loc[calendar["is_open"].astype(int) == 1, "cal_date"]).tolist())
    starts, ends = _membership_events(sw2014, days)

    active: dict[str, Counter] = defaultdict(Counter)
    gaps: list[str] = []
    daily_stock_days = expected_stock_days = 0
    excluded_pre_listing_stock_days = excluded_post_delisting_stock_days = 0
    unknown_lifecycle_stock_days = 0

    for index, trade_date in enumerate(days):
        for ts_code, l1_code in ends[index]:
            active[ts_code][l1_code] -= 1
            if active[ts_code][l1_code] == 0:
                del active[ts_code][l1_code]
            if not active[ts_code]:
                del active[ts_code]
        for ts_code, l1_code in starts[index]:
            active[ts_code][l1_code] += 1

        daily_path = FORMAL_DIR / "daily" / f"trade_date={trade_date}" / "part.parquet"
        if not daily_path.exists():
            gaps.append(f"{trade_date}: daily partition missing")
            continue
        daily_codes = pd.read_parquet(daily_path, columns=["ts_code"])["ts_code"].dropna().unique()
        daily_stock_days += len(daily_codes)
        life = lifecycle.reindex(daily_codes)
        unknown = life[life["list_date"].isna()].index.tolist()
        if unknown:
            unknown_lifecycle_stock_days += len(unknown)
            gaps.append(f"{trade_date}: {len(unknown)} daily stocks missing lifecycle")
        known = life.dropna(subset=["list_date"])
        pre_listing = known[known["list_date"] > trade_date]
        post_delisting = known[known["delist_date"] < trade_date]
        excluded_pre_listing_stock_days += len(pre_listing)
        excluded_post_delisting_stock_days += len(post_delisting)
        expected = set(known.index) - set(pre_listing.index) - set(post_delisting.index)
        expected_stock_days += len(expected)

        missing = expected - set(active)
        if missing:
            gaps.append(f"{trade_date}: {len(missing)} listed daily stocks missing SW2014 membership (e.g., {sorted(missing)[:3]})")
        conflicts = [code for code in expected if len(active.get(code, ())) != 1]
        if conflicts:
            gaps.append(f"{trade_date}: {len(conflicts)} listed daily stocks have multiple SW2014 L1 memberships")

    status = "taxonomy_selection_ready" if not gaps else "taxonomy_selection_not_ready"
    selection = {
        "taxonomy_source": "SW2014",
        "status": status,
        "audit_window": {"start": str(days[0]), "end": str(days[-1])},
        "checked_trade_days": len(days),
        "daily_stock_days": daily_stock_days,
        "expected_stock_days": expected_stock_days,
        "excluded_pre_listing_stock_days": excluded_pre_listing_stock_days,
        "excluded_post_delisting_stock_days": excluded_post_delisting_stock_days,
        "unknown_lifecycle_stock_days": unknown_lifecycle_stock_days,
        "blocking_gap_count": len(gaps),
        "first_blocking_gap": gaps[0] if gaps else None,
        "selected_partitions": [{"name": part["name"], "sha256": part["sha256"]} for part in selected_parts],
        "pit_rule": PIT_RULE,
        "taxonomy_policy_hash": hashlib.sha256(
            json.dumps({"source": "SW2014", "rule": PIT_RULE}, sort_keys=True).encode()
        ).hexdigest(),
    }
    (SW_DIR / "sw2014_selection.json").write_text(json.dumps(selection, indent=2))
    report = f"""# SW2014 PIT Taxonomy Audit

**Status:** {status}  
**Taxonomy:** SW2014 only  
**Audit window:** {days[0]} to {days[-1]}

## Full Expected-Universe Check

- Checked trade days: {len(days)}
- Daily stock-days read: {daily_stock_days:,}
- Expected listed daily stock-days: {expected_stock_days:,}
- Excluded before listing: {excluded_pre_listing_stock_days:,}
- Excluded after delisting: {excluded_post_delisting_stock_days:,}
- Missing lifecycle: {unknown_lifecycle_stock_days:,}
- Blocking gaps: {len(gaps)}

## Frozen Candidate Policy

- Taxonomy source: SW2014 only
- PIT rule: `{PIT_RULE}`
- Policy hash: `{selection['taxonomy_policy_hash']}`
- Selected partitions: {len(selected_parts)} with SHA-256 in the selection manifest

## First Blocking Gap

{selection['first_blocking_gap'] or 'None'}

This is a full taxonomy-selection audit only; it does not run formal qualification.
"""
    (PROJECT_ROOT / "docs/verification/SW2014_PIT_TAXONOMY_AUDIT.md").write_text(report)
    return selection


if __name__ == "__main__":
    result = run_audit()
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["status"] == "taxonomy_selection_ready" else 1)
