"""Tests for market scope filtering helper."""
from scripts.sw2021_pit_qualification_core import apply_market_scope


def test_apply_market_scope_sh_sz():
    """SH/SZ in scope."""
    eligible = {"000001.SZ", "600000.SH", "920000.BJ"}
    market_scope = ["SH", "SZ"]
    
    expected, bse, other = apply_market_scope(eligible, market_scope)
    
    assert expected == {"000001.SZ", "600000.SH"}
    assert bse == {"920000.BJ"}
    assert other == set()


def test_apply_market_scope_bj_only():
    """BJ explicitly excluded."""
    eligible = {"920000.BJ", "920001.BJ"}
    market_scope = ["SH", "SZ"]
    
    expected, bse, other = apply_market_scope(eligible, market_scope)
    
    assert expected == set()
    assert bse == {"920000.BJ", "920001.BJ"}
    assert other == set()


def test_apply_market_scope_unknown_suffix():
    """Unknown suffix → other."""
    eligible = {"000001.SZ", "999999.XX"}
    market_scope = ["SH", "SZ"]
    
    expected, bse, other = apply_market_scope(eligible, market_scope)
    
    assert expected == {"000001.SZ"}
    assert bse == set()
    assert other == {"999999.XX"}


def test_apply_market_scope_no_scope():
    """Empty scope → all out."""
    eligible = {"000001.SZ", "600000.SH"}
    market_scope = []
    
    expected, bse, other = apply_market_scope(eligible, market_scope)
    
    assert expected == set()
    assert bse == set()
    assert other == {"000001.SZ", "600000.SH"}
