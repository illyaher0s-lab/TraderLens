"""
Test Benchmark Data Source
"""
from datetime import date
from pathlib import Path
import unittest

from backend.app.benchmark_data import BenchmarkDataSource


class TestBenchmarkDataSource(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data_source = BenchmarkDataSource()
    
    def test_loads_2_benchmarks(self):
        """Benchmark data source should load 2 benchmarks (CSI 300 + CSI 500)."""
        codes = self.data_source.codes()
        self.assertEqual(len(codes), 2)
        self.assertIn("000300.SH", codes)
        self.assertIn("000905.SH", codes)
    
    def test_get_benchmark_identity(self):
        """Should load benchmark identity info."""
        identity = self.data_source.get_benchmark_identity("000300.SH")
        self.assertEqual(identity.code, "000300.SH")
        self.assertEqual(identity.name, "沪深300")
        self.assertEqual(identity.name_en, "CSI 300")
        self.assertEqual(identity.exchange, "CSI")
        self.assertEqual(identity.index_type, "broad_market")
    
    def test_get_daily_bars(self):
        """Should load daily bars for a benchmark."""
        bars = self.data_source.get_daily_bars("000300.SH")
        
        # Should have data for ~487 trading days
        self.assertGreater(len(bars), 400)
        
        # Verify structure
        bar = bars[0]
        self.assertIsInstance(bar.date, date)
        self.assertEqual(bar.code, "000300.SH")
        self.assertGreater(bar.open, 0)
        self.assertGreater(bar.high, 0)
        self.assertGreater(bar.low, 0)
        self.assertGreater(bar.close, 0)
        self.assertGreater(bar.volume, 0)
        self.assertGreater(bar.amount, 0)
    
    def test_get_daily_bar_by_date(self):
        """Should get single bar by date."""
        bar = self.data_source.get_daily_bar("000300.SH", date(2023, 1, 3))
        self.assertEqual(bar.date, date(2023, 1, 3))
        self.assertEqual(bar.code, "000300.SH")
    
    def test_get_close_price(self):
        """Should get closing price for a date."""
        price = self.data_source.get_close_price("000300.SH", date(2023, 1, 3))
        self.assertGreater(price, 0)
        
        # Should match bar close
        bar = self.data_source.get_daily_bar("000300.SH", date(2023, 1, 3))
        self.assertEqual(price, bar.close)
    
    def test_calculate_return(self):
        """Should calculate return between two dates."""
        start_date = date(2023, 1, 3)
        end_date = date(2023, 12, 29)
        
        total_return = self.data_source.calculate_return("000300.SH", start_date, end_date)
        
        # Return should be a decimal (e.g., 0.15 for 15%)
        self.assertIsInstance(total_return, float)
        
        # For mock data (slowly rising), return should be positive
        self.assertGreater(total_return, 0)
    
    def test_unknown_benchmark_fails_loud(self):
        """Should fail loudly for unknown benchmark code."""
        with self.assertRaises(ValueError) as ctx:
            self.data_source.get_daily_bars("999999.SH")
        
        self.assertIn("Unknown benchmark code", str(ctx.exception))
    
    def test_unknown_date_fails_loud(self):
        """Should fail loudly for date without data."""
        with self.assertRaises(ValueError) as ctx:
            self.data_source.get_daily_bar("000300.SH", date(2020, 1, 1))
        
        self.assertIn("No data for", str(ctx.exception))
    
    def test_data_caching(self):
        """Should cache loaded data to avoid repeated file reads."""
        # First load
        bars1 = self.data_source.get_daily_bars("000300.SH")
        
        # Second load (should use cache)
        bars2 = self.data_source.get_daily_bars("000300.SH")
        
        # Should return same object (cached)
        self.assertIs(bars1, bars2)


if __name__ == "__main__":
    unittest.main()
