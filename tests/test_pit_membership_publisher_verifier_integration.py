"""RED integration test: real production publisher/verifier with temp fixtures."""
import hashlib
import json
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_real_publisher_computes_hashes():
    """RED: Real publish_snapshot() must compute all hashes with canonical schema."""
    with tempfile.TemporaryDirectory() as td:
        temp = Path(td)
        src = temp / "source"
        src.mkdir()
        
        # Canonical production schema: name, src, sha256, row_count
        sw2021 = pd.DataFrame([
            {
                "ts_code": "600000.SH",
                "in_date": "20200101",
                "out_date": None,
                "l1_code": "801010.SI",
                "is_new": 0,
            },
            {
                "ts_code": "600001.SH",
                "in_date": "20180101",
                "out_date": "20201231",  # Delisted
                "l1_code": "801010.SI",
                "is_new": 0,
            },
        ])
        sw2021_path = src / "SW2021_801010.SI_is_new_Y.parquet"
        sw2021.to_parquet(sw2021_path, index=False)
        sw2021_sha = sha256_bytes(sw2021_path.read_bytes())
        
        # Poison SW2014 - unreadable if accessed
        poison_path = src / "SW2014_poison.parquet"
        poison_path.write_bytes(b"\x00\x00POISON")  # Invalid parquet
        poison_sha = sha256_bytes(poison_path.read_bytes())
        
        manifest = {
            "snapshot_id": "temp_real_001",
            "partitions": [
                {
                    "name": "SW2021_801010.SI_is_new_Y.parquet",
                    "src": "SW2021",
                    "sha256": sw2021_sha,
                    "row_count": 2,
                },
                {
                    "name": "SW2014_poison.parquet",
                    "src": "SW2014",
                    "sha256": poison_sha,
                    "row_count": 999,
                },
            ],
        }
        manifest_path = src / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        
        snapshot_root = temp / "snapshots"
        snapshot_root.mkdir()
        
        # Call production publisher with test overrides
        from scripts.publish_pit_membership_snapshot import publish_snapshot
        
        result = publish_snapshot(
            REPO_ROOT,
            date(2024, 12, 31),
            _test_source_manifest=manifest_path,
            _test_output_root=snapshot_root,
            _test_snapshot_id="temp_real_001",
        )
        
        # Must succeed (poison not read)
        assert result["status"] == "published", f"Got: {result}"
        
        # Check output
        output_manifest_path = snapshot_root / "temp_real_001" / "manifest.json"
        assert output_manifest_path.exists(), f"Manifest missing at {output_manifest_path}"
        
        output_manifest = json.loads(output_manifest_path.read_text(encoding="utf-8"))
        
        audit = output_manifest["source_partition_audit"]
        consumed = [e for e in audit if e["partition_name"] == "SW2021_801010.SI_is_new_Y.parquet"]
        excluded = [e for e in audit if e["partition_name"] == "SW2014_poison.parquet"]
        
        assert len(consumed) == 1
        assert consumed[0]["source_manifest_sha256"] == sw2021_sha
        assert consumed[0]["published_record_count"] == 2  # Two records published
        
        assert len(excluded) == 1
        assert excluded[0]["source_manifest_sha256"] == poison_sha
        assert excluded[0]["published_record_count"] == 0
        
        assert output_manifest["source_to_record_mapping_hash"] is not None
        
        # Records has both SW2021 records
        records = pd.read_parquet(snapshot_root / "temp_real_001" / "records.parquet")
        assert len(records) == 2


def test_verifier_rejects_004_for_null_hashes():
    """RED: Verifier must reject _004 as unaccepted_invalid_publication due to null hashes."""
    from scripts.verify_pit_membership_snapshot import verify_snapshot
    
    result = verify_snapshot(REPO_ROOT, "pims_traderlens_v2_shsz_sw2021_pit_004")
    assert result["status"] == "unaccepted_invalid_publication", \
        f"_004 with null hashes must be rejected, got: {result['status']}"
