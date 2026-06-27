"""B5 Control Comparison Tests."""
import unittest

from backend.services.control_comparison import ControlComparison


class TestControlComparison(unittest.TestCase):
    """Test benchmark and control comparison."""
    
    def test_absolute_profit_alone_cannot_pass(self):
        """Gate cannot pass on absolute profit alone without benchmark/control."""
        comp = ControlComparison()
        
        result = comp.check_absolute_profit_only(
            strategy_return=0.30,  # 30% return
            has_benchmark_comparison=False,
            has_control_comparison=False,
        )
        
        self.assertNotEqual(result["verdict"], "candidate_for_prototype_passed")
        self.assertIn("benchmark", result["reason"].lower())
    
    def test_benchmark_comparison_required(self):
        """Benchmark comparison is required for candidate verdict."""
        comp = ControlComparison()
        
        result = comp.validate_benchmark_comparison(benchmark_comparison=None)
        
        self.assertFalse(result["can_candidate"])
        self.assertIn("benchmark", result["reason"].lower())
    
    def test_same_universe_control_required(self):
        """Same-universe control comparison is required."""
        comp = ControlComparison()
        
        result = comp.validate_control_comparison(control_comparison=None)
        
        self.assertFalse(result["can_candidate"])
        self.assertIn("control", result["reason"].lower())
    
    def test_beta_dominated_result_blocks_candidate(self):
        """Beta-dominated result (pure market tracking) blocks candidate."""
        comp = ControlComparison()
        
        result = comp.check_beta_domination(
            strategy_return=0.15,
            benchmark_return=0.14,
            correlation=0.95,  # Very high correlation
            beta=1.02,  # Near 1.0
        )
        
        self.assertTrue(result["is_beta_dominated"])
        self.assertFalse(result["can_candidate"])
    
    def test_single_symbol_concentration_blocks_candidate(self):
        """Single symbol contributing >50% blocks candidate."""
        comp = ControlComparison()
        
        result = comp.check_single_symbol_concentration(
            top_symbol_contribution_pct=65.0  # 65% from one symbol
        )
        
        self.assertTrue(result["is_concentrated"])
        self.assertFalse(result["can_candidate"])
    
    def test_single_month_concentration_blocks_candidate(self):
        """Single month contributing >50% blocks candidate."""
        comp = ControlComparison()
        
        result = comp.check_single_month_concentration(
            top_month_contribution_pct=70.0  # 70% from one month
        )
        
        self.assertTrue(result["is_concentrated"])
        self.assertFalse(result["can_candidate"])
    
    def test_control_comparison_has_no_llm_dependency(self):
        """Control comparison must not import or call LLM."""
        import backend.services.control_comparison as comp_module
        import inspect
        
        source = inspect.getsource(comp_module)
        
        # Check no LLM imports
        forbidden_imports = ["import openai", "from openai", "import anthropic", "from anthropic"]
        for forbidden in forbidden_imports:
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
