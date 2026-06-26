"""
Data Source Behavior Tests - M2 Phase 4

Tests data source boundary behaviors:
- Missing data fail-loud policy
- Frozen snapshot guarantee
- Cache key stability
"""

import unittest
from pathlib import Path
from datetime import date

from backend.app.fixed_fixture import FixedFixtureDataSource
from backend.app.golden_cases import GoldenCaseDataSource
from backend.app.benchmark_data import BenchmarkDataSource


class TestMissingDataFailLoud(unittest.TestCase):
    """Test that missing data raises KeyError (fail-loud, no guessing)."""
    
    def setUp(self):
        """Load data sources."""
        self.fixture_path = Path(__file__).parent.parent / "tests" / "fixed_fixture"
        self.golden_path = Path(__file__).parent.parent / "tests" / "golden_cases"
        
        self.fixed_fixture = FixedFixtureDataSource(self.fixture_path)
        self.golden_case = GoldenCaseDataSource(self.golden_path)
    
    def test_unknown_symbol_fails_loud_fixed_fixture(self):
        """FixedFixture: unknown symbol → KeyError."""
        with self.assertRaises((KeyError, ValueError)) as ctx:
            self.fixed_fixture.get_daily_bars("UNKNOWN.XX")
        
        # Error message should mention the symbol
        self.assertIn("UNKNOWN", str(ctx.exception))
    
    def test_unknown_symbol_fails_loud_golden_case(self):
        """GoldenCase: unknown symbol → KeyError."""
        with self.assertRaises(KeyError) as ctx:
            self.golden_case.get_daily_bar("UNKNOWN.XX", date(2023, 1, 3))
        
        self.assertIn("UNKNOWN", str(ctx.exception))
    
    def test_missing_bar_date_fails_loud(self):
        """Missing bar date → KeyError (do not guess or interpolate)."""
        # Use a date far in the future that won't exist in fixture
        future_date = date(2099, 12, 31)
        
        symbol = self.fixed_fixture.symbols()[0]
        
        with self.assertRaises((KeyError, ValueError)) as ctx:
            self.fixed_fixture.get_daily_bar(symbol, future_date)
        
        # Error should mention date or symbol
        error_str = str(ctx.exception)
        self.assertTrue("2099" in error_str or symbol in error_str)
    
    def test_missing_status_date_fails_loud(self):
        """Missing status date → KeyError (do not guess)."""
        future_date = date(2099, 12, 31)
        symbol = self.fixed_fixture.symbols()[0]
        
        with self.assertRaises((KeyError, ValueError)) as ctx:
            self.fixed_fixture.get_daily_status(symbol, future_date)
        
        error_str = str(ctx.exception)
        self.assertTrue("2099" in error_str or symbol in error_str)
    
    def test_missing_price_date_fails_loud(self):
        """Missing price date → KeyError via get_price (PriceProvider)."""
        future_date = date(2099, 12, 31)
        symbol = self.fixed_fixture.symbols()[0]
        
        with self.assertRaises((KeyError, ValueError)) as ctx:
            self.fixed_fixture.get_price(symbol, future_date)
        
        error_str = str(ctx.exception)
        self.assertTrue("2099" in error_str or symbol in error_str)


class TestFrozenSnapshot(unittest.TestCase):
    """Test that data sources report frozen snapshot (immutable)."""
    
    def setUp(self):
        """Load data sources."""
        fixture_path = Path(__file__).parent.parent / "tests" / "fixed_fixture"
        golden_path = Path(__file__).parent.parent / "tests" / "golden_cases"
        benchmark_path = Path(__file__).parent.parent / "tests" / "fixed_fixture" / "benchmarks"
        
        self.fixed_fixture = FixedFixtureDataSource(fixture_path)
        self.golden_case = GoldenCaseDataSource(golden_path)
        self.benchmark = BenchmarkDataSource(benchmark_path)
    
    def test_fixed_fixture_is_frozen(self):
        """FixedFixture metadata reports is_frozen=True."""
        metadata = self.fixed_fixture.get_metadata()
        
        self.assertTrue(metadata.is_frozen,
                       "FixedFixture must be frozen for deterministic backtests")
    
    def test_golden_case_is_frozen(self):
        """GoldenCase metadata reports is_frozen=True."""
        metadata = self.golden_case.get_metadata()
        
        self.assertTrue(metadata.is_frozen,
                       "GoldenCase must be frozen for deterministic tests")
    
    def test_benchmark_is_frozen(self):
        """Benchmark metadata reports is_frozen=True."""
        metadata = self.benchmark.get_metadata()
        
        self.assertTrue(metadata.is_frozen,
                       "Benchmark must be frozen for deterministic tests")
    
    def test_snapshot_hash_is_stable(self):
        """Snapshot hash is stable (not random, not time-based)."""
        metadata1 = self.fixed_fixture.get_metadata()
        metadata2 = self.fixed_fixture.get_metadata()
        
        # Hash should be identical across calls
        self.assertEqual(metadata1.snapshot_hash, metadata2.snapshot_hash)
        
        # Hash should not be empty or generic
        self.assertNotEqual(metadata1.snapshot_hash, "")
        self.assertNotEqual(metadata1.snapshot_hash, "snapshot")
    
    def test_metadata_consistent_across_calls(self):
        """get_metadata() returns consistent results."""
        metadata1 = self.fixed_fixture.get_metadata()
        metadata2 = self.fixed_fixture.get_metadata()
        
        # All fields should be identical
        self.assertEqual(metadata1.source_id, metadata2.source_id)
        self.assertEqual(metadata1.source_type, metadata2.source_type)
        self.assertEqual(metadata1.schema_version, metadata2.schema_version)
        self.assertEqual(metadata1.snapshot_id, metadata2.snapshot_id)
        self.assertEqual(metadata1.snapshot_hash, metadata2.snapshot_hash)
        self.assertEqual(metadata1.is_frozen, metadata2.is_frozen)
        self.assertEqual(metadata1.symbol_count, metadata2.symbol_count)
        self.assertEqual(metadata1.trading_days, metadata2.trading_days)


class TestCacheKeyStability(unittest.TestCase):
    """Test that cache key components are stable."""
    
    def setUp(self):
        """Load data sources."""
        fixture_path = Path(__file__).parent.parent / "tests" / "fixed_fixture"
        self.fixed_fixture = FixedFixtureDataSource(fixture_path)
    
    def test_cache_key_components_present(self):
        """Cache key components (source_type, schema_version, snapshot_hash) are present."""
        metadata = self.fixed_fixture.get_metadata()
        
        # All cache key components must be non-empty
        self.assertTrue(metadata.source_type)
        self.assertTrue(metadata.schema_version)
        self.assertTrue(metadata.snapshot_hash)
    
    def test_cache_key_deterministic(self):
        """Cache key components are deterministic."""
        metadata1 = self.fixed_fixture.get_metadata()
        metadata2 = self.fixed_fixture.get_metadata()
        
        # Construct cache key
        cache_key_1 = f"{metadata1.source_type}:{metadata1.schema_version}:{metadata1.snapshot_hash}"
        cache_key_2 = f"{metadata2.source_type}:{metadata2.schema_version}:{metadata2.snapshot_hash}"
        
        # Cache keys should be identical
        self.assertEqual(cache_key_1, cache_key_2)
    
    def test_golden_case_cache_key_deterministic(self):
        """GoldenCase cache key is deterministic."""
        golden_path = Path(__file__).parent.parent / "tests" / "golden_cases"
        golden_case = GoldenCaseDataSource(golden_path)
        
        metadata1 = golden_case.get_metadata()
        metadata2 = golden_case.get_metadata()
        
        cache_key_1 = f"{metadata1.source_type}:{metadata1.schema_version}:{metadata1.snapshot_hash}"
        cache_key_2 = f"{metadata2.source_type}:{metadata2.schema_version}:{metadata2.snapshot_hash}"
        
        self.assertEqual(cache_key_1, cache_key_2)
        
        # Golden case should have deterministic hash (not random)
        self.assertEqual(metadata1.snapshot_hash, "golden_case_5_stocks_deterministic")


if __name__ == "__main__":
    unittest.main()
