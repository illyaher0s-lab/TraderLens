"""
B6 Final Vertical Flow Tests

Tests the minimal B-module V1 vertical flow from StrategyDraft to C admission.
"""
import unittest
from datetime import datetime, date

from backend.services.b5_oos_types import B6ValidationRunResult


class TestB6ValidationFlow(unittest.TestCase):
    def test_b6_run_result_is_frozen_and_has_no_trade_instruction_fields(self):
        """B6 run result is frozen and contains no buy/sell/trade fields."""
        result = B6ValidationRunResult(
            run_id="b6_run_001",
            strategy_revision_id="strat_001",
            protocol_snapshot_id="proto_001",
            report_id="report_001",
            gate_result_id="gate_001",
            explanation_id="expl_001",
            promotion_id=None,
            final_state="candidate_for_prototype_passed",
            status="completed",
            blocking_reason=None,
            created_at=datetime(2026, 6, 28, 10, 0, 0),
        )

        # Verify frozen
        self.assertTrue(result.frozen)

        # Verify no trade instruction fields
        dumped = result.model_dump()
        self.assertNotIn("buy", dumped)
        self.assertNotIn("sell", dumped)
        self.assertNotIn("target_price", dumped)
        self.assertNotIn("stop_loss", dumped)
        self.assertNotIn("action_plan", dumped)

        # Verify immutable
        with self.assertRaises(Exception):
            result.status = "changed"


if __name__ == "__main__":
    unittest.main()
