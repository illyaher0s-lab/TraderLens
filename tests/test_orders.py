from datetime import date
from pathlib import Path
import unittest

from backend.app.contracts import Signal
from backend.app.golden_cases import GoldenCaseDataSource
from strategy_core.orders import generate_orders
from strategy_core.position_sizer import PositionSizer
from strategy_core.portfolio import Position


def entry_signal(symbol="000001.SZ", signal_date=date(2024, 1, 3)):
    return Signal(
        signal_id=f"sig:{symbol}:{signal_date}",
        strategy_id="golden-breakout",
        strategy_version="v1",
        symbol=symbol,
        signal_date=signal_date,
        signal_type="entry",
        triggered_rules=["breakthrough:close>=high_2d"],
        audit_id=f"audit:{symbol}:{signal_date}",
    )


def exit_signal(symbol="000001.SZ", signal_date=date(2024, 1, 3)):
    return Signal(
        signal_id=f"sig:exit:{symbol}:{signal_date}",
        strategy_id="golden-breakout",
        strategy_version="v1",
        symbol=symbol,
        signal_date=signal_date,
        signal_type="exit",
        triggered_rules=["ma_condition:close<ma_5d"],
        audit_id=f"audit:exit:{symbol}:{signal_date}",
    )


class OrderGenerationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data_source = GoldenCaseDataSource(Path(__file__).parent / "golden_cases")
        cls.sizer = PositionSizer(position_ratio=0.2)

    def test_entry_signal_becomes_buy_order_intended_for_later_execution(self):
        """
        Entry signal uses position sizer to calculate quantity based on signal_date price.
        """
        signal = entry_signal(symbol="000001.SZ", signal_date=date(2024, 1, 2))
        price = self.data_source.get_price("000001.SZ", date(2024, 1, 2))
        available_capital = 10000.0
        expected_quantity = self.sizer.calculate_quantity(price, available_capital)

        result = generate_orders(
            [signal],
            date(2024, 1, 3),
            self.data_source,
            self.sizer,
            available_capital,
            current_positions={},
        )

        self.assertEqual(len(result.valid_orders), 1)
        order = result.valid_orders[0]
        self.assertEqual(order.signal_id, signal.signal_id)
        self.assertEqual(order.signal_date, signal.signal_date)
        self.assertEqual(order.intended_execution_date, date(2024, 1, 3))
        self.assertIsNone(order.actual_execution_date)
        self.assertEqual(order.symbol, "000001.SZ")
        self.assertEqual(order.direction, "buy")
        self.assertEqual(order.quantity, expected_quantity)
        self.assertGreater(order.quantity, 0)
        self.assertEqual(order.reason, "breakthrough:close>=high_2d")
        self.assertEqual(order.strategy_version, "v1")
        self.assertEqual(order.generated_by, "strategy_core")
        self.assertEqual(order.status, "planned")

    def test_hold_signal_does_not_create_order(self):
        """
        Hold signals do not generate orders.
        """
        signal = entry_signal()
        hold_signal = signal.model_copy(update={"signal_type": "hold", "signal_id": "hold:000001.SZ"})

        result = generate_orders(
            [hold_signal],
            date(2024, 1, 4),
            self.data_source,
            self.sizer,
            10000.0,
            current_positions={},
        )

        self.assertEqual(result.valid_orders, [])
        self.assertEqual(result.events, [])

    def test_entry_signal_with_insufficient_capital_produces_no_order(self):
        """
        When available capital is insufficient for one lot, no order is generated.
        """
        signal = entry_signal(symbol="000001.SZ", signal_date=date(2024, 1, 2))
        
        result = generate_orders(
            [signal],
            date(2024, 1, 3),
            self.data_source,
            self.sizer,
            available_capital=10.0,
            current_positions={},
        )

        self.assertEqual(result.valid_orders, [])
        self.assertEqual(len(result.events), 1)
        self.assertEqual(result.events[0].event_type, "zero_quantity")

    def test_exit_signal_generates_sell_order_for_entire_position(self):
        """
        Exit signal generates sell order for entire position.
        """
        signal = exit_signal(symbol="000001.SZ", signal_date=date(2024, 1, 2))
        current_positions = {
            "000001.SZ": Position(symbol="000001.SZ", quantity=200, sellable_quantity=200, avg_cost=10.0, last_price=12.0)
        }

        result = generate_orders(
            [signal],
            date(2024, 1, 3),
            self.data_source,
            self.sizer,
            10000.0,
            current_positions=current_positions,
        )

        self.assertEqual(len(result.valid_orders), 1)
        order = result.valid_orders[0]
        self.assertEqual(order.direction, "sell")
        self.assertEqual(order.quantity, 200)
        self.assertEqual(order.symbol, "000001.SZ")
        self.assertEqual(order.status, "planned")

    def test_exit_signal_rejected_when_no_position(self):
        """
        Exit signal creates rejected order when there is no position.
        """
        signal = exit_signal(symbol="000001.SZ", signal_date=date(2024, 1, 2))

        result = generate_orders(
            [signal],
            date(2024, 1, 3),
            self.data_source,
            self.sizer,
            10000.0,
            current_positions={},
        )

        self.assertEqual(len(result.valid_orders), 0)
        self.assertEqual(len(result.events), 1)
        event = result.events[0]
        self.assertEqual(event.event_type, "no_position_to_exit")
        self.assertEqual(event.symbol, "000001.SZ")

    def test_exit_signal_uses_current_position_quantity(self):
        """
        Exit signal uses the exact quantity from current position.
        """
        signal = exit_signal(symbol="000001.SZ", signal_date=date(2024, 1, 2))
        current_positions = {
            "000001.SZ": Position(symbol="000001.SZ", quantity=350, sellable_quantity=350, avg_cost=10.0, last_price=12.0)
        }

        result = generate_orders(
            [signal],
            date(2024, 1, 3),
            self.data_source,
            self.sizer,
            10000.0,
            current_positions=current_positions,
        )

        self.assertEqual(len(result.valid_orders), 1)
        self.assertEqual(result.valid_orders[0].quantity, 350)

    def test_entry_exit_conflict_on_same_symbol_rejects_entry(self):
        """
        When both entry and exit signals exist for same symbol, exit wins and entry is rejected.
        """
        entry_sig = entry_signal(symbol="000001.SZ", signal_date=date(2024, 1, 2))
        exit_sig = exit_signal(symbol="000001.SZ", signal_date=date(2024, 1, 2))
        current_positions = {
            "000001.SZ": Position(symbol="000001.SZ", quantity=200, sellable_quantity=200, avg_cost=10.0, last_price=12.0)
        }

        result = generate_orders(
            [entry_sig, exit_sig],
            date(2024, 1, 3),
            self.data_source,
            self.sizer,
            10000.0,
            current_positions=current_positions,
        )

        self.assertEqual(len(result.valid_orders), 1)
        self.assertEqual(len(result.events), 1)
        
        # Find exit order and conflict event
        exit_order = result.valid_orders[0]
        conflict_event = result.events[0]
        
        # Entry should be rejected via event
        self.assertEqual(conflict_event.event_type, "signal_conflict")
        self.assertEqual(conflict_event.reason, "entry_exit_conflict_on_same_day")
        
        # Exit should be planned
        self.assertEqual(exit_order.status, "planned")
        self.assertEqual(exit_order.quantity, 200)

    def test_exit_quantity_equals_position_quantity_mvp(self):
        """
        Exit quantity uses position.sellable_quantity (T+1 implemented).
        """
        signal = exit_signal(symbol="000001.SZ", signal_date=date(2024, 1, 2))
        current_positions = {
            "000001.SZ": Position(symbol="000001.SZ", quantity=500, sellable_quantity=500, avg_cost=10.0, last_price=12.0)
        }

        result = generate_orders(
            [signal],
            date(2024, 1, 3),
            self.data_source,
            self.sizer,
            10000.0,
            current_positions=current_positions,
        )

        # Uses sellable_quantity
        self.assertEqual(result.valid_orders[0].quantity, 500)

    def test_multiple_entry_signals_share_available_capital(self):
        """
        Multiple entry signals use the same available_capital.
        """
        signal1 = entry_signal(symbol="000001.SZ", signal_date=date(2024, 1, 2))
        signal2 = entry_signal(symbol="000002.SZ", signal_date=date(2024, 1, 2))
        available_capital = 10000.0

        result = generate_orders(
            [signal1, signal2],
            date(2024, 1, 3),
            self.data_source,
            self.sizer,
            available_capital,
            current_positions={},
        )

        self.assertEqual(len(result.valid_orders), 2)
        self.assertGreater(result.valid_orders[0].quantity, 0)
        self.assertGreater(result.valid_orders[1].quantity, 0)


if __name__ == "__main__":
    unittest.main()
