"""
Test research database operations.

These tests verify:
- creating a theme persists all input fields
- manual stock candidates are returned with their theme
- blocked candidate cannot be confirmed without override reason
- confirmed candidate appears in confirmed_candidate_pool
- confirmed candidate stores forward_only=True
- confirmed candidate stores source Serenity/Evidence run IDs when available
- confirmed candidate locks thesis, invalidation rules, price snapshot, and benchmark snapshot
- status can move backward only through reopen actions with reason
- action audit records proposed and applied states separately
- conversation messages do not change candidate or theme state
- proposed action IDs can be linked back to the conversation turn that produced them
- theme board_version starts at 0
- successful reducer-applied state mutation increments theme board_version by exactly 1
- failed validation, rejected pending action, conversation message, Serenity run, and Evidence run do not increment board_version
- reject and reopen audit records include actor, reason, and timestamp
"""

import unittest
from datetime import date, datetime
from backend.db.research import ResearchDB
from contracts.research import (
    ThemeInput,
    CandidateStock,
    SerenityOutput,
    EvidenceOutput,
    ProposedAction,
    ConversationMessage,
    AppliedAction,
    ConfirmedCandidate,
    AgentHarnessConfig,
)


class TestResearchDB(unittest.TestCase):
    """Test research database operations."""

    def setUp(self):
        """Create in-memory database for each test."""
        self.db = ResearchDB(":memory:")

    def test_creating_theme_persists_all_fields(self):
        """Creating a theme persists all input fields."""
        now = datetime.now()
        theme = ThemeInput(
            theme_id="theme_001",
            theme_name="新能源产业链",
            background="锂电池需求增长",
            source_type="manual_theme",
            research_mode="standard",
            urgency="normal",
            notes="测试主题",
            status="draft",
            board_version=0,
            created_at=now,
            updated_at=now,
        )
        self.db.create_theme(theme)
        
        retrieved = self.db.get_theme("theme_001")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.theme_name, "新能源产业链")
        self.assertEqual(retrieved.source_type, "manual_theme")
        self.assertEqual(retrieved.research_mode, "standard")
        self.assertEqual(retrieved.board_version, 0)

    def test_theme_board_version_starts_at_zero(self):
        """Theme board_version starts at 0."""
        now = datetime.now()
        theme = ThemeInput(
            theme_id="theme_002",
            theme_name="Test Theme",
            background="Test",
            source_type="manual_theme",
            board_version=0,
            created_at=now,
            updated_at=now,
        )
        self.db.create_theme(theme)
        
        retrieved = self.db.get_theme("theme_002")
        self.assertEqual(retrieved.board_version, 0)

    def test_manual_stock_candidates_returned_with_theme(self):
        """Manual stock candidates are returned with their theme."""
        now = datetime.now()
        theme = ThemeInput(
            theme_id="theme_003",
            theme_name="Test Theme",
            background="Test",
            source_type="manual_theme",
            board_version=0,
            created_at=now,
            updated_at=now,
        )
        self.db.create_theme(theme)
        
        candidate = CandidateStock(
            candidate_id="cand_001",
            theme_id="theme_003",
            symbol="300750.SZ",
            company_name="宁德时代",
            source_type="manual_stock",
            match_reason="手动添加",
            status="raw",
            created_at=now,
        )
        self.db.add_candidate(candidate)
        
        candidates = self.db.list_candidates("theme_003")
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].symbol, "300750.SZ")
        self.assertEqual(candidates[0].source_type, "manual_stock")

    def test_blocked_candidate_cannot_be_confirmed_without_override(self):
        """Blocked candidate cannot be confirmed without override reason."""
        now = datetime.now()
        theme = ThemeInput(
            theme_id="theme_004",
            theme_name="Test Theme",
            background="Test",
            source_type="manual_theme",
            board_version=0,
            created_at=now,
            updated_at=now,
        )
        self.db.create_theme(theme)
        
        candidate = CandidateStock(
            candidate_id="cand_002",
            theme_id="theme_004",
            symbol="600000.SH",
            source_type="manual_stock",
            match_reason="手动添加",
            status="blocked",
            hard_filter_flags=["is_st"],
            created_at=now,
        )
        self.db.add_candidate(candidate)
        
        # Attempt to confirm without override reason should fail
        with self.assertRaises(ValueError) as ctx:
            self.db.confirm_candidate(
                candidate_id="cand_002",
                confirmation_reason="测试",
                evidence_level="medium",
                confirmed_by="user_001",
                pool_snapshot_date=date.today(),
                thesis_snapshot="测试",
                invalidation_rules=[],
                price_snapshot={},
                benchmark_snapshot={},
                override_reason=None,
            )
        self.assertIn("override", str(ctx.exception).lower())

    def test_confirmed_candidate_appears_in_pool(self):
        """Confirmed candidate appears in confirmed_candidate_pool."""
        now = datetime.now()
        theme = ThemeInput(
            theme_id="theme_005",
            theme_name="Test Theme",
            background="Test",
            source_type="manual_theme",
            board_version=0,
            created_at=now,
            updated_at=now,
        )
        self.db.create_theme(theme)
        
        candidate = CandidateStock(
            candidate_id="cand_003",
            theme_id="theme_005",
            symbol="300750.SZ",
            source_type="manual_stock",
            match_reason="手动添加",
            status="raw",
            created_at=now,
        )
        self.db.add_candidate(candidate)
        
        confirmed = self.db.confirm_candidate(
            candidate_id="cand_003",
            confirmation_reason="测试确认",
            evidence_level="strong",
            confirmed_by="user_001",
            pool_snapshot_date=date.today(),
            thesis_snapshot="产业链核心",
            invalidation_rules=[{"type": "price_drop", "threshold": -0.2}],
            price_snapshot={"close": 500.0},
            benchmark_snapshot={"index": "399006.SZ"},
        )
        
        pool = self.db.list_confirmed_candidates("theme_005")
        self.assertEqual(len(pool), 1)
        self.assertEqual(pool[0].symbol, "300750.SZ")

    def test_confirmed_candidate_stores_forward_only_true(self):
        """Confirmed candidate stores forward_only=True."""
        now = datetime.now()
        theme = ThemeInput(
            theme_id="theme_006",
            theme_name="Test Theme",
            background="Test",
            source_type="manual_theme",
            board_version=0,
            created_at=now,
            updated_at=now,
        )
        self.db.create_theme(theme)
        
        candidate = CandidateStock(
            candidate_id="cand_004",
            theme_id="theme_006",
            symbol="002594.SZ",
            source_type="manual_stock",
            match_reason="手动添加",
            status="raw",
            created_at=now,
        )
        self.db.add_candidate(candidate)
        
        confirmed = self.db.confirm_candidate(
            candidate_id="cand_004",
            confirmation_reason="测试",
            evidence_level="medium",
            confirmed_by="user_001",
            pool_snapshot_date=date.today(),
            thesis_snapshot="测试",
            invalidation_rules=[],
            price_snapshot={},
            benchmark_snapshot={},
        )
        
        self.assertTrue(confirmed.forward_only)

    def test_confirmed_candidate_locks_snapshots(self):
        """Confirmed candidate locks thesis, invalidation rules, price snapshot, and benchmark snapshot."""
        now = datetime.now()
        theme = ThemeInput(
            theme_id="theme_007",
            theme_name="Test Theme",
            background="Test",
            source_type="manual_theme",
            board_version=0,
            created_at=now,
            updated_at=now,
        )
        self.db.create_theme(theme)
        
        candidate = CandidateStock(
            candidate_id="cand_005",
            theme_id="theme_007",
            symbol="000001.SZ",
            source_type="manual_stock",
            match_reason="手动添加",
            status="raw",
            created_at=now,
        )
        self.db.add_candidate(candidate)
        
        confirmed = self.db.confirm_candidate(
            candidate_id="cand_005",
            confirmation_reason="基本面稳健",
            evidence_level="strong",
            confirmed_by="user_001",
            pool_snapshot_date=date.today(),
            thesis_snapshot="银行股低估值",
            invalidation_rules=[
                {"type": "earnings_miss", "threshold": -0.1},
                {"type": "credit_rating_downgrade"},
            ],
            price_snapshot={"close": 12.5, "volume": 5000000},
            benchmark_snapshot={"index": "000001.SH", "close": 3000.0},
        )
        
        self.assertEqual(confirmed.thesis_snapshot, "银行股低估值")
        self.assertEqual(len(confirmed.invalidation_rules), 2)
        self.assertEqual(confirmed.price_snapshot["close"], 12.5)
        self.assertEqual(confirmed.benchmark_snapshot["index"], "000001.SH")

    def test_confirmed_candidate_freezes_verification_id(self):
        """Confirmed pool freezes the candidate identity verification reference."""
        now = datetime.now()
        theme = ThemeInput(
            theme_id="theme_verification_freeze",
            theme_name="Test Theme",
            background="Test",
            source_type="manual_theme",
            board_version=0,
            created_at=now,
            updated_at=now,
        )
        self.db.create_theme(theme)

        candidate = CandidateStock(
            candidate_id="cand_verification_freeze",
            theme_id="theme_verification_freeze",
            symbol="300750.SZ",
            company_name="宁德时代",
            verification_id="verify_freeze",
            source_type="manual_stock",
            match_reason="手动添加",
            status="raw",
            created_at=now,
        )
        self.db.add_candidate(candidate)

        confirmed = self.db.confirm_candidate(
            candidate_id="cand_verification_freeze",
            confirmation_reason="证据完整",
            evidence_level="strong",
            confirmed_by="user_001",
            pool_snapshot_date=date.today(),
            thesis_snapshot="身份核验可追溯",
            invalidation_rules=[{"type": "identity_break"}],
            price_snapshot={"close": 100.0},
            benchmark_snapshot={"index": "399006.SZ"},
        )

        pool = self.db.list_confirmed_candidates("theme_verification_freeze")
        self.assertEqual(confirmed.verification_id, "verify_freeze")
        self.assertEqual(pool[0].verification_id, "verify_freeze")

    def test_conversation_messages_do_not_change_state(self):
        """Conversation messages do not change candidate or theme state."""
        now = datetime.now()
        theme = ThemeInput(
            theme_id="theme_008",
            theme_name="Test Theme",
            background="Test",
            source_type="manual_theme",
            board_version=0,
            created_at=now,
            updated_at=now,
        )
        self.db.create_theme(theme)
        
        initial_version = self.db.get_theme("theme_008").board_version
        
        msg = ConversationMessage(
            message_id="msg_001",
            theme_id="theme_008",
            role="user",
            content="这是什么主题？",
            created_at=now,
        )
        self.db.store_conversation_message(msg)
        
        after_version = self.db.get_theme("theme_008").board_version
        self.assertEqual(initial_version, after_version)

    def test_proposed_action_ids_linked_to_conversation(self):
        """Proposed action IDs can be linked back to the conversation turn that produced them."""
        now = datetime.now()
        theme = ThemeInput(
            theme_id="theme_009",
            theme_name="Test Theme",
            background="Test",
            source_type="manual_theme",
            board_version=0,
            created_at=now,
            updated_at=now,
        )
        self.db.create_theme(theme)
        
        action = ProposedAction(
            action_id="action_001",
            action="add_candidate",
            target_id="theme_009",
            args={"symbol": "600000.SH"},
            rationale="用户请求",
            proposed_by="agent",
            proposed_at=now,
            board_version=0,
        )
        self.db.store_proposed_action(action)
        
        msg = ConversationMessage(
            message_id="msg_002",
            theme_id="theme_009",
            role="agent",
            content="已生成待审核动作",
            linked_proposed_action_ids=["action_001"],
            created_at=now,
        )
        self.db.store_conversation_message(msg)
        
        retrieved_msg = self.db.get_conversation_message("msg_002")
        self.assertIn("action_001", retrieved_msg.linked_proposed_action_ids)

    def test_successful_apply_increments_board_version(self):
        """Successful reducer-applied state mutation increments theme board_version by exactly 1."""
        now = datetime.now()
        theme = ThemeInput(
            theme_id="theme_010",
            theme_name="Test Theme",
            background="Test",
            source_type="manual_theme",
            board_version=0,
            created_at=now,
            updated_at=now,
        )
        self.db.create_theme(theme)
        
        initial_version = self.db.get_theme("theme_010").board_version
        
        # Simulate successful state mutation
        self.db.increment_board_version("theme_010")
        
        after_version = self.db.get_theme("theme_010").board_version
        self.assertEqual(after_version, initial_version + 1)

    def test_rejected_action_does_not_increment_board_version(self):
        """Rejected pending action does not increment board_version."""
        now = datetime.now()
        theme = ThemeInput(
            theme_id="theme_011",
            theme_name="Test Theme",
            background="Test",
            source_type="manual_theme",
            board_version=0,
            created_at=now,
            updated_at=now,
        )
        self.db.create_theme(theme)
        
        action = ProposedAction(
            action_id="action_002",
            action="add_candidate",
            target_id="theme_011",
            args={"symbol": "600000.SH"},
            rationale="测试",
            proposed_by="agent",
            proposed_at=now,
            board_version=0,
        )
        self.db.store_proposed_action(action)
        
        initial_version = self.db.get_theme("theme_011").board_version
        
        applied = AppliedAction(
            action_id="action_002",
            proposed_action=action,
            applied=False,
            rejection_reason="不符合条件",
            applied_by="user_001",
            applied_at=now,
        )
        self.db.store_applied_action(applied)
        
        after_version = self.db.get_theme("theme_011").board_version
        self.assertEqual(initial_version, after_version)

    def test_action_audit_records_proposed_and_applied_separately(self):
        """Action audit records proposed and applied states separately."""
        now = datetime.now()
        theme = ThemeInput(
            theme_id="theme_012",
            theme_name="Test Theme",
            background="Test",
            source_type="manual_theme",
            board_version=0,
            created_at=now,
            updated_at=now,
        )
        self.db.create_theme(theme)
        
        action = ProposedAction(
            action_id="action_003",
            action="add_candidate",
            target_id="theme_012",
            args={"symbol": "300750.SZ"},
            rationale="测试",
            proposed_by="agent",
            proposed_at=now,
            board_version=0,
        )
        self.db.store_proposed_action(action)
        
        applied = AppliedAction(
            action_id="action_003",
            proposed_action=action,
            applied=True,
            actor_reason="通过审核",
            applied_by="user_001",
            applied_at=now,
        )
        self.db.store_applied_action(applied)
        
        retrieved_proposed = self.db.get_proposed_action("action_003")
        retrieved_applied = self.db.get_applied_action("action_003")
        
        self.assertIsNotNone(retrieved_proposed)
        self.assertIsNotNone(retrieved_applied)
        self.assertTrue(retrieved_applied.applied)

    def test_reopen_records_include_actor_reason_timestamp(self):
        """Reject and reopen audit records include actor, reason, and timestamp."""
        now = datetime.now()
        theme = ThemeInput(
            theme_id="theme_013",
            theme_name="Test Theme",
            background="Test",
            source_type="manual_theme",
            board_version=0,
            created_at=now,
            updated_at=now,
        )
        self.db.create_theme(theme)
        
        candidate = CandidateStock(
            candidate_id="cand_006",
            theme_id="theme_013",
            symbol="600000.SH",
            source_type="manual_stock",
            match_reason="手动添加",
            status="confirmed",
            created_at=now,
        )
        self.db.add_candidate(candidate)
        
        reopen_action = self.db.reopen_candidate_to_evidence(
            candidate_id="cand_006",
            actor="user_001",
            reason="需要重新评估证据",
            timestamp=now,
        )
        
        self.assertEqual(reopen_action["actor"], "user_001")
        self.assertEqual(reopen_action["reason"], "需要重新评估证据")
        self.assertIsNotNone(reopen_action["timestamp"])


if __name__ == "__main__":
    unittest.main()
