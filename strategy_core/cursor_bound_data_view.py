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
    
    def __init__(
        self,
        raw_data_source,
        cursor: BacktestTimeCursor,
        adjustment_mode: str | None = None,
        adjustment_snapshot_date: date | None = None,
        adjustment_fingerprint: str | None = None,
        expected_adjustment_fingerprint: str | None = None,
    ):
        """
        Initialize cursor-bound data view.
        
        Args:
            raw_data_source: Raw data source
            cursor: BacktestTimeCursor
            adjustment_mode: Optional "raw", "qfq", or "hfq" (Task 8)
            adjustment_snapshot_date: Optional adjustment factor snapshot date (Task 8)
            adjustment_fingerprint: Optional adjustment factor fingerprint (Task 8)
            expected_adjustment_fingerprint: Optional expected fingerprint from B3 (Task 8)
        
        Task 8 compatibility:
        - If adjustment parameters are None → skip adjustment validation (backward compat)
        - If adjustment parameters are provided → enforce adjustment snapshot guard
        """
        self._raw = raw_data_source
        self._cursor = cursor
        
        # Task 8: Adjustment snapshot guard (optional)
        self._adjustment_mode = adjustment_mode
        self._adjustment_snapshot_date = adjustment_snapshot_date
        self._adjustment_fingerprint = adjustment_fingerprint
        self._expected_adjustment_fingerprint = expected_adjustment_fingerprint
        
        # Validate: either all adjustment params provided or all None
        adj_params = [
            adjustment_mode,
            adjustment_snapshot_date,
            adjustment_fingerprint,
            expected_adjustment_fingerprint,
        ]
        adj_provided_count = sum(p is not None for p in adj_params)
        if adj_provided_count not in (0, 4):
            raise ValueError(
                f"Adjustment validation requires all 4 parameters or none. "
                f"Got {adj_provided_count}/4 provided."
            )
    
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
                # Task 8: Validate adjustment snapshot if enabled
                if self._adjustment_mode is not None:
                    self._cursor.validate_bar_adjustment(
                        symbol=symbol,
                        bar=bar,
                        adjustment_mode=self._adjustment_mode,
                        adjustment_snapshot_date=self._adjustment_snapshot_date,
                        adjustment_fingerprint=self._adjustment_fingerprint,
                        expected_adjustment_fingerprint=self._expected_adjustment_fingerprint,
                        source="cursor_bound_data_view",
                    )
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
