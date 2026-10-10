"""Focused synthetic tests for the explicit-task B6 CLI boundary."""

from __future__ import annotations

import ast
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from io import StringIO
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from backend.services.b6_validation_worker import B6WorkerResult


class _RecordingWorker:
    def __init__(self, result: B6WorkerResult, calls: list[tuple[str, object]]) -> None:
        self.result = result
        self.calls = calls

    def run_task(self, task_id: str, *, execute_same_draw=None) -> B6WorkerResult:
        self.calls.append((task_id, execute_same_draw))
        return self.result


def _result(status: str, *, task_status: str = "queued") -> B6WorkerResult:
    return B6WorkerResult(
        task_id="task-synthetic-cli-001",
        task_key="k" * 64,
        task_status=task_status,
        status=status,
        reason=status,
        ready_for_reservation=status == "ready_for_reservation",
    )


class TestRunB6ValidationTask(unittest.TestCase):
    def _temp_root(self):
        directory = tempfile.TemporaryDirectory(prefix="b6-cli-")
        root = Path(directory.name)
        (root / "data").mkdir()
        return directory, root

    def _db_factory(self, opened):
        from backend.db.strategy import StrategyDB

        def factory(path):
            db = StrategyDB(str(path))
            opened.append(db)
            return db

        return factory

    @staticmethod
    def _noop_backup(_task_id, *, repo_root):
        return {"status": "published", "repo_root": str(repo_root)}

    def test_no_id_latest_and_extra_parameters_are_rejected_without_db_or_oos_side_effect(self):
        import scripts.run_b6_validation_task as cli

        for argv in ([], ["latest"], ["queued"], ["task-1", "task-2"], ["--task-id", "task-1"]):
            output = StringIO()
            with redirect_stdout(output):
                exit_code = cli.main(argv)
            self.assertEqual(exit_code, cli.EXIT_INVALID_INVOCATION, argv)
            payload = json.loads(output.getvalue())
            self.assertEqual(payload["status"], "invalid_invocation")
            self.assertEqual(payload["task_id"], None)

    def test_direct_script_entry_bootstraps_repo_root_before_importing_contracts(self):
        repo_root = Path(__file__).resolve().parents[1]
        script = repo_root / "scripts" / "run_b6_validation_task.py"
        environment = dict(__import__("os").environ)
        environment.pop("PYTHONPATH", None)

        completed = subprocess.run(
            [sys.executable, str(script)],
            cwd=repo_root,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 64)
        self.assertEqual(completed.stderr, "")
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["status"], "invalid_invocation")
        self.assertEqual(payload["reason"], "invalid task invocation")

    def test_exact_task_id_is_passed_once_and_no_polling_or_latest_scan_exists(self):
        import scripts.run_b6_validation_task as cli

        directory, root = self._temp_root()
        try:
            calls = []
            opened = []
            fake_executor = object()
            worker_result = _result("ready_for_reservation")

            def worker_factory(db, **_kwargs):
                return _RecordingWorker(worker_result, calls)

            code, payload = cli._run_task(
                "exact-task-id",
                repo_root=root,
                dependency_factory=lambda _root: fake_executor,
                db_factory=self._db_factory(opened),
                worker_factory=worker_factory,
                backup_factory=self._noop_backup,
            )

            self.assertEqual(code, cli.EXIT_BY_STATUS["ready_for_reservation"])
            self.assertEqual(payload["task_id"], worker_result.task_id)
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0][0], "exact-task-id")
            self.assertIs(calls[0][1], fake_executor)
            self.assertEqual(len(opened), 1)
            with self.assertRaises(sqlite3.ProgrammingError):
                opened[0].conn.execute("SELECT 1")
        finally:
            directory.cleanup()

    def test_missing_real_executor_blocks_before_claim(self):
        import scripts.run_b6_validation_task as cli

        directory, root = self._temp_root()
        try:
            db_called = []

            def forbidden_db(_path):
                db_called.append(True)
                raise AssertionError("DB must not open when dependency construction fails")

            def missing_executor(_root):
                raise FileNotFoundError("real same-draw executor dependency missing")

            code, payload = cli._run_task(
                "task-before-claim",
                repo_root=root,
                dependency_factory=missing_executor,
                db_factory=forbidden_db,
            )
            self.assertEqual(code, cli.EXIT_DEPENDENCY_FAILURE)
            self.assertEqual(payload["status"], "dependency_failed")
            self.assertEqual(db_called, [])
            self.assertFalse((root / "data" / "strategy.db").exists())
        finally:
            directory.cleanup()

    def test_worker_boundary_maps_queued_blocked_failed_completed_recovery_required_stably(self):
        import scripts.run_b6_validation_task as cli

        for status in ("completed", "blocked", "failed", "recovery_required", "ready_for_reservation"):
            directory, root = self._temp_root()
            try:
                worker_result = _result(status, task_status=status)

                def worker_factory(db, result=worker_result, **_kwargs):
                    return _RecordingWorker(result, [])

                code, payload = cli._run_task(
                    "task-status-boundary",
                    repo_root=root,
                    dependency_factory=lambda _root: (lambda _envelope: None),
                    db_factory=self._db_factory([]),
                    worker_factory=worker_factory,
                    backup_factory=self._noop_backup,
                )
                self.assertEqual(code, cli.EXIT_BY_STATUS[status])
                self.assertEqual(payload["status"], status)
                self.assertEqual(payload["task_status"], status)
                encoded_once = cli._canonical_json(payload)
                self.assertEqual(encoded_once, cli._canonical_json(payload))
            finally:
                directory.cleanup()

    def test_cli_never_exposes_window_hash_cost_benchmark_or_promotion_inputs(self):
        import scripts.run_b6_validation_task as cli

        source = Path(cli.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main")
        self.assertEqual([arg.arg for arg in main.args.args], ["argv"])
        calls = {
            node.func.id if isinstance(node.func, ast.Name) else node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and (isinstance(node.func, ast.Name) or isinstance(node.func, ast.Attribute))
        }
        self.assertNotIn("poll_once", calls)
        self.assertNotIn("promote_to_prototype_passed", calls)
        builder_source = source[source.index("def _build_production_executor"):source.index("def _result_payload")]
        self.assertIn("execute_production_same_draw", builder_source)
        self.assertIn("FormalPITPartitionAdapter", builder_source)
        self.assertIn("partial(execute_production_same_draw", builder_source)
        for forbidden in ("--window", "--cost", "--benchmark", "--universe", "--source", "--strategy"):
            self.assertNotIn(forbidden, source)

    def test_worker_exception_is_stable_and_closes_db(self):
        import scripts.run_b6_validation_task as cli

        directory, root = self._temp_root()
        try:
            opened = []

            class FailingWorker:
                def __init__(self, db, **_kwargs):
                    self.db = db

                def run_task(self, task_id, *, execute_same_draw):
                    raise RuntimeError("synthetic worker failure")

            code, payload = cli._run_task(
                "task-worker-error",
                repo_root=root,
                dependency_factory=lambda _root: (lambda _envelope: None),
                db_factory=self._db_factory(opened),
                worker_factory=FailingWorker,
                backup_factory=self._noop_backup,
            )
            self.assertEqual(code, cli.EXIT_WORKER_FAILURE)
            self.assertEqual(payload["status"], "failed")
            self.assertEqual(payload["reason"], "b6_worker_failed")
            self.assertEqual(len(opened), 1)
            with self.assertRaises(sqlite3.ProgrammingError):
                opened[0].conn.execute("SELECT 1")
        finally:
            directory.cleanup()

    def test_cli_emits_ordered_jsonl_progress_on_stderr_and_canonical_result_on_stdout(self):
        import scripts.run_b6_validation_task as cli

        directory, root = self._temp_root()
        try:
            progress = StringIO()
            stdout = StringIO()
            result = _result("completed", task_status="completed")

            def worker_factory(_db, **_kwargs):
                return _RecordingWorker(result, [])

            with redirect_stdout(stdout):
                code, payload = cli._run_task(
                    "progress-task",
                    repo_root=root,
                    dependency_factory=lambda _root: object(),
                    db_factory=self._db_factory([]),
                    worker_factory=worker_factory,
                    backup_factory=self._noop_backup,
                    progress_stream=progress,
                )
                print(cli._canonical_json(payload))

            events = [json.loads(line) for line in progress.getvalue().splitlines()]
            self.assertEqual(code, cli.EXIT_OK)
            self.assertEqual([event["event_seq"] for event in events], [1, 2, 3, 4])
            self.assertEqual(
                [event["stage"] for event in events],
                ["preflight", "dependencies_prepared", "executing", "terminal"],
            )
            self.assertEqual([event["task_id"] for event in events], ["progress-task"] * 4)
            for event in events:
                self.assertEqual(
                    set(event),
                    {
                        "schema_version",
                        "event_seq",
                        "stage",
                        "task_id",
                        "task_status",
                        "status",
                    },
                )
                self.assertEqual(event["schema_version"], "b6_validation_progress.v1")
            self.assertEqual(stdout.getvalue(), cli._canonical_json(payload) + "\n")
        finally:
            directory.cleanup()

    def test_preclaim_backup_uses_sqlite_consistency_backup_and_blocks_claim_on_failure(self):
        import scripts.run_b6_validation_task as cli
        from scripts.backup_strategy_db_once import _backup_strategy_db_once, BackupError

        directory, root = self._temp_root()
        try:
            incident = root / "docs" / "verification"
            incident.mkdir(parents=True)
            incident_file = incident / "v3_e4_protocol_migration_incident_20260823.json"
            incident_file.write_text(
                json.dumps(
                    {
                        "incident_id": "v3_e4_protocol_migration_incident_20260823",
                        "status": "contained_not_yet_recovered",
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            db_path = root / "data" / "strategy.db"
            with sqlite3.connect(db_path) as conn:
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
                    """
                )
                conn.execute(
                    "INSERT INTO research_protocol_snapshots VALUES (?, ?, ?, ?)",
                    ("protocol-1", "revision-1", "b6_coverage_bound", "{}"),
                )
                conn.execute(
                    "INSERT INTO b6_validation_tasks VALUES (?, ?, ?, ?, ?)",
                    ("backup-task", "k" * 64, "queued", "protocol-1", "{}"),
                )
                conn.commit()
            conn.close()

            opened = []
            worker_calls = []

            def db_factory(path):
                opened.append(path)
                raise AssertionError("claim DB must not open after preclaim backup failure")

            def worker_factory(*_args, **_kwargs):
                worker_calls.append(True)
                raise AssertionError("worker must not be constructed after backup failure")

            code, payload = cli._run_task(
                "backup-task",
                repo_root=root,
                dependency_factory=lambda _root: object(),
                db_factory=db_factory,
                worker_factory=worker_factory,
                backup_factory=lambda task_id, *, repo_root: _backup_strategy_db_once(
                    task_id, repo_root=repo_root, _fault="backup"
                ),
            )
            self.assertEqual(code, cli.EXIT_BY_STATUS["blocked"])
            self.assertEqual(payload["status"], "blocked")
            self.assertEqual(payload["reason"], "b6_preclaim_backup_failed")
            self.assertEqual(opened, [])
            self.assertEqual(worker_calls, [])
            with sqlite3.connect(db_path) as conn:
                self.assertEqual(
                    conn.execute(
                        "SELECT status FROM b6_validation_tasks WHERE task_id='backup-task'"
                    ).fetchone()[0],
                    "queued",
                )
            conn.close()
        finally:
            directory.cleanup()

    def test_cli_rejects_user_backup_path_and_all_oos_override_arguments(self):
        import scripts.run_b6_validation_task as cli

        for argv in (
            ["task-1", "--backup-path", "custom.sqlite3"],
            ["task-1", "--oos-override"],
            ["task-1", "--allow-oos"],
            ["task-1", "--promotion-id", "p1"],
        ):
            output = StringIO()
            error = StringIO()
            with redirect_stdout(output), redirect_stderr(error):
                exit_code = cli.main(argv)
            self.assertEqual(exit_code, cli.EXIT_INVALID_INVOCATION, argv)
            self.assertEqual(error.getvalue(), "")
            payload = json.loads(output.getvalue())
            self.assertEqual(payload["status"], "invalid_invocation")
            self.assertFalse(payload["oos_authorized"])

    def test_runbook_matches_queued_running_reserved_started_completed_failed_matrix(self):
        runbook = Path(__file__).parents[1] / "docs" / "operations" / "b6-validation-recovery-runbook.md"
        source = runbook.read_text(encoding="utf-8")
        for state in ("queued", "running", "reserved", "started", "completed", "failed"):
            self.assertIn(f"`{state}`", source)
        self.assertIn("requeue", source)
        self.assertIn("release", source)
        self.assertIn("fail_after_start", source)
        self.assertIn("never rerun", source)
        self.assertIn("exactly one explicit task_id", source)
        self.assertIn("data/strategy_backups/b6_preclaim", source)


if __name__ == "__main__":
    unittest.main()
