"""
Action Plan Data Models

C3 Action Plan: Human execution boundary for admitted planned signals.

Action Plan is NOT:
- A buy/sell recommendation
- An automatic execution trigger
- A profit guarantee
- A live trading signal

Action Plan IS:
- A checklist for human to decide whether to act on an admitted signal
- A structured record of pre-action checks and invalidation conditions
- A discipline layer for manual execution decisions
- A human decision log (execute/skip/partial/expired)

Design Principles:
- Deterministic generation from PlannedSignal (no LLM, no external data)
- Rule-based freshness, blocking, and warning logic
- No broker/order/fill/P&L fields (those belong to C4 Execution Log)
- Neutral user-facing language (入场/离场/处理/放弃, not 买入/卖出建议)
"""

from datetime import date, datetime
from typing import Literal
from pydantic import BaseModel, Field


class ActionCheck(BaseModel):
    """
    A single pre-action or invalidation check for Action Plan.

    Used to build structured checklists for human execution decisions.
    """

    check_id: str = Field(
        ...,
        description="Unique identifier for this check (e.g., 'admission_check', 'freshness_check')"
    )

    label: str = Field(
        ...,
        description="Human-readable check name (e.g., '信号准入检查', '日期新鲜度检查')"
    )

    source: Literal["strategy_core", "signal_metadata", "risk_flag", "system_rule"] = Field(
        ...,
        description="Where this check comes from: strategy_core output, signal metadata, risk flag, or system rule"
    )

    status: Literal["pass", "warning", "blocked", "unknown"] = Field(
        ...,
        description="Check result: pass=通过, warning=警告, blocked=阻断, unknown=未知"
    )

    blocking: bool = Field(
        ...,
        description="Whether this check blocks execution if not pass (true=阻断执行, false=仅提示)"
    )

    detail: str = Field(
        ...,
        description="Human-readable detail or reason (e.g., '信号状态: prototype_passed', '新鲜度: 过期 2 日')"
    )


class UserActionDecision(BaseModel):
    """
    User decision on Action Plan.

    Records what the human decided to do with this Action Plan.
    Does NOT record actual fills or executions (those belong to C4 Execution Log).
    """

    decision: Literal["execute", "skip", "partial", "expired"] = Field(
        ...,
        description="User decision: execute=准备执行, skip=今日放弃, partial=部分执行, expired=标记过期"
    )

    decided_at: datetime = Field(
        ...,
        description="When user made this decision"
    )

    decided_by: str = Field(
        ...,
        description="Username who made this decision"
    )

    reason: str | None = Field(
        None,
        description="Why user made this decision (required for skip/partial/expired)"
    )

    manual_notes: str | None = Field(
        None,
        description="Free-form notes from user (optional)"
    )


class ExecutionWindow(BaseModel):
    """
    Time window for Action Plan execution.

    Defines when this Action Plan is fresh, stale, or expired.
    """

    planned_date: date = Field(
        ...,
        description="Intended execution date from signal (T+1)"
    )

    valid_for_date: date = Field(
        ...,
        description="Date when this Action Plan is still valid (same as planned_date for C3 MVP)"
    )

    expires_after_date: date = Field(
        ...,
        description="Date after which this Action Plan is expired (planned_date + 1 trading day)"
    )


class ActionPlan(BaseModel):
    """
    Action Plan for an admitted planned signal.

    Generated deterministically from PlannedSignal.
    Provides structured checklist for human execution decisions.

    Does NOT:
    - Generate new signals
    - Make buy/sell recommendations
    - Auto-execute trades
    - Guarantee profit
    - Record actual fills (that's C4 Execution Log)

    Does:
    - Check admission status
    - Check freshness (fresh/stale/expired)
    - Check blocking conditions (evidence, review status, expiration)
    - Check warning conditions (risk flags, missing data)
    - Provide pre-action checklist
    - Provide invalidation conditions
    - Record user decision (execute/skip/partial/expired)
    """

    action_plan_id: str = Field(
        ...,
        description="Unique identifier for this Action Plan (UUID or deterministic hash)"
    )

    signal_id: str = Field(
        ...,
        description="PlannedSignal this Action Plan is based on"
    )

    strategy_id: str = Field(
        ...,
        description="Strategy identifier from signal"
    )

    strategy_version: str = Field(
        ...,
        description="Strategy version from signal"
    )

    strategy_revision_id: str | None = Field(
        None,
        description="Strategy revision ID from signal (C1 admission metadata)"
    )

    snapshot_hash: str = Field(
        ...,
        description="Snapshot hash from signal (reproducibility)"
    )

    symbol: str = Field(
        ...,
        description="Stock symbol from signal"
    )

    planned_action: Literal["enter", "exit"] = Field(
        ...,
        description="Planned action from signal (enter=入场, exit=离场). Neutral language, not buy/sell recommendation."
    )

    signal_date: date = Field(
        ...,
        description="When signal was generated"
    )

    intended_execution_date: date = Field(
        ...,
        description="Intended execution date from signal (T+1)"
    )

    action_plan_date: date = Field(
        ...,
        description="When this Action Plan was generated"
    )

    status: Literal[
        "draft",
        "ready_for_human",
        "user_marked_execute",
        "user_marked_skip",
        "user_marked_partial",
        "expired"
    ] = Field(
        ...,
        description="Action Plan status: draft=生成中, ready_for_human=待人工决定, user_marked_*=已决定, expired=已过期"
    )

    freshness_status: Literal["fresh", "stale", "expired"] = Field(
        ...,
        description="Freshness: fresh=新鲜(今日可执行), stale=不新鲜(已过计划日期1日), expired=已过期(超过2日)"
    )

    execution_window: ExecutionWindow = Field(
        ...,
        description="Time window for execution"
    )

    pre_action_checks: list[ActionCheck] = Field(
        default_factory=list,
        description="Pre-action checks (admission, freshness, evidence, risk, linkage)"
    )

    invalidation_checks: list[ActionCheck] = Field(
        default_factory=list,
        description="Invalidation checks (expired signal, blocked evidence, ignored/expired review status)"
    )

    risk_warnings: list[str] = Field(
        default_factory=list,
        description="Risk warnings from signal risk_flags and evidence status"
    )

    user_decision: UserActionDecision | None = Field(
        None,
        description="User decision on this Action Plan (if any)"
    )

    created_at: datetime = Field(
        ...,
        description="When this Action Plan was created"
    )

    updated_at: datetime = Field(
        ...,
        description="When this Action Plan was last updated"
    )


class ActionPlanDecisionRequest(BaseModel):
    """
    Request to record user decision on Action Plan.

    Used by POST /api/signals/{signal_id}/action-plan/decision endpoint.
    """

    decision: Literal["execute", "skip", "partial", "expired"] = Field(
        ...,
        description="User decision: execute=准备执行, skip=今日放弃, partial=部分执行, expired=标记过期"
    )

    decided_by: str = Field(
        ...,
        description="Username making this decision"
    )

    reason: str | None = Field(
        None,
        description="Why user made this decision (required for skip/partial/expired)"
    )

    manual_notes: str | None = Field(
        None,
        description="Free-form notes from user (optional)"
    )
