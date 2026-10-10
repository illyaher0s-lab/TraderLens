"""
Test research conversation service.

These tests prove:
- conversation can create a pending proposed action without changing board state
- conversation can return an explanatory reply with no proposed action
- conversation messages are stored
- conversation can link proposed actions to messages
"""

import unittest
import sqlite3
from datetime import datetime
from backend.db.research import ResearchDB
from backend.services.research_conversation import ResearchConversationService
from contracts.research import ThemeInput


class TestResearchConversation(unittest.TestCase):
    """Test research conversation service."""

    def setUp(self):
        """Set up in-memory database and conversation service."""
        self.db = ResearchDB(":memory:")
        # Use deterministic mode for tests (no LLM API calls)
        self.service = ResearchConversationService(self.db, mode="deterministic")

    def test_conversation_creates_pending_action_without_state_change(self):
        """Conversation can create a pending proposed action without changing board state."""
        now = datetime.now()
        theme = ThemeInput(
            theme_id="theme_001",
            theme_name="新能源产业链",
            background="锂电池需求增长",
            source_type="manual_theme",
            board_version=0,
            created_at=now,
            updated_at=now,
        )
        self.db.create_theme(theme)

        initial_version = self.db.get_theme("theme_001").board_version
        initial_candidates = len(self.db.list_candidates("theme_001"))

        result = self.service.process_user_message(
            theme_id="theme_001",
            user_content="添加 300750.SZ 到候选池",
        )

        # Check board state unchanged
        after_version = self.db.get_theme("theme_001").board_version
        after_candidates = len(self.db.list_candidates("theme_001"))
        self.assertEqual(initial_version, after_version)
        self.assertEqual(initial_candidates, after_candidates)

        # Check proposed action created
        self.assertGreater(len(result.proposed_actions), 0)

    def test_conversation_returns_reply_with_no_action(self):
        """Conversation can return an explanatory reply with no proposed action."""
        now = datetime.now()
        theme = ThemeInput(
            theme_id="theme_002",
            theme_name="新能源产业链",
            background="锂电池需求增长",
            source_type="manual_theme",
            board_version=0,
            created_at=now,
            updated_at=now,
        )
        self.db.create_theme(theme)

        result = self.service.process_user_message(
            theme_id="theme_002",
            user_content="这个主题是什么？",
        )

        # Check no proposed actions
        self.assertEqual(len(result.proposed_actions), 0)

        # Check agent message exists
        self.assertIsNotNone(result.agent_message)
        self.assertIn("新能源", result.agent_message.content)

    def test_conversation_messages_are_stored(self):
        """Conversation messages are stored."""
        now = datetime.now()
        theme = ThemeInput(
            theme_id="theme_003",
            theme_name="新能源产业链",
            background="锂电池需求增长",
            source_type="manual_theme",
            board_version=0,
            created_at=now,
            updated_at=now,
        )
        self.db.create_theme(theme)

        result = self.service.process_user_message(
            theme_id="theme_003",
            user_content="测试消息",
        )

        # Check user message stored
        user_msg = self.db.get_conversation_message(result.user_message.message_id)
        self.assertIsNotNone(user_msg)
        self.assertEqual(user_msg.role, "user")

        # Check agent message stored
        agent_msg = self.db.get_conversation_message(result.agent_message.message_id)
        self.assertIsNotNone(agent_msg)
        self.assertEqual(agent_msg.role, "agent")

    def test_conversation_links_proposed_actions_to_messages(self):
        """Conversation can link proposed actions to messages."""
        now = datetime.now()
        theme = ThemeInput(
            theme_id="theme_004",
            theme_name="新能源产业链",
            background="锂电池需求增长",
            source_type="manual_theme",
            board_version=0,
            created_at=now,
            updated_at=now,
        )
        self.db.create_theme(theme)

        result = self.service.process_user_message(
            theme_id="theme_004",
            user_content="添加 600000.SH",
        )

        if len(result.proposed_actions) > 0:
            # Check agent message links to proposed action
            action_id = result.proposed_actions[0].action_id
            self.assertIn(action_id, result.agent_message.linked_proposed_action_ids)


if __name__ == "__main__":
    unittest.main()


class FakeTushareClient:
    """Fake Tushare client for testing."""
    
    def __init__(self, config):
        self.config = config
    
    def query(self, api_name, **kwargs):
        """Fake query returns predefined data."""
        if api_name == "stock_basic":
            ts_code = kwargs.get("ts_code")
            
            # Known stocks
            if ts_code == "300750.SZ":
                import pandas as pd
                return pd.DataFrame([{
                    "ts_code": "300750.SZ",
                    "name": "宁德时代",
                    "list_status": "L",
                    "delist_date": None,
                }])
            elif ts_code == "600519.SH":
                import pandas as pd
                return pd.DataFrame([{
                    "ts_code": "600519.SH",
                    "name": "贵州茅台",
                    "list_status": "L",
                    "delist_date": None,
                }])
            elif ts_code == "600000.SH":
                import pandas as pd
                return pd.DataFrame([{
                    "ts_code": "600000.SH",
                    "name": "浦发银行",
                    "list_status": "L",
                    "delist_date": None,
                }])
            else:
                # Unknown stock
                import pandas as pd
                return pd.DataFrame()
        
        raise ValueError(f"Unsupported API: {api_name}")


class TestResearchConversationLLM(unittest.TestCase):
    """
    Test research conversation with fake LLM client.
    
    Uses deterministic fake LLM responses for testing.
    """

    def setUp(self):
        """Set up in-memory database and fake LLM conversation service."""
        self.db = ResearchDB(":memory:")
        
        # Create fake LLM client
        from backend.services.llm_client import LLMClient
        from backend.services.research_validation import ResearchValidator
        
        class FakeLLMClient:
            """Fake LLM client that returns predefined tool calls."""
            
            def create_message(self, messages, system=None, tools=None, max_tokens=4096):
                """Return fake response based on user message."""
                user_content = messages[0]["content"]
                
                # First turn: user asks to add stock
                if "300750.SZ" in user_content or "宁德时代" in user_content:
                    if len(messages) == 1:
                        # First response: call verify_ticker
                        return {
                            "id": "msg_fake_1",
                            "model": "fake-model",
                            "role": "assistant",
                            "content": [
                                {"type": "text", "text": "我来验证这个股票代码。"},
                                {"type": "tool_use", "id": "tool_1", "name": "verify_ticker", "input": {"symbol": "300750.SZ"}},
                            ],
                            "stop_reason": "tool_use",
                            "usage": {"input_tokens": 100, "output_tokens": 20},
                        }
                    else:
                        # Second response: after tool result, propose add with verification_id
                        # Extract verification_id from previous tool result
                        prev_content = messages[-1]["content"]
                        verification_id = "fake_verify_id"
                        for item in prev_content:
                            if item.get("type") == "tool_result":
                                import json
                                content = json.loads(item["content"])
                                verification_id = content.get("verification_id", "fake_verify_id")
                        
                        return {
                            "id": "msg_fake_2",
                            "model": "fake-model",
                            "role": "assistant",
                            "content": [
                                {"type": "tool_use", "id": "tool_2", "name": "propose_add_candidate", "input": {
                                    "symbol": "300750.SZ",
                                    "verification_id": verification_id,
                                    "match_reason": "锂电池产业链核心企业",
                                    "theme_id": "fake_theme",
                                }},
                            ],
                            "stop_reason": "tool_use",
                            "usage": {"input_tokens": 150, "output_tokens": 50},
                        }
                
                elif "999999.SZ" in user_content:
                    if len(messages) == 1:
                        # First response: call verify_ticker
                        return {
                            "id": "msg_fake_3",
                            "model": "fake-model",
                            "role": "assistant",
                            "content": [
                                {"type": "text", "text": "我来验证这个股票代码。"},
                                {"type": "tool_use", "id": "tool_3", "name": "verify_ticker", "input": {"symbol": "999999.SZ"}},
                            ],
                            "stop_reason": "tool_use",
                            "usage": {"input_tokens": 100, "output_tokens": 20},
                        }
                    else:
                        # Second response: explain ticker not found
                        return {
                            "id": "msg_fake_4",
                            "model": "fake-model",
                            "role": "assistant",
                            "content": [
                                {"type": "text", "text": "验证失败。股票代码 999999.SZ 未找到，无法创建添加提案。"},
                            ],
                            "stop_reason": "end_turn",
                            "usage": {"input_tokens": 150, "output_tokens": 30},
                        }
                
                # Default response
                return {
                    "id": "msg_fake_default",
                    "model": "fake-model",
                    "role": "assistant",
                    "content": [{"type": "text", "text": "我理解了。"}],
                    "stop_reason": "end_turn",
                    "usage": {"input_tokens": 50, "output_tokens": 10},
                }
        
        # Create service with fake clients
        fake_llm = FakeLLMClient()
        
        # Create fake validator
        from backend.app.tushare.config import TushareConfig
        config = TushareConfig(token="fake", api_url="http://fake.test")
        validator = ResearchValidator(tushare_config=config)
        validator._tushare_client = FakeTushareClient(config)
        
        self.service = ResearchConversationService(
            self.db,
            mode="real",
            llm_client=fake_llm,
            validator=validator,
        )

    def test_llm_verifies_ticker_before_adding(self):
        """LLM agent verifies ticker before proposing add."""
        now = datetime.now()
        theme = ThemeInput(
            theme_id="theme_llm_001",
            theme_name="新能源汽车产业链",
            background="分析锂电池产业链瓶颈",
            source_type="manual_theme",
            board_version=0,
            created_at=now,
            updated_at=now,
        )
        self.db.create_theme(theme)

        result = self.service.process_user_message(
            theme_id="theme_llm_001",
            user_content="请添加宁德时代（300750.SZ）到候选池",
        )

        # Check agent response exists
        self.assertIsNotNone(result.agent_message)
        self.assertGreater(len(result.agent_message.content), 0)
        
        # Check proposed action created (LLM should verify ticker and propose add)
        self.assertGreater(len(result.proposed_actions), 0, 
                          f"Expected proposed action, got agent response: {result.agent_message.content}")
        action = result.proposed_actions[0]
        self.assertEqual(action.action, "add_candidate")
        self.assertEqual(action.args["symbol"], "300750.SZ")
        self.assertEqual(action.args["company_name"], "宁德时代")

    def test_llm_rejects_unknown_ticker(self):
        """LLM agent rejects unknown ticker without proposing add."""
        now = datetime.now()
        theme = ThemeInput(
            theme_id="theme_llm_002",
            theme_name="新能源汽车产业链",
            background="分析锂电池产业链瓶颈",
            source_type="manual_theme",
            board_version=0,
            created_at=now,
            updated_at=now,
        )
        self.db.create_theme(theme)

        result = self.service.process_user_message(
            theme_id="theme_llm_002",
            user_content="请添加 999999.SZ 到候选池",
        )

        # Check agent explains the issue
        self.assertIsNotNone(result.agent_message)
        agent_content = result.agent_message.content.lower()
        self.assertTrue(
            "not found" in agent_content or "未找到" in agent_content or "不存在" in agent_content,
            f"Agent should explain ticker not found, got: {result.agent_message.content}"
        )
        
        # Check NO proposed action created
        self.assertEqual(len(result.proposed_actions), 0)


class _FailingConversationLLM:
    def __init__(self, *, fail_on_second_call=False):
        self.fail_on_second_call = fail_on_second_call
        self.calls = 0
        self.diagnostic = (
            "FAKE_CONVERSATION_SENTINEL; "
            "Authorization: Bearer FAKE_CONVERSATION_BEARER_ONLY"
        )

    def create_message(self, **_kwargs):
        self.calls += 1
        if self.fail_on_second_call and self.calls == 1:
            return {
                "content": [{
                    "type": "tool_use",
                    "id": "fixture_read_theme",
                    "name": "read_theme",
                    "input": {},
                }]
            }
        raise RuntimeError(self.diagnostic)


def _assert_conversation_provider_error_is_not_persisted(tmp_path, *, fail_on_second_call):
    db_path = tmp_path / "conversation.sqlite"
    db = ResearchDB(db_path=str(db_path))
    now = datetime.now()
    theme_id = "theme_provider_failure_fixture"
    db.create_theme(ThemeInput(
        theme_id=theme_id,
        theme_name="fixture theme",
        background="fixture background",
        source_type="manual_theme",
        board_version=0,
        created_at=now,
        updated_at=now,
    ))
    llm = _FailingConversationLLM(fail_on_second_call=fail_on_second_call)
    service = ResearchConversationService(db, mode="real", llm_client=llm)

    result = service.process_user_message(theme_id, "fixture question")
    with sqlite3.connect(db_path) as check:
        stored = check.execute(
            "SELECT content FROM conversation_messages "
            "WHERE theme_id = ? AND role = 'agent'",
            (theme_id,),
        ).fetchone()

    assert stored is not None
    forbidden_values = (
        "FAKE_CONVERSATION_SENTINEL",
        "Authorization: Bearer FAKE_CONVERSATION_BEARER_ONLY",
        "FAKE_CONVERSATION_BEARER_ONLY",
    )
    surfaces = {
        "returned agent_message": result.agent_message.content,
        "durable conversation message": stored[0],
    }
    leaking_surfaces = [
        name for name, content in surfaces.items()
        if any(value in content for value in forbidden_values)
    ]
    assert not leaking_surfaces, f"synthetic diagnostic escaped: {leaking_surfaces}"
    assert all("llm_provider_call_failed" in content for content in surfaces.values())


def test_first_llm_failure_does_not_echo_into_agent_message_or_database(tmp_path):
    _assert_conversation_provider_error_is_not_persisted(
        tmp_path,
        fail_on_second_call=False,
    )


def test_final_llm_failure_does_not_echo_into_agent_message_or_database(tmp_path):
    _assert_conversation_provider_error_is_not_persisted(
        tmp_path,
        fail_on_second_call=True,
    )
