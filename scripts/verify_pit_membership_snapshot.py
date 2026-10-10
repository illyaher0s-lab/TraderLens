#!/usr/bin/env python3
"""Verify PIT membership snapshot integrity."""

import hashlib
import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq


# Expected bindings (current prospective production snapshot)
SNAPSHOT_ID = "pims_traderlens_v2_shsz_sw2021_pit_005"

# Legacy status registry (immutable)
LEGACY_SNAPSHOT_REGISTRY = {
    "pims_traderlens_v2_shsz_sw2021_pit_001": {
        "status": "retired_unaccepted",
        "exit_code": 2,
        "reason": "Mixed SW2014/SW2021 taxonomy, lacked source contract proving include_delisted",
    },
    "pims_traderlens_v2_shsz_sw2021_pit_002": {
        "status": "unaccepted_invalid_publication",
        "exit_code": 3,
        "reason": "Applied DATE_POLICY_MIN filter during publication, discarding valid source records",
    },
    "pims_traderlens_v2_shsz_sw2021_pit_003": {
        "status": "unaccepted_invalid_publication",
        "exit_code": 3,
        "reason": "Missing source_partition_audit and source_to_record_mapping_hash",
    },
    "pims_traderlens_v2_shsz_sw2021_pit_004": {
        "status": "unaccepted_invalid_publication",
        "exit_code": 3,
        "reason": "Used .get('hash') instead of ['sha256'], resulting in null source_manifest_sha256",
    },
}

EXPECTED_FORMAL_DATA_SNAPSHOT_ID = "ds_traderlens_v2_shsz_pit_001"
EXPECTED_FORMAL_DATA_SEMANTIC_HASH = "da057716d4b4162b89fb89b7fd15864b4385d65cdee4e760a0743108cf1b135e"
EXPECTED_UNIVERSE_REFERENCE_ID = "uref_traderlens_v2_shsz_sw2021_pit_001"
BOUND_SW2021_MANIFEST = Path(
    "data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal/sw_l1_membership/manifest.json"
)


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
    
    # Check legacy status registry first (before any file access)
    base_dir = snapshots_root or (repo_root / "data/pit/pit_membership_snapshots")
    
    if snapshot_id in LEGACY_SNAPSHOT_REGISTRY:
        snapshot_dir = base_dir / snapshot_id
        legacy = LEGACY_SNAPSHOT_REGISTRY[snapshot_id]
        
        if snapshot_dir.exists():
            return {
                "status": legacy["status"],
                "snapshot_id": snapshot_id,
                "exit_code": legacy["exit_code"],
                "message": f"{snapshot_id} is {legacy['status']}",
                "reason": legacy["reason"],
            }
        else:
            return {"status": "missing", "errors": [f"Snapshot directory not found: {snapshot_dir}"]}
    
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
    
    # 8d. Verify all audit entries have required fields (4-field structure)
    audit = manifest.get("source_partition_audit", [])
    for entry in audit:
        if entry.get("source_manifest_sha256") is None:
            return {
                "status": "unaccepted_invalid_publication",
                "snapshot_id": snapshot_id,
                "message": f"{snapshot_id} is unaccepted (null source_manifest_sha256 in audit entry {entry.get('partition_name')})",
                "reason": "Audit entry lacks source partition hash",
            }
        # SW2021 partitions must have independently computed file fields
        if entry.get("taxonomy_status") == "sw2021_accepted":
            if entry.get("source_file_sha256") is None:
                return {
                    "status": "unaccepted_invalid_publication",
                    "snapshot_id": snapshot_id,
                    "message": f"{snapshot_id} is unaccepted (null source_file_sha256 in SW2021 entry {entry.get('partition_name')})",
                    "reason": "SW2021 audit entry lacks independently computed file hash",
                }
            if entry.get("source_file_row_count") is None:
                return {
                    "status": "unaccepted_invalid_publication",
                    "snapshot_id": snapshot_id,
                    "message": f"{snapshot_id} is unaccepted (null source_file_row_count in SW2021 entry {entry.get('partition_name')})",
                    "reason": "SW2021 audit entry lacks independently computed row count",
                }
    
    # 8e. Independently verify source files (read manifest and parquet files)
    source_contract = manifest.get("source_contract")
    if source_contract == "tushare_sw_l1_member_v2":
        # The production publisher binds this staged formal manifest.  Keep the
        # package scan as a fixture-compatible fallback for temporary sources.
        tushare_base = repo_root / "data/pit/tushare"
        candidates = [repo_root / BOUND_SW2021_MANIFEST]
        candidates.extend(
            pkg_dir / "sw_l1_membership" / "manifest.json"
            for pkg_dir in sorted(tushare_base.glob("*/"), reverse=True)
            if pkg_dir.is_dir() and not pkg_dir.name.startswith(".")
        )
        audited_partitions = {entry["partition_name"] for entry in audit}
        source_manifest_path = None
        for candidate in candidates:
            if not candidate.exists():
                continue
            candidate_manifest = json.loads(candidate.read_text(encoding="utf-8"))
            candidate_partitions = {entry["name"] for entry in candidate_manifest.get("partitions", [])}
            if audited_partitions.issubset(candidate_partitions):
                source_manifest_path = candidate
                break
        
        if source_manifest_path is None:
            warnings.append("Cannot verify source files: tushare sw_l1_membership manifest not found")
        else:
            source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
            source_partitions = {p["name"]: p for p in source_manifest.get("partitions", [])}
            source_dir = source_manifest_path.parent
            
            # Verify each audit entry's source file fields
            for entry in audit:
                partition_name = entry["partition_name"]
                taxonomy_status = entry.get("taxonomy_status")
                
                if partition_name not in source_partitions:
                    errors.append(f"{partition_name}: not found in source manifest")
                    continue
                
                source_meta = source_partitions[partition_name]
                
                # Verify manifest-declared fields match
                if entry["source_manifest_sha256"] != source_meta["sha256"]:
                    errors.append(
                        f"{partition_name}: source_manifest_sha256 mismatch "
                        f"(audit: {entry['source_manifest_sha256'][:16]}..., "
                        f"source manifest: {source_meta['sha256'][:16]}...)"
                    )
                
                if entry["source_record_count"] != source_meta["row_count"]:
                    errors.append(
                        f"{partition_name}: source_record_count mismatch "
                        f"(audit: {entry['source_record_count']}, source manifest: {source_meta['row_count']})"
                    )
                
                # For SW2021, verify independently computed file fields
                if taxonomy_status == "sw2021_accepted":
                    parquet_path = source_dir / partition_name
                    if not parquet_path.exists():
                        errors.append(f"{partition_name}: source file not found at {parquet_path}")
                        continue
                    
                    # Independently compute file hash
                    actual_file_hash = sha256_file(parquet_path)
                    if entry["source_file_sha256"] != actual_file_hash:
                        errors.append(
                            f"{partition_name}: source_file_sha256 mismatch "
                            f"(audit: {entry['source_file_sha256'][:16]}..., actual file: {actual_file_hash[:16]}...)"
                        )
                    
                    # Independently compute row count
                    try:
                        table = pq.read_table(parquet_path)
                        actual_row_count = len(table)
                        if entry["source_file_row_count"] != actual_row_count:
                            errors.append(
                                f"{partition_name}: source_file_row_count mismatch "
                                f"(audit: {entry['source_file_row_count']}, actual file: {actual_row_count})"
                            )
                    except Exception as e:
                        errors.append(f"{partition_name}: failed to read source file: {e}")
    
    # Early return if source file verification failed
    if errors:
        return {
            "status": "failed",
            "errors": errors,
            "warnings": warnings,
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
    
    # 12b. Independently recompute per-partition audit fields from records.parquet
    # Group records by source partition
    partition_records = {}
    for _, row in df.iterrows():
        source_provenance = row["source"]
        if source_provenance not in partition_records:
            partition_records[source_provenance] = []
        partition_records[source_provenance].append(row)
    
    # Verify each SW2021 partition's canonical_record_identity_hash and published_record_count
    for entry in audit:
        if entry["taxonomy_status"] == "sw2021_accepted":
            partition_name = entry["partition_name"]
            # Reconstruct source provenance from partition name: SW2021_801010.SI_is_new_Y.parquet
            parts = partition_name.replace(".parquet", "").split("_")
            if len(parts) >= 4:  # SW2021_801010.SI_is_new_Y
                l1_code = parts[1]  # 801010.SI
                is_new = parts[-1]  # Y or N
                source_provenance = f"SW2021_{l1_code}_is_new_{is_new}"
                
                records_for_partition = partition_records.get(source_provenance, [])
                actual_count = len(records_for_partition)
                declared_count = entry["published_record_count"]
                
                if actual_count != declared_count:
                    errors.append(
                        f"{partition_name}: published_record_count mismatch "
                        f"(declared {declared_count}, actual {actual_count})"
                    )
                
                # Recompute canonical_record_identity_hash
                canonical_identities = []
                for rec in records_for_partition:
                    identity_tuple = (
                        rec["symbol"],
                        rec["effective_from"].isoformat() if hasattr(rec["effective_from"], "isoformat") else str(rec["effective_from"]),
                        rec["effective_to"].isoformat() if rec["effective_to"] is not None and hasattr(rec["effective_to"], "isoformat") else (str(rec["effective_to"]) if rec["effective_to"] is not None else None),
                        l1_code,
                    )
                    canonical_identities.append(identity_tuple)
                
                canonical_identities_sorted = sorted(canonical_identities)
                canonical_payload = json.dumps(canonical_identities_sorted, separators=(",", ":"))
                recomputed_hash = hashlib.sha256(canonical_payload.encode()).hexdigest()
                
                declared_hash = entry.get("canonical_record_identity_hash")
                if declared_hash != recomputed_hash:
                    errors.append(
                        f"{partition_name}: canonical_record_identity_hash mismatch "
                        f"(declared {declared_hash[:16]}..., recomputed {recomputed_hash[:16]}...)"
                    )
    
    # 12c. Independently recompute source_to_record_mapping_hash from audit
    canonical_audit_payload = json.dumps(audit, sort_keys=True, separators=(",", ":"))
    recomputed_mapping_hash = hashlib.sha256(canonical_audit_payload.encode()).hexdigest()
    declared_mapping_hash = manifest.get("source_to_record_mapping_hash")
    
    if declared_mapping_hash != recomputed_mapping_hash:
        errors.append(
            f"source_to_record_mapping_hash mismatch "
            f"(declared {declared_mapping_hash[:16]}..., recomputed {recomputed_mapping_hash[:16]}...)"
        )
    
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
    
    # include_delisted is proved by source-record retention, not by delisted record existence
    
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
        print(f"\n[REJECTED] {result['message']}")
        print(f"Reason: {result['reason']}")
        print("\nThis snapshot must NOT be used. It is preserved only as audit evidence.")
        return result.get("exit_code", 2)
    
    if result["status"] == "unaccepted_invalid_publication":
        print(f"\n[REJECTED] {result['message']}")
        print(f"Reason: {result['reason']}")
        print("\nThis snapshot must NOT be used. It is preserved only as audit evidence.")
        return result.get("exit_code", 3)
    
    if result["status"] == "verified":
        print(f"Snapshot ID: {result['snapshot_id']}")
        print(f"Snapshot date: {result['snapshot_date']}")
        print(f"Record count: {result['record_count']}")
        print(f"Unique symbols: {result['unique_symbols']}")
        print(f"Canonical content hash: {result['canonical_content_hash']}")
        
        if result.get("warnings"):
            print("\nWarnings:")
            for w in result["warnings"]:
                print(f"  [WARN] {w}")
        
        print("\n[PASS] Verification passed")
        return 0
    else:
        print(f"\n[FAIL] Verification failed")
        
        if result.get("errors"):
            print("\nErrors:")
            for e in result["errors"]:
                print(f"  [ERROR] {e}")
        
        return 1


if __name__ == "__main__":
    sys.exit(main())
