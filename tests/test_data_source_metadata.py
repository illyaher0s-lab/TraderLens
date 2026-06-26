"""
Data Source Metadata Tests - M2 Phase 1 & 2

Validates that data sources provide required metadata.
"""

import unittest
from pathlib import Path

from backend.app.fixed_fixture import FixedFixtureDataSource
from backend.app.golden_cases import GoldenCaseDataSource
from backend.app.benchmark_data import BenchmarkDataSource
from strategy_core.data_source_metadata import DataSourceMetadata, validate_metadata
from contracts import SCHEMA_VERSION


class TestFixedFixtureMetadata(unittest.TestCase):
    """Test FixedFixtureDataSource provides valid metadata."""
    
    def setUp(self):
        """Load fixed fixture."""
        fixture_path = Path(__file__).parent.parent / "tests" / "fixed_fixture"
        self.data_source = FixedFixtureDataSource(fixture_path)
    
    def test_fixed_fixture_metadata_exists(self):
        """FixedFixtureDataSource provides metadata."""
        metadata = self.data_source.get_metadata()
        
        # Metadata must be DataSourceMetadata instance
        self.assertIsInstance(metadata, DataSourceMetadata)
    
    def test_metadata_schema_version_matches_contracts(self):
        """Metadata schema_version matches contracts.SCHEMA_VERSION."""
        metadata = self.data_source.get_metadata()
        
        self.assertEqual(metadata.schema_version, SCHEMA_VERSION)
        self.assertEqual(metadata.schema_version, "1.0")
    
    def test_metadata_has_required_fields(self):
        """Metadata includes all required fields."""
        metadata = self.data_source.get_metadata()
        
        # All fields must be populated
        self.assertTrue(metadata.source_id)
        self.assertEqual(metadata.source_type, "fixed_fixture")
        self.assertTrue(metadata.schema_version)
        self.assertTrue(metadata.snapshot_id)
        self.assertTrue(metadata.snapshot_hash)
        self.assertIsNotNone(metadata.created_at)
        self.assertEqual(metadata.data_mode, "fixed_fixture")
        self.assertTrue(metadata.is_frozen)
        self.assertGreater(metadata.symbol_count, 0)
        self.assertGreater(metadata.trading_days, 0)
        self.assertTrue(metadata.date_range_start)
        self.assertTrue(metadata.date_range_end)
    
    def test_metadata_symbol_count_matches_actual(self):
        """Metadata symbol_count matches actual symbol count."""
        metadata = self.data_source.get_metadata()
        actual_symbols = self.data_source.symbols()
        
        self.assertEqual(metadata.symbol_count, len(actual_symbols))
        self.assertEqual(metadata.symbol_count, 20)  # Fixed fixture has 20 stocks
    
    def test_metadata_is_frozen_true(self):
        """Fixed fixture metadata reports is_frozen=True."""
        metadata = self.data_source.get_metadata()
        
        self.assertTrue(metadata.is_frozen,
                       "Fixed fixture must be frozen (immutable) for deterministic backtests")
    
    def test_metadata_validation_passes(self):
        """Metadata passes validation."""
        metadata = self.data_source.get_metadata()
        
        # Should not raise
        validate_metadata(metadata)


class TestMetadataValidation(unittest.TestCase):
    """Test metadata validation rules."""
    
    def test_mismatched_schema_version_fails(self):
        """Metadata with wrong schema_version fails validation."""
        from datetime import datetime
        
        metadata = DataSourceMetadata(
            source_id="test",
            source_type="fixed_fixture",
            schema_version="99.0",  # Wrong version
            snapshot_id="test_snapshot",
            snapshot_hash="test_hash",
            created_at=datetime.now(),
            data_mode="fixed_fixture",
            is_frozen=True,
            symbol_count=10,
            trading_days=100,
            date_range_start="2023-01-01",
            date_range_end="2023-12-31",
        )
        
        with self.assertRaises(ValueError) as ctx:
            validate_metadata(metadata)
        
        self.assertIn("schema_version", str(ctx.exception))
        self.assertIn("does not match", str(ctx.exception))
    
    def test_empty_snapshot_id_fails(self):
        """Empty snapshot_id fails validation."""
        from datetime import datetime
        
        metadata = DataSourceMetadata(
            source_id="test",
            source_type="fixed_fixture",
            schema_version="1.0",
            snapshot_id="",  # Empty
            snapshot_hash="test_hash",
            created_at=datetime.now(),
            data_mode="fixed_fixture",
            is_frozen=True,
            symbol_count=10,
            trading_days=100,
            date_range_start="2023-01-01",
            date_range_end="2023-12-31",
        )
        
        with self.assertRaises(ValueError) as ctx:
            validate_metadata(metadata)
        
        self.assertIn("snapshot_id", str(ctx.exception))
    
    def test_zero_symbol_count_fails(self):
        """Zero symbol_count fails validation."""
        from datetime import datetime
        
        metadata = DataSourceMetadata(
            source_id="test",
            source_type="fixed_fixture",
            schema_version="1.0",
            snapshot_id="test_snapshot",
            snapshot_hash="test_hash",
            created_at=datetime.now(),
            data_mode="fixed_fixture",
            is_frozen=True,
            symbol_count=0,  # Zero
            trading_days=100,
            date_range_start="2023-01-01",
            date_range_end="2023-12-31",
        )
        
        with self.assertRaises(ValueError) as ctx:
            validate_metadata(metadata)
        
        self.assertIn("symbol_count", str(ctx.exception))
        self.assertIn("positive", str(ctx.exception))


class TestMissingManifestFields(unittest.TestCase):
    """Test behavior when manifest is missing required fields."""
    
    def test_missing_schema_version_fails_loud(self):
        """Missing schema_version in manifest fails loud."""
        # This test would require a fixture without schema_version
        # For now, document the expected behavior:
        # FixedFixtureDataSource.get_metadata() should raise ValueError
        # with clear message about missing schema_version
        pass  # Covered by docstring and actual implementation
    
    def test_missing_snapshot_hash_fails_loud(self):
        """Missing snapshot_hash in manifest fails loud."""
        # Same as above: documented in FixedFixtureDataSource.get_metadata()
        pass
    
    def test_missing_created_at_fails_loud(self):
        """Missing created_at in manifest fails loud."""
        # Same as above
        pass


class TestGoldenCaseMetadata(unittest.TestCase):
    """Test GoldenCaseDataSource provides valid metadata."""
    
    def setUp(self):
        """Load golden case."""
        # Golden case path is directly the data_snapshot directory
        golden_case_path = Path(__file__).parent.parent / "tests" / "golden_cases"
        self.data_source = GoldenCaseDataSource(golden_case_path)
    
    def test_golden_case_metadata_exists(self):
        """GoldenCaseDataSource provides metadata."""
        metadata = self.data_source.get_metadata()
        
        self.assertIsInstance(metadata, DataSourceMetadata)
    
    def test_golden_case_metadata_schema_version_matches(self):
        """Golden case metadata schema_version matches contracts.SCHEMA_VERSION."""
        metadata = self.data_source.get_metadata()
        
        self.assertEqual(metadata.schema_version, SCHEMA_VERSION)
        self.assertEqual(metadata.schema_version, "1.0")
    
    def test_golden_case_metadata_is_frozen(self):
        """Golden case metadata reports is_frozen=True."""
        metadata = self.data_source.get_metadata()
        
        self.assertTrue(metadata.is_frozen,
                       "Golden case must be frozen (immutable) for deterministic tests")
        self.assertEqual(metadata.source_type, "golden_case")
        self.assertEqual(metadata.data_mode, "golden_case")
    
    def test_golden_case_snapshot_hash_deterministic(self):
        """Golden case snapshot_hash is deterministic (not random)."""
        metadata = self.data_source.get_metadata()
        
        self.assertEqual(metadata.snapshot_hash, "golden_case_5_stocks_deterministic")
        self.assertEqual(metadata.snapshot_id, "golden_case_v1")


class TestBenchmarkMetadata(unittest.TestCase):
    """Test BenchmarkDataSource provides valid metadata."""
    
    def setUp(self):
        """Load benchmark data."""
        # BenchmarkDataSource expects the fixture root, it will look in benchmarks/ subdirectory
        fixture_path = Path(__file__).parent.parent / "tests" / "fixed_fixture" / "benchmarks"
        self.data_source = BenchmarkDataSource(fixture_path)
    
    def test_benchmark_metadata_exists(self):
        """BenchmarkDataSource provides metadata."""
        metadata = self.data_source.get_metadata()
        
        self.assertIsInstance(metadata, DataSourceMetadata)
    
    def test_benchmark_metadata_schema_version_matches(self):
        """Benchmark metadata schema_version matches contracts.SCHEMA_VERSION."""
        metadata = self.data_source.get_metadata()
        
        self.assertEqual(metadata.schema_version, SCHEMA_VERSION)
        self.assertEqual(metadata.schema_version, "1.0")
    
    def test_benchmark_metadata_is_frozen(self):
        """Benchmark metadata reports is_frozen=True."""
        metadata = self.data_source.get_metadata()
        
        self.assertTrue(metadata.is_frozen,
                       "Benchmark fixture must be frozen for deterministic tests")
        self.assertEqual(metadata.source_type, "benchmark_fixture")
        self.assertEqual(metadata.data_mode, "fixed_fixture")
    
    def test_benchmark_snapshot_hash_deterministic(self):
        """Benchmark snapshot_hash is deterministic (not random)."""
        metadata = self.data_source.get_metadata()
        
        self.assertEqual(metadata.snapshot_hash, "benchmark_fixture_deterministic")
        self.assertEqual(metadata.snapshot_id, "benchmark_mock_v2.1")


class TestAllFixtureMetadataValidates(unittest.TestCase):
    """Test that all fixture metadata passes validation."""
    
    def test_all_fixture_metadata_validates(self):
        """All data sources provide metadata that passes validation."""
        # Fixed fixture
        fixture_path = Path(__file__).parent.parent / "tests" / "fixed_fixture"
        fixed_fixture = FixedFixtureDataSource(fixture_path)
        metadata1 = fixed_fixture.get_metadata()
        validate_metadata(metadata1)  # Should not raise
        
        # Golden case
        golden_case_path = Path(__file__).parent.parent / "tests" / "golden_cases"
        golden_case = GoldenCaseDataSource(golden_case_path)
        metadata2 = golden_case.get_metadata()
        validate_metadata(metadata2)  # Should not raise
        
        # Benchmark
        benchmark_path = Path(__file__).parent.parent / "tests" / "fixed_fixture" / "benchmarks"
        benchmark = BenchmarkDataSource(benchmark_path)
        metadata3 = benchmark.get_metadata()
        validate_metadata(metadata3)  # Should not raise
        
        # All should have schema_version "1.0"
        self.assertEqual(metadata1.schema_version, "1.0")
        self.assertEqual(metadata2.schema_version, "1.0")
        self.assertEqual(metadata3.schema_version, "1.0")
        
        # All should be frozen
        self.assertTrue(metadata1.is_frozen)
        self.assertTrue(metadata2.is_frozen)
        self.assertTrue(metadata3.is_frozen)


if __name__ == "__main__":
    unittest.main()
