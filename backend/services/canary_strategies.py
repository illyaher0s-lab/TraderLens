"""B4 Canary Strategies - Intentional future access attempts for qualification."""
from __future__ import annotations

from datetime import date, timedelta

from backend.services.backtest_time_cursor import (
    BacktestTimeCursor,
    FutureDataAccessError,
)
from backend.services.future_data_guard import FutureDataGuard
from backend.services.b4_protocol_types import (
    CanaryCaseResult,
    FutureDataViolation,
)


class CanaryStrategy:
    """
    Base Canary strategy.
    
    Intentionally attempts future data access.
    Correct result: blocked by guard.
    """
    
    def __init__(
        self,
        case_id: str,
        case_name: str,
        attempted_violation: str,
    ):
        self.case_id = case_id
        self.case_name = case_name
        self.attempted_violation = attempted_violation
        self.violations: list[FutureDataViolation] = []
    
    def run(
        self,
        cursor: BacktestTimeCursor,
        guard: FutureDataGuard,
    ) -> CanaryCaseResult:
        """
        Run Canary case.
        
        Returns:
            CanaryCaseResult with outcome='blocked' (correct) or 'completed' (wrong)
        """
        raise NotImplementedError


class FutureBarCanary(CanaryStrategy):
    """Canary: attempt to read future bar."""
    
    def __init__(self):
        super().__init__(
            case_id="canary_future_bar",
            case_name="Future Bar Access",
            attempted_violation="future_bar",
        )
    
    def run(
        self,
        cursor: BacktestTimeCursor,
        guard: FutureDataGuard,
    ) -> CanaryCaseResult:
        """Attempt to read T+1 bar during signal phase."""
        future_date = cursor.current_date + timedelta(days=1)
        
        try:
            guard.check_bar_access(
                symbol="000001.SZ",
                requested_date=future_date,
                source="canary_future_bar",
            )
            # If we get here, guard failed to block
            return CanaryCaseResult(
                case_id=self.case_id,
                case_name=self.case_name,
                attempted_violation=self.attempted_violation,
                outcome="completed",  # Wrong
                violation_count=0,
                violations=(),
            )
        except FutureDataAccessError as e:
            # Correct: blocked
            return CanaryCaseResult(
                case_id=self.case_id,
                case_name=self.case_name,
                attempted_violation=self.attempted_violation,
                outcome="blocked",  # Correct
                violation_count=1,
                violations=(e.violation,),
            )


class FutureStatusCanary(CanaryStrategy):
    """Canary: attempt to read future daily status."""
    
    def __init__(self):
        super().__init__(
            case_id="canary_future_status",
            case_name="Future Daily Status Access",
            attempted_violation="future_status",
        )
    
    def run(
        self,
        cursor: BacktestTimeCursor,
        guard: FutureDataGuard,
    ) -> CanaryCaseResult:
        future_date = cursor.current_date + timedelta(days=1)
        
        try:
            guard.check_daily_status_access(
                symbol="000001.SZ",
                requested_date=future_date,
                source="canary_future_status",
            )
            return CanaryCaseResult(
                case_id=self.case_id,
                case_name=self.case_name,
                attempted_violation=self.attempted_violation,
                outcome="completed",
                violation_count=0,
                violations=(),
            )
        except FutureDataAccessError as e:
            return CanaryCaseResult(
                case_id=self.case_id,
                case_name=self.case_name,
                attempted_violation=self.attempted_violation,
                outcome="blocked",
                violation_count=1,
                violations=(e.violation,),
            )


class FutureFinancialCanary(CanaryStrategy):
    """Canary: attempt to read financial with future ann_date."""
    
    def __init__(self):
        super().__init__(
            case_id="canary_future_financial",
            case_name="Future Financial ann_date Access",
            attempted_violation="future_financial_ann_date",
        )
    
    def run(
        self,
        cursor: BacktestTimeCursor,
        guard: FutureDataGuard,
    ) -> CanaryCaseResult:
        future_date = cursor.current_date + timedelta(days=1)
        
        try:
            guard.check_financial_access(
                symbol="000001.SZ",
                ann_date=future_date,
                source="canary_future_financial",
            )
            return CanaryCaseResult(
                case_id=self.case_id,
                case_name=self.case_name,
                attempted_violation=self.attempted_violation,
                outcome="completed",
                violation_count=0,
                violations=(),
            )
        except FutureDataAccessError as e:
            return CanaryCaseResult(
                case_id=self.case_id,
                case_name=self.case_name,
                attempted_violation=self.attempted_violation,
                outcome="blocked",
                violation_count=1,
                violations=(e.violation,),
            )


class FutureMembershipCanary(CanaryStrategy):
    """Canary: attempt to read future universe membership."""
    
    def __init__(self):
        super().__init__(
            case_id="canary_future_membership",
            case_name="Future Universe Membership Access",
            attempted_violation="future_membership",
        )
    
    def run(
        self,
        cursor: BacktestTimeCursor,
        guard: FutureDataGuard,
    ) -> CanaryCaseResult:
        future_date = cursor.current_date + timedelta(days=1)
        
        try:
            guard.check_membership_access(
                symbol="000001.SZ",
                membership_date=future_date,
                source="canary_future_membership",
            )
            return CanaryCaseResult(
                case_id=self.case_id,
                case_name=self.case_name,
                attempted_violation=self.attempted_violation,
                outcome="completed",
                violation_count=0,
                violations=(),
            )
        except FutureDataAccessError as e:
            return CanaryCaseResult(
                case_id=self.case_id,
                case_name=self.case_name,
                attempted_violation=self.attempted_violation,
                outcome="blocked",
                violation_count=1,
                violations=(e.violation,),
            )


class FullSampleNormalizationCanary(CanaryStrategy):
    """Canary: attempt full-sample normalization (uses future data)."""
    
    def __init__(self):
        super().__init__(
            case_id="canary_full_sample_norm",
            case_name="Full Sample Normalization",
            attempted_violation="full_sample_normalization",
        )
    
    def run(
        self,
        cursor: BacktestTimeCursor,
        guard: FutureDataGuard,
    ) -> CanaryCaseResult:
        try:
            guard.block_full_sample_stats(
                operation="normalization",
                source="canary_full_sample_norm",
            )
            return CanaryCaseResult(
                case_id=self.case_id,
                case_name=self.case_name,
                attempted_violation=self.attempted_violation,
                outcome="completed",
                violation_count=0,
                violations=(),
            )
        except FutureDataAccessError as e:
            return CanaryCaseResult(
                case_id=self.case_id,
                case_name=self.case_name,
                attempted_violation=self.attempted_violation,
                outcome="blocked",
                violation_count=1,
                violations=(e.violation,),
            )


class FutureAdjustmentFactorCanary(CanaryStrategy):
    """Canary: attempt to read future adjustment factor."""
    
    def __init__(self):
        super().__init__(
            case_id="canary_future_adj_factor",
            case_name="Future Adjustment Factor Access",
            attempted_violation="future_adjustment_factor",
        )
    
    def run(
        self,
        cursor: BacktestTimeCursor,
        guard: FutureDataGuard,
    ) -> CanaryCaseResult:
        future_date = cursor.current_date + timedelta(days=1)
        
        try:
            guard.check_adjustment_factor_access(
                symbol="000001.SZ",
                factor_date=future_date,
                source="canary_future_adj_factor",
            )
            return CanaryCaseResult(
                case_id=self.case_id,
                case_name=self.case_name,
                attempted_violation=self.attempted_violation,
                outcome="completed",
                violation_count=0,
                violations=(),
            )
        except FutureDataAccessError as e:
            return CanaryCaseResult(
                case_id=self.case_id,
                case_name=self.case_name,
                attempted_violation=self.attempted_violation,
                outcome="blocked",
                violation_count=1,
                violations=(e.violation,),
            )
