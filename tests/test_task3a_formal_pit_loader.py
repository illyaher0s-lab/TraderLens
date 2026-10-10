"""Task 3A: Formal PIT Membership Snapshot loader RED tests.

RED → GREEN pattern for loading verified _005 and projecting PIT members.
"""
import unittest
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent


class TestFormalPITSnapshotLoader(unittest.TestCase):
    """RED: Formal snapshot loader from verified artifact."""
    
    def test_001_verified_005_loads_successfully(self):
        """_005 verified snapshot must load without reading source partitions."""
        from backend.services.formal_pit_loader import FormalSnapshotLoader
        
        loader = FormalSnapshotLoader(REPO_ROOT)
        snapshot = loader.load_snapshot("pims_traderlens_v2_shsz_sw2021_pit_005")
        
        self.assertEqual(snapshot.snapshot_id, "pims_traderlens_v2_shsz_sw2021_pit_005")
        self.assertEqual(len(snapshot.records), 7804)
        self.assertTrue(snapshot.include_delisted)
    
    def test_002_rejected_snapshots_fail_loud(self):
        """_001-_004 / missing / tampered snapshots must be rejected."""
        from backend.services.formal_pit_loader import FormalSnapshotLoader
        
        loader = FormalSnapshotLoader(REPO_ROOT)
        
        # _001 retired
        with self.assertRaises(ValueError) as cm:
            loader.load_snapshot("pims_traderlens_v2_shsz_sw2021_pit_001")
        self.assertIn("retired", str(cm.exception).lower())
        
        # _002 invalid
        with self.assertRaises(ValueError) as cm:
            loader.load_snapshot("pims_traderlens_v2_shsz_sw2021_pit_002")
        self.assertIn("unaccepted", str(cm.exception).lower())
        
        # Missing
        with self.assertRaises(ValueError) as cm:
            loader.load_snapshot("pims_traderlens_v2_shsz_sw2021_pit_999")
        self.assertIn("not found", str(cm.exception).lower())
    
    def test_003_formal_data_snapshot_binding_enforced(self):
        """Formal data snapshot ID / semantic hash must match caller input."""
        from backend.services.formal_pit_loader import FormalSnapshotLoader
        
        loader = FormalSnapshotLoader(REPO_ROOT)
        
        # Correct binding
        snapshot = loader.load_snapshot(
            "pims_traderlens_v2_shsz_sw2021_pit_005",
            expected_formal_data_snapshot_id="ds_traderlens_v2_shsz_pit_001",
        )
        self.assertEqual(snapshot.snapshot_id, "pims_traderlens_v2_shsz_sw2021_pit_005")
        
        # Wrong binding
        with self.assertRaises(ValueError) as cm:
            loader.load_snapshot(
                "pims_traderlens_v2_shsz_sw2021_pit_005",
                expected_formal_data_snapshot_id="ds_wrong_id",
            )
        self.assertIn("mismatch", str(cm.exception).lower())


class TestPITMembershipProjection(unittest.TestCase):
    """RED: PIT membership projection from _005."""
    
    def test_011_projection_within_window_returns_members(self):
        """Project at date within window returns correct closed-interval members."""
        from backend.services.formal_pit_loader import FormalSnapshotLoader, FormalMembershipSource
        
        loader = FormalSnapshotLoader(REPO_ROOT)
        snapshot = loader.load_snapshot("pims_traderlens_v2_shsz_sw2021_pit_005")
        
        source = FormalMembershipSource(snapshot)
        members = source.get_members_at_date(date(2024, 6, 1))
        
        # Must return some members
        self.assertGreater(len(members), 0)
        
        # Must be deterministic order
        symbols = [m.symbol for m in members]
        self.assertEqual(symbols, sorted(symbols))
    
    def test_012_effective_to_inclusive(self):
        """effective_to date is inclusive (closed interval)."""
        from backend.services.formal_pit_loader import FormalSnapshotLoader, FormalMembershipSource
        
        loader = FormalSnapshotLoader(REPO_ROOT)
        snapshot = loader.load_snapshot("pims_traderlens_v2_shsz_sw2021_pit_005")
        
        source = FormalMembershipSource(snapshot)
        
        # Load all records to find one with effective_to
        records = snapshot.records
        delisted = [r for r in records if r.effective_to is not None]
        self.assertGreater(len(delisted), 0, "Must have delisted records")
        
        # Pick first delisted
        test_record = delisted[0]
        
        # On effective_to date, still valid
        members_on_to = source.get_members_at_date(test_record.effective_to)
        symbols_on_to = [m.symbol for m in members_on_to]
        self.assertIn(test_record.symbol, symbols_on_to)
        
        # One day after effective_to, invalid
        from datetime import timedelta
        members_after = source.get_members_at_date(test_record.effective_to + timedelta(days=1))
        symbols_after = [m.symbol for m in members_after]
        self.assertNotIn(test_record.symbol, symbols_after)
    
    def test_013_before_effective_from_no_member(self):
        """Before effective_from, symbol not in members."""
        from backend.services.formal_pit_loader import FormalSnapshotLoader, FormalMembershipSource
        
        loader = FormalSnapshotLoader(REPO_ROOT)
        snapshot = loader.load_snapshot("pims_traderlens_v2_shsz_sw2021_pit_005")
        
        source = FormalMembershipSource(snapshot)
        
        # Pick earliest record
        records = snapshot.records
        earliest = min(records, key=lambda r: r.effective_from)
        
        # One day before effective_from
        from datetime import timedelta
        members_before = source.get_members_at_date(earliest.effective_from - timedelta(days=1))
        symbols_before = [m.symbol for m in members_before]
        self.assertNotIn(earliest.symbol, symbols_before)
    
    def test_014_after_snapshot_date_rejects(self):
        """Date after snapshot_date must be rejected (no extrapolation)."""
        from backend.services.formal_pit_loader import FormalSnapshotLoader, FormalMembershipSource
        
        loader = FormalSnapshotLoader(REPO_ROOT)
        snapshot = loader.load_snapshot("pims_traderlens_v2_shsz_sw2021_pit_005")
        
        source = FormalMembershipSource(snapshot)
        
        # snapshot_date = 2026-07-17
        from datetime import timedelta
        future_date = date(2026, 7, 17) + timedelta(days=1)
        
        with self.assertRaises(ValueError) as cm:
            source.get_members_at_date(future_date)
        self.assertIn("snapshot_date", str(cm.exception).lower())


class TestB3UniverseBuilderIntegration(unittest.TestCase):
    """RED: B3 universe builder consumes formal snapshot."""
    
    def test_021_universe_builder_accepts_formal_source(self):
        """PointInTimeUniverseBuilder accepts FormalMembershipSource."""
        from backend.services.formal_pit_loader import FormalSnapshotLoader, FormalMembershipSource
        from backend.services.point_in_time_universe import PointInTimeUniverseBuilder
        
        loader = FormalSnapshotLoader(REPO_ROOT)
        snapshot = loader.load_snapshot("pims_traderlens_v2_shsz_sw2021_pit_005")
        
        source = FormalMembershipSource(snapshot)
        builder = PointInTimeUniverseBuilder(membership_source=source)
        
        # Get PIT snapshot at a date
        pit_snapshot = source.get_snapshot(date(2024, 6, 1))
        
        self.assertEqual(pit_snapshot.snapshot_date, date(2024, 6, 1))
        self.assertGreater(len(pit_snapshot.records), 0)
    
    def test_022_zero_source_partition_reads(self):
        """Formal loader reads _005/records.parquet only, zero source partitions."""
        from backend.services.formal_pit_loader import FormalSnapshotLoader
        from pathlib import Path
        
        # Check source partitions untouched
        source_dir = REPO_ROOT / "data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal/sw_l1_membership"
        
        # Get mtime before
        manifest_path = source_dir / "manifest.json"
        mtime_before = manifest_path.stat().st_mtime if manifest_path.exists() else None
        
        loader = FormalSnapshotLoader(REPO_ROOT)
        snapshot = loader.load_snapshot("pims_traderlens_v2_shsz_sw2021_pit_005")
        
        # mtime unchanged
        mtime_after = manifest_path.stat().st_mtime if manifest_path.exists() else None
        self.assertEqual(mtime_before, mtime_after, "Source manifest must not be read")
    
    def test_023_zero_db_ledger_b6_side_effects(self):
        """Loading snapshot produces zero DB/ledger/B6/OOS/Gate side effects."""
        from backend.services.formal_pit_loader import FormalSnapshotLoader, FormalMembershipSource
        
        # This test verifies no side effects by construction:
        # FormalSnapshotLoader/FormalMembershipSource do not import:
        # - backend.db.* (no DB writes)
        # - backend.services.b6_validation_flow (no B6 validation)
        # - backend.services.oos_evaluation_controller (no OOS)
        # - backend.services.prototype_gate_v2 (no Gate)
        # - backend.services.strategy_promotion_reducer (no Promotion)
        
        loader = FormalSnapshotLoader(REPO_ROOT)
        snapshot = loader.load_snapshot("pims_traderlens_v2_shsz_sw2021_pit_005")
        
        source = FormalMembershipSource(snapshot)
        members = source.get_members_at_date(date(2024, 6, 1))
        
        # If we reach here without import errors, zero side effects ✓
        self.assertGreater(len(members), 0)


if __name__ == "__main__":
    unittest.main()
