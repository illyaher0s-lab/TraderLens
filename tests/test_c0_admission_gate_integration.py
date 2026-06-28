"""
C0 Task 2: C Admission Gate Integration Tests

Tests that generate_planned_signals.py enforces CAdmissionGate.
"""
import unittest
from datetime import datetime
from pathlib import Path
import tempfile

from backend.db.strategy import StrategyDB
from backend.services.strategy_promotion_reducer import StrategyPromotionReducer
from contracts.strategy import (
    StrategyDraft,
    BacktestUniverseSpec,
    StrategyLifecycleState,
    HumanPromotionConfirmation,
    ResearchProtocolSnapshot,
    PrototypeGateResultV2,
)


class TestC0AdmissionGateIntegration(unittest.TestCase):
    def setUp(self):
        """Create temporary StrategyDB for testing."""
        # Use temp file so admission gate can open it
        self.temp_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.temp_file.name
        self.temp_file.close()
        self.db = StrategyDB(self.db_path)

    def tearDown(self):
        """Close StrategyDB and clean up temp file."""
        self.db.close()
        import os
        import time
        time.sleep(0.1)  # Give OS time to release file handle
        try:
            os.remove(self.db_path)
        except (PermissionError, FileNotFoundError):
            pass  # Windows may still hold lock

    def _create_draft_strategy(self, strategy_revision_id: str):
        """Helper to create strategy draft in DB (state=draft)."""
        from datetime import date
        universe_spec = BacktestUniverseSpec(
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
        self.db.store_backtest_universe(universe_spec)

        draft = StrategyDraft(
            strategy_revision_id=strategy_revision_id,
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

        state = StrategyLifecycleState(
            lifecycle_state_id=f"state_{strategy_revision_id}",
            strategy_revision_id=strategy_revision_id,
            state_version=1,
            state="draft",  # Initial state must be draft
            source_record_id="source_001",
            recorded_at=datetime.now(),
            recorded_by="test",
        )

        self.db.create_strategy_draft(draft, state)

    def _promote_to_prototype_passed(self, strategy_revision_id: str):
        """Helper to promote strategy to prototype_passed via reducer."""
        from datetime import date

        # Store protocol
        protocol = ResearchProtocolSnapshot(
            protocol_snapshot_id="proto_001",
            theme_id="theme_001",
            hypothesis_source_snapshot_id="hypo_snap_001",
            strategy_revision_id=strategy_revision_id,
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
        self.db.store_protocol_snapshot(protocol)

        # Store backtest report (required by foreign key)
        from contracts.strategy import ImmutableBacktestReport
        report = ImmutableBacktestReport(
            report_id="report_001",
            theme_id="theme_001",
            strategy_revision_id=strategy_revision_id,
            protocol_snapshot_id="proto_001",
            strategy_config_hash="hash_config_001",
            data_snapshot_hash="hash_data_001",
            gate_criteria_hash="hash_gate_001",
            evaluation_mode="out_of_sample",
            oos_draw_index=1,
            shared_oos_window_id="oos_window_001",
            multiple_comparison_flag=False,
            report_payload_json='{}',
            integrity_status="valid",
            generated_at=datetime.now(),
            report_hash="report_hash_001",
        )
        self.db.store_backtest_report(report)

        # Store gate result
        gate_result = PrototypeGateResultV2(
            gate_result_id="gate_001",
            report_id="report_001",
            strategy_revision_id=strategy_revision_id,
            protocol_snapshot_id="proto_001",
            verdict="candidate_for_prototype_passed",
            checks_json='{}',
            blocking_issues=(),
            warnings=(),
            strategy_config_hash="hash_config_001",
            data_snapshot_hash="hash_data_001",
            gate_criteria_hash="hash_gate_001",
            oos_draw_index=1,
            shared_oos_window_id="oos_window_001",
            multiple_comparison_flag=False,
            generated_at=datetime.now(),
            gate_result_hash="gate_hash_001",
        )
        self.db.store_gate_result(gate_result)

        # Store human confirmation
        confirmation = HumanPromotionConfirmation(
            human_confirmation_id="confirm_001",
            strategy_revision_id=strategy_revision_id,
            gate_result_id="gate_001",
            decision="approve",
            confirmed_by="test_user",
            confirmed_at=datetime.now(),
        )
        self.db.store_human_confirmation(confirmation)

        # Promote via reducer
        reducer = StrategyPromotionReducer(self.db)
        reducer.promote_to_prototype_passed(
            strategy_revision_id=strategy_revision_id,
            gate_result_id="gate_001",
            human_confirmation_id="confirm_001",
            promoted_by="test_user",
        )

    def test_generate_signals_rejects_draft_strategy(self):
        """Signal generation rejects draft strategy (not prototype_passed)."""
        from backend.scripts.generate_planned_signals import generate_planned_signals_from_snapshot

        self._create_draft_strategy("strat_draft")

        # Attempt to generate signals for draft strategy
        with self.assertRaises(ValueError) as ctx:
            generate_planned_signals_from_snapshot(
                snapshot_dir=Path("nonexistent"),  # Won't reach data loading
                strategy_config=None,  # Won't reach config validation
                signal_date=None,  # Won't reach date validation
                strategy_revision_id="strat_draft",
                strategy_db_path=self.db_path,
            )

        # Should fail with C admission gate error
        self.assertIn("not prototype_passed", str(ctx.exception))
        self.assertIn("draft", str(ctx.exception))

    def test_generate_signals_rejects_missing_strategy_revision(self):
        """Signal generation rejects missing strategy_revision_id."""
        from backend.scripts.generate_planned_signals import generate_planned_signals_from_snapshot

        with self.assertRaises(ValueError) as ctx:
            generate_planned_signals_from_snapshot(
                snapshot_dir=Path("nonexistent"),
                strategy_config=None,
                signal_date=None,
                strategy_revision_id="nonexistent_strategy",
                strategy_db_path=self.db_path,
            )

        self.assertIn("not found", str(ctx.exception).lower())

    def test_generate_signals_requires_strategy_db_path_when_revision_id_provided(self):
        """Signal generation requires strategy_db_path when strategy_revision_id provided."""
        from backend.scripts.generate_planned_signals import generate_planned_signals_from_snapshot

        with self.assertRaises(ValueError) as ctx:
            generate_planned_signals_from_snapshot(
                snapshot_dir=Path("nonexistent"),
                strategy_config=None,
                signal_date=None,
                strategy_revision_id="strat_001",
                strategy_db_path=None,  # Missing DB path
            )

        self.assertIn("strategy_db_path is required", str(ctx.exception))

    def test_generate_signals_allows_prototype_passed_strategy(self):
        """
        Signal generation allows prototype_passed strategy (no ValueError).

        Note: This test creates a prototype_passed strategy and verifies that
        C admission gate accepts it. The test will fail at snapshot loading
        (expected), but should NOT fail at admission gate check.
        """
        from backend.scripts.generate_planned_signals import generate_planned_signals_from_snapshot

        self._create_draft_strategy("strat_passed")
        self._promote_to_prototype_passed("strat_passed")

        # Attempt signal generation - should pass admission gate
        # We expect failure at data loading (snapshot doesn't exist),
        # but the key assertion is that we pass the admission gate check.
        admission_gate_passed = False
        try:
            generate_planned_signals_from_snapshot(
                snapshot_dir=Path("nonexistent"),  # Will fail at data loading
                strategy_config=None,
                signal_date=None,
                strategy_revision_id="strat_passed",
                strategy_db_path=self.db_path,
            )
        except ValueError as e:
            # Check if this is admission gate error
            if "not prototype_passed" in str(e):
                self.fail(f"Admission gate rejected prototype_passed strategy: {e}")
            # Other ValueError (e.g., TushareConfig) means admission gate passed
            admission_gate_passed = True
        except (TypeError, FileNotFoundError):
            # TypeError from TushareConfig or FileNotFoundError from missing snapshot
            # Both mean admission gate passed
            admission_gate_passed = True

        self.assertTrue(admission_gate_passed, "Should pass admission gate for prototype_passed strategy")


if __name__ == "__main__":
    unittest.main()
