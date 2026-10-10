"""Atomic claim for B6 tasks (queued→running)."""
import hashlib
import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, date
from pathlib import Path
from pydantic import ValidationError
from backend.db.strategy import StrategyDB
from contracts.b6_task import B6ValidationTask, build_b6_task_id, build_b6_task_key
from contracts.strategy import *


class TestB6TaskV2Contract(unittest.TestCase):
    def test_v2_requires_paired_b5_fields_and_lowercase_sha(self):
        base = {
            "task_id": "v2-task",
            "task_key": "v2-key",
            "task_type": "b6_validation",
            "task_contract_version": "v2",
            "strategy_revision_id": "revision",
            "protocol_snapshot_id": "protocol",
            "status": "queued",
            "created_at": datetime(2026, 8, 18, 12, 0, 0),
        }
        valid_sha = "a" * 64
        valid = {
            **base,
            "b5_bundle_id": "bundle-v2",
            "b5_bundle_manifest_sha256": valid_sha,
        }
        task = B6ValidationTask(**valid)
        self.assertEqual(task.b5_bundle_id, "bundle-v2")
        self.assertEqual(task.b5_bundle_manifest_sha256, valid_sha)

        invalid_cases = (
            {**base, "b5_bundle_id": "bundle-v2"},
            {**base, "b5_bundle_manifest_sha256": valid_sha},
            {**valid, "b5_bundle_manifest_sha256": "A" * 64},
            {**valid, "b5_bundle_manifest_sha256": "not-a-sha"},
            {**valid, "b5_bundle_id": ""},
            {**valid, "b5_bundle_id": "../bundle"},
            {**valid, "b5_bundle_id": "bundle\\v2"},
            {**valid, "extra": True},
        )
        for candidate in invalid_cases:
            with self.subTest(candidate=candidate):
                with self.assertRaises(ValidationError):
                    B6ValidationTask(**candidate)

    def test_v2_task_key_includes_b5_identity_and_version(self):
        from contracts.b6_task import build_b6_task_key

        revision = "revision"
        protocol = "protocol"
        bundle_id = "bundle-v2"
        manifest_sha = "a" * 64
        v2_identity = {
            "b5_bundle_id": bundle_id,
            "b5_bundle_manifest_sha256": manifest_sha,
            "protocol_profile": "b6_coverage_bound",
            "protocol_snapshot_id": protocol,
            "strategy_revision_id": revision,
            "task_contract_version": "v2",
            "task_type": "b6_validation",
        }
        expected_v2 = hashlib.sha256(
            json.dumps(
                v2_identity,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()
        actual_v2 = build_b6_task_key(
            strategy_revision_id=revision,
            protocol_snapshot_id=protocol,
            task_contract_version="v2",
            b5_bundle_id=bundle_id,
            b5_bundle_manifest_sha256=manifest_sha,
        )
        actual_v1 = build_b6_task_key(
            strategy_revision_id=revision,
            protocol_snapshot_id=protocol,
            task_contract_version="v1",
        )
        self.assertEqual(actual_v2, expected_v2)
        self.assertEqual(len(actual_v2), 64)
        self.assertEqual(actual_v2, actual_v2.lower())
        self.assertNotEqual(actual_v2, actual_v1)

    def test_v1_task_remains_readable_without_b5_fields(self):
        task = B6ValidationTask(
            task_id="v1-task",
            task_key="v1-key",
            task_type="b6_validation",
            strategy_revision_id="revision",
            protocol_snapshot_id="protocol",
            status="queued",
            created_at=datetime(2026, 8, 18, 12, 0, 0),
        )
        self.assertEqual(task.task_contract_version, "v1")
        self.assertIsNone(getattr(task, "b5_bundle_id", None))
        self.assertIsNone(getattr(task, "b5_bundle_manifest_sha256", None))


class TestB6TaskV2Persistence(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "b6_v2.db"
        self.db = StrategyDB(str(self.db_path))
        self._store_fk_context()

    def tearDown(self):
        self.db.close()
        self.temp_dir.cleanup()

    def _store_fk_context(self):
        self.db.store_backtest_universe(BacktestUniverseSpec(
            universe_spec_id="v2-universe",
            universe_rule_type="point_in_time_membership",
            membership_source="test",
            membership_effective_from=date(2024, 1, 1),
            membership_effective_to=date(2024, 12, 31),
            snapshot_date=date(2024, 1, 1),
            membership_snapshot_ids=("v2-membership",),
            quality_status="ok",
        ))
        draft = StrategyDraft(
            strategy_revision_id="v2-revision",
            theme_id="v2-theme",
            hypothesis_id="v2-hypothesis",
            strategy_template_id="v2-template",
            strategy_template_version="v1",
            strategy_template_hash="v2-template-hash",
            hypothesis_source_snapshot_id="v2-hypothesis-snapshot",
            backtest_universe_spec_id="v2-universe",
            strategy_config_json="{}",
            sample_split_rule_id="v2-split",
            created_at=datetime(2026, 8, 18, 12, 0, 0),
        )
        self.db.create_strategy_draft(draft, StrategyLifecycleState(
            lifecycle_state_id="v2-lifecycle",
            strategy_revision_id="v2-revision",
            state_version=1,
            state="draft",
            source_record_id="v2-initial",
            recorded_at=datetime(2026, 8, 18, 12, 0, 0),
            recorded_by="test",
        ))
        self.db.store_protocol_snapshot(ResearchProtocolSnapshot(
            protocol_snapshot_id="v2-protocol",
            theme_id="v2-theme",
            hypothesis_source_snapshot_id="v2-hypothesis-snapshot",
            strategy_revision_id="v2-revision",
            sample_split_rule_id="v2-split",
            oos_window_rule_id="v2-window",
            oos_window_rule_params_json="{}",
            oos_window_start=date(2024, 1, 1),
            oos_window_end=date(2024, 12, 31),
            shared_oos_window_id="v2-shared-window",
            backtest_universe_spec_id="v2-universe",
            strategy_config_hash="v2-config-hash",
            data_snapshot_id="v2-data",
            data_snapshot_hash="v2-data-hash",
            kill_criteria_snapshot_id="v2-kill",
            prototype_gate_thresholds_json="{}",
            gate_criteria_hash="v2-gate-hash",
            frozen_at=datetime(2026, 8, 18, 12, 0, 0),
            frozen_by="test",
        ))

    def _v2_task(self, *, task_id=None, created_at=None, **updates):
        bundle_id = updates.pop("b5_bundle_id", "v2-bundle")
        manifest_sha = updates.pop("b5_bundle_manifest_sha256", "b" * 64)
        revision = updates.pop("strategy_revision_id", "v2-revision")
        protocol = updates.pop("protocol_snapshot_id", "v2-protocol")
        version = updates.pop("task_contract_version", "v2")
        task_key = updates.pop(
            "task_key",
            build_b6_task_key(
                strategy_revision_id=revision,
                protocol_snapshot_id=protocol,
                task_contract_version=version,
                b5_bundle_id=None if version == "v1" else bundle_id,
                b5_bundle_manifest_sha256=None if version == "v1" else manifest_sha,
            ),
        )
        task_id = task_id or build_b6_task_id(task_key)
        payload = {
            "task_id": task_id,
            "task_key": task_key,
            "task_type": "b6_validation",
            "task_contract_version": version,
            "strategy_revision_id": revision,
            "protocol_snapshot_id": protocol,
            "status": "queued",
            "created_at": created_at or datetime(2026, 8, 18, 12, 0, 0),
            "b5_bundle_id": None if version == "v1" else bundle_id,
            "b5_bundle_manifest_sha256": None if version == "v1" else manifest_sha,
        }
        payload.update(updates)
        return B6ValidationTask(**payload)

    def _row_snapshot(self, task_id):
        return self.db.conn.execute(
            """
            SELECT task_id, task_key, task_contract_version, strategy_revision_id,
                   protocol_snapshot_id, status, blocking_reason_code,
                   blocking_reason_detail, payload_json, created_at,
                   claimed_at, completed_at, b5_bundle_id,
                   b5_bundle_manifest_sha256
            FROM b6_validation_tasks WHERE task_id = ?
            """,
            (task_id,),
        ).fetchone()

    def _legacy_row_snapshot(self, task_id):
        return self.db.conn.execute(
            """
            SELECT task_id, task_key, task_contract_version, status,
                   payload_json, created_at, claimed_at, completed_at
            FROM b6_validation_tasks WHERE task_id = ?
            """,
            (task_id,),
        ).fetchone()

    def test_fresh_schema_has_b5_binding_columns(self):
        columns = {
            row[1]: row for row in self.db.conn.execute(
                "PRAGMA table_info(b6_validation_tasks)"
            )
        }
        self.assertIn("b5_bundle_id", columns)
        self.assertIn("b5_bundle_manifest_sha256", columns)
        self.assertEqual(columns["b5_bundle_id"][3], 0)
        self.assertEqual(columns["b5_bundle_manifest_sha256"][3], 0)

    def test_legacy_v1_row_loads_with_null_b5_binding(self):
        legacy = self._v2_task(
            task_id="legacy-v1",
            task_key="legacy-v1-key",
            task_contract_version="v1",
            b5_bundle_id=None,
            b5_bundle_manifest_sha256=None,
        )
        self.db.create_b6_task(legacy)
        payload = json.loads(
            self.db.conn.execute(
                "SELECT payload_json FROM b6_validation_tasks WHERE task_id = ?",
                (legacy.task_id,),
            ).fetchone()[0]
        )
        payload.pop("b5_bundle_id", None)
        payload.pop("b5_bundle_manifest_sha256", None)
        self.db.conn.execute(
            "UPDATE b6_validation_tasks SET payload_json = ? WHERE task_id = ?",
            (json.dumps(payload, sort_keys=True), legacy.task_id),
        )
        self.db.conn.commit()
        before = self._legacy_row_snapshot(legacy.task_id)

        from backend.db.migrations.migration_003_add_b5_binding_to_b6_tasks import (
            migrate_add_b5_binding_to_b6_tasks,
        )
        migrate_add_b5_binding_to_b6_tasks(self.db.conn)
        after = self._legacy_row_snapshot(legacy.task_id)

        self.assertEqual(before, after)
        b5_columns = self.db.conn.execute(
            "SELECT b5_bundle_id, b5_bundle_manifest_sha256 FROM b6_validation_tasks WHERE task_id = ?",
            (legacy.task_id,),
        ).fetchone()
        self.assertIsNone(b5_columns[0])
        self.assertIsNone(b5_columns[1])
        loaded = self.db.get_b6_task_by_id(legacy.task_id)
        self.assertEqual(loaded.task_contract_version, "v1")
        self.assertIsNone(loaded.b5_bundle_id)
        self.assertIsNone(loaded.b5_bundle_manifest_sha256)

    def test_v2_create_or_get_returns_created_then_exact_reuse(self):
        first = self._v2_task()
        winner, created = self.db.create_or_get_b6_task(first)
        retry = self._v2_task(
            task_id=first.task_id,
            created_at=datetime(2026, 8, 18, 13, 0, 0),
            task_key=first.task_key,
        )
        reused, created_again = self.db.create_or_get_b6_task(retry)

        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(winner.task_id, reused.task_id)
        self.assertEqual(winner.task_key, reused.task_key)
        self.assertEqual(winner.created_at, first.created_at)
        self.assertEqual(
            self.db.conn.execute("SELECT COUNT(*) FROM b6_validation_tasks").fetchone()[0],
            1,
        )

    def test_existing_lifecycle_state_does_not_change_identity(self):
        first = self._v2_task()
        self.db.create_or_get_b6_task(first)

        running = self.db.claim_b6_task(first.task_id)
        reused_running, created_running = self.db.create_or_get_b6_task(first)
        self.assertEqual(running.status, "running")
        self.assertEqual(reused_running.status, "running")
        self.assertFalse(created_running)

        self.db.update_b6_task_status(first.task_id, "completed", datetime(2026, 8, 18, 14, 0, 0))
        self.db.conn.commit()
        reused_terminal, created_terminal = self.db.create_or_get_b6_task(first)
        self.assertEqual(reused_terminal.status, "completed")
        self.assertFalse(created_terminal)

    def test_immutable_identity_mismatch_fails_loud(self):
        first = self._v2_task()
        self.db.create_or_get_b6_task(first)
        mutations = (
            {"task_id": "different-task"},
            {"strategy_revision_id": "different-revision"},
            {"protocol_snapshot_id": "different-protocol"},
            {"b5_bundle_id": "different-bundle"},
            {"b5_bundle_manifest_sha256": "c" * 64},
            {"task_contract_version": "v1", "b5_bundle_id": None, "b5_bundle_manifest_sha256": None},
        )
        before = self._row_snapshot(first.task_id)
        for update in mutations:
            with self.subTest(update=update):
                candidate_data = first.model_dump()
                candidate_data.update(update)
                candidate = B6ValidationTask(**candidate_data)
                with self.assertRaises(ValueError):
                    self.db.create_or_get_b6_task(candidate)
                self.assertEqual(self._row_snapshot(first.task_id), before)

    def test_create_failure_rolls_back_task_row(self):
        self.db.conn.execute(
            """
            CREATE TRIGGER fail_v2_task_insert
            BEFORE INSERT ON b6_validation_tasks
            WHEN NEW.task_contract_version = 'v2'
            BEGIN SELECT RAISE(ABORT, 'forced v2 insert failure'); END;
            """
        )
        self.db.conn.commit()
        task = self._v2_task()
        with self.assertRaises(sqlite3.DatabaseError) as ctx:
            self.db.create_or_get_b6_task(task)
        self.assertIn("forced v2 insert failure", str(ctx.exception))
        self.assertIsNone(self.db.get_b6_task_by_key(task.task_key))
        self.assertEqual(
            self.db.conn.execute("SELECT COUNT(*) FROM b6_validation_tasks").fetchone()[0],
            0,
        )

    def test_concurrent_v2_create_returns_one_winner(self):
        import threading

        db2 = StrategyDB(str(self.db_path))
        barrier = threading.Barrier(2)
        results = []
        errors = []
        task = self._v2_task()

        def create_worker(db):
            try:
                barrier.wait()
                results.append(db.create_or_get_b6_task(task))
            except Exception as error:
                errors.append(error)

        threads = [
            threading.Thread(target=create_worker, args=(self.db,)),
            threading.Thread(target=create_worker, args=(db2,)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        db2.close()

        self.assertEqual(errors, [])
        self.assertEqual(len(results), 2)
        self.assertEqual(sum(created for _, created in results), 1)
        self.assertEqual({winner.task_id for winner, _ in results}, {task.task_id})
        self.assertEqual(
            self.db.conn.execute("SELECT COUNT(*) FROM b6_validation_tasks").fetchone()[0],
            1,
        )

    def test_v2_rejects_task_key_not_matching_frozen_identity(self):
        task = self._v2_task(task_id="forged-key-task", task_key="forged-task-key")
        with self.assertRaises(ValueError):
            self.db.create_or_get_b6_task(task)
        self.assertEqual(
            self.db.conn.execute("SELECT COUNT(*) FROM b6_validation_tasks").fetchone()[0],
            0,
        )

    def test_v2_rejects_task_id_not_matching_canonical_identity(self):
        from contracts.b6_task import build_b6_task_id

        task = self._v2_task(task_id="noncanonical-task-id")
        self.assertNotEqual(task.task_id, build_b6_task_id(task.task_key))
        with self.assertRaises(ValueError):
            self.db.create_or_get_b6_task(task)
        self.assertEqual(
            self.db.conn.execute("SELECT COUNT(*) FROM b6_validation_tasks").fetchone()[0],
            0,
        )

    def test_loader_rejects_created_at_column_payload_mismatch(self):
        task = self._v2_task()
        self.db.create_or_get_b6_task(task)
        self.db.conn.execute(
            "UPDATE b6_validation_tasks SET created_at = ? WHERE task_id = ?",
            ("2026-08-18T15:00:00", task.task_id),
        )
        self.db.conn.commit()
        with self.assertRaises(ValueError):
            self.db.get_b6_task_by_id(task.task_id)


class TestB6TaskAtomicClaim(unittest.TestCase):
    def test_claim_queued_succeeds(self):
        """queued→running atomic."""
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        db = StrategyDB(str(Path(temp.name)/"c.db"))
        self.addCleanup(db.close)
        
        # FK setup
        db.store_backtest_universe(BacktestUniverseSpec(
            universe_spec_id="u", universe_rule_type="point_in_time_membership",
            membership_source="t", membership_effective_from=date(2024,1,1),
            membership_effective_to=date(2024,12,31), snapshot_date=date(2024,1,1),
            membership_snapshot_ids=("s",), quality_status="ok"))
        draft = StrategyDraft(
            strategy_revision_id="r", theme_id="t", hypothesis_id="h",
            strategy_template_id="tpl", strategy_template_version="v1",
            strategy_template_hash="hash", hypothesis_source_snapshot_id="hs",
            backtest_universe_spec_id="u", strategy_config_json="{}",
            sample_split_rule_id="split", created_at=datetime.now())
        protocol = ResearchProtocolSnapshot(
            protocol_snapshot_id="p", theme_id="t", hypothesis_source_snapshot_id="hs",
            strategy_revision_id="r", sample_split_rule_id="split",
            oos_window_rule_id="w", oos_window_rule_params_json="{}",
            oos_window_start=date(2024,1,1), oos_window_end=date(2024,12,31),
            shared_oos_window_id="w", backtest_universe_spec_id="u",
            strategy_config_hash="ch", data_snapshot_id="d", data_snapshot_hash="dh",
            kill_criteria_snapshot_id="k", prototype_gate_thresholds_json="{}",
            gate_criteria_hash="gh", frozen_at=datetime.now(), frozen_by="test")
        db.create_strategy_draft(draft, StrategyLifecycleState(
            lifecycle_state_id="ls", strategy_revision_id="r", state_version=1,
            state="draft", source_record_id="init", recorded_at=datetime.now(), recorded_by="test"))
        db.store_protocol_snapshot(protocol)
        
        task = B6ValidationTask(
            task_id="t1", task_key="k1", task_type="b6_validation",
            strategy_revision_id="r", protocol_snapshot_id="p",
            status="queued", created_at=datetime.now())
        db.create_b6_task(task)
        
        claimed = db.claim_b6_task("t1")
        self.assertIsNotNone(claimed)
        self.assertEqual(claimed.status, "running")
        self.assertIsNotNone(claimed.claimed_at)
    
    def test_claim_twice_second_fails(self):
        """Two threads+connections, only first claims (real concurrency)."""
        import threading
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        path = Path(temp.name)/"d.db"
        db1 = StrategyDB(str(path))
        self.addCleanup(db1.close)
        
        # FK
        db1.store_backtest_universe(BacktestUniverseSpec(
            universe_spec_id="u", universe_rule_type="point_in_time_membership",
            membership_source="t", membership_effective_from=date(2024,1,1),
            membership_effective_to=date(2024,12,31), snapshot_date=date(2024,1,1),
            membership_snapshot_ids=("s",), quality_status="ok"))
        draft = StrategyDraft(
            strategy_revision_id="r", theme_id="t", hypothesis_id="h",
            strategy_template_id="tpl", strategy_template_version="v1",
            strategy_template_hash="hash", hypothesis_source_snapshot_id="hs",
            backtest_universe_spec_id="u", strategy_config_json="{}",
            sample_split_rule_id="split", created_at=datetime.now())
        protocol = ResearchProtocolSnapshot(
            protocol_snapshot_id="p", theme_id="t", hypothesis_source_snapshot_id="hs",
            strategy_revision_id="r", sample_split_rule_id="split",
            oos_window_rule_id="w", oos_window_rule_params_json="{}",
            oos_window_start=date(2024,1,1), oos_window_end=date(2024,12,31),
            shared_oos_window_id="w", backtest_universe_spec_id="u",
            strategy_config_hash="ch", data_snapshot_id="d", data_snapshot_hash="dh",
            kill_criteria_snapshot_id="k", prototype_gate_thresholds_json="{}",
            gate_criteria_hash="gh", frozen_at=datetime.now(), frozen_by="test")
        db1.create_strategy_draft(draft, StrategyLifecycleState(
            lifecycle_state_id="ls", strategy_revision_id="r", state_version=1,
            state="draft", source_record_id="init", recorded_at=datetime.now(), recorded_by="test"))
        db1.store_protocol_snapshot(protocol)
        
        task = B6ValidationTask(
            task_id="t2", task_key="k2", task_type="b6_validation",
            strategy_revision_id="r", protocol_snapshot_id="p",
            status="queued", created_at=datetime.now())
        db1.create_b6_task(task)
        
        db2 = StrategyDB(str(path))
        self.addCleanup(db2.close)
        barrier = threading.Barrier(2)
        results = [None, None]
        
        def claim_worker(idx, db):
            barrier.wait()  # ponytail: sync start
            results[idx] = db.claim_b6_task("t2")
        
        t1 = threading.Thread(target=claim_worker, args=(0, db1))
        t2 = threading.Thread(target=claim_worker, args=(1, db2))
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        
        # ponytail: exactly one winner
        self.assertEqual(sum(r is not None for r in results), 1)
        winner = [r for r in results if r][0]
        self.assertEqual(winner.status, "running")
        self.assertIsNotNone(winner.claimed_at)
        
        # db2 reads running
        t = db2.get_b6_task_by_id("t2")
        self.assertEqual(t.status, "running")
    
    def test_claim_terminal_fails(self):
        """completed/failed/blocked not claimable."""
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        db = StrategyDB(str(Path(temp.name)/"e.db"))
        self.addCleanup(db.close)
        
        # FK
        db.store_backtest_universe(BacktestUniverseSpec(
            universe_spec_id="u", universe_rule_type="point_in_time_membership",
            membership_source="t", membership_effective_from=date(2024,1,1),
            membership_effective_to=date(2024,12,31), snapshot_date=date(2024,1,1),
            membership_snapshot_ids=("s",), quality_status="ok"))
        draft = StrategyDraft(
            strategy_revision_id="r", theme_id="t", hypothesis_id="h",
            strategy_template_id="tpl", strategy_template_version="v1",
            strategy_template_hash="hash", hypothesis_source_snapshot_id="hs",
            backtest_universe_spec_id="u", strategy_config_json="{}",
            sample_split_rule_id="split", created_at=datetime.now())
        protocol = ResearchProtocolSnapshot(
            protocol_snapshot_id="p", theme_id="t", hypothesis_source_snapshot_id="hs",
            strategy_revision_id="r", sample_split_rule_id="split",
            oos_window_rule_id="w", oos_window_rule_params_json="{}",
            oos_window_start=date(2024,1,1), oos_window_end=date(2024,12,31),
            shared_oos_window_id="w", backtest_universe_spec_id="u",
            strategy_config_hash="ch", data_snapshot_id="d", data_snapshot_hash="dh",
            kill_criteria_snapshot_id="k", prototype_gate_thresholds_json="{}",
            gate_criteria_hash="gh", frozen_at=datetime.now(), frozen_by="test")
        db.create_strategy_draft(draft, StrategyLifecycleState(
            lifecycle_state_id="ls", strategy_revision_id="r", state_version=1,
            state="draft", source_record_id="init", recorded_at=datetime.now(), recorded_by="test"))
        db.store_protocol_snapshot(protocol)
        
        for s in ["completed", "failed", "blocked"]:
            task = B6ValidationTask(
                task_id=f"t_{s}", task_key=f"k_{s}", task_type="b6_validation",
                strategy_revision_id="r", protocol_snapshot_id="p",
                status=s, created_at=datetime.now())
            db.create_b6_task(task)
            self.assertIsNone(db.claim_b6_task(f"t_{s}"))

if __name__ == "__main__": unittest.main()
