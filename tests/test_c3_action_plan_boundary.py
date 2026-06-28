"""
C3 Action Plan Boundary Tests

Tests for Action Plan builder and boundary enforcement.

C3-2 scope (this file):
- Builder logic tests (freshness, blocking, warning rules)
- Admission enforcement tests
- Deterministic generation tests

C3-3 scope (to be added):
- API endpoint tests (GET/POST action-plan)
- Direct-id bypass tests
- Batch endpoint tests (if added)
"""

import unittest
from datetime import date, datetime, timedelta, timezone

from contracts.signal_board import PlannedSignal
from backend.services.action_plan_builder import build_action_plan


class TestActionPlanBuilder(unittest.TestCase):
    """Tests for Action Plan builder logic."""

    def _create_test_signal(
        self,
        signal_id: str = "test-signal-1",
        lifecycle_state: str = "prototype_passed",
        evidence_status: str = "clean",
        review_status: str = "pending",
        risk_flags: list[str] | None = None,
        quantity: int | None = 100,
        current_price: float | None = 100.0,
        intended_execution_date: date | None = None,
        rejection_reason: str | None = None,
        **kwargs
    ) -> PlannedSignal:
        """Create test PlannedSignal with defaults."""
        if intended_execution_date is None:
            intended_execution_date = date.today() + timedelta(days=1)

        return PlannedSignal(
            signal_id=signal_id,
            strategy_id="test_strategy",
            strategy_version="v1.0.0",
            strategy_revision_id="rev-001",
            lifecycle_state_at_generation=lifecycle_state,
            admission_source="c_admission_gate",
            snapshot_hash="abc123def456",
            signal_date=date.today(),
            intended_execution_date=intended_execution_date,
            symbol="600519.SH",
            direction="buy",
            planned_action="enter",
            quantity=quantity,
            trigger_reason="Test trigger",
            review_status=review_status,
            reviewed_at=None,
            reviewed_by=None,
            rejection_reason=rejection_reason,
            current_price=current_price,
            position_before=0,
            created_at=datetime.now(timezone.utc),
            metadata={},
            risk_flags=risk_flags or [],
            evidence_status=evidence_status,
            evidence_checked_at=datetime.now(timezone.utc),
            **kwargs
        )

    def test_build_action_plan_requires_admitted_signal(self):
        """Builder rejects unadmitted signals."""
        signal = self._create_test_signal(
            lifecycle_state="draft"
        )

        with self.assertRaises(ValueError) as ctx:
            build_action_plan(signal)

        self.assertIn("unadmitted signal", str(ctx.exception).lower())
        self.assertIn("prototype_passed", str(ctx.exception))

    def test_build_action_plan_rejects_rejected_signal(self):
        """Builder rejects rejected signals."""
        signal = self._create_test_signal(
            lifecycle_state="rejected"
        )

        with self.assertRaises(ValueError) as ctx:
            build_action_plan(signal)

        self.assertIn("unadmitted signal", str(ctx.exception).lower())

    def test_build_action_plan_rejects_needs_review_signal(self):
        """Builder rejects needs_review signals."""
        signal = self._create_test_signal(
            lifecycle_state="needs_review"
        )

        with self.assertRaises(ValueError) as ctx:
            build_action_plan(signal)

        self.assertIn("unadmitted signal", str(ctx.exception).lower())

    def test_build_action_plan_for_admitted_signal_returns_checks(self):
        """Builder returns ActionPlan with checks for admitted signal."""
        signal = self._create_test_signal(
            lifecycle_state="prototype_passed",
            intended_execution_date=date.today()
        )

        plan = build_action_plan(signal, today=date.today())

        # Basic fields
        self.assertEqual(plan.signal_id, signal.signal_id)
        self.assertEqual(plan.strategy_id, signal.strategy_id)
        self.assertEqual(plan.planned_action, signal.planned_action)

        # Pre-action checks (6 required)
        self.assertEqual(len(plan.pre_action_checks), 6)
        check_ids = [c.check_id for c in plan.pre_action_checks]
        self.assertIn("admission_check", check_ids)
        self.assertIn("freshness_check", check_ids)
        self.assertIn("evidence_check", check_ids)
        self.assertIn("risk_flags_check", check_ids)
        self.assertIn("snapshot_linkage_check", check_ids)
        self.assertIn("strategy_revision_check", check_ids)

        # Invalidation checks (4 required)
        self.assertEqual(len(plan.invalidation_checks), 4)
        invalidation_ids = [c.check_id for c in plan.invalidation_checks]
        self.assertIn("expired_signal", invalidation_ids)
        self.assertIn("blocked_by_evidence", invalidation_ids)
        self.assertIn("already_ignored", invalidation_ids)
        self.assertIn("already_expired", invalidation_ids)

        # No user decision yet
        self.assertIsNone(plan.user_decision)

    def test_freshness_fresh_when_today_equals_intended_date(self):
        """Freshness is fresh when today == intended_execution_date."""
        intended_date = date.today()
        signal = self._create_test_signal(
            intended_execution_date=intended_date
        )

        plan = build_action_plan(signal, today=intended_date)

        self.assertEqual(plan.freshness_status, "fresh")
        self.assertEqual(plan.status, "ready_for_human")

        # Freshness check should pass
        freshness_check = next(c for c in plan.pre_action_checks if c.check_id == "freshness_check")
        self.assertEqual(freshness_check.status, "pass")
        self.assertFalse(freshness_check.blocking)

    def test_freshness_fresh_when_today_before_intended_date(self):
        """Freshness is fresh when today < intended_execution_date."""
        intended_date = date.today() + timedelta(days=1)
        signal = self._create_test_signal(
            intended_execution_date=intended_date
        )

        plan = build_action_plan(signal, today=date.today())

        self.assertEqual(plan.freshness_status, "fresh")
        self.assertEqual(plan.status, "ready_for_human")

    def test_freshness_stale_when_one_day_past(self):
        """Freshness is stale when today == intended_date + 1 day."""
        intended_date = date.today() - timedelta(days=1)
        signal = self._create_test_signal(
            intended_execution_date=intended_date
        )

        plan = build_action_plan(signal, today=date.today())

        self.assertEqual(plan.freshness_status, "stale")
        self.assertEqual(plan.status, "ready_for_human")  # Stale doesn't block

        # Freshness check should warn but not block
        freshness_check = next(c for c in plan.pre_action_checks if c.check_id == "freshness_check")
        self.assertEqual(freshness_check.status, "warning")
        self.assertFalse(freshness_check.blocking)

    def test_freshness_expired_when_two_days_past(self):
        """Freshness is expired when today > intended_date + 1 day."""
        intended_date = date.today() - timedelta(days=2)
        signal = self._create_test_signal(
            intended_execution_date=intended_date
        )

        plan = build_action_plan(signal, today=date.today())

        self.assertEqual(plan.freshness_status, "expired")
        self.assertEqual(plan.status, "expired")  # Expired blocks execution

        # Freshness check should block
        freshness_check = next(c for c in plan.pre_action_checks if c.check_id == "freshness_check")
        self.assertEqual(freshness_check.status, "blocked")
        self.assertTrue(freshness_check.blocking)

        # Expired invalidation check should block
        expired_check = next(c for c in plan.invalidation_checks if c.check_id == "expired_signal")
        self.assertEqual(expired_check.status, "blocked")
        self.assertTrue(expired_check.blocking)

    def test_blocking_rule_evidence_blocked(self):
        """ActionPlan is expired when evidence_status == blocked."""
        signal = self._create_test_signal(
            evidence_status="blocked",
            risk_flags=["suspended"]
        )

        plan = build_action_plan(signal)

        self.assertEqual(plan.status, "expired")

        # Evidence check should block
        evidence_check = next(c for c in plan.pre_action_checks if c.check_id == "evidence_check")
        self.assertEqual(evidence_check.status, "blocked")
        self.assertTrue(evidence_check.blocking)

        # Blocked by evidence invalidation check should block
        blocked_check = next(c for c in plan.invalidation_checks if c.check_id == "blocked_by_evidence")
        self.assertEqual(blocked_check.status, "blocked")
        self.assertTrue(blocked_check.blocking)

    def test_blocking_rule_review_status_ignored(self):
        """ActionPlan is expired when review_status == ignored."""
        signal = self._create_test_signal(
            review_status="ignored",
            rejection_reason="Low liquidity"
        )

        plan = build_action_plan(signal)

        self.assertEqual(plan.status, "expired")

        # Already ignored invalidation check should block
        ignored_check = next(c for c in plan.invalidation_checks if c.check_id == "already_ignored")
        self.assertEqual(ignored_check.status, "blocked")
        self.assertTrue(ignored_check.blocking)

    def test_blocking_rule_review_status_expired(self):
        """ActionPlan is expired when review_status == expired."""
        signal = self._create_test_signal(
            review_status="expired"
        )

        plan = build_action_plan(signal)

        self.assertEqual(plan.status, "expired")

        # Already expired invalidation check should block
        expired_check = next(c for c in plan.invalidation_checks if c.check_id == "already_expired")
        self.assertEqual(expired_check.status, "blocked")
        self.assertTrue(expired_check.blocking)

    def test_warning_rule_evidence_warning(self):
        """ActionPlan shows warning when evidence_status == warning."""
        signal = self._create_test_signal(
            evidence_status="warning",
            risk_flags=["ST", "low_liquidity"]
        )

        plan = build_action_plan(signal)

        self.assertEqual(plan.status, "ready_for_human")  # Warning doesn't block

        # Evidence check should warn but not block
        evidence_check = next(c for c in plan.pre_action_checks if c.check_id == "evidence_check")
        self.assertEqual(evidence_check.status, "warning")
        self.assertFalse(evidence_check.blocking)

        # Risk warnings present
        self.assertGreater(len(plan.risk_warnings), 0)
        self.assertTrue(any("ST" in w for w in plan.risk_warnings))

    def test_warning_rule_risk_flags_present(self):
        """ActionPlan shows warning when risk_flags is not empty."""
        signal = self._create_test_signal(
            evidence_status="warning",
            risk_flags=["limit_up", "low_liquidity"]
        )

        plan = build_action_plan(signal)

        # Risk flags check should warn
        risk_check = next(c for c in plan.pre_action_checks if c.check_id == "risk_flags_check")
        self.assertEqual(risk_check.status, "warning")
        self.assertFalse(risk_check.blocking)

        # Risk warnings present
        self.assertGreater(len(plan.risk_warnings), 0)

    def test_warning_rule_missing_quantity(self):
        """ActionPlan shows warning when quantity is None."""
        signal = self._create_test_signal(
            quantity=None
        )

        plan = build_action_plan(signal)

        self.assertEqual(plan.status, "ready_for_human")  # Warning doesn't block
        self.assertTrue(any("数量" in w for w in plan.risk_warnings))

    def test_warning_rule_missing_price(self):
        """ActionPlan shows warning when current_price is None."""
        signal = self._create_test_signal(
            current_price=None
        )

        plan = build_action_plan(signal)

        self.assertEqual(plan.status, "ready_for_human")
        self.assertTrue(any("价格" in w for w in plan.risk_warnings))

    def test_action_plan_includes_execution_window(self):
        """ActionPlan includes execution window with planned/valid/expires dates."""
        intended_date = date.today() + timedelta(days=1)
        signal = self._create_test_signal(
            intended_execution_date=intended_date
        )

        plan = build_action_plan(signal, today=date.today())

        self.assertEqual(plan.execution_window.planned_date, intended_date)
        self.assertEqual(plan.execution_window.valid_for_date, intended_date)
        self.assertEqual(plan.execution_window.expires_after_date, intended_date + timedelta(days=1))

    def test_action_plan_does_not_include_order_fields(self):
        """ActionPlan model does not have order/broker/fill fields."""
        signal = self._create_test_signal()

        plan = build_action_plan(signal)

        # Verify no forbidden fields exist
        plan_dict = plan.model_dump()
        forbidden_fields = ["order_id", "broker", "fill_price", "fill_quantity", "realized_pnl"]
        for field in forbidden_fields:
            self.assertNotIn(field, plan_dict)

    def test_builder_is_deterministic(self):
        """Builder produces same ActionPlan for same input (except timestamps and UUIDs)."""
        signal = self._create_test_signal()
        today = date.today()

        plan1 = build_action_plan(signal, today=today)
        plan2 = build_action_plan(signal, today=today)

        # Same deterministic fields
        self.assertEqual(plan1.signal_id, plan2.signal_id)
        self.assertEqual(plan1.freshness_status, plan2.freshness_status)
        self.assertEqual(plan1.status, plan2.status)
        self.assertEqual(len(plan1.pre_action_checks), len(plan2.pre_action_checks))
        self.assertEqual(len(plan1.invalidation_checks), len(plan2.invalidation_checks))

        # Check IDs match (deterministic)
        check1_ids = [c.check_id for c in plan1.pre_action_checks]
        check2_ids = [c.check_id for c in plan2.pre_action_checks]
        self.assertEqual(check1_ids, check2_ids)


if __name__ == "__main__":
    unittest.main()
