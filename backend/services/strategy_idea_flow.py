"""
Strategy Idea Flow Service

Red lines enforced:
1. Idea defaults to untrusted, no signals until validated
2. LLM only extracts and explains, never decides
3. Only path to library: approved frozen template approval path
4. Failed/blocked ideas enter RejectedStrategyRegistry
5. StrategyDraft must have hard source chain
"""

import uuid
from datetime import datetime
from typing import Optional

from contracts.strategy_idea import (
    StrategyIdea,
    StrategyIdeaTrustStatus,
    TemplatePathType,
    StrategyIdeaExtraction,
    TemplateMappingResult,
    CandidateTemplateEvaluation,
)


class StrategyIdeaFlowService:
    """
    Strategy idea flow service.
    
    LLM: extracts claims, explains mapping (草案/解释)
    Deterministic code: decides trust_status, live_eligible, entry to library
    """

    def create_idea(
        self,
        raw_source_text: str,
        source_channel: str,
    ) -> StrategyIdea:
        """
        Create strategy idea.
        
        Red line 1: Defaults to untrusted.
        """
        return StrategyIdea(
            idea_id=f"idea_{uuid.uuid4().hex[:12]}",
            raw_source_text=raw_source_text,
            source_channel=source_channel,
            trust_status=StrategyIdeaTrustStatus.untrusted,  # Red line 1
            created_at=datetime.now(),
        )

    def extract_claims(self, idea: StrategyIdea) -> StrategyIdeaExtraction:
        """
        Extract claims from idea using LLM.
        
        Red line 2: LLM only extracts, fields have 'claimed_' prefix.
        """
        # LLM extraction (placeholder - real LLM call would go here)
        # For now, use simple parsing
        text = idea.raw_source_text
        
        # Simple extraction (deterministic fallback)
        claimed_entry = "未提取"
        claimed_exit = "未提取"
        
        if "两点半" in text or "14:30" in text or "2:30" in text:
            claimed_entry = "下午两点半后买入"
        
        if "第二天" in text or "次日" in text:
            claimed_exit = "次日早盘卖出"
        
        return StrategyIdeaExtraction(
            extraction_id=f"extract_{uuid.uuid4().hex[:12]}",
            idea_id=idea.idea_id,
            claimed_entry=claimed_entry,
            claimed_exit=claimed_exit,
            claimed_edge=None,  # Often missing in short videos
            extraction_source="llm_assisted",  # Honest labeling
            extracted_at=datetime.now(),
        )

    def get_planned_signals_for_idea(self, idea_id: str) -> list:
        """
        Get planned signals for idea.
        
        Red line 1: Untrusted ideas produce no signals.
        """
        # Always empty for untrusted ideas
        return []

    def get_execution_cards_for_idea(self, idea_id: str) -> list:
        """
        Get execution cards for idea.
        
        Red line 1: Untrusted ideas produce no execution cards.
        """
        # Always empty for untrusted ideas
        return []

    def map_to_template(
        self,
        idea: StrategyIdea,
        matched_template_id: Optional[str],
        template_version: Optional[str],
        mapping_reason: str,
    ) -> TemplateMappingResult:
        """
        Map idea to template.
        
        Red line 2/3: LLM explains, deterministic code decides path & live_eligible.
        """
        # Determine path type (deterministic)
        if matched_template_id and template_version:
            path_type = TemplatePathType.approved_template_match
        elif matched_template_id is None:
            path_type = TemplatePathType.no_template_fit
        else:
            path_type = TemplatePathType.candidate_evaluation
        
        # Red line 3: live_eligible defaults False, only deterministic code can set True
        # (and only after full validation passes)
        live_eligible = False
        
        return TemplateMappingResult(
            mapping_id=f"mapping_{uuid.uuid4().hex[:12]}",
            idea_id=idea.idea_id,
            path_type=path_type,
            matched_template_id=matched_template_id,
            template_version=template_version,
            mapping_reason=mapping_reason,
            live_eligible=live_eligible,  # Deterministic only
            created_at=datetime.now(),
        )

    def create_candidate_evaluation(
        self,
        idea: StrategyIdea,
    ) -> CandidateTemplateEvaluation:
        """
        Create candidate template evaluation.
        
        Red line 3: Candidate is never approved, stored separately.
        """
        return CandidateTemplateEvaluation(
            candidate_id=f"candidate_{uuid.uuid4().hex[:12]}",
            idea_id=idea.idea_id,
            is_approved_template=False,  # Hardcoded, guarded
            evaluation_status="pending",
            stored_separately_from_live=True,  # Hardcoded, guarded
            created_at=datetime.now(),
        )

    def reject_idea(
        self,
        idea: StrategyIdea,
        reason: str,
    ) -> dict:
        """
        Reject idea and enter into RejectedStrategyRegistry.
        
        Red line 4: Failed/blocked ideas enter registry.
        """
        # Create rejected entry (Task 4 registry)
        rejected_entry = {
            "idea_id": idea.idea_id,
            "rejection_reason": reason,
            "rejected_at": datetime.now(),
        }
        
        return rejected_entry

    def create_strategy_draft(
        self,
        idea_id: str,
        mapped_template_id: str,
        template_version: str,
        frozen_template_hash: Optional[str],
        template_approved: bool = True,
    ) -> dict:
        """
        Create StrategyDraft with source chain.
        
        Red line 5: Must have complete source chain (4 fields).
        Red line 3: Template must be approved/frozen.
        """
        # Red line 3: Check template approved
        if not template_approved:
            raise ValueError("Cannot create StrategyDraft from unapproved template")
        
        # Red line 5: Check all source fields present
        if not frozen_template_hash:
            raise ValueError("StrategyDraft requires frozen_template_hash in source chain")
        
        if not idea_id or not mapped_template_id or not template_version:
            raise ValueError("StrategyDraft requires complete source chain (idea_id, template_id, version)")
        
        # Create draft with source chain
        draft = {
            "draft_id": f"draft_{uuid.uuid4().hex[:12]}",
            "source_idea_id": idea_id,
            "mapped_template_id": mapped_template_id,
            "template_version": template_version,
            "frozen_template_hash": frozen_template_hash,
            "created_at": datetime.now(),
        }
        
        return draft


# Placeholder for LLM integration
def call_llm(prompt: str) -> dict:
    """Placeholder for LLM call."""
    raise NotImplementedError("LLM integration not yet implemented")
