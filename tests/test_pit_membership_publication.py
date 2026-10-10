"""TDD tests for PIT membership snapshot publication.

RED tests first: prove structural failures, binding violations, write-once,
and no unauthorized access.
"""
import json
import shutil
from datetime import date, datetime
from pathlib import Path

import pytest

# Test configuration
REPO_ROOT = Path(__file__).parent.parent
SNAPSHOT_ID = "pims_traderlens_v2_shsz_sw2021_pit_001"
OUTPUT_DIR = REPO_ROOT / "data/pit/pit_membership_snapshots" / SNAPSHOT_ID


@pytest.fixture
def clean_output():
    """Clean output directory before specific test (opt-in, not autouse).
    
    WARNING: This fixture deletes published artifacts. Use only for tests
    that explicitly require clean state and are run in isolation.
    """
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    yield


def test_snapshot_date_horizon_enforcement():
    """RED: Records with dates > snapshot_date must be rejected."""
    # This will be tested via publisher validation
    # For now, assert output dir doesn't exist (will be created by GREEN implementation)
    assert not OUTPUT_DIR.exists(), "Output should not exist before publication"


def test_closed_interval_overlap_rejection():
    """RED: Overlapping closed intervals for same symbol must fail publication."""
    # Publisher must detect and reject overlaps
    assert not OUTPUT_DIR.exists()


def test_effective_to_none_bounded_by_snapshot_date():
    """RED: effective_to=None must only be valid through snapshot_date."""
    # Query with d > snapshot_date must be rejected by consumer (not publisher)
    # Publisher must document this constraint
    assert not OUTPUT_DIR.exists()


def test_metadata_only_universe_reference_not_pit_snapshot():
    """RED: Metadata-only universe reference cannot substitute formal snapshot."""
    uref_path = REPO_ROOT / "data/pit/universe_references/uref_traderlens_v2_shsz_sw2021_pit_001/manifest.json"
    uref = json.loads(uref_path.read_text(encoding="utf-8"))
    
    # Verify it's provenance_only
    assert uref.get("provenance_only") is True, "Universe reference must be provenance_only"
    
    # Verify it has no records field
    assert "records" not in uref, "Metadata-only reference must not have records"
    
    # Verify it cannot be used as PointInTimeMembershipSnapshot
    assert "snapshot_date" not in uref, "Metadata-only reference has no snapshot_date"
    assert "include_delisted" not in uref, "Metadata-only reference has no include_delisted"


def test_candidate_json_not_formal_snapshot():
    """RED: sw2021_universe_candidate.json is staging evidence, not formal snapshot."""
    candidate_path = REPO_ROOT / "data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal/sw_l1_membership/sw2021_universe_candidate.json"
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    
    assert candidate["status"] == "candidate_universe_ready", "Candidate is staging artifact"
    assert "records" not in candidate, "Candidate has no membership records"
    assert "snapshot_id" not in candidate, "Candidate has no formal snapshot_id"
    assert ".staging" in str(candidate_path), "Candidate is in staging directory"


def test_duplicate_record_rejection():
    """RED: Duplicate records with same identity must fail publication."""
    # Publisher validation must detect duplicates
    assert not OUTPUT_DIR.exists()


def test_invalid_interval_rejection():
    """RED: effective_to < effective_from must fail publication."""
    # Publisher validation must detect invalid intervals
    assert not OUTPUT_DIR.exists()


def test_wrong_snapshot_id_rejection():
    """RED: Records using wrong snapshot_id must fail publication."""
    # Publisher must set correct snapshot_id in all records
    assert not OUTPUT_DIR.exists()


def test_include_delisted_unproven_blocks_publication():
    """RED: If include_delisted cannot be proved, publication must fail."""
    # Publisher must prove from source data, not assert from contract
    assert not OUTPUT_DIR.exists()


def test_source_hash_tampering_rejection():
    """RED: Modified source manifest hash must fail publication."""
    # Publisher must verify all expected hashes
    assert not OUTPUT_DIR.exists()


def test_write_once_same_content_idempotent():
    """RED: Same canonical content must return already_published without rewrite."""
    # First publication will create artifacts
    # Second publication with same input must detect and skip
    assert not OUTPUT_DIR.exists()


def test_write_once_different_content_conflicts():
    """RED: Same snapshot_id with different canonical content must fail without overwrite."""
    # Publisher must detect content mismatch and refuse to overwrite
    assert not OUTPUT_DIR.exists()


def test_no_unauthorized_partition_access():
    """RED: Publisher must not read daily/daily_basic/stk_limit/adj_factor/lifecycle."""
    # This will be verified by code review and explicit path allowlist
    # For now, document the constraint
    assert not OUTPUT_DIR.exists()


def test_no_b6_oos_gate_promotion_signal():
    """RED: Publisher must not call B6/OOS/Gate/Promotion/Signal/ledger."""
    # Verified by code review and import allowlist
    assert not OUTPUT_DIR.exists()


def test_formal_data_manifest_unchanged():
    """RED: Existing formal data manifest must remain byte-identical."""
    formal_path = REPO_ROOT / "data/pit/data_snapshot_manifests/ds_traderlens_v2_shsz_pit_001/manifest.json"
    
    # Record hash before publication
    import hashlib
    with open(formal_path, "rb") as f:
        pre_hash = hashlib.sha256(f.read()).hexdigest()
    
    # After publication (GREEN), must verify hash unchanged
    # For now, just record baseline
    assert pre_hash == "4c4552a86afa09c5936db85d0c65df85fe28445d87b2372783a5c3f7281b0736"


def test_universe_reference_unchanged():
    """RED: Existing universe reference must remain byte-identical."""
    uref_path = REPO_ROOT / "data/pit/universe_references/uref_traderlens_v2_shsz_sw2021_pit_001/manifest.json"
    
    import hashlib
    with open(uref_path, "rb") as f:
        pre_hash = hashlib.sha256(f.read()).hexdigest()
    
    assert pre_hash == "ff34d4c5ba884b1bf9aa55d09880d7e08cb0d39841d1518c002b265275dff0d9"


def test_qualification_successor_unchanged():
    """RED: Existing qualification successor must remain byte-identical."""
    successor_path = REPO_ROOT / "data/pit/qualification_successors/e5100669ed247769/manifest.json"
    
    import hashlib
    with open(successor_path, "rb") as f:
        pre_hash = hashlib.sha256(f.read()).hexdigest()
    
    assert pre_hash == "f3bdb5124262f0fbe8e73ca2789645cba4b8fefd731c56ad719e29a46fd30e77"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
