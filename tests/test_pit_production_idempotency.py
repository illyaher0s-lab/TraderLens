"""Test production input idempotency with real 61 SW2021 + 53 SW2014 sources."""
import tempfile
import json
import hashlib
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.publish_pit_membership_snapshot import publish_snapshot


def sha256_file(path: Path) -> str:
    """Compute SHA-256 of file."""
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def test_production_input_idempotency():
    """Real 61+53 sources: first publish succeeds, second returns already_published."""
    repo_root = Path(__file__).parent.parent
    
    with tempfile.TemporaryDirectory() as tmpdir:
        output_root = Path(tmpdir)
        
        # First publish with real sources
        result1 = publish_snapshot(
            repo_root=repo_root,
            snapshot_date="2026-07-16",
            _test_snapshot_id="preview_idempotency",
            _test_output_root=output_root,
        )
        
        assert result1["status"] == "published", f"First publish failed: {result1}"
        
        # Second publish with identical inputs must return already_published
        result2 = publish_snapshot(
            repo_root=repo_root,
            snapshot_date="2026-07-16",
            _test_snapshot_id="preview_idempotency",
            _test_output_root=output_root,
        )
        
        assert result2["status"] == "already_published", \
            f"Expected already_published, got {result2['status']}"


def test_content_conflict_blocks_already_published():
    """Tampering with artifact before republish must trigger content_conflict, not already_published."""
    repo_root = Path(__file__).parent.parent
    
    with tempfile.TemporaryDirectory() as tmpdir:
        output_root = Path(tmpdir)
        
        # First publish
        result1 = publish_snapshot(
            repo_root=repo_root,
            snapshot_date="2026-07-16",
            _test_snapshot_id="preview_conflict",
            _test_output_root=output_root,
        )
        
        assert result1["status"] == "published"
        
        # Tamper with manifest
        snapshot_dir = output_root / "preview_conflict"
        manifest_path = snapshot_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        
        # Tamper with audit
        for entry in manifest["source_partition_audit"]:
            if entry["taxonomy_status"] == "sw2021_accepted":
                entry["published_record_count"] += 1  # Corrupt count
                break
        
        manifest_path.write_text(json.dumps(manifest, indent=2))
        
        # Update sidecar to match tampered manifest
        new_hash = sha256_file(manifest_path)
        (snapshot_dir / "manifest.json.sha256").write_text(f"{new_hash}  manifest.json\n")
        
        # Second publish must detect content_conflict, not return already_published
        result2 = publish_snapshot(
            repo_root=repo_root,
            snapshot_date="2026-07-16",
            _test_snapshot_id="preview_conflict",
            _test_output_root=output_root,
        )
        
        assert result2["status"] in {"content_conflict", "verification_failed", "failed"}, \
            f"Expected content_conflict, got {result2['status']}: {result2.get('message', '')}"
        assert result2["status"] != "already_published", \
            "Tampered artifact must not return already_published"


def test_sidecar_tampering_blocks_already_published():
    """Tampering with sidecar (without manifest change) must block already_published."""
    repo_root = Path(__file__).parent.parent
    
    with tempfile.TemporaryDirectory() as tmpdir:
        output_root = Path(tmpdir)
        
        # First publish
        result1 = publish_snapshot(
            repo_root=repo_root,
            snapshot_date="2026-07-16",
            _test_snapshot_id="preview_sidecar",
            _test_output_root=output_root,
        )
        
        assert result1["status"] == "published"
        
        # Tamper with sidecar only
        snapshot_dir = output_root / "preview_sidecar"
        sidecar_path = snapshot_dir / "manifest.json.sha256"
        sidecar_path.write_text("0" * 64 + "  manifest.json\n")
        
        # Second publish must detect conflict
        result2 = publish_snapshot(
            repo_root=repo_root,
            snapshot_date="2026-07-16",
            _test_snapshot_id="preview_sidecar",
            _test_output_root=output_root,
        )
        
        assert result2["status"] in {"content_conflict", "verification_failed", "tampered", "failed"}
        assert result2["status"] != "already_published"
