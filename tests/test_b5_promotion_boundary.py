"""
B5 Task 9: Human Confirmation and Promotion Boundary Tests

Validates that only StrategyPromotionReducer can write prototype_passed.
Gate cannot directly write prototype_passed.
Only candidate_for_prototype_passed + human approval can trigger promotion.
"""
import unittest
from datetime import datetime, date
from backend.db.strategy import StrategyDB
from backend.services.strategy_promotion_reducer import StrategyPromotionReducer
from backend.services.prototype_gate_v2 import PrototypeGateV2
from contracts.strategy import (
    StrategyDraft,
    StrategyLifecycleState,
    ResearchProtocolSnapshot,
    ImmutableBacktestReport,
    PrototypeGateResultV2,
    HumanPromotionConfirmation,
    BacktestUniverseSpec,
)


class TestPromotionBoundary(unittest.TestCase):
    def setUp(self):
        self.db = StrategyDB(":memory:")
        self.reducer = StrategyPromotionReducer(self.db)
        self.gate = PrototypeGateV2()
        self._create_universe_spec()

    def tearDown(self):
        self.db.close()

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
        self.db.store_backtest_universe(universe_spec)

    def _create_draft(self, strategy_revision_id: str = "strat_001") -> StrategyDraft:
        draft = StrategyDraft(
            strategy_revision_id=strategy_revision_id,
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
            lifecycle_state_id=f"lifecycle_{strategy_revision_id}_1",
            strategy_revision_id=strategy_revision_id,
            state_version=1,
            state="draft",
            source_record_id=strategy_revision_id,
            recorded_at=datetime.now(),
            recorded_by="test",
            frozen=True,
        )
        self.db.create_strategy_draft(draft, initial_state)
        return draft

    def _create_protocol(self, strategy_revision_id: str) -> ResearchProtocolSnapshot:
        protocol = ResearchProtocolSnapshot(
            protocol_snapshot_id=f"protocol_{strategy_revision_id}",
            theme_id="theme_001",
            hypothesis_source_snapshot_id="hypo_snap_001",
            strategy_revision_id=strategy_revision_id,
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
        self.db.store_protocol_snapshot(protocol)
        return protocol

    def _create_report(
        self, strategy_revision_id: str, protocol: ResearchProtocolSnapshot
    ) -> ImmutableBacktestReport:
        report = ImmutableBacktestReport(
            report_id=f"report_{strategy_revision_id}",
            theme_id="theme_001",
            strategy_revision_id=strategy_revision_id,
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
        self.db.store_backtest_report(report)
        return report

    def _create_gate_result(
        self,
        report: ImmutableBacktestReport,
        verdict: str = "candidate_for_prototype_passed",
    ) -> PrototypeGateResultV2:
        gate_result = self.gate.evaluate(report, report.gate_criteria_hash)
        # Override verdict for test scenarios
        if verdict != gate_result.verdict:
            gate_result = PrototypeGateResultV2(
                gate_result_id=gate_result.gate_result_id,
                report_id=gate_result.report_id,
                strategy_revision_id=gate_result.strategy_revision_id,
                protocol_snapshot_id=gate_result.protocol_snapshot_id,
                verdict=verdict,
                checks_json=gate_result.checks_json,
                blocking_issues=gate_result.blocking_issues,
                warnings=gate_result.warnings,
                strategy_config_hash=gate_result.strategy_config_hash,
                data_snapshot_hash=gate_result.data_snapshot_hash,
                gate_criteria_hash=gate_result.gate_criteria_hash,
                oos_draw_index=gate_result.oos_draw_index,
                shared_oos_window_id=gate_result.shared_oos_window_id,
                multiple_comparison_flag=gate_result.multiple_comparison_flag,
                generated_at=gate_result.generated_at,
                gate_result_hash=gate_result.gate_result_hash,
                frozen=True,
            )
        self.db.store_gate_result(gate_result)
        return gate_result

    def _create_human_confirmation(
        self, strategy_revision_id: str, gate_result_id: str, decision: str = "approve"
    ) -> HumanPromotionConfirmation:
        confirmation = HumanPromotionConfirmation(
            human_confirmation_id=f"confirm_{strategy_revision_id}",
            strategy_revision_id=strategy_revision_id,
            gate_result_id=gate_result_id,
            decision=decision,
            confirmed_by="user",
            confirmed_at=datetime.now(),
            frozen=True,
        )
        self.db.store_human_confirmation(confirmation)
        return confirmation

    def test_only_strategy_promotion_reducer_writes_prototype_passed(self):
        """Only StrategyPromotionReducer can write prototype_passed."""
        draft = self._create_draft()
        protocol = self._create_protocol(draft.strategy_revision_id)
        report = self._create_report(draft.strategy_revision_id, protocol)
        gate_result = self._create_gate_result(report)

        # Verify Gate does not write prototype_passed
        self.assertNotEqual(gate_result.verdict, "prototype_passed")
        self.assertIn(
            gate_result.verdict,
            ["rejected", "needs_review", "candidate_for_prototype_passed"],
        )

        # Verify lifecycle is still draft
        state = self.db.get_latest_lifecycle_state(draft.strategy_revision_id)
        self.assertEqual(state.state, "draft")

        # Only reducer can promote
        confirmation = self._create_human_confirmation(
            draft.strategy_revision_id, gate_result.gate_result_id
        )
        promotion = self.reducer.promote_to_prototype_passed(
            draft.strategy_revision_id,
            gate_result.gate_result_id,
            confirmation.human_confirmation_id,
            "test_promoter",
        )

        # Now lifecycle is prototype_passed
        state = self.db.get_latest_lifecycle_state(draft.strategy_revision_id)
        self.assertEqual(state.state, "prototype_passed")
        self.assertEqual(promotion.new_state, "prototype_passed")

    def test_gate_candidate_requires_human_approval_before_promotion(self):
        """Gate candidate requires human approval before promotion."""
        draft = self._create_draft()
        protocol = self._create_protocol(draft.strategy_revision_id)
        report = self._create_report(draft.strategy_revision_id, protocol)
        gate_result = self._create_gate_result(report, "candidate_for_prototype_passed")

        self.assertEqual(gate_result.verdict, "candidate_for_prototype_passed")

        # Cannot promote without human confirmation
        with self.assertRaises(ValueError) as ctx:
            self.reducer.promote_to_prototype_passed(
                draft.strategy_revision_id,
                gate_result.gate_result_id,
                "nonexistent_confirmation",
                "test_promoter",
            )
        self.assertIn("human confirmation not found", str(ctx.exception))

        # Add human confirmation
        confirmation = self._create_human_confirmation(
            draft.strategy_revision_id, gate_result.gate_result_id, "approve"
        )

        # Now promotion succeeds
        promotion = self.reducer.promote_to_prototype_passed(
            draft.strategy_revision_id,
            gate_result.gate_result_id,
            confirmation.human_confirmation_id,
            "test_promoter",
        )
        self.assertEqual(promotion.new_state, "prototype_passed")

    def test_rejected_gate_cannot_be_promoted(self):
        """Rejected Gate cannot be promoted."""
        draft = self._create_draft()
        protocol = self._create_protocol(draft.strategy_revision_id)
        report = self._create_report(draft.strategy_revision_id, protocol)
        gate_result = self._create_gate_result(report, "rejected")

        self.assertEqual(gate_result.verdict, "rejected")

        confirmation = self._create_human_confirmation(
            draft.strategy_revision_id, gate_result.gate_result_id, "approve"
        )

        # Cannot promote rejected verdict
        with self.assertRaises(ValueError) as ctx:
            self.reducer.promote_to_prototype_passed(
                draft.strategy_revision_id,
                gate_result.gate_result_id,
                confirmation.human_confirmation_id,
                "test_promoter",
            )
        self.assertIn("candidate_for_prototype_passed", str(ctx.exception))

    def test_needs_review_gate_cannot_be_promoted(self):
        """needs_review Gate cannot be promoted."""
        draft = self._create_draft()
        protocol = self._create_protocol(draft.strategy_revision_id)
        report = self._create_report(draft.strategy_revision_id, protocol)
        gate_result = self._create_gate_result(report, "needs_review")

        self.assertEqual(gate_result.verdict, "needs_review")

        confirmation = self._create_human_confirmation(
            draft.strategy_revision_id, gate_result.gate_result_id, "approve"
        )

        # Cannot promote needs_review verdict
        with self.assertRaises(ValueError) as ctx:
            self.reducer.promote_to_prototype_passed(
                draft.strategy_revision_id,
                gate_result.gate_result_id,
                confirmation.human_confirmation_id,
                "test_promoter",
            )
        self.assertIn("candidate_for_prototype_passed", str(ctx.exception))

    def test_hash_mismatch_blocks_promotion(self):
        """Hash mismatch between protocol/gate/report blocks promotion."""
        draft = self._create_draft()
        protocol = self._create_protocol(draft.strategy_revision_id)
        report = self._create_report(draft.strategy_revision_id, protocol)

        # Create gate with mismatched hash
        gate_result = PrototypeGateResultV2(
            gate_result_id=f"gate_{report.report_id}",
            report_id=report.report_id,
            strategy_revision_id=draft.strategy_revision_id,
            protocol_snapshot_id=protocol.protocol_snapshot_id,
            verdict="candidate_for_prototype_passed",
            checks_json='{}',
            strategy_config_hash="MISMATCHED_HASH",
            data_snapshot_hash=protocol.data_snapshot_hash,
            gate_criteria_hash=protocol.gate_criteria_hash,
            oos_draw_index=1,
            shared_oos_window_id="shared_oos_001",
            multiple_comparison_flag=False,
            generated_at=datetime.now(),
            gate_result_hash="hash_gate_mismatch",
            frozen=True,
        )
        self.db.store_gate_result(gate_result)

        confirmation = self._create_human_confirmation(
            draft.strategy_revision_id, gate_result.gate_result_id
        )

        # Hash mismatch blocks promotion
        with self.assertRaises(ValueError) as ctx:
            self.reducer.promote_to_prototype_passed(
                draft.strategy_revision_id,
                gate_result.gate_result_id,
                confirmation.human_confirmation_id,
                "test_promoter",
            )
        self.assertIn("hash mismatch", str(ctx.exception))

    def test_human_confirmation_contains_no_technical_parameters(self):
        """Human confirmation contains no technical parameters."""
        draft = self._create_draft()
        protocol = self._create_protocol(draft.strategy_revision_id)
        report = self._create_report(draft.strategy_revision_id, protocol)
        gate_result = self._create_gate_result(report, "candidate_for_prototype_passed")

        # Create confirmation (decision is approve/reject only)
        confirmation = HumanPromotionConfirmation(
            human_confirmation_id=f"confirm_{draft.strategy_revision_id}",
            strategy_revision_id=draft.strategy_revision_id,
            gate_result_id=gate_result.gate_result_id,
            decision="approve",
            confirmed_by="user",
            confirmed_at=datetime.now(),
            frozen=True,
        )

        # Verify confirmation has no technical parameter fields
        self.assertNotIn("sharpe_threshold", confirmation.model_dump())
        self.assertNotIn("oos_window", confirmation.model_dump())
        self.assertNotIn("stop_loss", confirmation.model_dump())
        self.assertNotIn("holding_period", confirmation.model_dump())
        self.assertNotIn("gate_criteria", confirmation.model_dump())

        # Only allowed fields are decision (approve/reject)
        self.assertIn(confirmation.decision, ["approve", "reject"])

    def test_b5_gate_does_not_call_promotion_reducer_directly(self):
        """B5 Gate does not call PromotionReducer directly."""
        draft = self._create_draft()
        protocol = self._create_protocol(draft.strategy_revision_id)
        report = self._create_report(draft.strategy_revision_id, protocol)

        # Gate evaluation
        gate_result = self.gate.evaluate(report, report.gate_criteria_hash)

        # Gate result does not trigger promotion
        state = self.db.get_latest_lifecycle_state(draft.strategy_revision_id)
        self.assertEqual(state.state, "draft")

        # Store gate result
        self.db.store_gate_result(gate_result)

        # Lifecycle still draft
        state = self.db.get_latest_lifecycle_state(draft.strategy_revision_id)
        self.assertEqual(state.state, "draft")

        # Gate never writes prototype_passed
        self.assertNotEqual(gate_result.verdict, "prototype_passed")

    def test_human_rejection_blocks_promotion(self):
        """Human rejection blocks promotion even if Gate is candidate."""
        draft = self._create_draft()
        protocol = self._create_protocol(draft.strategy_revision_id)
        report = self._create_report(draft.strategy_revision_id, protocol)
        gate_result = self._create_gate_result(report, "candidate_for_prototype_passed")

        # Human rejects
        confirmation = self._create_human_confirmation(
            draft.strategy_revision_id, gate_result.gate_result_id, "reject"
        )

        self.assertEqual(confirmation.decision, "reject")

        # Cannot promote with rejection
        with self.assertRaises(ValueError) as ctx:
            self.reducer.promote_to_prototype_passed(
                draft.strategy_revision_id,
                gate_result.gate_result_id,
                confirmation.human_confirmation_id,
                "test_promoter",
            )
        self.assertIn("approve", str(ctx.exception))

    def test_report_integrity_invalid_blocks_promotion(self):
        """Invalid report integrity blocks promotion."""
        draft = self._create_draft()
        protocol = self._create_protocol(draft.strategy_revision_id)

        # Create invalid report
        report = ImmutableBacktestReport(
            report_id=f"report_{draft.strategy_revision_id}",
            theme_id="theme_001",
            strategy_revision_id=draft.strategy_revision_id,
            protocol_snapshot_id=protocol.protocol_snapshot_id,
            strategy_config_hash=protocol.strategy_config_hash,
            data_snapshot_hash=protocol.data_snapshot_hash,
            gate_criteria_hash=protocol.gate_criteria_hash,
            evaluation_mode="out_of_sample",
            oos_draw_index=1,
            shared_oos_window_id="shared_oos_001",
            multiple_comparison_flag=False,
            report_payload_json='{"sharpe": 1.5}',
            integrity_status="invalid",
            generated_at=datetime.now(),
            report_hash="hash_report_invalid",
            frozen=True,
        )
        self.db.store_backtest_report(report)

        gate_result = self._create_gate_result(report, "candidate_for_prototype_passed")
        confirmation = self._create_human_confirmation(
            draft.strategy_revision_id, gate_result.gate_result_id
        )

        # Cannot promote invalid report
        with self.assertRaises(ValueError) as ctx:
            self.reducer.promote_to_prototype_passed(
                draft.strategy_revision_id,
                gate_result.gate_result_id,
                confirmation.human_confirmation_id,
                "test_promoter",
            )
        self.assertIn("integrity is invalid", str(ctx.exception))

    def test_confirmation_consumption_prevents_reuse(self):
        """Consumed confirmation cannot be reused for another promotion."""
        draft1 = self._create_draft("strat_001")
        protocol1 = self._create_protocol(draft1.strategy_revision_id)
        report1 = self._create_report(draft1.strategy_revision_id, protocol1)
        gate1 = self._create_gate_result(report1, "candidate_for_prototype_passed")
        confirmation1 = self._create_human_confirmation(
            draft1.strategy_revision_id, gate1.gate_result_id
        )

        # First promotion succeeds
        promotion1 = self.reducer.promote_to_prototype_passed(
            draft1.strategy_revision_id,
            gate1.gate_result_id,
            confirmation1.human_confirmation_id,
            "test",
        )
        self.assertEqual(promotion1.new_state, "prototype_passed")

        # Confirmation is now consumed
        self.assertTrue(self.db._confirmation_is_consumed(confirmation1.human_confirmation_id))

        # Create second draft trying to reuse same confirmation (hypothetical attack)
        draft2 = self._create_draft("strat_002")
        protocol2 = self._create_protocol(draft2.strategy_revision_id)

        # Create unique report with different hash
        report2 = ImmutableBacktestReport(
            report_id=f"report_{draft2.strategy_revision_id}",
            theme_id="theme_001",
            strategy_revision_id=draft2.strategy_revision_id,
            protocol_snapshot_id=protocol2.protocol_snapshot_id,
            strategy_config_hash=protocol2.strategy_config_hash,
            data_snapshot_hash=protocol2.data_snapshot_hash,
            gate_criteria_hash=protocol2.gate_criteria_hash,
            evaluation_mode="out_of_sample",
            oos_draw_index=1,
            shared_oos_window_id="shared_oos_001",
            multiple_comparison_flag=False,
            report_payload_json='{"sharpe": 1.5, "future_data_violation_count": 0, "stress_cost_result": {"status": "pass"}, "control_comparison": {"status": "pass"}, "base_cost_result": {"status": "pass"}, "benchmark_comparison": {"status": "pass"}, "data_quality_status": "ok"}',
            integrity_status="valid",
            generated_at=datetime.now(),
            report_hash="hash_report_002_unique",  # Unique hash
            frozen=True,
        )
        self.db.store_backtest_report(report2)

        gate2 = self._create_gate_result(report2, "candidate_for_prototype_passed")

        # Cannot reuse consumed confirmation (belongs to another strategy)
        with self.assertRaises(ValueError) as ctx:
            self.reducer.promote_to_prototype_passed(
                draft2.strategy_revision_id,
                gate2.gate_result_id,
                confirmation1.human_confirmation_id,  # Reusing consumed confirmation
                "test",
            )
        # Either "already consumed" or "belongs to another strategy" validates the boundary
        error_msg = str(ctx.exception)
        self.assertTrue(
            "already consumed" in error_msg or "belongs to another strategy" in error_msg,
            f"Expected consumption or ownership error, got: {error_msg}"
        )


if __name__ == "__main__":
    unittest.main()
