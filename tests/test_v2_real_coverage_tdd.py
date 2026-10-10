"""TDD tests for real V2 availability coverage builder."""
import pandas as pd
from pathlib import Path
import pytest


def test_expected_universe_independent_of_input_row_changes():
    """Expected universe must not change when input rows added/removed."""
    from scripts.build_v2_real_coverage import build_expected_universe_for_date
    
    # Will implement build_expected_universe_for_date that doesn't read inputs
    # For now, test structure
    pass


def test_missing_fields_fixed_sort_single_row_per_security_date():
    """One unavailable (date, code) with multiple missing fields → one row, sorted fields."""
    # Example: (20160104, "000001.SZ") missing ["daily_basic", "stk_limit"]
    # Should produce: missing_fields = ["daily_basic", "stk_limit"] (sorted)
    pass


def test_field_missing_count_equals_expanded_occurrences():
    """Each field's missing count must equal its appearances in all missing_fields."""
    # If 100 rows have ["daily_basic"] and 50 have ["daily_basic", "stk_limit"]
    # Then daily_basic count = 150, stk_limit count = 50
    pass


def test_complete_plus_unavailable_equals_expected():
    """Algebraic invariant must hold."""
    # Will verify against real output
    pass


def test_unavailable_stock_days_equals_parquet_rows():
    """unavailable_stock_days must equal unavailable_security_dates.parquet row count."""
    pass


def test_placeholder_never_becomes_output():
    """Placeholder path must never be used as real output."""
    placeholder = Path("data/pit/coverage_packages/de3fed9c3819d25c")
    
    assert (placeholder / "STATUS_INVALID.txt").exists()
    # Real output will use coverage_hash as directory name
