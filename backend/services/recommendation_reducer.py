"""
V1 Deterministic Recommendation Reducer

Pure deterministic reducer for live trade recommendations.
No LLM, no Tushare, no random, no datetime.now, no external services.

Reduction Order:
1. Check abandon conditions (strategy rejected/blocked, plan invalidated, signal expired)
2. Check do_not_execute conditions (mandatory preconditions + hard blockers)
   - Strategy must be prototype_passed
   - Signal must be active and admitted
   - Price, data, risk, cost, capital blockers
3. Check pause_observation conditions (Action Plan not valid, unknown price, soft blockers)
4. Check executable conditions (non-critical cautions)
5. Return strongly_execute if all hard conditions pass
"""

from contracts.live_trade import (
    RecommendationLevel,
    RecommendationInput,
    StrategyStatus,
    SignalStatus,
    ActionPlanStatus,
    PriceRangeStatus,
    MarketStatus,
    UserObservation,
)
from contracts.market_data_fault import MarketDataFaultState


def reduce_recommendation(input_data: RecommendationInput) -> RecommendationLevel:
    """
    Reduce recommendation level based on deterministic rules.

    Args:
        input_data: All required decision inputs

    Returns:
        RecommendationLevel (strongly_execute, executable, pause_observation, do_not_execute, abandon)
    """
    # 1. Check abandon conditions (highest priority)
    if _should_abandon(input_data):
        return RecommendationLevel.abandon

    # 2. Check do_not_execute conditions (mandatory preconditions + hard blockers)
    if _should_not_execute(input_data):
        return RecommendationLevel.do_not_execute

    # 3. Check pause_observation conditions (soft blockers, pending states)
    if _should_pause_observation(input_data):
        return RecommendationLevel.pause_observation

    # 4. Check executable conditions (non-critical cautions)
    if _has_non_critical_caution(input_data):
        return RecommendationLevel.executable

    # 5. All hard conditions pass
    return RecommendationLevel.strongly_execute


def _should_abandon(input_data: RecommendationInput) -> bool:
    """
    Check abandon conditions.

    Abandon when:
    - Strategy rejected or blocked
    - Action Plan invalidated
    - Signal expired
    """
    if input_data.strategy_status in [StrategyStatus.rejected, StrategyStatus.blocked]:
        return True

    if input_data.action_plan_status == ActionPlanStatus.invalidated:
        return True

    if input_data.signal_status == SignalStatus.expired:
        return True

    return False


def _should_not_execute(input_data: RecommendationInput) -> bool:
    """
    Check do_not_execute conditions.

    Do not execute when:
    - Strategy not prototype_passed (mandatory precondition)
    - Signal not active (mandatory precondition)
    - Signal not admitted
    - Signal stale
    - Price outside allowed range
    - Key market data unavailable/stale/inconsistent/unsupported
    - Risk blocker active
    - Stress cost failed
    - Capital insufficient
    - Market halted
    """
    # Mandatory precondition: Strategy must be prototype_passed
    if input_data.strategy_status != StrategyStatus.prototype_passed:
        return True

    # Mandatory precondition: Signal must be active
    if input_data.signal_status != SignalStatus.active:
        return True

    # Signal issues
    if not input_data.signal_admitted:
        return True

    if input_data.signal_stale:
        return True

    # Price issues
    if input_data.price_range_status == PriceRangeStatus.outside_range:
        return True

    # Market data issues (critical states)
    if input_data.market_data_state in [
        MarketDataFaultState.unavailable,
        MarketDataFaultState.stale,
        MarketDataFaultState.inconsistent,
        MarketDataFaultState.source_error,
        MarketDataFaultState.adapter_unsupported,
    ]:
        return True

    # Risk blockers
    if input_data.risk_blockers:
        return True

    # Cost validation failures
    if not input_data.stress_cost_passed:
        return True

    # Capital insufficient
    if not input_data.capital_sufficient:
        return True

    # Market halted
    if input_data.market_status == MarketStatus.halted:
        return True

    return False


def _should_pause_observation(input_data: RecommendationInput) -> bool:
    """
    Check pause_observation conditions.

    Pause when:
    - Action Plan not valid (pending)
    - Price range unknown (required execution fact missing)
    - Price near boundary (unclear if satisfies range)
    - Partial market data (non-critical)
    - Capital not confirmed by user
    - User observation downgrade risk
    - Market abnormal (non-critical)
    - Base cost not passed (warning)
    """
    # Action Plan not valid (pending means not ready)
    if input_data.action_plan_status != ActionPlanStatus.valid:
        return True

    # Price range unknown (required execution fact missing)
    if input_data.price_range_status == PriceRangeStatus.unknown:
        return True

    # Price near boundary (unclear if satisfies range)
    if input_data.price_range_status == PriceRangeStatus.near_boundary:
        return True

    # Partial data (non-critical)
    if input_data.market_data_state == MarketDataFaultState.partial:
        return True

    # Capital not confirmed
    if not input_data.capital_confirmed:
        return True

    # User observation downgrade risk
    if input_data.user_observation is not None:
        return True

    # Market abnormal (non-critical)
    if input_data.market_status == MarketStatus.abnormal:
        return True

    # Base cost not passed (warning, not blocker)
    if not input_data.base_cost_passed:
        return True

    return False


def _has_non_critical_caution(input_data: RecommendationInput) -> bool:
    """
    Check for non-critical cautions that prevent strongly_execute.

    Caution when:
    - Market status is caution
    """
    if input_data.market_status == MarketStatus.caution:
        return True

    return False
