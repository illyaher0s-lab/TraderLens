"""C1c tests for the narrow migration-005 production owner."""

from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import hashlib
import importlib
import json
from pathlib import Path
import sqlite3
from io import StringIO
import tempfile
import unittest
from unittest.mock import patch


MIGRATION_ID = "migration_005_add_b6_successor_attempt"
PROTECTED_EVIDENCE_TABLES = (
    "oos_budget_state",
    "oos_budget_reservations",
    "oos_evaluation_ledgers",
    "immutable_backtest_reports",
    "prototype_gate_results_v2",
    "strategy_promotions",
    "human_promotion_confirmations",
    "human_confirmation_consumptions",
)


def _owner_module():
    return importlib.import_module("scripts.run_b6_successor_migration_once")


def _seed_migration004(path: Path):
    from tests.test_b6_successor_attempt import _seed_pre005_v2_row

    return _seed_pre005_v2_row(path)


def _connection(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def _schema_snapshot(path: Path) -> dict:
    with closing(_connection(path)) as conn:
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
        ]
        columns = [
            tuple(row)
            for row in conn.execute("PRAGMA table_info(b6_validation_tasks)")
        ]
        task_columns = [row[1] for row in columns]
        tasks = [
            {column: row[column] for column in task_columns}
            for row in conn.execute("SELECT * FROM b6_validation_tasks ORDER BY rowid")
        ]
        for task in tasks:
            if isinstance(task.get("payload_json"), str):
                task["payload_json_bytes"] = task["payload_json"].encode("utf-8")
        indexes = [
            tuple(row)
            for row in conn.execute(
                "SELECT type, name, tbl_name, sql FROM sqlite_master "
                "WHERE type='index' ORDER BY name"
            )
        ]
        foreign_keys = [
            tuple(row)
            for row in conn.execute("PRAGMA foreign_key_list(b6_validation_tasks)")
        ]
        return {
            "tables": tables,
            "columns": columns,
            "tasks": tasks,
            "indexes": indexes,
            "foreign_keys": foreign_keys,
        }


def _protected_counts(path: Path) -> dict[str, int]:
    with closing(_connection(path)) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        return {
            table: int(
                conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            )
            for table in PROTECTED_EVIDENCE_TABLES
            if table in tables
        }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _invoke(module, *, root: Path, db_path: Path, backup_root: Path, **kwargs):
    stdout = StringIO()
    progress = StringIO()
    code, payload = module.run_once(
        repo_root=root,
        db_path=db_path,
        backup_root=backup_root,
        stdout=stdout,
        progress_stream=progress,
        **kwargs,
    )
    return code, payload, stdout.getvalue(), progress.getvalue()


class TestRunB6SuccessorMigrationOnce(unittest.TestCase):
    def test_main_rejects_arguments_without_opening_database(self):
        module = _owner_module()
        with patch.object(module, "run_once") as run_once:
            for argv in (("unexpected",), ("--db", "other.db"), ("--dry-run",)):
                with self.subTest(argv=argv):
                    self.assertEqual(module.main(list(argv)), 64)
            run_once.assert_not_called()

    def test_preflight_requires_migrations_001_to_004_and_rejects_partial_005(self):
        module = _owner_module()
        with tempfile.TemporaryDirectory(prefix="b6-c1c-preflight-") as raw_tmp:
            root = Path(raw_tmp)
            missing_db = root / "missing.db"
            missing_backup = root / "missing-backup"
            writer_calls: list[str] = []

            def writer(path: str):
                writer_calls.append(path)
                return sqlite3.connect(path)

            code, payload, _, _ = _invoke(
                module,
                root=root,
                db_path=missing_db,
                backup_root=missing_backup,
                connection_factory=writer,
            )
            self.assertEqual(code, 20)
            self.assertEqual(payload["status"], "blocked")
            self.assertEqual(writer_calls, [])
            self.assertFalse(missing_backup.exists())

            partial_db = root / "partial.db"
            _seed_migration004(partial_db)
            with closing(sqlite3.connect(str(partial_db))) as conn:
                conn.execute(
                    "ALTER TABLE b6_validation_tasks "
                    "ADD COLUMN predecessor_task_id TEXT"
                )
                conn.commit()
            partial_backup = root / "partial-backup"
            code, payload, _, _ = _invoke(
                module,
                root=root,
                db_path=partial_db,
                backup_root=partial_backup,
                connection_factory=writer,
            )
            self.assertEqual(code, 20)
            self.assertEqual(payload["reason"], "b6_schema_migration_partial_or_invalid")
            self.assertEqual(writer_calls, [])
            self.assertFalse(partial_backup.exists())

    def test_already_applied_is_stable_without_backup_or_migration_call(self):
        module = _owner_module()
        migration_module = importlib.import_module(
            "backend.db.migrations.migration_005_add_b6_successor_attempt"
        )
        with tempfile.TemporaryDirectory(prefix="b6-c1c-already-") as raw_tmp:
            root = Path(raw_tmp)
            db_path = root / "already.db"
            _seed_migration004(db_path)
            with closing(sqlite3.connect(str(db_path))) as conn:
                migration_module.migrate_add_b6_successor_attempt(conn)
            calls: list[str] = []

            def migration(conn):
                calls.append("migration")
                raise AssertionError("already-applied path called migration")

            def writer(path: str):
                raise AssertionError("already-applied path opened writer")

            backup_root = root / "backup"
            code, payload, _, progress = _invoke(
                module,
                root=root,
                db_path=db_path,
                backup_root=backup_root,
                connection_factory=writer,
                migration=migration,
            )
            self.assertEqual(code, 0)
            self.assertEqual(payload["status"], "already_applied")
            self.assertEqual(payload["migration_id"], MIGRATION_ID)
            self.assertEqual(calls, [])
            self.assertFalse(backup_root.exists())
            self.assertIn('"stage":"terminal"', progress)

    def test_exact_existing_backup_is_reused_without_recopy(self):
        module = _owner_module()
        migration_module = importlib.import_module(
            "backend.db.migrations.migration_005_add_b6_successor_attempt"
        )
        with tempfile.TemporaryDirectory(prefix="b6-c1c-reuse-") as raw_tmp:
            root = Path(raw_tmp)
            db_path = root / "reuse.db"
            _seed_migration004(db_path)
            backup_root = root / "backup"
            preflight = module._preflight(db_path)
            self.assertEqual(preflight["migration_005_state"], "not_applied")
            existing = module._create_backup(db_path, backup_root, preflight)
            existing_paths = {
                key: Path(existing[key])
                for key in (
                    "backup_path",
                    "backup_manifest_path",
                    "backup_manifest_sidecar_path",
                )
            }
            before = {
                path: (path.read_bytes(), path.stat().st_mtime_ns)
                for path in existing_paths.values()
            }
            manifest = json.loads(
                existing_paths["backup_manifest_path"].read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["source_db_sha256"], preflight["sha256"])
            self.assertEqual(manifest["source_size_bytes"], preflight["size_bytes"])
            self.assertEqual(manifest["source_mtime_ns"], preflight["mtime_ns"])
            calls: list[sqlite3.Connection] = []

            def migration(conn):
                calls.append(conn)
                return migration_module.migrate_add_b6_successor_attempt(conn)

            code, payload, _, _ = _invoke(
                module,
                root=root,
                db_path=db_path,
                backup_root=backup_root,
                migration=migration,
            )
            self.assertEqual(code, 0)
            self.assertEqual(payload["status"], "migrated")
            self.assertEqual(len(calls), 1)
            self.assertEqual(payload["backup_id"], existing["backup_id"])
            for key, path in existing_paths.items():
                self.assertEqual(Path(payload[key]), path)
            self.assertEqual(
                payload["backup_db_sha256"], existing["backup_db_sha256"]
            )
            self.assertEqual(
                payload["backup_manifest_sha256"], existing["backup_manifest_sha256"]
            )
            self.assertEqual(len(list(backup_root.glob("*.sqlite3"))), 1)
            self.assertEqual(list(backup_root.glob(".*.staging-*")), [])
            self.assertEqual(
                {
                    path: (path.read_bytes(), path.stat().st_mtime_ns)
                    for path in existing_paths.values()
                },
                before,
            )

    def test_partial_or_mismatched_existing_backup_blocks_before_write(self):
        module = _owner_module()
        for case in ("partial", "mismatch"):
            with self.subTest(case=case):
                with tempfile.TemporaryDirectory(prefix=f"b6-c1c-{case}-") as raw_tmp:
                    root = Path(raw_tmp)
                    db_path = root / f"{case}.db"
                    _seed_migration004(db_path)
                    backup_root = root / "backup"
                    backup_root.mkdir(parents=True)
                    target = backup_root / f"migration_005.{_sha256(db_path)}.sqlite3"
                    if case == "partial":
                        target.write_bytes(db_path.read_bytes())
                        evidence = {target: target.read_bytes()}
                    else:
                        preflight = module._preflight(db_path)
                        existing = module._create_backup(db_path, backup_root, preflight)
                        manifest_path = Path(existing["backup_manifest_path"])
                        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                        manifest["source_db_sha256"] = "0" * 64
                        manifest_path.write_text(
                            json.dumps(manifest, sort_keys=True), encoding="utf-8"
                        )
                        evidence = {
                            path: path.read_bytes()
                            for path in (
                                Path(existing["backup_path"]),
                                manifest_path,
                                Path(existing["backup_manifest_sidecar_path"]),
                            )
                        }

                    writer_calls: list[str] = []
                    migration_calls: list[sqlite3.Connection] = []

                    def writer(path: str):
                        writer_calls.append(path)
                        raise AssertionError("blocked backup opened writable connection")

                    def migration(conn):
                        migration_calls.append(conn)
                        raise AssertionError("blocked backup called migration")

                    code, payload, _, _ = _invoke(
                        module,
                        root=root,
                        db_path=db_path,
                        backup_root=backup_root,
                        connection_factory=writer,
                        migration=migration,
                    )
                    self.assertEqual(code, 20)
                    self.assertEqual(payload["status"], "blocked")
                    self.assertEqual(
                        payload["reason"], "b6_schema_migration_backup_conflict"
                    )
                    self.assertEqual(writer_calls, [])
                    self.assertEqual(migration_calls, [])
                    self.assertEqual(
                        {path: path.read_bytes() for path in evidence}, evidence
                    )

    def test_backup_precedes_the_only_writable_connection(self):
        module = _owner_module()
        with tempfile.TemporaryDirectory(prefix="b6-c1c-order-") as raw_tmp:
            root = Path(raw_tmp)
            db_path = root / "order.db"
            _seed_migration004(db_path)
            backup_root = root / "data" / "strategy_backups" / "b6_schema_migration"
            events: list[str] = []

            def writer(path: str):
                events.append("writer")
                self.assertTrue(backup_root.is_dir())
                sqlite_files = list(backup_root.glob("*.sqlite3"))
                self.assertEqual(len(sqlite_files), 1)
                self.assertFalse((root / "data" / "strategy_backups" / "b6_preclaim").exists())
                return sqlite3.connect(path)

            def migration(conn):
                events.append("migration")
                return importlib.import_module(
                    "backend.db.migrations.migration_005_add_b6_successor_attempt"
                ).migrate_add_b6_successor_attempt(conn)

            source_sha = _sha256(db_path)
            code, payload, _, _ = _invoke(
                module,
                root=root,
                db_path=db_path,
                backup_root=backup_root,
                connection_factory=writer,
                migration=migration,
            )
            self.assertEqual(code, 0)
            self.assertEqual(events, ["writer", "migration"])
            self.assertEqual(payload["status"], "migrated")
            backup_path = Path(payload["backup_path"])
            manifest_path = Path(payload["backup_manifest_path"])
            sidecar_path = Path(payload["backup_manifest_sidecar_path"])
            self.assertTrue(backup_path.is_file())
            self.assertTrue(manifest_path.is_file())
            self.assertTrue(sidecar_path.is_file())
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema_version"], "b6_schema_migration_backup.v1")
            self.assertEqual(manifest["source_db_sha256"], source_sha)
            self.assertEqual(manifest["backup_db_sha256"], _sha256(backup_path))

    def test_registered_migration_is_called_exactly_once(self):
        module = _owner_module()
        migration_module = importlib.import_module(
            "backend.db.migrations.migration_005_add_b6_successor_attempt"
        )
        with tempfile.TemporaryDirectory(prefix="b6-c1c-call-") as raw_tmp:
            root = Path(raw_tmp)
            db_path = root / "call.db"
            _seed_migration004(db_path)
            calls: list[sqlite3.Connection] = []

            def migration(conn):
                calls.append(conn)
                return migration_module.migrate_add_b6_successor_attempt(conn)

            with patch("backend.db.strategy.StrategyDB") as strategy_db:
                code, payload, _, _ = _invoke(
                    module,
                    root=root,
                    db_path=db_path,
                    backup_root=root / "backup",
                    migration=migration,
                )
            self.assertEqual(code, 0)
            self.assertEqual(payload["status"], "migrated")
            self.assertEqual(len(calls), 1)
            strategy_db.assert_not_called()

    def test_post_audit_preserves_rows_and_adds_exact_nullable_schema(self):
        module = _owner_module()
        with tempfile.TemporaryDirectory(prefix="b6-c1c-post-") as raw_tmp:
            root = Path(raw_tmp)
            db_path = root / "post.db"
            _seed_migration004(db_path)
            before = _schema_snapshot(db_path)
            code, payload, _, _ = _invoke(
                module,
                root=root,
                db_path=db_path,
                backup_root=root / "backup",
            )
            self.assertEqual(code, 0)
            self.assertEqual(payload["status"], "migrated")
            after = _schema_snapshot(db_path)
            before_columns = [row[1] for row in before["columns"]]
            after_columns = [row[1] for row in after["columns"]]
            self.assertEqual(
                after_columns,
                before_columns
                + [
                    "predecessor_task_id",
                    "predecessor_task_key",
                    "successor_attempt_number",
                ],
            )
            for before_task, after_task in zip(before["tasks"], after["tasks"]):
                for column in before_columns:
                    self.assertEqual(after_task[column], before_task[column])
                self.assertEqual(
                    after_task["payload_json_bytes"], before_task["payload_json_bytes"]
                )
                self.assertIsNone(after_task["predecessor_task_id"])
                self.assertIsNone(after_task["predecessor_task_key"])
                self.assertIsNone(after_task["successor_attempt_number"])

            column_by_name = {row[1]: row for row in after["columns"]}
            self.assertEqual(column_by_name["predecessor_task_id"][2], "TEXT")
            self.assertEqual(column_by_name["predecessor_task_id"][3:], (0, None, 0))
            self.assertEqual(column_by_name["predecessor_task_key"][2], "TEXT")
            self.assertEqual(column_by_name["predecessor_task_key"][3:], (0, None, 0))
            self.assertEqual(column_by_name["successor_attempt_number"][2], "INTEGER")
            self.assertEqual(column_by_name["successor_attempt_number"][3:], (0, None, 0))
            self.assertIn(
                True,
                [
                    row[2:5]
                    == ("b6_validation_tasks", "predecessor_task_id", "task_id")
                    for row in after["foreign_keys"]
                ],
            )
            with closing(_connection(db_path)) as conn:
                index_sql = conn.execute(
                    "SELECT sql FROM sqlite_master WHERE type='index' AND name=?",
                    ("uq_b6_direct_successor_predecessor",),
                ).fetchone()[0]
            self.assertEqual(
                " ".join(index_sql.split()),
                "CREATE UNIQUE INDEX uq_b6_direct_successor_predecessor ON b6_validation_tasks(predecessor_task_id) WHERE predecessor_task_id IS NOT NULL",
            )
            protected_counts = _protected_counts(db_path)
            self.assertTrue(protected_counts)
            self.assertTrue(all(value == 0 for value in protected_counts.values()))
            self.assertEqual(payload["post_health"]["quick_check"], "ok")
            self.assertEqual(payload["post_health"]["foreign_key_check"], [])

    def test_migration_failure_is_failed_closed_and_preserves_backup(self):
        module = _owner_module()
        with tempfile.TemporaryDirectory(prefix="b6-c1c-failure-") as raw_tmp:
            root = Path(raw_tmp)
            db_path = root / "failure.db"
            _seed_migration004(db_path)
            before = _schema_snapshot(db_path)
            backup_root = root / "backup"

            def fail_migration(conn):
                conn.execute("BEGIN IMMEDIATE")
                raise RuntimeError("injected migration failure")

            code, payload, _, _ = _invoke(
                module,
                root=root,
                db_path=db_path,
                backup_root=backup_root,
                migration=fail_migration,
            )
            self.assertEqual(code, 70)
            self.assertEqual(payload["status"], "failed")
            self.assertTrue(Path(payload["backup_path"]).is_file())
            self.assertTrue(Path(payload["backup_manifest_path"]).is_file())
            self.assertTrue(Path(payload["backup_manifest_sidecar_path"]).is_file())
            self.assertEqual(_schema_snapshot(db_path), before)
            self.assertEqual(len(list(backup_root.glob("*.sqlite3"))), 1)

    def test_progress_and_result_are_canonical_for_migrated_and_blocked(self):
        module = _owner_module()
        with tempfile.TemporaryDirectory(prefix="b6-c1c-output-") as raw_tmp:
            root = Path(raw_tmp)
            db_path = root / "output.db"
            _seed_migration004(db_path)
            code, payload, stdout, progress = _invoke(
                module,
                root=root,
                db_path=db_path,
                backup_root=root / "backup",
            )
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(stdout), payload)
            self.assertEqual(stdout.count("\n"), 1)
            progress_rows = [json.loads(line) for line in progress.splitlines()]
            self.assertGreaterEqual(len(progress_rows), 4)
            self.assertEqual(
                [row["event_seq"] for row in progress_rows],
                list(range(1, len(progress_rows) + 1)),
            )
            self.assertEqual(
                set(progress_rows[0]),
                {
                    "schema_version",
                    "event_seq",
                    "stage",
                    "migration_id",
                    "status",
                    "source_db_sha256",
                    "backup_id",
                },
            )
            self.assertEqual(
                set(payload),
                {
                    "schema_version",
                    "migration_id",
                    "status",
                    "db_path",
                    "source_db_sha256",
                    "source_size_bytes",
                    "source_mtime_ns",
                    "backup_id",
                    "backup_path",
                    "backup_manifest_path",
                    "backup_manifest_sidecar_path",
                    "backup_db_sha256",
                    "backup_manifest_sha256",
                    "post_schema_sha256",
                    "post_task_row_snapshot_sha256",
                    "post_health",
                    "post_protected_counts",
                    "migration_registry",
                    "reason",
                    "detail",
                },
            )
            blocked_db = root / "blocked.db"
            blocked_backup = root / "blocked-backup"
            blocked_code, blocked_payload, blocked_stdout, blocked_progress = _invoke(
                module,
                root=root,
                db_path=blocked_db,
                backup_root=blocked_backup,
            )
            self.assertEqual(blocked_code, 20)
            self.assertEqual(json.loads(blocked_stdout), blocked_payload)
            self.assertIn('"stage":"blocked"', blocked_progress)


if __name__ == "__main__":
    unittest.main()
