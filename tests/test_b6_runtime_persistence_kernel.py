"""
B6 Runtime Persistence Kernel Tests (TDD RED → GREEN)

Tests B6 同库持久化内核：schema、terminal transaction、B6 结果分离。
使用 file-backed SQLite + 两独立连接证明 durable/concurrent 行为。
"""
from __future__ import annotations

from contextlib import closing
import hashlib
import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, date
from pathlib import Path

from backend.db.strategy import StrategyDB
from backend.services.oos_budget_ledger import OOSBudgetLedger
from backend.services.b6_validation_flow import B6ValidationFlow
from contracts.strategy import (
    StrategyDraft,
    ResearchProtocolSnapshot,
    ImmutableBacktestReport,
    PrototypeGateResultV2,
    BacktestUniverseSpec,
    StrategyLifecycleState,
    compute_b6_protocol_id_from_fields,
)
from backend.services.b3_protocol_types import (
    DataSnapshotManifest,
    PointInTimeMembershipSnapshot,
)


def _computed_id(data: dict) -> str:
    return compute_b6_protocol_id_from_fields(
        **{
            key: value
            for key, value in data.items()
            if key not in {"protocol_snapshot_id", "frozen_at", "frozen_by", "frozen"}
        }
    )


class TestB6RuntimePersistenceKernel(unittest.TestCase):
    """B6 runtime persistence kernel TDD tests."""
    
    def setUp(self):
        """Create temporary file-backed DB for durable/concurrent tests."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_b6_runtime.db"
        
        # Primary connection via StrategyDB
        self.strategy_db = StrategyDB(str(self.db_path))
        
        # Independent second connection for concurrent/durable verification
        self.verify_conn = sqlite3.connect(str(self.db_path))
        self.verify_conn.row_factory = sqlite3.Row
    
    def tearDown(self):
        """Close connections and cleanup."""
        self.strategy_db.close()
        self.verify_conn.close()
        self.temp_dir.cleanup()
    
    # === RED Phase 1: Schema Tests ===
    
    def test_b6_validation_tasks_table_exists(self):
        """RED: b6_validation_tasks table must exist after migration."""
        # Expected to FAIL: table does not exist yet
        tables = self.strategy_db.list_table_names()
        self.assertIn("b6_validation_tasks", tables, 
                      "b6_validation_tasks table missing after fresh schema")
    
    def test_protocol_has_profile_field(self):
        """RED: research_protocol_snapshots must have protocol_profile field."""
        # Expected to FAIL: field does not exist yet
        columns = [row[1] for row in self.verify_conn.execute(
            "PRAGMA table_info(research_protocol_snapshots)"
        )]
        self.assertIn("protocol_profile", columns,
                      "protocol_profile field missing in research_protocol_snapshots")
    
    def test_b6_protocol_multiplicity_index(self):
        """Migration 004 permits immutable protocols to share revision/profile."""
        # Setup: create draft + universe
        universe = BacktestUniverseSpec(
            universe_spec_id="universe_001",
            universe_rule_type="point_in_time_membership",
            membership_source="test",
            membership_effective_from=date(2020, 1, 1),
            membership_effective_to=date(2025, 1, 1),
            snapshot_date=date(2025, 1, 1),
            membership_snapshot_ids=("snap_001",),
            quality_status="ok",
        )
        self.strategy_db.store_backtest_universe(universe)
        
        draft = StrategyDraft(
            strategy_revision_id="rev_001",
            theme_id="theme_001",
            hypothesis_id="hypo_001",
            strategy_template_id="template_001",
            strategy_template_version="v1",
            strategy_template_hash="hash_001",
            hypothesis_source_snapshot_id="hypo_snap_001",
            backtest_universe_spec_id="universe_001",
            strategy_config_json="{}",
            sample_split_rule_id="split_001",
            created_at=datetime.now(),
        )
        initial_state = StrategyLifecycleState(
            lifecycle_state_id="state_001",
            strategy_revision_id="rev_001",
            state_version=1,
            state="draft",
            source_record_id="initial",
            recorded_at=datetime.now(),
            recorded_by="test",
        )
        self.strategy_db.create_strategy_draft(draft, initial_state)
        
        # Try to store two b6_coverage_bound protocols for same revision. ponytail: no _temp
        p1_data = dict(
            protocol_snapshot_id="placeholder",
            theme_id="theme_001",
            hypothesis_source_snapshot_id="hypo_snap_001",
            strategy_revision_id="rev_001",
            sample_split_rule_id="split_001",
            oos_window_rule_id="window_001",
            oos_window_rule_params_json="{}",
            oos_window_start=date(2024, 1, 1),
            oos_window_end=date(2024, 12, 31),
            shared_oos_window_id="shared_001",
            backtest_universe_spec_id="universe_001",
            data_snapshot_id="data_001",
            kill_criteria_snapshot_id="kill_001",
            prototype_gate_thresholds_json='{"t":1}',
            strategy_config_hash="config_hash_001",
            data_snapshot_hash="data_hash_001",
            gate_criteria_hash="gate_hash_001",
            frozen_at=datetime.now(),
            frozen_by="test",
            protocol_profile="b6_coverage_bound",
            availability_successor_id="s",
            availability_successor_manifest_hash="h",
            availability_successor_algorithm_hash="a",
            predecessor_qualification_id="p",
            predecessor_qualification_manifest_hash="h",
            predecessor_qualification_status="availability_bounded_qualified",
            predecessor_qualification_algorithm_hash="a",
            coverage_package_id="c",
            coverage_manifest_hash="h",
            coverage_algorithm_hash="a",
            source_scope_hash="s",
            data_requirements_hash="d",
            expected_stock_days=100,
            complete_stock_days=90,
            unavailable_stock_days=10,
            gate_snapshot_id="g",
            gate_content_hash="h",
            kill_content_hash="k",
        )
        real_id1 = _computed_id(p1_data)
        p1_data["protocol_snapshot_id"] = real_id1
        protocol1 = ResearchProtocolSnapshot(**p1_data)
        self.strategy_db.store_protocol_snapshot(protocol1)
        
        # ponytail: protocol2 also needs computed ID, no _temp
        p2_data = dict(
            protocol_snapshot_id="placeholder",
            theme_id="theme_001",
            hypothesis_source_snapshot_id="hypo_snap_001",
            strategy_revision_id="rev_001",  # Same revision
            sample_split_rule_id="split_001",
            oos_window_rule_id="window_001",
            oos_window_rule_params_json="{}",
            oos_window_start=date(2024, 1, 1),
            oos_window_end=date(2024, 12, 31),
            shared_oos_window_id="shared_001",
            backtest_universe_spec_id="universe_001",
            data_snapshot_id="data_001",
            kill_criteria_snapshot_id="kill_001",
            prototype_gate_thresholds_json='{" t":2}',
            strategy_config_hash="config_hash_002",  # Different config
            data_snapshot_hash="data_hash_001",
            gate_criteria_hash="gate_hash_001",
            frozen_at=datetime.now(),
            frozen_by="test",
            protocol_profile="b6_coverage_bound",
            availability_successor_id="s",
            availability_successor_manifest_hash="h",
            availability_successor_algorithm_hash="a",
            predecessor_qualification_id="p",
            predecessor_qualification_manifest_hash="h",
            predecessor_qualification_status="availability_bounded_qualified",
            predecessor_qualification_algorithm_hash="a",
            coverage_package_id="c",
            coverage_manifest_hash="h",
            coverage_algorithm_hash="a",
            source_scope_hash="s",
            data_requirements_hash="d",
            expected_stock_days=100,
            complete_stock_days=90,
            unavailable_stock_days=10,
            gate_snapshot_id="g",
            gate_content_hash="h",
            kill_content_hash="k",
        )
        real_id2 = _computed_id(p2_data)
        p2_data["protocol_snapshot_id"] = real_id2
        protocol2 = ResearchProtocolSnapshot(**p2_data)
        
        self.strategy_db.store_protocol_snapshot(protocol2)
        self.assertEqual(
            self.strategy_db.conn.execute(
                "SELECT COUNT(*) FROM research_protocol_snapshots "
                "WHERE strategy_revision_id = 'rev_001' AND protocol_profile = 'b6_coverage_bound'"
            ).fetchone()[0],
            2,
        )
    
    def test_legacy_protocol_readable(self):
        """Legacy protocols (no profile field in payload) must remain readable."""
        # Create pre-migration protocol
        universe = BacktestUniverseSpec(
            universe_spec_id="universe_legacy",
            universe_rule_type="point_in_time_membership",
            membership_source="test",
            membership_effective_from=date(2020, 1, 1),
            membership_effective_to=date(2025, 1, 1),
            snapshot_date=date(2025, 1, 1),
            membership_snapshot_ids=("snap_001",),
            quality_status="ok",
        )
        self.strategy_db.store_backtest_universe(universe)
        
        draft = StrategyDraft(
            strategy_revision_id="rev_legacy",
            theme_id="theme_legacy",
            hypothesis_id="hypo_legacy",
            strategy_template_id="template_legacy",
            strategy_template_version="v1",
            strategy_template_hash="hash_legacy",
            hypothesis_source_snapshot_id="hypo_snap_legacy",
            backtest_universe_spec_id="universe_legacy",
            strategy_config_json="{}",
            sample_split_rule_id="split_legacy",
            created_at=datetime.now(),
        )
        initial_state = StrategyLifecycleState(
            lifecycle_state_id="state_legacy",
            strategy_revision_id="rev_legacy",
            state_version=1,
            state="draft",
            source_record_id="initial",
            recorded_at=datetime.now(),
            recorded_by="test",
        )
        self.strategy_db.create_strategy_draft(draft, initial_state)
        
        # Store legacy protocol (payload_json won't have protocol_profile)
        protocol = ResearchProtocolSnapshot(
            protocol_snapshot_id="proto_legacy",
            theme_id="theme_legacy",
            hypothesis_source_snapshot_id="hypo_snap_legacy",
            strategy_revision_id="rev_legacy",
            sample_split_rule_id="split_legacy",
            oos_window_rule_id="window_legacy",
            oos_window_rule_params_json="{}",
            oos_window_start=date(2024, 1, 1),
            oos_window_end=date(2024, 12, 31),
            shared_oos_window_id="shared_legacy",
            backtest_universe_spec_id="universe_legacy",
            data_snapshot_id="data_legacy",
            kill_criteria_snapshot_id="kill_legacy",
            prototype_gate_thresholds_json="{}",
            strategy_config_hash="config_hash_legacy",
            data_snapshot_hash="data_hash_legacy",
            gate_criteria_hash="gate_hash_legacy",
            frozen_at=datetime.now(),
            frozen_by="test",
            # protocol_profile defaults to legacy_b3
        )
        self.strategy_db.store_protocol_snapshot(protocol)
        
        # Read back protocol
        loaded = self.strategy_db.get_protocol_snapshot("proto_legacy")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.protocol_profile, "legacy_b3")
    
    def test_terminal_tx_audit_failure_rolls_back_all(self):
        """Audit INSERT failure → full terminal rollback (report/Gate/reservation/task)."""
        temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(temp_dir.name) / "audit_fail.db"
        db = None
        try:
            db = StrategyDB(str(db_path))
            from backend.services.oos_budget_ledger import OOSBudgetLedger
            ledger = OOSBudgetLedger(db)

            db.store_backtest_universe(BacktestUniverseSpec(
                universe_spec_id="u1", universe_rule_type="point_in_time_membership",
                membership_source="test", membership_effective_from=date(2024, 1, 1),
                membership_effective_to=date(2024, 12, 31), snapshot_date=date(2024, 1, 1),
                membership_snapshot_ids=("s1",), quality_status="ok",
            ))
            draft = StrategyDraft(
                strategy_revision_id="rev1", theme_id="t1", hypothesis_id="h1",
                strategy_template_id="tpl1", strategy_template_version="v1",
                strategy_template_hash="hash1", hypothesis_source_snapshot_id="hypo1",
                backtest_universe_spec_id="u1", strategy_config_json="{}",
                sample_split_rule_id="split1", created_at=datetime.now(),
            )
            protocol = ResearchProtocolSnapshot(
                protocol_snapshot_id="p1", theme_id="t1", hypothesis_source_snapshot_id="hypo1",
                strategy_revision_id="rev1", sample_split_rule_id="split1",
                oos_window_rule_id="w1", oos_window_rule_params_json="{}",
                oos_window_start=date(2024, 1, 1), oos_window_end=date(2024, 12, 31),
                shared_oos_window_id="w1", backtest_universe_spec_id="u1",
                strategy_config_hash="ch1", data_snapshot_id="d1", data_snapshot_hash="dh1",
                kill_criteria_snapshot_id="k1", prototype_gate_thresholds_json="{}",
                gate_criteria_hash="gh1", frozen_at=datetime.now(), frozen_by="test",
            )
            db.create_strategy_draft(draft, StrategyLifecycleState(
                lifecycle_state_id="ls1", strategy_revision_id="rev1", state_version=1,
                state="draft", source_record_id="init", recorded_at=datetime.now(), recorded_by="test",
            ))
            db.store_protocol_snapshot(protocol)
            from contracts.b6_task import B6ValidationTask
            db.create_b6_task(B6ValidationTask(
                task_id="task1", task_key="key1", task_type="b6_validation",
                strategy_revision_id="rev1", protocol_snapshot_id="p1",
                status="running", created_at=datetime.now(),
            ))

            rsv = ledger.reserve_oos_draw(
                "t1", "hypo1", "ch1", "dh1", "gh1", "w1",
                idempotency_key="key1", task_key="key1", protocol_snapshot_id="p1",
            )
            ledger.start_execution(rsv.reservation_id)

            db.conn.execute("CREATE TRIGGER block_audit BEFORE INSERT ON oos_evaluation_ledgers BEGIN SELECT RAISE(ABORT, 'forced audit failure'); END;")
            db.conn.commit()

            same_draw_identity = {
                "task_id": "task1",
                "task_key": "key1",
                "strategy_revision_id": "rev1",
                "protocol_snapshot_id": "p1",
                "b5_bundle_id": None,
                "b5_bundle_manifest_sha256": None,
                "shared_oos_window_id": "w1",
                "data_snapshot_hash": "dh1",
            }
            report_payload = {
                "task_id": "task1",
                "task_key": "key1",
                "protocol_snapshot_id": "p1",
                "b5_bundle_id": None,
                "b5_bundle_manifest_sha256": None,
                "same_draw_result": {"identity": same_draw_identity},
            }
            report_payload_json = json.dumps(
                report_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            )
            report_hash = hashlib.sha256(report_payload_json.encode("utf-8")).hexdigest()
            report = ImmutableBacktestReport(
                report_id="r1", theme_id="t1", strategy_revision_id="rev1",
                protocol_snapshot_id="p1", report_hash=report_hash, integrity_status="valid",
                evaluation_mode="out_of_sample", report_payload_json=report_payload_json,
                strategy_config_hash="ch1", data_snapshot_hash="dh1", gate_criteria_hash="gh1",
                oos_draw_index=1, shared_oos_window_id="w1", generated_at=datetime.now(),
            )
            gate_hash = hashlib.sha256(
                json.dumps(
                    {"report_id": "r1", "verdict": "rejected", "checks": []},
                    sort_keys=True,
                ).encode("utf-8")
            ).hexdigest()
            gate = PrototypeGateResultV2(
                gate_result_id="g1", strategy_revision_id="rev1",
                protocol_snapshot_id="p1", report_id="r1", verdict="rejected",
                checks_json="[]", strategy_config_hash="ch1", data_snapshot_hash="dh1",
                gate_criteria_hash="gh1", oos_draw_index=1, shared_oos_window_id="w1",
                generated_at=datetime.now(), gate_result_hash=gate_hash,
            )

            with self.assertRaises(Exception) as ctx:
                db.store_b6_terminal_result_tx(report, gate, rsv.reservation_id, "rejected", "task1", ledger)
            self.assertIn("forced audit failure", str(ctx.exception))

            with closing(sqlite3.connect(str(db_path))) as verify:
                verify.row_factory = sqlite3.Row
                self.assertIsNone(verify.execute("SELECT 1 FROM immutable_backtest_reports WHERE report_id='r1'").fetchone())
                self.assertIsNone(verify.execute("SELECT 1 FROM prototype_gate_results_v2 WHERE gate_result_id='g1'").fetchone())
                task = verify.execute("SELECT status FROM b6_validation_tasks WHERE task_id='task1'").fetchone()
                self.assertEqual(task["status"], "running")
                rsv_row = verify.execute("SELECT status FROM oos_budget_reservations WHERE reservation_id=?", (rsv.reservation_id,)).fetchone()
                self.assertEqual(rsv_row["status"], "started")
                state = verify.execute("SELECT consumed_draw_count FROM oos_budget_state WHERE theme_id='t1'").fetchone()
                self.assertEqual(state["consumed_draw_count"], 0)
        finally:
            if db is not None:
                db.close()
            temp_dir.cleanup()


if __name__ == "__main__":
    unittest.main()
