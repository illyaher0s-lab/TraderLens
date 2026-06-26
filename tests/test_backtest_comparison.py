"""
Test Backtest Comparison
"""
import json
import csv
import tempfile
import unittest
from pathlib import Path

from backend.scripts.compare_backtests import (
    compare_backtests,
    extract_comparison_row,
    export_comparison_csv,
)


class TestBacktestComparison(unittest.TestCase):
    def test_compare_two_valid_exports(self):
        """Should generate comparison.csv and comparison.json for two valid exports."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            
            # Create two mock export directories
            export1 = tmpdir / "export1"
            export1.mkdir()
            metrics1 = {
                "strategy_id": "strategy_A",
                "strategy_version": "v1",
                "initial_capital": 100000.0,
                "final_capital": 110000.0,
                "total_return": 0.1,
                "total_return_pct": 10.0,
                "max_drawdown": -0.05,
                "max_drawdown_pct": -5.0,
                "total_trades": 20,
                "total_round_trips": 10,
                "win_rate": 0.6,
                "profit_factor": 2.5,
                "t1_blocked_exit_count": 2,
                "partial_exit_due_to_t1_count": 1,
            }
            with open(export1 / "metrics.json", "w") as f:
                json.dump(metrics1, f)
            
            export2 = tmpdir / "export2"
            export2.mkdir()
            metrics2 = {
                "strategy_id": "strategy_B",
                "strategy_version": "v2",
                "initial_capital": 100000.0,
                "final_capital": 105000.0,
                "total_return": 0.05,
                "total_return_pct": 5.0,
                "max_drawdown": -0.08,
                "max_drawdown_pct": -8.0,
                "total_trades": 15,
                "total_round_trips": 8,
                "win_rate": 0.5,
                "profit_factor": 1.8,
                "t1_blocked_exit_count": 0,
                "partial_exit_due_to_t1_count": 0,
            }
            with open(export2 / "metrics.json", "w") as f:
                json.dump(metrics2, f)
            
            # Run comparison
            output_dir = tmpdir / "comparison"
            compare_backtests(
                input_dirs=[str(export1), str(export2)],
                output_dir=str(output_dir)
            )
            
            # Verify output files exist
            self.assertTrue((output_dir / "comparison.json").exists())
            self.assertTrue((output_dir / "comparison.csv").exists())
            
            # Verify JSON structure
            with open(output_dir / "comparison.json", "r") as f:
                comparison = json.load(f)
            
            self.assertEqual(comparison["input_count"], 2)
            self.assertEqual(comparison["valid_count"], 2)
            self.assertEqual(comparison["failed_count"], 0)
            self.assertEqual(len(comparison["rows"]), 2)
            
            # Verify CSV has correct row count
            with open(output_dir / "comparison.csv", "r") as f:
                reader = csv.DictReader(f)
                csv_rows = list(reader)
            
            self.assertEqual(len(csv_rows), 2)
    
    def test_compare_with_missing_metrics_file(self):
        """Should record failure when metrics.json is missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            
            # Create one valid export and one without metrics.json
            export1 = tmpdir / "export1"
            export1.mkdir()
            metrics1 = {
                "strategy_id": "strategy_A",
                "strategy_version": "v1",
                "total_return": 0.1,
            }
            with open(export1 / "metrics.json", "w") as f:
                json.dump(metrics1, f)
            
            export2 = tmpdir / "export2"
            export2.mkdir()
            # No metrics.json in export2
            
            # Run comparison
            output_dir = tmpdir / "comparison"
            compare_backtests(
                input_dirs=[str(export1), str(export2)],
                output_dir=str(output_dir)
            )
            
            # Verify JSON structure
            with open(output_dir / "comparison.json", "r") as f:
                comparison = json.load(f)
            
            self.assertEqual(comparison["input_count"], 2)
            self.assertEqual(comparison["valid_count"], 1)
            self.assertEqual(comparison["failed_count"], 1)
            self.assertGreater(len(comparison["failures"]), 0)
    
    def test_compare_with_missing_fields(self):
        """Should output null and record warnings for missing fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            
            export1 = tmpdir / "export1"
            export1.mkdir()
            # Incomplete metrics (missing win_rate, profit_factor)
            metrics1 = {
                "strategy_id": "strategy_A",
                "total_return": 0.1,
                # Missing many fields
            }
            with open(export1 / "metrics.json", "w") as f:
                json.dump(metrics1, f)
            
            # Run comparison
            output_dir = tmpdir / "comparison"
            compare_backtests(
                input_dirs=[str(export1)],
                output_dir=str(output_dir)
            )
            
            # Verify JSON structure
            with open(output_dir / "comparison.json", "r") as f:
                comparison = json.load(f)
            
            self.assertEqual(comparison["valid_count"], 1)
            self.assertGreater(len(comparison["warnings"]), 0)
            
            # Verify row has null values
            row = comparison["rows"][0]
            self.assertIsNone(row["win_rate"])
            self.assertIsNone(row["profit_factor"])
    
    def test_compare_with_sort_by(self):
        """Should sort results by specified field."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            
            # Create three exports with different returns
            for i, return_val in enumerate([0.05, 0.15, 0.10]):
                export = tmpdir / f"export{i}"
                export.mkdir()
                metrics = {
                    "strategy_id": f"strategy_{i}",
                    "total_return": return_val,
                }
                with open(export / "metrics.json", "w") as f:
                    json.dump(metrics, f)
            
            # Run comparison with sort
            output_dir = tmpdir / "comparison"
            compare_backtests(
                input_dirs=[str(tmpdir / f"export{i}") for i in range(3)],
                output_dir=str(output_dir),
                sort_by="total_return",
                descending=True
            )
            
            # Verify sort order
            with open(output_dir / "comparison.json", "r") as f:
                comparison = json.load(f)
            
            returns = [row["total_return"] for row in comparison["rows"]]
            self.assertEqual(returns, [0.15, 0.10, 0.05])
    
    def test_extract_comparison_row_with_benchmark(self):
        """Should calculate excess_return when benchmark_return exists."""
        metrics = {
            "strategy_id": "test",
            "total_return": 0.15,
            "benchmark_return": 0.10,
        }
        warnings = []
        
        row = extract_comparison_row(metrics, "/test", warnings)
        
        self.assertEqual(row["total_return"], 0.15)
        self.assertEqual(row["benchmark_return"], 0.10)
        self.assertAlmostEqual(row["excess_return"], 0.05, places=6)
    
    def test_extract_comparison_row_without_benchmark(self):
        """Should set excess_return to None when benchmark_return is missing."""
        metrics = {
            "strategy_id": "test",
            "total_return": 0.15,
            # No benchmark_return
        }
        warnings = []
        
        row = extract_comparison_row(metrics, "/test", warnings)
        
        self.assertEqual(row["total_return"], 0.15)
        self.assertIsNone(row["benchmark_return"])
        self.assertIsNone(row["excess_return"])
    
    def test_export_comparison_csv_preserves_decimals(self):
        """CSV should preserve decimal values for numeric fields."""
        rows = [
            {
                "strategy_name": "test",
                "total_return": 0.123456,
                "win_rate": 0.654321,
            }
        ]
        
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test.csv"
            export_comparison_csv(rows, output_path)
            
            with open(output_path, "r") as f:
                reader = csv.DictReader(f)
                csv_row = next(reader)
            
            # Should have 6 decimal places
            self.assertEqual(csv_row["total_return"], "0.123456")
            self.assertEqual(csv_row["win_rate"], "0.654321")


if __name__ == "__main__":
    unittest.main()
