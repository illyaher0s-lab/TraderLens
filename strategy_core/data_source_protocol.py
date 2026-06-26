"""
Data Source Protocol - M2

Defines the stable interface that all data sources must implement.
This protocol is frozen after M2 closeout.
"""

from __future__ import annotations
from datetime import date, datetime
from typing import Protocol, Literal
from dataclasses import dataclass

from contracts.stable import DailyBar, DailyStatus
from strategy_core.data_source_metadata import DataSourceMetadata


@dataclass
class DataSourceValidationResult:
    """
    Result of data source validation.
    
    M2 Requirement: All data sources must provide validation capability.
    """
    # Validation status
    status: Literal["pass", "degraded", "failed"]
    
    # Source identification
    source_id: str
    
    # Validation timestamp
    checked_at: datetime
    
    # Issues found
    errors: list[str]  # Critical issues (status=failed)
    warnings: list[str]  # Non-critical issues (status=degraded)
    
    # Validation details
    checks_performed: list[str]  # List of validation checks run
    data_quality_score: float | None = None  # Optional 0.0-1.0 score


class DataSource(Protocol):
    """
    Stable data source interface for strategy_core.
    
    M2 Contract: This protocol is frozen after M2 closeout.
    Breaking changes require schema version bump.
    
    All data sources MUST implement this interface to be compatible
    with strategy_core backtest engine.
    """
    
    def get_metadata(self) -> DataSourceMetadata:
        """
        Return data source metadata including schema version.
        
        M2 Requirement: All data sources MUST implement this.
        
        Returns:
            DataSourceMetadata with schema_version, snapshot info, etc.
        
        Raises:
            ValueError: If required metadata fields are missing.
        """
        ...
    
    def validate(self) -> DataSourceValidationResult:
        """
        Validate data integrity.
        
        M2 Requirement: All data sources MUST provide validation capability.
        
        Validation checks (minimum required):
        1. Schema version present and supported
        2. Trading calendar non-empty and sorted
        3. OHLC constraints per bar (low ≤ open, close ≤ high)
        4. Date continuity (no gaps in trading_dates)
        5. Symbol coverage (all symbols have bars and statuses)
        
        Returns:
            DataSourceValidationResult with status and issues found.
        
        Note: Validation result can be cached. Backtest engine will
              call this before each backtest run.
        """
        ...
    
    def symbols(self) -> list[str]:
        """
        Return list of available symbols.
        
        Returns:
            List of symbol strings (e.g., ["600519.SH", "000001.SZ"])
        """
        ...
    
    def get_daily_bars(self, symbol: str) -> list[DailyBar]:
        """
        Return all daily bars for a symbol.
        
        Args:
            symbol: Stock symbol (e.g., "600519.SH")
        
        Returns:
            List of DailyBar sorted by date
        
        Raises:
            KeyError: If symbol not found (fail-loud, M2 policy)
        
        Missing data behavior (M2 policy):
        - Missing symbol → KeyError (fail-loud, do not guess)
        - Empty result → valid (symbol exists but no bars)
        """
        ...
    
    def get_daily_statuses(self, symbol: str) -> list[DailyStatus]:
        """
        Return all daily statuses for a symbol.
        
        Args:
            symbol: Stock symbol
        
        Returns:
            List of DailyStatus sorted by date
        
        Raises:
            KeyError: If symbol not found (fail-loud)
        
        Missing data behavior: same as get_daily_bars.
        """
        ...
    
    def get_daily_bar(self, symbol: str, date: date) -> DailyBar:
        """
        Return single bar for symbol on date.
        
        Args:
            symbol: Stock symbol
            date: Trading date
        
        Returns:
            DailyBar for that symbol and date
        
        Raises:
            KeyError: If symbol/date not found (fail-loud)
        
        Missing data behavior (M2 policy):
        - Missing symbol/date → KeyError (fail-loud, do not guess)
        - Do NOT forward-fill, interpolate, or use default values
        """
        ...
    
    def get_daily_status(self, symbol: str, date: date) -> DailyStatus:
        """
        Return single status for symbol on date.
        
        Args:
            symbol: Stock symbol
            date: Trading date
        
        Returns:
            DailyStatus for that symbol and date
        
        Raises:
            KeyError: If symbol/date not found (fail-loud)
        
        Missing data behavior: same as get_daily_bar.
        """
        ...
    
    def get_price(self, symbol: str, date: date) -> float:
        """
        PriceProvider protocol: get close price for symbol on date.
        
        Args:
            symbol: Stock symbol
            date: Trading date
        
        Returns:
            Closing price (float)
        
        Raises:
            KeyError: If symbol/date not found (fail-loud)
        
        Used by: order generation (position sizing)
        
        Missing data behavior: KeyError (fail-loud)
        """
        ...


# Type alias for backward compatibility
PriceProvider = DataSource
