"""
Contract Serialization Tests - M2 Stability Validation

Validates that stable contracts can be serialized and deserialized without loss.
Focuses on core backtest artifacts that appear in export files.

Test coverage:
- JSON round-trip (serialize → deserialize = identity)
- Date/datetime format preservation
- Decimal/float precision policy
- Backward compatibility (old vs new import paths)
- Deterministic serialization (stable hashing)

Schema version recording is tested at export level (not per-model).
"""

import unittest
from datetime import date, datetime
from decimal import Decimal
import json

# Test both import paths
from contracts.stable import (
    StrategyConfig,
    Signal,
    Order,
    Trade,
    RoundTrip,
    DailyPortfolioValue,
    BacktestMetrics,
    PrototypeGateResult,
    BacktestResult,
)
from backend.app.contracts import (
    StrategyConfig as OldStrategyConfig,
    Trade as OldTrade,
)
from contracts import SCHEMA_VERSION


class TestJSONRoundTrip(unittest.TestCase):
    """Test that core contracts survive JSON serialization round-trip."""
    
    def test_trade_round_trip(self):
        """Trade: complete transaction record with cost breakdown."""
        original = Trade(
            trade_id="T001",
            order_id="O001",
            symbol="600519.SH",
            direction="buy",
            quantity=100,
            price=150.50,
            trade_date=date(2023, 6, 15),
            gross_amount=15050.0,
            commission=5.0,
            stamp_duty=0.0,
            transfer_fee=0.0,
            total_fee=5.0,
            net_cash_flow=-15055.0,
            cost=-15055.0,
        )
        
        # Serialize to JSON
        json_str = original.model_dump_json()
        
        # Deserialize back
        restored = Trade.model_validate_json(json_str)
        
        # Verify identity
        self.assertEqual(restored.trade_id, original.trade_id)
        self.assertEqual(restored.symbol, original.symbol)
        self.assertEqual(restored.direction, original.direction)
        self.assertEqual(restored.quantity, original.quantity)
        self.assertEqual(restored.price, original.price)
        self.assertEqual(restored.trade_date, original.trade_date)
        self.assertEqual(restored.gross_amount, original.gross_amount)
        self.assertEqual(restored.commission, original.commission)
        self.assertEqual(restored.net_cash_flow, original.net_cash_flow)
    
    def test_round_trip_round_trip(self):
        """RoundTrip: completed buy→sell pair with realized PnL."""
        original = RoundTrip(
            round_trip_id="RT001",
            symbol="600519.SH",
            buy_trade_id="T001",
            buy_date=date(2023, 6, 15),
            buy_price=150.50,
            buy_trade_quantity=100,
            matched_quantity=100,
            buy_cost=15055.0,
            sell_trade_id="T002",
            sell_date=date(2023, 6, 20),
            sell_price=155.00,
            sell_trade_quantity=100,
            sell_proceeds=15484.5,
            realized_pnl=429.5,
            holding_days=5,
        )
        
        json_str = original.model_dump_json()
        restored = RoundTrip.model_validate_json(json_str)
        
        self.assertEqual(restored.symbol, original.symbol)
        self.assertEqual(restored.buy_date, original.buy_date)
        self.assertEqual(restored.sell_date, original.sell_date)
        self.assertEqual(restored.matched_quantity, original.matched_quantity)
        self.assertEqual(restored.realized_pnl, original.realized_pnl)
        self.assertEqual(restored.holding_days, original.holding_days)
    
    def test_daily_portfolio_value_round_trip(self):
        """DailyPortfolioValue: daily portfolio snapshot."""
        original = DailyPortfolioValue(
            date=date(2023, 6, 15),
            cash=50000.0,
            market_value=45000.0,
            total_value=95000.0,
        )
        
        json_str = original.model_dump_json()
        restored = DailyPortfolioValue.model_validate_json(json_str)
        
        self.assertEqual(restored.date, original.date)
        self.assertEqual(restored.cash, original.cash)
        self.assertEqual(restored.market_value, original.market_value)
        self.assertEqual(restored.total_value, original.total_value)
    
    def test_backtest_metrics_round_trip(self):
        """BacktestMetrics: performance summary."""
        original = BacktestMetrics(
            total_return=0.15,
            max_drawdown=-0.08,
            sharpe_ratio=1.25,
            total_trades=50,
            filled_orders=48,
            completed_round_trips=24,
            closed_lot_win_rate=0.625,
            profit_factor=2.5,
            avg_win=500.0,
            avg_loss=-200.0,
            unmatched_sells=0,
        )
        
        json_str = original.model_dump_json()
        restored = BacktestMetrics.model_validate_json(json_str)
        
        self.assertAlmostEqual(restored.total_return, original.total_return, places=6)
        self.assertAlmostEqual(restored.max_drawdown, original.max_drawdown, places=6)
        self.assertAlmostEqual(restored.sharpe_ratio, original.sharpe_ratio, places=6)
        self.assertEqual(restored.total_trades, original.total_trades)
        self.assertAlmostEqual(restored.closed_lot_win_rate, original.closed_lot_win_rate, places=6)
        self.assertAlmostEqual(restored.profit_factor, original.profit_factor, places=6)


class TestDatetimeFormat(unittest.TestCase):
    """Test date/datetime serialization formats."""
    
    def test_date_format_iso(self):
        """Date fields serialize to ISO format (YYYY-MM-DD)."""
        trade = Trade(
            trade_id="T001",
            order_id="O001",
            symbol="600519.SH",
            direction="buy",
            quantity=100,
            price=150.0,
            trade_date=date(2023, 6, 15),
            gross_amount=15000.0,
            commission=5.0,
            stamp_duty=0.0,
            total_fee=5.0,
            net_cash_flow=-15005.0,
            cost=-15005.0,
        )
        
        json_obj = trade.model_dump(mode="json")
        
        # Date serializes to ISO string
        self.assertEqual(json_obj["trade_date"], "2023-06-15")
        
        # Can deserialize back
        restored = Trade.model_validate(json_obj)
        self.assertEqual(restored.trade_date, date(2023, 6, 15))
    
    def test_datetime_format_iso(self):
        """Datetime fields serialize to ISO format with timezone."""
        from contracts.stable import AuditSnapshot
        
        audit = AuditSnapshot(
            created_at=datetime(2023, 6, 15, 12, 30, 45),
            created_by="test_user",
            last_modified_at=datetime(2023, 6, 15, 14, 0, 0),
            config_hash="abc123",
        )
        
        json_obj = audit.model_dump(mode="json")
        
        # Datetime serializes to ISO string
        self.assertIn("2023-06-15T12:30:45", json_obj["created_at"])
        
        # Can deserialize back
        restored = AuditSnapshot.model_validate(json_obj)
        self.assertEqual(restored.created_at, datetime(2023, 6, 15, 12, 30, 45))


class TestDecimalFloatPrecision(unittest.TestCase):
    """Test float precision preservation for financial metrics."""
    
    def test_return_metrics_precision(self):
        """Return/drawdown/sharpe preserve 6 decimal places."""
        metrics = BacktestMetrics(
            total_return=0.123456789,  # Input has 9 decimals
            max_drawdown=-0.087654321,
            sharpe_ratio=1.234567890,
            total_trades=10,
            filled_orders=10,
            completed_round_trips=5,
        )
        
        json_str = metrics.model_dump_json()
        restored = BacktestMetrics.model_validate_json(json_str)
        
        # Should be within 6 decimal places (financial precision)
        self.assertAlmostEqual(restored.total_return, 0.123456789, places=6)
        self.assertAlmostEqual(restored.max_drawdown, -0.087654321, places=6)
        self.assertAlmostEqual(restored.sharpe_ratio, 1.234567890, places=6)
    
    def test_pnl_preserves_cents(self):
        """PnL fields preserve 2 decimal places (cents)."""
        round_trip = RoundTrip(
            round_trip_id="RT001",
            symbol="600519.SH",
            buy_trade_id="T001",
            buy_date=date(2023, 6, 15),
            buy_price=150.55,
            buy_trade_quantity=100,
            matched_quantity=100,
            buy_cost=15060.50,
            sell_trade_id="T002",
            sell_date=date(2023, 6, 20),
            sell_price=155.12,
            sell_trade_quantity=100,
            sell_proceeds=15496.88,
            realized_pnl=436.38,  # Exact cents
            holding_days=5,
        )
        
        json_str = round_trip.model_dump_json()
        restored = RoundTrip.model_validate_json(json_str)
        
        # Should preserve cents (2 decimals)
        self.assertAlmostEqual(restored.buy_cost, 15060.50, places=2)
        self.assertAlmostEqual(restored.sell_proceeds, 15496.88, places=2)
        self.assertAlmostEqual(restored.realized_pnl, 436.38, places=2)


class TestBackwardCompatibility(unittest.TestCase):
    """Test old import path points to new contracts."""
    
    def test_old_import_equals_new_import(self):
        """backend.app.contracts re-exports point to same classes."""
        # StrategyConfig
        self.assertIs(OldStrategyConfig, StrategyConfig)
        
        # Trade
        self.assertIs(OldTrade, Trade)
    
    def test_old_path_creates_same_instance(self):
        """Instances from old path are identical to new path."""
        trade_old = OldTrade(
            trade_id="T001",
            order_id="O001",
            symbol="600519.SH",
            direction="buy",
            quantity=100,
            price=150.0,
            trade_date=date(2023, 6, 15),
            gross_amount=15000.0,
            commission=5.0,
            stamp_duty=0.0,
            total_fee=5.0,
            net_cash_flow=-15005.0,
            cost=-15005.0,
        )
        
        trade_new = Trade(
            trade_id="T001",
            order_id="O001",
            symbol="600519.SH",
            direction="buy",
            quantity=100,
            price=150.0,
            trade_date=date(2023, 6, 15),
            gross_amount=15000.0,
            commission=5.0,
            stamp_duty=0.0,
            total_fee=5.0,
            net_cash_flow=-15005.0,
            cost=-15005.0,
        )
        
        # Should be equal
        self.assertEqual(trade_old, trade_new)
        self.assertEqual(type(trade_old), type(trade_new))


class TestDeterministicSerialization(unittest.TestCase):
    """Test serialization output is deterministic (stable for hashing)."""
    
    def test_same_object_same_json(self):
        """Same object produces same JSON string (deterministic key order)."""
        trade = Trade(
            trade_id="T001",
            order_id="O001",
            symbol="600519.SH",
            direction="buy",
            quantity=100,
            price=150.0,
            trade_date=date(2023, 6, 15),
            gross_amount=15000.0,
            commission=5.0,
            stamp_duty=0.0,
            total_fee=5.0,
            net_cash_flow=-15005.0,
            cost=-15005.0,
        )
        
        json_str_1 = trade.model_dump_json()
        json_str_2 = trade.model_dump_json()
        
        # Should be identical strings
        self.assertEqual(json_str_1, json_str_2)
        
        # Can hash for content addressing
        import hashlib
        hash_1 = hashlib.sha256(json_str_1.encode()).hexdigest()
        hash_2 = hashlib.sha256(json_str_2.encode()).hexdigest()
        self.assertEqual(hash_1, hash_2)
    
    def test_dict_mode_deterministic_keys(self):
        """Dict mode preserves field order (Pydantic default)."""
        metrics = BacktestMetrics(
            total_return=0.15,
            max_drawdown=-0.08,
            sharpe_ratio=1.25,
            total_trades=50,
            filled_orders=48,
            completed_round_trips=24,
        )
        
        dict_1 = metrics.model_dump(mode="json")
        dict_2 = metrics.model_dump(mode="json")
        
        # Keys should appear in same order
        self.assertEqual(list(dict_1.keys()), list(dict_2.keys()))


class TestSchemaVersion(unittest.TestCase):
    """Test schema version is defined and accessible."""
    
    def test_schema_version_defined(self):
        """SCHEMA_VERSION constant is defined."""
        self.assertEqual(SCHEMA_VERSION, "1.0")
    
    def test_schema_version_for_exports(self):
        """Export-level metadata should include schema_version."""
        # This tests the convention, not enforced at model level
        export_metadata = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": "2026-06-22T12:00:00",
            "data_source": "fixed_fixture",
        }
        
        self.assertEqual(export_metadata["schema_version"], "1.0")
        
        # Individual models don't need schema_version field
        trade = Trade(
            trade_id="T001",
            order_id="O001",
            symbol="600519.SH",
            direction="buy",
            quantity=100,
            price=150.0,
            trade_date=date(2023, 6, 15),
            gross_amount=15000.0,
            commission=5.0,
            stamp_duty=0.0,
            total_fee=5.0,
            net_cash_flow=-15005.0,
            cost=-15005.0,
        )
        
        # Trade doesn't have schema_version field (correct)
        trade_dict = trade.model_dump()
        self.assertNotIn("schema_version", trade_dict)


if __name__ == "__main__":
    unittest.main()
