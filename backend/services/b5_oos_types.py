"""B5 OOS Validation Types - Frozen contracts for out-of-sample evaluation."""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class FrozenB5Contract(BaseModel):
    """Base class for all B5 frozen contracts."""
    model_config = ConfigDict(extra="forbid", frozen=True)


class OOSReservation(FrozenB5Contract):
    """
    Atomic OOS budget reservation.
    
    Prevents concurrent over-draw and ensures budget integrity.
    Status transitions: reserved -> completed | released | failed
    """
    reservation_id: str = Field(min_length=1)
    theme_id: str = Field(min_length=1)
    hypothesis_source_snapshot_id: str = Field(min_length=1)
    strategy_config_hash: str = Field(min_length=1)
    data_snapshot_hash: str = Field(min_length=1)
    gate_criteria_hash: str = Field(min_length=1)
    oos_draw_index: int = Field(ge=1, le=3)
    status: Literal["reserved", "completed", "released", "failed"]
    reserved_at: datetime
    completed_at: datetime | None = None
    frozen: Literal[True] = True


class GateCheckItem(FrozenB5Contract):
    """
    Deterministic Gate check result.
    
    Must reference deterministic source (report_id, protocol_id, data_hash).
    No LLM verdict, no subjective scores.
    """
    check_id: str = Field(min_length=1)
    check_type: str = Field(min_length=1)
    status: Literal["pass", "fail", "degraded"]
    deterministic_source: str = Field(min_length=1)  # e.g., "report:abc123", "protocol:xyz789"
    reason: str = Field(min_length=1)
    frozen: Literal[True] = True


class ReportPayloadSchema(FrozenB5Contract):
    """
    Immutable backtest report payload schema.
    
    Must NOT contain buy/sell recommendations or live trading instructions.
    Only historical validation facts.
    """
    protocol_snapshot_id: str = Field(min_length=1)
    strategy_config_hash: str = Field(min_length=1)
    data_snapshot_hash: str = Field(min_length=1)
    gate_criteria_hash: str = Field(min_length=1)
    oos_draw_index: int | None = Field(default=None, ge=1, le=3)
    shared_oos_window_id: str | None = None
    b4_read_trace_summary: str  # Summary of BacktestTimeCursor read trace
    future_data_violation_count: int = Field(ge=0)
    adjustment_mode: Literal["raw", "qfq", "hfq"]
    adjustment_snapshot_fingerprint: str = Field(min_length=1)
    liquidation_impact: float = Field(ge=0.0)
    disclaimer: str = Field(min_length=1)  # Fixed: "not profit guarantee, not live trading instruction"
    frozen: Literal[True] = True


class ExplanationSnapshot(FrozenB5Contract):
    """
    Plain-language Gate explanation for user.
    
    References deterministic report and Gate IDs.
    No LLM verdict override, no buy/sell recommendations.
    """
    explanation_id: str = Field(min_length=1)
    report_id: str = Field(min_length=1)
    gate_result_id: str = Field(min_length=1)
    plain_summary: str = Field(min_length=1)
    deterministic_evidence: tuple[str, ...]  # List of check_ids or report fields
    generated_at: datetime
    frozen: Literal[True] = True


class B5ValidationBoundary(FrozenB5Contract):
    """
    B5 validation boundary proof.
    
    Tests must verify:
    - B5 types frozen / extra forbid
    - OOS reservation has reserved/completed/released/failed states
    - Gate check references deterministic source (no LLM verdict)
    - Report payload has no buy/sell recommendation
    - Explanation snapshot references report/gate IDs
    - No prototype_passed write capability in B5 types
    """
    boundary_name: Literal["b5_oos_types_frozen"]
    proof_timestamp: datetime
    frozen: Literal[True] = True
