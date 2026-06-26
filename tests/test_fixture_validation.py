"""
Test Fixed Fixture Validation
"""
import json
import tempfile
import unittest
from pathlib import Path

from backend.scripts.validate_fixed_fixture import (
    validate_fixed_fixture,
    validate_manifest,
    validate_stock_identities,
    validate_symbol_data,
)


class TestFixtureValidation(unittest.TestCase):
    def test_validate_existing_fixture_returns_degraded(self):
        """Validate existing mock fixture should return degraded (mock data warning)."""
        fixture_path = Path(__file__).parent / "fixed_fixture"
        
        if not fixture_path.exists():
            self.skipTest("Fixed fixture not found")
        
        report = validate_fixed_fixture(fixture_path)
        
        # Should be degraded (mock data warning)
        self.assertIn(report["status"], ["pass", "degraded"])
        
        # Should validate all 20 stocks
        self.assertEqual(len(report["per_symbol_summary"]), 20)
        
        # Each symbol should have counts
        for symbol, summary in report["per_symbol_summary"].items():
            self.assertGreater(summary["daily_bars_count"], 0)
            self.assertGreater(summary["daily_status_count"], 0)
    
    def test_validate_manifest_detects_missing_fields(self):
        """Manifest validation should detect missing required fields."""
        report = {
            "missing_fields": [],
            "errors": [],
            "warnings": [],
        }
        
        # Incomplete manifest
        manifest = {
            "dataset_name": "test",
            # Missing version, source, etc.
        }
        
        validate_manifest(manifest, report)
        
        # Should have errors for missing fields
        self.assertGreater(len(report["errors"]), 0)
        self.assertGreater(len(report["missing_fields"]), 0)
    
    def test_validate_manifest_warns_on_mock_source(self):
        """Manifest validation should warn when source is mock."""
        report = {
            "missing_fields": [],
            "errors": [],
            "warnings": [],
        }
        
        manifest = {
            "dataset_name": "test",
            "version": "1.0.0",
            "source": "mock",
            "date_range": {"start": "2023-01-01", "end": "2024-12-31"},
            "adjust_type": "qfq",
            "schema_version": "1.0",
            "stock_count": 20,
        }
        
        validate_manifest(manifest, report)
        
        # Should have warning about mock data
        self.assertTrue(any("mock" in w.lower() for w in report["warnings"]))
    
    def test_validate_stock_identities_detects_missing_fields(self):
        """Stock identity validation should detect missing required fields."""
        report = {
            "missing_fields": [],
            "errors": [],
            "warnings": [],
        }
        
        stock_list = [
            {
                "symbol": "000001.SZ",
                "name": "平安银行",
                # Missing exchange, current_status
            }
        ]
        
        validate_stock_identities(stock_list, report)
        
        # Should have errors for missing fields
        self.assertGreater(len(report["errors"]), 0)
        self.assertIn("stock_list[0].exchange", report["missing_fields"])
        self.assertIn("stock_list[0].current_status", report["missing_fields"])
    
    def test_validate_stock_identities_warns_on_invalid_exchange(self):
        """Stock identity validation should warn on invalid exchange."""
        report = {
            "missing_fields": [],
            "errors": [],
            "warnings": [],
        }
        
        stock_list = [
            {
                "symbol": "000001.SZ",
                "name": "平安银行",
                "exchange": "INVALID",
                "current_status": "listed",
            }
        ]
        
        validate_stock_identities(stock_list, report)
        
        # Should have warning about invalid exchange
        self.assertTrue(any("invalid exchange" in w.lower() for w in report["warnings"]))
    
    def test_validation_report_saved_to_json(self):
        """Validation report should be saved as JSON."""
        fixture_path = Path(__file__).parent / "fixed_fixture"
        
        if not fixture_path.exists():
            self.skipTest("Fixed fixture not found")
        
        report = validate_fixed_fixture(fixture_path)
        
        # Check report structure
        self.assertIn("validation_timestamp", report)
        self.assertIn("fixture_path", report)
        self.assertIn("status", report)
        self.assertIn("errors", report)
        self.assertIn("warnings", report)
        self.assertIn("per_symbol_summary", report)
        
        # Status should be valid
        self.assertIn(report["status"], ["pass", "degraded", "failed"])


if __name__ == "__main__":
    unittest.main()
