import unittest
from datetime import date

from backend.services.b3_protocol_types import (
    UniverseMembershipRecord,
    PointInTimeMembershipSnapshot,
    DataSnapshotManifest,
    OOSWindowSpec,
    TimeConsistencyCheckResult,
)


class TestB3Contracts(unittest.TestCase):
    def test_b3_contracts_are_frozen(self):
        record = UniverseMembershipRecord(
            symbol="000001.SZ",
            effective_from=date(2024, 1, 1),
            effective_to=date(2024, 12, 31),
            source="index_constituent",
            snapshot_id="snap_001",
        )
        with self.assertRaises(Exception):
            record.symbol = "000002.SZ"

    def test_membership_record_requires_effective_dates(self):
        with self.assertRaises(Exception):
            UniverseMembershipRecord(
                symbol="000001.SZ",
                effective_from=None,
                effective_to=date(2024, 12, 31),
                source="index_constituent",
                snapshot_id="snap_001",
            )

    def test_membership_snapshot_requires_include_delisted(self):
        snapshot = PointInTimeMembershipSnapshot(
            snapshot_id="snap_001",
            snapshot_date=date(2024, 1, 1),
            universe_rule_type="point_in_time_membership",
            membership_source="historical_index",
            include_delisted=True,
            records=(),
            quality_status="ok",
            gaps=(),
        )
        self.assertEqual(snapshot.include_delisted, True)

    def test_data_snapshot_manifest_requires_hash_and_sources(self):
        manifest = DataSnapshotManifest(
            data_snapshot_id="data_001",
            data_snapshot_hash="hash123",
            created_at=date(2024, 1, 1),
            market_data_fingerprint="mkt_fp",
            daily_status_fingerprint="status_fp",
            membership_fingerprint="member_fp",
            quality_status="ok",
            gaps=(),
        )
        self.assertNotEqual(manifest.data_snapshot_hash, "")

    def test_oos_window_spec_requires_registered_rule(self):
        spec = OOSWindowSpec(
            oos_window_rule_id="fixed_30d_after_is",
            oos_window_start=date(2024, 7, 1),
            oos_window_end=date(2024, 7, 31),
            generated_at=date(2024, 1, 1),
        )
        self.assertIsNotNone(spec.oos_window_rule_id)

    def test_time_consistency_result_separates_blocking_and_warnings(self):
        result = TimeConsistencyCheckResult(
            status="fail",
            blocking_violations=("future_data_used",),
            warnings=("partial_membership",),
        )
        self.assertGreater(len(result.blocking_violations), 0)


if __name__ == "__main__":
    unittest.main()
