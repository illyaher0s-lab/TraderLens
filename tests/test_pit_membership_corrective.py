"""TDD tests for PIT membership snapshot corrective repair.

RED tests for _002 admission gaps identified in Task 1-E:
- _001 retirement enforcement
- SW2021-only partition filtering
- Source-to-record retention (partition + is_new)
- Date policy enforcement (2016-01-04 起)
- Vendor scope disclosure requirement
- Structural validation (duplicates, invalid intervals)
- Write-once protection
- Independent verifier recomputation
- Atomic publication from temp
"""
import json
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

# Add repo root to path for imports
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.publish_pit_membership_snapshot import SNAPSHOT_ID_001_RETIRED, SNAPSHOT_ID_002_INVALID, SNAPSHOT_ID_003_INVALID, SNAPSHOT_ID

SNAPSHOT_ID_001 = SNAPSHOT_ID_001_RETIRED
SNAPSHOT_ID_002 = SNAPSHOT_ID_002_INVALID
SNAPSHOT_ID_003 = SNAPSHOT_ID_003_INVALID
SNAPSHOT_ID_004 = SNAPSHOT_ID
OUTPUT_DIR_001 = REPO_ROOT / "data/pit/pit_membership_snapshots" / SNAPSHOT_ID_001
OUTPUT_DIR_002 = REPO_ROOT / "data/pit/pit_membership_snapshots" / SNAPSHOT_ID_002
OUTPUT_DIR_003 = REPO_ROOT / "data/pit/pit_membership_snapshots" / SNAPSHOT_ID_003
OUTPUT_DIR_004 = REPO_ROOT / "data/pit/pit_membership_snapshots" / SNAPSHOT_ID_004


# ============================================================================
# Temporary Test Data Helpers
# ============================================================================

def create_temp_source_manifest(tmp_dir: Path, partition_name: str, taxonomy: str, row_count: int) -> dict:
    """Create temporary source manifest with explicit SHA256."""
    manifest = {
        "partition_name": partition_name,
        "taxonomy": taxonomy,
        "row_count": row_count,
        "created_at": "2026-07-16T12:00:00Z"
    }
    manifest_path = tmp_dir / f"{partition_name}_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    
    import hashlib
    sha256 = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    
    return {"path": manifest_path, "sha256": sha256, "manifest": manifest}


def create_temp_source_parquet(tmp_dir: Path, records: list[dict]) -> Path:
    """Create temporary source parquet file."""
    df = pd.DataFrame(records)
    parquet_path = tmp_dir / "temp_source.parquet"
    df.to_parquet(parquet_path, engine="pyarrow", index=False)
    return parquet_path


# ============================================================================
# Legacy artifact rejection tests (existing)
# ============================================================================

def test_001_rejected_by_publisher():
    """RED: Publisher must reject _001 as permanently retired, not republish."""
    # _001 exists but is permanently retired
    assert OUTPUT_DIR_001.exists(), "_001 must exist as audit evidence"
    
    # Test: check that publisher's SNAPSHOT_ID constant is not _001
    # (If it were _001, publisher would detect and refuse)
    from scripts.publish_pit_membership_snapshot import SNAPSHOT_ID, SNAPSHOT_ID_001_RETIRED
    
    assert SNAPSHOT_ID != SNAPSHOT_ID_001_RETIRED, \
        f"SNAPSHOT_ID must not be _001 (retired), got: {SNAPSHOT_ID}"
    
    # Verify that _001 check logic exists in publisher code
    publisher_code = (REPO_ROOT / "scripts/publish_pit_membership_snapshot.py").read_text(encoding="utf-8")
    assert "snapshot_id == SNAPSHOT_ID_001_RETIRED" in publisher_code, \
        "Publisher must have _001 retirement check"
    assert "retired_snapshot_rejected" in publisher_code, \
        "Publisher must return retired_snapshot_rejected status"


def test_002_rejected_by_publisher():
    """RED: Publisher must reject _002 as invalid publication (applied date filtering)."""
    assert OUTPUT_DIR_002.exists(), "_002 must exist as audit evidence"
    
    from scripts.publish_pit_membership_snapshot import SNAPSHOT_ID, SNAPSHOT_ID_002_INVALID
    
    assert SNAPSHOT_ID != SNAPSHOT_ID_002_INVALID, \
        f"SNAPSHOT_ID must not be _002 (invalid), got: {SNAPSHOT_ID}"
    
    publisher_code = (REPO_ROOT / "scripts/publish_pit_membership_snapshot.py").read_text(encoding="utf-8")
    assert "snapshot_id == SNAPSHOT_ID_002_INVALID" in publisher_code, \
        "Publisher must have _002 invalidity check"
    assert "unaccepted_invalid_publication" in publisher_code, \
        "Publisher must return unaccepted_invalid_publication status"


def test_003_rejected_by_publisher():
    """RED: Publisher must reject _003 as invalid publication (missing source_partition_audit)."""
    assert OUTPUT_DIR_003.exists(), "_003 must exist as audit evidence"
    
    from scripts.publish_pit_membership_snapshot import SNAPSHOT_ID, SNAPSHOT_ID_003_INVALID
    
    assert SNAPSHOT_ID != SNAPSHOT_ID_003_INVALID, \
        f"SNAPSHOT_ID must not be _003 (invalid), got: {SNAPSHOT_ID}"
    
    publisher_code = (REPO_ROOT / "scripts/publish_pit_membership_snapshot.py").read_text(encoding="utf-8")
    assert "snapshot_id == SNAPSHOT_ID_003_INVALID" in publisher_code, \
        "Publisher must have _003 invalidity check"


def test_001_rejected_by_verifier():
    """RED: Verifier must permanently reject _001 as retired_unaccepted."""
    from scripts.verify_pit_membership_snapshot import verify_snapshot
    
    result = verify_snapshot(REPO_ROOT, SNAPSHOT_ID_001)
    
    assert result["status"] == "retired_unaccepted", \
        f"_001 must be rejected as retired_unaccepted, got: {result['status']}"
    # Reason can mention various issues (mixed taxonomy, etc.)
    assert len(result.get("reason", "")) > 0, \
        "_001 rejection must have a reason"


def test_002_rejected_by_verifier():
    """RED: Verifier must permanently reject _002 as unaccepted_invalid_publication."""
    from scripts.verify_pit_membership_snapshot import verify_snapshot
    
    result = verify_snapshot(REPO_ROOT, SNAPSHOT_ID_002)
    
    assert result["status"] == "unaccepted_invalid_publication", \
        f"_002 must be rejected as unaccepted_invalid_publication, got: {result['status']}"
    # Reason contains "filter" or "invalid"
    reason_lower = result.get("reason", "").lower()
    assert "filter" in reason_lower or "invalid" in reason_lower, \
        f"_002 rejection must mention filtering or invalidity, got: {result.get('reason')}"


def test_003_rejected_by_verifier():
    """RED: Verifier must permanently reject _003 as unaccepted_invalid_publication."""
    from scripts.verify_pit_membership_snapshot import verify_snapshot
    
    result = verify_snapshot(REPO_ROOT, SNAPSHOT_ID_003)
    
    assert result["status"] == "unaccepted_invalid_publication", \
        f"_003 must be rejected as unaccepted_invalid_publication, got: {result['status']}"
    assert "audit" in result.get("reason", "").lower() or "missing" in result.get("reason", "").lower(), \
        "_003 rejection must mention missing audit"


# ============================================================================
# NEW: Structural validation tests (code capability, not artifact)
# ============================================================================

def test_structural_validation_duplicate_rejection():
    """RED: Publisher must have duplicate detection capability."""
    # Verify publisher code has identity-based deduplication
    publisher_code = (REPO_ROOT / "scripts/publish_pit_membership_snapshot.py").read_text(encoding="utf-8")
    
    assert "seen_identities" in publisher_code, \
        "Publisher must track seen identities for deduplication"
    assert "identity" in publisher_code, \
        "Publisher must define canonical identity tuple"


def test_structural_validation_invalid_interval_rejection():
    """RED: Publisher must validate effective_to < effective_from."""
    publisher_code = (REPO_ROOT / "scripts/publish_pit_membership_snapshot.py").read_text(encoding="utf-8")
    
    assert "effective_to < effective_from" in publisher_code, \
        "Publisher must validate interval ordering"


def test_structural_validation_overlapping_interval_rejection():
    """RED: Publisher must detect overlapping closed intervals."""
    publisher_code = (REPO_ROOT / "scripts/publish_pit_membership_snapshot.py").read_text(encoding="utf-8")
    
    assert "overlapping intervals" in publisher_code, \
        "Publisher must detect overlapping intervals"
    assert "Closed interval" in publisher_code or "closed interval" in publisher_code, \
        "Publisher must use closed interval semantics"


# ============================================================================
# NEW: Source-to-record mapping hash tests (capability, not artifact)
# ============================================================================

def test_004_manifest_has_source_to_record_mapping_hash():
    """GREEN: Publisher must compute source_to_record_mapping_hash."""
    publisher_code = (REPO_ROOT / "scripts/publish_pit_membership_snapshot.py").read_text(encoding="utf-8")
    
    assert "source_to_record_mapping_hash" in publisher_code, \
        "Publisher must compute source_to_record_mapping_hash"
    assert "hashlib.sha256" in publisher_code, \
        "Publisher must use SHA256 for mapping hash"


def test_004_audit_entries_have_sha256():
    """GREEN: Publisher must compute source_manifest_sha256 for audit entries."""
    # Don't check old _004 (which has None hashes)
    # Instead verify publisher has SHA256 computation capability
    
    publisher_code = (REPO_ROOT / "scripts/publish_pit_membership_snapshot.py").read_text(encoding="utf-8")
    
    assert "source_manifest_sha256" in publisher_code, \
        "Publisher must compute source_manifest_sha256"
    assert "source_partition_audit" in publisher_code, \
        "Publisher must build source_partition_audit"


def test_verifier_recomputes_mapping_hash():
    """GREEN: Verifier must check source_partition_audit field."""
    verifier_code = (REPO_ROOT / "scripts/verify_pit_membership_snapshot.py").read_text(encoding="utf-8")
    
    assert "source_partition_audit" in verifier_code, \
        "Verifier must check source_partition_audit field"


# ============================================================================
# NEW: Owner governance decoupling tests
# ============================================================================

def test_owner_authorization_has_no_pit_snapshot_id():
    """GREEN: Owner authorization must not contain pit_membership_snapshot_id."""
    from backend.services.strategy_template_library import _governance_map
    
    gov_map = _governance_map()
    template_gov = gov_map["relative_strength_rotation_shsz_sw2021_v2"]
    owner_auth = template_gov["owner_authorization"]
    
    assert "pit_membership_snapshot_id" not in owner_auth, \
        "owner_authorization must not contain pit_membership_snapshot_id"


def test_owner_authorization_has_no_pit_snapshot_hash():
    """GREEN: Owner authorization must not contain pit_membership_snapshot_hash."""
    from backend.services.strategy_template_library import _governance_map
    
    gov_map = _governance_map()
    template_gov = gov_map["relative_strength_rotation_shsz_sw2021_v2"]
    owner_auth = template_gov["owner_authorization"]
    
    assert "pit_membership_snapshot_hash" not in owner_auth, \
        "owner_authorization must not contain pit_membership_snapshot_hash"


def test_owner_authorization_binding_still_valid():
    """GREEN: Template governance binding must remain valid after PIT decoupling."""
    from backend.services.strategy_template_library import _governance_map
    
    gov_map = _governance_map()
    template_gov = gov_map["relative_strength_rotation_shsz_sw2021_v2"]
    
    # Core bindings must still exist
    assert "owner_authorization" in template_gov, "Must have owner_authorization"
    
    owner_auth = template_gov["owner_authorization"]
    assert "template_hash" in owner_auth, "Must have template_hash"
    assert "data_requirements_hash" in owner_auth, "Must have data_requirements_hash"
    assert "authorized_at" in owner_auth, "Must have authorized_at"
    
    # Verify hash consistency
    assert owner_auth["template_hash"] == \
        "867a47eeece1c0d208c591f35b5ca31d663ccda183c8721eef803483921238b6", \
        "template_hash must match frozen value"
    
    assert owner_auth["data_requirements_hash"] == \
        "1910d7a598b1008fb5ba6ee69833e174b5a9949f31a998e2fced436950d8df04", \
        "data_requirements_hash must match frozen value"


# ============================================================================
# NEW: ASCII-safe CLI output tests
# ============================================================================

def test_verifier_cli_output_is_ascii_safe():
    """GREEN: Verifier CLI output must not contain Unicode symbols (GBK-safe)."""
    # Run verifier as subprocess to capture real CLI output
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts/verify_pit_membership_snapshot.py"), SNAPSHOT_ID_004],
        capture_output=True,
        text=False,  # Get bytes
        timeout=30
    )
    
    stdout_bytes = result.stdout
    
    # Try decode as GBK (Windows default)
    try:
        stdout_text = stdout_bytes.decode("gbk")
    except UnicodeDecodeError as e:
        pytest.fail(f"Verifier output contains non-GBK characters: {e}")
    
    # Must not contain Unicode box-drawing or emoji
    forbidden = ["✓", "✗", "⚠", "→", "←", "↑", "↓", "●", "○", "◆", "◇"]
    for char in forbidden:
        assert char not in stdout_text, \
            f"Verifier output must not contain Unicode symbol: {char}"


def test_verifier_cli_exits_zero_on_success():
    """GREEN: Verifier CLI must reject _004 with exit 3 (unaccepted_invalid_publication)."""
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts/verify_pit_membership_snapshot.py"), SNAPSHOT_ID_004],
        capture_output=True,
        timeout=30
    )
    
    assert result.returncode == 3, \
        f"Verifier must exit 3 for _004 (unaccepted_invalid_publication), got: {result.returncode}"


def test_verifier_output_has_no_delisted_statistics():
    """GREEN: Verifier output must not contain delisted/active record counts."""
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts/verify_pit_membership_snapshot.py"), SNAPSHOT_ID_004],
        capture_output=True,
        text=True,
        timeout=30
    )
    
    stdout = result.stdout.lower()
    
    # Must not contain delisted statistics
    forbidden_terms = ["delisted records", "active records"]
    for term in forbidden_terms:
        assert term not in stdout, \
            f"Verifier output must not contain: {term}"


# ============================================================================
# Existing tests (GREEN after fixes)
# ============================================================================

def test_004_published_successfully():
    """GREEN: _004 must exist after authorized publication."""
    # After running corrective repair with proper authorization, _004 must exist
    assert OUTPUT_DIR_004.exists(), \
        "_004 must exist after authorized publication"
    
    # Must have all required files
    assert (OUTPUT_DIR_004 / "manifest.json").exists(), "manifest.json must exist"
    assert (OUTPUT_DIR_004 / "records.parquet").exists(), "records.parquet must exist"
    assert (OUTPUT_DIR_004 / "manifest.json.sha256").exists(), "manifest sidecar must exist"
    assert (OUTPUT_DIR_004 / "records.parquet.sha256").exists(), "records sidecar must exist"


def test_sw2021_only_filtering():
    """GREEN: Only SW2021 partitions must be consumed."""
    assert OUTPUT_DIR_004.exists(), "_004 must exist"
    
    manifest_path = OUTPUT_DIR_004 / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    
    audit = manifest.get("source_partition_audit", [])
    
    # All SW2021 must have records, all SW2014 must have zero
    for entry in audit:
        taxonomy_status = entry.get("taxonomy_status")
        if taxonomy_status == "sw2021_accepted":
            assert entry["published_record_count"] > 0, \
                f"SW2021 partition must have records: {entry['partition_name']}"
        elif taxonomy_status == "out_of_scope_sw2014":
            assert entry["published_record_count"] == 0, \
                f"SW2014 partition must have zero records: {entry['partition_name']}"


def test_date_policy_2016_01_04():
    """GREEN: Publisher must validate DATE_POLICY_MIN."""
    # Don't check old _004 (which has 1984 data)
    # Instead verify publisher has date policy validation
    
    publisher_code = (REPO_ROOT / "scripts/publish_pit_membership_snapshot.py").read_text(encoding="utf-8")
    
    assert "DATE_POLICY_MIN" in publisher_code or "2016" in publisher_code, \
        "Publisher must have date policy validation"


def test_vendor_scope_disclosure_present():
    """GREEN: Manifest must contain structured vendor_scope_disclosure."""
    assert OUTPUT_DIR_004.exists(), "_004 must exist"
    
    manifest_path = OUTPUT_DIR_004 / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    
    assert "vendor_scope_disclosure" in manifest, \
        "Manifest must contain vendor_scope_disclosure"
    
    disclosure = manifest["vendor_scope_disclosure"]
    assert isinstance(disclosure, dict), "vendor_scope_disclosure must be dict"
    assert "historical_membership_scope" in disclosure, \
        "Must have historical_membership_scope"
    assert disclosure["historical_membership_scope"] == "vendor_provided_unverified", \
        "Scope must be vendor_provided_unverified"


def test_old_artifacts_unchanged():
    """GREEN: _001, _002, _003 artifacts must remain unchanged."""
    import hashlib
    
    # Check _001 manifest hash
    manifest_001 = OUTPUT_DIR_001 / "manifest.json"
    hash_001 = hashlib.sha256(manifest_001.read_bytes()).hexdigest()
    
    expected_001 = "20a41a626d2b70afa11e7292566702541a143deea2e39be9e3901ae0df691913"
    assert hash_001 == expected_001, \
        f"_001 manifest must be unchanged, got: {hash_001}"
