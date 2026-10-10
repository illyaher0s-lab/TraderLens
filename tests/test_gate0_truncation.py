"""Gate 0 truncation detection tests."""
import pandas as pd
import pytest
from pathlib import Path


def test_no_partition_hits_5000_row_limit():
    """No monthly partition should hit the 5000-row limit."""
    snapshot_dir = Path("data/pit/tushare").glob("*/")
    snapshots = [d for d in snapshot_dir if d.is_dir() and not d.name.startswith(".")]
    
    if not snapshots:
        pytest.skip("No snapshots found")
    
    latest = max(snapshots, key=lambda p: p.stat().st_mtime)
    suspend_d_path = latest / "suspend_d.parquet"
    
    if not suspend_d_path.exists():
        pytest.skip("suspend_d.parquet not found")
    
    df = pd.read_parquet(suspend_d_path)
    df['month'] = pd.to_datetime(df['trade_date'], format='%Y%m%d').dt.to_period('M')
    monthly_counts = df.groupby('month').size()
    
    max_rows = monthly_counts.max()
    assert max_rows < 5000, f"Monthly partition hit 5000-row limit: {monthly_counts[monthly_counts == 5000]}"


def test_truncation_status_blocks_probe():
    """Gate 0 probe must fail if any interface has truncated status."""
    snapshot_dir = Path("data/pit/tushare").glob("*/")
    snapshots = [d for d in snapshot_dir if d.is_dir() and not d.name.startswith(".")]
    
    if not snapshots:
        pytest.skip("No snapshots found")
    
    latest = max(snapshots, key=lambda p: p.stat().st_mtime)
    manifest_path = latest / "manifest.json"
    
    if not manifest_path.exists():
        pytest.skip("manifest.json not found")
    
    import json
    with open(manifest_path) as f:
        manifest = json.load(f)
    
    # If interface_status exists and any interface is truncated, gate0_status must NOT be feasibility_probe_passed
    if "interface_status" in manifest:
        truncated = [k for k, v in manifest["interface_status"].items() if v.get("status") == "truncated"]
        if truncated:
            assert manifest.get("gate0_status") != "feasibility_probe_passed", \
                f"Manifest reports feasibility_probe_passed despite truncated interfaces: {truncated}"
            assert manifest.get("feasibility_probe_passed") is False, \
                "feasibility_probe_passed must be False when interfaces are truncated"


def test_2022_q3_q4_refined_to_monthly():
    """Verify Q3/Q4 2022 (previously 5000 rows) were refined to monthly partitions."""
    snapshot_dir = Path("data/pit/tushare").glob("*/")
    snapshots = [d for d in snapshot_dir if d.is_dir() and not d.name.startswith(".")]
    
    if not snapshots:
        pytest.skip("No snapshots found")
    
    latest = max(snapshots, key=lambda p: p.stat().st_mtime)
    suspend_d_path = latest / "suspend_d.parquet"
    
    if not suspend_d_path.exists():
        pytest.skip("suspend_d.parquet not found")
    
    df = pd.read_parquet(suspend_d_path)
    df['month'] = pd.to_datetime(df['trade_date'], format='%Y%m%d').dt.to_period('M')
    
    # Check that Jul-Sep 2022 and Oct-Dec 2022 are present as individual months
    q3_2022_months = ['2022-07', '2022-08', '2022-09']
    q4_2022_months = ['2022-10', '2022-11', '2022-12']
    
    present_months = set(df['month'].astype(str).unique())
    
    for m in q3_2022_months + q4_2022_months:
        assert m in present_months, f"Expected monthly partition {m} not found (quarterly refinement failed)"
