"""Verify a published V2 coverage artifact without re-scanning daily partitions."""
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
QUALIFICATION_ID = "de3fed9c3819d25c"
OLD_CONTENT_HASHES = {
    "old_invalid_manifest": "3d0333042dcafa0214d31627275266d31f7feb4560f7e63ca1a8693393d8dcbb",
    "qualification_manifest": "1cdb48bf9b78b7664513bd3afa7ac4466483529dedcf78bd996d1846b7f2087d",
    "placeholder_status": "74a5d00f38d31f348d56a03e11d744c763ffd55f802eafb1fdef767d51c861f9",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bound_manifest_hashes() -> dict[str, str]:
    formal = ROOT / "data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal"
    vendor = ROOT / "data/pit/vendor_daily_snapshot/vendor_8e64285ae2fdea2e"
    return {
        "qualification_manifest.json": _sha256(ROOT / "data/pit/formal_packages" / QUALIFICATION_ID / "manifest.json"),
        "sw2021_membership_manifest.json": _sha256(formal / "sw_l1_membership/manifest.json"),
        "sw2021_universe_candidate.json": _sha256(formal / "sw_l1_membership/sw2021_universe_candidate.json"),
        "vendor_lifecycle_candidate.json": _sha256(vendor / "security_lifecycle_candidate.json"),
        "vendor_snapshot_manifest.json": _sha256(vendor / "manifest.json"),
    }


def _top_ten_is_sorted(rows) -> bool:
    return list(rows) == sorted(rows, key=lambda row: (-row[1], row[0]))


def verify_coverage_package(coverage_hash: str) -> dict:
    """Validate recorded integrity and bindings; it does not infer scan execution."""
    from scripts.build_v2_coverage import COVERAGE_SCHEMA, _algorithm_hash

    base = ROOT / "data/pit/coverage_packages" / coverage_hash
    manifest_path = base / "coverage_manifest.json"
    if not manifest_path.exists():
        return {"status": "not_found", "coverage_hash": coverage_hash}
    manifest = json.loads(manifest_path.read_text())
    qualification = json.loads((ROOT / "data/pit/formal_packages" / QUALIFICATION_ID / "manifest.json").read_text())
    unavailable = pd.read_parquet(base / "unavailable_security_dates.parquet")
    by_date = pd.read_parquet(base / "coverage_by_date.parquet")
    by_code = pd.read_parquet(base / "coverage_by_code.parquet")
    checks = {
        "manifest_hash": (base / "coverage_manifest.json.sha256").exists()
        and (base / "coverage_manifest.json.sha256").read_text().strip() == _sha256(manifest_path),
        "artifact_hashes": (
            _sha256(base / "coverage_by_date.parquet") == manifest.get("coverage_by_date_hash")
            and _sha256(base / "coverage_by_code.parquet") == manifest.get("coverage_by_code_hash")
            and _sha256(base / "unavailable_security_dates.parquet") == manifest.get("unavailable_parquet_hash")
        ),
        "binding": (
            manifest.get("input_qualification_package_id") == QUALIFICATION_ID
            and all(manifest.get(f"input_{key}") == qualification.get(key) for key in (
                "scope_hash", "template_hash", "data_requirements_hash", "snapshot_hash"
            ))
            and manifest.get("algorithm_hash") == _algorithm_hash()
            and manifest.get("coverage_schema") == COVERAGE_SCHEMA
            and manifest.get("input_manifest_content_hashes") == _bound_manifest_hashes()
        ),
        "expected_matches_qualification": manifest.get("expected_stock_days") == qualification.get("expected_stock_days_after_market_scope"),
        "algebraic_invariant": manifest.get("complete_stock_days", 0) + manifest.get("unavailable_stock_days", 0) == manifest.get("expected_stock_days"),
        "unavailable_row_count": len(unavailable) == manifest.get("unavailable_stock_days"),
        "field_counts_match": dict(sorted(Counter(field for fields in unavailable["missing_fields"] for field in fields).items())) == manifest.get("field_missing_counts"),
        "by_date_aggregates": all(by_date[column].sum() == manifest[key] for column, key in (
            ("expected_codes", "expected_stock_days"), ("complete_codes", "complete_stock_days"),
            ("unavailable_codes", "unavailable_stock_days"),
        )),
        "by_code_aggregates": all(by_code[column].sum() == manifest[key] for column, key in (
            ("expected_days", "expected_stock_days"), ("complete_days", "complete_stock_days"),
            ("unavailable_days", "unavailable_stock_days"),
        )),
        "fixed_ordering": (
            all(list(fields) == sorted(fields) for fields in unavailable["missing_fields"])
            and _top_ten_is_sorted(manifest.get("top_10_dates_by_unavailable", []))
            and _top_ten_is_sorted(manifest.get("top_10_codes_by_unavailable", []))
        ),
        "build_completed": manifest.get("build_completion") == {
            "status": "completed",
            "scanned_trade_days": qualification.get("checked_trade_days"),
            "required_partition_reads": qualification.get("checked_trade_days") * 4,
            "structural_validation": "passed",
        } and manifest.get("structural_errors") == [],
        "old_content_unchanged": {
            "old_invalid_manifest": _sha256(ROOT / "data/pit/formal_packages/35d996036cc04179/manifest.json"),
            "qualification_manifest": _sha256(ROOT / "data/pit/formal_packages/de3fed9c3819d25c/manifest.json"),
            "placeholder_status": _sha256(ROOT / "data/pit/coverage_packages/de3fed9c3819d25c/STATUS_INVALID.txt"),
        } == OLD_CONTENT_HASHES,
    }
    return {
        "status": "verified" if all(checks.values()) else "failed",
        "coverage_hash": coverage_hash,
        "expected_stock_days": manifest.get("expected_stock_days"),
        "complete_stock_days": manifest.get("complete_stock_days"),
        "unavailable_stock_days": manifest.get("unavailable_stock_days"),
        "checks": checks,
    }


if __name__ == "__main__":
    package_id = sys.argv[1] if len(sys.argv) == 2 else ""
    result = verify_coverage_package(package_id)
    print(json.dumps(result, indent=2, sort_keys=True))
    sys.exit(0 if result["status"] == "verified" else 1)
