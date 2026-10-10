"""Publish V2 formal data snapshot manifest and universe reference."""
import argparse
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from scripts.publish_v2_formal_snapshot import (
    publish_data_snapshot_manifest,
    publish_universe_reference,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_sha256(path: Path, expected: str):
    actual = _sha256(path)
    if actual != expected:
        raise ValueError(f"{path.name} hash mismatch: expected {expected}, got {actual}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--predecessor-manifest", type=Path, required=True)
    parser.add_argument("--coverage-manifest", type=Path, required=True)
    parser.add_argument("--coverage-sidecar", type=Path, required=True)
    parser.add_argument("--coverage-by-date", type=Path, required=True)
    parser.add_argument("--successor-manifest", type=Path, required=True)
    parser.add_argument("--sw2021-membership-manifest", type=Path, required=True)
    parser.add_argument("--sw2021-universe-candidate", type=Path, required=True)
    parser.add_argument("--vendor-manifest", type=Path, required=True)
    parser.add_argument("--vendor-lifecycle-candidate", type=Path, required=True)
    parser.add_argument("--scope-freeze", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=Path("data/pit"))
    args = parser.parse_args()
    
    # 1. Verify predecessor
    predecessor_hash = _sha256(args.predecessor_manifest)
    predecessor = json.loads(args.predecessor_manifest.read_text(encoding="utf-8"))
    expected_snapshot_hash = "da057716d4b4162b89fb89b7fd15864b4385d65cdee4e760a0743108cf1b135e"
    if predecessor["snapshot_hash"] != expected_snapshot_hash:
        raise ValueError(f"Predecessor snapshot_hash mismatch")
    
    # 2. Verify coverage
    _verify_sha256(args.coverage_manifest, "4e8b6163d4db11836e8a3aedc542d69ed6707bab566b6e0b16cb124d2b1e705f")
    sidecar_content = args.coverage_sidecar.read_text().strip()
    if sidecar_content != "4e8b6163d4db11836e8a3aedc542d69ed6707bab566b6e0b16cb124d2b1e705f":
        raise ValueError("Coverage sidecar mismatch")
    
    coverage = json.loads(args.coverage_manifest.read_text(encoding="utf-8"))
    if coverage["status"] != "coverage_published":
        raise ValueError("Coverage not published")
    
    build_completion = coverage["build_completion"]
    if build_completion["status"] != "completed":
        raise ValueError("Coverage build not completed")
    if build_completion["structural_validation"] != "passed":
        raise ValueError("Coverage structural validation failed")
    if coverage["structural_errors"]:
        raise ValueError("Coverage has structural errors")
    
    expected = coverage["expected_stock_days"]
    complete = coverage["complete_stock_days"]
    unavailable = coverage["unavailable_stock_days"]
    if complete + unavailable != expected:
        raise ValueError("Coverage arithmetic mismatch")
    
    _verify_sha256(args.coverage_by_date, "7571f482559ef597af89ef640896ca45c747ecfbfc469a28ad38f93f6b4313f3")
    
    # ponytail: read trade_date column, verify 2554 distinct dates
    import pyarrow.parquet as pq
    tbl = pq.read_table(
        args.coverage_by_date,
        columns=["trade_date", "expected_codes", "complete_codes", "unavailable_codes"],
    )
    by_date = tbl.to_pydict()
    dates = by_date["trade_date"]
    distinct_dates = sorted(set(dates))
    if len(distinct_dates) != 2554:
        raise ValueError(f"Expected 2554 distinct dates, got {len(distinct_dates)}")
    
    market_start = date(distinct_dates[0] // 10000, (distinct_dates[0] // 100) % 100, distinct_dates[0] % 100)
    market_end = date(distinct_dates[-1] // 10000, (distinct_dates[-1] // 100) % 100, distinct_dates[-1] % 100)
    
    if market_start != date(2016, 1, 4):
        raise ValueError(f"Market start mismatch: expected 2016-01-04, got {market_start}")
    if market_end != date(2026, 7, 10):
        raise ValueError(f"Market end mismatch: expected 2026-07-10, got {market_end}")
    if (
        sum(by_date["expected_codes"]) != expected
        or sum(by_date["complete_codes"]) != complete
        or sum(by_date["unavailable_codes"]) != unavailable
    ):
        raise ValueError("Coverage-by-date aggregate mismatch")
    
    # 3. Verify successor bindings
    successor = json.loads(args.successor_manifest.read_text(encoding="utf-8"))
    if successor["status"] != "availability_bounded_qualified":
        raise ValueError("Successor status mismatch")
    if successor["predecessor_manifest_sha256"] != predecessor_hash:
        raise ValueError("Successor predecessor manifest hash mismatch")
    if coverage["input_manifest_content_hashes"]["qualification_manifest.json"] != predecessor_hash:
        raise ValueError("Coverage predecessor manifest hash mismatch")
    if successor["predecessor_snapshot_hash"] != expected_snapshot_hash:
        raise ValueError("Successor predecessor_snapshot_hash mismatch")
    if successor["coverage_template_hash"] != "17a1be7ea3547e7a3cc85ea25e63b43aa2ddb4e8ced50c699db5a1bdd9cec9f0":
        raise ValueError("Successor template_hash mismatch")
    if successor["predecessor_scope_hash"] != "35d996036cc04179":
        raise ValueError("Successor scope_hash mismatch")
    if coverage["input_scope_hash"] != "35d996036cc04179":
        raise ValueError("Coverage scope_hash mismatch")
    if coverage["input_template_hash"] != "17a1be7ea3547e7a3cc85ea25e63b43aa2ddb4e8ced50c699db5a1bdd9cec9f0":
        raise ValueError("Coverage template_hash mismatch")
    if coverage["input_snapshot_hash"] != expected_snapshot_hash:
        raise ValueError("Coverage snapshot_hash mismatch")
    if (
        predecessor["data_requirements_hash"] != coverage["input_data_requirements_hash"]
        or successor["predecessor_data_requirements_hash"] != predecessor["data_requirements_hash"]
    ):
        raise ValueError("Data requirements hash mismatch")
    if (
        predecessor["template_hash"] != coverage["input_template_hash"]
        or successor["predecessor_template_hash"] != predecessor["template_hash"]
    ):
        raise ValueError("Template hash mismatch")
    if (
        predecessor["scope_hash"] != coverage["input_scope_hash"]
        or successor["predecessor_scope_hash"] != predecessor["scope_hash"]
    ):
        raise ValueError("Scope hash mismatch")
    if _sha256(args.scope_freeze) != successor["scope_freeze_sha256"]:
        raise ValueError("Scope-freeze document hash mismatch")
    
    # 4. Verify source manifests
    sw2021_membership_sha = _sha256(args.sw2021_membership_manifest)
    sw2021_universe_sha = _sha256(args.sw2021_universe_candidate)
    vendor_manifest_sha = _sha256(args.vendor_manifest)
    vendor_lifecycle_sha = _sha256(args.vendor_lifecycle_candidate)
    
    expected_hashes = coverage["input_manifest_content_hashes"]
    if sw2021_membership_sha != expected_hashes["sw2021_membership_manifest.json"]:
        raise ValueError("SW2021 membership manifest hash mismatch")
    if sw2021_universe_sha != expected_hashes["sw2021_universe_candidate.json"]:
        raise ValueError("SW2021 universe candidate hash mismatch")
    if vendor_manifest_sha != expected_hashes["vendor_snapshot_manifest.json"]:
        raise ValueError("Vendor manifest hash mismatch")
    if vendor_lifecycle_sha != expected_hashes["vendor_lifecycle_candidate.json"]:
        raise ValueError("Vendor lifecycle candidate hash mismatch")
    
    # 5. Read universe definition hash
    universe_candidate = json.loads(args.sw2021_universe_candidate.read_text(encoding="utf-8"))
    universe_definition_hash = universe_candidate["universe_definition_hash"]
    
    # 6. Publish universe reference
    uref_dir = args.output_root / "universe_references"
    uref_dir.mkdir(parents=True, exist_ok=True)
    
    uref_result = publish_universe_reference(
        universe_reference_id="uref_traderlens_v2_shsz_sw2021_pit_001",
        sw2021_membership_manifest_sha256=sw2021_membership_sha,
        sw2021_universe_candidate_sha256=sw2021_universe_sha,
        universe_definition_hash=universe_definition_hash,
        source_taxonomy="SW2021",
        output_dir=uref_dir,
    )
    print(json.dumps({"universe_reference": uref_result}))
    
    # 7. Publish data snapshot manifest
    ds_dir = args.output_root / "data_snapshot_manifests"
    ds_dir.mkdir(parents=True, exist_ok=True)
    
    ds_result = publish_data_snapshot_manifest(
        snapshot_id="ds_traderlens_v2_shsz_pit_001",
        provider="mixed_vendor_tushare",
        market_data_start=market_start,
        market_data_end=market_end,
        semantic_hash=expected_snapshot_hash,
        universe_reference_ids=("uref_traderlens_v2_shsz_sw2021_pit_001",),
        coverage_package_id="695245b51005e50b",
        coverage_manifest_sha256="4e8b6163d4db11836e8a3aedc542d69ed6707bab566b6e0b16cb124d2b1e705f",
        expected_stock_days=expected,
        complete_stock_days=complete,
        unavailable_stock_days=unavailable,
        field_missing_counts=coverage["field_missing_counts"],
        source_manifest_hashes={
            "sw2021_membership_manifest.json": sw2021_membership_sha,
            "sw2021_universe_candidate.json": sw2021_universe_sha,
            "vendor_lifecycle_candidate.json": vendor_lifecycle_sha,
            "vendor_snapshot_manifest.json": vendor_manifest_sha,
        },
        output_dir=ds_dir,
    )
    print(json.dumps({"data_snapshot": ds_result}))


if __name__ == "__main__":
    main()
