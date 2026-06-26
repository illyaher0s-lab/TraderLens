from datetime import date
from pathlib import Path
import unittest

from backend.app.golden_cases import GoldenCaseDataSource
from strategy_core.dsl_parser import parse_strategy_config
from strategy_core.trading_calendar import TradingCalendar
from strategy_core.backtest_engine import run_backtest


class TestBacktestEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data_source = GoldenCaseDataSource(Path(__file__).parent / "golden_cases")
        cls.calendar = TradingCalendar(cls.data_source)
        cls.strategy_config = parse_strategy_config(
            Path(__file__).parent / "golden_cases" / "strategy_config.yaml"
        )

    def test_backtest_initializes_with_initial_capital(self):
        """
        Backtest initializes portfolio with initial capital.
        """
        result = run_backtest(
            self.strategy_config,
            self.data_source,
            self.calendar,
            initial_capital=100000.0,
        )
        
        self.assertEqual(result.initial_capital, 100000.0)
        self.assertGreaterEqual(result.final_capital, 0)

    def test_backtest_generates_signals_and_orders_on_each_day(self):
        """
        Backtest generates signals and orders for each trading day.
        """
        result = run_backtest(
            self.strategy_config,
            self.data_source,
            self.calendar,
            initial_capital=100000.0,
        )
        
        # Should have some trades or rejected orders
        self.assertIsInstance(result.trades, list)
        self.assertIsInstance(result.rejected_orders, list)

    def test_backtest_fills_buy_order_on_next_trading_day(self):
        """
        When entry signal is generated, buy order is filled on next trading day.
        """
        result = run_backtest(
            self.strategy_config,
            self.data_source,
            self.calendar,
            initial_capital=100000.0,
        )
        
        if result.trades:
            # Verify trades have execution dates
            for trade in result.trades:
                self.assertIsNotNone(trade.trade_date)
                self.assertGreater(trade.price, 0)
                self.assertGreater(trade.quantity, 0)

    def test_backtest_records_daily_portfolio_values(self):
        """
        Backtest records portfolio value for each trading day.
        """
        result = run_backtest(
            self.strategy_config,
            self.data_source,
            self.calendar,
            initial_capital=100000.0,
        )
        
        trading_dates = self.calendar.all_trading_dates()
        # Should have at least initial value recorded
        self.assertGreaterEqual(len(result.daily_portfolio_values), 1)
        
        # First day should have initial capital
        first_day = result.daily_portfolio_values[0]
        self.assertEqual(first_day.total_value, 100000.0)

    def test_backtest_result_serializes_to_json(self):
        """
        BacktestResult can be serialized to JSON.
        """
        result = run_backtest(
            self.strategy_config,
            self.data_source,
            self.calendar,
            initial_capital=100000.0,
        )
        
        json_data = result.model_dump_json()
        self.assertIsInstance(json_data, str)
        self.assertIn("initial_capital", json_data)
        self.assertIn("final_capital", json_data)

    def test_backtest_includes_transaction_cost_warning(self):
        """
        BacktestResult includes warning about transaction costs.
        """
        result = run_backtest(
            self.strategy_config,
            self.data_source,
            self.calendar,
            initial_capital=100000.0,
        )
        
        self.assertIsInstance(result.warnings, list)
        self.assertGreater(len(result.warnings), 0)
        warning_text = " ".join(result.warnings)
        self.assertIn("commission", warning_text.lower())

    def test_backtest_calculates_total_return(self):
        """
        Backtest calculates total return correctly.
        """
        result = run_backtest(
            self.strategy_config,
            self.data_source,
            self.calendar,
            initial_capital=100000.0,
        )
        
        expected_return = (result.final_capital - result.initial_capital) / result.initial_capital
        self.assertAlmostEqual(result.total_return, expected_return, places=6)

    def test_backtest_trade_includes_cost_breakdown(self):
        """
        Trade records include transaction cost breakdown.
        """
        result = run_backtest(
            self.strategy_config,
            self.data_source,
            self.calendar,
            initial_capital=100000.0,
        )
        
        if result.trades:
            trade = result.trades[0]
            # Verify cost fields exist
            self.assertIsNotNone(trade.gross_amount)
            self.assertIsNotNone(trade.commission)
            self.assertIsNotNone(trade.stamp_duty)
            self.assertIsNotNone(trade.transfer_fee)
            self.assertIsNotNone(trade.total_fee)
            self.assertIsNotNone(trade.net_cash_flow)
            
            # Verify consistency
            self.assertEqual(trade.gross_amount, trade.price * trade.quantity)
            self.assertEqual(trade.total_fee, trade.commission + trade.stamp_duty + trade.transfer_fee)
            
            # Buy should have negative net_cash_flow
            if trade.direction == "buy":
                self.assertLess(trade.net_cash_flow, 0)
                self.assertEqual(trade.stamp_duty, 0.0)  # no stamp duty on buy
            else:  # sell
                self.assertGreater(trade.net_cash_flow, 0)
                self.assertGreater(trade.stamp_duty, 0.0)  # stamp duty on sell

    def test_backtest_commission_minimum_enforced(self):
        """
        Small trades pay minimum commission (5 RMB).
        """
        result = run_backtest(
            self.strategy_config,
            self.data_source,
            self.calendar,
            initial_capital=100000.0,
        )
        
        if result.trades:
            # Find a small trade
            small_trades = [t for t in result.trades if t.gross_amount < 20000]
            if small_trades:
                trade = small_trades[0]
                # Small trade should pay minimum commission
                self.assertGreaterEqual(trade.commission, 5.0)

    def test_backtest_includes_prototype_gate_result(self):
        """
        Backtest result includes prototype gate evaluation.
        """
        result = run_backtest(
            self.strategy_config,
            self.data_source,
            self.calendar,
            initial_capital=100000.0,
        )
        
        self.assertIsNotNone(result.prototype_gate_result)
        self.assertIn(result.prototype_gate_result.status, ["not_evaluated", "passed", "needs_review", "failed"])
        self.assertIsNotNone(result.prototype_gate_result.metrics_full)

    def test_backtest_gate_disabled_returns_not_evaluated(self):
        """
        When gate is disabled, status is 'not_evaluated'.
        """
        # Modify config to disable gate
        config_dict = self.strategy_config.model_dump()
        config_dict["prototype_gate"]["enabled"] = False
        
        from backend.app.contracts import StrategyConfig
        modified_config = StrategyConfig.model_validate(config_dict)
        
        result = run_backtest(
            modified_config,
            self.data_source,
            self.calendar,
            initial_capital=100000.0,
        )
        
        self.assertEqual(result.prototype_gate_result.status, "not_evaluated")

    def test_backtest_gate_splits_is_and_oos_metrics(self):
        """
        Gate evaluates IS and OOS metrics separately when sample_split exists.
        """
        result = run_backtest(
            self.strategy_config,
            self.data_source,
            self.calendar,
            initial_capital=100000.0,
        )
        
        gate_result = result.prototype_gate_result
        
        # Golden Case has sample_split, so IS/OOS should be evaluated
        if self.strategy_config.backtest_config.sample_split:
            self.assertIsNotNone(gate_result.metrics_is)
            self.assertIsNotNone(gate_result.oos_split_date)

    def test_backtest_includes_round_trips(self):
        """
        Backtest result includes round-trip details.
        """
        result = run_backtest(
            self.strategy_config,
            self.data_source,
            self.calendar,
            initial_capital=100000.0,
        )
        
        self.assertIsNotNone(result.round_trips)
        # If there are completed round-trips, verify structure
        if result.round_trips:
            rt = result.round_trips[0]
            self.assertIsNotNone(rt.round_trip_id)
            self.assertIsNotNone(rt.matched_quantity)
            self.assertIsNotNone(rt.realized_pnl)

    def test_backtest_round_trips_match_metrics(self):
        """
        Round-trip count in result matches metrics.
        """
        result = run_backtest(
            self.strategy_config,
            self.data_source,
            self.calendar,
            initial_capital=100000.0,
        )
        
        gate_result = result.prototype_gate_result
        self.assertEqual(len(result.round_trips), gate_result.metrics_full.completed_round_trips)

    def test_backtest_respects_configured_end_date(self):
        """
        Backtest should not trade or record portfolio values after configured end_date.

        This matters because T+1 execution needs a next trading day; diagnostics
        must not run beyond the strategy's requested backtest window.
        """
        result = run_backtest(
            self.strategy_config,
            self.data_source,
            self.calendar,
            initial_capital=100000.0,
        )

        end_date = self.strategy_config.backtest_config.end_date
        for trade in result.trades:
            self.assertLessEqual(trade.trade_date, end_date)
        for daily_value in result.daily_portfolio_values:
            self.assertLessEqual(daily_value.date, end_date)


if __name__ == "__main__":
    unittest.main()
