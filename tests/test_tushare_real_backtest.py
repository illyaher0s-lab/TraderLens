"""
Test Tushare Real Backtest - M3.4
"""
import shutil, tempfile, unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock
import pandas as pd

from backend.app.tushare.config import TushareConfig
from backend.app.tushare.snapshot_generator import SnapshotGenerator
from backend.app.tushare.tushare_data_source import TushareDataSource
from strategy_core.backtest_engine import run_backtest
from strategy_core.trading_calendar import TradingCalendar
from strategy_core.dsl_parser import parse_strategy_config

class TestTushareRealBacktest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.config = TushareConfig(token="test", snapshot_root=self.temp_dir)
        self._generate_test_snapshot()
    
    def tearDown(self):
        if self.temp_dir.exists(): shutil.rmtree(self.temp_dir)
    
    def test_load_tushare_snapshot(self):
        ds = TushareDataSource(self.config)
        self.assertTrue(ds.get_metadata().is_frozen)
        self.assertEqual(ds.get_metadata().symbol_count, 2)
    
    def test_run_backtest_with_tushare_data(self):
        ds = TushareDataSource(self.config)
        calendar = TradingCalendar(ds)
        test_config = Path(__file__).parent / "test_tushare_minimal_strategy.yaml"
        strategy_config = parse_strategy_config(test_config)
        result = run_backtest(strategy_config, ds, calendar, initial_capital=100000.0)
        self.assertIsNotNone(result)
        self.assertGreater(result.final_capital, 0)
    
    def test_backtest_reproducibility(self):
        ds = TushareDataSource(self.config)
        calendar = TradingCalendar(ds)
        test_config = Path(__file__).parent / "test_tushare_minimal_strategy.yaml"
        strategy_config = parse_strategy_config(test_config)
        result1 = run_backtest(strategy_config, ds, calendar, initial_capital=100000.0)
        result2 = run_backtest(strategy_config, ds, calendar, initial_capital=100000.0)
        self.assertEqual(result1.final_capital, result2.final_capital)
        self.assertEqual(result1.total_return, result2.total_return)
    
    def _generate_test_snapshot(self):
        mock_client = Mock()
        symbols = ["600519.SH", "000001.SZ"]
        dates = ["20231201","20231204","20231205","20231206","20231207","20231208",
                 "20231211","20231212","20231213","20231214","20231215","20231218",
                 "20231219","20231220","20231221","20231222","20231225","20231226",
                 "20231227","20231228","20231229"]
        def mock_query(api, **kw):
            if api == "stock_basic":
                return pd.DataFrame([{"ts_code": kw.get("ts_code"), "name": "Test", 
                                     "industry": "Test", "area": "Test", "list_date": "20000101"}])
            elif api == "trade_cal":
                return pd.DataFrame({"cal_date": dates, "is_open": [1]*len(dates)})
            elif api == "daily":
                data = [{"trade_date": d, "open": 100+i*0.5, "high": (100+i*0.5)*1.02,
                        "low": (100+i*0.5)*0.98, "close": (100+i*0.5)*1.01,
                        "vol": 10000+i*100, "amount": 100000+i*1000} for i, d in enumerate(dates)]
                return pd.DataFrame(data)
            elif api == "adj_factor":
                return pd.DataFrame({"trade_date": dates, "adj_factor": [1.0]*len(dates)})
            elif api == "suspend_d":
                return pd.DataFrame()
            return pd.DataFrame()
        mock_client.query.side_effect = mock_query
        generator = SnapshotGenerator(self.config, client=mock_client)
        generator.generate_snapshot(symbols=symbols, start_date="20231201", 
                                   end_date="20231229", snapshot_id="2stocks_21days_test")

if __name__ == "__main__": unittest.main()
