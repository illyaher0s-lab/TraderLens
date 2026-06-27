"""Backtest Report Builder - Convert B4 result to ImmutableBacktestReport."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime

from contracts.strategy import ImmutableBacktestReport
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
        report_id: str,
        strategy_revision_id: str,
        protocol_snapshot_id: str,
        strategy_config_hash: str,
        data_snapshot_hash: str,
        gate_criteria_hash: str,
        oos_draw_index: int | None,
        shared_oos_window_id: str | None,
        b4_result: EventBacktestResult,
        adjustment_mode: str,
        adjustment_snapshot_fingerprint: str,
    ) -> ImmutableBacktestReport:
        """
        Build immutable backtest report from B4 result.
        
        Args:
            report_id: Unique report ID
            strategy_revision_id: Strategy revision ID
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
            ImmutableBacktestReport with all required fields
        
        Raises:
            ValueError: If required B4 metadata missing
        """
        # Validate required B4 metadata
        self._validate_b4_metadata(
            b4_result,
            strategy_revision_id=strategy_revision_id,
            protocol_snapshot_id=protocol_snapshot_id,
        )
        
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
        
        # Build report payload with explicit missing fields
        report_payload_dict = {
            "protocol_snapshot_id": protocol_snapshot_id,
            "strategy_config_hash": strategy_config_hash,
            "data_snapshot_hash": data_snapshot_hash,
            "gate_criteria_hash": gate_criteria_hash,
            "oos_draw_index": oos_draw_index,
            "shared_oos_window_id": shared_oos_window_id,
            "b4_read_trace_summary": b4_read_trace_summary,
            "future_data_violation_count": future_data_violation_count,
            "adjustment_mode": adjustment_mode,
            "adjustment_snapshot_fingerprint": adjustment_snapshot_fingerprint,
            "liquidation_impact": liquidation_impact,
            "base_cost_result": "not_available_from_b4_result",
            "stress_cost_result": "not_available_from_b4_result",
            "control_comparison": "not_available_from_b4_result",
            "disclaimer": disclaimer,
        }
        
        report_payload_json = json.dumps(report_payload_dict, sort_keys=True)
        
        # Compute report hash
        report_hash = self.compute_report_hash_from_dict(report_payload_dict)
        
        # Determine evaluation mode
        evaluation_mode = self._determine_evaluation_mode(oos_draw_index)
        
        # Build ImmutableBacktestReport
        report = ImmutableBacktestReport(
            report_id=report_id,
            theme_id="not_available_from_b4_result",  # Future: extract from protocol
            strategy_revision_id=strategy_revision_id,
            protocol_snapshot_id=protocol_snapshot_id,
            strategy_config_hash=strategy_config_hash,
            data_snapshot_hash=data_snapshot_hash,
            gate_criteria_hash=gate_criteria_hash,
            evaluation_mode=evaluation_mode,
            oos_draw_index=oos_draw_index,
            shared_oos_window_id=shared_oos_window_id,
            multiple_comparison_flag=False,
            report_payload_json=report_payload_json,
            integrity_status="valid",
            generated_at=datetime.now(),
            report_hash=report_hash,
        )
        
        return report
    
    def _validate_b4_metadata(
        self,
        b4_result: EventBacktestResult,
        strategy_revision_id: str,
        protocol_snapshot_id: str,
    ) -> None:
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

        if b4_result.protocol_snapshot_id != protocol_snapshot_id:
            raise ValueError(
                f"protocol_snapshot_id mismatch: "
                f"B4 has '{b4_result.protocol_snapshot_id}', "
                f"report input has '{protocol_snapshot_id}'"
            )

        if b4_result.strategy_revision_id != strategy_revision_id:
            raise ValueError(
                f"strategy_revision_id mismatch: "
                f"B4 has '{b4_result.strategy_revision_id}', "
                f"report input has '{strategy_revision_id}'"
            )
    
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
    
    def compute_report_hash(self, report: ImmutableBacktestReport) -> str:
        """
        Compute deterministic report hash from ImmutableBacktestReport.
        
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
        import json
        payload = json.loads(report.report_payload_json)
        
        hash_input = {
            "protocol_snapshot_id": payload["protocol_snapshot_id"],
            "strategy_config_hash": payload["strategy_config_hash"],
            "data_snapshot_hash": payload["data_snapshot_hash"],
            "gate_criteria_hash": payload["gate_criteria_hash"],
            "oos_draw_index": payload["oos_draw_index"],
            "shared_oos_window_id": payload["shared_oos_window_id"],
            "b4_read_trace_summary": payload["b4_read_trace_summary"],
            "future_data_violation_count": payload["future_data_violation_count"],
            "adjustment_mode": payload["adjustment_mode"],
            "adjustment_snapshot_fingerprint": payload["adjustment_snapshot_fingerprint"],
            "liquidation_impact": payload["liquidation_impact"],
        }
        
        serialized = json.dumps(hash_input, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    
    def compute_report_hash_from_dict(self, report_payload_dict: dict) -> str:
        """
        Compute deterministic report hash from dict.
        
        Returns:
            SHA256 hash (hex string)
        """
        hash_input = {
            "protocol_snapshot_id": report_payload_dict["protocol_snapshot_id"],
            "strategy_config_hash": report_payload_dict["strategy_config_hash"],
            "data_snapshot_hash": report_payload_dict["data_snapshot_hash"],
            "gate_criteria_hash": report_payload_dict["gate_criteria_hash"],
            "oos_draw_index": report_payload_dict["oos_draw_index"],
            "shared_oos_window_id": report_payload_dict["shared_oos_window_id"],
            "b4_read_trace_summary": report_payload_dict["b4_read_trace_summary"],
            "future_data_violation_count": report_payload_dict["future_data_violation_count"],
            "adjustment_mode": report_payload_dict["adjustment_mode"],
            "adjustment_snapshot_fingerprint": report_payload_dict["adjustment_snapshot_fingerprint"],
            "liquidation_impact": report_payload_dict["liquidation_impact"],
        }
        
        serialized = json.dumps(hash_input, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    
    def _determine_evaluation_mode(self, oos_draw_index: int | None) -> str:
        """
        Determine evaluation mode from OOS draw index.
        
        Returns:
            "out_of_sample" if oos_draw_index is set, else "in_sample"
        """
        if oos_draw_index is not None and oos_draw_index >= 1:
            return "out_of_sample"
        return "in_sample"
