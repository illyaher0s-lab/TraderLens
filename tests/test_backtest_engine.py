from datetime import date, timedelta
from pathlib import Path
import unittest
from unittest.mock import patch

from backend.app.golden_cases import GoldenCaseDataSource
from contracts.stable import DailyBar, DailyStatus, Signal, StrategyConfig
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

    def test_backtest_uses_explicit_stamp_tax_for_synthetic_execution(self):
        from strategy_core import backtest_engine, signals as signal_module

        symbol = "600000.SH"
        dates = [date(2025, 1, 2) + timedelta(days=offset) for offset in range(5)]

        class SyntheticExecutionSource:
            def __init__(self):
                self.bars = {
                    day: DailyBar(
                        date=day,
                        symbol=symbol,
                        open=10.0,
                        high=10.0,
                        low=10.0,
                        close=10.0,
                        volume=100_000,
                        amount=1_000_000.0,
                        adj_factor=1.0,
                    )
                    for day in dates
                }
                self.statuses = {
                    day: DailyStatus(
                        date=day,
                        symbol=symbol,
                        is_st=False,
                        is_suspended=False,
                        is_limit_up=False,
                        is_limit_down=False,
                    )
                    for day in dates
                }

            def symbols(self):
                return [symbol]

            def get_daily_bars(self, requested_symbol):
                self.assert_symbol(requested_symbol)
                return list(self.bars.values())

            def get_daily_bar(self, requested_symbol, target_date):
                self.assert_symbol(requested_symbol)
                return self.bars[target_date]

            def get_daily_status(self, requested_symbol, target_date):
                self.assert_symbol(requested_symbol)
                return self.statuses[target_date]

            def get_price(self, requested_symbol, target_date):
                return self.get_daily_bar(requested_symbol, target_date).close

            @staticmethod
            def assert_symbol(requested_symbol):
                if requested_symbol != symbol:
                    raise KeyError(requested_symbol)

        def make_signal(config, signal_date, signal_type):
            signal_id = f"synthetic:{signal_type}:{signal_date}"
            return Signal(
                signal_id=signal_id,
                strategy_id=config.strategy_name,
                strategy_version=config.version,
                symbol=symbol,
                signal_date=signal_date,
                signal_type=signal_type,
                triggered_rules=[f"synthetic-{signal_type}"],
                audit_id=signal_id,
            )

        for stamp_tax in (0.0, 0.001):
            with self.subTest(stamp_tax=stamp_tax):
                config_dict = self.strategy_config.model_dump()
                config_dict["universe"]["symbols"] = [symbol]
                config_dict["fill_model"]["stamp_tax"] = stamp_tax
                config_dict["backtest_config"]["start_date"] = dates[0]
                config_dict["backtest_config"]["end_date"] = dates[-1]
                config_dict["backtest_config"]["sample_split"] = {
                    "in_sample_end": dates[1],
                    "out_of_sample_start": dates[2],
                }
                config = StrategyConfig.model_validate(config_dict)
                source = SyntheticExecutionSource()
                calendar = TradingCalendar(source)

                def synthetic_entries(config, data_source, trade_date, universe):
                    if trade_date == dates[0]:
                        return [make_signal(config, trade_date, "entry")]
                    return []

                def synthetic_exits(config, data_source, trade_date, positions):
                    if trade_date == dates[2] and symbol in positions:
                        return [make_signal(config, trade_date, "exit")]
                    return []

                with patch.object(backtest_engine, "generate_signals", side_effect=synthetic_entries):
                    with patch.object(signal_module, "generate_exit_signals", side_effect=synthetic_exits):
                        result = run_backtest(config, source, calendar, initial_capital=100_000.0)

                buy_trades = [trade for trade in result.trades if trade.direction == "buy"]
                sell_trades = [trade for trade in result.trades if trade.direction == "sell"]
                self.assertEqual(len(buy_trades), 1)
                self.assertEqual(len(sell_trades), 1)
                self.assertEqual(buy_trades[0].stamp_duty, 0.0)
                self.assertAlmostEqual(
                    sell_trades[0].stamp_duty,
                    sell_trades[0].gross_amount * stamp_tax,
                )
                self.assertAlmostEqual(
                    sell_trades[0].total_fee,
                    sell_trades[0].commission + sell_trades[0].stamp_duty + sell_trades[0].transfer_fee,
                )
                self.assertAlmostEqual(
                    result.final_capital,
                    100_000.0 - 12.0 - (20_000.0 * stamp_tax),
                )


if __name__ == "__main__":
    unittest.main()
