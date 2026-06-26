"""B3 Protocol Types - Point-in-time data contracts and frozen snapshots."""
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict


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


class DataSnapshotManifest(BaseModel):
    """
    Immutable manifest recording all data sources used in backtest.
    
    Hash covers semantic content only (market data, status, membership fingerprints).
    Runtime metadata excluded from hash.
    """
    
    model_config = ConfigDict(frozen=True, extra="forbid")
    
    data_snapshot_id: str
    data_snapshot_hash: str
    created_at: date
    market_data_fingerprint: str
    daily_status_fingerprint: str
    membership_fingerprint: str
    financial_visibility_fingerprint: str = ""
    benchmark_fingerprint: str = ""
    quality_status: Literal["ok", "insufficient"]
    gaps: tuple[str, ...]


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
