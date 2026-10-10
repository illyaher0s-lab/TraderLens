"""
Migration 002 Safety Tests - Real additive migration validation

Tests that migration_002 is safe, additive, and preserves existing data/FKs.
Uses real file-backed SQLite to prove durable behavior.
"""
from __future__ import annotations

import sqlite3
import tempfile
import unittest
import ast
import os
from contextlib import closing
from datetime import datetime, date
from pathlib import Path

from backend.db.strategy import StrategyDB
from contracts.strategy import (
    BacktestUniverseSpec,
    StrategyDraft,
    StrategyLifecycleState,
    ResearchProtocolSnapshot,
)


class TestMigration002Safety(unittest.TestCase):
    """Test migration_002 additive safety and data preservation."""
    
    def setUp(self):
        """Create temporary file-backed DB."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_migration_safety.db"
    
    def tearDown(self):
        """Cleanup."""
        self.temp_dir.cleanup()

    def test_zero_arg_strategydb_callers_are_temp_cwd_guarded(self):
        """Every test-only zero-argument StrategyDB call must be temp-scoped."""
        tests_root = Path(__file__).resolve().parent
        callers = []

        class Visitor(ast.NodeVisitor):
            def __init__(self):
                self.function_name = None

            def visit_FunctionDef(self, node):
                previous = self.function_name
                self.function_name = node.name
                for child in node.body:
                    self.visit(child)
                self.function_name = previous

            def visit_Call(self, node):
                if (
                    isinstance(node.func, ast.Name)
                    and node.func.id == "StrategyDB"
                    and not node.args
                    and not node.keywords
                ):
                    callers.append((Path(__file__), self.function_name, node.lineno))
                self.generic_visit(node)

        for path in tests_root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            Visitor().visit(tree)

        self.assertEqual(
            [(path.name, function_name) for path, function_name, _ in callers],
            [(Path(__file__).name, "test_strategydb_default_is_file_backed")],
        )
        method_source = ast.get_source_segment(
            Path(__file__).read_text(encoding="utf-8"),
            next(
                node
                for node in ast.walk(ast.parse(Path(__file__).read_text(encoding="utf-8")))
                if isinstance(node, ast.FunctionDef)
                and node.name == "test_strategydb_default_is_file_backed"
            ),
        )
        self.assertIn("TemporaryDirectory", method_source)
        self.assertIn("chdir", method_source)
    
    def test_strategydb_default_is_file_backed(self):
        """StrategyDB() default resolves inside a temporary cwd only."""
        production_path = Path(__file__).resolve().parents[1] / "data" / "strategy.db"

        def production_fingerprint():
            stat = production_path.stat()
            uri = f"file:{production_path.as_posix()}?mode=ro"
            with closing(sqlite3.connect(uri, uri=True)) as conn:
                indexes = tuple(
                    conn.execute(
                        "SELECT name, sql FROM sqlite_master "
                        "WHERE type='index' AND tbl_name='research_protocol_snapshots' "
                        "ORDER BY name"
                    )
                )
            return stat.st_mtime_ns, stat.st_size, indexes

        before = production_fingerprint()
        previous_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as raw_tmp:
            temp_root = Path(raw_tmp)
            (temp_root / "data").mkdir()
            db = None
            try:
                os.chdir(temp_root)
                db = StrategyDB()
                result = db.conn.execute("PRAGMA database_list").fetchone()
                db_file = Path(result[2]).resolve()
                self.assertEqual(db_file, (temp_root / "data" / "strategy.db").resolve())
                self.assertTrue(db_file.exists())
            finally:
                if db is not None:
                    db.close()
                os.chdir(previous_cwd)

        after = production_fingerprint()
        self.assertEqual(after, before)
    
    def test_migration_preserves_legacy_protocol_data(self):
        """RED: Migration must preserve existing protocol rows and FKs."""
        # Step 1: Create pre-migration schema (without protocol_profile)
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(
            """
            CREATE TABLE strategy_drafts (
                strategy_revision_id TEXT PRIMARY KEY,
                theme_id TEXT NOT NULL,
                hypothesis_id TEXT NOT NULL,
                backtest_universe_spec_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            
            CREATE TABLE backtest_universe_specs (
                universe_spec_id TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            
            CREATE TABLE research_protocol_snapshots (
                protocol_snapshot_id TEXT PRIMARY KEY,
                strategy_revision_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                strategy_config_hash TEXT NOT NULL,
                data_snapshot_hash TEXT NOT NULL,
                gate_criteria_hash TEXT NOT NULL,
                frozen_at TEXT NOT NULL,
                FOREIGN KEY (strategy_revision_id)
                    REFERENCES strategy_drafts(strategy_revision_id)
            );
            
            CREATE TABLE immutable_backtest_reports (
                report_id TEXT PRIMARY KEY,
                strategy_revision_id TEXT NOT NULL,
                protocol_snapshot_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                report_hash TEXT NOT NULL UNIQUE,
                integrity_status TEXT NOT NULL,
                generated_at TEXT NOT NULL,
                FOREIGN KEY (strategy_revision_id)
                    REFERENCES strategy_drafts(strategy_revision_id),
                FOREIGN KEY (protocol_snapshot_id)
                    REFERENCES research_protocol_snapshots(protocol_snapshot_id)
            );
            """
        )
        
        # Step 2: Insert legacy data
        conn.execute(
            "INSERT INTO backtest_universe_specs VALUES (?, ?, ?)",
            ("universe_legacy", "{}", datetime.now().isoformat())
        )
        conn.execute(
            "INSERT INTO strategy_drafts VALUES (?, ?, ?, ?, ?, ?)",
            ("rev_legacy", "theme_legacy", "hypo_legacy", "universe_legacy", "{}", datetime.now().isoformat())
        )
        conn.execute(
            """
            INSERT INTO research_protocol_snapshots 
            (protocol_snapshot_id, strategy_revision_id, payload_json,
             strategy_config_hash, data_snapshot_hash, gate_criteria_hash, frozen_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("proto_legacy_001", "rev_legacy", '{"test": "legacy"}', 
             "config_hash_legacy", "data_hash_legacy", "gate_hash_legacy",
             datetime.now().isoformat())
        )
        conn.execute(
            """
            INSERT INTO immutable_backtest_reports
            (report_id, strategy_revision_id, protocol_snapshot_id, payload_json,
             report_hash, integrity_status, generated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("report_legacy", "rev_legacy", "proto_legacy_001", "{}", 
             "report_hash_legacy", "valid", datetime.now().isoformat())
        )
        conn.commit()
        
        # Capture pre-migration state
        pre_protocol_count = conn.execute(
            "SELECT COUNT(*) FROM research_protocol_snapshots"
        ).fetchone()[0]
        pre_protocol_row = conn.execute(
            "SELECT * FROM research_protocol_snapshots WHERE protocol_snapshot_id = ?",
            ("proto_legacy_001",)
        ).fetchone()
        pre_report_count = conn.execute(
            "SELECT COUNT(*) FROM immutable_backtest_reports"
        ).fetchone()[0]
        
        conn.close()
        
        # Step 3: Run migration via StrategyDB (which calls migration_002)
        # Expected to FAIL if migration uses DROP TABLE (breaks FK)
        db = StrategyDB(str(self.db_path))
        
        # Step 4: Verify data preservation
        post_protocol_count = db.conn.execute(
            "SELECT COUNT(*) FROM research_protocol_snapshots"
        ).fetchone()[0]
        self.assertEqual(post_protocol_count, pre_protocol_count,
                        "Migration lost protocol rows")
        
        post_protocol_row = db.conn.execute(
            "SELECT * FROM research_protocol_snapshots WHERE protocol_snapshot_id = ?",
            ("proto_legacy_001",)
        ).fetchone()
        self.assertIsNotNone(post_protocol_row, "Migration lost legacy protocol")
        
        # Verify payload/hashes unchanged
        row_dict = dict(post_protocol_row)
        self.assertEqual(row_dict["payload_json"], pre_protocol_row[2])
        self.assertEqual(row_dict["strategy_config_hash"], pre_protocol_row[3])
        self.assertEqual(row_dict["data_snapshot_hash"], pre_protocol_row[4])
        self.assertEqual(row_dict["gate_criteria_hash"], pre_protocol_row[5])
        self.assertEqual(row_dict["frozen_at"], pre_protocol_row[6])
        
        # Verify new profile field exists with default
        self.assertIn("protocol_profile", row_dict.keys())
        self.assertEqual(row_dict["protocol_profile"], "legacy_b3")
        
        # Verify FK integrity
        fk_violations = db.conn.execute("PRAGMA foreign_key_check").fetchall()
        self.assertEqual(len(fk_violations), 0, 
                        f"Migration broke FKs: {fk_violations}")
        
        # Verify inbound FK still works (report → protocol)
        post_report_count = db.conn.execute(
            "SELECT COUNT(*) FROM immutable_backtest_reports"
        ).fetchone()[0]
        self.assertEqual(post_report_count, pre_report_count,
                        "Migration lost reports (FK broken)")
        
        db.close()
    
    def test_migration_idempotent(self):
        """Migration must be idempotent (safe to run multiple times)."""
        # Create minimal pre-migration schema
        conn = sqlite3.connect(str(self.db_path))
        conn.executescript(
            """
            CREATE TABLE research_protocol_snapshots (
                protocol_snapshot_id TEXT PRIMARY KEY,
                strategy_revision_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                strategy_config_hash TEXT NOT NULL,
                data_snapshot_hash TEXT NOT NULL,
                gate_criteria_hash TEXT NOT NULL,
                frozen_at TEXT NOT NULL
            );
            """
        )
        conn.commit()
        conn.close()
        
        # Run migration first time
        db1 = StrategyDB(str(self.db_path))
        columns_after_first = [row[1] for row in db1.conn.execute(
            "PRAGMA table_info(research_protocol_snapshots)"
        )]
        db1.close()
        
        # Run migration second time (idempotent)
        db2 = StrategyDB(str(self.db_path))
        columns_after_second = [row[1] for row in db2.conn.execute(
            "PRAGMA table_info(research_protocol_snapshots)"
        )]
        db2.close()
        
        # Columns should be identical
        self.assertEqual(columns_after_first, columns_after_second)
        self.assertIn("protocol_profile", columns_after_first)
    
    def test_b6_multiplicity_index_after_upgrade(self):
        """Migration 004 replaces the historical unique index with a lookup index."""
        # Create pre-migration schema
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(
            """
            CREATE TABLE strategy_drafts (
                strategy_revision_id TEXT PRIMARY KEY,
                theme_id TEXT,
                hypothesis_id TEXT,
                backtest_universe_spec_id TEXT,
                payload_json TEXT,
                created_at TEXT
            );
            
            CREATE TABLE research_protocol_snapshots (
                protocol_snapshot_id TEXT PRIMARY KEY,
                strategy_revision_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                strategy_config_hash TEXT NOT NULL,
                data_snapshot_hash TEXT NOT NULL,
                gate_criteria_hash TEXT NOT NULL,
                frozen_at TEXT NOT NULL
            );
            """
        )
        conn.execute("INSERT INTO strategy_drafts VALUES (?, ?, ?, ?, ?, ?)",
                    ("rev_001", "theme", "hypo", "universe", "{}", datetime.now().isoformat()))
        conn.commit()
        conn.close()
        
        # Run migration
        db = StrategyDB(str(self.db_path))
        
        # Try to insert two b6_coverage_bound protocols for same revision
        db.conn.execute(
            """
            INSERT INTO research_protocol_snapshots
            (protocol_snapshot_id, strategy_revision_id, payload_json,
             strategy_config_hash, data_snapshot_hash, gate_criteria_hash, 
             frozen_at, protocol_profile)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("proto_001", "rev_001", "{}", "hash_001", "hash_001", "hash_001",
             datetime.now().isoformat(), "b6_coverage_bound")
        )
        db.conn.commit()
        
        db.conn.execute(
            """
            INSERT INTO research_protocol_snapshots
            (protocol_snapshot_id, strategy_revision_id, payload_json,
             strategy_config_hash, data_snapshot_hash, gate_criteria_hash,
             frozen_at, protocol_profile)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("proto_002", "rev_001", "{}", "hash_002", "hash_002", "hash_002",
             datetime.now().isoformat(), "b6_coverage_bound")
        )
        db.conn.commit()
        self.assertEqual(
            db.conn.execute(
                "SELECT COUNT(*) FROM research_protocol_snapshots "
                "WHERE strategy_revision_id = 'rev_001' AND protocol_profile = 'b6_coverage_bound'"
            ).fetchone()[0],
            2,
        )
        indexes = {
            row[0]
            for row in db.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='research_protocol_snapshots'"
            )
        }
        self.assertNotIn("uq_protocol_b6_profile_per_revision", indexes)
        self.assertIn("idx_protocol_b6_profile_per_revision", indexes)
        
        db.close()
    
    def test_reservation_extensions_are_nullable(self):
        """RED: Existing reservations must remain valid with NULL extensions."""
        # Create pre-migration schema with reservation
        conn = sqlite3.connect(str(self.db_path))
        conn.executescript(
            """
            CREATE TABLE oos_budget_state (
                theme_id TEXT NOT NULL,
                hypothesis_source_snapshot_id TEXT NOT NULL,
                consumed_draw_count INTEGER NOT NULL DEFAULT 0,
                next_oos_draw_index INTEGER NOT NULL DEFAULT 1,
                budget_status TEXT NOT NULL DEFAULT 'available',
                active_reservation_id TEXT,
                state_version INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (theme_id, hypothesis_source_snapshot_id)
            );
            
            CREATE TABLE oos_budget_reservations (
                reservation_id TEXT PRIMARY KEY,
                theme_id TEXT NOT NULL,
                hypothesis_source_snapshot_id TEXT NOT NULL,
                strategy_config_hash TEXT NOT NULL,
                data_snapshot_hash TEXT NOT NULL,
                gate_criteria_hash TEXT NOT NULL,
                shared_oos_window_id TEXT NOT NULL,
                oos_draw_index INTEGER NOT NULL,
                status TEXT NOT NULL,
                reserved_at TEXT NOT NULL,
                idempotency_key TEXT NOT NULL
            );
            
            INSERT INTO oos_budget_state VALUES 
            ('theme', 'hypo', 0, 1, 'available', NULL, 1, datetime('now'));
            
            INSERT INTO oos_budget_reservations VALUES
            ('res_legacy', 'theme', 'hypo', 'hash_c', 'hash_d', 'hash_g',
             'window', 1, 'completed', datetime('now'), 'idempotency_legacy');
            """
        )
        conn.commit()
        conn.close()
        
        # Run migration
        db = StrategyDB(str(self.db_path))
        
        # Verify existing reservation still readable
        row = db.conn.execute(
            "SELECT * FROM oos_budget_reservations WHERE reservation_id = ?",
            ("res_legacy",)
        ).fetchone()
        self.assertIsNotNone(row)
        
        row_dict = dict(row)
        # New columns should exist
        self.assertIn("task_key", row_dict.keys())
        self.assertIn("protocol_snapshot_id", row_dict.keys())
        
        # New columns should be NULL for legacy rows
        self.assertIsNone(row_dict["task_key"])
        self.assertIsNone(row_dict["protocol_snapshot_id"])
        
        db.close()


if __name__ == "__main__":
    unittest.main()
