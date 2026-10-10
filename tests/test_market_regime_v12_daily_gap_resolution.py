import pytest

from scripts.diagnose_market_regime_v12_daily_gaps import _classify_missing_gap


def test_same_day_formal_suspension_is_resolved_before_corrective_gap() -> None:
    assert _classify_missing_gap(
        "000001.SZ", "20200203", [{"suspend_type": "S"}], None
    ) == "resolved_formal_suspension"


def test_exact_existing_evidence_is_separate_from_new_unresolved_gap() -> None:
    assert _classify_missing_gap(
        "000001.SZ", "20200203", [], {"qualified": True}
    ) == "existing_qualified_evidence"
    assert _classify_missing_gap(
        "000001.SZ", "20200203", [], None
    ) == "new_unresolved"


def test_unauthorized_evidence_is_not_extrapolated() -> None:
    assert _classify_missing_gap(
        "000001.SZ", "20200203", [], {"qualified": False}
    ) == "new_unresolved"


def test_unknown_suspend_type_is_not_formal_resolution() -> None:
    assert _classify_missing_gap(
        "000001.SZ", "20200203", [{"suspend_type": "R"}], None
    ) == "new_unresolved"
