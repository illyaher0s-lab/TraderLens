"""
V1 Workbench Orchestration Gap Audit Tests

Task 20: Systematic audit to identify state/action mismatches in workbench flows.

These tests verify that workflow states correspond to actual business actions,
not just status labels without backing work.

Red lines:
- Workflow state = "researching" must trigger actual research
- Workflow state = "validating" must trigger actual validation
- Timeline artifacts must prove actions occurred
- No fake progress status
"""

import pytest
from uuid import uuid4
from fastapi.testclient import TestClient
from backend.api.research import create_research_app
from backend.db.research import ResearchDB
from tests.fake_serenity_runner import FakeSerenityRunner


def manual_execution_request(feedback, symbol):
    return {
        "feedback": feedback,
        "symbol": symbol,
        "execution_date": "2026-10-01",
        "operation_id": str(uuid4()),
        "confirmed_already_executed": True,
    }


@pytest.fixture
def market_data_provider():
    """Deterministic market data provider."""
    def provider(symbol: str, as_of):
        return {
            "close": 12.50,
            "volume": 8000000,
            "trade_date": str(as_of)
        }
    return provider


@pytest.fixture
def app(market_data_provider, monkeypatch):
    """Create test app."""
    monkeypatch.setenv("RESEARCH_LLM_API_KEY", "test_key")
    monkeypatch.setenv("TUSHARE_TOKEN", "test_token")
    
    from tests.fake_validator import FakeValidator
    
    db = ResearchDB(db_path=":memory:")
    fake_serenity = FakeSerenityRunner()
    fake_validator = FakeValidator()
    
    app = create_research_app(
        db=db,
        conversation_mode="real",
        serenity_execution_mode="two_phase",
        validator=fake_validator,
        serenity_runner=fake_serenity,
        market_data_provider=market_data_provider,
        allow_test_serenity_runner=True,
    )
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


class TestWorkbenchOrchestrationGaps:
    """Audit tests for workbench orchestration gaps."""
    
    def test_friend_stock_message_creates_real_artifacts_not_fake_progress(self, client):
        """
        P0-1 FIXED: Friend stock message creates real action artifacts.
        
        Expected behavior (AFTER Task 21 fix):
        - User sends friend stock message
        - System sets workflow_state based on actual outcome
        - Timeline contains real friend_stock action artifacts
        
        Previously (P0 gap):
        - System set workflow_state=researching with no action
        - Timeline only had workflow_intent
        
        Now (fixed):
        - Timeline has friend_stock_flow artifact
        - If ticker verified + research succeeded: workflow_state=waiting_for_approval
        - If ticker verified but no serenity: workflow_state=stopped (honest failure)
        - If ambiguous: workflow_state=created (need clarification)
        - If failed: workflow_state=stopped (honest failure)
        
        Severity: P0 (was critical fake progress, now fixed)
        """
        response = client.post(
            "/api/agent/workbench/message",
            json={"message": "帮我查一下，宏昌电子是否值得买入？"},
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Should route to friend_stock
        assert data["workflow_type"] == "friend_stock"
        
        # Get timeline
        conversation_id = data["conversation_id"]
        session_response = client.get(f"/api/agent/workbench/{conversation_id}")
        assert session_response.status_code == 200
        session_data = session_response.json()
        
        timeline = session_data["timeline"]
        artifact_types = [item["content"]["artifact_type"] for item in timeline if item["type"] == "artifact_ref"]
        
        # FIXED: Must have friend_stock_flow artifact (proves intake was called)
        assert "friend_stock_flow" in artifact_types, "Missing friend_stock_flow artifact - intake was not called"
        
        # Must NOT have fake researching state without action
        stage = data["stage"]
        if stage == "researching":
            # If state is "researching", must have research_report artifact
            assert "research_report" in artifact_types, "workflow_state=researching but no research_report artifact"
        
        # Acceptable states after orchestration:
        # - "waiting_for_approval" (research succeeded)
        # - "stopped" (honest failure - no serenity, verification failed, etc.)
        # - "created" (ambiguous, need clarification)
        assert stage in ["waiting_for_approval", "stopped", "created"], \
            f"Unexpected state: {stage}. Must be honest about outcome."
    
    def test_strategy_idea_message_creates_real_artifacts_not_fake_progress(self, client):
        """
        P0-2 FIXED: Strategy idea message creates real action artifacts.
        
        Expected behavior (AFTER Task 22 fix):
        - User sends strategy idea message
        - System sets workflow_state based on actual outcome
        - Timeline contains real strategy_idea action artifacts
        
        Previously (P0 gap):
        - System set workflow_state=validating with no action
        - Timeline only had workflow_intent
        
        Now (fixed):
        - Timeline has strategy_idea artifact
        - Timeline has strategy_idea_extraction artifact
        - Timeline has template_mapping artifact (or rejection/blocked)
        - If extraction succeeded: workflow_state=stopped (honest: no approved templates)
        - If extraction failed: workflow_state=stopped (honest failure)
        
        Severity: P0 (was critical fake progress, now fixed)
        """
        response = client.post(
            "/api/agent/workbench/message",
            json={"message": "我在抖音看到一个策略，下午两点半买入第二天卖出，帮我验证"},
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Should route to strategy_idea
        assert data["workflow_type"] == "strategy_idea"
        
        # Get timeline
        conversation_id = data["conversation_id"]
        session_response = client.get(f"/api/agent/workbench/{conversation_id}")
        assert session_response.status_code == 200
        session_data = session_response.json()
        
        timeline = session_data["timeline"]
        artifact_types = [item["content"]["artifact_type"] for item in timeline if item["type"] == "artifact_ref"]
        
        # FIXED: Must have strategy_idea artifact (proves create_idea was called)
        assert "strategy_idea" in artifact_types, "Missing strategy_idea artifact - create_idea was not called"
        
        # FIXED: Must have extraction artifact (proves extract_claims was called)
        assert "strategy_idea_extraction" in artifact_types, "Missing strategy_idea_extraction artifact - extract_claims was not called"
        
        # FIXED: Must have template_mapping or rejection artifact (proves map_to_template was called)
        has_mapping_or_rejection = ("template_mapping" in artifact_types or 
                                     "rejected_strategy" in artifact_types or
                                     "blocked_strategy_idea" in artifact_types)
        assert has_mapping_or_rejection, "Missing template_mapping/rejected_strategy artifact - map_to_template was not called"
        
        # Must NOT have fake validating state without action
        stage = data["stage"]
        if stage == "validating":
            # If state is "validating", must have all validation artifacts
            assert "strategy_idea" in artifact_types, "workflow_state=validating but no strategy_idea artifact"
            assert "strategy_idea_extraction" in artifact_types, "workflow_state=validating but no extraction artifact"
        
        # Acceptable states after orchestration:
        # - "stopped" (honest: no approved templates, extraction failed, etc.)
        # - "completed" (if somehow approved template path succeeded, unlikely in current system)
        # - "created" (ambiguous, need clarification)
        assert stage in ["stopped", "completed", "created"], \
            f"Unexpected state: {stage}. Must be honest about outcome."
    
    def test_execution_feedback_does_create_real_artifacts(self, client):
        """
        PASS: Execution feedback endpoint creates real artifacts.
        
        This is NOT a gap - execution-feedback actually works.
        
        Severity: N/A (working correctly)
        """
        # Create session first
        response = client.post(
            "/api/agent/workbench/message",
            json={"message": "帮我查一下，宏昌电子是否值得买入？"},
        )
        conversation_id = response.json()["conversation_id"]
        
        # Submit buy feedback
        feedback_response = client.post(
            "/api/agent/workbench/execution-feedback",
            json=manual_execution_request("已买入 100 股，成交价 12.34", "600123.SH"),
        )
        
        assert feedback_response.status_code == 200
        feedback_data = feedback_response.json()
        
        # Execution feedback DOES create real artifacts
        assert feedback_data["status"] == "success"
        assert feedback_data["action"] == "buy"
        assert "position_id" in feedback_data
        assert "log_id" in feedback_data
        
        # Verify timeline contains execution artifacts (not tested here, but exists in test_v1_workbench_live_loop_api.py)
    
    def test_daily_signal_does_create_real_artifacts(self, client):
        """
        PASS: Daily signal endpoint creates real artifacts.
        
        This is NOT a gap - daily-signal actually works.
        
        Severity: N/A (working correctly)
        """
        # Create session first
        response = client.post(
            "/api/agent/workbench/message",
            json={"message": "帮我查一下，宏昌电子是否值得买入？"},
        )
        conversation_id = response.json()["conversation_id"]
        
        # Create position first (daily-signal requires open position)
        client.post(
            "/api/agent/workbench/execution-feedback",
            json=manual_execution_request("已买入 100 股，成交价 12.34", "600123.SH"),
        )
        
        # Generate daily signal
        signal_response = client.post(
            f"/api/agent/workbench/{conversation_id}/daily-signal",
            json={},
        )
        
        assert signal_response.status_code == 200
        signal_data = signal_response.json()
        
        # Daily signal DOES create real artifacts
        assert signal_data["status"] == "success"
        assert len(signal_data["signals"]) > 0
        assert "signal_id" in signal_data["signals"][0]
    
    def test_unknown_workflow_has_no_fake_progress_state(self, client):
        """
        PASS: Unknown workflow does not set fake progress state.
        
        This is NOT a gap - unknown workflow correctly stays in "created" state.
        
        Severity: N/A (working correctly)
        """
        response = client.post(
            "/api/agent/workbench/message",
            json={"message": "你好"},
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Unknown workflow stays in "created" state (not "researching" or "validating")
        assert data["stage"] == "created"
        assert data["workflow_type"] == "unknown"
        assert data["next_required_user_action"] == "clarify_intent"
