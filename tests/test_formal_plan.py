"""Test formal-plan correctness."""
from scripts.verify_gate0_data_feasibility import run_formal_plan, get_data_requirements, compute_data_requirements_hash


def test_formal_plan_finds_window_start():
    """formal-plan must compute window start as 2016-01-04."""
    result = run_formal_plan()
    assert "window_start" in result
    assert result["window_start"] == "20160104"


def test_formal_plan_finds_last_closed():
    """formal-plan must find last closed trading day from trade_cal."""
    result = run_formal_plan()
    assert "last_closed_trading_day" in result
    # ponytail: must be >= 20160104 and actual trading day
    assert int(result["last_closed_trading_day"]) >= 20160104


def test_formal_plan_ready_to_collect():
    """formal-plan must output ready_to_collect, never formal_qualified."""
    result = run_formal_plan()
    assert result["status"] in ["ready_to_collect", "blocked"]
    assert result.get("gate0_status") != "formal_qualified"


def test_data_requirements_has_control_group():
    """data_requirements must include control_group definition."""
    req = get_data_requirements()
    assert "control_group" in req
    assert req["control_group"]["type"] == "same_sw_l1_industry_excluding_self"
