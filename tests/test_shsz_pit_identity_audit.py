"""Tests for SHSZ PIT identity audit."""
import json
from pathlib import Path


def test_all_five_codes_present():
    """All 5 codes in output."""
    audit = json.loads(Path("docs/verification/shsz_pit_identity_lifecycle_audit.json").read_text())
    assert set(audit["results"].keys()) == {"001914.SZ", "300216.SZ", "002604.SZ", "000939.SZ", "000760.SZ"}


def test_001914_requires_alias():
    """001914 conclusion is requires_pit_code_alias."""
    audit = json.loads(Path("docs/verification/shsz_pit_identity_lifecycle_audit.json").read_text())
    assert audit["results"]["001914.SZ"]["conclusion"] == "requires_pit_code_alias"
    assert audit["results"]["001914.SZ"]["predecessor_code"] == "000043.SZ"


def test_delist_codes_require_lifecycle():
    """Delisted codes require lifecycle correction."""
    audit = json.loads(Path("docs/verification/shsz_pit_identity_lifecycle_audit.json").read_text())
    for code in ["300216.SZ", "002604.SZ", "000939.SZ", "000760.SZ"]:
        assert audit["results"][code]["conclusion"] in ["requires_lifecycle_correction", "unexplained_blocking"]


def test_no_changes_to_scope():
    """Audit does not change scope."""
    audit = json.loads(Path("docs/verification/shsz_pit_identity_lifecycle_audit.json").read_text())
    assert "No changes applied" in audit["notes"] or "no changes" in audit["notes"].lower()
