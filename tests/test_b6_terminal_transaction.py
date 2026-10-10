"""
Task 4A-Corrective-2: B6 Terminal Transaction Tests

Tests that B6 validation uses two short transactions correctly:
1. Reserve transaction (before OOS execution)
2. Terminal transaction (after OOS execution, atomic write)
"""
from __future__ import annotations

import hashlib
import sqlite3
import tempfile
import unittest
from datetime import datetime, date
from pathlib import Path

from backend.db.strategy import StrategyDB
from backend.services.b4_protocol_types import DailyPortfolioSnapshot, EventBacktestResult
from backend.services.backtest_report_builder import BacktestReportBuilder
from backend.services.oos_budget_ledger import OOSBudgetLedger
from backend.services.b6_validation_flow import B6ValidationFlow
from backend.services.prototype_gate_v2 import PrototypeGateV2
from contracts.strategy import (
    BacktestUniverseSpec,
    StrategyDraft,
    StrategyLifecycleState,
    ResearchProtocolSnapshot,
    ImmutableBacktestReport,
    PrototypeGateResultV2,
    compute_b6_protocol_id_from_fields,
)
from contracts.b6_task import B6ValidationTask, build_b6_task_id, build_b6_task_key


class TestB6TerminalTransaction(unittest.TestCase):
    """Test B6 two-short-transaction correctness."""
    
    def setUp(self):
        """Create temporary file-backed DB."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_b6_terminal.db"
        
        self.strategy_db = StrategyDB(str(self.db_path))
        self.oos_ledger = OOSBudgetLedger(self.strategy_db)
        
        # Second independent connection for verification
        self.verify_conn = sqlite3.connect(str(self.db_path))
        self.verify_conn.row_factory = sqlite3.Row
    
    def tearDown(self):
        """Cleanup."""
        self.strategy_db.close()
        self.verify_conn.close()
        self.temp_dir.cleanup()
    
    # === RED Phase 1: Terminal Transaction Atomicity ===
    
    def test_terminal_transaction_atomic_success(self):
        """RED: Terminal TX must write report + Gate + ledger + task atomically."""
        # Expected to FAIL: no store_b6_terminal_result_tx() exists yet
        
        # Setup: create draft + protocol
        self._create_test_draft_and_protocol()
        
        # Synthetic same-draw report + Gate (would come from real B6 validation)
        report = self._create_fake_report()
        gate_result = self._create_fake_gate(report)

        # Reserve (first short transaction)
        reservation = self.oos_ledger.reserve_oos_draw(
            theme_id="theme_001",
            hypothesis_source_snapshot_id="hypo_001",
            strategy_config_hash=self.protocol.strategy_config_hash,
            data_snapshot_hash=self.protocol.data_snapshot_hash,
            gate_criteria_hash=self.protocol.gate_criteria_hash,
            shared_oos_window_id=self.protocol.shared_oos_window_id,
            idempotency_key=self.task.task_key,
            task_key=self.task.task_key,
            protocol_snapshot_id=self.protocol.protocol_snapshot_id,
        )
        self.oos_ledger.start_execution(reservation.reservation_id)

        # Terminal transaction (second short transaction)
        self.strategy_db.store_b6_terminal_result_tx(
            report=report,
            gate_result=gate_result,
            reservation_id=reservation.reservation_id,
            verdict=gate_result.verdict,
            task_id=self.task.task_id,
            oos_budget_ledger=self.oos_ledger,
        )
        
        # Verify all writes committed
        report_row = self.verify_conn.execute(
            "SELECT * FROM immutable_backtest_reports WHERE report_id = ?",
            (report.report_id,)
        ).fetchone()
        self.assertIsNotNone(report_row)
        
        gate_row = self.verify_conn.execute(
            "SELECT * FROM prototype_gate_results_v2 WHERE gate_result_id = ?",
            (gate_result.gate_result_id,)
        ).fetchone()
        self.assertIsNotNone(gate_row)
        
        reservation_row = self.verify_conn.execute(
            "SELECT status FROM oos_budget_reservations WHERE reservation_id = ?",
            (reservation.reservation_id,)
        ).fetchone()
        self.assertEqual(reservation_row["status"], "completed")
        
        task_row = self.verify_conn.execute(
            "SELECT status FROM b6_validation_tasks WHERE task_id = ?",
            (self.task.task_id,)
        ).fetchone()
        self.assertEqual(task_row["status"], "completed")
    
    def test_terminal_transaction_rollback_on_report_failure(self):
        """A report insert conflict leaves the terminal chain unchanged."""
        self._create_test_draft_and_protocol()
        report = self._create_fake_report()
        gate_result = self._create_fake_gate(report)
        reservation = self.oos_ledger.reserve_oos_draw(
            theme_id=self.protocol.theme_id,
            hypothesis_source_snapshot_id=self.protocol.hypothesis_source_snapshot_id,
            strategy_config_hash=self.protocol.strategy_config_hash,
            data_snapshot_hash=self.protocol.data_snapshot_hash,
            gate_criteria_hash=self.protocol.gate_criteria_hash,
            shared_oos_window_id=self.protocol.shared_oos_window_id,
            idempotency_key=self.task.task_key,
            task_key=self.task.task_key,
            protocol_snapshot_id=self.protocol.protocol_snapshot_id,
        )
        self.oos_ledger.start_execution(reservation.reservation_id)

        self.strategy_db.conn.execute(
            """
            INSERT INTO immutable_backtest_reports
            (report_id, strategy_revision_id, protocol_snapshot_id,
             payload_json, report_hash, integrity_status, generated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report.report_id,
                report.strategy_revision_id,
                report.protocol_snapshot_id,
                self.strategy_db._json(report),
                report.report_hash,
                report.integrity_status,
                report.generated_at.isoformat(),
            ),
        )
        self.strategy_db.conn.commit()

        with self.assertRaises(Exception):
            self.strategy_db.store_b6_terminal_result_tx(
                report=report,
                gate_result=gate_result,
                reservation_id=reservation.reservation_id,
                verdict=gate_result.verdict,
                task_id=self.task.task_id,
                oos_budget_ledger=self.oos_ledger,
            )

        self.assertEqual(
            self.verify_conn.execute(
                "SELECT COUNT(*) FROM immutable_backtest_reports WHERE report_id = ?",
                (report.report_id,),
            ).fetchone()[0],
            1,
        )
        self.assertEqual(
            self.verify_conn.execute("SELECT COUNT(*) FROM prototype_gate_results_v2").fetchone()[0],
            0,
        )
        self.assertEqual(
            self.verify_conn.execute(
                "SELECT status FROM oos_budget_reservations WHERE reservation_id = ?",
                (reservation.reservation_id,),
            ).fetchone()[0],
            "started",
        )
        self.assertEqual(
            self.verify_conn.execute(
                "SELECT status FROM b6_validation_tasks WHERE task_id = ?",
                (self.task.task_id,),
            ).fetchone()[0],
            "running",
        )
    
    def test_b6_validation_flow_rejects_human_decision(self):
        """RED: B6ValidationFlow must not accept human_decision parameter."""
        flow = B6ValidationFlow(
            oos_budget_ledger=self.oos_ledger,
            strategy_db=self.strategy_db,
        )
        
        # Try to call with human_decision
        # Expected to FAIL: current implementation still accepts it
        with self.assertRaises(TypeError):
            flow.run_minimal_validation(
                strategy_draft=None,
                protocol=None,
                manifest=None,
                universe=None,
                b4_qualification=None,
                b4_event_result=None,
                human_decision="approve",  # Should be rejected
            )
    
    def test_b6_validation_always_persists_report_gate(self):
        """The terminal chain persists report and Gate without Promotion."""
        self._create_test_draft_and_protocol()
        report = self._create_fake_report()
        gate_result = self._create_fake_gate(report)
        reservation = self.oos_ledger.reserve_oos_draw(
            theme_id=self.protocol.theme_id,
            hypothesis_source_snapshot_id=self.protocol.hypothesis_source_snapshot_id,
            strategy_config_hash=self.protocol.strategy_config_hash,
            data_snapshot_hash=self.protocol.data_snapshot_hash,
            gate_criteria_hash=self.protocol.gate_criteria_hash,
            shared_oos_window_id=self.protocol.shared_oos_window_id,
            idempotency_key=self.task.task_key,
            task_key=self.task.task_key,
            protocol_snapshot_id=self.protocol.protocol_snapshot_id,
        )
        self.oos_ledger.start_execution(reservation.reservation_id)
        self.strategy_db.store_b6_terminal_result_tx(
            report=report,
            gate_result=gate_result,
            reservation_id=reservation.reservation_id,
            verdict=gate_result.verdict,
            task_id=self.task.task_id,
            oos_budget_ledger=self.oos_ledger,
        )

        self.assertIsNotNone(
            self.verify_conn.execute(
                "SELECT 1 FROM immutable_backtest_reports WHERE report_id = ?",
                (report.report_id,),
            ).fetchone()
        )
        self.assertIsNotNone(
            self.verify_conn.execute(
                "SELECT 1 FROM prototype_gate_results_v2 WHERE report_id = ?",
                (report.report_id,),
            ).fetchone()
        )
        self.assertEqual(
            self.verify_conn.execute(
                "SELECT status FROM b6_validation_tasks WHERE task_id = ?",
                (self.task.task_id,),
            ).fetchone()[0],
            "completed",
        )
    
    # === Helper Methods ===
    
    def _create_test_draft_and_protocol(self):
        """Create minimal draft + protocol for testing."""
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
            hypothesis_source_snapshot_id="hypo_001",
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
        
        protocol_fields = {
            "protocol_profile": "b6_coverage_bound",
            "theme_id": "theme_001",
            "hypothesis_source_snapshot_id": "hypo_001",
            "strategy_revision_id": "rev_001",
            "sample_split_rule_id": "split_001",
            "oos_window_rule_id": "window_001",
            "oos_window_rule_params_json": "{}",
            "oos_window_start": date(2024, 1, 1),
            "oos_window_end": date(2024, 12, 31),
            "shared_oos_window_id": "window_001",
            "backtest_universe_spec_id": "universe_001",
            "data_snapshot_id": "data_001",
            "data_snapshot_hash": "2" * 64,
            "kill_criteria_snapshot_id": "kill_001",
            "prototype_gate_thresholds_json": '{"threshold": 0.5}',
            "strategy_config_hash": "1" * 64,
            "gate_criteria_hash": "3" * 64,
            "availability_successor_id": "successor_001",
            "availability_successor_manifest_hash": "a" * 64,
            "availability_successor_algorithm_hash": "successor_algorithm_001",
            "predecessor_qualification_id": "predecessor_001",
            "predecessor_qualification_manifest_hash": "b" * 64,
            "predecessor_qualification_status": "availability_bounded_qualified",
            "predecessor_qualification_algorithm_hash": "predecessor_algorithm_001",
            "coverage_package_id": "coverage_001",
            "coverage_manifest_hash": "c" * 64,
            "coverage_algorithm_hash": "coverage_algorithm_001",
            "source_scope_hash": "scope_hash_001",
            "data_requirements_hash": "requirements_hash_001",
            "expected_stock_days": 1000,
            "complete_stock_days": 900,
            "unavailable_stock_days": 100,
            "gate_snapshot_id": "gate_snapshot_001",
            "gate_content_hash": "gate_content_hash_001",
            "kill_content_hash": "kill_content_hash_001",
        }
        protocol = ResearchProtocolSnapshot(
            protocol_snapshot_id=compute_b6_protocol_id_from_fields(**protocol_fields),
            theme_id="theme_001",
            hypothesis_source_snapshot_id="hypo_001",
            strategy_revision_id="rev_001",
            sample_split_rule_id="split_001",
            oos_window_rule_id="window_001",
            oos_window_rule_params_json="{}",
            oos_window_start=date(2024, 1, 1),
            oos_window_end=date(2024, 12, 31),
            shared_oos_window_id="window_001",
            backtest_universe_spec_id="universe_001",
            data_snapshot_id="data_001",
            kill_criteria_snapshot_id="kill_001",
            prototype_gate_thresholds_json='{"threshold": 0.5}',
            strategy_config_hash="1" * 64,
            data_snapshot_hash="2" * 64,
            gate_criteria_hash="3" * 64,
            frozen_at=datetime.now(),
            frozen_by="test",
            protocol_profile="b6_coverage_bound",
            availability_successor_id="successor_001",
            availability_successor_manifest_hash="a" * 64,
            availability_successor_algorithm_hash="successor_algorithm_001",
            predecessor_qualification_id="predecessor_001",
            predecessor_qualification_manifest_hash="b" * 64,
            predecessor_qualification_status="availability_bounded_qualified",
            predecessor_qualification_algorithm_hash="predecessor_algorithm_001",
            coverage_package_id="coverage_001",
            coverage_manifest_hash="c" * 64,
            coverage_algorithm_hash="coverage_algorithm_001",
            source_scope_hash="scope_hash_001",
            data_requirements_hash="requirements_hash_001",
            expected_stock_days=1000,
            complete_stock_days=900,
            unavailable_stock_days=100,
            gate_snapshot_id="gate_snapshot_001",
            gate_content_hash="gate_content_hash_001",
            kill_content_hash="kill_content_hash_001",
        )
        self.strategy_db.store_protocol_snapshot(protocol)

        self.protocol = protocol
        b5_bundle_id = "bundle_terminal_synthetic_001"
        b5_bundle_manifest_sha256 = "4" * 64
        task_key = build_b6_task_key(
            strategy_revision_id=protocol.strategy_revision_id,
            protocol_snapshot_id=protocol.protocol_snapshot_id,
            task_contract_version="v2",
            b5_bundle_id=b5_bundle_id,
            b5_bundle_manifest_sha256=b5_bundle_manifest_sha256,
        )
        task = B6ValidationTask(
            task_id=build_b6_task_id(task_key),
            task_key=task_key,
            task_type="b6_validation",
            task_contract_version="v2",
            strategy_revision_id=protocol.strategy_revision_id,
            protocol_snapshot_id=protocol.protocol_snapshot_id,
            status="queued",
            created_at=datetime(2026, 8, 21, 12, 0, 0),
            b5_bundle_id=b5_bundle_id,
            b5_bundle_manifest_sha256=b5_bundle_manifest_sha256,
        )
        winner, created = self.strategy_db.create_or_get_b6_task(task)
        if not created:
            raise AssertionError("synthetic terminal fixture task was not created")
        self.task = self.strategy_db.claim_b6_task(winner.task_id)
        if self.task is None:
            raise AssertionError("synthetic terminal fixture task was not claimed")

    def _create_fake_b4_result(self) -> EventBacktestResult:
        return EventBacktestResult(
            result_id="b4_terminal_synthetic_001",
            strategy_revision_id=self.protocol.strategy_revision_id,
            protocol_snapshot_id=self.protocol.protocol_snapshot_id,
            evaluation_mode="formal_backtest",
            backtest_start=self.protocol.oos_window_start,
            backtest_end=self.protocol.oos_window_end,
            order_intents=(),
            fills=(),
            rejected_orders=(),
            future_violations=(),
            final_portfolio=DailyPortfolioSnapshot(
                snapshot_id="portfolio_terminal_synthetic_001",
                snapshot_date=self.protocol.oos_window_end,
                cash=100000.0,
                positions=(),
                portfolio_value=100000.0,
            ),
            frozen_at=self.protocol.oos_window_end,
        )

    def _create_fake_same_draw_result(self):
        from backend.services.b5_oos_types import (
            B6SameDrawOOSResult,
            BaseCostResult,
            SameDrawExecutionIdentity,
            StressCostResult,
        )

        identity = SameDrawExecutionIdentity(
            task_id=self.task.task_id,
            task_key=self.task.task_key,
            strategy_revision_id=self.protocol.strategy_revision_id,
            protocol_snapshot_id=self.protocol.protocol_snapshot_id,
            b5_bundle_id=self.task.b5_bundle_id,
            b5_bundle_manifest_sha256=self.task.b5_bundle_manifest_sha256,
            b4_artifact_id="b4_terminal_synthetic_001",
            b4_manifest_sha256="5" * 64,
            b4_event_result_sha256="6" * 64,
            formal_snapshot_id="formal_terminal_synthetic_001",
            formal_snapshot_manifest_sha256="7" * 64,
            membership_snapshot_id="membership_terminal_synthetic_001",
            membership_manifest_sha256="8" * 64,
            calendar_id="calendar_terminal_synthetic_001",
            calendar_manifest_sha256="9" * 64,
            data_snapshot_hash=self.protocol.data_snapshot_hash,
            execution_input_hash="a" * 64,
            shared_oos_window_id=self.protocol.shared_oos_window_id,
            oos_start=self.protocol.oos_window_start,
            oos_end=self.protocol.oos_window_end,
            result_schema_version="b6_same_draw_oos_result.v1",
        )
        return B6SameDrawOOSResult(
            identity=identity,
            starting_nav=100000.0,
            ending_nav_base=101000.0,
            ending_nav_stress=100500.0,
            strategy_net_return_base=0.10,
            strategy_net_return_stress=0.05,
            benchmark_net_return_base=0.04,
            benchmark_net_return_stress=0.02,
            same_universe_control_return_base=0.03,
            same_universe_control_return_stress=0.01,
            base_cost_result=BaseCostResult(
                result_id="base_cost_terminal_synthetic_001",
                slippage_bps=1.0,
                commission_bps=2.0,
                impact_bps=1.0,
                total_cost_bps=4.0,
                assumptions_hash="b" * 64,
            ),
            stress_cost_result=StressCostResult(
                result_id="stress_cost_terminal_synthetic_001",
                slippage_bps=2.0,
                commission_bps=3.0,
                impact_bps=2.0,
                total_cost_bps=7.0,
                stress_multiplier=2.0,
                assumptions_hash="c" * 64,
            ),
        )

    def _create_fake_report(self) -> ImmutableBacktestReport:
        """Create a current-contract report from synthetic same-draw facts."""
        return BacktestReportBuilder().build_report(
            report_id="report_001",
            strategy_revision_id=self.protocol.strategy_revision_id,
            protocol_snapshot_id=self.protocol.protocol_snapshot_id,
            strategy_config_hash=self.protocol.strategy_config_hash,
            data_snapshot_hash=self.protocol.data_snapshot_hash,
            gate_criteria_hash=self.protocol.gate_criteria_hash,
            oos_draw_index=1,
            shared_oos_window_id=self.protocol.shared_oos_window_id,
            b4_result=self._create_fake_b4_result(),
            adjustment_mode="qfq",
            adjustment_snapshot_fingerprint="d" * 64,
            same_draw_result=self._create_fake_same_draw_result(),
        )

    def _create_fake_gate(self, report: ImmutableBacktestReport) -> PrototypeGateResultV2:
        """Create a current-contract deterministic Gate result."""
        return PrototypeGateV2().evaluate(
            report=report,
            gate_criteria_hash=self.protocol.gate_criteria_hash,
        )


if __name__ == "__main__":
    unittest.main()
