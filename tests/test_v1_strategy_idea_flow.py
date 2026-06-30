"""
Task 11: Strategy Idea Flow Tests

PRD scenario: "我在抖音看到一个股票策略:下午两点半后买入,第二天早上卖出。
帮我评估它到底能不能赚钱,能不能加入策略里。"

Red lines enforced:
1. Idea defaults to untrusted, no signals until validated
2. LLM only extracts and explains, never directly enters library
3. Only path to library: approved frozen template approval path
4. Failed/blocked ideas enter RejectedStrategyRegistry
5. StrategyDraft must have hard source chain
"""

import pytest
from datetime import datetime
from unittest.mock import patch

from contracts.strategy_idea import (
    StrategyIdea,
    StrategyIdeaTrustStatus,
    TemplatePathType,
    StrategyIdeaExtraction,
    TemplateMappingResult,
    CandidateTemplateEvaluation,
)
from backend.services.strategy_idea_flow import StrategyIdeaFlowService


@pytest.fixture
def flow_service():
    """Create strategy idea flow service."""
    return StrategyIdeaFlowService()


@pytest.fixture
def prd_raw_text():
    """PRD scenario: User's original words from Douyin."""
    return "我在抖音看到一个股票策略:下午两点半后买入,第二天早上卖出。帮我评估它到底能不能赚钱,能不能加入策略里。"


def test_idea_creation_defaults_untrusted(flow_service, prd_raw_text):
    """Red line 1: Idea defaults to untrusted with source channel."""
    idea = flow_service.create_idea(
        raw_source_text=prd_raw_text,
        source_channel="douyin",
    )

    # Red line 1: untrusted by default
    assert idea.trust_status == StrategyIdeaTrustStatus.untrusted
    assert idea.source_channel == "douyin"
    assert idea.raw_source_text == prd_raw_text


def test_llm_extraction_uses_claimed_prefix(flow_service, prd_raw_text):
    """Red line 2: LLM extraction uses 'claimed_' prefix (not verified facts)."""
    idea = flow_service.create_idea(prd_raw_text, "douyin")
    
    # Mock LLM extraction
    with patch("backend.services.strategy_idea_flow.call_llm") as mock_llm:
        mock_llm.return_value = {
            "entry": "14:30 后买入",
            "exit": "次日早盘卖出",
            "edge": None,
        }
        
        extraction = flow_service.extract_claims(idea)
    
    # Fields must have 'claimed_' prefix
    assert hasattr(extraction, "claimed_entry")
    assert hasattr(extraction, "claimed_exit")
    assert hasattr(extraction, "claimed_edge")
    
    # Extraction source labeled llm_assisted
    assert extraction.extraction_source == "llm_assisted"
    
    # Content extracted
    assert "14:30" in extraction.claimed_entry or "两点半" in extraction.claimed_entry
    assert "次日" in extraction.claimed_exit or "早盘" in extraction.claimed_exit


def test_untrusted_produces_no_signals(flow_service, prd_raw_text):
    """Red line 1: Untrusted idea produces no planned signals or execution cards."""
    idea = flow_service.create_idea(prd_raw_text, "douyin")
    
    # Check no signals generated
    signals = flow_service.get_planned_signals_for_idea(idea.idea_id)
    execution_cards = flow_service.get_execution_cards_for_idea(idea.idea_id)
    
    # Red line 1: untrusted → no signals
    assert len(signals) == 0
    assert len(execution_cards) == 0


def test_approved_template_match_path(flow_service, prd_raw_text):
    """Red line 3: Match to approved template, but live_eligible still False until validated."""
    idea = flow_service.create_idea(prd_raw_text, "douyin")
    
    # Mock template matching
    mapping = flow_service.map_to_template(
        idea,
        matched_template_id="template_001",
        template_version="v1",
        mapping_reason="类似日内短线模板",
    )
    
    # Path type correct
    assert mapping.path_type == TemplatePathType.approved_template_match
    
    # Red line 3: live_eligible still False (not yet validated)
    assert mapping.live_eligible is False


def test_no_template_fit_blocks_idea(flow_service, prd_raw_text):
    """Red line 3: No template fit → block with reason."""
    idea = flow_service.create_idea(prd_raw_text, "douyin")
    
    # No template fits
    mapping = flow_service.map_to_template(
        idea,
        matched_template_id=None,
        template_version=None,
        mapping_reason="无已批准模板能接住此策略",
    )
    
    # Blocked
    assert mapping.path_type == TemplatePathType.no_template_fit
    assert mapping.live_eligible is False
    assert "无已批准模板" in mapping.mapping_reason


def test_candidate_evaluation_path(flow_service, prd_raw_text):
    """Red line 3: Candidate evaluation path, never approved."""
    idea = flow_service.create_idea(prd_raw_text, "douyin")
    
    # Create candidate evaluation
    candidate = flow_service.create_candidate_evaluation(idea)
    
    # Red line 3: candidate is never approved
    assert candidate.is_approved_template is False
    assert candidate.stored_separately_from_live is True


def test_candidate_cannot_impersonate_approved(flow_service):
    """Red line 3: Candidate cannot be marked as approved (guard rejects)."""
    # Attempt to create candidate with is_approved_template=True
    with pytest.raises(ValueError, match="approved"):
        CandidateTemplateEvaluation(
            candidate_id="cand_001",
            idea_id="idea_001",
            is_approved_template=True,  # ← Guard should reject
            evaluation_status="pending",
            stored_separately_from_live=True,
            created_at=datetime.now(),
        )


def test_validation_failure_enters_rejected_registry(flow_service, prd_raw_text):
    """Red line 4: Failed idea enters RejectedStrategyRegistry."""
    idea = flow_service.create_idea(prd_raw_text, "douyin")
    
    # Fail validation
    rejected_entry = flow_service.reject_idea(
        idea,
        reason="回测历史数据显示无正向收益",
    )
    
    # Red line 4: entered registry
    assert rejected_entry is not None
    assert "回测" in rejected_entry["rejection_reason"] or "无正向收益" in rejected_entry["rejection_reason"]


def test_llm_cannot_change_live_eligible(flow_service, prd_raw_text):
    """Red line 2: LLM output cannot change live_eligible (deterministic only)."""
    idea = flow_service.create_idea(prd_raw_text, "douyin")
    
    # Mock LLM tries to set live_eligible=True
    with patch("backend.services.strategy_idea_flow.call_llm") as mock_llm:
        mock_llm.return_value = {
            "live_eligible": True,  # LLM tries to set
            "reason": "看起来很靠谱",
        }
        
        mapping = flow_service.map_to_template(
            idea,
            matched_template_id="template_001",
            template_version="v1",
            mapping_reason="LLM 说看起来靠谱",
        )
    
    # Red line 2: live_eligible still False (LLM cannot change)
    assert mapping.live_eligible is False


def test_strategy_draft_source_chain_complete(flow_service, prd_raw_text):
    """Red line 5: StrategyDraft must have complete source chain."""
    idea = flow_service.create_idea(prd_raw_text, "douyin")
    
    # Create draft with complete source chain
    draft = flow_service.create_strategy_draft(
        idea_id=idea.idea_id,
        mapped_template_id="template_001",
        template_version="v1",
        frozen_template_hash="abc123def456",
    )
    
    # Red line 5: all four fields present
    assert draft["source_idea_id"] == idea.idea_id
    assert draft["mapped_template_id"] == "template_001"
    assert draft["template_version"] == "v1"
    assert draft["frozen_template_hash"] == "abc123def456"


def test_strategy_draft_missing_source_field_rejected(flow_service, prd_raw_text):
    """Red line 5: StrategyDraft missing source field → creation fails."""
    idea = flow_service.create_idea(prd_raw_text, "douyin")
    
    # Missing frozen_template_hash
    with pytest.raises((ValueError, KeyError, TypeError), match="frozen_template_hash|source"):
        flow_service.create_strategy_draft(
            idea_id=idea.idea_id,
            mapped_template_id="template_001",
            template_version="v1",
            frozen_template_hash=None,  # ← Missing!
        )


def test_unfrozen_template_cannot_create_draft(flow_service, prd_raw_text):
    """Red line 3: Unfrozen/unapproved template cannot create StrategyDraft."""
    idea = flow_service.create_idea(prd_raw_text, "douyin")
    
    # Template not approved/frozen
    with pytest.raises(ValueError, match="approved|frozen"):
        flow_service.create_strategy_draft(
            idea_id=idea.idea_id,
            mapped_template_id="unapproved_template",
            template_version="v1",
            frozen_template_hash="xyz789",
            template_approved=False,  # ← Not approved
        )
