"""
V1 Agent Workbench DB Tests

Tests for agent workbench persistence layer.

Requirements:
- Store conversation-driven workflow timeline
- Preserve messages, artifact refs, approval cards in insertion order
- Reject technical approval payloads
- No LLM, no Tushare, no trading logic
"""

import unittest
import tempfile
import os
from datetime import datetime, timezone

from contracts.agent_workbench import (
    WorkflowKind,
    WorkflowState,
    AgentSession,
    AgentMessage,
    ArtifactRef,
)
from contracts.approval_card import ApprovalCard
from backend.db.agent_workbench import (
    init_agent_workbench_db,
    create_session,
    get_session,
    append_message,
    list_messages,
    attach_artifact_ref,
    list_artifact_refs,
    attach_approval_card,
    list_approval_cards,
    get_session_timeline,
)


class TestAgentWorkbenchDB(unittest.TestCase):
    """Test agent workbench database operations."""

    def setUp(self):
        """Set up test database."""
        self.db_fd, self.db_path = tempfile.mkstemp()
        import sqlite3
        self.conn = sqlite3.connect(self.db_path)
        init_agent_workbench_db(self.conn)

    def tearDown(self):
        """Clean up test database."""
        self.conn.close()
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def test_create_friend_stock_session(self):
        """Can create friend_stock session."""
        now = datetime(2026, 6, 29, 12, 0, 0, tzinfo=timezone.utc)
        session = AgentSession(
            session_id="session_001",
            workflow_kind=WorkflowKind.FRIEND_STOCK,
            workflow_state=WorkflowState.CREATED,
            title="Friend recommended stock",
            created_at=now,
            updated_at=now,
        )

        create_session(self.conn, session)
        retrieved = get_session(self.conn, "session_001")

        self.assertEqual(retrieved.session_id, "session_001")
        self.assertEqual(retrieved.workflow_kind, WorkflowKind.FRIEND_STOCK)
        self.assertEqual(retrieved.workflow_state, WorkflowState.CREATED)

    def test_create_strategy_idea_session(self):
        """Can create strategy_idea session."""
        now = datetime(2026, 6, 29, 12, 0, 0, tzinfo=timezone.utc)
        session = AgentSession(
            session_id="session_002",
            workflow_kind=WorkflowKind.STRATEGY_IDEA,
            workflow_state=WorkflowState.CREATED,
            title="Short-video strategy idea",
            created_at=now,
            updated_at=now,
        )

        create_session(self.conn, session)
        retrieved = get_session(self.conn, "session_002")

        self.assertEqual(retrieved.workflow_kind, WorkflowKind.STRATEGY_IDEA)

    def test_append_user_message(self):
        """Can append user message."""
        now = datetime(2026, 6, 29, 12, 0, 0, tzinfo=timezone.utc)
        session = AgentSession(
            session_id="session_003",
            workflow_kind=WorkflowKind.FRIEND_STOCK,
            workflow_state=WorkflowState.CREATED,
            title="Test",
            created_at=now,
            updated_at=now,
        )
        create_session(self.conn, session)

        message = AgentMessage(
            message_id="msg_001",
            session_id="session_003",
            role="user",
            content="My friend recommended this stock",
            created_at=now,
        )

        append_message(self.conn, message)
        messages = list_messages(self.conn, "session_003")

        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].role, "user")
        self.assertEqual(messages[0].content, "My friend recommended this stock")

    def test_append_agent_message(self):
        """Can append agent message."""
        now = datetime(2026, 6, 29, 12, 0, 0, tzinfo=timezone.utc)
        session = AgentSession(
            session_id="session_004",
            workflow_kind=WorkflowKind.FRIEND_STOCK,
            workflow_state=WorkflowState.CREATED,
            title="Test",
            created_at=now,
            updated_at=now,
        )
        create_session(self.conn, session)

        message = AgentMessage(
            message_id="msg_002",
            session_id="session_004",
            role="agent",
            content="Let me research that company",
            created_at=now,
        )

        append_message(self.conn, message)
        messages = list_messages(self.conn, "session_004")

        self.assertEqual(messages[0].role, "agent")

    def test_messages_in_insertion_order(self):
        """Retrieve messages in insertion order."""
        now = datetime(2026, 6, 29, 12, 0, 0, tzinfo=timezone.utc)
        session = AgentSession(
            session_id="session_005",
            workflow_kind=WorkflowKind.FRIEND_STOCK,
            workflow_state=WorkflowState.CREATED,
            title="Test",
            created_at=now,
            updated_at=now,
        )
        create_session(self.conn, session)

        msg1 = AgentMessage(
            message_id="msg_003",
            session_id="session_005",
            role="user",
            content="First message",
            created_at=now,
        )
        msg2 = AgentMessage(
            message_id="msg_004",
            session_id="session_005",
            role="agent",
            content="Second message",
            created_at=now,
        )

        append_message(self.conn, msg1)
        append_message(self.conn, msg2)
        messages = list_messages(self.conn, "session_005")

        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0].content, "First message")
        self.assertEqual(messages[1].content, "Second message")

    def test_reject_invalid_role(self):
        """Reject invalid role such as trader, llm, developer."""
        now = datetime(2026, 6, 29, 12, 0, 0, tzinfo=timezone.utc)

        invalid_roles = ["trader", "llm", "developer", "assistant", "tool"]

        for invalid_role in invalid_roles:
            with self.assertRaises(ValueError) as ctx:
                AgentMessage(
                    message_id="msg_invalid",
                    session_id="session_006",
                    role=invalid_role,
                    content="Invalid",
                    created_at=now,
                )

            self.assertIn("role", str(ctx.exception).lower())

    def test_attach_artifact_reference(self):
        """Can attach research/validation artifact IDs."""
        now = datetime(2026, 6, 29, 12, 0, 0, tzinfo=timezone.utc)
        session = AgentSession(
            session_id="session_007",
            workflow_kind=WorkflowKind.FRIEND_STOCK,
            workflow_state=WorkflowState.RESEARCHING,
            title="Test",
            created_at=now,
            updated_at=now,
        )
        create_session(self.conn, session)

        artifact_ref = ArtifactRef(
            artifact_ref_id="ref_001",
            session_id="session_007",
            artifact_id="research_report_001",
            artifact_type="research_report",
            created_at=now,
        )

        attach_artifact_ref(self.conn, artifact_ref)
        refs = list_artifact_refs(self.conn, "session_007")

        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0].artifact_id, "research_report_001")
        self.assertEqual(refs[0].artifact_type, "research_report")

    def test_artifact_ref_stores_reference_only(self):
        """Artifact ref stores reference only, not raw report body."""
        now = datetime(2026, 6, 29, 12, 0, 0, tzinfo=timezone.utc)
        artifact_ref = ArtifactRef(
            artifact_ref_id="ref_002",
            session_id="session_008",
            artifact_id="validation_report_001",
            artifact_type="validation_report",
            created_at=now,
        )

        # ArtifactRef should not have 'content' or 'body' field
        self.assertFalse(hasattr(artifact_ref, "content"))
        self.assertFalse(hasattr(artifact_ref, "body"))
        self.assertFalse(hasattr(artifact_ref, "report_data"))

    def test_attach_valid_approval_card(self):
        """Can attach valid result-level approval card."""
        now = datetime(2026, 6, 29, 12, 0, 0, tzinfo=timezone.utc)
        session = AgentSession(
            session_id="session_009",
            workflow_kind=WorkflowKind.FRIEND_STOCK,
            workflow_state=WorkflowState.WAITING_FOR_APPROVAL,
            title="Test",
            created_at=now,
            updated_at=now,
        )
        create_session(self.conn, session)

        approval_card = ApprovalCard(
            approval_card_id="approval_001",
            workflow_id="session_009",
            stage="research_confirmation",
            title="Research Confirmation",
            plain_language_summary="Company looks promising",
            allowed_decisions=["continue", "stop"],
            blocked_technical_decisions=["strategy_parameters"],
            artifact_ids=["research_report_001"],
            created_at=now,
            decided_at=None,
            decision=None,
            decided_by=None,
        )

        attach_approval_card(self.conn, "session_009", approval_card)
        cards = list_approval_cards(self.conn, "session_009")

        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0].approval_card_id, "approval_001")
        self.assertIn("research_report_001", cards[0].artifact_ids)

    def test_reject_approval_card_with_strategy_parameters(self):
        """Approval card with allowed_decisions=['strategy_parameters'] is rejected."""
        now = datetime(2026, 6, 29, 12, 0, 0, tzinfo=timezone.utc)

        with self.assertRaises(ValueError) as ctx:
            ApprovalCard(
                approval_card_id="approval_002",
                workflow_id="session_010",
                stage="validation",
                title="Validation",
                plain_language_summary="Summary",
                allowed_decisions=["strategy_parameters"],  # Technical decision
                blocked_technical_decisions=[],
                artifact_ids=["validation_001"],
                created_at=now,
                decided_at=None,
                decision=None,
                decided_by=None,
            )

        self.assertIn("technical", str(ctx.exception).lower())

    def test_reject_approval_card_with_thresholds(self):
        """Approval card with allowed_decisions=['thresholds'] is rejected."""
        now = datetime(2026, 6, 29, 12, 0, 0, tzinfo=timezone.utc)

        with self.assertRaises(ValueError) as ctx:
            ApprovalCard(
                approval_card_id="approval_003",
                workflow_id="session_011",
                stage="validation",
                title="Validation",
                plain_language_summary="Summary",
                allowed_decisions=["thresholds"],  # Technical decision
                blocked_technical_decisions=[],
                artifact_ids=["validation_001"],
                created_at=now,
                decided_at=None,
                decision=None,
                decided_by=None,
            )

        self.assertIn("technical", str(ctx.exception).lower())

    def test_reject_approval_card_with_position_sizing_formulas(self):
        """Approval card with allowed_decisions=['position_sizing_formulas'] is rejected."""
        now = datetime(2026, 6, 29, 12, 0, 0, tzinfo=timezone.utc)

        with self.assertRaises(ValueError) as ctx:
            ApprovalCard(
                approval_card_id="approval_004",
                workflow_id="session_012",
                stage="execution",
                title="Execution",
                plain_language_summary="Summary",
                allowed_decisions=["position_sizing_formulas"],  # Technical decision
                blocked_technical_decisions=[],
                artifact_ids=["execution_001"],
                created_at=now,
                decided_at=None,
                decision=None,
                decided_by=None,
            )

        self.assertIn("technical", str(ctx.exception).lower())

    def test_reject_approval_card_with_incomplete_market_data_usable(self):
        """Approval card with allowed_decisions=['incomplete_market_data_usable'] is rejected."""
        now = datetime(2026, 6, 29, 12, 0, 0, tzinfo=timezone.utc)

        with self.assertRaises(ValueError) as ctx:
            ApprovalCard(
                approval_card_id="approval_005",
                workflow_id="session_013",
                stage="execution",
                title="Execution",
                plain_language_summary="Summary",
                allowed_decisions=["incomplete_market_data_usable"],  # Technical decision
                blocked_technical_decisions=[],
                artifact_ids=["execution_001"],
                created_at=now,
                decided_at=None,
                decision=None,
                decided_by=None,
            )

        self.assertIn("technical", str(ctx.exception).lower())

    def test_session_timeline(self):
        """Retrieve full timeline in insertion order."""
        now = datetime(2026, 6, 29, 12, 0, 0, tzinfo=timezone.utc)

        # Create session
        session = AgentSession(
            session_id="session_014",
            workflow_kind=WorkflowKind.FRIEND_STOCK,
            workflow_state=WorkflowState.CREATED,
            title="Timeline Test",
            created_at=now,
            updated_at=now,
        )
        create_session(self.conn, session)

        # Append message
        msg = AgentMessage(
            message_id="msg_timeline_001",
            session_id="session_014",
            role="user",
            content="Test message",
            created_at=now,
        )
        append_message(self.conn, msg)

        # Attach artifact
        artifact = ArtifactRef(
            artifact_ref_id="ref_timeline_001",
            session_id="session_014",
            artifact_id="research_001",
            artifact_type="research_report",
            created_at=now,
        )
        attach_artifact_ref(self.conn, artifact)

        # Attach approval card
        approval = ApprovalCard(
            approval_card_id="approval_timeline_001",
            workflow_id="session_014",
            stage="research_confirmation",
            title="Confirmation",
            plain_language_summary="Summary",
            allowed_decisions=["continue", "stop"],
            blocked_technical_decisions=[],
            artifact_ids=["research_001"],
            created_at=now,
            decided_at=None,
            decision=None,
            decided_by=None,
        )
        attach_approval_card(self.conn, "session_014", approval)

        # Get timeline
        timeline = get_session_timeline(self.conn, "session_014")

        # Timeline should have 3 items in order
        self.assertEqual(len(timeline), 3)

        # First item is message
        self.assertEqual(timeline[0]["type"], "message")
        self.assertEqual(timeline[0]["content"]["content"], "Test message")

        # Second item is artifact_ref
        self.assertEqual(timeline[1]["type"], "artifact_ref")
        self.assertEqual(timeline[1]["content"]["artifact_id"], "research_001")

        # Third item is approval_card
        self.assertEqual(timeline[2]["type"], "approval_card")
        self.assertEqual(timeline[2]["content"]["approval_card_id"], "approval_timeline_001")

    def test_db_does_not_call_llm(self):
        """DB layer must not import or call LLM clients."""
        import backend.db.agent_workbench as db_module
        import inspect

        source = inspect.getsource(db_module)

        # Should not import OpenAI, Anthropic, or any LLM client
        self.assertNotIn("openai", source.lower())
        self.assertNotIn("anthropic", source.lower())
        self.assertNotIn("gpt", source.lower())
        self.assertNotIn("claude", source.lower())

    def test_db_does_not_call_tushare(self):
        """DB layer must not import Tushare."""
        import backend.db.agent_workbench as db_module
        import inspect

        source = inspect.getsource(db_module)

        # Should not import Tushare
        self.assertNotIn("tushare", source.lower())

    def test_db_does_not_call_strategy_validation(self):
        """DB layer must not import strategy validation services."""
        import backend.db.agent_workbench as db_module
        import inspect

        source = inspect.getsource(db_module)

        # Should not import strategy validation
        self.assertNotIn("strategy_promotion", source)
        self.assertNotIn("validation_gate", source)
        self.assertNotIn("recommendation_reducer", source)

    def test_db_does_not_call_random(self):
        """DB layer must not import random."""
        import backend.db.agent_workbench as db_module
        import inspect

        source = inspect.getsource(db_module)

        # Should not import random
        self.assertNotIn("import random", source)
        self.assertNotIn("from random import", source)


if __name__ == "__main__":
    unittest.main()
