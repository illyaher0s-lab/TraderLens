import unittest

from pydantic import ValidationError

from backend.services.hypothesis_builder_types import (
    HypothesisBuilderInput,
    LLMTemplateSelection,
)
from contracts.strategy import BacktestUniverseSpec
from tests.b1_fixtures import make_backtest_universe


class TestLLMTemplateSelectionContract(unittest.TestCase):
    def test_llm_selection_accepts_only_template_id_reason_and_unmapped_elements(self):
        selection = LLMTemplateSelection(
            strategy_template_id="theme_momentum_breakout_v1",
            template_selection_reason="Theme matches momentum hypothesis",
            unmapped_hypothesis_elements=("specific_company_events",),
        )
        self.assertEqual(selection.strategy_template_id, "theme_momentum_breakout_v1")
        self.assertEqual(len(selection.unmapped_hypothesis_elements), 1)

    def test_llm_selection_rejects_entry_parameters(self):
        with self.assertRaises(ValidationError):
            LLMTemplateSelection(
                strategy_template_id="theme_momentum_breakout_v1",
                template_selection_reason="reason",
                entry_params={"breakout_days": 50},
            )

    def test_llm_selection_rejects_exit_parameters(self):
        with self.assertRaises(ValidationError):
            LLMTemplateSelection(
                strategy_template_id="theme_momentum_breakout_v1",
                template_selection_reason="reason",
                exit_params={"stop_loss": 5},
            )

    def test_llm_selection_rejects_risk_parameters(self):
        with self.assertRaises(ValidationError):
            LLMTemplateSelection(
                strategy_template_id="theme_momentum_breakout_v1",
                template_selection_reason="reason",
                risk_params={"max_positions": 10},
            )

    def test_llm_selection_rejects_status_hash_gate_and_budget_fields(self):
        with self.assertRaises(ValidationError):
            LLMTemplateSelection(
                strategy_template_id="theme_momentum_breakout_v1",
                template_selection_reason="reason",
                status="draft",
            )
        
        with self.assertRaises(ValidationError):
            LLMTemplateSelection(
                strategy_template_id="theme_momentum_breakout_v1",
                template_selection_reason="reason",
                hash="abc123",
            )
        
        with self.assertRaises(ValidationError):
            LLMTemplateSelection(
                strategy_template_id="theme_momentum_breakout_v1",
                template_selection_reason="reason",
                gate_verdict="pass",
            )
        
        with self.assertRaises(ValidationError):
            LLMTemplateSelection(
                strategy_template_id="theme_momentum_breakout_v1",
                template_selection_reason="reason",
                oos_budget=3,
            )

    def test_llm_selection_rejects_oos_dates(self):
        with self.assertRaises(ValidationError):
            LLMTemplateSelection(
                strategy_template_id="theme_momentum_breakout_v1",
                template_selection_reason="reason",
                oos_start="2025-01-01",
            )
        
        with self.assertRaises(ValidationError):
            LLMTemplateSelection(
                strategy_template_id="theme_momentum_breakout_v1",
                template_selection_reason="reason",
                oos_end="2025-12-31",
            )

    def test_llm_selection_rejects_multiple_templates(self):
        with self.assertRaises(ValidationError):
            LLMTemplateSelection(
                strategy_template_id="theme_momentum_breakout_v1",
                template_selection_reason="reason",
                alternative_templates=["relative_strength_rotation_v1"],
            )


class TestHypothesisBuilderInput(unittest.TestCase):
    def test_input_requires_strategy_revision_id(self):
        universe = make_backtest_universe()
        
        with self.assertRaisesRegex(ValidationError, "strategy_revision_id"):
            HypothesisBuilderInput(
                theme_id="theme_001",
                hypothesis_id="hyp_001",
                hypothesis_source_snapshot_id="snapshot_001",
                hypothesis_type="theme_momentum",
                hypothesis_text="Text",
                rule_candidates={},
                evidence_summary=None,
                backtest_universe_spec=universe,
                strategy_revision_id="",
            )

    def test_input_requires_backtest_universe_spec_type(self):
        with self.assertRaises(ValidationError):
            HypothesisBuilderInput(
                theme_id="theme_001",
                hypothesis_id="hyp_001",
                hypothesis_source_snapshot_id="snapshot_001",
                hypothesis_type="theme_momentum",
                hypothesis_text="Text",
                rule_candidates={},
                evidence_summary=None,
                backtest_universe_spec={"symbols": ["300750.SZ"]},
                strategy_revision_id="rev_001",
            )


if __name__ == "__main__":
    unittest.main()
