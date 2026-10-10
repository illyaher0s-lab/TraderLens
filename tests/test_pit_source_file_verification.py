#!/usr/bin/env python3
"""Test PIT membership publisher and verifier source file verification.

Core requirement: Publisher must independently compute source file hash and row count.
Verifier must independently read source files and verify 4-field structure:
- source_manifest_sha256 (manifest declares)
- source_file_sha256 (independently computed from file)
- source_record_count (manifest declares)
- source_file_row_count (independently computed from file)
"""

import json
import tempfile
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from scripts.publish_pit_membership_snapshot import publish_snapshot
from scripts.verify_pit_membership_snapshot import verify_snapshot


def test_publisher_computes_source_file_fields(tmp_path):
    """Publisher must independently compute source_file_sha256 and source_file_row_count."""
    
    # Create minimal source manifest with 1 SW2021 partition
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    
    # Create real parquet with known content
    df = pd.DataFrame({
        "ts_code": ["600000.SH"],
        "in_date": [20200101],
        "out_date": [None],
        "l1_code": ["801010.SI"],
        "is_new": ["Y"],
    })
    parquet_path = source_dir / "SW2021_801010.SI_is_new_Y.parquet"
    table = pa.Table.from_pandas(df)
    pq.write_table(table, parquet_path)
    
    # Compute actual file hash and row count
    import hashlib
    with open(parquet_path, "rb") as f:
        actual_file_hash = hashlib.sha256(f.read()).hexdigest()
    actual_row_count = len(df)
    
    # Create source manifest (publisher will read this)
    source_manifest = {
        "partitions": [
            {
                "name": "SW2021_801010.SI_is_new_Y.parquet",
                "src": "SW2021",
                "sha256": "MANIFEST_DECLARED_HASH_DIFFERENT_FROM_FILE",
                "row_count": 999,  # Different from actual
            }
        ]
    }
    manifest_path = source_dir / "manifest.json"
    manifest_path.write_text(json.dumps(source_manifest, indent=2), encoding="utf-8")
    
    # Publish with test mode
    output_root = tmp_path / "output"
    output_root.mkdir()
    
    result = publish_snapshot(
        repo_root=tmp_path,  # Dummy repo_root
        snapshot_date="2026-07-16",
        _test_snapshot_id="test_source_file_fields",
        _test_source_manifest=manifest_path,
        _test_output_root=output_root,
    )
    
    assert result["status"] == "published"
    
    # Read published manifest (test mode uses short directory name)
    published_manifest_path = output_root / "test_source_file_fields" / "manifest.json"
    published_manifest = json.loads(published_manifest_path.read_text(encoding="utf-8"))
    
    audit = published_manifest["source_partition_audit"]
    assert len(audit) == 1
    
    entry = audit[0]
    
    # Verify 4-field structure exists
    assert "source_manifest_sha256" in entry
    assert "source_file_sha256" in entry
    assert "source_record_count" in entry
    assert "source_file_row_count" in entry
    
    # Verify manifest-declared fields (copied from source manifest)
    assert entry["source_manifest_sha256"] == "MANIFEST_DECLARED_HASH_DIFFERENT_FROM_FILE"
    assert entry["source_record_count"] == 999
    
    # Verify independently computed fields (from actual file)
    assert entry["source_file_sha256"] == actual_file_hash
    assert entry["source_file_row_count"] == actual_row_count


def test_verifier_independently_reads_source_files(tmp_path):
    """Verifier must independently read source files and detect tampering."""
    
    # Setup: create source and publish
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    
    df = pd.DataFrame({
        "ts_code": ["600000.SH"],
        "in_date": [20200101],
        "out_date": [None],
        "l1_code": ["801010.SI"],
        "is_new": ["Y"],
    })
    parquet_path = source_dir / "SW2021_801010.SI_is_new_Y.parquet"
    table = pa.Table.from_pandas(df)
    pq.write_table(table, parquet_path)
    
    import hashlib
    with open(parquet_path, "rb") as f:
        correct_file_hash = hashlib.sha256(f.read()).hexdigest()
    
    source_manifest = {
        "partitions": [
            {
                "name": "SW2021_801010.SI_is_new_Y.parquet",
                "src": "SW2021",
                "sha256": "manifest_hash",
                "row_count": 1,
            }
        ]
    }
    manifest_path = source_dir / "manifest.json"
    manifest_path.write_text(json.dumps(source_manifest, indent=2), encoding="utf-8")
    
    output_root = tmp_path / "output"
    output_root.mkdir()
    
    result = publish_snapshot(
        repo_root=tmp_path,
        snapshot_date="2026-07-16",
        _test_snapshot_id="test_verifier_source",
        _test_source_manifest=manifest_path,
        _test_output_root=output_root,
    )
    
    assert result["status"] == "published"
    
    # Tamper with audit: change source_file_sha256 to wrong value (test mode uses short directory name)
    published_manifest_path = output_root / "test_verifier_source" / "manifest.json"
    published_manifest = json.loads(published_manifest_path.read_text(encoding="utf-8"))
    
    published_manifest["source_partition_audit"][0]["source_file_sha256"] = "TAMPERED_WRONG_HASH"
    
    # Update manifest and sidecar
    published_manifest_path.write_text(json.dumps(published_manifest, indent=2), encoding="utf-8")
    with open(published_manifest_path, "rb") as f:
        new_manifest_hash = hashlib.sha256(f.read()).hexdigest()
    sidecar_path = published_manifest_path.parent / "manifest.json.sha256"
    sidecar_path.write_text(new_manifest_hash, encoding="utf-8")
    
    # Create mock repo structure for verifier
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    tushare_pkg = repo_root / "data/pit/tushare/test_pkg/sw_l1_membership"
    tushare_pkg.mkdir(parents=True)
    
    # Copy source files to mock repo location
    import shutil
    shutil.copy(manifest_path, tushare_pkg / "manifest.json")
    shutil.copy(parquet_path, tushare_pkg / parquet_path.name)
    
    # Verifier must detect tampering by reading actual source file
    verify_result = verify_snapshot(
        repo_root,
        "test_verifier_source",
        snapshots_root=output_root,
    )
    
    # Must fail because source_file_sha256 doesn't match actual file
    assert verify_result["status"] != "verified"
    assert any("source_file_sha256 mismatch" in str(e) for e in verify_result.get("errors", []))


def test_verifier_rejects_missing_source_file_fields(tmp_path):
    """Verifier must reject artifacts missing source_file_sha256 or source_file_row_count."""
    
    # Create minimal artifact with old 2-field structure (missing source_file_* fields)
    snapshot_dir = tmp_path / "pims_traderlens_v2_shsz_sw2021_pit_test_missing_fields"
    snapshot_dir.mkdir()
    
    manifest = {
        "snapshot_id": "test_missing_fields",
        "snapshot_date": "2026-07-16",
        "universe_rule_type": "dummy",
        "membership_source": "dummy",
        "vendor_scope_disclosure": {"historical_membership_scope": "vendor_provided_unverified", "disclosure_text": "dummy"},
        "include_delisted": True,
        "frozen": True,
        "quality_status": "ok",
        "gaps": [],
        "record_count": 1,
        "formal_data_snapshot_id": "dummy",
        "formal_data_semantic_hash": "dummy",
        "universe_reference_id": "dummy",
        "records_parquet_sha256": "dummy",
        "canonical_content_hash": "dummy",
        "schema_version": "v1",
        "interval_semantics": "closed_inclusive",
        "not_authorized_for_b6_oos_gate_promotion_signal": True,
        "source_to_record_mapping_hash": "dummy",
        "source_partition_audit": [
            {
                "partition_name": "SW2021_801010.SI_is_new_Y.parquet",
                "source_manifest_sha256": "hash",
                "source_record_count": 1,
                # Missing: source_file_sha256, source_file_row_count
                "published_record_count": 1,
                "taxonomy_status": "sw2021_accepted",
            }
        ],
    }
    
    manifest_path = snapshot_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    
    import hashlib
    with open(manifest_path, "rb") as f:
        manifest_hash = hashlib.sha256(f.read()).hexdigest()
    
    sidecar_path = snapshot_dir / "manifest.json.sha256"
    sidecar_path.write_text(manifest_hash, encoding="utf-8")
    
    # Create dummy records.parquet
    df = pd.DataFrame({
        "symbol": ["600000.SH"],
        "effective_from": [pd.Timestamp("2020-01-01")],
        "effective_to": [None],
        "source": ["SW2021_801010.SI_is_new_Y"],
        "snapshot_id": ["test_missing_fields"],
    })
    records_path = snapshot_dir / "records.parquet"
    pq.write_table(pa.Table.from_pandas(df), records_path)
    
    with open(records_path, "rb") as f:
        records_hash = hashlib.sha256(f.read()).hexdigest()
    records_sidecar = snapshot_dir / "records.parquet.sha256"
    records_sidecar.write_text(records_hash, encoding="utf-8")
    
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    
    # Verifier must reject immediately (before trying to read source files)
    result = verify_snapshot(repo_root, snapshot_dir.name, snapshots_root=snapshot_dir.parent)
    
    assert result["status"] == "unaccepted_invalid_publication"
    assert "source_file_sha256" in result["message"] or "source_file_row_count" in result["message"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
