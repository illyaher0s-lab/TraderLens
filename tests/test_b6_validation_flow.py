"""
B6 Final Vertical Flow Tests

Tests the minimal B-module V1 vertical flow from StrategyDraft to C admission.
"""
import unittest
from datetime import datetime, date

from backend.services.b5_oos_types import B6ValidationRunResult
from backend.services.b6_validation_flow import B6ValidationFlow
from contracts.strategy import (
    StrategyDraft,
    ResearchProtocolSnapshot,
    BacktestUniverseSpec,
    StrategyLifecycleState,
    ImmutableBacktestReport,
    PrototypeGateResultV2,
)
from backend.services.b3_protocol_types import (
    DataSnapshotManifest,
    PointInTimeMembershipSnapshot,
    UniverseMembershipRecord,
)
from backend.services.b4_protocol_types import EventBacktestResult
from backend.services.b5_oos_types import ExplanationSnapshot
from backend.db.strategy import StrategyDB
from backend.services.strategy_promotion_reducer import StrategyPromotionReducer


class TestB6ValidationFlow(unittest.TestCase):
    def test_b6_run_result_is_frozen_and_has_no_trade_instruction_fields(self):
        """B6 run result is frozen and contains no buy/sell/trade fields."""
        result = B6ValidationRunResult(
            run_id="b6_run_001",
            strategy_revision_id="strat_001",
            protocol_snapshot_id="proto_001",
            report_id="report_001",
            gate_result_id="gate_001",
            explanation_id="expl_001",
            promotion_id=None,
            final_state="candidate_for_prototype_passed",
            status="completed",
            blocking_reason=None,
            created_at=datetime(2026, 6, 28, 10, 0, 0),
        )

        # Verify frozen
        self.assertTrue(result.frozen)

        # Verify no trade instruction fields
        dumped = result.model_dump()
        self.assertNotIn("buy", dumped)
        self.assertNotIn("sell", dumped)
        self.assertNotIn("target_price", dumped)
        self.assertNotIn("stop_loss", dumped)
        self.assertNotIn("action_plan", dumped)

        # Verify immutable
        with self.assertRaises(Exception):
            result.status = "changed"

    def test_b6_flow_rejects_missing_strategy_draft(self):
        """B6 flow rejects missing StrategyDraft."""
        flow = B6ValidationFlow()

        with self.assertRaises(ValueError) as ctx:
            flow.run_minimal_validation(
                strategy_draft=None,
                protocol=None,
                manifest=None,
                universe=None,
                b4_qualification=None,
                b4_event_result=None,
                human_decision=None,
            )

        self.assertIn("StrategyDraft is required", str(ctx.exception))

    def test_b6_flow_rejects_missing_b4_formal_qualification(self):
        """B6 flow rejects missing B4 formal qualification."""
        flow = B6ValidationFlow()

        # Create minimal fixtures
        strategy_draft = self._create_strategy_draft()
        protocol = self._create_protocol()

        with self.assertRaises(ValueError) as ctx:
            flow.run_minimal_validation(
                strategy_draft=strategy_draft,
                protocol=protocol,
                manifest=None,
                universe=None,
                b4_qualification=None,
                b4_event_result=None,
                human_decision=None,
            )

        self.assertIn("required", str(ctx.exception).lower())

    def test_b6_flow_rejects_user_supplied_technical_parameters(self):
        """B6 flow rejects user-supplied technical parameters."""
        flow = B6ValidationFlow()

        with self.assertRaises(ValueError) as ctx:
            flow.run_minimal_validation(
                strategy_draft=None,
                protocol=None,
                manifest=None,
                universe=None,
                b4_qualification=None,
                b4_event_result=None,
                human_decision=None,
                user_gate_thresholds={"min_sharpe": 0.1},
            )

        self.assertIn("user-supplied technical parameters", str(ctx.exception).lower())

    def test_b6_flow_stops_on_failed_b4_qualification(self):
        """B6 flow stops on failed B4 qualification."""
        flow = B6ValidationFlow()

        strategy_draft = self._create_strategy_draft()
        protocol = self._create_protocol()
        manifest = self._create_manifest()
        universe = self._create_universe()

        # Create failed B4 qualification
        failed_b4 = self._create_b4_qualification_dict()
        failed_b4["result"].qualification_status = "fail"

        with self.assertRaises(ValueError) as ctx:
            flow.run_minimal_validation(
                strategy_draft=strategy_draft,
                protocol=protocol,
                manifest=manifest,
                universe=universe,
                b4_qualification=failed_b4,
                b4_event_result=self._create_b4_event_result(),
                human_decision=None,
            )

        self.assertIn("qualification failed", str(ctx.exception).lower())

    def test_b6_flow_stops_on_b4_metadata_mismatch(self):
        """B6 flow stops on B4 metadata mismatch."""
        flow = B6ValidationFlow()

        strategy_draft = self._create_strategy_draft()
        protocol = self._create_protocol()
        manifest = self._create_manifest()
        universe = self._create_universe()

        # Create B4 with mismatched data_snapshot_hash
        mismatched_b4 = self._create_b4_qualification_dict()
        mismatched_b4["data_snapshot_hash"] = "wrong_hash"

        with self.assertRaises(ValueError) as ctx:
            flow.run_minimal_validation(
                strategy_draft=strategy_draft,
                protocol=protocol,
                manifest=manifest,
                universe=universe,
                b4_qualification=mismatched_b4,
                b4_event_result=self._create_b4_event_result(),
                human_decision=None,
            )

        self.assertIn("mismatch", str(ctx.exception).lower())

    def test_b6_flow_produces_report_gate_and_explanation(self):
        """B6 flow produces report, gate, and explanation."""
        flow = B6ValidationFlow()

        result = flow.run_minimal_validation(
            strategy_draft=self._create_strategy_draft(),
            protocol=self._create_protocol(),
            manifest=self._create_manifest(),
            universe=self._create_universe(),
            b4_qualification=self._create_b4_qualification_dict(),
            b4_event_result=self._create_b4_event_result(),
            human_decision=None,
        )

        self.assertEqual(result.status, "completed")
        self.assertIsNotNone(result.report_id)
        self.assertIsNotNone(result.gate_result_id)
        self.assertIsNotNone(result.explanation_id)
        self.assertIn(
            result.final_state,
            ["rejected", "needs_review", "candidate_for_prototype_passed"],
        )

    def test_b6_flow_candidate_without_human_approval_is_not_prototype_passed(self):
        """B6 flow candidate without human approval is not prototype_passed."""
        flow = B6ValidationFlow()

        result = flow.run_minimal_validation(
            strategy_draft=self._create_strategy_draft(),
            protocol=self._create_protocol(),
            manifest=self._create_manifest(),
            universe=self._create_universe(),
            b4_qualification=self._create_b4_qualification_dict(),
            b4_event_result=self._create_b4_event_result(),
            human_decision=None,
        )

        self.assertNotEqual(result.final_state, "prototype_passed")
        self.assertIsNone(result.promotion_id)

    def test_b6_flow_human_reject_never_promotes(self):
        """B6 flow human reject never promotes."""
        flow = B6ValidationFlow()

        result = flow.run_minimal_validation(
            strategy_draft=self._create_strategy_draft(),
            protocol=self._create_protocol(),
            manifest=self._create_manifest(),
            universe=self._create_universe(),
            b4_qualification=self._create_b4_qualification_dict(),
            b4_event_result=self._create_b4_event_result(),
            human_decision="reject",
        )

        self.assertNotEqual(result.final_state, "prototype_passed")
        self.assertIsNone(result.promotion_id)

    def test_b6_flow_uses_strategy_promotion_reducer_for_prototype_passed(self):
        """B6 flow uses StrategyPromotionReducer for prototype_passed."""
        # Create in-memory DB
        db = StrategyDB(":memory:")
        reducer = StrategyPromotionReducer(db)
        flow = B6ValidationFlow(strategy_db=db, promotion_reducer=reducer)

        # Create fixtures
        strategy_draft = self._create_strategy_draft()
        universe_spec = self._create_universe_spec()

        # Store universe and draft in DB
        db.store_backtest_universe(universe_spec)
        initial_state = StrategyLifecycleState(
            lifecycle_state_id="lifecycle_draft_001",
            strategy_revision_id=strategy_draft.strategy_revision_id,
            state_version=1,
            state="draft",
            source_record_id="draft_001",
            recorded_at=datetime.now(),
            recorded_by="test",
        )
        db.create_strategy_draft(strategy_draft, initial_state)

        # Store protocol
        protocol = self._create_protocol()
        db.store_protocol_snapshot(protocol)

        # Run flow with human approval
        result = flow.run_minimal_validation(
            strategy_draft=strategy_draft,
            protocol=protocol,
            manifest=self._create_manifest(),
            universe=self._create_universe(),
            b4_qualification=self._create_b4_qualification_dict(),
            b4_event_result=self._create_b4_event_result(),
            human_decision="approve",
        )

        # Verify promotion happened if Gate was candidate
        if result.final_state == "prototype_passed":
            self.assertIsNotNone(result.promotion_id)
            state = db.get_latest_lifecycle_state(strategy_draft.strategy_revision_id)
            self.assertEqual(state.state, "prototype_passed")

        db.close()

    def test_b6_flow_forced_candidate_promotes_through_reducer(self):
        """A candidate Gate result with human approval must promote through the reducer."""
        db = StrategyDB(":memory:")
        reducer = StrategyPromotionReducer(db)
        strategy_draft = self._create_strategy_draft()
        protocol = self._create_protocol()

        db.store_backtest_universe(self._create_universe_spec())
        db.create_strategy_draft(
            strategy_draft,
            StrategyLifecycleState(
                lifecycle_state_id="lifecycle_forced_candidate_001",
                strategy_revision_id=strategy_draft.strategy_revision_id,
                state_version=1,
                state="draft",
                source_record_id="draft_001",
                recorded_at=datetime.now(),
                recorded_by="test",
            ),
        )
        db.store_protocol_snapshot(protocol)

        flow = B6ValidationFlow(
            report_builder=_CandidateReportBuilder(),
            gate=_CandidateGate(),
            explanation_builder=_CandidateExplanationBuilder(),
            strategy_db=db,
            promotion_reducer=reducer,
        )

        result = flow.run_minimal_validation(
            strategy_draft=strategy_draft,
            protocol=protocol,
            manifest=self._create_manifest(),
            universe=self._create_universe(),
            b4_qualification=self._create_b4_qualification_dict(),
            b4_event_result=self._create_b4_event_result(),
            human_decision="approve",
        )

        self.assertEqual(result.final_state, "prototype_passed")
        self.assertIsNotNone(result.promotion_id)
        state = db.get_latest_lifecycle_state(strategy_draft.strategy_revision_id)
        self.assertEqual(state.state, "prototype_passed")
        db.close()

    def test_b6_flow_reducer_error_fails_loud(self):
        """Reducer errors must not be swallowed by B6."""
        db = StrategyDB(":memory:")
        strategy_draft = self._create_strategy_draft()
        protocol = self._create_protocol()
        db.store_backtest_universe(self._create_universe_spec())
        db.create_strategy_draft(
            strategy_draft,
            StrategyLifecycleState(
                lifecycle_state_id="lifecycle_reducer_failure_001",
                strategy_revision_id=strategy_draft.strategy_revision_id,
                state_version=1,
                state="draft",
                source_record_id="draft_001",
                recorded_at=datetime.now(),
                recorded_by="test",
            ),
        )
        db.store_protocol_snapshot(protocol)

        flow = B6ValidationFlow(
            report_builder=_CandidateReportBuilder(),
            gate=_CandidateGate(),
            explanation_builder=_CandidateExplanationBuilder(),
            strategy_db=db,
            promotion_reducer=_FailingPromotionReducer(),
        )

        with self.assertRaises(ValueError) as ctx:
            flow.run_minimal_validation(
                strategy_draft=strategy_draft,
                protocol=protocol,
                manifest=self._create_manifest(),
                universe=self._create_universe(),
                b4_qualification=self._create_b4_qualification_dict(),
                b4_event_result=self._create_b4_event_result(),
                human_decision="approve",
            )

        self.assertIn("forced reducer failure", str(ctx.exception))
        db.close()

    # Helper methods
    def _create_strategy_draft(self) -> StrategyDraft:
        return StrategyDraft(
            strategy_revision_id="strat_001",
            theme_id="theme_001",
            hypothesis_id="hypo_001",
            strategy_template_id="template_001",
            strategy_template_version="v1",
            strategy_template_hash="hash_001",
            hypothesis_source_snapshot_id="hypo_snap_001",
            backtest_universe_spec_id="univ_001",
            strategy_config_json="{}",
            sample_split_rule_id="split_001",
            created_at=datetime.now(),
        )

    def _create_universe_spec(self) -> BacktestUniverseSpec:
        return BacktestUniverseSpec(
            universe_spec_id="univ_001",
            universe_rule_type="point_in_time_membership",
            membership_source="test",
            membership_effective_from=date(2020, 1, 1),
            membership_effective_to=date(2025, 12, 31),
            snapshot_date=date(2025, 1, 1),
            include_delisted=True,
            membership_snapshot_ids=("snap_001",),
            quality_status="ok",
            gaps=(),
        )

    def _create_protocol(self) -> ResearchProtocolSnapshot:
        return ResearchProtocolSnapshot(
            protocol_snapshot_id="proto_001",
            theme_id="theme_001",
            hypothesis_source_snapshot_id="hypo_snap_001",
            strategy_revision_id="strat_001",
            sample_split_rule_id="split_001",
            oos_window_rule_id="oos_rule_001",
            oos_window_rule_params_json="{}",
            oos_window_start=date(2024, 1, 1),
            oos_window_end=date(2024, 12, 31),
            shared_oos_window_id="oos_window_001",
            backtest_universe_spec_id="univ_001",
            data_snapshot_id="data_001",
            kill_criteria_snapshot_id="kill_001",
            prototype_gate_thresholds_json="{}",
            strategy_config_hash="hash_config_001",
            data_snapshot_hash="hash_data_001",
            gate_criteria_hash="hash_gate_001",
            frozen_at=datetime.now(),
            frozen_by="test",
        )

    def _create_manifest(self) -> DataSnapshotManifest:
        return DataSnapshotManifest(
            data_snapshot_id="data_001",
            data_snapshot_hash="hash_data_001",
            created_at=date(2024, 1, 1),
            market_data_fingerprint="market_001",
            daily_status_fingerprint="status_001",
            membership_fingerprint="member_001",
            quality_status="ok",
            gaps=(),
            adjustment_factor_fingerprint="adj_001",
        )

    def _create_universe(self) -> PointInTimeMembershipSnapshot:
        return PointInTimeMembershipSnapshot(
            snapshot_id="univ_snap_001",
            snapshot_date=date(2024, 1, 1),
            universe_rule_type="point_in_time_membership",
            membership_source="test",
            include_delisted=True,
            records=(
                UniverseMembershipRecord(
                    symbol="000001.SZ",
                    effective_from=date(2020, 1, 1),
                    effective_to=date(2025, 12, 31),
                    source="test",
                    snapshot_id="univ_snap_001",
                ),
            ),
            quality_status="ok",
            gaps=(),
        )

    def _create_b4_qualification_dict(self) -> dict:
        # Mock B4 qualification result
        class QualResult:
            qualification_status = "pass"

        return {
            "result": QualResult(),
            "protocol_snapshot_id": "proto_001",
            "data_snapshot_hash": "hash_data_001",
            "data_snapshot_id": "data_001",
            "universe_type": "point_in_time",
            "universe_snapshot_id": "univ_snap_001",
        }

    def _create_b4_event_result(self) -> EventBacktestResult:
        from backend.services.b4_protocol_types import DailyPortfolioSnapshot

        return EventBacktestResult(
            result_id="b4_result_001",
            protocol_snapshot_id="proto_001",
            strategy_revision_id="strat_001",
            evaluation_mode="formal_backtest",
            backtest_start=date(2024, 1, 1),
            backtest_end=date(2024, 12, 31),
            order_intents=(),
            fills=(),
            rejected_orders=(),
            future_violations=(),
            final_portfolio=DailyPortfolioSnapshot(
                snapshot_id="portfolio_001",
                snapshot_date=date(2024, 12, 31),
                cash=100000.0,
                positions=(),
                portfolio_value=100000.0,
            ),
            frozen_at=date(2024, 12, 31),
        )


class _CandidateReportBuilder:
    def build_report(self, **kwargs):
        return ImmutableBacktestReport(
            report_id=kwargs["report_id"],
            theme_id="theme_001",
            strategy_revision_id=kwargs["strategy_revision_id"],
            protocol_snapshot_id=kwargs["protocol_snapshot_id"],
            strategy_config_hash=kwargs["strategy_config_hash"],
            data_snapshot_hash=kwargs["data_snapshot_hash"],
            gate_criteria_hash=kwargs["gate_criteria_hash"],
            evaluation_mode="out_of_sample",
            oos_draw_index=kwargs["oos_draw_index"],
            shared_oos_window_id=kwargs["shared_oos_window_id"],
            multiple_comparison_flag=False,
            report_payload_json=(
                '{"future_data_violation_count": 0, '
                '"base_cost_result": {"status": "pass"}, '
                '"stress_cost_result": {"status": "pass"}, '
                '"benchmark_comparison": {"status": "pass"}, '
                '"control_comparison": {"status": "pass"}, '
                '"data_quality_status": "ok"}'
            ),
            integrity_status="valid",
            generated_at=datetime.now(),
            report_hash="candidate_report_hash",
        )


class _CandidateGate:
    def evaluate(self, report, gate_criteria_hash):
        return PrototypeGateResultV2(
            gate_result_id="gate_candidate_001",
            report_id=report.report_id,
            strategy_revision_id=report.strategy_revision_id,
            protocol_snapshot_id=report.protocol_snapshot_id,
            verdict="candidate_for_prototype_passed",
            checks_json='{"base_cost_present": true}',
            blocking_issues=(),
            warnings=(),
            strategy_config_hash=report.strategy_config_hash,
            data_snapshot_hash=report.data_snapshot_hash,
            gate_criteria_hash=gate_criteria_hash,
            oos_draw_index=report.oos_draw_index,
            shared_oos_window_id=report.shared_oos_window_id,
            multiple_comparison_flag=report.multiple_comparison_flag,
            generated_at=datetime.now(),
            gate_result_hash="candidate_gate_hash",
        )


class _CandidateExplanationBuilder:
    def build_explanation(self, report_id, gate_result):
        return ExplanationSnapshot(
            explanation_id="expl_candidate_001",
            report_id=report_id,
            gate_result_id=gate_result.gate_result_id,
            plain_summary="Candidate requires human confirmation.",
            deterministic_evidence=("base_cost_present",),
            generated_at=datetime.now(),
        )


class _FailingPromotionReducer:
    def promote_to_prototype_passed(self, **kwargs):
        raise ValueError("forced reducer failure")


if __name__ == "__main__":
    unittest.main()
