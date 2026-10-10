"""Checks for the vendor security-lifecycle candidate evidence."""
import json
from pathlib import Path


MANIFEST = Path("data/pit/vendor_daily_snapshot/vendor_8e64285ae2fdea2e/security_lifecycle_candidate.json")


def test_candidate_binds_the_verified_vendor_package():
    """A lifecycle exception cannot float free of its vendor package hash."""
    evidence = json.loads(MANIFEST.read_text())
    assert evidence["status"] == "candidate_verified"
    assert len(evidence["vendor_package_sha256"]) == 64


def test_candidate_covers_all_three_formal_lifecycle_holes():
    """Every daily observation absent from stock_basic needs dated vendor coverage."""
    evidence = json.loads(MANIFEST.read_text())
    assert evidence["uncovered_formal_daily_dates"] == 0
    assert {item["ts_code"] for item in evidence["codes"]} == {"000022.SZ", "000043.SZ", "300114.SZ"}
