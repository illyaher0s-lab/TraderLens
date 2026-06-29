"""
V1 Approval Card Tests

Tests for result-level approval card contract and reducer.

Hard requirements:
1. Allowed decisions are exactly: continue, stop, downgrade_to_observation,
   enter_risk_capped_live_execution, accept_execution_record_interpretation
2. Approval cards cannot ask for technical decisions:
   - candidate pool technical quality
   - strategy parameters
   - OOS windows
   - thresholds
   - stop-loss
   - liquidity rules
   - manual execution fields
3. Reducer must be deterministic
4. Every approval card requires at least one artifact_id
"""

import unittest
from datetime import datetime, timezone

from contracts.approval_card import ApprovalCard, ApprovalDecision
from backend.services.approval_card_reducer import (
    create_approval_card,
    apply_decision,
    validate_decision,
)


class TestApprovalCardContract(unittest.TestCase):
    """Test ApprovalCard contract structure."""

    def test_approval_card_has_required_fields(self):
        """ApprovalCard must have all required fields."""
        now = datetime.now(timezone.utc)
        card = ApprovalCard(
            approval_card_id="card_001",
            workflow_id="workflow_001",
            stage="research_confirmation",
            title="Research Confirmation",
            plain_language_summary="Company looks promising, continue research?",
            allowed_decisions=["continue", "stop"],
            blocked_technical_decisions=[
                "candidate_pool_technical_quality",
                "strategy_parameters",
            ],
            artifact_ids=["research_001"],
            created_at=now,
            decided_at=None,
            decision=None,
            decided_by=None,
        )

        self.assertEqual(card.approval_card_id, "card_001")
        self.assertEqual(card.workflow_id, "workflow_001")
        self.assertEqual(card.stage, "research_confirmation")
        self.assertEqual(card.title, "Research Confirmation")
        self.assertIsNotNone(card.plain_language_summary)
        self.assertIsInstance(card.allowed_decisions, list)
        self.assertIsInstance(card.blocked_technical_decisions, list)
        self.assertIsInstance(card.artifact_ids, list)
        self.assertEqual(card.created_at, now)
        self.assertIsNone(card.decided_at)
        self.assertIsNone(card.decision)
        self.assertIsNone(card.decided_by)

    def test_approval_card_requires_artifact_ids(self):
        """ApprovalCard must have at least one artifact_id."""
        now = datetime.now(timezone.utc)

        # Empty artifact_ids should fail
        with self.assertRaises(ValueError) as ctx:
            ApprovalCard(
                approval_card_id="card_002",
                workflow_id="workflow_001",
                stage="research_confirmation",
                title="Research Confirmation",
                plain_language_summary="Summary",
                allowed_decisions=["continue"],
                blocked_technical_decisions=[],
                artifact_ids=[],  # Empty - should fail
                created_at=now,
                decided_at=None,
                decision=None,
                decided_by=None,
            )

        self.assertIn("artifact_ids", str(ctx.exception).lower())


class TestApprovalDecision(unittest.TestCase):
    """Test allowed approval decisions."""

    def test_only_allowed_decisions(self):
        """Only these decisions are allowed."""
        allowed = [
            "continue",
            "stop",
            "downgrade_to_observation",
            "enter_risk_capped_live_execution",
            "accept_execution_record_interpretation",
        ]

        for decision in allowed:
            # Should not raise
            validated = ApprovalDecision(decision)
            self.assertEqual(validated, decision)

    def test_unknown_decision_rejected(self):
        """Unknown decisions must be rejected."""
        forbidden = [
            "approve",
            "reject",
            "execute",
            "buy",
            "sell",
            "set_threshold",
        ]

        for decision in forbidden:
            with self.assertRaises(ValueError) as ctx:
                ApprovalDecision(decision)
            self.assertIn("unknown decision", str(ctx.exception).lower())


class TestBlockedTechnicalDecisions(unittest.TestCase):
    """Test that technical decisions are blocked."""

    def test_forbidden_technical_decisions(self):
        """These technical decisions must be blocked."""
        forbidden_technical = [
            "candidate_pool_technical_quality",
            "strategy_parameters",
            "oos_windows",
            "thresholds",
            "stop_loss",
            "liquidity_rules",
            "manual_execution_fields",
        ]

        now = datetime.now(timezone.utc)
        card = ApprovalCard(
            approval_card_id="card_003",
            workflow_id="workflow_001",
            stage="validation_gate",
            title="Validation Result",
            plain_language_summary="Strategy passed validation",
            allowed_decisions=["continue", "stop"],
            blocked_technical_decisions=forbidden_technical,
            artifact_ids=["validation_report_001"],
            created_at=now,
            decided_at=None,
            decision=None,
            decided_by=None,
        )

        # All forbidden technical decisions must be in blocked list
        for tech_decision in forbidden_technical:
            self.assertIn(tech_decision, card.blocked_technical_decisions)

    def test_technical_decision_labels_rejected(self):
        """Reducer must reject technical decision labels."""
        # If someone tries to add a technical decision to allowed_decisions
        with self.assertRaises(ValueError) as ctx:
            validate_decision(
                allowed_decisions=["continue", "stop"],
                blocked_technical_decisions=["strategy_parameters"],
                proposed_decision="strategy_parameters",
            )

        self.assertIn("blocked", str(ctx.exception).lower())


class TestApprovalCardReducer(unittest.TestCase):
    """Test approval card reducer."""

    def test_create_approval_card_requires_artifact_id(self):
        """Reducer rejects creating card without artifact_id."""
        with self.assertRaises(ValueError) as ctx:
            create_approval_card(
                workflow_id="workflow_001",
                stage="research_confirmation",
                title="Research Confirmation",
                plain_language_summary="Summary",
                allowed_decisions=["continue", "stop"],
                artifact_ids=[],  # No artifacts - should fail
            )

        self.assertIn("artifact_id", str(ctx.exception).lower())

    def test_create_approval_card_deterministic(self):
        """Reducer produces deterministic approval_card_id."""
        now = datetime(2026, 6, 29, 12, 0, 0, tzinfo=timezone.utc)

        card1 = create_approval_card(
            workflow_id="workflow_001",
            stage="research_confirmation",
            title="Research Confirmation",
            plain_language_summary="Summary",
            allowed_decisions=["continue", "stop"],
            artifact_ids=["research_001"],
            created_at=now,
        )

        card2 = create_approval_card(
            workflow_id="workflow_001",
            stage="research_confirmation",
            title="Research Confirmation",
            plain_language_summary="Summary",
            allowed_decisions=["continue", "stop"],
            artifact_ids=["research_001"],
            created_at=now,
        )

        # Same input produces same approval_card_id
        self.assertEqual(card1.approval_card_id, card2.approval_card_id)
        self.assertEqual(card1.created_at, card2.created_at)

    def test_apply_decision_updates_card(self):
        """Applying decision updates card state."""
        now = datetime(2026, 6, 29, 12, 0, 0, tzinfo=timezone.utc)
        decided_at = datetime(2026, 6, 29, 13, 0, 0, tzinfo=timezone.utc)

        card = create_approval_card(
            workflow_id="workflow_001",
            stage="research_confirmation",
            title="Research Confirmation",
            plain_language_summary="Summary",
            allowed_decisions=["continue", "stop"],
            artifact_ids=["research_001"],
            created_at=now,
        )

        updated_card = apply_decision(
            card=card,
            decision="continue",
            decided_by="user",
            decided_at=decided_at,
        )

        self.assertEqual(updated_card.decision, "continue")
        self.assertEqual(updated_card.decided_by, "user")
        self.assertEqual(updated_card.decided_at, decided_at)

    def test_apply_unknown_decision_rejected(self):
        """Applying unknown decision is rejected."""
        now = datetime.now(timezone.utc)
        card = create_approval_card(
            workflow_id="workflow_001",
            stage="research_confirmation",
            title="Research Confirmation",
            plain_language_summary="Summary",
            allowed_decisions=["continue", "stop"],
            artifact_ids=["research_001"],
            created_at=now,
        )

        with self.assertRaises(ValueError) as ctx:
            apply_decision(
                card=card,
                decision="execute_immediately",  # Not in allowed_decisions
                decided_by="user",
                decided_at=now,
            )

        self.assertIn("not allowed", str(ctx.exception).lower())

    def test_reducer_does_not_call_llm(self):
        """Reducer must be deterministic and not call LLM."""
        # This is a structural test: reducer functions should not have
        # any LLM client imports or calls
        import backend.services.approval_card_reducer as reducer_module
        import inspect

        source = inspect.getsource(reducer_module)

        # Should not import OpenAI, Anthropic, or any LLM client
        self.assertNotIn("openai", source.lower())
        self.assertNotIn("anthropic", source.lower())
        self.assertNotIn("llm", source.lower())
        self.assertNotIn("gpt", source.lower())
        self.assertNotIn("claude", source.lower())

    def test_reducer_does_not_call_tushare(self):
        """Reducer must not call Tushare."""
        import backend.services.approval_card_reducer as reducer_module
        import inspect

        source = inspect.getsource(reducer_module)

        # Should not import Tushare
        self.assertNotIn("tushare", source.lower())

    def test_reducer_does_not_call_db(self):
        """Reducer must not call database."""
        import backend.services.approval_card_reducer as reducer_module
        import inspect

        source = inspect.getsource(reducer_module)

        # Should not import DB modules
        self.assertNotIn("backend.db", source)
        self.assertNotIn("from db import", source)


if __name__ == "__main__":
    unittest.main()
