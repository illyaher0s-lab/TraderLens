"""
B6 Final Vertical Flow Tests

Tests the minimal B-module V1 vertical flow from StrategyDraft to C admission.
"""
import hashlib
import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, date
from pathlib import Path

from backend.services.b5_oos_types import B6ValidationRunResult
from backend.services.b6_validation_flow import B6ValidationFlow
from backend.services.oos_budget_ledger import OOSBudgetLedger
from contracts.strategy import (
    StrategyDraft,
    ResearchProtocolSnapshot,
    BacktestUniverseSpec,
    StrategyLifecycleState,
    ImmutableBacktestReport,
    PrototypeGateResultV2,
    SourceRuleMapping,
    StrategyTemplateDefinition,
)
from backend.services.b3_protocol_types import (
    DataSnapshotManifest,
    PointInTimeMembershipSnapshot,
    UniverseMembershipRecord,
)
from backend.services.b4_protocol_types import EventBacktestResult
from backend.services.b5_oos_types import ExplanationSnapshot
from backend.db.strategy import StrategyDB
from contracts.b6_task import B6ValidationTask
import tempfile
import uuid
from pathlib import Path
from backend.services.strategy_promotion_reducer import StrategyPromotionReducer


class TestB6ValidationFlow(unittest.TestCase):
    """B6 validation flow integration tests."""

    def setUp(self):
        """Inject approved test fixture into template library for this test only."""
        import backend.services.strategy_template_library as lib_module
        from backend.services.strategy_template_library import StrategyTemplate
        from datetime import date

        # ponytail: backup production state
        self._original_templates = lib_module._TEMPLATES
        self._original_get_template = lib_module.get_template_by_id if hasattr(lib_module, 'get_template_by_id') else None

        # Inject test fixture temporarily
        test_fixture = StrategyTemplate(
            template_id="template_001",
            version="v1",
            hypothesis_types=("test",),
            core_entry_rule_id="test_entry",
            supported_universe_rule_types=("point_in_time_membership",),
            sample_split_rule_ids=("split_001",),
            benchmark_rule_id="test_benchmark",
            strategy_config_payload={"test": True},
            forbidden_fields=(),
            forbidden_evidence_terms=(),
            market_fit="Test fixture",
            forbidden_market=(),
            entry_rules="Test",
            exit_rules="Test",
            risk_rules="Test",
            position_sizing_rules="Test",
            validation_gate_profile="standard",
        )

        lib_module._TEMPLATES = self._original_templates + (test_fixture,)
        lib_module.APPROVED_TEMPLATES = lib_module._TEMPLATES

        # Patch convert_to_frozen_contract to mark template_001 as approved
        self._original_convert = lib_module.convert_to_frozen_contract

        def patched_convert(template, created_at):
            frozen = self._original_convert(template, created_at)
            if template.template_id == "template_001":
                # ponytail: test-only approved fixture must satisfy the real contract.
                return StrategyTemplateDefinition.model_validate(
                    {
                        **frozen.model_dump(mode="json"),
                        "governance_status": "approved",
                        "source_citation": "test://source",
                        "source_retrieval_date": date(2026, 7, 1),
                        "source_rule_mappings": (
                            SourceRuleMapping(
                                source_claim_id="test-claim",
                                source_locator="test",
                                frozen_rule_id="test_entry",
                                mapping_kind="source_claim",
                                rationale="Test-only approved fixture.",
                            ),
                        ),
                        "market_scope_difference": "Test-only scope disclosure.",
                        "data_requirements_hash": "test-requirements-hash",
                        "governance_evidence_hash": "test-governance-hash",
                    "reviewer_id": "test-reviewer",
                    "reviewed_at": datetime(2026, 7, 1, 10, 0, 0),
                    "review_due_date": date(2027, 7, 1),
                    "review_evidence_path": "tests/fixture-review.md",
                    "review_evidence_sha256": "0" * 64,
                    "owner_authorization_hash": "1" * 64,
                    "authorized_by": "test-owner",
                    "authorized_at": datetime(2026, 7, 1, 11, 0, 0),
                }
            )
            return frozen
        lib_module.convert_to_frozen_contract = patched_convert
    
    def _create_running_b6_task(self, db, draft, protocol):
        """ponytail: helper, call after draft+protocol persist"""
        from contracts.b6_task import B6ValidationTask
        db.create_b6_task(B6ValidationTask(
            task_id="test_task_001", task_key="key_001", task_type="b6_validation",
            strategy_revision_id=draft.strategy_revision_id,
            protocol_snapshot_id=protocol.protocol_snapshot_id,
            status="running", created_at=datetime.now()
        ))
        return db.get_b6_task_by_id("test_task_001")
    
    def tearDown(self):
        """Restore production templates."""
        import backend.services.strategy_template_library as lib_module
        # ponytail: restore exact original objects, not new wrappers
        lib_module._TEMPLATES = self._original_templates
        lib_module.APPROVED_TEMPLATES = self._original_templates
        lib_module.get_template_by_id = self._original_get_template
        lib_module.convert_to_frozen_contract = self._original_convert

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
        db = StrategyDB(":memory:")
        ledger = OOSBudgetLedger(db)
        flow = B6ValidationFlow(oos_budget_ledger=ledger, strategy_db=db)

        with self.assertRaises(ValueError) as ctx:
            flow.run_minimal_validation(
                strategy_draft=None,
                protocol=None,
                manifest=None,
                universe=None,
                b4_qualification=None,
                b4_event_result=None,
                task_id="test_task_001",
            )

        self.assertIn("StrategyDraft is required", str(ctx.exception))
        db.close()

    def test_b6_flow_rejects_missing_b4_formal_qualification(self):
        """B6 flow rejects missing B4 formal qualification."""
        db = StrategyDB(":memory:")
        ledger = OOSBudgetLedger(db)
        flow = B6ValidationFlow(oos_budget_ledger=ledger, strategy_db=db)

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
                task_id="test_task_001",
            )

        self.assertIn("required", str(ctx.exception).lower())
        db.close()

    def test_b6_flow_rejects_user_supplied_technical_parameters(self):
        """B6 flow rejects user-supplied technical parameters."""
        db = StrategyDB(":memory:")
        ledger = OOSBudgetLedger(db)
        flow = B6ValidationFlow(oos_budget_ledger=ledger, strategy_db=db)

        with self.assertRaises(ValueError) as ctx:
            flow.run_minimal_validation(
                strategy_draft=None,
                protocol=None,
                manifest=None,
                universe=None,
                b4_qualification=None,
                b4_event_result=None,
                task_id="test_task_001",
                user_gate_thresholds={"min_sharpe": 0.1},
            )

        self.assertIn("user-supplied technical parameters", str(ctx.exception).lower())
        db.close()

    def test_b6_flow_stops_on_failed_b4_qualification(self):
        """B6 flow stops on failed B4 qualification."""
        db = StrategyDB(":memory:")
        ledger = OOSBudgetLedger(db)
        flow = B6ValidationFlow(oos_budget_ledger=ledger, strategy_db=db)

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
                task_id="test_task_001",
            )

        self.assertIn("qualification failed", str(ctx.exception).lower())
        db.close()

    def test_b6_flow_stops_on_b4_metadata_mismatch(self):
        """B6 flow stops on B4 metadata mismatch."""
        db = StrategyDB(":memory:")
        ledger = OOSBudgetLedger(db)
        flow = B6ValidationFlow(oos_budget_ledger=ledger, strategy_db=db)

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
                task_id="test_task_001",
            )

        self.assertIn("mismatch", str(ctx.exception).lower())
        db.close()

    def test_b6_flow_produces_report_gate_and_explanation(self):
        """B6 validation produces immutable report, Gate result, and explanation."""
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        db_path = Path(temp_dir.name) / "test_b6_flow.db"
        db = StrategyDB(str(db_path))
        self.addCleanup(db.close)
        ledger = OOSBudgetLedger(db)
        
        # Setup: draft + universe + protocol
        strategy_draft = self._create_strategy_draft()
        protocol = self._create_protocol()
        db.store_backtest_universe(self._create_universe_spec())
        db.create_strategy_draft(
            strategy_draft,
            StrategyLifecycleState(
                lifecycle_state_id="state_flow_001",
                strategy_revision_id=strategy_draft.strategy_revision_id,
                state_version=1,
                state="draft",
                source_record_id="initial",
                recorded_at=datetime.now(),
                recorded_by="test",
            ),
        )
        db.store_protocol_snapshot(protocol)
        task = self._create_running_b6_task(db, strategy_draft, protocol)
        
        flow = B6ValidationFlow(
            oos_budget_ledger=ledger,
            report_builder=_CandidateReportBuilder(task),
            gate=_CandidateGate(),
            explanation_builder=_CandidateExplanationBuilder(),
            strategy_db=db,
        )

        result = flow.run_minimal_validation(
            strategy_draft=strategy_draft,
            protocol=protocol,
            manifest=self._create_manifest(),
            universe=self._create_universe(),
            b4_qualification=self._create_b4_qualification_dict(),
            b4_event_result=self._create_b4_event_result(),
            task_id=task.task_id,
        )

        self.assertEqual(result.status, "completed")
        self.assertIsNotNone(result.report_id)
        self.assertIsNotNone(result.gate_result_id)
        self.assertIsNotNone(result.explanation_id)
        self.assertIn(
            result.final_state,
            ["rejected", "needs_review", "candidate_for_prototype_passed"],
        )
        state = ledger.get_ledger_state("theme_001", "hypo_snap_001")
        self.assertEqual(state["completed_draw_count"], 1)
        self.assertIsNone(state["active_reservation_id"])
        
        # Verify durable (separate connection)
        verify_conn = sqlite3.connect(str(db_path))
        verify_conn.row_factory = sqlite3.Row
        report_row = verify_conn.execute("SELECT report_id FROM immutable_backtest_reports WHERE report_id = ?", (result.report_id,)).fetchone()
        self.assertIsNotNone(report_row)
        verify_conn.close()

    def test_b6_flow_candidate_without_human_approval_is_not_prototype_passed(self):
        """Candidate verdict doesn't become prototype_passed without human confirmation."""
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        db_path = Path(temp_dir.name) / "test_b6_candidate.db"
        db = StrategyDB(str(db_path))
        self.addCleanup(db.close)
        ledger = OOSBudgetLedger(db)
        
        strategy_draft = self._create_strategy_draft()
        protocol = self._create_protocol()
        db.store_backtest_universe(self._create_universe_spec())
        db.create_strategy_draft(
            strategy_draft,
            StrategyLifecycleState(
                lifecycle_state_id="state_no_promo_001",
                strategy_revision_id=strategy_draft.strategy_revision_id,
                state_version=1,
                state="draft",
                source_record_id="initial",
                recorded_at=datetime.now(),
                recorded_by="test",
            ),
        )
        db.store_protocol_snapshot(protocol)
        task = self._create_running_b6_task(db, strategy_draft, protocol)
        
        flow = B6ValidationFlow(
            oos_budget_ledger=ledger,
            report_builder=_CandidateReportBuilder(task),
            gate=_CandidateGate(),
            explanation_builder=_CandidateExplanationBuilder(),
            strategy_db=db,
        )

        result = flow.run_minimal_validation(
            strategy_draft=strategy_draft,
            protocol=protocol,
            manifest=self._create_manifest(),
            universe=self._create_universe(),
            b4_qualification=self._create_b4_qualification_dict(),
            b4_event_result=self._create_b4_event_result(),
            task_id=task.task_id,
        )

        self.assertEqual(result.status, "completed")
        self.assertIsNone(result.promotion_id)
    
    def test_b6_flow_reducer_not_called(self):
        """B6 does NOT call reducer directly (deferred to application service)."""
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        db_path = Path(temp_dir.name) / "test_b6_reducer.db"
        db = StrategyDB(str(db_path))
        self.addCleanup(db.close)
        ledger = OOSBudgetLedger(db)
        strategy_draft = self._create_strategy_draft()
        protocol = self._create_protocol()
        db.store_backtest_universe(self._create_universe_spec())
        db.create_strategy_draft(
            strategy_draft,
            StrategyLifecycleState(
                lifecycle_state_id="state_reducer_001",
                strategy_revision_id=strategy_draft.strategy_revision_id,
                state_version=1,
                state="draft",
                source_record_id="initial",
                recorded_at=datetime.now(),
                recorded_by="test",
            ),
        )
        db.store_protocol_snapshot(protocol)
        task = self._create_running_b6_task(db, strategy_draft, protocol)
        
        flow = B6ValidationFlow(
            oos_budget_ledger=ledger,
            report_builder=_CandidateReportBuilder(task),
            gate=_CandidateGate(),
            explanation_builder=_CandidateExplanationBuilder(),
            strategy_db=db,
            promotion_reducer=_FailingPromotionReducer(),
        )

        result = flow.run_minimal_validation(
            strategy_draft=strategy_draft,
            protocol=protocol,
            manifest=self._create_manifest(),
            universe=self._create_universe(),
            b4_qualification=self._create_b4_qualification_dict(),
            b4_event_result=self._create_b4_event_result(),
            task_id=task.task_id,
        )

        self.assertEqual(result.status, "completed")
        self.assertIsNone(result.promotion_id)

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
            data_snapshot_id="data_snap_001",
            kill_criteria_snapshot_id="kill_001",
            prototype_gate_thresholds_json="{}",
            strategy_config_hash="hash_config_001",
            data_snapshot_hash="hash_001",
            gate_criteria_hash="hash_gate_001",
            frozen_at=datetime.now(),
            frozen_by="test",
        )

    def _create_manifest(self) -> DataSnapshotManifest:
        return DataSnapshotManifest(
            snapshot_id="data_snap_001",
            provider="mock",
            retrieval_date=date(2026, 1, 1),
            market_data_start=date(2020, 1, 1),
            market_data_end=date(2023, 12, 31),
            universe_snapshot_ids=("u_snap_001",),
            semantic_hash="hash_001",
            quality_status="ok",
            gaps=(),
        )

    def _create_universe(self) -> PointInTimeMembershipSnapshot:
        return PointInTimeMembershipSnapshot(
            snapshot_id="u_snap_001",
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
                    snapshot_id="u_snap_001",
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
            "data_snapshot_hash": "hash_001",
            "data_snapshot_id": "data_snap_001",
            "universe_type": "point_in_time",
            "universe_snapshot_id": "u_snap_001",
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
    def __init__(self, task):
        self.task = task

    def build_report(self, **kwargs):
        payload = {
            "future_data_violation_count": 0,
            "base_cost_result": {"status": "pass"},
            "stress_cost_result": {"status": "pass"},
            "benchmark_comparison": {"status": "pass"},
            "control_comparison": {"status": "pass"},
            "data_quality_status": "ok",
            "task_id": self.task.task_id,
            "task_key": self.task.task_key,
            "protocol_snapshot_id": kwargs["protocol_snapshot_id"],
            "b5_bundle_id": self.task.b5_bundle_id,
            "b5_bundle_manifest_sha256": self.task.b5_bundle_manifest_sha256,
            "same_draw_result": {
                "identity": {
                    "task_id": self.task.task_id,
                    "task_key": self.task.task_key,
                    "strategy_revision_id": self.task.strategy_revision_id,
                    "protocol_snapshot_id": self.task.protocol_snapshot_id,
                    "b5_bundle_id": self.task.b5_bundle_id,
                    "b5_bundle_manifest_sha256": self.task.b5_bundle_manifest_sha256,
                    "shared_oos_window_id": kwargs["shared_oos_window_id"],
                    "data_snapshot_hash": kwargs["data_snapshot_hash"],
                },
            },
        }
        payload_json = json.dumps(payload, sort_keys=True)
        report_hash = hashlib.sha256(
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
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
            report_payload_json=payload_json,
            integrity_status="valid",
            generated_at=datetime.now(),
            report_hash=report_hash,
        )


class _CandidateGate:
    def evaluate(self, report, gate_criteria_hash) -> PrototypeGateResultV2:
        checks = {"base_cost_present": True}
        checks_json = json.dumps(checks, sort_keys=True)
        gate_result_hash = hashlib.sha256(
            json.dumps(
                {
                    "report_id": report.report_id,
                    "verdict": "candidate_for_prototype_passed",
                    "checks": checks,
                },
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        return PrototypeGateResultV2(
            gate_result_id="gate_candidate_001",
            report_id=report.report_id,
            strategy_revision_id=report.strategy_revision_id,
            protocol_snapshot_id=report.protocol_snapshot_id,
            verdict="candidate_for_prototype_passed",
            checks_json=checks_json,
            strategy_config_hash=report.strategy_config_hash,
            data_snapshot_hash=report.data_snapshot_hash,
            gate_criteria_hash=gate_criteria_hash,
            oos_draw_index=report.oos_draw_index,
            shared_oos_window_id=report.shared_oos_window_id,
            multiple_comparison_flag=report.multiple_comparison_flag,
            generated_at=datetime.now(),
            gate_result_hash=gate_result_hash,
        )


class _CandidateExplanationBuilder:
    def build_explanation(self, report_id, gate_result) -> ExplanationSnapshot:
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
