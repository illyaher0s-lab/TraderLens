"""Test verifier independent recomputation of audit hashes."""
import tempfile
import json
import hashlib
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.publish_pit_membership_snapshot import publish_snapshot
from scripts.verify_pit_membership_snapshot import verify_snapshot


def sha256_file(path: Path) -> str:
    """Compute SHA-256 of file."""
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def test_verifier_recomputes_canonical_identity_hashes():
    """Verifier must independently recompute canonical_record_identity_hash from records.parquet."""
    repo_root = Path(__file__).parent.parent
    
    with tempfile.TemporaryDirectory() as tmpdir:
        result = publish_snapshot(
            repo_root=repo_root,
            snapshot_date="2026-07-16",
            _test_snapshot_id="preview_verify_identity",
            _test_output_root=Path(tmpdir),
        )
        
        snapshot_dir = Path(tmpdir) / "preview_verify_identity"
        
        # Clean verification must pass
        verify_result = verify_snapshot(repo_root, "preview_verify_identity", snapshots_root=Path(tmpdir))
        assert verify_result["status"] == "verified"
        
        # Tamper with canonical_record_identity_hash
        manifest_path = snapshot_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        
        original_hash = None
        for entry in manifest["source_partition_audit"]:
            if entry["taxonomy_status"] == "sw2021_accepted" and entry["published_record_count"] > 0:
                original_hash = entry["canonical_record_identity_hash"]
                entry["canonical_record_identity_hash"] = "f" * 64
                break
        
        assert original_hash is not None, "No SW2021 partition found"
        manifest_path.write_text(json.dumps(manifest, indent=2))
        
        # Update sidecar to bypass sidecar check
        new_hash = sha256_file(manifest_path)
        (snapshot_dir / "manifest.json.sha256").write_text(f"{new_hash}  manifest.json\n")
        
        # Verifier must detect via independent recomputation
        verify_result = verify_snapshot(repo_root, "preview_verify_identity", snapshots_root=Path(tmpdir))
        assert verify_result["status"] == "failed", f"Expected failed, got {verify_result['status']}"
        errors_str = " ".join(verify_result.get("errors", []))
        assert "canonical_record_identity_hash" in errors_str.lower(), \
            f"Expected canonical_record_identity_hash error, got: {errors_str}"


def test_verifier_recomputes_mapping_hash():
    """Verifier must independently recompute source_to_record_mapping_hash from audit."""
    repo_root = Path(__file__).parent.parent
    
    with tempfile.TemporaryDirectory() as tmpdir:
        result = publish_snapshot(
            repo_root=repo_root,
            snapshot_date="2026-07-16",
            _test_snapshot_id="preview_verify_mapping",
            _test_output_root=Path(tmpdir),
        )
        
        snapshot_dir = Path(tmpdir) / "preview_verify_mapping"
        
        # Tamper with mapping hash
        manifest_path = snapshot_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        original_mapping_hash = manifest["source_to_record_mapping_hash"]
        manifest["source_to_record_mapping_hash"] = "a" * 64
        manifest_path.write_text(json.dumps(manifest, indent=2))
        
        # Update sidecar
        new_hash = sha256_file(manifest_path)
        (snapshot_dir / "manifest.json.sha256").write_text(f"{new_hash}  manifest.json\n")
        
        # Verifier must detect
        verify_result = verify_snapshot(repo_root, "preview_verify_mapping", snapshots_root=Path(tmpdir))
        assert verify_result["status"] == "failed"
        errors_str = " ".join(verify_result.get("errors", []))
        assert "mapping" in errors_str.lower() or "source_to_record" in errors_str.lower(), \
            f"Expected mapping hash error, got: {errors_str}"


def test_verifier_recomputes_record_counts():
    """Verifier must independently verify published_record_count from records.parquet."""
    repo_root = Path(__file__).parent.parent
    
    with tempfile.TemporaryDirectory() as tmpdir:
        result = publish_snapshot(
            repo_root=repo_root,
            snapshot_date="2026-07-16",
            _test_snapshot_id="preview_verify_counts",
            _test_output_root=Path(tmpdir),
        )
        
        snapshot_dir = Path(tmpdir) / "preview_verify_counts"
        
        # Tamper with published_record_count
        manifest_path = snapshot_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        
        tampered = False
        for entry in manifest["source_partition_audit"]:
            if entry["taxonomy_status"] == "sw2021_accepted" and entry["published_record_count"] > 10:
                entry["published_record_count"] += 100  # Inflate count
                tampered = True
                break
        
        assert tampered, "No suitable partition to tamper"
        manifest_path.write_text(json.dumps(manifest, indent=2))
        
        # Update sidecar
        new_hash = sha256_file(manifest_path)
        (snapshot_dir / "manifest.json.sha256").write_text(f"{new_hash}  manifest.json\n")
        
        # Verifier must detect
        verify_result = verify_snapshot(repo_root, "preview_verify_counts", snapshots_root=Path(tmpdir))
        assert verify_result["status"] == "failed"
        errors_str = " ".join(verify_result.get("errors", []))
        assert "count" in errors_str.lower() or "published_record" in errors_str.lower(), \
            f"Expected count mismatch error, got: {errors_str}"
