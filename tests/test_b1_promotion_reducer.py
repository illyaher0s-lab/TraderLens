import sqlite3
import unittest
from datetime import datetime

from backend.db.strategy import StrategyDB
from backend.services.strategy_promotion_reducer import StrategyPromotionReducer
from contracts.strategy import HumanPromotionConfirmation
from tests.b1_fixtures import (
    make_backtest_universe,
    make_confirmation,
    make_gate_result,
    make_lifecycle_state,
    make_protocol_snapshot,
    make_report,
    make_strategy_draft,
    make_template_definition,
)


class TestStrategyPromotionReducer(unittest.TestCase):
    def setUp(self):
        self.db = StrategyDB(":memory:")
        self.db.store_strategy_template(make_template_definition())
        self.db.store_backtest_universe(make_backtest_universe())
        self.db.create_strategy_draft(
            make_strategy_draft(),
            make_lifecycle_state(),
        )
        self.db.store_protocol_snapshot(make_protocol_snapshot())
        self.db.store_backtest_report(make_report())
        self.db.store_gate_result(make_gate_result())
        self.db.store_human_confirmation(make_confirmation())
        self.reducer = StrategyPromotionReducer(self.db)

    def tearDown(self):
        self.db.close()

    def test_valid_human_confirmation_promotes_atomically(self):
        promotion = self.reducer.promote_to_prototype_passed(
            strategy_revision_id="strategy_revision_001",
            gate_result_id="gate_001",
            human_confirmation_id="human_confirmation_001",
            promoted_by="owner_001",
        )
        self.assertEqual(promotion.new_state, "prototype_passed")
        self.assertEqual(
            self.db.get_latest_lifecycle_state(
                "strategy_revision_001"
            ).state,
            "prototype_passed",
        )

    def test_same_request_is_idempotent(self):
        first = self.reducer.promote_to_prototype_passed(
            "strategy_revision_001",
            "gate_001",
            "human_confirmation_001",
            "owner_001",
        )
        second = self.reducer.promote_to_prototype_passed(
            "strategy_revision_001",
            "gate_001",
            "human_confirmation_001",
            "owner_001",
        )
        self.assertEqual(first.promotion_id, second.promotion_id)

    def test_different_gate_after_promotion_is_rejected(self):
        self.reducer.promote_to_prototype_passed(
            "strategy_revision_001",
            "gate_001",
            "human_confirmation_001",
            "owner_001",
        )
        with self.assertRaisesRegex(ValueError, "different gate"):
            self.reducer.promote_to_prototype_passed(
                "strategy_revision_001",
                "gate_other",
                "human_confirmation_other",
                "owner_001",
            )

    def test_rejected_gate_cannot_promote(self):
        rejected = make_gate_result(verdict="rejected").model_copy(
            update={
                "gate_result_id": "gate_rejected",
                "gate_result_hash": "gate_hash_rejected",
            }
        )
        self.db.store_gate_result(rejected)
        confirmation = HumanPromotionConfirmation(
            human_confirmation_id="human_confirmation_rejected",
            strategy_revision_id="strategy_revision_001",
            gate_result_id="gate_rejected",
            decision="approve",
            confirmed_by="owner_001",
            confirmed_at=datetime(2026, 6, 26, 10, 0, 0),
            frozen=True,
        )
        self.db.store_human_confirmation(confirmation)
        with self.assertRaisesRegex(ValueError, "candidate_for_prototype_passed"):
            self.reducer.promote_to_prototype_passed(
                "strategy_revision_001",
                "gate_rejected",
                "human_confirmation_rejected",
                "owner_001",
            )

    def test_hash_mismatch_rolls_back_all_writes(self):
        bad_gate = make_gate_result().model_copy(
            update={
                "gate_result_id": "gate_bad_hash",
                "gate_result_hash": "gate_result_hash_bad",
                "data_snapshot_hash": "different_data_hash",
            }
        )
        self.db.store_gate_result(bad_gate)
        confirmation = HumanPromotionConfirmation(
            human_confirmation_id="human_confirmation_bad_hash",
            strategy_revision_id="strategy_revision_001",
            gate_result_id="gate_bad_hash",
            decision="approve",
            confirmed_by="owner_001",
            confirmed_at=datetime(2026, 6, 26, 10, 0, 0),
            frozen=True,
        )
        self.db.store_human_confirmation(confirmation)
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            self.reducer.promote_to_prototype_passed(
                "strategy_revision_001",
                "gate_bad_hash",
                "human_confirmation_bad_hash",
                "owner_001",
            )
        self.assertEqual(
            self.db.get_latest_lifecycle_state(
                "strategy_revision_001"
            ).state,
            "draft",
        )
        self.assertFalse(
            self.db._confirmation_is_consumed(
                "human_confirmation_bad_hash"
            )
        )


if __name__ == "__main__":
    unittest.main()
