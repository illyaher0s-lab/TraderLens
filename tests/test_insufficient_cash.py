"""
Test Insufficient Cash Handling

Regression tests for negative cash bug fix.
"""
import unittest
from datetime import date

from strategy_core.portfolio import PortfolioState, Position
from strategy_core.transaction_costs import calculate_affordable_quantity, calculate_total_cash_required


class TestInsufficientCashHandling(unittest.TestCase):
    def test_calculate_affordable_quantity_with_low_cash(self):
        """calculate_affordable_quantity should return 0 when cash is too low."""
        # Cash too low to afford even 100 shares
        affordable = calculate_affordable_quantity(
            available_cash=500.0,
            price=10.0,
            commission_rate=0.0003,
            min_commission=5.0,
            lot_size=100
        )
        
        self.assertEqual(affordable, 0)
    
    def test_calculate_affordable_quantity_with_sufficient_cash(self):
        """calculate_affordable_quantity should return correct lot-sized quantity."""
        # Cash enough for 400 shares (4 lots)
        affordable = calculate_affordable_quantity(
            available_cash=5000.0,
            price=10.0,
            commission_rate=0.0003,
            min_commission=5.0,
            lot_size=100
        )
        
        # Should be able to afford 4 lots (400 shares)
        self.assertGreaterEqual(affordable, 400)
        self.assertEqual(affordable % 100, 0)  # Lot-sized
        
        # Verify actual cost is within budget
        actual_cost = calculate_total_cash_required(
            affordable, 10.0, 0.0003, 5.0
        )
        self.assertLessEqual(actual_cost, 5000.0)
    
    def test_calculate_affordable_quantity_at_boundary(self):
        """calculate_affordable_quantity should handle boundary cases."""
        # Exactly enough for 100 shares
        # gross = 1000, commission = max(1000*0.0003, 5) = 5, total = 1005
        affordable = calculate_affordable_quantity(
            available_cash=1005.0,
            price=10.0,
            commission_rate=0.0003,
            min_commission=5.0,
            lot_size=100
        )
        
        self.assertEqual(affordable, 100)
    
    def test_portfolio_invariant_rejects_negative_cash(self):
        """Portfolio.validate_invariants() should raise when cash < 0."""
        portfolio = PortfolioState(cash=-100.0, positions={})
        
        with self.assertRaises(ValueError) as ctx:
            portfolio.validate_invariants()
        
        self.assertIn("cash < 0", str(ctx.exception))
        self.assertIn("Margin trading is not supported", str(ctx.exception))
    
    def test_portfolio_invariant_accepts_zero_cash(self):
        """Portfolio.validate_invariants() should accept cash = 0."""
        portfolio = PortfolioState(cash=0.0, positions={})
        
        # Should not raise
        portfolio.validate_invariants()
    
    def test_portfolio_invariant_accepts_positive_cash(self):
        """Portfolio.validate_invariants() should accept positive cash."""
        portfolio = PortfolioState(cash=100000.0, positions={})
        
        # Should not raise
        portfolio.validate_invariants()
    
    def test_sequential_cash_consumption(self):
        """Simulated sequential buy orders should reduce cash progressively."""
        portfolio = PortfolioState(cash=10000.0, positions={})
        
        # First buy: 500 shares @ 10.0
        cash_required_1 = calculate_total_cash_required(500, 10.0, 0.0003, 5.0)
        portfolio.cash -= cash_required_1
        
        self.assertGreater(portfolio.cash, 0)
        cash_after_first = portfolio.cash
        
        # Second buy: use remaining cash
        affordable_2 = calculate_affordable_quantity(
            portfolio.cash, 10.0, 0.0003, 5.0, 100
        )
        
        if affordable_2 > 0:
            cash_required_2 = calculate_total_cash_required(affordable_2, 10.0, 0.0003, 5.0)
            portfolio.cash -= cash_required_2
        
        # Portfolio should remain valid
        portfolio.validate_invariants()
        self.assertGreaterEqual(portfolio.cash, 0.0)


if __name__ == "__main__":
    unittest.main()
