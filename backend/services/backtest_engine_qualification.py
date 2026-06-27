"""B4 Backtest Engine Qualification - Run Canary suite before legal strategies."""
from __future__ import annotations

from datetime import date

from pydantic import ValidationError

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
from backend.services.b3_protocol_types import (
    DataSnapshotManifest,
    PointInTimeMembershipSnapshot,
)
from contracts.strategy import ResearchProtocolSnapshot, ForwardWatchlistSnapshot


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
    
    def _run_qualification_internal(
        self,
        protocol_snapshot_id: str,
        qualification_date: date,
    ) -> BacktestEngineQualificationResult:
        """
        Internal Canary qualification (Task 10 v3: private, use run_qualification_with_b3_protocol).
        
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
    
    def run_qualification(
        self,
        protocol_snapshot_id: str,
        qualification_date: date,
    ) -> BacktestEngineQualificationResult:
        """
        Legacy Canary qualification (Task 4 compatibility).
        
        WARNING: This is a legacy entrypoint for Task 4 tests only.
        For formal B4 backtest with B3 protocol, use run_qualification_with_b3_protocol().
        
        Returns:
            BacktestEngineQualificationResult
        """
        return self._run_qualification_internal(protocol_snapshot_id, qualification_date)
    
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
        # Task 10 v4: Enforce B3 protocol requirements with strict isinstance() checks

        # Strict type checking: reject None and fake objects
        if not isinstance(protocol, ResearchProtocolSnapshot):
            if protocol is None:
                raise ValueError("ResearchProtocolSnapshot is required (got None)")
            raise ValueError(
                f"Invalid protocol object type: {type(protocol).__name__}. "
                f"Must be ResearchProtocolSnapshot (got fake object)."
            )

        if not isinstance(manifest, DataSnapshotManifest):
            if manifest is None:
                raise ValueError("DataSnapshotManifest is required (got None)")
            raise ValueError(
                f"Invalid manifest object type: {type(manifest).__name__}. "
                f"Must be DataSnapshotManifest (got fake object)."
            )

        # Verify protocol frozen=True (ResearchProtocolSnapshot has explicit frozen field)
        if not protocol.frozen:
            raise ValueError("Protocol must be frozen (frozen=True)")

        # 1. Validate data_snapshot_hash match
        self._validate_data_snapshot_hash(protocol, manifest)

        # 2. Validate universe specification (strict type check inside)
        universe_info = self._validate_universe_spec(universe_spec)

        # 3. Run Canary qualification (internal only)
        qualification_result = self._run_qualification_internal(
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
        # Reject static symbol list
        if isinstance(universe_spec, (list, tuple)):
            raise ValueError(
                "Static symbol list cannot be used as historical universe. "
                "Must use point-in-time membership snapshot."
            )

        # Reject ForwardWatchlistSnapshot (strict type check)
        if isinstance(universe_spec, ForwardWatchlistSnapshot):
            raise ValueError(
                "ForwardWatchlistSnapshot cannot be used in historical backtest. "
                "Forward watchlist is prospective-only."
            )

        # Accept only PointInTimeMembershipSnapshot (strict type check)
        if isinstance(universe_spec, PointInTimeMembershipSnapshot):
            return {
                "universe_type": "point_in_time",
                "snapshot_id": universe_spec.snapshot_id,
                "as_of_date": universe_spec.snapshot_date,
            }

        if universe_spec is None:
            raise ValueError("PointInTimeMembershipSnapshot is required (got None)")

        raise ValueError(
            f"Invalid universe specification type: {type(universe_spec).__name__}. "
            f"Must be PointInTimeMembershipSnapshot (got fake object)."
        )
