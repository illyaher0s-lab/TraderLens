"""OOS Evaluation Controller - B3/B4 prerequisite boundary enforcement."""
from __future__ import annotations

from backend.services.b3_protocol_types import (
    DataSnapshotManifest,
    PointInTimeMembershipSnapshot,
)
from contracts.strategy import (
    ResearchProtocolSnapshot,
    ForwardWatchlistSnapshot,
)


class OOSEvaluationController:
    """
    OOS evaluation controller with strict B3/B4 prerequisite boundary.
    
    Requirements:
    - B3 ResearchProtocolSnapshot (frozen, required)
    - B3 DataSnapshotManifest with data_snapshot_hash
    - B4 formal qualification result from run_qualification_with_b3_protocol()
    - Point-in-time universe (rejects ForwardWatchlist, static symbols)
    
    Rejects:
    - Missing B3 protocol
    - Fake protocol object (non-isinstance)
    - Missing data_snapshot_hash
    - B4 legacy qualification (string-only result)
    - B4 result with Gate/promotion/prototype_passed fields
    - ForwardWatchlistSnapshot
    - Static symbol list universe
    - Protocol manifest hash mismatch
    """
    
    def validate_b3_b4_prerequisites(
        self,
        protocol: ResearchProtocolSnapshot,
        manifest: DataSnapshotManifest,
        universe: PointInTimeMembershipSnapshot,
        b4_result: dict,
    ) -> dict:
        """
        Validate B3/B4 prerequisites before OOS evaluation.
        
        Args:
            protocol: B3 ResearchProtocolSnapshot (frozen, required)
            manifest: B3 DataSnapshotManifest with data_snapshot_hash
            universe: Point-in-time membership snapshot (required)
            b4_result: B4 formal qualification result dict
        
        Returns:
            dict with validated metadata:
            - protocol_snapshot_id
            - data_snapshot_hash
            - data_snapshot_id
            - universe_type
            - universe_snapshot_id
        
        Raises:
            ValueError: If any prerequisite validation fails
        """
        # 1. Validate B3 protocol snapshot
        self._validate_b3_protocol(protocol)
        
        # 2. Validate data snapshot manifest
        self._validate_data_snapshot_manifest(manifest)
        
        # 3. Validate universe specification
        self._validate_universe_spec(universe)
        
        # 4. Validate B4 formal qualification
        self._validate_b4_formal_qualification(b4_result)
        
        # 5. Validate hash consistency
        self._validate_hash_consistency(protocol, manifest)
        
        # 6. Record validated metadata
        return {
            "protocol_snapshot_id": protocol.protocol_snapshot_id,
            "data_snapshot_hash": protocol.data_snapshot_hash,
            "data_snapshot_id": protocol.data_snapshot_id,
            "universe_type": "point_in_time",
            "universe_snapshot_id": universe.snapshot_id,
        }
    
    def _validate_b3_protocol(self, protocol) -> None:
        """
        Validate B3 ResearchProtocolSnapshot.
        
        Raises:
            ValueError: If protocol missing or fake object
        """
        # Strict isinstance check (reject None and fake objects)
        if not isinstance(protocol, ResearchProtocolSnapshot):
            if protocol is None:
                raise ValueError("B3 ResearchProtocolSnapshot is required (got None)")
            raise ValueError(
                f"Invalid protocol object type: {type(protocol).__name__}. "
                f"Must be ResearchProtocolSnapshot (got fake object)."
            )
        
        # Verify frozen
        if not protocol.frozen:
            raise ValueError("B3 protocol must be frozen (frozen=True)")
    
    def _validate_data_snapshot_manifest(self, manifest) -> None:
        """
        Validate B3 DataSnapshotManifest.
        
        Raises:
            ValueError: If manifest missing or no data_snapshot_hash
        """
        # Strict isinstance check
        if not isinstance(manifest, DataSnapshotManifest):
            if manifest is None:
                raise ValueError("B3 DataSnapshotManifest is required (got None)")
            raise ValueError(
                f"Invalid manifest object type: {type(manifest).__name__}. "
                f"Must be DataSnapshotManifest (got fake object)."
            )
        
        # Verify data_snapshot_hash exists
        if not manifest.data_snapshot_hash or len(manifest.data_snapshot_hash.strip()) == 0:
            raise ValueError("DataSnapshotManifest must have non-empty data_snapshot_hash")
    
    def _validate_universe_spec(self, universe) -> None:
        """
        Validate universe specification.
        
        Only PointInTimeMembershipSnapshot is accepted.
        Rejects ForwardWatchlistSnapshot and static symbol lists.
        
        Raises:
            ValueError: If universe invalid for formal backtest
        """
        # Reject static symbol list
        if isinstance(universe, (list, tuple)):
            raise ValueError(
                "Static symbol list cannot be used in formal OOS backtest. "
                "Must use B3 PointInTimeMembershipSnapshot."
            )
        
        # Reject ForwardWatchlistSnapshot
        if isinstance(universe, ForwardWatchlistSnapshot):
            raise ValueError(
                "ForwardWatchlistSnapshot cannot be used in formal OOS backtest. "
                "Forward watchlist is prospective-only."
            )
        
        # Accept only PointInTimeMembershipSnapshot
        if not isinstance(universe, PointInTimeMembershipSnapshot):
            if universe is None:
                raise ValueError("B3 PointInTimeMembershipSnapshot is required (got None)")
            raise ValueError(
                f"Invalid universe specification type: {type(universe).__name__}. "
                f"Must be PointInTimeMembershipSnapshot (got fake object)."
            )
    
    def _validate_b4_formal_qualification(self, b4_result: dict) -> None:
        """
        Validate B4 formal qualification result.
        
        Must be from run_qualification_with_b3_protocol(), not legacy run_qualification().
        
        Raises:
            ValueError: If B4 result invalid or legacy format
        """
        # B4 result must be dict (formal path), not string (legacy path)
        if isinstance(b4_result, str):
            raise ValueError(
                "B4 legacy qualification result rejected. "
                "Must use run_qualification_with_b3_protocol() formal path."
            )
        
        # Verify required metadata fields from B4 formal path
        required_fields = [
            "result",
            "protocol_snapshot_id",
            "data_snapshot_hash",
            "data_snapshot_id",
            "universe_type",
            "universe_snapshot_id",
        ]
        
        for field in required_fields:
            if field not in b4_result:
                raise ValueError(
                    f"B4 formal qualification result missing required field: '{field}'. "
                    f"Must come from run_qualification_with_b3_protocol()."
                )
        
        # Verify B4 result does not contain Gate/promotion fields
        forbidden_fields = [
            "gate_verdict",
            "prototype_gate_result",
            "promotion_id",
            "prototype_passed",
        ]
        
        for field in forbidden_fields:
            if field in b4_result or field in b4_result.get("result", {}).__dict__:
                raise ValueError(
                    f"B4 result contains forbidden field: '{field}'. "
                    f"B4 must not create Gate or promotion."
                )
    
    def _validate_hash_consistency(
        self,
        protocol: ResearchProtocolSnapshot,
        manifest: DataSnapshotManifest,
    ) -> None:
        """
        Validate protocol manifest hash matches data snapshot hash.
        
        Raises:
            ValueError: If hashes don't match
        """
        expected = protocol.data_snapshot_hash
        actual = manifest.data_snapshot_hash
        
        if expected != actual:
            raise ValueError(
                f"Protocol manifest hash mismatch: "
                f"protocol expects '{expected}', "
                f"manifest has '{actual}'. "
                f"Cannot proceed with mismatched data snapshot."
            )
