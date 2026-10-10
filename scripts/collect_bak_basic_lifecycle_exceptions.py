"""Collect the bounded bak_basic supplement for stock_basic historical holes."""
import hashlib
import json
import os
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
FORMAL = ROOT / "data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal"
OUT = FORMAL / "bak_basic_lifecycle"
FIELDS = "trade_date,ts_code,name,list_date"


def _load_env() -> None:
    for raw in (ROOT / ".env.local").read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key, value)


def _gap_dates_by_code(codes: set[str]) -> dict[str, set[str]]:
    calendar = pd.read_parquet(FORMAL / "trade_cal" / "part.parquet")
    days = calendar.loc[calendar["is_open"].astype(int) == 1, "cal_date"].astype(str)
    result = {code: set() for code in codes}
    for trade_date in days:
        daily = pd.read_parquet(FORMAL / "daily" / f"trade_date={trade_date}" / "part.parquet", columns=["ts_code"])
        for code in codes & set(daily["ts_code"].dropna()):
            result[code].add(trade_date)
    return result


def run_collection() -> dict:
    evidence_path = ROOT / "docs/verification/pit_lifecycle_gap_evidence.json"
    evidence = json.loads(evidence_path.read_text())
    codes = {item["ts_code"] for item in evidence["gap_codes"]}
    if not codes:
        raise ValueError("no lifecycle gap codes to collect")
    _load_env()
    from backend.app.tushare.config import TushareConfig
    from backend.app.tushare.tushare_client import TushareClient

    expected_dates = _gap_dates_by_code(codes)
    client = TushareClient(TushareConfig.from_env())
    OUT.mkdir(parents=True, exist_ok=True)
    partitions = []
    uncovered = 0
    errors = []
    for code in sorted(codes):
        try:
            client._enforce_rate_limit()
            frame = client.pro.bak_basic(ts_code=code, fields=FIELDS)
            required = set(FIELDS.split(","))
            if frame is None or required - set(frame.columns):
                raise ValueError(f"bak_basic missing fields: {sorted(required - set(frame.columns if frame is not None else []))}")
            frame = frame.loc[:, FIELDS.split(",")].copy()
            frame["trade_date"] = frame["trade_date"].astype(str)
            frame["list_date"] = frame["list_date"].astype(str)
            if frame.empty or frame["list_date"].isin(["", "None", "nan"]).any() or frame["list_date"].nunique() != 1:
                raise ValueError("bak_basic lifecycle list_date is empty or inconsistent")
            missing_dates = expected_dates[code] - set(frame["trade_date"])
            uncovered += len(missing_dates)
            if missing_dates:
                raise ValueError(f"bak_basic misses {len(missing_dates)} observed daily dates")
            path = OUT / f"ts_code={code}" / "part.parquet"
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = path.with_suffix(".tmp.parquet")
            frame.to_parquet(temp, index=False)
            os.replace(temp, path)
            sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
            path.with_suffix(".parquet.sha256").write_text(sha256)
            partitions.append({
                "ts_code": code,
                "row_count": len(frame),
                "list_date": frame["list_date"].iloc[0],
                "first_trade_date": frame["trade_date"].min(),
                "last_trade_date": frame["trade_date"].max(),
                "expected_daily_gap_dates": len(expected_dates[code]),
                "sha256": sha256,
            })
        except Exception as error:
            errors.append({"ts_code": code, "error_type": type(error).__name__})
    status = "candidate_verified" if not errors and uncovered == 0 and len(partitions) == len(codes) else "candidate_not_verified"
    manifest = {
        "status": status,
        "source": "bak_basic",
        "source_fields": FIELDS.split(","),
        "lifecycle_gap_evidence_sha256": hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
        "partitions": partitions,
        "uncovered_daily_gap_dates": uncovered,
        "errors": errors,
        "formal_qualification_run": False,
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2))
    report = f"""# bak_basic Lifecycle Supplement Candidate

**Status:** {status}  
**Source:** Tushare `bak_basic` (historical daily stock list)  
**Formal qualification run:** No

| ts_code | list_date | bak_basic dates | covered daily gap dates |
|---|---|---:|---:|
""" + "\n".join(
        f"| {part['ts_code']} | {part['list_date']} | {part['row_count']} | {part['expected_daily_gap_dates']} |"
        for part in partitions
    ) + f"""

- Uncovered observed daily dates: {uncovered}
- Errors: {errors}
- The manifest binds each persisted partition by SHA-256.

This is a bounded candidate supplement for historical security identity only. It does not make the data package formal-qualified.
"""
    (ROOT / "docs/verification/BAK_BASIC_LIFECYCLE_SUPPLEMENT.md").write_text(report)
    return manifest


if __name__ == "__main__":
    result = run_collection()
    print(json.dumps({"status": result["status"], "uncovered_daily_gap_dates": result["uncovered_daily_gap_dates"]}))
    sys.exit(0 if result["status"] == "candidate_verified" else 1)
