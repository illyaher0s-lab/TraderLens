"""Test source-to-record mapping hash computation and verification."""
import tempfile
import json
import hashlib
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.publish_pit_membership_snapshot import publish_snapshot


def test_sw2021_partition_has_canonical_identity_hash():
    """Each SW2021 partition audit must include canonical_record_identity_hash."""
    repo_root = Path(__file__).parent.parent
    
    with tempfile.TemporaryDirectory() as tmpdir:
        result = publish_snapshot(
            repo_root=repo_root,
            snapshot_date="2026-07-16",
            _test_snapshot_id="preview_mapping",
            _test_output_root=Path(tmpdir),
        )
        
        assert result["status"] == "published"
        
        manifest_path = Path(tmpdir) / "preview_mapping" / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        audit = manifest["source_partition_audit"]
        
        sw2021 = [e for e in audit if e["taxonomy_status"] == "sw2021_accepted"]
        assert len(sw2021) == 61, f"Expected 61 SW2021, got {len(sw2021)}"
        
        # Each SW2021 partition must have canonical_record_identity_hash
        for entry in sw2021:
            assert "canonical_record_identity_hash" in entry, \
                f"Missing canonical_record_identity_hash in {entry['partition_name']}"
            assert entry["canonical_record_identity_hash"] is not None
            assert len(entry["canonical_record_identity_hash"]) == 64  # SHA-256


def test_source_to_record_mapping_hash_deterministic():
    """source_to_record_mapping_hash must be deterministic from audit payload."""
    repo_root = Path(__file__).parent.parent
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Publish twice to same directory
        result1 = publish_snapshot(
            repo_root=repo_root,
            snapshot_date="2026-07-16",
            _test_snapshot_id="preview_det1",
            _test_output_root=Path(tmpdir),
        )
        
        result1_path = Path(tmpdir) / "preview_det1" / "manifest.json"
        manifest1 = json.loads(result1_path.read_text())
        hash1 = manifest1["source_to_record_mapping_hash"]
        
        result2 = publish_snapshot(
            repo_root=repo_root,
            snapshot_date="2026-07-16",
            _test_snapshot_id="preview_det2",
            _test_output_root=Path(tmpdir),
        )
        
        result2_path = Path(tmpdir) / "preview_det2" / "manifest.json"
        manifest2 = json.loads(result2_path.read_text())
        hash2 = manifest2["source_to_record_mapping_hash"]
        
        assert hash1 == hash2, f"Mapping hash not deterministic: {hash1} vs {hash2}"


def test_mapping_hash_computed_from_sorted_audit():
    """Mapping hash must be SHA-256 of sorted canonical audit JSON."""
    repo_root = Path(__file__).parent.parent
    
    with tempfile.TemporaryDirectory() as tmpdir:
        result = publish_snapshot(
            repo_root=repo_root,
            snapshot_date="2026-07-16",
            _test_snapshot_id="preview_sorted",
            _test_output_root=Path(tmpdir),
        )
        
        manifest_path = Path(tmpdir) / "preview_sorted" / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        
        # Recompute hash from audit
        audit = manifest["source_partition_audit"]
        canonical_payload = json.dumps(audit, sort_keys=True, separators=(",", ":"))
        computed_hash = hashlib.sha256(canonical_payload.encode()).hexdigest()
        
        assert manifest["source_to_record_mapping_hash"] == computed_hash, \
            f"Mapping hash mismatch: manifest={manifest['source_to_record_mapping_hash']}, computed={computed_hash}"
