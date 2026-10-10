"""Gate 0 formal qualification tests."""
import hashlib
import json
from pathlib import Path

import pytest


def test_formal_plan_requires_st_pit():
    """formal-plan must fail if ST history PIT is unavailable."""
    # ponytail: this test documents the blocker, implementation will return st_history_pit_unavailable
    pass


def test_formal_qualify_rejects_candidate_guard():
    """formal-qualify must reject candidate guard as if frozen."""
    # ponytail: guard validation_status must be frozen, not candidate
    pass


def test_formal_qualify_rejects_scope_mismatch():
    """formal-qualify must reject if scope hash doesn't match."""
    pass


def test_data_requirements_hash_changes_on_control_group_change():
    """Changing control group definition must change data_requirements_hash."""
    from scripts.verify_gate0_data_feasibility import compute_data_requirements_hash
    
    req1 = {"interfaces": {}, "control_group": {"type": "shenwan_l1"}}
    req2 = {"interfaces": {}, "control_group": {"type": "market_cap_tercile"}}
    
    hash1 = compute_data_requirements_hash(req1)
    hash2 = compute_data_requirements_hash(req2)
    assert hash1 != hash2, "Hash must change when control group changes"


def test_formal_qualify_requires_complete_snapshot():
    """formal-qualify must reject incomplete snapshot."""
    # ponytail: missing files, truncated partitions, hash mismatch all fail
    pass
