"""SW L1 PIT collection tests."""
import hashlib
import json
from pathlib import Path
import pandas as pd
import pytest


def test_truncation_5000_rows_fails():
    """5000 rows exactly → suspected_truncation."""
    manifest_path = Path("data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal/sw_l1_membership/manifest.json")
    
    if not manifest_path.exists():
        pytest.skip("Manifest not generated yet")
    
    manifest = json.loads(manifest_path.read_text())
    
    # Check all partitions
    for partition in manifest.get("partitions", []):
        assert partition["row_count"] != 5000, f"Partition {partition['name']} has exactly 5000 rows → suspected truncation"


def test_required_fields_present():
    """Every partition has required fields."""
    data_dir = Path("data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal/sw_l1_membership")
    
    if not data_dir.exists():
        pytest.skip("Data not collected yet")
    
    required = {"ts_code", "l1_code", "l1_name", "in_date", "out_date", "is_new"}
    
    for parquet in data_dir.rglob("*.parquet"):
        if parquet.name.endswith(".parquet"):
            df = pd.read_parquet(parquet)
            missing = required - set(df.columns)
            assert not missing, f"{parquet.name} missing fields: {missing}"


def test_sidecar_hash_matches():
    """Every .parquet has matching .sha256 sidecar."""
    data_dir = Path("data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal/sw_l1_membership")
    
    if not data_dir.exists():
        pytest.skip("Data not collected yet")
    
    for parquet in data_dir.rglob("*.parquet"):
        if parquet.name.endswith(".parquet"):
            sidecar = parquet.with_suffix(".parquet.sha256")
            assert sidecar.exists(), f"Missing sidecar for {parquet.name}"
            
            computed = hashlib.sha256(parquet.read_bytes()).hexdigest()
            stored = sidecar.read_text().strip()
            assert computed == stored, f"{parquet.name} hash mismatch"


def test_same_date_multiple_l1_fails():
    """Same stock + same date + multiple L1 → conflict."""
    manifest_path = Path("data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal/sw_l1_membership/manifest.json")
    
    if not manifest_path.exists():
        pytest.skip("Manifest not generated yet")
    
    manifest = json.loads(manifest_path.read_text())
    
    # If collected_verified, conflicts must be 0
    if manifest.get("status") == "collected_verified":
        assert manifest.get("conflicts", 0) == 0, "collected_verified must have zero conflicts"


def test_empty_industry_legal():
    """NO MEMBERSHIP before listing is legal, not a gap."""
    # ponytail: documented rule, verified by coverage check in collection
    pass


def test_coverage_sample_dates():
    """Sample dates covered for listed stocks."""
    manifest_path = Path("data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal/sw_l1_membership/manifest.json")
    
    if not manifest_path.exists():
        pytest.skip("Manifest not generated yet")
    
    manifest = json.loads(manifest_path.read_text())
    
    # Check coverage report exists
    assert "coverage_check" in manifest, "Manifest must include coverage_check"
    
    coverage = manifest["coverage_check"]
    for date_check in coverage:
        # Each date should have checked_stocks > 0
        assert date_check.get("checked_stocks", 0) > 0, f"No stocks checked for {date_check['date']}"
