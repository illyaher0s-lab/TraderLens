"""
Test Tushare Snapshot Generator - M3.2

Test snapshot generation with mocked TushareClient.
"""

import json
import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock

import pandas as pd

from backend.app.tushare.config import TushareConfig
from backend.app.tushare.snapshot_generator import SnapshotGenerator
from contracts import SCHEMA_VERSION


class TestSnapshotGenerator(unittest.TestCase):
    """Test snapshot generation with mocked API."""
    
    def setUp(self):
        """Create temp directory for test snapshots."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.config = TushareConfig(
            token="test_token",
            snapshot_root=self.temp_dir,
        )
        
        # Create mock client
        self.mock_client = Mock()
        self.generator = SnapshotGenerator(self.config, client=self.mock_client)
    
    def tearDown(self):
        """Clean up temp directory."""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
    
    def test_generate_snapshot_creates_files(self):
        """Snapshot generation creates all required files."""
        # Mock API responses
        self._setup_mock_responses(["600519.SH", "000001.SZ"])
        
        # Generate snapshot
        self.generator.generate_snapshot(
            symbols=["600519.SH", "000001.SZ"],
            start_date="20230101",
            end_date="20230105",  # 3 trading days (假设)
            snapshot_id="test_2stocks_3days",
        )
        
        # Verify files exist
        self.assertTrue((self.config.metadata_dir / "manifest.json").exists())
        self.assertTrue((self.config.metadata_dir / "stock_list.json").exists())
        self.assertTrue((self.config.metadata_dir / "trade_calendar.json").exists())
        
        self.assertTrue((self.config.data_dir / "600519.SH_daily.parquet").exists())
        self.assertTrue((self.config.data_dir / "600519.SH_status.parquet").exists())
        self.assertTrue((self.config.data_dir / "000001.SZ_daily.parquet").exists())
        self.assertTrue((self.config.data_dir / "000001.SZ_status.parquet").exists())
    
    def test_manifest_has_required_fields(self):
        """Manifest contains all required fields."""
        self._setup_mock_responses(["600519.SH"])
        
        self.generator.generate_snapshot(
            symbols=["600519.SH"],
            start_date="20230101",
            end_date="20230105",
            snapshot_id="test_1stock",
        )
        
        manifest_file = self.config.metadata_dir / "manifest.json"
        with open(manifest_file, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        
        # Check required fields
        required = [
            "dataset_name", "version", "source", "fetched_at", "created_at",
            "date_range", "schema_version", "snapshot_hash", "is_frozen",
            "stock_count", "trading_days_count", "stocks"
        ]
        
        for field in required:
            self.assertIn(field, manifest, f"Manifest missing field: {field}")
        
        # Check values
        self.assertEqual(manifest["source"], "tushare")
        self.assertEqual(manifest["schema_version"], SCHEMA_VERSION)
        self.assertTrue(manifest["is_frozen"])
        self.assertEqual(manifest["stock_count"], 1)
        self.assertEqual(manifest["stocks"], ["600519.SH"])
    
    def test_snapshot_hash_is_deterministic(self):
        """Same data produces same hash."""
        self._setup_mock_responses(["600519.SH"])
        
        # Generate first snapshot
        self.generator.generate_snapshot(
            symbols=["600519.SH"],
            start_date="20230101",
            end_date="20230105",
            snapshot_id="test_hash_1",
        )
        
        manifest_file = self.config.metadata_dir / "manifest.json"
        with open(manifest_file, "r", encoding="utf-8") as f:
            manifest1 = json.load(f)
        
        hash1 = manifest1["snapshot_hash"]
        
        # Clean up and regenerate
        shutil.rmtree(self.temp_dir)
        self.temp_dir.mkdir()
        self.config.ensure_directories()
        
        self._setup_mock_responses(["600519.SH"])
        
        self.generator.generate_snapshot(
            symbols=["600519.SH"],
            start_date="20230101",
            end_date="20230105",
            snapshot_id="test_hash_2",  # Different snapshot_id
        )
        
        with open(manifest_file, "r", encoding="utf-8") as f:
            manifest2 = json.load(f)
        
        hash2 = manifest2["snapshot_hash"]
        
        # Hash should be identical (snapshot_id not in hash)
        self.assertEqual(hash1, hash2, "Snapshot hash should be deterministic")
    
    def test_validate_snapshot_pass(self):
        """Validation passes for valid snapshot."""
        self._setup_mock_responses(["600519.SH"])
        
        self.generator.generate_snapshot(
            symbols=["600519.SH"],
            start_date="20230101",
            end_date="20230105",
            snapshot_id="test_valid",
        )
        
        result = self.generator.validate_snapshot()
        
        self.assertEqual(result["status"], "pass")
        self.assertEqual(len(result["errors"]), 0)
    
    def test_validate_snapshot_fails_missing_manifest(self):
        """Validation fails when manifest missing."""
        result = self.generator.validate_snapshot()
        
        self.assertEqual(result["status"], "failed")
        self.assertGreater(len(result["errors"]), 0)
        self.assertIn("Manifest not found", result["errors"][0])
    
    def test_validate_snapshot_fails_missing_parquet(self):
        """Validation fails when Parquet files missing."""
        self._setup_mock_responses(["600519.SH"])
        
        self.generator.generate_snapshot(
            symbols=["600519.SH"],
            start_date="20230101",
            end_date="20230105",
            snapshot_id="test_missing_parquet",
        )
        
        # Delete one Parquet file
        (self.config.data_dir / "600519.SH_daily.parquet").unlink()
        
        result = self.generator.validate_snapshot()
        
        self.assertEqual(result["status"], "failed")
        self.assertTrue(any("Missing daily data" in err for err in result["errors"]))
    
    def test_stock_list_json_structure(self):
        """stock_list.json has correct structure."""
        self._setup_mock_responses(["600519.SH"])
        
        self.generator.generate_snapshot(
            symbols=["600519.SH"],
            start_date="20230101",
            end_date="20230105",
            snapshot_id="test_stock_list",
        )
        
        stock_list_file = self.config.metadata_dir / "stock_list.json"
        with open(stock_list_file, "r", encoding="utf-8") as f:
            stock_list = json.load(f)
        
        self.assertEqual(len(stock_list), 1)
        
        stock = stock_list[0]
        required_fields = ["symbol", "name", "exchange", "list_date", "current_status", "industry", "sector"]
        
        for field in required_fields:
            self.assertIn(field, stock, f"Stock missing field: {field}")
        
        self.assertEqual(stock["symbol"], "600519.SH")
        self.assertEqual(stock["exchange"], "SSE")
    
    def test_trade_calendar_sorted(self):
        """Trade calendar is sorted."""
        self._setup_mock_responses(["600519.SH"])
        
        self.generator.generate_snapshot(
            symbols=["600519.SH"],
            start_date="20230101",
            end_date="20230105",
            snapshot_id="test_calendar",
        )
        
        calendar_file = self.config.metadata_dir / "trade_calendar.json"
        with open(calendar_file, "r", encoding="utf-8") as f:
            calendar_data = json.load(f)
        
        trading_dates = calendar_data["trading_dates"]
        
        self.assertEqual(trading_dates, sorted(trading_dates), "Trade calendar should be sorted")
        self.assertGreater(len(trading_dates), 0)
    
    def _setup_mock_responses(self, symbols: list[str]):
        """Setup mock API responses."""
        def mock_query(api_name, **kwargs):
            if api_name == "stock_basic":
                # Return stock identity
                ts_code = kwargs.get("ts_code")
                return pd.DataFrame([{
                    "ts_code": ts_code,
                    "name": "茅台" if "600519" in ts_code else "平安银行",
                    "industry": "白酒",
                    "area": "贵州",
                    "list_date": "20010827",
                }])
            
            elif api_name == "trade_cal":
                # Return 3 trading days
                return pd.DataFrame({
                    "cal_date": ["20230103", "20230104", "20230105"],
                    "is_open": [1, 1, 1],
                })
            
            elif api_name == "daily":
                # Return daily bars
                ts_code = kwargs.get("ts_code")
                return pd.DataFrame({
                    "trade_date": ["20230103", "20230104", "20230105"],
                    "open": [100.0, 101.0, 102.0],
                    "high": [102.0, 103.0, 104.0],
                    "low": [99.0, 100.0, 101.0],
                    "close": [101.0, 102.0, 103.0],
                    "vol": [10000, 11000, 12000],  # 手
                    "amount": [100000, 110000, 120000],  # 千元
                })
            
            elif api_name == "adj_factor":
                # Return adj_factor
                return pd.DataFrame({
                    "trade_date": ["20230103", "20230104", "20230105"],
                    "adj_factor": [1.0, 1.0, 1.0],
                })
            
            elif api_name == "suspend_d":
                # No suspensions
                return pd.DataFrame()
            
            else:
                return pd.DataFrame()
        
        self.mock_client.query.side_effect = mock_query


if __name__ == "__main__":
    unittest.main()
