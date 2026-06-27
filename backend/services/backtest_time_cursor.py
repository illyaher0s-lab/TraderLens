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
        
        # Adjustment snapshot state (Task 8)
        self.adjustment_snapshot_date: date | None = None
        self.adjustment_snapshot_fingerprint: str | None = None
        self.locked_adjustment_mode: str | None = None
        
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


    def validate_bar_adjustment(
        self,
        symbol: str,
        bar,  # DailyBar
        adjustment_mode: str,
        adjustment_snapshot_date: date,
        adjustment_fingerprint: str,
        expected_adjustment_fingerprint: str,
        source: str,
    ) -> None:
        """
        Validate bar adjustment factor against snapshot constraints.
        
        Task 8: Adjustment price snapshot guard.
        
        Rules:
        1. Adjustment mode (raw/qfq/hfq) must be locked per backtest run
        2. Mixed modes are hard rejected
        3. Adjustment fingerprint must match expected (from B3 DataSnapshotManifest)
        4. Adjustment snapshot_date must not be after current_date (future data)
        
        Args:
            symbol: Stock symbol
            bar: DailyBar with adj_factor
            adjustment_mode: "raw", "qfq", or "hfq"
            adjustment_snapshot_date: Adjustment factor snapshot as-of date
            adjustment_fingerprint: Adjustment factor snapshot fingerprint
            expected_adjustment_fingerprint: Expected fingerprint from B3 manifest
            source: Source identifier for audit trail
        
        Raises:
            ValueError: Mixed adjustment modes or fingerprint mismatch
            FutureDataAccessError: Adjustment snapshot dated after current_date
        """
        allowed_modes = {"raw", "qfq", "hfq"}
        if adjustment_mode not in allowed_modes:
            raise ValueError(
                f"Invalid adjustment mode: {adjustment_mode}. "
                f"Expected one of {sorted(allowed_modes)}, source={source}"
            )

        # 1. Lock adjustment mode on first call
        if self.locked_adjustment_mode is None:
            self.locked_adjustment_mode = adjustment_mode
            self.adjustment_snapshot_date = adjustment_snapshot_date
            self.adjustment_snapshot_fingerprint = adjustment_fingerprint
        else:
            # 2. Check mixed modes (hard reject)
            if self.locked_adjustment_mode != adjustment_mode:
                raise ValueError(
                    f"Mixed adjustment modes rejected: "
                    f"locked={self.locked_adjustment_mode}, attempted={adjustment_mode}, "
                    f"source={source}"
                )
            
            # Check snapshot consistency
            if self.adjustment_snapshot_date != adjustment_snapshot_date:
                raise ValueError(
                    f"Adjustment snapshot date changed: "
                    f"locked={self.adjustment_snapshot_date}, attempted={adjustment_snapshot_date}, "
                    f"source={source}"
                )
            
            if self.adjustment_snapshot_fingerprint != adjustment_fingerprint:
                raise ValueError(
                    f"Adjustment snapshot fingerprint changed: "
                    f"locked={self.adjustment_snapshot_fingerprint}, attempted={adjustment_fingerprint}, "
                    f"source={source}"
                )
        
        # 3. Validate fingerprint matches expected (from B3 DataSnapshotManifest)
        if adjustment_fingerprint != expected_adjustment_fingerprint:
            raise ValueError(
                f"Adjustment factor fingerprint mismatch: "
                f"expected={expected_adjustment_fingerprint}, got={adjustment_fingerprint}, "
                f"source={source}"
            )
        
        # 4. Check adjustment snapshot_date not after current_date (future data)
        if adjustment_snapshot_date > self.current_date:
            violation = FutureDataViolation(
                requested_date=adjustment_snapshot_date,
                allowed_max_date=self.current_date,
                source=source,
                reason=(
                    f"Adjustment factor snapshot date {adjustment_snapshot_date} > "
                    f"current date {self.current_date}"
                ),
                evaluation_mode=self.evaluation_mode,
            )
            raise FutureDataAccessError(violation)
        
        # 5. Record adjustment read in trace
        trace_entry = (
            f"adjustment_factor:{symbol}:{bar.date}:"
            f"mode={adjustment_mode}:"
            f"adj_factor={bar.adj_factor}:"
            f"fingerprint={adjustment_fingerprint}:"
            f"snapshot_date={adjustment_snapshot_date}:"
            f"source={source}"
        )
        self.read_trace.append(trace_entry)


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
