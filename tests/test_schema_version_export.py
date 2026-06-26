"""
Schema Version Export Tests - M2 Export Format Finalization

Validates that export JSON files include schema_version field.
Ensures external tools can detect schema compatibility.

M2 Requirement: All export JSON files must include schema_version at top level.
"""

import unittest
import tempfile
import json
from pathlib import Path
from datetime import datetime

# Import export functions
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.scripts.export_backtest_result import export_metrics
from backend.scripts.compare_backtests import compare_backtests
from contracts import SCHEMA_VERSION


class TestSchemaVersionInExports(unittest.TestCase):
    """Test that export JSON files include schema_version."""
    
    def setUp(self):
        """Create temp directory for test exports."""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)
    
    def tearDown(self):
        """Clean up temp directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_metrics_json_has_schema_version(self):
        """metrics.json includes schema_version at top level."""
        # Create minimal backtest result
        result = {
            "strategy_id": "test_strategy",
            "strategy_version": "v1",
            "initial_capital": 100000.0,
            "final_capital": 105000.0,
            "total_return": 0.05,
            "trades": [],
            "round_trips": [],
            "daily_portfolio_values": [{
                "date": "2023-06-15",
                "cash": 105000.0,
                "market_value": 0.0,
                "total_value": 105000.0,
            }],
        }
        
        # Export metrics.json
        export_path = self.temp_path / "metrics.json"
        export_metrics(result, export_path)
        
        # Read and verify
        with open(export_path, "r", encoding="utf-8") as f:
            metrics = json.load(f)
        
        # Schema version must be present
        self.assertIn("schema_version", metrics,
                     "metrics.json must include schema_version field")
        self.assertEqual(metrics["schema_version"], SCHEMA_VERSION)
        
        # Artifact type must be present
        self.assertIn("artifact_type", metrics,
                     "metrics.json must include artifact_type field")
        self.assertEqual(metrics["artifact_type"], "metrics")
        
        # Existing fields should remain at top level (not wrapped in 'data')
        self.assertIn("strategy_id", metrics,
                     "Existing fields must remain at top level for backward compatibility")
        self.assertIn("total_return", metrics)
        self.assertIn("total_trades", metrics)
    
    def test_comparison_json_has_schema_version(self):
        """comparison.json includes schema_version at top level."""
        # Create minimal metrics files
        export1 = self.temp_path / "export1"
        export1.mkdir()
        
        metrics1 = {
            "schema_version": "1.0",
            "artifact_type": "metrics",
            "strategy_id": "strategy_A",
            "strategy_version": "v1",
            "initial_capital": 100000.0,
            "final_capital": 105000.0,
            "total_return": 0.05,
            "total_return_pct": 5.0,
            "max_drawdown": -0.02,
            "total_trades": 10,
            "total_round_trips": 5,
            "win_rate": 0.6,
        }
        
        with open(export1 / "metrics.json", "w", encoding="utf-8") as f:
            json.dump(metrics1, f)
        
        # Run comparison
        comparison_dir = self.temp_path / "comparison"
        compare_backtests(
            input_dirs=[str(export1)],
            output_dir=str(comparison_dir),
        )
        
        # Read comparison.json
        comparison_path = comparison_dir / "comparison.json"
        with open(comparison_path, "r", encoding="utf-8") as f:
            comparison = json.load(f)
        
        # Schema version must be present
        self.assertIn("schema_version", comparison,
                     "comparison.json must include schema_version field")
        self.assertEqual(comparison["schema_version"], SCHEMA_VERSION)
        
        # Artifact type must be present
        self.assertIn("artifact_type", comparison,
                     "comparison.json must include artifact_type field")
        self.assertEqual(comparison["artifact_type"], "comparison")
        
        # Existing fields should remain at top level
        self.assertIn("generated_at", comparison)
        self.assertIn("rows", comparison)
        self.assertIn("valid_count", comparison)
    
    def test_schema_version_matches_contracts_package(self):
        """Exported schema_version matches contracts.SCHEMA_VERSION."""
        from contracts import SCHEMA_VERSION as CONTRACTS_VERSION
        
        self.assertEqual(CONTRACTS_VERSION, "1.0",
                        "contracts.SCHEMA_VERSION must be '1.0' in M2")
        
        # Test that exports use the same constant
        result = {
            "strategy_id": "test",
            "strategy_version": "v1",
            "initial_capital": 100000.0,
            "final_capital": 100000.0,
            "total_return": 0.0,
            "trades": [],
            "round_trips": [],
            "daily_portfolio_values": [],
        }
        
        export_path = self.temp_path / "metrics.json"
        export_metrics(result, export_path)
        
        with open(export_path, "r", encoding="utf-8") as f:
            metrics = json.load(f)
        
        self.assertEqual(metrics["schema_version"], CONTRACTS_VERSION)
    
    def test_existing_metric_fields_remain_top_level(self):
        """Backward compatibility: existing fields stay at top level (not wrapped)."""
        result = {
            "strategy_id": "test_strategy",
            "strategy_version": "v1",
            "initial_capital": 100000.0,
            "final_capital": 102500.0,
            "total_return": 0.025,
            "trades": [{
                "trade_id": "T001",
                "order_id": "O001",
                "symbol": "600519.SH",
                "direction": "buy",
                "quantity": 100,
                "price": 150.0,
                "trade_date": "2023-06-15",
                "gross_amount": 15000.0,
                "commission": 5.0,
                "stamp_duty": 0.0,
                "transfer_fee": 0.0,
                "total_fee": 5.0,
                "net_cash_flow": -15005.0,
                "cost": -15005.0,
            }],
            "round_trips": [{
                "round_trip_id": "RT001",
                "symbol": "600519.SH",
                "buy_date": "2023-06-15",
                "sell_date": "2023-06-20",
                "holding_days": 5,
                "matched_quantity": 100,
                "buy_price": 150.0,
                "sell_price": 155.0,
                "buy_cost": 15005.0,
                "sell_proceeds": 15479.5,
                "realized_pnl": 474.5,
            }],
            "daily_portfolio_values": [{
                "date": "2023-06-15",
                "cash": 85000.0,
                "market_value": 15000.0,
                "total_value": 100000.0,
            }],
        }
        
        export_path = self.temp_path / "metrics.json"
        export_metrics(result, export_path)
        
        with open(export_path, "r", encoding="utf-8") as f:
            metrics = json.load(f)
        
        # All expected fields at top level
        expected_fields = [
            "schema_version", "artifact_type",  # New M2 fields
            "strategy_id", "strategy_version",
            "initial_capital", "final_capital",
            "total_return", "total_return_pct",
            "max_drawdown", "max_drawdown_pct",
            "total_trades", "buy_trades", "sell_trades",
            "total_round_trips", "winning_trips", "losing_trips",
            "win_rate", "profit_factor", "avg_holding_days",
            "total_commission", "total_stamp_duty", "total_fees",
            "t1_blocked_exit_count", "partial_exit_due_to_t1_count",
            "rejected_orders",
        ]
        
        for field in expected_fields:
            self.assertIn(field, metrics,
                         f"Field '{field}' must be at top level for backward compatibility")
        
        # Should NOT be wrapped in a 'data' key
        self.assertNotIn("data", metrics,
                        "Fields should not be wrapped in 'data' key (breaking change)")


class TestSchemaVersionConstant(unittest.TestCase):
    """Test SCHEMA_VERSION constant is correct."""
    
    def test_schema_version_is_1_0(self):
        """SCHEMA_VERSION is '1.0' for M2."""
        from contracts import SCHEMA_VERSION
        
        self.assertEqual(SCHEMA_VERSION, "1.0")
        self.assertIsInstance(SCHEMA_VERSION, str)


if __name__ == "__main__":
    unittest.main()
