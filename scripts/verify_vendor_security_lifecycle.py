"""Verify vendor list/delist metadata for the bounded stock_basic exceptions."""
import csv
import json
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).parent.parent
VENDOR_ROOT = ROOT / "data/pit/vendor_daily_snapshot/vendor_8e64285ae2fdea2e"
FORMAL = ROOT / "data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal"
LIFECYCLE_EVIDENCE = ROOT / "docs/verification/pit_lifecycle_gap_evidence.json"


def _formal_daily_dates(codes: set[str]) -> dict[str, set[str]]:
    result = {code: set() for code in codes}
    for path in (FORMAL / "daily").glob("trade_date=*/part.parquet"):
        values = set(pd.read_parquet(path, columns=["ts_code"])["ts_code"].dropna())
        for code in codes & values:
            result[code].add(path.parent.name.split("=", 1)[1])
    return result


def run_verification() -> dict:
    intake = json.loads((VENDOR_ROOT / "manifest.json").read_text())
    gaps = json.loads(LIFECYCLE_EVIDENCE.read_text())
    codes = {item["ts_code"] for item in gaps["gap_codes"]}
    expected = _formal_daily_dates(codes)
    observations = {code: {"dates": set(), "list_dates": set(), "delist_dates": set()} for code in codes}
    for file_entry in intake["files"]:
        path = ROOT / file_entry["path"]
        with path.open(encoding="utf-8-sig", newline="") as source:
            reader = csv.reader(source)
            header = next(reader, None)
            if header is None or len(header) != 37:
                raise ValueError(f"vendor schema invalid: {path.name}")
            for row in reader:
                if len(row) != 37:
                    raise ValueError(f"vendor row width invalid: {path.name}")
                code = f"{row[1].zfill(6)}.{'SH' if row[1].startswith('6') else 'SZ'}"
                if code in observations:
                    observations[code]["dates"].add(row[0].replace("-", ""))
                    observations[code]["list_dates"].add(row[35].replace("-", ""))
                    observations[code]["delist_dates"].add(row[36].replace("-", ""))
    details = []
    uncovered = 0
    errors = []
    for code in sorted(codes):
        observed = observations[code]
        missing = expected[code] - observed["dates"]
        uncovered += len(missing)
        if len(observed["list_dates"]) != 1 or len(observed["delist_dates"]) != 1:
            errors.append({"ts_code": code, "error": "inconsistent vendor lifecycle metadata"})
            continue
        list_date = next(iter(observed["list_dates"]))
        delist_date = next(iter(observed["delist_dates"]))
        if not list_date or not delist_date or list_date > min(expected[code]) or delist_date != max(expected[code]) or missing:
            errors.append({"ts_code": code, "error": "vendor lifecycle does not bound formal daily observations"})
        details.append({
            "ts_code": code,
            "list_date": list_date,
            "delist_date": delist_date,
            "vendor_observed_dates": len(observed["dates"]),
            "formal_daily_gap_dates": len(expected[code]),
            "uncovered_formal_daily_dates": len(missing),
        })
    status = "candidate_verified" if not errors and uncovered == 0 else "candidate_not_verified"
    evidence = {
        "status": status,
        "vendor_snapshot_id": intake["snapshot_id"],
        "vendor_package_sha256": intake["package_sha256"],
        "codes": details,
        "uncovered_formal_daily_dates": uncovered,
        "errors": errors,
        "formal_qualification_run": False,
        "usage_boundary": "candidate historical lifecycle evidence only; not yet part of a formal data package",
    }
    (VENDOR_ROOT / "security_lifecycle_candidate.json").write_text(json.dumps(evidence, indent=2))
    report = "# Vendor Security Lifecycle Candidate\n\n" + f"**Status:** {status}  \n**Formal qualification run:** No\n\n" + "| ts_code | list date | terminal date | vendor days | formal days | uncovered |\n|---|---|---|---:|---:|---:|\n" + "\n".join(
        f"| {item['ts_code']} | {item['list_date']} | {item['delist_date']} | {item['vendor_observed_dates']} | {item['formal_daily_gap_dates']} | {item['uncovered_formal_daily_dates']} |"
        for item in details
    ) + f"\n\n- Bound package hash: `{intake['package_sha256']}`\n- Errors: {errors}\n- This candidate is not automatically used by formal qualification.\n"
    (ROOT / "docs/verification/VENDOR_SECURITY_LIFECYCLE_CANDIDATE.md").write_text(report)
    return evidence


if __name__ == "__main__":
    result = run_verification()
    print(json.dumps({"status": result["status"], "uncovered_formal_daily_dates": result["uncovered_formal_daily_dates"]}))
    sys.exit(0 if result["status"] == "candidate_verified" else 1)
