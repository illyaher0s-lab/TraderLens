"""B4 Backtest Time Cursor - Strict time-based data access control."""
from __future__ import annotations

from datetime import date

from backend.services.b4_protocol_types import (
    BacktestCursorState,
    BacktestReadRequest,
    FutureDataViolation,
)


class BacktestTimeCursor:
    """
    Strict backtest time cursor.
    
    Rules:
    - T日 signal phase: only read <= T
    - T+1 execution data: only in execution phase, cannot backflow to T
    - Strategy logic cannot directly access raw full dataset
    - Unknown symbol/date: fail loud
    - Read trace recorded
    - No DB write, no LLM dependency
    """
    
    def __init__(
        self,
        cursor_id: str,
        current_date: date,
        evaluation_mode: str,
    ):
        self.cursor_id = cursor_id
        self.current_date = current_date
        self.evaluation_mode = evaluation_mode
        self.read_trace: list[str] = []
        
        # Set allowed read window based on mode
        if evaluation_mode == "signal_phase":
            # Signal phase: can only read <= current_date
            self.allowed_read_until = current_date
        elif evaluation_mode == "execution_phase":
            # Execution phase: can read current_date + 1 (for execution data)
            # But this cannot backflow into signal logic
            from datetime import timedelta
            self.allowed_read_until = current_date + timedelta(days=1)
        else:
            raise ValueError(f"Unknown evaluation_mode: {evaluation_mode}")
    
    def get_state(self) -> BacktestCursorState:
        """Get immutable cursor state snapshot."""
        return BacktestCursorState(
            cursor_id=self.cursor_id,
            current_date=self.current_date,
            allowed_read_until=self.allowed_read_until,
            evaluation_mode=self.evaluation_mode,
            read_trace=tuple(self.read_trace),
        )
    
    def request_read(
        self,
        symbol: str,
        requested_date: date,
        data_type: str,
        source: str,
    ) -> tuple[bool, FutureDataViolation | None]:
        """
        Request data read with time validation.
        
        Returns:
            (allowed, violation) - allowed=True means read OK, violation=None
                                   allowed=False means blocked, violation has details
        """
        # Validate requested_date <= allowed_read_until
        if requested_date > self.allowed_read_until:
            violation = FutureDataViolation(
                requested_date=requested_date,
                allowed_max_date=self.allowed_read_until,
                source=source,
                reason=f"Requested date {requested_date} > allowed max {self.allowed_read_until}",
                evaluation_mode=self.evaluation_mode,
            )
            return (False, violation)
        
        # Record read in trace
        trace_entry = f"{data_type}:{symbol}:{requested_date}:{source}"
        self.read_trace.append(trace_entry)
        
        return (True, None)
    
    def validate_read_request(
        self,
        request: BacktestReadRequest,
    ) -> tuple[bool, FutureDataViolation | None]:
        """Validate read request against cursor rules."""
        return self.request_read(
            symbol=request.symbol,
            requested_date=request.requested_date,
            data_type=request.data_type,
            source=request.source,
        )


class FutureDataAccessError(Exception):
    """
    Raised when strategy attempts to access future data.
    
    This is a blocking failure, not a degraded success.
    """
    
    def __init__(self, violation: FutureDataViolation):
        self.violation = violation
        super().__init__(
            f"Future data access blocked: requested {violation.requested_date}, "
            f"allowed max {violation.allowed_max_date}, source={violation.source}"
        )
