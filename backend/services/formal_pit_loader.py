"""Formal PIT Membership Snapshot Loader - Task 3A.

Load verified formal snapshots and project PIT members.
Only reads verified _005+ artifacts, never source partitions.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

import pyarrow.parquet as pq

from backend.services.b3_protocol_types import (
    MembershipCoverageUnavailable,
    PointInTimeMembershipSnapshot,
    UniverseMembershipRecord,
)


class FormalSnapshotLoader:
    """Load formal PIT membership snapshot from verified artifact."""
    
    def __init__(self, repo_root: Path):
        self.repo_root = Path(repo_root)
        self.snapshots_root = self.repo_root / "data/pit/pit_membership_snapshots"
        self.verifier_script = self.repo_root / "scripts/verify_pit_membership_snapshot.py"
    
    def _verify_artifact_only(self, snapshot_id: str, snapshot_dir: Path) -> tuple[bool, str]:
        """
        Lightweight artifact-only verification for runtime loading.
        
        Checks:
        - Legacy rejection (_001-_004)
        - Manifest/records sidecar integrity
        - Required fields present
        
        Does NOT:
        - Re-audit source partitions (publisher/prepublication responsibility)
        - Re-verify source-to-record mapping (frozen at publication)
        
        Returns:
            (is_verified, error_message)
        """
        # 1. Check legacy rejection
        LEGACY_REJECTED = {
            "pims_traderlens_v2_shsz_sw2021_pit_001": "retired_unaccepted",
            "pims_traderlens_v2_shsz_sw2021_pit_002": "unaccepted_invalid_publication",
            "pims_traderlens_v2_shsz_sw2021_pit_003": "unaccepted_invalid_publication",
            "pims_traderlens_v2_shsz_sw2021_pit_004": "unaccepted_invalid_publication",
        }
        
        if snapshot_id in LEGACY_REJECTED:
            return (False, f"Snapshot {snapshot_id} is {LEGACY_REJECTED[snapshot_id]}")
        
        # 2. All immutable artifact files and sidecars are required at runtime.
        manifest_path = snapshot_dir / "manifest.json"
        records_path = snapshot_dir / "records.parquet"
        manifest_sidecar = snapshot_dir / "manifest.json.sha256"
        records_sidecar = snapshot_dir / "records.parquet.sha256"
        for path in (manifest_path, records_path, manifest_sidecar, records_sidecar):
            if not path.exists():
                return (False, f"Required artifact file missing: {path.name}")
        
        # 3. Load manifest
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as e:
            return (False, f"Manifest parse error: {e}")
        
        # 4. Check required fields and requested identity.
        required = [
            "snapshot_id",
            "snapshot_date",
            "universe_rule_type",
            "membership_source",
            "include_delisted",
            "frozen",
            "quality_status",
            "gaps",
            "formal_data_snapshot_id",
            "formal_data_semantic_hash",
            "canonical_content_hash",
            "records_parquet_sha256",
            "source_to_record_mapping_hash",
        ]
        
        for field in required:
            if field not in manifest:
                return (False, f"Missing required field: {field}")
        if manifest["snapshot_id"] != snapshot_id:
            return (False, "Manifest snapshot_id does not match requested snapshot")
        if manifest["frozen"] is not True:
            return (False, "Formal snapshot must be frozen")

        # 5. Verify sidecars, manifest binding, and canonical content without source reads.
        expected_manifest_hash = manifest_sidecar.read_text(encoding="utf-8").strip().split()[0]
        actual_manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        if actual_manifest_hash != expected_manifest_hash:
            return (False, f"Manifest hash mismatch: {actual_manifest_hash} != {expected_manifest_hash}")

        expected_records_hash = records_sidecar.read_text(encoding="utf-8").strip().split()[0]
        actual_records_hash = hashlib.sha256(records_path.read_bytes()).hexdigest()
        if actual_records_hash != expected_records_hash:
            return (False, f"Records hash mismatch: {actual_records_hash} != {expected_records_hash}")
        if actual_records_hash != manifest["records_parquet_sha256"]:
            return (False, "Records hash does not match manifest")

        canonical_payload = {
            key: value for key, value in manifest.items()
            if key not in {"canonical_content_hash", "manifest_published_at"}
        }
        canonical_hash = hashlib.sha256(
            json.dumps(canonical_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        if canonical_hash != manifest["canonical_content_hash"]:
            return (False, "Canonical content hash mismatch")

        formal_data_path = (
            self.repo_root / "data/pit/data_snapshot_manifests" /
            manifest["formal_data_snapshot_id"] / "manifest.json"
        )
        if not formal_data_path.exists():
            return (False, "Bound formal data manifest not found")
        formal_data = json.loads(formal_data_path.read_text(encoding="utf-8"))
        if formal_data.get("snapshot_id") != manifest["formal_data_snapshot_id"]:
            return (False, "Formal data snapshot ID binding mismatch")
        if formal_data.get("semantic_hash") != manifest["formal_data_semantic_hash"]:
            return (False, "Formal data semantic hash binding mismatch")
        
        return (True, "")
    
    def load_snapshot(
        self,
        snapshot_id: str,
        expected_formal_data_snapshot_id: str | None = None,
        expected_formal_data_semantic_hash: str | None = None,
    ) -> PointInTimeMembershipSnapshot:
        """
        Load verified formal snapshot.
        
        Args:
            snapshot_id: Formal snapshot ID (e.g., pims_traderlens_v2_shsz_sw2021_pit_005)
            expected_formal_data_snapshot_id: Optional binding check
            expected_formal_data_semantic_hash: Optional semantic hash check
        
        Returns:
            PointInTimeMembershipSnapshot with records from artifact
        
        Raises:
            ValueError: If snapshot not verified, binding mismatch, or not found
        """
        snapshot_dir = self.snapshots_root / snapshot_id
        
        # 1. Check existence
        if not snapshot_dir.exists():
            raise ValueError(f"Snapshot not found: {snapshot_id}")
        
        # 2. Lightweight artifact-only verification (no source re-audit)
        is_verified, error = self._verify_artifact_only(snapshot_id, snapshot_dir)
        if not is_verified:
            raise ValueError(f"Snapshot {snapshot_id} verification failed: {error}")
        
        # 3. Load manifest
        manifest_path = snapshot_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        
        # 4. Check binding if provided
        if expected_formal_data_snapshot_id is not None:
            actual_id = manifest.get("formal_data_snapshot_id")
            if actual_id != expected_formal_data_snapshot_id:
                raise ValueError(
                    f"Formal data snapshot ID mismatch: expected {expected_formal_data_snapshot_id}, "
                    f"got {actual_id}"
                )
        
        if expected_formal_data_semantic_hash is not None:
            actual_hash = manifest.get("formal_data_semantic_hash")
            if actual_hash != expected_formal_data_semantic_hash:
                raise ValueError(
                    f"Formal data semantic hash mismatch: expected {expected_formal_data_semantic_hash}, "
                    f"got {actual_hash}"
                )
        
        # 5. Load records from parquet (not source partitions)
        records_path = snapshot_dir / "records.parquet"
        table = pq.read_table(records_path)
        records_df = table.to_pandas()
        
        # 6. Convert to UniverseMembershipRecord
        records = []
        for _, row in records_df.iterrows():
            # Parse dates (already date objects from parquet)
            effective_from = row["effective_from"]
            effective_to = row.get("effective_to")
            
            # Handle None/NaT for effective_to
            if effective_to is None or (hasattr(effective_to, '__class__') and effective_to.__class__.__name__ == 'NaTType'):
                effective_to = None
            
            records.append(
                UniverseMembershipRecord(
                    symbol=row["symbol"],
                    effective_from=effective_from,
                    effective_to=effective_to,
                    source=row["source"],
                    snapshot_id=snapshot_id,
                )
            )
        
        # 7. Build PointInTimeMembershipSnapshot
        snapshot_date_str = manifest["snapshot_date"]
        if isinstance(snapshot_date_str, str):
            parts = snapshot_date_str.split("-")
            snapshot_date = date(int(parts[0]), int(parts[1]), int(parts[2]))
        else:
            snapshot_date = snapshot_date_str
        
        return PointInTimeMembershipSnapshot(
            snapshot_id=snapshot_id,
            snapshot_date=snapshot_date,
            universe_rule_type="point_in_time_membership",
            membership_source=manifest.get("membership_source", "tushare_index_member_all_sw2021"),
            include_delisted=manifest["include_delisted"],
            records=tuple(records),
            quality_status=manifest.get("quality_status", "ok"),
            gaps=tuple(manifest.get("gaps", [])),
        )


class FormalMembershipSource:
    """PIT membership source from formal snapshot."""
    
    def __init__(self, snapshot: PointInTimeMembershipSnapshot):
        self.snapshot = snapshot
        self.snapshot_date = snapshot.snapshot_date
        self._records = snapshot.records
        self.formal_snapshot_id = snapshot.snapshot_id
        self.formal_membership_source = snapshot.membership_source
    
    def records_for_universe(
        self,
        universe: any,  # BacktestUniverseSpec
        backtest_start: date,
        backtest_end: date,
    ) -> tuple[UniverseMembershipRecord, ...]:
        """
        Get records with closed-interval overlap with backtest window.
        
        Returns records where effective window has ANY overlap with [backtest_start, backtest_end].
        Preserves effective_from/effective_to — does NOT collapse to current constituents.
        
        Args:
            universe: Universe spec (not used for formal source)
            backtest_start: Backtest window start
            backtest_end: Backtest window end
        
        Returns:
            Records with effective window overlapping backtest window
        
        Raises:
            ValueError: If backtest_end > snapshot_date (no extrapolation)
        """
        # No extrapolation beyond snapshot_date
        if backtest_end > self.snapshot_date:
            raise MembershipCoverageUnavailable(
                f"Cannot extrapolate beyond snapshot_date {self.snapshot_date}, "
                f"requested backtest_end {backtest_end}"
            )
        
        # Filter records with closed-interval overlap
        # Overlap: (effective_from <= backtest_end) AND (effective_to is None OR effective_to >= backtest_start)
        overlapping = []
        for record in self._records:
            # effective_from > backtest_end → no overlap
            if record.effective_from > backtest_end:
                continue
            
            # effective_to < backtest_start → no overlap
            if record.effective_to is not None and record.effective_to < backtest_start:
                continue
            
            overlapping.append(record)
        
        return tuple(overlapping)
    
    def get_members_at_date(self, as_of_date: date) -> tuple[UniverseMembershipRecord, ...]:
        """
        Get PIT members at a specific date.
        
        Semantics: effective_from <= as_of_date AND (effective_to IS NULL OR as_of_date <= effective_to)
        
        Args:
            as_of_date: Target date for projection
        
        Returns:
            Tuple of records valid at as_of_date, sorted by symbol
        
        Raises:
            ValueError: If as_of_date > snapshot_date (no extrapolation)
        """
        # No extrapolation beyond snapshot_date
        if as_of_date > self.snapshot_date:
            raise ValueError(
                f"Cannot project beyond snapshot_date {self.snapshot_date}, "
                f"requested {as_of_date}"
            )
        
        # Filter records: closed interval semantics
        valid = []
        for record in self._records:
            # effective_from <= as_of_date
            if record.effective_from > as_of_date:
                continue
            
            # as_of_date <= effective_to (or effective_to is None)
            if record.effective_to is not None and as_of_date > record.effective_to:
                continue
            
            valid.append(record)
        
        # Deterministic order: sort by symbol
        valid_sorted = sorted(valid, key=lambda r: r.symbol)
        
        return tuple(valid_sorted)
    
    def get_snapshot(self, as_of_date: date) -> PointInTimeMembershipSnapshot:
        """
        Get PointInTimeMembershipSnapshot at a specific date.
        
        Compatible with InMemoryMembershipSource interface.
        """
        members = self.get_members_at_date(as_of_date)
        
        return PointInTimeMembershipSnapshot(
            snapshot_id=self.snapshot.snapshot_id,
            snapshot_date=as_of_date,
            universe_rule_type="point_in_time_membership",
            membership_source=self.snapshot.membership_source,
            include_delisted=self.snapshot.include_delisted,
            records=members,
            quality_status=self.snapshot.quality_status,
            gaps=self.snapshot.gaps,
        )
