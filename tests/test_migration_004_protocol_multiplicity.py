from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

from backend.db.strategy import StrategyDB
from contracts.strategy import (
    BacktestUniverseSpec,
    ImmutableBacktestReport,
    ResearchProtocolSnapshot,
    StrategyDraft,
    StrategyLifecycleState,
    compute_b6_protocol_id_from_fields,
)


def _draft(db: StrategyDB, revision: str = "revision_001") -> None:
    universe = BacktestUniverseSpec(
        universe_spec_id=f"universe_{revision}",
        universe_rule_type="point_in_time_membership",
        membership_source="synthetic",
        membership_effective_from=date(2020, 1, 1),
        membership_effective_to=date(2026, 1, 1),
        snapshot_date=date(2026, 1, 1),
        membership_snapshot_ids=(f"membership_{revision}",),
        quality_status="ok",
    )
    db.store_backtest_universe(universe)
    draft = StrategyDraft(
        strategy_revision_id=revision,
        theme_id="theme_001",
        hypothesis_id="hypothesis_001",
        strategy_template_id="template_001",
        strategy_template_version="v1",
        strategy_template_hash="template_hash",
        hypothesis_source_snapshot_id="hypothesis_snapshot_001",
        backtest_universe_spec_id=universe.universe_spec_id,
        strategy_config_json="{}",
        sample_split_rule_id="split_001",
        created_at=datetime(2026, 1, 1),
    )
    state = StrategyLifecycleState(
        lifecycle_state_id=f"state_{revision}",
        strategy_revision_id=revision,
        state_version=1,
        state="draft",
        source_record_id="initial",
        recorded_at=datetime(2026, 1, 1),
        recorded_by="test",
    )
    db.create_strategy_draft(draft, state)


def _protocol(
    revision: str = "revision_001",
    variant: str = "one",
    universe_id: str | None = None,
) -> ResearchProtocolSnapshot:
    data = {
        "protocol_snapshot_id": "placeholder",
        "theme_id": "theme_001",
        "hypothesis_source_snapshot_id": "hypothesis_snapshot_001",
        "strategy_revision_id": revision,
        "sample_split_rule_id": "split_001",
        "oos_window_rule_id": "fixed_ratio_70_30",
        "oos_window_rule_params_json": "{}",
        "oos_window_start": date(2024, 1, 1),
        "oos_window_end": date(2024, 12, 31),
        "shared_oos_window_id": "window_001",
        "backtest_universe_spec_id": universe_id or f"universe_{revision}",
        "data_snapshot_id": "data_snapshot_001",
        "kill_criteria_snapshot_id": "kill_001",
        "prototype_gate_thresholds_json": '{"threshold":0.5}',
        "strategy_config_hash": "strategy_config_001",
        "data_snapshot_hash": "data_hash_001",
        "gate_criteria_hash": "gate_hash_001",
        "frozen_at": datetime(2026, 1, 1),
        "frozen_by": "test",
        "protocol_profile": "b6_coverage_bound",
        "availability_successor_id": "successor_001",
        "availability_successor_manifest_hash": "successor_manifest_hash",
        "availability_successor_algorithm_hash": "successor_algorithm_hash",
        "predecessor_qualification_id": "predecessor_001",
        "predecessor_qualification_manifest_hash": "predecessor_manifest_hash",
        "predecessor_qualification_status": "availability_bounded_qualified",
        "predecessor_qualification_algorithm_hash": "predecessor_algorithm_hash",
        "coverage_package_id": "coverage_001",
        "coverage_manifest_hash": "coverage_manifest_hash",
        "coverage_algorithm_hash": "coverage_algorithm_hash",
        "source_scope_hash": "source_scope_hash",
        "data_requirements_hash": "data_requirements_hash",
        "expected_stock_days": 1000,
        "complete_stock_days": 900,
        "unavailable_stock_days": 100,
        "gate_snapshot_id": "gate_001",
        "gate_content_hash": "gate_content_hash_001" if variant == "one" else "gate_content_hash_002",
        "kill_content_hash": "kill_content_hash_001",
    }
    data["protocol_snapshot_id"] = compute_b6_protocol_id_from_fields(
        **{key: value for key, value in data.items() if key not in {"protocol_snapshot_id", "frozen_at", "frozen_by", "frozen"}}
    )
    return ResearchProtocolSnapshot(**data)


class TestMigration004ProtocolMultiplicity(unittest.TestCase):
    def test_migration_004_allows_two_same_revision_profile_protocols(self):
        with tempfile.TemporaryDirectory() as raw_tmp:
            db = StrategyDB(str(Path(raw_tmp) / "fresh.db"))
            try:
                _draft(db)
                db.store_protocol_snapshot(_protocol(variant="one"))
                db.store_protocol_snapshot(_protocol(variant="two"))
                self.assertEqual(
                    db.conn.execute(
                        "SELECT COUNT(*) FROM research_protocol_snapshots WHERE strategy_revision_id = ? AND protocol_profile = ?",
                        ("revision_001", "b6_coverage_bound"),
                    ).fetchone()[0],
                    2,
                )
                indexes = {
                    row[0]
                    for row in db.conn.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = 'research_protocol_snapshots'"
                    )
                }
                self.assertNotIn("uq_protocol_b6_profile_per_revision", indexes)
                self.assertIn("idx_protocol_b6_profile_per_revision", indexes)
            finally:
                db.close()

    def test_upgrade_preserves_rows_and_report_foreign_key(self):
        with tempfile.TemporaryDirectory() as raw_tmp:
            db_path = Path(raw_tmp) / "upgrade.db"
            db = StrategyDB(str(db_path))
            _draft(db)
            protocol = _protocol(variant="one")
            db.store_protocol_snapshot(protocol)
            db.conn.execute(
                "INSERT INTO immutable_backtest_reports "
                "(report_id,strategy_revision_id,protocol_snapshot_id,payload_json,report_hash,integrity_status,generated_at) "
                "VALUES (?,?,?,?,?,?,?)",
                ("report_001", "revision_001", protocol.protocol_snapshot_id, "{}", "report_hash_001", "valid", "2026-01-01T00:00:00"),
            )
            db.conn.commit()
            db.close()

            legacy_conn = sqlite3.connect(str(db_path))
            existing_indexes = {
                row[0]
                for row in legacy_conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='index'"
                )
            }
            if "idx_protocol_b6_profile_per_revision" in existing_indexes:
                legacy_conn.execute("DROP INDEX idx_protocol_b6_profile_per_revision")
            if "uq_protocol_b6_profile_per_revision" in existing_indexes:
                legacy_conn.execute("DROP INDEX uq_protocol_b6_profile_per_revision")
            legacy_conn.execute(
                "CREATE UNIQUE INDEX uq_protocol_b6_profile_per_revision "
                "ON research_protocol_snapshots(strategy_revision_id, protocol_profile) "
                "WHERE protocol_profile = 'b6_coverage_bound'"
            )
            legacy_conn.commit()
            legacy_conn.close()

            upgraded = StrategyDB(str(db_path))
            try:
                self.assertEqual(upgraded.conn.execute("SELECT COUNT(*) FROM research_protocol_snapshots").fetchone()[0], 1)
                self.assertEqual(upgraded.conn.execute("SELECT COUNT(*) FROM immutable_backtest_reports").fetchone()[0], 1)
                self.assertEqual(upgraded.conn.execute("PRAGMA foreign_key_check").fetchall(), [])
                self.assertIsNotNone(upgraded.get_protocol_snapshot(protocol.protocol_snapshot_id))
                self.assertNotIn(
                    "uq_protocol_b6_profile_per_revision",
                    {row[0] for row in upgraded.conn.execute("SELECT name FROM sqlite_master WHERE type='index'")},
                )
            finally:
                upgraded.close()

    def test_strict_revision_profile_lookup_has_unavailable_exact_and_ambiguous_states(self):
        from backend.db.strategy import ProtocolSnapshotLookupError

        with tempfile.TemporaryDirectory() as raw_tmp:
            db = StrategyDB(str(Path(raw_tmp) / "lookup.db"))
            try:
                _draft(db)
                with self.assertRaisesRegex(ProtocolSnapshotLookupError, "protocol_snapshot_unavailable"):
                    db.get_protocol_snapshot_by_revision_profile("revision_001", "b6_coverage_bound")
                first = _protocol(variant="one")
                db.store_protocol_snapshot(first)
                self.assertEqual(
                    db.get_protocol_snapshot_by_revision_profile("revision_001", "b6_coverage_bound").protocol_snapshot_id,
                    first.protocol_snapshot_id,
                )
                db.store_protocol_snapshot(_protocol(variant="two"))
                with self.assertRaisesRegex(ProtocolSnapshotLookupError, "protocol_snapshot_ambiguous"):
                    db.get_protocol_snapshot_by_revision_profile("revision_001", "b6_coverage_bound")
            finally:
                db.close()

    def test_same_protocol_id_payload_conflict_is_owned_by_primary_key(self):
        with tempfile.TemporaryDirectory() as raw_tmp:
            db = StrategyDB(str(Path(raw_tmp) / "conflict.db"))
            try:
                _draft(db)
                protocol = _protocol(variant="one")
                self.assertEqual(db.store_protocol_snapshot_exact(protocol), "created")
                conflicting = protocol.model_copy(update={"gate_content_hash": "tampered"})
                with self.assertRaisesRegex(ValueError, "protocol snapshot conflict"):
                    db.store_protocol_snapshot_exact(conflicting)
                self.assertEqual(db.conn.execute("SELECT COUNT(*) FROM research_protocol_snapshots").fetchone()[0], 1)
            finally:
                db.close()

    def test_migration_004_is_idempotent_and_two_connections_preserve_exact_identity(self):
        with tempfile.TemporaryDirectory() as raw_tmp:
            db_path = Path(raw_tmp) / "concurrent.db"
            db1 = StrategyDB(str(db_path))
            db2 = StrategyDB(str(db_path))
            try:
                _draft(db1)
                first = _protocol(variant="one")
                second = _protocol(variant="two")
                self.assertEqual(db1.store_protocol_snapshot_exact(first), "created")
                self.assertEqual(db2.store_protocol_snapshot_exact(first), "reused")
                db2.store_protocol_snapshot(second)
                self.assertEqual(db1.store_protocol_snapshot_exact(second), "reused")
                self.assertEqual(db1.conn.execute("SELECT COUNT(*) FROM research_protocol_snapshots").fetchone()[0], 2)
            finally:
                db2.close()
                db1.close()

    def test_reopen_after_multiplicity_does_not_recreate_historical_unique_index(self):
        with tempfile.TemporaryDirectory() as raw_tmp:
            db_path = Path(raw_tmp) / "reopen.db"
            db = StrategyDB(str(db_path))
            _draft(db)
            db.store_protocol_snapshot(_protocol(variant="one"))
            db.store_protocol_snapshot(_protocol(variant="two"))
            db.close()

            reopened = StrategyDB(str(db_path))
            try:
                self.assertEqual(
                    reopened.conn.execute(
                        "SELECT COUNT(*) FROM research_protocol_snapshots "
                        "WHERE strategy_revision_id = 'revision_001' AND protocol_profile = 'b6_coverage_bound'"
                    ).fetchone()[0],
                    2,
                )
                indexes = {
                    row[0]
                    for row in reopened.conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='research_protocol_snapshots'"
                    )
                }
                self.assertNotIn("uq_protocol_b6_profile_per_revision", indexes)
                self.assertIn("idx_protocol_b6_profile_per_revision", indexes)
            finally:
                reopened.close()

    def test_migration_004_failure_rolls_back_old_index(self):
        from backend.db.migrations.migration_004_allow_protocol_multiplicity import (
            migrate_allow_protocol_multiplicity,
        )

        with tempfile.TemporaryDirectory() as raw_tmp:
            db = StrategyDB(str(Path(raw_tmp) / "rollback.db"))
            db.close()
            conn = sqlite3.connect(str(Path(raw_tmp) / "rollback.db"))
            conn.execute("DROP INDEX IF EXISTS idx_protocol_b6_profile_per_revision")
            conn.execute(
                "CREATE UNIQUE INDEX uq_protocol_b6_profile_per_revision "
                "ON research_protocol_snapshots(strategy_revision_id, protocol_profile) "
                "WHERE protocol_profile = 'b6_coverage_bound'"
            )
            conn.execute("CREATE TABLE idx_protocol_b6_profile_per_revision (marker TEXT)")
            conn.commit()
            with self.assertRaises(sqlite3.OperationalError):
                migrate_allow_protocol_multiplicity(conn)
            indexes = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='research_protocol_snapshots'"
                )
            }
            self.assertIn("uq_protocol_b6_profile_per_revision", indexes)
            self.assertNotIn("idx_protocol_b6_profile_per_revision", indexes)
            conn.close()


if __name__ == "__main__":
    unittest.main()
