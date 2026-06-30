"""
Strategy Idea Contracts

Short-form video strategy idea intake and validation flow.

Red lines:
1. Idea defaults to untrusted, no signals until validated
2. LLM only extracts and explains, never directly enters strategy library
3. Only path to library: approved frozen template approval path
4. Failed/blocked ideas all enter RejectedStrategyRegistry
5. StrategyDraft must have hard source chain (Task 7)
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, field_validator


class StrategyIdeaTrustStatus(str, Enum):
    """Strategy idea trust status."""

    untrusted = "untrusted"
    under_validation = "under_validation"
    validated_passed = "validated_passed"
    rejected = "rejected"
    blocked = "blocked"


class TemplatePathType(str, Enum):
    """Template mapping path type."""

    approved_template_match = "approved_template_match"
    candidate_evaluation = "candidate_evaluation"
    no_template_fit = "no_template_fit"


class StrategyIdea(BaseModel, frozen=True, extra="forbid"):
    """
    Strategy idea from external source (e.g., short-form video).
    
    Red line 1: Defaults to untrusted, no signals until validated.
    """

    idea_id: str
    raw_source_text: str  # User's original words
    source_channel: str  # e.g., "douyin" (unreliable source)
    trust_status: StrategyIdeaTrustStatus
    created_at: datetime

    @field_validator("trust_status")
    @classmethod
    def default_untrusted(cls, v: StrategyIdeaTrustStatus) -> StrategyIdeaTrustStatus:
        """Ideas default to untrusted."""
        # Note: This validator doesn't enforce default, just validates
        return v


class StrategyIdeaExtraction(BaseModel, frozen=True, extra="forbid"):
    """
    LLM extraction result (claims, not verified facts).
    
    Red line 2: LLM only extracts, field names must have 'claimed_' prefix.
    """

    extraction_id: str
    idea_id: str
    # Claimed conditions (not verified facts!)
    claimed_entry: str  # e.g., "14:30 后买入"
    claimed_exit: str   # e.g., "次日早盘卖出"
    claimed_edge: Optional[str]  # Claimed edge (often missing in videos)
    # Source
    extraction_source: str  # Fixed: "llm_assisted"
    extracted_at: datetime

    @field_validator("extraction_source")
    @classmethod
    def source_must_be_llm_assisted(cls, v: str) -> str:
        """Extraction source must be llm_assisted (honest labeling)."""
        if v != "llm_assisted":
            raise ValueError("extraction_source must be 'llm_assisted'")
        return v


class TemplateMappingResult(BaseModel, frozen=True, extra="forbid"):
    """
    Template mapping result (LLM explanation + deterministic decision).
    
    Red line 3: Only approved frozen template path to library.
    """

    mapping_id: str
    idea_id: str
    path_type: TemplatePathType
    matched_template_id: Optional[str]
    template_version: Optional[str]
    mapping_reason: str  # LLM explanation (why it matches/doesn't)
    live_eligible: bool  # Only deterministic code can set True
    created_at: datetime


class CandidateTemplateEvaluation(BaseModel, frozen=True, extra="forbid"):
    """
    Candidate template evaluation (never approved).
    
    Red line 3: Candidate is never approved template.
    """

    candidate_id: str
    idea_id: str
    is_approved_template: bool  # Hardcoded False, guarded
    evaluation_status: str
    stored_separately_from_live: bool  # Hardcoded True
    created_at: datetime

    @field_validator("is_approved_template")
    @classmethod
    def never_approved(cls, v: bool) -> bool:
        """Candidate can never be approved template."""
        if v is True:
            raise ValueError("Candidate template cannot be marked as approved (is_approved_template must be False)")
        return v

    @field_validator("stored_separately_from_live")
    @classmethod
    def must_be_separate(cls, v: bool) -> bool:
        """Candidate must be stored separately."""
        if v is not True:
            raise ValueError("Candidate template must be stored separately (stored_separately_from_live must be True)")
        return v
