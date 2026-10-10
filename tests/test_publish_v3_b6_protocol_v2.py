from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import shutil
from contextlib import closing
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_DB = ROOT / "data" / "strategy.db"


class TestPublishV3B6ProtocolV2(unittest.TestCase):
    def _copy_production_db(self, temp: str) -> Path:
        db_path = Path(temp) / "strategy.db"
        shutil.copy2(PRODUCTION_DB, db_path)
        return db_path

    def _counts(self, db_path: Path) -> tuple[int, ...]:
        tables = (
            "research_protocol_snapshots",
            "b6_validation_tasks",
            "oos_budget_reservations",
            "oos_budget_state",
            "oos_evaluation_ledgers",
            "immutable_backtest_reports",
            "prototype_gate_results_v2",
        )
        with closing(sqlite3.connect(db_path)) as conn:
            return tuple(
                conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in tables
            )

    def test_temp_publish_creates_exact_candidate_without_b6_or_oos_side_effects(self):
        import scripts.publish_v3_b6_protocol_v2 as publisher

        with tempfile.TemporaryDirectory() as temp:
            db_path = Path(temp) / "strategy.db"
            shutil.copy2(PRODUCTION_DB, db_path)
            result = publisher._publish_v3_b6_protocol_v2(
                repo_root=ROOT,
                db_path=db_path,
            )
            with closing(sqlite3.connect(db_path)) as conn:
                candidate = conn.execute(
                    "SELECT payload_json FROM research_protocol_snapshots WHERE protocol_snapshot_id = ?",
                    (result["protocol_snapshot_id"],),
                ).fetchone()
                old_task = conn.execute(
                    "SELECT protocol_snapshot_id, status, task_contract_version FROM b6_validation_tasks"
                ).fetchone()
                final_counts = self._counts(db_path)

        self.assertEqual(result["status"], "created")
        self.assertEqual(
            result["protocol_snapshot_id"],
            "8770c56c5a69ef128442c0f593f9e4b081a6b13c69744b27171b27cc8c8b7bbe",
        )
        self.assertEqual(
            result["payload_sha256"],
            "2872d63578d66e6dfc02fd767c4061fd3e291bcb9bbd65f0f2409a4482f6e2a3",
        )
        self.assertEqual(
            result["criteria_envelope_hash"],
            "94da0dda30af75d663a7d28deb0a15d64a4e068586a1295f3b4f52203a8c4738",
        )
        self.assertEqual(
            result["changed_fields"],
            [
                "gate_criteria_hash",
                "gate_snapshot_id",
                "kill_criteria_snapshot_id",
                "protocol_snapshot_id",
            ],
        )
        self.assertEqual(old_task, (publisher.OLD_PROTOCOL_ID, "queued", "v2"))
        self.assertEqual(final_counts, (2, 1, 0, 0, 0, 0, 0))
        self.assertIsNotNone(candidate)

    def test_exact_retry_reuses_candidate_without_new_side_effects(self):
        import scripts.publish_v3_b6_protocol_v2 as publisher

        with tempfile.TemporaryDirectory() as temp:
            db_path = self._copy_production_db(temp)
            first = publisher._publish_v3_b6_protocol_v2(repo_root=ROOT, db_path=db_path)
            before = self._counts(db_path)
            second = publisher._publish_v3_b6_protocol_v2(repo_root=ROOT, db_path=db_path)
            after = self._counts(db_path)

        self.assertEqual(first["status"], "created")
        self.assertEqual(second["status"], "reused")
        self.assertEqual(first["protocol_snapshot_id"], second["protocol_snapshot_id"])
        self.assertEqual(before, (2, 1, 0, 0, 0, 0, 0))
        self.assertEqual(after, before)

    def test_same_candidate_id_conflicting_payload_fails_without_overwrite(self):
        import scripts.publish_v3_b6_protocol_v2 as publisher

        with tempfile.TemporaryDirectory() as temp:
            db_path = self._copy_production_db(temp)
            with closing(sqlite3.connect(db_path)) as conn:
                conn.execute(
                    """
                    INSERT INTO research_protocol_snapshots
                    (protocol_snapshot_id, strategy_revision_id, payload_json,
                     strategy_config_hash, data_snapshot_hash, gate_criteria_hash,
                     frozen_at, protocol_profile)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        publisher.EXPECTED_PROTOCOL_ID,
                        publisher.OLD_REVISION_ID,
                        "{}",
                        "conflict-config",
                        "conflict-data",
                        "conflict-gate",
                        "2026-08-23T00:00:00",
                        "b6_coverage_bound",
                    ),
                )
                conn.commit()
            before = self._counts(db_path)

            with self.assertRaises(ValueError):
                publisher._publish_v3_b6_protocol_v2(repo_root=ROOT, db_path=db_path)

            after = self._counts(db_path)

        self.assertEqual(before, (2, 1, 0, 0, 0, 0, 0))
        self.assertEqual(after, before)

    def test_insert_failure_rolls_back_without_touching_old_task_or_oos(self):
        import scripts.publish_v3_b6_protocol_v2 as publisher

        with tempfile.TemporaryDirectory() as temp:
            db_path = self._copy_production_db(temp)
            with closing(sqlite3.connect(db_path)) as conn:
                conn.executescript(
                    f"""
                    CREATE TRIGGER reject_v2_protocol_insert
                    BEFORE INSERT ON research_protocol_snapshots
                    WHEN NEW.protocol_snapshot_id = '{publisher.EXPECTED_PROTOCOL_ID}'
                    BEGIN
                        SELECT RAISE(ABORT, 'forced protocol insert failure');
                    END;
                    """
                )
                conn.commit()
            before = self._counts(db_path)

            with self.assertRaises(Exception):
                publisher._publish_v3_b6_protocol_v2(repo_root=ROOT, db_path=db_path)

            after = self._counts(db_path)

        self.assertEqual(before, (1, 1, 0, 0, 0, 0, 0))
        self.assertEqual(after, before)

    def test_two_real_file_connections_have_one_candidate_winner(self):
        import scripts.publish_v3_b6_protocol_v2 as publisher

        with tempfile.TemporaryDirectory() as temp:
            db_path = self._copy_production_db(temp)
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [
                    pool.submit(
                        publisher._publish_v3_b6_protocol_v2,
                        repo_root=ROOT,
                        db_path=db_path,
                    )
                    for _ in range(2)
                ]
                results = [future.result() for future in futures]

            with closing(sqlite3.connect(db_path)) as conn:
                candidate_rows = conn.execute(
                    "SELECT protocol_snapshot_id, payload_json FROM research_protocol_snapshots "
                    "WHERE protocol_snapshot_id = ?",
                    (publisher.EXPECTED_PROTOCOL_ID,),
                ).fetchall()
            final_counts = self._counts(db_path)

        self.assertEqual({result["status"] for result in results}, {"created", "reused"})
        self.assertEqual(len(candidate_rows), 1)
        self.assertEqual(final_counts, (2, 1, 0, 0, 0, 0, 0))

    def test_cli_rejects_user_paths_and_identity_overrides(self):
        import inspect
        import scripts.publish_v3_b6_protocol_v2 as publisher

        self.assertEqual(tuple(inspect.signature(publisher.publish_v3_b6_protocol_v2).parameters), ())
        self.assertEqual(publisher.main(["user.db"]), 2)
        self.assertEqual(publisher.main(["user.db", "user-id"]), 2)

    def test_invalid_criteria_blocks_before_store_and_oos_side_effects(self):
        import scripts.publish_v3_b6_protocol_v2 as publisher

        with tempfile.TemporaryDirectory() as temp:
            db_path = self._copy_production_db(temp)
            before = self._counts(db_path)
            with patch.object(publisher, "verify_criteria_pair", return_value={"status": "invalid"}):
                with self.assertRaises(ValueError):
                    publisher._publish_v3_b6_protocol_v2(repo_root=ROOT, db_path=db_path)
            after = self._counts(db_path)

        self.assertEqual(before, (1, 1, 0, 0, 0, 0, 0))
        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
