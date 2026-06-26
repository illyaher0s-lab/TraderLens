import unittest

from backend.db.research import ResearchDB
from contracts.stable import PrototypeGateResult
from contracts.strategy import PrototypeGateResultV2
from strategy_core.prototype_gate import evaluate_prototype_gate


class TestB1Compatibility(unittest.TestCase):
    def test_old_gate_contract_remains_distinct(self):
        self.assertIsNot(PrototypeGateResult, PrototypeGateResultV2)
        self.assertTrue(callable(evaluate_prototype_gate))

    def test_research_db_schema_is_not_modified_by_strategy_db(self):
        db = ResearchDB(":memory:")
        table_names = {
            row["name"]
            for row in db.conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        self.assertNotIn("strategy_drafts", table_names)
        self.assertNotIn("strategy_promotions", table_names)

    def test_stable_contract_has_no_b1_verdict_field(self):
        self.assertNotIn(
            "verdict",
            PrototypeGateResult.model_fields,
        )


if __name__ == "__main__":
    unittest.main()
