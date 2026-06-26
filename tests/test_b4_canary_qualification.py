"""B4 Canary Qualification Tests - Verify Canary cases are blocked."""
import unittest
from datetime import date

from backend.services.backtest_time_cursor import BacktestTimeCursor
from backend.services.future_data_guard import FutureDataGuard
from backend.services.canary_strategies import (
    FutureBarCanary,
    FutureStatusCanary,
    FutureFinancialCanary,
    FutureMembershipCanary,
    FullSampleNormalizationCanary,
    FutureAdjustmentFactorCanary,
)
from backend.services.backtest_engine_qualification import BacktestEngineQualification


class TestCanaryQualification(unittest.TestCase):
    def setUp(self):
        self.cursor = BacktestTimeCursor(
            cursor_id="cursor_001",
            current_date=date(2024, 1, 10),
            evaluation_mode="signal_phase",
        )
        self.guard = FutureDataGuard(self.cursor)

    def test_future_bar_canary_blocked(self):
        """Future bar Canary must be blocked (not completed)."""
        canary = FutureBarCanary()
        result = canary.run(self.cursor, self.guard)
        
        # Correct result: blocked
        self.assertEqual(result.outcome, "blocked")
        self.assertEqual(result.violation_count, 1)
        self.assertGreater(len(result.violations), 0)

    def test_future_status_canary_blocked(self):
        """Future status Canary must be blocked."""
        canary = FutureStatusCanary()
        result = canary.run(self.cursor, self.guard)
        
        self.assertEqual(result.outcome, "blocked")
        self.assertGreater(result.violation_count, 0)

    def test_future_financial_canary_blocked(self):
        """Future financial ann_date Canary must be blocked."""
        canary = FutureFinancialCanary()
        result = canary.run(self.cursor, self.guard)
        
        self.assertEqual(result.outcome, "blocked")
        self.assertGreater(result.violation_count, 0)

    def test_future_membership_canary_blocked(self):
        """Future membership Canary must be blocked."""
        canary = FutureMembershipCanary()
        result = canary.run(self.cursor, self.guard)
        
        self.assertEqual(result.outcome, "blocked")
        self.assertGreater(result.violation_count, 0)

    def test_full_sample_normalization_canary_blocked(self):
        """Full-sample normalization Canary must be blocked."""
        canary = FullSampleNormalizationCanary()
        result = canary.run(self.cursor, self.guard)
        
        self.assertEqual(result.outcome, "blocked")
        self.assertGreater(result.violation_count, 0)

    def test_future_adjustment_factor_canary_blocked(self):
        """Future adjustment factor Canary must be blocked."""
        canary = FutureAdjustmentFactorCanary()
        result = canary.run(self.cursor, self.guard)
        
        self.assertEqual(result.outcome, "blocked")
        self.assertGreater(result.violation_count, 0)

    def test_qualification_suite_all_blocked(self):
        """Full Canary qualification suite: all cases must be blocked."""
        qualification = BacktestEngineQualification()
        
        result = qualification.run_qualification(
            protocol_snapshot_id="proto_001",
            qualification_date=date(2024, 1, 10),
        )
        
        # All Canary cases must be blocked
        for canary_case in result.canary_cases:
            self.assertEqual(
                canary_case.outcome,
                "blocked",
                f"Canary {canary_case.case_name} was {canary_case.outcome}, expected blocked",
            )
        
        # Qualification must pass (all blocked)
        self.assertEqual(result.qualification_status, "pass")

    def test_qualification_result_frozen(self):
        """Qualification result must be frozen."""
        qualification = BacktestEngineQualification()
        
        result = qualification.run_qualification(
            protocol_snapshot_id="proto_001",
            qualification_date=date(2024, 1, 10),
        )
        
        # Frozen
        self.assertTrue(result.frozen)
        
        with self.assertRaises(Exception):
            result.qualification_status = "fail"

    def test_canary_completed_means_qualification_failed(self):
        """If any Canary completes normally, qualification fails."""
        # This test documents the expected behavior
        # In correct implementation, all Canaries should be blocked
        # If a Canary shows outcome='completed', that means guard failed
        
        qualification = BacktestEngineQualification()
        result = qualification.run_qualification(
            protocol_snapshot_id="proto_001",
            qualification_date=date(2024, 1, 10),
        )
        
        # Check no Canary completed (all blocked)
        completed_canaries = [c for c in result.canary_cases if c.outcome == "completed"]
        self.assertEqual(
            len(completed_canaries),
            0,
            f"Canaries completed: {[c.case_name for c in completed_canaries]}",
        )

    def test_qualification_no_gate_verdict(self):
        """Qualification result must not have Gate verdict."""
        qualification = BacktestEngineQualification()
        result = qualification.run_qualification(
            protocol_snapshot_id="proto_001",
            qualification_date=date(2024, 1, 10),
        )
        
        # No Gate fields
        self.assertFalse(hasattr(result, "gate_verdict"))
        self.assertFalse(hasattr(result, "prototype_passed"))
        self.assertFalse(hasattr(result, "promotion_status"))


if __name__ == "__main__":
    unittest.main()
