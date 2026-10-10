import unittest
from decimal import Decimal

from strategy_core.transaction_costs import (
    calculate_transaction_costs,
    calculate_total_cash_required,
    calculate_affordable_quantity,
)


class TestTransactionCosts(unittest.TestCase):
    def test_buy_commission_with_minimum_threshold(self):
        """
        Buy order with small amount should pay minimum commission (5 RMB).
        """
        gross, commission, stamp_duty, transfer_fee, total_fee, net_cash_flow = calculate_transaction_costs(
            "buy", 100, 10.0
        )
        
        self.assertEqual(gross, 1000.0)
        self.assertEqual(commission, 5.0)  # 1000 * 0.0003 = 0.3 < 5, so min 5
        self.assertEqual(stamp_duty, 0.0)  # no stamp duty on buy
        self.assertEqual(transfer_fee, 0.0)
        self.assertEqual(total_fee, 5.0)
        self.assertEqual(net_cash_flow, -1005.0)  # -(1000 + 5)

    def test_buy_commission_above_minimum(self):
        """
        Buy order with large amount pays commission above minimum.
        """
        gross, commission, stamp_duty, transfer_fee, total_fee, net_cash_flow = calculate_transaction_costs(
            "buy", 10000, 10.0
        )
        
        self.assertEqual(gross, 100000.0)
        self.assertAlmostEqual(commission, 30.0, places=2)  # 100000 * 0.0003 = 30 > 5
        self.assertEqual(stamp_duty, 0.0)
        self.assertEqual(transfer_fee, 0.0)
        self.assertAlmostEqual(total_fee, 30.0, places=2)
        self.assertAlmostEqual(net_cash_flow, -100030.0, places=2)

    def test_sell_commission_and_stamp_duty(self):
        """
        Sell order pays commission and stamp duty.
        """
        gross, commission, stamp_duty, transfer_fee, total_fee, net_cash_flow = calculate_transaction_costs(
            "sell", 1000, 12.0
        )
        
        self.assertEqual(gross, 12000.0)
        self.assertEqual(commission, 5.0)  # 12000 * 0.0003 = 3.6 < 5, so min 5
        self.assertEqual(stamp_duty, 12.0)  # 12000 * 0.001 = 12
        self.assertEqual(transfer_fee, 0.0)
        self.assertEqual(total_fee, 17.0)
        self.assertEqual(net_cash_flow, 11983.0)  # 12000 - 17

    def test_stamp_duty_only_on_sell(self):
        """
        Stamp duty is only charged on sell, not buy.
        """
        _, _, buy_stamp, _, _, _ = calculate_transaction_costs("buy", 1000, 10.0)
        _, _, sell_stamp, _, _, _ = calculate_transaction_costs("sell", 1000, 10.0)
        
        self.assertEqual(buy_stamp, 0.0)
        self.assertGreater(sell_stamp, 0.0)

    def test_commission_rounds_to_minimum(self):
        """
        Very small trades pay minimum commission regardless of amount.
        """
        # 100 shares * 1 RMB = 100 RMB, commission = 0.03 < 5
        _, commission, _, _, _, _ = calculate_transaction_costs("buy", 100, 1.0)
        self.assertEqual(commission, 5.0)

    def test_zero_commission_rate(self):
        """
        Zero commission rate still enforces minimum commission.
        """
        _, commission, _, _, _, _ = calculate_transaction_costs(
            "buy", 1000, 10.0, commission_rate=0.0, min_commission=5.0
        )
        self.assertEqual(commission, 5.0)

    def test_zero_minimum_commission(self):
        """
        Zero minimum commission allows very small commission amounts.
        """
        _, commission, _, _, _, _ = calculate_transaction_costs(
            "buy", 100, 10.0, commission_rate=0.0003, min_commission=0.0
        )
        self.assertEqual(commission, 0.3)  # 1000 * 0.0003

    def test_transfer_fee_when_enabled(self):
        """
        Transfer fee is charged when transfer_fee_rate > 0.
        """
        gross, commission, stamp_duty, transfer_fee, total_fee, net_cash_flow = calculate_transaction_costs(
            "buy", 10000, 10.0, transfer_fee_rate=0.00002
        )
        
        self.assertAlmostEqual(transfer_fee, 2.0, places=2)  # 100000 * 0.00002
        self.assertAlmostEqual(total_fee, 32.0, places=2)  # 30 (commission) + 0 (stamp) + 2 (transfer)
        self.assertAlmostEqual(net_cash_flow, -100032.0, places=2)

    def test_calculate_total_cash_required(self):
        """
        Total cash required includes gross amount and commission.
        """
        total = calculate_total_cash_required(100, 10.0)
        self.assertEqual(total, 1005.0)  # 1000 + 5 (min commission)
        
        total = calculate_total_cash_required(10000, 10.0)
        self.assertAlmostEqual(total, 100030.0, places=2)  # 100000 + 30 (commission)

    def test_calculate_affordable_quantity_with_sufficient_capital(self):
        """
        Affordable quantity calculation with sufficient capital.
        """
        # 10000 RMB can afford ~990 shares at 10 RMB
        # 9900 RMB + commission(9900*0.0003=2.97->5) = 9905
        qty = calculate_affordable_quantity(10000.0, 10.0)
        self.assertGreater(qty, 0)
        self.assertEqual(qty % 100, 0)  # must be lot-sized
        
        # Verify it's actually affordable
        required = calculate_total_cash_required(qty, 10.0)
        self.assertLessEqual(required, 10000.0)

    def test_calculate_affordable_quantity_with_insufficient_capital(self):
        """
        Affordable quantity returns 0 when capital insufficient.
        """
        # 5 RMB can only cover minimum commission, cannot buy any shares
        qty = calculate_affordable_quantity(5.0, 10.0)
        self.assertEqual(qty, 0)
        
        # 100 RMB cannot afford 100 shares at 10 RMB (need 1005)
        qty = calculate_affordable_quantity(100.0, 10.0)
        self.assertEqual(qty, 0)

    def test_calculate_affordable_quantity_at_boundary(self):
        """
        Affordable quantity at capital boundary.
        """
        # Exactly 1005 RMB can afford 100 shares at 10 RMB
        qty = calculate_affordable_quantity(1005.0, 10.0)
        self.assertEqual(qty, 100)
        
        # Slightly less cannot afford
        qty = calculate_affordable_quantity(1004.0, 10.0)
        self.assertEqual(qty, 0)


class TestTransactionCostsCentRounding(unittest.TestCase):
    def test_half_up_cent_rounding_is_opt_in_for_sell_commission(self):
        legacy = calculate_transaction_costs(
            "sell", 100, 167.500, 0.0003, 5.0, 0.0, 0.0
        )
        settled = calculate_transaction_costs(
            "sell", 100, 167.500, 0.0003, 5.0, 0.0, 0.0,
            round_to_cents=True,
        )

        self.assertAlmostEqual(legacy[1], 5.025)
        self.assertAlmostEqual(legacy[5], 16744.975)
        self.assertEqual(settled, (16750.0, 5.03, 0.0, 0.0, 5.03, 16744.97))

    def test_cent_rounding_uses_rounded_gross_and_commission_for_buy_debit(self):
        settled = calculate_transaction_costs(
            "buy", 100, 167.466, 0.0003, 5.0, 0.0, 0.0,
            round_to_cents=True,
        )

        self.assertEqual(settled, (16746.60, 5.02, 0.0, 0.0, 5.02, -16751.62))

    def test_cent_rounding_sums_individually_rounded_sell_fees(self):
        settled = calculate_transaction_costs(
            "sell", 1000, 16.675, 0.0006, 10.0, 0.001, 0.00002,
            round_to_cents=True,
        )

        self.assertEqual(settled, (16675.0, 10.01, 16.68, 0.33, 27.02, 16647.98))
        self.assertEqual(
            Decimal(str(settled[4])),
            sum((Decimal(str(fee)) for fee in settled[1:4]), Decimal("0.00")),
        )
        self.assertEqual(
            Decimal(str(settled[5])),
            Decimal(str(settled[0])) - Decimal(str(settled[4])),
        )

    def test_cent_rounded_buy_cash_helpers_respect_the_cent_boundary(self):
        required = calculate_total_cash_required(
            100, 167.466, 0.0003, 5.0, round_to_cents=True
        )
        affordable_at_boundary = calculate_affordable_quantity(
            16751.62, 167.466, 0.0003, 5.0, 100, round_to_cents=True
        )
        unaffordable_below_boundary = calculate_affordable_quantity(
            16751.61, 167.466, 0.0003, 5.0, 100, round_to_cents=True
        )

        self.assertEqual(required, 16751.62)
        self.assertEqual(affordable_at_boundary, 100)
        self.assertEqual(unaffordable_below_boundary, 0)


if __name__ == "__main__":
    unittest.main()
