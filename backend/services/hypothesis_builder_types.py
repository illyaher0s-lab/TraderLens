"""B2 Hypothesis Builder types - Frozen contracts for LLM template selection."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator

from contracts.strategy import BacktestUniverseSpec


class LLMTemplateSelection(BaseModel):
    """
    LLM output contract for template selection.
    
    LLM is ONLY allowed to choose a template ID and explain reasoning.
    No parameters, no status, no hash, no Gate, no OOS, no budget.
    """
    
    model_config = ConfigDict(frozen=True, extra="forbid")
    
    strategy_template_id: str
    template_selection_reason: str
    unmapped_hypothesis_elements: tuple[str, ...] = ()
    
    @field_validator("strategy_template_id", "template_selection_reason")
    @classmethod
    def must_be_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must be non-empty")
        return value


class HypothesisBuilderInput(BaseModel):
    """
    Input contract for Hypothesis Builder.
    
    Contains all context needed to select a template and generate strategy draft.
    """
    
    model_config = ConfigDict(frozen=True, extra="forbid")
    
    theme_id: str
    hypothesis_id: str
    hypothesis_source_snapshot_id: str
    hypothesis_type: str
    hypothesis_text: str
    rule_candidates: dict
    evidence_summary: dict | None
    backtest_universe_spec: BacktestUniverseSpec
    strategy_revision_id: str
    
    @field_validator("strategy_revision_id")
    @classmethod
    def revision_id_must_be_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("strategy_revision_id must be non-empty")
        return value


class HypothesisBuilderResult(BaseModel):
    """
    B2 Hypothesis Builder result contract.
    
    Success: status=success, contains strategy_draft and validation_result.
    Failure: status=failed, contains error details.
    """
    
    model_config = ConfigDict(frozen=True, extra="forbid")
    
    status: str  # "success" or "failed"
    strategy_revision_id: str
    selected_template_id: str | None = None
    template_selection_reason: str | None = None
    unmapped_hypothesis_elements: tuple[str, ...] = ()
    strategy_config_json: str | None = None
    validation_result: str | None = None  # "pass" or error details
    repair_attempts: int = 0
    failure_stage: str | None = None  # "template_selection" | "validation" | "repair_exhausted" | "storage"
    errors: tuple[str, ...] = ()
    raw_llm_output_snapshot: str | None = None
    validation_errors: tuple[str, ...] = ()
