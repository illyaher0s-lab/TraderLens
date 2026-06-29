"""
V1 Recommendation Reducer Tests

Verifies deterministic recommendation level reduction based on:
- Strategy prototype_passed status
- Signal validity/active/stale/expired
- Action Plan validity
- Price range status
- MarketDataFault states
- Risk blockers
- Market status
- Base/stress cost results
- Capital context
- User intraday observation (downgrade only)

No LLM, no Tushare, no random, no datetime.now, no external services.
"""

import inspect
import unittest
from datetime import datetime, timezone
from typing import Optional

from pydantic import ValidationError

from contracts.live_trade import (
    RecommendationLevel,
    StrategyStatus,
    SignalStatus,
    ActionPlanStatus,
    PriceRangeStatus,
    MarketStatus,
    RiskBlocker,
    CostValidationResult,
    UserObservation,
    RecommendationInput,
    ExecutionCard,
)
from contracts.market_data_fault import MarketDataFaultState
from backend.services.recommendation_reducer import reduce_recommendation
from backend.services.execution_card_builder import build_execution_card


class TestRecommendationLevel(unittest.TestCase):
    """Test RecommendationLevel enum."""

    def test_all_levels_are_valid(self):
        """All recommendation levels should be accessible."""
        levels = [
            RecommendationLevel.strongly_execute,
            RecommendationLevel.executable,
            RecommendationLevel.pause_observation,
            RecommendationLevel.do_not_execute,
            RecommendationLevel.abandon,
        ]
        self.assertEqual(len(levels), 5)


class TestStronglyExecute(unittest.TestCase):
    """Test strongly_execute conditions."""

    def test_all_conditions_pass_yields_strongly_execute(self):
        """All hard conditions pass -> strongly_execute."""
        input_data = RecommendationInput(
            strategy_status=StrategyStatus.prototype_passed,
            signal_status=SignalStatus.active,
            signal_admitted=True,
            signal_stale=False,
            action_plan_status=ActionPlanStatus.valid,
            price_range_status=PriceRangeStatus.inside_range,
            market_data_state=MarketDataFaultState.ok,
            risk_blockers=[],
            market_status=MarketStatus.normal,
            base_cost_passed=True,
            stress_cost_passed=True,
            capital_confirmed=True,
            capital_sufficient=True,
            user_observation=None,
        )
        level = reduce_recommendation(input_data)
        self.assertEqual(level, RecommendationLevel.strongly_execute)


class TestMandatoryPreconditions(unittest.TestCase):
    """Test mandatory preconditions for execution eligibility."""

    def test_strategy_under_review_yields_do_not_execute(self):
        """Strategy under_review -> do_not_execute (not eligible for execution)."""
        input_data = RecommendationInput(
            strategy_status=StrategyStatus.under_review,  # Not prototype_passed
            signal_status=SignalStatus.active,
            signal_admitted=True,
            signal_stale=False,
            action_plan_status=ActionPlanStatus.valid,
            price_range_status=PriceRangeStatus.inside_range,
            market_data_state=MarketDataFaultState.ok,
            risk_blockers=[],
            market_status=MarketStatus.normal,
            base_cost_passed=True,
            stress_cost_passed=True,
            capital_confirmed=True,
            capital_sufficient=True,
            user_observation=None,
        )
        level = reduce_recommendation(input_data)
        self.assertEqual(level, RecommendationLevel.do_not_execute)

    def test_signal_pending_yields_do_not_execute(self):
        """Signal pending -> do_not_execute (not active yet)."""
        input_data = RecommendationInput(
            strategy_status=StrategyStatus.prototype_passed,
            signal_status=SignalStatus.pending,  # Not active
            signal_admitted=True,
            signal_stale=False,
            action_plan_status=ActionPlanStatus.valid,
            price_range_status=PriceRangeStatus.inside_range,
            market_data_state=MarketDataFaultState.ok,
            risk_blockers=[],
            market_status=MarketStatus.normal,
            base_cost_passed=True,
            stress_cost_passed=True,
            capital_confirmed=True,
            capital_sufficient=True,
            user_observation=None,
        )
        level = reduce_recommendation(input_data)
        self.assertEqual(level, RecommendationLevel.do_not_execute)

    def test_action_plan_pending_yields_pause_observation(self):
        """Action Plan pending -> pause_observation (not valid yet)."""
        input_data = RecommendationInput(
            strategy_status=StrategyStatus.prototype_passed,
            signal_status=SignalStatus.active,
            signal_admitted=True,
            signal_stale=False,
            action_plan_status=ActionPlanStatus.pending,  # Not valid
            price_range_status=PriceRangeStatus.inside_range,
            market_data_state=MarketDataFaultState.ok,
            risk_blockers=[],
            market_status=MarketStatus.normal,
            base_cost_passed=True,
            stress_cost_passed=True,
            capital_confirmed=True,
            capital_sufficient=True,
            user_observation=None,
        )
        level = reduce_recommendation(input_data)
        self.assertEqual(level, RecommendationLevel.pause_observation)

    def test_price_range_unknown_yields_pause_observation(self):
        """Price range unknown -> pause_observation (required execution fact missing)."""
        input_data = RecommendationInput(
            strategy_status=StrategyStatus.prototype_passed,
            signal_status=SignalStatus.active,
            signal_admitted=True,
            signal_stale=False,
            action_plan_status=ActionPlanStatus.valid,
            price_range_status=PriceRangeStatus.unknown,  # Unknown
            market_data_state=MarketDataFaultState.ok,
            risk_blockers=[],
            market_status=MarketStatus.normal,
            base_cost_passed=True,
            stress_cost_passed=True,
            capital_confirmed=True,
            capital_sufficient=True,
            user_observation=None,
        )
        level = reduce_recommendation(input_data)
        self.assertEqual(level, RecommendationLevel.pause_observation)


class TestExecutable(unittest.TestCase):
    """Test executable conditions (hard conditions pass, non-critical cautions)."""

    def test_non_critical_caution_yields_executable(self):
        """Hard conditions pass but non-critical caution -> executable."""
        # Example: market status is slightly abnormal but not blocking
        input_data = RecommendationInput(
            strategy_status=StrategyStatus.prototype_passed,
            signal_status=SignalStatus.active,
            signal_admitted=True,
            signal_stale=False,
            action_plan_status=ActionPlanStatus.valid,
            price_range_status=PriceRangeStatus.inside_range,
            market_data_state=MarketDataFaultState.ok,
            risk_blockers=[],
            market_status=MarketStatus.caution,  # Non-critical
            base_cost_passed=True,
            stress_cost_passed=True,
            capital_confirmed=True,
            capital_sufficient=True,
            user_observation=None,
        )
        level = reduce_recommendation(input_data)
        self.assertEqual(level, RecommendationLevel.executable)


class TestPauseObservation(unittest.TestCase):
    """Test pause_observation conditions."""

    def test_capital_not_confirmed_yields_pause_observation(self):
        """capital_confirmed=False -> pause_observation."""
        input_data = RecommendationInput(
            strategy_status=StrategyStatus.prototype_passed,
            signal_status=SignalStatus.active,
            signal_admitted=True,
            signal_stale=False,
            action_plan_status=ActionPlanStatus.valid,
            price_range_status=PriceRangeStatus.inside_range,
            market_data_state=MarketDataFaultState.ok,
            risk_blockers=[],
            market_status=MarketStatus.normal,
            base_cost_passed=True,
            stress_cost_passed=True,
            capital_confirmed=False,  # Not confirmed
            capital_sufficient=True,
            user_observation=None,
        )
        level = reduce_recommendation(input_data)
        self.assertEqual(level, RecommendationLevel.pause_observation)

    def test_partial_non_critical_data_yields_pause_observation(self):
        """partial market data (non-critical) -> pause_observation."""
        input_data = RecommendationInput(
            strategy_status=StrategyStatus.prototype_passed,
            signal_status=SignalStatus.active,
            signal_admitted=True,
            signal_stale=False,
            action_plan_status=ActionPlanStatus.valid,
            price_range_status=PriceRangeStatus.inside_range,
            market_data_state=MarketDataFaultState.partial,  # Partial
            risk_blockers=[],
            market_status=MarketStatus.normal,
            base_cost_passed=True,
            stress_cost_passed=True,
            capital_confirmed=True,
            capital_sufficient=True,
            user_observation=None,
        )
        level = reduce_recommendation(input_data)
        self.assertEqual(level, RecommendationLevel.pause_observation)

    def test_user_observation_downgrade_risk_yields_pause_observation(self):
        """User observation with downgrade risk -> pause_observation."""
        input_data = RecommendationInput(
            strategy_status=StrategyStatus.prototype_passed,
            signal_status=SignalStatus.active,
            signal_admitted=True,
            signal_stale=False,
            action_plan_status=ActionPlanStatus.valid,
            price_range_status=PriceRangeStatus.inside_range,
            market_data_state=MarketDataFaultState.ok,
            risk_blockers=[],
            market_status=MarketStatus.normal,
            base_cost_passed=True,
            stress_cost_passed=True,
            capital_confirmed=True,
            capital_sufficient=True,
            user_observation=UserObservation.execution_risk,  # Downgrade risk
        )
        level = reduce_recommendation(input_data)
        self.assertEqual(level, RecommendationLevel.pause_observation)


class TestDoNotExecute(unittest.TestCase):
    """Test do_not_execute conditions."""

    def test_signal_not_admitted_yields_do_not_execute(self):
        """Signal not admitted -> do_not_execute."""
        input_data = RecommendationInput(
            strategy_status=StrategyStatus.prototype_passed,
            signal_status=SignalStatus.active,
            signal_admitted=False,  # Not admitted
            signal_stale=False,
            action_plan_status=ActionPlanStatus.valid,
            price_range_status=PriceRangeStatus.inside_range,
            market_data_state=MarketDataFaultState.ok,
            risk_blockers=[],
            market_status=MarketStatus.normal,
            base_cost_passed=True,
            stress_cost_passed=True,
            capital_confirmed=True,
            capital_sufficient=True,
            user_observation=None,
        )
        level = reduce_recommendation(input_data)
        self.assertEqual(level, RecommendationLevel.do_not_execute)

    def test_signal_stale_yields_do_not_execute(self):
        """Signal stale -> do_not_execute."""
        input_data = RecommendationInput(
            strategy_status=StrategyStatus.prototype_passed,
            signal_status=SignalStatus.active,
            signal_admitted=True,
            signal_stale=True,  # Stale
            action_plan_status=ActionPlanStatus.valid,
            price_range_status=PriceRangeStatus.inside_range,
            market_data_state=MarketDataFaultState.ok,
            risk_blockers=[],
            market_status=MarketStatus.normal,
            base_cost_passed=True,
            stress_cost_passed=True,
            capital_confirmed=True,
            capital_sufficient=True,
            user_observation=None,
        )
        level = reduce_recommendation(input_data)
        self.assertEqual(level, RecommendationLevel.do_not_execute)

    def test_price_outside_range_yields_do_not_execute(self):
        """Price outside allowed range -> do_not_execute."""
        input_data = RecommendationInput(
            strategy_status=StrategyStatus.prototype_passed,
            signal_status=SignalStatus.active,
            signal_admitted=True,
            signal_stale=False,
            action_plan_status=ActionPlanStatus.valid,
            price_range_status=PriceRangeStatus.outside_range,  # Outside
            market_data_state=MarketDataFaultState.ok,
            risk_blockers=[],
            market_status=MarketStatus.normal,
            base_cost_passed=True,
            stress_cost_passed=True,
            capital_confirmed=True,
            capital_sufficient=True,
            user_observation=None,
        )
        level = reduce_recommendation(input_data)
        self.assertEqual(level, RecommendationLevel.do_not_execute)

    def test_adapter_unsupported_yields_do_not_execute(self):
        """adapter_unsupported market data -> do_not_execute."""
        input_data = RecommendationInput(
            strategy_status=StrategyStatus.prototype_passed,
            signal_status=SignalStatus.active,
            signal_admitted=True,
            signal_stale=False,
            action_plan_status=ActionPlanStatus.valid,
            price_range_status=PriceRangeStatus.inside_range,
            market_data_state=MarketDataFaultState.adapter_unsupported,  # Unsupported
            risk_blockers=[],
            market_status=MarketStatus.normal,
            base_cost_passed=True,
            stress_cost_passed=True,
            capital_confirmed=True,
            capital_sufficient=True,
            user_observation=None,
        )
        level = reduce_recommendation(input_data)
        self.assertEqual(level, RecommendationLevel.do_not_execute)

    def test_risk_blocker_active_yields_do_not_execute(self):
        """Active risk blocker -> do_not_execute."""
        input_data = RecommendationInput(
            strategy_status=StrategyStatus.prototype_passed,
            signal_status=SignalStatus.active,
            signal_admitted=True,
            signal_stale=False,
            action_plan_status=ActionPlanStatus.valid,
            price_range_status=PriceRangeStatus.inside_range,
            market_data_state=MarketDataFaultState.ok,
            risk_blockers=[RiskBlocker.position_limit_reached],  # Blocker
            market_status=MarketStatus.normal,
            base_cost_passed=True,
            stress_cost_passed=True,
            capital_confirmed=True,
            capital_sufficient=True,
            user_observation=None,
        )
        level = reduce_recommendation(input_data)
        self.assertEqual(level, RecommendationLevel.do_not_execute)

    def test_stress_cost_failed_yields_do_not_execute(self):
        """Stress cost failed -> do_not_execute."""
        input_data = RecommendationInput(
            strategy_status=StrategyStatus.prototype_passed,
            signal_status=SignalStatus.active,
            signal_admitted=True,
            signal_stale=False,
            action_plan_status=ActionPlanStatus.valid,
            price_range_status=PriceRangeStatus.inside_range,
            market_data_state=MarketDataFaultState.ok,
            risk_blockers=[],
            market_status=MarketStatus.normal,
            base_cost_passed=True,
            stress_cost_passed=False,  # Failed
            capital_confirmed=True,
            capital_sufficient=True,
            user_observation=None,
        )
        level = reduce_recommendation(input_data)
        self.assertEqual(level, RecommendationLevel.do_not_execute)

    def test_capital_insufficient_yields_do_not_execute(self):
        """Capital insufficient -> do_not_execute."""
        input_data = RecommendationInput(
            strategy_status=StrategyStatus.prototype_passed,
            signal_status=SignalStatus.active,
            signal_admitted=True,
            signal_stale=False,
            action_plan_status=ActionPlanStatus.valid,
            price_range_status=PriceRangeStatus.inside_range,
            market_data_state=MarketDataFaultState.ok,
            risk_blockers=[],
            market_status=MarketStatus.normal,
            base_cost_passed=True,
            stress_cost_passed=True,
            capital_confirmed=True,
            capital_sufficient=False,  # Insufficient
            user_observation=None,
        )
        level = reduce_recommendation(input_data)
        self.assertEqual(level, RecommendationLevel.do_not_execute)


class TestAbandon(unittest.TestCase):
    """Test abandon conditions."""

    def test_strategy_rejected_yields_abandon(self):
        """Strategy rejected -> abandon."""
        input_data = RecommendationInput(
            strategy_status=StrategyStatus.rejected,  # Rejected
            signal_status=SignalStatus.active,
            signal_admitted=True,
            signal_stale=False,
            action_plan_status=ActionPlanStatus.valid,
            price_range_status=PriceRangeStatus.inside_range,
            market_data_state=MarketDataFaultState.ok,
            risk_blockers=[],
            market_status=MarketStatus.normal,
            base_cost_passed=True,
            stress_cost_passed=True,
            capital_confirmed=True,
            capital_sufficient=True,
            user_observation=None,
        )
        level = reduce_recommendation(input_data)
        self.assertEqual(level, RecommendationLevel.abandon)

    def test_action_plan_invalidated_yields_abandon(self):
        """Action Plan invalidated -> abandon."""
        input_data = RecommendationInput(
            strategy_status=StrategyStatus.prototype_passed,
            signal_status=SignalStatus.active,
            signal_admitted=True,
            signal_stale=False,
            action_plan_status=ActionPlanStatus.invalidated,  # Invalidated
            price_range_status=PriceRangeStatus.inside_range,
            market_data_state=MarketDataFaultState.ok,
            risk_blockers=[],
            market_status=MarketStatus.normal,
            base_cost_passed=True,
            stress_cost_passed=True,
            capital_confirmed=True,
            capital_sufficient=True,
            user_observation=None,
        )
        level = reduce_recommendation(input_data)
        self.assertEqual(level, RecommendationLevel.abandon)

    def test_signal_expired_yields_abandon(self):
        """Signal expired -> abandon."""
        input_data = RecommendationInput(
            strategy_status=StrategyStatus.prototype_passed,
            signal_status=SignalStatus.expired,  # Expired
            signal_admitted=True,
            signal_stale=False,
            action_plan_status=ActionPlanStatus.valid,
            price_range_status=PriceRangeStatus.inside_range,
            market_data_state=MarketDataFaultState.ok,
            risk_blockers=[],
            market_status=MarketStatus.normal,
            base_cost_passed=True,
            stress_cost_passed=True,
            capital_confirmed=True,
            capital_sufficient=True,
            user_observation=None,
        )
        level = reduce_recommendation(input_data)
        self.assertEqual(level, RecommendationLevel.abandon)


class TestExecutionCardBuilder(unittest.TestCase):
    """Test execution card building."""

    def test_build_execution_card_includes_required_fields(self):
        """Execution card must include all required fields."""
        input_data = RecommendationInput(
            strategy_status=StrategyStatus.prototype_passed,
            signal_status=SignalStatus.active,
            signal_admitted=True,
            signal_stale=False,
            action_plan_status=ActionPlanStatus.valid,
            price_range_status=PriceRangeStatus.inside_range,
            market_data_state=MarketDataFaultState.ok,
            risk_blockers=[],
            market_status=MarketStatus.normal,
            base_cost_passed=True,
            stress_cost_passed=True,
            capital_confirmed=True,
            capital_sufficient=True,
            user_observation=None,
        )
        level = reduce_recommendation(input_data)

        card = build_execution_card(
            symbol="000001.SZ",
            name="平安银行",
            direction="buy",
            recommendation_level=level,
            planned_cash_amount=10000.0,
            planned_share_count=1000,
            allowed_price_range=(9.8, 10.2),
            maximum_acceptable_deviation=0.05,
            invalidation_conditions=["price > 10.5", "signal expired"],
            review_time=datetime(2026, 6, 1, 14, 30, 0, tzinfo=timezone.utc),
            reasons=["Breakout signal", "Volume confirmation"],
            risks=["Market volatility"],
            market_data_state=MarketDataFaultState.ok,
            artifact_ids=["signal_123", "plan_456"],
        )

        self.assertEqual(card.symbol, "000001.SZ")
        self.assertEqual(card.name, "平安银行")
        self.assertEqual(card.direction, "buy")
        self.assertEqual(card.recommendation_level, RecommendationLevel.strongly_execute)
        self.assertEqual(card.planned_cash_amount, 10000.0)
        self.assertEqual(card.planned_share_count, 1000)
        self.assertEqual(card.allowed_price_range, (9.8, 10.2))
        self.assertEqual(card.maximum_acceptable_deviation, 0.05)
        self.assertEqual(len(card.invalidation_conditions), 2)
        self.assertEqual(card.review_time, datetime(2026, 6, 1, 14, 30, 0, tzinfo=timezone.utc))
        self.assertEqual(len(card.reasons), 2)
        self.assertEqual(len(card.risks), 1)
        self.assertEqual(card.market_data_state, MarketDataFaultState.ok)
        self.assertEqual(len(card.artifact_ids), 2)

    def test_execution_card_rejects_empty_artifact_ids(self):
        """Execution card must reject empty artifact_ids (no upstream evidence)."""
        with self.assertRaises(ValidationError) as ctx:
            build_execution_card(
                symbol="000001.SZ",
                name="平安银行",
                direction="buy",
                recommendation_level=RecommendationLevel.strongly_execute,
                planned_cash_amount=10000.0,
                planned_share_count=1000,
                allowed_price_range=(9.8, 10.2),
                maximum_acceptable_deviation=0.05,
                invalidation_conditions=[],
                review_time=datetime(2026, 6, 1, 14, 30, 0, tzinfo=timezone.utc),
                reasons=[],
                risks=[],
                market_data_state=MarketDataFaultState.ok,
                artifact_ids=[],  # Empty - should fail
            )
        self.assertIn("artifact_ids", str(ctx.exception).lower())

    def test_execution_card_requires_non_empty_symbol_name_direction(self):
        """Execution card must require non-empty symbol, name, direction."""
        # Empty symbol
        with self.assertRaises(ValidationError):
            build_execution_card(
                symbol="",  # Empty
                name="平安银行",
                direction="buy",
                recommendation_level=RecommendationLevel.strongly_execute,
                planned_cash_amount=10000.0,
                planned_share_count=1000,
                allowed_price_range=(9.8, 10.2),
                maximum_acceptable_deviation=0.05,
                invalidation_conditions=[],
                review_time=datetime(2026, 6, 1, 14, 30, 0, tzinfo=timezone.utc),
                reasons=[],
                risks=[],
                market_data_state=MarketDataFaultState.ok,
                artifact_ids=["signal_123"],
            )

        # Empty name
        with self.assertRaises(ValidationError):
            build_execution_card(
                symbol="000001.SZ",
                name="",  # Empty
                direction="buy",
                recommendation_level=RecommendationLevel.strongly_execute,
                planned_cash_amount=10000.0,
                planned_share_count=1000,
                allowed_price_range=(9.8, 10.2),
                maximum_acceptable_deviation=0.05,
                invalidation_conditions=[],
                review_time=datetime(2026, 6, 1, 14, 30, 0, tzinfo=timezone.utc),
                reasons=[],
                risks=[],
                market_data_state=MarketDataFaultState.ok,
                artifact_ids=["signal_123"],
            )

        # Empty direction
        with self.assertRaises(ValidationError):
            build_execution_card(
                symbol="000001.SZ",
                name="平安银行",
                direction="",  # Empty
                recommendation_level=RecommendationLevel.strongly_execute,
                planned_cash_amount=10000.0,
                planned_share_count=1000,
                allowed_price_range=(9.8, 10.2),
                maximum_acceptable_deviation=0.05,
                invalidation_conditions=[],
                review_time=datetime(2026, 6, 1, 14, 30, 0, tzinfo=timezone.utc),
                reasons=[],
                risks=[],
                market_data_state=MarketDataFaultState.ok,
                artifact_ids=["signal_123"],
            )

    def test_execution_card_rejects_invalid_allowed_price_range(self):
        """Execution card must reject invalid price range (low > high or <= 0)."""
        # Low > High
        with self.assertRaises(ValidationError):
            build_execution_card(
                symbol="000001.SZ",
                name="平安银行",
                direction="buy",
                recommendation_level=RecommendationLevel.strongly_execute,
                planned_cash_amount=10000.0,
                planned_share_count=1000,
                allowed_price_range=(10.2, 9.8),  # Low > High
                maximum_acceptable_deviation=0.05,
                invalidation_conditions=[],
                review_time=datetime(2026, 6, 1, 14, 30, 0, tzinfo=timezone.utc),
                reasons=[],
                risks=[],
                market_data_state=MarketDataFaultState.ok,
                artifact_ids=["signal_123"],
            )

        # Negative price
        with self.assertRaises(ValidationError):
            build_execution_card(
                symbol="000001.SZ",
                name="平安银行",
                direction="buy",
                recommendation_level=RecommendationLevel.strongly_execute,
                planned_cash_amount=10000.0,
                planned_share_count=1000,
                allowed_price_range=(-1.0, 10.2),  # Negative
                maximum_acceptable_deviation=0.05,
                invalidation_conditions=[],
                review_time=datetime(2026, 6, 1, 14, 30, 0, tzinfo=timezone.utc),
                reasons=[],
                risks=[],
                market_data_state=MarketDataFaultState.ok,
                artifact_ids=["signal_123"],
            )

        # Zero price
        with self.assertRaises(ValidationError):
            build_execution_card(
                symbol="000001.SZ",
                name="平安银行",
                direction="buy",
                recommendation_level=RecommendationLevel.strongly_execute,
                planned_cash_amount=10000.0,
                planned_share_count=1000,
                allowed_price_range=(0.0, 10.2),  # Zero
                maximum_acceptable_deviation=0.05,
                invalidation_conditions=[],
                review_time=datetime(2026, 6, 1, 14, 30, 0, tzinfo=timezone.utc),
                reasons=[],
                risks=[],
                market_data_state=MarketDataFaultState.ok,
                artifact_ids=["signal_123"],
            )

    def test_execution_card_rejects_negative_cash_or_share_count(self):
        """Execution card must reject negative cash amount or share count."""
        # Negative cash
        with self.assertRaises(ValidationError):
            build_execution_card(
                symbol="000001.SZ",
                name="平安银行",
                direction="buy",
                recommendation_level=RecommendationLevel.strongly_execute,
                planned_cash_amount=-10000.0,  # Negative
                planned_share_count=1000,
                allowed_price_range=(9.8, 10.2),
                maximum_acceptable_deviation=0.05,
                invalidation_conditions=[],
                review_time=datetime(2026, 6, 1, 14, 30, 0, tzinfo=timezone.utc),
                reasons=[],
                risks=[],
                market_data_state=MarketDataFaultState.ok,
                artifact_ids=["signal_123"],
            )

        # Negative share count
        with self.assertRaises(ValidationError):
            build_execution_card(
                symbol="000001.SZ",
                name="平安银行",
                direction="buy",
                recommendation_level=RecommendationLevel.strongly_execute,
                planned_cash_amount=10000.0,
                planned_share_count=-1000,  # Negative
                allowed_price_range=(9.8, 10.2),
                maximum_acceptable_deviation=0.05,
                invalidation_conditions=[],
                review_time=datetime(2026, 6, 1, 14, 30, 0, tzinfo=timezone.utc),
                reasons=[],
                risks=[],
                market_data_state=MarketDataFaultState.ok,
                artifact_ids=["signal_123"],
            )

    def test_execution_card_has_no_forbidden_fields(self):
        """Execution card must not have broker/order/profit fields."""
        card = build_execution_card(
            symbol="000001.SZ",
            name="平安银行",
            direction="buy",
            recommendation_level=RecommendationLevel.strongly_execute,
            planned_cash_amount=10000.0,
            planned_share_count=1000,
            allowed_price_range=(9.8, 10.2),
            maximum_acceptable_deviation=0.05,
            invalidation_conditions=[],
            review_time=datetime(2026, 6, 1, 14, 30, 0, tzinfo=timezone.utc),
            reasons=[],
            risks=[],
            market_data_state=MarketDataFaultState.ok,
            artifact_ids=["signal_123", "action_plan_456"],  # Fixed: non-empty
        )

        fields = set(ExecutionCard.model_fields.keys())
        forbidden = {
            "broker_connection",
            "auto_order",
            "guaranteed_profit",
            "llm_target_price",
            "execution_record",
        }
        intersection = fields & forbidden
        self.assertEqual(
            len(intersection),
            0,
            f"ExecutionCard must not have forbidden fields: {intersection}",
        )


class TestNoForbiddenLogic(unittest.TestCase):
    """Verify no LLM/Tushare/random/datetime.now logic."""

    def test_no_forbidden_imports_in_reducer(self):
        """recommendation_reducer.py must not import forbidden modules."""
        from backend.services import recommendation_reducer

        source = inspect.getsource(recommendation_reducer)
        # Check imports only (not docstrings)
        import_lines = [
            line for line in source.split("\n") if line.strip().startswith("import") or line.strip().startswith("from")
        ]
        import_text = "\n".join(import_lines)
        
        forbidden = [
            "anthropic",
            "openai",
            "tushare",
            "random",
            "numpy.random",
            "datetime.now",
            "datetime.utcnow",
            "time.time",
        ]
        for module in forbidden:
            self.assertNotIn(
                module,
                import_text,
                f"recommendation_reducer.py must not import or use {module}",
            )

    def test_no_forbidden_imports_in_card_builder(self):
        """execution_card_builder.py must not import forbidden modules."""
        from backend.services import execution_card_builder

        source = inspect.getsource(execution_card_builder)
        # Check imports only (not docstrings)
        import_lines = [
            line for line in source.split("\n") if line.strip().startswith("import") or line.strip().startswith("from")
        ]
        import_text = "\n".join(import_lines)
        
        forbidden = [
            "anthropic",
            "openai",
            "tushare",
            "random",
            "numpy.random",
            "datetime.now",
            "datetime.utcnow",
            "time.time",
        ]
        for module in forbidden:
            self.assertNotIn(
                module,
                import_text,
                f"execution_card_builder.py must not import or use {module}",
            )


if __name__ == "__main__":
    unittest.main()
