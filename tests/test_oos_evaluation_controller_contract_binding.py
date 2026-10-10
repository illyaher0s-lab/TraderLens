"""OOS Evaluation Controller contract binding tests."""
import unittest
from datetime import date

from backend.services.oos_evaluation_controller import OOSEvaluationController
from backend.services.b3_protocol_types import DataSnapshotManifest, PointInTimeMembershipSnapshot, UniverseMembershipRecord
from contracts.strategy import ResearchProtocolSnapshot


class TestOOSControllerContractBinding(unittest.TestCase):
    def test_current_contract_manifest_passes_validation(self):
        """Current DataSnapshotManifest with semantic_hash passes."""
        controller = OOSEvaluationController()
        
        manifest = DataSnapshotManifest(
            snapshot_id="snap_001",
            provider="mock",
            retrieval_date=date(2026, 1, 1),
            market_data_start=date(2020, 1, 1),
            market_data_end=date(2023, 12, 31),
            universe_snapshot_ids=("u_001",),
            semantic_hash="hash_001",
            quality_status="ok",
            gaps=(),
        )
        
        protocol = ResearchProtocolSnapshot(
            protocol_snapshot_id="proto_001",
            theme_id="theme_001",
            hypothesis_source_snapshot_id="hypo_001",
            strategy_revision_id="strat_001",
            sample_split_rule_id="split_001",
            oos_window_rule_id="oos_001",
            oos_window_rule_params_json="{}",
            oos_window_start=date(2024, 1, 1),
            oos_window_end=date(2024, 12, 31),
            shared_oos_window_id="window_001",
            backtest_universe_spec_id="u_001",
            data_snapshot_id="snap_001",
            kill_criteria_snapshot_id="kill_001",
            prototype_gate_thresholds_json="{}",
            strategy_config_hash="config_001",
            data_snapshot_hash="hash_001",
            gate_criteria_hash="gate_001",
            frozen_at=date(2026, 1, 1),
            frozen_by="test",
        )
        
        universe = PointInTimeMembershipSnapshot(
            snapshot_id="u_001",
            snapshot_date=date(2024, 1, 1),
            universe_rule_type="point_in_time_membership",
            membership_source="mock",
            include_delisted=True,
            records=(),
            quality_status="ok",
            gaps=(),
        )
        
        class B4Result:
            qualification_status = "pass"
        
        b4_result = {
            "result": B4Result(),
            "protocol_snapshot_id": "proto_001",
            "data_snapshot_hash": "hash_001",
            "data_snapshot_id": "snap_001",
            "universe_type": "point_in_time",
            "universe_snapshot_id": "u_001",
        }
        
        result = controller.validate_b3_b4_prerequisites(protocol, manifest, universe, b4_result)
        self.assertEqual(result["data_snapshot_hash"], "hash_001")
        self.assertEqual(result["data_snapshot_id"], "snap_001")
    
    def test_empty_semantic_hash_rejected(self):
        """Empty manifest.semantic_hash is rejected."""
        controller = OOSEvaluationController()
        
        manifest = DataSnapshotManifest(
            snapshot_id="snap_001",
            provider="mock",
            retrieval_date=date(2026, 1, 1),
            market_data_start=date(2020, 1, 1),
            market_data_end=date(2023, 12, 31),
            universe_snapshot_ids=("u_001",),
            semantic_hash="",
            quality_status="ok",
            gaps=(),
        )
        
        with self.assertRaises(ValueError) as ctx:
            controller._validate_data_snapshot_manifest(manifest)
        
        self.assertIn("semantic_hash", str(ctx.exception))
    
    def test_protocol_manifest_hash_mismatch_rejected(self):
        """protocol.data_snapshot_hash != manifest.semantic_hash rejected."""
        controller = OOSEvaluationController()
        
        manifest = DataSnapshotManifest(
            snapshot_id="snap_001",
            provider="mock",
            retrieval_date=date(2026, 1, 1),
            market_data_start=date(2020, 1, 1),
            market_data_end=date(2023, 12, 31),
            universe_snapshot_ids=("u_001",),
            semantic_hash="hash_manifest",
            quality_status="ok",
            gaps=(),
        )
        
        protocol = ResearchProtocolSnapshot(
            protocol_snapshot_id="proto_001",
            theme_id="theme_001",
            hypothesis_source_snapshot_id="hypo_001",
            strategy_revision_id="strat_001",
            sample_split_rule_id="split_001",
            oos_window_rule_id="oos_001",
            oos_window_rule_params_json="{}",
            oos_window_start=date(2024, 1, 1),
            oos_window_end=date(2024, 12, 31),
            shared_oos_window_id="window_001",
            backtest_universe_spec_id="u_001",
            data_snapshot_id="snap_001",
            kill_criteria_snapshot_id="kill_001",
            prototype_gate_thresholds_json="{}",
            strategy_config_hash="config_001",
            data_snapshot_hash="hash_protocol",
            gate_criteria_hash="gate_001",
            frozen_at=date(2026, 1, 1),
            frozen_by="test",
        )
        
        with self.assertRaises(ValueError) as ctx:
            controller._validate_hash_consistency(protocol, manifest)
        
        self.assertIn("hash_protocol", str(ctx.exception))
        self.assertIn("hash_manifest", str(ctx.exception))
    
    def test_b4_manifest_hash_mismatch_rejected(self):
        """B4 data_snapshot_hash != manifest.semantic_hash rejected."""
        controller = OOSEvaluationController()
        
        manifest = DataSnapshotManifest(
            snapshot_id="snap_001",
            provider="mock",
            retrieval_date=date(2026, 1, 1),
            market_data_start=date(2020, 1, 1),
            market_data_end=date(2023, 12, 31),
            universe_snapshot_ids=("u_001",),
            semantic_hash="hash_manifest",
            quality_status="ok",
            gaps=(),
        )
        
        protocol = ResearchProtocolSnapshot(
            protocol_snapshot_id="proto_001",
            theme_id="theme_001",
            hypothesis_source_snapshot_id="hypo_001",
            strategy_revision_id="strat_001",
            sample_split_rule_id="split_001",
            oos_window_rule_id="oos_001",
            oos_window_rule_params_json="{}",
            oos_window_start=date(2024, 1, 1),
            oos_window_end=date(2024, 12, 31),
            shared_oos_window_id="window_001",
            backtest_universe_spec_id="u_001",
            data_snapshot_id="snap_001",
            kill_criteria_snapshot_id="kill_001",
            prototype_gate_thresholds_json="{}",
            strategy_config_hash="config_001",
            data_snapshot_hash="hash_manifest",
            gate_criteria_hash="gate_001",
            frozen_at=date(2026, 1, 1),
            frozen_by="test",
        )
        
        universe = PointInTimeMembershipSnapshot(
            snapshot_id="u_001",
            snapshot_date=date(2024, 1, 1),
            universe_rule_type="point_in_time_membership",
            membership_source="mock",
            include_delisted=True,
            records=(),
            quality_status="ok",
            gaps=(),
        )
        
        class B4Result:
            qualification_status = "pass"
        
        b4_result = {
            "result": B4Result(),
            "protocol_snapshot_id": "proto_001",
            "data_snapshot_hash": "hash_b4",
            "data_snapshot_id": "snap_001",
            "universe_type": "point_in_time",
            "universe_snapshot_id": "u_001",
        }
        
        with self.assertRaises(ValueError) as ctx:
            controller._validate_b4_metadata_consistency(b4_result, protocol, manifest, universe)
        
        self.assertIn("hash_b4", str(ctx.exception))
        self.assertIn("hash_manifest", str(ctx.exception))
    
    def test_b4_manifest_id_mismatch_rejected(self):
        """B4 data_snapshot_id != manifest.snapshot_id rejected."""
        controller = OOSEvaluationController()
        
        manifest = DataSnapshotManifest(
            snapshot_id="snap_manifest",
            provider="mock",
            retrieval_date=date(2026, 1, 1),
            market_data_start=date(2020, 1, 1),
            market_data_end=date(2023, 12, 31),
            universe_snapshot_ids=("u_001",),
            semantic_hash="hash_001",
            quality_status="ok",
            gaps=(),
        )
        
        protocol = ResearchProtocolSnapshot(
            protocol_snapshot_id="proto_001",
            theme_id="theme_001",
            hypothesis_source_snapshot_id="hypo_001",
            strategy_revision_id="strat_001",
            sample_split_rule_id="split_001",
            oos_window_rule_id="oos_001",
            oos_window_rule_params_json="{}",
            oos_window_start=date(2024, 1, 1),
            oos_window_end=date(2024, 12, 31),
            shared_oos_window_id="window_001",
            backtest_universe_spec_id="u_001",
            data_snapshot_id="snap_manifest",
            kill_criteria_snapshot_id="kill_001",
            prototype_gate_thresholds_json="{}",
            strategy_config_hash="config_001",
            data_snapshot_hash="hash_001",
            gate_criteria_hash="gate_001",
            frozen_at=date(2026, 1, 1),
            frozen_by="test",
        )
        
        universe = PointInTimeMembershipSnapshot(
            snapshot_id="u_001",
            snapshot_date=date(2024, 1, 1),
            universe_rule_type="point_in_time_membership",
            membership_source="mock",
            include_delisted=True,
            records=(),
            quality_status="ok",
            gaps=(),
        )
        
        class B4Result:
            qualification_status = "pass"
        
        b4_result = {
            "result": B4Result(),
            "protocol_snapshot_id": "proto_001",
            "data_snapshot_hash": "hash_001",
            "data_snapshot_id": "snap_b4",
            "universe_type": "point_in_time",
            "universe_snapshot_id": "u_001",
        }
        
        with self.assertRaises(ValueError) as ctx:
            controller._validate_b4_metadata_consistency(b4_result, protocol, manifest, universe)
        
        self.assertIn("snap_b4", str(ctx.exception))
        self.assertIn("snap_manifest", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
