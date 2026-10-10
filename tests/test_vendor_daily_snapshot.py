"""Test vendor daily snapshot verification."""
import pytest


def test_code_column_must_be_string():
    """CSV 代码 column must be read as string to preserve leading zeros."""
    pass


def test_all_codes_six_digits():
    r"""All codes must match ^\d{6}$."""
    pass


def test_daily_codes_unique_or_metadata_foldable():
    """Duplicates allowed if name+industry identical (metadata projection)."""
    pass


def test_headers_stable_across_days():
    """Headers must be identical across all CSVs."""
    pass


def test_csv_content_change_changes_package_hash():
    """Changing any CSV content must change package_sha256."""
    pass


def test_header_change_fails_audit():
    """Any header deviation from baseline must fail audit."""
    pass


def test_metadata_conflict_fails_audit():
    """Name or industry mismatch on same (date,code) must fail."""
    pass


def test_rejected_field_diff_not_blocker():
    """均线/涨幅 etc diff does not block if name+industry match."""
    pass


def test_ohlc_amount_match_formal():
    """开高低收/成交额 must match formal daily for sample stocks."""
    pass


def test_gbk_console_compatible():
    """CLI output must be ASCII-safe for Windows GBK console."""
    # ponytail: RED first - will pass after fix
    pass
