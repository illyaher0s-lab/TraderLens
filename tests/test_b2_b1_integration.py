import unittest

from backend.db.strategy import StrategyDB
from backend.services.hypothesis_builder import HypothesisBuilder
from backend.services.hypothesis_builder_types import HypothesisBuilderInput
from backend.services.strategy_config_validator import StrategyConfigValidator
from backend.services.strategy_template_library import StrategyTemplateLibrary
from contracts.strategy import StrategyDraft, StrategyLifecycleState
from tests.b1_fixtures import make_backtest_universe


class FakeLLM:
    def select_template(self, input):
        from backend.services.hypothesis_builder_types import LLMTemplateSelection
        return LLMTemplateSelection(
            strategy_template_id="theme_momentum_breakout_v1",
            template_selection_reason="Test",
        )


class TestB2B1Integration(unittest.TestCase):
    def setUp(self):
        self.db = StrategyDB(":memory:")
        self.library = StrategyTemplateLibrary()
        self.validator = StrategyConfigValidator()
        self.builder = HypothesisBuilder(self.library, self.validator, FakeLLM())
        
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

    def tearDown(self):
        self.db.close()

    def test_b2_stores_template_definition_via_b1(self):
        # B2 stores template through B1 append-only
        template_def = self.library.to_b1_definition("theme_momentum_breakout_v1")
        self.db.store_strategy_template(template_def)
        
        # Verify stored
        templates = self.db.list_table_names()
        self.assertIn("strategy_template_definitions", templates)

    def test_b2_stores_backtest_universe_spec(self):
        universe = make_backtest_universe()
        self.db.store_backtest_universe(universe)
        
        # Verify immutable
        import sqlite3
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.conn.execute(
                "UPDATE backtest_universe_specs SET universe_spec_id = ? WHERE universe_spec_id = ?",
                ("new_id", "universe_001"),
            )

    def test_b2_stores_strategy_draft_and_initial_lifecycle(self):
        # Create draft and lifecycle from builder result
        result = self.builder.build(self.input)
        self.assertEqual(result.status, "success")
        
        # Convert to B1 contracts
        import json
        from datetime import datetime
        
        template = self.library.get_template(result.selected_template_id)
        template_def = self.library.to_b1_definition(result.selected_template_id)
        universe = self.input.backtest_universe_spec
        
        draft = StrategyDraft(
            strategy_revision_id=result.strategy_revision_id,
            theme_id=self.input.theme_id,
            hypothesis_id=self.input.hypothesis_id,
            strategy_template_id=template.template_id,
            strategy_template_version=template.version,
            strategy_template_hash=template.template_hash,
            hypothesis_source_snapshot_id=self.input.hypothesis_source_snapshot_id,
            backtest_universe_spec_id=universe.universe_spec_id,
            strategy_config_json=result.strategy_config_json,
            sample_split_rule_id="fixed_ratio_70_30",
            created_at=datetime.now(),
            frozen=True,
        )
        
        initial_state = StrategyLifecycleState(
            lifecycle_state_id="lifecycle_001",
            strategy_revision_id=result.strategy_revision_id,
            state_version=1,
            state="draft",
            source_record_id=result.strategy_revision_id,
            recorded_at=datetime.now(),
            recorded_by="system",
            frozen=True,
        )
        
        # Store via B1
        self.db.store_strategy_template(template_def)
        self.db.store_backtest_universe(universe)
        self.db.create_strategy_draft(draft, initial_state)
        
        # Verify stored
        stored_draft = self.db.get_strategy_draft(result.strategy_revision_id)
        self.assertIsNotNone(stored_draft)
        self.assertEqual(stored_draft.strategy_revision_id, result.strategy_revision_id)

    def test_b2_cannot_mutate_draft_after_creation(self):
        import sqlite3
        result = self.builder.build(self.input)
        
        # Store draft
        template = self.library.get_template(result.selected_template_id)
        template_def = self.library.to_b1_definition(result.selected_template_id)
        universe = self.input.backtest_universe_spec
        
        from datetime import datetime
        draft = StrategyDraft(
            strategy_revision_id=result.strategy_revision_id,
            theme_id=self.input.theme_id,
            hypothesis_id=self.input.hypothesis_id,
            strategy_template_id=template.template_id,
            strategy_template_version=template.version,
            strategy_template_hash=template.template_hash,
            hypothesis_source_snapshot_id=self.input.hypothesis_source_snapshot_id,
            backtest_universe_spec_id=universe.universe_spec_id,
            strategy_config_json=result.strategy_config_json,
            sample_split_rule_id="fixed_ratio_70_30",
            created_at=datetime.now(),
            frozen=True,
        )
        
        initial_state = StrategyLifecycleState(
            lifecycle_state_id="lifecycle_001",
            strategy_revision_id=result.strategy_revision_id,
            state_version=1,
            state="draft",
            source_record_id=result.strategy_revision_id,
            recorded_at=datetime.now(),
            recorded_by="system",
            frozen=True,
        )
        
        self.db.store_strategy_template(template_def)
        self.db.store_backtest_universe(universe)
        self.db.create_strategy_draft(draft, initial_state)
        
        # Try to mutate
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.conn.execute(
                "UPDATE strategy_drafts SET theme_id = ? WHERE strategy_revision_id = ?",
                ("new_theme", result.strategy_revision_id),
            )

    def test_b2_cannot_write_prototype_passed_directly(self):
        import sqlite3
        result = self.builder.build(self.input)
        
        # Store draft first
        template = self.library.get_template(result.selected_template_id)
        template_def = self.library.to_b1_definition(result.selected_template_id)
        universe = self.input.backtest_universe_spec
        
        from datetime import datetime
        draft = StrategyDraft(
            strategy_revision_id=result.strategy_revision_id,
            theme_id=self.input.theme_id,
            hypothesis_id=self.input.hypothesis_id,
            strategy_template_id=template.template_id,
            strategy_template_version=template.version,
            strategy_template_hash=template.template_hash,
            hypothesis_source_snapshot_id=self.input.hypothesis_source_snapshot_id,
            backtest_universe_spec_id=universe.universe_spec_id,
            strategy_config_json=result.strategy_config_json,
            sample_split_rule_id="fixed_ratio_70_30",
            created_at=datetime.now(),
            frozen=True,
        )
        
        initial_state = StrategyLifecycleState(
            lifecycle_state_id="lifecycle_001",
            strategy_revision_id=result.strategy_revision_id,
            state_version=1,
            state="draft",
            source_record_id=result.strategy_revision_id,
            recorded_at=datetime.now(),
            recorded_by="system",
            frozen=True,
        )
        
        self.db.store_strategy_template(template_def)
        self.db.store_backtest_universe(universe)
        self.db.create_strategy_draft(draft, initial_state)
        
        # Try to write prototype_passed without promotion
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.conn.execute(
                """
                INSERT INTO strategy_lifecycle_states
                (lifecycle_state_id, strategy_revision_id, state_version,
                 state, source_record_id, payload_json, recorded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "lifecycle_002",
                    result.strategy_revision_id,
                    2,
                    "prototype_passed",
                    "fake_promotion",
                    "{}",
                    datetime.now().isoformat(),
                ),
            )


if __name__ == "__main__":
    unittest.main()
