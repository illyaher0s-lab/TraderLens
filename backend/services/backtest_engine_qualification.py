"""B4 Backtest Engine Qualification - Run Canary suite before legal strategies."""
from __future__ import annotations

from datetime import date

from backend.services.backtest_time_cursor import BacktestTimeCursor
from backend.services.future_data_guard import FutureDataGuard
from backend.services.canary_strategies import (
    FutureBarCanary,
    FutureStatusCanary,
    FutureFinancialCanary,
    FutureMembershipCanary,
    FullSampleNormalizationCanary,
    FutureAdjustmentFactorCanary,
)
from backend.services.b4_protocol_types import (
    BacktestEngineQualificationResult,
    CanaryCaseResult,
)


class BacktestEngineQualification:
    """
    Backtest engine qualification via Canary suite.
    
    All Canary cases must be blocked before legal strategies can run.
    Any Canary completing normally = qualification failed.
    """
    
    CANARY_SUITE = [
        FutureBarCanary,
        FutureStatusCanary,
        FutureFinancialCanary,
        FutureMembershipCanary,
        FullSampleNormalizationCanary,
        FutureAdjustmentFactorCanary,
    ]
    
    def run_qualification(
        self,
        protocol_snapshot_id: str,
        qualification_date: date,
    ) -> BacktestEngineQualificationResult:
        """
        Run Canary qualification suite.
        
        Returns:
            BacktestEngineQualificationResult with qualification_status='pass' if all blocked
        """
        # Create cursor for Canary run
        cursor = BacktestTimeCursor(
            cursor_id=f"canary_{protocol_snapshot_id}",
            current_date=qualification_date,
            evaluation_mode="signal_phase",
        )
        
        guard = FutureDataGuard(cursor)
        
        # Run all Canary cases
        canary_results: list[CanaryCaseResult] = []
        
        for canary_class in self.CANARY_SUITE:
            canary = canary_class()
            result = canary.run(cursor, guard)
            canary_results.append(result)
        
        # Check qualification status
        # All must be "blocked" to pass
        all_blocked = all(r.outcome == "blocked" for r in canary_results)
        
        qualification_status = "pass" if all_blocked else "fail"
        
        return BacktestEngineQualificationResult(
            qualification_id=f"qual_{protocol_snapshot_id}",
            protocol_snapshot_id=protocol_snapshot_id,
            canary_cases=tuple(canary_results),
            qualification_status=qualification_status,
            qualified_at=qualification_date,
        )
