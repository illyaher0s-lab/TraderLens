"""Cursor-bound data view for event-driven backtest."""
from __future__ import annotations

from datetime import date

from backend.services.backtest_time_cursor import BacktestTimeCursor, FutureDataAccessError
from contracts.stable import DailyBar


class CursorBoundDataView:
    """
    Cursor-bound data view that enforces time-based read constraints.
    
    All data reads go through cursor validation. Future data access is blocked.
    Read trace is automatically recorded in cursor.
    """
    
    def __init__(self, raw_data_source, cursor: BacktestTimeCursor):
        self._raw = raw_data_source
        self._cursor = cursor
    
    def get_daily_bars(self, symbol: str) -> list[DailyBar]:
        """
        Get daily bars for symbol.
        
        Note: This returns all bars but callers must filter by cursor-allowed dates.
        Individual bar access should use get_bar() which enforces cursor.
        """
        return self._raw.get_daily_bars(symbol)
    
    def get_bar(self, symbol: str, as_of_date: date) -> DailyBar | None:
        """Get single bar with cursor validation."""
        allowed, violation = self._cursor.request_read(
            symbol=symbol,
            requested_date=as_of_date,
            data_type="bar",
            source="event_loop_data_view",
        )
        
        if not allowed:
            raise FutureDataAccessError(violation)
        
        # Get bar from raw source
        bars = self._raw.get_daily_bars(symbol)
        for bar in bars:
            if bar.date == as_of_date:
                return bar
        return None
    
    def get_daily_bar(self, symbol: str, trade_date: date) -> DailyBar:
        """Compatibility adapter for get_bar (used by fill_simulator)."""
        bar = self.get_bar(symbol, trade_date)
        if bar is None:
            raise KeyError(f"No bar for {symbol} on {trade_date}")
        return bar
    
    def get_price(self, symbol: str, as_of_date: date) -> float:
        """Get close price with cursor validation."""
        bar = self.get_bar(symbol, as_of_date)
        if bar is None:
            raise ValueError(f"No bar for {symbol} on {as_of_date}")
        return bar.close
    
    def get_status(self, symbol: str, as_of_date: date):
        """Get daily status with cursor validation."""
        allowed, violation = self._cursor.request_read(
            symbol=symbol,
            requested_date=as_of_date,
            data_type="daily_status",
            source="event_loop_data_view",
        )
        
        if not allowed:
            raise FutureDataAccessError(violation)
        
        return self._raw.get_status(symbol, as_of_date)
    
    def get_daily_status(self, symbol: str, trade_date: date):
        """Compatibility adapter for get_status (used by fill_simulator)."""
        return self.get_status(symbol, trade_date)
