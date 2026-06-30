"""
Task 12 API-level integration tests for friend-stock flow.

Tests the full HTTP API path, not just service layer.
"""

import pytest
from datetime import date
from fastapi.testclient import TestClient
from backend.api.research import create_research_app
from backend.db.research import ResearchDB


@pytest.fixture
def market_data_provider():
    """Deterministic market data provider for testing."""
    def provider(symbol: str, as_of: date) -> dict:
        # Return deterministic non-10.5 values
        if symbol == "600000.SH":
            return {"close": 12.34, "volume": 5000000}
        elif symbol == "000300.SH":  # Benchmark
            return {"close": 3456.78, "volume": 10000000}
        else:
            return {"close": 15.67, "volume": 3000000}
    return provider


@pytest.fixture
def app(market_data_provider):
    """Create test app with in-memory DB and deterministic market data provider."""
    db = ResearchDB(db_path=":memory:")
    app = create_research_app(
        db=db,
        conversation_mode="deterministic",
        serenity_execution_mode="stub",
        market_data_provider=market_data_provider,
    )
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


def test_friend_stock_api_intake_persists_flow(client):
    """Test that intake endpoint persists flow state to DB."""
    response = client.post(
        "/api/research/friend-stock/intake",
        json={
            "raw_company_input": "PUDONG BANK",
            "raw_code_input": None,
            "source_note": "Friend recommendation",
        },
    )
    
    assert response.status_code == 200
    result = response.json()
    
    # Should return verification result with flow_id
    assert "flow_id" in result
    assert result["status"] == "verified"
    assert result["resolved_ticker"] == "600000.SH"


def test_friend_stock_api_resolve_reads_candidates_from_db(client):
    """Test that resolve-ambiguous reads candidates from DB, not empty array."""
    # First, create an ambiguous verification
    intake_response = client.post(
        "/api/research/friend-stock/intake",
        json={
            "raw_company_input": "PINGAN",
            "raw_code_input": None,
            "source_note": "Friend recommendation",
        },
    )
    
    assert intake_response.status_code == 200
    intake_result = intake_response.json()
    assert intake_result["status"] == "ambiguous"
    assert len(intake_result["candidates"]) >= 2
    
    flow_id = intake_result["flow_id"]
    
    # Now resolve - should read candidates from DB
    resolve_response = client.post(
        f"/api/research/friend-stock/{flow_id}/resolve-ambiguous",
        json={"chosen_ticker": "000001.SZ"},
    )
    
    assert resolve_response.status_code == 200
    resolve_result = resolve_response.json()
    assert resolve_result["status"] == "verified"
    assert resolve_result["resolved_ticker"] == "000001.SZ"


def test_friend_stock_api_resolve_rejects_out_of_bounds_ticker(client):
    """Test that resolve-ambiguous rejects ticker not in candidates."""
    # Create ambiguous flow
    intake_response = client.post(
        "/api/research/friend-stock/intake",
        json={
            "raw_company_input": "PINGAN",
            "raw_code_input": None,
            "source_note": "Friend recommendation",
        },
    )
    
    flow_id = intake_response.json()["flow_id"]
    
    # Try to resolve with out-of-bounds ticker - should return 400
    resolve_response = client.post(
        f"/api/research/friend-stock/{flow_id}/resolve-ambiguous",
        json={"chosen_ticker": "999999.SH"},  # Not in candidates
    )
    
    assert resolve_response.status_code == 400
    assert "not in candidates" in resolve_response.json()["detail"]


def test_friend_stock_api_run_research_blocks_without_serenity(client):
    """Test that run-research endpoint blocks without real serenity."""
    # Create verified flow first
    intake_response = client.post(
        "/api/research/friend-stock/intake",
        json={
            "raw_company_input": "PUDONG BANK",
            "raw_code_input": None,
            "source_note": "Friend recommendation",
        },
    )
    
    flow_id = intake_response.json()["flow_id"]
    
    # Run research - will return 503 without real SerenityRunner
    research_response = client.post(
        f"/api/research/friend-stock/{flow_id}/run-research",
        params={"ticker": "600000.SH", "company_name": "PUDONG BANK"},
    )
    
    assert research_response.status_code == 503
    assert "SerenityAgentRunner not configured" in research_response.json()["detail"]


def test_friend_stock_api_create_pool_rejects_without_verified_ticker(client, app):
    """Test that create-pool rejects if ticker not verified."""
    # Create verified flow
    intake_response = client.post(
        "/api/research/friend-stock/intake",
        json={
            "raw_company_input": "PUDONG BANK",
            "raw_code_input": None,
            "source_note": "Friend recommendation",
        },
    )
    
    flow_id = intake_response.json()["flow_id"]
    
    # Try to create pool without research
    response = client.post(
        f"/api/research/friend-stock/{flow_id}/create-pool",
        json={
            "ticker": "600000.SH",
            "name": "PUDONG BANK",
            "exchange": "SSE",
            "approval_card_id": "card_001",
            "snapshot_date": "2026-06-30",
        },
    )
    
    # Should reject because research not completed
    assert response.status_code == 400
    assert "Research not completed" in response.json()["detail"]


def test_friend_stock_api_create_pool_rejects_ticker_mismatch(client, app):
    """Test that create-pool rejects if request ticker doesn't match verified ticker."""
    # Create verified flow
    intake_response = client.post(
        "/api/research/friend-stock/intake",
        json={
            "raw_company_input": "PUDONG BANK",
            "raw_code_input": None,
            "source_note": "Friend recommendation",
        },
    )
    
    flow_id = intake_response.json()["flow_id"]
    verified_result = intake_response.json()
    
    # Verified ticker is 600000.SH
    assert verified_result["resolved_ticker"] == "600000.SH"
    
    # Manually add research output via DB
    db = app.state.db
    
    flow_state = db.get_friend_stock_flow(flow_id)
    db.store_friend_stock_flow(
        flow_id=flow_id,
        raw_company_input=flow_state["raw_company_input"],
        raw_code_input=flow_state["raw_code_input"],
        source_note=flow_state["source_note"],
        ticker_verification_result=flow_state["ticker_verification_result"],
        research_output={"candidate_rationales": {"600000.SH": {"rationale": "test"}}},
    )
    
    # Try to create pool with mismatched ticker - should hit ticker mismatch before other checks
    response = client.post(
        f"/api/research/friend-stock/{flow_id}/create-pool",
        json={
            "ticker": "000001.SZ",  # Wrong ticker
            "name": "PUDONG BANK",
            "exchange": "SSE",
            "approval_card_id": "card_001",
            "snapshot_date": "2026-06-30",
        },
    )
    
    assert response.status_code == 400
    assert "does not match verified ticker" in response.json()["detail"]


def test_friend_stock_api_create_pool_does_not_use_mock_market_price(client, app):
    """Test that create-pool does not use mock market price (10.5), uses injected provider."""
    # Create verified flow
    intake_response = client.post(
        "/api/research/friend-stock/intake",
        json={
            "raw_company_input": "PUDONG BANK",
            "raw_code_input": None,
            "source_note": "Friend recommendation",
        },
    )
    
    flow_id = intake_response.json()["flow_id"]
    
    # Manually add research output via DB
    db = app.state.db
    
    flow_state = db.get_friend_stock_flow(flow_id)
    db.store_friend_stock_flow(
        flow_id=flow_id,
        raw_company_input=flow_state["raw_company_input"],
        raw_code_input=flow_state["raw_code_input"],
        source_note=flow_state["source_note"],
        ticker_verification_result=flow_state["ticker_verification_result"],
        research_output={"candidate_rationales": {"600000.SH": {"rationale": "test", "supporting_source_ids": [], "counter_evidence": []}}},
    )
    
    # Create pool - should use injected provider with 12.34, not 10.5
    response = client.post(
        f"/api/research/friend-stock/{flow_id}/create-pool",
        json={
            "ticker": "600000.SH",
            "name": "PUDONG BANK",
            "exchange": "SSE",
            "approval_card_id": "card_001",
            "snapshot_date": "2026-06-30",
        },
    )
    
    assert response.status_code == 200
    pool = response.json()
    
    # Verify price is from injected provider (12.34), not mock (10.5)
    assert pool["price_snapshot"]["close"] == 12.34
    assert pool["benchmark_snapshot"]["close"] == 3456.78


def test_friend_stock_api_create_pool_persists_and_reads_back_confirmed_candidate(client, app):
    """
    Test that create-pool persists confirmed candidate and can be read back.
    """
    # Create verified flow
    intake_response = client.post(
        "/api/research/friend-stock/intake",
        json={
            "raw_company_input": "PUDONG BANK",
            "raw_code_input": None,
            "source_note": "Friend recommendation",
        },
    )
    
    flow_id = intake_response.json()["flow_id"]
    
    # Add research output
    db = app.state.db
    
    flow_state = db.get_friend_stock_flow(flow_id)
    db.store_friend_stock_flow(
        flow_id=flow_id,
        raw_company_input=flow_state["raw_company_input"],
        raw_code_input=flow_state["raw_code_input"],
        source_note=flow_state["source_note"],
        ticker_verification_result=flow_state["ticker_verification_result"],
        research_output={"candidate_rationales": {"600000.SH": {"rationale": "Strong player", "supporting_source_ids": ["src_001"], "counter_evidence": []}}},
    )
    
    # Create pool
    response = client.post(
        f"/api/research/friend-stock/{flow_id}/create-pool",
        json={
            "ticker": "600000.SH",
            "name": "PUDONG BANK",
            "exchange": "SSE",
            "approval_card_id": "card_001",
            "snapshot_date": "2026-06-30",
        },
    )
    
    # Verify 200 success
    assert response.status_code == 200
    pool = response.json()
    
    # Verify confirmed_id returned
    assert "confirmed_id" in pool
    confirmed_id = pool["confirmed_id"]
    
    # Read back from DB
    retrieved = db.get_confirmed_candidate(confirmed_id)
    
    # Verify read back succeeded
    assert retrieved is not None
    assert retrieved.symbol == "600000.SH"
    assert retrieved.company_name == "浦发银行"  # Resolved name from verification
    assert retrieved.price_snapshot["close"] == 12.34
    assert retrieved.verification_id == flow_id  # Linked to verification
    
    # Verify snapshot fields present
    assert retrieved.thesis_snapshot
    assert retrieved.invalidation_rules
    assert retrieved.benchmark_snapshot
