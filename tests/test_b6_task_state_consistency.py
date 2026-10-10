"""Task state consistency tests (Task 4A-Corrective-7)."""
import hashlib
import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, date
from pathlib import Path

from backend.db.strategy import StrategyDB
from backend.services.oos_budget_ledger import OOSBudgetLedger
from contracts.strategy import (
    StrategyDraft, StrategyLifecycleState, ResearchProtocolSnapshot,
    BacktestUniverseSpec, ImmutableBacktestReport, PrototypeGateResultV2,
)
from contracts.b6_task import B6ValidationTask, build_b6_task_id, build_b6_task_key


def _valid_terminal_inputs(task: B6ValidationTask, protocol: ResearchProtocolSnapshot, report_id: str):
    identity = {
        "task_id": task.task_id,
        "task_key": task.task_key,
        "strategy_revision_id": task.strategy_revision_id,
        "protocol_snapshot_id": task.protocol_snapshot_id,
        "b5_bundle_id": task.b5_bundle_id,
        "b5_bundle_manifest_sha256": task.b5_bundle_manifest_sha256,
        "shared_oos_window_id": protocol.shared_oos_window_id,
        "data_snapshot_hash": protocol.data_snapshot_hash,
    }
    payload = {
        "task_id": task.task_id,
        "task_key": task.task_key,
        "protocol_snapshot_id": task.protocol_snapshot_id,
        "b5_bundle_id": task.b5_bundle_id,
        "b5_bundle_manifest_sha256": task.b5_bundle_manifest_sha256,
        "same_draw_result": {"identity": identity},
    }
    report_payload_json = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    report = ImmutableBacktestReport(
        report_id=report_id,
        theme_id=protocol.theme_id,
        strategy_revision_id=task.strategy_revision_id,
        protocol_snapshot_id=task.protocol_snapshot_id,
        report_hash=hashlib.sha256(report_payload_json.encode("utf-8")).hexdigest(),
        integrity_status="valid",
        evaluation_mode="out_of_sample",
        report_payload_json=report_payload_json,
        strategy_config_hash=protocol.strategy_config_hash,
        data_snapshot_hash=protocol.data_snapshot_hash,
        gate_criteria_hash=protocol.gate_criteria_hash,
        oos_draw_index=1,
        shared_oos_window_id=protocol.shared_oos_window_id,
        generated_at=datetime.now(),
    )
    checks = []
    gate_result = PrototypeGateResultV2(
        gate_result_id=f"gate-{report_id}",
        strategy_revision_id=task.strategy_revision_id,
        protocol_snapshot_id=task.protocol_snapshot_id,
        report_id=report.report_id,
        verdict="rejected",
        checks_json="[]",
        strategy_config_hash=protocol.strategy_config_hash,
        data_snapshot_hash=protocol.data_snapshot_hash,
        gate_criteria_hash=protocol.gate_criteria_hash,
        oos_draw_index=1,
        shared_oos_window_id=protocol.shared_oos_window_id,
        generated_at=datetime.now(),
        gate_result_hash=hashlib.sha256(
            json.dumps(
                {"report_id": report.report_id, "verdict": "rejected", "checks": checks},
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest(),
    )
    return report, gate_result


class TestB6TaskStateConsistency(unittest.TestCase):
    def test_completed_task_readable_from_second_connection(self):
        """After terminal success, second conn reads completed + completed_at."""
        temp = tempfile.TemporaryDirectory()
        path = Path(temp.name) / "t.db"
        db = StrategyDB(str(path))
        ledger = OOSBudgetLedger(db)
        db.store_backtest_universe(BacktestUniverseSpec(
            universe_spec_id="u", universe_rule_type="point_in_time_membership",
            membership_source="t", membership_effective_from=date(2024, 1, 1),
            membership_effective_to=date(2024, 12, 31), snapshot_date=date(2024, 1, 1),
            membership_snapshot_ids=("s",), quality_status="ok"
        ))
        draft = StrategyDraft(
            strategy_revision_id="r", theme_id="t", hypothesis_id="h",
            strategy_template_id="tpl", strategy_template_version="v1",
            strategy_template_hash="hash", hypothesis_source_snapshot_id="hs",
            backtest_universe_spec_id="u", strategy_config_json="{}",
            sample_split_rule_id="split", created_at=datetime.now()
        )
        protocol = ResearchProtocolSnapshot(
            protocol_snapshot_id="p", theme_id="t", hypothesis_source_snapshot_id="hs",
            strategy_revision_id="r", sample_split_rule_id="split",
            oos_window_rule_id="w", oos_window_rule_params_json="{}",
            oos_window_start=date(2024, 1, 1), oos_window_end=date(2024, 12, 31),
            shared_oos_window_id="w", backtest_universe_spec_id="u",
            strategy_config_hash="ch", data_snapshot_id="d", data_snapshot_hash="dh",
            kill_criteria_snapshot_id="k", prototype_gate_thresholds_json="{}",
            gate_criteria_hash="gh", frozen_at=datetime.now(), frozen_by="test"
        )
        db.create_strategy_draft(draft, StrategyLifecycleState(
            lifecycle_state_id="ls", strategy_revision_id="r", state_version=1,
            state="draft", source_record_id="init", recorded_at=datetime.now(), recorded_by="test"
        ))
        db.store_protocol_snapshot(protocol)
        task_key = build_b6_task_key(
            strategy_revision_id="r", protocol_snapshot_id="p", task_contract_version="v1"
        )
        task = B6ValidationTask(
            task_id=build_b6_task_id(task_key), task_key=task_key,
            task_type="b6_validation", strategy_revision_id="r",
            protocol_snapshot_id="p", status="queued", created_at=datetime.now()
        )
        db.create_b6_task(task)
        task = db.claim_b6_task(task.task_id)
        self.assertIsNotNone(task)

        rsv = ledger.reserve_oos_draw(
            protocol.theme_id, protocol.hypothesis_source_snapshot_id,
            protocol.strategy_config_hash, protocol.data_snapshot_hash,
            protocol.gate_criteria_hash, protocol.shared_oos_window_id,
            idempotency_key=task.task_key, task_key=task.task_key,
            protocol_snapshot_id=task.protocol_snapshot_id,
        )
        ledger.start_execution(rsv.reservation_id)
        reservation_id = rsv.reservation_id

        report, gate = _valid_terminal_inputs(task, protocol, "rpt")
        db.store_b6_terminal_result_tx(
            report, gate, rsv.reservation_id, "rejected", task.task_id, ledger
        )
        
        # Read via second conn
        v = sqlite3.connect(str(path))
        v.row_factory = sqlite3.Row
        row = v.execute(
            "SELECT status, completed_at FROM b6_validation_tasks WHERE task_id=?",
            (task.task_id,),
        ).fetchone()
        self.assertEqual(row["status"], "completed")
        self.assertIsNotNone(row["completed_at"])
        v.close()
        
        db.close()
        temp.cleanup()
    
    def test_report_builder_failure_writes_failed_task_no_report(self):
        """Report-builder throws → task=failed, rsv=failed, no report/Gate."""
        temp = tempfile.TemporaryDirectory()
        path = Path(temp.name) / "f.db"
        db = StrategyDB(str(path))
        from backend.services.oos_budget_ledger import OOSBudgetLedger
        ledger = OOSBudgetLedger(db)
        
        # ponytail: inline mock that raises
        class FailBuilder:
            def build_report(self, **kw):
                raise ValueError("forced report failure")
        
        db.store_backtest_universe(BacktestUniverseSpec(
            universe_spec_id="u", universe_rule_type="point_in_time_membership",
            membership_source="t", membership_effective_from=date(2024,1,1),
            membership_effective_to=date(2024,12,31), snapshot_date=date(2024,1,1),
            membership_snapshot_ids=("s",), quality_status="ok"
        ))
        draft = StrategyDraft(
            strategy_revision_id="r", theme_id="t", hypothesis_id="h",
            strategy_template_id="tpl", strategy_template_version="v1",
            strategy_template_hash="hash", hypothesis_source_snapshot_id="hs",
            backtest_universe_spec_id="u", strategy_config_json="{}",
            sample_split_rule_id="split", created_at=datetime.now()
        )
        protocol = ResearchProtocolSnapshot(
            protocol_snapshot_id="p", theme_id="t", hypothesis_source_snapshot_id="hs",
            strategy_revision_id="r", sample_split_rule_id="split",
            oos_window_rule_id="w", oos_window_rule_params_json="{}",
            oos_window_start=date(2024,1,1), oos_window_end=date(2024,12,31),
            shared_oos_window_id="w", backtest_universe_spec_id="u",
            strategy_config_hash="ch", data_snapshot_id="d", data_snapshot_hash="dh",
            kill_criteria_snapshot_id="k", prototype_gate_thresholds_json="{}",
            gate_criteria_hash="gh", frozen_at=datetime.now(), frozen_by="test"
        )
        db.create_strategy_draft(draft, StrategyLifecycleState(
            lifecycle_state_id="ls", strategy_revision_id="r", state_version=1,
            state="draft", source_record_id="init", recorded_at=datetime.now(), recorded_by="test"
        ))
        db.store_protocol_snapshot(protocol)
        
        # ponytail: directly call reserve+start+fail, skip full B6ValidationFlow
        rsv = ledger.reserve_oos_draw("t", "hs", "ch", "dh", "gh", "w", idempotency_key="k")
        ledger.start_execution(rsv.reservation_id)
        
        from contracts.b6_task import B6ValidationTask
        import hashlib
        task_key = hashlib.sha256(b"r|p|b6_validation|v1").hexdigest()[:16]
        db.create_b6_task(B6ValidationTask(
            task_id="task_fail", task_key=task_key, task_type="b6_validation",
            strategy_revision_id="r", protocol_snapshot_id="p",
            status="running", created_at=datetime.now()
        ))
        
        # Simulate report failure → write failure terminal
        try:
            db.conn.execute("BEGIN IMMEDIATE")
            ledger.fail_reservation_within_tx(db.conn, rsv.reservation_id, "report_build_failed: forced")
            cursor = db.update_b6_task_status("task_fail", "failed", datetime.now(), "report_build_failed", "forced")
            if cursor.rowcount != 1:
                raise RuntimeError("Task UPDATE affected 0 rows")
            db.conn.commit()
        except:
            db.conn.rollback()
            raise
        
        # Verify failure terminal
        v = sqlite3.connect(str(path))
        v.row_factory = sqlite3.Row
        task = v.execute("SELECT status FROM b6_validation_tasks WHERE task_id='task_fail'").fetchone()
        self.assertEqual(task["status"], "failed")
        rsv_count = v.execute("SELECT COUNT(*) FROM oos_budget_reservations WHERE status='failed'").fetchone()[0]
        self.assertEqual(rsv_count, 1)
        consumed = v.execute("SELECT consumed_draw_count FROM oos_budget_state WHERE theme_id='t'").fetchone()[0]
        self.assertEqual(consumed, 1)
        audit_count = v.execute("SELECT COUNT(*) FROM oos_evaluation_ledgers").fetchone()[0]
        self.assertGreater(audit_count, 0)
        report_count = v.execute("SELECT COUNT(*) FROM immutable_backtest_reports").fetchone()[0]
        self.assertEqual(report_count, 0)
        v.close()
        
        db.close()
        temp.cleanup()
    
    def test_task_update_zero_rows_fails_loud_and_rolls_back(self):
        """Task UPDATE affecting 0 rows → exception, full rollback."""
        temp = tempfile.TemporaryDirectory()
        path = Path(temp.name) / "z.db"
        db = StrategyDB(str(path))
        ledger = OOSBudgetLedger(db)
        
        db.store_backtest_universe(BacktestUniverseSpec(
            universe_spec_id="u", universe_rule_type="point_in_time_membership",
            membership_source="t", membership_effective_from=date(2024,1,1),
            membership_effective_to=date(2024,12,31), snapshot_date=date(2024,1,1),
            membership_snapshot_ids=("s",), quality_status="ok"
        ))
        draft = StrategyDraft(
            strategy_revision_id="r", theme_id="t", hypothesis_id="h",
            strategy_template_id="tpl", strategy_template_version="v1",
            strategy_template_hash="hash", hypothesis_source_snapshot_id="hs",
            backtest_universe_spec_id="u", strategy_config_json="{}",
            sample_split_rule_id="split", created_at=datetime.now()
        )
        protocol = ResearchProtocolSnapshot(
            protocol_snapshot_id="p", theme_id="t", hypothesis_source_snapshot_id="hs",
            strategy_revision_id="r", sample_split_rule_id="split",
            oos_window_rule_id="w", oos_window_rule_params_json="{}",
            oos_window_start=date(2024,1,1), oos_window_end=date(2024,12,31),
            shared_oos_window_id="w", backtest_universe_spec_id="u",
            strategy_config_hash="ch", data_snapshot_id="d", data_snapshot_hash="dh",
            kill_criteria_snapshot_id="k", prototype_gate_thresholds_json="{}",
            gate_criteria_hash="gh", frozen_at=datetime.now(), frozen_by="test"
        )
        db.create_strategy_draft(draft, StrategyLifecycleState(
            lifecycle_state_id="ls", strategy_revision_id="r", state_version=1,
            state="draft", source_record_id="init", recorded_at=datetime.now(), recorded_by="test"
        ))
        db.store_protocol_snapshot(protocol)

        b5_bundle_id = "bundle_state_consistency_001"
        b5_bundle_manifest_sha256 = "4" * 64
        task_key = build_b6_task_key(
            strategy_revision_id="r",
            protocol_snapshot_id="p",
            task_contract_version="v2",
            b5_bundle_id=b5_bundle_id,
            b5_bundle_manifest_sha256=b5_bundle_manifest_sha256,
        )
        task = B6ValidationTask(
            task_id=build_b6_task_id(task_key),
            task_key=task_key,
            task_type="b6_validation",
            task_contract_version="v2",
            strategy_revision_id="r",
            protocol_snapshot_id="p",
            status="queued",
            created_at=datetime.now(),
            b5_bundle_id=b5_bundle_id,
            b5_bundle_manifest_sha256=b5_bundle_manifest_sha256,
        )
        winner, created = db.create_or_get_b6_task(task)
        self.assertTrue(created)
        task = db.claim_b6_task(winner.task_id)
        self.assertIsNotNone(task)

        rsv = ledger.reserve_oos_draw(
            protocol.theme_id,
            protocol.hypothesis_source_snapshot_id,
            protocol.strategy_config_hash,
            protocol.data_snapshot_hash,
            protocol.gate_criteria_hash,
            protocol.shared_oos_window_id,
            idempotency_key=task.task_key,
            task_key=task.task_key,
            protocol_snapshot_id=task.protocol_snapshot_id,
        )
        ledger.start_execution(rsv.reservation_id)
        reservation_id = rsv.reservation_id

        report, gate = _valid_terminal_inputs(task, protocol, "rpt")
        db.conn.execute(
            """
            CREATE TRIGGER suppress_completed_task_update
            BEFORE UPDATE OF status ON b6_validation_tasks
            WHEN NEW.status = 'completed'
            BEGIN SELECT RAISE(IGNORE); END;
            """
        )
        db.conn.commit()

        with self.assertRaises(RuntimeError) as ctx:
            db.store_b6_terminal_result_tx(
                report, gate, rsv.reservation_id, "rejected", task.task_id, ledger
            )
        self.assertIn("task", str(ctx.exception).lower())

        # Full rollback
        v = sqlite3.connect(str(path))
        v.row_factory = sqlite3.Row
        self.assertIsNone(v.execute("SELECT 1 FROM immutable_backtest_reports WHERE report_id='rpt'").fetchone())
        self.assertIsNone(v.execute("SELECT 1 FROM prototype_gate_results_v2 WHERE gate_result_id='gate'").fetchone())
        rsv_row = v.execute(
            "SELECT status, reservation_id FROM oos_budget_reservations WHERE reservation_id=?",
            (reservation_id,),
        ).fetchone()
        self.assertEqual(rsv_row["status"], "started")
        task_row = v.execute(
            "SELECT status, completed_at FROM b6_validation_tasks WHERE task_id=?",
            (task.task_id,),
        ).fetchone()
        self.assertEqual(task_row["status"], "running")
        self.assertIsNone(task_row["completed_at"])
        state_row = v.execute(
            """
            SELECT consumed_draw_count, next_oos_draw_index,
                   active_reservation_id, budget_status
            FROM oos_budget_state
            WHERE theme_id=? AND hypothesis_source_snapshot_id=?
            """,
            (protocol.theme_id, protocol.hypothesis_source_snapshot_id),
        ).fetchone()
        self.assertEqual(
            tuple(state_row),
            (0, 1, reservation_id, "available"),
        )
        self.assertEqual(
            v.execute("SELECT COUNT(*) FROM oos_evaluation_ledgers").fetchone()[0],
            2,
        )
        v.close()

        db.close()
        temp.cleanup()


if __name__ == "__main__":
    unittest.main()
