"""
B5 Task 10: Vertical Flow Test

End-to-end test from frozen B3/B4 to B5 Gate/Explanation.
Uses real B5 components to prove complete flow.
"""
import unittest
from datetime import datetime, date
from backend.db.strategy import StrategyDB
from backend.services.oos_evaluation_controller import OOSEvaluationController
from backend.services.prototype_gate_v2 import PrototypeGateV2
from backend.services.gate_explanation_builder import GateExplanationBuilder
from backend.services.oos_budget_ledger import OOSBudgetLedger
from backend.services.b3_protocol_types import (
    DataSnapshotManifest,
    PointInTimeMembershipSnapshot,
)
from contracts.strategy import (
    StrategyDraft,
    StrategyLifecycleState,
    ResearchProtocolSnapshot,
    ImmutableBacktestReport,
    BacktestUniverseSpec,
)


class TestB5VerticalFlow(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path
        from backend.db.strategy import StrategyDB
        
        self.tmpfile = tempfile.NamedTemporaryFile(mode='w', suffix='.db', delete=False)
        self.tmpfile.close()
        self.db_path = Path(self.tmpfile.name)
        self.strategy_db = StrategyDB(str(self.db_path))
        self.budget_ledger = OOSBudgetLedger(self.strategy_db)
        self.controller = OOSEvaluationController()
        self.gate = PrototypeGateV2()
        self.explanation_builder = GateExplanationBuilder()
        self._create_universe_spec()
    
    def tearDown(self):
        self.strategy_db.close()
        if self.db_path.exists():
            self.db_path.unlink()

    def _create_universe_spec(self):
        """Create required BacktestUniverseSpec."""
        universe_spec = BacktestUniverseSpec(
            universe_spec_id="univ_001",
            universe_rule_type="point_in_time_membership",
            membership_source="test_source",
            membership_effective_from=date(2023, 1, 1),
            membership_effective_to=date(2024, 12, 31),
            snapshot_date=date(2024, 1, 1),
            include_delisted=True,
            membership_snapshot_ids=("snap_001",),
            quality_status="ok",
            frozen=True,
        )
        self.strategy_db.store_backtest_universe(universe_spec)

    def _create_frozen_protocol(self) -> ResearchProtocolSnapshot:
        """Create frozen B3 protocol."""
        protocol = ResearchProtocolSnapshot(
            protocol_snapshot_id="protocol_001",
            theme_id="theme_001",
            hypothesis_source_snapshot_id="hypo_snap_001",
            strategy_revision_id="strat_001",
            sample_split_rule_id="split_001",
            oos_window_rule_id="oos_rule_001",
            oos_window_rule_params_json='{"draw": 1}',
            oos_window_start=date(2024, 1, 1),
            oos_window_end=date(2024, 6, 30),
            shared_oos_window_id="shared_oos_001",
            backtest_universe_spec_id="univ_001",
            data_snapshot_id="data_001",
            kill_criteria_snapshot_id="kill_001",
            prototype_gate_thresholds_json='{"min_sharpe": 1.0}',
            strategy_config_hash="hash_config",
            data_snapshot_hash="hash_data",
            gate_criteria_hash="hash_gate",
            frozen_at=datetime.now(),
            frozen_by="test",
            frozen=True,
        )
        return protocol

    def _create_data_manifest(self) -> DataSnapshotManifest:
        """Create B3 data snapshot manifest."""
        return DataSnapshotManifest(
            snapshot_id="data_001",
            provider="test_provider",
            retrieval_date=date(2024, 1, 1),
            market_data_start=date(2023, 1, 1),
            market_data_end=date(2024, 6, 30),
            universe_snapshot_ids=("univ_pit_001",),
            semantic_hash="hash_data",
            quality_status="ok",
            gaps=(),
        )

    def _create_universe(self) -> PointInTimeMembershipSnapshot:
        """Create point-in-time universe."""
        return PointInTimeMembershipSnapshot(
            snapshot_id="univ_pit_001",
            snapshot_date=date(2024, 1, 1),
            universe_rule_type="point_in_time_membership",
            membership_source="index_constituent",
            include_delisted=True,
            records=(),
            quality_status="ok",
            gaps=(),
        )

    def _create_b4_formal_result(self, protocol: ResearchProtocolSnapshot) -> dict:
        """Create B4 formal qualification result."""
        return {
            "result": type(
                "BacktestEngineQualificationResult",
                (),
                {"qualification_status": "pass"},
            )(),
            "protocol_snapshot_id": protocol.protocol_snapshot_id,
            "data_snapshot_hash": protocol.data_snapshot_hash,
            "data_snapshot_id": protocol.data_snapshot_id,
            "universe_type": "point_in_time",
            "universe_snapshot_id": "univ_pit_001",
        }

    def _create_oos_report(
        self, protocol: ResearchProtocolSnapshot
    ) -> ImmutableBacktestReport:
        """Create OOS backtest report."""
        report = ImmutableBacktestReport(
            report_id="report_001",
            theme_id="theme_001",
            strategy_revision_id="strat_001",
            protocol_snapshot_id=protocol.protocol_snapshot_id,
            strategy_config_hash=protocol.strategy_config_hash,
            data_snapshot_hash=protocol.data_snapshot_hash,
            gate_criteria_hash=protocol.gate_criteria_hash,
            evaluation_mode="out_of_sample",
            oos_draw_index=1,
            shared_oos_window_id="shared_oos_001",
            multiple_comparison_flag=False,
            report_payload_json='{"sharpe": 1.5, "future_data_violation_count": 0, "stress_cost_result": {"status": "pass"}, "control_comparison": {"status": "pass"}, "base_cost_result": {"status": "pass"}, "benchmark_comparison": {"status": "pass"}, "data_quality_status": "ok"}',
            integrity_status="valid",
            generated_at=datetime.now(),
            report_hash="hash_report_001",
            frozen=True,
        )
        return report

    def test_vertical_flow_from_frozen_protocol_to_gate_explanation(self):
        """Complete flow from B3 protocol to B5 Gate explanation."""
        # Step 1: Create frozen B3 protocol
        protocol = self._create_frozen_protocol()
        self.assertTrue(protocol.frozen)
        self.assertEqual(protocol.strategy_config_hash, "hash_config")

        # Step 2: Create B3 data manifest
        manifest = self._create_data_manifest()
        self.assertEqual(manifest.semantic_hash, "hash_data")

        # Step 3: Create point-in-time universe
        universe = self._create_universe()
        self.assertEqual(universe.quality_status, "ok")

        # Step 4: Validate B3/B4 prerequisites
        b4_result = self._create_b4_formal_result(protocol)
        validated_metadata = self.controller.validate_b3_b4_prerequisites(
            protocol, manifest, universe, b4_result
        )

        self.assertEqual(
            validated_metadata["protocol_snapshot_id"], protocol.protocol_snapshot_id
        )
        self.assertEqual(
            validated_metadata["data_snapshot_hash"], protocol.data_snapshot_hash
        )

        # Step 5: Reserve OOS budget
        reservation = self.budget_ledger.reserve_oos_draw(
            theme_id=protocol.theme_id,
            hypothesis_source_snapshot_id=protocol.hypothesis_source_snapshot_id,
            strategy_config_hash=protocol.strategy_config_hash,
            data_snapshot_hash=protocol.data_snapshot_hash,
            gate_criteria_hash=protocol.gate_criteria_hash,
            shared_oos_window_id=protocol.shared_oos_window_id,
            idempotency_key="vertical_flow_complete",
        )

        self.assertEqual(reservation.oos_draw_index, 1)
        self.assertEqual(reservation.status, "reserved")
        self.budget_ledger.start_execution(reservation.reservation_id)

        # Step 6: Create OOS report
        report = self._create_oos_report(protocol)
        self.assertEqual(report.integrity_status, "valid")
        self.assertEqual(report.oos_draw_index, 1)

        # Step 7: Run Gate evaluation
        gate_result = self.gate.evaluate(report, protocol.gate_criteria_hash)

        self.assertIn(
            gate_result.verdict,
            ["rejected", "needs_review", "candidate_for_prototype_passed"],
        )
        self.assertEqual(gate_result.report_id, report.report_id)
        self.assertEqual(gate_result.strategy_config_hash, protocol.strategy_config_hash)

        # Step 8: Build explanation
        explanation = self.explanation_builder.build_explanation(
            report.report_id, gate_result
        )

        self.assertEqual(explanation.report_id, report.report_id)
        self.assertEqual(explanation.gate_result_id, gate_result.gate_result_id)
        self.assertIsNotNone(explanation.plain_summary)
        self.assertGreater(len(explanation.deterministic_evidence), 0)

        # Step 9: Complete reservation
        self.budget_ledger.complete_reservation(
            reservation.reservation_id, gate_result.verdict, report_id=report.report_id
        )

        # Verify budget consumed
        ledger_state = self.budget_ledger.get_ledger_state(
            protocol.theme_id, protocol.hypothesis_source_snapshot_id
        )
        self.assertEqual(ledger_state["completed_draw_count"], 1)

    def test_vertical_flow_stops_on_failed_b4_qualification(self):
        """Flow stops when B4 qualification fails."""
        protocol = self._create_frozen_protocol()
        manifest = self._create_data_manifest()
        universe = self._create_universe()

        # Create failed B4 result
        b4_result = {
            "result": type(
                "BacktestEngineQualificationResult",
                (),
                {"qualification_status": "fail"},
            )(),
            "protocol_snapshot_id": protocol.protocol_snapshot_id,
            "data_snapshot_hash": protocol.data_snapshot_hash,
            "data_snapshot_id": protocol.data_snapshot_id,
            "universe_type": "point_in_time",
            "universe_snapshot_id": "univ_pit_001",
        }

        # Validation must fail
        with self.assertRaises(ValueError) as ctx:
            self.controller.validate_b3_b4_prerequisites(
                protocol, manifest, universe, b4_result
            )
        self.assertIn("qualification failed", str(ctx.exception))

    def test_vertical_flow_stops_on_b4_metadata_mismatch(self):
        """Flow stops when B4 metadata mismatches protocol."""
        protocol = self._create_frozen_protocol()
        manifest = self._create_data_manifest()
        universe = self._create_universe()

        # Create B4 result with mismatched hash
        b4_result = {
            "result": type(
                "BacktestEngineQualificationResult",
                (),
                {"qualification_status": "pass"},
            )(),
            "protocol_snapshot_id": protocol.protocol_snapshot_id,
            "data_snapshot_hash": "MISMATCHED_HASH",
            "data_snapshot_id": protocol.data_snapshot_id,
            "universe_type": "point_in_time",
            "universe_snapshot_id": "univ_pit_001",
        }

        # Validation must fail
        with self.assertRaises(ValueError) as ctx:
            self.controller.validate_b3_b4_prerequisites(
                protocol, manifest, universe, b4_result
            )
        self.assertIn("mismatch", str(ctx.exception))

    def test_vertical_flow_candidate_is_not_prototype_passed(self):
        """Gate candidate is not prototype_passed."""
        protocol = self._create_frozen_protocol()
        report = self._create_oos_report(protocol)

        # Run Gate
        gate_result = self.gate.evaluate(report, protocol.gate_criteria_hash)

        # Gate never outputs prototype_passed
        self.assertNotEqual(gate_result.verdict, "prototype_passed")
        self.assertIn(
            gate_result.verdict,
            ["rejected", "needs_review", "candidate_for_prototype_passed"],
        )

    def test_vertical_flow_uses_budget_reservation(self):
        """Vertical flow uses OOS budget reservation."""
        protocol = self._create_frozen_protocol()

        # Reserve budget
        reservation = self.budget_ledger.reserve_oos_draw(
            theme_id=protocol.theme_id,
            hypothesis_source_snapshot_id=protocol.hypothesis_source_snapshot_id,
            strategy_config_hash=protocol.strategy_config_hash,
            data_snapshot_hash=protocol.data_snapshot_hash,
            gate_criteria_hash=protocol.gate_criteria_hash,
            shared_oos_window_id=protocol.shared_oos_window_id,
            idempotency_key="vertical_budget_reservation",
        )

        self.assertEqual(reservation.status, "reserved")

        # Create report and run Gate
        report = self._create_oos_report(protocol)
        gate_result = self.gate.evaluate(report, protocol.gate_criteria_hash)
        self.budget_ledger.start_execution(reservation.reservation_id)

        # Complete reservation
        self.budget_ledger.complete_reservation(
            reservation.reservation_id, gate_result.verdict, report_id=report.report_id
        )

        # Verify budget consumed
        ledger_state = self.budget_ledger.get_ledger_state(
            protocol.theme_id, protocol.hypothesis_source_snapshot_id
        )
        self.assertEqual(ledger_state["completed_draw_count"], 1)
        self.assertEqual(ledger_state["next_oos_draw_index"], 2)

    def test_vertical_flow_rejected_report_remains_visible(self):
        """Rejected reports remain visible (not deleted)."""
        # Create draft and protocol first
        draft = StrategyDraft(
            strategy_revision_id="strat_001",
            theme_id="theme_001",
            hypothesis_id="hypo_001",
            strategy_template_id="template_001",
            strategy_template_version="1.0",
            strategy_template_hash="hash_template",
            hypothesis_source_snapshot_id="hypo_snap_001",
            backtest_universe_spec_id="univ_001",
            strategy_config_json='{"entry_rule": "test"}',
            sample_split_rule_id="split_001",
            created_at=datetime.now(),
            frozen=True,
        )
        initial_state = StrategyLifecycleState(
            lifecycle_state_id="lifecycle_strat_001_1",
            strategy_revision_id="strat_001",
            state_version=1,
            state="draft",
            source_record_id="strat_001",
            recorded_at=datetime.now(),
            recorded_by="test",
            frozen=True,
        )
        self.strategy_db.create_strategy_draft(draft, initial_state)

        protocol = self._create_frozen_protocol()
        self.strategy_db.store_protocol_snapshot(protocol)

        # Create report with failing data
        report = ImmutableBacktestReport(
            report_id="report_rejected",
            theme_id="theme_001",
            strategy_revision_id="strat_001",
            protocol_snapshot_id=protocol.protocol_snapshot_id,
            strategy_config_hash=protocol.strategy_config_hash,
            data_snapshot_hash=protocol.data_snapshot_hash,
            gate_criteria_hash=protocol.gate_criteria_hash,
            evaluation_mode="out_of_sample",
            oos_draw_index=1,
            shared_oos_window_id="shared_oos_001",
            multiple_comparison_flag=False,
            report_payload_json='{"sharpe": 0.5, "future_data_violation_count": 5, "data_quality_status": "insufficient"}',
            integrity_status="invalid",
            generated_at=datetime.now(),
            report_hash="hash_report_rejected",
            frozen=True,
        )

        # Store report
        self.strategy_db.store_backtest_report(report)

        # Run Gate (will reject)
        gate_result = self.gate.evaluate(report, protocol.gate_criteria_hash)
        self.assertEqual(gate_result.verdict, "rejected")

        # Store gate result
        self.strategy_db.store_gate_result(gate_result)

        # Report still exists in DB
        retrieved_report = self.strategy_db.get_backtest_report(report.report_id)
        self.assertIsNotNone(retrieved_report)
        self.assertEqual(retrieved_report.report_id, report.report_id)

        # Gate result still exists
        retrieved_gate = self.strategy_db.get_gate_result(gate_result.gate_result_id)
        self.assertIsNotNone(retrieved_gate)
        self.assertEqual(retrieved_gate.verdict, "rejected")

    def test_vertical_flow_with_cache_hit(self):
        """Vertical flow with cache hit does not consume budget."""
        protocol = self._create_frozen_protocol()

        # First draw
        reservation1 = self.budget_ledger.reserve_oos_draw(
            theme_id=protocol.theme_id,
            hypothesis_source_snapshot_id=protocol.hypothesis_source_snapshot_id,
            strategy_config_hash=protocol.strategy_config_hash,
            data_snapshot_hash=protocol.data_snapshot_hash,
            gate_criteria_hash=protocol.gate_criteria_hash,
            shared_oos_window_id=protocol.shared_oos_window_id,
            idempotency_key="vertical_cache_hit",
        )
        self.assertEqual(reservation1.oos_draw_index, 1)

        report = self._create_oos_report(protocol)
        gate_result = self.gate.evaluate(report, protocol.gate_criteria_hash)
        self.budget_ledger.start_execution(reservation1.reservation_id)
        self.budget_ledger.complete_reservation(
            reservation1.reservation_id, gate_result.verdict, report_id=report.report_id
        )

        # Second attempt with same hashes (cache hit)
        cache_check = self.budget_ledger.check_cache(
            protocol.strategy_config_hash,
            protocol.data_snapshot_hash,
            protocol.gate_criteria_hash,
        )
        self.assertIsNotNone(cache_check)

        # Budget still at 1 draw
        ledger_state = self.budget_ledger.get_ledger_state(
            protocol.theme_id, protocol.hypothesis_source_snapshot_id
        )
        self.assertEqual(ledger_state["completed_draw_count"], 1)


if __name__ == "__main__":
    unittest.main()
