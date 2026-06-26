import unittest
from datetime import date

from backend.services.time_consistency_guard import TimeConsistencyGuard
from backend.services.b3_protocol_types import TimeConsistencyCheckResult


class TestTimeConsistencyGuard(unittest.TestCase):
    def setUp(self):
        self.guard = TimeConsistencyGuard()

    def test_universe_snapshot_after_backtest_start_blocks_formal_validation(self):
        """Universe snapshot date > backtest_start must block formal validation."""
        result = self.guard.validate_universe_snapshot(
            snapshot_date=date(2024, 6, 1),
            backtest_start=date(2024, 1, 1),
            universe_type="historical_backtest",
        )
        
        self.assertEqual(result.status, "fail")
        self.assertGreater(len(result.blocking_violations), 0)
        self.assertIn("future", result.blocking_violations[0].lower())

    def test_current_labels_cannot_filter_history(self):
        """Current labels must not filter historical universe."""
        result = self.guard.validate_filter_timestamp(
            filter_name="current_labels",
            filter_timestamp=date(2024, 12, 31),
            evaluation_date=date(2024, 1, 1),
        )
        
        self.assertEqual(result.status, "fail")
        self.assertGreater(len(result.blocking_violations), 0)

    def test_current_confirmed_candidates_cannot_be_historical_universe(self):
        """Confirmed candidate pool from A module cannot be historical universe."""
        result = self.guard.validate_universe_source(
            source_type="confirmed_candidate_pool",
            source_snapshot_date=date(2024, 12, 31),
            backtest_start=date(2024, 1, 1),
        )
        
        self.assertEqual(result.status, "fail")
        self.assertGreater(len(result.blocking_violations), 0)
        self.assertIn("candidate", result.blocking_violations[0].lower())

    def test_future_ann_date_blocks_financial_filter(self):
        """Financial filter with future ann_date must block."""
        result = self.guard.validate_financial_filter(
            ann_date=date(2024, 6, 1),
            evaluation_date=date(2024, 1, 1),
        )
        
        self.assertEqual(result.status, "fail")
        self.assertGreater(len(result.blocking_violations), 0)
        self.assertIn("future", result.blocking_violations[0].lower())

    def test_current_sector_membership_cannot_backfill_past(self):
        """Current sector membership used for historical backtest must block."""
        result = self.guard.validate_universe_snapshot(
            snapshot_date=date(2024, 12, 31),
            backtest_start=date(2024, 1, 1),
            universe_type="sector_membership",
        )
        
        self.assertEqual(result.status, "fail")
        self.assertGreater(len(result.blocking_violations), 0)

    def test_missing_delisted_coverage_blocks_or_degrades(self):
        """Missing delisted coverage must block or degrade according to policy."""
        result = self.guard.validate_delisted_coverage(
            has_delisted_coverage=False,
            policy="strict",
        )
        
        # Strict policy: block
        self.assertEqual(result.status, "fail")
        self.assertGreater(len(result.blocking_violations), 0)
        
        # Lenient policy: degrade
        result_lenient = self.guard.validate_delisted_coverage(
            has_delisted_coverage=False,
            policy="lenient",
        )
        
        self.assertEqual(result_lenient.status, "pass")
        self.assertGreater(len(result_lenient.warnings), 0)

    def test_unknown_daily_status_creates_degradation(self):
        """Unknown daily status (ST, suspension, limit) must create degradation."""
        result = self.guard.validate_daily_status_coverage(
            has_complete_status=False,
        )
        
        self.assertEqual(result.status, "pass")
        self.assertGreater(len(result.warnings), 0)
        self.assertIn("status", result.warnings[0].lower())

    def test_filter_input_timestamp_after_eval_date_blocks(self):
        """Any filter with input timestamp > eval date must block."""
        result = self.guard.validate_filter_timestamp(
            filter_name="technical_indicator",
            filter_timestamp=date(2024, 6, 1),
            evaluation_date=date(2024, 1, 1),
        )
        
        self.assertEqual(result.status, "fail")
        self.assertGreater(len(result.blocking_violations), 0)

    def test_evidence_run_cannot_clean_historical_universe(self):
        """Evidence run_date > backtest_start cannot clean historical universe."""
        result = self.guard.validate_evidence_timestamp(
            evidence_run_date=date(2024, 6, 1),
            backtest_start=date(2024, 1, 1),
        )
        
        self.assertEqual(result.status, "fail")
        self.assertGreater(len(result.blocking_violations), 0)
        self.assertIn("evidence", result.blocking_violations[0].lower())

    def test_evidence_conflict_not_marked_as_degradation(self):
        """evidence_conflict is separate from degradation warnings."""
        result = self.guard.check_evidence_conflict(
            evidence_a="bullish momentum",
            evidence_b="bearish breakdown",
        )
        
        # Evidence conflict detected but not degradation
        self.assertTrue(result.has_conflict)
        self.assertGreater(len(result.conflicts), 0)
        # Should not be in warnings (separate field)
        self.assertEqual(len(result.warnings), 0)

    def test_no_silent_fallback_to_static_symbols(self):
        """Guard must not silently fall back to static symbol list."""
        # Missing universe source should fail loud, not fall back
        result = self.guard.validate_universe_source(
            source_type="missing",
            source_snapshot_date=date(2024, 1, 1),
            backtest_start=date(2024, 1, 1),
        )
        
        self.assertEqual(result.status, "fail")
        self.assertGreater(len(result.blocking_violations), 0)


if __name__ == "__main__":
    unittest.main()
