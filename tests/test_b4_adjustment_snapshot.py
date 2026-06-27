"""B4 Task 8: Adjustment price snapshot guard tests.

All tests go through real CursorBoundDataView.get_bar() path.

Proves:
1. Adjustment mode (raw/qfq/hfq) is locked per backtest run
2. Mixed modes are hard rejected
3. Factor source/snapshot must match B3 DataSnapshotManifest
4. Future adjustment factors cannot rewrite past adjusted prices
5. T+1 corporate action cannot affect T-day signal
6. Read trace records mode/source/fingerprint/snapshot_date
7. No LLM dependency
"""
import unittest
from datetime import date, timedelta

from backend.services.backtest_time_cursor import (
    BacktestTimeCursor,
    FutureDataAccessError,
)
from strategy_core.cursor_bound_data_view import CursorBoundDataView
from contracts.stable import DailyBar
from tests.b4_fixtures import create_mock_bar_data_source


class TestAdjustmentFactorSourceMatchesDataSnapshot(unittest.TestCase):
    """Adjustment factor source/fingerprint must match B3 data snapshot."""
    
    def test_adjustment_factor_source_matches_data_snapshot(self):
        """Factor fingerprint matches B3 DataSnapshotManifest → allowed."""
        cursor = BacktestTimeCursor(
            cursor_id="test_cursor",
            current_date=date(2024, 1, 10),
            evaluation_mode="signal_phase",
        )
        
        # Mock bar data
        bars = {
            "000001.SZ": [
                DailyBar(
                    date=date(2024, 1, 10),
                    symbol="000001.SZ",
                    open=10.0, high=11.0, low=9.0, close=10.5,
                    volume=1000000, amount=10500000.0,
                    adj_factor=1.0,
                )
            ]
        }
        mock_source = create_mock_bar_data_source(bars)
        
        # Fingerprint matches B3
        fingerprint = "abc123"
        expected_fingerprint = "abc123"
        
        data_view = CursorBoundDataView(
            mock_source,
            cursor,
            adjustment_mode="qfq",
            adjustment_snapshot_date=date(2024, 1, 9),
            adjustment_fingerprint=fingerprint,
            expected_adjustment_fingerprint=expected_fingerprint,
        )
        
        # Should not raise
        bar = data_view.get_bar("000001.SZ", date(2024, 1, 10))
        self.assertIsNotNone(bar)
        self.assertEqual(bar.adj_factor, 1.0)
    
    def test_factor_fingerprint_mismatch_rejected(self):
        """Factor fingerprint mismatch with B3 data snapshot is hard reject."""
        cursor = BacktestTimeCursor(
            cursor_id="test_cursor",
            current_date=date(2024, 1, 10),
            evaluation_mode="signal_phase",
        )
        
        bars = {
            "000001.SZ": [
                DailyBar(
                    date=date(2024, 1, 10),
                    symbol="000001.SZ",
                    open=10.0, high=11.0, low=9.0, close=10.5,
                    volume=1000000, amount=10500000.0,
                    adj_factor=1.0,
                )
            ]
        }
        mock_source = create_mock_bar_data_source(bars)
        
        # B3 expects one fingerprint, but data_view provides different
        fingerprint = "xyz789"
        expected_fingerprint = "abc123"
        
        data_view = CursorBoundDataView(
            mock_source,
            cursor,
            adjustment_mode="qfq",
            adjustment_snapshot_date=date(2024, 1, 9),
            adjustment_fingerprint=fingerprint,
            expected_adjustment_fingerprint=expected_fingerprint,
        )
        
        # Should raise ValueError (hard reject)
        with self.assertRaises(ValueError) as ctx:
            data_view.get_bar("000001.SZ", date(2024, 1, 10))
        
        self.assertIn("mismatch", str(ctx.exception).lower())
        self.assertIn("abc123", str(ctx.exception))
        self.assertIn("xyz789", str(ctx.exception))


class TestAdjustmentFactorSnapshotDateNotAfterCurrentDate(unittest.TestCase):
    """Factor snapshot date must not be after cursor current_date."""
    
    def test_adjustment_factor_snapshot_date_not_after_current_date(self):
        """Factor snapshot dated after current_date is future data violation."""
        current_date = date(2024, 1, 10)
        cursor = BacktestTimeCursor(
            cursor_id="test_cursor",
            current_date=current_date,
            evaluation_mode="signal_phase",
        )
        
        bars = {
            "000001.SZ": [
                DailyBar(
                    date=current_date,
                    symbol="000001.SZ",
                    open=10.0, high=11.0, low=9.0, close=10.5,
                    volume=1000000, amount=10500000.0,
                    adj_factor=1.0,
                )
            ]
        }
        mock_source = create_mock_bar_data_source(bars)
        
        # Factor snapshot dated T+1 (future)
        future_snapshot_date = current_date + timedelta(days=1)
        
        data_view = CursorBoundDataView(
            mock_source,
            cursor,
            adjustment_mode="qfq",
            adjustment_snapshot_date=future_snapshot_date,
            adjustment_fingerprint="abc123",
            expected_adjustment_fingerprint="abc123",
        )
        
        # Should raise FutureDataAccessError (hard block)
        with self.assertRaises(FutureDataAccessError) as ctx:
            data_view.get_bar("000001.SZ", current_date)
        
        violation = ctx.exception.violation
        self.assertEqual(violation.requested_date, future_snapshot_date)
        self.assertEqual(violation.allowed_max_date, current_date)
        self.assertIn("snapshot", violation.reason.lower())
    
    def test_past_factor_snapshot_date_allowed(self):
        """Factor snapshot dated <= current_date is allowed."""
        current_date = date(2024, 1, 10)
        cursor = BacktestTimeCursor(
            cursor_id="test_cursor",
            current_date=current_date,
            evaluation_mode="signal_phase",
        )
        
        bars = {
            "000001.SZ": [
                DailyBar(
                    date=current_date,
                    symbol="000001.SZ",
                    open=10.0, high=11.0, low=9.0, close=10.5,
                    volume=1000000, amount=10500000.0,
                    adj_factor=1.0,
                )
            ]
        }
        mock_source = create_mock_bar_data_source(bars)
        
        # T-1 snapshot
        past_snapshot_date = current_date - timedelta(days=1)
        
        data_view = CursorBoundDataView(
            mock_source,
            cursor,
            adjustment_mode="qfq",
            adjustment_snapshot_date=past_snapshot_date,
            adjustment_fingerprint="abc123",
            expected_adjustment_fingerprint="abc123",
        )
        
        # Should not raise
        bar = data_view.get_bar("000001.SZ", current_date)
        self.assertIsNotNone(bar)


class TestLateCorporateActionCannotRewritePastPrices(unittest.TestCase):
    """T+1 corporate action / factor cannot rewrite T-day adjusted price."""
    
    def test_late_corporate_action_cannot_rewrite_past_prices(self):
        """
        Proof: T+1 adjustment factor snapshot cannot be used in T-day signal.
        
        Scenario:
        - T = 2024-01-10, cursor in signal_phase
        - Strategy reads bar for T
        - Adjustment snapshot dated T+1 (late corporate action)
        - Must be hard blocked by FutureDataAccessError
        """
        current_date = date(2024, 1, 10)
        cursor = BacktestTimeCursor(
            cursor_id="test_cursor",
            current_date=current_date,
            evaluation_mode="signal_phase",
        )
        
        bars = {
            "000001.SZ": [
                DailyBar(
                    date=current_date,
                    symbol="000001.SZ",
                    open=10.0, high=11.0, low=9.0, close=10.5,
                    volume=1000000, amount=10500000.0,
                    adj_factor=1.05,  # T+1 corporate action adjusted this
                )
            ]
        }
        mock_source = create_mock_bar_data_source(bars)
        
        # T+1 adjustment snapshot (late corporate action)
        future_snapshot_date = current_date + timedelta(days=1)
        
        data_view = CursorBoundDataView(
            mock_source,
            cursor,
            adjustment_mode="qfq",
            adjustment_snapshot_date=future_snapshot_date,
            adjustment_fingerprint="future_adj_abc",
            expected_adjustment_fingerprint="future_adj_abc",
        )
        
        # Must raise FutureDataAccessError
        with self.assertRaises(FutureDataAccessError) as ctx:
            data_view.get_bar("000001.SZ", current_date)
        
        violation = ctx.exception.violation
        self.assertEqual(violation.requested_date, future_snapshot_date)
        self.assertEqual(violation.allowed_max_date, current_date)
    
    def test_t_factor_allowed_in_t_signal(self):
        """T-day signal can read adjustment factor dated <= T."""
        current_date = date(2024, 1, 10)
        cursor = BacktestTimeCursor(
            cursor_id="test_cursor",
            current_date=current_date,
            evaluation_mode="signal_phase",
        )
        
        bars = {
            "000001.SZ": [
                DailyBar(
                    date=current_date,
                    symbol="000001.SZ",
                    open=10.0, high=11.0, low=9.0, close=10.5,
                    volume=1000000, amount=10500000.0,
                    adj_factor=1.0,
                )
            ]
        }
        mock_source = create_mock_bar_data_source(bars)
        
        # T snapshot (allowed)
        data_view = CursorBoundDataView(
            mock_source,
            cursor,
            adjustment_mode="qfq",
            adjustment_snapshot_date=current_date,
            adjustment_fingerprint="abc123",
            expected_adjustment_fingerprint="abc123",
        )
        
        # Should not raise
        bar = data_view.get_bar("000001.SZ", current_date)
        self.assertIsNotNone(bar)


class TestMixedAdjustmentModesRejected(unittest.TestCase):
    """Mixed raw/qfq/hfq in one backtest run is hard reject."""
    
    def test_mixed_adjustment_modes_rejected(self):
        """raw → qfq is hard reject."""
        cursor = BacktestTimeCursor(
            cursor_id="test_cursor",
            current_date=date(2024, 1, 10),
            evaluation_mode="signal_phase",
        )
        
        bars = {
            "000001.SZ": [
                DailyBar(
                    date=date(2024, 1, 10),
                    symbol="000001.SZ",
                    open=10.0, high=11.0, low=9.0, close=10.5,
                    volume=1000000, amount=10500000.0,
                    adj_factor=1.0,
                )
            ]
        }
        mock_source = create_mock_bar_data_source(bars)
        
        # First access: raw
        data_view_raw = CursorBoundDataView(
            mock_source,
            cursor,
            adjustment_mode="raw",
            adjustment_snapshot_date=date(2024, 1, 9),
            adjustment_fingerprint="abc123",
            expected_adjustment_fingerprint="abc123",
        )
        
        bar1 = data_view_raw.get_bar("000001.SZ", date(2024, 1, 10))
        self.assertIsNotNone(bar1)
        
        # Second access: qfq → should reject
        data_view_qfq = CursorBoundDataView(
            mock_source,
            cursor,
            adjustment_mode="qfq",
            adjustment_snapshot_date=date(2024, 1, 9),
            adjustment_fingerprint="abc123",
            expected_adjustment_fingerprint="abc123",
        )
        
        with self.assertRaises(ValueError) as ctx:
            data_view_qfq.get_bar("000001.SZ", date(2024, 1, 10))
        
        self.assertIn("mixed", str(ctx.exception).lower())
        self.assertIn("raw", str(ctx.exception).lower())
        self.assertIn("qfq", str(ctx.exception).lower())
    
    def test_same_mode_repeated_allowed(self):
        """Repeated use of same mode is allowed."""
        cursor = BacktestTimeCursor(
            cursor_id="test_cursor",
            current_date=date(2024, 1, 10),
            evaluation_mode="signal_phase",
        )
        
        bars = {
            "000001.SZ": [
                DailyBar(
                    date=date(2024, 1, 10),
                    symbol="000001.SZ",
                    open=10.0, high=11.0, low=9.0, close=10.5,
                    volume=1000000, amount=10500000.0,
                    adj_factor=1.0,
                )
            ],
            "000002.SZ": [
                DailyBar(
                    date=date(2024, 1, 10),
                    symbol="000002.SZ",
                    open=20.0, high=21.0, low=19.0, close=20.5,
                    volume=2000000, amount=41000000.0,
                    adj_factor=1.0,
                )
            ]
        }
        mock_source = create_mock_bar_data_source(bars)
        
        data_view = CursorBoundDataView(
            mock_source,
            cursor,
            adjustment_mode="qfq",
            adjustment_snapshot_date=date(2024, 1, 9),
            adjustment_fingerprint="abc123",
            expected_adjustment_fingerprint="abc123",
        )
        
        # Multiple reads with same mode
        bar1 = data_view.get_bar("000001.SZ", date(2024, 1, 10))
        bar2 = data_view.get_bar("000002.SZ", date(2024, 1, 10))
        bar3 = data_view.get_bar("000001.SZ", date(2024, 1, 10))
        
        self.assertIsNotNone(bar1)
        self.assertIsNotNone(bar2)
        self.assertIsNotNone(bar3)


class TestRawQfqHfqModeRecorded(unittest.TestCase):
    """Adjustment mode (raw/qfq/hfq) is recorded in cursor state."""
    
    def test_raw_qfq_hfq_mode_recorded(self):
        """After first get_bar(), cursor reflects locked mode."""
        cursor = BacktestTimeCursor(
            cursor_id="test_cursor",
            current_date=date(2024, 1, 10),
            evaluation_mode="signal_phase",
        )
        
        bars = {
            "000001.SZ": [
                DailyBar(
                    date=date(2024, 1, 10),
                    symbol="000001.SZ",
                    open=10.0, high=11.0, low=9.0, close=10.5,
                    volume=1000000, amount=10500000.0,
                    adj_factor=1.0,
                )
            ]
        }
        mock_source = create_mock_bar_data_source(bars)
        
        # Before any read: no mode locked
        self.assertIsNone(cursor.locked_adjustment_mode)
        
        # Read with qfq
        data_view = CursorBoundDataView(
            mock_source,
            cursor,
            adjustment_mode="qfq",
            adjustment_snapshot_date=date(2024, 1, 9),
            adjustment_fingerprint="abc123",
            expected_adjustment_fingerprint="abc123",
        )
        
        bar = data_view.get_bar("000001.SZ", date(2024, 1, 10))
        self.assertIsNotNone(bar)
        
        # After read: mode locked
        self.assertEqual(cursor.locked_adjustment_mode, "qfq")
        self.assertEqual(cursor.adjustment_snapshot_date, date(2024, 1, 9))
        self.assertEqual(cursor.adjustment_snapshot_fingerprint, "abc123")


class TestAdjustedPriceReadTraceRecordsFactorVersion(unittest.TestCase):
    """Read trace must record adjustment mode/source/fingerprint/snapshot_date."""
    
    def test_adjusted_price_read_trace_records_factor_version(self):
        """Adjustment factor access is recorded with full metadata."""
        current_date = date(2024, 1, 10)
        cursor = BacktestTimeCursor(
            cursor_id="test_cursor",
            current_date=current_date,
            evaluation_mode="signal_phase",
        )
        
        bars = {
            "000001.SZ": [
                DailyBar(
                    date=current_date,
                    symbol="000001.SZ",
                    open=10.0, high=11.0, low=9.0, close=10.5,
                    volume=1000000, amount=10500000.0,
                    adj_factor=1.05,
                )
            ]
        }
        mock_source = create_mock_bar_data_source(bars)
        
        data_view = CursorBoundDataView(
            mock_source,
            cursor,
            adjustment_mode="qfq",
            adjustment_snapshot_date=date(2024, 1, 9),
            adjustment_fingerprint="test_fingerprint_abc123",
            expected_adjustment_fingerprint="test_fingerprint_abc123",
        )
        
        bar = data_view.get_bar("000001.SZ", current_date)
        self.assertIsNotNone(bar)
        
        # Check trace
        trace = cursor.read_trace
        adj_trace = [t for t in trace if "adjustment_factor" in t]
        self.assertTrue(len(adj_trace) > 0)
        
        entry = adj_trace[0]
        # Must contain: symbol, date, mode, adj_factor, fingerprint, snapshot_date
        self.assertIn("000001.SZ", entry)
        self.assertIn(str(current_date), entry)
        self.assertIn("qfq", entry.lower())
        self.assertIn("1.05", entry)
        self.assertIn("test_fingerprint_abc123", entry)
        self.assertIn("2024-01-09", entry)


class TestFutureAdjustmentFactorCanaryBlocked(unittest.TestCase):
    """Canary attempting future adjustment factor access must be blocked."""
    
    def test_future_adjustment_factor_canary_blocked(self):
        """
        Canary proof: Adjustment snapshot dated T+1 is blocked by guard.
        
        This test simulates FutureAdjustmentFactorCanary behavior through
        real CursorBoundDataView.get_bar() path.
        """
        current_date = date(2024, 1, 10)
        cursor = BacktestTimeCursor(
            cursor_id="canary_cursor",
            current_date=current_date,
            evaluation_mode="signal_phase",
        )
        
        bars = {
            "000001.SZ": [
                DailyBar(
                    date=current_date,
                    symbol="000001.SZ",
                    open=10.0, high=11.0, low=9.0, close=10.5,
                    volume=1000000, amount=10500000.0,
                    adj_factor=1.0,
                )
            ]
        }
        mock_source = create_mock_bar_data_source(bars)
        
        # Canary: attempt to use T+1 adjustment snapshot
        future_snapshot = current_date + timedelta(days=1)
        
        data_view = CursorBoundDataView(
            mock_source,
            cursor,
            adjustment_mode="qfq",
            adjustment_snapshot_date=future_snapshot,
            adjustment_fingerprint="canary_future_adj",
            expected_adjustment_fingerprint="canary_future_adj",
        )
        
        # Must be blocked
        with self.assertRaises(FutureDataAccessError) as ctx:
            data_view.get_bar("000001.SZ", current_date)
        
        violation = ctx.exception.violation
        self.assertEqual(violation.requested_date, future_snapshot)
        self.assertEqual(violation.allowed_max_date, current_date)


class TestAdjustmentGuardHasNoLLMDependency(unittest.TestCase):
    """Adjustment guard must not import or call LLM."""
    
    def test_adjustment_guard_has_no_llm_dependency(self):
        """backtest_time_cursor.py must not import LLM libraries."""
        import backend.services.backtest_time_cursor as cursor_module
        
        module_source = inspect.getsource(cursor_module)
        
        forbidden = ["openai", "anthropic", "langchain"]
        for term in forbidden:
            self.assertNotIn(term.lower(), module_source.lower())


import inspect

if __name__ == "__main__":
    unittest.main()
