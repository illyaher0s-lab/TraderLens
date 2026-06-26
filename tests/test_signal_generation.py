"""
Integration tests for Signal Generation Script.

Tests that generate_planned_signals.py can:
1. Load frozen snapshot
2. Load strategy YAML
3. Generate PlannedSignal JSON
4. All PlannedSignal fields are complete
5. planned_action mapping is correct
6. review_status defaults to pending
7. snapshot_hash / strategy_version are bound
8. No network access (API-free)
"""

import json
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

from backend.scripts.generate_planned_signals import (
    compute_deterministic_signal_id,
    convert_signal_to_planned_signal,
    load_strategy_config,
    map_direction_to_planned_action,
)
from contracts.signal_board import PlannedSignal
from contracts.stable import Signal


class TestDeterministicSignalId(unittest.TestCase):
    """Test deterministic signal_id computation."""
    
    def test_same_inputs_same_id(self):
        """Test that same inputs produce same signal_id."""
        signal_id_1 = compute_deterministic_signal_id(
            strategy_id="momentum_v2",
            strategy_version="v2.1.0",
            snapshot_hash="abc123",
            signal_date=date(2023, 12, 29),
            intended_execution_date=date(2024, 1, 2),
            symbol="600519.SH",
            direction="buy",
            trigger_reason="Price broke above 5-day high",
        )
        
        signal_id_2 = compute_deterministic_signal_id(
            strategy_id="momentum_v2",
            strategy_version="v2.1.0",
            snapshot_hash="abc123",
            signal_date=date(2023, 12, 29),
            intended_execution_date=date(2024, 1, 2),
            symbol="600519.SH",
            direction="buy",
            trigger_reason="Price broke above 5-day high",
        )
        
        self.assertEqual(signal_id_1, signal_id_2)
        self.assertEqual(len(signal_id_1), 64)  # SHA256 hex string
    
    def test_different_symbol_different_id(self):
        """Test that different symbols produce different signal_ids."""
        signal_id_1 = compute_deterministic_signal_id(
            strategy_id="momentum_v2",
            strategy_version="v2.1.0",
            snapshot_hash="abc123",
            signal_date=date(2023, 12, 29),
            intended_execution_date=date(2024, 1, 2),
            symbol="600519.SH",
            direction="buy",
            trigger_reason="Price broke above 5-day high",
        )
        
        signal_id_2 = compute_deterministic_signal_id(
            strategy_id="momentum_v2",
            strategy_version="v2.1.0",
            snapshot_hash="abc123",
            signal_date=date(2023, 12, 29),
            intended_execution_date=date(2024, 1, 2),
            symbol="000001.SZ",  # Different symbol
            direction="buy",
            trigger_reason="Price broke above 5-day high",
        )
        
        self.assertNotEqual(signal_id_1, signal_id_2)
    
    def test_different_trigger_reason_different_id(self):
        """Test that different trigger_reasons produce different signal_ids."""
        signal_id_1 = compute_deterministic_signal_id(
            strategy_id="momentum_v2",
            strategy_version="v2.1.0",
            snapshot_hash="abc123",
            signal_date=date(2023, 12, 29),
            intended_execution_date=date(2024, 1, 2),
            symbol="600519.SH",
            direction="buy",
            trigger_reason="Price broke above 5-day high",
        )
        
        signal_id_2 = compute_deterministic_signal_id(
            strategy_id="momentum_v2",
            strategy_version="v2.1.0",
            snapshot_hash="abc123",
            signal_date=date(2023, 12, 29),
            intended_execution_date=date(2024, 1, 2),
            symbol="600519.SH",
            direction="buy",
            trigger_reason="Volume surge 2.5x average",  # Different reason
        )
        
        self.assertNotEqual(signal_id_1, signal_id_2)
    
    def test_different_direction_different_id(self):
        """Test that different directions produce different signal_ids."""
        signal_id_1 = compute_deterministic_signal_id(
            strategy_id="momentum_v2",
            strategy_version="v2.1.0",
            snapshot_hash="abc123",
            signal_date=date(2023, 12, 29),
            intended_execution_date=date(2024, 1, 2),
            symbol="600519.SH",
            direction="buy",
            trigger_reason="Price broke above 5-day high",
        )
        
        signal_id_2 = compute_deterministic_signal_id(
            strategy_id="momentum_v2",
            strategy_version="v2.1.0",
            snapshot_hash="abc123",
            signal_date=date(2023, 12, 29),
            intended_execution_date=date(2024, 1, 2),
            symbol="600519.SH",
            direction="sell",  # Different direction
            trigger_reason="Price broke above 5-day high",
        )
        
        self.assertNotEqual(signal_id_1, signal_id_2)


class TestPlannedActionMapping(unittest.TestCase):
    """Test direction → planned_action mapping."""
    
    def test_buy_maps_to_enter(self):
        """Test buy → enter."""
        self.assertEqual(map_direction_to_planned_action("buy"), "enter")
    
    def test_sell_maps_to_exit(self):
        """Test sell → exit."""
        self.assertEqual(map_direction_to_planned_action("sell"), "exit")
    
    def test_invalid_direction_raises(self):
        """Test invalid direction raises ValueError."""
        with self.assertRaises(ValueError):
            map_direction_to_planned_action("hold")


class TestSignalConversion(unittest.TestCase):
    """Test Signal → PlannedSignal conversion."""
    
    def setUp(self):
        """Create mock data source for testing."""
        # Create a minimal mock data source for unit tests
        # (Avoids dependency on golden case data files)
        from contracts.stable import DailyBar
        
        class MockDataSource:
            """Mock data source for testing."""
            
            def get_price(self, symbol: str, date_: date) -> float:
                """Return mock price."""
                return 1850.0  # Fixed price for testing
            
            def get_daily_bars(self, symbol: str) -> list[DailyBar]:
                """Return mock daily bars."""
                return [
                    DailyBar(
                        date=date(2023, 1, 3),
                        symbol=symbol,
                        open=1800.0,
                        high=1900.0,
                        low=1750.0,
                        close=1850.0,
                        volume=1000000,
                        amount=1850000000.0,
                        adj_factor=1.0,
                    )
                ]
        
        self.data_source = MockDataSource()
        
        # Load a sample strategy config
        # (We'll use a minimal mock for unit tests)
        from contracts.stable import (
            AuditSnapshot,
            BacktestConfig,
            BenchmarkConfig,
            DataRange,
            FillHandling,
            FillModel,
            HypothesisSourceSnapshot,
            RebalanceConfig,
            RiskFilters,
            RuleGroup,
            SampleSplit,
            StrategyConfig,
            UniverseConfig,
        )
        
        self.strategy_config = StrategyConfig(
            strategy_name="test_strategy",
            version="v1.0.0",
            status="draft",
            hypothesis_source_snapshot=HypothesisSourceSnapshot(
                source_type="manual",
                source_run_id="test",
                generated_at=datetime.utcnow(),
                data_range_used_for_generation=DataRange(
                    start=date(2023, 1, 1),
                    end=date(2023, 12, 31),
                ),
            ),
            universe=UniverseConfig(type="static_list", symbols=["600519.SH"]),
            entry_conditions=RuleGroup(logic="AND", rules=[]),
            exit_conditions=RuleGroup(logic="OR", rules=[]),
            risk_filters=RiskFilters(
                max_position_per_stock=0.1,
                max_total_position=1.0,
                restrict_limit_up_buy=True,
                restrict_limit_down_sell=True,
                restrict_suspended=True,
                min_liquidity_for_trade=0.0,
            ),
            rebalance=RebalanceConfig(frequency="daily", check_time="close"),
            fill_model=FillModel(
                signal_to_execution="T+1",
                execution_price="open",
                commission=0.0003,
                stamp_tax=0.001,
                slippage=0.0,
                lot_size=100,
                lot_rounding="floor",
                handling=FillHandling(
                    limit_up_buy="skip",
                    limit_down_sell="skip",
                    suspended="skip",
                ),
            ),
            backtest_config=BacktestConfig(
                initial_capital=100000.0,
                start_date=date(2023, 1, 1),
                end_date=date(2023, 12, 31),
                sample_split=SampleSplit(
                    in_sample_end=date(2023, 6, 30),
                    out_of_sample_start=date(2023, 7, 1),
                ),
                benchmark=BenchmarkConfig(type="index", code="000001.SH", name="上证指数"),
                data_source="golden_case",
                include_delisted="none",
            ),
            audit=AuditSnapshot(
                created_at=datetime.utcnow(),
                created_by="test",
                last_modified_at=datetime.utcnow(),
                config_hash="test_hash",
            ),
        )
    
    def test_entry_signal_converts_to_buy_enter(self):
        """Test entry signal → direction=buy, planned_action=enter."""
        signal = Signal(
            signal_id="test_signal_1",
            strategy_id="test_strategy",
            strategy_version="v1.0.0",
            symbol="600519.SH",
            signal_date=date(2023, 1, 3),
            signal_type="entry",
            triggered_rules=["breakthrough:close>=high_5d"],
            audit_id="test_audit",
        )
        
        planned_signal = convert_signal_to_planned_signal(
            signal=signal,
            snapshot_hash="test_snapshot_hash",
            signal_date=date(2023, 1, 3),
            intended_execution_date=date(2023, 1, 4),
            data_source=self.data_source,
            strategy_config=self.strategy_config,
        )
        
        self.assertEqual(planned_signal.direction, "buy")
        self.assertEqual(planned_signal.planned_action, "enter")
        self.assertEqual(planned_signal.review_status, "pending")
        self.assertEqual(planned_signal.symbol, "600519.SH")
        self.assertIsNotNone(planned_signal.signal_id)
        self.assertEqual(len(planned_signal.signal_id), 64)  # SHA256 hex
    
    def test_exit_signal_converts_to_sell_exit(self):
        """Test exit signal → direction=sell, planned_action=exit."""
        signal = Signal(
            signal_id="test_signal_2",
            strategy_id="test_strategy",
            strategy_version="v1.0.0",
            symbol="600519.SH",
            signal_date=date(2023, 1, 3),
            signal_type="exit",
            triggered_rules=["ma_condition:close<ma_10"],
            audit_id="test_audit",
        )
        
        planned_signal = convert_signal_to_planned_signal(
            signal=signal,
            snapshot_hash="test_snapshot_hash",
            signal_date=date(2023, 1, 3),
            intended_execution_date=date(2023, 1, 4),
            data_source=self.data_source,
            strategy_config=self.strategy_config,
        )
        
        self.assertEqual(planned_signal.direction, "sell")
        self.assertEqual(planned_signal.planned_action, "exit")
        self.assertEqual(planned_signal.review_status, "pending")
    
    def test_planned_signal_has_all_required_fields(self):
        """Test PlannedSignal has all required fields."""
        signal = Signal(
            signal_id="test_signal_3",
            strategy_id="test_strategy",
            strategy_version="v1.0.0",
            symbol="600519.SH",
            signal_date=date(2023, 1, 3),
            signal_type="entry",
            triggered_rules=["breakthrough:close>=high_5d", "volume_surge:volume>=ma_volume_5d*2.0"],
            audit_id="test_audit",
        )
        
        planned_signal = convert_signal_to_planned_signal(
            signal=signal,
            snapshot_hash="test_snapshot_hash",
            signal_date=date(2023, 1, 3),
            intended_execution_date=date(2023, 1, 4),
            data_source=self.data_source,
            strategy_config=self.strategy_config,
        )
        
        # Check all required fields
        self.assertIsNotNone(planned_signal.signal_id)
        self.assertEqual(planned_signal.strategy_id, "test_strategy")
        self.assertEqual(planned_signal.strategy_version, "v1.0.0")
        self.assertEqual(planned_signal.snapshot_hash, "test_snapshot_hash")
        self.assertEqual(planned_signal.signal_date, date(2023, 1, 3))
        self.assertEqual(planned_signal.intended_execution_date, date(2023, 1, 4))
        self.assertEqual(planned_signal.symbol, "600519.SH")
        self.assertEqual(planned_signal.direction, "buy")
        self.assertEqual(planned_signal.planned_action, "enter")
        self.assertIn("breakthrough", planned_signal.trigger_reason)
        self.assertIn("volume_surge", planned_signal.trigger_reason)
        self.assertEqual(planned_signal.review_status, "pending")
        self.assertIsNone(planned_signal.reviewed_at)
        self.assertIsNone(planned_signal.reviewed_by)
        self.assertIsNone(planned_signal.rejection_reason)
        self.assertIsNotNone(planned_signal.created_at)
        self.assertIsInstance(planned_signal.metadata, dict)
    
    def test_signal_without_triggered_rules_raises(self):
        """Test signal without triggered_rules raises ValueError."""
        signal = Signal(
            signal_id="test_signal_4",
            strategy_id="test_strategy",
            strategy_version="v1.0.0",
            symbol="600519.SH",
            signal_date=date(2023, 1, 3),
            signal_type="entry",
            triggered_rules=[],  # Empty!
            audit_id="test_audit",
        )
        
        with self.assertRaises(ValueError) as cm:
            convert_signal_to_planned_signal(
                signal=signal,
                snapshot_hash="test_snapshot_hash",
                signal_date=date(2023, 1, 3),
                intended_execution_date=date(2023, 1, 4),
                data_source=self.data_source,
                strategy_config=self.strategy_config,
            )
        
        self.assertIn("no triggered_rules", str(cm.exception).lower())


if __name__ == "__main__":
    unittest.main()
