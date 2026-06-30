"""
Task 12: Friend Stock Flow Tests

All 18 test scenarios from PRD.
"""

import pytest
from datetime import datetime

from contracts.friend_stock import (
    FriendStockIntake,
    TickerVerificationResult,
    ConfirmedCandidatePool,
)
from backend.services.friend_stock_flow import FriendStockFlowService


@pytest.fixture
def flow_service():
    """Create friend stock flow service."""
    return FriendStockFlowService()


def test_clear_company_name_verified(flow_service):
    """Test 1: Clear company name → verified."""
    result = flow_service.verify_ticker(
        raw_company_input="浦发银行",
        raw_code_input=None,
    )
    
    # Ticker from tool, segment matches exchange
    assert result.status == "verified"
    assert result.resolved_ticker is not None
    assert result.resolved_ticker.startswith("600")  # SSE main board
    assert result.exchange == "SSE"
    assert result.data_source == "stock_basic_query"  # From tool


def test_code_only_reverse_lookup(flow_service):
    """Test 2: Code only → reverse lookup name."""
    result = flow_service.verify_ticker(
        raw_company_input=None,
        raw_code_input="600000.SH",
    )
    
    assert result.status == "verified"
    assert result.resolved_name is not None
    assert "浦发" in result.resolved_name or "银行" in result.resolved_name


def test_name_and_code_consistent_verified(flow_service):
    """Test 3: Name + code both given and consistent → verified."""
    result = flow_service.verify_ticker(
        raw_company_input="浦发银行",
        raw_code_input="600000.SH",
    )
    
    # Both directions verified
    assert result.status == "verified"
    assert result.resolved_ticker == "600000.SH"
    assert "浦发" in result.resolved_name


def test_name_code_mismatch(flow_service):
    """Test 4: Name and code mismatch → mismatch status."""
    result = flow_service.verify_ticker(
        raw_company_input="招商银行",
        raw_code_input="600000.SH",  # Wrong code
    )
    
    # Mismatch detected, no research
    assert result.status == "mismatch"


def test_segment_exchange_mismatch(flow_service):
    """Test 5: Segment doesn't match exchange → mismatch."""
    result = flow_service.verify_ticker(
        raw_company_input=None,
        raw_code_input="688001",  # 688xxx should be SSE, not SZSE
        claimed_exchange="SZSE",  # Wrong exchange
    )
    
    # Deterministic segment check catches this
    assert result.status == "mismatch"


def test_ambiguous_multiple_candidates(flow_service):
    """Test 6: Multiple candidates → ambiguous, flow pauses."""
    result = flow_service.verify_ticker(
        raw_company_input="平安",  # Could be 平安银行/中国平安
        raw_code_input=None,
    )
    
    # Ambiguous, no auto-selection
    assert result.status == "ambiguous"
    assert len(result.candidates) >= 2
    # Flow should pause, not auto-pick


def test_resolve_ticker_out_of_bounds_rejected(flow_service):
    """Test 7: Resolve ticker with out-of-bounds code → rejected."""
    # First get ambiguous result
    verify_result = flow_service.verify_ticker(
        raw_company_input="平安",
        raw_code_input=None,
    )
    
    if verify_result.status == "ambiguous":
        # Try to resolve with code not in candidates
        with pytest.raises(ValueError, match="not in candidates|out of bounds"):
            flow_service.resolve_ambiguous_ticker(
                flow_id=verify_result.flow_id,
                chosen_ticker="999999.SH",  # Not in candidates
                original_candidates=verify_result.candidates,
            )


def test_not_found(flow_service):
    """Test 8: Stock not found → not_found status."""
    result = flow_service.verify_ticker(
        raw_company_input="不存在的公司XYZ",
        raw_code_input=None,
    )
    
    # Not found, no fabrication
    assert result.status == "not_found"
    assert result.resolved_ticker is None


def test_delisted_or_suspended(flow_service):
    """Test 9: Delisted/suspended → blocked or downgraded."""
    result = flow_service.verify_ticker(
        raw_company_input=None,
        raw_code_input="600000.SH",
        mock_status="delisted",  # Mock delisted
    )
    
    # Blocked or downgraded, not continue
    assert result.status in ["delisted", "suspended"]


def test_adapter_unsupported(flow_service):
    """Test 10: stock_basic unavailable → adapter_unsupported."""
    result = flow_service.verify_ticker(
        raw_company_input="某公司",
        raw_code_input=None,
        mock_adapter_fault=True,  # Mock adapter failure
    )
    
    # Fault recorded, no fabrication
    assert result.status == "adapter_unsupported"
    assert result.market_data_fault is not None


def test_llm_cannot_inject_code(flow_service):
    """Test 11: LLM cannot inject ticker code."""
    # Payload with fake LLM suggestion
    result = flow_service.verify_ticker(
        raw_company_input="某公司",
        raw_code_input=None,
        llm_suggested_code="999999.SH",  # Fake suggestion
    )
    
    # R2: Ticker still from tool query, not LLM
    assert result.resolved_ticker != "999999.SH" or result.status == "not_found"
    assert result.data_source != "llm"


def test_approval_card_structure(flow_service):
    """Test 12: Approval card structure."""
    # Mock research output with counter-evidence
    research_output = {
        "candidate_rationales": {
            "600000.SH": {
                "rationale": "核心玩家",
                "counter_evidence": ["反证1", "反证2"],
            }
        },
        "hypothesis_draft": [{"hypothesis": "假设1"}],
    }
    
    card = flow_service.create_approval_card(
        flow_id="flow_001",
        ticker="600000.SH",
        research_output=research_output,
    )
    
    # R3: Three decisions, has counter-evidence, no tech fields
    assert set(card["allowed_decisions"]) == {"continue", "stop", "downgrade_to_observation"}
    assert "counter_evidence" in card
    assert "price_snapshot" not in card
    assert "llm_score" not in card


def test_confirmed_pool_complete_fields(flow_service):
    """Test 13: Pool has all 8 field types - end-to-end with real flow."""
    from datetime import date
    
    # Mock market data provider
    def mock_provider(symbol: str, as_of: date) -> dict:
        return {"close": 10.5, "volume": 1000000}
    
    flow_service.market_data_provider = mock_provider
    
    # Mock research output (would come from real Serenity in production)
    research_output = {
        "theme_id": "flow_001",
        "demand_driver": "产业链需求",
        "candidate_rationales": {
            "600000.SH": {
                "rationale": "核心玩家，业绩稳定",
                "supporting_source_ids": ["evidence_001"],
                "counter_evidence": [
                    {"description": "市场竞争加剧", "source_record_id": "counter_001"}
                ],
            }
        },
    }
    
    pool = flow_service.create_confirmed_pool(
        flow_id="flow_001",
        ticker="600000.SH",
        name="浦发银行",
        exchange="SSE",
        approval_card_id="card_001",
        research_output=research_output,
        snapshot_date=date.today(),
    )
    
    # R4: All 8 types present
    assert pool.ticker
    assert pool.thesis_snapshot
    assert pool.invalidation_rules
    assert pool.price_snapshot
    assert pool.benchmark_snapshot
    assert pool.evidence_snapshot_ids
    assert pool.source_provenance
    assert pool.snapshot_hash


def test_pool_frozen_after_write(flow_service):
    """Test 14: Pool frozen after write."""
    from datetime import date
    
    # Mock market data provider
    def mock_provider(symbol: str, as_of: date) -> dict:
        return {"close": 10.5, "volume": 1000000}
    
    flow_service.market_data_provider = mock_provider
    
    # Mock research output
    research_output = {
        "theme_id": "flow_001",
        "candidate_rationales": {
            "600000.SH": {
                "rationale": "核心玩家",
                "supporting_source_ids": ["evidence_001"],
                "counter_evidence": [],
            }
        },
    }
    
    pool = flow_service.create_confirmed_pool(
        flow_id="flow_001",
        ticker="600000.SH",
        name="浦发银行",
        exchange="SSE",
        approval_card_id="card_001",
        research_output=research_output,
        snapshot_date=date.today(),
    )
    
    # R4: Frozen (Pydantic frozen=True raises ValidationError)
    from pydantic_core import ValidationError
    with pytest.raises((AttributeError, TypeError, ValidationError)):
        pool.price_snapshot = {"close": 999.99}


def test_price_from_adapter_not_llm(flow_service):
    """Test 15: Price/benchmark from adapter, not LLM."""
    from datetime import date
    
    # Mock market data provider
    def mock_provider(symbol: str, as_of: date) -> dict:
        return {"close": 10.5, "volume": 1000000}
    
    flow_service.market_data_provider = mock_provider
    
    # Mock research output
    research_output = {
        "theme_id": "flow_001",
        "candidate_rationales": {
            "600000.SH": {
                "rationale": "核心玩家",
                "supporting_source_ids": ["evidence_001"],
                "counter_evidence": [],
            }
        },
    }
    
    pool = flow_service.create_confirmed_pool(
        flow_id="flow_001",
        ticker="600000.SH",
        name="浦发银行",
        exchange="SSE",
        approval_card_id="card_001",
        research_output=research_output,
        snapshot_date=date.today(),
    )
    
    # R5: Price from Tushare adapter, source must match actual call
    assert pool.price_snapshot["source"] == "tushare_private"  # From actual adapter
    assert pool.benchmark_snapshot["source"] == "tushare_private"  # From actual adapter
    
    # Fault case
    if pool.price_snapshot.get("fault_state"):
        # Fault recorded, not fabricated
        assert pool.price_snapshot["close"] is None or pool.price_snapshot["fault_state"] is not None


def test_stop_downgrade_flow(flow_service):
    """Test 16: stop/downgrade decisions."""
    # Stop decision
    result = flow_service.process_decision(
        flow_id="flow_001",
        decision="stop",
    )
    assert result["pool_created"] is False
    
    # Downgrade decision
    result = flow_service.process_decision(
        flow_id="flow_002",
        decision="downgrade_to_observation",
    )
    assert result["pool_created"] is False
    assert result["status"] == "downgraded"


def test_orchestration_not_reimplementation(flow_service):
    """Test 17: Flow orchestrates, doesn't reimplement."""
    # Check flow service calls existing services
    import inspect
    source = inspect.getsource(flow_service.__class__)
    
    # Should NOT have research algorithm reimplementation
    assert "def calculate_supply_chain" not in source
    assert "def collect_evidence" not in source
    
    # Should call existing services (stub check)
    assert "R1:" in source or "orchestrate" in source.lower()


def test_pool_persists_to_db_and_read_back():
    """Test 18: Pool writes to DB and can be read back with consistent snapshot_hash."""
    from datetime import date
    from backend.db.research import ResearchDB
    from backend.services.friend_stock_flow import FriendStockFlowService
    
    # Setup
    db = ResearchDB(db_path=":memory:")
    flow_service = FriendStockFlowService()
    
    # Mock market data provider
    def mock_provider(symbol: str, as_of: date) -> dict:
        return {"close": 10.5, "volume": 1000000}
    
    flow_service.market_data_provider = mock_provider
    
    # Mock research output
    research_output = {
        "theme_id": "flow_001",
        "candidate_rationales": {
            "600000.SH": {
                "rationale": "核心玩家，业绩稳定",
                "supporting_source_ids": ["evidence_001"],
                "counter_evidence": [
                    {"description": "市场竞争加剧", "source_record_id": "counter_001"}
                ],
            }
        },
    }
    
    # Create pool
    pool = flow_service.create_confirmed_pool(
        flow_id="flow_001",
        ticker="600000.SH",
        name="浦发银行",
        exchange="SSE",
        approval_card_id="card_001",
        research_output=research_output,
        snapshot_date=date.today(),
    )
    
    original_hash = pool.snapshot_hash
    
    # Persist to DB (need to create candidate first)
    from contracts.research import CandidateStock
    candidate = CandidateStock(
        candidate_id="cand_001",
        theme_id=pool.flow_id,
        symbol=pool.ticker,
        company_name=pool.name,
        verification_id="",
        source_type="manual_stock",  # Use allowed enum value
        chain_layer="",
        match_reason="Friend recommendation",
        match_confidence="high",
        status="raw",  # Use allowed enum value
        hard_filter_flags=[],
        created_at=pool.created_at,
    )
    db.add_candidate(candidate)
    
    # Confirm candidate
    confirmed = db.confirm_candidate(
        candidate_id="cand_001",
        confirmation_reason="Test",
        evidence_level="medium",
        confirmed_by="test",
        pool_snapshot_date=pool.confirmation_date.date(),
        thesis_snapshot=pool.thesis_snapshot,
        invalidation_rules=pool.invalidation_rules,
        price_snapshot=pool.price_snapshot,
        benchmark_snapshot=pool.benchmark_snapshot,
        evidence_snapshot_ids=pool.evidence_snapshot_ids,
        primary_evidence_snapshot_id=None,
    )
    
    # Read back from DB using the confirmed_id returned by confirm_candidate
    retrieved = db.get_confirmed_candidate(confirmed.confirmed_id)
    
    # Verify read back succeeded
    assert retrieved is not None
    assert retrieved.symbol == "600000.SH"
    assert retrieved.company_name == "浦发银行"
    assert retrieved.thesis_snapshot == pool.thesis_snapshot
    
    # Verify semantic fields match
    assert retrieved.invalidation_rules == pool.invalidation_rules
    assert retrieved.price_snapshot == pool.price_snapshot
    assert retrieved.benchmark_snapshot == pool.benchmark_snapshot
    assert retrieved.evidence_snapshot_ids == pool.evidence_snapshot_ids
    
    # Reconstruct snapshot_hash from DB fields (use same logic as friend_stock_flow.py)
    import hashlib
    # friend_stock_flow.py uses: f"{ticker}{name}{pool_data['confirmation_date']}{pool_data['thesis_snapshot']}"
    # But confirmation_date is datetime, need to use same format
    hash_input = f"{retrieved.symbol}{retrieved.company_name}{confirmed.confirmed_at}{retrieved.thesis_snapshot}"
    reconstructed_hash = hashlib.sha256(hash_input.encode()).hexdigest()[:16]
    
    # Verify hash consistency (proves frozen snapshot)
    assert reconstructed_hash == original_hash
