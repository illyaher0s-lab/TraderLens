"""Tests for SHSZ official lifecycle evidence."""
import json
from pathlib import Path


def test_no_url_no_confirmed():
    """Without official URL, cannot be confirmed."""
    ev = json.loads(Path("docs/verification/shsz_official_lifecycle_evidence.json").read_text())
    for code, data in ev["codes"].items():
        if data.get("official_announcement_url") is None:
            assert data["evidence_level"] in ["unexplained_blocking", "lifecycle_evidence_unconfirmed"]


def test_001914_requires_canonical_identity():
    """001914 alias requires canonical identity deduplication."""
    ev = json.loads(Path("docs/verification/shsz_official_lifecycle_evidence.json").read_text())
    assert ev["codes"]["001914.SZ"]["requires_canonical_identity"] is True


def test_all_codes_present():
    """All 5 codes documented."""
    ev = json.loads(Path("docs/verification/shsz_official_lifecycle_evidence.json").read_text())
    assert set(ev["codes"].keys()) == {"001914.SZ", "300216.SZ", "002604.SZ", "000939.SZ", "000760.SZ"}


def test_gap_period_comparison():
    """Gap periods documented for verification."""
    ev = json.loads(Path("docs/verification/shsz_official_lifecycle_evidence.json").read_text())
    for code in ["300216.SZ", "002604.SZ", "000939.SZ", "000760.SZ"]:
        assert "gap_first" in ev["codes"][code]
        assert "gap_last" in ev["codes"][code]
