"""PrototypeGateV2 - Deterministic Gate evaluator."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime

from contracts.strategy import ImmutableBacktestReport, PrototypeGateResultV2


class PrototypeGateV2:
    """
    Deterministic PrototypeGateV2 evaluator.
    
    Requirements:
    - Inputs: frozen protocol/report/ledger/gate criteria
    - Outputs: rejected / needs_review / candidate_for_prototype_passed
    - Never outputs prototype_passed
    - Never writes lifecycle state
    - Future data violations: hard reject
    - Missing base/stress/control: hard reject or needs_review
    - Data insufficient: cannot candidate
    - Draw 2/3: stricter thresholds than draw 1
    - No LLM dependency
    """
    
    # System-frozen OOS draw policies
    OOS_DRAW_POLICIES = {
        1: {"min_sharpe": 1.0, "min_trades": 10, "max_drawdown": 0.20},
        2: {"min_sharpe": 1.2, "min_trades": 15, "max_drawdown": 0.15},
        3: {"min_sharpe": 1.5, "min_trades": 20, "max_drawdown": 0.10},
    }
    
    def get_oos_policy(self, oos_draw_index: int) -> dict:
        """
        Get frozen OOS policy for draw index.
        
        Draw 2/3 are stricter than draw 1 (higher Sharpe, more trades, lower drawdown).
        
        Returns:
            dict with policy thresholds
        """
        return self.OOS_DRAW_POLICIES.get(oos_draw_index, self.OOS_DRAW_POLICIES[1])
    
    def evaluate(
        self,
        report: ImmutableBacktestReport,
        gate_criteria_hash: str,
    ) -> PrototypeGateResultV2:
        """
        Evaluate Gate for ImmutableBacktestReport.
        
        Args:
            report: Immutable backtest report
            gate_criteria_hash: Expected gate criteria hash
        
        Returns:
            PrototypeGateResultV2 with verdict
        
        Raises:
            ValueError: If gate_criteria_hash mismatch
        """
        # Validate gate criteria hash
        if report.gate_criteria_hash != gate_criteria_hash:
            raise ValueError(
                f"Gate criteria hash mismatch: "
                f"report has '{report.gate_criteria_hash}', "
                f"gate expects '{gate_criteria_hash}'"
            )
        
        # Parse report payload
        payload = json.loads(report.report_payload_json)
        
        # Collect blocking issues and warnings
        blocking_issues = []
        warnings = []
        
        # Check 1: Future data violations (hard reject)
        future_violations = payload.get("future_data_violation_count", 0)
        if future_violations > 0:
            blocking_issues.append(
                f"Future data violations detected: {future_violations} violations. "
                f"Cannot proceed with strategy that accessed future information."
            )
        
        # Check 2: Data integrity
        if report.integrity_status != "valid":
            blocking_issues.append(
                f"Data integrity insufficient: status='{report.integrity_status}'. "
                f"Cannot candidate with invalid data."
            )
        
        # Check 3: Missing or failed base/stress/control/benchmark results
        stress_cost = payload.get("stress_cost_result")
        control_comparison = payload.get("control_comparison")
        base_cost = payload.get("base_cost_result")
        benchmark_comparison = payload.get("benchmark_comparison")
        
        if stress_cost == "not_available_from_b4_result" or stress_cost is None:
            blocking_issues.append("Missing stress cost result blocks candidate verdict")
        elif self._is_failed_result(stress_cost):
            blocking_issues.append("Stress cost result failed and blocks candidate verdict")
        
        if control_comparison == "not_available_from_b4_result" or control_comparison is None:
            blocking_issues.append("Missing control comparison blocks candidate verdict")
        elif self._is_failed_result(control_comparison):
            blocking_issues.append("Control comparison failed and blocks candidate verdict")
        
        if base_cost == "not_available_from_b4_result" or base_cost is None:
            blocking_issues.append("Missing base cost result blocks candidate verdict")
        elif self._is_failed_result(base_cost):
            blocking_issues.append("Base cost result failed and blocks candidate verdict")

        if benchmark_comparison == "not_available_from_b4_result" or benchmark_comparison is None:
            blocking_issues.append("Missing benchmark comparison blocks candidate verdict")
        elif self._is_failed_result(benchmark_comparison):
            blocking_issues.append("Benchmark comparison failed and blocks candidate verdict")

        # Check 4: Data quality and anti-self-deception risk flags
        data_quality_status = payload.get("data_quality_status")
        if data_quality_status in {"insufficient", "invalid"}:
            blocking_issues.append(
                f"Data quality status '{data_quality_status}' blocks candidate verdict"
            )

        if payload.get("beta_dominated") is True:
            blocking_issues.append("Beta domination blocks candidate verdict")

        for field, label in (
            ("single_symbol_concentration", "Single-symbol concentration"),
            ("single_month_concentration", "Single-month concentration"),
        ):
            if self._is_failed_result(payload.get(field)):
                blocking_issues.append(f"{label} blocks candidate verdict")
        
        # Determine verdict
        if blocking_issues:
            verdict = "rejected"
        else:
            # All checks pass - candidate for prototype_passed
            # (but Gate never writes prototype_passed itself)
            verdict = "candidate_for_prototype_passed"
        
        # Build Gate result
        checks = {
            "future_data_violations": future_violations,
            "data_integrity": report.integrity_status,
            "stress_cost_present": stress_cost not in [None, "not_available_from_b4_result"],
            "control_comparison_present": control_comparison not in [None, "not_available_from_b4_result"],
            "base_cost_present": base_cost not in [None, "not_available_from_b4_result"],
            "benchmark_comparison_present": benchmark_comparison not in [None, "not_available_from_b4_result"],
            "data_quality_status": data_quality_status,
            "beta_dominated": payload.get("beta_dominated", False),
        }
        
        gate_result_id = self._generate_gate_result_id(report.report_id)
        gate_result_hash = self._compute_gate_result_hash(report.report_id, verdict, checks)
        
        return PrototypeGateResultV2(
            gate_result_id=gate_result_id,
            report_id=report.report_id,
            strategy_revision_id=report.strategy_revision_id,
            protocol_snapshot_id=report.protocol_snapshot_id,
            verdict=verdict,
            checks_json=json.dumps(checks, sort_keys=True),
            blocking_issues=tuple(blocking_issues),
            warnings=tuple(warnings),
            strategy_config_hash=report.strategy_config_hash,
            data_snapshot_hash=report.data_snapshot_hash,
            gate_criteria_hash=report.gate_criteria_hash,
            oos_draw_index=report.oos_draw_index,
            shared_oos_window_id=report.shared_oos_window_id,
            multiple_comparison_flag=report.multiple_comparison_flag,
            generated_at=datetime.now(),
            gate_result_hash=gate_result_hash,
        )
    
    def _generate_gate_result_id(self, report_id: str) -> str:
        """Generate deterministic gate result ID."""
        return f"gate_{report_id}_{datetime.now().isoformat()}"
    
    def _compute_gate_result_hash(self, report_id: str, verdict: str, checks: dict) -> str:
        """Compute deterministic gate result hash."""
        hash_input = {
            "report_id": report_id,
            "verdict": verdict,
            "checks": checks,
        }
        serialized = json.dumps(hash_input, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _is_failed_result(self, result) -> bool:
        """Return True when a deterministic check explicitly blocks candidacy."""
        if result is None:
            return False

        if isinstance(result, str):
            return result.lower() in {"fail", "failed", "rejected", "insufficient"}

        if isinstance(result, dict):
            status = str(result.get("status", "")).lower()
            if status in {"fail", "failed", "rejected", "insufficient"}:
                return True
            can_candidate = result.get("can_candidate")
            if can_candidate is False:
                return True
            passed = result.get("passed")
            if passed is False:
                return True

        return False
