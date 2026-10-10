"""Publish bounded, qualified lifecycle metadata without changing its sources."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _gap_dates(gap: dict, formal_root: Path) -> dict[str, set[str]]:
    result = {}
    for item in gap["gap_codes"]:
        dates = set()
        for partition in sorted((formal_root / "daily").glob("trade_date=*/part.parquet")):
            date = partition.parent.name.split("=", 1)[1]
            import pandas as pd
            values = set(pd.read_parquet(partition, columns=["ts_code"])["ts_code"].dropna())
            if item["ts_code"] in values:
                dates.add(date)
        result[item["ts_code"]] = dates
    return result


def qualify(*, formal: Path, vendor: Path, vendor_manifest: Path, candidate: Path, gap_audit: Path, output_root: Path) -> dict:
    formal = Path(formal).resolve()
    vendor = Path(vendor).resolve()
    vendor_manifest = Path(vendor_manifest).resolve()
    candidate = Path(candidate).resolve()
    gap_audit = Path(gap_audit).resolve()
    intake = json.loads(vendor_manifest.read_text(encoding="utf-8"))
    evidence = json.loads(candidate.read_text(encoding="utf-8"))
    gap = json.loads(gap_audit.read_text(encoding="utf-8"))
    if evidence.get("status") != "candidate_verified" or evidence.get("uncovered_formal_daily_dates") != 0 or evidence.get("errors") != []:
        raise ValueError("candidate evidence is not a clean RED boundary")
    audit_items = gap.get("gap_codes", [])
    expected_codes = {item["ts_code"] for item in audit_items}
    actual_codes = {item["ts_code"] for item in evidence.get("codes", [])}
    if actual_codes != expected_codes:
        raise ValueError("code set mismatch")
    if evidence.get("vendor_snapshot_id") != intake.get("snapshot_id"):
        raise ValueError("vendor snapshot mismatch")
    package_hash = intake.get("package_sha256")
    if not package_hash or evidence.get("vendor_package_sha256") != package_hash:
        raise ValueError("vendor package hash mismatch")
    vendor_files = []
    for item in intake.get("files", []):
        path = vendor / item["path"].replace("\\\\", "/")
        if "sha256" in item:
            if not path.is_file() or _sha(path) != item["sha256"]:
                raise ValueError("vendor file hash mismatch")
        elif not path.is_file():
            raise ValueError("vendor file missing")
        vendor_files.append(path)
    expected_dates = _gap_dates(gap, formal)
    observations = {code: {"dates": set(), "list": set(), "delist": set()} for code in expected_codes}
    for path in vendor_files:
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.reader(stream)
            header = next(reader, None)
            if header is None or len(header) != 37:
                raise ValueError("vendor CSV must have exactly 37 columns")
            if (header[0], header[1], header[35], header[36]) != ("日期", "代码", "上市时间", "退市时间"):
                raise ValueError("vendor CSV lifecycle header mismatch")
            for row in reader:
                if len(row) != 37:
                    raise ValueError("vendor CSV row must have exactly 37 columns")
                code_value = row[1]
                code = f"{code_value.zfill(6)}.{'SH' if code_value.startswith('6') else 'SZ'}"
                if code not in observations:
                    continue
                observations[code]["dates"].add(row[0].replace("-", ""))
                observations[code]["list"].add(row[35].replace("-", ""))
                observations[code]["delist"].add(row[36].replace("-", ""))
    qualified = []
    for item in audit_items:
        code = item["ts_code"]
        observed = observations[code]
        if observed["dates"] != expected_dates[code]:
            raise ValueError(f"{code}: formal daily gap dates not fully covered")
        if len(observed["list"]) != 1 or len(observed["delist"]) != 1:
            raise ValueError(f"{code}: lifecycle dates are not unique")
        list_date = next(iter(observed["list"]))
        delist_date = next(iter(observed["delist"]))
        if list_date > min(expected_dates[code]) or delist_date != max(expected_dates[code]):
            raise ValueError(f"{code}: lifecycle dates do not bound observations")
        if item.get("first_date") != min(expected_dates[code]) or item.get("last_date") != max(expected_dates[code]) or item.get("total_days") != len(expected_dates[code]):
            raise ValueError(f"{code}: gap audit range mismatch")
        qualified.append({"ts_code": code, "list_date": list_date, "delist_date": delist_date, "gap_dates": sorted(expected_dates[code])})
    semantic = {
        "schema_version": "bounded_vendor_lifecycle_successor.v1",
        "qualification_status": "bounded_qualified_vendor_lifecycle",
        "source_kind": "vendor_lifecycle_evidence_not_official_source",
        "vendor_manifest_sha256": _sha(vendor_manifest),
        "vendor_package_sha256": package_hash,
        "candidate_sha256": _sha(candidate),
        "gap_audit_sha256": _sha(gap_audit),
        "checked_trade_days": gap["checked_trade_days"],
        "codes": qualified,
        "uncovered_formal_daily_dates": 0,
        "errors": [],
    }
    successor_id = hashlib.sha256(_canonical(semantic)).hexdigest()[:16]
    payload = {**semantic, "successor_id": successor_id}
    target = Path(output_root).resolve() / successor_id
    if target.exists():
        raise ValueError("successor already exists")
    target.mkdir(parents=True)
    manifest = target / "manifest.json"
    manifest.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    (target / "manifest.json.sha256").write_text(_sha(manifest), encoding="utf-8")
    return {"status": "published", "qualification_status": payload["qualification_status"], "successor_id": successor_id}