"""
Approval Card Contract

Result-level approval cards for V1 Agent Workbench.

User can only approve result-level decisions. Technical decisions
(strategy parameters, thresholds, OOS, stop-loss, liquidity rules,
manual execution fields) are blocked.

Allowed approval decisions:
- continue: Continue to next stage
- stop: Stop this workflow
- downgrade_to_observation: Track without live execution
- enter_risk_capped_live_execution: Approve live trading with risk cap
- accept_execution_record_interpretation: Approve parsed execution record
"""

from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field, field_validator


# Allowed approval decisions (exhaustive list)
ALLOWED_DECISIONS = {
    "continue",
    "stop",
    "downgrade_to_observation",
    "enter_risk_capped_live_execution",
    "accept_execution_record_interpretation",
}


def ApprovalDecision(value: str) -> str:
    """
    Validate approval decision.

    Only allowed decisions are accepted. Unknown decisions raise ValueError.
    """
    if value not in ALLOWED_DECISIONS:
        raise ValueError(
            f"Unknown decision: {value}. "
            f"Allowed decisions: {', '.join(sorted(ALLOWED_DECISIONS))}"
        )
    return value


class ApprovalCard(BaseModel):
    """
    Result-level approval card.

    User approves high-level decisions only. Technical decisions are blocked.

    Blocked technical decisions (user cannot approve):
    - candidate_pool_technical_quality
    - strategy_parameters
    - oos_windows
    - thresholds
    - stop_loss
    - liquidity_rules
    - manual_execution_fields
    """

    approval_card_id: str = Field(
        ...,
        description="Unique identifier for this approval card",
    )

    workflow_id: str = Field(
        ...,
        description="Workflow session this card belongs to",
    )

    stage: str = Field(
        ...,
        description="Workflow stage (e.g., research_confirmation, validation_gate, execution_card)",
    )

    title: str = Field(
        ...,
        description="Human-readable card title",
    )

    plain_language_summary: str = Field(
        ...,
        description="Plain-language summary of what user is approving",
    )

    allowed_decisions: list[str] = Field(
        ...,
        description="List of allowed decisions for this card (subset of ALLOWED_DECISIONS)",
    )

    blocked_technical_decisions: list[str] = Field(
        default_factory=list,
        description="List of technical decisions user cannot make (for audit)",
    )

    artifact_ids: list[str] = Field(
        ...,
        description="Artifact IDs (research report, validation report, execution record) backing this card",
    )

    created_at: datetime = Field(
        ...,
        description="When this card was created",
    )

    decided_at: datetime | None = Field(
        None,
        description="When user made decision (None if pending)",
    )

    decision: str | None = Field(
        None,
        description="User's decision (None if pending)",
    )

    decided_by: str | None = Field(
        None,
        description="User who made decision (None if pending)",
    )

    @field_validator("artifact_ids")
    @classmethod
    def validate_artifact_ids(cls, v):
        """Every approval card requires at least one artifact_id."""
        if not v or len(v) == 0:
            raise ValueError("Approval card requires at least one artifact_id")
        return v

    @field_validator("decision")
    @classmethod
    def validate_decision(cls, v):
        """Decision must be in ALLOWED_DECISIONS if present."""
        if v is not None:
            ApprovalDecision(v)  # Raises if invalid
        return v
