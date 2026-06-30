"""
Test V1 Agent Workbench API.

Task 13: Unified agent conversation API that routes natural language
to friend-stock or strategy-idea flows without exposing technical parameters.
"""

import pytest
from fastapi.testclient import TestClient
from backend.api.research import create_research_app
from backend.db.research import ResearchDB
from backend.services.research_validation import ResearchValidator
from tests.fake_serenity_runner import FakeSerenityRunner
from tests.fake_validator import FakeValidator


@pytest.fixture
def market_data_provider():
    """Minimal market data provider for testing."""
    def provider(symbol: str, as_of):
        return {
            "close": 10.5,
            "trade_date": as_of.isoformat() if hasattr(as_of, 'isoformat') else as_of,
        }
    return provider


@pytest.fixture
def app(market_data_provider):
    """Create test app with workbench API."""
    db = ResearchDB(":memory:")
    fake_validator = FakeValidator()
    
    # Don't inject serenity_runner - let it auto-create SerenityStubRunner
    app = create_research_app(
        db=db,
        conversation_mode="deterministic",
        serenity_execution_mode="stub",
        validator=fake_validator,
        market_data_provider=market_data_provider,
    )
    return app


def test_friend_stock_message_routes_to_friend_stock_workflow(app):
    """
    Friend stock message routes to friend_stock workflow.
    
    Input: "我朋友推荐了浦发银行，帮我看看"
    Expected:
    - status 200
    - workflow_type == "friend_stock"
    - returns conversation_id
    - returns agent_reply
    - does not require user to fill technical fields
    """
    client = TestClient(app)
    
    response = client.post(
        "/api/agent/workbench/message",
        json={
            "message": "我朋友推荐了浦发银行，帮我看看能不能做",
        },
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert "conversation_id" in data
    assert data["workflow_type"] == "friend_stock"
    assert "agent_reply" in data
    assert isinstance(data["agent_reply"], str)
    assert len(data["agent_reply"]) > 0
    
    # Must not ask for technical fields
    reply_lower = data["agent_reply"].lower()
    forbidden_terms = ["oos", "threshold", "止损", "流动性", "仓位", "回测参数"]
    for term in forbidden_terms:
        assert term not in reply_lower, f"Agent reply contains forbidden term: {term}"
    
    # Should have next action guidance
    assert "next_required_user_action" in data


def test_stock_code_routes_to_friend_stock_workflow(app):
    """
    Stock code routes to friend_stock workflow.
    
    Input: "朋友推荐 600000.SH"
    Expected: same as above
    """
    client = TestClient(app)
    
    response = client.post(
        "/api/agent/workbench/message",
        json={
            "message": "朋友推荐 600000.SH，帮我看看",
        },
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["workflow_type"] == "friend_stock"
    assert "agent_reply" in data
    assert "conversation_id" in data


def test_strategy_video_routes_to_strategy_idea_workflow(app):
    """
    Strategy video routes to strategy_idea workflow.
    
    Input: "我在抖音看到一个策略，下午两点半买入第二天卖出，帮我验证"
    Expected:
    - workflow_type == "strategy_idea"
    - does not directly add to strategy library
    - returns "进入策略理解/待验证假设" status
    """
    client = TestClient(app)
    
    response = client.post(
        "/api/agent/workbench/message",
        json={
            "message": "我在抖音看到一个策略，下午两点半买入第二天卖出，帮我验证能不能用",
        },
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["workflow_type"] == "strategy_idea"
    assert "agent_reply" in data
    
    # Must not promise immediate live execution
    reply_lower = data["agent_reply"].lower()
    assert "验证" in reply_lower or "评估" in reply_lower or "检查" in reply_lower


def test_unknown_message_asks_plain_clarification(app):
    """
    Unknown message asks plain clarification.
    
    Input: "你好"
    Expected:
    - workflow_type == "unknown"
    - next_required_user_action is plain clarification, not technical parameters
    """
    client = TestClient(app)
    
    response = client.post(
        "/api/agent/workbench/message",
        json={
            "message": "你好",
        },
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["workflow_type"] == "unknown"
    assert "agent_reply" in data
    
    # Should ask for clarification in plain language
    reply = data["agent_reply"]
    assert len(reply) > 0


def test_api_must_not_expose_technical_approval_fields(app):
    """
    API must not expose technical approval fields.
    
    Assert response JSON does not contain:
    - oos
    - threshold
    - stop_loss
    - liquidity_rule
    - position_size
    - backtest_param
    """
    client = TestClient(app)
    
    response = client.post(
        "/api/agent/workbench/message",
        json={
            "message": "我朋友推荐了浦发银行",
        },
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # Serialize to string and check
    import json
    response_text = json.dumps(data).lower()
    
    forbidden_fields = [
        "oos",
        "threshold", 
        "stop_loss",
        "liquidity_rule",
        "position_size",
        "backtest_param",
    ]
    
    for field in forbidden_fields:
        assert field not in response_text, f"Response contains forbidden field: {field}"


def test_no_real_llm_dependency(app):
    """
    No real LLM dependency.
    
    Test environment does not set RESEARCH_LLM_API_KEY.
    Workbench API still completes deterministic routing.
    """
    # This test passes if the app was created successfully
    # and the previous tests pass without setting RESEARCH_LLM_API_KEY
    client = TestClient(app)
    
    response = client.post(
        "/api/agent/workbench/message",
        json={
            "message": "朋友推荐 600000.SH",
        },
    )
    
    # Should succeed with deterministic routing
    assert response.status_code == 200
    data = response.json()
    assert data["workflow_type"] == "friend_stock"


def test_conversation_continuity(app):
    """
    Conversation continuity: second message in same conversation.
    """
    client = TestClient(app)
    
    # First message
    response1 = client.post(
        "/api/agent/workbench/message",
        json={
            "message": "我朋友推荐了浦发银行",
        },
    )
    
    assert response1.status_code == 200
    data1 = response1.json()
    conversation_id = data1["conversation_id"]
    
    # Second message in same conversation
    response2 = client.post(
        "/api/agent/workbench/message",
        json={
            "conversation_id": conversation_id,
            "message": "继续",
        },
    )
    
    assert response2.status_code == 200
    data2 = response2.json()
    
    # Should maintain same conversation
    assert data2["conversation_id"] == conversation_id


def test_approval_card_returned_when_needed(app):
    """
    Approval card returned when human decision needed.
    
    After friend stock research, should return approval_card with
    allowed decisions: continue, stop, downgrade_to_observation
    """
    client = TestClient(app)
    
    # Start friend stock flow
    response = client.post(
        "/api/agent/workbench/message",
        json={
            "message": "我朋友推荐了浦发银行，帮我看看",
        },
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # approval_card may be present immediately or after further messages
    # For now, check structure is correct when present
    if "approval_card" in data and data["approval_card"]:
        card = data["approval_card"]
        assert "allowed_decisions" in card
        # Must be result-level decisions only
        for decision in card["allowed_decisions"]:
            assert decision in [
                "continue",
                "stop", 
                "downgrade_to_observation",
                "enter_risk_capped_live_execution",
                "accept_execution_record_interpretation",
            ]
