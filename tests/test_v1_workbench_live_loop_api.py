"""
V1 Workbench Live Observation Loop API Tests

Task 18: Test execution -> observation -> P&L chain wired into Workbench.

Hard requirements:
- No automatic trading
- No broker fields
- No technical parameters exposed to users
- LLM does not decide buy/sell or P&L
- No mock profit fabrication
- Every step has artifact/DB record
"""

import pytest
from datetime import date
from fastapi.testclient import TestClient

from backend.api.research import create_research_app
from backend.db.research import ResearchDB
from tests.fake_serenity_runner import FakeSerenityRunner


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
    
    db = ResearchDB(db_path=":memory:")
    fake_serenity = FakeSerenityRunner()
    
    app = create_research_app(
        db=db,
        conversation_mode="real",
        serenity_execution_mode="two_phase",
        serenity_runner=fake_serenity,
        market_data_provider=market_data_provider,
        allow_test_serenity_runner=True,
    )
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


class TestWorkbenchLiveLoop:
    """Test complete live observation loop from workbench."""
    
    def test_cannot_create_execution_card_without_candidate(self, client):
        """
        Red line: Cannot create execution card without qualified artifact.
        
        Must verify:
        - Empty conversation -> no execution card
        - Error message readable (not system crash)
        """
        # Create workbench session
        response = client.post(
            "/api/agent/workbench/message",
            json={"message": "hello"}
        )
        assert response.status_code == 200
        conversation_id = response.json()["conversation_id"]
        
        # Try to create execution card without candidate
        exec_response = client.post(
            f"/api/agent/workbench/{conversation_id}/execution-card",
            json={}
        )
        
        # Must fail with readable error
        assert exec_response.status_code in [400, 404]
        assert "artifact" in exec_response.json()["detail"].lower() or \
               "candidate" in exec_response.json()["detail"].lower()
    
    def test_buy_feedback_creates_position(self, client, app):
        """
        Verify buy feedback -> execution log -> observation position.
        
        Must verify:
        - Natural language "已买入 100 股，成交价 12.34" parsed correctly
        - ExecutionObservationLog created
        - ObservationPosition created (open state)
        - No technical parameters required from user
        """
        # Create workbench session with confirmed candidate
        response = client.post(
            "/api/agent/workbench/message",
            json={"message": "我朋友推荐了浦发银行"}
        )
        assert response.status_code == 200
        conversation_id = response.json()["conversation_id"]
        
        # Create confirmed candidate (simplified for test)
        # In real flow, this comes from friend_stock_flow
        intake_response = client.post(
            "/api/research/friend-stock/intake",
            json={
                "raw_company_input": "浦发银行",
                "raw_code_input": None,
                "source_note": "workbench test"
            }
        )
        assert intake_response.status_code == 200
        flow_id = intake_response.json()["flow_id"]
        
        # Run research
        client.post(
            f"/api/research/friend-stock/{flow_id}/run-research",
            params={"ticker": "600000.SH", "company_name": "浦发银行"}
        )
        
        # Create pool
        pool_response = client.post(
            f"/api/research/friend-stock/{flow_id}/create-pool",
            json={
                "ticker": "600000.SH",
                "name": "浦发银行",
                "exchange": "SSE",
                "approval_card_id": "test_approval",
                "snapshot_date": str(date.today())
            }
        )
        assert pool_response.status_code == 200
        
        # Now submit buy feedback
        feedback_response = client.post(
            f"/api/agent/workbench/{conversation_id}/execution-feedback",
            json={
                "feedback": "已买入 100 股，成交价 12.34",
                "symbol": "600000.SH"
            }
        )
        
        # Should succeed and create position
        assert feedback_response.status_code == 200
        assert "position_id" in feedback_response.json()
    
    def test_daily_signal_requires_open_position(self, client):
        """
        Verify daily signal only works with open position.
        
        Must verify:
        - No position -> readable error
        - Open position -> daily signal generated (deterministic)
        """
        pytest.skip("Implementation pending")
    
    def test_sell_feedback_closes_position_and_generates_pnl(self, client):
        """
        Verify complete loop: sell -> position close -> P&L -> discipline review.
        
        Must verify:
        - Natural language "已卖出 100 股，成交价 13.10" parsed correctly
        - Position closed
        - P&L calculated from confirmed logs (deterministic)
        - Discipline review created
        - No LLM decides P&L
        """
        pytest.skip("Implementation pending")
    
    def test_timeline_shows_complete_chain(self, client):
        """
        Verify timeline readback shows all artifacts in order.
        
        Must verify:
        - execution_card artifact
        - buy execution_log artifact
        - observation_position artifact
        - daily_signal artifact
        - sell execution_log artifact
        - discipline_review artifact
        """
        pytest.skip("Implementation pending")
    
    def test_no_technical_parameters_exposed(self, client):
        """
        Verify user never sees technical parameters.
        
        Forbidden:
        - OOS, threshold, stop_loss, liquidity_rule
        - position_size, backtest_param
        - 仓位公式, 止损比例, 回测参数
        """
        pytest.skip("Implementation pending")
