"""
V1 Execution Card Builder

Assembles execution card from deterministic inputs.
No LLM, no Tushare, no random, no external data fetching, no trading logic.
"""

from datetime import datetime

from contracts.live_trade import ExecutionCard, RecommendationLevel
from contracts.market_data_fault import MarketDataFaultState


def build_execution_card(
    symbol: str,
    name: str,
    direction: str,
    recommendation_level: RecommendationLevel,
    planned_cash_amount: float,
    planned_share_count: int,
    allowed_price_range: tuple[float, float],
    maximum_acceptable_deviation: float,
    invalidation_conditions: list[str],
    review_time: datetime,
    reasons: list[str],
    risks: list[str],
    market_data_state: MarketDataFaultState,
    artifact_ids: list[str],
) -> ExecutionCard:
    """
    Build execution card for human review.

    All inputs must be deterministic and pre-computed.
    No ad-hoc generation of thresholds, prices, or parameters.

    Args:
        symbol: Stock symbol
        name: Stock name
        direction: Trade direction (buy/sell)
        recommendation_level: Reducer output
        planned_cash_amount: Pre-computed cash amount
        planned_share_count: Pre-computed share count
        allowed_price_range: Pre-computed price range from Action Plan
        maximum_acceptable_deviation: Pre-computed from Action Plan/template
        invalidation_conditions: Pre-computed from Action Plan
        review_time: Pre-computed review deadline
        reasons: Pre-computed reasons list
        risks: Pre-computed risks list
        market_data_state: Current market data state
        artifact_ids: Related artifact IDs (signal, plan, etc.)

    Returns:
        ExecutionCard ready for human review
    """
    return ExecutionCard(
        symbol=symbol,
        name=name,
        direction=direction,
        recommendation_level=recommendation_level,
        planned_cash_amount=planned_cash_amount,
        planned_share_count=planned_share_count,
        allowed_price_range=allowed_price_range,
        maximum_acceptable_deviation=maximum_acceptable_deviation,
        invalidation_conditions=invalidation_conditions,
        review_time=review_time,
        reasons=reasons,
        risks=risks,
        market_data_state=market_data_state,
        artifact_ids=artifact_ids,
    )
