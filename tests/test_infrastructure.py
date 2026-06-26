import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path


class InfrastructureTests(unittest.TestCase):
    def test_database_initialization_creates_task_and_cache_metadata_tables(self):
        from backend.app.db import initialize_database

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "traderlens.sqlite3"
            initialize_database(db_path, enable_wal=False)

            with closing(sqlite3.connect(db_path)) as conn:
                tables = {
                    row[0]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }
                task_columns = {
                    row[1] for row in conn.execute("PRAGMA table_info(tasks)")
                }

        self.assertIn("tasks", tables)
        self.assertIn("data_cache_metadata", tables)
        self.assertIn("task_id", task_columns)
        self.assertIn("retry_count", task_columns)

    def test_worker_polls_queued_tasks_without_executing_strategy_logic(self):
        from backend.app.db import initialize_database
        from backend.app.worker import poll_once

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "traderlens.sqlite3"
            initialize_database(db_path, enable_wal=False)
            with closing(sqlite3.connect(db_path)) as conn:
                conn.execute(
                    """
                    INSERT INTO tasks (
                        task_id, task_type, status, created_at, config, retry_count
                    ) VALUES (
                        'task_001', 'backtest', 'queued', '2026-06-21T00:00:00',
                        X'7B7D', 0
                    )
                    """
                )
                conn.commit()

            claimed = poll_once(db_path)

            with closing(sqlite3.connect(db_path)) as conn:
                row = conn.execute(
                    "SELECT status, error_message FROM tasks WHERE task_id = 'task_001'"
                ).fetchone()

        self.assertEqual(claimed.task_id, "task_001")
        self.assertEqual(row[0], "failed")
        self.assertIn("no executor registered", row[1])

    def test_golden_case_manifest_and_expected_output_are_loadable_contract_fixtures(self):
        root = Path(__file__).resolve().parent / "golden_cases"

        stocks = json.loads((root / "test_stocks.json").read_text(encoding="utf-8"))
        expected = json.loads(
            (root / "expected_backtest_output.json").read_text(encoding="utf-8")
        )

        self.assertEqual(len(stocks), 5)
        self.assertEqual(expected["status"], "fixture_only")
        self.assertEqual(
            expected["m0_scope_note"],
            "M0 validates contracts and data loading only; strategy_core runs in M1.",
        )


if __name__ == "__main__":
    unittest.main()
