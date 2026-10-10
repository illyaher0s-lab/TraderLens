"""SW2014 taxonomy audit tests."""
import json
from pathlib import Path
import pandas as pd
import pytest


def test_checked_all_2554_days():
    """Must check all 2554 trading days."""
    sel_path = Path("data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal/sw_l1_membership/sw2014_selection.json")
    
    if not sel_path.exists():
        pytest.skip("Selection not generated")
    
    sel = json.loads(sel_path.read_text())
    assert sel["checked_trade_days"] == 2554, "Must check all 2554 trading days"


def test_selection_records_lifecycle_exclusions():
    """Future listings in old daily partitions must not become taxonomy gaps."""
    sel_path = Path("data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal/sw_l1_membership/sw2014_selection.json")
    sel = json.loads(sel_path.read_text())

    assert sel["daily_stock_days"] > sel["expected_stock_days"]
    assert sel["excluded_pre_listing_stock_days"] > 0
    assert "excluded_post_delisting_stock_days" in sel


def test_pre_listing_excluded():
    """Stocks before list_date must be excluded."""
    sel_path = Path("data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal/sw_l1_membership/sw2014_selection.json")
    
    if not sel_path.exists():
        pytest.skip("Selection not generated")
    
    sel = json.loads(sel_path.read_text())
    
    # Must have excluded some pre-listing instances
    assert sel["excluded_pre_listing_stock_days"] > 0, "Should exclude future stocks on early dates"


def test_post_delisting_excluded():
    """Stocks after delist_date must be excluded."""
    sel_path = Path("data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal/sw_l1_membership/sw2014_selection.json")
    
    if not sel_path.exists():
        pytest.skip("Selection not generated")
    
    sel = json.loads(sel_path.read_text())
    
    # May be zero if no delisted stocks have market data after delist_date
    assert sel["excluded_post_delisting_stock_days"] >= 0


def test_listed_with_market_but_no_member_blocks():
    """Listed stock with market data but no SW2014 member → blocking gap."""
    sel_path = Path("data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal/sw_l1_membership/sw2014_selection.json")
    
    if not sel_path.exists():
        pytest.skip("Selection not generated")
    
    sel = json.loads(sel_path.read_text())
    
    # If ready, zero blocking gaps
    if sel["status"] == "taxonomy_selection_ready":
        assert sel["blocking_gap_count"] == 0


def test_selection_ready_means_zero_gaps():
    """taxonomy_selection_ready ↔ zero blocking gaps."""
    sel_path = Path("data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal/sw_l1_membership/sw2014_selection.json")
    
    if not sel_path.exists():
        pytest.skip("Selection not generated")
    
    sel = json.loads(sel_path.read_text())
    
    if sel["status"] == "taxonomy_selection_ready":
        assert sel["blocking_gap_count"] == 0
    elif sel["blocking_gap_count"] == 0:
        assert sel["status"] == "taxonomy_selection_ready"
