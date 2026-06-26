"""
Test Backtest Result Export
"""
import json
import csv
import tempfile
import unittest
from pathlib import Path

from backend.app.fixed_fixture import FixedFixtureDataSource
from strategy_core.trading_calendar import TradingCalendar
from strategy_core.backtest_engine import run_backtest
from strategy_core.dsl_parser import parse_strategy_config_dict
from backend.scripts.export_backtest_result import (
    export_backtest_result,
    export_metrics,
    export_trades,
    export_round_trips,
    export_equity_curve,
)


class TestBacktestExport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data_source = FixedFixtureDataSource()
        cls.calendar = TradingCalendar(cls.data_source)
        
        # Run a simple backtest to get result
        strategy_dict = {
            "strategy_name": "export-test",
            "version": "v1",
            "status": "draft",
            "hypothesis_source_snapshot": {
                "source_type": "manual",
                "source_run_id": "manual_export",
                "evidence_pack_ids": [],
                "generated_at": "2026-06-22T00:00:00",
                "data_range_used_for_generation": {
                    "start": "2023-01-01",
                    "end": "2023-06-30"
                }
            },
            "universe": {
                "type": "static_list",
                "symbols": ["000001.SZ", "600519.SH"]
            },
            "entry_conditions": {
                "logic": "AND",
                "rules": [
                    {
                        "type": "breakthrough",
                        "field": "close",
                        "benchmark": "high_3d",
                        "operator": ">="
                    }
                ]
            },
            "exit_conditions": {
                "logic": "OR",
                "rules": [
                    {
                        "type": "ma_condition",
                        "field": "close",
                        "ma_period": 5,
                        "operator": "<"
                    }
                ]
            },
            "risk_filters": {
                "max_position_per_stock": 0.2,
                "max_total_position": 0.8,
                "restrict_limit_up_buy": True,
                "restrict_limit_down_sell": True,
                "restrict_suspended": True,
                "min_liquidity_for_trade": 10000000
            },
            "rebalance": {
                "frequency": "daily",
                "check_time": "close"
            },
            "fill_model": {
                "signal_to_execution": "T+1",
                "execution_price": "open",
                "commission": 0.0003,
                "stamp_tax": 0.001,
                "slippage": 0.0,
                "lot_size": 100,
                "lot_rounding": "floor",
                "handling": {
                    "limit_up_buy": "skip",
                    "limit_down_sell": "defer_next_day",
                    "suspended": "skip"
                }
            },
            "backtest_config": {
                "initial_capital": 100000.0,
                "start_date": "2023-01-03",
                "end_date": "2023-06-30",
                "sample_split": {
                    "in_sample_end": "2023-03-31",
                    "out_of_sample_start": "2023-04-01"
                },
                "benchmark": {
                    "type": "index",
                    "code": "000905.SH",
                    "name": "CSI 500"
                },
                "data_source": "fixed_fixture",
                "include_delisted": "partial"
            },
            "prototype_gate": {
                "enabled": False
            },
            "audit": {
                "created_at": "2026-06-22T00:00:00",
                "created_by": "test",
                "last_modified_at": "2026-06-22T00:00:00",
                "config_hash": "export-test"
            }
        }
        
        config = parse_strategy_config_dict(strategy_dict)
        cls.result = run_backtest(config, cls.data_source, cls.calendar, initial_capital=100000.0)
    
    def test_export_metrics_creates_json_file(self):
        """Export metrics should create JSON file with key metrics."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "metrics.json"
            
            result_dict = self.result.model_dump(mode="json")
            export_metrics(result_dict, output_path)
            
            self.assertTrue(output_path.exists())
            
            with open(output_path, "r", encoding="utf-8") as f:
                metrics = json.load(f)
            
            # Verify key fields
            self.assertEqual(metrics["strategy_id"], "export-test")
            self.assertEqual(metrics["initial_capital"], 100000.0)
            self.assertIn("total_return_pct", metrics)
            self.assertIn("max_drawdown_pct", metrics)
            self.assertIn("win_rate", metrics)
            self.assertIn("profit_factor", metrics)
            self.assertIn("t1_blocked_exit_count", metrics)
    
    def test_export_trades_creates_csv_file(self):
        """Export trades should create CSV file with all trades."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "trades.csv"
            
            result_dict = self.result.model_dump(mode="json")
            export_trades(result_dict, output_path)
            
            self.assertTrue(output_path.exists())
            
            with open(output_path, "r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
            
            # Verify headers
            self.assertIn("trade_id", reader.fieldnames)
            self.assertIn("symbol", reader.fieldnames)
            self.assertIn("direction", reader.fieldnames)
            self.assertIn("quantity", reader.fieldnames)
            self.assertIn("price", reader.fieldnames)
            self.assertIn("commission", reader.fieldnames)
            self.assertIn("stamp_duty", reader.fieldnames)
    
    def test_export_round_trips_creates_csv_file(self):
        """Export round trips should create CSV file with PnL details."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "round_trips.csv"
            
            result_dict = self.result.model_dump(mode="json")
            export_round_trips(result_dict, output_path)
            
            self.assertTrue(output_path.exists())
            
            with open(output_path, "r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
            
            # Verify headers
            self.assertIn("symbol", reader.fieldnames)
            self.assertIn("buy_date", reader.fieldnames)
            self.assertIn("sell_date", reader.fieldnames)
            self.assertIn("holding_days", reader.fieldnames)
            self.assertIn("realized_pnl", reader.fieldnames)
            self.assertIn("return_pct", reader.fieldnames)
    
    def test_export_equity_curve_creates_csv_file(self):
        """Export equity curve should create CSV file with daily values."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "equity_curve.csv"
            
            result_dict = self.result.model_dump(mode="json")
            export_equity_curve(result_dict, output_path)
            
            self.assertTrue(output_path.exists())
            
            with open(output_path, "r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
            
            # Verify headers
            self.assertIn("date", reader.fieldnames)
            self.assertIn("cash", reader.fieldnames)
            self.assertIn("market_value", reader.fieldnames)
            self.assertIn("total_value", reader.fieldnames)
            self.assertIn("return_from_start_pct", reader.fieldnames)
            
            # Should have data
            self.assertGreater(len(rows), 0)
    
    def test_export_all_artifacts(self):
        """Export all artifacts should create all files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Save result to JSON first
            result_json_path = Path(tmpdir) / "result.json"
            with open(result_json_path, "w", encoding="utf-8") as f:
                json.dump(self.result.model_dump(mode="json"), f)
            
            output_dir = Path(tmpdir) / "output"
            export_backtest_result(str(result_json_path), str(output_dir))
            
            # Verify all files created
            self.assertTrue((output_dir / "metrics.json").exists())
            self.assertTrue((output_dir / "trades.csv").exists())
            self.assertTrue((output_dir / "round_trips.csv").exists())
            self.assertTrue((output_dir / "equity_curve.csv").exists())
            
            # Verify PNG files created
            self.assertTrue((output_dir / "equity_curve.png").exists())
            self.assertTrue((output_dir / "drawdown_curve.png").exists())
            
            # Verify PNG files have non-zero size
            self.assertGreater((output_dir / "equity_curve.png").stat().st_size, 0)
            self.assertGreater((output_dir / "drawdown_curve.png").stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
