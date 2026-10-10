"""Read-only root-cause audit for daily codes absent from PIT stock_basic."""
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).parent.parent
FORMAL = ROOT / "data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal"
LIFECYCLE_FIELDS = "ts_code,symbol,name,market,exchange,list_status,list_date,delist_date"
sys.path.insert(0, str(ROOT))


def _load_env_local() -> None:
    env_file = ROOT / ".env.local"
    if not env_file.exists():
        return
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key, value)


def _trading_days() -> list[str]:
    calendar = pd.read_parquet(FORMAL / "trade_cal" / "part.parquet")
    return sorted(calendar.loc[calendar["is_open"].astype(int) == 1, "cal_date"].astype(str).tolist())


def _local_lifecycle_codes() -> set[str]:
    frames = [
        pd.read_parquet(FORMAL / "stock_basic" / f"list_status={status}" / "part.parquet", columns=["ts_code"])
        for status in ("L", "D", "P")
    ]
    return set(pd.concat(frames, ignore_index=True)["ts_code"].dropna())


def _gap_days(days: list[str], lifecycle_codes: set[str]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = defaultdict(list)
    for trade_date in days:
        path = FORMAL / "daily" / f"trade_date={trade_date}" / "part.parquet"
        if not path.exists():
            raise FileNotFoundError(f"daily partition missing: {trade_date}")
        codes = pd.read_parquet(path, columns=["ts_code"])["ts_code"].dropna().unique()
        for code in codes:
            if code not in lifecycle_codes:
                result[code].append(trade_date)
    return result


def _intervals(dates: list[str], all_days: list[str]) -> list[dict]:
    positions = {day: index for index, day in enumerate(all_days)}
    intervals: list[dict] = []
    start = previous = dates[0]
    count = 1
    for day in dates[1:]:
        if positions[day] == positions[previous] + 1:
            count += 1
        else:
            intervals.append({"start": start, "end": previous, "trading_days": count})
            start, count = day, 1
        previous = day
    intervals.append({"start": start, "end": previous, "trading_days": count})
    return intervals


def _local_event_codes(directory: str) -> set[str]:
    paths = list((FORMAL / directory).rglob("*.parquet"))
    if not paths:
        return set()
    return set(pd.concat([pd.read_parquet(path, columns=["ts_code"]) for path in paths])["ts_code"].dropna())


def _native_stock_basic_probe(gap_codes: set[str]) -> dict:
    _load_env_local()
    from backend.app.tushare.config import TushareConfig
    from backend.app.tushare.tushare_client import TushareClient

    client = TushareClient(TushareConfig.from_env())
    results = []
    found_codes: set[str] = set()
    for status in ("L", "D", "P"):
        try:
            client._enforce_rate_limit()
            frame = client.pro.stock_basic(exchange="", list_status=status, fields=LIFECYCLE_FIELDS)
            fields = list(frame.columns) if frame is not None else []
            codes = set(frame["ts_code"].dropna()) if frame is not None and "ts_code" in frame else set()
            found = sorted(gap_codes & codes)
            found_codes.update(found)
            results.append({
                "list_status": status,
                "row_count": 0 if frame is None else len(frame),
                "fields": fields,
                "found_gap_codes": found,
                "error_type": None,
            })
        except Exception as error:
            results.append({
                "list_status": status,
                "row_count": None,
                "fields": [],
                "found_gap_codes": [],
                "error_type": type(error).__name__,
            })
    return {
        "attempted_statuses": ["L", "D", "P"],
        "requested_fields": LIFECYCLE_FIELDS.split(","),
        "results": results,
        "found_gap_codes": sorted(found_codes),
    }


def run_audit() -> dict:
    days = _trading_days()
    gaps = _gap_days(days, _local_lifecycle_codes())
    gap_codes = set(gaps)
    namechange_codes = _local_event_codes("namechange")
    stock_st_codes = _local_event_codes("stock_st")
    probe = _native_stock_basic_probe(gap_codes) if gap_codes else {
        "attempted_statuses": ["L", "D", "P"], "requested_fields": LIFECYCLE_FIELDS.split(","), "results": [], "found_gap_codes": []
    }
    probe_failed = any(item["error_type"] for item in probe["results"])
    if not gap_codes:
        status = "lifecycle_resolution_ready"
    elif probe_failed:
        status = "lifecycle_provider_probe_failed"
    elif gap_codes <= set(probe["found_gap_codes"]):
        status = "lifecycle_snapshot_incomplete"
    else:
        status = "lifecycle_source_incomplete"
    details = [
        {
            "ts_code": code,
            "total_days": len(gaps[code]),
            "first_date": gaps[code][0],
            "last_date": gaps[code][-1],
            "intervals": _intervals(gaps[code], days),
            "in_namechange": code in namechange_codes,
            "in_stock_st": code in stock_st_codes,
        }
        for code in sorted(gap_codes, key=lambda value: len(gaps[value]), reverse=True)
    ]
    evidence = {
        "status": status,
        "checked_trade_days": len(days),
        "unique_gap_codes": len(gap_codes),
        "total_gap_stock_days": sum(len(value) for value in gaps.values()),
        "gap_codes": details,
        "native_stock_basic_probe": probe,
        "formal_qualification_run": False,
    }
    (ROOT / "docs/verification/pit_lifecycle_gap_evidence.json").write_text(json.dumps(evidence, indent=2))
    rows = "\n".join(
        f"| {item['ts_code']} | {item['total_days']} | {item['first_date']} | {item['last_date']} | {item['in_namechange']} | {item['in_stock_st']} |"
        for item in details
    ) or "| None | 0 | - | - | - | - |"
    report = f"""# PIT Lifecycle Gap Audit

**Status:** {status}  
**Checked trading days:** {len(days)}  
**Formal qualification run:** No

## Local gaps

| ts_code | Missing stock-days | First | Last | namechange | stock_st |
|---|---:|---|---|---|---|
{rows}

## Native provider probe

- Calls: `stock_basic` for L, D, P only
- Requested fields: `{LIFECYCLE_FIELDS}`
- Provider found gap codes: {probe['found_gap_codes']}
- Probe errors: {[item['error_type'] for item in probe['results'] if item['error_type']]}

No name-based or vendor-based lifecycle inference was used. This audit does not qualify the data package.
"""
    (ROOT / "docs/verification/PIT_LIFECYCLE_GAP_AUDIT.md").write_text(report)
    return evidence


if __name__ == "__main__":
    result = run_audit()
    print(json.dumps({key: result[key] for key in ("status", "unique_gap_codes", "total_gap_stock_days")}, indent=2))
    sys.exit(0 if result["status"] == "lifecycle_resolution_ready" else 1)
