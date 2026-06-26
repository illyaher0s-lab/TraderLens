"""
Draft Contracts - TraderLens Schema v1.0

These contracts are defined but not yet implemented in production code.
Subject to change without migration path until promoted to stable.

Stability: DRAFT (M2)
Reserved for: M3+ research modules, execution tracking, task abstractions
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from contracts.stable import ContractModel


# =============================================================================
# Research Contracts (reserved for Evidence Agent / Serenity)
# =============================================================================

class EvidenceItem(ContractModel):
    """
    Single piece of evidence from research.
    
    Stability: DRAFT
    Reserved for: Evidence Agent (M3+)
    """
    type: str
    source: str
    content_summary: str
    published_at: date | None = None
    retrieved_at: date
    evidence_level: Literal["strong", "medium", "weak", "unknown"]
    expiry_days: int | None = Field(default=None, ge=0)
    stale_after: date | None = None


class EvidenceOutput(ContractModel):
    """
    Complete evidence collection result.
    
    Stability: DRAFT
    Reserved for: Evidence Agent (M3+)
    """
    symbol: str
    company_name: str
    check_depth: Literal["light", "deep"]
    identity_check: dict[str, Any]
    data_quality: Literal["ok", "degraded", "insufficient"]
    evidence_items: list[EvidenceItem] = Field(default_factory=list)
    evidence_summary: dict[str, list[str]] = Field(default_factory=dict)
    counter_evidence: list[str] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)
    relation_to_bottleneck: dict[str, Any]
    evidence_level: Literal["strong", "medium", "weak", "unknown"]
    missing_evidence: list[str] = Field(default_factory=list)
    next_check: list[str] = Field(default_factory=list)
    pipeline_suggestion: dict[str, Any]
    tool_trace: list[dict[str, Any]] = Field(default_factory=list)


class KillCriteria(ContractModel):
    """
    Falsification criteria for hypothesis.
    
    Stability: DRAFT
    Reserved for: Evidence Agent (M3+)
    """
    id: str
    description: str
    category: str
    data_required: list[str]
    trigger_rule: dict[str, Any]
    action_on_trigger: str
    evaluator: Literal["strategy_core", "data_quality", "evidence_agent"]


class KillCriteriaSnapshot(ContractModel):
    """
    Frozen kill criteria before evidence run.
    
    Stability: DRAFT
    Reserved for: Evidence Agent (M3+)
    
    Must be frozen (editable=False) before Evidence Agent can run.
    """
    hypothesis_id: str
    criteria_version: str
    frozen_at: datetime
    frozen_by: str
    criteria_hash: str
    editable: bool = False
    code_checkable: list[KillCriteria] = Field(default_factory=list)
    evidence_checkable: list[KillCriteria] = Field(default_factory=list)

    @field_validator("editable")
    @classmethod
    def snapshot_must_be_frozen(cls, value: bool) -> bool:
        if value:
            raise ValueError("kill_criteria_snapshot must be frozen before evidence runs")
        return value


class HypothesisDraft(ContractModel):
    """
    Generated hypothesis draft from research.
    
    Stability: DRAFT
    Reserved for: Serenity / Hypothesis Builder (M3+)
    """
    hypothesis_id: str
    theme_id: str
    thesis: str
    universe_snapshot_date: date
    generated_at: datetime
    kill_criteria_snapshot: KillCriteriaSnapshot


# =============================================================================
# Execution Tracking Contracts (reserved for Signal Board / live execution)
# =============================================================================

class PositionPlan(ContractModel):
    """
    Position planning metadata.
    
    Stability: DRAFT
    Reserved for: Signal Board / Action Plan (M3+)
    """
    max_position_pct: float = Field(ge=0, le=1)
    current_position_pct: float = Field(ge=0, le=1)
    planned_position_pct: float = Field(ge=0, le=1)
    available_position_pct: float = Field(ge=0, le=1)
    portfolio_source: Literal["paper_portfolio", "manual_input", "unavailable"]


class InvalidCondition(ContractModel):
    """
    Condition that invalidates a trade plan.
    
    Stability: DRAFT
    Reserved for: Signal Board (M3+)
    """
    type: Literal["market_state", "stock_status", "price_limit", "liquidity"]
    scope: Literal["market", "stock"]
    rule: str


class TradePlan(ContractModel):
    """
    Trade plan generated from signal.
    
    Stability: DRAFT
    Reserved for: Signal Board / Action Plan (M3+)
    
    Not implemented in M1/M2. Reserved for future execution tracking.
    """
    trade_plan_id: str
    signal_id: str
    planned_trade_date: date
    planned_action: Literal["plan_buy", "plan_sell", "hold", "no_action"]
    execution_window: Literal["open_next_day", "close_next_day", "conservative"]
    position_plan: PositionPlan
    invalid_if: list[InvalidCondition]
    fallback_action: Literal["cancel", "defer_next_day", "manual_review"]
    next_check_date: date | None = None
    post_trade_review_date: date | None = None
    generated_by: str = "action_plan_generator"
    audit_id: str


class ExecutionLog(ContractModel):
    """
    User execution log for paper trading or live tracking.
    
    Stability: DRAFT
    Reserved for: Execution tracking (M3+)
    
    Not implemented in M1/M2. Reserved for future live execution integration.
    """
    execution_log_id: str
    trade_plan_id: str
    user_actual_action: Literal["executed", "skipped", "modified", "not_recorded"]
    actual_price: float | None = Field(default=None, ge=0)
    actual_quantity: int | None = Field(default=None, ge=0)
    manual_override: bool
    override_reason: str | None = None
    drift_type: Literal["price_drift", "quantity_drift", "timing_drift", "skip"] | None = None
    note: str | None = None
    recorded_at: datetime
    audit_id: str


class ForwardCandidate(ContractModel):
    """
    Forward-looking candidate from research pipeline.
    
    Stability: DRAFT
    Reserved for: Evidence pipeline / Forward tracking (M3+)
    """
    id: str
    date_added: date
    theme_id: str
    theme_name: str
    source_run_id: str
    evidence_pack_id: str
    symbol: str
    company_name: str
    chain_layer: str
    evidence_level: Literal["high", "medium", "low", "unknown"]
    thesis: str
    invalidation_rules: list[dict[str, Any]]
    price_snapshot: dict[str, Any]
    benchmark: dict[str, Any]
    review_policy: dict[str, Any]
    status: Literal["active", "converted_to_strategy", "downgraded", "removed"]
    latest_review_result: dict[str, Any] | None = None
    alpha_vs_benchmark: float | None = None
    converted_to_strategy_id: str | None = None


# =============================================================================
# Task Abstraction Contracts (M2 boundary discussion)
# =============================================================================

class BacktestTask(ContractModel):
    """
    Backtest task definition.
    
    Stability: DRAFT (M2 discussion)
    
    Used by: backend/app/worker.py (skeleton only)
    
    M2 decision pending: Should this be the primary task abstraction?
    Or should we have a more general Task contract?
    """
    task_id: str
    strategy_config: "StrategyConfig"  # Forward reference to stable contract
    created_at: datetime


class BacktestReport(ContractModel):
    """
    Backtest report metadata.
    
    Stability: DRAFT (M2 discussion)
    
    M2 decision pending: Is this distinct from BacktestResult?
    Should reports be a separate abstraction layer?
    """
    report_id: str
    task_id: str
    strategy_name: str
    status: Literal["fixture_only", "success", "failed", "prototype_passed", "rejected"]
    generated_at: datetime
    metrics: dict[str, Any] = Field(default_factory=dict)
    admission_gate: dict[str, Any] = Field(default_factory=dict)
    m0_scope_note: str | None = None


class AuditLog(ContractModel):
    """
    General-purpose audit log.
    
    Stability: DRAFT (M2 discussion)
    
    M2 decision pending: Should this be the primary audit abstraction?
    Or should we have more specific audit contracts (BacktestAudit, StrategyAudit)?
    """
    audit_id: str
    event_type: str
    created_at: datetime
    actor: str
    payload: dict[str, Any]
    tool_snapshots: list[dict[str, Any]] = Field(default_factory=list)


# Forward reference resolution
from contracts.stable import StrategyConfig
BacktestTask.model_rebuild()
