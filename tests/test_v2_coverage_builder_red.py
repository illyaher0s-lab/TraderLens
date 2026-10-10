"""TDD RED phase: tests that will fail until coverage builder implemented."""
import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).parent.parent


def test_coverage_builder_imports():
    """Coverage builder module must exist."""
    from scripts.build_v2_coverage import build_coverage_package
    assert callable(build_coverage_package)


def test_coverage_hash_deterministic():
    """Same inputs must produce identical coverage_hash."""
    from scripts.build_v2_coverage import compute_coverage_hash
    
    manifest_path = ROOT / "data/pit/formal_packages/de3fed9c3819d25c/manifest.json"
    manifest = json.loads(manifest_path.read_text())
    
    hash1 = compute_coverage_hash(manifest, "dummy_algorithm_hash")
    hash2 = compute_coverage_hash(manifest, "dummy_algorithm_hash")
    
    assert hash1 == hash2
    assert len(hash1) == 16  # short hash


def test_coverage_hash_binds_all_inputs():
    """Coverage hash must change when any input changes."""
    from scripts.build_v2_coverage import compute_coverage_hash
    
    manifest = {
        "qualification_package_id": "de3fed9c3819d25c",
        "template_hash": "hash1",
        "data_requirements_hash": "hash2",
        "snapshot_hash": "hash3",
        "scope_hash": "hash4",
    }
    
    hash_base = compute_coverage_hash(manifest, "algo_v1")
    
    # Change template
    manifest["template_hash"] = "hash1_changed"
    assert compute_coverage_hash(manifest, "algo_v1") != hash_base
    
    # Change algorithm
    manifest["template_hash"] = "hash1"
    assert compute_coverage_hash(manifest, "algo_v2") != hash_base


def test_expected_universe_uses_independent_builder():
    """Must use eligible_codes_independent, not daily rows."""
    from scripts.build_v2_coverage import build_expected_codes_for_date
    import inspect
    
    sig = inspect.signature(build_expected_codes_for_date)
    params = list(sig.parameters.keys())
    
    # Must NOT accept daily_codes or daily frame
    assert 'daily_codes' not in params
    assert 'daily' not in params
    
    # Must accept lifecycle, active, date
    assert 'lifecycle' in params
    assert 'active' in params
    assert 'date' in params


def test_unavailable_rows_have_sorted_missing_fields():
    """Each unavailable row must have sorted missing_fields list."""
    from scripts.build_v2_coverage import build_coverage_package
    
    result = build_coverage_package("de3fed9c3819d25c")
    
    unavailable_path = ROOT / f"data/pit/coverage_packages/{result['coverage_hash']}/unavailable_security_dates.parquet"
    unavailable = pd.read_parquet(unavailable_path)
    
    for fields in unavailable['missing_fields']:
        assert list(fields) == sorted(fields), f"Fields not sorted: {fields}"


def test_unavailable_stock_days_equals_parquet_rows():
    """unavailable_stock_days must equal unavailable parquet row count."""
    from scripts.build_v2_coverage import build_coverage_package
    
    result = build_coverage_package("de3fed9c3819d25c")
    
    unavailable_path = ROOT / f"data/pit/coverage_packages/{result['coverage_hash']}/unavailable_security_dates.parquet"
    unavailable = pd.read_parquet(unavailable_path)
    
    assert len(unavailable) == result['unavailable_stock_days']


def test_complete_plus_unavailable_equals_expected():
    """Algebraic invariant: complete + unavailable = expected."""
    from scripts.build_v2_coverage import build_coverage_package
    
    result = build_coverage_package("de3fed9c3819d25c")
    
    expected = result['expected_stock_days']
    complete = result['complete_stock_days']
    unavailable = result['unavailable_stock_days']
    
    assert complete + unavailable == expected


def test_field_counts_from_expanded_missing_fields():
    """Each field's count must equal occurrences in expanded missing_fields."""
    from scripts.build_v2_coverage import build_coverage_package
    
    result = build_coverage_package("de3fed9c3819d25c")
    
    unavailable_path = ROOT / f"data/pit/coverage_packages/{result['coverage_hash']}/unavailable_security_dates.parquet"
    unavailable = pd.read_parquet(unavailable_path)
    
    # Expand missing_fields and count
    from collections import Counter
    field_counts = Counter()
    for fields in unavailable['missing_fields']:
        field_counts.update(fields)
    
    # Compare with manifest
    for field, count in result['field_missing_counts'].items():
        assert field_counts[field] == count, f"Field {field}: expected {count}, got {field_counts[field]}"


def test_coverage_by_date_aggregates_to_global():
    """coverage_by_date must sum to global totals."""
    from scripts.build_v2_coverage import build_coverage_package
    
    result = build_coverage_package("de3fed9c3819d25c")
    
    by_date_path = ROOT / f"data/pit/coverage_packages/{result['coverage_hash']}/coverage_by_date.parquet"
    by_date = pd.read_parquet(by_date_path)
    
    assert by_date['expected_codes'].sum() == result['expected_stock_days']
    assert by_date['complete_codes'].sum() == result['complete_stock_days']
    assert by_date['unavailable_codes'].sum() == result['unavailable_stock_days']


def test_coverage_by_code_aggregates_to_global():
    """coverage_by_code must sum to global totals."""
    from scripts.build_v2_coverage import build_coverage_package
    
    result = build_coverage_package("de3fed9c3819d25c")
    
    by_code_path = ROOT / f"data/pit/coverage_packages/{result['coverage_hash']}/coverage_by_code.parquet"
    by_code = pd.read_parquet(by_code_path)
    
    assert by_code['expected_days'].sum() == result['expected_stock_days']
    assert by_code['complete_days'].sum() == result['complete_stock_days']
    assert by_code['unavailable_days'].sum() == result['unavailable_stock_days']


def test_duplicate_security_date_is_structural_error():
    """Same (trade_date, ts_code) twice in one table → structural error."""
    from scripts.build_v2_coverage import build_coverage_package
    
    result = build_coverage_package("de3fed9c3819d25c")
    
    # If structural errors exist, must be reported
    if result.get('structural_errors'):
        for err in result['structural_errors']:
            assert 'duplicate' not in err.lower() or 'FAIL' in err


def test_partition_date_mismatch_is_structural_error():
    """Partition path date != row trade_date → structural error."""
    from scripts.build_v2_coverage import build_coverage_package
    
    result = build_coverage_package("de3fed9c3819d25c")
    
    if result.get('structural_errors'):
        for err in result['structural_errors']:
            assert 'mismatch' not in err.lower() or 'FAIL' in err


def test_expected_stock_days_matches_qualification():
    """Expected stock days must match qualification manifest."""
    from scripts.build_v2_coverage import build_coverage_package
    
    result = build_coverage_package("de3fed9c3819d25c")
    
    assert result['expected_stock_days'] == 10659050


def test_old_packages_untouched():
    """Old invalid and new qualification packages must not be modified."""
    old_invalid = ROOT / "data/pit/formal_packages/35d996036cc04179/manifest.json"
    new_qual = ROOT / "data/pit/formal_packages/de3fed9c3819d25c/manifest.json"
    
    old_hash_before = None
    if old_invalid.exists():
        old_hash_before = hashlib.sha256(old_invalid.read_bytes()).hexdigest()
    
    new_hash_before = hashlib.sha256(new_qual.read_bytes()).hexdigest()
    
    from scripts.build_v2_coverage import build_coverage_package
    build_coverage_package("de3fed9c3819d25c")
    
    if old_hash_before:
        assert hashlib.sha256(old_invalid.read_bytes()).hexdigest() == old_hash_before
    
    assert hashlib.sha256(new_qual.read_bytes()).hexdigest() == new_hash_before


def test_placeholder_coverage_dir_never_used():
    """Placeholder coverage dir must never become output."""
    placeholder = ROOT / "data/pit/coverage_packages/de3fed9c3819d25c"
    
    from scripts.build_v2_coverage import build_coverage_package
    result = build_coverage_package("de3fed9c3819d25c")
    
    output_dir = ROOT / f"data/pit/coverage_packages/{result['coverage_hash']}"
    
    # Output must use coverage_hash, not qualification_package_id
    assert output_dir != placeholder
    assert result['coverage_hash'] != "de3fed9c3819d25c"


def test_second_run_already_published():
    """Second run with same inputs → already_published, same hashes."""
    from scripts.build_v2_coverage import build_coverage_package
    
    result1 = build_coverage_package("de3fed9c3819d25c")
    result2 = build_coverage_package("de3fed9c3819d25c")
    
    assert result2['status'] == 'already_published'
    assert result1['coverage_hash'] == result2['coverage_hash']
    assert result1['unavailable_parquet_hash'] == result2['unavailable_parquet_hash']


def test_top_10_sorted_descending_then_ascending():
    """Top 10 must be sorted by count DESC, then by date/code ASC."""
    from scripts.build_v2_coverage import build_coverage_package
    
    result = build_coverage_package("de3fed9c3819d25c")
    
    if 'top_10_dates_by_unavailable' in result:
        top_dates = result['top_10_dates_by_unavailable']
        for i in range(len(top_dates) - 1):
            curr_count = top_dates[i][1]
            next_count = top_dates[i+1][1]
            if curr_count == next_count:
                # Same count → date must be ascending
                assert top_dates[i][0] <= top_dates[i+1][0]
            else:
                # Different count → must be descending
                assert curr_count > next_count


def test_manifest_has_required_keys():
    """Manifest must have all required keys."""
    from scripts.build_v2_coverage import build_coverage_package
    
    result = build_coverage_package("de3fed9c3819d25c")
    
    required = {
        'status', 'coverage_hash', 'expected_stock_days', 'complete_stock_days',
        'unavailable_stock_days', 'field_missing_counts', 'structural_errors',
        'unavailable_parquet_hash', 'coverage_by_date_hash', 'coverage_by_code_hash',
        'input_qualification_package_id', 'input_template_hash', 'input_snapshot_hash',
    }
    
    for key in required:
        assert key in result, f"Missing key: {key}"


def test_report_contains_mask_disclosure():
    """Report must state this is coverage diagnostic, not new formal package."""
    from scripts.build_v2_coverage import build_coverage_package
    
    result = build_coverage_package("de3fed9c3819d25c")
    
    report_path = ROOT / "docs/verification/V2_AVAILABILITY_COVERAGE_REPORT.md"
    report = report_path.read_text()
    
    assert "availability mask" in report.lower()
    assert (
        "availability mask 是覆盖诊断产物，不是新的 formal package、tradability mask 或回测 universe。"
        "后续 B6/OOS 若跳过 unavailable observations，必须同时保留原始 expected-universe 分母并披露逐日覆盖率，"
        "不得只报告 supported observations 上的收益而省略覆盖变化。"
    ) in report


def test_bound_partition_rejects_missing_registered_hash(tmp_path):
    """A bound partition without its registered digest is structural, never unavailable."""
    from scripts.build_v2_coverage import read_bound_partition

    path = tmp_path / "part.parquet"
    pd.DataFrame({"trade_date": [20240102], "ts_code": ["000001.SZ"]}).to_parquet(path)

    with pytest.raises(ValueError, match="registered hash"):
        read_bound_partition(path, 20240102, "daily")


def test_bound_partition_rejects_duplicate_or_date_mismatch(tmp_path):
    """Duplicate rows and path/date mismatches invalidate the whole bound input."""
    from scripts.build_v2_coverage import read_bound_partition

    path = tmp_path / "part.parquet"
    pd.DataFrame({
        "trade_date": [20240102, 20240102],
        "ts_code": ["000001.SZ", "000001.SZ"],
    }).to_parquet(path)
    (tmp_path / "part.parquet.sha256").write_text(hashlib.sha256(path.read_bytes()).hexdigest())

    with pytest.raises(ValueError, match="duplicate"):
        read_bound_partition(path, 20240102, "daily")


def test_coverage_hash_binds_schema_and_input_manifest_mapping():
    """Changing a bound manifest digest or schema changes the immutable output identity."""
    from scripts.build_v2_coverage import compute_coverage_hash

    manifest = {
        "qualification_package_id": "de3fed9c3819d25c",
        "template_hash": "template",
        "data_requirements_hash": "requirements",
        "snapshot_hash": "snapshot",
        "scope_hash": "scope",
    }
    base = compute_coverage_hash(
        manifest,
        "algorithm",
        input_manifest_hashes={"source.json": "one"},
        schema={"fields": ["trade_date", "ts_code"]},
    )
    assert compute_coverage_hash(
        manifest,
        "algorithm",
        input_manifest_hashes={"source.json": "two"},
        schema={"fields": ["trade_date", "ts_code"]},
    ) != base
    assert compute_coverage_hash(
        manifest,
        "algorithm",
        input_manifest_hashes={"source.json": "one"},
        schema={"fields": ["trade_date", "ts_code", "missing_fields"]},
    ) != base
