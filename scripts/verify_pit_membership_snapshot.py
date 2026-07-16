"""Verify formal PIT membership snapshot integrity.

Independent verifier: checks manifest, records parquet, sidecars, bindings,
and structural invariants.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import date
from pathlib import Path

import pyarrow.parquet as pq


SNAPSHOT_ID_001_RETIRED = "pims_traderlens_v2_shsz_sw2021_pit_001"  # Permanently retired/unaccepted
SNAPSHOT_ID_002_INVALID = "pims_traderlens_v2_shsz_sw2021_pit_002"  # Invalid publication
SNAPSHOT_ID_003_INVALID = "pims_traderlens_v2_shsz_sw2021_pit_003"  # Invalid: missing source_partition_audit
SNAPSHOT_ID = "pims_traderlens_v2_shsz_sw2021_pit_004"  # Current prospective ID
EXPECTED_FORMAL_DATA_SNAPSHOT_ID = "ds_traderlens_v2_shsz_pit_001"
EXPECTED_FORMAL_DATA_SEMANTIC_HASH = "da057716d4b4162b89fb89b7fd15864b4385d65cdee4e760a0743108cf1b135e"
EXPECTED_UNIVERSE_REFERENCE_ID = "uref_traderlens_v2_shsz_sw2021_pit_001"


def sha256_file(path: Path) -> str:
    """Compute SHA-256 of file bytes."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def canonical_json_hash(obj: dict, exclude_keys: set[str]) -> str:
    """Compute SHA-256 of canonical JSON."""
    filtered = {k: v for k, v in obj.items() if k not in exclude_keys}
    canonical = json.dumps(filtered, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def verify_snapshot(repo_root: Path, snapshot_id: str = SNAPSHOT_ID) -> dict:
    """Verify formal PIT membership snapshot integrity.
    
    Args:
        snapshot_id: Snapshot ID to verify (default: _002)
    
    Returns:
        verification result dict
    """
    
    # Check if verifying retired _001 or invalid _002/_003
    if snapshot_id == SNAPSHOT_ID_001_RETIRED:
        snapshot_dir = repo_root / "data/pit/pit_membership_snapshots" / snapshot_id
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
        snapshot_dir = repo_root / "data/pit/pit_membership_snapshots" / snapshot_id
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
        snapshot_dir = repo_root / "data/pit/pit_membership_snapshots" / snapshot_id
        if snapshot_dir.exists():
            return {
                "status": "unaccepted_invalid_publication",
                "snapshot_id": snapshot_id,
                "message": f"{snapshot_id} is unaccepted (missing source_partition_audit and source_to_record_mapping_hash)",
                "reason": "Lacks source-to-record provenance binding and partition audit trail",
            }
        else:
            return {"status": "missing", "errors": [f"Invalid snapshot directory not found: {snapshot_dir}"]}
    
    
    
    snapshot_dir = repo_root / "data/pit/pit_membership_snapshots" / snapshot_id
    
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
    
    # 6. Verify snapshot_id
    if manifest["snapshot_id"] != SNAPSHOT_ID:
        errors.append(f"snapshot_id mismatch: {manifest['snapshot_id']} != {SNAPSHOT_ID}")
    
    # 7. Verify bindings
    if manifest["formal_data_snapshot_id"] != EXPECTED_FORMAL_DATA_SNAPSHOT_ID:
        errors.append(f"formal_data_snapshot_id mismatch: {manifest['formal_data_snapshot_id']}")
    
    if manifest["formal_data_semantic_hash"] != EXPECTED_FORMAL_DATA_SEMANTIC_HASH:
        errors.append(f"formal_data_semantic_hash mismatch: {manifest['formal_data_semantic_hash']}")
    
    if manifest["universe_reference_id"] != EXPECTED_UNIVERSE_REFERENCE_ID:
        errors.append(f"universe_reference_id mismatch: {manifest['universe_reference_id']}")
    
    # 8. Verify contract fields
    if manifest["universe_rule_type"] != "point_in_time_membership":
        errors.append(f"Invalid universe_rule_type: {manifest['universe_rule_type']}")
    
    if manifest["include_delisted"] is not True:
        errors.append(f"include_delisted must be True, got: {manifest['include_delisted']}")
    
    if manifest["frozen"] is not True:
        errors.append(f"frozen must be True, got: {manifest['frozen']}")
    
    if manifest["not_authorized_for_b6_oos_gate_promotion_signal"] is not True:
        errors.append("not_authorized_for_b6_oos_gate_promotion_signal must be True")
    
    # 8b. Verify vendor_scope_disclosure structure (Task 3)
    vendor_disclosure = manifest.get("vendor_scope_disclosure")
    if not isinstance(vendor_disclosure, dict):
        errors.append(f"vendor_scope_disclosure must be dict, got: {type(vendor_disclosure)}")
    elif vendor_disclosure.get("historical_membership_scope") != "vendor_provided_unverified":
        errors.append(f"vendor_scope_disclosure.historical_membership_scope must be 'vendor_provided_unverified', got: {vendor_disclosure.get('historical_membership_scope')}")
    elif "disclosure_text" not in vendor_disclosure:
        errors.append("vendor_scope_disclosure must contain 'disclosure_text' field")
    
    
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
    wrong_snapshot_ids = df[df["snapshot_id"] != SNAPSHOT_ID]
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
    
    # 17. Verify include_delisted evidence
    delisted_count = df["effective_to"].notna().sum()
    active_count = df["effective_to"].isna().sum()
    
    if delisted_count == 0:
        errors.append("No delisted records found, cannot prove include_delisted=True")
    
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
        "snapshot_id": SNAPSHOT_ID,
        "snapshot_date": manifest["snapshot_date"],
        "record_count": len(df),
        "unique_symbols": df["symbol"].nunique(),
        "delisted_count": delisted_count,
        "active_count": active_count,
        "canonical_content_hash": manifest["canonical_content_hash"],
        "warnings": warnings,
    }


def main():
    repo_root = Path(__file__).parent.parent
    
    import sys
    snapshot_id = sys.argv[1] if len(sys.argv) > 1 else SNAPSHOT_ID
    
    print(f"Verifying PIT membership snapshot: {snapshot_id}")
    print()
    
    result = verify_snapshot(repo_root, snapshot_id)
    
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
        
        if result.get("warnings"):
            print("\nWarnings:")
            for w in result["warnings"]:
                print(f"  ⚠ {w}")
        
        return 1


if __name__ == "__main__":
    sys.exit(main())
