"""B5 OOS Validation Types - Frozen contracts for out-of-sample evaluation."""
from __future__ import annotations

from datetime import date, datetime
import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class FrozenB5Contract(BaseModel):
    """Base class for all B5 frozen contracts."""
    model_config = ConfigDict(extra="forbid", frozen=True)


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _finite_number(value: object, field_name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a finite number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a finite number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field_name} must be finite")
    return number


def _lower_sha256(value: object, field_name: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be 64 lowercase hexadecimal characters")
    return value


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


class B6SameDrawReadAudit(FrozenB5Contract):
    """Canonical bounded read summary for one same-draw execution."""

    schema_version: Literal["b6_same_draw_read_audit.v1"] = "b6_same_draw_read_audit.v1"
    owner: Literal["b6_same_draw_executor"] = "b6_same_draw_executor"
    allowed_end: date
    max_requested_date: date | None = None
    future_violation_count: int = Field(ge=0, le=0)
    operation_counts: dict[str, int]
    read_count: int = Field(ge=0)
    canonical_trace_sha256: str

    @field_validator("future_violation_count", "read_count", mode="before")
    @classmethod
    def _validate_integer_fields(cls, value: object, info):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{info.field_name} must be an integer")
        if value < 0:
            raise ValueError(f"{info.field_name} must be non-negative")
        return value

    @field_validator("operation_counts", mode="before")
    @classmethod
    def _validate_operation_counts(cls, value: object):
        if not isinstance(value, Mapping):
            raise ValueError("operation_counts must be a mapping")
        normalized: dict[str, int] = {}
        for operation, count in value.items():
            if not isinstance(operation, str) or re.fullmatch(r"[a-z][a-z0-9_]*", operation) is None:
                raise ValueError("operation_counts keys must be stable operation names")
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise ValueError("operation_counts values must be non-negative integers")
            normalized[operation] = count
        return dict(sorted(normalized.items()))

    @field_validator("canonical_trace_sha256")
    @classmethod
    def _validate_trace_sha256(cls, value: object, info):
        return _lower_sha256(value, info.field_name)

    @model_validator(mode="after")
    def _validate_bounds_and_counts(self):
        if self.max_requested_date is not None and self.max_requested_date > self.allowed_end:
            raise ValueError("max_requested_date must not exceed allowed_end")
        if self.future_violation_count != 0:
            raise ValueError("future_violation_count must be exactly zero")
        if self.read_count != sum(self.operation_counts.values()):
            raise ValueError("read_count must equal the sum of operation_counts")
        return self

    @classmethod
    def from_trace(
        cls,
        *,
        allowed_end: date,
        trace: Sequence[Mapping[str, Any]],
    ) -> "B6SameDrawReadAudit":
        """Build the persisted summary from an ordered in-memory trace."""
        records: list[dict[str, Any]] = []
        operation_counts: dict[str, int] = {}
        max_requested_date: date | None = None
        future_violation_count = 0
        for record in trace:
            if not isinstance(record, Mapping):
                raise ValueError("read trace records must be mappings")
            normalized = dict(record)
            operation = normalized.get("operation")
            if not isinstance(operation, str) or re.fullmatch(r"[a-z][a-z0-9_]*", operation) is None:
                raise ValueError("read trace operation must be a stable operation name")
            requested_date = normalized.get("requested_date")
            if requested_date is not None:
                if not isinstance(requested_date, str):
                    raise ValueError("requested_date must be an ISO date string")
                try:
                    parsed_date = date.fromisoformat(requested_date)
                except ValueError as exc:
                    raise ValueError("requested_date must be an ISO date string") from exc
                max_requested_date = (
                    parsed_date
                    if max_requested_date is None
                    else max(max_requested_date, parsed_date)
                )
                if parsed_date > allowed_end:
                    future_violation_count += 1
            operation_counts[operation] = operation_counts.get(operation, 0) + 1
            records.append(normalized)
        trace_hash = hashlib.sha256(_canonical_json_bytes(records)).hexdigest()
        return cls(
            allowed_end=allowed_end,
            max_requested_date=max_requested_date,
            future_violation_count=future_violation_count,
            operation_counts=operation_counts,
            read_count=len(records),
            canonical_trace_sha256=trace_hash,
        )


class SameDrawExecutionIdentity(FrozenB5Contract):
    """Immutable input identity for one same-draw B6 OOS envelope."""

    task_id: str = Field(min_length=1)
    task_key: str = Field(min_length=1)
    strategy_revision_id: str = Field(min_length=1)
    protocol_snapshot_id: str = Field(min_length=1)
    b5_bundle_id: str = Field(min_length=1)
    b5_bundle_manifest_sha256: str
    b4_artifact_id: str = Field(min_length=1)
    b4_manifest_sha256: str
    b4_event_result_sha256: str
    formal_snapshot_id: str = Field(min_length=1)
    formal_snapshot_manifest_sha256: str
    membership_snapshot_id: str = Field(min_length=1)
    membership_manifest_sha256: str
    calendar_id: str = Field(min_length=1)
    calendar_manifest_sha256: str
    data_snapshot_hash: str
    execution_input_hash: str
    shared_oos_window_id: str = Field(min_length=1)
    oos_start: date
    oos_end: date
    result_schema_version: Literal[
        "b6_same_draw_oos_result.v1",
        "b6_same_draw_oos_result.v2",
    ]

    @field_validator(
        "b5_bundle_manifest_sha256",
        "b4_manifest_sha256",
        "b4_event_result_sha256",
        "formal_snapshot_manifest_sha256",
        "membership_manifest_sha256",
        "calendar_manifest_sha256",
        "data_snapshot_hash",
        "execution_input_hash",
    )
    @classmethod
    def _validate_sha256(cls, value: object, info):
        return _lower_sha256(value, info.field_name)

    @model_validator(mode="after")
    def _validate_window(self):
        if self.oos_start > self.oos_end:
            raise ValueError("oos_start must be on or before oos_end")
        return self


class B6SameDrawOOSResult(FrozenB5Contract):
    """Six net returns with Alpha derived only from those returns."""

    identity: SameDrawExecutionIdentity
    starting_nav: float = Field(gt=0)
    ending_nav_base: float = Field(gt=0)
    ending_nav_stress: float = Field(gt=0)
    strategy_net_return_base: float
    strategy_net_return_stress: float
    benchmark_net_return_base: float
    benchmark_net_return_stress: float
    same_universe_control_return_base: float
    same_universe_control_return_stress: float
    base_cost_result: "BaseCostResult"
    stress_cost_result: "StressCostResult"
    read_audit: B6SameDrawReadAudit | None = None

    @field_validator(
        "starting_nav",
        "ending_nav_base",
        "ending_nav_stress",
        "strategy_net_return_base",
        "strategy_net_return_stress",
        "benchmark_net_return_base",
        "benchmark_net_return_stress",
        "same_universe_control_return_base",
        "same_universe_control_return_stress",
        mode="before",
    )
    @classmethod
    def _validate_finite_values(cls, value: object, info):
        return _finite_number(value, info.field_name)

    @model_validator(mode="after")
    def _validate_cost_order(self):
        base = self.base_cost_result
        stress = self.stress_cost_result
        for field_name in ("slippage_bps", "commission_bps", "impact_bps", "total_cost_bps"):
            if getattr(stress, field_name) < getattr(base, field_name):
                raise ValueError(f"stress cost {field_name} must be >= base cost")
        if self.identity.result_schema_version == "b6_same_draw_oos_result.v2":
            if self.read_audit is None:
                raise ValueError("v2 same-draw result requires read_audit")
            _lower_sha256(base.assumptions_hash, "base_cost_result.assumptions_hash")
            _lower_sha256(stress.assumptions_hash, "stress_cost_result.assumptions_hash")
        return self

    def assert_production_terminal_eligible(self) -> "B6SameDrawOOSResult":
        if self.identity.result_schema_version != "b6_same_draw_oos_result.v2" or self.read_audit is None:
            raise ValueError("production terminal requires a v2 same-draw result with read_audit")
        return self

    @property
    def alpha_vs_benchmark_base(self) -> float:
        return self.strategy_net_return_base - self.benchmark_net_return_base

    @property
    def alpha_vs_benchmark_stress(self) -> float:
        return self.strategy_net_return_stress - self.benchmark_net_return_stress

    @property
    def alpha_vs_control_base(self) -> float:
        return self.strategy_net_return_base - self.same_universe_control_return_base

    @property
    def alpha_vs_control_stress(self) -> float:
        return self.strategy_net_return_stress - self.same_universe_control_return_stress

    def to_payload(self) -> dict:
        """Return the canonical report-facing payload with derived Alpha values."""
        payload = {
            "schema_version": self.identity.result_schema_version,
            "identity": self.identity.model_dump(mode="json"),
            "starting_nav": self.starting_nav,
            "ending_nav_base": self.ending_nav_base,
            "ending_nav_stress": self.ending_nav_stress,
            "strategy_net_return_base": self.strategy_net_return_base,
            "strategy_net_return_stress": self.strategy_net_return_stress,
            "benchmark_net_return_base": self.benchmark_net_return_base,
            "benchmark_net_return_stress": self.benchmark_net_return_stress,
            "same_universe_control_return_base": self.same_universe_control_return_base,
            "same_universe_control_return_stress": self.same_universe_control_return_stress,
            "alpha_vs_benchmark_base": self.alpha_vs_benchmark_base,
            "alpha_vs_benchmark_stress": self.alpha_vs_benchmark_stress,
            "alpha_vs_control_base": self.alpha_vs_control_base,
            "alpha_vs_control_stress": self.alpha_vs_control_stress,
            "base_cost_result": self.base_cost_result.model_dump(mode="json"),
            "stress_cost_result": self.stress_cost_result.model_dump(mode="json"),
        }
        if self.read_audit is not None:
            payload["read_audit"] = self.read_audit.model_dump(mode="json")
        return payload


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


class BaseCostResult(FrozenB5Contract):
    """
    Base cost assumptions result.
    
    Must be explicitly present (not None, not 0 by default).
    """
    result_id: str = Field(min_length=1)
    slippage_bps: float = Field(ge=0.0)
    commission_bps: float = Field(ge=0.0)
    impact_bps: float = Field(ge=0.0)
    total_cost_bps: float = Field(ge=0.0)
    assumptions_hash: str = Field(min_length=1)
    frozen: Literal[True] = True


class StressCostResult(FrozenB5Contract):
    """
    Stress cost assumptions result.
    
    Must be stricter than base cost (higher slippage/commission/impact).
    """
    result_id: str = Field(min_length=1)
    slippage_bps: float = Field(ge=0.0)
    commission_bps: float = Field(ge=0.0)
    impact_bps: float = Field(ge=0.0)
    total_cost_bps: float = Field(ge=0.0)
    stress_multiplier: float = Field(ge=1.0)  # Must be >= 1.0
    assumptions_hash: str = Field(min_length=1)
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


class B6ValidationRunResult(FrozenB5Contract):
    """
    Auditable B6 vertical validation run result.

    Records the complete validation flow from StrategyDraft to final state.
    Does NOT contain buy/sell recommendations or technical parameters.
    """
    run_id: str = Field(min_length=1)
    strategy_revision_id: str = Field(min_length=1)
    protocol_snapshot_id: str = Field(min_length=1)
    report_id: str | None = None
    gate_result_id: str | None = None
    explanation_id: str | None = None
    promotion_id: str | None = None
    final_state: Literal[
        "draft",
        "rejected",
        "needs_review",
        "candidate_for_prototype_passed",
        "prototype_passed",
    ]
    status: Literal["completed", "blocked", "failed"]
    blocking_reason: str | None = None
    created_at: datetime
    frozen: Literal[True] = True
