import unittest
from datetime import date, datetime

from backend.services.research_protocol_freezer import ResearchProtocolFreezer
from backend.services.b3_protocol_types import (
    DataSnapshotManifest,
    OOSWindowSpec,
)
from contracts.strategy import BacktestUniverseSpec, StrategyDraft


class TestResearchProtocolFreezer(unittest.TestCase):
    def setUp(self):
        self.freezer = ResearchProtocolFreezer()
        
        # Valid inputs
        self.strategy_draft = StrategyDraft(
            strategy_revision_id="rev_001",
            theme_id="theme_001",
            hypothesis_id="hyp_001",
            strategy_template_id="tmpl_001",
            strategy_template_version="v1",
            strategy_template_hash="hash_tmpl",
            hypothesis_source_snapshot_id="snap_001",
            backtest_universe_spec_id="universe_001",
            strategy_config_json='{"entry": "breakout"}',
            sample_split_rule_id="split_001",
            created_at=datetime(2024, 1, 1),
        )
        
        self.universe = BacktestUniverseSpec(
            universe_spec_id="universe_001",
            universe_rule_type="point_in_time_membership",
            membership_source="historical_index",
            membership_effective_from=date(2024, 1, 1),
            membership_effective_to=date(2024, 12, 31),
            snapshot_date=date(2024, 1, 1),
            membership_snapshot_ids=("snap_001",),
            quality_status="ok",
            gaps=(),
        )
        
        self.data_snapshot = DataSnapshotManifest(
            snapshot_id="data_001",
            provider="tushare",
            retrieval_date=date(2024, 1, 1),
            market_data_start=date(2024, 1, 1),
            market_data_end=date(2024, 12, 31),
            universe_snapshot_ids=("snap_001",),
            semantic_hash="hash_data_001",
            quality_status="ok",
            gaps=(),
        )
        
        self.oos_window = OOSWindowSpec(
            oos_window_rule_id="fixed_ratio_70_30",
            oos_window_start=date(2024, 7, 1),
            oos_window_end=date(2024, 12, 31),
            generated_at=date(2024, 1, 1),
        )

    def test_freezes_protocol_when_all_inputs_valid(self):
        """Freeze protocol when all inputs valid."""
        protocol = self.freezer.freeze_protocol(
            strategy_draft=self.strategy_draft,
            universe=self.universe,
            data_snapshot=self.data_snapshot,
            oos_window=self.oos_window,
            gate_criteria_hash="hash_gate",
            frozen_by="test_agent",
            backtest_start=date(2024, 1, 1),
        )
        
        self.assertIsNotNone(protocol)
        self.assertEqual(protocol.strategy_revision_id, "rev_001")

    def test_rejects_missing_strategy_config_hash(self):
        """Missing strategy_config_hash must fail."""
        # strategy_config_json empty would mean no config hash
        invalid_draft = StrategyDraft(
            strategy_revision_id="rev_001",
            theme_id="theme_001",
            hypothesis_id="hyp_001",
            strategy_template_id="tmpl_001",
            strategy_template_version="v1",
            strategy_template_hash="hash_tmpl",
            hypothesis_source_snapshot_id="snap_001",
            backtest_universe_spec_id="universe_001",
            strategy_config_json="",  # Empty
            sample_split_rule_id="split_001",
            created_at=datetime(2024, 1, 1),
        )
        
        with self.assertRaises(ValueError) as ctx:
            self.freezer.freeze_protocol(
                strategy_draft=invalid_draft,
                universe=self.universe,
                data_snapshot=self.data_snapshot,
                oos_window=self.oos_window,
                gate_criteria_hash="hash_gate",
                frozen_by="test_agent",
                backtest_start=date(2024, 1, 1),
            )
        
        self.assertIn("strategy_config", str(ctx.exception).lower())

    def test_rejects_missing_data_snapshot_hash(self):
        """Missing data_snapshot_hash must fail. ponytail: semantic_hash"""
        invalid_snapshot = DataSnapshotManifest(
            snapshot_id="data_001",
            provider="tushare",
            retrieval_date=date(2024, 1, 1),
            market_data_start=date(2024, 1, 1),
            market_data_end=date(2024, 12, 31),
            universe_snapshot_ids=("snap_001",),
            semantic_hash="",  # Empty
            quality_status="ok",
            gaps=(),
        )
        
        with self.assertRaises(ValueError) as ctx:
            self.freezer.freeze_protocol(
                strategy_draft=self.strategy_draft,
                universe=self.universe,
                data_snapshot=invalid_snapshot,
                oos_window=self.oos_window,
                gate_criteria_hash="hash_gate",
                frozen_by="test_agent",
                backtest_start=date(2024, 1, 1),
            )
        
        self.assertIn("semantic_hash", str(ctx.exception).lower())

    def test_rejects_missing_gate_criteria_hash(self):
        """Missing gate_criteria_hash must fail."""
        with self.assertRaises(ValueError) as ctx:
            self.freezer.freeze_protocol(
                strategy_draft=self.strategy_draft,
                universe=self.universe,
                data_snapshot=self.data_snapshot,
                oos_window=self.oos_window,
                gate_criteria_hash="",  # Empty
                frozen_by="test_agent",
                backtest_start=date(2024, 1, 1),
            )
        
        self.assertIn("gate_criteria_hash", str(ctx.exception).lower())

    def test_rejects_user_supplied_oos_dates(self):
        """User-supplied OOS dates must be rejected."""
        # OOS with unregistered rule
        invalid_oos = OOSWindowSpec(
            oos_window_rule_id="user_custom_window",
            oos_window_start=date(2024, 7, 1),
            oos_window_end=date(2024, 12, 31),
            generated_at=date(2024, 1, 1),
        )
        
        with self.assertRaises(ValueError) as ctx:
            self.freezer.freeze_protocol(
                strategy_draft=self.strategy_draft,
                universe=self.universe,
                data_snapshot=self.data_snapshot,
                oos_window=invalid_oos,
                gate_criteria_hash="hash_gate",
                frozen_by="test_agent",
                backtest_start=date(2024, 1, 1),
            )
        
        self.assertIn("oos", str(ctx.exception).lower())

    def test_rejects_insufficient_data_snapshot(self):
        """Insufficient data snapshot must fail."""
        insufficient_snapshot = DataSnapshotManifest(
            snapshot_id="data_001",
            provider="tushare",
            retrieval_date=date(2024, 1, 1),
            market_data_start=date(2024, 1, 1),
            market_data_end=date(2024, 12, 31),
            universe_snapshot_ids=("snap_001",),
            semantic_hash="hash_data_001",
            quality_status="insufficient",
            gaps=("missing critical data",),
        )
        
        with self.assertRaises(ValueError) as ctx:
            self.freezer.freeze_protocol(
                strategy_draft=self.strategy_draft,
                universe=self.universe,
                data_snapshot=insufficient_snapshot,
                oos_window=self.oos_window,
                gate_criteria_hash="hash_gate",
                frozen_by="test_agent",
                backtest_start=date(2024, 1, 1),
            )
        
        self.assertIn("insufficient", str(ctx.exception).lower())

    def test_rejects_contaminated_universe(self):
        """Contaminated universe (insufficient membership) must fail."""
        contaminated_universe = BacktestUniverseSpec(
            universe_spec_id="universe_001",
            universe_rule_type="point_in_time_membership",
            membership_source="historical_index",
            membership_effective_from=date(2024, 1, 1),
            membership_effective_to=date(2024, 12, 31),
            snapshot_date=date(2024, 1, 1),
            membership_snapshot_ids=(),  # Empty
            quality_status="insufficient",
            gaps=("no membership data",),
        )
        
        with self.assertRaises(ValueError) as ctx:
            self.freezer.freeze_protocol(
                strategy_draft=self.strategy_draft,
                universe=contaminated_universe,
                data_snapshot=self.data_snapshot,
                oos_window=self.oos_window,
                gate_criteria_hash="hash_gate",
                frozen_by="test_agent",
                backtest_start=date(2024, 1, 1),
            )
        
        self.assertIn("universe", str(ctx.exception).lower())

    def test_protocol_freeze_creates_no_gate_report_or_promotion(self):
        """Protocol freeze must not create Gate/report/promotion."""
        protocol = self.freezer.freeze_protocol(
            strategy_draft=self.strategy_draft,
            universe=self.universe,
            data_snapshot=self.data_snapshot,
            oos_window=self.oos_window,
            gate_criteria_hash="hash_gate",
            frozen_by="test_agent",
            backtest_start=date(2024, 1, 1),
        )
        
        # Protocol should not have Gate/report/promotion fields
        self.assertFalse(hasattr(protocol, "prototype_passed"))
        self.assertFalse(hasattr(protocol, "gate_result"))
        self.assertFalse(hasattr(protocol, "promotion_status"))

    def test_protocol_snapshot_is_immutable(self):
        """Protocol snapshot must be immutable (frozen)."""
        protocol = self.freezer.freeze_protocol(
            strategy_draft=self.strategy_draft,
            universe=self.universe,
            data_snapshot=self.data_snapshot,
            oos_window=self.oos_window,
            gate_criteria_hash="hash_gate",
            frozen_by="test_agent",
            backtest_start=date(2024, 1, 1),
        )
        
        # Pydantic frozen model cannot be modified
        with self.assertRaises(Exception):
            protocol.strategy_revision_id = "modified"

    def test_protocol_freezer_has_no_llm_dependency(self):
        """Protocol freezer must be deterministic, no LLM."""
        from backend.services import research_protocol_freezer
        import inspect
        
        source = inspect.getsource(research_protocol_freezer)
        lines = [line for line in source.split('\n') if not line.strip().startswith('"') and not line.strip().startswith('#')]
        code_only = '\n'.join(lines).lower()
        
        self.assertNotIn("import llm", code_only)
        self.assertNotIn("from llm", code_only)
        self.assertNotIn("openai", code_only)
        self.assertNotIn("anthropic", code_only)

    # P0-1: End-to-end time consistency tests
    def test_e2e_rejects_universe_snapshot_after_backtest_start(self):
        """E2E: Universe snapshot_date > backtest_start must fail at freezer."""
        future_universe = BacktestUniverseSpec(
            universe_spec_id="universe_001",
            universe_rule_type="point_in_time_membership",
            membership_source="historical_index",
            membership_effective_from=date(2024, 1, 1),
            membership_effective_to=date(2024, 12, 31),
            snapshot_date=date(2024, 6, 1),  # After backtest_start
            membership_snapshot_ids=("snap_001",),
            quality_status="ok",
            gaps=(),
        )
        
        with self.assertRaises(ValueError) as ctx:
            self.freezer.freeze_protocol(
                strategy_draft=self.strategy_draft,
                universe=future_universe,
                data_snapshot=self.data_snapshot,
                oos_window=self.oos_window,
                gate_criteria_hash="hash_gate",
                frozen_by="test_agent",
                backtest_start=date(2024, 1, 1),
            )
        
        # Must fail with time consistency violation
        self.assertIn("time consistency", str(ctx.exception).lower())
        # Must NOT return protocol snapshot
        # (assertRaises already confirms no return)

    def test_e2e_rejects_current_confirmed_candidate_pool(self):
        """E2E: Current confirmed candidate pool must fail at freezer."""
        candidate_universe = BacktestUniverseSpec(
            universe_spec_id="confirmed_candidate_pool_2024",
            universe_rule_type="point_in_time_membership",
            membership_source="confirmed_candidate_pool",  # Contaminated
            membership_effective_from=date(2024, 1, 1),
            membership_effective_to=date(2024, 12, 31),
            snapshot_date=date(2024, 1, 1),
            membership_snapshot_ids=("snap_001",),
            quality_status="ok",
            gaps=(),
        )
        
        with self.assertRaises(ValueError) as ctx:
            self.freezer.freeze_protocol(
                strategy_draft=self.strategy_draft,
                universe=candidate_universe,
                data_snapshot=self.data_snapshot,
                oos_window=self.oos_window,
                gate_criteria_hash="hash_gate",
                frozen_by="test_agent",
                backtest_start=date(2024, 1, 1),
            )
        
        # Must fail with source violation
        self.assertIn("candidate", str(ctx.exception).lower())

    def test_e2e_rejects_current_sector_membership(self):
        """E2E: Current sector membership for historical backtest must fail."""
        current_sector_universe = BacktestUniverseSpec(
            universe_spec_id="universe_001",
            universe_rule_type="sector_plus_tags",
            membership_source="current_sector_snapshot",
            membership_effective_from=date(2024, 1, 1),
            membership_effective_to=date(2024, 12, 31),
            snapshot_date=date(2024, 12, 31),  # Current snapshot
            membership_snapshot_ids=("snap_001",),
            quality_status="ok",
            gaps=(),
        )
        
        with self.assertRaises(ValueError) as ctx:
            self.freezer.freeze_protocol(
                strategy_draft=self.strategy_draft,
                universe=current_sector_universe,
                data_snapshot=self.data_snapshot,
                oos_window=self.oos_window,
                gate_criteria_hash="hash_gate",
                frozen_by="test_agent",
                backtest_start=date(2024, 1, 1),
            )
        
        # Must fail at freezer (time consistency violation)
        error_msg = str(ctx.exception).lower()
        self.assertTrue(
            "time consistency" in error_msg or "future" in error_msg or "source" in error_msg
        )


if __name__ == "__main__":
    unittest.main()
