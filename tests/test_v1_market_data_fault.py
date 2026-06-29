"""
V1 Market Data Fault Boundary Tests

Verifies:
- All MarketDataFaultState values are valid
- Non-ok states require message and evidence
- adapter_unsupported must be non-recoverable
- Non-ok faults cannot have data
- ok faults must have data
- Intraday minute data returns adapter_unsupported
- Daily snapshot returns ok when provider succeeds
- Daily snapshot returns source_error/unavailable when provider fails
- No LLM/recommendation/execution/broker/random logic
"""

import inspect
import unittest
from datetime import date
from typing import Any

from pydantic import ValidationError

from contracts.market_data_fault import (
    MarketDataFault,
    MarketDataFaultState,
    MarketDataResult,
)
from backend.services.live_market_data import (
    get_daily_basic_snapshot,
    get_current_price_snapshot,
    get_intraday_minute_snapshot,
)


class TestMarketDataFaultState(unittest.TestCase):
    """Test MarketDataFaultState enum."""

    def test_all_states_are_valid(self):
        """All MarketDataFaultState values should be accessible."""
        states = [
            MarketDataFaultState.ok,
            MarketDataFaultState.stale,
            MarketDataFaultState.partial,
            MarketDataFaultState.inconsistent,
            MarketDataFaultState.unavailable,
            MarketDataFaultState.source_error,
            MarketDataFaultState.adapter_unsupported,
        ]
        self.assertEqual(len(states), 7)


class TestMarketDataFault(unittest.TestCase):
    """Test MarketDataFault validation rules."""

    def test_non_ok_state_requires_message(self):
        """Non-ok states must have message."""
        with self.assertRaises(ValidationError) as ctx:
            MarketDataFault(
                state=MarketDataFaultState.unavailable,
                source="test_source",
                dataset="test_dataset",
                symbol="000001.SZ",
                as_of=date(2026, 6, 1),
                message="",  # Empty message
                recoverable=False,
                evidence={},
            )
        self.assertIn("message", str(ctx.exception))

    def test_non_ok_state_requires_evidence(self):
        """Non-ok states must have evidence."""
        with self.assertRaises(ValidationError) as ctx:
            MarketDataFault(
                state=MarketDataFaultState.unavailable,
                source="test_source",
                dataset="test_dataset",
                symbol="000001.SZ",
                as_of=date(2026, 6, 1),
                message="Data unavailable",
                recoverable=False,
                evidence={},  # Empty evidence
            )
        self.assertIn("evidence", str(ctx.exception))

    def test_ok_state_cannot_have_message(self):
        """ok state must have message=None."""
        with self.assertRaises(ValidationError) as ctx:
            MarketDataFault(
                state=MarketDataFaultState.ok,
                source="test_source",
                dataset="test_dataset",
                symbol="000001.SZ",
                as_of=date(2026, 6, 1),
                message="provider failed",  # Error-like message not allowed
                recoverable=True,
                evidence=None,
            )
        self.assertIn("message", str(ctx.exception).lower())

    def test_ok_state_cannot_have_evidence(self):
        """ok state must have evidence=None or empty."""
        with self.assertRaises(ValidationError) as ctx:
            MarketDataFault(
                state=MarketDataFaultState.ok,
                source="test_source",
                dataset="test_dataset",
                symbol="000001.SZ",
                as_of=date(2026, 6, 1),
                message=None,
                recoverable=True,
                evidence={"error": "x"},  # Evidence not allowed for ok
            )
        self.assertIn("evidence", str(ctx.exception).lower())

    def test_adapter_unsupported_must_be_non_recoverable(self):
        """adapter_unsupported must have recoverable=False."""
        with self.assertRaises(ValidationError) as ctx:
            MarketDataFault(
                state=MarketDataFaultState.adapter_unsupported,
                source="tushare_private",
                dataset="intraday_minute",
                symbol="000001.SZ",
                as_of=date(2026, 6, 1),
                message="Minute data not supported",
                recoverable=True,  # Wrong
                evidence={"reason": "rt_min unavailable"},
            )
        self.assertIn("recoverable", str(ctx.exception))

    def test_non_ok_fault_cannot_have_data(self):
        """Non-ok fault must not have data in MarketDataResult."""
        fault = MarketDataFault(
            state=MarketDataFaultState.unavailable,
            source="test_source",
            dataset="test_dataset",
            symbol="000001.SZ",
            as_of=date(2026, 6, 1),
            message="Data unavailable",
            recoverable=False,
            evidence={"reason": "network timeout"},
        )
        with self.assertRaises(ValidationError) as ctx:
            MarketDataResult(
                symbol="000001.SZ",
                dataset="test_dataset",
                as_of=date(2026, 6, 1),
                data={"price": 10.0},  # Should not have data
                fault=fault,
            )
        self.assertIn("data", str(ctx.exception).lower())

    def test_ok_fault_must_have_non_empty_data(self):
        """ok fault must have non-empty data in MarketDataResult."""
        fault = MarketDataFault(
            state=MarketDataFaultState.ok,
            source="test_source",
            dataset="test_dataset",
            symbol="000001.SZ",
            as_of=date(2026, 6, 1),
            message=None,
            recoverable=True,
            evidence=None,
        )
        # Test None data
        with self.assertRaises(ValidationError) as ctx:
            MarketDataResult(
                symbol="000001.SZ",
                dataset="test_dataset",
                as_of=date(2026, 6, 1),
                data=None,  # Should have data
                fault=fault,
            )
        self.assertIn("data", str(ctx.exception).lower())

        # Test empty dict
        with self.assertRaises(ValidationError) as ctx:
            MarketDataResult(
                symbol="000001.SZ",
                dataset="test_dataset",
                as_of=date(2026, 6, 1),
                data={},  # Empty dict not allowed
                fault=fault,
            )
        self.assertIn("data", str(ctx.exception).lower())


class TestLiveMarketDataAdapter(unittest.TestCase):
    """Test live market data adapter behavior."""

    def test_intraday_minute_returns_adapter_unsupported(self):
        """Intraday minute data must return adapter_unsupported."""
        result = get_intraday_minute_snapshot(
            symbol="000001.SZ",
            as_of=date(2026, 6, 1),
        )
        self.assertEqual(result.fault.state, MarketDataFaultState.adapter_unsupported)
        self.assertFalse(result.fault.recoverable)
        self.assertIsNone(result.data)

    def test_intraday_minute_evidence_mentions_unavailable_apis(self):
        """Evidence should mention rt_min, stk_mins, pro_bar_1min."""
        result = get_intraday_minute_snapshot(
            symbol="000001.SZ",
            as_of=date(2026, 6, 1),
        )
        evidence_str = str(result.fault.evidence).lower()
        # Should mention at least one of the unavailable APIs
        has_mention = any(
            api in evidence_str
            for api in ["rt_min", "stk_mins", "pro_bar", "1min", "minute"]
        )
        self.assertTrue(
            has_mention,
            f"Evidence should mention unavailable minute data APIs: {result.fault.evidence}",
        )

    def test_daily_snapshot_returns_ok_when_provider_succeeds(self):
        """Daily snapshot returns ok when provider provides data."""

        def mock_provider(symbol: str, as_of: date) -> dict[str, Any]:
            return {
                "symbol": symbol,
                "as_of": as_of,
                "close": 10.5,
                "volume": 1000000,
            }

        result = get_daily_basic_snapshot(
            symbol="000001.SZ",
            as_of=date(2026, 6, 1),
            provider=mock_provider,
        )
        self.assertEqual(result.fault.state, MarketDataFaultState.ok)
        self.assertIsNotNone(result.data)
        self.assertEqual(result.data["close"], 10.5)

    def test_daily_snapshot_returns_unavailable_when_provider_returns_empty(self):
        """Daily snapshot returns unavailable when provider returns empty dict."""

        def empty_provider(symbol: str, as_of: date) -> dict[str, Any]:
            return {}

        result = get_daily_basic_snapshot(
            symbol="000001.SZ",
            as_of=date(2026, 6, 1),
            provider=empty_provider,
        )
        self.assertEqual(result.fault.state, MarketDataFaultState.unavailable)
        self.assertIsNone(result.data)
        self.assertIn("empty", result.fault.message.lower())

    def test_daily_snapshot_returns_source_error_when_provider_fails(self):
        """Daily snapshot returns source_error when provider raises exception."""

        def failing_provider(symbol: str, as_of: date) -> dict[str, Any]:
            raise ConnectionError("Network timeout")

        result = get_daily_basic_snapshot(
            symbol="000001.SZ",
            as_of=date(2026, 6, 1),
            provider=failing_provider,
        )
        self.assertIn(
            result.fault.state,
            [MarketDataFaultState.source_error, MarketDataFaultState.unavailable],
        )
        self.assertIsNone(result.data)
        self.assertIn("network", result.fault.message.lower())

    def test_current_price_snapshot_returns_ok_when_provider_succeeds(self):
        """Current price snapshot returns ok when provider provides data."""

        def mock_provider(symbol: str, as_of: date) -> dict[str, Any]:
            return {
                "symbol": symbol,
                "as_of": as_of,
                "price": 10.5,
            }

        result = get_current_price_snapshot(
            symbol="000001.SZ",
            as_of=date(2026, 6, 1),
            provider=mock_provider,
        )
        self.assertEqual(result.fault.state, MarketDataFaultState.ok)
        self.assertIsNotNone(result.data)
        self.assertEqual(result.data["price"], 10.5)

    def test_current_price_snapshot_returns_unavailable_when_provider_returns_empty(
        self,
    ):
        """Current price snapshot returns unavailable when provider returns empty dict."""

        def empty_provider(symbol: str, as_of: date) -> dict[str, Any]:
            return {}

        result = get_current_price_snapshot(
            symbol="000001.SZ",
            as_of=date(2026, 6, 1),
            provider=empty_provider,
        )
        self.assertEqual(result.fault.state, MarketDataFaultState.unavailable)
        self.assertIsNone(result.data)
        self.assertIn("empty", result.fault.message.lower())


class TestNoForbiddenLogic(unittest.TestCase):
    """Verify no LLM/recommendation/execution/broker/random logic."""

    def test_no_forbidden_imports_in_contract(self):
        """contracts/market_data_fault.py must not import forbidden modules."""
        from contracts import market_data_fault

        source = inspect.getsource(market_data_fault)
        forbidden = ["anthropic", "openai", "random", "numpy.random"]
        for module in forbidden:
            self.assertNotIn(
                module,
                source,
                f"contracts/market_data_fault.py must not import {module}",
            )

    def test_no_forbidden_imports_in_service(self):
        """backend/services/live_market_data.py must not import forbidden modules."""
        from backend.services import live_market_data

        source = inspect.getsource(live_market_data)
        forbidden = ["anthropic", "openai", "random", "numpy.random"]
        for module in forbidden:
            self.assertNotIn(
                module,
                source,
                f"backend/services/live_market_data.py must not import {module}",
            )


if __name__ == "__main__":
    unittest.main()
