"""Test schema migration from old to new oos_evaluation_ledgers structure."""
import json
import sqlite3
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from backend.db.migrations.migration_001_add_hypothesis_to_audit import (
    migrate_oos_evaluation_ledgers_add_hypothesis,
)


class TestOOSLedgerMigration(unittest.TestCase):
    """Test migration from UNIQUE(theme_id, ledger_version) to UNIQUE(theme, hypo, version)."""
    
    def setUp(self):
        self.tmpfile = tempfile.NamedTemporaryFile(mode='w', suffix='.db', delete=False)
        self.tmpfile.close()
        self.db_path = Path(self.tmpfile.name)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
    
    def tearDown(self):
        self.conn.close()
        if self.db_path.exists():
            self.db_path.unlink()
    
    def _create_old_schema(self):
        """Create old schema with UNIQUE(theme_id, ledger_version)."""
        self.conn.executescript("""
            CREATE TABLE oos_evaluation_ledgers (
                ledger_snapshot_id TEXT PRIMARY KEY,
                theme_id TEXT NOT NULL,
                ledger_version INTEGER NOT NULL,
                payload_json TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                UNIQUE (theme_id, ledger_version)
            );
            
            CREATE TRIGGER prevent_oos_evaluation_ledgers_update
            BEFORE UPDATE ON oos_evaluation_ledgers
            BEGIN
                SELECT RAISE(ABORT, 'oos_evaluation_ledgers is append-only');
            END;
            
            CREATE TRIGGER prevent_oos_evaluation_ledgers_delete
            BEFORE DELETE ON oos_evaluation_ledgers
            BEGIN
                SELECT RAISE(ABORT, 'oos_evaluation_ledgers is append-only');
            END;
        """)
        self.conn.commit()
    
    def _insert_old_record(self, ledger_snapshot_id, theme_id, hypothesis_id, ledger_version):
        """Insert record in old schema format."""
        payload = {
            "ledger_snapshot_id": ledger_snapshot_id,
            "theme_id": theme_id,
            "hypothesis_source_snapshot_id": hypothesis_id,
            "ledger_version": ledger_version,
            "oos_evaluation_count": ledger_version,
            "oos_budget_limit": 3,
            "next_oos_draw_index": ledger_version + 1,
            "budget_status": "available",
            "completed_evaluation_ids": (),
            "active_reservation_ids": (),
            "report_ids": (),
            "recorded_at": datetime.now().isoformat(),
            "frozen": True,
        }
        self.conn.execute(
            "INSERT INTO oos_evaluation_ledgers (ledger_snapshot_id, theme_id, ledger_version, payload_json, recorded_at) VALUES (?, ?, ?, ?, ?)",
            (ledger_snapshot_id, theme_id, ledger_version, json.dumps(payload), datetime.now().isoformat())
        )
        self.conn.commit()
        return json.dumps(payload)
    
    def test_fresh_schema_has_new_structure(self):
        """Fresh schema has hypothesis_source_snapshot_id column."""
        self.conn.executescript("""
            CREATE TABLE oos_evaluation_ledgers (
                ledger_snapshot_id TEXT PRIMARY KEY,
                theme_id TEXT NOT NULL,
                hypothesis_source_snapshot_id TEXT NOT NULL,
                ledger_version INTEGER NOT NULL,
                payload_json TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                UNIQUE (theme_id, hypothesis_source_snapshot_id, ledger_version)
            )
        """)
        self.conn.commit()
        
        # Check columns
        cursor = self.conn.execute("PRAGMA table_info(oos_evaluation_ledgers)")
        columns = [row[1] for row in cursor.fetchall()]
        assert "hypothesis_source_snapshot_id" in columns
        
        # Check constraint
        cursor = self.conn.execute("PRAGMA index_list(oos_evaluation_ledgers)")
        found_new_unique = False
        for row in cursor.fetchall():
            cursor2 = self.conn.execute(f"PRAGMA index_info({row[1]})")
            idx_cols = [r[2] for r in cursor2.fetchall()]
            if sorted(idx_cols) == sorted(["theme_id", "hypothesis_source_snapshot_id", "ledger_version"]):
                found_new_unique = True
        assert found_new_unique
    
    def test_migration_from_old_schema(self):
        """Old schema migrates to new schema."""
        self._create_old_schema()
        
        # Insert old records - must use different versions due to old UNIQUE constraint
        payload1 = self._insert_old_record("snap1", "theme_A", "hypo_001", 1)
        payload2 = self._insert_old_record("snap2", "theme_A", "hypo_002", 2)  # Different version in old schema
        
        # Verify old constraint exists
        cursor = self.conn.execute("PRAGMA index_list(oos_evaluation_ledgers)")
        old_unique_exists = False
        for row in cursor.fetchall():
            cursor2 = self.conn.execute(f"PRAGMA index_info({row[1]})")
            idx_cols = [r[2] for r in cursor2.fetchall()]
            if idx_cols == ["theme_id", "ledger_version"]:
                old_unique_exists = True
        assert old_unique_exists, "Old UNIQUE constraint should exist before migration"
        
        # Run migration
        migrate_oos_evaluation_ledgers_add_hypothesis(self.conn)
        
        # Verify new schema
        cursor = self.conn.execute("PRAGMA table_info(oos_evaluation_ledgers)")
        columns = [row[1] for row in cursor.fetchall()]
        assert "hypothesis_source_snapshot_id" in columns
        
        # Verify old constraint removed
        cursor = self.conn.execute("PRAGMA index_list(oos_evaluation_ledgers)")
        old_still_exists = False
        for row in cursor.fetchall():
            cursor2 = self.conn.execute(f"PRAGMA index_info({row[1]})")
            idx_cols = [r[2] for r in cursor2.fetchall()]
            if idx_cols == ["theme_id", "ledger_version"]:
                old_still_exists = True
        assert not old_still_exists, "Old UNIQUE(theme_id, ledger_version) should be removed"
        
        # Verify records preserved
        cursor = self.conn.execute("SELECT COUNT(*) FROM oos_evaluation_ledgers")
        assert cursor.fetchone()[0] == 2
        
        # Verify payload_json preserved
        cursor = self.conn.execute("SELECT ledger_snapshot_id, payload_json FROM oos_evaluation_ledgers ORDER BY ledger_snapshot_id")
        rows = cursor.fetchall()
        assert rows[0][1] == payload1
        assert rows[1][1] == payload2
        
        # Verify hypothesis extracted
        cursor = self.conn.execute("SELECT hypothesis_source_snapshot_id FROM oos_evaluation_ledgers WHERE ledger_snapshot_id='snap1'")
        assert cursor.fetchone()[0] == "hypo_001"
    
    def test_migration_allows_same_version_different_hypothesis(self):
        """After migration, same theme can have multiple hypotheses with same version."""
        self._create_old_schema()
        # Old schema: must use different versions
        self._insert_old_record("snap1", "theme_A", "hypo_001", 1)
        self._insert_old_record("snap2", "theme_B", "hypo_002", 1)  # Different theme to avoid old constraint
        
        migrate_oos_evaluation_ledgers_add_hypothesis(self.conn)
        
        # NOW can insert same version for different hypothesis under same theme
        self.conn.execute(
            "INSERT INTO oos_evaluation_ledgers (ledger_snapshot_id, theme_id, hypothesis_source_snapshot_id, ledger_version, payload_json, recorded_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("snap3", "theme_A", "hypo_003", 1, "{}", datetime.now().isoformat())
        )
        self.conn.commit()
        
        # Verify both exist
        cursor = self.conn.execute(
            "SELECT COUNT(*) FROM oos_evaluation_ledgers WHERE theme_id='theme_A' AND ledger_version=1"
        )
        assert cursor.fetchone()[0] == 2  # snap1 (hypo_001) and snap3 (hypo_003)
    
    def test_migration_rejects_duplicate_owner_version(self):
        """After migration, duplicate (theme, hypothesis, version) is rejected."""
        self._create_old_schema()
        self._insert_old_record("snap1", "theme_A", "hypo_001", 1)
        
        migrate_oos_evaluation_ledgers_add_hypothesis(self.conn)
        
        # Try to insert duplicate
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO oos_evaluation_ledgers (ledger_snapshot_id, theme_id, hypothesis_source_snapshot_id, ledger_version, payload_json, recorded_at) VALUES (?, ?, ?, ?, ?, ?)",
                ("snap_dup", "theme_A", "hypo_001", 1, "{}", datetime.now().isoformat())
            )
    
    def test_migration_preserves_immutable_triggers(self):
        """After migration, UPDATE and DELETE still blocked."""
        self._create_old_schema()
        self._insert_old_record("snap1", "theme_A", "hypo_001", 1)
        
        migrate_oos_evaluation_ledgers_add_hypothesis(self.conn)
        
        # Try UPDATE
        with self.assertRaises(sqlite3.IntegrityError) as ctx:
            self.conn.execute("UPDATE oos_evaluation_ledgers SET ledger_version=99 WHERE ledger_snapshot_id='snap1'")
        assert "append-only" in str(ctx.exception)
        
        # Try DELETE
        with self.assertRaises(sqlite3.IntegrityError) as ctx:
            self.conn.execute("DELETE FROM oos_evaluation_ledgers WHERE ledger_snapshot_id='snap1'")
        assert "append-only" in str(ctx.exception)
    
    def test_migration_rollback_on_missing_hypothesis(self):
        """Migration fails and rolls back if hypothesis_source_snapshot_id missing."""
        self._create_old_schema()
        
        # Insert record without hypothesis in payload
        bad_payload = {"ledger_snapshot_id": "snap_bad", "theme_id": "theme_X"}
        self.conn.execute(
            "INSERT INTO oos_evaluation_ledgers (ledger_snapshot_id, theme_id, ledger_version, payload_json, recorded_at) VALUES (?, ?, ?, ?, ?)",
            ("snap_bad", "theme_X", 1, json.dumps(bad_payload), datetime.now().isoformat())
        )
        self.conn.commit()
        
        # Migration should fail
        with self.assertRaises(ValueError):
            migrate_oos_evaluation_ledgers_add_hypothesis(self.conn)
        
        # Old table should still exist
        cursor = self.conn.execute("SELECT COUNT(*) FROM oos_evaluation_ledgers")
        assert cursor.fetchone()[0] == 1
        
        # Old schema intact
        cursor = self.conn.execute("PRAGMA table_info(oos_evaluation_ledgers)")
        columns = [row[1] for row in cursor.fetchall()]
        assert "hypothesis_source_snapshot_id" not in columns
    
    def test_migration_idempotent(self):
        """Running migration twice is safe."""
        self._create_old_schema()
        self._insert_old_record("snap1", "theme_A", "hypo_001", 1)
        
        migrate_oos_evaluation_ledgers_add_hypothesis(self.conn)
        migrate_oos_evaluation_ledgers_add_hypothesis(self.conn)  # Second call
        
        cursor = self.conn.execute("SELECT COUNT(*) FROM oos_evaluation_ledgers")
        assert cursor.fetchone()[0] == 1


if __name__ == "__main__":
    unittest.main()
