"""
C3 Action Plan Boundary Tests

Tests for Action Plan builder and API boundary enforcement.

C3-2 scope:
- Builder logic tests (freshness, blocking, warning rules)
- Admission enforcement tests
- Deterministic generation tests

C3-3 scope:
- API endpoint tests (GET/POST action-plan)
- Direct-id bypass tests
- Decision validation tests
- Forbidden fields tests
"""

import unittest
from datetime import date, datetime, timedelta, timezone
import tempfile
import os

from contracts.signal_board import PlannedSignal
from backend.services.action_plan_builder import build_action_plan
from backend.db.signal_board import SignalBoardDB
from backend.api.signal_board import router, init_signal_board_api
from fastapi.testclient import TestClient
from fastapi import FastAPI


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
        """ActionPlan shows blocking check when evidence_status == blocked."""
        signal = self._create_test_signal(
            evidence_status="blocked",
            risk_flags=["suspended"]
        )

        plan = build_action_plan(signal)

        # Status is ready_for_human (blocking represented by checks, not status)
        self.assertEqual(plan.status, "ready_for_human")

        # Evidence check should block
        evidence_check = next(c for c in plan.pre_action_checks if c.check_id == "evidence_check")
        self.assertEqual(evidence_check.status, "blocked")
        self.assertTrue(evidence_check.blocking)

        # Blocked by evidence invalidation check should block
        blocked_check = next(c for c in plan.invalidation_checks if c.check_id == "blocked_by_evidence")
        self.assertEqual(blocked_check.status, "blocked")
        self.assertTrue(blocked_check.blocking)

    def test_blocking_rule_review_status_ignored(self):
        """ActionPlan shows blocking check when review_status == ignored."""
        signal = self._create_test_signal(
            review_status="ignored",
            rejection_reason="Low liquidity"
        )

        plan = build_action_plan(signal)

        # Status is ready_for_human (blocking represented by checks, not status)
        self.assertEqual(plan.status, "ready_for_human")

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
        """Builder produces identical ActionPlan for same input (signal, today, now)."""
        signal = self._create_test_signal()
        today = date.today()
        now = datetime(2026, 6, 28, 12, 0, 0, tzinfo=timezone.utc)

        plan1 = build_action_plan(signal, today=today, now=now)
        plan2 = build_action_plan(signal, today=today, now=now)

        # Full equality including action_plan_id and timestamps
        plan1_dict = plan1.model_dump()
        plan2_dict = plan2.model_dump()

        self.assertEqual(plan1_dict, plan2_dict)

        # Verify deterministic ID
        self.assertEqual(plan1.action_plan_id, plan2.action_plan_id)
        self.assertTrue(plan1.action_plan_id.startswith("ap_"))

        # Verify deterministic timestamps
        self.assertEqual(plan1.created_at, plan2.created_at)
        self.assertEqual(plan1.updated_at, plan2.updated_at)
        self.assertEqual(plan1.created_at, now)
        self.assertEqual(plan1.updated_at, now)


class TestActionPlanAPI(unittest.TestCase):
    """Tests for Action Plan API endpoints (C3-3)."""

    def setUp(self):
        """Set up test database and API client."""
        self.db_fd, self.db_path = tempfile.mkstemp()
        self.db = SignalBoardDB(self.db_path)

        # Initialize API
        init_signal_board_api(self.db_path)

        # Create FastAPI app with router
        app = FastAPI()
        app.include_router(router)
        self.client = TestClient(app)

    def tearDown(self):
        """Clean up test database."""
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def _create_test_signal(
        self,
        signal_id: str = "test-signal-api",
        lifecycle_state: str = "prototype_passed",
        evidence_status: str = "clean",
        review_status: str = "pending",
        intended_execution_date: date | None = None,
        **kwargs
    ) -> PlannedSignal:
        """Create and insert test signal."""
        if intended_execution_date is None:
            intended_execution_date = date.today() + timedelta(days=1)

        signal = PlannedSignal(
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
            quantity=100,
            trigger_reason="Test trigger",
            review_status=review_status,
            reviewed_at=None,
            reviewed_by=None,
            rejection_reason=None,
            current_price=100.0,
            position_before=0,
            created_at=datetime.now(timezone.utc),
            metadata={},
            risk_flags=[],
            evidence_status=evidence_status,
            evidence_checked_at=datetime.now(timezone.utc),
            **kwargs
        )
        self.db.create_signal(signal)
        return signal

    def test_get_action_plan_requires_admitted_signal(self):
        """GET action-plan returns 404 for unadmitted signals."""
        # Create draft signal
        signal = self._create_test_signal(
            signal_id="draft-signal",
            lifecycle_state="draft"
        )

        response = self.client.get(f"/api/signals/draft-signal/action-plan")

        self.assertEqual(response.status_code, 404)

    def test_get_action_plan_rejects_rejected_signal(self):
        """GET action-plan returns 404 for rejected signals."""
        signal = self._create_test_signal(
            signal_id="rejected-signal",
            lifecycle_state="rejected"
        )

        response = self.client.get(f"/api/signals/rejected-signal/action-plan")

        self.assertEqual(response.status_code, 404)

    def test_get_action_plan_rejects_needs_review_signal(self):
        """GET action-plan returns 404 for needs_review signals."""
        signal = self._create_test_signal(
            signal_id="needs-review-signal",
            lifecycle_state="needs_review"
        )

        response = self.client.get(f"/api/signals/needs-review-signal/action-plan")

        self.assertEqual(response.status_code, 404)

    def test_get_action_plan_for_admitted_signal_returns_checks(self):
        """GET action-plan returns 200 with checks for admitted signal."""
        signal = self._create_test_signal()

        response = self.client.get(f"/api/signals/{signal.signal_id}/action-plan")

        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Contains signal_id
        self.assertEqual(data["signal_id"], signal.signal_id)

        # Contains pre_action_checks
        self.assertIn("pre_action_checks", data)
        self.assertEqual(len(data["pre_action_checks"]), 6)

        # Contains invalidation_checks
        self.assertIn("invalidation_checks", data)
        self.assertEqual(len(data["invalidation_checks"]), 4)

        # No user_decision yet
        self.assertIsNone(data["user_decision"])

    def test_post_action_decision_skip_requires_reason(self):
        """POST decision returns 400 if skip without reason."""
        signal = self._create_test_signal()

        response = self.client.post(
            f"/api/signals/{signal.signal_id}/action-plan/decision",
            json={
                "decision": "skip",
                "decided_by": "trader1"
            }
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("reason", response.json()["detail"].lower())

    def test_post_action_decision_partial_requires_reason(self):
        """POST decision returns 400 if partial without reason."""
        signal = self._create_test_signal()

        response = self.client.post(
            f"/api/signals/{signal.signal_id}/action-plan/decision",
            json={
                "decision": "partial",
                "decided_by": "trader1"
            }
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("reason", response.json()["detail"].lower())

    def test_post_action_decision_expired_requires_reason(self):
        """POST decision returns 400 if expired without reason."""
        signal = self._create_test_signal()

        response = self.client.post(
            f"/api/signals/{signal.signal_id}/action-plan/decision",
            json={
                "decision": "expired",
                "decided_by": "trader1"
            }
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("reason", response.json()["detail"].lower())

    def test_post_action_decision_does_not_accept_order_fields(self):
        """POST decision ignores broker/order/fill fields if present."""
        signal = self._create_test_signal()

        # Attempt to send forbidden fields
        response = self.client.post(
            f"/api/signals/{signal.signal_id}/action-plan/decision",
            json={
                "decision": "execute",
                "decided_by": "trader1",
                "order_id": "order-123",  # Forbidden
                "broker": "broker-x",  # Forbidden
                "fill_price": 100.5,  # Forbidden
                "fill_qty": 100,  # Forbidden
                "realized_pnl": 500.0  # Forbidden
            }
        )

        # Should succeed (fields ignored)
        self.assertEqual(response.status_code, 200)

        # Verify no forbidden fields stored in decision
        decision_record = self.db.get_action_plan_decision(response.json()["action_plan_id"])
        self.assertIsNotNone(decision_record)
        self.assertNotIn("order_id", decision_record)
        self.assertNotIn("broker", decision_record)
        self.assertNotIn("fill_price", decision_record)
        self.assertNotIn("fill_qty", decision_record)
        self.assertNotIn("realized_pnl", decision_record)

    def test_post_action_decision_updates_review_status_mapping(self):
        """POST decision maps to correct review_status."""
        # Test execute -> watching
        signal1 = self._create_test_signal(signal_id="signal-execute")
        response = self.client.post(
            f"/api/signals/signal-execute/action-plan/decision",
            json={"decision": "execute", "decided_by": "trader1"}
        )
        self.assertEqual(response.status_code, 200)
        signal_after = self.db.get_signal("signal-execute")
        self.assertEqual(signal_after.review_status, "watching")

        # Test partial -> watching
        signal2 = self._create_test_signal(signal_id="signal-partial")
        response = self.client.post(
            f"/api/signals/signal-partial/action-plan/decision",
            json={"decision": "partial", "decided_by": "trader1", "reason": "Only 50 shares"}
        )
        self.assertEqual(response.status_code, 200)
        signal_after = self.db.get_signal("signal-partial")
        self.assertEqual(signal_after.review_status, "watching")

        # Test skip -> ignored
        signal3 = self._create_test_signal(signal_id="signal-skip")
        response = self.client.post(
            f"/api/signals/signal-skip/action-plan/decision",
            json={"decision": "skip", "decided_by": "trader1", "reason": "Low liquidity"}
        )
        self.assertEqual(response.status_code, 200)
        signal_after = self.db.get_signal("signal-skip")
        self.assertEqual(signal_after.review_status, "ignored")

        # Test expired -> expired
        signal4 = self._create_test_signal(signal_id="signal-expired")
        response = self.client.post(
            f"/api/signals/signal-expired/action-plan/decision",
            json={"decision": "expired", "decided_by": "trader1", "reason": "Too late"}
        )
        self.assertEqual(response.status_code, 200)
        signal_after = self.db.get_signal("signal-expired")
        self.assertEqual(signal_after.review_status, "expired")

    def test_post_action_decision_rejects_unadmitted_direct_id(self):
        """POST decision returns 404 for unadmitted signals."""
        signal = self._create_test_signal(
            signal_id="unadmitted-decision",
            lifecycle_state="draft"
        )

        response = self.client.post(
            f"/api/signals/unadmitted-decision/action-plan/decision",
            json={"decision": "execute", "decided_by": "trader1"}
        )

        self.assertEqual(response.status_code, 404)

    def test_post_action_decision_rejects_execute_on_expired(self):
        """Cannot execute expired Action Plan."""
        from datetime import date, timedelta

        signal = self._create_test_signal(
            signal_id="expired-execute",
            intended_execution_date=date.today() - timedelta(days=2)  # Expired
        )

        response = self.client.post(
            f"/api/signals/expired-execute/action-plan/decision",
            json={"decision": "execute", "decided_by": "trader1"}
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("blocked or expired", response.json()["detail"].lower())

    def test_post_action_decision_rejects_partial_on_expired(self):
        """Cannot partially execute expired Action Plan."""
        from datetime import date, timedelta

        signal = self._create_test_signal(
            signal_id="expired-partial",
            intended_execution_date=date.today() - timedelta(days=2)  # Expired
        )

        response = self.client.post(
            f"/api/signals/expired-partial/action-plan/decision",
            json={"decision": "partial", "decided_by": "trader1", "reason": "Trying anyway"}
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("blocked or expired", response.json()["detail"].lower())

    def test_post_action_decision_rejects_execute_on_evidence_blocked(self):
        """Cannot execute Action Plan with blocked evidence."""
        signal = self._create_test_signal(
            signal_id="evidence-blocked-execute",
            evidence_status="blocked"
        )

        response = self.client.post(
            f"/api/signals/evidence-blocked-execute/action-plan/decision",
            json={"decision": "execute", "decided_by": "trader1"}
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("blocked or expired", response.json()["detail"].lower())

    def test_post_action_decision_rejects_partial_on_evidence_blocked(self):
        """Cannot partially execute Action Plan with blocked evidence."""
        signal = self._create_test_signal(
            signal_id="evidence-blocked-partial",
            evidence_status="blocked"
        )

        response = self.client.post(
            f"/api/signals/evidence-blocked-partial/action-plan/decision",
            json={"decision": "partial", "decided_by": "trader1", "reason": "Trying anyway"}
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("blocked or expired", response.json()["detail"].lower())

    def test_post_action_decision_allows_skip_on_blocked(self):
        """Can skip blocked Action Plan."""
        signal = self._create_test_signal(
            signal_id="blocked-skip",
            evidence_status="blocked"
        )

        response = self.client.post(
            f"/api/signals/blocked-skip/action-plan/decision",
            json={"decision": "skip", "decided_by": "trader1", "reason": "Evidence blocked"}
        )

        self.assertEqual(response.status_code, 200)

    def test_post_action_decision_allows_expired_on_expired_plan(self):
        """Can mark expired Action Plan as expired."""
        from datetime import date, timedelta

        signal = self._create_test_signal(
            signal_id="expired-mark-expired",
            intended_execution_date=date.today() - timedelta(days=2)  # Expired
        )

        response = self.client.post(
            f"/api/signals/expired-mark-expired/action-plan/decision",
            json={"decision": "expired", "decided_by": "trader1", "reason": "Too late"}
        )

        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
