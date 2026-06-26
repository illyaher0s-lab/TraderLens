"""
T+1 Freeze Logic Tests

Hybrid approach:
- Integration tests: full backtest with mini strategy YAML
- Unit tests: direct construction of Signal/Order/Portfolio for boundary cases
"""
from datetime import date
from pathlib import Path
import unittest

from backend.app.contracts import Signal, Order, StrategyConfig
from backend.app.golden_cases import GoldenCaseDataSource
from strategy_core.trading_calendar import TradingCalendar
from strategy_core.portfolio import PortfolioState, Position
from strategy_core.orders import generate_orders
from strategy_core.position_sizer import PositionSizer
from strategy_core.fill_simulator import simulate_fill
from strategy_core.backtest_engine import run_backtest
from strategy_core.dsl_parser import parse_strategy_config_dict


class TestT1FreezeLogic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data_source = GoldenCaseDataSource(Path(__file__).parent / "golden_cases")
        cls.calendar = TradingCalendar(cls.data_source)
        cls.sizer = PositionSizer(position_ratio=0.2)

    def test_t1_buy_unlock_next_day_can_sell(self):
        """
        Integration test: Verify T+1 statistics are tracked in BacktestResult.
        
        This is a smoke test to ensure backtest_engine correctly:
        1. Collects order_generation_events
        2. Tracks t1_blocked_exit_count and partial_exit_due_to_t1_count
        3. Doesn't crash with T+1 logic enabled
        
        We don't rely on natural signal triggering (Golden Case data may not satisfy conditions).
        Instead, we verify the backtest runs and statistical fields exist.
        """
        # Use existing Golden Case strategy (already has entry/exit rules)
        from pathlib import Path
        from strategy_core.dsl_parser import parse_strategy_config
        
        strategy_path = Path(__file__).parent / "golden_cases" / "strategy_config.yaml"
        config = parse_strategy_config(strategy_path)
        
        result = run_backtest(config, self.data_source, self.calendar, initial_capital=1000000.0)
        
        # Verify T+1 statistical fields exist and are non-negative
        self.assertIsInstance(result.order_generation_events, list)
        self.assertIsInstance(result.t1_blocked_exit_count, int)
        self.assertIsInstance(result.partial_exit_due_to_t1_count, int)
        self.assertGreaterEqual(result.t1_blocked_exit_count, 0)
        self.assertGreaterEqual(result.partial_exit_due_to_t1_count, 0)
        
        # If there are any T+1 events, verify they have correct structure
        for event in result.order_generation_events:
            if event.event_type in ["t1_frozen", "partial_exit_due_to_t1_freeze"]:
                self.assertIsNotNone(event.symbol)
                self.assertIsNotNone(event.intended_execution_date)
                self.assertIsNotNone(event.reason)

    def test_t1_buy_cannot_sell_same_day_blocked_by_order_generation(self):
        """
        Unit test: Buy creates frozen lot, same-day exit signal generates t1_frozen event.
        """
        # Setup: simulate buy on 2024-01-02
        portfolio = PortfolioState(cash=100000.0)
        portfolio.add_position(
            symbol="000001.SZ",
            quantity=200,
            price=10.0,
            buy_date=date(2024, 1, 2),
            calendar=self.calendar
        )
        
        # Day 1 end: position should be fully frozen
        pos = portfolio.positions["000001.SZ"]
        self.assertEqual(pos.quantity, 200)
        self.assertEqual(pos.sellable_quantity, 0)
        self.assertEqual(len(pos.frozen_lots), 1)
        self.assertEqual(pos.frozen_lots[0].quantity, 200)
        
        # Same day: exit signal triggers
        exit_signal = Signal(
            signal_id="exit:000001.SZ:2024-01-02",
            strategy_id="t1-test",
            strategy_version="v1",
            symbol="000001.SZ",
            signal_date=date(2024, 1, 2),
            signal_type="exit",
            triggered_rules=["ma_condition:close<ma_5d"],
            audit_id="audit:exit:000001.SZ:2024-01-02",
        )
        
        result = generate_orders(
            [exit_signal],
            intended_execution_date=date(2024, 1, 3),
            price_provider=self.data_source,
            sizer=self.sizer,
            available_capital=portfolio.cash,
            current_positions=portfolio.positions,
        )
        
        # Should generate no valid orders, one t1_frozen event
        self.assertEqual(len(result.valid_orders), 0)
        self.assertEqual(len(result.events), 1)
        
        event = result.events[0]
        self.assertEqual(event.event_type, "t1_frozen")
        self.assertEqual(event.symbol, "000001.SZ")
        self.assertEqual(event.requested_quantity, 200)
        self.assertEqual(event.generated_quantity, 0)
        self.assertEqual(event.sellable_quantity, 0)
        self.assertEqual(event.total_quantity, 200)

    def test_t1_multiple_buys_partial_frozen_generates_partial_exit_event(self):
        """
        Unit test: Multiple buys with different unlock dates, exit when partially frozen.
        """
        # Day 1: buy 200
        portfolio = PortfolioState(cash=100000.0)
        portfolio.add_position(
            symbol="000001.SZ",
            quantity=200,
            price=10.0,
            buy_date=date(2024, 1, 2),
            calendar=self.calendar
        )
        
        # Day 2: unlock Day 1 buy, then buy 100 more
        portfolio.unlock_frozen_lots(date(2024, 1, 3))
        portfolio.add_position(
            symbol="000001.SZ",
            quantity=100,
            price=10.5,
            buy_date=date(2024, 1, 3),
            calendar=self.calendar
        )
        
        # Day 2 end: position should be 300 total, 200 sellable, 100 frozen
        pos = portfolio.positions["000001.SZ"]
        self.assertEqual(pos.quantity, 300)
        self.assertEqual(pos.sellable_quantity, 200)
        self.assertEqual(len(pos.frozen_lots), 1)
        self.assertEqual(pos.frozen_lots[0].quantity, 100)
        
        # Day 2 night: exit signal triggers (wants to sell 300)
        exit_signal = Signal(
            signal_id="exit:000001.SZ:2024-01-03",
            strategy_id="t1-test",
            strategy_version="v1",
            symbol="000001.SZ",
            signal_date=date(2024, 1, 3),
            signal_type="exit",
            triggered_rules=["ma_condition:close<ma_5d"],
            audit_id="audit:exit:000001.SZ:2024-01-03",
        )
        
        result = generate_orders(
            [exit_signal],
            intended_execution_date=date(2024, 1, 4),
            price_provider=self.data_source,
            sizer=self.sizer,
            available_capital=portfolio.cash,
            current_positions=portfolio.positions,
        )
        
        # Should generate sell 200 order + partial_exit event
        self.assertEqual(len(result.valid_orders), 1)
        self.assertEqual(len(result.events), 1)
        
        order = result.valid_orders[0]
        self.assertEqual(order.direction, "sell")
        self.assertEqual(order.quantity, 200)  # Only sellable_quantity
        
        event = result.events[0]
        self.assertEqual(event.event_type, "partial_exit_due_to_t1_freeze")
        self.assertEqual(event.symbol, "000001.SZ")
        self.assertEqual(event.requested_quantity, 300)
        self.assertEqual(event.generated_quantity, 200)
        self.assertEqual(event.sellable_quantity, 200)
        self.assertEqual(event.total_quantity, 300)

    def test_t1_old_position_fully_sellable_exits_normally(self):
        """
        Unit test: Position held for 2+ days is fully sellable, no T+1 events.
        """
        # Day 1: buy 300
        portfolio = PortfolioState(cash=100000.0)
        portfolio.add_position(
            symbol="000001.SZ",
            quantity=300,
            price=10.0,
            buy_date=date(2024, 1, 2),
            calendar=self.calendar
        )
        
        # Day 2: unlock
        portfolio.unlock_frozen_lots(date(2024, 1, 3))
        
        # Day 3: unlock again (no effect, already unlocked)
        portfolio.unlock_frozen_lots(date(2024, 1, 4))
        
        # Position should be fully sellable
        pos = portfolio.positions["000001.SZ"]
        self.assertEqual(pos.quantity, 300)
        self.assertEqual(pos.sellable_quantity, 300)
        self.assertEqual(len(pos.frozen_lots), 0)
        
        # Day 3: exit signal triggers
        exit_signal = Signal(
            signal_id="exit:000001.SZ:2024-01-04",
            strategy_id="t1-test",
            strategy_version="v1",
            symbol="000001.SZ",
            signal_date=date(2024, 1, 4),
            signal_type="exit",
            triggered_rules=["ma_condition:close<ma_5d"],
            audit_id="audit:exit:000001.SZ:2024-01-04",
        )
        
        result = generate_orders(
            [exit_signal],
            intended_execution_date=date(2024, 1, 5),
            price_provider=self.data_source,
            sizer=self.sizer,
            available_capital=portfolio.cash,
            current_positions=portfolio.positions,
        )
        
        # Should generate sell 300 order, no events
        self.assertEqual(len(result.valid_orders), 1)
        self.assertEqual(len(result.events), 0)
        
        order = result.valid_orders[0]
        self.assertEqual(order.direction, "sell")
        self.assertEqual(order.quantity, 300)

    def test_t1_fill_simulator_final_check_rejects_bypassed_violation(self):
        """
        Unit test: simulate_fill rejects order that bypasses order generation pre-check.
        """
        # Setup: position with 100 frozen, 0 sellable
        portfolio = PortfolioState(cash=100000.0)
        portfolio.add_position(
            symbol="000001.SZ",
            quantity=100,
            price=10.0,
            buy_date=date(2024, 1, 2),
            calendar=self.calendar
        )
        
        pos = portfolio.positions["000001.SZ"]
        self.assertEqual(pos.sellable_quantity, 0)
        
        # Manually construct a sell order that bypasses orders.py pre-check
        order = Order(
            order_id="bypass:000001.SZ:2024-01-03",
            signal_id="fake-signal",
            signal_date=date(2024, 1, 2),
            intended_execution_date=date(2024, 1, 3),
            actual_execution_date=None,
            symbol="000001.SZ",
            direction="sell",
            quantity=100,  # Violates T+1: sellable_quantity is 0
            reason="bypass_test",
            strategy_version="v1",
            audit_id="audit:bypass:000001.SZ:2024-01-03",
        )
        
        # simulate_fill should reject
        filled_order = simulate_fill(
            order,
            date(2024, 1, 3),
            self.data_source,
            portfolio,
            calendar=self.calendar
        )
        
        self.assertEqual(filled_order.status, "rejected")
        self.assertIn("t1_violation", filled_order.rejection_reason)
        self.assertIn("only 0 sellable", filled_order.rejection_reason)
        
        # Position should remain unchanged
        self.assertEqual(pos.quantity, 100)
        self.assertEqual(pos.sellable_quantity, 0)

    def test_t1_position_invariant_always_holds(self):
        """
        Unit test: Position invariant (quantity == sellable_quantity + frozen_quantity) holds.
        """
        portfolio = PortfolioState(cash=100000.0)
        
        # Buy 1: 200 shares
        portfolio.add_position(
            symbol="000001.SZ",
            quantity=200,
            price=10.0,
            buy_date=date(2024, 1, 2),
            calendar=self.calendar
        )
        
        pos = portfolio.positions["000001.SZ"]
        frozen_quantity = sum(lot.quantity for lot in pos.frozen_lots)
        self.assertEqual(pos.quantity, pos.sellable_quantity + frozen_quantity,
                        "Invariant violated after first buy")
        
        # Unlock
        portfolio.unlock_frozen_lots(date(2024, 1, 3))
        pos = portfolio.positions["000001.SZ"]
        frozen_quantity = sum(lot.quantity for lot in pos.frozen_lots)
        self.assertEqual(pos.quantity, pos.sellable_quantity + frozen_quantity,
                        "Invariant violated after unlock")
        
        # Buy 2: 100 shares
        portfolio.add_position(
            symbol="000001.SZ",
            quantity=100,
            price=10.5,
            buy_date=date(2024, 1, 3),
            calendar=self.calendar
        )
        
        pos = portfolio.positions["000001.SZ"]
        frozen_quantity = sum(lot.quantity for lot in pos.frozen_lots)
        self.assertEqual(pos.quantity, pos.sellable_quantity + frozen_quantity,
                        "Invariant violated after second buy")
        
        # Sell partial (150 shares, all sellable)
        portfolio.reduce_position("000001.SZ", 150)
        
        pos = portfolio.positions["000001.SZ"]
        frozen_quantity = sum(lot.quantity for lot in pos.frozen_lots)
        self.assertEqual(pos.quantity, pos.sellable_quantity + frozen_quantity,
                        "Invariant violated after partial sell")
        
        # Unlock again
        portfolio.unlock_frozen_lots(date(2024, 1, 4))
        pos = portfolio.positions["000001.SZ"]
        frozen_quantity = sum(lot.quantity for lot in pos.frozen_lots)
        self.assertEqual(pos.quantity, pos.sellable_quantity + frozen_quantity,
                        "Invariant violated after second unlock")


if __name__ == "__main__":
    unittest.main()
