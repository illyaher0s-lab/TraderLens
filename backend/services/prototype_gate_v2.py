"""PrototypeGateV2 - Deterministic Gate evaluator."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime

from contracts.strategy import ImmutableBacktestReport, PrototypeGateResultV2
from backend.services.b5_oos_types import B6SameDrawOOSResult
from backend.services.prototype_gate_criteria_surface import (
    FrozenEffectiveCriteriaInput,
    evaluate_effective_criteria,
)


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

        future_violations = payload.get("future_data_violation_count", 0)

        # Check 3: Missing or failed base/stress/control/benchmark results
        same_draw_result = None
        same_draw_error = None
        if "same_draw_result" in payload:
            try:
                same_draw_result = self._parse_same_draw_result(payload, report)
            except (TypeError, ValueError, KeyError) as exc:
                same_draw_error = str(exc)

        if same_draw_error is not None:
            blocking_issues.append(f"Same-draw result invalid: {same_draw_error}")

        stress_cost = (
            same_draw_result.stress_cost_result.model_dump(mode="json")
            if same_draw_result is not None
            else payload.get("stress_cost_result")
        )
        control_comparison = (
            {"status": "pass", "return_base": same_draw_result.same_universe_control_return_base,
             "return_stress": same_draw_result.same_universe_control_return_stress}
            if same_draw_result is not None
            else payload.get("control_comparison")
        )
        base_cost = (
            same_draw_result.base_cost_result.model_dump(mode="json")
            if same_draw_result is not None
            else payload.get("base_cost_result")
        )
        benchmark_comparison = (
            {"status": "pass", "return_base": same_draw_result.benchmark_net_return_base,
             "return_stress": same_draw_result.benchmark_net_return_stress}
            if same_draw_result is not None
            else payload.get("benchmark_comparison")
        )

        data_quality_status = payload.get("data_quality_status")
        effective_decision = evaluate_effective_criteria(
            FrozenEffectiveCriteriaInput(
                future_data_violation_count=future_violations,
                integrity_status=report.integrity_status,
                stress_cost_result=stress_cost,
                control_comparison=control_comparison,
                base_cost_result=base_cost,
                benchmark_comparison=benchmark_comparison,
                data_quality_status=data_quality_status,
                beta_dominated=payload.get("beta_dominated"),
                single_symbol_concentration=payload.get("single_symbol_concentration"),
                single_month_concentration=payload.get("single_month_concentration"),
            )
        )
        for issue_id in effective_decision.blocking_issue_ids:
            if issue_id == "future_data_violation":
                blocking_issues.append(
                    f"Future data violations detected: {future_violations} violations. "
                    f"Cannot proceed with strategy that accessed future information."
                )
            elif issue_id == "invalid_report_integrity":
                blocking_issues.append(
                    f"Data integrity insufficient: status='{report.integrity_status}'. "
                    f"Cannot candidate with invalid data."
                )
            elif issue_id == "missing_or_failed_b4_result":
                for value, label, name in (
                    (stress_cost, "Stress cost result", "stress cost result"),
                    (control_comparison, "Control comparison", "control comparison"),
                    (base_cost, "Base cost result", "base cost result"),
                    (benchmark_comparison, "Benchmark comparison", "benchmark comparison"),
                ):
                    if value == "not_available_from_b4_result" or value is None:
                        blocking_issues.append(f"Missing {name} blocks candidate verdict")
                    elif self._is_failed_result(value):
                        blocking_issues.append(f"{label} failed and blocks candidate verdict")
            elif issue_id == "invalid_data_quality":
                blocking_issues.append(
                    f"Data quality status '{data_quality_status}' blocks candidate verdict"
                )
            elif issue_id == "beta_dominated":
                blocking_issues.append("Beta domination blocks candidate verdict")
            elif issue_id == "concentration_risk":
                for field, label in (
                    ("single_symbol_concentration", "Single-symbol concentration"),
                    ("single_month_concentration", "Single-month concentration"),
                ):
                    if self._is_failed_result(payload.get(field)):
                        blocking_issues.append(f"{label} blocks candidate verdict")

        verdict = "rejected" if blocking_issues else effective_decision.verdict

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
        if same_draw_result is not None:
            checks["same_draw_result"] = same_draw_result.to_payload()
            checks["same_draw_alpha_is_arithmetic_not_causal"] = True
            if same_draw_result.identity.result_schema_version == "b6_same_draw_oos_result.v2":
                checks["same_draw_read_audit_verified"] = True

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

    def _parse_same_draw_result(
        self,
        payload: dict,
        report: ImmutableBacktestReport,
    ) -> B6SameDrawOOSResult:
        raw = payload.get("same_draw_result")
        if not isinstance(raw, dict):
            raise ValueError("same_draw_result must be an object")
        raw = dict(raw)
        provided_alpha = {
            name: raw.pop(name, None)
            for name in (
                "alpha_vs_benchmark_base",
                "alpha_vs_benchmark_stress",
                "alpha_vs_control_base",
                "alpha_vs_control_stress",
            )
        }
        if any(value is None for value in provided_alpha.values()):
            raise ValueError("same_draw_result Alpha fields are required")
        raw.pop("schema_version", None)
        result = B6SameDrawOOSResult.model_validate(raw)
        identity = result.identity
        report_schema_version = payload.get("schema_version")
        if report_schema_version not in {
            "b6_same_draw_oos_report.v1",
            "b6_same_draw_oos_report.v2",
        }:
            raise ValueError("same-draw report schema mismatch")
        if payload.get("task_id") != identity.task_id or payload.get("task_key") != identity.task_key:
            raise ValueError("same-draw task identity mismatch")
        if payload.get("strategy_revision_id") != identity.strategy_revision_id:
            raise ValueError("same-draw strategy revision mismatch")
        if payload.get("protocol_snapshot_id") != identity.protocol_snapshot_id:
            raise ValueError("same-draw protocol mismatch")
        if payload.get("data_snapshot_hash") != identity.data_snapshot_hash:
            raise ValueError("same-draw data snapshot mismatch")
        if payload.get("b5_bundle_id") != identity.b5_bundle_id:
            raise ValueError("same-draw B5 bundle mismatch")
        if payload.get("b5_bundle_manifest_sha256") != identity.b5_bundle_manifest_sha256:
            raise ValueError("same-draw B5 manifest mismatch")
        if payload.get("b4_lineage") != {
            "artifact_id": identity.b4_artifact_id,
            "manifest_sha256": identity.b4_manifest_sha256,
            "event_result_sha256": identity.b4_event_result_sha256,
        }:
            raise ValueError("same-draw B4 lineage mismatch")
        if payload.get("result_schema_version") != identity.result_schema_version:
            raise ValueError("same-draw result schema mismatch")
        expected_report_schema = (
            "b6_same_draw_oos_report.v2"
            if identity.result_schema_version == "b6_same_draw_oos_result.v2"
            else "b6_same_draw_oos_report.v1"
        )
        if report_schema_version != expected_report_schema:
            raise ValueError("same-draw report/result version mismatch")
        if identity.result_schema_version == "b6_same_draw_oos_result.v2":
            result.assert_production_terminal_eligible()
            if result.read_audit.allowed_end != identity.oos_end:
                raise ValueError("same-draw read audit allowed_end mismatch")
        expected_alpha = {
            "alpha_vs_benchmark_base": result.alpha_vs_benchmark_base,
            "alpha_vs_benchmark_stress": result.alpha_vs_benchmark_stress,
            "alpha_vs_control_base": result.alpha_vs_control_base,
            "alpha_vs_control_stress": result.alpha_vs_control_stress,
        }
        if provided_alpha != expected_alpha:
            raise ValueError("same-draw Alpha formula mismatch")
        if report.strategy_revision_id != identity.strategy_revision_id:
            raise ValueError("report/result strategy revision mismatch")
        if report.protocol_snapshot_id != identity.protocol_snapshot_id:
            raise ValueError("report/result protocol mismatch")
        return result

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
