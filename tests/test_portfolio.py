import unittest

from strategy_core.portfolio import Position, PortfolioState


class TestPortfolio(unittest.TestCase):
    def test_position_calculates_market_value_and_unrealized_pnl(self):
        """
        Position correctly calculates market value and unrealized PnL.
        """
        pos = Position(symbol="000001.SZ", quantity=100, sellable_quantity=100, avg_cost=10.0, last_price=12.0)
        
        self.assertEqual(pos.market_value(), 1200.0)
        self.assertEqual(pos.unrealized_pnl(), 200.0)

    def test_portfolio_state_tracks_cash_and_positions(self):
        """
        PortfolioState correctly tracks cash and positions.
        """
        portfolio = PortfolioState(cash=10000.0)
        portfolio.positions["000001.SZ"] = Position(
            symbol="000001.SZ", quantity=100, sellable_quantity=100, avg_cost=10.0, last_price=12.0
        )
        
        self.assertEqual(portfolio.cash, 10000.0)
        self.assertEqual(len(portfolio.positions), 1)
        self.assertIn("000001.SZ", portfolio.positions)

    def test_portfolio_state_calculates_total_value(self):
        """
        PortfolioState correctly calculates market value and total value.
        """
        portfolio = PortfolioState(cash=5000.0)
        portfolio.positions["000001.SZ"] = Position(
            symbol="000001.SZ", quantity=100, sellable_quantity=100, avg_cost=10.0, last_price=12.0
        )
        portfolio.positions["000002.SZ"] = Position(
            symbol="000002.SZ", quantity=200, sellable_quantity=200, avg_cost=15.0, last_price=18.0
        )
        
        expected_market_value = 100 * 12.0 + 200 * 18.0
        self.assertEqual(portfolio.market_value(), expected_market_value)
        self.assertEqual(portfolio.total_value(), 5000.0 + expected_market_value)

    def test_portfolio_update_position_prices(self):
        """
        PortfolioState correctly updates position prices.
        """
        portfolio = PortfolioState(cash=5000.0)
        portfolio.positions["000001.SZ"] = Position(
            symbol="000001.SZ", quantity=100, sellable_quantity=100, avg_cost=10.0, last_price=12.0
        )
        portfolio.positions["000002.SZ"] = Position(
            symbol="000002.SZ", quantity=200, sellable_quantity=200, avg_cost=15.0, last_price=18.0
        )
        
        new_prices = {"000001.SZ": 13.0, "000002.SZ": 17.0}
        portfolio.update_position_prices(new_prices)
        
        self.assertEqual(portfolio.positions["000001.SZ"].last_price, 13.0)
        self.assertEqual(portfolio.positions["000002.SZ"].last_price, 17.0)

    def test_portfolio_available_capital_returns_cash(self):
        """
        available_capital returns current cash.
        """
        portfolio = PortfolioState(cash=8000.0)
        self.assertEqual(portfolio.available_capital(), 8000.0)

    def test_portfolio_market_value_zero_when_no_positions(self):
        """
        market_value returns 0 when there are no positions.
        """
        portfolio = PortfolioState(cash=10000.0)
        self.assertEqual(portfolio.market_value(), 0.0)
        self.assertEqual(portfolio.total_value(), 10000.0)


if __name__ == "__main__":
    unittest.main()
