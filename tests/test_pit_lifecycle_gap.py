"""Regression checks for the formal PIT lifecycle-gap audit artifact."""
import json
from pathlib import Path


EVIDENCE = Path("docs/verification/pit_lifecycle_gap_evidence.json")


def _evidence():
    return json.loads(EVIDENCE.read_text())


def test_native_stock_basic_probe_is_recorded():
    """Local absence cannot prove provider absence without L/D/P probes."""
    probe = _evidence()["native_stock_basic_probe"]
    assert probe["attempted_statuses"] == ["L", "D", "P"]
    assert len(probe["results"]) == 3


def test_gap_intervals_preserve_the_observed_day_count():
    """Compressed intervals must account for every missing daily observation."""
    for detail in _evidence()["gap_codes"]:
        assert sum(interval["trading_days"] for interval in detail["intervals"]) == detail["total_days"]


def test_status_is_not_ready_when_any_gap_code_remains():
    """An unresolved lifecycle code cannot be silently treated as unlisted."""
    evidence = _evidence()
    if evidence["unique_gap_codes"]:
        assert evidence["status"] != "lifecycle_resolution_ready"


def test_provider_fields_are_the_required_lifecycle_schema():
    """A successful probe must return the fields needed for PIT eligibility."""
    required = {"ts_code", "list_date", "delist_date"}
    for result in _evidence()["native_stock_basic_probe"]["results"]:
        if result["error_type"] is None:
            assert required <= set(result["fields"])
