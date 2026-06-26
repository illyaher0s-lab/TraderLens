import unittest
from datetime import date

from backend.app.contracts import (
    PrototypeGateConfig,
    DailyPortfolioValue,
    Trade,
)
from strategy_core.prototype_gate import evaluate_prototype_gate


def create_daily_values(total_values: list[float], start_date=date(2024, 1, 1)) -> list[DailyPortfolioValue]:
    """Helper to create daily portfolio values."""
    return [
        DailyPortfolioValue(
            date=date(2024, 1, i+1),
            cash=0,
            market_value=0,
            total_value=v
        )
        for i, v in enumerate(total_values)
    ]


class TestPrototypeGate(unittest.TestCase):
    def test_gate_disabled_returns_not_evaluated(self):
        """
        When gate is disabled, status is 'not_evaluated'.
        """
        gate_config = PrototypeGateConfig(enabled=False)
        daily_values = create_daily_values([100000, 110000])
        
        result = evaluate_prototype_gate([], daily_values, 100000.0, gate_config)
        
        self.assertEqual(result.status, "not_evaluated")
        self.assertEqual(result.recommendation, "review")
        self.assertEqual(len(result.failed_checks), 0)

    def test_gate_passes_when_all_checks_met(self):
        """
        Gate passes when all thresholds are met.
        """
        gate_config = PrototypeGateConfig(
            enabled=True,
            min_total_return=0.05,
            max_drawdown=-0.15,
            min_sharpe_ratio=0.0,
            min_trades=1,
        )
        
        # 10% return, -5% drawdown
        daily_values = create_daily_values([100000, 110000, 105000, 110000])
        
        trades = [
            Trade(
                trade_id="t1", order_id="o1", symbol="000001.SZ", direction="buy",
                quantity=100, price=10.0, trade_date=date(2024, 1, 2),
                gross_amount=1000, commission=5, stamp_duty=0, transfer_fee=0,
                total_fee=5, net_cash_flow=-1005, cost=-1005
            )
        ]
        
        result = evaluate_prototype_gate(trades, daily_values, 100000.0, gate_config)
        
        self.assertEqual(result.status, "passed")
        self.assertEqual(result.recommendation, "candidate_for_prototype_passed")
        self.assertEqual(len(result.failed_checks), 0)

    def test_gate_fails_on_low_return(self):
        """
        Gate fails when total return below threshold.
        """
        gate_config = PrototypeGateConfig(
            enabled=True,
            min_total_return=0.10,
        )
        
        # Only 3% return
        daily_values = create_daily_values([100000, 103000])
        
        result = evaluate_prototype_gate([], daily_values, 100000.0, gate_config)
        
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.recommendation, "reject")
        self.assertGreater(len(result.failed_checks), 0)
        self.assertIn("total_return", result.failed_checks[0])

    def test_gate_fails_on_high_drawdown(self):
        """
        Gate fails when drawdown exceeds threshold.
        """
        gate_config = PrototypeGateConfig(
            enabled=True,
            max_drawdown=-0.10,
        )
        
        # -15% drawdown
        daily_values = create_daily_values([100000, 110000, 93500])
        
        result = evaluate_prototype_gate([], daily_values, 100000.0, gate_config)
        
        self.assertEqual(result.status, "failed")
        self.assertIn("max_drawdown", result.failed_checks[0])

    def test_gate_fails_on_low_trades(self):
        """
        Gate fails when trade count below threshold.
        """
        gate_config = PrototypeGateConfig(
            enabled=True,
            min_trades=5,
        )
        
        daily_values = create_daily_values([100000, 105000])
        trades = [
            Trade(
                trade_id="t1", order_id="o1", symbol="000001.SZ", direction="buy",
                quantity=100, price=10.0, trade_date=date(2024, 1, 2),
                gross_amount=1000, commission=5, stamp_duty=0, transfer_fee=0,
                total_fee=5, net_cash_flow=-1005, cost=-1005
            )
        ]
        
        result = evaluate_prototype_gate(trades, daily_values, 100000.0, gate_config)
        
        self.assertEqual(result.status, "failed")
        self.assertIn("filled_orders", result.failed_checks[0])

    def test_gate_evaluates_oos_metrics(self):
        """
        Gate evaluates OOS-specific metrics when sample_split_date provided.
        """
        gate_config = PrototypeGateConfig(
            enabled=True,
            min_oos_return=0.0,
            min_oos_trades=1,
        )
        
        daily_values = [
            DailyPortfolioValue(date=date(2024, 1, 1), cash=0, market_value=0, total_value=100000),
            DailyPortfolioValue(date=date(2024, 6, 30), cash=0, market_value=0, total_value=105000),  # End IS
            DailyPortfolioValue(date=date(2025, 1, 1), cash=0, market_value=0, total_value=107000),
            DailyPortfolioValue(date=date(2025, 6, 30), cash=0, market_value=0, total_value=110000),  # End OOS
        ]
        
        trades = [
            Trade(
                trade_id="t1", order_id="o1", symbol="000001.SZ", direction="buy",
                quantity=100, price=10.0, trade_date=date(2025, 1, 2),
                gross_amount=1000, commission=5, stamp_duty=0, transfer_fee=0,
                total_fee=5, net_cash_flow=-1005, cost=-1005
            )
        ]
        
        result = evaluate_prototype_gate(
            trades, daily_values, 100000.0, gate_config,
            sample_split_date=date(2024, 12, 31)
        )
        
        self.assertIsNotNone(result.metrics_oos)
        self.assertIsNotNone(result.oos_split_date)
        self.assertEqual(result.oos_split_date, date(2024, 12, 31))
        self.assertEqual(result.status, "passed")

    def test_gate_warns_on_insufficient_oos_trades(self):
        """
        Gate issues warning when OOS trades below threshold.
        """
        gate_config = PrototypeGateConfig(
            enabled=True,
            min_oos_trades=3,
        )
        
        daily_values = [
            DailyPortfolioValue(date=date(2024, 1, 1), cash=0, market_value=0, total_value=100000),
            DailyPortfolioValue(date=date(2024, 12, 31), cash=0, market_value=0, total_value=105000),
            DailyPortfolioValue(date=date(2025, 6, 30), cash=0, market_value=0, total_value=110000),
        ]
        
        trades = [
            Trade(
                trade_id="t1", order_id="o1", symbol="000001.SZ", direction="buy",
                quantity=100, price=10.0, trade_date=date(2025, 1, 2),
                gross_amount=1000, commission=5, stamp_duty=0, transfer_fee=0,
                total_fee=5, net_cash_flow=-1005, cost=-1005
            )
        ]
        
        result = evaluate_prototype_gate(
            trades, daily_values, 100000.0, gate_config,
            sample_split_date=date(2024, 12, 31)
        )
        
        self.assertEqual(result.status, "needs_review")
        self.assertEqual(result.recommendation, "review")
        self.assertGreater(len(result.warning_checks), 0)
        self.assertIn("insufficient_sample", result.warning_checks[0])

    def test_gate_oos_return_check(self):
        """
        Gate checks OOS return threshold.
        """
        gate_config = PrototypeGateConfig(
            enabled=True,
            min_oos_return=0.05,
        )
        
        daily_values = [
            DailyPortfolioValue(date=date(2024, 12, 31), cash=0, market_value=0, total_value=105000),
            DailyPortfolioValue(date=date(2025, 6, 30), cash=0, market_value=0, total_value=106000),  # Only ~0.95% OOS return
        ]
        
        result = evaluate_prototype_gate(
            [], daily_values, 100000.0, gate_config,
            sample_split_date=date(2024, 12, 31)
        )
        
        self.assertEqual(result.status, "failed")
        self.assertIn("oos_return", result.failed_checks[0])

    def test_gate_checks_min_completed_round_trips(self):
        """
        Gate checks min_completed_round_trips threshold.
        """
        gate_config = PrototypeGateConfig(
            enabled=True,
            min_completed_round_trips=2,
        )
        
        # Only 1 completed round-trip
        trades = [
            Trade(
                trade_id="t1", order_id="o1", symbol="000001.SZ", direction="buy",
                quantity=100, price=10.0, trade_date=date(2024, 1, 2),
                gross_amount=1000, commission=5, stamp_duty=0, transfer_fee=0,
                total_fee=5, net_cash_flow=-1005, cost=-1005
            ),
            Trade(
                trade_id="t2", order_id="o2", symbol="000001.SZ", direction="sell",
                quantity=100, price=12.0, trade_date=date(2024, 1, 3),
                gross_amount=1200, commission=5, stamp_duty=1.2, transfer_fee=0,
                total_fee=6.2, net_cash_flow=1193.8, cost=1193.8
            ),
        ]
        
        daily_values = create_daily_values([100000, 105000])
        
        result = evaluate_prototype_gate(trades, daily_values, 100000.0, gate_config)
        
        self.assertEqual(result.status, "failed")
        self.assertIn("completed_round_trips", result.failed_checks[0])


if __name__ == "__main__":
    unittest.main()
