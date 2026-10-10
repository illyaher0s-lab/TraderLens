"""C1b tests for the explicit B6 successor owner CLI."""

from __future__ import annotations

from contextlib import closing
from io import StringIO
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from backend.db.strategy import StrategyDB
from tests.test_b6_successor_attempt import _seed_failed_v2


def _incident(root: Path) -> None:
    path = root / "docs" / "verification" / "v3_e4_protocol_migration_incident_20260823.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "incident_id": "v3_e4_protocol_migration_incident_20260823",
                "status": "contained_not_yet_recovered",
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _temp_failed_root(raw_tmp: str) -> tuple[Path, dict]:
    root = Path(raw_tmp)
    (root / "data").mkdir(parents=True)
    case = _seed_failed_v2(root / "data" / "strategy.db")
    _incident(root)
    case["db"].close()
    return root, case


class TestB6SuccessorCLI(unittest.TestCase):
    def test_cli_requires_one_explicit_predecessor_and_no_overrides(self):
        cli = __import__("scripts.create_b6_successor_attempt", fromlist=["main"])
        for argv in (
            (),
            ("pred", "extra"),
            ("latest",),
            ("queued",),
            ("--task-id", "pred"),
            ("pred/path",),
        ):
            with self.subTest(argv=argv):
                with self.assertRaises(ValueError):
                    cli._parse_predecessor_task_id(argv)
        predecessor = "a" * 64
        self.assertEqual(cli._parse_predecessor_task_id((predecessor,)), predecessor)

    def test_backup_completes_before_owner_write_and_result_is_canonical(self):
        cli = __import__("scripts.create_b6_successor_attempt", fromlist=["_run_successor"])
        with tempfile.TemporaryDirectory(prefix="b6-c1b-cli-") as raw_tmp:
            root, case = _temp_failed_root(raw_tmp)
            events: list[str] = []
            stdout = StringIO()
            stderr = StringIO()

            def backup_factory(task_id, *, repo_root):
                events.append("backup")
                return cli.backup_strategy_db_once(task_id, repo_root=repo_root)

            def db_factory(path):
                events.append("db_open")
                return StrategyDB(str(path))

            code, payload = cli._run_successor(
                case["predecessor"].task_id,
                repo_root=root,
                backup_factory=backup_factory,
                db_factory=db_factory,
                stdout=stdout,
                progress_stream=stderr,
            )
            self.assertEqual(code, cli.EXIT_OK)
            self.assertEqual(events, ["backup", "db_open"])
            self.assertEqual(payload["schema_version"], "b6_successor_attempt.cli.v1")
            self.assertEqual(payload["predecessor_task_id"], case["predecessor"].task_id)
            self.assertEqual(payload["task_contract_version"], "v3")
            self.assertEqual(payload["task_status"], "queued")
            self.assertFalse(payload["oos_authorized"])
            self.assertFalse(payload["oos_consumed"])
            self.assertIsNone(payload["promotion_id"])
            self.assertEqual(json.loads(stdout.getvalue()), payload)
            progress = [json.loads(line) for line in stderr.getvalue().splitlines()]
            self.assertEqual([event["event_seq"] for event in progress], list(range(1, len(progress) + 1)))
            self.assertEqual([event["stage"] for event in progress], ["preflight", "backup", "owner_write", "terminal"])
            self.assertTrue(all(set(event) == {
                "schema_version", "event_seq", "stage", "predecessor_task_id", "successor_task_id", "status"
            } for event in progress))
            with closing(sqlite3.connect(case["path"])) as conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM b6_validation_tasks").fetchone()[0], 2)
            second_stdout = StringIO()
            second_code, second_payload = cli._run_successor(
                case["predecessor"].task_id,
                repo_root=root,
                backup_factory=cli.backup_strategy_db_once,
                db_factory=db_factory,
                stdout=second_stdout,
            )
            self.assertEqual(second_code, cli.EXIT_OK)
            self.assertEqual(second_payload["status"], "reused")
            self.assertEqual(second_payload["successor_task_id"], payload["successor_task_id"])
            self.assertEqual(json.loads(second_stdout.getvalue()), second_payload)
            with closing(sqlite3.connect(case["path"])) as conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM b6_validation_tasks").fetchone()[0], 2)

    def test_blocked_backup_or_precondition_has_no_db_write(self):
        cli = __import__("scripts.create_b6_successor_attempt", fromlist=["_run_successor"])
        with tempfile.TemporaryDirectory(prefix="b6-c1b-cli-blocked-") as raw_tmp:
            root, case = _temp_failed_root(raw_tmp)
            calls: list[str] = []

            def db_factory(path):
                calls.append("db_open")
                return StrategyDB(str(path))

            code, payload = cli._run_successor(
                case["predecessor"].task_id,
                repo_root=root,
                backup_factory=lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("backup blocked")),
                db_factory=db_factory,
            )
            self.assertEqual(code, cli.EXIT_BLOCKED)
            self.assertEqual(payload["status"], "blocked")
            self.assertEqual(calls, [])
            with closing(sqlite3.connect(case["path"])) as conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM b6_validation_tasks").fetchone()[0], 1)

        with tempfile.TemporaryDirectory(prefix="b6-c1b-cli-precondition-") as raw_tmp:
            root, case = _temp_failed_root(raw_tmp)
            with closing(sqlite3.connect(case["path"])) as conn:
                conn.execute(
                    "UPDATE b6_validation_tasks SET status='queued', claimed_at=NULL, completed_at=NULL "
                    "WHERE task_id=?",
                    (case["predecessor"].task_id,),
                )
                conn.commit()
            calls: list[str] = []

            def db_factory(path):
                calls.append("db_open")
                return StrategyDB(str(path))

            code, payload = cli._run_successor(
                case["predecessor"].task_id,
                repo_root=root,
                backup_factory=cli.backup_strategy_db_once,
                db_factory=db_factory,
            )
            self.assertEqual(code, cli.EXIT_BLOCKED)
            self.assertEqual(payload["reason"], "b6_successor_predecessor_not_failed")
            self.assertEqual(calls, ["db_open"])
            with closing(sqlite3.connect(case["path"])) as conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM b6_validation_tasks").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
