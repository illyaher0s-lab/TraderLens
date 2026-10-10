import pandas as pd


def test_event_sweep_expires_membership_after_out_date():
    from scripts.sw2021_pit_qualification_core import build_events, step_active

    days = [20240102, 20240103, 20240104]
    members = pd.DataFrame({
        "ts_code": ["000001.SZ"],
        "l1_code": ["801780.SI"],
        "in_date": [20240102],
        "out_date": [20240103],
    })
    starts, ends = build_events(members, days)
    active = {}
    active = step_active(active, ends, starts, 0)
    assert set(active["000001.SZ"]) == {"801780.SI"}
    active = step_active(active, ends, starts, 1)
    assert set(active["000001.SZ"]) == {"801780.SI"}
    active = step_active(active, ends, starts, 2)
    assert "000001.SZ" not in active


def test_eligible_codes_excludes_missing_or_ambiguous_membership():
    from scripts.sw2021_pit_qualification_core import eligible_codes

    lifecycle = pd.DataFrame({
        "list_date": [20200101, 20200101, 20200101],
        "delist_date": [99991231, 99991231, 99991231],
    }, index=["A", "B", "C"])
    active = {"A": {"I1"}, "B": set(), "C": {"I1", "I2"}}
    eligible, excluded_pre, excluded_no_industry, unknown, ambiguous = eligible_codes(
        {"A", "B", "C"}, lifecycle, active, 20240102
    )
    assert eligible == {"A"}
    assert excluded_pre == 0
    assert excluded_no_industry == 1
    assert unknown == 0
    assert ambiguous == {"C"}


def test_event_sweep_keeps_overlapping_same_industry_until_last_interval_ends():
    from scripts.sw2021_pit_qualification_core import build_events, step_active

    days = [20240102, 20240103, 20240104, 20240105]
    members = pd.DataFrame({
        "ts_code": ["000001.SZ", "000001.SZ"],
        "l1_code": ["801780.SI", "801780.SI"],
        "in_date": [20240102, 20240103],
        "out_date": [20240103, 20240104],
    })
    starts, ends = build_events(members, days)
    active = {}
    for index in range(3):
        active = step_active(active, ends, starts, index)
    assert set(active["000001.SZ"]) == {"801780.SI"}
