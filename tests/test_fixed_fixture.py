"""
Test Fixed Fixture Data Source
"""
from datetime import date
from pathlib import Path
import unittest

from backend.app.fixed_fixture import FixedFixtureDataSource


class TestFixedFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data_source = FixedFixtureDataSource()
    
    def test_loads_20_stocks(self):
        """Fixed fixture should contain exactly 20 stocks."""
        symbols = self.data_source.symbols()
        self.assertEqual(len(symbols), 20)
        
        # Verify expected symbols
        self.assertIn("000001.SZ", symbols)
        self.assertIn("600519.SH", symbols)
        self.assertIn("300750.SZ", symbols)
    
    def test_get_stock_identity(self):
        """Should load stock identity info."""
        identity = self.data_source.get_stock_identity("000001.SZ")
        self.assertEqual(identity.symbol, "000001.SZ")
        self.assertEqual(identity.name, "平安银行")
        self.assertEqual(identity.exchange, "SZSE")
        self.assertEqual(identity.current_status, "listed")
    
    def test_get_daily_bars(self):
        """Should load daily bars for a symbol."""
        bars = self.data_source.get_daily_bars("000001.SZ")
        
        # Should have data for ~487 trading days
        self.assertGreater(len(bars), 400)
        
        # Verify structure
        bar = bars[0]
        self.assertIsInstance(bar.date, date)
        self.assertEqual(bar.symbol, "000001.SZ")
        self.assertGreater(bar.open, 0)
        self.assertGreater(bar.high, 0)
        self.assertGreater(bar.low, 0)
        self.assertGreater(bar.close, 0)
        self.assertGreater(bar.volume, 0)
        self.assertGreater(bar.amount, 0)
        self.assertEqual(bar.adj_factor, 1.0)
    
    def test_get_daily_statuses(self):
        """Should load daily status for a symbol."""
        statuses = self.data_source.get_daily_statuses("000001.SZ")
        
        # Should have same count as bars
        bars = self.data_source.get_daily_bars("000001.SZ")
        self.assertEqual(len(statuses), len(bars))
        
        # Verify structure
        status = statuses[0]
        self.assertIsInstance(status.date, date)
        self.assertEqual(status.symbol, "000001.SZ")
        self.assertIsInstance(status.is_st, bool)
        self.assertIsInstance(status.is_suspended, bool)
        self.assertIsInstance(status.is_limit_up, bool)
        self.assertIsInstance(status.is_limit_down, bool)
    
    def test_get_daily_bar_by_date(self):
        """Should get single bar by date."""
        bar = self.data_source.get_daily_bar("000001.SZ", date(2023, 1, 3))
        self.assertEqual(bar.date, date(2023, 1, 3))
        self.assertEqual(bar.symbol, "000001.SZ")
    
    def test_get_daily_status_by_date(self):
        """Should get single status by date."""
        status = self.data_source.get_daily_status("000001.SZ", date(2023, 1, 3))
        self.assertEqual(status.date, date(2023, 1, 3))
        self.assertEqual(status.symbol, "000001.SZ")
    
    def test_get_price_implements_price_provider(self):
        """Should implement PriceProvider protocol."""
        price = self.data_source.get_price("000001.SZ", date(2023, 1, 3))
        self.assertGreater(price, 0)
        
        # Should return closing price
        bar = self.data_source.get_daily_bar("000001.SZ", date(2023, 1, 3))
        self.assertEqual(price, bar.close)
    
    def test_get_manifest(self):
        """Should return manifest metadata."""
        manifest = self.data_source.get_manifest()
        self.assertEqual(manifest["dataset_name"], "20-stock-fixture")
        self.assertEqual(manifest["stock_count"], 20)
        self.assertEqual(manifest["trading_days_count"], 487)
        self.assertEqual(manifest["source"], "mock")
    
    def test_unknown_symbol_fails_loud(self):
        """Should fail loudly for unknown symbol."""
        with self.assertRaises(ValueError) as ctx:
            self.data_source.get_daily_bars("999999.SZ")
        
        self.assertIn("Unknown symbol", str(ctx.exception))
    
    def test_unknown_date_fails_loud(self):
        """Should fail loudly for date without data."""
        with self.assertRaises(ValueError) as ctx:
            self.data_source.get_daily_bar("000001.SZ", date(2020, 1, 1))
        
        self.assertIn("No data for", str(ctx.exception))
    
    def test_data_caching(self):
        """Should cache loaded data to avoid repeated file reads."""
        # First load
        bars1 = self.data_source.get_daily_bars("000001.SZ")
        
        # Second load (should use cache)
        bars2 = self.data_source.get_daily_bars("000001.SZ")
        
        # Should return same object (cached)
        self.assertIs(bars1, bars2)


if __name__ == "__main__":
    unittest.main()
