"""C1a tests for the write-once B6 successor-attempt owner."""

from __future__ import annotations

from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from backend.db.strategy import StrategyDB
from backend.services.oos_budget_ledger import OOSBudgetLedger
from contracts.b6_task import (
    B6ValidationTask,
    build_b6_task_id,
    build_b6_task_key,
)
from contracts.strategy import (
    BacktestUniverseSpec,
    ImmutableBacktestReport,
    OOSEvaluationLedger,
    PrototypeGateResultV2,
    ResearchProtocolSnapshot,
    StrategyDraft,
    StrategyLifecycleState,
    compute_b6_protocol_id_from_fields,
)


def _successor_key(predecessor: B6ValidationTask) -> str:
    from contracts import b6_task

    builder = getattr(b6_task, "build_b6_successor_task_key", None)
    if not callable(builder):
        raise AssertionError("C1a v3 successor key builder is not implemented")
    return builder(
        predecessor_task_id=predecessor.task_id,
        predecessor_task_key=predecessor.task_key,
        strategy_revision_id=predecessor.strategy_revision_id,
        protocol_snapshot_id=predecessor.protocol_snapshot_id,
        b5_bundle_id=predecessor.b5_bundle_id,
        b5_bundle_manifest_sha256=predecessor.b5_bundle_manifest_sha256,
        attempt_number=1,
    )


def _seed_failed_v2(path: Path) -> dict:
    db = StrategyDB(str(path))
    universe = BacktestUniverseSpec(
        universe_spec_id="successor-universe",
        universe_rule_type="point_in_time_membership",
        membership_source="c1a-test",
        membership_effective_from=date(2024, 1, 1),
        membership_effective_to=date(2024, 12, 31),
        snapshot_date=date(2024, 1, 1),
        membership_snapshot_ids=("successor-membership",),
        quality_status="ok",
    )
    draft = StrategyDraft(
        strategy_revision_id="successor-revision",
        theme_id="successor-theme",
        hypothesis_id="successor-hypothesis",
        strategy_template_id="successor-template",
        strategy_template_version="v1",
        strategy_template_hash="successor-template-hash",
        hypothesis_source_snapshot_id="successor-hypothesis-snapshot",
        backtest_universe_spec_id=universe.universe_spec_id,
        strategy_config_json="{}",
        sample_split_rule_id="successor-split",
        created_at=datetime(2026, 9, 3, 12, 0, 0),
    )
    protocol_data = {
        "protocol_snapshot_id": "placeholder",
        "theme_id": draft.theme_id,
        "hypothesis_source_snapshot_id": draft.hypothesis_source_snapshot_id,
        "strategy_revision_id": draft.strategy_revision_id,
        "sample_split_rule_id": draft.sample_split_rule_id,
        "oos_window_rule_id": "successor-window-rule",
        "oos_window_rule_params_json": "{}",
        "oos_window_start": date(2024, 1, 1),
        "oos_window_end": date(2024, 12, 31),
        "shared_oos_window_id": "successor-window",
        "backtest_universe_spec_id": universe.universe_spec_id,
        "strategy_config_hash": "1" * 64,
        "data_snapshot_id": "successor-data",
        "data_snapshot_hash": "2" * 64,
        "kill_criteria_snapshot_id": "successor-kill",
        "prototype_gate_thresholds_json": '{"threshold":0.5}',
        "gate_criteria_hash": "3" * 64,
        "frozen_at": datetime(2026, 9, 3, 12, 0, 0),
        "frozen_by": "c1a-test",
        "protocol_profile": "b6_coverage_bound",
        "availability_successor_id": "successor-availability",
        "availability_successor_manifest_hash": "4" * 64,
        "availability_successor_algorithm_hash": "5" * 64,
        "predecessor_qualification_id": "successor-qualification",
        "predecessor_qualification_manifest_hash": "6" * 64,
        "predecessor_qualification_status": "availability_bounded_qualified",
        "predecessor_qualification_algorithm_hash": "7" * 64,
        "coverage_package_id": "successor-coverage",
        "coverage_manifest_hash": "8" * 64,
        "coverage_algorithm_hash": "9" * 64,
        "source_scope_hash": "a" * 64,
        "data_requirements_hash": "b" * 64,
        "expected_stock_days": 100,
        "complete_stock_days": 90,
        "unavailable_stock_days": 10,
        "gate_snapshot_id": "successor-gate",
        "gate_content_hash": "c" * 64,
        "kill_content_hash": "d" * 64,
    }
    protocol_data["protocol_snapshot_id"] = compute_b6_protocol_id_from_fields(
        **{
            key: value
            for key, value in protocol_data.items()
            if key not in {"protocol_snapshot_id", "frozen_at", "frozen_by", "frozen"}
        }
    )
    protocol = ResearchProtocolSnapshot(**protocol_data)
    db.store_backtest_universe(universe)
    db.create_strategy_draft(
        draft,
        StrategyLifecycleState(
            lifecycle_state_id="successor-lifecycle",
            strategy_revision_id=draft.strategy_revision_id,
            state_version=1,
            state="draft",
            source_record_id="successor-initial",
            recorded_at=datetime(2026, 9, 3, 12, 0, 0),
            recorded_by="c1a-test",
        ),
    )
    db.store_protocol_snapshot(protocol)
    b5_id = "successor-b5"
    b5_sha = "4" * 64
    task_key = build_b6_task_key(
        strategy_revision_id=draft.strategy_revision_id,
        protocol_snapshot_id=protocol.protocol_snapshot_id,
        task_contract_version="v2",
        b5_bundle_id=b5_id,
        b5_bundle_manifest_sha256=b5_sha,
    )
    task = B6ValidationTask(
        task_id=build_b6_task_id(task_key),
        task_key=task_key,
        task_type="b6_validation",
        task_contract_version="v2",
        strategy_revision_id=draft.strategy_revision_id,
        protocol_snapshot_id=protocol.protocol_snapshot_id,
        status="queued",
        created_at=datetime(2026, 9, 3, 12, 1, 0),
        b5_bundle_id=b5_id,
        b5_bundle_manifest_sha256=b5_sha,
    )
    winner, created = db.create_or_get_b6_task(task)
    if not created:
        raise AssertionError("C1a setup did not create its v2 predecessor")
    claimed = db.claim_b6_task(winner.task_id)
    if claimed is None:
        raise AssertionError("C1a setup did not claim its v2 predecessor")
    db.update_b6_task_status(
        claimed.task_id,
        "failed",
        completed_at=datetime(2026, 9, 3, 12, 2, 0),
        blocking_reason_code="invariant_error",
        blocking_reason_detail="synthetic pre-reservation failure",
    )
    db.conn.commit()
    failed = db.get_b6_task_by_id(claimed.task_id)
    if failed is None or failed.status != "failed":
        raise AssertionError("C1a setup did not persist failed predecessor")
    return {"db": db, "path": path, "protocol": protocol, "predecessor": failed}


def _task_row(path: Path, task_id: str) -> dict:
    with closing(sqlite3.connect(str(path))) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM b6_validation_tasks WHERE task_id = ?", (task_id,)
        ).fetchone()
        return dict(row) if row is not None else {}


def _seed_pre005_v2_row(path: Path) -> B6ValidationTask:
    """Build a migration-004 database without running StrategyDB migrations."""
    from backend.db.migrations.migration_001_add_hypothesis_to_audit import (
        migrate_oos_evaluation_ledgers_add_hypothesis,
    )
    from backend.db.migrations.migration_002_add_b6_runtime_schema import (
        migrate_add_b6_runtime_schema,
    )
    from backend.db.migrations.migration_003_add_b5_binding_to_b6_tasks import (
        migrate_add_b5_binding_to_b6_tasks,
    )
    from backend.db.migrations.migration_004_allow_protocol_multiplicity import (
        migrate_allow_protocol_multiplicity,
    )

    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA foreign_keys = ON")
    schema_owner = StrategyDB.__new__(StrategyDB)
    schema_owner.conn = conn
    StrategyDB._initialize_schema(schema_owner)
    migrate_oos_evaluation_ledgers_add_hypothesis(conn)
    migrate_add_b6_runtime_schema(conn)
    migrate_add_b5_binding_to_b6_tasks(conn)
    migrate_allow_protocol_multiplicity(conn)

    conn.execute(
        "INSERT INTO backtest_universe_specs "
        "(universe_spec_id, payload_json, created_at) VALUES (?, ?, ?)",
        ("legacy-universe", "{}", "2026-09-03T12:00:00"),
    )
    conn.execute(
        "INSERT INTO strategy_drafts "
        "(strategy_revision_id, theme_id, hypothesis_id, backtest_universe_spec_id, payload_json, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            "legacy-revision",
            "legacy-theme",
            "legacy-hypothesis",
            "legacy-universe",
            "{}",
            "2026-09-03T12:00:00",
        ),
    )
    conn.execute(
        "INSERT INTO research_protocol_snapshots "
        "(protocol_snapshot_id, strategy_revision_id, payload_json, strategy_config_hash, "
        "data_snapshot_hash, gate_criteria_hash, frozen_at, protocol_profile) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "legacy-protocol",
            "legacy-revision",
            "{}",
            "legacy-config",
            "legacy-data",
            "legacy-gate",
            "2026-09-03T12:00:00",
            "legacy_b3",
        ),
    )
    b5_id = "legacy-b5"
    b5_sha = "e" * 64
    task_key = build_b6_task_key(
        strategy_revision_id="legacy-revision",
        protocol_snapshot_id="legacy-protocol",
        task_contract_version="v2",
        b5_bundle_id=b5_id,
        b5_bundle_manifest_sha256=b5_sha,
    )
    task = B6ValidationTask(
        task_id=build_b6_task_id(task_key),
        task_key=task_key,
        task_type="b6_validation",
        task_contract_version="v2",
        strategy_revision_id="legacy-revision",
        protocol_snapshot_id="legacy-protocol",
        status="failed",
        blocking_reason_code="legacy_failure",
        blocking_reason_detail="legacy fixture",
        created_at=datetime(2026, 9, 3, 12, 1, 0),
        claimed_at=datetime(2026, 9, 3, 12, 1, 30),
        completed_at=datetime(2026, 9, 3, 12, 2, 0),
        b5_bundle_id=b5_id,
        b5_bundle_manifest_sha256=b5_sha,
    )
    conn.execute(
        "INSERT INTO b6_validation_tasks "
        "(task_id, task_key, task_type, task_contract_version, strategy_revision_id, "
        "protocol_snapshot_id, status, blocking_reason_code, blocking_reason_detail, "
        "payload_json, created_at, claimed_at, completed_at, b5_bundle_id, "
        "b5_bundle_manifest_sha256) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            task.task_id,
            task.task_key,
            task.task_type,
            task.task_contract_version,
            task.strategy_revision_id,
            task.protocol_snapshot_id,
            task.status,
            task.blocking_reason_code,
            task.blocking_reason_detail,
            task.model_dump_json(),
            task.created_at.isoformat(),
            task.claimed_at.isoformat(),
            task.completed_at.isoformat(),
            task.b5_bundle_id,
            task.b5_bundle_manifest_sha256,
        ),
    )
    conn.commit()
    conn.close()
    return task


class TestB6SuccessorTaskContract(unittest.TestCase):
    def test_v3_requires_predecessor_binding_and_attempt_one(self):
        with tempfile.TemporaryDirectory(prefix="b6-c1a-contract-") as raw_tmp:
            case = _seed_failed_v2(Path(raw_tmp) / "contract.db")
            try:
                predecessor = case["predecessor"]
                key = _successor_key(predecessor)
                task = B6ValidationTask(
                    task_id=build_b6_task_id(key),
                    task_key=key,
                    task_type="b6_validation",
                    task_contract_version="v3",
                    strategy_revision_id=predecessor.strategy_revision_id,
                    protocol_snapshot_id=predecessor.protocol_snapshot_id,
                    status="queued",
                    created_at=datetime(2026, 9, 3, 12, 3, 0),
                    b5_bundle_id=predecessor.b5_bundle_id,
                    b5_bundle_manifest_sha256=predecessor.b5_bundle_manifest_sha256,
                    predecessor_task_id=predecessor.task_id,
                    predecessor_task_key=predecessor.task_key,
                    successor_attempt_number=1,
                )
                self.assertEqual(task.task_contract_version, "v3")
                invalid = (
                    {"predecessor_task_id": None},
                    {"predecessor_task_key": None},
                    {"successor_attempt_number": 2},
                    {"predecessor_task_id": "other"},
                )
                for update in invalid:
                    with self.subTest(update=update):
                        values = task.model_dump()
                        values.update(update)
                        with self.assertRaises(Exception):
                            B6ValidationTask(**values)
            finally:
                case["db"].close()

    def test_v3_key_is_distinct_and_v1_v2_keys_are_unchanged(self):
        from contracts.b6_task import B6_TASK_TYPE, B6_PROTOCOL_PROFILE

        v1 = build_b6_task_key(
            strategy_revision_id="r",
            protocol_snapshot_id="p",
            task_contract_version="v1",
        )
        v2 = build_b6_task_key(
            strategy_revision_id="r",
            protocol_snapshot_id="p",
            task_contract_version="v2",
            b5_bundle_id="b5",
            b5_bundle_manifest_sha256="a" * 64,
        )
        expected_v1 = hashlib.sha256(
            json.dumps(
                {
                    "protocol_profile": B6_PROTOCOL_PROFILE,
                    "protocol_snapshot_id": "p",
                    "strategy_revision_id": "r",
                    "task_contract_version": "v1",
                    "task_type": B6_TASK_TYPE,
                },
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()
        expected_v2 = hashlib.sha256(
            json.dumps(
                {
                    "b5_bundle_id": "b5",
                    "b5_bundle_manifest_sha256": "a" * 64,
                    "protocol_profile": B6_PROTOCOL_PROFILE,
                    "protocol_snapshot_id": "p",
                    "strategy_revision_id": "r",
                    "task_contract_version": "v2",
                    "task_type": B6_TASK_TYPE,
                },
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()
        self.assertEqual(v1, expected_v1)
        self.assertEqual(v2, expected_v2)
        with tempfile.TemporaryDirectory(prefix="b6-c1a-key-") as raw_tmp:
            case = _seed_failed_v2(Path(raw_tmp) / "key.db")
            try:
                predecessor = case["predecessor"]
                successor = _successor_key(predecessor)
                self.assertNotEqual(successor, v2)
                self.assertEqual(len(successor), 64)
                expected_v3 = hashlib.sha256(
                    json.dumps(
                        {
                            "attempt_number": 1,
                            "b5_bundle_id": predecessor.b5_bundle_id,
                            "b5_bundle_manifest_sha256": predecessor.b5_bundle_manifest_sha256,
                            "predecessor_task_id": predecessor.task_id,
                            "predecessor_task_key": predecessor.task_key,
                            "protocol_profile": B6_PROTOCOL_PROFILE,
                            "protocol_snapshot_id": predecessor.protocol_snapshot_id,
                            "strategy_revision_id": predecessor.strategy_revision_id,
                            "task_contract_version": "v3",
                            "task_type": B6_TASK_TYPE,
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                        ensure_ascii=False,
                    ).encode("utf-8")
                ).hexdigest()
                self.assertEqual(successor, expected_v3)
            finally:
                case["db"].close()


class TestB6SuccessorSchema(unittest.TestCase):
    def test_fresh_and_upgrade_migrations_are_additive_idempotent_and_fk_clean(self):
        with tempfile.TemporaryDirectory(prefix="b6-c1a-schema-") as raw_tmp:
            path = Path(raw_tmp) / "fresh.db"
            db = StrategyDB(str(path))
            try:
                columns = {
                    row[1]
                    for row in db.conn.execute("PRAGMA table_info(b6_validation_tasks)")
                }
                self.assertTrue(
                    {
                        "predecessor_task_id",
                        "predecessor_task_key",
                        "successor_attempt_number",
                    }.issubset(columns)
                )
                index_sql = db.conn.execute(
                    "SELECT sql FROM sqlite_master WHERE type='index' AND name=?",
                    ("uq_b6_direct_successor_predecessor",),
                ).fetchone()
                self.assertIsNotNone(index_sql)
                self.assertIn("WHERE predecessor_task_id IS NOT NULL", index_sql[0])
                self.assertTrue(
                    any(
                        row[2] == "b6_validation_tasks"
                        and row[3] == "predecessor_task_id"
                        and row[4] == "task_id"
                        for row in db.conn.execute(
                            "PRAGMA foreign_key_list(b6_validation_tasks)"
                        )
                    )
                )
                self.assertEqual(db.conn.execute("PRAGMA foreign_key_check").fetchall(), [])
            finally:
                db.close()

            upgraded = StrategyDB(str(path))
            try:
                row_count = upgraded.conn.execute(
                    "SELECT COUNT(*) FROM b6_validation_tasks"
                ).fetchone()[0]
                self.assertEqual(row_count, 0)
                self.assertEqual(upgraded.conn.execute("PRAGMA foreign_key_check").fetchall(), [])
            finally:
                upgraded.close()

    def test_upgrade_preserves_v2_row_payload_and_indexes(self):
        with tempfile.TemporaryDirectory(prefix="b6-c1a-upgrade-") as raw_tmp:
            path = Path(raw_tmp) / "legacy.db"
            task = _seed_pre005_v2_row(path)
            before = _task_row(path, task.task_id)
            with closing(sqlite3.connect(str(path))) as before_conn:
                index_names_before = {
                    row[0]
                    for row in before_conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='index'"
                    )
                }
            from backend.db.migrations.migration_005_add_b6_successor_attempt import (
                migrate_add_b6_successor_attempt,
            )

            conn = sqlite3.connect(str(path))
            try:
                migrate_add_b6_successor_attempt(conn)
                migrate_add_b6_successor_attempt(conn)
                after = _task_row(path, before["task_id"])
                self.assertEqual(
                    {key: after[key] for key in before},
                    before,
                )
                self.assertIsNone(after["predecessor_task_id"])
                self.assertIsNone(after["predecessor_task_key"])
                self.assertIsNone(after["successor_attempt_number"])
                index_names_after = {
                    row[0]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='index'"
                    )
                }
                self.assertTrue(index_names_before.issubset(index_names_after))
                self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])
            finally:
                conn.close()


class TestB6SuccessorOwner(unittest.TestCase):
    def test_failed_pre_reservation_v2_creates_one_queued_v3_without_oos(self):
        with tempfile.TemporaryDirectory(prefix="b6-c1a-owner-") as raw_tmp:
            case = _seed_failed_v2(Path(raw_tmp) / "owner.db")
            try:
                predecessor = case["predecessor"]
                winner, created = case["db"].create_or_get_b6_successor_attempt(
                    predecessor.task_id
                )
                self.assertTrue(created)
                self.assertEqual(winner.status, "queued")
                self.assertEqual(winner.task_contract_version, "v3")
                self.assertEqual(winner.predecessor_task_id, predecessor.task_id)
                self.assertEqual(winner.predecessor_task_key, predecessor.task_key)
                self.assertEqual(winner.successor_attempt_number, 1)
                self.assertEqual(winner.strategy_revision_id, predecessor.strategy_revision_id)
                self.assertEqual(winner.protocol_snapshot_id, predecessor.protocol_snapshot_id)
                self.assertEqual(winner.b5_bundle_id, predecessor.b5_bundle_id)
                self.assertEqual(
                    winner.b5_bundle_manifest_sha256,
                    predecessor.b5_bundle_manifest_sha256,
                )
                with closing(sqlite3.connect(str(case["path"]))) as verify:
                    verify.row_factory = sqlite3.Row
                    self.assertEqual(
                        verify.execute("SELECT COUNT(*) FROM b6_validation_tasks").fetchone()[0],
                        2,
                    )
                    self.assertEqual(
                        verify.execute("SELECT COUNT(*) FROM oos_budget_state").fetchone()[0],
                        0,
                    )
                    self.assertEqual(
                        verify.execute("SELECT COUNT(*) FROM oos_budget_reservations").fetchone()[0],
                        0,
                    )
                    self.assertEqual(
                        verify.execute("SELECT COUNT(*) FROM oos_evaluation_ledgers").fetchone()[0],
                        0,
                    )
                    self.assertEqual(
                        verify.execute("SELECT COUNT(*) FROM immutable_backtest_reports").fetchone()[0],
                        0,
                    )
                    self.assertEqual(
                        verify.execute("SELECT COUNT(*) FROM prototype_gate_results_v2").fetchone()[0],
                        0,
                    )
                    self.assertEqual(
                        verify.execute(
                            "SELECT status FROM b6_validation_tasks WHERE task_id=?",
                            (predecessor.task_id,),
                        ).fetchone()[0],
                        "failed",
                    )
            finally:
                case["db"].close()

    def test_exact_retry_reuses_successor_in_any_legal_lifecycle_state(self):
        with tempfile.TemporaryDirectory(prefix="b6-c1a-retry-") as raw_tmp:
            case = _seed_failed_v2(Path(raw_tmp) / "retry.db")
            try:
                first, created = case["db"].create_or_get_b6_successor_attempt(
                    case["predecessor"].task_id
                )
                self.assertTrue(created)
                for status in ("queued", "running", "blocked", "completed", "failed"):
                    if status != "queued":
                        case["db"].update_b6_task_status(
                            first.task_id,
                            status,
                            completed_at=(datetime(2026, 9, 3, 12, 4, 0) if status in {"completed", "failed"} else None),
                            blocking_reason_code=("synthetic" if status in {"blocked", "failed"} else None),
                            blocking_reason_detail=("synthetic" if status in {"blocked", "failed"} else None),
                        )
                        case["db"].conn.commit()
                    reused, created_again = case["db"].create_or_get_b6_successor_attempt(
                        case["predecessor"].task_id
                    )
                    self.assertFalse(created_again)
                    self.assertEqual(reused.task_id, first.task_id)
                    self.assertEqual(reused.status, status)
                self.assertEqual(
                    case["db"].conn.execute(
                        "SELECT COUNT(*) FROM b6_validation_tasks WHERE predecessor_task_id IS NOT NULL"
                    ).fetchone()[0],
                    1,
                )
            finally:
                case["db"].close()

    def test_two_file_backed_connections_return_one_successor_winner(self):
        with tempfile.TemporaryDirectory(prefix="b6-c1a-concurrent-") as raw_tmp:
            path = Path(raw_tmp) / "concurrent.db"
            seed = _seed_failed_v2(path)
            predecessor_id = seed["predecessor"].task_id
            seed["db"].close()
            db1 = StrategyDB(str(path))
            db2 = StrategyDB(str(path))
            try:
                with ThreadPoolExecutor(max_workers=2) as pool:
                    results = list(
                        pool.map(
                            lambda db: db.create_or_get_b6_successor_attempt(predecessor_id),
                            (db1, db2),
                        )
                    )
                self.assertEqual({winner.task_id for winner, _ in results}, {results[0][0].task_id})
                self.assertEqual(sum(created for _, created in results), 1)
                with closing(sqlite3.connect(str(path))) as verify:
                    self.assertEqual(
                        verify.execute(
                            "SELECT COUNT(*) FROM b6_validation_tasks WHERE predecessor_task_id IS NOT NULL"
                        ).fetchone()[0],
                        1,
                    )
            finally:
                db2.close()
                db1.close()

    def test_nonfailed_or_v1_predecessor_is_rejected_without_write(self):
        for state in ("queued", "running", "completed", "blocked"):
            with self.subTest(state=state), tempfile.TemporaryDirectory(prefix="b6-c1a-state-") as raw_tmp:
                case = _seed_failed_v2(Path(raw_tmp) / f"{state}.db")
                try:
                    predecessor = case["predecessor"]
                    if state != "failed":
                        case["db"].update_b6_task_status(predecessor.task_id, state)
                        case["db"].conn.commit()
                    with self.assertRaises(Exception) as ctx:
                        case["db"].create_or_get_b6_successor_attempt(predecessor.task_id)
                    self.assertIn("successor", str(ctx.exception).lower())
                    self.assertEqual(
                        case["db"].conn.execute("SELECT COUNT(*) FROM b6_validation_tasks").fetchone()[0],
                        1,
                    )
                finally:
                    case["db"].close()

    def test_unclaimed_failed_and_failed_v3_predecessors_are_rejected(self):
        with tempfile.TemporaryDirectory(prefix="b6-c1a-unclaimed-") as raw_tmp:
            case = _seed_failed_v2(Path(raw_tmp) / "unclaimed.db")
            try:
                predecessor = case["predecessor"]
                case["db"].conn.execute(
                    "UPDATE b6_validation_tasks SET claimed_at=NULL WHERE task_id=?",
                    (predecessor.task_id,),
                )
                case["db"].conn.commit()
                with self.assertRaises(Exception) as ctx:
                    case["db"].create_or_get_b6_successor_attempt(predecessor.task_id)
                self.assertEqual(
                    getattr(ctx.exception, "reason_code", None),
                    "b6_successor_predecessor_not_failed",
                )
                self.assertEqual(
                    case["db"].conn.execute(
                        "SELECT COUNT(*) FROM b6_validation_tasks WHERE predecessor_task_id IS NOT NULL"
                    ).fetchone()[0],
                    0,
                )
            finally:
                case["db"].close()

        with tempfile.TemporaryDirectory(prefix="b6-c1a-v3-predecessor-") as raw_tmp:
            case = _seed_failed_v2(Path(raw_tmp) / "v3.db")
            try:
                successor, created = case["db"].create_or_get_b6_successor_attempt(
                    case["predecessor"].task_id
                )
                self.assertTrue(created)
                case["db"].update_b6_task_status(
                    successor.task_id,
                    "failed",
                    completed_at=datetime(2026, 9, 3, 12, 6, 0),
                    blocking_reason_code="synthetic",
                    blocking_reason_detail="synthetic",
                )
                case["db"].conn.commit()
                with self.assertRaises(Exception) as ctx:
                    case["db"].create_or_get_b6_successor_attempt(successor.task_id)
                self.assertEqual(
                    getattr(ctx.exception, "reason_code", None),
                    "b6_successor_predecessor_not_v2",
                )
            finally:
                case["db"].close()

    def test_oos_report_or_gate_evidence_blocks_successor_without_write(self):
        evidence_cases = ("state", "reservation", "ledger", "report", "gate")
        for evidence in evidence_cases:
            with self.subTest(evidence=evidence), tempfile.TemporaryDirectory(prefix="b6-c1a-evidence-") as raw_tmp:
                case = _seed_failed_v2(Path(raw_tmp) / f"{evidence}.db")
                try:
                    predecessor = case["predecessor"]
                    protocol = case["protocol"]
                    if evidence in {"state", "reservation"}:
                        reservation = OOSBudgetLedger(case["db"]).reserve_oos_draw(
                            protocol.theme_id,
                            protocol.hypothesis_source_snapshot_id,
                            protocol.strategy_config_hash,
                            protocol.data_snapshot_hash,
                            protocol.gate_criteria_hash,
                            protocol.shared_oos_window_id,
                            idempotency_key=predecessor.task_key,
                            task_key=predecessor.task_key,
                            protocol_snapshot_id=protocol.protocol_snapshot_id,
                        )
                        if evidence == "state":
                            OOSBudgetLedger(case["db"]).release_pre_execution(
                                reservation.reservation_id, "synthetic evidence"
                            )
                    elif evidence == "ledger":
                        case["db"].store_oos_ledger(
                            OOSEvaluationLedger(
                                ledger_snapshot_id="ledger-evidence",
                                theme_id=protocol.theme_id,
                                hypothesis_source_snapshot_id=protocol.hypothesis_source_snapshot_id,
                                ledger_version=1,
                                oos_evaluation_count=0,
                                next_oos_draw_index=1,
                                budget_status="available",
                                recorded_at=datetime(2026, 9, 3, 12, 5, 0),
                            )
                        )
                    else:
                        payload = {
                            "task_id": predecessor.task_id,
                            "task_key": predecessor.task_key,
                            "protocol_snapshot_id": predecessor.protocol_snapshot_id,
                            "same_draw_result": {
                                "identity": {
                                    "task_id": predecessor.task_id,
                                    "task_key": predecessor.task_key,
                                }
                            },
                        }
                        payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
                        report = ImmutableBacktestReport(
                            report_id=f"report-{evidence}",
                            theme_id=protocol.theme_id,
                            strategy_revision_id=predecessor.strategy_revision_id,
                            protocol_snapshot_id=protocol.protocol_snapshot_id,
                            strategy_config_hash=protocol.strategy_config_hash,
                            data_snapshot_hash=protocol.data_snapshot_hash,
                            gate_criteria_hash=protocol.gate_criteria_hash,
                            evaluation_mode="out_of_sample",
                            oos_draw_index=1,
                            shared_oos_window_id=protocol.shared_oos_window_id,
                            report_payload_json=payload_json,
                            integrity_status="valid",
                            generated_at=datetime(2026, 9, 3, 12, 5, 0),
                            report_hash=hashlib.sha256(payload_json.encode("utf-8")).hexdigest(),
                        )
                        case["db"].store_backtest_report(report)
                        if evidence == "gate":
                            checks_json = "[]"
                            case["db"].store_gate_result(
                                PrototypeGateResultV2(
                                    gate_result_id="gate-evidence",
                                    report_id=report.report_id,
                                    strategy_revision_id=report.strategy_revision_id,
                                    protocol_snapshot_id=report.protocol_snapshot_id,
                                    verdict="rejected",
                                    checks_json=checks_json,
                                    strategy_config_hash=protocol.strategy_config_hash,
                                    data_snapshot_hash=protocol.data_snapshot_hash,
                                    gate_criteria_hash=protocol.gate_criteria_hash,
                                    oos_draw_index=1,
                                    shared_oos_window_id=protocol.shared_oos_window_id,
                                    generated_at=datetime(2026, 9, 3, 12, 5, 0),
                                    gate_result_hash=hashlib.sha256(
                                        json.dumps(
                                            {"report_id": report.report_id, "verdict": "rejected", "checks": []},
                                            sort_keys=True,
                                        ).encode("utf-8")
                                    ).hexdigest(),
                                )
                            )
                    with self.assertRaises(Exception) as ctx:
                        case["db"].create_or_get_b6_successor_attempt(predecessor.task_id)
                    self.assertIn("successor", str(ctx.exception).lower())
                    self.assertEqual(
                        case["db"].conn.execute(
                            "SELECT COUNT(*) FROM b6_validation_tasks WHERE predecessor_task_id IS NOT NULL"
                        ).fetchone()[0],
                        0,
                    )
                finally:
                    case["db"].close()

    def test_predecessor_canonical_identity_corruption_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="b6-c1a-corrupt-") as raw_tmp:
            case = _seed_failed_v2(Path(raw_tmp) / "corrupt.db")
            try:
                case["db"].conn.execute(
                    "UPDATE b6_validation_tasks SET task_key=? WHERE task_id=?",
                    ("f" * 64, case["predecessor"].task_id),
                )
                case["db"].conn.commit()
                with self.assertRaises(Exception) as ctx:
                    case["db"].create_or_get_b6_successor_attempt(case["predecessor"].task_id)
                self.assertIn("successor", str(ctx.exception).lower())
                self.assertEqual(
                    case["db"].conn.execute(
                        "SELECT COUNT(*) FROM b6_validation_tasks WHERE predecessor_task_id IS NOT NULL"
                    ).fetchone()[0],
                    0,
                )
            finally:
                case["db"].close()

    def test_insert_failure_rolls_back_and_preserves_failed_predecessor(self):
        with tempfile.TemporaryDirectory(prefix="b6-c1a-rollback-") as raw_tmp:
            case = _seed_failed_v2(Path(raw_tmp) / "rollback.db")
            try:
                predecessor_before = _task_row(case["path"], case["predecessor"].task_id)
                case["db"].conn.execute(
                    """
                    CREATE TRIGGER fail_c1a_successor_insert
                    BEFORE INSERT ON b6_validation_tasks
                    WHEN NEW.task_contract_version = 'v3'
                    BEGIN SELECT RAISE(ABORT, 'forced C1a successor insert failure'); END;
                    """
                )
                case["db"].conn.commit()
                with self.assertRaises(Exception) as ctx:
                    case["db"].create_or_get_b6_successor_attempt(case["predecessor"].task_id)
                self.assertIn("forced C1a successor insert failure", str(ctx.exception))
                self.assertEqual(_task_row(case["path"], case["predecessor"].task_id), predecessor_before)
                self.assertEqual(
                    case["db"].conn.execute(
                        "SELECT COUNT(*) FROM b6_validation_tasks WHERE predecessor_task_id IS NOT NULL"
                    ).fetchone()[0],
                    0,
                )
            finally:
                case["db"].close()

    def test_existing_create_or_get_b6_task_v2_behavior_is_unchanged(self):
        with tempfile.TemporaryDirectory(prefix="b6-c1a-v2-") as raw_tmp:
            case = _seed_failed_v2(Path(raw_tmp) / "v2.db")
            try:
                admission = case["predecessor"].model_copy(
                    update={
                        "status": "queued",
                        "blocking_reason_code": None,
                        "blocking_reason_detail": None,
                        "claimed_at": None,
                        "completed_at": None,
                    }
                )
                winner, created = case["db"].create_or_get_b6_task(admission)
                self.assertFalse(created)
                self.assertEqual(winner.task_id, case["predecessor"].task_id)
                self.assertEqual(winner.status, "failed")
                self.assertEqual(
                    case["db"].conn.execute("SELECT COUNT(*) FROM b6_validation_tasks").fetchone()[0],
                    1,
                )
            finally:
                case["db"].close()


if __name__ == "__main__":
    unittest.main()
