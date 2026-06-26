"""
Test Exit Rules: breakthrough, holding_days, stop_loss_pct
"""
from datetime import date
from pathlib import Path
import unittest

from backend.app.contracts import Signal, DailyBar
from backend.app.fixed_fixture import FixedFixtureDataSource
from strategy_core.signals import (
    generate_exit_signals,
    _evaluate_breakthrough_exit,
    _evaluate_holding_days_exit,
    _evaluate_stop_loss_pct_exit,
)
from strategy_core.portfolio import Position, FrozenLot
from backend.app.contracts import StrategyConfig


class TestBreakthroughExit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data_source = FixedFixtureDataSource()
    
    def test_breakthrough_exit_triggers_when_close_below_low_Nd(self):
        """Breakthrough exit should trigger when close < low_Nd."""
        rule = {
            "type": "breakthrough",
            "direction": "breakdown",
            "field": "close",
            "benchmark": "low_5d",
            "operator": "<"
        }
        
        bars = self.data_source.get_daily_bars("000001.SZ")
        
        # Find a date where close < recent 5-day low
        for i in range(5, min(len(bars), 50)):
            trade_date = bars[i].date
            recent_5d = bars[i-5:i]
            low_5d = min(bar.low for bar in recent_5d)
            
            if bars[i].close < low_5d:
                # Should trigger
                result = _evaluate_breakthrough_exit(rule, bars, trade_date)
                self.assertTrue(result, f"Should trigger on {trade_date}: close={bars[i].close:.2f} < low_5d={low_5d:.2f}")
                return
        
        self.skipTest("No suitable date found in fixture data")
    
    def test_breakthrough_exit_does_not_trigger_when_close_above_low_Nd(self):
        """Breakthrough exit should not trigger when close >= low_Nd."""
        rule = {
            "type": "breakthrough",
            "direction": "breakdown",
            "field": "close",
            "benchmark": "low_5d",
            "operator": "<"
        }
        
        bars = self.data_source.get_daily_bars("000001.SZ")
        
        # Find a date where close >= recent 5-day low
        for i in range(5, min(len(bars), 50)):
            trade_date = bars[i].date
            recent_5d = bars[i-5:i]
            low_5d = min(bar.low for bar in recent_5d)
            
            if bars[i].close >= low_5d:
                # Should not trigger
                result = _evaluate_breakthrough_exit(rule, bars, trade_date)
                self.assertFalse(result, f"Should not trigger on {trade_date}: close={bars[i].close:.2f} >= low_5d={low_5d:.2f}")
                return
        
        self.skipTest("No suitable date found in fixture data")
    
    def test_breakthrough_exit_insufficient_data_returns_false(self):
        """Breakthrough exit should return False when insufficient data."""
        rule = {
            "type": "breakthrough",
            "direction": "breakdown",
            "field": "close",
            "benchmark": "low_20d",
            "operator": "<"
        }
        
        bars = self.data_source.get_daily_bars("000001.SZ")
        
        # Use first few days (insufficient for 20-day window)
        if len(bars) > 5:
            trade_date = bars[5].date
            result = _evaluate_breakthrough_exit(rule, bars, trade_date)
            self.assertFalse(result)


class TestHoldingDaysExit(unittest.TestCase):
    def test_holding_days_exit_triggers_when_max_reached(self):
        """Holding days exit should trigger when holding >= max_holding_days."""
        rule = {
            "type": "holding_days",
            "max_holding_days": 10
        }
        
        # Create position with proper frozen lot
        # Note: holding_days evaluation uses unlock_date - 1 as buy_date (T+1 rule)
        frozen_lot = FrozenLot(
            quantity=100,
            unlock_date=date(2024, 1, 2)  # Bought on 2024-01-01
        )
        
        position = Position(
            symbol="000001.SZ",
            quantity=100,
            sellable_quantity=0,
            avg_cost=10.0,
            last_price=12.0,
            frozen_lots=[frozen_lot]
        )
        
        trade_date = date(2024, 1, 11)  # 10 days after unlock (11 days after buy)
        result = _evaluate_holding_days_exit(rule, position, trade_date)
        self.assertTrue(result)
    
    def test_holding_days_exit_does_not_trigger_when_below_max(self):
        """Holding days exit should not trigger when holding < max_holding_days."""
        rule = {
            "type": "holding_days",
            "max_holding_days": 10
        }
        
        frozen_lot = FrozenLot(
            quantity=100,
            unlock_date=date(2024, 1, 2)
        )
        
        position = Position(
            symbol="000001.SZ",
            quantity=100,
            sellable_quantity=0,
            avg_cost=10.0,
            last_price=12.0,
            frozen_lots=[frozen_lot]
        )
        
        trade_date = date(2024, 1, 9)  # 8 days after unlock
        result = _evaluate_holding_days_exit(rule, position, trade_date)
        self.assertFalse(result)
    
    def test_holding_days_exit_no_frozen_lots_returns_false(self):
        """Holding days exit should return False when no frozen lots."""
        rule = {
            "type": "holding_days",
            "max_holding_days": 10
        }
        
        position = Position(
            symbol="000001.SZ",
            quantity=100,
            sellable_quantity=100,
            avg_cost=10.0,
            last_price=12.0,
            frozen_lots=[]
        )
        
        trade_date = date(2024, 1, 11)
        result = _evaluate_holding_days_exit(rule, position, trade_date)
        self.assertFalse(result)

    def test_holding_days_exit_triggers_after_t1_lot_unlocked(self):
        """
        Holding-days exit must still know the buy date after T+1 unlock.

        This protects the full backtest path: frozen_lots are removed when shares
        become sellable, but holding_days still needs a stable holding start.
        """
        rule = {
            "type": "holding_days",
            "max_holding_days": 5
        }

        position = Position(
            symbol="000001.SZ",
            quantity=100,
            sellable_quantity=100,
            avg_cost=10.0,
            last_price=12.0,
            frozen_lots=[],
            oldest_buy_date=date(2024, 1, 2),
        )

        trade_date = date(2024, 1, 8)
        result = _evaluate_holding_days_exit(rule, position, trade_date)
        self.assertTrue(result)


class TestStopLossPctExit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data_source = FixedFixtureDataSource()
    
    def test_stop_loss_pct_exit_triggers_when_loss_exceeds_threshold(self):
        """Stop loss exit should trigger when loss >= threshold."""
        rule = {
            "type": "stop_loss_pct",
            "threshold": -0.08,  # -8%
            "price_field": "close"
        }
        
        # Mock position with avg_cost = 10.0
        position = Position(
            symbol="000001.SZ",
            quantity=100,
            sellable_quantity=100,
            avg_cost=10.0,
            last_price=9.0,  # -10% loss
            frozen_lots=[]
        )
        
        bars = self.data_source.get_daily_bars("000001.SZ")
        
        if len(bars) > 10:
            trade_date = bars[10].date
            
            # Mock bars with current close = 9.0 (10% loss from avg_cost=10.0)
            mock_bars = bars[:10] + [
                DailyBar(
                    date=trade_date,
                    symbol="000001.SZ",
                    open=9.0,
                    high=9.5,
                    low=8.8,
                    close=9.0,
                    volume=1000000,
                    amount=9000000.0,
                    adj_factor=1.0
                )
            ]
            
            result = _evaluate_stop_loss_pct_exit(rule, mock_bars, trade_date, position)
            self.assertTrue(result)
    
    def test_stop_loss_pct_exit_does_not_trigger_when_loss_below_threshold(self):
        """Stop loss exit should not trigger when loss < threshold."""
        rule = {
            "type": "stop_loss_pct",
            "threshold": -0.08,  # -8%
            "price_field": "close"
        }
        
        position = Position(
            symbol="000001.SZ",
            quantity=100,
            sellable_quantity=100,
            avg_cost=10.0,
            last_price=9.5,  # -5% loss
            frozen_lots=[]
        )
        
        bars = self.data_source.get_daily_bars("000001.SZ")
        
        if len(bars) > 10:
            trade_date = bars[10].date
            
            mock_bars = bars[:10] + [
                DailyBar(
                    date=trade_date,
                    symbol="000001.SZ",
                    open=9.5,
                    high=9.8,
                    low=9.3,
                    close=9.5,
                    volume=1000000,
                    amount=9500000.0,
                    adj_factor=1.0
                )
            ]
            
            result = _evaluate_stop_loss_pct_exit(rule, mock_bars, trade_date, position)
            self.assertFalse(result)
    
    def test_stop_loss_pct_exit_boundary_at_threshold(self):
        """Stop loss exit should trigger when loss exactly at threshold."""
        rule = {
            "type": "stop_loss_pct",
            "threshold": -0.08,  # -8%
            "price_field": "close"
        }
        
        position = Position(
            symbol="000001.SZ",
            quantity=100,
            sellable_quantity=100,
            avg_cost=10.0,
            last_price=9.2,  # Exactly -8% loss
            frozen_lots=[]
        )
        
        bars = self.data_source.get_daily_bars("000001.SZ")
        
        if len(bars) > 10:
            trade_date = bars[10].date
            
            mock_bars = bars[:10] + [
                DailyBar(
                    date=trade_date,
                    symbol="000001.SZ",
                    open=9.2,
                    high=9.3,
                    low=9.1,
                    close=9.2,
                    volume=1000000,
                    amount=9200000.0,
                    adj_factor=1.0
                )
            ]
            
            result = _evaluate_stop_loss_pct_exit(rule, mock_bars, trade_date, position)
            self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
