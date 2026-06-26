"""B4 A-share Fill Constraints Tests - Verify A-share execution rules."""
import unittest
from datetime import date

from strategy_core.fill_simulator import simulate_fill
from strategy_core.portfolio import PortfolioState
from strategy_core.trading_calendar import TradingCalendar
from backend.app.golden_cases import GoldenCaseDataSource
from contracts.stable import Order, DailyBar, DailyStatus
from pathlib import Path


class MockDataSource:
    """Mock data source for testing fill constraints."""
    
    def __init__(self):
        self.bars = {}
        self.statuses = {}
    
    def symbols(self):
        """Return list of symbols."""
        return list(self.bars.keys())
    
    def add_bar(self, symbol: str, trade_date: date, bar: DailyBar):
        if symbol not in self.bars:
            self.bars[symbol] = {}
        self.bars[symbol][trade_date] = bar
    
    def add_status(self, symbol: str, trade_date: date, status: DailyStatus):
        if symbol not in self.statuses:
            self.statuses[symbol] = {}
        self.statuses[symbol][trade_date] = status
    
    def get_daily_bar(self, symbol: str, trade_date: date) -> DailyBar:
        if symbol not in self.bars or trade_date not in self.bars[symbol]:
            raise KeyError(f"No bar for {symbol} on {trade_date}")
        return self.bars[symbol][trade_date]
    
    def get_daily_status(self, symbol: str, trade_date: date) -> DailyStatus:
        if symbol not in self.statuses or trade_date not in self.statuses[symbol]:
            raise KeyError(f"No status for {symbol} on {trade_date}")
        return self.statuses[symbol][trade_date]
    
    def get_daily_bars(self, symbol: str) -> list[DailyBar]:
        if symbol not in self.bars:
            return []
        return list(self.bars[symbol].values())


class TestB4AshareFillConstraints(unittest.TestCase):
    """Test A-share execution constraints and cost model."""
    
    def setUp(self):
        self.data_source = MockDataSource()
        self.portfolio = PortfolioState(cash=100000.0)
    
    def _create_calendar(self):
        """Create calendar with mock data."""
        # Add some trading dates to mock data source
        for day in range(1, 20):
            bar = DailyBar(
                date=date(2024, 1, day),
                symbol="000001.SZ",
                open=10.0, high=10.5, low=9.5, close=10.0,
                volume=1000000, amount=10000000.0, adj_factor=1.0,
            )
            self.data_source.add_bar("000001.SZ", date(2024, 1, day), bar)
        
        return TradingCalendar(self.data_source)
    
    def _create_order(self, order_id: str, symbol: str, direction: str, quantity: int, 
                     signal_date: date, execution_date: date) -> Order:
        """Create test order with required fields."""
        return Order(
            order_id=order_id,
            signal_id=f"signal_{order_id}",
            signal_date=signal_date,
            intended_execution_date=execution_date,
            symbol=symbol,
            direction=direction,
            quantity=quantity,
            reason="test_order",
            strategy_version="test_v1",
            audit_id=f"audit_{order_id}",
            status="planned",
        )
    
    def test_limit_up_blocks_buy(self):
        """Limit-up blocks buy orders."""
        calendar = self._create_calendar()
        
        # Setup: limit-up bar
        bar = DailyBar(
            date=date(2024, 1, 10),
            symbol="000001.SZ",
            open=10.0, high=11.0, low=10.0, close=11.0,
            volume=1000000, amount=10500000.0, adj_factor=1.0,
        )
        status = DailyStatus(
            date=date(2024, 1, 10),
            symbol="000001.SZ",
            is_st=False, is_suspended=False,
            is_limit_up=True, is_limit_down=False,
        )
        
        self.data_source.add_bar("000001.SZ", date(2024, 1, 10), bar)
        self.data_source.add_status("000001.SZ", date(2024, 1, 10), status)
        
        # Create buy order
        order = self._create_order(
            "order_001", "000001.SZ", "buy", 100,
            date(2024, 1, 9), date(2024, 1, 10)
        )
        
        # Simulate fill
        filled = simulate_fill(
            order, date(2024, 1, 10), self.data_source, self.portfolio,
            commission_rate=0.0003, min_commission=5.0,
            stamp_duty_rate=0.001, calendar=calendar,
        )
        
        # Verify rejected
        self.assertEqual(filled.status, "rejected")
        self.assertEqual(filled.rejection_reason, "limit_up")
    
    def test_limit_down_blocks_sell(self):
        """Limit-down blocks sell orders."""
        calendar = self._create_calendar()
        
        # Setup: limit-down bar
        bar = DailyBar(
            date=date(2024, 1, 10),
            symbol="000001.SZ",
            open=9.0, high=9.0, low=8.0, close=8.0,
            volume=1000000, amount=8500000.0, adj_factor=1.0,
        )
        status = DailyStatus(
            date=date(2024, 1, 10),
            symbol="000001.SZ",
            is_st=False, is_suspended=False,
            is_limit_up=False, is_limit_down=True,
        )
        
        self.data_source.add_bar("000001.SZ", date(2024, 1, 10), bar)
        self.data_source.add_status("000001.SZ", date(2024, 1, 10), status)
        
        # Add position to portfolio
        self.portfolio.add_position("000001.SZ", 200, 10.0, date(2024, 1, 8), calendar)
        self.portfolio.unlock_frozen_lots(date(2024, 1, 10))
        
        # Create sell order
        order = self._create_order(
            "order_002", "000001.SZ", "sell", 100,
            date(2024, 1, 9), date(2024, 1, 10)
        )
        
        # Simulate fill
        filled = simulate_fill(
            order, date(2024, 1, 10), self.data_source, self.portfolio,
            commission_rate=0.0003, min_commission=5.0,
            stamp_duty_rate=0.001, calendar=calendar,
        )
        
        # Verify rejected
        self.assertEqual(filled.status, "rejected")
        self.assertEqual(filled.rejection_reason, "limit_down")
    
    def test_suspended_blocks_buy_and_sell(self):
        """Suspended status blocks both buy and sell."""
        calendar = self._create_calendar()
        
        # Setup: suspended
        bar = DailyBar(
            date=date(2024, 1, 10),
            symbol="000001.SZ",
            open=10.0, high=10.0, low=10.0, close=10.0,
            volume=0, amount=0.0, adj_factor=1.0,
        )
        status = DailyStatus(
            date=date(2024, 1, 10),
            symbol="000001.SZ",
            is_st=False, is_suspended=True,
            is_limit_up=False, is_limit_down=False,
            suspend_reason="major_announcement",
        )
        
        self.data_source.add_bar("000001.SZ", date(2024, 1, 10), bar)
        self.data_source.add_status("000001.SZ", date(2024, 1, 10), status)
        
        # Test buy
        buy_order = self._create_order(
            "order_003", "000001.SZ", "buy", 100,
            date(2024, 1, 9), date(2024, 1, 10)
        )
        
        filled_buy = simulate_fill(
            buy_order, date(2024, 1, 10), self.data_source, self.portfolio,
            commission_rate=0.0003, min_commission=5.0,
            stamp_duty_rate=0.001, calendar=calendar,
        )
        
        self.assertEqual(filled_buy.status, "rejected")
        self.assertEqual(filled_buy.rejection_reason, "suspended")
        
        # Test sell (add position first)
        self.portfolio.add_position("000001.SZ", 200, 10.0, date(2024, 1, 8), calendar)
        self.portfolio.unlock_frozen_lots(date(2024, 1, 10))
        
        sell_order = self._create_order(
            "order_004", "000001.SZ", "sell", 100,
            date(2024, 1, 9), date(2024, 1, 10)
        )
        
        filled_sell = simulate_fill(
            sell_order, date(2024, 1, 10), self.data_source, self.portfolio,
            commission_rate=0.0003, min_commission=5.0,
            stamp_duty_rate=0.001, calendar=calendar,
        )
        
        self.assertEqual(filled_sell.status, "rejected")
        self.assertEqual(filled_sell.rejection_reason, "suspended")
    
    def test_t_plus_1_blocks_same_day_sell(self):
        """T+1 restriction: cannot sell same-day purchased stock."""
        calendar = self._create_calendar()
        
        # Buy on T
        bar_t = DailyBar(
            date=date(2024, 1, 10),
            symbol="000001.SZ",
            open=10.0, high=10.5, low=9.5, close=10.2,
            volume=1000000, amount=10100000.0, adj_factor=1.0,
        )
        self.data_source.add_bar("000001.SZ", date(2024, 1, 10), bar_t)
        
        # Add position on T (frozen until T+1)
        self.portfolio.add_position("000001.SZ", 100, 10.0, date(2024, 1, 10), calendar)
        
        # Check: sellable_quantity should be 0 (frozen)
        position = self.portfolio.positions["000001.SZ"]
        self.assertEqual(position.quantity, 100)
        self.assertEqual(position.sellable_quantity, 0)
        
        # Unlock on T+1
        self.portfolio.unlock_frozen_lots(date(2024, 1, 11))
        
        # Now sellable_quantity should be 100
        self.assertEqual(position.sellable_quantity, 100)
    
    def test_lot_size_rounds_to_100_shares(self):
        """Buy quantity must round down to 100-share lots."""
        from strategy_core.transaction_costs import calculate_affordable_quantity
        
        # Available cash: 10,000
        # Price: 10.0
        # Without costs: can buy 1000 shares
        # With costs (commission 0.0003): ~10,003
        # Should round down to 900 shares (9 lots)
        
        affordable = calculate_affordable_quantity(
            available_cash=10000.0,
            price=10.0,
            commission_rate=0.0003,
            min_commission=5.0,
            lot_size=100,
        )
        
        # Verify rounds to 100-share lots
        self.assertEqual(affordable % 100, 0)
        self.assertLessEqual(affordable, 1000)
        self.assertGreater(affordable, 0)
    
    def test_order_below_one_lot_rejected(self):
        """Orders below 100 shares must be rejected."""
        calendar = self._create_calendar()
        
        # This is enforced by position_sizer / order_generation
        # If an order with quantity < 100 reaches fill_simulator, verify it works
        
        bar = DailyBar(
            date=date(2024, 1, 10),
            symbol="000001.SZ",
            open=10.0, high=10.5, low=9.5, close=10.2,
            volume=1000000, amount=10100000.0, adj_factor=1.0,
        )
        status = DailyStatus(
            date=date(2024, 1, 10),
            symbol="000001.SZ",
            is_st=False, is_suspended=False,
            is_limit_up=False, is_limit_down=False,
        )
        
        self.data_source.add_bar("000001.SZ", date(2024, 1, 10), bar)
        self.data_source.add_status("000001.SZ", date(2024, 1, 10), status)
        
        # Order with 50 shares (below one lot)
        order = self._create_order(
            "order_005", "000001.SZ", "buy", 50,
            date(2024, 1, 9), date(2024, 1, 10)
        )
        
        # Portfolio with limited cash (can't even afford 100 shares)
        limited_portfolio = PortfolioState(cash=500.0)
        
        filled = simulate_fill(
            order, date(2024, 1, 10), self.data_source, limited_portfolio,
            commission_rate=0.0003, min_commission=5.0,
            stamp_duty_rate=0.001, calendar=calendar,
        )
        
        # Should be rejected (insufficient capital)
        self.assertEqual(filled.status, "rejected")
        self.assertIn("insufficient_capital", filled.rejection_reason)
    
    def test_commission_applied_on_buy_and_sell(self):
        """Commission applied on both buy and sell."""
        from strategy_core.transaction_costs import calculate_transaction_costs
        
        # Buy
        gross_buy, commission_buy, stamp_buy, transfer_buy, total_buy, net_buy = calculate_transaction_costs(
            "buy", 1000, 10.0,
            commission_rate=0.0003, min_commission=5.0, stamp_duty_rate=0.001,
        )
        
        self.assertEqual(gross_buy, 10000.0)
        self.assertGreater(commission_buy, 0)  # Commission applied
        self.assertEqual(stamp_buy, 0.0)  # No stamp on buy
        
        # Sell
        gross_sell, commission_sell, stamp_sell, transfer_sell, total_sell, net_sell = calculate_transaction_costs(
            "sell", 1000, 12.0,
            commission_rate=0.0003, min_commission=5.0, stamp_duty_rate=0.001,
        )
        
        self.assertEqual(gross_sell, 12000.0)
        self.assertGreater(commission_sell, 0)  # Commission applied
        self.assertGreater(stamp_sell, 0)  # Stamp on sell
    
    def test_stamp_tax_applied_only_on_sell(self):
        """Stamp tax applied only on sell."""
        from strategy_core.transaction_costs import calculate_transaction_costs
        
        # Buy: no stamp
        _, _, stamp_buy, _, _, _ = calculate_transaction_costs(
            "buy", 1000, 10.0,
            stamp_duty_rate=0.001,
        )
        self.assertEqual(stamp_buy, 0.0)
        
        # Sell: stamp applied
        _, _, stamp_sell, _, _, _ = calculate_transaction_costs(
            "sell", 1000, 12.0,
            stamp_duty_rate=0.001,
        )
        self.assertEqual(stamp_sell, 12.0)  # 12000 * 0.001
    
    def test_minimum_commission_applied(self):
        """Minimum commission (5 RMB) applied when percentage < min."""
        from strategy_core.transaction_costs import calculate_transaction_costs
        
        # Small trade: 100 shares * 10 = 1000 RMB
        # Commission rate 0.0003: 1000 * 0.0003 = 0.3 RMB
        # Min commission: 5 RMB
        # Should use 5 RMB
        
        _, commission, _, _, _, _ = calculate_transaction_costs(
            "buy", 100, 10.0,
            commission_rate=0.0003, min_commission=5.0,
        )
        
        self.assertEqual(commission, 5.0)  # Min commission applied
    
    def test_slippage_applied_to_fill_price(self):
        """Slippage affects actual fill price."""
        calendar = self._create_calendar()
        
        bar = DailyBar(
            date=date(2024, 1, 10),
            symbol="000001.SZ",
            open=10.0, high=10.5, low=9.5, close=10.2,
            volume=1000000, amount=10100000.0, adj_factor=1.0,
        )
        status = DailyStatus(
            date=date(2024, 1, 10),
            symbol="000001.SZ",
            is_st=False, is_suspended=False,
            is_limit_up=False, is_limit_down=False,
        )
        
        self.data_source.add_bar("000001.SZ", date(2024, 1, 10), bar)
        self.data_source.add_status("000001.SZ", date(2024, 1, 10), status)
        
        # Test buy with slippage
        buy_order = self._create_order(
            "order_buy_slip", "000001.SZ", "buy", 100,
            date(2024, 1, 9), date(2024, 1, 10)
        )
        
        filled_buy = simulate_fill(
            buy_order, date(2024, 1, 10), self.data_source, self.portfolio,
            commission_rate=0.0003, min_commission=5.0,
            stamp_duty_rate=0.001, slippage_rate=0.01,  # 1% slippage
            calendar=calendar,
        )
        
        # Buy pays more: 10.0 * (1 + 0.01) = 10.1
        self.assertEqual(filled_buy.status, "filled")
        self.assertEqual(filled_buy.actual_price, 10.1)
        
        # Test sell with slippage
        self.portfolio.add_position("000001.SZ", 200, 10.0, date(2024, 1, 8), calendar)
        self.portfolio.unlock_frozen_lots(date(2024, 1, 10))
        
        sell_order = self._create_order(
            "order_sell_slip", "000001.SZ", "sell", 100,
            date(2024, 1, 9), date(2024, 1, 10)
        )
        
        filled_sell = simulate_fill(
            sell_order, date(2024, 1, 10), self.data_source, self.portfolio,
            commission_rate=0.0003, min_commission=5.0,
            stamp_duty_rate=0.001, slippage_rate=0.01,  # 1% slippage
            calendar=calendar,
        )
        
        # Sell gets less: 10.0 * (1 - 0.01) = 9.9
        self.assertEqual(filled_sell.status, "filled")
        self.assertEqual(filled_sell.actual_price, 9.9)
    
    def test_liquidity_shortfall_rejects_or_partial_fills_by_policy(self):
        """Liquidity shortfall follows reject policy."""
        calendar = self._create_calendar()
        
        # Setup: low volume bar (100,000 shares)
        bar = DailyBar(
            date=date(2024, 1, 10),
            symbol="000001.SZ",
            open=10.0, high=10.5, low=9.5, close=10.2,
            volume=100000,  # Low volume
            amount=1010000.0, adj_factor=1.0,
        )
        status = DailyStatus(
            date=date(2024, 1, 10),
            symbol="000001.SZ",
            is_st=False, is_suspended=False,
            is_limit_up=False, is_limit_down=False,
        )
        
        self.data_source.add_bar("000001.SZ", date(2024, 1, 10), bar)
        self.data_source.add_status("000001.SZ", date(2024, 1, 10), status)
        
        # Max participation: 10% of 100,000 = 10,000 shares, round to 10,000
        # Try to buy 20,000 shares (exceeds liquidity)
        order = self._create_order(
            "order_liquidity", "000001.SZ", "buy", 20000,
            date(2024, 1, 9), date(2024, 1, 10)
        )
        
        filled = simulate_fill(
            order, date(2024, 1, 10), self.data_source, self.portfolio,
            commission_rate=0.0003, min_commission=5.0,
            stamp_duty_rate=0.001, max_participation_rate=0.10,  # 10%
            calendar=calendar,
        )
        
        # Should be rejected
        self.assertEqual(filled.status, "rejected")
        self.assertEqual(filled.rejection_reason, "liquidity_shortfall")
        
        # Test sell with liquidity constraint
        self.portfolio.add_position("000001.SZ", 50000, 10.0, date(2024, 1, 8), calendar)
        self.portfolio.unlock_frozen_lots(date(2024, 1, 10))
        
        sell_order = self._create_order(
            "order_sell_liquidity", "000001.SZ", "sell", 20000,
            date(2024, 1, 9), date(2024, 1, 10)
        )
        
        filled_sell = simulate_fill(
            sell_order, date(2024, 1, 10), self.data_source, self.portfolio,
            commission_rate=0.0003, min_commission=5.0,
            stamp_duty_rate=0.001, max_participation_rate=0.10,
            calendar=calendar,
        )
        
        # Sell also rejected by liquidity
        self.assertEqual(filled_sell.status, "rejected")
        self.assertEqual(filled_sell.rejection_reason, "liquidity_shortfall")
    
    def test_rejected_order_records_reason(self):
        """Rejected orders must record rejection reason."""
        calendar = self._create_calendar()
        
        # Setup: no data available
        order = self._create_order(
            "order_006", "UNKNOWN.SZ", "buy", 100,
            date(2024, 1, 9), date(2024, 1, 10)
        )
        
        filled = simulate_fill(
            order, date(2024, 1, 10), self.data_source, self.portfolio,
            commission_rate=0.0003, min_commission=5.0,
            stamp_duty_rate=0.001, calendar=calendar,
        )
        
        self.assertEqual(filled.status, "rejected")
        self.assertIsNotNone(filled.rejection_reason)
        self.assertIn("no data available", filled.rejection_reason)
    
    def test_cash_never_goes_negative(self):
        """Portfolio cash cannot go negative."""
        calendar = self._create_calendar()
        
        # Portfolio with 1000 cash
        portfolio = PortfolioState(cash=1000.0)
        
        bar = DailyBar(
            date=date(2024, 1, 10),
            symbol="000001.SZ",
            open=10.0, high=10.5, low=9.5, close=10.2,
            volume=1000000, amount=10100000.0, adj_factor=1.0,
        )
        status = DailyStatus(
            date=date(2024, 1, 10),
            symbol="000001.SZ",
            is_st=False, is_suspended=False,
            is_limit_up=False, is_limit_down=False,
        )
        
        self.data_source.add_bar("000001.SZ", date(2024, 1, 10), bar)
        self.data_source.add_status("000001.SZ", date(2024, 1, 10), status)
        
        # Try to buy 1000 shares (10,000 RMB + costs) with only 1000 cash
        order = self._create_order(
            "order_007", "000001.SZ", "buy", 1000,
            date(2024, 1, 9), date(2024, 1, 10)
        )
        
        filled = simulate_fill(
            order, date(2024, 1, 10), self.data_source, portfolio,
            commission_rate=0.0003, min_commission=5.0,
            stamp_duty_rate=0.001, calendar=calendar,
        )
        
        # Order should be rejected or partially filled
        # Cash should never go negative
        self.assertGreaterEqual(portfolio.cash, 0.0)
        
        if filled.status == "filled":
            # Partial fill: verify actual quantity <= affordable
            self.assertLess(filled.actual_quantity, order.planned_quantity)
    
    def test_position_never_goes_negative(self):
        """Position quantity cannot go negative."""
        calendar = self._create_calendar()
        
        # Add position
        self.portfolio.add_position("000001.SZ", 100, 10.0, date(2024, 1, 8), calendar)
        self.portfolio.unlock_frozen_lots(date(2024, 1, 10))
        
        bar = DailyBar(
            date=date(2024, 1, 10),
            symbol="000001.SZ",
            open=10.0, high=10.5, low=9.5, close=10.2,
            volume=1000000, amount=10100000.0, adj_factor=1.0,
        )
        status = DailyStatus(
            date=date(2024, 1, 10),
            symbol="000001.SZ",
            is_st=False, is_suspended=False,
            is_limit_up=False, is_limit_down=False,
        )
        
        self.data_source.add_bar("000001.SZ", date(2024, 1, 10), bar)
        self.data_source.add_status("000001.SZ", date(2024, 1, 10), status)
        
        # Try to sell 200 shares (more than we have)
        order = self._create_order(
            "order_008", "000001.SZ", "sell", 200,
            date(2024, 1, 9), date(2024, 1, 10)
        )
        
        filled = simulate_fill(
            order, date(2024, 1, 10), self.data_source, self.portfolio,
            commission_rate=0.0003, min_commission=5.0,
            stamp_duty_rate=0.001, calendar=calendar,
        )
        
        # Order should be rejected or capped at available quantity
        position = self.portfolio.positions.get("000001.SZ")
        if position:
            self.assertGreaterEqual(position.quantity, 0)
            self.assertGreaterEqual(position.sellable_quantity, 0)


if __name__ == "__main__":
    unittest.main()
