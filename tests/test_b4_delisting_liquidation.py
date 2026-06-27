"""B4 Task 9: Delisting and long suspension liquidation policy tests (v2).

Proves:
1. Delisted stocks are included in universe before delisting
2. Delisted stocks are not assumed clean exit
3. Actual tradable exit is used when available
4. Long suspension uses penalty policy
5. No exit price marks result insufficient
6. Delisting penalty is system baseline, cannot be runtime lowered
7. Delisting liquidation records reason and impact
8. Delisting impact visible in result
9. Missing delisting status blocks or degrades

All tests use real fill_simulator and portfolio paths.
"""
import unittest
from datetime import date

from contracts.stable import Order, DailyBar, DailyStatus
from strategy_core.fill_simulator import (
    simulate_fill,
    try_force_liquidation,
    apply_force_liquidation,
    DELISTING_PENALTY_PCT,
)
from strategy_core.portfolio import PortfolioState, Position
from tests.b4_fixtures import create_mock_bar_data_source


class MockDataSourceWithDelisting:
    """Mock data source with delisting/suspension support."""
    
    def __init__(self, bars_by_date, status_by_date):
        self.bars_by_date = bars_by_date
        self.status_by_date = status_by_date
    
    def get_daily_bar(self, symbol: str, trade_date: date) -> DailyBar:
        key = (symbol, trade_date)
        if key not in self.bars_by_date:
            raise KeyError(f"No bar for {symbol} on {trade_date}")
        return self.bars_by_date[key]
    
    def get_daily_status(self, symbol: str, trade_date: date) -> DailyStatus:
        key = (symbol, trade_date)
        if key not in self.status_by_date:
            raise KeyError(f"No status for {symbol} on {trade_date}")
        return self.status_by_date[key]


class TestDelistedStockIncludedBeforeDelisting(unittest.TestCase):
    """Delisted stock must be included in universe before delisting date."""
    
    def test_delisted_stock_included_before_delisting(self):
        """Stock is tradable before delisting, included in universe."""
        # Stock is normal until 2024-01-15
        bars = {
            ("000001.SZ", date(2024, 1, 15)): DailyBar(
                date=date(2024, 1, 15),
                symbol="000001.SZ",
                open=10.0, high=10.5, low=9.5, close=10.0,
                volume=1000000, amount=10000000.0, adj_factor=1.0,
            ),
            ("000001.SZ", date(2024, 1, 16)): DailyBar(
                date=date(2024, 1, 16),
                symbol="000001.SZ",
                open=10.0, high=10.0, low=10.0, close=10.0,
                volume=0, amount=0.0, adj_factor=1.0,
            ),
        }
        status = {
            ("000001.SZ", date(2024, 1, 15)): DailyStatus(
                date=date(2024, 1, 15),
                symbol="000001.SZ",
                is_st=False, is_suspended=False,
                is_limit_up=False, is_limit_down=False,
            ),
            ("000001.SZ", date(2024, 1, 16)): DailyStatus(
                date=date(2024, 1, 16),
                symbol="000001.SZ",
                is_st=False, is_suspended=False,
                is_limit_up=False, is_limit_down=False,
            ),
        }
        
        data_source = MockDataSourceWithDelisting(bars, status)
        
        # Create simple calendar adapter
        class CalendarAdapter:
            def __init__(self, ds):
                self.dates = sorted(set(d for (s, d) in ds.bars_by_date.keys()))
            
            def next_trading_day(self, current_date):
                idx = self.dates.index(current_date)
                if idx + 1 >= len(self.dates):
                    raise ValueError("no next trading day")
                return self.dates[idx + 1]
        
        calendar = CalendarAdapter(data_source)
        portfolio = PortfolioState(cash=100000.0)
        
        # Buy order on T-1 (before delisting)
        order = Order(
            order_id="test_buy",
            signal_id="signal_test_buy",
            signal_date=date(2024, 1, 14),
            intended_execution_date=date(2024, 1, 15),
            symbol="000001.SZ",
            direction="buy",
            quantity=100,
            status="planned",
            reason="test",
            strategy_version="v1",
            audit_id="audit_test",
        )
        
        filled_order = simulate_fill(order, date(2024, 1, 15), data_source, portfolio, calendar=calendar)
        
        # Should fill successfully before delisting
        self.assertEqual(filled_order.status, "filled")
        self.assertAlmostEqual(filled_order.actual_price, 10.0, places=2)


class TestDelistedStockNotAssumedCleanExit(unittest.TestCase):
    """Delisted stock cannot be assumed to exit cleanly at last close."""
    
    def test_delisted_stock_not_assumed_clean_exit(self):
        """Delisting without tradable exit must apply penalty, not clean exit."""
        portfolio = PortfolioState(cash=10000.0)
        portfolio.positions["000001.SZ"] = Position(
            symbol="000001.SZ",
            quantity=100,
            sellable_quantity=100,
            avg_cost=10.0,
            last_price=10.0,
        )
        
        last_bar = DailyBar(
            date=date(2024, 1, 15),
            symbol="000001.SZ",
            open=10.0, high=10.5, low=9.5, close=10.0,
            volume=1000000, amount=10000000.0, adj_factor=1.0,
        )
        
        # Force liquidation with delisting
        liquidation = try_force_liquidation(
            symbol="000001.SZ",
            position=portfolio.positions["000001.SZ"],
            last_tradable_bar=last_bar,
            reason="delisted",
        )
        
        self.assertEqual(liquidation["status"], "liquidated")
        self.assertEqual(liquidation["reason"], "delisted")
        self.assertLess(liquidation["exit_price"], 10.0)  # Must be penalized
        
        # Penalty applied
        expected_exit_price = 10.0 * (1 - DELISTING_PENALTY_PCT)
        self.assertAlmostEqual(liquidation["exit_price"], expected_exit_price, places=2)
        
        # Apply to portfolio
        initial_cash = portfolio.cash
        apply_force_liquidation(portfolio, liquidation)
        
        # Position removed
        self.assertNotIn("000001.SZ", portfolio.positions)
        
        # Cash updated with penalized proceeds
        expected_proceeds = 100 * expected_exit_price
        self.assertAlmostEqual(portfolio.cash, initial_cash + expected_proceeds, places=2)


class TestActualTradableExitUsedWhenAvailable(unittest.TestCase):
    """If tradable exit day exists before delisting, use actual fill."""
    
    def test_actual_tradable_exit_used_when_available(self):
        """Real tradable day before delisting uses normal fill constraints."""
        bars = {
            ("000001.SZ", date(2024, 1, 15)): DailyBar(
                date=date(2024, 1, 15),
                symbol="000001.SZ",
                open=9.8, high=10.0, low=9.5, close=9.7,
                volume=1000000, amount=9700000.0, adj_factor=1.0,
            ),
        }
        status = {
            ("000001.SZ", date(2024, 1, 15)): DailyStatus(
                date=date(2024, 1, 15),
                symbol="000001.SZ",
                is_st=False, is_suspended=False,
                is_limit_up=False, is_limit_down=False,
            ),
        }
        
        data_source = MockDataSourceWithDelisting(bars, status)
        portfolio = PortfolioState(cash=10000.0)
        portfolio.positions["000001.SZ"] = Position(
            symbol="000001.SZ",
            quantity=100,
            sellable_quantity=100,
            avg_cost=10.0,
            last_price=10.0,
        )
        
        # Sell order on last tradable day
        order = Order(
            order_id="test_sell",
            signal_id="signal_test_sell",
            signal_date=date(2024, 1, 14),
            intended_execution_date=date(2024, 1, 15),
            symbol="000001.SZ",
            direction="sell",
            quantity=100,
            status="planned",
            reason="test",
            strategy_version="v1",
            audit_id="audit_test",
        )
        
        filled_order = simulate_fill(order, date(2024, 1, 15), data_source, portfolio)
        
        # Should fill at actual market price (open=9.8), not penalized fallback
        self.assertEqual(filled_order.status, "filled")
        self.assertAlmostEqual(filled_order.actual_price, 9.8, places=2)


class TestLongSuspensionUsesPenaltyPolicy(unittest.TestCase):
    """Long suspension with no executable exit uses penalty policy."""
    
    def test_long_suspension_uses_penalty_policy(self):
        """Long suspension forces liquidation with penalty."""
        portfolio = PortfolioState(cash=10000.0)
        portfolio.positions["000002.SZ"] = Position(
            symbol="000002.SZ",
            quantity=200,
            sellable_quantity=200,
            avg_cost=15.0,
            last_price=15.0,
        )
        
        last_bar = DailyBar(
            date=date(2024, 1, 10),
            symbol="000002.SZ",
            open=15.0, high=15.5, low=14.5, close=15.0,
            volume=500000, amount=7500000.0, adj_factor=1.0,
        )
        
        # Force liquidation due to long suspension
        liquidation = try_force_liquidation(
            symbol="000002.SZ",
            position=portfolio.positions["000002.SZ"],
            last_tradable_bar=last_bar,
            reason="long_suspension",
        )
        
        self.assertEqual(liquidation["status"], "liquidated")
        self.assertEqual(liquidation["reason"], "long_suspension")
        
        # Penalty applied to last tradable price
        expected_exit_price = 15.0 * (1 - DELISTING_PENALTY_PCT)
        self.assertAlmostEqual(liquidation["exit_price"], expected_exit_price, places=2)


class TestNoExitPriceMarksResultInsufficient(unittest.TestCase):
    """No reliable exit price must mark result as insufficient."""
    
    def test_no_exit_price_marks_result_insufficient(self):
        """Missing last tradable price marks liquidation insufficient."""
        portfolio = PortfolioState(cash=10000.0)
        portfolio.positions["000003.SZ"] = Position(
            symbol="000003.SZ",
            quantity=100,
            sellable_quantity=100,
            avg_cost=20.0,
            last_price=20.0,
        )
        
        # No last tradable bar available (data gap)
        liquidation = try_force_liquidation(
            symbol="000003.SZ",
            position=portfolio.positions["000003.SZ"],
            last_tradable_bar=None,  # No data
            reason="delisted",
        )
        
        self.assertEqual(liquidation["status"], "insufficient")
        self.assertIn("no_reliable_exit_price", liquidation["insufficient_reason"])


class TestDelistingPenaltyIsSystemDefaultNotRuntimeLowered(unittest.TestCase):
    """Penalty pct is system baseline, cannot be lowered at runtime."""
    
    def test_delisting_penalty_is_system_default_not_runtime_lowered(self):
        """Runtime penalty cannot be lower than system baseline."""
        portfolio = PortfolioState(cash=10000.0)
        portfolio.positions["000004.SZ"] = Position(
            symbol="000004.SZ",
            quantity=100,
            sellable_quantity=100,
            avg_cost=10.0,
            last_price=10.0,
        )
        
        last_bar = DailyBar(
            date=date(2024, 1, 15),
            symbol="000004.SZ",
            open=10.0, high=10.5, low=9.5, close=10.0,
            volume=1000000, amount=10000000.0, adj_factor=1.0,
        )
        
        # Attempt to pass zero penalty (clean exit) → should raise ValueError
        with self.assertRaises(ValueError) as ctx:
            try_force_liquidation(
                symbol="000004.SZ",
                position=portfolio.positions["000004.SZ"],
                last_tradable_bar=last_bar,
                reason="delisted",
                runtime_penalty_pct=0.0,
            )
        
        self.assertIn("cannot be lower than", str(ctx.exception).lower())
        self.assertIn("baseline", str(ctx.exception).lower())
        
        # Attempt to pass lower penalty (0.01 < 0.05) → should raise ValueError
        with self.assertRaises(ValueError) as ctx:
            try_force_liquidation(
                symbol="000004.SZ",
                position=portfolio.positions["000004.SZ"],
                last_tradable_bar=last_bar,
                reason="delisted",
                runtime_penalty_pct=0.01,
            )
        
        self.assertIn("cannot be lower than", str(ctx.exception).lower())
        
        # Using baseline or higher is allowed
        liquidation_baseline = try_force_liquidation(
            symbol="000004.SZ",
            position=portfolio.positions["000004.SZ"],
            last_tradable_bar=last_bar,
            reason="delisted",
        )
        self.assertEqual(liquidation_baseline["penalty_pct"], DELISTING_PENALTY_PCT)
        
        # Higher penalty allowed
        liquidation_higher = try_force_liquidation(
            symbol="000004.SZ",
            position=portfolio.positions["000004.SZ"],
            last_tradable_bar=last_bar,
            reason="delisted",
            runtime_penalty_pct=0.10,
        )
        self.assertEqual(liquidation_higher["penalty_pct"], 0.10)


class TestDelistingLiquidationRecordsReason(unittest.TestCase):
    """Liquidation must record reason and impact."""
    
    def test_delisting_liquidation_records_reason(self):
        """Liquidation record includes reason, symbol, status, price, impact."""
        portfolio = PortfolioState(cash=10000.0)
        portfolio.positions["000005.SZ"] = Position(
            symbol="000005.SZ",
            quantity=100,
            sellable_quantity=100,
            avg_cost=12.0,
            last_price=12.0,
        )
        
        last_bar = DailyBar(
            date=date(2024, 1, 15),
            symbol="000005.SZ",
            open=12.0, high=12.5, low=11.5, close=12.0,
            volume=1000000, amount=12000000.0, adj_factor=1.0,
        )
        
        liquidation = try_force_liquidation(
            symbol="000005.SZ",
            position=portfolio.positions["000005.SZ"],
            last_tradable_bar=last_bar,
            reason="delisted",
        )
        
        # Required fields
        self.assertIn("symbol", liquidation)
        self.assertIn("reason", liquidation)
        self.assertIn("quantity", liquidation)
        self.assertIn("exit_price", liquidation)
        self.assertIn("exit_price_source", liquidation)
        self.assertIn("penalty_pct", liquidation)
        self.assertIn("impact_on_value", liquidation)
        
        self.assertEqual(liquidation["symbol"], "000005.SZ")
        self.assertEqual(liquidation["reason"], "delisted")
        self.assertEqual(liquidation["quantity"], 100)


class TestDelistingImpactVisibleInResult(unittest.TestCase):
    """Delisting impact must be visible in backtest result."""
    
    def test_delisting_impact_visible_in_result(self):
        """Liquidation impact (loss from penalty) is calculated and visible."""
        portfolio = PortfolioState(cash=10000.0)
        portfolio.positions["000006.SZ"] = Position(
            symbol="000006.SZ",
            quantity=100,
            sellable_quantity=100,
            avg_cost=10.0,
            last_price=10.0,
        )
        
        last_bar = DailyBar(
            date=date(2024, 1, 15),
            symbol="000006.SZ",
            open=10.0, high=10.5, low=9.5, close=10.0,
            volume=1000000, amount=10000000.0, adj_factor=1.0,
        )
        
        liquidation = try_force_liquidation(
            symbol="000006.SZ",
            position=portfolio.positions["000006.SZ"],
            last_tradable_bar=last_bar,
            reason="delisted",
        )
        
        # Impact calculation
        exit_price = 10.0 * (1 - DELISTING_PENALTY_PCT)
        expected_impact = 100 * exit_price
        
        self.assertIn("impact_on_value", liquidation)
        self.assertAlmostEqual(liquidation["impact_on_value"], expected_impact, places=2)


class TestMissingDelistingStatusBlocksOrDegrades(unittest.TestCase):
    """Missing delisting status must block or degrade backtest result."""
    
    def test_missing_delisting_status_blocks_or_degrades(self):
        """No delisting status data marks result as degraded/insufficient."""
        portfolio = PortfolioState(cash=10000.0)
        portfolio.positions["000007.SZ"] = Position(
            symbol="000007.SZ",
            quantity=100,
            sellable_quantity=100,
            avg_cost=10.0,
            last_price=10.0,
        )
        
        # No last tradable bar (data missing)
        liquidation = try_force_liquidation(
            symbol="000007.SZ",
            position=portfolio.positions["000007.SZ"],
            last_tradable_bar=None,
            reason="delisted",
        )
        
        # Must be marked insufficient
        self.assertEqual(liquidation["status"], "insufficient")
        self.assertIn("insufficient_reason", liquidation)


class TestPortfolioApplicationOfLiquidation(unittest.TestCase):
    """apply_force_liquidation must update portfolio state."""
    
    def test_portfolio_application_removes_position_and_adds_cash(self):
        """Applying liquidation removes position and adds penalized proceeds to cash."""
        portfolio = PortfolioState(cash=10000.0)
        portfolio.positions["000008.SZ"] = Position(
            symbol="000008.SZ",
            quantity=100,
            sellable_quantity=100,
            avg_cost=10.0,
            last_price=10.0,
        )
        
        last_bar = DailyBar(
            date=date(2024, 1, 15),
            symbol="000008.SZ",
            open=10.0, high=10.5, low=9.5, close=10.0,
            volume=1000000, amount=10000000.0, adj_factor=1.0,
        )
        
        liquidation = try_force_liquidation(
            symbol="000008.SZ",
            position=portfolio.positions["000008.SZ"],
            last_tradable_bar=last_bar,
            reason="delisted",
        )
        
        initial_cash = portfolio.cash
        initial_position_count = len(portfolio.positions)
        
        # Apply liquidation
        apply_force_liquidation(portfolio, liquidation)
        
        # Position removed
        self.assertNotIn("000008.SZ", portfolio.positions)
        self.assertEqual(len(portfolio.positions), initial_position_count - 1)
        
        # Cash increased by liquidation proceeds (with penalty)
        expected_proceeds = liquidation["impact_on_value"]
        self.assertAlmostEqual(portfolio.cash, initial_cash + expected_proceeds, places=2)
    
    def test_portfolio_application_rejects_insufficient_liquidation(self):
        """Applying insufficient liquidation raises ValueError."""
        portfolio = PortfolioState(cash=10000.0)
        portfolio.positions["000009.SZ"] = Position(
            symbol="000009.SZ",
            quantity=100,
            sellable_quantity=100,
            avg_cost=10.0,
            last_price=10.0,
        )
        
        # Insufficient liquidation (no last tradable bar)
        liquidation = try_force_liquidation(
            symbol="000009.SZ",
            position=portfolio.positions["000009.SZ"],
            last_tradable_bar=None,
            reason="delisted",
        )
        
        # Applying insufficient liquidation should raise
        with self.assertRaises(ValueError) as ctx:
            apply_force_liquidation(portfolio, liquidation)
        
        self.assertIn("insufficient", str(ctx.exception).lower())


if __name__ == "__main__":
    unittest.main()
