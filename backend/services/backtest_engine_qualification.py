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
    
    def run_qualification_with_b3_protocol(
        self,
        protocol,  # ResearchProtocolSnapshot
        manifest,  # DataSnapshotManifest
        universe_spec,  # PointInTimeMembershipSnapshot
        qualification_date: date,
    ) -> dict:
        """
        Run B4 qualification with B3 frozen protocol (Task 10 integration boundary).
        
        This is the official B4 entrypoint that enforces B3 protocol requirements:
        - Validates data_snapshot_hash match (hard reject on mismatch)
        - Validates universe specification (rejects forward watchlist / static list)
        - Records B3 protocol_snapshot_id and data_snapshot_hash in result
        
        Args:
            protocol: B3 ResearchProtocolSnapshot (frozen, required)
            manifest: B3 DataSnapshotManifest (frozen, required)
            universe_spec: B3 PointInTimeMembershipSnapshot (frozen, required)
            qualification_date: Date to run qualification
        
        Returns:
            dict with:
            - result: BacktestEngineQualificationResult
            - protocol_snapshot_id: str
            - data_snapshot_hash: str
            - data_snapshot_id: str
            - universe_type: str
            - universe_snapshot_id: str
        
        Raises:
            ValueError: If protocol/manifest/universe validation fails
        """
        # Task 10: Enforce B3 protocol requirements (cannot bypass)
        
        # 1. Validate data_snapshot_hash match
        self._validate_data_snapshot_hash(protocol, manifest)
        
        # 2. Validate universe specification
        universe_info = self._validate_universe_spec(universe_spec)
        
        # 3. Run Canary qualification
        qualification_result = self.run_qualification(
            protocol_snapshot_id=protocol.protocol_snapshot_id,
            qualification_date=qualification_date,
        )
        
        # 4. Return enhanced result with B3 metadata
        return {
            "result": qualification_result,
            "protocol_snapshot_id": protocol.protocol_snapshot_id,
            "data_snapshot_hash": protocol.data_snapshot_hash,
            "data_snapshot_id": protocol.data_snapshot_id,
            "universe_type": universe_info["universe_type"],
            "universe_snapshot_id": universe_info["snapshot_id"],
            "universe_as_of_date": universe_info["as_of_date"],
        }
    
    def _validate_data_snapshot_hash(
        self,
        protocol,  # ResearchProtocolSnapshot
        manifest,  # DataSnapshotManifest
    ) -> None:
        """
        Validate data_snapshot_hash match (Task 10).
        
        Raises:
            ValueError: If hashes don't match (hard reject)
        """
        expected = protocol.data_snapshot_hash
        actual = manifest.data_snapshot_hash
        
        if expected != actual:
            raise ValueError(
                f"Data snapshot hash mismatch: "
                f"protocol expects '{expected}', "
                f"manifest has '{actual}'. "
                f"Cannot proceed with mismatched data snapshot."
            )
    
    def _validate_universe_spec(
        self,
        universe_spec,
    ) -> dict:
        """
        Validate universe specification (Task 10).
        
        Raises:
            ValueError: If universe invalid for historical backtest
        """
        # Reject ForwardWatchlistSnapshot
        if hasattr(universe_spec, 'forward_only') and universe_spec.forward_only:
            raise ValueError(
                "ForwardWatchlistSnapshot cannot be used in historical backtest. "
                "Forward watchlist is prospective-only."
            )
        
        # Reject static symbol list
        if isinstance(universe_spec, (list, tuple)):
            raise ValueError(
                "Static symbol list cannot be used as historical universe. "
                "Must use point-in-time membership snapshot."
            )
        
        # Accept PointInTimeMembershipSnapshot
        if hasattr(universe_spec, 'snapshot_date') and hasattr(universe_spec, 'snapshot_id'):
            return {
                "universe_type": "point_in_time",
                "snapshot_id": universe_spec.snapshot_id,
                "as_of_date": universe_spec.snapshot_date,
            }
        
        raise ValueError(f"Unknown universe specification type: {type(universe_spec)}")
