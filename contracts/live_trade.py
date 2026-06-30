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


class PositionLifecycleState(str, Enum):
    """Position lifecycle state."""

    open = "open"
    closed = "closed"


class DailySignalType(str, Enum):
    """Daily observation signal type."""

    hold = "hold"
    sell = "sell"
    risk = "risk"
    invalidated = "invalidated"


class InvalidationTrigger(str, Enum):
    """Invalidation trigger types (拆细 invalidated)."""

    price_break = "price_break"
    fundamental_breach = "fundamental_breach"
    thesis_broken = "thesis_broken"
    event_risk = "event_risk"
    theme_faded = "theme_faded"
    stop_rule = "stop_rule"


class ExplanationSource(str, Enum):
    """Explanation source for daily signals."""

    none = "none"
    template_text = "template_text"
    llm_assisted = "llm_assisted"


class PnlSource(str, Enum):
    """P&L source (Task 10)."""

    user_reported = "user_reported"
    calculated_from_confirmed_details = "calculated_from_confirmed_details"
    incomplete = "incomplete"
    # NOTE: broker_verified intentionally NOT included (red line 1)


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


class ObservationPosition(BaseModel, frozen=True, extra="forbid"):
    """
    Observation pool position.
    
    Red line 1: only created from ExecutionObservationLog (confirmed), never from draft.
    """

    position_id: str
    # Evidence chain (5 IDs + source_log_id pointing to confirmed log)
    source_log_id: str  # Must point to ExecutionObservationLog
    execution_card_id: str
    signal_id: str
    action_plan_id: str
    capital_context_id: str
    # Position details
    symbol: str
    name: str
    entry_price: float  # From confirmed log, not fabricated
    quantity: int
    # Template rules lock
    template_id: str
    template_version: str
    # Entry thesis snapshot
    entry_thesis: str
    # Lifecycle
    lifecycle_state: PositionLifecycleState
    opened_at: datetime
    closed_at: Optional[datetime]

    @field_validator("source_log_id", "execution_card_id", "signal_id", "action_plan_id", "capital_context_id")
    @classmethod
    def evidence_chain_must_be_non_empty(cls, v: str, info) -> str:
        """Evidence chain fields must all be non-empty."""
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must be non-empty (evidence chain required)")
        return v

    @field_validator("entry_price")
    @classmethod
    def entry_price_must_be_positive(cls, v: float) -> float:
        """Entry price must be > 0."""
        if v <= 0:
            raise ValueError("entry_price must be positive")
        return v

    @field_validator("quantity")
    @classmethod
    def quantity_must_be_positive(cls, v: int) -> int:
        """Quantity must be > 0."""
        if v <= 0:
            raise ValueError("quantity must be positive")
        return v


class DailyObservationSignal(BaseModel, frozen=True, extra="forbid"):
    """
    Daily observation signal for a position.
    
    Red line 2: 100% deterministic reducer output, LLM never decides.
    Red line 3: hold signals have zero LLM calls, only sell/risk/invalidated may call LLM once for explanation.
    """

    signal_record_id: str
    position_id: str
    signal_type: DailySignalType
    triggered_invalidations: list[InvalidationTrigger]  # Empty for hold
    as_of_date: datetime
    market_data_state: MarketDataFaultState
    # Audit trail (must be present and complete)
    rule_trace: dict  # {"rule": "stop_rule", "threshold": -0.08, "actual": -0.093, "hit": true}
    # Explanation (only filled for sell/risk/invalidated, empty for hold)
    plain_explanation: Optional[str]
    explanation_source: ExplanationSource

    @field_validator("triggered_invalidations")
    @classmethod
    def triggered_invalidations_empty_for_hold(cls, v: list[InvalidationTrigger], info) -> list[InvalidationTrigger]:
        """triggered_invalidations must be empty for hold signals."""
        # Note: validator runs before we can access signal_type, so we validate in service layer
        return v


class PnlRecord(BaseModel, frozen=True, extra="forbid"):
    """
    P&L record (Task 10).
    
    Red line 1: Only from user-confirmed execution details, never fabricated.
    """

    pnl_record_id: str
    position_id: str
    # From confirmed logs (None if missing)
    buy_price: Optional[float]
    sell_price: Optional[float]
    quantity: Optional[int]
    fees: Optional[float]
    # Calculated P&L (None if incomplete)
    pnl_amount: Optional[float]
    pnl_pct: Optional[float]
    # Source and completeness
    pnl_source: PnlSource
    missing_fields: list[str]
    computed_at: datetime


class PlanAdherenceResult(BaseModel, frozen=True, extra="forbid"):
    """
    Plan adherence result.
    
    Red line 4: Determined by deterministic rules, not LLM.
    """

    followed_plan: Optional[bool]  # None = undetermined
    deviations: list[dict]  # [{"type": "late_exit", "signal_date": "D+2", ...}]
    adherence_trace: dict  # Audit trail


class DisciplineReview(BaseModel, frozen=True, extra="forbid"):
    """
    Discipline review for a closed position.
    
    Red lines:
    2. Complete input chain required, missing parts explicitly marked
    3. LLM only explains, never recommends forward-looking actions
    4. Plan adherence by rules, not LLM
    """

    review_id: str
    position_id: str
    # Evidence chain (延续证据链)
    execution_card_id: str
    signal_id: str
    daily_signal_ids: list[str]
    buy_log_id: str
    sell_log_id: str
    # Input completeness
    input_completeness: dict  # {"execution_card": "present", "sell_log": "missing", ...}
    # P&L and adherence
    pnl_record: PnlRecord
    plan_adherence: PlanAdherenceResult
    # LLM narrative (optional)
    plain_narrative: Optional[str]
    narrative_source: ExplanationSource
    forward_looking_guard_passed: bool
    created_at: datetime
