"""Gate Explanation Builder - Plain-language Gate explanation."""
from __future__ import annotations

from datetime import datetime

from backend.services.b5_oos_types import ExplanationSnapshot
from contracts.strategy import PrototypeGateResultV2


class GateExplanationBuilder:
    """
    Gate explanation builder.
    
    Requirements:
    - Plain-language text explaining Gate verdict
    - Cannot override verdict
    - Cannot generate buy/sell instructions
    - Cannot ask user for technical parameters
    - Must bind to report_id and gate_result_id
    - Must fail loud if deterministic evidence missing
    - No LLM dependency (MVP uses template-based explanation)
    """
    
    def build_explanation(
        self,
        report_id: str,
        gate_result: PrototypeGateResultV2 | None,
    ) -> ExplanationSnapshot:
        """
        Build plain-language explanation from Gate result.
        
        Args:
            report_id: Report ID
            gate_result: Gate result (required)
        
        Returns:
            ExplanationSnapshot with plain summary
        
        Raises:
            ValueError: If gate_result is missing
        """
        # Fail loud if evidence missing
        if gate_result is None:
            raise ValueError("gate_result is required (cannot build explanation without deterministic Gate result)")

        if report_id != gate_result.report_id:
            raise ValueError(
                f"report_id mismatch: explanation input has '{report_id}', "
                f"Gate result has '{gate_result.report_id}'"
            )
        
        # Generate plain summary based on verdict
        plain_summary = self._generate_plain_summary(gate_result)
        
        # Extract deterministic evidence references
        deterministic_evidence = self._extract_evidence_references(gate_result)
        if not deterministic_evidence:
            raise ValueError(
                "Deterministic evidence is required to build Gate explanation"
            )
        
        # Build explanation snapshot
        explanation_id = f"expl_{gate_result.gate_result_id}"
        
        return ExplanationSnapshot(
            explanation_id=explanation_id,
            report_id=report_id,
            gate_result_id=gate_result.gate_result_id,
            plain_summary=plain_summary,
            deterministic_evidence=deterministic_evidence,
            generated_at=datetime.now(),
        )
    
    def _generate_plain_summary(self, gate_result: PrototypeGateResultV2) -> str:
        """
        Generate plain-language summary based on Gate verdict.
        
        Template-based (no LLM in MVP).
        
        Returns:
            Plain summary text
        """
        verdict = gate_result.verdict
        same_draw_result = None
        read_audit_verified = False
        try:
            import json

            checks = json.loads(gate_result.checks_json)
            candidate = checks.get("same_draw_result")
            if isinstance(candidate, dict):
                same_draw_result = candidate
            read_audit_verified = checks.get("same_draw_read_audit_verified") is True
        except (json.JSONDecodeError, AttributeError):
            same_draw_result = None
        
        if verdict == "rejected":
            # Summarize blocking issues
            issues = gate_result.blocking_issues
            if issues:
                issues_text = "; ".join(issues[:3])  # First 3 issues
                summary = (
                    f"Strategy rejected due to blocking issues: {issues_text}. "
                    f"This strategy cannot proceed to prototype testing."
                )
            else:
                summary = "Strategy rejected. Cannot proceed to prototype testing."
        
        elif verdict == "needs_review":
            # Summarize warnings
            warnings = gate_result.warnings
            if warnings:
                warnings_text = "; ".join(warnings[:3])
                summary = (
                    f"Strategy needs manual review: {warnings_text}. "
                    f"Additional analysis required before deciding on prototype testing."
                )
            else:
                summary = "Strategy needs manual review before proceeding."
        
        elif verdict == "candidate_for_prototype_passed":
            summary = (
                "Strategy passed OOS validation Gate checks and is a candidate for prototype testing. "
                "Human confirmation required before promotion to prototype_passed status."
            )
        
        else:
            summary = f"Gate verdict: {verdict}"
        
        if same_draw_result is not None:
            summary += (
                " Same-draw results show strategy net return "
                f"base={same_draw_result['strategy_net_return_base']}, "
                f"stress={same_draw_result['strategy_net_return_stress']}; "
                "market benchmark net return "
                f"base={same_draw_result['benchmark_net_return_base']}, "
                f"stress={same_draw_result['benchmark_net_return_stress']}; "
                "same-universe control return "
                f"base={same_draw_result['same_universe_control_return_base']}, "
                f"stress={same_draw_result['same_universe_control_return_stress']}. "
                "Arithmetic excess Alpha vs benchmark is "
                f"base={same_draw_result['alpha_vs_benchmark_base']}, "
                f"stress={same_draw_result['alpha_vs_benchmark_stress']}; "
                "vs control is "
                f"base={same_draw_result['alpha_vs_control_base']}, "
                f"stress={same_draw_result['alpha_vs_control_stress']}. "
                "These are arithmetic excess measures, not causal attribution."
            )
            if read_audit_verified:
                summary += " Read audit verified for the same-draw execution envelope."

        return summary
    
    def _extract_evidence_references(self, gate_result: PrototypeGateResultV2) -> tuple[str, ...]:
        """
        Extract deterministic evidence references from Gate result.
        
        Returns:
            Tuple of check IDs or report field references
        """
        import json
        
        # Parse checks_json to get check IDs
        try:
            checks = json.loads(gate_result.checks_json)
            evidence = tuple(checks.keys())
        except (json.JSONDecodeError, AttributeError):
            evidence = ()
        
        return evidence
