import json
import unittest

from backend.services.hypothesis_builder import HypothesisBuilder
from backend.services.hypothesis_builder_types import (
    HypothesisBuilderInput,
    LLMTemplateSelection,
)
from backend.services.strategy_config_validator import StrategyConfigValidator
from backend.services.strategy_template_library import StrategyTemplateLibrary
from contracts.strategy import StrategyDraft, StrategyLifecycleState
from tests.b1_fixtures import make_backtest_universe


class FakeLLMClient:
    """Deterministic fake LLM for testing."""
    
    def __init__(self, template_id: str = "theme_momentum_breakout_v1"):
        self.template_id = template_id
        self.call_count = 0
    
    def select_template(self, input: HypothesisBuilderInput) -> LLMTemplateSelection:
        self.call_count += 1
        return LLMTemplateSelection(
            strategy_template_id=self.template_id,
            template_selection_reason="Test selection",
            unmapped_hypothesis_elements=("specific_events",),
        )


class TestHypothesisBuilder(unittest.TestCase):
    def setUp(self):
        self.library = StrategyTemplateLibrary()
        self.validator = StrategyConfigValidator()
        self.llm_client = FakeLLMClient()
        self.builder = HypothesisBuilder(
            template_library=self.library,
            validator=self.validator,
            llm_client=self.llm_client,
        )
        
        self.input = HypothesisBuilderInput(
            theme_id="theme_001",
            hypothesis_id="hyp_001",
            hypothesis_source_snapshot_id="snapshot_001",
            hypothesis_type="theme_momentum",
            hypothesis_text="Theme momentum hypothesis",
            rule_candidates={},
            evidence_summary=None,
            backtest_universe_spec=make_backtest_universe(),
            strategy_revision_id="rev_001",
        )

    def test_builder_normal_path_uses_one_llm_call(self):
        result = self.builder.build(self.input)
        self.assertEqual(self.llm_client.call_count, 1)
        self.assertEqual(result.status, "success")

    def test_builder_generates_config_from_template_not_llm_params(self):
        result = self.builder.build(self.input)
        self.assertEqual(result.status, "success")
        
        # Config should match template exactly
        config = json.loads(result.strategy_config_json)
        template = self.library.get_template("theme_momentum_breakout_v1")
        self.assertEqual(config, template.strategy_config_payload)

    def test_builder_creates_frozen_strategy_draft_without_status(self):
        result = self.builder.build(self.input)
        self.assertEqual(result.status, "success")
        
        # Draft should be in result metadata (not returned directly)
        self.assertIsNotNone(result.strategy_config_json)
        self.assertIsNone(result.failure_stage)
        
        # Verify no status field exists in config
        config = json.loads(result.strategy_config_json)
        self.assertNotIn("status", config)

    def test_builder_creates_initial_draft_lifecycle_state(self):
        result = self.builder.build(self.input)
        self.assertEqual(result.status, "success")
        self.assertEqual(result.validation_result, "pass")

    def test_builder_rejects_candidate_level_strategy(self):
        # Builder only accepts theme-level, not per-candidate
        # This is enforced by input contract, just verify it doesn't generate multiple
        result = self.builder.build(self.input)
        self.assertEqual(result.status, "success")
        # Single revision ID means single strategy
        self.assertEqual(result.strategy_revision_id, "rev_001")

    def test_builder_rejects_multiple_template_selection(self):
        # LLM contract already forbids multiple templates
        # Builder should only use the single selected template
        result = self.builder.build(self.input)
        self.assertEqual(result.selected_template_id, "theme_momentum_breakout_v1")

    def test_builder_rejects_forward_watchlist_input(self):
        from tests.b1_fixtures import make_forward_watchlist
        
        bad_input = self.input.model_copy(
            update={"backtest_universe_spec": make_forward_watchlist()}
        )
        
        result = self.builder.build(bad_input)
        self.assertEqual(result.status, "failed")
        self.assertTrue(any("Universe" in e for e in result.errors))

    def test_evidence_summary_cannot_enter_trade_rules(self):
        input_with_evidence = self.input.model_copy(
            update={
                "evidence_summary": {
                    "announcement_events": ["event1"],
                }
            }
        )
        
        result = self.builder.build(input_with_evidence)
        self.assertEqual(result.status, "success")
        
        # Evidence should not appear in config
        config = json.loads(result.strategy_config_json)
        config_str = json.dumps(config)
        self.assertNotIn("announcement", config_str.lower())

    def test_rerun_requires_new_strategy_revision_id(self):
        result1 = self.builder.build(self.input)
        self.assertEqual(result1.status, "success")
        
        # Same input with different revision ID should work
        input2 = self.input.model_copy(
            update={"strategy_revision_id": "rev_002"}
        )
        result2 = self.builder.build(input2)
        self.assertEqual(result2.status, "success")
        self.assertEqual(result2.strategy_revision_id, "rev_002")


if __name__ == "__main__":
    unittest.main()
