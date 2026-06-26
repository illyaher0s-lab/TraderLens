from pathlib import Path
import unittest

from pydantic import ValidationError


class DslParserTests(unittest.TestCase):
    def test_parse_golden_case_yaml_into_strategy_config_contract(self):
        from strategy_core.dsl_parser import parse_strategy_config

        config = parse_strategy_config(Path("tests/golden_cases/strategy_config.yaml"))

        self.assertEqual(config.strategy_name, "golden-breakout")
        self.assertEqual(config.universe.type, "static_list")
        self.assertEqual(len(config.universe.symbols), 5)
        self.assertEqual(config.fill_model.signal_to_execution, "T+1")
        self.assertEqual(config.backtest_config.data_source, "golden_case")

    def test_reject_invalid_oos_split_before_any_backtest_runs(self):
        from strategy_core.dsl_parser import parse_strategy_config_dict

        invalid = {
            "strategy_name": "invalid-oos",
            "version": "v1",
            "status": "draft",
            "hypothesis_source_snapshot": {
                "source_type": "manual",
                "source_run_id": "manual_invalid",
                "evidence_pack_ids": [],
                "generated_at": "2026-06-21T00:00:00",
                "data_range_used_for_generation": {
                    "start": "2024-01-01",
                    "end": "2025-12-31",
                },
            },
            "universe": {"type": "static_list", "symbols": ["000001.SZ"]},
            "entry_conditions": {"logic": "AND", "rules": []},
            "exit_conditions": {"logic": "OR", "rules": []},
            "risk_filters": {
                "max_position_per_stock": 0.2,
                "max_total_position": 0.8,
                "restrict_limit_up_buy": True,
                "restrict_limit_down_sell": True,
                "restrict_suspended": True,
                "min_liquidity_for_trade": 10000000,
            },
            "rebalance": {"frequency": "daily", "check_time": "close"},
            "fill_model": {
                "signal_to_execution": "T+1",
                "execution_price": "open",
                "commission": 0.0003,
                "stamp_tax": 0.001,
                "slippage": 0.002,
                "lot_size": 100,
                "lot_rounding": "floor",
                "handling": {
                    "limit_up_buy": "skip",
                    "limit_down_sell": "defer_next_day",
                    "suspended": "skip",
                },
            },
            "backtest_config": {
                "initial_capital": 1000000,
                "start_date": "2024-01-01",
                "end_date": "2025-12-31",
                "sample_split": {
                    "in_sample_end": "2025-01-01",
                    "out_of_sample_start": "2025-01-01",
                },
                "benchmark": {
                    "type": "index",
                    "code": "000905.SH",
                    "name": "CSI 500",
                },
                "data_source": "golden_case",
                "include_delisted": "partial",
            },
            "audit": {
                "created_at": "2026-06-21T00:00:00",
                "created_by": "user",
                "last_modified_at": "2026-06-21T00:00:00",
                "config_hash": "invalid",
            },
        }

        with self.assertRaises(ValidationError):
            parse_strategy_config_dict(invalid)


if __name__ == "__main__":
    unittest.main()
