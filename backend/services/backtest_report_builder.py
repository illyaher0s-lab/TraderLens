"""Backtest Report Builder - Convert B4 result to ImmutableBacktestReport."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime

from backend.services.b5_oos_types import ReportPayloadSchema
from backend.services.b4_protocol_types import EventBacktestResult


class BacktestReportBuilder:
    """
    Build ImmutableBacktestReport from B4 event backtest result.
    
    Report records facts only:
    - Protocol IDs and three hashes
    - OOS draw index and shared window ID
    - B4 read trace summary
    - Future data violations
    - Adjustment mode and fingerprint
    - Liquidation impact
    - Fixed disclaimer (not profit guarantee, not live trading instruction)
    
    Report does NOT:
    - Generate buy/sell recommendations
    - Create Gate verdict
    - Write promotion
    - Contain prototype_passed
    """
    
    def build_report(
        self,
        protocol_snapshot_id: str,
        strategy_config_hash: str,
        data_snapshot_hash: str,
        gate_criteria_hash: str,
        oos_draw_index: int | None,
        shared_oos_window_id: str | None,
        b4_result: EventBacktestResult,
        adjustment_mode: str,
        adjustment_snapshot_fingerprint: str,
    ) -> ReportPayloadSchema:
        """
        Build immutable backtest report from B4 result.
        
        Args:
            protocol_snapshot_id: B3 protocol snapshot ID
            strategy_config_hash: Strategy config hash
            data_snapshot_hash: Data snapshot hash
            gate_criteria_hash: Gate criteria hash
            oos_draw_index: OOS draw index (1, 2, or 3)
            shared_oos_window_id: Shared OOS window ID
            b4_result: B4 event backtest result
            adjustment_mode: Adjustment mode (raw/qfq/hfq)
            adjustment_snapshot_fingerprint: Adjustment snapshot fingerprint
        
        Returns:
            ReportPayloadSchema with report facts
        
        Raises:
            ValueError: If required B4 metadata missing
        """
        # Validate required B4 metadata
        self._validate_b4_metadata(b4_result)
        
        # Extract B4 read trace summary
        b4_read_trace_summary = self._summarize_b4_read_trace(b4_result)
        
        # Count future data violations
        future_data_violation_count = len(b4_result.future_violations)
        
        # Calculate liquidation impact
        liquidation_impact = self._calculate_liquidation_impact(b4_result)
        
        # Fixed disclaimer
        disclaimer = (
            "This report is historical OOS validation under frozen data, frozen strategy, and frozen Gate policy. "
            "It is not a future profit guarantee, not a live trading instruction, and not a promotion by itself."
        )
        
        # Build report payload
        report_payload = ReportPayloadSchema(
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
        
        return report_payload
    
    def _validate_b4_metadata(self, b4_result: EventBacktestResult) -> None:
        """
        Validate B4 result has required metadata.
        
        Raises:
            ValueError: If required metadata missing
        """
        if not b4_result.protocol_snapshot_id or len(b4_result.protocol_snapshot_id.strip()) == 0:
            raise ValueError("B4 result missing protocol_snapshot_id")
        
        if not b4_result.strategy_revision_id or len(b4_result.strategy_revision_id.strip()) == 0:
            raise ValueError("B4 result missing strategy_revision_id")
        
        if b4_result.evaluation_mode not in ["formal_backtest", "in_sample", "out_of_sample"]:
            raise ValueError(f"Invalid B4 evaluation_mode: {b4_result.evaluation_mode}")
    
    def _summarize_b4_read_trace(self, b4_result: EventBacktestResult) -> str:
        """
        Summarize B4 BacktestTimeCursor read trace.
        
        Returns:
            Human-readable summary of read trace
        """
        # For MVP, return simple count summary
        # Future: parse read_trace and categorize by data type
        order_count = len(b4_result.order_intents)
        fill_count = len(b4_result.fills)
        
        return (
            f"Orders: {order_count}, "
            f"Fills: {fill_count}, "
            f"Evaluation mode: {b4_result.evaluation_mode}"
        )
    
    def _calculate_liquidation_impact(self, b4_result: EventBacktestResult) -> float:
        """
        Calculate liquidation impact from delisting/suspension penalties.
        
        Returns:
            Total liquidation impact (non-negative)
        """
        # For MVP, return 0.0
        # Future: extract from EventBacktestResult.liquidation_events if added
        return 0.0
    
    def compute_report_hash(self, report_payload: ReportPayloadSchema) -> str:
        """
        Compute deterministic report hash.
        
        Hash includes:
        - Protocol snapshot ID
        - Three hashes (strategy, data, gate)
        - OOS draw index
        - Shared OOS window ID
        - B4 metadata (read trace, violations, adjustment)
        
        Hash excludes:
        - Disclaimer text (constant)
        - Runtime metadata
        
        Returns:
            SHA256 hash (hex string)
        """
        hash_input = {
            "protocol_snapshot_id": report_payload.protocol_snapshot_id,
            "strategy_config_hash": report_payload.strategy_config_hash,
            "data_snapshot_hash": report_payload.data_snapshot_hash,
            "gate_criteria_hash": report_payload.gate_criteria_hash,
            "oos_draw_index": report_payload.oos_draw_index,
            "shared_oos_window_id": report_payload.shared_oos_window_id,
            "b4_read_trace_summary": report_payload.b4_read_trace_summary,
            "future_data_violation_count": report_payload.future_data_violation_count,
            "adjustment_mode": report_payload.adjustment_mode,
            "adjustment_snapshot_fingerprint": report_payload.adjustment_snapshot_fingerprint,
            "liquidation_impact": report_payload.liquidation_impact,
        }
        
        serialized = json.dumps(hash_input, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
