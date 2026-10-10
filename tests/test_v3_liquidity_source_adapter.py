from __future__ import annotations

import pytest


def _resolve(*, daily_row=None, suspend_rows=None, interval_evidence=None):
    from scripts.v3_liquidity_source_adapter import resolve_source_amount

    return resolve_source_amount(
        daily_row=daily_row,
        suspend_rows=suspend_rows or [],
        interval_evidence=interval_evidence,
    )


def test_valid_daily_amount_wins_over_r():
    result = _resolve(daily_row={"amount": 12.5}, suspend_rows=[{"suspend_type": "R"}])

    assert result == {"status": "daily", "amount_yuan": 12500.0}


def test_valid_daily_amount_wins_over_r_plus_s():
    result = _resolve(
        daily_row={"amount": 12.5},
        suspend_rows=[{"suspend_type": "R"}, {"suspend_type": "S"}],
    )

    assert result == {"status": "daily", "amount_yuan": 12500.0}


def test_missing_daily_with_r_only_is_data_fault():
    result = _resolve(suspend_rows=[{"suspend_type": "R"}])

    assert result == {"status": "data_fault", "reason": "daily_missing_without_suspension_evidence"}


@pytest.mark.parametrize("suspend_type", ["S", "P"])
def test_missing_daily_with_exact_s_or_p_is_zero(suspend_type: str):
    result = _resolve(suspend_rows=[{"suspend_type": suspend_type}])

    assert result == {"status": "suspended", "amount_yuan": 0.0}


def test_missing_daily_with_qualified_interval_is_zero():
    result = _resolve(interval_evidence={"qualified": True, "scope_artifact_id": "scope"})

    assert result == {"status": "suspended", "amount_yuan": 0.0}


def test_invalid_daily_amount_cannot_be_masked_by_suspension():
    result = _resolve(daily_row={"amount": None}, suspend_rows=[{"suspend_type": "S"}])

    assert result == {"status": "data_fault", "reason": "daily_amount_invalid"}


def test_unresolved_missing_daily_is_data_fault():
    result = _resolve()

    assert result == {"status": "data_fault", "reason": "daily_missing_without_suspension_evidence"}
