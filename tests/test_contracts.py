from datetime import date, datetime
import unittest


class ContractModelTests(unittest.TestCase):
    def test_stock_identity_daily_bar_and_status_encode_a_share_constraints(self):
        from backend.app.contracts import DailyBar, DailyStatus, StockIdentity

        identity = StockIdentity(
            symbol="000001.SZ",
            name="平安银行",
            exchange="SZSE",
            list_date=date(1991, 4, 3),
            current_status="listed",
            industry="银行",
            sector="银行",
        )
        bar = DailyBar(
            date=date(2024, 1, 2),
            symbol=identity.symbol,
            open=10.0,
            high=10.5,
            low=9.9,
            close=10.2,
            volume=1000000,
            amount=10200000.0,
            adj_factor=1.0,
        )
        status = DailyStatus(
            date=bar.date,
            symbol=identity.symbol,
            is_st=False,
            is_suspended=False,
            is_limit_up=False,
            is_limit_down=False,
        )

        self.assertEqual(identity.exchange, "SZSE")
        self.assertEqual(bar.symbol, status.symbol)
        self.assertFalse(status.is_suspended)

    def test_strategy_config_preserves_oos_split_and_a_share_fill_model(self):
        from backend.app.contracts import StrategyConfig

        config = StrategyConfig.model_validate(
            {
                "strategy_name": "golden-breakout",
                "version": "v1",
                "status": "draft",
                "hypothesis_source_snapshot": {
                    "source_type": "manual",
                    "source_run_id": "manual_m0",
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
                        "in_sample_end": "2024-12-31",
                        "out_of_sample_start": "2025-01-01",
                    },
                    "benchmark": {
                        "type": "index",
                        "code": "000905.SH",
                        "name": "中证500",
                    },
                    "data_source": "golden_case",
                    "include_delisted": "partial",
                },
                "audit": {
                    "created_at": "2026-06-21T00:00:00",
                    "created_by": "user",
                    "last_modified_at": "2026-06-21T00:00:00",
                    "config_hash": "m0-golden",
                },
            }
        )

        self.assertEqual(config.fill_model.signal_to_execution, "T+1")
        self.assertLess(
            config.backtest_config.sample_split.in_sample_end,
            config.backtest_config.sample_split.out_of_sample_start,
        )

    def test_action_plan_and_forward_candidate_contracts_are_reserved_for_later_milestones(self):
        from backend.app.contracts import (
            ExecutionLog,
            ForwardCandidate,
            PositionPlan,
            Signal,
            TradePlan,
        )

        signal = Signal(
            signal_id="sig_001",
            strategy_id="strategy_001",
            strategy_version="v1",
            symbol="000001.SZ",
            signal_date=date(2025, 12, 30),
            signal_type="entry",
            triggered_rules=["golden_case_manual_signal"],
            audit_id="audit_001",
        )
        trade_plan = TradePlan(
            trade_plan_id="plan_001",
            signal_id=signal.signal_id,
            planned_trade_date=date(2025, 12, 31),
            planned_action="plan_buy",
            execution_window="open_next_day",
            position_plan=PositionPlan(
                max_position_pct=0.2,
                current_position_pct=0.0,
                planned_position_pct=0.2,
                available_position_pct=0.2,
                portfolio_source="paper_portfolio",
            ),
            invalid_if=[],
            fallback_action="cancel",
            audit_id="audit_002",
        )
        execution_log = ExecutionLog(
            execution_log_id="exec_001",
            trade_plan_id=trade_plan.trade_plan_id,
            user_actual_action="not_recorded",
            manual_override=False,
            recorded_at=datetime(2026, 6, 21, 0, 0, 0),
            audit_id="audit_003",
        )
        candidate = ForwardCandidate(
            id="fc_001",
            date_added=date(2026, 6, 21),
            theme_id="theme_001",
            theme_name="golden theme",
            source_run_id="serenity_001",
            evidence_pack_id="evidence_001",
            symbol="000001.SZ",
            company_name="平安银行",
            chain_layer="test layer",
            evidence_level="medium",
            thesis="M0 fixture candidate",
            invalidation_rules=[],
            price_snapshot={
                "snapshot_date": "2025-12-31",
                "open": 10,
                "high": 10,
                "low": 10,
                "close": 10,
                "volume": 1,
                "amount": 10,
                "is_limit_up": False,
                "is_limit_down": False,
                "is_suspended": False,
            },
            benchmark={
                "type": "index",
                "code": "000905.SH",
                "name": "中证500",
                "snapshot_value": 1000,
            },
            review_policy={"review_date": "2026-07-21", "default_review_days": 30},
            status="active",
        )

        self.assertEqual(trade_plan.signal_id, signal.signal_id)
        self.assertEqual(execution_log.user_actual_action, "not_recorded")
        self.assertEqual(candidate.status, "active")


if __name__ == "__main__":
    unittest.main()
