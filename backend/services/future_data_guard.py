"""B4 Future Data Guard - Comprehensive future data access prevention."""
from __future__ import annotations

from datetime import date

from backend.services.backtest_time_cursor import (
    BacktestTimeCursor,
    FutureDataAccessError,
)
from backend.services.b4_protocol_types import FutureDataViolation


class FutureDataGuard:
    """
    Comprehensive future data access guard.
    
    Blocks:
    - Future bar access
    - Future daily status
    - Future financial ann_date
    - Future universe membership
    - Full-sample mean/percentile (uses future data)
    - Future adjustment factor
    
    All violations are blocking failures, not degraded success.
    """
    
    def __init__(self, cursor: BacktestTimeCursor):
        self.cursor = cursor
        self.violations: list[FutureDataViolation] = []
    
    def check_bar_access(
        self,
        symbol: str,
        requested_date: date,
        source: str = "bar_reader",
    ) -> None:
        """
        Check bar access against cursor.
        
        Raises:
            FutureDataAccessError: If requested_date > allowed_read_until
        """
        allowed, violation = self.cursor.request_read(
            symbol=symbol,
            requested_date=requested_date,
            data_type="bar",
            source=source,
        )
        
        if not allowed:
            self.violations.append(violation)
            raise FutureDataAccessError(violation)
    
    def check_daily_status_access(
        self,
        symbol: str,
        requested_date: date,
        source: str = "status_reader",
    ) -> None:
        """Check daily status (ST, suspension, limit) access."""
        allowed, violation = self.cursor.request_read(
            symbol=symbol,
            requested_date=requested_date,
            data_type="daily_status",
            source=source,
        )
        
        if not allowed:
            self.violations.append(violation)
            raise FutureDataAccessError(violation)
    
    def check_financial_access(
        self,
        symbol: str,
        ann_date: date,
        source: str = "financial_reader",
    ) -> None:
        """
        Check financial data access (ann_date must be <= cursor date).
        
        Uses ann_date, not report_period_end.
        """
        allowed, violation = self.cursor.request_read(
            symbol=symbol,
            requested_date=ann_date,
            data_type="financial",
            source=source,
        )
        
        if not allowed:
            self.violations.append(violation)
            raise FutureDataAccessError(violation)
    
    def check_membership_access(
        self,
        symbol: str,
        membership_date: date,
        source: str = "membership_reader",
    ) -> None:
        """Check universe membership access."""
        allowed, violation = self.cursor.request_read(
            symbol=symbol,
            requested_date=membership_date,
            data_type="membership",
            source=source,
        )
        
        if not allowed:
            self.violations.append(violation)
            raise FutureDataAccessError(violation)
    
    def check_adjustment_factor_access(
        self,
        symbol: str,
        factor_date: date,
        source: str = "adjustment_factor_reader",
    ) -> None:
        """Check adjustment factor access."""
        allowed, violation = self.cursor.request_read(
            symbol=symbol,
            requested_date=factor_date,
            data_type="adjustment_factor",
            source=source,
        )
        
        if not allowed:
            self.violations.append(violation)
            raise FutureDataAccessError(violation)
    
    def block_full_sample_stats(
        self,
        operation: str,
        source: str = "stats_calculator",
    ) -> None:
        """
        Block full-sample mean/percentile/normalization.
        
        These use future data and must be blocked.
        """
        # Full-sample stats implicitly access all dates including future
        # Create violation with max possible date to indicate this
        violation = FutureDataViolation(
            requested_date=date(9999, 12, 31),  # Sentinel: full sample
            allowed_max_date=self.cursor.allowed_read_until,
            source=source,
            reason=f"Full-sample {operation} uses future data",
            evaluation_mode=self.cursor.evaluation_mode,
        )
        
        self.violations.append(violation)
        raise FutureDataAccessError(violation)
    
    def get_violations(self) -> tuple[FutureDataViolation, ...]:
        """Get all recorded violations."""
        return tuple(self.violations)
