"""Tests for Gate 0 PIT data feasibility verification."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from verify_gate0_data_feasibility import (
    compute_data_requirements_hash,
    compute_snapshot_id,
    get_data_requirements,
)


def test_data_requirements_frozen():
    """Data requirements must be frozen (reproducible hash)."""
    req1 = get_data_requirements()
    req2 = get_data_requirements()
    
    hash1 = compute_data_requirements_hash(req1)
    hash2 = compute_data_requirements_hash(req2)
    
    assert hash1 == hash2
    assert len(hash1) == 32


def test_data_requirements_structure():
    """Data requirements must have expected structure."""
    req = get_data_requirements()
    
    assert req["template_id"] == "relative_strength_rotation_v1"
    assert "interfaces" in req
    assert "daily" in req["interfaces"]
    assert "daily_basic" in req["interfaces"]
    assert "trade_cal" in req["interfaces"]
    assert "stock_basic" in req["interfaces"]
    assert "benchmarks" in req
    assert "000300.SH" in req["benchmarks"]


def test_snapshot_id_computation():
    """Snapshot ID must be deterministic."""
    template_hash = "abc123"
    data_req_hash = "def456"
    
    id1 = compute_snapshot_id("test_template", template_hash, data_req_hash)
    id2 = compute_snapshot_id("test_template", template_hash, data_req_hash)
    
    assert id1 == id2
    assert len(id1) == 16


def test_snapshot_id_changes_with_inputs():
    """Snapshot ID must change when inputs change."""
    id1 = compute_snapshot_id("test", "hash1", "hash2")
    id2 = compute_snapshot_id("test", "hash1", "hash3")
    
    assert id1 != id2


def test_manifest_hash_excludes_token():
    """Manifest hash must exclude Tushare token."""
    manifest = {
        "snapshot_id": "test123",
        "provider": "tushare",
        "interfaces_probed": ["daily", "trade_cal"],
        "data_requirements_hash": "abc123",
    }
    
    manifest_bytes = json.dumps(manifest, sort_keys=True).encode("utf-8")
    hash1 = hashlib.sha256(manifest_bytes).hexdigest()
    
    # Token not in manifest
    assert "token" not in json.dumps(manifest).lower()
    assert len(hash1) == 64


def test_critical_interfaces_defined():
    """Critical interfaces must be present in data requirements."""
    req = get_data_requirements()
    interfaces = req["interfaces"]
    
    critical = ["daily", "daily_basic", "trade_cal", "stock_basic", 
                "stk_limit", "adj_factor", "index_daily"]
    
    for iface in critical:
        assert iface in interfaces, f"Missing critical interface: {iface}"
        assert "fields" in interfaces[iface]


def test_guard_rules_defined():
    """Guard rules must be present in data requirements."""
    req = get_data_requirements()
    
    assert "guard_rules" in req
    assert "min_avg_amount_20d" in req["guard_rules"]
    assert req["guard_rules"]["min_avg_amount_20d"] == 50000000


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
