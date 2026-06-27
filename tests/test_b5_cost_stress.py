"""B5 Cost Stress Runner Tests."""
import unittest

from backend.services.cost_stress_runner import CostStressRunner
from backend.services.b5_oos_types import BaseCostResult, StressCostResult


class TestCostStressRunner(unittest.TestCase):
    """Test cost stress orchestration."""
    
    def test_base_and_stress_cost_results_are_required(self):
        """Base and stress cost results must be explicitly present."""
        runner = CostStressRunner()
        
        # Missing base/stress results should be explicit, not silent 0
        with self.assertRaises((ValueError, AttributeError)):
            runner.validate_cost_results(base_result=None, stress_result=None)
    
    def test_stress_cost_cannot_be_lower_than_system_baseline(self):
        """Stress cost must be stricter than base cost."""
        runner = CostStressRunner()
        
        # Stress cost lower than base should be rejected
        with self.assertRaises(ValueError) as ctx:
            runner.validate_stress_cost_strictness(
                base_slippage_bps=5.0,
                stress_slippage_bps=3.0  # Lower than base - invalid
            )
        self.assertIn("stress", str(ctx.exception).lower())
    
    def test_runtime_lowering_stress_cost_rejected(self):
        """Runtime attempt to lower stress cost is rejected."""
        runner = CostStressRunner()
        
        # User/LLM/API cannot pass parameters that lower stress cost
        with self.assertRaises(ValueError) as ctx:
            runner.run_stress_test(
                base_slippage_bps=5.0,
                user_stress_multiplier=0.5  # Attempt to lower - invalid
            )
        self.assertIn("cannot lower", str(ctx.exception).lower())
    
    def test_missing_stress_cost_blocks_candidate(self):
        """Missing stress cost result blocks candidate_for_prototype_passed."""
        runner = CostStressRunner()
        
        result = runner.check_stress_cost_gate_impact(stress_result=None)
        
        self.assertIn(result["max_verdict"], ["rejected", "needs_review"])
        self.assertNotEqual(result["max_verdict"], "candidate_for_prototype_passed")
    
    def test_cost_stress_runner_has_no_llm_dependency(self):
        """Cost stress runner must not import or call LLM."""
        import backend.services.cost_stress_runner as runner_module
        import inspect
        
        source = inspect.getsource(runner_module)
        
        # Check no LLM imports
        forbidden_imports = ["import openai", "from openai", "import anthropic", "from anthropic"]
        for forbidden in forbidden_imports:
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
