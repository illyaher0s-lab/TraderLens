"""B6 OOS Ledger Boundary Tests - Mock-only, no real OOS."""
import tempfile
import unittest
import hashlib
import json
from datetime import datetime, date
from pathlib import Path

from backend.services.b6_validation_flow import B6ValidationFlow
from backend.services.oos_budget_ledger import OOSBudgetLedger
from backend.db.strategy import StrategyDB
from contracts.strategy import StrategyDraft, ResearchProtocolSnapshot, BacktestUniverseSpec, StrategyLifecycleState
from contracts.b6_task import B6ValidationTask, build_b6_task_id, build_b6_task_key
from backend.services.b3_protocol_types import DataSnapshotManifest, PointInTimeMembershipSnapshot, UniverseMembershipRecord
from backend.services.b4_protocol_types import EventBacktestResult, DailyPortfolioSnapshot


TEST_B5_BUNDLE_ID = "bundle_boundary_synthetic"
TEST_B5_BUNDLE_SHA = "b" * 64
TEST_TASK_KEY = build_b6_task_key(
    strategy_revision_id="rev_001",
    protocol_snapshot_id="proto_001",
    task_contract_version="v2",
    b5_bundle_id=TEST_B5_BUNDLE_ID,
    b5_bundle_manifest_sha256=TEST_B5_BUNDLE_SHA,
)
TEST_TASK_ID = build_b6_task_id(TEST_TASK_KEY)


class MockReportBuilder:
    """Mock that tracks calls."""
    def __init__(
        self,
        call_sequence=None,
        *,
        task_id=TEST_TASK_ID,
        task_key=TEST_TASK_KEY,
    ):
        self.call_count = 0
        self.last_oos_draw_index = None
        self.call_sequence = call_sequence
        self.task_id = task_id
        self.task_key = task_key
    
    def build_report(self, **kwargs):
        self.call_count += 1
        self.last_oos_draw_index = kwargs.get("oos_draw_index")
        if self.call_sequence is not None:
            self.call_sequence.append("report")
        from backend.services.backtest_report_builder import BacktestReportBuilder
        from backend.services.b5_oos_types import (
            B6SameDrawOOSResult,
            BaseCostResult,
            SameDrawExecutionIdentity,
            StressCostResult,
        )

        b4_result = kwargs["b4_result"]
        same_draw_result = B6SameDrawOOSResult(
            identity=SameDrawExecutionIdentity(
                task_id=self.task_id,
                task_key=self.task_key,
                strategy_revision_id=kwargs["strategy_revision_id"],
                protocol_snapshot_id=kwargs["protocol_snapshot_id"],
                b5_bundle_id=TEST_B5_BUNDLE_ID,
                b5_bundle_manifest_sha256=TEST_B5_BUNDLE_SHA,
                b4_artifact_id=b4_result.result_id,
                b4_manifest_sha256="c" * 64,
                b4_event_result_sha256="d" * 64,
                formal_snapshot_id="formal_boundary_synthetic",
                formal_snapshot_manifest_sha256="e" * 64,
                membership_snapshot_id="membership_boundary_synthetic",
                membership_manifest_sha256="f" * 64,
                calendar_id="calendar_boundary_synthetic",
                calendar_manifest_sha256="1" * 64,
                data_snapshot_hash=kwargs["data_snapshot_hash"],
                execution_input_hash="3" * 64,
                shared_oos_window_id=kwargs["shared_oos_window_id"],
                oos_start=b4_result.backtest_start,
                oos_end=b4_result.backtest_end,
                result_schema_version="b6_same_draw_oos_result.v1",
            ),
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
                result_id="base_cost_boundary_synthetic",
                slippage_bps=1.0,
                commission_bps=2.0,
                impact_bps=1.0,
                total_cost_bps=4.0,
                assumptions_hash="4" * 64,
            ),
            stress_cost_result=StressCostResult(
                result_id="stress_cost_boundary_synthetic",
                slippage_bps=2.0,
                commission_bps=3.0,
                impact_bps=2.0,
                total_cost_bps=7.0,
                stress_multiplier=2.0,
                assumptions_hash="5" * 64,
            ),
        )
        builder_kwargs = dict(kwargs)
        builder_kwargs["adjustment_snapshot_fingerprint"] = (
            kwargs.get("adjustment_snapshot_fingerprint")
            or "adjustment_boundary_synthetic"
        )
        builder_kwargs["same_draw_result"] = same_draw_result
        return BacktestReportBuilder().build_report(**builder_kwargs)


class MockGate:
    def __init__(self, call_sequence=None):
        self.call_count = 0
        self.call_sequence = call_sequence
    
    def evaluate(self, report, gate_criteria_hash):
        self.call_count += 1
        if self.call_sequence is not None:
            self.call_sequence.append("gate")
        from contracts.strategy import PrototypeGateResultV2
        checks_json = "[]"
        gate_result_hash = hashlib.sha256(
            json.dumps(
                {"report_id": report.report_id, "verdict": "rejected", "checks": []},
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        return PrototypeGateResultV2(
            gate_result_id=f"gate_{report.report_id}",
            report_id=report.report_id,
            strategy_revision_id=report.strategy_revision_id,
            protocol_snapshot_id=report.protocol_snapshot_id,
            verdict="rejected",
            checks_json=checks_json,
            strategy_config_hash=report.strategy_config_hash,
            data_snapshot_hash=report.data_snapshot_hash,
            gate_criteria_hash=gate_criteria_hash,
            oos_draw_index=report.oos_draw_index,
            shared_oos_window_id=report.shared_oos_window_id,
            generated_at=datetime(2026, 1, 1),
            gate_result_hash=gate_result_hash,
        )


class MockExplanationBuilder:
    def __init__(self, call_sequence=None):
        self.call_count = 0
        self.call_sequence = call_sequence
    
    def build_explanation(self, report_id, gate_result):
        self.call_count += 1
        if self.call_sequence is not None:
            self.call_sequence.append("explanation")
        from backend.services.b5_oos_types import ExplanationSnapshot
        return ExplanationSnapshot(
            explanation_id=f"expl_{report_id}",
            report_id=report_id,
            gate_result_id=gate_result.gate_result_id,
            plain_summary="Mock explanation",
            deterministic_evidence=(),
            generated_at=datetime.now(),
        )


class MockOOSController:
    def __init__(self, call_sequence=None):
        self.call_sequence = call_sequence

    def validate_b3_b4_prerequisites(self, **kwargs):
        if self.call_sequence is not None:
            self.call_sequence.append("prerequisites")


class RecordingLedger:
    """Fake ledger that records method calls."""
    def __init__(self, real_ledger, call_sequence):
        self.real_ledger = real_ledger
        self.call_sequence = call_sequence
        self.reserve_calls = 0
        self.start_calls = 0
        self.release_calls = 0
        self.fail_calls = 0
        self.terminal_calls = 0
    
    def reserve_oos_draw(self, *args, **kwargs):
        self.reserve_calls += 1
        self.call_sequence.append("reserve")
        return self.real_ledger.reserve_oos_draw(*args, **kwargs)
    
    def start_execution(self, *args, **kwargs):
        self.start_calls += 1
        self.call_sequence.append("start")
        return self.real_ledger.start_execution(*args, **kwargs)

    def release_pre_execution(self, *args, **kwargs):
        self.release_calls += 1
        self.call_sequence.append("release")
        return self.real_ledger.release_pre_execution(*args, **kwargs)

    def fail_after_start(self, *args, **kwargs):
        self.fail_calls += 1
        self.call_sequence.append("fail_after_start")
        return self.real_ledger.fail_after_start(*args, **kwargs)

    def fail_reservation_within_tx(self, *args, **kwargs):
        self.fail_calls += 1
        self.call_sequence.append("fail_after_start")
        return self.real_ledger.fail_reservation_within_tx(*args, **kwargs)
    
    def complete_reservation(self, *args, **kwargs):
        self.call_sequence.append("complete")
        return self.real_ledger.complete_reservation(*args, **kwargs)
    
    def complete_reservation_within_tx(self, *args, **kwargs):
        self.terminal_calls += 1
        self.call_sequence.append("complete")
        return self.real_ledger.complete_reservation_within_tx(*args, **kwargs)

    def get_terminal_metadata(self, *args, **kwargs):
        return self.real_ledger.get_terminal_metadata(*args, **kwargs)
    
    def get_ledger_state(self, *args, **kwargs):
        return self.real_ledger.get_ledger_state(*args, **kwargs)


class TestB6LedgerBoundary(unittest.TestCase):
    def setUp(self):
        self.tmpfile = tempfile.NamedTemporaryFile(mode='w', suffix='.db', delete=False)
        self.tmpfile.close()
        self.db_path = Path(self.tmpfile.name)
        self.db = StrategyDB(str(self.db_path))
        self.ledger = OOSBudgetLedger(self.db)
        
        # Inject approved template fixture for tpl_001 (test-only, isolated)
        from backend.services import strategy_template_library
        from backend.services.strategy_template_library import StrategyTemplate
        from contracts.strategy import StrategyTemplateDefinition, SourceRuleMapping
        
        self.test_template = StrategyTemplate(
            template_id="tpl_001",
            version="v1",
            hypothesis_types=("test",),
            core_entry_rule_id="test_entry",
            supported_universe_rule_types=("point_in_time_membership",),
            sample_split_rule_ids=("fixed_ratio_70_30",),
            benchmark_rule_id="equal_weight",
            strategy_config_payload={},
            forbidden_fields=(),
            forbidden_evidence_terms=(),
            default_cost_model="base",
            default_fill_model="market_open",
            default_risk_rules={},
            market_fit="Test only",
            forbidden_market=(),
            entry_rules="Test entry",
            exit_rules="Test exit",
            risk_rules="Test risk",
            position_sizing_rules="Test sizing",
            validation_gate_profile="standard",
        )
        
        # Patch convert_to_frozen_contract to return approved template for tpl_001
        self._original_convert = strategy_template_library.convert_to_frozen_contract
        self._original_get_template = strategy_template_library.get_template_by_id
        
        def patched_convert(template, created_at):
            if template.template_id == "tpl_001":
                # Test fixture with complete approved governance
                return StrategyTemplateDefinition(
                    template_id=template.template_id,
                    version=template.version,
                    template_hash=template.frozen_template_hash,
                    hypothesis_types=template.hypothesis_types,
                    core_entry_rule_id=template.core_entry_rule_id,
                    supported_universe_rule_types=template.supported_universe_rule_types,
                    sample_split_rule_ids=template.sample_split_rule_ids,
                    benchmark_rule_id=template.benchmark_rule_id,
                    created_at=created_at,
                    governance_status="approved",
                    source_citation="test://source",
                    source_retrieval_date=date(2026, 7, 1),
                    source_rule_mappings=(
                        SourceRuleMapping(
                            source_claim_id="test-claim",
                            source_locator="test",
                            frozen_rule_id="test_entry",
                            mapping_kind="source_claim",
                            rationale="Test-only approved fixture.",
                        ),
                    ),
                    market_scope_difference="Test-only scope disclosure.",
                    data_requirements_hash="test-requirements-hash",
                    governance_evidence_hash="test-governance-hash",
                    reviewer_id="test-reviewer",
                    reviewed_at=datetime(2026, 7, 1, 10, 0, 0),
                    review_due_date=date(2027, 7, 1),
                    review_evidence_path="tests/fixture-review.md",
                    review_evidence_sha256="0" * 64,
                    owner_authorization_hash="1" * 64,
                    authorized_by="test-owner",
                    authorized_at=datetime(2026, 7, 1, 11, 0, 0),
                )
            return self._original_convert(template, created_at)
        
        strategy_template_library.convert_to_frozen_contract = patched_convert
        strategy_template_library.get_template_by_id = lambda tid: self.test_template if tid == "tpl_001" else None
        
        # Define entities first
        self.strategy_draft = StrategyDraft(
            strategy_revision_id="rev_001",
            theme_id="theme_boundary",
            hypothesis_id="hypo_001",
            strategy_template_id="tpl_001",
            strategy_template_version="v1",
            strategy_template_hash="tplhash_001",
            hypothesis_source_snapshot_id="hypo_001",
            backtest_universe_spec_id="u001",
            strategy_config_json="{}",
            sample_split_rule_id="split_001",
            created_at=datetime.now(),
        )
        
        self.protocol = ResearchProtocolSnapshot(
            protocol_snapshot_id="proto_001",
            theme_id="theme_boundary",
            hypothesis_source_snapshot_id="hypo_001",
            strategy_revision_id="rev_001",
            sample_split_rule_id="split_001",
            oos_window_rule_id="window_001",
            oos_window_rule_params_json="{}",
            oos_window_start=date(2024, 1, 1),
            oos_window_end=date(2024, 12, 31),
            shared_oos_window_id="window_001",
            backtest_universe_spec_id="u001",
            strategy_config_hash="confighash_001",
            data_snapshot_id="data_snap_001",
            data_snapshot_hash="2" * 64,
            kill_criteria_snapshot_id="kill_001",
            prototype_gate_thresholds_json="{}",
            gate_criteria_hash="gatehash_001",
            frozen_at=datetime.now(),
            frozen_by="test",
        )
        
        # Create them in DB for terminal TX to reference
        universe = BacktestUniverseSpec(
            universe_spec_id="u001",
            universe_rule_type="point_in_time_membership",
            membership_source="test",
            membership_effective_from=date(2020, 1, 1),
            membership_effective_to=date(2025, 1, 1),
            snapshot_date=date(2025, 1, 1),
            membership_snapshot_ids=("snap_001",),
            quality_status="ok",
        )
        self.db.store_backtest_universe(universe)
        
        initial_state = StrategyLifecycleState(
            lifecycle_state_id="state_001",
            strategy_revision_id="rev_001",
            state_version=1,
            state="draft",
            source_record_id="initial",
            recorded_at=datetime.now(),
            recorded_by="test",
        )
        self.db.create_strategy_draft(self.strategy_draft, initial_state)
        self.db.store_protocol_snapshot(self.protocol)
        
        # Current v2 admission fixture: queued create-or-get followed by a
        # real conditional claim, so terminal tests exercise the running row.
        self.task_key = TEST_TASK_KEY
        self.task_id = TEST_TASK_ID
        winner, created = self.db.create_or_get_b6_task(B6ValidationTask(
            task_id=self.task_id,
            task_key=self.task_key,
            task_type="b6_validation",
            task_contract_version="v2",
            strategy_revision_id="rev_001",
            protocol_snapshot_id="proto_001",
            status="queued",
            b5_bundle_id=TEST_B5_BUNDLE_ID,
            b5_bundle_manifest_sha256=TEST_B5_BUNDLE_SHA,
            created_at=datetime.now(),
        ))
        assert created is True
        assert winner.task_id == self.task_id
        assert self.db.claim_b6_task(self.task_id) is not None
        self.manifest = DataSnapshotManifest(
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
        
        self.universe = PointInTimeMembershipSnapshot(
            snapshot_id="u_snap_001",
            snapshot_date=date(2023, 1, 1),
            universe_rule_type="point_in_time_membership",
            membership_source="mock",
            include_delisted=True,
            records=(),
            quality_status="ok",
            gaps=(),
        )
        
        self.b4_qualification = {"status": "pass"}
        self.b4_event_result = EventBacktestResult(
            result_id="b4_001",
            strategy_revision_id="rev_001",
            protocol_snapshot_id="proto_001",
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
    
    def tearDown(self):
        # Restore original template library functions
        from backend.services import strategy_template_library
        strategy_template_library.convert_to_frozen_contract = self._original_convert
        strategy_template_library.get_template_by_id = self._original_get_template
        
        self.db.close()
        try:
            self.db_path.unlink()
        except:
            pass
    
    def test_no_ledger_blocks_report(self):
        """No ledger: report builder never called."""
        mock_report = MockReportBuilder()
        flow = B6ValidationFlow(
            strategy_db=self.db,
            oos_controller=MockOOSController(),
            report_builder=mock_report,
            gate=MockGate(),
            explanation_builder=MockExplanationBuilder(),
            oos_budget_ledger=None,  # No ledger
        )
        
        result = flow.run_minimal_validation(
            strategy_draft=self.strategy_draft,
            protocol=self.protocol,
            manifest=self.manifest,
            universe=self.universe,
            b4_qualification=self.b4_qualification,
            b4_event_result=self.b4_event_result,
            task_id=self.task_id,
            )
        
        assert result.status == "blocked"
        assert result.final_state == "draft"
        assert "ledger" in result.blocking_reason.lower()
        assert mock_report.call_count == 0
    
    def test_budget_exhausted_blocks_report(self):
        """Exhausted budget: report builder never called."""
        # Exhaust budget
        for i in range(3):
            rsv = self.ledger.reserve_oos_draw(
                "theme_boundary", "hypo_001", f"config_{i}", "data", "gate", "window",
                idempotency_key=f"k{i}"
            )
            self.ledger.start_execution(rsv.reservation_id)
            self.ledger.complete_reservation(rsv.reservation_id, "rejected", report_id=f"rpt_{i}")
        
        mock_report = MockReportBuilder()
        flow = B6ValidationFlow(
            strategy_db=self.db,
            oos_controller=MockOOSController(),
            report_builder=mock_report,
            gate=MockGate(),
            explanation_builder=MockExplanationBuilder(),
            oos_budget_ledger=self.ledger,
        )
        
        result = flow.run_minimal_validation(
            strategy_draft=self.strategy_draft,
            protocol=self.protocol,
            manifest=self.manifest,
            universe=self.universe,
            b4_qualification=self.b4_qualification,
            b4_event_result=self.b4_event_result,
            task_id=self.task_id,
            )
        assert result.final_state == "draft"
        assert result.status == "blocked"
        assert "unavailable" in result.blocking_reason.lower() or "exhausted" in result.blocking_reason.lower()
        assert mock_report.call_count == 0
    
    def test_happy_path_calls_in_order(self):
        """Normal flow: reserve → start → report(draw_index) → gate → explanation → complete."""
        call_sequence = []
        mock_report = MockReportBuilder(call_sequence)
        mock_gate = MockGate(call_sequence)
        mock_explanation = MockExplanationBuilder(call_sequence)
        
        flow = B6ValidationFlow(
            strategy_db=self.db,
            oos_controller=MockOOSController(call_sequence),
            report_builder=mock_report,
            gate=mock_gate,
            explanation_builder=mock_explanation,
            oos_budget_ledger=RecordingLedger(self.ledger, call_sequence),
        )
        
        result = flow.run_minimal_validation(
            strategy_draft=self.strategy_draft,
            protocol=self.protocol,
            manifest=self.manifest,
            universe=self.universe,
            b4_qualification=self.b4_qualification,
            b4_event_result=self.b4_event_result,
            task_id=self.task_id,
            )
        
        assert result.status == "completed"
        assert mock_report.call_count == 1
        assert mock_report.last_oos_draw_index == 1  # First draw
        assert mock_gate.call_count == 1
        assert mock_explanation.call_count == 1
        # ponytail: terminal TX calls complete_reservation_within_tx, still logs "complete"
        assert call_sequence == [
            "prerequisites", "reserve", "start", "report", "gate", "explanation", "complete",
        ]
        
        # Verify reservation completed (via terminal TX)
        state = self.ledger.get_ledger_state("theme_boundary", "hypo_001")
        assert state["completed_draw_count"] == 1
    
    def test_report_builder_exception_consumes_budget_once(self):
        """Report builder fails: reservation failed, budget consumed once."""
        class FailingReportBuilder:
            def __init__(self):
                self.call_count = 0
            
            def build_report(self, **kwargs):
                self.call_count += 1
                raise RuntimeError("Mock report failure")
        
        failing_report = FailingReportBuilder()
        flow = B6ValidationFlow(
            strategy_db=self.db,
            oos_controller=MockOOSController(),
            report_builder=failing_report,
            gate=MockGate(),
            explanation_builder=MockExplanationBuilder(),
            oos_budget_ledger=self.ledger,
        )
        
        with self.assertRaises(RuntimeError):
            flow.run_minimal_validation(
                strategy_draft=self.strategy_draft,
                protocol=self.protocol,
                manifest=self.manifest,
                universe=self.universe,
                b4_qualification=self.b4_qualification,
                b4_event_result=self.b4_event_result,
                task_id=self.task_id,
                )
        
        assert failing_report.call_count == 1
        state = self.ledger.get_ledger_state("theme_boundary", "hypo_001")
        assert state["completed_draw_count"] == 1  # Consumed
    
    def test_gate_exception_consumes_budget_once(self):
        """Gate fails: budget consumed once."""
        class FailingGate:
            def __init__(self):
                self.call_count = 0
            
            def evaluate(self, report, gate_criteria_hash):
                self.call_count += 1
                raise RuntimeError("Mock gate failure")
        
        failing_gate = FailingGate()
        flow = B6ValidationFlow(
            strategy_db=self.db,
            oos_controller=MockOOSController(),
            report_builder=MockReportBuilder(),
            gate=failing_gate,
            explanation_builder=MockExplanationBuilder(),
            oos_budget_ledger=self.ledger,
        )
        
        with self.assertRaises(RuntimeError):
            flow.run_minimal_validation(
                strategy_draft=self.strategy_draft,
                protocol=self.protocol,
                manifest=self.manifest,
                universe=self.universe,
                b4_qualification=self.b4_qualification,
                b4_event_result=self.b4_event_result,
                task_id=self.task_id,
                )
        
        assert failing_gate.call_count == 1
        state = self.ledger.get_ledger_state("theme_boundary", "hypo_001")
        assert state["completed_draw_count"] == 1
    
    def test_idempotent_retry_skips_report(self):
        """Completed task: second call blocked by precheck, report not called again."""
        mock_report = MockReportBuilder()
        flow = B6ValidationFlow(
            strategy_db=self.db,
            oos_controller=MockOOSController(),
            report_builder=mock_report,
            gate=MockGate(),
            explanation_builder=MockExplanationBuilder(),
            oos_budget_ledger=self.ledger,
        )
        
        # First run
        result1 = flow.run_minimal_validation(
            strategy_draft=self.strategy_draft,
            protocol=self.protocol,
            manifest=self.manifest,
            universe=self.universe,
            b4_qualification=self.b4_qualification,
            b4_event_result=self.b4_event_result,
            task_id=self.task_id,
            )
        assert result1.status == "completed"
        assert mock_report.call_count == 1
        
        # Retry same task_id → precheck blocks terminal task
        mock_report.call_count = 0
        result2 = flow.run_minimal_validation(
            strategy_draft=self.strategy_draft,
            protocol=self.protocol,
            manifest=self.manifest,
            universe=self.universe,
            b4_qualification=self.b4_qualification,
            b4_event_result=self.b4_event_result,
            task_id=self.task_id,
            )
        
        assert result2.status == "blocked"
        assert "status" in result2.blocking_reason.lower()  # task not running
        assert mock_report.call_count == 0  # Not called

    def test_failed_terminal_replay_returns_failed_draft_without_report(self):
        """A consumed failed draw replays its persisted failure without rerunning B6."""
        reservation = self.ledger.reserve_oos_draw(
            "theme_boundary", "hypo_001", "confighash_001", "2" * 64,
            "gatehash_001", "window_001", idempotency_key=self.task_key,
            task_key=self.task_key, protocol_snapshot_id="proto_001",
        )
        self.ledger.start_execution(reservation.reservation_id)
        self.ledger.fail_after_start(reservation.reservation_id, "report_build_failed: test")
        mock_report = MockReportBuilder()
        flow = B6ValidationFlow(
            strategy_db=self.db,
            oos_controller=MockOOSController(),
            report_builder=mock_report,
            gate=MockGate(),
            explanation_builder=MockExplanationBuilder(),
            oos_budget_ledger=self.ledger,
        )

        result = flow.run_minimal_validation(
            strategy_draft=self.strategy_draft,
            protocol=self.protocol,
            manifest=self.manifest,
            universe=self.universe,
            b4_qualification=self.b4_qualification,
            b4_event_result=self.b4_event_result,
            task_id=self.task_id,
            )

        assert result.final_state == "draft"
        assert result.status == "failed"
        assert result.report_id is None
        assert result.blocking_reason == "report_build_failed: test"
        assert mock_report.call_count == 0

    def test_released_terminal_replay_returns_blocked_draft_without_report(self):
        """A pre-execution release replays as blocked without rerunning B6."""
        reservation = self.ledger.reserve_oos_draw(
            "theme_boundary", "hypo_001", "confighash_001", "2" * 64,
            "gatehash_001", "window_001", idempotency_key=self.task_key,
            task_key=self.task_key, protocol_snapshot_id="proto_001",
        )
        self.ledger.release_pre_execution(reservation.reservation_id, "start_failed: test")
        mock_report = MockReportBuilder()
        flow = B6ValidationFlow(
            strategy_db=self.db,
            oos_controller=MockOOSController(),
            report_builder=mock_report,
            gate=MockGate(),
            explanation_builder=MockExplanationBuilder(),
            oos_budget_ledger=self.ledger,
        )

        result = flow.run_minimal_validation(
            strategy_draft=self.strategy_draft,
            protocol=self.protocol,
            manifest=self.manifest,
            universe=self.universe,
            b4_qualification=self.b4_qualification,
            b4_event_result=self.b4_event_result,
            task_id=self.task_id,
            )

        assert result.final_state == "draft"
        assert result.status == "blocked"
        assert result.report_id is None
        assert result.blocking_reason == "start_failed: test"
        assert mock_report.call_count == 0

    def test_completed_terminal_replay_rejects_invalid_persisted_verdict(self):
        """Corrupt completed metadata must fail loudly instead of inventing a lifecycle state."""
        reservation = self.ledger.reserve_oos_draw(
            "theme_boundary", "hypo_001", "confighash_001", "2" * 64,
            "gatehash_001", "window_001", idempotency_key=self.task_key,
            task_key=self.task_key, protocol_snapshot_id="proto_001",
        )
        self.ledger.start_execution(reservation.reservation_id)
        self.ledger.complete_reservation(
            reservation.reservation_id, "rejected", report_id="report_rev_001_1",
        )
        self.db.conn.execute(
            "UPDATE oos_budget_reservations SET verdict = 'invalid_verdict' WHERE reservation_id = ?",
            (reservation.reservation_id,),
        )
        self.db.conn.commit()
        flow = B6ValidationFlow(
            strategy_db=self.db,
            oos_controller=MockOOSController(),
            report_builder=MockReportBuilder(),
            gate=MockGate(),
            explanation_builder=MockExplanationBuilder(),
            oos_budget_ledger=self.ledger,
        )

        with self.assertRaisesRegex(ValueError, "invalid persisted verdict"):
            flow.run_minimal_validation(
                strategy_draft=self.strategy_draft,
                protocol=self.protocol,
                manifest=self.manifest,
                universe=self.universe,
                b4_qualification=self.b4_qualification,
                b4_event_result=self.b4_event_result,
                task_id=self.task_id,
                )

    def test_completed_terminal_replay_rejects_missing_persisted_report_id(self):
        """A completed draw without its report identity is incomplete audit metadata."""
        reservation = self.ledger.reserve_oos_draw(
            "theme_boundary", "hypo_001", "confighash_001", "2" * 64,
            "gatehash_001", "window_001", idempotency_key=self.task_key,
            task_key=self.task_key, protocol_snapshot_id="proto_001",
        )
        self.ledger.start_execution(reservation.reservation_id)
        self.ledger.complete_reservation(reservation.reservation_id, "rejected")
        flow = B6ValidationFlow(
            strategy_db=self.db,
            oos_controller=MockOOSController(),
            report_builder=MockReportBuilder(),
            gate=MockGate(),
            explanation_builder=MockExplanationBuilder(),
            oos_budget_ledger=self.ledger,
        )

        with self.assertRaisesRegex(ValueError, "missing verdict or report_id"):
            flow.run_minimal_validation(
                strategy_draft=self.strategy_draft,
                protocol=self.protocol,
                manifest=self.manifest,
                universe=self.universe,
                b4_qualification=self.b4_qualification,
                b4_event_result=self.b4_event_result,
                task_id=self.task_id,
                )


if __name__ == "__main__":
    unittest.main()
