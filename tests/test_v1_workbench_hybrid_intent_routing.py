"""
Test V1 Workbench Hybrid Intent Routing

Task 20A: Test the hybrid agent pipeline:
PreScan -> LLM Intent -> Tushare Identity -> Router -> Activity Timeline

Must cover:
1. Stock research + company name + bare code
2. Stock research + company name + "买入"
3. Stock research + company name only
4. Bare code only
5. Stock name + bare code
6. "买入宏昌电子可以吗"
7. Douyin strategy
8. Pure strategy rule
9. Unknown
10. Tushare data_fault doesn't enter fake researching
11. Ambiguous doesn't enter fake researching
12. LLM schema failure doesn't misroute
13. All routes produce pipeline artifacts
14. Stock-related routes produce stock_identity_resolution
"""

import pytest
from fastapi.testclient import TestClient
from backend.api.research import create_research_app
from backend.db.research import ResearchDB
from tests.fake_validator import FakeValidator


@pytest.fixture
def market_data_provider():
    """Minimal market data provider."""
    def provider(symbol: str, as_of):
        return {"close": 10.5, "trade_date": str(as_of)}
    return provider


@pytest.fixture
def app(market_data_provider):
    """Create test app with hybrid intent routing."""
    db = ResearchDB(":memory:")
    fake_validator = FakeValidator()
    
    app = create_research_app(
        db=db,
        conversation_mode="deterministic",
        serenity_execution_mode="stub",
        validator=fake_validator,
        market_data_provider=market_data_provider,
    )
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


class TestWorkbenchHybridIntentRouting:
    """Test hybrid agent intent routing pipeline."""
    
    def test_stock_research_with_company_and_bare_code(self, client):
        """
        Input: "帮我看一下宏昌电子是否值得买入?603002"
        Expected: friend_stock, verified
        """
        response = client.post(
            "/api/agent/workbench/message",
            json={"message": "帮我看一下宏昌电子是否值得买入?603002"},
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Should route to friend_stock
        assert data["workflow_type"] == "friend_stock"
        
        # Should not be in researching state without real action
        assert data["stage"] in ["created", "stopped"]
        
        # Get timeline to verify artifacts
        conversation_id = data["conversation_id"]
        session_response = client.get(f"/api/agent/workbench/{conversation_id}")
        assert session_response.status_code == 200
        
        timeline = session_response.json()["timeline"]
        artifact_types = [
            item["content"]["artifact_type"]
            for item in timeline
            if item["type"] == "artifact_ref"
        ]
        
        # Must have pipeline artifacts
        assert "prescan_result" in artifact_types
        assert "intent_extraction" in artifact_types
        assert "stock_identity_resolution" in artifact_types
        assert "workflow_route_decision" in artifact_types
    
    def test_stock_research_with_company_and_buy_keyword(self, client):
        """
        Input: "看一下宏昌电子适不适合买入"
        Expected: friend_stock (not strategy_idea)
        """
        response = client.post(
            "/api/agent/workbench/message",
            json={"message": "\u770b\u4e00\u4e0b\u5b8f\u660c\u7535\u5b50\u9002\u4e0d\u9002\u5408\u4e70\u5165"},
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Must be friend_stock, not strategy_idea
        assert data["workflow_type"] == "friend_stock"
        
        # Verify artifacts
        conversation_id = data["conversation_id"]
        session_response = client.get(f"/api/agent/workbench/{conversation_id}")
        timeline = session_response.json()["timeline"]
        artifact_types = [
            item["content"]["artifact_type"]
            for item in timeline
            if item["type"] == "artifact_ref"
        ]
        
        assert "prescan_result" in artifact_types
        assert "intent_extraction" in artifact_types
        assert "stock_identity_resolution" in artifact_types
    
    def test_stock_research_with_company_only(self, client):
        """
        Input: "帮我查一下宏昌电子是否值得买入"
        Expected: friend_stock, verified
        """
        response = client.post(
            "/api/agent/workbench/message",
            json={"message": "\u5e2e\u6211\u67e5\u4e00\u4e0b\u5b8f\u660c\u7535\u5b50\u662f\u5426\u503c\u5f97\u4e70\u5165"},
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["workflow_type"] == "friend_stock"
        
        # Verify pipeline artifacts
        conversation_id = data["conversation_id"]
        session_response = client.get(f"/api/agent/workbench/{conversation_id}")
        timeline = session_response.json()["timeline"]
        artifact_types = [
            item["content"]["artifact_type"]
            for item in timeline
            if item["type"] == "artifact_ref"
        ]
        
        assert "prescan_result" in artifact_types
        assert "intent_extraction" in artifact_types
        assert "stock_identity_resolution" in artifact_types
    
    def test_bare_code_only(self, client):
        """
        Input: "603002"
        Expected: friend_stock, verified
        """
        response = client.post(
            "/api/agent/workbench/message",
            json={"message": "603002"},
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["workflow_type"] == "friend_stock"
        
        # Verify artifacts
        conversation_id = data["conversation_id"]
        session_response = client.get(f"/api/agent/workbench/{conversation_id}")
        timeline = session_response.json()["timeline"]
        artifact_types = [
            item["content"]["artifact_type"]
            for item in timeline
            if item["type"] == "artifact_ref"
        ]
        
        assert "prescan_result" in artifact_types
        assert "stock_identity_resolution" in artifact_types
    
    def test_stock_name_with_bare_code(self, client):
        """
        Input: "宏昌电子 603002"
        Expected: friend_stock, verified
        """
        response = client.post(
            "/api/agent/workbench/message",
            json={"message": "\u5b8f\u660c\u7535\u5b50 603002"},
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["workflow_type"] == "friend_stock"
        
        # Verify artifacts
        conversation_id = data["conversation_id"]
        session_response = client.get(f"/api/agent/workbench/{conversation_id}")
        timeline = session_response.json()["timeline"]
        artifact_types = [
            item["content"]["artifact_type"]
            for item in timeline
            if item["type"] == "artifact_ref"
        ]
        
        assert "stock_identity_resolution" in artifact_types
    
    def test_buy_company_question(self, client):
        """
        Input: "买入宏昌电子可以吗"
        Expected: friend_stock (not strategy_idea)
        """
        response = client.post(
            "/api/agent/workbench/message",
            json={"message": "\u4e70\u5165\u5b8f\u660c\u7535\u5b50\u53ef\u4ee5\u5417"},
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Must be friend_stock
        assert data["workflow_type"] == "friend_stock"
    
    def test_douyin_strategy(self, client):
        """
        Input: "我在抖音看到一个策略，下午两点半买入第二天卖出，帮我验证"
        Expected: strategy_idea
        """
        response = client.post(
            "/api/agent/workbench/message",
            json={"message": "\u6211\u5728\u6296\u97f3\u770b\u5230\u4e00\u4e2a\u7b56\u7565\uff0c\u4e0b\u5348\u4e24\u70b9\u534a\u4e70\u5165\u7b2c\u4e8c\u5929\u5356\u51fa\uff0c\u5e2e\u6211\u9a8c\u8bc1"},
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["workflow_type"] == "strategy_idea"
        
        # Verify artifacts
        conversation_id = data["conversation_id"]
        session_response = client.get(f"/api/agent/workbench/{conversation_id}")
        timeline = session_response.json()["timeline"]
        artifact_types = [
            item["content"]["artifact_type"]
            for item in timeline
            if item["type"] == "artifact_ref"
        ]
        
        assert "prescan_result" in artifact_types
        assert "intent_extraction" in artifact_types
    
    def test_pure_strategy_rule(self, client):
        """
        Input: "下午两点半买入，第二天早上卖出"
        Expected: strategy_idea
        """
        response = client.post(
            "/api/agent/workbench/message",
            json={"message": "\u4e0b\u5348\u4e24\u70b9\u534a\u4e70\u5165\uff0c\u7b2c\u4e8c\u5929\u65e9\u4e0a\u5356\u51fa"},
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["workflow_type"] == "strategy_idea"
    
    def test_unknown_intent(self, client):
        """
        Input: "你好"
        Expected: unknown, clarification
        """
        response = client.post(
            "/api/agent/workbench/message",
            json={"message": "\u4f60\u597d"},
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["workflow_type"] == "unknown"
        assert data["next_required_user_action"] == "clarify_intent"
    
    def test_unknown_stock_not_found(self, client):
        """
        Input: "帮我看看不存在的公司"
        Expected: stopped (not fake researching)
        """
        response = client.post(
            "/api/agent/workbench/message",
            json={"message": "\u5e2e\u6211\u770b\u770b\u963f\u65af\u987f\u9a6c\u4e01\u516c\u53f8"},
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Must not enter researching without verified stock
        assert data["stage"] != "researching"
        assert data["stage"] in ["created", "stopped"]
    
    def test_all_routes_produce_pipeline_artifacts(self, client):
        """
        All routes must produce at least prescan_result and intent_extraction.
        """
        test_messages = [
            "603002",
            "宏昌电子",
            "下午两点半买入第二天卖出",
            "你好",
        ]
        
        for message in test_messages:
            response = client.post(
                "/api/agent/workbench/message",
                json={"message": message},
            )
            
            assert response.status_code == 200
            conversation_id = response.json()["conversation_id"]
            
            session_response = client.get(f"/api/agent/workbench/{conversation_id}")
            timeline = session_response.json()["timeline"]
            artifact_types = [
                item["content"]["artifact_type"]
                for item in timeline
                if item["type"] == "artifact_ref"
            ]
            
            # Must have prescan and intent
            assert "prescan_result" in artifact_types, f"Missing prescan for: {message}"
            assert "intent_extraction" in artifact_types, f"Missing intent for: {message}"
    
    def test_stock_routes_produce_identity_resolution(self, client):
        """
        Stock-related routes must produce stock_identity_resolution artifact.
        """
        stock_messages = [
            "603002",
            "\u5b8f\u660c\u7535\u5b50",  # 宏昌电子
            "\u5e2e\u6211\u770b\u770b\u5b8f\u660c\u7535\u5b50",  # 帮我看看宏昌电子
        ]
        
        for message in stock_messages:
            response = client.post(
                "/api/agent/workbench/message",
                json={"message": message},
            )
            
            assert response.status_code == 200
            conversation_id = response.json()["conversation_id"]
            
            session_response = client.get(f"/api/agent/workbench/{conversation_id}")
            timeline = session_response.json()["timeline"]
            artifact_types = [
                item["content"]["artifact_type"]
                for item in timeline
                if item["type"] == "artifact_ref"
            ]
            
            assert "stock_identity_resolution" in artifact_types, f"Missing stock_identity for: {message}"
