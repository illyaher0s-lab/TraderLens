"""
Test Tushare Backtest Reproducibility - M3.4

Verify that same snapshot + same strategy produces identical results.
Hash comparison excludes non-deterministic fields.
"""

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

import pandas as pd

from backend.app.tushare.config import TushareConfig
from backend.app.tushare.snapshot_generator import SnapshotGenerator
from backend.app.tushare.tushare_data_source import TushareDataSource
from strategy_core.backtest_engine import run_backtest
from strategy_core.trading_calendar import TradingCalendar
from strategy_core.dsl_parser import parse_strategy_config
from backend.scripts.export_backtest_result import (
    export_metrics,
    export_trades,
    export_round_trips,
    export_equity_curve,
)


class TestTushareBacktestReproducibility(unittest.TestCase):
    """Test backtest reproducibility with hash verification."""
    
    def setUp(self):
        """Create temp snapshot and output directories."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.config = TushareConfig(token="test", snapshot_root=self.temp_dir)
        self.output_dir_1 = self.temp_dir / "run1"
        self.output_dir_2 = self.temp_dir / "run2"
        
        self._generate_test_snapshot()
    
    def tearDown(self):
        """Clean up temp directories."""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
    
    def test_backtest_results_are_deterministic(self):
        """Two runs produce identical core results."""
        ds = TushareDataSource(self.config)
        calendar = TradingCalendar(ds)
        
        test_config = Path(__file__).parent / "test_tushare_minimal_strategy.yaml"
        strategy_config = parse_strategy_config(test_config)
        
        # Run 1
        result1 = run_backtest(strategy_config, ds, calendar, initial_capital=100000.0)
        self.output_dir_1.mkdir(parents=True)
        self._export_result(result1, self.output_dir_1)
        
        # Run 2
        result2 = run_backtest(strategy_config, ds, calendar, initial_capital=100000.0)
        self.output_dir_2.mkdir(parents=True)
        self._export_result(result2, self.output_dir_2)
        
        # Verify identical in-memory results
        self.assertEqual(result1.final_capital, result2.final_capital)
        self.assertEqual(result1.total_return, result2.total_return)
        self.assertEqual(len(result1.trades), len(result2.trades))
        self.assertEqual(len(result1.daily_portfolio_values), len(result2.daily_portfolio_values))
    
    def test_export_files_have_identical_content_hash(self):
        """Exported files produce identical content hash."""
        ds = TushareDataSource(self.config)
        calendar = TradingCalendar(ds)
        
        test_config = Path(__file__).parent / "test_tushare_minimal_strategy.yaml"
        strategy_config = parse_strategy_config(test_config)
        
        # Run 1
        result1 = run_backtest(strategy_config, ds, calendar, initial_capital=100000.0)
        self.output_dir_1.mkdir(parents=True)
        self._export_result(result1, self.output_dir_1)
        
        # Run 2
        result2 = run_backtest(strategy_config, ds, calendar, initial_capital=100000.0)
        self.output_dir_2.mkdir(parents=True)
        self._export_result(result2, self.output_dir_2)
        
        # Compute hashes (excluding non-deterministic fields)
        hash1 = self._compute_export_hash(self.output_dir_1)
        hash2 = self._compute_export_hash(self.output_dir_2)
        
        self.assertEqual(hash1, hash2, 
                        f"Export hashes differ: {hash1} != {hash2}. "
                        "Backtest is not reproducible!")
    
    def test_metrics_json_core_fields_identical(self):
        """Core metrics fields are identical across runs."""
        ds = TushareDataSource(self.config)
        calendar = TradingCalendar(ds)
        
        test_config = Path(__file__).parent / "test_tushare_minimal_strategy.yaml"
        strategy_config = parse_strategy_config(test_config)
        
        # Run 1
        result1 = run_backtest(strategy_config, ds, calendar, initial_capital=100000.0)
        self.output_dir_1.mkdir(parents=True)
        self._export_result(result1, self.output_dir_1)
        
        # Run 2
        result2 = run_backtest(strategy_config, ds, calendar, initial_capital=100000.0)
        self.output_dir_2.mkdir(parents=True)
        self._export_result(result2, self.output_dir_2)
        
        # Load metrics
        with open(self.output_dir_1 / "metrics.json", "r") as f:
            metrics1 = json.load(f)
        
        with open(self.output_dir_2 / "metrics.json", "r") as f:
            metrics2 = json.load(f)
        
        # Core fields that must be identical
        core_fields = [
            "initial_capital", "final_capital", "total_return",
            "total_trades", "buy_trades", "sell_trades",
            "win_rate", "max_drawdown"
        ]
        
        for field in core_fields:
            if field in metrics1 and field in metrics2:
                self.assertEqual(metrics1[field], metrics2[field],
                               f"Metrics field '{field}' differs: {metrics1[field]} != {metrics2[field]}")
    
    def _compute_export_hash(self, export_dir: Path) -> str:
        """
        Compute deterministic hash of exported files.
        
        Excludes non-deterministic fields:
        - Timestamps (created_at, runtime, etc.)
        - Absolute paths
        - Process IDs
        """
        hasher = hashlib.sha256()
        
        # Core files to hash (sorted for determinism)
        core_files = [
            "trades.csv",
            "round_trips.csv",
            "equity_curve.csv",
        ]
        
        for filename in sorted(core_files):
            file_path = export_dir / filename
            if file_path.exists():
                with open(file_path, "rb") as f:
                    content = f.read()
                    # Filter out comment lines (contain timestamps)
                    lines = content.decode("utf-8").split("\n")
                    data_lines = [line for line in lines if not line.startswith("#")]
                    filtered_content = "\n".join(data_lines).encode("utf-8")
                    hasher.update(filtered_content)
        
        # metrics.json (filter out timestamps)
        metrics_file = export_dir / "metrics.json"
        if metrics_file.exists():
            with open(metrics_file, "r") as f:
                metrics = json.load(f)
            
            # Remove non-deterministic fields
            non_deterministic = ["created_at", "runtime_seconds", "export_time"]
            for field in non_deterministic:
                metrics.pop(field, None)
            
            # Sort keys for determinism
            metrics_json = json.dumps(metrics, sort_keys=True)
            hasher.update(metrics_json.encode("utf-8"))
        
        return hasher.hexdigest()[:16]
    
    def _export_result(self, result, output_dir: Path):
        """Export backtest result to files."""
        # Convert Pydantic model to dict for export functions
        result_dict = result.model_dump(mode='json')
        export_metrics(result_dict, output_dir / "metrics.json")
        export_trades(result_dict, output_dir / "trades.csv")
        export_round_trips(result_dict, output_dir / "round_trips.csv")
        export_equity_curve(result_dict, output_dir / "equity_curve.csv")
    
    def _generate_test_snapshot(self):
        """Generate test snapshot (2 stocks, 21 days)."""
        mock_client = Mock()
        symbols = ["600519.SH", "000001.SZ"]
        dates = [
            "20231201","20231204","20231205","20231206","20231207","20231208",
            "20231211","20231212","20231213","20231214","20231215","20231218",
            "20231219","20231220","20231221","20231222","20231225","20231226",
            "20231227","20231228","20231229"
        ]
        
        def mock_query(api, **kw):
            if api == "stock_basic":
                return pd.DataFrame([{
                    "ts_code": kw.get("ts_code"), 
                    "name": "Test", 
                    "industry": "Test", 
                    "area": "Test", 
                    "list_date": "20000101"
                }])
            elif api == "trade_cal":
                return pd.DataFrame({"cal_date": dates, "is_open": [1]*len(dates)})
            elif api == "daily":
                data = [{
                    "trade_date": d, 
                    "open": 100+i*0.5, 
                    "high": (100+i*0.5)*1.02,
                    "low": (100+i*0.5)*0.98, 
                    "close": (100+i*0.5)*1.01,
                    "vol": 10000+i*100, 
                    "amount": 100000+i*1000
                } for i, d in enumerate(dates)]
                return pd.DataFrame(data)
            elif api == "adj_factor":
                return pd.DataFrame({"trade_date": dates, "adj_factor": [1.0]*len(dates)})
            elif api == "suspend_d":
                return pd.DataFrame()
            return pd.DataFrame()
        
        mock_client.query.side_effect = mock_query
        generator = SnapshotGenerator(self.config, client=mock_client)
        generator.generate_snapshot(
            symbols=symbols,
            start_date="20231201",
            end_date="20231229",
            snapshot_id="reproducibility_test"
        )


if __name__ == "__main__":
    unittest.main()
