"""
V1 Capital Context Service

Builds capital context with deterministic V1 conservative position sizing rules.
No user selection of technical parameters. Fixed defaults only.

V1 Conservative Rules:
- max_total_live_capital = min(cash_available, total_capital * 0.30)
- max_single_position_capital = min(max_total_live_capital * 0.25, total_capital * 0.10)
- max_position_count = 4 (fixed)
- risk_cap_per_trade = min(max_single_position_capital * 0.08, total_capital * 0.01)

No LLM, no Tushare, no market data, no recommendations, no execution logic.
No current time generation - all timestamps passed explicitly.
"""

from datetime import datetime

from contracts.capital_context import (
    CapitalProfile,
    PositionSizingPlan,
    CapitalContext,
)


def build_position_sizing_plan(
    profile: CapitalProfile, created_at: datetime
) -> PositionSizingPlan:
    """
    Build position sizing plan using V1 conservative defaults.

    Args:
        profile: Capital profile
        created_at: Explicit timestamp for plan creation

    Returns:
        PositionSizingPlan with deterministic V1 rules
    """
    # V1 Conservative Rule 1: max 30% of total capital or available cash
    max_total_live_capital = min(
        profile.cash_available,
        profile.total_capital * 0.30,
    )

    # V1 Conservative Rule 2: max 25% of live capital or 10% of total capital
    max_single_position_capital = min(
        max_total_live_capital * 0.25,
        profile.total_capital * 0.10,
    )

    # V1 Conservative Rule 3: exactly 4 positions
    max_position_count = 4

    # V1 Conservative Rule 4: max 8% of single position or 1% of total capital
    risk_cap_per_trade = min(
        max_single_position_capital * 0.08,
        profile.total_capital * 0.01,
    )

    return PositionSizingPlan(
        plan_id=f"{profile.profile_id}_v1_conservative",
        profile_id=profile.profile_id,
        max_single_position_capital=max_single_position_capital,
        max_total_live_capital=max_total_live_capital,
        max_position_count=max_position_count,
        risk_cap_per_trade=risk_cap_per_trade,
        created_at=created_at,
        basis="V1_conservative_defaults",
    )


def validate_live_capability(context: CapitalContext) -> tuple[bool, str | None]:
    """
    Validate if context is capable of live trading.

    Args:
        context: Capital context to validate

    Returns:
        Tuple of (is_live_capable, blocking_reason)
    """
    if not context.profile.confirmed_by_user:
        return False, "Profile not confirmed by user"

    return True, None


def build_capital_context(
    profile: CapitalProfile, created_at: datetime
) -> CapitalContext:
    """
    Build complete capital context with live-trading capability assessment.

    Args:
        profile: Capital profile
        created_at: Explicit timestamp for context creation

    Returns:
        CapitalContext with position sizing plan and capability assessment
    """
    position_sizing_plan = build_position_sizing_plan(profile, created_at)

    # Assess live-trading capability
    if not profile.confirmed_by_user:
        is_live_capable = False
        blocking_reason = "Profile not confirmed by user"
    else:
        is_live_capable = True
        blocking_reason = None

    return CapitalContext(
        profile=profile,
        position_sizing_plan=position_sizing_plan,
        is_live_capable=is_live_capable,
        blocking_reason=blocking_reason,
    )
