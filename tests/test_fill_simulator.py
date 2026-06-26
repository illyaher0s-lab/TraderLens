from datetime import date
from pathlib import Path
import unittest

from backend.app.contracts import Order, Signal
from backend.app.golden_cases import GoldenCaseDataSource
from strategy_core.portfolio import Position, PortfolioState
from strategy_core.fill_simulator import simulate_fill
from strategy_core.trading_calendar import TradingCalendar


def buy_order(symbol="000001.SZ", quantity=100, signal_date=date(2024, 1, 2), execution_date=date(2024, 1, 3)):
    return Order(
        order_id=f"order:{symbol}:{execution_date}",
        signal_id=f"sig:{symbol}:{signal_date}",
        signal_date=signal_date,
        intended_execution_date=execution_date,
        symbol=symbol,
        direction="buy",
        quantity=quantity,
        reason="test",
        strategy_version="v1",
        audit_id="test_audit",
    )


def sell_order(symbol="000001.SZ", quantity=100, signal_date=date(2024, 1, 2), execution_date=date(2024, 1, 3)):
    return Order(
        order_id=f"order:{symbol}:{execution_date}",
        signal_id=f"sig:{symbol}:{signal_date}",
        signal_date=signal_date,
        intended_execution_date=execution_date,
        symbol=symbol,
        direction="sell",
        quantity=quantity,
        reason="test",
        strategy_version="v1",
        audit_id="test_audit",
    )


class TestFillSimulator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data_source = GoldenCaseDataSource(Path(__file__).parent / "golden_cases")
        cls.calendar = TradingCalendar(cls.data_source)

    def test_buy_order_fills_at_open_price_when_conditions_met(self):
        """
        Buy order fills at open price when not suspended/limit_up and capital is sufficient.
        """
        portfolio = PortfolioState(cash=10000.0)
        order = buy_order(symbol="000001.SZ", quantity=100, execution_date=date(2024, 1, 3))
        
        filled_order = simulate_fill(order, date(2024, 1, 3), self.data_source, portfolio, calendar=self.calendar)
        
        self.assertEqual(filled_order.status, "filled")
        self.assertEqual(filled_order.actual_execution_date, date(2024, 1, 3))
        self.assertIsNotNone(filled_order.actual_price)
        self.assertEqual(filled_order.actual_quantity, 100)
        self.assertIn("000001.SZ", portfolio.positions)
        self.assertEqual(portfolio.positions["000001.SZ"].quantity, 100)

    def test_buy_order_rejected_when_suspended(self):
        """
        Buy order rejected when symbol is suspended.
        """
        portfolio = PortfolioState(cash=10000.0)
        # 600000.SH is suspended on 2024-01-03 (from Golden Case)
        order = buy_order(symbol="600000.SH", quantity=100, execution_date=date(2024, 1, 3))
        
        filled_order = simulate_fill(order, date(2024, 1, 3), self.data_source, portfolio, calendar=self.calendar)
        
        self.assertEqual(filled_order.status, "rejected")
        self.assertEqual(filled_order.rejection_reason, "suspended")
        self.assertNotIn("600000.SH", portfolio.positions)

    def test_buy_order_rejected_when_limit_up(self):
        """
        Buy order rejected when symbol is limit up.
        """
        portfolio = PortfolioState(cash=100000.0)
        # 600519.SH is limit up on 2024-01-03 (from Golden Case)
        order = buy_order(symbol="600519.SH", quantity=100, execution_date=date(2024, 1, 3))
        
        filled_order = simulate_fill(order, date(2024, 1, 3), self.data_source, portfolio, calendar=self.calendar)
        
        self.assertEqual(filled_order.status, "rejected")
        self.assertEqual(filled_order.rejection_reason, "limit_up")

    def test_buy_order_reduces_quantity_when_insufficient_capital(self):
        """
        Buy order quantity is reduced to affordable lots when capital is insufficient.
        """
        portfolio = PortfolioState(cash=1500.0)
        # price is around 10-20, so 1500 can afford 1 lot but not 2
        order = buy_order(symbol="000001.SZ", quantity=200, execution_date=date(2024, 1, 3))
        
        filled_order = simulate_fill(order, date(2024, 1, 3), self.data_source, portfolio, calendar=self.calendar)
        
        self.assertEqual(filled_order.status, "filled")
        self.assertLess(filled_order.actual_quantity, 200)
        self.assertGreater(filled_order.actual_quantity, 0)
        self.assertEqual(filled_order.actual_quantity % 100, 0, "quantity must be lot-sized")

    def test_buy_order_rejected_when_capital_insufficient_for_one_lot(self):
        """
        Buy order rejected when capital cannot afford even one lot.
        """
        portfolio = PortfolioState(cash=50.0)
        order = buy_order(symbol="000001.SZ", quantity=100, execution_date=date(2024, 1, 3))
        
        filled_order = simulate_fill(order, date(2024, 1, 3), self.data_source, portfolio, calendar=self.calendar)
        
        self.assertEqual(filled_order.status, "rejected")
        self.assertEqual(filled_order.rejection_reason, "insufficient_capital")

    def test_buy_order_rejected_when_no_t1_unlock_date_exists(self):
        """
        Buy order should reject on the final available trading day.

        A-share T+1 tracking needs a following trading day to create the frozen
        lot unlock date. The simulator should fail loud as a rejected order, not
        mutate cash and then raise from PortfolioState.add_position().
        """
        portfolio = PortfolioState(cash=10000.0)
        order = buy_order(
            symbol="000001.SZ",
            quantity=100,
            signal_date=date(2024, 1, 3),
            execution_date=date(2025, 1, 2),
        )

        filled_order = simulate_fill(order, date(2025, 1, 2), self.data_source, portfolio, calendar=self.calendar)

        self.assertEqual(filled_order.status, "rejected")
        self.assertEqual(filled_order.rejection_reason, "no_t1_unlock_date")
        self.assertEqual(portfolio.cash, 10000.0)
        self.assertNotIn("000001.SZ", portfolio.positions)

    def test_buy_order_updates_position_and_cash(self):
        """
        Buy order deducts cash and creates/updates position (including transaction costs).
        """
        portfolio = PortfolioState(cash=10000.0)
        order = buy_order(symbol="000001.SZ", quantity=100, execution_date=date(2024, 1, 3))
        
        initial_cash = portfolio.cash
        filled_order = simulate_fill(order, date(2024, 1, 3), self.data_source, portfolio, calendar=self.calendar)
        
        self.assertLess(portfolio.cash, initial_cash)
        self.assertEqual(portfolio.positions["000001.SZ"].quantity, 100)
        
        # Cash should be deducted by gross amount + commission (min 5 RMB)
        gross = filled_order.actual_price * filled_order.actual_quantity
        commission = 5.0  # minimum commission
        expected_cash = initial_cash - gross - commission
        self.assertAlmostEqual(portfolio.cash, expected_cash, places=2)

    def test_sell_order_fills_at_open_price_when_conditions_met(self):
        """
        Sell order fills at open price when not limit_down and position is sufficient.
        """
        portfolio = PortfolioState(cash=5000.0)
        portfolio.positions["000001.SZ"] = Position(
            symbol="000001.SZ", quantity=200, sellable_quantity=200, avg_cost=10.0, last_price=12.0
        )
        order = sell_order(symbol="000001.SZ", quantity=100, execution_date=date(2024, 1, 3))
        
        initial_cash = portfolio.cash
        filled_order = simulate_fill(order, date(2024, 1, 3), self.data_source, portfolio, calendar=self.calendar)
        
        self.assertEqual(filled_order.status, "filled")
        self.assertEqual(filled_order.actual_quantity, 100)
        self.assertEqual(portfolio.positions["000001.SZ"].quantity, 100)
        self.assertGreater(portfolio.cash, initial_cash)

    def test_sell_order_rejected_when_limit_down(self):
        """
        Sell order rejected when symbol is limit down.
        """
        portfolio = PortfolioState(cash=5000.0)
        portfolio.positions["000002.SZ"] = Position(
            symbol="000002.SZ", quantity=100, sellable_quantity=100, avg_cost=12.0, last_price=14.0
        )
        # 000002.SZ is limit down on 2024-01-03 (from Golden Case)
        order = sell_order(symbol="000002.SZ", quantity=100, execution_date=date(2024, 1, 3))
        
        filled_order = simulate_fill(order, date(2024, 1, 3), self.data_source, portfolio, calendar=self.calendar)
        
        self.assertEqual(filled_order.status, "rejected")
        self.assertEqual(filled_order.rejection_reason, "limit_down")
        self.assertEqual(portfolio.positions["000002.SZ"].quantity, 100)

    def test_sell_order_rejected_when_no_position(self):
        """
        Sell order rejected when there is no position in the symbol.
        """
        portfolio = PortfolioState(cash=5000.0)
        order = sell_order(symbol="000001.SZ", quantity=100, execution_date=date(2024, 1, 3))
        
        filled_order = simulate_fill(order, date(2024, 1, 3), self.data_source, portfolio, calendar=self.calendar)
        
        self.assertEqual(filled_order.status, "rejected")
        self.assertEqual(filled_order.rejection_reason, "no_position")

    def test_sell_order_rejected_when_insufficient_position(self):
        """
        Sell order rejected when position quantity is insufficient.
        """
        portfolio = PortfolioState(cash=5000.0)
        portfolio.positions["000001.SZ"] = Position(
            symbol="000001.SZ", quantity=50, sellable_quantity=50, avg_cost=10.0, last_price=12.0
        )
        order = sell_order(symbol="000001.SZ", quantity=100, execution_date=date(2024, 1, 3))
        
        filled_order = simulate_fill(order, date(2024, 1, 3), self.data_source, portfolio, calendar=self.calendar)
        
        self.assertEqual(filled_order.status, "rejected")
        self.assertEqual(filled_order.rejection_reason, "insufficient_position")
        self.assertEqual(portfolio.positions["000001.SZ"].quantity, 50)

    def test_buy_order_deducts_commission_from_cash(self):
        """
        Buy order deducts commission (minimum 5 RMB) from cash.
        """
        portfolio = PortfolioState(cash=10000.0)
        order = buy_order(symbol="000001.SZ", quantity=100, execution_date=date(2024, 1, 3))
        
        initial_cash = portfolio.cash
        filled_order = simulate_fill(order, date(2024, 1, 3), self.data_source, portfolio, calendar=self.calendar)
        
        # Small trade pays minimum commission
        gross = filled_order.actual_price * filled_order.actual_quantity
        commission = 5.0
        expected_deduction = gross + commission
        
        self.assertAlmostEqual(portfolio.cash, initial_cash - expected_deduction, places=2)

    def test_sell_order_deducts_commission_and_stamp_duty(self):
        """
        Sell order deducts commission and stamp duty from proceeds.
        """
        portfolio = PortfolioState(cash=5000.0)
        portfolio.positions["000001.SZ"] = Position(
            symbol="000001.SZ", quantity=200, sellable_quantity=200, avg_cost=10.0, last_price=12.0
        )
        order = sell_order(symbol="000001.SZ", quantity=100, execution_date=date(2024, 1, 3))
        
        initial_cash = portfolio.cash
        filled_order = simulate_fill(order, date(2024, 1, 3), self.data_source, portfolio, calendar=self.calendar)
        
        # Calculate expected proceeds
        gross = filled_order.actual_price * filled_order.actual_quantity
        commission = 5.0  # minimum
        stamp_duty = gross * 0.001
        net_proceeds = gross - commission - stamp_duty
        
        self.assertAlmostEqual(portfolio.cash, initial_cash + net_proceeds, places=2)

    def test_buy_rejected_when_capital_insufficient_after_costs(self):
        """
        Buy order rejected when capital insufficient to cover price + commission.
        """
        portfolio = PortfolioState(cash=1004.0)  # Just below 1005 needed
        order = buy_order(symbol="000001.SZ", quantity=100, execution_date=date(2024, 1, 3))
        
        filled_order = simulate_fill(order, date(2024, 1, 3), self.data_source, portfolio, calendar=self.calendar)
        
        # Should be rejected due to insufficient capital
        self.assertEqual(filled_order.status, "rejected")
        self.assertEqual(filled_order.rejection_reason, "insufficient_capital")

    def test_small_trade_pays_minimum_commission(self):
        """
        Very small trades pay minimum commission (5 RMB).
        """
        portfolio = PortfolioState(cash=10000.0)
        order = buy_order(symbol="000001.SZ", quantity=100, execution_date=date(2024, 1, 3))
        
        initial_cash = portfolio.cash
        simulate_fill(order, date(2024, 1, 3), self.data_source, portfolio, calendar=self.calendar)
        
        # Commission should be 5 RMB (minimum), not gross * 0.0003
        # Even if gross is ~1000, 0.0003 * 1000 = 0.3 < 5
        cash_spent = initial_cash - portfolio.cash
        # cash_spent = gross + commission, so commission = cash_spent - gross
        # We expect commission to be exactly 5 RMB
        self.assertGreater(cash_spent, portfolio.positions["000001.SZ"].avg_cost * 100)


if __name__ == "__main__":
    unittest.main()
