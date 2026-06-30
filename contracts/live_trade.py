"""
V1 Live Trade Contracts

Defines recommendation levels, statuses, and execution card structure.
No LLM, no Tushare, no random, no broker connections, no auto-execution.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, field_validator, model_validator

from contracts.market_data_fault import MarketDataFaultState


class ExecutionInterpretationStatus(str, Enum):
    """Execution observation interpretation status."""

    draft_pending_confirmation = "draft_pending_confirmation"
    needs_more_info = "needs_more_info"
    confirmed = "confirmed"
    corrected = "corrected"
    rejected = "rejected"


class RecommendationLevel(str, Enum):
    """Recommendation level for execution decisions."""

    strongly_execute = "strongly_execute"
    executable = "executable"
    pause_observation = "pause_observation"
    do_not_execute = "do_not_execute"
    abandon = "abandon"


class StrategyStatus(str, Enum):
    """Strategy validation status."""

    prototype_passed = "prototype_passed"
    under_review = "under_review"
    rejected = "rejected"
    blocked = "blocked"


class SignalStatus(str, Enum):
    """Signal lifecycle status."""

    active = "active"
    inactive = "inactive"
    expired = "expired"
    pending = "pending"


class ActionPlanStatus(str, Enum):
    """Action Plan validation status."""

    valid = "valid"
    pending = "pending"
    invalidated = "invalidated"


class PriceRangeStatus(str, Enum):
    """Current price vs allowed range status."""

    inside_range = "inside_range"
    outside_range = "outside_range"
    near_boundary = "near_boundary"
    unknown = "unknown"


class MarketStatus(str, Enum):
    """Market execution environment status."""

    normal = "normal"
    caution = "caution"
    halted = "halted"
    abnormal = "abnormal"


class RiskBlocker(str, Enum):
    """Active risk blockers."""

    position_limit_reached = "position_limit_reached"
    daily_loss_limit = "daily_loss_limit"
    correlation_risk = "correlation_risk"
    liquidity_insufficient = "liquidity_insufficient"
    suspended = "suspended"


class CostValidationResult(str, Enum):
    """Cost validation result."""

    passed = "passed"
    failed = "failed"
    not_applicable = "not_applicable"


class UserObservation(str, Enum):
    """User intraday observation (downgrade only)."""

    execution_risk = "execution_risk"
    market_concern = "market_concern"
    strategy_doubt = "strategy_doubt"


class RecommendationInput(BaseModel, frozen=True, extra="forbid"):
    """Input for deterministic recommendation reducer."""

    strategy_status: StrategyStatus
    signal_status: SignalStatus
    signal_admitted: bool
    signal_stale: bool
    action_plan_status: ActionPlanStatus
    price_range_status: PriceRangeStatus
    market_data_state: MarketDataFaultState
    risk_blockers: list[RiskBlocker]
    market_status: MarketStatus
    base_cost_passed: bool
    stress_cost_passed: bool
    capital_confirmed: bool
    capital_sufficient: bool
    user_observation: Optional[UserObservation] = None


class ExecutionCard(BaseModel, frozen=True, extra="forbid"):
    """Execution card for human review and manual execution."""

    symbol: str
    name: str
    direction: str
    recommendation_level: RecommendationLevel
    planned_cash_amount: float
    planned_share_count: int
    allowed_price_range: tuple[float, float]
    maximum_acceptable_deviation: float
    invalidation_conditions: list[str]
    review_time: datetime
    reasons: list[str]
    risks: list[str]
    market_data_state: MarketDataFaultState
    artifact_ids: list[str]

    @field_validator("symbol", "name", "direction")
    @classmethod
    def must_be_non_empty_string(cls, v: str, info) -> str:
        """Symbol, name, and direction must be non-empty."""
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must be non-empty")
        return v

    @field_validator("artifact_ids")
    @classmethod
    def artifact_ids_must_not_be_empty(cls, v: list[str]) -> list[str]:
        """artifact_ids must contain at least one upstream artifact (signal/plan)."""
        if not v:
            raise ValueError(
                "artifact_ids must contain at least one upstream artifact (no execution without evidence)"
            )
        return v

    @field_validator("planned_cash_amount")
    @classmethod
    def planned_cash_must_be_non_negative(cls, v: float) -> float:
        """Planned cash amount must be non-negative."""
        if v < 0:
            raise ValueError("planned_cash_amount must be non-negative")
        return v

    @field_validator("planned_share_count")
    @classmethod
    def planned_share_count_must_be_non_negative(cls, v: int) -> int:
        """Planned share count must be non-negative."""
        if v < 0:
            raise ValueError("planned_share_count must be non-negative")
        return v

    @model_validator(mode="after")
    def validate_price_range(self):
        """Allowed price range must have low <= high and both > 0."""
        low, high = self.allowed_price_range
        if low <= 0 or high <= 0:
            raise ValueError("allowed_price_range values must be > 0")
        if low > high:
            raise ValueError("allowed_price_range low must be <= high")
        return self


class ExecutionObservationDraft(BaseModel, frozen=True, extra="forbid"):
    """
    Execution observation draft from natural-language user feedback.
    
    Red lines:
    1. Draft never auto-promotes to log — user must confirm/correct.
    2. broker_verified is always False, cannot be set True.
    3. No fabricated price/quantity — missing fields → needs_more_info.
    """

    draft_id: str
    # Evidence chain (Task 7 linkage, all required non-empty)
    execution_card_id: str
    signal_id: str
    action_plan_id: str
    capital_context_id: str
    market_snapshot_id: str
    # User input
    raw_user_text: str
    # Parsed fields
    parsed_action: str  # buy / sell / none
    parsed_execution_status: str  # executed_full / executed_partial / skipped / forgot / abandoned
    parsed_price: Optional[float]
    parsed_quantity: Optional[int]
    parsed_reason: Optional[str]
    # Follow-up
    missing_fields: list[str]
    follow_up_question: Optional[str]
    # Metadata
    interpretation_source: str  # deterministic / llm_assisted
    status: ExecutionInterpretationStatus
    broker_verified: bool
    created_at: datetime

    @field_validator("broker_verified")
    @classmethod
    def broker_verified_must_be_false(cls, v: bool) -> bool:
        """Red line 2: broker_verified must always be False in draft."""
        if v is not False:
            raise ValueError("broker_verified must be False (no broker verification in V1)")
        return v

    @field_validator("execution_card_id", "signal_id", "action_plan_id", "capital_context_id", "market_snapshot_id")
    @classmethod
    def evidence_chain_must_be_non_empty(cls, v: str, info) -> str:
        """Evidence chain fields must all be non-empty."""
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must be non-empty (evidence chain required)")
        return v


class ExecutionObservationLog(BaseModel, frozen=True, extra="forbid"):
    """
    Confirmed execution observation log.
    
    Only created after user confirm/correct, never auto-generated from draft.
    """

    log_id: str
    draft_id: str
    # Evidence chain (same as draft)
    execution_card_id: str
    signal_id: str
    action_plan_id: str
    capital_context_id: str
    market_snapshot_id: str
    # Confirmed fields
    confirmed_action: str  # buy / sell / none
    confirmed_execution_status: str  # executed_full / executed_partial / skipped / forgot / abandoned
    confirmed_price: Optional[float]
    confirmed_quantity: Optional[int]
    reason: Optional[str]
    # Metadata
    confirmed_by_user: bool
    broker_verified: bool
    confirmed_at: datetime

    @field_validator("broker_verified")
    @classmethod
    def broker_verified_must_be_false_in_log(cls, v: bool) -> bool:
        """Red line 2: broker_verified must always be False (no broker in V1)."""
        if v is not False:
            raise ValueError("broker_verified must be False (no broker verification in V1)")
        return v

    @field_validator("confirmed_by_user")
    @classmethod
    def confirmed_by_user_must_be_true(cls, v: bool) -> bool:
        """Log must be user-confirmed."""
        if v is not True:
            raise ValueError("confirmed_by_user must be True (no auto-promotion)")
        return v
