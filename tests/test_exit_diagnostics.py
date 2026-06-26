"""
Exit diagnostics test suite.

Validates:
1. holding_days exit triggers and completes round_trip
2. stop_loss_pct exit triggers on losing positions
3. ma_condition exit triggers
4. Exit signal counts are tracked
5. Sell orders are generated and filled
6. Round trips are completed
"""
from datetime import date
from pathlib import Path
import unittest

from backend.app.fixed_fixture import FixedFixtureDataSource
from strategy_core.trading_calendar import TradingCalendar
from strategy_core.backtest_engine import run_backtest
from strategy_core.dsl_parser import parse_strategy_config


class TestExitDiagnostics(unittest.TestCase):
    """
    Diagnostic tests for exit logic validation.
    """
    
    @classmethod
    def setUpClass(cls):
        cls.data_source = FixedFixtureDataSource(Path(__file__).parent / "fixed_fixture")
        cls.calendar = TradingCalendar(cls.data_source)

    def test_holding_days_exit_completes_round_trip(self):
        """
        holding_days exit should:
        1. Generate exit signal after N days
        2. Generate sell order
        3. Fill sell order (T+1)
        4. Complete round_trip
        5. Update cash correctly
        """
        strategy_config = parse_strategy_config(
            Path(__file__).parent / "diagnostic_strategies" / "holding_days_exit.yaml"
        )
        
        result = run_backtest(
            strategy_config,
            self.data_source,
            self.calendar,
            initial_capital=100000.0,
        )
        
        # Print diagnostic info
        print("\n=== HOLDING_DAYS EXIT DIAGNOSTIC ===")
        print(f"Total trades: {len(result.trades)}")
        print(f"Buy trades: {len([t for t in result.trades if t.direction == 'buy'])}")
        print(f"Sell trades: {len([t for t in result.trades if t.direction == 'sell'])}")
        print(f"Rejected orders: {len(result.rejected_orders)}")
        print(f"Entry signals: {result.entry_signal_count}")
        print(f"Exit signals: {result.exit_signal_count}")
        print(f"Buy orders: {result.buy_order_count}")
        print(f"Sell orders: {result.sell_order_count}")
        print(f"Buy fills: {result.buy_fill_count}")
        print(f"Sell fills: {result.sell_fill_count}")
        print(f"Exit rejected: {result.exit_rejected_count}")
        print(f"Completed round trips: {result.completed_round_trips}")
        print(f"Exit triggered rules: {result.exit_triggered_rules}")
        print(f"Final cash: {result.daily_portfolio_values[-1].cash if result.daily_portfolio_values else 'N/A'}")
        
        # Print all trades
        for trade in result.trades:
            print(f"  {trade.trade_date} {trade.direction} {trade.symbol} qty={trade.quantity} price={trade.price}")
        
        # Print rejected orders
        for order in result.rejected_orders:
            print(f"  REJECTED: {order.signal_date} {order.direction} {order.symbol} reason={order.rejection_reason}")
        
        # Verify at least one buy
        buy_trades = [t for t in result.trades if t.direction == "buy"]
        self.assertGreater(len(buy_trades), 0, "Should have at least one buy trade")
        self.assertGreater(result.entry_signal_count, 0, "Should count entry signals")
        self.assertGreater(result.buy_order_count, 0, "Should count buy orders")
        self.assertGreater(result.buy_fill_count, 0, "Should count buy fills")
        
        # Verify at least one sell
        sell_trades = [t for t in result.trades if t.direction == "sell"]
        self.assertGreater(len(sell_trades), 0, "Should have at least one sell trade")
        self.assertGreater(result.exit_signal_count, 0, "Should count exit signals")
        self.assertGreater(result.sell_order_count, 0, "Should count sell orders")
        self.assertGreater(result.sell_fill_count, 0, "Should count sell fills")
        self.assertGreater(result.completed_round_trips, 0, "Should complete at least one round trip")
        self.assertIn("holding_days >= 5", result.exit_triggered_rules)
        
        # Verify sell happened after buy
        for sell in sell_trades:
            matching_buys = [b for b in buy_trades if b.symbol == sell.symbol and b.trade_date < sell.trade_date]
            self.assertGreater(len(matching_buys), 0, f"Sell {sell.symbol} should have prior buy")
        
        # Verify no negative cash
        for daily_value in result.daily_portfolio_values:
            self.assertGreaterEqual(daily_value.cash, 0, f"Cash should not be negative on {daily_value.date}")

    def test_stop_loss_pct_exit_completes_losing_round_trip(self):
        """
        stop_loss_pct exit should trigger at least once and produce negative realized PnL.
        """
        strategy_config = parse_strategy_config(
            Path(__file__).parent / "diagnostic_strategies" / "stop_loss_exit.yaml"
        )

        result = run_backtest(
            strategy_config,
            self.data_source,
            self.calendar,
            initial_capital=100000.0,
        )

        self.assertGreater(result.entry_signal_count, 0)
        self.assertGreater(result.exit_signal_count, 0)
        self.assertGreater(result.sell_fill_count, 0)
        self.assertGreater(result.completed_round_trips, 0)
        self.assertIn("stop_loss:-2.0%", result.exit_triggered_rules)
        self.assertTrue(
            any(round_trip.realized_pnl < 0 for round_trip in result.round_trips),
            "Stop-loss diagnostic should produce at least one losing round trip",
        )
        for daily_value in result.daily_portfolio_values:
            self.assertGreaterEqual(daily_value.cash, 0, f"Cash should not be negative on {daily_value.date}")

    def test_ma_condition_exit_generates_sell_path_or_explicit_rejection(self):
        """
        ma_condition exit should generate exit signals and either fill sells or explain rejection.
        """
        strategy_config = parse_strategy_config(
            Path(__file__).parent / "diagnostic_strategies" / "ma_condition_exit.yaml"
        )

        result = run_backtest(
            strategy_config,
            self.data_source,
            self.calendar,
            initial_capital=100000.0,
        )

        self.assertGreater(result.exit_signal_count, 0)
        self.assertGreater(result.sell_order_count, 0)
        self.assertIn("ma_condition:close<ma_5", result.exit_triggered_rules)
        if result.sell_fill_count == 0:
            rejected_sells = [order for order in result.rejected_orders if order.direction == "sell"]
            self.assertGreater(len(rejected_sells), 0)
            for order in rejected_sells:
                self.assertIsNotNone(order.rejection_reason)
        for daily_value in result.daily_portfolio_values:
            self.assertGreaterEqual(daily_value.cash, 0, f"Cash should not be negative on {daily_value.date}")


if __name__ == "__main__":
    unittest.main()
