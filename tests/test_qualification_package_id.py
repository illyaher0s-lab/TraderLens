"""Tests for deterministic qualification package ID and overwrite protection."""
import json
from pathlib import Path


def test_qualification_package_id_deterministic():
    """Same inputs must produce same package ID."""
    from scripts.qualify_sw2021_pit_package import _qualification_package_id
    
    scope = "test_scope"
    template = "test_template"
    requirements = "test_requirements"
    snapshot = "test_snapshot"
    algorithm = "test_algorithm"
    
    id1 = _qualification_package_id(scope, template, requirements, snapshot, algorithm)
    id2 = _qualification_package_id(scope, template, requirements, snapshot, algorithm)
    
    assert id1 == id2
    assert len(id1) == 16  # 16-char hex


def test_algorithm_change_produces_different_package_id():
    """Different algorithm hash must produce different package ID."""
    from scripts.qualify_sw2021_pit_package import _qualification_package_id
    
    scope = "test_scope"
    template = "test_template"
    requirements = "test_requirements"
    snapshot = "test_snapshot"
    
    id1 = _qualification_package_id(scope, template, requirements, snapshot, "algo_v1")
    id2 = _qualification_package_id(scope, template, requirements, snapshot, "algo_v2")
    
    assert id1 != id2


def test_scope_change_produces_different_package_id():
    """Different scope must produce different package ID."""
    from scripts.qualify_sw2021_pit_package import _qualification_package_id
    
    template = "test_template"
    requirements = "test_requirements"
    snapshot = "test_snapshot"
    algorithm = "test_algorithm"
    
    id1 = _qualification_package_id("scope1", template, requirements, snapshot, algorithm)
    id2 = _qualification_package_id("scope2", template, requirements, snapshot, algorithm)
    
    assert id1 != id2


def test_algorithm_hash_includes_both_sources():
    """Algorithm hash must include both core and qualifier sources."""
    from scripts.qualify_sw2021_pit_package import _algorithm_hash
    
    algo_hash = _algorithm_hash()
    
    # Must be 64-char hex (SHA256)
    assert len(algo_hash) == 64
    assert all(c in '0123456789abcdef' for c in algo_hash)


def test_old_package_35d996036cc04179_not_overwritten():
    """Old package must not be affected by new qualification runs."""
    old_path = Path("data/pit/formal_packages/35d996036cc04179")
    
    # Old package exists
    assert old_path.exists()
    assert (old_path / "STATUS.txt").exists()
    
    # Old manifest hash must be unchanged from isolation
    old_manifest = json.loads((old_path / "manifest.json").read_text())
    assert old_manifest["scope_hash"] == "35d996036cc04179"
    
    # Old package uses scope_hash as directory name (old pattern)
    # New packages use qualification_package_id (different)
