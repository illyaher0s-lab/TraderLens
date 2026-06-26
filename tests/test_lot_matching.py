import unittest
from datetime import date

from backend.app.contracts import Trade
from strategy_core.lot_matching import LotMatcher


def create_buy_trade(trade_id: str, symbol: str, quantity: int, price: float, trade_date: date) -> Trade:
    """Helper to create a buy trade."""
    gross_amount = quantity * price
    commission = max(gross_amount * 0.0003, 5.0)
    return Trade(
        trade_id=trade_id,
        order_id=f"o_{trade_id}",
        symbol=symbol,
        direction="buy",
        quantity=quantity,
        price=price,
        trade_date=trade_date,
        gross_amount=gross_amount,
        commission=commission,
        stamp_duty=0.0,
        transfer_fee=0.0,
        total_fee=commission,
        net_cash_flow=-(gross_amount + commission),
        cost=-(gross_amount + commission),
    )


def create_sell_trade(trade_id: str, symbol: str, quantity: int, price: float, trade_date: date) -> Trade:
    """Helper to create a sell trade."""
    gross_amount = quantity * price
    commission = max(gross_amount * 0.0003, 5.0)
    stamp_duty = gross_amount * 0.001
    return Trade(
        trade_id=trade_id,
        order_id=f"o_{trade_id}",
        symbol=symbol,
        direction="sell",
        quantity=quantity,
        price=price,
        trade_date=trade_date,
        gross_amount=gross_amount,
        commission=commission,
        stamp_duty=stamp_duty,
        transfer_fee=0.0,
        total_fee=commission + stamp_duty,
        net_cash_flow=gross_amount - commission - stamp_duty,
        cost=gross_amount - commission - stamp_duty,
    )


class TestLotMatching(unittest.TestCase):
    def test_simple_buy_sell_generates_one_round_trip(self):
        """
        Simple buy → sell generates one round-trip.
        """
        matcher = LotMatcher()
        
        buy = create_buy_trade("t1", "000001.SZ", 100, 10.0, date(2024, 1, 2))
        sell = create_sell_trade("t2", "000001.SZ", 100, 12.0, date(2024, 1, 3))
        
        matcher.process_trade(buy)
        round_trips = matcher.process_trade(sell)
        
        self.assertEqual(len(round_trips), 1)
        self.assertEqual(round_trips[0].matched_quantity, 100)
        self.assertEqual(round_trips[0].buy_trade_id, "t1")
        self.assertEqual(round_trips[0].sell_trade_id, "t2")
        self.assertGreater(round_trips[0].realized_pnl, 0)  # Profit

    def test_fifo_matching_with_multiple_buys(self):
        """
        Multiple buys → one sell matches FIFO (oldest first).
        """
        matcher = LotMatcher()
        
        buy1 = create_buy_trade("t1", "000001.SZ", 100, 10.0, date(2024, 1, 2))
        buy2 = create_buy_trade("t2", "000001.SZ", 100, 11.0, date(2024, 1, 3))
        sell = create_sell_trade("t3", "000001.SZ", 150, 12.0, date(2024, 1, 4))
        
        matcher.process_trade(buy1)
        matcher.process_trade(buy2)
        round_trips = matcher.process_trade(sell)
        
        self.assertEqual(len(round_trips), 2)
        # First round-trip closes buy1 (100 shares)
        self.assertEqual(round_trips[0].buy_trade_id, "t1")
        self.assertEqual(round_trips[0].matched_quantity, 100)
        # Second round-trip closes 50 shares from buy2
        self.assertEqual(round_trips[1].buy_trade_id, "t2")
        self.assertEqual(round_trips[1].matched_quantity, 50)

    def test_partial_sell_closes_partial_lot(self):
        """
        Sell quantity < buy quantity leaves open lot.
        """
        matcher = LotMatcher()
        
        buy = create_buy_trade("t1", "000001.SZ", 100, 10.0, date(2024, 1, 2))
        sell = create_sell_trade("t2", "000001.SZ", 50, 12.0, date(2024, 1, 3))
        
        matcher.process_trade(buy)
        round_trips = matcher.process_trade(sell)
        
        self.assertEqual(len(round_trips), 1)
        self.assertEqual(round_trips[0].matched_quantity, 50)
        
        # Remaining lot should still be open
        self.assertEqual(len(matcher.open_lots["000001.SZ"]), 1)
        self.assertEqual(matcher.open_lots["000001.SZ"][0].remaining_quantity, 50)

    def test_multiple_sells_close_same_buy_lot(self):
        """
        Multiple sells can close the same buy lot sequentially.
        """
        matcher = LotMatcher()
        
        buy = create_buy_trade("t1", "000001.SZ", 100, 10.0, date(2024, 1, 2))
        sell1 = create_sell_trade("t2", "000001.SZ", 30, 12.0, date(2024, 1, 3))
        sell2 = create_sell_trade("t3", "000001.SZ", 70, 12.0, date(2024, 1, 4))
        
        matcher.process_trade(buy)
        rt1 = matcher.process_trade(sell1)
        rt2 = matcher.process_trade(sell2)
        
        self.assertEqual(len(rt1), 1)
        self.assertEqual(rt1[0].matched_quantity, 30)
        
        self.assertEqual(len(rt2), 1)
        self.assertEqual(rt2[0].matched_quantity, 70)
        
        # All buy lot consumed
        self.assertEqual(len(matcher.open_lots.get("000001.SZ", [])), 0)

    def test_sell_without_buy_returns_empty_and_warns(self):
        """
        Sell without buy returns empty round-trips and increments unmatched_sells_count.
        """
        matcher = LotMatcher()
        
        sell = create_sell_trade("t1", "000001.SZ", 100, 12.0, date(2024, 1, 3))
        
        round_trips = matcher.process_trade(sell)
        
        self.assertEqual(len(round_trips), 0)
        self.assertEqual(matcher.unmatched_sells_count, 1)

    def test_round_trip_pnl_calculation(self):
        """
        Round-trip PnL is calculated correctly.
        """
        matcher = LotMatcher()
        
        buy = create_buy_trade("t1", "000001.SZ", 100, 10.0, date(2024, 1, 2))
        sell = create_sell_trade("t2", "000001.SZ", 100, 12.0, date(2024, 1, 3))
        
        matcher.process_trade(buy)
        round_trips = matcher.process_trade(sell)
        
        rt = round_trips[0]
        
        # Buy cost = gross + commission
        expected_buy_cost = 1000.0 + 5.0  # min commission
        self.assertAlmostEqual(rt.buy_cost, expected_buy_cost, places=2)
        
        # Sell proceeds = gross - commission - stamp_duty
        # For 1200 gross: commission = max(1200 * 0.0003, 5.0) = 5.0
        # stamp_duty = 1200 * 0.001 = 1.2
        # But actual sell trade uses gross * 0.0003 = 0.36, so min 5.0
        actual_commission = max(1200.0 * 0.0003, 5.0)
        actual_stamp_duty = 1200.0 * 0.001
        expected_sell_proceeds = 1200.0 - actual_commission - actual_stamp_duty
        self.assertAlmostEqual(rt.sell_proceeds, expected_sell_proceeds, places=2)
        
        # PnL = sell_proceeds - buy_cost
        expected_pnl = expected_sell_proceeds - expected_buy_cost
        self.assertAlmostEqual(rt.realized_pnl, expected_pnl, places=2)

    def test_holding_days_calculation(self):
        """
        Holding days is calculated correctly.
        """
        matcher = LotMatcher()
        
        buy = create_buy_trade("t1", "000001.SZ", 100, 10.0, date(2024, 1, 2))
        sell = create_sell_trade("t2", "000001.SZ", 100, 12.0, date(2024, 1, 10))
        
        matcher.process_trade(buy)
        round_trips = matcher.process_trade(sell)
        
        self.assertEqual(round_trips[0].holding_days, 8)

    def test_sell_exceeding_available_lots_warns(self):
        """
        Sell quantity > total available lots increments unmatched_sells_count.
        """
        matcher = LotMatcher()
        
        buy = create_buy_trade("t1", "000001.SZ", 100, 10.0, date(2024, 1, 2))
        sell = create_sell_trade("t2", "000001.SZ", 150, 12.0, date(2024, 1, 3))
        
        matcher.process_trade(buy)
        round_trips = matcher.process_trade(sell)
        
        # Should generate 1 round-trip for 100 shares
        self.assertEqual(len(round_trips), 1)
        self.assertEqual(round_trips[0].matched_quantity, 100)
        
        # Remaining 50 shares unmatched
        self.assertEqual(matcher.unmatched_sells_count, 1)


if __name__ == "__main__":
    unittest.main()
