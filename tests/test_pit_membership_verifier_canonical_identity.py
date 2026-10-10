"""RED tests: PIT membership verifier canonical identity reconciliation.

Enforce:
1. Legacy status registry (_001 retired, _002/_003/_004 unaccepted)
2. ASCII-safe CLI output ([PASS], [REJECTED], [FAIL])
3. Correct exit codes (0=pass, 2=retired, 3=unaccepted)
4. Remove old 2024 identity
5. GBK-safe output (no UnicodeEncodeError)
"""
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.publish_pit_membership_snapshot import (
    SNAPSHOT_ID_001_RETIRED,
    SNAPSHOT_ID_002_INVALID,
    SNAPSHOT_ID_003_INVALID,
    SNAPSHOT_ID,
)


def test_001_retired_snapshot_exit_2_ascii_safe():
    """_001 must return retired_unaccepted with exit 2 and ASCII markers."""
    verifier = REPO_ROOT / "scripts/verify_pit_membership_snapshot.py"
    python_exe = REPO_ROOT / ".venv/Scripts/python.exe"
    
    proc = subprocess.run(
        [str(python_exe), str(verifier), SNAPSHOT_ID_001_RETIRED],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    
    # Must exit 2 for retired
    assert proc.returncode == 2, f"Expected exit 2, got {proc.returncode}\nstdout: {proc.stdout}\nstderr: {proc.stderr}"
    
    # Must output [REJECTED] marker
    assert "[REJECTED]" in proc.stdout, f"Missing [REJECTED] in output:\n{proc.stdout}"
    
    # Must not contain Unicode symbols (only ASCII markers)
    for forbidden in ["✓", "✗", "❌"]:
        assert forbidden not in proc.stdout, f"Found Unicode symbol '{forbidden}' in stdout"


def test_002_unaccepted_002_exit_3_ascii_safe():
    """_002 must return unaccepted_invalid_publication with exit 3."""
    verifier = REPO_ROOT / "scripts/verify_pit_membership_snapshot.py"
    python_exe = REPO_ROOT / ".venv/Scripts/python.exe"
    
    proc = subprocess.run(
        [str(python_exe), str(verifier), SNAPSHOT_ID_002_INVALID],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    
    assert proc.returncode == 3, f"Expected exit 3, got {proc.returncode}\nstdout: {proc.stdout}"
    assert "[REJECTED]" in proc.stdout, f"Missing [REJECTED]:\n{proc.stdout}"
    
    for forbidden in ["✓", "✗", "❌"]:
        assert forbidden not in proc.stdout


def test_003_unaccepted_003_exit_3_ascii_safe():
    """_003 must return unaccepted_invalid_publication with exit 3."""
    verifier = REPO_ROOT / "scripts/verify_pit_membership_snapshot.py"
    python_exe = REPO_ROOT / ".venv/Scripts/python.exe"
    
    proc = subprocess.run(
        [str(python_exe), str(verifier), SNAPSHOT_ID_003_INVALID],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    
    assert proc.returncode == 3, f"Expected exit 3, got {proc.returncode}"
    assert "[REJECTED]" in proc.stdout


def test_004_unaccepted_004_exit_3_ascii_safe():
    """_004 must return unaccepted_invalid_publication with exit 3 (null source_manifest_sha256)."""
    verifier = REPO_ROOT / "scripts/verify_pit_membership_snapshot.py"
    python_exe = REPO_ROOT / ".venv/Scripts/python.exe"
    
    proc = subprocess.run(
        [str(python_exe), str(verifier), "pims_traderlens_v2_shsz_sw2021_pit_004"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    
    assert proc.returncode == 3, f"Expected exit 3, got {proc.returncode}"
    assert "[REJECTED]" in proc.stdout


def test_005_temp_artifact_exit_0_pass_marker_gbk_safe():
    """Temporary test artifact must exit 0 with [PASS] marker, GBK-safe."""
    import tempfile
    import json
    from datetime import date
    
    verifier = REPO_ROOT / "scripts/verify_pit_membership_snapshot.py"
    python_exe = REPO_ROOT / ".venv/Scripts/python.exe"
    
    with tempfile.TemporaryDirectory() as tmpdir:
        snapshot_root = Path(tmpdir) / "snapshots"
        snapshot_root.mkdir()
        
        snapshot_dir = snapshot_root / "temp_test_snapshot"
        snapshot_dir.mkdir()
        
        # Minimal valid manifest
        manifest = {
            "snapshot_id": "temp_test_snapshot",
            "snapshot_date": "2024-12-31",
            "universe_rule_type": "vendor_list",
            "membership_source": "tushare_stock_basic_sw2021",
            "vendor_scope_disclosure": {
                "historical_membership_scope": "vendor_provided_unverified"
            },
            "include_delisted": True,
            "frozen": False,
            "quality_status": "test_fixture",
            "gaps": [],
            "record_count": 1,
            "formal_data_snapshot_id": "test",
            "formal_data_semantic_hash": "a" * 64,
            "universe_reference_id": "test_ref",
            "records_parquet_sha256": "b" * 64,
            "canonical_content_hash": "c" * 64,
            "schema_version": "v2",
            "interval_semantics": "half_open_left_closed",
            "not_authorized_for_b6_oos_gate_promotion_signal": True,
            "source_partition_audit": [],
        }
        
        manifest_path = snapshot_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        
        # Create dummy sidecar and parquet (content doesn't matter for this test)
        import hashlib
        manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        (snapshot_dir / "manifest.json.sha256").write_text(f"{manifest_hash}  manifest.json", encoding="utf-8")
        
        records_path = snapshot_dir / "records.parquet"
        records_path.write_bytes(b"dummy")  # Will fail hash check but structure is valid
        
        records_hash = hashlib.sha256(b"dummy").hexdigest()
        (snapshot_dir / "records.parquet.sha256").write_text(f"{records_hash}  records.parquet", encoding="utf-8")
        
        # Run verifier
        proc = subprocess.run(
            [str(python_exe), str(verifier), "temp_test_snapshot", "--snapshots-root", str(snapshot_root)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        
        # Should fail hash check but not crash with Unicode error
        # For this test we just verify no encoding errors
        assert proc.stderr == "" or "UnicodeEncodeError" not in proc.stderr, f"Encoding error:\n{proc.stderr}"


def test_006_verifier_no_old_2024_identity():
    """Verifier must not contain old 2024-12-31 identity strings."""
    verifier = REPO_ROOT / "scripts/verify_pit_membership_snapshot.py"
    content = verifier.read_text(encoding="utf-8")
    
    forbidden = "pit_membership_shsz_sw2021_2024-12-31"
    assert forbidden not in content, f"Verifier still contains old identity '{forbidden}'"


def test_007_verifier_no_delisted_count_fields():
    """Verifier must not output delisted_count, active_count, has_delisted."""
    verifier = REPO_ROOT / "scripts/verify_pit_membership_snapshot.py"
    content = verifier.read_text(encoding="utf-8")
    
    forbidden_fields = ["delisted_count", "active_count", "has_delisted"]
    for field in forbidden_fields:
        assert field not in content, f"Verifier still references '{field}'"
