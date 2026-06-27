"""B5 test fixtures."""
from datetime import date, datetime

from backend.services.b5_oos_types import (
    OOSReservation,
    GateCheckItem,
    ReportPayloadSchema,
    ExplanationSnapshot,
)


def make_oos_reservation(
    reservation_id: str = "rsv_test_001",
    theme_id: str = "theme_test",
    hypothesis_source_snapshot_id: str = "hyp_snap_001",
    strategy_config_hash: str = "config_hash_001",
    data_snapshot_hash: str = "data_hash_001",
    gate_criteria_hash: str = "gate_hash_001",
    oos_draw_index: int = 1,
    status: str = "reserved",
    reserved_at: datetime | None = None,
    completed_at: datetime | None = None,
) -> OOSReservation:
    """Create OOSReservation fixture."""
    if reserved_at is None:
        reserved_at = datetime(2024, 1, 1, 10, 0, 0)
    
    return OOSReservation(
        reservation_id=reservation_id,
        theme_id=theme_id,
        hypothesis_source_snapshot_id=hypothesis_source_snapshot_id,
        strategy_config_hash=strategy_config_hash,
        data_snapshot_hash=data_snapshot_hash,
        gate_criteria_hash=gate_criteria_hash,
        oos_draw_index=oos_draw_index,
        status=status,
        reserved_at=reserved_at,
        completed_at=completed_at,
    )


def make_gate_check_item(
    check_id: str = "check_001",
    check_type: str = "sample_size",
    status: str = "pass",
    deterministic_source: str = "report:rpt_001",
    reason: str = "OOS sample has 252 trading days",
) -> GateCheckItem:
    """Create GateCheckItem fixture."""
    return GateCheckItem(
        check_id=check_id,
        check_type=check_type,
        status=status,
        deterministic_source=deterministic_source,
        reason=reason,
    )


def make_report_payload_schema(
    protocol_snapshot_id: str = "proto_001",
    strategy_config_hash: str = "config_hash_001",
    data_snapshot_hash: str = "data_hash_001",
    gate_criteria_hash: str = "gate_hash_001",
    oos_draw_index: int | None = 1,
    shared_oos_window_id: str | None = "shared_oos_001",
    b4_read_trace_summary: str = "signal_phase: 252 reads, execution_phase: 252 reads",
    future_data_violation_count: int = 0,
    adjustment_mode: str = "qfq",
    adjustment_snapshot_fingerprint: str = "adj_fp_001",
    liquidation_impact: float = 0.0,
    disclaimer: str = "This report is historical OOS validation. Not a profit guarantee, not live trading instruction, not promotion.",
) -> ReportPayloadSchema:
    """Create ReportPayloadSchema fixture."""
    return ReportPayloadSchema(
        protocol_snapshot_id=protocol_snapshot_id,
        strategy_config_hash=strategy_config_hash,
        data_snapshot_hash=data_snapshot_hash,
        gate_criteria_hash=gate_criteria_hash,
        oos_draw_index=oos_draw_index,
        shared_oos_window_id=shared_oos_window_id,
        b4_read_trace_summary=b4_read_trace_summary,
        future_data_violation_count=future_data_violation_count,
        adjustment_mode=adjustment_mode,
        adjustment_snapshot_fingerprint=adjustment_snapshot_fingerprint,
        liquidation_impact=liquidation_impact,
        disclaimer=disclaimer,
    )


def make_explanation_snapshot(
    explanation_id: str = "expl_001",
    report_id: str = "rpt_001",
    gate_result_id: str = "gate_001",
    plain_summary: str = "Strategy rejected due to insufficient OOS sample size.",
    deterministic_evidence: tuple[str, ...] = ("check_sample_size", "check_trade_count"),
    generated_at: datetime | None = None,
) -> ExplanationSnapshot:
    """Create ExplanationSnapshot fixture."""
    if generated_at is None:
        generated_at = datetime(2024, 1, 1, 12, 0, 0)
    
    return ExplanationSnapshot(
        explanation_id=explanation_id,
        report_id=report_id,
        gate_result_id=gate_result_id,
        plain_summary=plain_summary,
        deterministic_evidence=deterministic_evidence,
        generated_at=generated_at,
    )
