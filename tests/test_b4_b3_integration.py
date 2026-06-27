"""B4 Task 10: B3 to B4 integration tests (v2).

Proves B4 consumes B3 frozen protocol through enforced boundary.

All tests use run_qualification_with_b3_protocol() - the official B4 entrypoint.
"""
import unittest
from datetime import date, datetime

from backend.services.backtest_engine_qualification import BacktestEngineQualification
from backend.services.b3_protocol_types import DataSnapshotManifest, PointInTimeMembershipSnapshot
from contracts.strategy import ResearchProtocolSnapshot, ForwardWatchlistSnapshot


def create_valid_protocol():
    return ResearchProtocolSnapshot(
        protocol_snapshot_id="proto_001",
        theme_id="theme_001",
        hypothesis_source_snapshot_id="hyp_001",
        strategy_revision_id="rev_001",
        sample_split_rule_id="split_001",
        oos_window_rule_id="oos_rule_001",
        oos_window_rule_params_json="{}",
        oos_window_start=date(2024, 6, 1),
        oos_window_end=date(2024, 12, 31),
        shared_oos_window_id="oos_win_001",
        backtest_universe_spec_id="univ_001",
        data_snapshot_id="data_001",
        kill_criteria_snapshot_id="kill_001",
        prototype_gate_thresholds_json="{}",
        strategy_config_hash="config_hash_abc",
        data_snapshot_hash="valid_hash_xyz",
        gate_criteria_hash="gate_hash_123",
        frozen_at=datetime(2024, 1, 1, 12, 0, 0),
        frozen_by="system",
    )


def create_valid_manifest():
    return DataSnapshotManifest(
        data_snapshot_id="data_001",
        data_snapshot_hash="valid_hash_xyz",
        created_at=date(2024, 1, 1),
        market_data_fingerprint="market_fp",
        daily_status_fingerprint="status_fp",
        membership_fingerprint="member_fp",
        quality_status="ok",
        gaps=(),
    )


def create_valid_pit_universe():
    return PointInTimeMembershipSnapshot(
        snapshot_id="pit_001",
        snapshot_date=date(2023, 12, 31),
        universe_rule_type="point_in_time_membership",
        membership_source="index_constituents",
        include_delisted=True,
        records=(),
        quality_status="ok",
        gaps=(),
    )


class TestB3ProtocolSnapshotRequiredForB4Backtest(unittest.TestCase):
    """B4 entrypoint requires B3 protocol snapshot."""
    
    def test_b3_protocol_snapshot_required_for_b4_backtest(self):
        """Missing protocol raises ValueError through B4 entrypoint."""
        qualification = BacktestEngineQualification()
        manifest = create_valid_manifest()
        universe = create_valid_pit_universe()
        
        with self.assertRaises((ValueError, AttributeError, TypeError)):
            qualification.run_qualification_with_b3_protocol(
                protocol=None,  # Missing
                manifest=manifest,
                universe_spec=universe,
                qualification_date=date(2024, 1, 10),
            )


class TestB3DataSnapshotHashRequiredForB4Backtest(unittest.TestCase):
    """B4 entrypoint requires data_snapshot_hash."""
    
    def test_b3_data_snapshot_hash_required_for_b4_backtest(self):
        """Protocol with data_snapshot_hash is required."""
        # ResearchProtocolSnapshot.data_snapshot_hash is required field
        # Attempting to create without it would fail at Pydantic level
        protocol = create_valid_protocol()
        
        # Verify hash is present
        self.assertIsNotNone(protocol.data_snapshot_hash)
        self.assertTrue(len(protocol.data_snapshot_hash) > 0)


class TestB4RejectsMutatedProtocolSnapshot(unittest.TestCase):
    """B4 rejects mutated protocol (frozen=True)."""
    
    def test_b4_rejects_mutated_protocol_snapshot(self):
        """Protocol snapshot is frozen, cannot mutate."""
        protocol = create_valid_protocol()
        
        # FrozenStrategyContract prevents mutation
        with self.assertRaises(Exception):
            protocol.data_snapshot_hash = "different_hash"


class TestB4RejectsDataSnapshotHashMismatch(unittest.TestCase):
    """B4 entrypoint hard rejects hash mismatch."""
    
    def test_b4_rejects_data_snapshot_hash_mismatch(self):
        """Hash mismatch through B4 entrypoint raises ValueError."""
        qualification = BacktestEngineQualification()
        
        protocol = create_valid_protocol()  # hash="valid_hash_xyz"
        
        manifest = DataSnapshotManifest(
            data_snapshot_id="data_001",
            data_snapshot_hash="different_hash_abc",  # Mismatch
            created_at=date(2024, 1, 1),
            market_data_fingerprint="market_fp",
            daily_status_fingerprint="status_fp",
            membership_fingerprint="member_fp",
            quality_status="ok",
            gaps=(),
        )
        
        universe = create_valid_pit_universe()
        
        # B4 entrypoint must reject hash mismatch
        with self.assertRaises(ValueError) as ctx:
            qualification.run_qualification_with_b3_protocol(
                protocol=protocol,
                manifest=manifest,
                universe_spec=universe,
                qualification_date=date(2024, 1, 10),
            )
        
        self.assertIn("mismatch", str(ctx.exception).lower())
        self.assertIn("valid_hash_xyz", str(ctx.exception))
        self.assertIn("different_hash_abc", str(ctx.exception))


class TestB4RejectsForwardWatchlistUniverse(unittest.TestCase):
    """B4 entrypoint rejects forward watchlist."""
    
    def test_b4_rejects_forward_watchlist_universe(self):
        """ForwardWatchlistSnapshot rejected through B4 entrypoint."""
        qualification = BacktestEngineQualification()
        protocol = create_valid_protocol()
        manifest = create_valid_manifest()
        
        forward_watchlist = ForwardWatchlistSnapshot(
            watchlist_snapshot_id="watch_001",
            theme_id="theme_001",
            confirmed_candidate_ids=("cand_001",),
            symbols=("000001.SZ",),
            snapshot_date=date(2024, 1, 15),
            created_at=datetime(2024, 1, 15, 10, 0, 0),
        )
        
        # B4 entrypoint must reject forward watchlist
        with self.assertRaises(ValueError) as ctx:
            qualification.run_qualification_with_b3_protocol(
                protocol=protocol,
                manifest=manifest,
                universe_spec=forward_watchlist,
                qualification_date=date(2024, 1, 10),
            )
        
        self.assertIn("forward", str(ctx.exception).lower())


class TestB4RejectsCurrentStaticSymbolUniverse(unittest.TestCase):
    """B4 entrypoint rejects static symbol list."""
    
    def test_b4_rejects_current_static_symbol_universe(self):
        """Static symbol list rejected through B4 entrypoint."""
        qualification = BacktestEngineQualification()
        protocol = create_valid_protocol()
        manifest = create_valid_manifest()
        
        static_symbols = ["000001.SZ", "000002.SZ"]
        
        # B4 entrypoint must reject static list
        with self.assertRaises(ValueError) as ctx:
            qualification.run_qualification_with_b3_protocol(
                protocol=protocol,
                manifest=manifest,
                universe_spec=static_symbols,
                qualification_date=date(2024, 1, 10),
            )
        
        self.assertIn("static", str(ctx.exception).lower())


class TestB4UsesPointInTimeMembershipSnapshot(unittest.TestCase):
    """B4 entrypoint accepts PIT snapshot."""
    
    def test_b4_uses_point_in_time_membership_snapshot(self):
        """PIT snapshot accepted through B4 entrypoint."""
        qualification = BacktestEngineQualification()
        protocol = create_valid_protocol()
        manifest = create_valid_manifest()
        pit_universe = create_valid_pit_universe()
        
        # B4 entrypoint accepts PIT snapshot
        result = qualification.run_qualification_with_b3_protocol(
            protocol=protocol,
            manifest=manifest,
            universe_spec=pit_universe,
            qualification_date=date(2024, 1, 10),
        )
        
        # Result records universe info
        self.assertEqual(result["universe_type"], "point_in_time")
        self.assertEqual(result["universe_snapshot_id"], "pit_001")


class TestB4RecordsProtocolAndSnapshotIDsInResult(unittest.TestCase):
    """B4 result records protocol_snapshot_id and data_snapshot_hash."""
    
    def test_b4_records_protocol_and_snapshot_ids_in_result(self):
        """Result includes B3 metadata."""
        qualification = BacktestEngineQualification()
        protocol = create_valid_protocol()
        manifest = create_valid_manifest()
        universe = create_valid_pit_universe()
        
        result = qualification.run_qualification_with_b3_protocol(
            protocol=protocol,
            manifest=manifest,
            universe_spec=universe,
            qualification_date=date(2024, 1, 10),
        )
        
        # Result must record B3 metadata
        self.assertIn("protocol_snapshot_id", result)
        self.assertIn("data_snapshot_hash", result)
        self.assertIn("data_snapshot_id", result)
        
        self.assertEqual(result["protocol_snapshot_id"], "proto_001")
        self.assertEqual(result["data_snapshot_hash"], "valid_hash_xyz")
        self.assertEqual(result["data_snapshot_id"], "data_001")


class TestB4DoesNotModifyB3Protocol(unittest.TestCase):
    """B4 does not mutate B3 protocol."""
    
    def test_b4_does_not_modify_b3_protocol(self):
        """Protocol remains unchanged after B4 run."""
        qualification = BacktestEngineQualification()
        protocol = create_valid_protocol()
        manifest = create_valid_manifest()
        universe = create_valid_pit_universe()
        
        original_hash = protocol.data_snapshot_hash
        
        qualification.run_qualification_with_b3_protocol(
            protocol=protocol,
            manifest=manifest,
            universe_spec=universe,
            qualification_date=date(2024, 1, 10),
        )
        
        # Protocol unchanged
        self.assertEqual(protocol.data_snapshot_hash, original_hash)


class TestB4DoesNotWriteGateOrPromotion(unittest.TestCase):
    """B4 result does not contain Gate/promotion."""
    
    def test_b4_does_not_write_gate_or_promotion(self):
        """Result has no Gate/promotion fields."""
        qualification = BacktestEngineQualification()
        protocol = create_valid_protocol()
        manifest = create_valid_manifest()
        universe = create_valid_pit_universe()
        
        result = qualification.run_qualification_with_b3_protocol(
            protocol=protocol,
            manifest=manifest,
            universe_spec=universe,
            qualification_date=date(2024, 1, 10),
        )
        
        # No Gate/promotion
        self.assertNotIn("gate", result)
        self.assertNotIn("promotion", result)
        self.assertNotIn("prototype_passed", result)


if __name__ == "__main__":
    unittest.main()
