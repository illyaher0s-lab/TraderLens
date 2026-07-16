#!/usr/bin/env python3
"""Verify PIT membership snapshot integrity."""

import hashlib
import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq


# Expected bindings
SNAPSHOT_ID = "pit_membership_shsz_sw2021_2024-12-31_004"
SNAPSHOT_ID_001_RETIRED = "pit_membership_shsz_sw2021_2024-12-31_001"
SNAPSHOT_ID_002_INVALID = "pit_membership_shsz_sw2021_2024-12-31_002"
SNAPSHOT_ID_003_INVALID = "pit_membership_shsz_sw2021_2024-12-31_003"

EXPECTED_FORMAL_DATA_SNAPSHOT_ID = "tushare_stock_basic_SW2021_membership_20241231"
EXPECTED_FORMAL_DATA_SEMANTIC_HASH = "b7e57ef8a8e67be10c36d479adfdc4766b2c64b5dcd91b82a83f1cbedb8b3ac8"
EXPECTED_UNIVERSE_REFERENCE_ID = "relative_strength_rotation_shsz_sw2021_v2::v2_shsz_sw2021_pit_12m::867a47eeece1c0d208c591f35b5ca31d663ccda183c8721eef803483921238b6"


def sha256_file(path: Path) -> str:
    """Compute SHA-256 of file."""
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def canonical_json_hash(obj: dict, exclude_keys: set[str]) -> str:
    """Compute SHA-256 of canonical JSON."""
    filtered = {k: v for k, v in obj.items() if k not in exclude_keys}
    canonical = json.dumps(filtered, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def verify_snapshot(repo_root: Path, snapshot_id: str, snapshots_root: Path | None = None) -> dict:
    """Verify formal PIT membership snapshot integrity.
    
    Args:
        repo_root: Repository root path
        snapshot_id: Snapshot ID to verify
        snapshots_root: Optional override for snapshots directory (for test fixtures)
    
    Returns:
        verification result dict
    """
    
    # Check if verifying retired _001 or invalid _002/_003
    base_dir = snapshots_root or (repo_root / "data/pit/pit_membership_snapshots")
    
    if snapshot_id == SNAPSHOT_ID_001_RETIRED:
        snapshot_dir = base_dir / snapshot_id
        if snapshot_dir.exists():
            return {
                "status": "retired_unaccepted",
                "snapshot_id": snapshot_id,
                "message": f"{snapshot_id} is permanently retired and unaccepted audit evidence. It must not be used for B6/OOS or any production workflow.",
                "reason": "Contained SW2014+SW2021 mixed taxonomy records and lacked source contract proving include_delisted",
            }
        else:
            return {"status": "missing", "errors": [f"Retired snapshot directory not found: {snapshot_dir}"]}
    
    if snapshot_id == SNAPSHOT_ID_002_INVALID:
        snapshot_dir = base_dir / snapshot_id
        if snapshot_dir.exists():
            return {
                "status": "unaccepted_invalid_publication",
                "snapshot_id": snapshot_id,
                "message": f"{snapshot_id} is unaccepted (applied date filtering to source records, violating source retention principle)",
                "reason": "Applied DATE_POLICY_MIN filter during publication, discarding valid source records",
            }
        else:
            return {"status": "missing", "errors": [f"Invalid snapshot directory not found: {snapshot_dir}"]}
    
    if snapshot_id == SNAPSHOT_ID_003_INVALID:
        snapshot_dir = base_dir / snapshot_id
        if snapshot_dir.exists():
            return {
                "status": "unaccepted_invalid_publication",
                "snapshot_id": snapshot_id,
                "message": f"{snapshot_id} is unaccepted (missing source_partition_audit and source_to_record_mapping_hash)",
                "reason": "Lacks source-to-record provenance binding and partition audit trail",
            }
        else:
            return {"status": "missing", "errors": [f"Invalid snapshot directory not found: {snapshot_dir}"]}
    
    
    
    snapshot_dir = base_dir / snapshot_id
    
    errors = []
    warnings = []
    
    # 1. Check directory exists
    if not snapshot_dir.exists():
        return {"status": "missing", "errors": [f"Snapshot directory not found: {snapshot_dir}"]}
    
    # 2. Check required files
    required_files = ["manifest.json", "manifest.json.sha256", "records.parquet", "records.parquet.sha256"]
    for fname in required_files:
        if not (snapshot_dir / fname).exists():
            errors.append(f"Missing required file: {fname}")
    
    if errors:
        return {"status": "incomplete", "errors": errors}
    
    # 3. Verify manifest sidecar
    manifest_path = snapshot_dir / "manifest.json"
    manifest_sidecar_path = snapshot_dir / "manifest.json.sha256"
    
    actual_manifest_hash = sha256_file(manifest_path)
    expected_manifest_hash = manifest_sidecar_path.read_text(encoding="utf-8").split()[0]
    
    if actual_manifest_hash != expected_manifest_hash:
        errors.append(f"Manifest sidecar mismatch: {actual_manifest_hash} != {expected_manifest_hash}")
        return {"status": "tampered", "errors": errors}
    
    # 4. Load manifest
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    
    # 5. Verify manifest structure
    required_manifest_fields = [
        "snapshot_id", "snapshot_date", "universe_rule_type", "membership_source",
        "vendor_scope_disclosure",
        "include_delisted", "frozen", "quality_status", "gaps", "record_count",
        "formal_data_snapshot_id", "formal_data_semantic_hash", "universe_reference_id",
        "records_parquet_sha256", "canonical_content_hash", "schema_version",
        "interval_semantics", "not_authorized_for_b6_oos_gate_promotion_signal",
        "source_partition_audit",  # Required for _004+
    ]
    
    for field in required_manifest_fields:
        if field not in manifest:
            errors.append(f"Missing manifest field: {field}")
    
    if errors:
        return {"status": "invalid_manifest", "errors": errors}
    
    # 6. Verify snapshot_id matches requested
    if manifest["snapshot_id"] != snapshot_id:
        errors.append(f"snapshot_id mismatch: {manifest['snapshot_id']} != {snapshot_id}")
    
    # 7. Verify bindings (only for production snapshot_id)
    if snapshot_id == SNAPSHOT_ID:
        if manifest["formal_data_snapshot_id"] != EXPECTED_FORMAL_DATA_SNAPSHOT_ID:
            errors.append(f"formal_data_snapshot_id mismatch: {manifest['formal_data_snapshot_id']}")
        
        if manifest["formal_data_semantic_hash"] != EXPECTED_FORMAL_DATA_SEMANTIC_HASH:
            errors.append(f"formal_data_semantic_hash mismatch: {manifest['formal_data_semantic_hash']}")
        
        if manifest["universe_reference_id"] != EXPECTED_UNIVERSE_REFERENCE_ID:
            errors.append(f"universe_reference_id mismatch: {manifest['universe_reference_id']}")
    
    # 8. Verify vendor_scope_disclosure structure
    vendor_disclosure = manifest.get("vendor_scope_disclosure", {})
    
    if not isinstance(vendor_disclosure, dict):
        errors.append("vendor_scope_disclosure must be a dict")
    elif "historical_membership_scope" not in vendor_disclosure:
        errors.append("vendor_scope_disclosure must contain 'historical_membership_scope' field")
    elif "disclosure_text" not in vendor_disclosure:
        errors.append("vendor_scope_disclosure must contain 'disclosure_text' field")
    
    # 8c. Verify source_to_record_mapping_hash is present and non-null
    mapping_hash = manifest.get("source_to_record_mapping_hash")
    if mapping_hash is None:
        return {
            "status": "unaccepted_invalid_publication",
            "snapshot_id": snapshot_id,
            "message": f"{snapshot_id} is unaccepted (null source_to_record_mapping_hash)",
            "reason": "Lacks source-to-record provenance binding",
        }
    
    # 8d. Verify all audit entries have non-null source_manifest_sha256
    audit = manifest.get("source_partition_audit", [])
    for entry in audit:
        if entry.get("source_manifest_sha256") is None:
            return {
                "status": "unaccepted_invalid_publication",
                "snapshot_id": snapshot_id,
                "message": f"{snapshot_id} is unaccepted (null source_manifest_sha256 in audit entry {entry.get('partition_name')})",
                "reason": "Audit entry lacks source partition hash",
            }
    
    
    # 9. Verify records parquet sidecar
    records_path = snapshot_dir / "records.parquet"
    records_sidecar_path = snapshot_dir / "records.parquet.sha256"
    
    actual_records_hash = sha256_file(records_path)
    expected_records_hash = records_sidecar_path.read_text(encoding="utf-8").split()[0]
    
    if actual_records_hash != expected_records_hash:
        errors.append(f"Records sidecar mismatch: {actual_records_hash} != {expected_records_hash}")
    
    if actual_records_hash != manifest["records_parquet_sha256"]:
        errors.append(f"Records hash in manifest mismatch: {actual_records_hash} != {manifest['records_parquet_sha256']}")
    
    # 10. Verify records parquet structure
    table = pq.read_table(records_path)
    df = table.to_pandas()
    
    expected_columns = {"symbol", "effective_from", "effective_to", "source", "snapshot_id"}
    actual_columns = set(df.columns)
    
    if actual_columns != expected_columns:
        errors.append(f"Records columns mismatch: {actual_columns} != {expected_columns}")
    
    # 11. Verify record count
    if len(df) != manifest["record_count"]:
        errors.append(f"Record count mismatch: {len(df)} != {manifest['record_count']}")
    
    # 12. Verify all records have correct snapshot_id
    wrong_snapshot_ids = df[df["snapshot_id"] != snapshot_id]
    if len(wrong_snapshot_ids) > 0:
        errors.append(f"Found {len(wrong_snapshot_ids)} records with wrong snapshot_id")
    
    # 13. Verify canonical content hash
    exclude_keys = {"canonical_content_hash", "manifest_published_at"}
    recomputed_canonical_hash = canonical_json_hash(manifest, exclude_keys)
    
    if recomputed_canonical_hash != manifest["canonical_content_hash"]:
        errors.append(f"Canonical content hash mismatch: {recomputed_canonical_hash} != {manifest['canonical_content_hash']}")
    
    # 14. Verify interval semantics
    snapshot_date = date.fromisoformat(manifest["snapshot_date"])
    
    invalid_intervals = df[
        (df["effective_to"].notna()) &
        (df["effective_to"] < df["effective_from"])
    ]
    if len(invalid_intervals) > 0:
        errors.append(f"Found {len(invalid_intervals)} invalid intervals (effective_to < effective_from)")
    
    # 15. Verify horizon
    future_starts = df[df["effective_from"] > snapshot_date]
    if len(future_starts) > 0:
        errors.append(f"Found {len(future_starts)} records with effective_from > snapshot_date")
    
    future_ends = df[(df["effective_to"].notna()) & (df["effective_to"] > snapshot_date)]
    if len(future_ends) > 0:
        errors.append(f"Found {len(future_ends)} records with effective_to > snapshot_date")
    
    # 16. Check for duplicates
    duplicates = df[df.duplicated(subset=["symbol", "effective_from", "effective_to", "snapshot_id"], keep=False)]
    if len(duplicates) > 0:
        errors.append(f"Found {len(duplicates)} duplicate records")
    
    # 17. Verify include_delisted evidence (removed check)
    delisted_count = df["effective_to"].notna().sum()
    active_count = df["effective_to"].isna().sum()
    
    # include_delisted is proved by source-record retention, not by delisted record existence
    
    if active_count == 0:
        warnings.append("No active records found (suspicious)")
    
    if errors:
        return {
            "status": "failed",
            "errors": errors,
            "warnings": warnings,
        }
    
    return {
        "status": "verified",
        "snapshot_id": snapshot_id,
        "snapshot_date": manifest["snapshot_date"],
        "record_count": len(df),
        "unique_symbols": df["symbol"].nunique(),
        "delisted_count": delisted_count,
        "active_count": active_count,
        "canonical_content_hash": manifest["canonical_content_hash"],
        "warnings": warnings,
    }


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Verify PIT membership snapshot")
    parser.add_argument("snapshot_id", nargs="?", default=SNAPSHOT_ID, help="Snapshot ID to verify")
    parser.add_argument("--snapshots-root", type=Path, help="Override snapshots root directory")
    args = parser.parse_args()
    
    repo_root = Path(__file__).parent.parent
    
    print(f"Verifying PIT membership snapshot: {args.snapshot_id}")
    print()
    
    result = verify_snapshot(repo_root, args.snapshot_id, snapshots_root=args.snapshots_root)
    
    print("=" * 60)
    print(f"Verification status: {result['status']}")
    
    if result["status"] == "retired_unaccepted":
        print(f"\n✗ {result['message']}")
        print(f"Reason: {result['reason']}")
        print("\nThis snapshot must NOT be used. It is preserved only as audit evidence.")
        return 2  # Distinct exit code for retired
    
    if result["status"] == "unaccepted_invalid_publication":
        print(f"\n✗ {result['message']}")
        print(f"Reason: {result['reason']}")
        print("\nThis snapshot must NOT be used. It is preserved only as audit evidence.")
        return 3  # Distinct exit code for invalid publication
    
    if result["status"] == "verified":
        print(f"Snapshot ID: {result['snapshot_id']}")
        print(f"Snapshot date: {result['snapshot_date']}")
        print(f"Record count: {result['record_count']}")
        print(f"Unique symbols: {result['unique_symbols']}")
        print(f"Delisted records: {result['delisted_count']}")
        print(f"Active records: {result['active_count']}")
        print(f"Canonical content hash: {result['canonical_content_hash']}")
        
        if result.get("warnings"):
            print("\nWarnings:")
            for w in result["warnings"]:
                print(f"  ⚠ {w}")
        
        print("\n✓ Verification passed")
        return 0
    else:
        print(f"\n✗ Verification failed")
        
        if result.get("errors"):
            print("\nErrors:")
            for e in result["errors"]:
                print(f"  ✗ {e}")
        
        return 1


if __name__ == "__main__":
    sys.exit(main())
