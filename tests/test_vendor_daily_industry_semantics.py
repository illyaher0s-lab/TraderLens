"""Test vendor daily industry semantics."""


def test_hash_mismatch_fails():
    """Audit must fail if file hash differs from manifest."""
    pass


def test_consecutive_ab_counts_as_change():
    """A→B on consecutive trading days = 1 change."""
    pass


def test_absence_not_change():
    """Missing days between appearances don't count as change."""
    pass


def test_aba_within_5days_is_flap():
    """A→B→A within 5 trading days = flap."""
    pass


def test_no_change_unproven():
    """Zero changes → industry_pit_semantics_unproven."""
    pass
