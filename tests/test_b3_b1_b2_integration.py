import unittest
import sqlite3
import tempfile
from datetime import date, datetime
from pathlib import Path

from backend.db.strategy import StrategyDB
from backend.services.b3_protocol_types import DataSnapshotManifest, OOSWindowSpec
from backend.services.research_protocol_freezer import ResearchProtocolFreezer
from contracts.strategy import (
    BacktestUniverseSpec,
    StrategyDraft,
    StrategyLifecycleState,
)


class TestB3B1B2Integration(unittest.TestCase):
    def setUp(self):
        # Create temporary database
        self.temp_db = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.db')
        self.temp_db.close()
        self.db_path = Path(self.temp_db.name)
        
        self.db = StrategyDB(str(self.db_path))
        self.freezer = ResearchProtocolFreezer()

    def tearDown(self):
        self.db.conn.close()
        self.db_path.unlink()

    def _create_test_draft_with_deps(self, revision_id="rev_001"):
        """Helper to create draft with all dependencies."""
        # Create universe dependency
        universe = BacktestUniverseSpec(
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
        self.db.store_backtest_universe(universe)
        
        # Create draft
        draft = StrategyDraft(
            strategy_revision_id=revision_id,
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
        
        initial_state = StrategyLifecycleState(
            lifecycle_state_id=f"state_{revision_id}",
            strategy_revision_id=revision_id,
            state_version=1,
            state="draft",
            source_record_id=f"draft_{revision_id}",
            recorded_at=datetime(2024, 1, 1),
            recorded_by="test_agent",
        )
        
        self.db.create_strategy_draft(draft, initial_state)
        return draft, universe

    def _create_test_protocol(self, draft, universe):
        """Helper to create protocol from draft and universe."""
        data_snapshot = DataSnapshotManifest(
            data_snapshot_id="data_001",
            data_snapshot_hash="hash_data_001",
            created_at=date(2024, 1, 1),
            market_data_fingerprint="mkt_fp",
            daily_status_fingerprint="status_fp",
            membership_fingerprint="member_fp",
            quality_status="ok",
            gaps=(),
        )
        
        oos_window = OOSWindowSpec(
            oos_window_rule_id="fixed_ratio_70_30",
            oos_window_start=date(2024, 7, 1),
            oos_window_end=date(2024, 12, 31),
            generated_at=date(2024, 1, 1),
        )
        
        return self.freezer.freeze_protocol(
            strategy_draft=draft,
            universe=universe,
            data_snapshot=data_snapshot,
            oos_window=oos_window,
            gate_criteria_hash="hash_gate",
            frozen_by="test_agent",
            backtest_start=date(2024, 1, 1),
        )

    def test_b2_draft_can_enter_b3_protocol_freeze(self):
        """B2 StrategyDraft can enter B3 protocol preparation."""
        draft, universe = self._create_test_draft_with_deps()
        
        # B3 freeze protocol
        protocol = self._create_test_protocol(draft, universe)
        
        # Verify protocol created
        self.assertIsNotNone(protocol)
        self.assertEqual(protocol.strategy_revision_id, "rev_001")

    def test_b3_stores_protocol_snapshot_append_only(self):
        """B3 can append-only store protocol snapshot."""
        draft, universe = self._create_test_draft_with_deps()
        protocol = self._create_test_protocol(draft, universe)
        
        # Store protocol (append-only)
        self.db.store_protocol_snapshot(protocol)
        
        # Verify stored
        stored = self.db.get_protocol_snapshot(protocol.protocol_snapshot_id)
        self.assertIsNotNone(stored)
        self.assertEqual(stored.protocol_snapshot_id, protocol.protocol_snapshot_id)

    def test_duplicate_protocol_id_cannot_overwrite(self):
        """Duplicate protocol ID must fail (PRIMARY KEY constraint)."""
        draft, universe = self._create_test_draft_with_deps()
        protocol = self._create_test_protocol(draft, universe)
        
        # Store once
        self.db.store_protocol_snapshot(protocol)
        
        # Try to store again with same ID
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.store_protocol_snapshot(protocol)

    def test_protocol_snapshot_cannot_be_updated(self):
        """Protocol snapshot cannot be updated (append-only trigger)."""
        draft, universe = self._create_test_draft_with_deps()
        protocol = self._create_test_protocol(draft, universe)
        
        self.db.store_protocol_snapshot(protocol)
        
        # Try to update
        with self.assertRaises(sqlite3.IntegrityError) as ctx:
            self.db.conn.execute(
                """
                UPDATE research_protocol_snapshots
                SET gate_criteria_hash = 'modified'
                WHERE protocol_snapshot_id = ?
                """,
                (protocol.protocol_snapshot_id,)
            )
            self.db.conn.commit()
        
        self.assertIn("append-only", str(ctx.exception))

    def test_protocol_snapshot_cannot_be_deleted(self):
        """Protocol snapshot cannot be deleted (append-only trigger)."""
        draft, universe = self._create_test_draft_with_deps()
        protocol = self._create_test_protocol(draft, universe)
        
        self.db.store_protocol_snapshot(protocol)
        
        # Try to delete
        with self.assertRaises(sqlite3.IntegrityError) as ctx:
            self.db.conn.execute(
                """
                DELETE FROM research_protocol_snapshots
                WHERE protocol_snapshot_id = ?
                """,
                (protocol.protocol_snapshot_id,)
            )
            self.db.conn.commit()
        
        self.assertIn("append-only", str(ctx.exception))

    def test_b3_can_read_latest_draft_state(self):
        """B3 can read latest draft state but not change it."""
        draft, universe = self._create_test_draft_with_deps()
        
        # B3 can read
        loaded = self.db.get_strategy_draft("rev_001")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.strategy_revision_id, "rev_001")
        
        # B3 cannot modify (append-only trigger)
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.conn.execute(
                """
                UPDATE strategy_drafts
                SET theme_id = 'modified'
                WHERE strategy_revision_id = ?
                """,
                ("rev_001",)
            )
            self.db.conn.commit()


if __name__ == "__main__":
    unittest.main()
