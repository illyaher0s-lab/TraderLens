"""
Test Backtest with 20-Stock Fixed Fixture

Verify backtest engine works with larger stock pool (20 stocks vs 5 Golden Case stocks).
"""
from datetime import date
from pathlib import Path
import unittest

from backend.app.fixed_fixture import FixedFixtureDataSource
from strategy_core.trading_calendar import TradingCalendar
from strategy_core.backtest_engine import run_backtest
from strategy_core.dsl_parser import parse_strategy_config_dict


class TestBacktestWith20StockFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data_source = FixedFixtureDataSource()
        cls.calendar = TradingCalendar(cls.data_source)
    
    def test_backtest_runs_with_20_stock_universe(self):
        """
        Backtest should run successfully with 20-stock universe.
        """
        # Strategy with 20-stock static list
        strategy_dict = {
            "strategy_name": "20-stock-test",
            "version": "v1",
            "status": "draft",
            "hypothesis_source_snapshot": {
                "source_type": "manual",
                "source_run_id": "manual_20stock",
                "evidence_pack_ids": [],
                "generated_at": "2026-06-22T00:00:00",
                "data_range_used_for_generation": {
                    "start": "2023-01-01",
                    "end": "2024-12-31"
                }
            },
            "universe": {
                "type": "static_list",
                "symbols": self.data_source.symbols()  # All 20 stocks
            },
            "entry_conditions": {
                "logic": "AND",
                "rules": [
                    {
                        "type": "breakthrough",
                        "field": "close",
                        "benchmark": "high_5d",
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
                        "ma_period": 10,
                        "operator": "<"
                    }
                ]
            },
            "risk_filters": {
                "max_position_per_stock": 0.1,
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
                "initial_capital": 1000000.0,
                "start_date": "2023-01-03",
                "end_date": "2023-12-31",
                "sample_split": {
                    "in_sample_end": "2023-06-30",
                    "out_of_sample_start": "2023-07-01"
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
                "config_hash": "20stock-test"
            }
        }
        
        config = parse_strategy_config_dict(strategy_dict)
        result = run_backtest(config, self.data_source, self.calendar, initial_capital=1000000.0)
        
        # Verify backtest completed
        self.assertIsNotNone(result)
        self.assertEqual(result.strategy_id, "20-stock-test")
        self.assertEqual(result.initial_capital, 1000000.0)
        
        # Should have daily portfolio values
        self.assertGreater(len(result.daily_portfolio_values), 0)
        
        # Verify T+1 statistics are tracked
        self.assertIsInstance(result.t1_blocked_exit_count, int)
        self.assertIsInstance(result.partial_exit_due_to_t1_count, int)
        self.assertGreaterEqual(result.t1_blocked_exit_count, 0)
        self.assertGreaterEqual(result.partial_exit_due_to_t1_count, 0)
        
        # Result should be deterministic (no randomness)
        self.assertIsInstance(result.final_capital, float)
        self.assertIsInstance(result.total_return, float)
    
    def test_backtest_result_is_deterministic(self):
        """
        Running same backtest twice should produce identical results.
        """
        strategy_dict = {
            "strategy_name": "determinism-test",
            "version": "v1",
            "status": "draft",
            "hypothesis_source_snapshot": {
                "source_type": "manual",
                "source_run_id": "manual_determinism",
                "evidence_pack_ids": [],
                "generated_at": "2026-06-22T00:00:00",
                "data_range_used_for_generation": {
                    "start": "2023-01-01",
                    "end": "2023-06-30"
                }
            },
            "universe": {
                "type": "static_list",
                "symbols": ["000001.SZ", "600519.SH", "300750.SZ"]
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
                "config_hash": "determinism-test"
            }
        }
        
        config = parse_strategy_config_dict(strategy_dict)
        
        # Run backtest twice
        result1 = run_backtest(config, self.data_source, self.calendar, initial_capital=100000.0)
        result2 = run_backtest(config, self.data_source, self.calendar, initial_capital=100000.0)
        
        # Results should be identical
        self.assertEqual(result1.final_capital, result2.final_capital)
        self.assertEqual(result1.total_return, result2.total_return)
        self.assertEqual(len(result1.trades), len(result2.trades))
        self.assertEqual(len(result1.daily_portfolio_values), len(result2.daily_portfolio_values))
        
        # Trade details should match
        for trade1, trade2 in zip(result1.trades, result2.trades):
            self.assertEqual(trade1.symbol, trade2.symbol)
            self.assertEqual(trade1.direction, trade2.direction)
            self.assertEqual(trade1.quantity, trade2.quantity)
            self.assertEqual(trade1.price, trade2.price)
            self.assertEqual(trade1.trade_date, trade2.trade_date)


if __name__ == "__main__":
    unittest.main()
