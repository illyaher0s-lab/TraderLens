"""
Data Source Protocol Conformance Tests - M2 Phase 3

Validates that data sources conform to DataSource Protocol.
"""

import unittest
from pathlib import Path

from backend.app.fixed_fixture import FixedFixtureDataSource
from backend.app.golden_cases import GoldenCaseDataSource
from backend.app.benchmark_data import BenchmarkDataSource
from strategy_core.data_source_protocol import DataSource, DataSourceValidationResult


class TestProtocolConformance(unittest.TestCase):
    """Test that data sources conform to DataSource Protocol."""
    
    def test_golden_case_conforms_to_data_source_protocol(self):
        """GoldenCaseDataSource implements DataSource Protocol."""
        golden_case_path = Path(__file__).parent.parent / "tests" / "golden_cases"
        data_source = GoldenCaseDataSource(golden_case_path)
        
        # Check that it has all required methods
        self.assertTrue(hasattr(data_source, "get_metadata"))
        self.assertTrue(hasattr(data_source, "validate"))
        self.assertTrue(hasattr(data_source, "symbols"))
        self.assertTrue(hasattr(data_source, "get_daily_bars"))
        self.assertTrue(hasattr(data_source, "get_daily_statuses"))
        self.assertTrue(hasattr(data_source, "get_daily_bar"))
        self.assertTrue(hasattr(data_source, "get_daily_status"))
        self.assertTrue(hasattr(data_source, "get_price"))
        
        # All methods should be callable
        self.assertTrue(callable(data_source.get_metadata))
        self.assertTrue(callable(data_source.validate))
        self.assertTrue(callable(data_source.symbols))
    
    def test_fixed_fixture_conforms_to_data_source_protocol(self):
        """FixedFixtureDataSource implements DataSource Protocol."""
        fixture_path = Path(__file__).parent.parent / "tests" / "fixed_fixture"
        data_source = FixedFixtureDataSource(fixture_path)
        
        # Check all required methods
        self.assertTrue(hasattr(data_source, "get_metadata"))
        self.assertTrue(hasattr(data_source, "validate"))
        self.assertTrue(hasattr(data_source, "symbols"))
        self.assertTrue(hasattr(data_source, "get_daily_bars"))
        self.assertTrue(hasattr(data_source, "get_daily_statuses"))
        self.assertTrue(hasattr(data_source, "get_daily_bar"))
        self.assertTrue(hasattr(data_source, "get_daily_status"))
        self.assertTrue(hasattr(data_source, "get_price"))
    
    def test_benchmark_conforms_to_data_source_protocol(self):
        """BenchmarkDataSource implements DataSource Protocol."""
        benchmark_path = Path(__file__).parent.parent / "tests" / "fixed_fixture" / "benchmarks"
        data_source = BenchmarkDataSource(benchmark_path)
        
        # Check all required methods
        self.assertTrue(hasattr(data_source, "get_metadata"))
        self.assertTrue(hasattr(data_source, "validate"))
        # Note: BenchmarkDataSource has codes() instead of symbols()
        self.assertTrue(hasattr(data_source, "codes"))
        self.assertTrue(hasattr(data_source, "get_daily_bars"))
        self.assertTrue(hasattr(data_source, "get_daily_bar"))


class TestValidationResult(unittest.TestCase):
    """Test DataSourceValidationResult structure and behavior."""
    
    def test_validation_result_shape(self):
        """DataSourceValidationResult has expected fields."""
        from datetime import datetime
        
        result = DataSourceValidationResult(
            status="pass",
            source_id="test_source",
            checked_at=datetime.now(),
            errors=[],
            warnings=[],
            checks_performed=["schema_version"],
        )
        
        # All required fields present
        self.assertEqual(result.status, "pass")
        self.assertEqual(result.source_id, "test_source")
        self.assertIsInstance(result.checked_at, datetime)
        self.assertIsInstance(result.errors, list)
        self.assertIsInstance(result.warnings, list)
        self.assertIsInstance(result.checks_performed, list)
    
    def test_fixed_fixture_validation_passes(self):
        """FixedFixtureDataSource.validate() returns pass status."""
        fixture_path = Path(__file__).parent.parent / "tests" / "fixed_fixture"
        data_source = FixedFixtureDataSource(fixture_path)
        
        result = data_source.validate()
        
        # Should pass validation
        self.assertIsInstance(result, DataSourceValidationResult)
        self.assertEqual(result.status, "pass")
        self.assertEqual(len(result.errors), 0)
        self.assertGreater(len(result.checks_performed), 0)
    
    def test_golden_case_validation_passes(self):
        """GoldenCaseDataSource.validate() returns pass status."""
        golden_case_path = Path(__file__).parent.parent / "tests" / "golden_cases"
        data_source = GoldenCaseDataSource(golden_case_path)
        
        result = data_source.validate()
        
        # Should pass validation
        self.assertIsInstance(result, DataSourceValidationResult)
        self.assertEqual(result.status, "pass")
        self.assertEqual(len(result.errors), 0)
    
    def test_benchmark_validation_passes(self):
        """BenchmarkDataSource.validate() returns pass status."""
        benchmark_path = Path(__file__).parent.parent / "tests" / "fixed_fixture" / "benchmarks"
        data_source = BenchmarkDataSource(benchmark_path)
        
        result = data_source.validate()
        
        # Should pass validation
        self.assertIsInstance(result, DataSourceValidationResult)
        self.assertEqual(result.status, "pass")
        self.assertEqual(len(result.errors), 0)
    
    def test_validation_status_values(self):
        """Validation status can only be pass/degraded/failed."""
        from datetime import datetime
        
        # Valid statuses
        for status in ["pass", "degraded", "failed"]:
            result = DataSourceValidationResult(
                status=status,
                source_id="test",
                checked_at=datetime.now(),
                errors=[],
                warnings=[],
                checks_performed=[],
            )
            self.assertEqual(result.status, status)


if __name__ == "__main__":
    unittest.main()
