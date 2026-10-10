"""Task 3A Corrective: Real B3 Universe Builder integration RED tests.

Verify FormalMembershipSource implements builder-required interface.
"""
import unittest
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent


class TestFormalSourceBuilderInterface(unittest.TestCase):
    """RED: FormalMembershipSource must implement builder interface."""
    
    def test_001_formal_source_has_records_for_universe(self):
        """FormalMembershipSource must have records_for_universe() method."""
        from backend.services.formal_pit_loader import FormalSnapshotLoader, FormalMembershipSource
        
        loader = FormalSnapshotLoader(REPO_ROOT)
        snapshot = loader.load_snapshot("pims_traderlens_v2_shsz_sw2021_pit_005")
        source = FormalMembershipSource(snapshot)
        
        # Must have method
        self.assertTrue(hasattr(source, "records_for_universe"))
        
        # Must be callable
        self.assertTrue(callable(getattr(source, "records_for_universe")))
    
    def test_002_formal_source_returns_interval_records(self):
        """records_for_universe() returns records with effective_from/to preserved."""
        from backend.services.formal_pit_loader import FormalSnapshotLoader, FormalMembershipSource
        from tests.b1_fixtures import make_backtest_universe
        
        loader = FormalSnapshotLoader(REPO_ROOT)
        snapshot = loader.load_snapshot("pims_traderlens_v2_shsz_sw2021_pit_005")
        source = FormalMembershipSource(snapshot)
        
        universe = make_backtest_universe().model_copy(
            update={"membership_snapshot_ids": (snapshot.snapshot_id,)}
        )
        records = source.records_for_universe(
            universe,
            backtest_start=date(2020, 1, 1),
            backtest_end=date(2024, 12, 31),
        )
        
        # Must return records
        self.assertGreater(len(records), 0)
        
        # Must preserve effective_from/to
        for r in records:
            self.assertIsNotNone(r.effective_from)
            # effective_to can be None (still active)
    
    def test_003_formal_source_rejects_extrapolation(self):
        """backtest_end > snapshot_date must fail/insufficient."""
        from backend.services.formal_pit_loader import FormalSnapshotLoader, FormalMembershipSource
        from tests.b1_fixtures import make_backtest_universe
        
        loader = FormalSnapshotLoader(REPO_ROOT)
        snapshot = loader.load_snapshot("pims_traderlens_v2_shsz_sw2021_pit_005")
        source = FormalMembershipSource(snapshot)
        
        universe = make_backtest_universe()
        
        # snapshot_date = 2026-07-17, request 2026-08-01
        with self.assertRaises((ValueError, AssertionError)):
            source.records_for_universe(
                universe,
                backtest_start=date(2020, 1, 1),
                backtest_end=date(2026, 8, 1),  # > snapshot_date
            )
    
    def test_004_formal_source_allows_historical_window(self):
        """Historical window (backtest_start < snapshot_date) must succeed."""
        from backend.services.formal_pit_loader import FormalSnapshotLoader, FormalMembershipSource
        from tests.b1_fixtures import make_backtest_universe
        
        loader = FormalSnapshotLoader(REPO_ROOT)
        snapshot = loader.load_snapshot("pims_traderlens_v2_shsz_sw2021_pit_005")
        source = FormalMembershipSource(snapshot)
        
        universe = make_backtest_universe()
        
        # Historical window: 2020–2024 (all < snapshot_date 2026-07-17)
        records = source.records_for_universe(
            universe,
            backtest_start=date(2020, 1, 1),
            backtest_end=date(2024, 12, 31),
        )
        
        self.assertGreater(len(records), 0)


class TestBuilderWithFormalSource(unittest.TestCase):
    """RED: PointInTimeUniverseBuilder must accept FormalMembershipSource."""
    
    def test_011_builder_build_membership_snapshot_with_formal_source(self):
        """Builder.build_membership_snapshot() accepts FormalMembershipSource."""
        from backend.services.formal_pit_loader import FormalSnapshotLoader, FormalMembershipSource
        from backend.services.point_in_time_universe import PointInTimeUniverseBuilder
        from tests.b1_fixtures import make_backtest_universe
        
        loader = FormalSnapshotLoader(REPO_ROOT)
        snapshot = loader.load_snapshot("pims_traderlens_v2_shsz_sw2021_pit_005")
        source = FormalMembershipSource(snapshot)
        
        builder = PointInTimeUniverseBuilder(membership_source=source)
        universe = make_backtest_universe().model_copy(
            update={"membership_snapshot_ids": (snapshot.snapshot_id,)}
        )
        
        # Real builder call
        pit_snapshot = builder.build_membership_snapshot(
            universe,
            backtest_start=date(2020, 1, 1),
            backtest_end=date(2024, 12, 31),
        )
        
        self.assertEqual(pit_snapshot.snapshot_date, date(2020, 1, 1))
        self.assertGreater(len(pit_snapshot.records), 0)
        self.assertEqual(pit_snapshot.quality_status, "ok")
        self.assertEqual(pit_snapshot.snapshot_id, snapshot.snapshot_id)
    
    def test_012_builder_rejects_future_extrapolation(self):
        """Builder rejects backtest_end > snapshot_date."""
        from backend.services.formal_pit_loader import FormalSnapshotLoader, FormalMembershipSource
        from backend.services.point_in_time_universe import PointInTimeUniverseBuilder
        from tests.b1_fixtures import make_backtest_universe
        
        loader = FormalSnapshotLoader(REPO_ROOT)
        snapshot = loader.load_snapshot("pims_traderlens_v2_shsz_sw2021_pit_005")
        source = FormalMembershipSource(snapshot)
        
        builder = PointInTimeUniverseBuilder(membership_source=source)
        universe = make_backtest_universe()
        
        # Request beyond snapshot_date
        pit_snapshot = builder.build_membership_snapshot(
            universe,
            backtest_start=date(2020, 1, 1),
            backtest_end=date(2026, 8, 1),  # > 2026-07-17
        )
        
        # Must be insufficient
        self.assertEqual(pit_snapshot.quality_status, "insufficient")
        self.assertIn("snapshot_date", " ".join(pit_snapshot.gaps).lower())
    
    def test_013_in_memory_future_backfill_still_rejected(self):
        """InMemoryMembershipSource must still reject future backfill (fail loud)."""
        from backend.services.point_in_time_universe import (
            InMemoryMembershipSource,
            PointInTimeUniverseBuilder,
        )
        from backend.services.b3_protocol_types import UniverseMembershipRecord
        from tests.b1_fixtures import make_backtest_universe
        
        # Current snapshot (2024-12-31)
        current_records = (
            UniverseMembershipRecord(
                symbol="000001.SZ",
                effective_from=date(2020, 1, 1),
                effective_to=None,
                source="current",
                snapshot_id="current",
            ),
        )
        
        source = InMemoryMembershipSource(
            records=current_records,
            source_snapshot_date=date(2024, 12, 31),
        )
        
        builder = PointInTimeUniverseBuilder(membership_source=source)
        universe = make_backtest_universe()
        
        # Backtest 2020 with 2024 snapshot → fail loud (not insufficient)
        with self.assertRaises(ValueError) as cm:
            builder.build_membership_snapshot(
                universe,
                backtest_start=date(2020, 1, 1),
                backtest_end=date(2020, 12, 31),
            )
        
        error_msg = str(cm.exception).lower()
        self.assertIn("future", error_msg)


class TestLoaderArtifactOnlyVerification(unittest.TestCase):
    """RED: Loader runtime must not read source partitions."""
    
    def test_021_loader_zero_source_partition_reads(self):
        """Loader reads _005 artifact only, zero source partition reads."""
        from backend.services.formal_pit_loader import FormalSnapshotLoader
        import pyarrow.parquet as pq
        from unittest.mock import patch
        
        loader = FormalSnapshotLoader(REPO_ROOT)
        
        # Trap source partition reads
        original_read_table = pq.read_table
        source_reads = []
        
        def trapped_read_table(path, **kwargs):
            path_str = str(path)
            # Allow _005 artifact reads
            if "pims_traderlens_v2_shsz_sw2021_pit_005" in path_str:
                return original_read_table(path, **kwargs)
            # Block source partition reads
            if "tushare/.staging" in path_str or "sw_l1_membership" in path_str:
                source_reads.append(path_str)
                raise RuntimeError(f"TRAP: Source partition read blocked: {path_str}")
            return original_read_table(path, **kwargs)
        
        with patch("pyarrow.parquet.read_table", side_effect=trapped_read_table):
            snapshot = loader.load_snapshot("pims_traderlens_v2_shsz_sw2021_pit_005")
        
        # Zero source reads
        self.assertEqual(len(source_reads), 0, f"Source reads detected: {source_reads}")
        self.assertGreater(len(snapshot.records), 0)


if __name__ == "__main__":
    unittest.main()
