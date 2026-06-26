"""B3 Data Snapshot Manifest - Deterministic hash for reproducible data snapshots."""
from __future__ import annotations

import hashlib
import json
from datetime import date

from backend.services.b3_protocol_types import DataSnapshotManifest


class DataSnapshotManifestBuilder:
    """
    Build data snapshot manifests with deterministic hashes.
    
    Hash covers semantic data only (market data, status, membership, financial visibility).
    Runtime metadata (created_at, generated_by, notes) excluded from hash.
    """
    
    def build(
        self,
        data_snapshot_id: str,
        market_data_fingerprint: str,
        daily_status_fingerprint: str,
        membership_fingerprint: str,
        quality_status: str = "ok",
        gaps: tuple[str, ...] = (),
        trading_calendar_fingerprint: str = "",
        delisted_coverage_policy: str = "",
        financial_visibility_fingerprint: str = "",
        benchmark_fingerprint: str = "",
        adjustment_factor_fingerprint: str = "",
        provider_fingerprints: tuple[str, ...] = (),
        generated_by: str = "",
    ) -> DataSnapshotManifest:
        """
        Build manifest with computed hash.
        
        Args:
            data_snapshot_id: Unique snapshot identifier
            market_data_fingerprint: Hash of market data (OHLCV bars)
            daily_status_fingerprint: Hash of daily status (ST, suspension, limit)
            membership_fingerprint: Hash of point-in-time universe membership
            quality_status: ok | insufficient
            gaps: Detected data gaps
            trading_calendar_fingerprint: Hash of trading calendar
            delisted_coverage_policy: Policy for delisted coverage
            financial_visibility_fingerprint: Hash of financial ann_date visibility
            benchmark_fingerprint: Hash of benchmark data
            adjustment_factor_fingerprint: Hash of adjustment factors
            provider_fingerprints: Tuple of data provider fingerprints
            generated_by: Runtime metadata (excluded from hash)
        
        Returns:
            DataSnapshotManifest with computed hash
        """
        # Build manifest without hash first (for hash computation)
        manifest_dict = {
            "data_snapshot_id": data_snapshot_id,
            "market_data_fingerprint": market_data_fingerprint,
            "daily_status_fingerprint": daily_status_fingerprint,
            "membership_fingerprint": membership_fingerprint,
            "trading_calendar_fingerprint": trading_calendar_fingerprint,
            "delisted_coverage_policy": delisted_coverage_policy,
            "financial_visibility_fingerprint": financial_visibility_fingerprint,
            "benchmark_fingerprint": benchmark_fingerprint,
            "adjustment_factor_fingerprint": adjustment_factor_fingerprint,
            "provider_fingerprints": provider_fingerprints,
            "quality_status": quality_status,
            "gaps": gaps,
        }
        
        # Compute hash
        computed_hash = self._compute_hash_from_dict(manifest_dict)
        
        # Build final manifest with real hash
        return DataSnapshotManifest(
            data_snapshot_id=data_snapshot_id,
            data_snapshot_hash=computed_hash,
            created_at=date.today(),
            market_data_fingerprint=market_data_fingerprint,
            daily_status_fingerprint=daily_status_fingerprint,
            membership_fingerprint=membership_fingerprint,
            trading_calendar_fingerprint=trading_calendar_fingerprint,
            delisted_coverage_policy=delisted_coverage_policy,
            financial_visibility_fingerprint=financial_visibility_fingerprint,
            benchmark_fingerprint=benchmark_fingerprint,
            adjustment_factor_fingerprint=adjustment_factor_fingerprint,
            provider_fingerprints=provider_fingerprints,
            quality_status=quality_status,
            gaps=gaps,
            generated_by=generated_by,
        )
    
    def compute_hash(self, manifest: DataSnapshotManifest) -> str:
        """
        Compute deterministic hash from existing manifest.
        
        Excludes runtime metadata (created_at, generated_by).
        """
        manifest_dict = {
            "data_snapshot_id": manifest.data_snapshot_id,
            "market_data_fingerprint": manifest.market_data_fingerprint,
            "daily_status_fingerprint": manifest.daily_status_fingerprint,
            "membership_fingerprint": manifest.membership_fingerprint,
            "trading_calendar_fingerprint": manifest.trading_calendar_fingerprint,
            "delisted_coverage_policy": manifest.delisted_coverage_policy,
            "financial_visibility_fingerprint": manifest.financial_visibility_fingerprint,
            "benchmark_fingerprint": manifest.benchmark_fingerprint,
            "adjustment_factor_fingerprint": manifest.adjustment_factor_fingerprint,
            "provider_fingerprints": manifest.provider_fingerprints,
            "quality_status": manifest.quality_status,
            "gaps": manifest.gaps,
        }
        
        return self._compute_hash_from_dict(manifest_dict)
    
    def _compute_hash_from_dict(self, data: dict) -> str:
        """
        Compute SHA256 hash from dict.
        
        Excludes:
        - created_at
        - generated_by
        - data_snapshot_hash (placeholder)
        - UI notes
        - runtime duration
        """
        # Extract semantic fields only (in sorted order for stability)
        semantic_data = {
            "adjustment_factor_fingerprint": data.get("adjustment_factor_fingerprint", ""),
            "benchmark_fingerprint": data.get("benchmark_fingerprint", ""),
            "daily_status_fingerprint": data.get("daily_status_fingerprint", ""),
            "delisted_coverage_policy": data.get("delisted_coverage_policy", ""),
            "financial_visibility_fingerprint": data.get("financial_visibility_fingerprint", ""),
            "gaps": data.get("gaps", ()),
            "market_data_fingerprint": data.get("market_data_fingerprint", ""),
            "membership_fingerprint": data.get("membership_fingerprint", ""),
            "provider_fingerprints": data.get("provider_fingerprints", ()),
            "quality_status": data.get("quality_status", ""),
            "trading_calendar_fingerprint": data.get("trading_calendar_fingerprint", ""),
        }
        
        # Serialize to JSON (keys already sorted in dict literal above)
        serialized = json.dumps(semantic_data, sort_keys=True, ensure_ascii=False)
        
        # Hash
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
