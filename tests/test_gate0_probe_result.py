"""Test Gate 0 feasibility probe results."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest


def test_gate0_snapshot_exists():
    """Gate 0 snapshot directory must exist."""
    snapshot_dir = Path(__file__).parent.parent / "data" / "pit" / "tushare" / "4469647337475dce"
    assert snapshot_dir.exists()


def test_gate0_manifest_valid():
    """Gate 0 manifest must be valid and have correct structure."""
    manifest_path = Path(__file__).parent.parent / "data" / "pit" / "tushare" / "4469647337475dce" / "manifest.json"
    assert manifest_path.exists()
    
    with open(manifest_path) as f:
        manifest = json.load(f)
    
    assert manifest["snapshot_id"] == "4469647337475dce"
    assert manifest["provider"] == "tushare"
    assert manifest["gate0_status"] == "feasibility_probe_passed"
    assert manifest["gate0_reason"] is None
    assert manifest["feasibility_probe_passed"] is True


def test_gate0_critical_interfaces_present():
    """All critical interfaces must be in probed list."""
    manifest_path = Path(__file__).parent.parent / "data" / "pit" / "tushare" / "4469647337475dce" / "manifest.json"
    
    with open(manifest_path) as f:
        manifest = json.load(f)
    
    critical = ["daily", "daily_basic", "trade_cal", "stock_basic", "stk_limit", "adj_factor", "index_daily"]
    interfaces_probed = manifest["interfaces_probed"]
    
    for iface in critical:
        assert iface in interfaces_probed, f"Critical interface missing: {iface}"


def test_gate0_data_files_exist():
    """All critical data files must exist."""
    snapshot_dir = Path(__file__).parent.parent / "data" / "pit" / "tushare" / "4469647337475dce"
    
    critical_files = [
        "daily.parquet",
        "daily_basic.parquet",
        "trade_cal.parquet",
        "stock_basic.parquet",
        "stk_limit.parquet",
        "adj_factor.parquet",
        "index_daily.parquet",
    ]
    
    for filename in critical_files:
        filepath = snapshot_dir / filename
        assert filepath.exists(), f"Critical data file missing: {filename}"


def test_gate0_manifest_hash_valid():
    """Manifest SHA-256 hash must be valid."""
    snapshot_dir = Path(__file__).parent.parent / "data" / "pit" / "tushare" / "4469647337475dce"
    manifest_path = snapshot_dir / "manifest.json"
    hash_path = snapshot_dir / "manifest.sha256"
    
    assert hash_path.exists()
    
    import hashlib
    actual_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    expected_hash = hash_path.read_text().strip()
    
    assert actual_hash == expected_hash


def test_gate0_coverage_2019_2025():
    """Coverage must span 2019-2025 for feasibility."""
    manifest_path = Path(__file__).parent.parent / "data" / "pit" / "tushare" / "4469647337475dce" / "manifest.json"
    
    with open(manifest_path) as f:
        manifest = json.load(f)
    
    assert manifest["coverage_start"] == "20190101"
    assert manifest["coverage_end"] == "20251231"


def test_gate0_trade_calendar_readable():
    """Trade calendar must be readable and have expected structure."""
    cal_path = Path(__file__).parent.parent / "data" / "pit" / "tushare" / "4469647337475dce" / "trade_cal.parquet"
    
    df = pd.read_parquet(cal_path)
    
    assert len(df) > 0
    assert "cal_date" in df.columns
    assert "is_open" in df.columns
    # ponytail: cal_date is string not int
    min_date = int(df["cal_date"].min()) if isinstance(df["cal_date"].iloc[0], str) else df["cal_date"].min()
    max_date = int(df["cal_date"].max()) if isinstance(df["cal_date"].iloc[0], str) else df["cal_date"].max()
    assert min_date <= 20190101
    assert max_date >= 20251231


def test_gate0_stock_basic_readable():
    """Stock basic must be readable and have expected structure."""
    stock_path = Path(__file__).parent.parent / "data" / "pit" / "tushare" / "4469647337475dce" / "stock_basic.parquet"
    
    df = pd.read_parquet(stock_path)
    
    assert len(df) > 0
    assert "ts_code" in df.columns
    assert "list_date" in df.columns
    assert len(df) > 5000  # At least 5000 stocks


def test_gate0_not_formal_qualified():
    """Gate 0 is feasibility only, NOT formal qualification."""
    manifest_path = Path(__file__).parent.parent / "data" / "pit" / "tushare" / "4469647337475dce" / "manifest.json"
    
    with open(manifest_path) as f:
        manifest = json.load(f)
    
    # Gate 0 status is feasibility_probe_passed, NOT formal_qualified
    assert manifest["gate0_status"] != "formal_qualified"
    assert manifest["note"] == "2019-2025 feasibility only, NOT formal_qualified (requires 2010-present)"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
