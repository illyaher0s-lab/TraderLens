import unittest

from backend.db.research import ResearchDB
from backend.services.hypothesis_builder import HypothesisBuilder
from backend.services.strategy_template_library import StrategyTemplateLibrary
from contracts.stable import PrototypeGateResult
from contracts.strategy import PrototypeGateResultV2


class TestB2Compatibility(unittest.TestCase):
    def test_b2_does_not_modify_research_db_schema(self):
        db = ResearchDB(":memory:")
        tables = {
            row["name"]
            for row in db.conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        
        # B2 tables should not appear in ResearchDB
        self.assertNotIn("strategy_template_definitions", tables)
        self.assertNotIn("strategy_drafts", tables)
        self.assertNotIn("hypothesis_repair_attempts", tables)

    def test_b2_gate_v2_distinct_from_stable_gate(self):
        # B1 introduced PrototypeGateResultV2, stable gate unchanged
        self.assertIsNot(PrototypeGateResult, PrototypeGateResultV2)
        
        # V2 has verdict field, stable does not
        self.assertIn("verdict", PrototypeGateResultV2.model_fields)
        self.assertNotIn("verdict", PrototypeGateResult.model_fields)

    def test_b2_builder_does_not_call_strategy_core(self):
        # B2 does not call prototype_gate or backtest
        from backend.services import hypothesis_builder
        import inspect
        
        source = inspect.getsource(hypothesis_builder)
        self.assertNotIn("prototype_gate", source)
        self.assertNotIn("run_backtest", source)
        self.assertNotIn("strategy_core", source)

    def test_b2_template_library_is_append_only(self):
        library = StrategyTemplateLibrary()
        
        # No mutation methods
        self.assertFalse(hasattr(library, "add_template"))
        self.assertFalse(hasattr(library, "update_template"))
        self.assertFalse(hasattr(library, "delete_template"))
        self.assertFalse(hasattr(library, "register_template"))

    def test_b2_llm_contract_forbids_parameters(self):
        from backend.services.hypothesis_builder_types import LLMTemplateSelection
        from pydantic import ValidationError
        
        # LLM cannot set entry params
        with self.assertRaises(ValidationError):
            LLMTemplateSelection(
                strategy_template_id="theme_momentum_breakout_v1",
                template_selection_reason="reason",
                entry_params={"breakout_days": 50},
            )

    def test_b2_validator_forbids_evidence_in_trade_rules(self):
        from backend.services.strategy_config_validator import EVIDENCE_EVENT_TERMS
        
        # Evidence terms are explicitly forbidden
        self.assertIn("announcement", EVIDENCE_EVENT_TERMS)
        self.assertIn("disclosure", EVIDENCE_EVENT_TERMS)
        self.assertIn("公告", EVIDENCE_EVENT_TERMS)

    def test_b2_repair_loop_has_hard_max_2(self):
        from backend.services.hypothesis_repair_loop import HypothesisRepairLoop
        
        loop = HypothesisRepairLoop(None, max_repairs=2)
        self.assertEqual(loop.max_repairs, 2)


if __name__ == "__main__":
    unittest.main()
