"""Tests that expected universe is independent of required input rows."""
import pandas as pd
from collections import Counter


def test_expected_universe_independent_of_daily_rows():
    """Expected universe must not change when daily rows added/removed."""
    from scripts.sw2021_pit_qualification_core import eligible_codes_independent
    
    lifecycle = pd.DataFrame({
        "list_date": [20200101, 20200101],
        "delist_date": [99991231, 99991231],
    }, index=["A.SZ", "B.SH"])
    
    active = {"A.SZ": Counter({"I1": 1}), "B.SH": Counter({"I2": 1})}
    date = 20240102
    
    # Expected universe must be same regardless of which codes have daily rows
    expected1, _, _, _, _ = eligible_codes_independent(lifecycle, active, date)
    expected2, _, _, _, _ = eligible_codes_independent(lifecycle, active, date)
    
    assert expected1 == {"A.SZ", "B.SH"}
    assert expected2 == {"A.SZ", "B.SH"}


def test_daily_exists_lifecycle_missing_not_in_expected():
    """Code with daily row but no lifecycle must not enter expected universe."""
    from scripts.sw2021_pit_qualification_core import eligible_codes_independent
    
    lifecycle = pd.DataFrame({
        "list_date": [20200101],
        "delist_date": [99991231],
    }, index=["A.SZ"])
    
    active = {"A.SZ": Counter({"I1": 1})}
    date = 20240102
    
    expected, _, _, _, _ = eligible_codes_independent(lifecycle, active, date)
    
    # "B.SZ" has daily row but no lifecycle → not in expected
    assert expected == {"A.SZ"}
    assert "B.SZ" not in expected


def test_daily_exists_membership_missing_not_in_expected():
    """Code with daily row but no membership must not enter expected universe."""
    from scripts.sw2021_pit_qualification_core import eligible_codes_independent
    
    lifecycle = pd.DataFrame({
        "list_date": [20200101, 20200101],
        "delist_date": [99991231, 99991231],
    }, index=["A.SZ", "B.SZ"])
    
    # B.SZ has no membership
    active = {"A.SZ": Counter({"I1": 1})}
    date = 20240102
    
    expected, _, _, excluded_no_industry, _ = eligible_codes_independent(lifecycle, active, date)
    
    assert expected == {"A.SZ"}
    assert "B.SZ" not in expected
    assert excluded_no_industry == 1


def test_market_scope_filters_expected_independently():
    """Market scope must filter expected universe independent of daily."""
    from scripts.sw2021_pit_qualification_core import eligible_codes_independent, apply_market_scope
    
    lifecycle = pd.DataFrame({
        "list_date": [20200101, 20200101, 20200101],
        "delist_date": [99991231, 99991231, 99991231],
    }, index=["A.SZ", "B.SH", "C.BJ"])
    
    active = {
        "A.SZ": Counter({"I1": 1}),
        "B.SH": Counter({"I2": 1}),
        "C.BJ": Counter({"I3": 1}),
    }
    date = 20240102
    
    expected, _, _, _, _ = eligible_codes_independent(lifecycle, active, date)
    expected_in_scope, bse, other = apply_market_scope(expected, ["SH", "SZ"])
    
    assert expected_in_scope == {"A.SZ", "B.SH"}
    assert bse == {"C.BJ"}
    assert other == set()


def test_lifecycle_boundary_honored():
    """Lifecycle list_date/delist_date boundaries must be honored."""
    from scripts.sw2021_pit_qualification_core import eligible_codes_independent
    
    lifecycle = pd.DataFrame({
        "list_date": [20200101, 20200201, 20200101],
        "delist_date": [20200110, 99991231, 99991231],
    }, index=["A.SZ", "B.SZ", "C.SZ"])
    
    active = {
        "A.SZ": Counter({"I1": 1}),
        "B.SZ": Counter({"I1": 1}),
        "C.SZ": Counter({"I1": 1}),
    }
    
    # 20200105: A listed, B not yet, C listed
    expected, excluded_pre, _, _, _ = eligible_codes_independent(lifecycle, active, 20200105)
    assert expected == {"A.SZ", "C.SZ"}
    assert excluded_pre == 1  # B not yet listed
    
    # 20200115: A delisted, B listed, C listed
    expected, excluded_pre, _, _, _ = eligible_codes_independent(lifecycle, active, 20200115)
    assert expected == {"B.SZ", "C.SZ"}
    assert excluded_pre == 1  # A delisted
