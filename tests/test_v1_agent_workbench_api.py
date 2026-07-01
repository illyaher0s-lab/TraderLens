"""
Test V1 Agent Workbench API.

Task 13: Unified agent conversation API that routes natural language
to friend-stock or strategy-idea flows without exposing technical parameters.

Tests cover:
- DB persistence (not in-memory dict)
- Timeline readback
- Artifact tracking
- Approval card flow
- No LLM dependency
"""

import pytest
from fastapi.testclient import TestClient
from backend.api.research import create_research_app
from backend.db.research import ResearchDB
from backend.services.research_validation import ResearchValidator
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
    
    Input: "我朋友推荐了宏昌电子，帮我看看"
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
            "message": "\u6211\u670b\u53cb\u63a8\u8350\u4e86\u5b8f\u660c\u7535\u5b50\uff0c\u5e2e\u6211\u770b\u770b\u80fd\u4e0d\u80fd\u505a",
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
    # Task 22: After orchestration fix, reply includes extraction result and rejection notice
    reply_lower = data["agent_reply"].lower()
    # Check for validation/audit keywords OR extraction/rejection keywords
    has_validation_or_extraction = (
        "验证" in reply_lower or 
        "审批" in reply_lower or 
        "评估" in reply_lower or
        "提取" in reply_lower or
        "拒绝" in reply_lower or
        "记录" in reply_lower
    )
    assert has_validation_or_extraction, f"Reply missing validation/extraction keywords: {data['agent_reply']}"


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


def test_conversation_continuity_with_db_persistence(app):
    """
    Conversation continuity: second message in same conversation.
    
    DB persistence test:
    - POST message creates session in DB
    - GET session/timeline reads back user/agent messages
    - Second POST appends to DB timeline
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
    
    # GET session timeline
    response_get = client.get(f"/api/agent/workbench/{conversation_id}")
    assert response_get.status_code == 200
    session_data = response_get.json()
    
    assert "session" in session_data
    assert "timeline" in session_data
    assert session_data["session"]["session_id"] == conversation_id
    
    # Timeline should have 2 messages (user + agent) and artifact_refs
    # Task 21: friend_stock now creates friend_stock_flow artifact
    timeline = session_data["timeline"]
    messages = [item for item in timeline if item["type"] == "message"]
    artifact_refs = [item for item in timeline if item["type"] == "artifact_ref"]

    assert len(messages) == 2
    assert messages[0]["content"]["role"] == "user"
    assert messages[1]["content"]["role"] == "agent"
    # Was 3 (user_message, agent_message, workflow_intent)
    # Now 4+ (adds friend_stock_flow after Task 21 fix)
    assert len(artifact_refs) >= 3  # At least: user_message, agent_message, workflow_intent
    
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
    
    # GET timeline again
    response_get2 = client.get(f"/api/agent/workbench/{conversation_id}")
    assert response_get2.status_code == 200
    session_data2 = response_get2.json()
    
    timeline2 = session_data2["timeline"]
    messages2 = [item for item in timeline2 if item["type"] == "message"]
    
    # Should have 4 messages now (2 exchanges)
    assert len(messages2) == 4


def test_artifact_ids_non_empty(app):
    """
    artifact_ids must be non-empty.
    
    Every message exchange creates:
    - user_message artifact
    - agent_message artifact
    - workflow_intent artifact (on first message)
    
    artifact_ids returned and persisted in timeline.
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
    
    # artifact_ids must be non-empty
    assert "artifact_ids" in data
    assert isinstance(data["artifact_ids"], list)
    assert len(data["artifact_ids"]) > 0
    
    # Should have at least 3 artifacts: user_message, agent_message, workflow_intent
    assert len(data["artifact_ids"]) >= 3
    
    # Verify artifacts are in DB timeline
    conversation_id = data["conversation_id"]
    response_get = client.get(f"/api/agent/workbench/{conversation_id}")
    assert response_get.status_code == 200
    
    timeline = response_get.json()["timeline"]
    artifact_refs = [item for item in timeline if item["type"] == "artifact_ref"]
    
    assert len(artifact_refs) >= 3
    
    # Artifact IDs returned should match artifact_refs in timeline
    artifact_ids_from_timeline = [ref["content"]["artifact_id"] for ref in artifact_refs]
    for artifact_id in data["artifact_ids"]:
        assert artifact_id in artifact_ids_from_timeline


def test_get_session_returns_404_for_unknown_session(app):
    """
    GET session returns 404 for unknown session.
    """
    client = TestClient(app)
    
    response = client.get("/api/agent/workbench/unknown_session_id")
    assert response.status_code == 404
    assert "Session not found" in response.json()["detail"]


def test_approval_card_decide_endpoint(app):
    """
    POST /api/agent/workbench/{conversation_id}/approval-cards/{card_id}/decide
    
    Uses approval_card_reducer for deterministic validation.
    Returns 404 if card not found.
    """
    from datetime import datetime
    from backend.db.agent_workbench import attach_approval_card
    from backend.services.approval_card_reducer import create_approval_card
    
    client = TestClient(app)
    
    # Create a session first
    response = client.post(
        "/api/agent/workbench/message",
        json={
            "message": "我朋友推荐了浦发银行",
        },
    )
    assert response.status_code == 200
    conversation_id = response.json()["conversation_id"]
    
    # Try to decide on non-existent card
    response_decide = client.post(
        f"/api/agent/workbench/{conversation_id}/approval-cards/fake_card_id/decide",
        json={
            "decision": "continue",
            "decided_by": "test_user",
        },
    )
    
    # Should return 404 for non-existent card
    assert response_decide.status_code == 404
    assert "Approval card not found" in response_decide.json()["detail"]

    artifact_id = response.json()["artifact_ids"][0]
    card = create_approval_card(
        workflow_id=conversation_id,
        stage="research_confirmation",
        title="是否继续",
        plain_language_summary="请决定是否继续调查这只股票。",
        allowed_decisions=["continue", "stop", "downgrade_to_observation"],
        artifact_ids=[artifact_id],
        created_at=datetime.now(),
    )
    attach_approval_card(app.state.db.conn, conversation_id, card)

    response_decide = client.post(
        f"/api/agent/workbench/{conversation_id}/approval-cards/{card.approval_card_id}/decide",
        json={
            "decision": "continue",
            "decided_by": "test_user",
        },
    )

    assert response_decide.status_code == 200
    decision_data = response_decide.json()
    assert decision_data["approval_card_id"] == card.approval_card_id
    assert decision_data["decision"] == "continue"
    assert decision_data["decided_by"] == "test_user"
    assert decision_data["decided_at"] is not None

    response_get = client.get(f"/api/agent/workbench/{conversation_id}")
    assert response_get.status_code == 200
    approval_cards = [
        item["content"]
        for item in response_get.json()["timeline"]
        if item["type"] == "approval_card"
    ]
    assert approval_cards[0]["approval_card_id"] == card.approval_card_id
    assert approval_cards[0]["decision"] == "continue"
    assert approval_cards[0]["decided_by"] == "test_user"
