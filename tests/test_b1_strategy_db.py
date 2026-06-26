import sqlite3
import unittest

from backend.db.strategy import StrategyDB
from tests.b1_fixtures import (
    make_backtest_universe,
    make_confirmation,
    make_gate_result,
    make_ledger,
    make_lifecycle_state,
    make_protocol_snapshot,
    make_report,
    make_strategy_draft,
    make_template_definition,
)


class TestStrategyDBSchema(unittest.TestCase):
    def setUp(self):
        self.db = StrategyDB(":memory:")

    def tearDown(self):
        self.db.close()

    def test_schema_is_separate_from_research_db(self):
        tables = self.db.list_table_names()
        self.assertIn("strategy_drafts", tables)
        self.assertNotIn("research_candidates", tables)

    def test_immutable_table_rejects_update(self):
        self.db.store_strategy_template(make_template_definition())
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.conn.execute(
                "UPDATE strategy_template_definitions SET version = ? WHERE template_id = ?",
                ("v2", "theme_momentum_breakout_v1"),
            )

    def test_immutable_table_rejects_delete(self):
        self.db.store_backtest_universe(make_backtest_universe())
        self.db.create_strategy_draft(
            make_strategy_draft(),
            make_lifecycle_state(),
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.conn.execute(
                "DELETE FROM strategy_drafts WHERE strategy_revision_id = ?",
                ("strategy_revision_001",),
            )

    def test_duplicate_primary_key_does_not_overwrite(self):
        self.db.store_backtest_universe(make_backtest_universe())
        self.db.create_strategy_draft(
            make_strategy_draft(),
            make_lifecycle_state(),
        )
        self.db.store_protocol_snapshot(make_protocol_snapshot())
        report = make_report()
        self.db.store_backtest_report(report)
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.store_backtest_report(report)


class TestStrategyDBRoundTrip(unittest.TestCase):
    def setUp(self):
        self.db = StrategyDB(":memory:")
        self.db.store_strategy_template(make_template_definition())
        self.db.store_backtest_universe(make_backtest_universe())
        self.db.create_strategy_draft(
            make_strategy_draft(),
            make_lifecycle_state(),
        )
        self.db.store_protocol_snapshot(make_protocol_snapshot())
        self.db.store_oos_ledger(make_ledger())
        self.db.store_backtest_report(make_report())
        self.db.store_gate_result(make_gate_result())
        self.db.store_human_confirmation(make_confirmation())

    def tearDown(self):
        self.db.close()

    def test_reads_return_typed_frozen_contracts(self):
        self.assertEqual(
            self.db.get_strategy_draft("strategy_revision_001"),
            make_strategy_draft(),
        )
        self.assertEqual(
            self.db.get_protocol_snapshot("protocol_001"),
            make_protocol_snapshot(),
        )
        self.assertEqual(
            self.db.get_backtest_report("report_001"),
            make_report(),
        )
        self.assertEqual(
            self.db.get_gate_result("gate_001"),
            make_gate_result(),
        )

    def test_latest_lifecycle_state_is_draft(self):
        state = self.db.get_latest_lifecycle_state("strategy_revision_001")
        self.assertIsNotNone(state)
        self.assertEqual(state.state, "draft")
        self.assertEqual(state.state_version, 1)

    def test_create_draft_with_initial_state_is_atomic(self):
        second = make_strategy_draft().model_copy(
            update={"strategy_revision_id": "strategy_revision_002"}
        )
        initial = make_lifecycle_state().model_copy(
            update={
                "lifecycle_state_id": "lifecycle_002",
                "strategy_revision_id": "strategy_revision_002",
            }
        )
        self.db.create_strategy_draft(second, initial)
        self.assertIsNotNone(
            self.db.get_strategy_draft("strategy_revision_002")
        )
        self.assertEqual(
            self.db.get_latest_lifecycle_state("strategy_revision_002").state,
            "draft",
        )


class TestPromotionStorageGuards(unittest.TestCase):
    def setUp(self):
        self.db = StrategyDB(":memory:")
        self.db.store_strategy_template(make_template_definition())
        self.db.store_backtest_universe(make_backtest_universe())
        self.db.create_strategy_draft(
            make_strategy_draft(),
            make_lifecycle_state(),
        )

    def tearDown(self):
        self.db.close()

    def test_direct_prototype_passed_state_without_promotion_fails(self):
        promoted_state = make_lifecycle_state(
            state="prototype_passed",
            state_version=2,
            source_record_id="missing_promotion",
        )
        with self.assertRaisesRegex(
            sqlite3.IntegrityError,
            "requires promotion",
        ):
            self.db.conn.execute(
                """
                INSERT INTO strategy_lifecycle_states
                (lifecycle_state_id, strategy_revision_id, state_version,
                 state, source_record_id, payload_json, recorded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    promoted_state.lifecycle_state_id,
                    promoted_state.strategy_revision_id,
                    promoted_state.state_version,
                    promoted_state.state,
                    promoted_state.source_record_id,
                    promoted_state.model_dump_json(),
                    promoted_state.recorded_at.isoformat(),
                ),
            )

    def test_strategy_db_has_no_public_status_update_method(self):
        self.assertFalse(hasattr(self.db, "update_strategy_status"))
        self.assertFalse(hasattr(self.db, "update_strategy_draft_status"))


if __name__ == "__main__":
    unittest.main()
