"""stk_limit gap audit tests."""
import json
from pathlib import Path
import pytest


def test_audit_covers_2554_days():
    """Must audit all 2554 trading days."""
    p = Path("docs/verification/stk_limit_gap_audit.json")
    if not p.exists(): pytest.skip("not run")
    ev = json.loads(p.read_text())
    assert ev["checked_trade_days"] == 2554


def test_gap_count_matches_stk_limit_breakdown():
    """Gap count must match formal manifest stk_limit breakdown."""
    audit = json.loads(Path("docs/verification/stk_limit_gap_audit.json").read_text())
    manifest = json.loads(Path("data/pit/formal_packages/fa4e3fd8f98d8758/manifest.json").read_text())
    
    stk_limit_msg = manifest["gap_counts_by_type"].get("stk_limit", {}).get("message_count", 0)
    assert audit["total_gap_messages"] == stk_limit_msg


def test_stock_days_not_confused_with_messages():
    """Stock-days != message count."""
    p = Path("docs/verification/stk_limit_gap_audit.json")
    if not p.exists(): pytest.skip("not run")
    ev = json.loads(p.read_text())
    assert ev["total_gap_stock_days"] != ev["total_gap_messages"]


def test_classification_sums_to_stock_days():
    """Classification covers all stock-days."""
    p = Path("docs/verification/stk_limit_gap_audit.json")
    if not p.exists(): pytest.skip("not run")
    ev = json.loads(p.read_text())
    assert sum(ev["classification"].values()) == ev["total_gap_stock_days"]


def test_manifest_gap_count_is_sum_of_types():
    """blocking_gap_count == sum of all gap_counts_by_type message counts."""
    manifest = json.loads(Path("data/pit/formal_packages/fa4e3fd8f98d8758/manifest.json").read_text())
    total = sum(v["message_count"] for v in manifest["gap_counts_by_type"].values())
    assert manifest["blocking_gap_count"] == total
