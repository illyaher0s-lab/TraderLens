import unittest
from datetime import date

from backend.services.data_snapshot_manifest import DataSnapshotManifestBuilder
from backend.services.b3_protocol_types import DataSnapshotManifest


class TestDataSnapshotManifest(unittest.TestCase):
    def setUp(self):
        self.builder = DataSnapshotManifestBuilder()

    def test_same_manifest_inputs_same_hash(self):
        """Same semantic inputs must produce identical hash."""
        manifest1 = DataSnapshotManifest(
            data_snapshot_id="snap_001",
            data_snapshot_hash="placeholder",
            created_at=date(2024, 1, 1),
            market_data_fingerprint="mkt_fp_001",
            daily_status_fingerprint="status_fp_001",
            membership_fingerprint="member_fp_001",
            quality_status="ok",
            gaps=(),
        )
        
        manifest2 = DataSnapshotManifest(
            data_snapshot_id="snap_001",
            data_snapshot_hash="placeholder",
            created_at=date(2024, 1, 2),  # Different runtime metadata
            market_data_fingerprint="mkt_fp_001",
            daily_status_fingerprint="status_fp_001",
            membership_fingerprint="member_fp_001",
            quality_status="ok",
            gaps=(),
        )
        
        hash1 = self.builder.compute_hash(manifest1)
        hash2 = self.builder.compute_hash(manifest2)
        
        self.assertEqual(hash1, hash2)

    def test_market_data_fingerprint_changes_hash(self):
        """Changing market data fingerprint must change hash."""
        manifest1 = DataSnapshotManifest(
            data_snapshot_id="snap_001",
            data_snapshot_hash="placeholder",
            created_at=date(2024, 1, 1),
            market_data_fingerprint="mkt_fp_001",
            daily_status_fingerprint="status_fp_001",
            membership_fingerprint="member_fp_001",
            quality_status="ok",
            gaps=(),
        )
        
        manifest2 = DataSnapshotManifest(
            data_snapshot_id="snap_001",
            data_snapshot_hash="placeholder",
            created_at=date(2024, 1, 1),
            market_data_fingerprint="mkt_fp_002",  # Changed
            daily_status_fingerprint="status_fp_001",
            membership_fingerprint="member_fp_001",
            quality_status="ok",
            gaps=(),
        )
        
        hash1 = self.builder.compute_hash(manifest1)
        hash2 = self.builder.compute_hash(manifest2)
        
        self.assertNotEqual(hash1, hash2)

    def test_daily_status_fingerprint_changes_hash(self):
        """Changing daily status fingerprint must change hash."""
        manifest1 = DataSnapshotManifest(
            data_snapshot_id="snap_001",
            data_snapshot_hash="placeholder",
            created_at=date(2024, 1, 1),
            market_data_fingerprint="mkt_fp_001",
            daily_status_fingerprint="status_fp_001",
            membership_fingerprint="member_fp_001",
            quality_status="ok",
            gaps=(),
        )
        
        manifest2 = DataSnapshotManifest(
            data_snapshot_id="snap_001",
            data_snapshot_hash="placeholder",
            created_at=date(2024, 1, 1),
            market_data_fingerprint="mkt_fp_001",
            daily_status_fingerprint="status_fp_002",  # Changed
            membership_fingerprint="member_fp_001",
            quality_status="ok",
            gaps=(),
        )
        
        hash1 = self.builder.compute_hash(manifest1)
        hash2 = self.builder.compute_hash(manifest2)
        
        self.assertNotEqual(hash1, hash2)

    def test_membership_fingerprint_changes_hash(self):
        """Changing membership snapshot must change hash."""
        manifest1 = DataSnapshotManifest(
            data_snapshot_id="snap_001",
            data_snapshot_hash="placeholder",
            created_at=date(2024, 1, 1),
            market_data_fingerprint="mkt_fp_001",
            daily_status_fingerprint="status_fp_001",
            membership_fingerprint="member_fp_001",
            quality_status="ok",
            gaps=(),
        )
        
        manifest2 = DataSnapshotManifest(
            data_snapshot_id="snap_001",
            data_snapshot_hash="placeholder",
            created_at=date(2024, 1, 1),
            market_data_fingerprint="mkt_fp_001",
            daily_status_fingerprint="status_fp_001",
            membership_fingerprint="member_fp_002",  # Changed
            quality_status="ok",
            gaps=(),
        )
        
        hash1 = self.builder.compute_hash(manifest1)
        hash2 = self.builder.compute_hash(manifest2)
        
        self.assertNotEqual(hash1, hash2)

    def test_financial_visibility_fingerprint_changes_hash(self):
        """Changing financial visibility snapshot must change hash."""
        manifest1 = DataSnapshotManifest(
            data_snapshot_id="snap_001",
            data_snapshot_hash="placeholder",
            created_at=date(2024, 1, 1),
            market_data_fingerprint="mkt_fp_001",
            daily_status_fingerprint="status_fp_001",
            membership_fingerprint="member_fp_001",
            financial_visibility_fingerprint="fin_fp_001",
            quality_status="ok",
            gaps=(),
        )
        
        manifest2 = DataSnapshotManifest(
            data_snapshot_id="snap_001",
            data_snapshot_hash="placeholder",
            created_at=date(2024, 1, 1),
            market_data_fingerprint="mkt_fp_001",
            daily_status_fingerprint="status_fp_001",
            membership_fingerprint="member_fp_001",
            financial_visibility_fingerprint="fin_fp_002",  # Changed
            quality_status="ok",
            gaps=(),
        )
        
        hash1 = self.builder.compute_hash(manifest1)
        hash2 = self.builder.compute_hash(manifest2)
        
        self.assertNotEqual(hash1, hash2)

    def test_benchmark_fingerprint_changes_hash(self):
        """Changing benchmark data must change hash."""
        manifest1 = DataSnapshotManifest(
            data_snapshot_id="snap_001",
            data_snapshot_hash="placeholder",
            created_at=date(2024, 1, 1),
            market_data_fingerprint="mkt_fp_001",
            daily_status_fingerprint="status_fp_001",
            membership_fingerprint="member_fp_001",
            benchmark_fingerprint="bench_fp_001",
            quality_status="ok",
            gaps=(),
        )
        
        manifest2 = DataSnapshotManifest(
            data_snapshot_id="snap_001",
            data_snapshot_hash="placeholder",
            created_at=date(2024, 1, 1),
            market_data_fingerprint="mkt_fp_001",
            daily_status_fingerprint="status_fp_001",
            membership_fingerprint="member_fp_001",
            benchmark_fingerprint="bench_fp_002",  # Changed
            quality_status="ok",
            gaps=(),
        )
        
        hash1 = self.builder.compute_hash(manifest1)
        hash2 = self.builder.compute_hash(manifest2)
        
        self.assertNotEqual(hash1, hash2)

    def test_runtime_metadata_excluded_from_hash(self):
        """Runtime metadata (created_at, generated_by) must not affect hash."""
        manifest1 = DataSnapshotManifest(
            data_snapshot_id="snap_001",
            data_snapshot_hash="placeholder",
            created_at=date(2024, 1, 1),
            market_data_fingerprint="mkt_fp_001",
            daily_status_fingerprint="status_fp_001",
            membership_fingerprint="member_fp_001",
            generated_by="agent_v1",
            quality_status="ok",
            gaps=(),
        )
        
        manifest2 = DataSnapshotManifest(
            data_snapshot_id="snap_001",
            data_snapshot_hash="placeholder",
            created_at=date(2024, 12, 31),  # Different created_at
            market_data_fingerprint="mkt_fp_001",
            daily_status_fingerprint="status_fp_001",
            membership_fingerprint="member_fp_001",
            generated_by="agent_v2",  # Different generated_by
            quality_status="ok",
            gaps=(),
        )
        
        hash1 = self.builder.compute_hash(manifest1)
        hash2 = self.builder.compute_hash(manifest2)
        
        # Runtime metadata (created_at, generated_by) changes must NOT change hash
        self.assertEqual(hash1, hash2)

    def test_trading_calendar_fingerprint_changes_hash(self):
        """Changing trading calendar must change hash."""
        manifest1 = DataSnapshotManifest(
            data_snapshot_id="snap_001",
            data_snapshot_hash="placeholder",
            created_at=date(2024, 1, 1),
            market_data_fingerprint="mkt_fp_001",
            daily_status_fingerprint="status_fp_001",
            membership_fingerprint="member_fp_001",
            trading_calendar_fingerprint="cal_fp_001",
            quality_status="ok",
            gaps=(),
        )
        
        manifest2 = DataSnapshotManifest(
            data_snapshot_id="snap_001",
            data_snapshot_hash="placeholder",
            created_at=date(2024, 1, 1),
            market_data_fingerprint="mkt_fp_001",
            daily_status_fingerprint="status_fp_001",
            membership_fingerprint="member_fp_001",
            trading_calendar_fingerprint="cal_fp_002",  # Changed
            quality_status="ok",
            gaps=(),
        )
        
        hash1 = self.builder.compute_hash(manifest1)
        hash2 = self.builder.compute_hash(manifest2)
        
        self.assertNotEqual(hash1, hash2)

    def test_delisted_coverage_policy_changes_hash(self):
        """Changing delisted coverage policy must change hash."""
        manifest1 = DataSnapshotManifest(
            data_snapshot_id="snap_001",
            data_snapshot_hash="placeholder",
            created_at=date(2024, 1, 1),
            market_data_fingerprint="mkt_fp_001",
            daily_status_fingerprint="status_fp_001",
            membership_fingerprint="member_fp_001",
            delisted_coverage_policy="strict",
            quality_status="ok",
            gaps=(),
        )
        
        manifest2 = DataSnapshotManifest(
            data_snapshot_id="snap_001",
            data_snapshot_hash="placeholder",
            created_at=date(2024, 1, 1),
            market_data_fingerprint="mkt_fp_001",
            daily_status_fingerprint="status_fp_001",
            membership_fingerprint="member_fp_001",
            delisted_coverage_policy="lenient",  # Changed
            quality_status="ok",
            gaps=(),
        )
        
        hash1 = self.builder.compute_hash(manifest1)
        hash2 = self.builder.compute_hash(manifest2)
        
        self.assertNotEqual(hash1, hash2)

    def test_adjustment_factor_fingerprint_changes_hash(self):
        """Changing adjustment factor must change hash."""
        manifest1 = DataSnapshotManifest(
            data_snapshot_id="snap_001",
            data_snapshot_hash="placeholder",
            created_at=date(2024, 1, 1),
            market_data_fingerprint="mkt_fp_001",
            daily_status_fingerprint="status_fp_001",
            membership_fingerprint="member_fp_001",
            adjustment_factor_fingerprint="adj_fp_001",
            quality_status="ok",
            gaps=(),
        )
        
        manifest2 = DataSnapshotManifest(
            data_snapshot_id="snap_001",
            data_snapshot_hash="placeholder",
            created_at=date(2024, 1, 1),
            market_data_fingerprint="mkt_fp_001",
            daily_status_fingerprint="status_fp_001",
            membership_fingerprint="member_fp_001",
            adjustment_factor_fingerprint="adj_fp_002",  # Changed
            quality_status="ok",
            gaps=(),
        )
        
        hash1 = self.builder.compute_hash(manifest1)
        hash2 = self.builder.compute_hash(manifest2)
        
        self.assertNotEqual(hash1, hash2)

    def test_provider_fingerprints_changes_hash(self):
        """Changing provider fingerprints must change hash."""
        manifest1 = DataSnapshotManifest(
            data_snapshot_id="snap_001",
            data_snapshot_hash="placeholder",
            created_at=date(2024, 1, 1),
            market_data_fingerprint="mkt_fp_001",
            daily_status_fingerprint="status_fp_001",
            membership_fingerprint="member_fp_001",
            provider_fingerprints=("provider_a", "provider_b"),
            quality_status="ok",
            gaps=(),
        )
        
        manifest2 = DataSnapshotManifest(
            data_snapshot_id="snap_001",
            data_snapshot_hash="placeholder",
            created_at=date(2024, 1, 1),
            market_data_fingerprint="mkt_fp_001",
            daily_status_fingerprint="status_fp_001",
            membership_fingerprint="member_fp_001",
            provider_fingerprints=("provider_a", "provider_c"),  # Changed
            quality_status="ok",
            gaps=(),
        )
        
        hash1 = self.builder.compute_hash(manifest1)
        hash2 = self.builder.compute_hash(manifest2)
        
        self.assertNotEqual(hash1, hash2)

    def test_missing_data_gaps_recorded(self):
        """Missing data gaps must be recorded in manifest."""
        manifest = self.builder.build(
            data_snapshot_id="snap_001",
            market_data_fingerprint="mkt_fp_001",
            daily_status_fingerprint="status_fp_001",
            membership_fingerprint="member_fp_001",
            gaps=("missing delisted coverage", "unknown daily status"),
        )
        
        self.assertGreater(len(manifest.gaps), 0)
        self.assertIn("missing delisted coverage", manifest.gaps)

    def test_insufficient_snapshot_blocks_protocol(self):
        """Insufficient snapshot must prevent protocol freeze."""
        manifest = self.builder.build(
            data_snapshot_id="snap_001",
            market_data_fingerprint="mkt_fp_001",
            daily_status_fingerprint="status_fp_001",
            membership_fingerprint="member_fp_001",
            quality_status="insufficient",
            gaps=("critical data missing",),
        )
        
        self.assertEqual(manifest.quality_status, "insufficient")
        # Insufficient must block protocol freeze (tested in Task 7)

    def test_manifest_requires_non_empty_hash(self):
        """Manifest hash must be non-empty for formal protocol."""
        manifest = self.builder.build(
            data_snapshot_id="snap_001",
            market_data_fingerprint="mkt_fp_001",
            daily_status_fingerprint="status_fp_001",
            membership_fingerprint="member_fp_001",
            quality_status="ok",
            gaps=(),
        )
        
        self.assertIsNotNone(manifest.data_snapshot_hash)
        self.assertNotEqual(manifest.data_snapshot_hash, "")
        self.assertGreater(len(manifest.data_snapshot_hash), 0)


if __name__ == "__main__":
    unittest.main()
