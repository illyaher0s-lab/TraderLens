"""
V1 Capital Context Tests

Verifies:
- Valid profile builds live-capable context
- Unconfirmed profile is not live-capable
- Invalid profiles are rejected (cash > total, total <= 0, risk > total)
- Position sizing uses deterministic V1 conservative rules
- max_total_live_capital capped at 30% total and cash_available
- max_single_position_capital capped at 25% live and 10% total
- max_position_count is exactly 4
- risk_cap_per_trade capped at 8% single position and 1% total
- No symbol/recommendation/order/P&L fields
- No LLM/Tushare/market data/recommendation/execution/broker/random/time logic
"""

import inspect
import unittest
from datetime import datetime, timezone

from pydantic import ValidationError

from contracts.capital_context import CapitalProfile, PositionSizingPlan, CapitalContext
from backend.services.capital_context import (
    build_capital_context,
    build_position_sizing_plan,
    validate_live_capability,
)


class TestCapitalProfile(unittest.TestCase):
    """Test CapitalProfile validation."""

    def test_total_capital_must_be_positive(self):
        """total_capital must be > 0."""
        with self.assertRaises(ValidationError):
            CapitalProfile(
                profile_id="test",
                total_capital=0.0,
                cash_available=0.0,
                max_risk_budget=1000.0,
                capital_unit="CNY",
                created_at=datetime.now(timezone.utc),
                source="manual",
                confirmed_by_user=False,
            )

    def test_cash_available_cannot_exceed_total_capital(self):
        """cash_available must be <= total_capital."""
        with self.assertRaises(ValidationError):
            CapitalProfile(
                profile_id="test",
                total_capital=100000.0,
                cash_available=150000.0,  # More than total
                max_risk_budget=10000.0,
                capital_unit="CNY",
                created_at=datetime.now(timezone.utc),
                source="manual",
                confirmed_by_user=False,
            )

    def test_max_risk_budget_cannot_exceed_total_capital(self):
        """max_risk_budget must be <= total_capital."""
        with self.assertRaises(ValidationError):
            CapitalProfile(
                profile_id="test",
                total_capital=100000.0,
                cash_available=100000.0,
                max_risk_budget=150000.0,  # More than total
                capital_unit="CNY",
                created_at=datetime.now(timezone.utc),
                source="manual",
                confirmed_by_user=False,
            )

    def test_valid_profile(self):
        """Valid profile should be created successfully."""
        profile = CapitalProfile(
            profile_id="test",
            total_capital=100000.0,
            cash_available=80000.0,
            max_risk_budget=10000.0,
            capital_unit="CNY",
            created_at=datetime.now(timezone.utc),
            source="manual",
            confirmed_by_user=True,
        )
        self.assertEqual(profile.total_capital, 100000.0)
        self.assertEqual(profile.cash_available, 80000.0)


class TestPositionSizingPlan(unittest.TestCase):
    """Test PositionSizingPlan validation."""

    def test_all_limits_must_be_positive(self):
        """All sizing limits must be > 0."""
        with self.assertRaises(ValidationError):
            PositionSizingPlan(
                plan_id="test",
                profile_id="test_profile",
                max_single_position_capital=0.0,  # Invalid
                max_total_live_capital=10000.0,
                max_position_count=4,
                risk_cap_per_trade=100.0,
                created_at=datetime.now(timezone.utc),
                basis="V1_conservative_defaults",
            )

    def test_max_single_cannot_exceed_max_total(self):
        """max_single_position_capital must be <= max_total_live_capital."""
        with self.assertRaises(ValidationError):
            PositionSizingPlan(
                plan_id="test",
                profile_id="test_profile",
                max_single_position_capital=15000.0,  # More than total
                max_total_live_capital=10000.0,
                max_position_count=4,
                risk_cap_per_trade=100.0,
                created_at=datetime.now(timezone.utc),
                basis="V1_conservative_defaults",
            )


class TestCapitalContext(unittest.TestCase):
    """Test CapitalContext construction."""

    def test_unconfirmed_profile_is_not_live_capable(self):
        """Unconfirmed profile should not be live-capable."""
        profile = CapitalProfile(
            profile_id="test",
            total_capital=100000.0,
            cash_available=80000.0,
            max_risk_budget=10000.0,
            capital_unit="CNY",
            created_at=datetime.now(timezone.utc),
            source="manual",
            confirmed_by_user=False,  # Not confirmed
        )
        context = build_capital_context(profile)
        self.assertFalse(context.is_live_capable)
        self.assertIn("not confirmed", context.blocking_reason.lower())

    def test_confirmed_valid_profile_is_live_capable(self):
        """Confirmed valid profile should be live-capable."""
        profile = CapitalProfile(
            profile_id="test",
            total_capital=100000.0,
            cash_available=80000.0,
            max_risk_budget=10000.0,
            capital_unit="CNY",
            created_at=datetime.now(timezone.utc),
            source="manual",
            confirmed_by_user=True,
        )
        context = build_capital_context(profile)
        self.assertTrue(context.is_live_capable)
        self.assertIsNone(context.blocking_reason)


class TestPositionSizingRules(unittest.TestCase):
    """Test V1 conservative position sizing rules."""

    def test_max_total_live_capital_capped_at_30_percent_and_cash(self):
        """max_total_live_capital = min(cash_available, total_capital * 0.30)."""
        # Case 1: cash is limiting factor
        profile1 = CapitalProfile(
            profile_id="test1",
            total_capital=100000.0,
            cash_available=20000.0,  # Less than 30%
            max_risk_budget=10000.0,
            capital_unit="CNY",
            created_at=datetime.now(timezone.utc),
            source="manual",
            confirmed_by_user=True,
        )
        plan1 = build_position_sizing_plan(profile1)
        self.assertEqual(plan1.max_total_live_capital, 20000.0)

        # Case 2: 30% is limiting factor
        profile2 = CapitalProfile(
            profile_id="test2",
            total_capital=100000.0,
            cash_available=50000.0,  # More than 30%
            max_risk_budget=10000.0,
            capital_unit="CNY",
            created_at=datetime.now(timezone.utc),
            source="manual",
            confirmed_by_user=True,
        )
        plan2 = build_position_sizing_plan(profile2)
        self.assertEqual(plan2.max_total_live_capital, 30000.0)  # 30% of 100k

    def test_max_single_position_capped_at_25_percent_live_and_10_percent_total(self):
        """max_single_position_capital = min(max_total_live * 0.25, total * 0.10)."""
        profile = CapitalProfile(
            profile_id="test",
            total_capital=100000.0,
            cash_available=50000.0,
            max_risk_budget=10000.0,
            capital_unit="CNY",
            created_at=datetime.now(timezone.utc),
            source="manual",
            confirmed_by_user=True,
        )
        plan = build_position_sizing_plan(profile)
        # max_total_live = min(50000, 30000) = 30000
        # max_single = min(30000 * 0.25, 100000 * 0.10) = min(7500, 10000) = 7500
        self.assertEqual(plan.max_single_position_capital, 7500.0)

    def test_max_position_count_is_exactly_4(self):
        """max_position_count must be exactly 4."""
        profile = CapitalProfile(
            profile_id="test",
            total_capital=100000.0,
            cash_available=80000.0,
            max_risk_budget=10000.0,
            capital_unit="CNY",
            created_at=datetime.now(timezone.utc),
            source="manual",
            confirmed_by_user=True,
        )
        plan = build_position_sizing_plan(profile)
        self.assertEqual(plan.max_position_count, 4)

    def test_risk_cap_per_trade_capped_at_8_percent_single_and_1_percent_total(self):
        """risk_cap_per_trade = min(max_single * 0.08, total * 0.01)."""
        profile = CapitalProfile(
            profile_id="test",
            total_capital=100000.0,
            cash_available=50000.0,
            max_risk_budget=10000.0,
            capital_unit="CNY",
            created_at=datetime.now(timezone.utc),
            source="manual",
            confirmed_by_user=True,
        )
        plan = build_position_sizing_plan(profile)
        # max_single = 7500 (from previous test)
        # risk_cap = min(7500 * 0.08, 100000 * 0.01) = min(600, 1000) = 600
        self.assertEqual(plan.risk_cap_per_trade, 600.0)


class TestNoForbiddenFields(unittest.TestCase):
    """Verify no symbol/recommendation/order/P&L fields."""

    def test_capital_profile_has_no_forbidden_fields(self):
        """CapitalProfile must not have symbol/recommendation/order/P&L fields."""
        fields = set(CapitalProfile.model_fields.keys())
        forbidden = {"symbol", "recommendation", "order", "pnl", "profit", "loss"}
        intersection = fields & forbidden
        self.assertEqual(
            len(intersection),
            0,
            f"CapitalProfile must not have forbidden fields: {intersection}",
        )

    def test_position_sizing_plan_has_no_forbidden_fields(self):
        """PositionSizingPlan must not have symbol/recommendation/order/P&L fields."""
        fields = set(PositionSizingPlan.model_fields.keys())
        forbidden = {"symbol", "recommendation", "order", "pnl", "profit", "loss"}
        intersection = fields & forbidden
        self.assertEqual(
            len(intersection),
            0,
            f"PositionSizingPlan must not have forbidden fields: {intersection}",
        )


class TestNoForbiddenLogic(unittest.TestCase):
    """Verify no LLM/Tushare/market data/recommendation/execution/broker/random/time logic."""

    def test_no_forbidden_imports_in_contract(self):
        """contracts/capital_context.py must not import forbidden modules."""
        from contracts import capital_context

        source = inspect.getsource(capital_context)
        forbidden = [
            "anthropic",
            "openai",
            "tushare",
            "random",
            "numpy.random",
            "time.sleep",
        ]
        for module in forbidden:
            self.assertNotIn(
                module,
                source,
                f"contracts/capital_context.py must not import {module}",
            )

    def test_no_forbidden_imports_in_service(self):
        """backend/services/capital_context.py must not import forbidden modules."""
        from backend.services import capital_context

        source = inspect.getsource(capital_context)
        forbidden = [
            "anthropic",
            "openai",
            "tushare",
            "random",
            "numpy.random",
            "time.sleep",
        ]
        for module in forbidden:
            self.assertNotIn(
                module,
                source,
                f"backend/services/capital_context.py must not import {module}",
            )


if __name__ == "__main__":
    unittest.main()
