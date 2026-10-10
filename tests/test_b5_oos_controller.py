"""B5 OOS Controller Tests - B3/B4 prerequisite boundary."""
import unittest
from datetime import date, datetime

from backend.services.oos_evaluation_controller import OOSEvaluationController
from backend.services.b3_protocol_types import (
    DataSnapshotManifest,
    PointInTimeMembershipSnapshot,
)
from contracts.strategy import (
    ResearchProtocolSnapshot,
    ForwardWatchlistSnapshot,
)
from backend.services.b4_protocol_types import BacktestEngineQualificationResult


class FakeProtocol:
    """Fake protocol object for duck-typing rejection test."""
    def __init__(self):
        self.protocol_snapshot_id = "fake_proto_001"
        self.data_snapshot_hash = "fake_data_hash"
        self.data_snapshot_id = "fake_data_id"
        self.frozen = True


class FakeManifest:
    """Fake manifest object for duck-typing rejection test."""
    def __init__(self):
        self.data_snapshot_hash = "fake_data_hash"


class FakeUniverse:
    """Fake universe object for duck-typing rejection test."""
    def __init__(self):
        self.snapshot_id = "fake_universe_001"


class TestB5B3B4PrerequisiteBoundary(unittest.TestCase):
    """Test B5 OOS controller B3/B4 prerequisite boundary enforcement."""
    
    def setUp(self):
        self.controller = OOSEvaluationController()
        
        # Valid B3 protocol
        self.protocol = ResearchProtocolSnapshot(
            protocol_snapshot_id="proto_001",
            theme_id="theme_001",
            hypothesis_source_snapshot_id="hyp_001",
            strategy_revision_id="strat_001",
            sample_split_rule_id="split_001",
            oos_window_rule_id="latest_252_trading_days",
            oos_window_rule_params_json="{}",
            oos_window_start=date(2023, 1, 1),
            oos_window_end=date(2023, 12, 31),
            shared_oos_window_id="shared_oos_001",
            backtest_universe_spec_id="univ_001",
            data_snapshot_id="data_snap_001",
            kill_criteria_snapshot_id="kill_001",
            prototype_gate_thresholds_json="{}",
            strategy_config_hash="config_hash_001",
            data_snapshot_hash="data_hash_001",
            gate_criteria_hash="gate_hash_001",
            frozen_at=datetime(2024, 1, 1, 10, 0, 0),
            frozen_by="test",
        )
        
        # Valid B3 manifest
        self.manifest = DataSnapshotManifest(
            snapshot_id="data_snap_001",
            provider="test_provider",
            retrieval_date=date(2024, 1, 1),
            market_data_start=date(2023, 1, 1),
            market_data_end=date(2023, 12, 31),
            universe_snapshot_ids=("univ_snap_001",),
            semantic_hash="data_hash_001",
            financial_visibility_fingerprint="fin_fp_001",
            benchmark_fingerprint="bench_fp_001",
            adjustment_factor_fingerprint="adj_fp_001",
            provider_fingerprints=("tushare_fp_001",),
            quality_status="ok",
            gaps=(),
            generated_by="test",
        )
        
        # Valid point-in-time universe
        self.universe = PointInTimeMembershipSnapshot(
            snapshot_id="univ_snap_001",
            snapshot_date=date(2023, 1, 1),
            universe_rule_type="point_in_time_membership",
            membership_source="test_index",
            include_delisted=True,
            records=(),
            quality_status="ok",
            gaps=(),
        )
        
        # Valid B4 formal qualification result
        self.b4_result = {
            "result": BacktestEngineQualificationResult(
                qualification_id="qual_001",
                protocol_snapshot_id="proto_001",
                canary_cases=(),
                qualification_status="pass",
                qualified_at=date(2024, 1, 1),
            ),
            "protocol_snapshot_id": "proto_001",
            "data_snapshot_hash": "data_hash_001",
            "data_snapshot_id": "data_snap_001",
            "universe_type": "point_in_time",
            "universe_snapshot_id": "univ_snap_001",
        }
    
    def test_b5_requires_b3_protocol_snapshot(self):
        """B5 requires B3 ResearchProtocolSnapshot (not None, not fake object)."""
        # None protocol rejected
        with self.assertRaises(ValueError) as ctx:
            self.controller.validate_b3_b4_prerequisites(
                None, self.manifest, self.universe, self.b4_result
            )
        self.assertIn("ResearchProtocolSnapshot is required", str(ctx.exception))
        self.assertIn("got None", str(ctx.exception))
    
    def test_b5_rejects_fake_protocol_object(self):
        """B5 rejects fake protocol object (duck-typing prevention)."""
        fake_protocol = FakeProtocol()
        
        with self.assertRaises(ValueError) as ctx:
            self.controller.validate_b3_b4_prerequisites(
                fake_protocol, self.manifest, self.universe, self.b4_result
            )
        self.assertIn("Invalid protocol object type", str(ctx.exception))
        self.assertIn("fake object", str(ctx.exception).lower())
    
    def test_b5_requires_data_snapshot_hash(self):
        """B5 requires DataSnapshotManifest with non-empty data_snapshot_hash."""
        # None manifest rejected
        with self.assertRaises(ValueError) as ctx:
            self.controller.validate_b3_b4_prerequisites(
                self.protocol, None, self.universe, self.b4_result
            )
        self.assertIn("DataSnapshotManifest is required", str(ctx.exception))
    
    def test_b5_requires_formal_b4_qualification(self):
        """B5 requires B4 formal qualification from run_qualification_with_b3_protocol()."""
        # Legacy B4 string result rejected
        legacy_b4_result = "qualification_pass"
        
        with self.assertRaises(ValueError) as ctx:
            self.controller.validate_b3_b4_prerequisites(
                self.protocol, self.manifest, self.universe, legacy_b4_result
            )
        self.assertIn("legacy qualification result rejected", str(ctx.exception).lower())
        self.assertIn("run_qualification_with_b3_protocol", str(ctx.exception))
    
    def test_b5_rejects_legacy_b4_qualification_result(self):
        """B5 rejects B4 legacy qualification (string-only result)."""
        # String result (legacy)
        with self.assertRaises(ValueError) as ctx:
            self.controller.validate_b3_b4_prerequisites(
                self.protocol, self.manifest, self.universe, "pass"
            )
        self.assertIn("legacy", str(ctx.exception).lower())
    
    def test_b5_rejects_b4_result_with_gate_or_promotion_fields(self):
        """B5 rejects B4 result containing Gate or promotion fields."""
        # B4 result with forbidden gate_verdict field
        invalid_b4_result = self.b4_result.copy()
        invalid_b4_result["gate_verdict"] = "rejected"
        
        with self.assertRaises(ValueError) as ctx:
            self.controller.validate_b3_b4_prerequisites(
                self.protocol, self.manifest, self.universe, invalid_b4_result
            )
        self.assertIn("forbidden field", str(ctx.exception).lower())
        self.assertIn("gate_verdict", str(ctx.exception))
    
    def test_b5_rejects_forward_watchlist_universe(self):
        """B5 rejects ForwardWatchlistSnapshot universe."""
        forward_watchlist = ForwardWatchlistSnapshot(
            watchlist_snapshot_id="watch_001",
            theme_id="theme_001",
            confirmed_candidate_ids=(),
            symbols=("000001.SZ",),
            snapshot_date=date(2024, 1, 1),
            created_at=datetime(2024, 1, 1, 10, 0, 0),
        )
        
        with self.assertRaises(ValueError) as ctx:
            self.controller.validate_b3_b4_prerequisites(
                self.protocol, self.manifest, forward_watchlist, self.b4_result
            )
        self.assertIn("ForwardWatchlistSnapshot cannot be used", str(ctx.exception))
        self.assertIn("prospective-only", str(ctx.exception))
    
    def test_b5_rejects_static_symbol_universe(self):
        """B5 rejects static symbol list universe."""
        static_symbols = ["000001.SZ", "000002.SZ"]
        
        with self.assertRaises(ValueError) as ctx:
            self.controller.validate_b3_b4_prerequisites(
                self.protocol, self.manifest, static_symbols, self.b4_result
            )
        self.assertIn("Static symbol list cannot be used", str(ctx.exception))
        self.assertIn("PointInTimeMembershipSnapshot", str(ctx.exception))
    
    def test_b5_rejects_protocol_manifest_hash_mismatch(self):
        """B5 rejects protocol manifest hash mismatch."""
        # Manifest with different data_snapshot_hash
        mismatched_manifest = DataSnapshotManifest(
            snapshot_id="data_snap_002",
            provider="test_provider",
            retrieval_date=date(2024, 1, 1),
            market_data_start=date(2023, 1, 1),
            market_data_end=date(2023, 12, 31),
            universe_snapshot_ids=("univ_snap_001",),
            semantic_hash="data_hash_DIFFERENT",
            financial_visibility_fingerprint="fin_fp_001",
            benchmark_fingerprint="bench_fp_001",
            adjustment_factor_fingerprint="adj_fp_001",
            provider_fingerprints=("tushare_fp_001",),
            quality_status="ok",
            gaps=(),
            generated_by="test",
        )
        
        with self.assertRaises(ValueError) as ctx:
            self.controller.validate_b3_b4_prerequisites(
                self.protocol, mismatched_manifest, self.universe, self.b4_result
            )
        self.assertIn("hash mismatch", str(ctx.exception).lower())
        self.assertIn("data_hash_001", str(ctx.exception))
        self.assertIn("data_hash_DIFFERENT", str(ctx.exception))
    
    def test_b5_records_protocol_and_snapshot_ids(self):
        """B5 records protocol_snapshot_id, data_snapshot_hash, and data_snapshot_id."""
        result = self.controller.validate_b3_b4_prerequisites(
            self.protocol, self.manifest, self.universe, self.b4_result
        )
        
        self.assertEqual(result["protocol_snapshot_id"], "proto_001")
        self.assertEqual(result["data_snapshot_hash"], "data_hash_001")
        self.assertEqual(result["data_snapshot_id"], "data_snap_001")
        self.assertEqual(result["universe_type"], "point_in_time")
        self.assertEqual(result["universe_snapshot_id"], "univ_snap_001")
    
    def test_b5_rejects_failed_b4_qualification(self):
        """B5 rejects B4 qualification with status != 'pass'."""
        # B4 result with failed qualification
        failed_b4_result = self.b4_result.copy()
        failed_b4_result["result"] = BacktestEngineQualificationResult(
            qualification_id="qual_002",
            protocol_snapshot_id="proto_001",
            canary_cases=(),
            qualification_status="fail",  # Failed
            qualified_at=date(2024, 1, 1),
        )
        
        with self.assertRaises(ValueError) as ctx:
            self.controller.validate_b3_b4_prerequisites(
                self.protocol, self.manifest, self.universe, failed_b4_result
            )
        self.assertIn("qualification failed", str(ctx.exception).lower())
        self.assertIn("fail", str(ctx.exception))
    
    def test_b5_rejects_b4_protocol_snapshot_id_mismatch(self):
        """B5 rejects B4 result with mismatched protocol_snapshot_id."""
        mismatched_b4 = self.b4_result.copy()
        mismatched_b4["protocol_snapshot_id"] = "proto_DIFFERENT"
        
        with self.assertRaises(ValueError) as ctx:
            self.controller.validate_b3_b4_prerequisites(
                self.protocol, self.manifest, self.universe, mismatched_b4
            )
        self.assertIn("protocol_snapshot_id mismatch", str(ctx.exception).lower())
        self.assertIn("proto_001", str(ctx.exception))
        self.assertIn("proto_DIFFERENT", str(ctx.exception))
    
    def test_b5_rejects_b4_data_snapshot_hash_mismatch(self):
        """B5 rejects B4 result with mismatched data_snapshot_hash."""
        mismatched_b4 = self.b4_result.copy()
        mismatched_b4["data_snapshot_hash"] = "data_hash_DIFFERENT"
        
        with self.assertRaises(ValueError) as ctx:
            self.controller.validate_b3_b4_prerequisites(
                self.protocol, self.manifest, self.universe, mismatched_b4
            )
        self.assertIn("data_snapshot_hash mismatch", str(ctx.exception).lower())
        self.assertIn("data_hash_001", str(ctx.exception))
        self.assertIn("data_hash_DIFFERENT", str(ctx.exception))
    
    def test_b5_rejects_b4_data_snapshot_id_mismatch(self):
        """B5 rejects B4 result with mismatched data_snapshot_id."""
        mismatched_b4 = self.b4_result.copy()
        mismatched_b4["data_snapshot_id"] = "data_snap_DIFFERENT"
        
        with self.assertRaises(ValueError) as ctx:
            self.controller.validate_b3_b4_prerequisites(
                self.protocol, self.manifest, self.universe, mismatched_b4
            )
        self.assertIn("data_snapshot_id mismatch", str(ctx.exception).lower())
        self.assertIn("data_snap_001", str(ctx.exception))
        self.assertIn("data_snap_DIFFERENT", str(ctx.exception))
    
    def test_b5_rejects_b4_universe_snapshot_id_mismatch(self):
        """B5 rejects B4 result with mismatched universe_snapshot_id."""
        mismatched_b4 = self.b4_result.copy()
        mismatched_b4["universe_snapshot_id"] = "univ_snap_DIFFERENT"
        
        with self.assertRaises(ValueError) as ctx:
            self.controller.validate_b3_b4_prerequisites(
                self.protocol, self.manifest, self.universe, mismatched_b4
            )
        self.assertIn("universe_snapshot_id mismatch", str(ctx.exception).lower())
        self.assertIn("univ_snap_001", str(ctx.exception))
        self.assertIn("univ_snap_DIFFERENT", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
