"""
V1 Live Market Data Adapter

Provides auditable market data snapshots with explicit fault states.
Current private Tushare service does NOT support minute-level data.

No LLM, no recommendations, no execution logic.
"""

from datetime import date
from typing import Any, Callable, Optional

from contracts.market_data_fault import (
    MarketDataFault,
    MarketDataFaultState,
    MarketDataResult,
)


def get_daily_basic_snapshot(
    symbol: str,
    as_of: date,
    provider: Optional[Callable[[str, date], dict[str, Any]]] = None,
) -> MarketDataResult:
    """
    Get daily basic market data snapshot.

    Args:
        symbol: Stock symbol (e.g., "000001.SZ")
        as_of: Date for the snapshot
        provider: Optional provider function for testing (symbol, as_of) -> data

    Returns:
        MarketDataResult with fault information
    """
    if provider is None:
        # No real provider configured, return unavailable
        fault = MarketDataFault(
            state=MarketDataFaultState.unavailable,
            source="tushare_private",
            dataset="daily_basic",
            symbol=symbol,
            as_of=as_of,
            message="No real provider configured",
            recoverable=False,
            evidence={"reason": "provider_not_configured"},
        )
        return MarketDataResult(
            symbol=symbol,
            dataset="daily_basic",
            as_of=as_of,
            data=None,
            fault=fault,
        )

    try:
        data = provider(symbol, as_of)
        fault = MarketDataFault(
            state=MarketDataFaultState.ok,
            source="tushare_private",
            dataset="daily_basic",
            symbol=symbol,
            as_of=as_of,
            message=None,
            recoverable=True,
            evidence=None,
        )
        return MarketDataResult(
            symbol=symbol,
            dataset="daily_basic",
            as_of=as_of,
            data=data,
            fault=fault,
        )
    except Exception as e:
        fault = MarketDataFault(
            state=MarketDataFaultState.source_error,
            source="tushare_private",
            dataset="daily_basic",
            symbol=symbol,
            as_of=as_of,
            message=f"Provider failed: {str(e)}",
            recoverable=False,
            evidence={"exception": str(e), "exception_type": type(e).__name__},
        )
        return MarketDataResult(
            symbol=symbol,
            dataset="daily_basic",
            as_of=as_of,
            data=None,
            fault=fault,
        )


def get_current_price_snapshot(
    symbol: str,
    as_of: date,
    provider: Optional[Callable[[str, date], dict[str, Any]]] = None,
) -> MarketDataResult:
    """
    Get current price snapshot.

    Args:
        symbol: Stock symbol (e.g., "000001.SZ")
        as_of: Date for the snapshot
        provider: Optional provider function for testing (symbol, as_of) -> data

    Returns:
        MarketDataResult with fault information
    """
    if provider is None:
        fault = MarketDataFault(
            state=MarketDataFaultState.unavailable,
            source="tushare_private",
            dataset="current_price",
            symbol=symbol,
            as_of=as_of,
            message="No real provider configured",
            recoverable=False,
            evidence={"reason": "provider_not_configured"},
        )
        return MarketDataResult(
            symbol=symbol,
            dataset="current_price",
            as_of=as_of,
            data=None,
            fault=fault,
        )

    try:
        data = provider(symbol, as_of)
        fault = MarketDataFault(
            state=MarketDataFaultState.ok,
            source="tushare_private",
            dataset="current_price",
            symbol=symbol,
            as_of=as_of,
            message=None,
            recoverable=True,
            evidence=None,
        )
        return MarketDataResult(
            symbol=symbol,
            dataset="current_price",
            as_of=as_of,
            data=data,
            fault=fault,
        )
    except Exception as e:
        fault = MarketDataFault(
            state=MarketDataFaultState.source_error,
            source="tushare_private",
            dataset="current_price",
            symbol=symbol,
            as_of=as_of,
            message=f"Provider failed: {str(e)}",
            recoverable=False,
            evidence={"exception": str(e), "exception_type": type(e).__name__},
        )
        return MarketDataResult(
            symbol=symbol,
            dataset="current_price",
            as_of=as_of,
            data=None,
            fault=fault,
        )


def get_intraday_minute_snapshot(
    symbol: str,
    as_of: date,
    provider: Optional[Callable[[str, date], dict[str, Any]]] = None,
) -> MarketDataResult:
    """
    Get intraday minute-level snapshot.

    IMPORTANT: Current private Tushare service does NOT support minute data.
    rt_min, stk_mins, and pro_bar with 1min frequency are not available.

    This function ALWAYS returns adapter_unsupported.

    Args:
        symbol: Stock symbol (e.g., "000001.SZ")
        as_of: Date for the snapshot
        provider: Ignored (minute data not supported)

    Returns:
        MarketDataResult with adapter_unsupported fault
    """
    fault = MarketDataFault(
        state=MarketDataFaultState.adapter_unsupported,
        source="tushare_private",
        dataset="intraday_minute",
        symbol=symbol,
        as_of=as_of,
        message="Minute-level data not supported by current Tushare service",
        recoverable=False,
        evidence={
            "reason": "adapter_unsupported",
            "unavailable_apis": ["rt_min", "stk_mins", "pro_bar_1min"],
            "supported_frequencies": ["daily"],
        },
    )
    return MarketDataResult(
        symbol=symbol,
        dataset="intraday_minute",
        as_of=as_of,
        data=None,
        fault=fault,
    )
