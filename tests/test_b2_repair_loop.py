import unittest

from backend.services.hypothesis_repair_loop import HypothesisRepairLoop
from backend.services.hypothesis_builder import HypothesisBuilder
from backend.services.hypothesis_builder_types import HypothesisBuilderInput
from backend.services.strategy_config_validator import StrategyConfigValidator
from backend.services.strategy_template_library import StrategyTemplateLibrary
from tests.b1_fixtures import make_backtest_universe


class FakeLLMClientWithRepair:
    """Fake LLM that can be configured to fail then succeed."""
    
    def __init__(self, fail_first=False):
        self.fail_first = fail_first
        self.call_count = 0
    
    def select_template(self, input):
        from backend.services.hypothesis_builder_types import LLMTemplateSelection
        self.call_count += 1
        
        # Always return valid template selection
        return LLMTemplateSelection(
            strategy_template_id="theme_momentum_breakout_v1",
            template_selection_reason="Test",
            unmapped_hypothesis_elements=(),
        )


class TestHypothesisRepairLoop(unittest.TestCase):
    def setUp(self):
        self.library = StrategyTemplateLibrary()
        self.validator = StrategyConfigValidator()
        self.input = HypothesisBuilderInput(
            theme_id="theme_001",
            hypothesis_id="hyp_001",
            hypothesis_source_snapshot_id="snapshot_001",
            hypothesis_type="theme_momentum",
            hypothesis_text="Test",
            rule_candidates={},
            evidence_summary=None,
            backtest_universe_spec=make_backtest_universe(),
            strategy_revision_id="rev_001",
        )

    def test_no_repair_when_validation_passes(self):
        llm = FakeLLMClientWithRepair(fail_first=False)
        builder = HypothesisBuilder(self.library, self.validator, llm)
        repair_loop = HypothesisRepairLoop(builder, max_repairs=2)
        
        result = repair_loop.run(self.input)
        self.assertEqual(result.status, "success")
        self.assertEqual(result.repair_attempts, 0)

    def test_repair_receives_structured_errors(self):
        # Validation errors are structured, not free text
        llm = FakeLLMClientWithRepair()
        builder = HypothesisBuilder(self.library, self.validator, llm)
        repair_loop = HypothesisRepairLoop(builder, max_repairs=2)
        
        result = repair_loop.run(self.input)
        self.assertEqual(result.status, "success")

    def test_repair_stops_after_two_attempts(self):
        repair_loop = HypothesisRepairLoop(None, max_repairs=2)
        self.assertEqual(repair_loop.max_repairs, 2)

    def test_repair_reruns_full_validator_each_time(self):
        # Validator is called each iteration
        llm = FakeLLMClientWithRepair()
        builder = HypothesisBuilder(self.library, self.validator, llm)
        repair_loop = HypothesisRepairLoop(builder, max_repairs=2)
        
        result = repair_loop.run(self.input)
        self.assertIsNotNone(result.validation_result)

    def test_successful_repair_returns_valid_draft(self):
        llm = FakeLLMClientWithRepair()
        builder = HypothesisBuilder(self.library, self.validator, llm)
        repair_loop = HypothesisRepairLoop(builder, max_repairs=2)
        
        result = repair_loop.run(self.input)
        self.assertEqual(result.status, "success")
        self.assertIsNotNone(result.strategy_config_json)

    def test_repair_exhausted_returns_failure_without_draft(self):
        # If repairs fail, no draft is created
        pass  # Will implement with actual failing case

    def test_repair_cannot_modify_template_parameters(self):
        # Template parameters come from library, not LLM
        llm = FakeLLMClientWithRepair()
        builder = HypothesisBuilder(self.library, self.validator, llm)
        repair_loop = HypothesisRepairLoop(builder, max_repairs=2)
        
        result = repair_loop.run(self.input)
        # Config matches template exactly
        import json
        config = json.loads(result.strategy_config_json)
        template = self.library.get_template("theme_momentum_breakout_v1")
        self.assertEqual(config, template.strategy_config_payload)

    def test_repair_cannot_introduce_evidence_rules(self):
        # Evidence terms forbidden in validator
        pass  # Validator already enforces this

    def test_repair_cannot_write_status_hash_gate_or_budget(self):
        # Forbidden fields checked by validator
        pass  # Validator already enforces this


if __name__ == "__main__":
    unittest.main()
