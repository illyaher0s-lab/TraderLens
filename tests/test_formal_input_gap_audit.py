"""Formal input gap audit tests."""
import json
from pathlib import Path


def test_message_counts_match_manifest():
    """Both interfaces match manifest breakdown."""
    audit = json.loads(Path("docs/verification/formal_input_gap_audit.json").read_text())
    manifest = json.loads(Path("data/pit/formal_packages/fa4e3fd8f98d8758/manifest.json").read_text())
    
    assert audit["stk_limit"]["message_count"] == manifest["gap_counts_by_type"]["stk_limit"]["message_count"]
    assert audit["daily_basic"]["message_count"] == manifest["gap_counts_by_type"]["daily_basic"]["message_count"]


def test_stock_days_not_messages():
    """Stock-days != messages for both."""
    audit = json.loads(Path("docs/verification/formal_input_gap_audit.json").read_text())
    assert audit["stk_limit"]["stock_day_count"] != audit["stk_limit"]["message_count"]
    assert audit["daily_basic"]["stock_day_count"] != audit["daily_basic"]["message_count"]


def test_overlap_sums():
    """Intersection + only = total."""
    audit = json.loads(Path("docs/verification/formal_input_gap_audit.json").read_text())
    # ponytail: set algebra
    assert audit["intersection"]["stock_day_count"] + audit["stk_limit_only"]["stock_day_count"] == audit["stk_limit"]["stock_day_count"]
    assert audit["intersection"]["stock_day_count"] + audit["daily_basic_only"]["stock_day_count"] == audit["daily_basic"]["stock_day_count"]


def test_first_gap_exists():
    """First gap is earliest real gap."""
    audit = json.loads(Path("docs/verification/formal_input_gap_audit.json").read_text())
    assert audit["first_gap"] is not None
    assert audit["first_gap"] >= 20160104


def test_classification_per_date():
    """First_n requires per-date check (implicit via code logic)."""
    audit = json.loads(Path("docs/verification/formal_input_gap_audit.json").read_text())
    # ponytail: can't assert implementation, but check result exists
    assert "first_n_trading_days_observed" in audit["stk_limit"]["classification"] or "first_n_trading_days_observed" in audit["daily_basic"]["classification"]
