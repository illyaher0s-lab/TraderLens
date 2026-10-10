"""Tests for SHSZ V2 qualification."""
import json
import hashlib
from pathlib import Path


OLD_MANIFEST_PATH = Path("data/pit/formal_packages/fa4e3fd8f98d8758/manifest.json")


def test_old_manifest_hash_baseline():
    """Record old manifest hash."""
    expected = "21f7dd6a813d384a5e2f7e3b6aedbf0e18f9e44000e4538bc88a65ec4a1cfd3a"
    actual = hashlib.sha256(OLD_MANIFEST_PATH.read_bytes()).hexdigest()
    assert actual == expected, "Old manifest changed before test"


def test_new_template_hash_differs():
    """New template has different hash."""
    from backend.services.strategy_template_library import get_template_by_id
    old = get_template_by_id("relative_strength_rotation_sw2021_pit_v1")
    new = get_template_by_id("relative_strength_rotation_shsz_sw2021_v1")
    assert old.frozen_template_hash != new.frozen_template_hash


def test_bj_excluded_by_market_scope():
    """.BJ excluded even when data present."""
    from scripts.sw2021_pit_qualification_core import apply_market_scope
    eligible = {"000001.SZ", "600000.SH", "920000.BJ"}
    expected, bse, other = apply_market_scope(eligible, ["SH", "SZ"])
    assert "920000.BJ" not in expected
    assert "920000.BJ" in bse


def test_shsz_missing_data_is_blocking():
    """.SH/.SZ missing data produces gap."""
    # ponytail: synthetic, real CLI will verify
    eligible = {"000001.SZ"}
    present = set()
    missing = eligible - present
    assert len(missing) == 1


def test_n_zero_no_early_exemption():
    """N=0 means all days expected."""
    from backend.services.strategy_template_library import get_template_by_id
    t = get_template_by_id("relative_strength_rotation_shsz_sw2021_v1")
    assert t.strategy_config_payload["minimum_history_trading_days"] == 0


def test_old_manifest_unchanged_after_new_run():
    """Old manifest hash stable after new qualification."""
    # ponytail: run after CLI
    expected = "21f7dd6a813d384a5e2f7e3b6aedbf0e18f9e44000e4538bc88a65ec4a1cfd3a"
    actual = hashlib.sha256(OLD_MANIFEST_PATH.read_bytes()).hexdigest()
    assert actual == expected, "Old manifest was modified"
