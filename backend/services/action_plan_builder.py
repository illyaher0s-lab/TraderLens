"""
Action Plan Builder Service

C3 deterministic Action Plan builder.

Builds Action Plan from admitted PlannedSignal using only:
- Signal metadata
- Date arithmetic
- Rule-based checks

Does NOT use:
- LLM
- External data sources
- Live market data
- Broker APIs
- Order/fill/execution records

Core Rules:
1. Freshness: fresh (today <= intended_date), stale (1 day past), expired (2+ days past)
2. Blocking: non-prototype_passed, evidence blocked, ignored/expired review status, expired freshness
3. Warning: evidence warning, risk_flags present, stale freshness, missing quantity/price
4. Pre-action checks: admission, freshness, evidence, risk, snapshot linkage, strategy revision linkage
5. Invalidation checks: expired signal, blocked evidence, ignored review, expired review

Determinism:
- action_plan_id is deterministic hash from signal metadata
- Timestamps are injectable for testing
- Same input (signal, today, now) produces identical output
"""

import hashlib
from datetime import date, datetime, timezone

from contracts.signal_board import PlannedSignal
from contracts.action_plan import (
    ActionPlan,
    ActionCheck,
    ExecutionWindow,
    UserActionDecision,
)


def _generate_deterministic_action_plan_id(signal: PlannedSignal) -> str:
    """
    Generate deterministic Action Plan ID from signal metadata.

    Uses SHA256 hash over signal identifying fields to ensure:
    - Same signal always produces same action_plan_id
    - Different signals produce different action_plan_ids
    - No random UUIDs

    Args:
        signal: PlannedSignal to generate ID from

    Returns:
        Deterministic action_plan_id string (format: "ap_<hash_prefix>")
    """
    components = [
        signal.signal_id,
        signal.strategy_id,
        signal.strategy_version,
        signal.strategy_revision_id or "",
        signal.snapshot_hash,
        signal.intended_execution_date.isoformat(),
    ]
    hash_input = "|".join(components)
    hash_digest = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()
    # Use first 16 chars of hash for readability
    return f"ap_{hash_digest[:16]}"


def _determine_freshness(
    today: date,
    intended_execution_date: date,
) -> tuple[str, date, date]:
    """
    Determine freshness status and execution window.

    Args:
        today: Current date
        intended_execution_date: Intended execution date from signal

    Returns:
        Tuple of (freshness_status, valid_for_date, expires_after_date)

    Freshness Rules (C3 MVP - simplified without trading calendar):
        - fresh: today <= intended_execution_date
        - stale: today == intended_execution_date + 1 day
        - expired: today > intended_execution_date + 1 day
    """
    if today <= intended_execution_date:
        freshness_status = "fresh"
    elif today.toordinal() == intended_execution_date.toordinal() + 1:
        freshness_status = "stale"
    else:
        freshness_status = "expired"

    # C3 MVP: valid_for_date = intended_execution_date
    # expires_after_date = intended_execution_date + 1 day
    from datetime import timedelta
    valid_for_date = intended_execution_date
    expires_after_date = intended_execution_date + timedelta(days=1)

    return freshness_status, valid_for_date, expires_after_date


def _build_pre_action_checks(signal: PlannedSignal, freshness_status: str) -> list[ActionCheck]:
    """
    Build pre-action checks from signal metadata.

    Required checks:
    1. Signal admission check
    2. Date freshness check
    3. Evidence status check
    4. Risk flags check
    5. Snapshot linkage check
    6. Strategy revision linkage check
    """
    checks = []

    # 1. Admission check
    admission_pass = signal.lifecycle_state_at_generation == "prototype_passed"
    checks.append(ActionCheck(
        check_id="admission_check",
        label="信号准入检查",
        source="signal_metadata",
        status="pass" if admission_pass else "blocked",
        blocking=True,
        detail=f"信号状态: {signal.lifecycle_state_at_generation or '未知'}" +
               (f" (来源: {signal.admission_source})" if signal.admission_source else "")
    ))

    # 2. Freshness check
    freshness_map = {
        "fresh": ("pass", "新鲜 (今日可执行)"),
        "stale": ("warning", "不新鲜 (已过计划日期 1 日)"),
        "expired": ("blocked", "已过期 (超过计划日期)")
    }
    freshness_check_status, freshness_detail = freshness_map[freshness_status]
    checks.append(ActionCheck(
        check_id="freshness_check",
        label="日期新鲜度检查",
        source="system_rule",
        status=freshness_check_status,
        blocking=(freshness_status == "expired"),
        detail=f"计划日期: {signal.intended_execution_date}, {freshness_detail}"
    ))

    # 3. Evidence status check
    evidence_map = {
        "clean": ("pass", "无风险"),
        "warning": ("warning", "存在风险警告"),
        "blocked": ("blocked", "被证据阻断 (停牌/涨跌停/流动性)")
    }
    evidence_status, evidence_detail = evidence_map[signal.evidence_status]
    checks.append(ActionCheck(
        check_id="evidence_check",
        label="证据状态检查",
        source="risk_flag",
        status=evidence_status,
        blocking=(signal.evidence_status == "blocked"),
        detail=f"证据状态: {signal.evidence_status}, {evidence_detail}"
    ))

    # 4. Risk flags check
    risk_flags_present = len(signal.risk_flags) > 0
    checks.append(ActionCheck(
        check_id="risk_flags_check",
        label="风险标记检查",
        source="risk_flag",
        status="warning" if risk_flags_present else "pass",
        blocking=False,
        detail=f"风险标记: {', '.join(signal.risk_flags) if signal.risk_flags else '无'}"
    ))

    # 5. Snapshot linkage check
    snapshot_exists = bool(signal.snapshot_hash)
    checks.append(ActionCheck(
        check_id="snapshot_linkage_check",
        label="快照关联检查",
        source="signal_metadata",
        status="pass" if snapshot_exists else "warning",
        blocking=False,
        detail=f"快照哈希: {signal.snapshot_hash[:16] + '...' if snapshot_exists else '缺失'}"
    ))

    # 6. Strategy revision linkage check
    revision_exists = bool(signal.strategy_revision_id)
    checks.append(ActionCheck(
        check_id="strategy_revision_check",
        label="策略版本关联检查",
        source="signal_metadata",
        status="pass" if revision_exists else "warning",
        blocking=False,
        detail=f"策略版本 ID: {signal.strategy_revision_id[:16] + '...' if revision_exists else '缺失 (C0 前信号)'}"
    ))

    return checks


def _build_invalidation_checks(
    signal: PlannedSignal,
    freshness_status: str
) -> list[ActionCheck]:
    """
    Build invalidation checks (conditions that block execution).

    Required checks:
    1. Expired signal
    2. Blocked by evidence
    3. Already ignored
    4. Already expired
    """
    checks = []

    # 1. Expired signal
    is_expired = freshness_status == "expired"
    checks.append(ActionCheck(
        check_id="expired_signal",
        label="信号过期检查",
        source="system_rule",
        status="blocked" if is_expired else "pass",
        blocking=True,
        detail=f"新鲜度: {freshness_status}, {'已过期，无法执行' if is_expired else '未过期'}"
    ))

    # 2. Blocked by evidence
    is_blocked = signal.evidence_status == "blocked"
    checks.append(ActionCheck(
        check_id="blocked_by_evidence",
        label="证据阻断检查",
        source="risk_flag",
        status="blocked" if is_blocked else "pass",
        blocking=True,
        detail=f"证据状态: {signal.evidence_status}, {'被阻断 (停牌/涨跌停/流动性)' if is_blocked else '未阻断'}"
    ))

    # 3. Already ignored
    is_ignored = signal.review_status == "ignored"
    checks.append(ActionCheck(
        check_id="already_ignored",
        label="人工忽略检查",
        source="signal_metadata",
        status="blocked" if is_ignored else "pass",
        blocking=True,
        detail=f"审核状态: {signal.review_status}, {'已被人工忽略' if is_ignored else '未忽略'}" +
               (f" (原因: {signal.rejection_reason})" if is_ignored and signal.rejection_reason else "")
    ))

    # 4. Already expired by review
    is_review_expired = signal.review_status == "expired"
    checks.append(ActionCheck(
        check_id="already_expired",
        label="人工过期标记检查",
        source="signal_metadata",
        status="blocked" if is_review_expired else "pass",
        blocking=True,
        detail=f"审核状态: {signal.review_status}, {'已被人工标记为过期' if is_review_expired else '未标记过期'}"
    ))

    return checks


def _build_risk_warnings(signal: PlannedSignal) -> list[str]:
    """
    Build risk warnings from signal metadata.

    Warnings for:
    - Evidence status = warning
    - Risk flags present
    - Missing quantity
    - Missing current price
    """
    warnings = []

    if signal.evidence_status == "warning":
        warnings.append(f"证据警告: {', '.join(signal.risk_flags) if signal.risk_flags else '存在风险'}")

    if signal.risk_flags:
        warnings.append(f"风险标记: {', '.join(signal.risk_flags)}")

    if signal.quantity is None:
        warnings.append("未设置数量 (需人工确定仓位)")

    if signal.current_price is None:
        warnings.append("缺失价格信息")

    return warnings


def _determine_action_plan_status(
    signal: PlannedSignal,
    freshness_status: str,
    invalidation_checks: list[ActionCheck]
) -> str:
    """
    Determine Action Plan status based on signal state and checks.

    Status logic:
    - "expired": Only if freshness is expired OR review_status is "expired"
    - "ready_for_human": Can be reviewed (may have blocking checks, but not date-expired)

    Blocking conditions (evidence blocked, ignored review) are represented by
    ActionCheck.blocking=True, not by ActionPlan.status="expired".

    Returns one of:
    - "ready_for_human": Can be reviewed by human (even if some checks block execution)
    - "expired": Date-expired or marked expired by review
    """
    # Only mark as expired if actually date-expired or review status expired
    if freshness_status == "expired" or signal.review_status == "expired":
        return "expired"

    # All other cases (including evidence blocked, ignored) are ready_for_human
    # Blocking is represented by individual check.blocking=True
    return "ready_for_human"


def build_action_plan(
    signal: PlannedSignal,
    today: date | None = None,
    now: datetime | None = None
) -> ActionPlan:
    """
    Build deterministic Action Plan from admitted PlannedSignal.

    Args:
        signal: Admitted PlannedSignal (must have lifecycle_state_at_generation == "prototype_passed")
        today: Current date (defaults to UTC today if None)
        now: Current timestamp (defaults to UTC now if None)

    Returns:
        ActionPlan with deterministic checks and status

    Raises:
        ValueError: If signal is not admitted (lifecycle_state_at_generation != "prototype_passed")

    Determinism:
        When today and now are provided, output is fully deterministic:
        - action_plan_id is SHA256 hash of signal metadata
        - created_at and updated_at are set to provided now
        - Same (signal, today, now) produces identical ActionPlan
    """
    # Validate admission
    if signal.lifecycle_state_at_generation != "prototype_passed":
        raise ValueError(
            f"Cannot build Action Plan for unadmitted signal. "
            f"lifecycle_state_at_generation={signal.lifecycle_state_at_generation}, "
            f"expected 'prototype_passed'"
        )

    # Default to today and now
    if today is None:
        today = datetime.now(timezone.utc).date()
    if now is None:
        now = datetime.now(timezone.utc)

    # Determine freshness
    freshness_status, valid_for_date, expires_after_date = _determine_freshness(
        today, signal.intended_execution_date
    )

    # Build execution window
    execution_window = ExecutionWindow(
        planned_date=signal.intended_execution_date,
        valid_for_date=valid_for_date,
        expires_after_date=expires_after_date
    )

    # Build checks
    pre_action_checks = _build_pre_action_checks(signal, freshness_status)
    invalidation_checks = _build_invalidation_checks(signal, freshness_status)
    risk_warnings = _build_risk_warnings(signal)

    # Determine status
    action_plan_status = _determine_action_plan_status(
        signal, freshness_status, invalidation_checks
    )

    # Generate deterministic Action Plan ID
    action_plan_id = _generate_deterministic_action_plan_id(signal)

    # Build Action Plan
    return ActionPlan(
        action_plan_id=action_plan_id,
        signal_id=signal.signal_id,
        strategy_id=signal.strategy_id,
        strategy_version=signal.strategy_version,
        strategy_revision_id=signal.strategy_revision_id,
        snapshot_hash=signal.snapshot_hash,
        symbol=signal.symbol,
        planned_action=signal.planned_action,
        signal_date=signal.signal_date,
        intended_execution_date=signal.intended_execution_date,
        action_plan_date=today,
        status=action_plan_status,
        freshness_status=freshness_status,
        execution_window=execution_window,
        pre_action_checks=pre_action_checks,
        invalidation_checks=invalidation_checks,
        risk_warnings=risk_warnings,
        user_decision=None,
        created_at=now,
        updated_at=now
    )
