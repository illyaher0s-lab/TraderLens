"""Cost Stress Runner - Deterministic base/stress cost orchestration."""
from __future__ import annotations

from backend.services.b5_oos_types import BaseCostResult, StressCostResult


class CostStressRunner:
    """
    Deterministic cost stress orchestration.
    
    Requirements:
    - Base and stress cost results must be explicitly present
    - Stress cost must be stricter than base (higher slippage/commission/impact)
    - Runtime cannot lower stress cost parameters
    - Missing stress cost blocks candidate_for_prototype_passed
    - No LLM dependency
    """
    
    # System-frozen stress multiplier (cannot be lowered by user/API/LLM)
    SYSTEM_STRESS_MULTIPLIER = 2.0
    
    def validate_cost_results(
        self,
        base_result: BaseCostResult | None,
        stress_result: StressCostResult | None,
    ) -> None:
        """
        Validate base and stress cost results are present.
        
        Raises:
            ValueError: If either result is missing
        """
        if base_result is None:
            raise ValueError("Base cost result is required (cannot be None)")
        
        if stress_result is None:
            raise ValueError("Stress cost result is required (cannot be None)")
    
    def validate_stress_cost_strictness(
        self,
        base_slippage_bps: float,
        stress_slippage_bps: float,
    ) -> None:
        """
        Validate stress cost is stricter than base cost.
        
        Raises:
            ValueError: If stress cost is lower than base
        """
        if stress_slippage_bps < base_slippage_bps:
            raise ValueError(
                f"Stress cost cannot be lower than base cost: "
                f"base_slippage={base_slippage_bps} bps, "
                f"stress_slippage={stress_slippage_bps} bps. "
                f"Stress must be >= base."
            )
    
    def run_stress_test(
        self,
        base_slippage_bps: float,
        user_stress_multiplier: float | None = None,
    ) -> dict:
        """
        Run stress test with system-frozen stress multiplier.
        
        Args:
            base_slippage_bps: Base slippage in bps
            user_stress_multiplier: User-provided multiplier (rejected if < system baseline)
        
        Returns:
            dict with stress test result
        
        Raises:
            ValueError: If user_stress_multiplier attempts to lower stress cost
        """
        if user_stress_multiplier is not None:
            if user_stress_multiplier < self.SYSTEM_STRESS_MULTIPLIER:
                raise ValueError(
                    f"Runtime cannot lower stress cost multiplier: "
                    f"system baseline={self.SYSTEM_STRESS_MULTIPLIER}, "
                    f"user_provided={user_stress_multiplier}. "
                    f"User/LLM/API cannot pass parameters that lower stress cost."
                )
        
        # Use system-frozen multiplier
        stress_multiplier = self.SYSTEM_STRESS_MULTIPLIER
        stress_slippage_bps = base_slippage_bps * stress_multiplier
        
        return {
            "base_slippage_bps": base_slippage_bps,
            "stress_slippage_bps": stress_slippage_bps,
            "stress_multiplier": stress_multiplier,
        }
    
    def check_stress_cost_gate_impact(
        self,
        stress_result: StressCostResult | None,
    ) -> dict:
        """
        Check how missing stress cost impacts Gate verdict.
        
        Missing stress cost blocks candidate_for_prototype_passed.
        
        Returns:
            dict with max_verdict constraint
        """
        if stress_result is None:
            return {
                "max_verdict": "needs_review",
                "reason": "Missing stress cost result blocks candidate_for_prototype_passed",
            }
        
        # Stress result present - no verdict constraint from this check
        return {
            "max_verdict": "candidate_for_prototype_passed",
            "reason": "Stress cost result present",
        }
