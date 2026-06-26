import unittest
from datetime import date

from backend.app.contracts import DailyPortfolioValue, Trade
from strategy_core.metrics import calculate_metrics


class TestMetrics(unittest.TestCase):
    def test_calculate_total_return(self):
        """
        Total return is calculated correctly.
        """
        daily_values = [
            DailyPortfolioValue(date=date(2024, 1, 1), cash=100000, market_value=0, total_value=100000),
            DailyPortfolioValue(date=date(2024, 1, 2), cash=80000, market_value=22000, total_value=102000),
            DailyPortfolioValue(date=date(2024, 1, 3), cash=80000, market_value=25000, total_value=105000),
        ]
        
        metrics = calculate_metrics([], daily_values, 100000.0)
        
        self.assertAlmostEqual(metrics.total_return, 0.05, places=4)  # 5% return

    def test_calculate_max_drawdown(self):
        """
        Maximum drawdown is calculated correctly (negative value).
        """
        daily_values = [
            DailyPortfolioValue(date=date(2024, 1, 1), cash=0, market_value=0, total_value=100000),
            DailyPortfolioValue(date=date(2024, 1, 2), cash=0, market_value=0, total_value=110000),  # peak
            DailyPortfolioValue(date=date(2024, 1, 3), cash=0, market_value=0, total_value=99000),   # -10% from peak
            DailyPortfolioValue(date=date(2024, 1, 4), cash=0, market_value=0, total_value=105000),
        ]
        
        metrics = calculate_metrics([], daily_values, 100000.0)
        
        self.assertAlmostEqual(metrics.max_drawdown, -0.1, places=4)  # -10% drawdown

    def test_calculate_sharpe_ratio(self):
        """
        Sharpe ratio is calculated with annualization.
        """
        # Create simple daily values with consistent positive returns
        daily_values = [
            DailyPortfolioValue(date=date(2024, 1, i), cash=0, market_value=0, total_value=100000 * (1.001 ** i))
            for i in range(1, 11)
        ]
        
        metrics = calculate_metrics([], daily_values, 100000.0)
        
        # Sharpe should be positive with consistent returns
        self.assertGreater(metrics.sharpe_ratio, 0)

    def test_metrics_with_no_trades(self):
        """
        Metrics handle zero trades correctly.
        """
        daily_values = [
            DailyPortfolioValue(date=date(2024, 1, 1), cash=100000, market_value=0, total_value=100000),
        ]
        
        metrics = calculate_metrics([], daily_values, 100000.0)
        
        self.assertEqual(metrics.total_trades, 0)
        self.assertEqual(metrics.filled_orders, 0)
        self.assertEqual(metrics.completed_round_trips, 0)

    def test_metrics_with_trades(self):
        """
        Trade counts are recorded correctly.
        """
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
                gross_amount=1200, commission=5, stamp_duty=12, transfer_fee=0,
                total_fee=17, net_cash_flow=1183, cost=1183
            ),
        ]
        
        daily_values = [
            DailyPortfolioValue(date=date(2024, 1, 1), cash=100000, market_value=0, total_value=100000),
            DailyPortfolioValue(date=date(2024, 1, 2), cash=98995, market_value=1000, total_value=99995),
            DailyPortfolioValue(date=date(2024, 1, 3), cash=100178, market_value=0, total_value=100178),
        ]
        
        metrics = calculate_metrics(trades, daily_values, 100000.0)
        
        self.assertEqual(metrics.total_trades, 2)
        self.assertEqual(metrics.filled_orders, 2)

    def test_metrics_with_empty_daily_values(self):
        """
        Metrics handle empty daily_values gracefully.
        """
        metrics = calculate_metrics([], [], 100000.0)
        
        self.assertEqual(metrics.total_return, 0.0)
        self.assertEqual(metrics.max_drawdown, 0.0)
        self.assertEqual(metrics.sharpe_ratio, 0.0)

    def test_sharpe_ratio_with_zero_volatility(self):
        """
        Sharpe ratio returns 0 when volatility is zero (flat returns).
        """
        # All days have same total_value
        daily_values = [
            DailyPortfolioValue(date=date(2024, 1, i), cash=100000, market_value=0, total_value=100000)
            for i in range(1, 6)
        ]
        
        metrics = calculate_metrics([], daily_values, 100000.0)
        
        self.assertEqual(metrics.sharpe_ratio, 0.0)

    def test_metrics_includes_closed_lot_win_rate_and_profit_factor(self):
        """
        Metrics include closed_lot_win_rate and profit_factor from round-trips.
        """
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
        
        daily_values = [
            DailyPortfolioValue(date=date(2024, 1, 1), cash=100000, market_value=0, total_value=100000),
            DailyPortfolioValue(date=date(2024, 1, 2), cash=98995, market_value=1000, total_value=99995),
            DailyPortfolioValue(date=date(2024, 1, 3), cash=100188.8, market_value=0, total_value=100188.8),
        ]
        
        metrics = calculate_metrics(trades, daily_values, 100000.0)
        
        self.assertEqual(metrics.completed_round_trips, 1)
        self.assertGreater(metrics.closed_lot_win_rate, 0)
        self.assertGreater(metrics.profit_factor, 0)

    def test_closed_lot_win_rate_with_mixed_round_trips(self):
        """
        Win rate is calculated correctly with winning and losing round-trips.
        """
        trades = [
            # Buy 1
            Trade(
                trade_id="t1", order_id="o1", symbol="000001.SZ", direction="buy",
                quantity=100, price=10.0, trade_date=date(2024, 1, 2),
                gross_amount=1000, commission=5, stamp_duty=0, transfer_fee=0,
                total_fee=5, net_cash_flow=-1005, cost=-1005
            ),
            # Sell 1 (profit)
            Trade(
                trade_id="t2", order_id="o2", symbol="000001.SZ", direction="sell",
                quantity=100, price=12.0, trade_date=date(2024, 1, 3),
                gross_amount=1200, commission=5, stamp_duty=1.2, transfer_fee=0,
                total_fee=6.2, net_cash_flow=1193.8, cost=1193.8
            ),
            # Buy 2
            Trade(
                trade_id="t3", order_id="o3", symbol="000001.SZ", direction="buy",
                quantity=100, price=10.0, trade_date=date(2024, 1, 4),
                gross_amount=1000, commission=5, stamp_duty=0, transfer_fee=0,
                total_fee=5, net_cash_flow=-1005, cost=-1005
            ),
            # Sell 2 (loss)
            Trade(
                trade_id="t4", order_id="o4", symbol="000001.SZ", direction="sell",
                quantity=100, price=9.0, trade_date=date(2024, 1, 5),
                gross_amount=900, commission=5, stamp_duty=0.9, transfer_fee=0,
                total_fee=5.9, net_cash_flow=894.1, cost=894.1
            ),
        ]
        
        daily_values = [
            DailyPortfolioValue(date=date(2024, 1, 1), cash=100000, market_value=0, total_value=100000),
        ]
        
        metrics = calculate_metrics(trades, daily_values, 100000.0)
        
        self.assertEqual(metrics.completed_round_trips, 2)
        self.assertAlmostEqual(metrics.closed_lot_win_rate, 0.5, places=2)  # 1 win, 1 loss

    def test_metrics_with_no_completed_round_trips(self):
        """
        Metrics handle zero completed round-trips gracefully.
        """
        trades = [
            Trade(
                trade_id="t1", order_id="o1", symbol="000001.SZ", direction="buy",
                quantity=100, price=10.0, trade_date=date(2024, 1, 2),
                gross_amount=1000, commission=5, stamp_duty=0, transfer_fee=0,
                total_fee=5, net_cash_flow=-1005, cost=-1005
            ),
        ]
        
        daily_values = [
            DailyPortfolioValue(date=date(2024, 1, 1), cash=100000, market_value=0, total_value=100000),
        ]
        
        metrics = calculate_metrics(trades, daily_values, 100000.0)
        
        self.assertEqual(metrics.completed_round_trips, 0)
        self.assertEqual(metrics.closed_lot_win_rate, 0.0)
        self.assertEqual(metrics.profit_factor, 0.0)


if __name__ == "__main__":
    unittest.main()
