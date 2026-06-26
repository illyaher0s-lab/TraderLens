"""B4 Future Data Guard Tests - Verify future access is blocked."""
import unittest
from datetime import date

from backend.services.backtest_time_cursor import (
    BacktestTimeCursor,
    FutureDataAccessError,
)
from backend.services.future_data_guard import FutureDataGuard


class TestFutureDataGuard(unittest.TestCase):
    def setUp(self):
        self.cursor = BacktestTimeCursor(
            cursor_id="cursor_001",
            current_date=date(2024, 1, 10),
            evaluation_mode="signal_phase",
        )
        self.guard = FutureDataGuard(self.cursor)

    def test_future_bar_access_blocked(self):
        """Future bar access must raise FutureDataAccessError."""
        with self.assertRaises(FutureDataAccessError) as ctx:
            self.guard.check_bar_access(
                symbol="000001.SZ",
                requested_date=date(2024, 1, 11),  # Future
                source="strategy",
            )
        
        self.assertIn("Future data access blocked", str(ctx.exception))
        
        # Violation recorded
        violations = self.guard.get_violations()
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].requested_date, date(2024, 1, 11))
        self.assertEqual(violations[0].allowed_max_date, date(2024, 1, 10))

    def test_current_bar_access_allowed(self):
        """Current date bar access is allowed."""
        # Should not raise
        self.guard.check_bar_access(
            symbol="000001.SZ",
            requested_date=date(2024, 1, 10),  # Current
            source="strategy",
        )
        
        # No violations
        self.assertEqual(len(self.guard.get_violations()), 0)

    def test_future_daily_status_blocked(self):
        """Future daily status access must be blocked."""
        with self.assertRaises(FutureDataAccessError):
            self.guard.check_daily_status_access(
                symbol="000001.SZ",
                requested_date=date(2024, 1, 11),
                source="status_reader",
            )

    def test_future_financial_ann_date_blocked(self):
        """Future financial ann_date access must be blocked."""
        with self.assertRaises(FutureDataAccessError):
            self.guard.check_financial_access(
                symbol="000001.SZ",
                ann_date=date(2024, 1, 11),  # Future ann_date
                source="financial_reader",
            )

    def test_future_membership_blocked(self):
        """Future universe membership access must be blocked."""
        with self.assertRaises(FutureDataAccessError):
            self.guard.check_membership_access(
                symbol="000001.SZ",
                membership_date=date(2024, 1, 11),
                source="membership_reader",
            )

    def test_future_adjustment_factor_blocked(self):
        """Future adjustment factor access must be blocked."""
        with self.assertRaises(FutureDataAccessError):
            self.guard.check_adjustment_factor_access(
                symbol="000001.SZ",
                factor_date=date(2024, 1, 11),
                source="adjustment_factor_reader",
            )

    def test_full_sample_mean_blocked(self):
        """Full-sample mean must be blocked (uses future data)."""
        with self.assertRaises(FutureDataAccessError) as ctx:
            self.guard.block_full_sample_stats(
                operation="mean",
                source="stats_calculator",
            )
        
        self.assertIn("Full-sample mean uses future data", str(ctx.exception.violation.reason))

    def test_full_sample_percentile_blocked(self):
        """Full-sample percentile must be blocked."""
        with self.assertRaises(FutureDataAccessError):
            self.guard.block_full_sample_stats(
                operation="percentile",
                source="stats_calculator",
            )

    def test_future_violation_is_blocking_not_degraded(self):
        """Future violation is blocking failure, not degraded success."""
        try:
            self.guard.check_bar_access(
                symbol="000001.SZ",
                requested_date=date(2024, 1, 11),
                source="test",
            )
            self.fail("Should have raised FutureDataAccessError")
        except FutureDataAccessError as e:
            # Violation does not have severity/warning fields
            self.assertFalse(hasattr(e.violation, "severity"))
            self.assertFalse(hasattr(e.violation, "is_warning"))
            # It's a hard block

    def test_multiple_violations_recorded(self):
        """All violations must be recorded."""
        # Attempt multiple future accesses
        try:
            self.guard.check_bar_access("000001.SZ", date(2024, 1, 11), "test")
        except FutureDataAccessError:
            pass
        
        try:
            self.guard.check_daily_status_access("000002.SZ", date(2024, 1, 12), "test")
        except FutureDataAccessError:
            pass
        
        violations = self.guard.get_violations()
        self.assertEqual(len(violations), 2)


if __name__ == "__main__":
    unittest.main()
