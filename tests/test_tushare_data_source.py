"""
Test Tushare Data Source - M3.3

Test loading frozen Tushare snapshots and DataSource Protocol compliance.
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
from backend.app.tushare.tushare_data_source import TushareDataSource
from contracts import SCHEMA_VERSION
from contracts.stable import DailyBar, DailyStatus


class TestTushareDataSource(unittest.TestCase):
    """Test TushareDataSource with frozen snapshot."""
    
    def setUp(self):
        """Create temp snapshot for testing."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.config = TushareConfig(
            token="test_token",
            snapshot_root=self.temp_dir,
        )
        
        # Generate test snapshot
        self._generate_test_snapshot()
    
    def tearDown(self):
        """Clean up temp directory."""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
    
    def test_init_loads_manifest(self):
        """Initialization loads manifest successfully."""
        ds = TushareDataSource(self.config)
        
        self.assertIsNotNone(ds.manifest)
        self.assertEqual(ds.manifest["source"], "tushare")
        self.assertTrue(ds.manifest["is_frozen"])
    
    def test_init_fails_without_snapshot(self):
        """Initialization fails when snapshot missing."""
        empty_config = TushareConfig(
            token="test_token",
            snapshot_root=Path(tempfile.mkdtemp()),
        )
        
        with self.assertRaises(FileNotFoundError) as ctx:
            TushareDataSource(empty_config)
        
        self.assertIn("snapshot metadata not found", str(ctx.exception))
    
    def test_symbols_returns_correct_list(self):
        """symbols() returns all symbols from snapshot."""
        ds = TushareDataSource(self.config)
        
        symbols = ds.symbols()
        
        self.assertEqual(len(symbols), 2)
        self.assertIn("600519.SH", symbols)
        self.assertIn("000001.SZ", symbols)
    
    def test_get_daily_bars_returns_list(self):
        """get_daily_bars() returns list of DailyBar."""
        ds = TushareDataSource(self.config)
        
        bars = ds.get_daily_bars("600519.SH")
        
        self.assertIsInstance(bars, list)
        self.assertGreater(len(bars), 0)
        self.assertIsInstance(bars[0], DailyBar)
        self.assertEqual(bars[0].symbol, "600519.SH")
    
    def test_get_daily_bars_fails_for_missing_symbol(self):
        """get_daily_bars() raises KeyError for missing symbol."""
        ds = TushareDataSource(self.config)
        
        with self.assertRaises(KeyError) as ctx:
            ds.get_daily_bars("999999.SH")
        
        self.assertIn("Symbol not found", str(ctx.exception))
    
    def test_get_daily_bars_caches_result(self):
        """get_daily_bars() caches result on second call."""
        ds = TushareDataSource(self.config)
        
        bars1 = ds.get_daily_bars("600519.SH")
        bars2 = ds.get_daily_bars("600519.SH")
        
        # Should be same object (cached)
        self.assertIs(bars1, bars2)
    
    def test_get_daily_statuses_returns_list(self):
        """get_daily_statuses() returns list of DailyStatus."""
        ds = TushareDataSource(self.config)
        
        statuses = ds.get_daily_statuses("600519.SH")
        
        self.assertIsInstance(statuses, list)
        self.assertGreater(len(statuses), 0)
        self.assertIsInstance(statuses[0], DailyStatus)
        self.assertEqual(statuses[0].symbol, "600519.SH")
    
    def test_get_daily_statuses_fails_for_missing_symbol(self):
        """get_daily_statuses() raises KeyError for missing symbol."""
        ds = TushareDataSource(self.config)
        
        with self.assertRaises(KeyError) as ctx:
            ds.get_daily_statuses("999999.SH")
        
        self.assertIn("Symbol not found", str(ctx.exception))
    
    def test_get_daily_bar_single_date(self):
        """get_daily_bar() returns single bar for date."""
        ds = TushareDataSource(self.config)
        
        bar = ds.get_daily_bar("600519.SH", date(2023, 1, 3))
        
        self.assertIsInstance(bar, DailyBar)
        self.assertEqual(bar.symbol, "600519.SH")
        self.assertEqual(bar.date, date(2023, 1, 3))
        self.assertEqual(bar.close, 101.0)
    
    def test_get_daily_bar_fails_for_missing_date(self):
        """get_daily_bar() raises KeyError for missing date."""
        ds = TushareDataSource(self.config)
        
        with self.assertRaises(KeyError) as ctx:
            ds.get_daily_bar("600519.SH", date(2099, 12, 31))
        
        self.assertIn("No daily bar data", str(ctx.exception))
    
    def test_get_daily_status_single_date(self):
        """get_daily_status() returns single status for date."""
        ds = TushareDataSource(self.config)
        
        status = ds.get_daily_status("600519.SH", date(2023, 1, 3))
        
        self.assertIsInstance(status, DailyStatus)
        self.assertEqual(status.symbol, "600519.SH")
        self.assertEqual(status.date, date(2023, 1, 3))
        self.assertFalse(status.is_st)
    
    def test_get_daily_status_fails_for_missing_date(self):
        """get_daily_status() raises KeyError for missing date."""
        ds = TushareDataSource(self.config)
        
        with self.assertRaises(KeyError) as ctx:
            ds.get_daily_status("600519.SH", date(2099, 12, 31))
        
        self.assertIn("No daily status data", str(ctx.exception))
    
    def test_get_price_returns_close(self):
        """get_price() returns closing price."""
        ds = TushareDataSource(self.config)
        
        price = ds.get_price("600519.SH", date(2023, 1, 3))
        
        self.assertEqual(price, 101.0)
        self.assertIsInstance(price, float)
    
    def test_get_price_fails_for_missing_symbol_date(self):
        """get_price() raises KeyError for missing symbol/date."""
        ds = TushareDataSource(self.config)
        
        with self.assertRaises(KeyError):
            ds.get_price("999999.SH", date(2023, 1, 3))
        
        with self.assertRaises(KeyError):
            ds.get_price("600519.SH", date(2099, 12, 31))
    
    def test_get_metadata_returns_correct_structure(self):
        """get_metadata() returns DataSourceMetadata with correct fields."""
        ds = TushareDataSource(self.config)
        
        metadata = ds.get_metadata()
        
        self.assertEqual(metadata.schema_version, SCHEMA_VERSION)
        self.assertTrue(metadata.is_frozen)
        self.assertEqual(metadata.data_mode, "real_data")
        self.assertEqual(metadata.symbol_count, 2)
        self.assertEqual(metadata.trading_days, 3)
        self.assertIsNotNone(metadata.snapshot_hash)
    
    def test_get_metadata_snapshot_hash_matches_manifest(self):
        """get_metadata() snapshot_hash matches manifest."""
        ds = TushareDataSource(self.config)
        
        metadata = ds.get_metadata()
        
        self.assertEqual(metadata.snapshot_hash, ds.manifest["snapshot_hash"])
    
    def test_validate_returns_pass(self):
        """validate() returns pass for valid snapshot."""
        ds = TushareDataSource(self.config)
        
        result = ds.validate()
        
        self.assertEqual(result.status, "pass")
        self.assertEqual(len(result.errors), 0)
        self.assertGreater(len(result.checks_performed), 0)
    
    def test_validate_fails_for_missing_parquet(self):
        """validate() returns failed when Parquet file missing."""
        ds = TushareDataSource(self.config)
        
        # Delete one Parquet file
        (self.config.data_dir / "600519.SH_daily.parquet").unlink()
        
        result = ds.validate()
        
        self.assertEqual(result.status, "failed")
        self.assertGreater(len(result.errors), 0)
    
    def test_daily_bar_contract_validation(self):
        """DailyBar contracts are validated on load."""
        ds = TushareDataSource(self.config)
        
        bars = ds.get_daily_bars("600519.SH")
        
        for bar in bars:
            # Pydantic validation should pass
            self.assertGreaterEqual(bar.low, 0)
            self.assertLessEqual(bar.low, bar.high)
            self.assertGreaterEqual(bar.volume, 0)
            self.assertGreater(bar.adj_factor, 0)
    
    def test_daily_status_contract_validation(self):
        """DailyStatus contracts are validated on load."""
        ds = TushareDataSource(self.config)
        
        statuses = ds.get_daily_statuses("600519.SH")
        
        for status in statuses:
            # Pydantic validation should pass
            self.assertIsInstance(status.is_st, bool)
            self.assertIsInstance(status.is_suspended, bool)
            # Cannot be both limit_up and limit_down
            self.assertFalse(status.is_limit_up and status.is_limit_down)
    
    def _generate_test_snapshot(self):
        """Generate test snapshot using SnapshotGenerator."""
        # Create mock client
        mock_client = Mock()
        
        def mock_query(api_name, **kwargs):
            if api_name == "stock_basic":
                ts_code = kwargs.get("ts_code")
                return pd.DataFrame([{
                    "ts_code": ts_code,
                    "name": "茅台" if "600519" in ts_code else "平安银行",
                    "industry": "白酒",
                    "area": "贵州",
                    "list_date": "20010827",
                }])
            
            elif api_name == "trade_cal":
                return pd.DataFrame({
                    "cal_date": ["20230103", "20230104", "20230105"],
                    "is_open": [1, 1, 1],
                })
            
            elif api_name == "daily":
                return pd.DataFrame({
                    "trade_date": ["20230103", "20230104", "20230105"],
                    "open": [100.0, 101.0, 102.0],
                    "high": [102.0, 103.0, 104.0],
                    "low": [99.0, 100.0, 101.0],
                    "close": [101.0, 102.0, 103.0],
                    "vol": [10000, 11000, 12000],
                    "amount": [100000, 110000, 120000],
                })
            
            elif api_name == "adj_factor":
                return pd.DataFrame({
                    "trade_date": ["20230103", "20230104", "20230105"],
                    "adj_factor": [1.0, 1.0, 1.0],
                })
            
            elif api_name == "suspend_d":
                return pd.DataFrame()
            
            else:
                return pd.DataFrame()
        
        mock_client.query.side_effect = mock_query
        
        # Generate snapshot
        generator = SnapshotGenerator(self.config, client=mock_client)
        generator.generate_snapshot(
            symbols=["600519.SH", "000001.SZ"],
            start_date="20230101",
            end_date="20230105",
            snapshot_id="test_snapshot",
        )


if __name__ == "__main__":
    unittest.main()
