"""B5 Gate Explanation Builder Tests."""
import unittest
from datetime import datetime

from backend.services.gate_explanation_builder import GateExplanationBuilder
from contracts.strategy import PrototypeGateResultV2


class TestGateExplanationBuilder(unittest.TestCase):
    """Test Gate explanation builder."""
    
    def setUp(self):
        self.builder = GateExplanationBuilder()
    
    def test_explanation_references_report_and_gate(self):
        """Explanation must reference report_id and gate_result_id."""
        gate_result = PrototypeGateResultV2(
            gate_result_id="gate_001",
            report_id="rpt_001",
            strategy_revision_id="strat_001",
            protocol_snapshot_id="proto_001",
            verdict="rejected",
            checks_json='{"future_data_violations": 2}',
            blocking_issues=("Future data violations",),
            warnings=(),
            strategy_config_hash="config_001",
            data_snapshot_hash="data_001",
            gate_criteria_hash="gate_001",
            oos_draw_index=1,
            shared_oos_window_id="oos_001",
            multiple_comparison_flag=False,
            generated_at=datetime.now(),
            gate_result_hash="hash_001",
        )
        
        explanation = self.builder.build_explanation(
            report_id="rpt_001",
            gate_result=gate_result,
        )
        
        self.assertEqual(explanation.report_id, "rpt_001")
        self.assertEqual(explanation.gate_result_id, "gate_001")
    
    def test_explanation_cannot_override_gate_verdict(self):
        """Explanation cannot change Gate verdict."""
        gate_result = PrototypeGateResultV2(
            gate_result_id="gate_001",
            report_id="rpt_001",
            strategy_revision_id="strat_001",
            protocol_snapshot_id="proto_001",
            verdict="rejected",
            checks_json="{}",
            blocking_issues=("Test issue",),
            warnings=(),
            strategy_config_hash="config_001",
            data_snapshot_hash="data_001",
            gate_criteria_hash="gate_001",
            oos_draw_index=1,
            shared_oos_window_id="oos_001",
            multiple_comparison_flag=False,
            generated_at=datetime.now(),
            gate_result_hash="hash_001",
        )
        
        explanation = self.builder.build_explanation(
            report_id="rpt_001",
            gate_result=gate_result,
        )
        
        # Explanation summary must reflect Gate verdict
        self.assertIn("rejected", explanation.plain_summary.lower())
        # Explanation cannot suggest opposite verdict
        self.assertNotIn("passed", explanation.plain_summary.lower())
        self.assertNotIn("candidate", explanation.plain_summary.lower())
    
    def test_explanation_contains_no_buy_sell_instruction(self):
        """Explanation must not contain buy/sell instructions."""
        gate_result = PrototypeGateResultV2(
            gate_result_id="gate_001",
            report_id="rpt_001",
            strategy_revision_id="strat_001",
            protocol_snapshot_id="proto_001",
            verdict="candidate_for_prototype_passed",
            checks_json="{}",
            blocking_issues=(),
            warnings=(),
            strategy_config_hash="config_001",
            data_snapshot_hash="data_001",
            gate_criteria_hash="gate_001",
            oos_draw_index=1,
            shared_oos_window_id="oos_001",
            multiple_comparison_flag=False,
            generated_at=datetime.now(),
            gate_result_hash="hash_001",
        )
        
        explanation = self.builder.build_explanation(
            report_id="rpt_001",
            gate_result=gate_result,
        )
        
        forbidden_terms = ["buy", "sell", "action plan", "entry price", "target price", "stop loss"]
        summary_lower = explanation.plain_summary.lower()
        
        for term in forbidden_terms:
            self.assertNotIn(term, summary_lower)
    
    def test_explanation_does_not_ask_user_for_technical_parameters(self):
        """Explanation must not ask user for technical parameters."""
        gate_result = PrototypeGateResultV2(
            gate_result_id="gate_001",
            report_id="rpt_001",
            strategy_revision_id="strat_001",
            protocol_snapshot_id="proto_001",
            verdict="needs_review",
            checks_json="{}",
            blocking_issues=(),
            warnings=("Low trade count",),
            strategy_config_hash="config_001",
            data_snapshot_hash="data_001",
            gate_criteria_hash="gate_001",
            oos_draw_index=1,
            shared_oos_window_id="oos_001",
            multiple_comparison_flag=False,
            generated_at=datetime.now(),
            gate_result_hash="hash_001",
        )
        
        explanation = self.builder.build_explanation(
            report_id="rpt_001",
            gate_result=gate_result,
        )
        
        forbidden_questions = [
            "sharpe ratio",
            "threshold",
            "stop loss",
            "position size",
            "max drawdown",
            "how much",
            "what parameter",
        ]
        summary_lower = explanation.plain_summary.lower()
        
        for question in forbidden_questions:
            self.assertNotIn(question, summary_lower)
    
    def test_explanation_fails_when_deterministic_evidence_missing(self):
        """Explanation must fail loud when Gate/report evidence is missing."""
        # Missing gate_result
        with self.assertRaises(ValueError) as ctx:
            self.builder.build_explanation(
                report_id="rpt_001",
                gate_result=None,
            )
        
        self.assertIn("gate_result", str(ctx.exception).lower())
    
    def test_explanation_has_no_llm_dependency_or_llm_is_summary_only(self):
        """Explanation builder must not import LLM, or LLM is summary-only after deterministic Gate."""
        import backend.services.gate_explanation_builder as builder_module
        import inspect
        
        source = inspect.getsource(builder_module)
        
        # Check no LLM imports (for MVP)
        # If LLM is used in future, it must be post-Gate summary only
        forbidden_imports = ["import openai", "from openai", "import anthropic", "from anthropic"]
        for forbidden in forbidden_imports:
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
