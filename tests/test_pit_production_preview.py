"""Production-input preview tests for PIT membership publisher.

Tests real 61 SW2021 + 53 SW2014 source partitions with tempfile output.
No formal snapshot IDs, no modification to _001-_004.
"""
import os
import subprocess
import tempfile
from pathlib import Path
import json
import sys
import hashlib
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

# ponytail: add repo root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.publish_pit_membership_snapshot import publish_snapshot
from scripts.verify_pit_membership_snapshot import verify_snapshot
from scripts.verify_pit_membership_snapshot import canonical_json_hash


def test_production_input_preview_61_sw2021_53_sw2014():
    """Preview with real production source manifest (61 SW2021 + 53 SW2014)."""
    repo_root = Path(__file__).parent.parent
    
    with tempfile.TemporaryDirectory() as tmpdir:
        result = publish_snapshot(
            repo_root=repo_root,
            snapshot_date="2026-07-16",
            _test_snapshot_id="preview_production_input",
            _test_output_root=Path(tmpdir),
        )
        
        # Should succeed with production source
        assert result["status"] == "published", f"Got {result.get('status')}: {result.get('message')}"
        
        # Verify temp artifact exists
        preview_dir = Path(tmpdir) / "preview_production_input"
        assert preview_dir.exists(), "Preview snapshot not created"
        
        manifest_path = preview_dir / "manifest.json"
        assert manifest_path.exists(), "Manifest not created"
        
        manifest = json.loads(manifest_path.read_text())
        audit = manifest["source_partition_audit"]
        
        sw2021 = [e for e in audit if e["taxonomy_status"] == "sw2021_accepted"]
        sw2014 = [e for e in audit if e["taxonomy_status"] == "out_of_scope_sw2014"]
        
        # Verify counts
        assert len(sw2021) == 61, f"Expected 61 SW2021, got {len(sw2021)}"
        assert len(sw2014) == 53, f"Expected 53 SW2014, got {len(sw2014)}"
        
        # Verify SW2021 has real hashes (not null)
        null_hashes = [e for e in sw2021 if e["source_manifest_sha256"] is None]
        assert len(null_hashes) == 0, f"Found {len(null_hashes)} SW2021 with null hash"
        
        # Verify SW2014 zero reads
        sw2014_published = [e for e in sw2014 if e["published_record_count"] != 0]
        assert len(sw2014_published) == 0, f"SW2014 should have 0 records, got {sw2014_published}"
        
        # Temp dir auto-cleans on exit


def test_production_preview_verifier_recomputes_bound_source_files():
    """The real verifier must read the bound 61-partition source, not warn-and-skip."""
    repo_root = Path(__file__).parent.parent

    with tempfile.TemporaryDirectory() as tmpdir:
        snapshot_root = Path(tmpdir)
        snapshot_id = "preview_production_source_recompute"
        published = publish_snapshot(
            repo_root=repo_root,
            snapshot_date="2026-07-16",
            _test_snapshot_id=snapshot_id,
            _test_output_root=snapshot_root,
        )
        assert published["status"] == "published"

        verified = verify_snapshot(repo_root, snapshot_id, snapshots_root=snapshot_root)
        assert verified["status"] == "verified", verified
        assert not any(
            "Cannot verify source files" in warning
            for warning in verified.get("warnings", [])
        ), verified


def test_production_preview_verifier_rejects_tampered_source_file_hash():
    """A self-consistent temp manifest still fails if a real source-file hash lies."""
    repo_root = Path(__file__).parent.parent

    with tempfile.TemporaryDirectory() as tmpdir:
        snapshot_root = Path(tmpdir)
        snapshot_id = "preview_production_source_tamper"
        published = publish_snapshot(
            repo_root=repo_root,
            snapshot_date="2026-07-16",
            _test_snapshot_id=snapshot_id,
            _test_output_root=snapshot_root,
        )
        assert published["status"] == "published"

        manifest_path = snapshot_root / snapshot_id / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        sw2021 = next(
            entry for entry in manifest["source_partition_audit"]
            if entry["taxonomy_status"] == "sw2021_accepted"
        )
        sw2021["source_file_sha256"] = "0" * 64
        manifest["source_to_record_mapping_hash"] = hashlib.sha256(
            json.dumps(manifest["source_partition_audit"], sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        manifest["canonical_content_hash"] = canonical_json_hash(
            manifest, {"canonical_content_hash", "manifest_published_at"}
        )
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        (snapshot_root / snapshot_id / "manifest.json.sha256").write_text(
            f"{manifest_hash}  manifest.json\n", encoding="utf-8"
        )

        verified = verify_snapshot(repo_root, snapshot_id, snapshots_root=snapshot_root)
        assert verified["status"] == "failed", verified
        assert any("source_file_sha256 mismatch" in error for error in verified["errors"])


def test_duplicate_canonical_identity_rejects():
    """Duplicate (symbol, effective_from, effective_to, l1_code) must fail loud."""
    repo_root = Path(__file__).parent.parent
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create minimal source with duplicate
        source_dir = Path(tmpdir) / "source"
        source_dir.mkdir()
        
        schema = pa.schema([
            ("ts_code", pa.string()),
            ("in_date", pa.int32()),
            ("out_date", pa.int32()),
            ("l1_code", pa.string()),
            ("is_new", pa.int8()),
        ])
        
        # Two identical records
        table = pa.table({
            "ts_code": ["600000.SH", "600000.SH"],
            "in_date": [20200101, 20200101],
            "out_date": [20201231, 20201231],
            "l1_code": ["801010.SI", "801010.SI"],
            "is_new": [1, 1],
        }, schema=schema)
        
        partition_path = source_dir / "SW2021_801010.SI_is_new_Y.parquet"
        pq.write_table(table, partition_path)
        
        # Create source manifest
        import hashlib
        with open(partition_path, "rb") as f:
            sha256 = hashlib.sha256(f.read()).hexdigest()
        
        manifest = {
            "partitions": [
                {
                    "name": "SW2021_801010.SI_is_new_Y.parquet",
                    "src": "SW2021",
                    "row_count": 2,
                    "sha256": sha256,
                }
            ]
        }
        
        manifest_path = source_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2))
        
        # Publish should reject
        result = publish_snapshot(
            repo_root=repo_root,
            snapshot_date="2026-07-16",
            _test_snapshot_id="preview_duplicate",
            _test_output_root=Path(tmpdir) / "output",
            _test_source_manifest=manifest_path,
        )
        
        assert result["status"] == "validation_failed", f"Expected validation_failed, got {result['status']}"
        
        # Check errors contain duplicate detection
        errors_str = " ".join(result.get("errors", []))
        assert "duplicate" in errors_str.lower(), f"Expected duplicate in errors, got: {result.get('errors', [])}"
        
        # Final snapshot dir must not exist
        snapshot_dir = Path(tmpdir) / "output" / "preview_duplicate"
        assert not snapshot_dir.exists(), "Snapshot created despite validation failure"


def test_effective_to_before_from_rejects():
    """effective_to < effective_from must be rejected."""
    repo_root = Path(__file__).parent.parent
    
    with tempfile.TemporaryDirectory() as tmpdir:
        source_dir = Path(tmpdir) / "source"
        source_dir.mkdir()
        
        schema = pa.schema([
            ("ts_code", pa.string()),
            ("in_date", pa.int32()),
            ("out_date", pa.int32()),
            ("l1_code", pa.string()),
            ("is_new", pa.int8()),
        ])
        
        # Invalid interval: out_date < in_date
        table = pa.table({
            "ts_code": ["600000.SH"],
            "in_date": [20201231],
            "out_date": [20200101],
            "l1_code": ["801010.SI"],
            "is_new": [1],
        }, schema=schema)
        
        partition_path = source_dir / "SW2021_801010.SI_is_new_Y.parquet"
        pq.write_table(table, partition_path)
        
        import hashlib
        with open(partition_path, "rb") as f:
            sha256 = hashlib.sha256(f.read()).hexdigest()
        
        manifest = {
            "partitions": [
                {
                    "name": "SW2021_801010.SI_is_new_Y.parquet",
                    "src": "SW2021",
                    "row_count": 1,
                    "sha256": sha256,
                }
            ]
        }
        
        manifest_path = source_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2))
        
        result = publish_snapshot(
            repo_root=repo_root,
            snapshot_date="2026-07-16",
            _test_snapshot_id="preview_invalid_interval",
            _test_output_root=Path(tmpdir) / "output",
            _test_source_manifest=manifest_path,
        )
        
        assert result["status"] == "validation_failed", f"Expected validation_failed, got {result['status']}"
        
        # Check errors contain interval validation
        errors_str = " ".join(result.get("errors", []))
        assert "effective_to < effective_from" in errors_str, f"Expected interval error in errors, got: {result.get('errors', [])}"
        
        snapshot_dir = Path(tmpdir) / "output" / "preview_invalid_interval"
        assert not snapshot_dir.exists(), "Snapshot created despite validation failure"


def test_overlapping_closed_intervals_rejects():
    """Overlapping closed intervals for same symbol must be rejected."""
    repo_root = Path(__file__).parent.parent
    
    with tempfile.TemporaryDirectory() as tmpdir:
        source_dir = Path(tmpdir) / "source"
        source_dir.mkdir()
        
        schema = pa.schema([
            ("ts_code", pa.string()),
            ("in_date", pa.int32()),
            ("out_date", pa.int32()),
            ("l1_code", pa.string()),
            ("is_new", pa.int8()),
        ])
        
        # Overlapping intervals: [20200101, 20201231] and [20200601, 20210630]
        table = pa.table({
            "ts_code": ["600000.SH", "600000.SH"],
            "in_date": [20200101, 20200601],
            "out_date": [20201231, 20210630],
            "l1_code": ["801010.SI", "801020.SI"],
            "is_new": [0, 0],
        }, schema=schema)
        
        partition_path = source_dir / "SW2021_mixed_is_new_N.parquet"
        pq.write_table(table, partition_path)
        
        import hashlib
        with open(partition_path, "rb") as f:
            sha256 = hashlib.sha256(f.read()).hexdigest()
        
        manifest = {
            "partitions": [
                {
                    "name": "SW2021_mixed_is_new_N.parquet",
                    "src": "SW2021",
                    "row_count": 2,
                    "sha256": sha256,
                }
            ]
        }
        
        manifest_path = source_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2))
        
        result = publish_snapshot(
            repo_root=repo_root,
            snapshot_date="2026-07-16",
            _test_snapshot_id="preview_overlap",
            _test_output_root=Path(tmpdir) / "output",
            _test_source_manifest=manifest_path,
        )
        
        assert result["status"] == "validation_failed", f"Expected validation_failed, got {result['status']}"
        
        # Check errors contain overlap detection
        errors_str = " ".join(result.get("errors", []))
        assert "overlap" in errors_str.lower(), f"Expected overlap error in errors, got: {result.get('errors', [])}"
        
        snapshot_dir = Path(tmpdir) / "output" / "preview_overlap"
        assert not snapshot_dir.exists(), "Snapshot created despite validation failure"


def test_production_cli_gbk_rejects_004_without_encoding_failure():
    """Publisher must reject _004 republication in GBK environment without crash."""
    repo_root = Path(__file__).parent.parent
    
    # Test via Python subprocess with GBK encoding
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "gbk"
    
    test_code = """
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
from scripts.publish_pit_membership_snapshot import publish_snapshot
result = publish_snapshot(Path.cwd(), '2026-07-17', _test_snapshot_id='pims_traderlens_v2_shsz_sw2021_pit_004')
print(f"Status: {result['status']}")
sys.exit(0 if result['status'] == 'unaccepted_invalid_publication' else 1)
"""
    
    result = subprocess.run(
        [sys.executable, "-c", test_code],
        cwd=repo_root,
        capture_output=True,
        env=env,
        timeout=60,
    )
    
    stdout = result.stdout.decode("gbk", errors="strict")
    stderr = result.stderr.decode("gbk", errors="strict")
    
    # _004 should be rejected
    assert result.returncode == 0, (result.returncode, stdout, stderr)
    assert "unaccepted_invalid_publication" in stdout
    assert "UnicodeEncodeError" not in stderr


@pytest.mark.parametrize(
    ("name", "src"),
    [
        ("SW2021_mismatch.parquet", "SW2014"),
        ("SW2014_mismatch.parquet", "SW2021"),
    ],
)
def test_taxonomy_src_and_filename_mismatch_rejects_before_parquet_read(name, src):
    """Manifest src and filename taxonomy must agree before any parquet read."""
    repo_root = Path(__file__).parent.parent

    with tempfile.TemporaryDirectory() as tmpdir:
        source_dir = Path(tmpdir) / "source"
        source_dir.mkdir()
        poison_path = source_dir / name
        poison_path.write_bytes(b"not a parquet file")

        import hashlib

        manifest_path = source_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "partitions": [
                        {
                            "name": name,
                            "src": src,
                            "row_count": 1,
                            "sha256": hashlib.sha256(poison_path.read_bytes()).hexdigest(),
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        result = publish_snapshot(
            repo_root=repo_root,
            snapshot_date="2026-07-16",
            _test_snapshot_id=f"preview_{src.lower()}_mismatch",
            _test_output_root=Path(tmpdir) / "output",
            _test_source_manifest=manifest_path,
        )

        assert result["status"] == "validation_failed"
        assert "taxonomy mismatch" in " ".join(result["errors"]).lower()
        assert not (Path(tmpdir) / "output" / f"preview_{src.lower()}_mismatch").exists()
