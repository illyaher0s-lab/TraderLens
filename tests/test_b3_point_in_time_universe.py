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


class TestPointInTimeUniverseBuilder(unittest.TestCase):
    def setUp(self):
        from backend.services.point_in_time_universe import (
            PointInTimeUniverseBuilder,
            InMemoryMembershipSource,
        )
        from tests.b1_fixtures import make_backtest_universe
        
        # Create test records with effective date windows
        test_records = (
            UniverseMembershipRecord(
                symbol="000001.SZ",
                effective_from=date(2020, 1, 1),
                effective_to=None,  # Still trading
                source="test_index",
                snapshot_id="test_snap",
            ),
            UniverseMembershipRecord(
                symbol="000002.SZ",
                effective_from=date(2023, 1, 1),
                effective_to=date(2023, 12, 31),  # Delisted
                source="test_index",
                snapshot_id="test_snap",
            ),
            UniverseMembershipRecord(
                symbol="000003.SZ",
                effective_from=date(2025, 1, 1),
                effective_to=None,  # Future listing
                source="test_index",
                snapshot_id="test_snap",
            ),
        )
        
        self.membership_source = InMemoryMembershipSource(
            records=test_records,
            source_snapshot_date=date(2023, 1, 1),
        )
        self.builder = PointInTimeUniverseBuilder(membership_source=self.membership_source)
        self.universe = make_backtest_universe()

    def test_builder_only_accepts_backtest_universe_spec(self):
        """Only BacktestUniverseSpec allowed, not ForwardWatchlistSnapshot or plain list."""
        from contracts.strategy import BacktestUniverseSpec
        
        self.assertIsInstance(self.universe, BacktestUniverseSpec)
        
        # Should not raise
        snapshot = self.builder.build_membership_snapshot(
            self.universe,
            backtest_start=date(2024, 1, 1),
            backtest_end=date(2024, 12, 31),
        )
        self.assertEqual(snapshot.universe_rule_type, "point_in_time_membership")

    def test_builder_rejects_forward_watchlist(self):
        """Forward watchlist must be rejected for formal backtest."""
        from tests.b1_fixtures import make_forward_watchlist
        
        watchlist = make_forward_watchlist()
        is_valid, error = self.builder.validate_universe_input(watchlist)
        self.assertFalse(is_valid)
        self.assertIn("ForwardWatchlist", error)

    def test_rejects_confirmed_candidate_symbol_pool(self):
        """Confirmed candidate pool from A module must be rejected."""
        from contracts.strategy import BacktestUniverseSpec
        
        candidate_pool = BacktestUniverseSpec(
            universe_spec_id="confirmed_candidate_pool_2024",
            universe_rule_type="point_in_time_membership",
            membership_source="a_module_candidates",
            membership_effective_from=date(2024, 1, 1),
            membership_effective_to=date(2024, 12, 31),
            snapshot_date=date(2024, 1, 1),
            membership_snapshot_ids=("snap_001",),
            quality_status="ok",
        )
        
        with self.assertRaises(ValueError) as ctx:
            self.builder.build_membership_snapshot(
                candidate_pool,
                backtest_start=date(2024, 1, 1),
                backtest_end=date(2024, 12, 31),
            )
        
        self.assertIn("Confirmed candidate pool", str(ctx.exception))

    def test_membership_respects_effective_date_window(self):
        """Records must respect effective_from/to window logic."""
        snapshot = self.builder.build_membership_snapshot(
            self.universe,
            backtest_start=date(2024, 1, 1),
            backtest_end=date(2024, 12, 31),
        )
        
        symbols = {r.symbol for r in snapshot.records}
        
        # 000001.SZ: listed 2020, still trading → included
        self.assertIn("000001.SZ", symbols)
        
        # 000002.SZ: delisted 2023-12-31, backtest 2024 → excluded
        self.assertNotIn("000002.SZ", symbols)
        
        # 000003.SZ: listed 2025, backtest 2024 → excluded
        self.assertNotIn("000003.SZ", symbols)

    def test_delisted_stock_present_during_valid_period(self):
        """Delisted stock must appear if backtest period overlaps its valid period."""
        snapshot = self.builder.build_membership_snapshot(
            self.universe,
            backtest_start=date(2023, 6, 1),
            backtest_end=date(2023, 12, 1),
        )
        
        symbols = {r.symbol for r in snapshot.records}
        
        # 000002.SZ valid until 2023-12-31, backtest overlaps → included
        self.assertIn("000002.SZ", symbols)

    def test_stock_absent_before_listing_date(self):
        """Stock must not appear before its effective_from date."""
        # Use a membership source snapshot taken BEFORE the backtest period
        from backend.services.point_in_time_universe import (
            InMemoryMembershipSource,
            PointInTimeUniverseBuilder,
        )
        
        early_records = (
            UniverseMembershipRecord(
                symbol="000001.SZ",
                effective_from=date(2020, 1, 1),
                effective_to=None,
                source="test_index",
                snapshot_id="early_snap",
            ),
            UniverseMembershipRecord(
                symbol="000002.SZ",
                effective_from=date(2023, 1, 1),
                effective_to=date(2023, 12, 31),
                source="test_index",
                snapshot_id="early_snap",
            ),
        )
        
        early_source = InMemoryMembershipSource(
            records=early_records,
            source_snapshot_date=date(2021, 1, 1),  # Before backtest 2022
        )
        
        builder = PointInTimeUniverseBuilder(membership_source=early_source)
        
        snapshot = builder.build_membership_snapshot(
            self.universe,
            backtest_start=date(2022, 1, 1),
            backtest_end=date(2022, 12, 31),
        )
        
        symbols = {r.symbol for r in snapshot.records}
        
        # 000002.SZ listed 2023-01-01, backtest 2022 → excluded
        self.assertNotIn("000002.SZ", symbols)

    def test_stock_absent_after_delisting_date(self):
        """Stock must not appear after its effective_to date."""
        snapshot = self.builder.build_membership_snapshot(
            self.universe,
            backtest_start=date(2024, 1, 1),
            backtest_end=date(2024, 12, 31),
        )
        
        symbols = {r.symbol for r in snapshot.records}
        
        # 000002.SZ delisted 2023-12-31, backtest 2024 → excluded
        self.assertNotIn("000002.SZ", symbols)

    def test_missing_membership_source_is_insufficient(self):
        """Builder without membership source must fail loud."""
        from backend.services.point_in_time_universe import PointInTimeUniverseBuilder
        
        builder_no_source = PointInTimeUniverseBuilder(membership_source=None)
        
        snapshot = builder_no_source.build_membership_snapshot(
            self.universe,
            backtest_start=date(2024, 1, 1),
            backtest_end=date(2024, 12, 31),
        )
        
        self.assertEqual(snapshot.quality_status, "insufficient")
        self.assertGreater(len(snapshot.gaps), 0)
        self.assertEqual(len(snapshot.records), 0)

    def test_current_membership_cannot_backfill_history(self):
        """Membership source snapshot_date > backtest_start must fail."""
        from backend.services.point_in_time_universe import (
            InMemoryMembershipSource,
            PointInTimeUniverseBuilder,
        )
        
        # Current membership snapshot (2024-12-31)
        current_records = (
            UniverseMembershipRecord(
                symbol="000001.SZ",
                effective_from=date(2020, 1, 1),
                effective_to=None,
                source="current_snapshot",
                snapshot_id="current",
            ),
        )
        
        current_source = InMemoryMembershipSource(
            records=current_records,
            source_snapshot_date=date(2024, 12, 31),  # Future relative to backtest
        )
        
        builder = PointInTimeUniverseBuilder(membership_source=current_source)
        
        # Try to backtest in 2023 using 2024 membership → must fail
        with self.assertRaises(ValueError) as ctx:
            builder.build_membership_snapshot(
                self.universe,
                backtest_start=date(2023, 1, 1),
                backtest_end=date(2023, 12, 31),
            )
        
        self.assertIn("backfill history", str(ctx.exception))

    def test_current_sector_membership_cannot_backfill_past(self):
        """Current sector/concept membership must not be used for historical backtest."""
        from backend.services.point_in_time_universe import (
            InMemoryMembershipSource,
            PointInTimeUniverseBuilder,
        )
        
        # Current sector snapshot taken today
        sector_records = (
            UniverseMembershipRecord(
                symbol="000001.SZ",
                effective_from=date(2020, 1, 1),
                effective_to=None,
                source="current_sector_snapshot",
                snapshot_id="sector_2024",
            ),
        )
        
        current_sector = InMemoryMembershipSource(
            records=sector_records,
            source_snapshot_date=date(2024, 6, 1),  # Current
        )
        
        builder = PointInTimeUniverseBuilder(membership_source=current_sector)
        
        # Try to use current sector membership for 2023 backtest → fail
        with self.assertRaises(ValueError) as ctx:
            builder.build_membership_snapshot(
                self.universe,
                backtest_start=date(2023, 1, 1),
                backtest_end=date(2023, 12, 31),
            )
        
        self.assertIn("backfill history", str(ctx.exception))

    def test_no_llm_call_in_universe_builder(self):
        """Universe builder must be deterministic, no LLM."""
        from backend.services import point_in_time_universe
        import inspect
        
        source = inspect.getsource(point_in_time_universe)
        # Check implementation, not docstrings
        lines = [line for line in source.split('\n') if not line.strip().startswith('"') and not line.strip().startswith('#')]
        code_only = '\n'.join(lines).lower()
        
        self.assertNotIn("import llm", code_only)
        self.assertNotIn("from llm", code_only)
        self.assertNotIn("openai", code_only)
        self.assertNotIn("anthropic", code_only)


if __name__ == "__main__":
    unittest.main()
