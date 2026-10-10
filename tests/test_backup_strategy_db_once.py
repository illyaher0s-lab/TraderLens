from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
from io import StringIO
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch


TASK_ID = "task_backup_001"
INCIDENT_ID = "v3_e4_protocol_migration_incident_20260823"


def _make_temp_repo(*, wal: bool = False) -> tuple[tempfile.TemporaryDirectory, Path]:
    temp_dir = tempfile.TemporaryDirectory()
    root = Path(temp_dir.name)
    (root / "data").mkdir()
    (root / "docs" / "verification").mkdir(parents=True)
    (root / "docs" / "verification" / f"{INCIDENT_ID}.json").write_text(
        json.dumps({"incident_id": INCIDENT_ID, "status": "contained_not_yet_recovered"}, sort_keys=True),
        encoding="utf-8",
    )
    db_path = root / "data" / "strategy.db"
    conn = sqlite3.connect(db_path)
    try:
        if wal:
            conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(
            """
            PRAGMA foreign_keys=ON;
            CREATE TABLE research_protocol_snapshots (
                protocol_snapshot_id TEXT PRIMARY KEY,
                strategy_revision_id TEXT NOT NULL,
                protocol_profile TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );
            CREATE TABLE b6_validation_tasks (
                task_id TEXT PRIMARY KEY,
                task_key TEXT NOT NULL,
                status TEXT NOT NULL,
                protocol_snapshot_id TEXT NOT NULL
                    REFERENCES research_protocol_snapshots(protocol_snapshot_id),
                payload_json TEXT NOT NULL
            );
            CREATE TABLE oos_budget_reservations (reservation_id TEXT PRIMARY KEY);
            CREATE TABLE oos_budget_state (state_id TEXT PRIMARY KEY);
            CREATE TABLE oos_evaluation_ledgers (ledger_id TEXT PRIMARY KEY);
            CREATE TABLE immutable_backtest_reports (report_id TEXT PRIMARY KEY);
            CREATE TABLE prototype_gate_results_v2 (gate_result_id TEXT PRIMARY KEY);
            CREATE TABLE snapshot_marker (marker TEXT PRIMARY KEY);
            CREATE INDEX idx_protocol_b6_profile_per_revision
                ON research_protocol_snapshots(strategy_revision_id, protocol_profile);
            """
        )
        conn.execute(
            "INSERT INTO research_protocol_snapshots VALUES (?, ?, ?, ?)",
            ("protocol_backup_001", "revision_backup_001", "b6_coverage_bound", "{}"),
        )
        conn.execute(
            "INSERT INTO b6_validation_tasks VALUES (?, ?, ?, ?, ?)",
            (TASK_ID, "task-key-backup-001", "queued", "protocol_backup_001", "{}"),
        )
        conn.commit()
    finally:
        conn.close()
    return temp_dir, root


def _backup_path(result: dict) -> Path:
    return Path(result["backup_path"])


class TestBackupStrategyDBOnce(unittest.TestCase):
    def test_successful_consistent_backup_is_write_once_and_source_unchanged(self):
        from scripts.backup_strategy_db_once import backup_strategy_db_once

        temp_dir, root = _make_temp_repo()
        try:
            source = root / "data" / "strategy.db"
            before = (source.stat().st_mtime_ns, source.stat().st_size, source.read_bytes())
            result = backup_strategy_db_once(TASK_ID, repo_root=root)
            self.assertEqual(result["status"], "published")
            target = _backup_path(result)
            self.assertTrue(target.is_file())
            self.assertTrue(Path(result["manifest_path"]).is_file())
            self.assertTrue(Path(result["manifest_sidecar_path"]).is_file())
            manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
            self.assertEqual(manifest["task_id"], TASK_ID)
            self.assertEqual(manifest["incident_id"], INCIDENT_ID)
            self.assertEqual(manifest["source_snapshot"]["counts"]["b6_validation_tasks"], 1)
            self.assertEqual(manifest["backup_snapshot"], manifest["source_snapshot"])
            self.assertEqual(
                (source.stat().st_mtime_ns, source.stat().st_size, source.read_bytes()),
                before,
            )
            self.assertEqual(
                Path(result["manifest_sidecar_path"]).read_text(encoding="utf-8").split()[0],
                result["manifest_sha256"],
            )
        finally:
            temp_dir.cleanup()

    def test_wal_committed_state_is_included_with_two_real_connections(self):
        from scripts.backup_strategy_db_once import backup_strategy_db_once

        temp_dir, root = _make_temp_repo(wal=True)
        writer = sqlite3.connect(root / "data" / "strategy.db")
        try:
            writer.execute("INSERT INTO snapshot_marker VALUES ('committed')")
            writer.commit()
            result = backup_strategy_db_once(TASK_ID, repo_root=root)
            with closing(sqlite3.connect(_backup_path(result))) as copied:
                self.assertEqual(
                    copied.execute("SELECT marker FROM snapshot_marker").fetchone()[0],
                    "committed",
                )
        finally:
            writer.close()
            temp_dir.cleanup()

    def test_uncommitted_state_is_not_in_backup(self):
        from scripts.backup_strategy_db_once import backup_strategy_db_once

        temp_dir, root = _make_temp_repo()
        writer = sqlite3.connect(root / "data" / "strategy.db")
        try:
            writer.execute("INSERT INTO snapshot_marker VALUES ('uncommitted')")
            result = backup_strategy_db_once(TASK_ID, repo_root=root)
            with closing(sqlite3.connect(_backup_path(result))) as copied:
                self.assertIsNone(
                    copied.execute(
                        "SELECT marker FROM snapshot_marker WHERE marker='uncommitted'"
                    ).fetchone()
                )
            writer.rollback()
        finally:
            writer.close()
            temp_dir.cleanup()

    def test_exact_retry_reuses_without_rewriting(self):
        from scripts.backup_strategy_db_once import backup_strategy_db_once

        temp_dir, root = _make_temp_repo()
        try:
            first = backup_strategy_db_once(TASK_ID, repo_root=root)
            target = _backup_path(first)
            before = (target.stat().st_mtime_ns, target.read_bytes())
            second = backup_strategy_db_once(TASK_ID, repo_root=root)
            self.assertEqual(second["status"], "reused")
            self.assertEqual(second["manifest_sha256"], first["manifest_sha256"])
            self.assertEqual((target.stat().st_mtime_ns, target.read_bytes()), before)
            self.assertEqual(len(list((root / "data" / "strategy_backups" / "b6_preclaim").glob("*.sqlite3"))), 1)
        finally:
            temp_dir.cleanup()

    def test_conflicting_existing_final_fails_without_overwrite(self):
        from scripts.backup_strategy_db_once import BackupConflictError, backup_strategy_db_once

        temp_dir, root = _make_temp_repo()
        try:
            first = backup_strategy_db_once(TASK_ID, repo_root=root)
            manifest_path = Path(first["manifest_path"])
            original = manifest_path.read_bytes()
            manifest = json.loads(original)
            manifest["incident_id"] = "tampered"
            manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
            with self.assertRaises(BackupConflictError):
                backup_strategy_db_once(TASK_ID, repo_root=root)
            self.assertEqual(manifest_path.read_text(encoding="utf-8"), json.dumps(manifest, sort_keys=True))
        finally:
            temp_dir.cleanup()

    def test_backup_verify_and_rename_failures_leave_no_final_or_staging(self):
        from scripts.backup_strategy_db_once import BackupError, _backup_strategy_db_once

        for fault in ("backup", "verify", "rename"):
            with self.subTest(fault=fault):
                temp_dir, root = _make_temp_repo()
                try:
                    with self.assertRaises(BackupError):
                        _backup_strategy_db_once(TASK_ID, repo_root=root, _fault=fault)
                    backup_root = root / "data" / "strategy_backups" / "b6_preclaim"
                    self.assertFalse(list(backup_root.glob("*.sqlite3")))
                    self.assertFalse(list(backup_root.glob(".*.staging-*")))
                finally:
                    temp_dir.cleanup()

    def test_owner_is_read_only_source_backup_only_and_cli_rejects_extra_paths(self):
        import scripts.backup_strategy_db_once as owner

        source = Path(owner.__file__).read_text(encoding="utf-8")
        self.assertIn(".backup(", source)
        self.assertNotIn("from backend.db.strategy", source)
        self.assertNotIn("StrategyDB(", source)
        self.assertNotIn("OOSBudgetLedger", source)
        self.assertNotIn("migrate_", source)
        self.assertNotIn("shutil", source)
        output = StringIO()
        with patch("sys.stdout", output):
            self.assertEqual(owner.main([]), 2)
            self.assertEqual(owner.main(["task", "extra"]), 2)
        self.assertIn('"status":"invalid_invocation"', output.getvalue().replace(" ", ""))


if __name__ == "__main__":
    unittest.main()
