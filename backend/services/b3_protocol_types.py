"""B3 Protocol Types - Point-in-time data contracts and frozen snapshots."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class MembershipCoverageUnavailable(ValueError):
    """A formally bounded membership source cannot cover the requested window."""


class FutureMembershipLeakError(ValueError):
    """A single-observation membership source would backfill historical data."""


class UniverseMembershipRecord(BaseModel):
    """
    Point-in-time membership record for a symbol.

    Records when a symbol was valid for strategy universe selection.
    effective_from/to must reflect historical reality, not current state.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str
    effective_from: date
    effective_to: date | None  # None = still effective
    source: str  # "index_constituent", "sector_member", "manual"
    snapshot_id: str


class PointInTimeMembershipSnapshot(BaseModel):
    """
    Frozen membership snapshot for a specific date.

    include_delisted: must be True for formal backtest to avoid survivorship bias.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    snapshot_id: str
    snapshot_date: date
    universe_rule_type: Literal["point_in_time_membership"]
    membership_source: str
    include_delisted: bool
    records: tuple[UniverseMembershipRecord, ...]
    quality_status: Literal["ok", "insufficient", "partial"]
    gaps: tuple[str, ...]  # List of detected gaps


class CoverageDisclosure(BaseModel):
    """Immutable coverage aggregate disclosure."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    coverage_package_id: str
    coverage_manifest_sha256: str
    expected_stock_days: int
    complete_stock_days: int
    unavailable_stock_days: int
    field_missing_counts: tuple[tuple[str, int], ...]  # sorted by field name


class DataSnapshotManifest(BaseModel):
    """
    Immutable manifest recording all data sources used in backtest.

    Hash covers semantic content only (market data, status, membership fingerprints).
    Tushare token, retrieval timestamps, absolute file paths are excluded.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    snapshot_id: str
    provider: str
    retrieval_date: date | None  # ponytail: None when unknown
    market_data_start: date
    market_data_end: date
    universe_snapshot_ids: tuple[str, ...]
    semantic_hash: str
    quality_status: Literal["ok", "insufficient"]
    gaps: tuple[str, ...]
    frozen: bool = True

    # V2 formal publication fields
    retrieval_date_status: Literal["verified", "unknown"] = "verified"
    manifest_published_at: datetime | None = None
    universe_reference_ids: tuple[str, ...] = ()
    coverage_disclosure: CoverageDisclosure | None = None
    source_manifest_hashes: tuple[tuple[str, str], ...] = ()
    manifest_content_hash: str = ""
    not_authorized_for_b6_oos_gate_promotion_signal: bool = True

    # V3 formal, metadata-only qualification fields. Legacy V2 manifests keep
    # their existing defaults and authorization disclosure.
    schema_version: str = "legacy_data_snapshot.v2"
    availability_status: str = ""
    authorization_scope: str = ""
    v3_qualification: dict[str, Any] = Field(default_factory=dict)

    # V2 Gate 0 fields (Task 1)
    gate0_status: Literal["feasibility_probe_passed", "formal_qualified", "not_qualified"] = "not_qualified"  # ponytail: default not_qualified
    gate0_reason: str | None = None  # blocking gap or permission error
    interfaces_probed: tuple[str, ...] = ()  # Tushare interface names
    coverage_start: date | None = None  # actual data coverage
    coverage_end: date | None = None

    # Legacy fingerprint fields
    financial_visibility_fingerprint: str = ""
    benchmark_fingerprint: str = ""
    adjustment_factor_fingerprint: str = ""
    provider_fingerprints: tuple[str, ...] = ()
    generated_by: str = ""  # Runtime metadata (excluded from hash)

    @model_validator(mode='after')
    def validate_retrieval_date_status(self):
        if not self.frozen:
            raise ValueError("DataSnapshotManifest must be frozen")
        # ponytail: verified requires date, unknown requires None
        if self.retrieval_date_status == "verified" and self.retrieval_date is None:
            raise ValueError("retrieval_date_status='verified' requires retrieval_date")
        if self.retrieval_date_status == "unknown" and self.retrieval_date is not None:
            raise ValueError("retrieval_date_status='unknown' requires retrieval_date=None")
        if self.provider == "mixed_vendor_tushare":
            if self.universe_snapshot_ids:
                raise ValueError("V2 formal manifest requires universe_snapshot_ids=()")
            if len(self.universe_reference_ids) != 1:
                raise ValueError("V2 formal manifest requires one universe_reference_id")
            if self.gaps != ("availability_limited",):
                raise ValueError("V2 formal manifest requires availability_limited disclosure")
            if self.coverage_disclosure is None:
                raise ValueError("V2 formal manifest requires coverage_disclosure")
            if not self.source_manifest_hashes or tuple(sorted(self.source_manifest_hashes)) != self.source_manifest_hashes:
                raise ValueError("V2 formal manifest requires sorted source_manifest_hashes")
        if self.not_authorized_for_b6_oos_gate_promotion_signal is False:
            if self.schema_version != "v3_formal_data_snapshot.v1":
                raise ValueError("v3 formal authorization requires v3 schema")
            if self.availability_status != "availability_bounded":
                raise ValueError("v3 formal authorization requires availability_bounded disclosure")
            if self.authorization_scope != "b6_coverage_bound":
                raise ValueError("v3 formal authorization requires b6_coverage_bound scope")
            required = {
                "template",
                "scope",
                "coverage",
                "calendar",
                "membership",
                "lifecycle",
                "suspension_evidence",
                "source_inventory",
                "execution_scope",
                "source_scope",
            }
            missing = sorted(required - self.v3_qualification.keys())
            if missing:
                raise ValueError(f"v3 formal qualification fields missing: {', '.join(missing)}")
            coverage = self.v3_qualification["coverage"]
            coverage_stats = coverage.get("stats", coverage)
            if coverage_stats.get("data_fault_count") != 0:
                raise ValueError("v3 formal qualification requires data_fault_count=0")
        return self


class OOSWindowSpec(BaseModel):
    """
    Deterministically generated OOS window.

    User/LLM cannot choose dates. System generates via registered rule.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    oos_window_rule_id: str
    oos_window_start: date
    oos_window_end: date
    generated_at: date


class TimeConsistencyCheckResult(BaseModel):
    """
    Result of time consistency validation.

    Separates blocking violations from warnings.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["pass", "fail"]
    blocking_violations: tuple[str, ...]
    warnings: tuple[str, ...]
