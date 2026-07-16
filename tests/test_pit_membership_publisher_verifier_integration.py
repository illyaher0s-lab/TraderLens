"""Integration tests: production publisher/verifier prepublication validation.

All 5 tests call real production code without wrappers/mocks.
"""
import hashlib
import json
import subprocess
import tempfile
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from scripts.audit_pit_source_manifest import audit_source_manifest
from scripts.publish_pit_membership_snapshot import publish_snapshot

REPO_ROOT = Path(__file__).resolve().parents[1]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_001_production_source_manifest_audit():
    """Verify 61 SW2021 partition hashes + 53 SW2014 metadata enumeration."""
    result = audit_source_manifest(REPO_ROOT)
    
    assert result["manifest_sha256"] == "a38b3cc6be947b290078fe637466991ee8d13dee2794d398fb709d5c4c3826f3"
    assert len(result["sw2021_verified"]) == 61
    assert len(result["sw2021_mismatches"]) == 0
    assert len(result["sw2014_metadata"]) == 53
    assert result["total_partitions"] == 114
    
    # Verify SW2021 entries have required fields
    for entry in result["sw2021_verified"]:
        assert "partition_name" in entry
        assert "source_manifest_sha256" in entry
        assert "source_record_count" in entry
        assert entry["source_manifest_sha256"]  # Non-empty hash
    
    # Verify SW2014 entries are metadata-only
    for entry in result["sw2014_metadata"]:
        assert "partition_name" in entry
        assert "source_record_count" in entry
        assert entry["taxonomy_status"] == "out_of_scope_sw2014"


def test_002_sw2014_zero_read_verification():
    """Prove publisher does not read SW2014 parquet via unreadable poison file."""
    with tempfile.TemporaryDirectory() as td:
        temp = Path(td)
        src = temp / "source"
        src.mkdir()
        
        # Valid SW2021 partition
        sw2021 = pd.DataFrame([
            {
                "ts_code": "600000.SH",
                "in_date": "20200101",
                "out_date": None,
                "l1_code": "801010.SI",
                "is_new": 0,
            },
        ])
        sw2021_path = src / "SW2021_801010.SI_is_new_Y.parquet"
        sw2021.to_parquet(sw2021_path, index=False)
        sw2021_sha = sha256_bytes(sw2021_path.read_bytes())
        
        # Poison SW2014 - unreadable if accessed
        poison_path = src / "SW2014_poison.parquet"
        poison_path.write_bytes(b"\x00\x00POISON_NOT_PARQUET")
        poison_sha = sha256_bytes(poison_path.read_bytes())
        
        manifest = {
            "snapshot_id": "temp_sw2014_zero_read",
            "status": "collected_verified",
            "partitions": [
                {
                    "name": "SW2021_801010.SI_is_new_Y.parquet",
                    "src": "SW2021",
                    "sha256": sw2021_sha,
                    "row_count": 1,
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
        
        # Call production publisher - must NOT crash on poison SW2014
        result = publish_snapshot(
            REPO_ROOT,
            date(2024, 12, 31),
            _test_source_manifest=manifest_path,
            _test_output_root=snapshot_root,
            _test_snapshot_id="temp_sw2014_zero_read",
        )
        
        assert result["status"] == "published", f"Publisher crashed on poison SW2014: {result}"
        
        # Verify audit lists SW2014 but published_record_count=0
        output_manifest_path = snapshot_root / "temp_sw2014_zero_read" / "manifest.json"
        output_manifest = json.loads(output_manifest_path.read_text(encoding="utf-8"))
        
        audit = output_manifest["source_partition_audit"]
        sw2014_entries = [e for e in audit if e["partition_name"] == "SW2014_poison.parquet"]
        assert len(sw2014_entries) == 1
        assert sw2014_entries[0]["published_record_count"] == 0
        assert sw2014_entries[0]["taxonomy_status"] == "out_of_scope_sw2014"


def test_003_write_once_idempotency():
    """Verify write-once: same content returns already_published, modified content rejects."""
    with tempfile.TemporaryDirectory() as td:
        temp = Path(td)
        src = temp / "source"
        src.mkdir()
        
        # Initial content
        df = pd.DataFrame([
            {
                "ts_code": "600000.SH",
                "in_date": "20200101",
                "out_date": None,
                "l1_code": "801010.SI",
                "is_new": 0,
            },
        ])
        parquet_path = src / "SW2021_test.parquet"
        df.to_parquet(parquet_path, index=False)
        original_sha = sha256_bytes(parquet_path.read_bytes())
        
        manifest = {
            "snapshot_id": "temp_write_once",
            "status": "collected_verified",
            "partitions": [
                {
                    "name": "SW2021_test.parquet",
                    "src": "SW2021",
                    "sha256": original_sha,
                    "row_count": 1,
                },
            ],
        }
        manifest_path = src / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        
        snapshot_root = temp / "snapshots"
        snapshot_root.mkdir()
        
        # First publish
        result1 = publish_snapshot(
            REPO_ROOT,
            date(2024, 12, 31),
            _test_source_manifest=manifest_path,
            _test_output_root=snapshot_root,
            _test_snapshot_id="temp_write_once",
        )
        assert result1["status"] == "published"
        
        # Second publish with same content - should detect already_published
        result2 = publish_snapshot(
            REPO_ROOT,
            date(2024, 12, 31),
            _test_source_manifest=manifest_path,
            _test_output_root=snapshot_root,
            _test_snapshot_id="temp_write_once",
        )
        assert result2["status"] == "already_published"
        
        # Third publish with modified content but same manifest hash - should reject
        df_modified = pd.DataFrame([
            {
                "ts_code": "600001.SH",  # Changed symbol
                "in_date": "20200101",
                "out_date": None,
                "l1_code": "801010.SI",
                "is_new": 0,
            },
        ])
        parquet_path.unlink()
        df_modified.to_parquet(parquet_path, index=False)
        new_sha = sha256_bytes(parquet_path.read_bytes())
        
        # Update manifest with new hash
        manifest["partitions"][0]["sha256"] = new_sha
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        
        result3 = publish_snapshot(
            REPO_ROOT,
            date(2024, 12, 31),
            _test_source_manifest=manifest_path,
            _test_output_root=snapshot_root,
            _test_snapshot_id="temp_write_once",
        )
        assert result3["status"] == "content_conflict"


def test_004_real_verifier_cli_exit_0():
    """Verify CLI verifier accepts temporary successful artifact with exit 0."""
    with tempfile.TemporaryDirectory() as td:
        temp = Path(td)
        src = temp / "source"
        src.mkdir()
        
        df = pd.DataFrame([
            {
                "ts_code": "600000.SH",
                "in_date": "20200101",
                "out_date": None,
                "l1_code": "801010.SI",
                "is_new": 0,
            },
        ])
        parquet_path = src / "SW2021_test.parquet"
        df.to_parquet(parquet_path, index=False)
        parquet_sha = sha256_bytes(parquet_path.read_bytes())
        
        manifest = {
            "snapshot_id": "temp_verifier_test",
            "status": "collected_verified",
            "partitions": [
                {
                    "name": "SW2021_test.parquet",
                    "src": "SW2021",
                    "sha256": parquet_sha,
                    "row_count": 1,
                },
            ],
        }
        manifest_path = src / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        
        snapshot_root = temp / "snapshots"
        snapshot_root.mkdir()
        
        # Publish artifact
        result = publish_snapshot(
            REPO_ROOT,
            date(2024, 12, 31),
            _test_source_manifest=manifest_path,
            _test_output_root=snapshot_root,
            _test_snapshot_id="temp_verifier_test",
        )
        assert result["status"] == "published"
        
        # Call real verifier CLI with --snapshots-root
        verifier_path = REPO_ROOT / "scripts/verify_pit_membership_snapshot.py"
        python_exe = REPO_ROOT / ".venv/Scripts/python.exe"
        proc = subprocess.run(
            [
                str(python_exe),
                str(verifier_path),
                "temp_verifier_test",  # Positional argument
                "--snapshots-root", str(snapshot_root),
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        
        # Must exit 0 and output verification passed
        assert proc.returncode == 0, f"Verifier failed:\nstdout: {proc.stdout}\nstderr: {proc.stderr}"
        assert "Verification passed" in proc.stdout, f"Missing verification success in output:\n{proc.stdout}"


def test_005_include_delisted_validates_retention_not_effective_to():
    """Verify include_delisted checks source record retention, not effective_to presence."""
    with tempfile.TemporaryDirectory() as td:
        temp = Path(td)
        src = temp / "source"
        src.mkdir()
        
        # Records without effective_to (all still listed)
        df_no_delisted = pd.DataFrame([
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
                "out_date": None,
                "l1_code": "801010.SI",
                "is_new": 0,
            },
        ])
        parquet_path = src / "SW2021_no_delisted.parquet"
        df_no_delisted.to_parquet(parquet_path, index=False)
        parquet_sha = sha256_bytes(parquet_path.read_bytes())
        
        manifest = {
            "snapshot_id": "temp_include_delisted_test",
            "status": "collected_verified",
            "partitions": [
                {
                    "name": "SW2021_no_delisted.parquet",
                    "src": "SW2021",
                    "sha256": parquet_sha,
                    "row_count": 2,
                },
            ],
        }
        manifest_path = src / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        
        snapshot_root = temp / "snapshots"
        snapshot_root.mkdir()
        
        # Must succeed even without any effective_to records
        result = publish_snapshot(
            REPO_ROOT,
            date(2024, 12, 31),
            _test_source_manifest=manifest_path,
            _test_output_root=snapshot_root,
            _test_snapshot_id="temp_include_delisted_test",
        )
        assert result["status"] == "published"
        
        # Verify manifest declares include_delisted=true
        output_manifest_path = snapshot_root / "temp_include_delisted_test" / "manifest.json"
        output_manifest = json.loads(output_manifest_path.read_text(encoding="utf-8"))
        assert output_manifest["include_delisted"] is True
