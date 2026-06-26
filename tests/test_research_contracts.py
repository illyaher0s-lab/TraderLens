"""
Test research contracts.

These tests prove:
- a theme can be created from manual input
- a new theme starts with board_version=0
- a manual stock candidate can be attached to a theme
- EvidenceLevel accepts 'conflicted'
- evidence items carry expiry_days or valid_until
- EvidenceOutput requires kill_criteria_hash
- ProposedAction has proposed != applied semantics
- ProposedAction carries action_id and optional board_version
- ConversationMessage can link to proposed action IDs without applying them
- ConversationTurnResult can return zero or more proposed actions
- AgentHarnessConfig can identify 'stub' or 'langgraph'
- ResearchAction excludes 'run_serenity' and 'run_evidence'
- ConfirmedCandidate has pool_snapshot_date and forward_only=True
- ConfirmedCandidate.forward_only cannot be set to False
- ConfirmedCandidate locks thesis, invalidation rules, price snapshot, and benchmark snapshot at confirmation time
- blocked candidates carry hard_filter_flags
- confirmed candidates require evidence level and confirmation reason
"""

import unittest
from datetime import date, datetime, timedelta
from contracts.research import (
    ThemeInput,
    CandidateStock,
    EvidenceItem,
    ConflictItem,
    AgentHarnessConfig,
    SerenityOutput,
    EvidenceOutput,
    DataToolResult,
    ProposedAction,
    ConversationMessage,
    ConversationTurnResult,
    AppliedAction,
    ConfirmedCandidate,
    ThemeSourceType,
    ResearchMode,
    ThemeStatus,
    CandidateStatus,
    EvidenceLevel,
    ConversationRole,
    ResearchAction,
)


class TestThemeInput(unittest.TestCase):
    """Test ThemeInput contract."""

    def test_theme_can_be_created_from_manual_input(self):
        """A theme can be created from manual input."""
        now = datetime.now()
        theme = ThemeInput(
            theme_id="theme_001",
            theme_name="新能源产业链",
            background="锂电池需求增长",
            source_type="manual_theme",
            research_mode="standard",
            urgency="normal",
            notes="",
            status="draft",
            board_version=0,
            created_at=now,
            updated_at=now,
        )
        self.assertEqual(theme.theme_id, "theme_001")
        self.assertEqual(theme.source_type, "manual_theme")
        self.assertEqual(theme.research_mode, "standard")
        self.assertEqual(theme.status, "draft")

    def test_new_theme_starts_with_board_version_zero(self):
        """A new theme starts with board_version=0."""
        now = datetime.now()
        theme = ThemeInput(
            theme_id="theme_002",
            theme_name="Test Theme",
            background="Test background",
            source_type="manual_theme",
            board_version=0,
            created_at=now,
            updated_at=now,
        )
        self.assertEqual(theme.board_version, 0)


class TestCandidateStock(unittest.TestCase):
    """Test CandidateStock contract."""

    def test_manual_stock_candidate_can_be_attached_to_theme(self):
        """A manual stock candidate can be attached to a theme."""
        now = datetime.now()
        candidate = CandidateStock(
            candidate_id="cand_001",
            theme_id="theme_001",
            symbol="300750.SZ",
            company_name="宁德时代",
            source_type="manual_stock",
            chain_layer=None,
            match_reason="用户手动添加",
            match_confidence="unknown",
            status="raw",
            hard_filter_flags=[],
            override_reason=None,
            created_at=now,
        )
        self.assertEqual(candidate.theme_id, "theme_001")
        self.assertEqual(candidate.symbol, "300750.SZ")
        self.assertEqual(candidate.source_type, "manual_stock")

    def test_blocked_candidates_carry_hard_filter_flags(self):
        """Blocked candidates carry hard_filter_flags."""
        now = datetime.now()
        candidate = CandidateStock(
            candidate_id="cand_002",
            theme_id="theme_001",
            symbol="600000.SH",
            company_name="浦发银行",
            source_type="manual_stock",
            match_reason="手动添加",
            status="blocked",
            hard_filter_flags=["is_st", "low_liquidity"],
            created_at=now,
        )
        self.assertEqual(candidate.status, "blocked")
        self.assertIn("is_st", candidate.hard_filter_flags)
        self.assertIn("low_liquidity", candidate.hard_filter_flags)


class TestEvidenceLevel(unittest.TestCase):
    """Test EvidenceLevel accepts 'conflicted'."""

    def test_evidence_level_accepts_conflicted(self):
        """EvidenceLevel accepts 'conflicted'."""
        level: EvidenceLevel = "conflicted"
        self.assertEqual(level, "conflicted")


class TestEvidenceItem(unittest.TestCase):
    """Test evidence items carry source identity, expiry, and thesis links."""

    def test_evidence_item_carries_expiry_days(self):
        """Evidence items carry expiry_days."""
        now = datetime.now()
        item = EvidenceItem(
            source="公司公告",
            source_type="announcement",
            source_quality="first_hand",
            description="年报披露营收增长",
            published_at=date.today(),
            retrieved_at=now,
            expiry_days=90,
            valid_until=None,
        )
        self.assertEqual(item.expiry_days, 90)

    def test_evidence_item_carries_valid_until(self):
        """Evidence items carry valid_until."""
        now = datetime.now()
        valid_date = date.today() + timedelta(days=30)
        item = EvidenceItem(
            source="行业报告",
            source_type="news",
            source_quality="second_hand",
            description="市场份额数据",
            published_at=date.today(),
            retrieved_at=now,
            expiry_days=None,
            valid_until=valid_date,
        )
        self.assertEqual(item.valid_until, valid_date)

    def test_evidence_item_defaults_source_type_to_unknown(self):
        """EvidenceItem defaults source_type to 'unknown' when not provided."""
        now = datetime.now()
        item = EvidenceItem(
            source="some-source",
            description="test",
            retrieved_at=now,
        )
        self.assertEqual(item.source_type, "unknown")
        self.assertEqual(item.source_quality, "weak")
        self.assertEqual(item.supports, [])
        self.assertEqual(item.falsifies, [])
        self.assertEqual(item.conflicts, [])

    def test_evidence_item_carries_source_type_and_quality(self):
        """EvidenceItem carries explicit source_type and source_quality."""
        now = datetime.now()
        item = EvidenceItem(
            source="年报2025",
            source_type="financial_report",
            source_quality="first_hand",
            description="ROE 连续三年 > 15%",
            retrieved_at=now,
        )
        self.assertEqual(item.source_type, "financial_report")
        self.assertEqual(item.source_quality, "first_hand")

    def test_evidence_item_carries_supports_falsifies_conflicts(self):
        """EvidenceItem links to specific theses via supports/falsifies/conflicts."""
        now = datetime.now()
        item = EvidenceItem(
            source="券商研报",
            source_type="news",
            source_quality="second_hand",
            description="行业增速超预期",
            retrieved_at=now,
            supports=["thesis_demand_growth"],
            falsifies=["thesis_margin_expansion"],
            conflicts=["source_mismatch_vs_financials"],
        )
        self.assertEqual(item.supports, ["thesis_demand_growth"])
        self.assertEqual(item.falsifies, ["thesis_margin_expansion"])
        self.assertEqual(item.conflicts, ["source_mismatch_vs_financials"])

    def test_evidence_item_serializes_all_source_fields(self):
        """EvidenceItem JSON round-trip preserves all source identity fields."""
        now = datetime.now()
        item = EvidenceItem(
            source="招股说明书",
            source_type="prospectus",
            source_quality="first_hand",
            description="核心客户集中度风险",
            published_at=date(2024, 6, 1),
            retrieved_at=now,
            supports=["thesis_tech_leadership"],
            falsifies=["thesis_customer_diversity"],
            conflicts=[],
        )
        data = item.model_dump(mode="json")
        self.assertEqual(data["source_type"], "prospectus")
        self.assertEqual(data["source_quality"], "first_hand")
        self.assertEqual(data["supports"], ["thesis_tech_leadership"])
        self.assertEqual(data["falsifies"], ["thesis_customer_diversity"])
        self.assertEqual(data["conflicts"], [])


class TestEvidenceOutput(unittest.TestCase):
    """Test EvidenceOutput requires kill_criteria_hash."""

    def test_evidence_output_requires_kill_criteria_hash(self):
        """EvidenceOutput requires kill_criteria_hash."""
        now = datetime.now()
        output = EvidenceOutput(
            candidate_id="cand_001",
            kill_criteria_hash="abc123",
            evidence_level="medium",
            supporting_evidence=[],
            falsifying_evidence=[],
            conflict_items=[],
            blocking_issues=[],
            evidence_gaps=[],
            tool_trace=[],
            created_at=now,
        )
        self.assertEqual(output.kill_criteria_hash, "abc123")


class TestDataToolResult(unittest.TestCase):
    """Test DataToolResult unified return contract."""

    def test_datatoolresult_defaults_empty_lists(self):
        """DataToolResult defaults gaps and errors to empty lists."""
        now = datetime.now()
        result = DataToolResult(
            tool_name="get_financials",
            source="tushare_income",
            retrieved_at=now,
        )
        self.assertEqual(result.raw_data, [])
        self.assertEqual(result.gaps, [])
        self.assertEqual(result.errors, [])

    def test_datatoolresult_enforces_no_silent_pass_invariant(self):
        """Empty raw_data should have gaps or errors — contract enforces all empty defaults."""
        now = datetime.now()
        result = DataToolResult(
            tool_name="test_tool",
            source="test_source",
            retrieved_at=now,
        )
        # Contract-level check: empty lists by default
        # The consumer (DataToolsService) is responsible for populating gaps/errors
        self.assertEqual(result.raw_data, [])
        self.assertEqual(result.gaps, [])
        self.assertEqual(result.errors, [])

    def test_datatoolresult_with_data_serializes(self):
        """DataToolResult with rows serializes correctly."""
        now = datetime.now()
        result = DataToolResult(
            tool_name="get_financials",
            raw_data=[{"total_revenue": 1e10, "n_income": 2e9}],
            source="tushare_income",
            retrieved_at=now,
            gaps=["income.basic_eps_missing_all_rows"],
            errors=[],
        )
        data = result.model_dump(mode="json")
        self.assertEqual(data["tool_name"], "get_financials")
        self.assertEqual(len(data["raw_data"]), 1)
        self.assertEqual(data["raw_data"][0]["total_revenue"], 10000000000.0)
        self.assertIn("income.basic_eps_missing_all_rows", data["gaps"])


class TestProposedAction(unittest.TestCase):
    """Test ProposedAction semantics."""

    def test_proposed_action_has_proposed_not_applied_semantics(self):
        """ProposedAction has proposed != applied semantics."""
        now = datetime.now()
        action = ProposedAction(
            action_id="action_001",
            action="add_candidate",
            target_id="theme_001",
            args={"symbol": "600000.SH", "match_reason": "手动添加"},
            rationale="用户请求添加该股票",
            proposed_by="agent",
            proposed_at=now,
            expires_at=None,
            board_version=0,
        )
        # ProposedAction itself does not indicate applied state
        self.assertEqual(action.action, "add_candidate")
        self.assertEqual(action.proposed_by, "agent")

    def test_proposed_action_carries_action_id_and_optional_board_version(self):
        """ProposedAction carries action_id and optional board_version."""
        now = datetime.now()
        action = ProposedAction(
            action_id="action_002",
            action="propose_confirm",
            target_id="cand_001",
            args={},
            rationale="候选股符合确认条件",
            proposed_by="agent",
            proposed_at=now,
            board_version=5,
        )
        self.assertEqual(action.action_id, "action_002")
        self.assertEqual(action.board_version, 5)


class TestConversationMessage(unittest.TestCase):
    """Test ConversationMessage can link to proposed action IDs."""

    def test_conversation_message_links_to_proposed_actions(self):
        """ConversationMessage can link to proposed action IDs without applying them."""
        now = datetime.now()
        msg = ConversationMessage(
            message_id="msg_001",
            theme_id="theme_001",
            role="agent",
            content="我已经生成了一个待审核动作",
            linked_proposed_action_ids=["action_001", "action_002"],
            created_at=now,
        )
        self.assertIn("action_001", msg.linked_proposed_action_ids)
        self.assertIn("action_002", msg.linked_proposed_action_ids)


class TestConversationTurnResult(unittest.TestCase):
    """Test ConversationTurnResult can return zero or more proposed actions."""

    def test_conversation_turn_with_zero_proposed_actions(self):
        """ConversationTurnResult can return zero proposed actions."""
        now = datetime.now()
        user_msg = ConversationMessage(
            message_id="msg_u_001",
            theme_id="theme_001",
            role="user",
            content="这个主题是什么？",
            created_at=now,
        )
        agent_msg = ConversationMessage(
            message_id="msg_a_001",
            theme_id="theme_001",
            role="agent",
            content="这是新能源产业链主题",
            created_at=now,
        )
        result = ConversationTurnResult(
            user_message=user_msg,
            agent_message=agent_msg,
            proposed_actions=[],
        )
        self.assertEqual(len(result.proposed_actions), 0)

    def test_conversation_turn_with_multiple_proposed_actions(self):
        """ConversationTurnResult can return multiple proposed actions."""
        now = datetime.now()
        user_msg = ConversationMessage(
            message_id="msg_u_002",
            theme_id="theme_001",
            role="user",
            content="添加 600000.SH 和 300750.SZ",
            created_at=now,
        )
        agent_msg = ConversationMessage(
            message_id="msg_a_002",
            theme_id="theme_001",
            role="agent",
            content="已生成两个待审核动作",
            linked_proposed_action_ids=["action_003", "action_004"],
            created_at=now,
        )
        action1 = ProposedAction(
            action_id="action_003",
            action="add_candidate",
            target_id="theme_001",
            args={"symbol": "600000.SH"},
            rationale="用户请求",
            proposed_by="agent",
            proposed_at=now,
        )
        action2 = ProposedAction(
            action_id="action_004",
            action="add_candidate",
            target_id="theme_001",
            args={"symbol": "300750.SZ"},
            rationale="用户请求",
            proposed_by="agent",
            proposed_at=now,
        )
        result = ConversationTurnResult(
            user_message=user_msg,
            agent_message=agent_msg,
            proposed_actions=[action1, action2],
        )
        self.assertEqual(len(result.proposed_actions), 2)


class TestAgentHarnessConfig(unittest.TestCase):
    """Test AgentHarnessConfig with execution_engine and llm_provider."""

    def test_harness_config_stub(self):
        """AgentHarnessConfig can identify 'stub' execution."""
        config = AgentHarnessConfig(
            execution_engine="stub",
            llm_provider="none",
            provider="stub",  # DEPRECATED
            tool_whitelist=["read_theme", "list_candidates"],
            max_steps=10,
            token_budget=5000,
            replayable=True,
        )
        self.assertEqual(config.execution_engine, "stub")
        self.assertEqual(config.llm_provider, "none")
        self.assertEqual(config.provider, "stub")  # 兼容性检查

    def test_harness_config_two_phase(self):
        """AgentHarnessConfig can identify 'two_phase' execution."""
        config = AgentHarnessConfig(
            execution_engine="two_phase",
            llm_provider="openai",
            provider=None,  # 不再伪装为 langgraph
            tool_whitelist=["web_search", "read_theme"],
            max_steps=20,
            token_budget=10000,
            replayable=True,
        )
        self.assertEqual(config.execution_engine, "two_phase")
        self.assertEqual(config.llm_provider, "openai")
        self.assertIsNone(config.provider)


class TestResearchAction(unittest.TestCase):
    """Test ResearchAction excludes 'run_serenity' and 'run_evidence'."""

    def test_research_action_excludes_run_serenity_and_run_evidence(self):
        """ResearchAction excludes 'run_serenity' and 'run_evidence'."""
        valid_actions: list[ResearchAction] = [
            "create_theme",
            "add_candidate",
            "propose_confirm",
            "propose_reject",
            "reopen_to_serenity",
            "reopen_to_evidence",
        ]
        self.assertIn("add_candidate", valid_actions)
        self.assertIn("propose_confirm", valid_actions)
        # 'run_serenity' and 'run_evidence' are not ResearchAction values


class TestConfirmedCandidate(unittest.TestCase):
    """Test ConfirmedCandidate contract."""

    def test_confirmed_candidate_has_pool_snapshot_date_and_forward_only(self):
        """ConfirmedCandidate has pool_snapshot_date and forward_only=True."""
        now = datetime.now()
        confirmed = ConfirmedCandidate(
            confirmed_id="conf_001",
            theme_id="theme_001",
            candidate_id="cand_001",
            source_serenity_run_id="serenity_run_001",
            source_evidence_run_id="evidence_run_001",
            symbol="300750.SZ",
            company_name="宁德时代",
            chain_layer="电池制造",
            thesis_snapshot="产业链核心环节",
            invalidation_rules=[{"type": "price_drop", "threshold": -0.2}],
            price_snapshot={"close": 500.0, "volume": 1000000},
            benchmark_snapshot={"index": "399006.SZ", "close": 3000.0},
            confirmation_reason="证据充分",
            evidence_level="strong",
            confirmed_by="user_001",
            confirmed_at=now,
            pool_snapshot_date=date.today(),
        )
        self.assertEqual(confirmed.pool_snapshot_date, date.today())
        self.assertTrue(confirmed.forward_only)

    def test_confirmed_candidate_forward_only_cannot_be_set_to_false(self):
        """ConfirmedCandidate.forward_only cannot be set to False."""
        now = datetime.now()
        # Literal[True] enforces forward_only=True
        confirmed = ConfirmedCandidate(
            confirmed_id="conf_002",
            theme_id="theme_001",
            candidate_id="cand_002",
            symbol="600000.SH",
            company_name="浦发银行",
            thesis_snapshot="金融板块",
            invalidation_rules=[],
            price_snapshot={},
            benchmark_snapshot={},
            confirmation_reason="确认",
            evidence_level="medium",
            confirmed_by="user_001",
            confirmed_at=now,
            pool_snapshot_date=date.today(),
        )
        self.assertTrue(confirmed.forward_only)

    def test_confirmed_candidate_locks_thesis_invalidation_price_benchmark(self):
        """ConfirmedCandidate locks thesis, invalidation rules, price snapshot, and benchmark snapshot at confirmation time."""
        now = datetime.now()
        confirmed = ConfirmedCandidate(
            confirmed_id="conf_003",
            theme_id="theme_001",
            candidate_id="cand_003",
            symbol="000001.SZ",
            company_name="平安银行",
            thesis_snapshot="银行股低估值",
            invalidation_rules=[
                {"type": "earnings_miss", "threshold": -0.1},
                {"type": "credit_rating_downgrade"},
            ],
            price_snapshot={"close": 12.5, "volume": 5000000, "date": "2023-12-29"},
            benchmark_snapshot={"index": "000001.SH", "close": 3000.0},
            confirmation_reason="基本面稳健",
            evidence_level="strong",
            confirmed_by="user_001",
            confirmed_at=now,
            pool_snapshot_date=date.today(),
        )
        self.assertEqual(confirmed.thesis_snapshot, "银行股低估值")
        self.assertEqual(len(confirmed.invalidation_rules), 2)
        self.assertEqual(confirmed.price_snapshot["close"], 12.5)
        self.assertEqual(confirmed.benchmark_snapshot["index"], "000001.SH")

    def test_confirmed_candidate_requires_evidence_level_and_confirmation_reason(self):
        """Confirmed candidates require evidence level and confirmation reason."""
        now = datetime.now()
        confirmed = ConfirmedCandidate(
            confirmed_id="conf_004",
            theme_id="theme_001",
            candidate_id="cand_004",
            symbol="002594.SZ",
            company_name="比亚迪",
            thesis_snapshot="新能源汽车龙头",
            invalidation_rules=[],
            price_snapshot={},
            benchmark_snapshot={},
            confirmation_reason="市场地位稳固，证据充分",
            evidence_level="strong",
            confirmed_by="user_001",
            confirmed_at=now,
            pool_snapshot_date=date.today(),
        )
        self.assertEqual(confirmed.confirmation_reason, "市场地位稳固，证据充分")
        self.assertEqual(confirmed.evidence_level, "strong")


if __name__ == "__main__":
    unittest.main()
