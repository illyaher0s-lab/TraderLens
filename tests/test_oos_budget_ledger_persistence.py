"""Durable OOS Budget Ledger Persistence Tests."""
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
import sqlite3

from backend.db.strategy import StrategyDB
from backend.services.oos_budget_ledger import OOSBudgetLedger


class TestOOSBudgetLedgerPersistence(unittest.TestCase):
    """Test DB-backed OOS budget ledger persistence."""
    
    def setUp(self):
        self.tmpfile = tempfile.NamedTemporaryFile(mode='w', suffix='.db', delete=False)
        self.tmpfile.close()
        self.db_path = Path(self.tmpfile.name)
        self.db = StrategyDB(str(self.db_path))
    
    def tearDown(self):
        self.db.close()
        if self.db_path.exists():
            self.db_path.unlink()
    
    def test_absent_owner_read_is_default_and_zero_writes(self):
        """Reading nonexistent owner returns defaults without writing."""
        ledger = OOSBudgetLedger(self.db)
        
        state = ledger.get_ledger_state("theme_001", "hypo_001")
        
        assert state["completed_draw_count"] == 0
        assert state["next_oos_draw_index"] == 1
        assert state["budget_status"] == "available"
        
        # Verify zero writes
        new_db = StrategyDB(str(self.db_path))
        new_ledger = OOSBudgetLedger(new_db)
        state2 = new_ledger.get_ledger_state("theme_001", "hypo_001")
        assert state2["completed_draw_count"] == 0
        new_db.close()
    
    def test_reserve_persists_across_connections(self):
        """Reserved state visible in new StrategyDB connection."""
        ledger = OOSBudgetLedger(self.db)
        
        rsv = ledger.reserve_oos_draw(
            theme_id="theme_001",
            hypothesis_source_snapshot_id="hypo_001",
            strategy_config_hash="config_001",
            data_snapshot_hash="data_001",
            gate_criteria_hash="gate_001",
            shared_oos_window_id="window_001",
            idempotency_key="k1",
        )
        
        assert rsv.status == "reserved"
        assert rsv.oos_draw_index == 1
        
        new_db = StrategyDB(str(self.db_path))
        try:
            new_ledger = OOSBudgetLedger(new_db)
            state = new_ledger.get_ledger_state("theme_001", "hypo_001")
            # Reserve does NOT increment next_oos_draw_index
            assert state["next_oos_draw_index"] == 1
            assert state["completed_draw_count"] == 0
        finally:
            new_db.close()
    
    def test_complete_consumes_draw_and_increments_index(self):
        """Complete consumes draw and increments next_oos_draw_index."""
        ledger = OOSBudgetLedger(self.db)
        
        rsv = ledger.reserve_oos_draw(
            "theme_001", "hypo_001", "config_001", "data_001", "gate_001", "window_001",
            idempotency_key="k2"
        )
        ledger.start_execution(rsv.reservation_id)
        ledger.complete_reservation(rsv.reservation_id, "rejected")
        
        state = ledger.get_ledger_state("theme_001", "hypo_001")
        assert state["completed_draw_count"] == 1
        assert state["next_oos_draw_index"] == 2
        assert state["budget_status"] == "available"
    
    def test_start_then_complete_sequence(self):
        """Start execution, then complete."""
        ledger = OOSBudgetLedger(self.db)
        
        rsv = ledger.reserve_oos_draw(
            "theme_001", "hypo_001", "config_001", "data_001", "gate_001", "window_001",
            idempotency_key="k3"
        )
        ledger.start_execution(rsv.reservation_id)
        ledger.complete_reservation(rsv.reservation_id, "approved")
        
        state = ledger.get_ledger_state("theme_001", "hypo_001")
        assert state["completed_draw_count"] == 1
        assert state["next_oos_draw_index"] == 2
    
    def test_release_pre_execution_does_not_consume_draw(self):
        """Release before start does NOT consume draw."""
        ledger = OOSBudgetLedger(self.db)
        
        rsv = ledger.reserve_oos_draw(
            "theme_001", "hypo_001", "config_001", "data_001", "gate_001", "window_001",
            idempotency_key="k4"
        )
        ledger.release_pre_execution(rsv.reservation_id, "infra_failure")
        
        state = ledger.get_ledger_state("theme_001", "hypo_001")
        assert state["completed_draw_count"] == 0
        assert state["next_oos_draw_index"] == 1  # not incremented
        
        # Can reserve again with same index
        rsv2 = ledger.reserve_oos_draw(
            "theme_001", "hypo_001", "config_002", "data_001", "gate_001", "window_001",
            idempotency_key="k5"
        )
        assert rsv2.oos_draw_index == 1
    
    def test_fail_after_start_consumes_draw(self):
        """Fail after start consumes draw."""
        ledger = OOSBudgetLedger(self.db)
        
        rsv = ledger.reserve_oos_draw(
            "theme_001", "hypo_001", "config_001", "data_001", "gate_001", "window_001",
            idempotency_key="k6"
        )
        ledger.start_execution(rsv.reservation_id)
        ledger.fail_after_start(rsv.reservation_id, "crash")
        
        state = ledger.get_ledger_state("theme_001", "hypo_001")
        assert state["completed_draw_count"] == 1
        assert state["next_oos_draw_index"] == 2
        
        # Cannot reuse same hash tuple
        with self.assertRaises(ValueError) as ctx:
            ledger.reserve_oos_draw(
                "theme_001", "hypo_001", "config_001", "data_001", "gate_001", "window_002",
            idempotency_key="k7"
            )
        assert "Hash tuple already used" in str(ctx.exception)
    
    def test_hash_tuple_guard_prevents_reuse(self):
        """Same hash tuple blocked after reserve/start/complete/fail."""
        ledger = OOSBudgetLedger(self.db)
        
        rsv = ledger.reserve_oos_draw(
            "theme_001", "hypo_001", "config_001", "data_001", "gate_001", "window_001",
            idempotency_key="k8"
        )
        
        with self.assertRaises(ValueError) as ctx:
            ledger.reserve_oos_draw(
                "theme_001", "hypo_001", "config_001", "data_001", "gate_001", "window_002",
            idempotency_key="k9"
            )
        assert "Hash tuple already used" in str(ctx.exception)
    
    def test_cross_theme_window_guard_blocks_different_theme(self):
        """Different theme cannot reuse same window+data."""
        ledger = OOSBudgetLedger(self.db)
        
        ledger.reserve_oos_draw(
            "theme_A", "hypo_001", "config_001", "data_001", "gate_001", "window_shared",
            idempotency_key="k10"
        )
        
        with self.assertRaises(ValueError) as ctx:
            ledger.reserve_oos_draw(
                "theme_B", "hypo_002", "config_002", "data_001", "gate_002", "window_shared",
            idempotency_key="k11"
            )
        assert "Cross-theme OOS reuse" in str(ctx.exception)
    
    def test_same_theme_can_reuse_window(self):
        """Same theme CAN reuse window+data (different config)."""
        ledger = OOSBudgetLedger(self.db)
        
        rsv1 = ledger.reserve_oos_draw(
            "theme_A", "hypo_001", "config_001", "data_001", "gate_001", "window_shared",
            idempotency_key="k12"
        )
        ledger.start_execution(rsv1.reservation_id)
        ledger.complete_reservation(rsv1.reservation_id, "rejected")
        
        rsv2 = ledger.reserve_oos_draw(
            "theme_A", "hypo_001", "config_002", "data_001", "gate_002", "window_shared",
            idempotency_key="k13"
        )
        assert rsv2.oos_draw_index == 2
    
    def test_three_draws_then_exhausted(self):
        """After 3 completed draws, budget exhausted."""
        ledger = OOSBudgetLedger(self.db)
        
        for i in range(3):
            rsv = ledger.reserve_oos_draw(
                "theme_001", "hypo_001", f"config_{i}", "data_001", "gate_001", "window_001",
            idempotency_key=f"kloop{i}"
            )
            ledger.start_execution(rsv.reservation_id)
            ledger.complete_reservation(rsv.reservation_id, "rejected")
        
        state = ledger.get_ledger_state("theme_001", "hypo_001")
        assert state["budget_status"] == "oos_budget_exhausted"
        
        with self.assertRaises(ValueError) as ctx:
            ledger.reserve_oos_draw(
                "theme_001", "hypo_001", "config_3", "data_001", "gate_001", "window_001",
            idempotency_key="k15"
            )
        assert "OOS budget exhausted" in str(ctx.exception)
    
    def test_concurrent_reserve_one_wins(self):
        """Two concurrent reserves, one wins."""
        ledger1 = OOSBudgetLedger(self.db)
        ledger2 = OOSBudgetLedger(StrategyDB(str(self.db_path)))
        
        rsv1 = ledger1.reserve_oos_draw(
            "theme_001", "hypo_001", "config_001", "data_001", "gate_001", "window_001",
            idempotency_key="k16"
        )
        
        with self.assertRaises((ValueError, RuntimeError)) as ctx:
            ledger2.reserve_oos_draw(
                "theme_001", "hypo_001", "config_002", "data_001", "gate_001", "window_001",
            idempotency_key="k17"
            )
        # Either "Active reservation" or hash guard
        assert "Active reservation" in str(ctx.exception) or "Hash tuple" in str(ctx.exception)
        
        ledger2.db.close()
    
    def test_audit_snapshot_written_on_complete(self):
        """Complete writes OOSEvaluationLedger audit snapshot."""
        ledger = OOSBudgetLedger(self.db)
        
        rsv = ledger.reserve_oos_draw(
            "theme_001", "hypo_001", "config_001", "data_001", "gate_001", "window_001",
            idempotency_key="k18"
        )
        ledger.start_execution(rsv.reservation_id)
        ledger.complete_reservation(rsv.reservation_id, "rejected")
        
        # Check audit table
        row = self.db.conn.execute(
            "SELECT ledger_snapshot_id FROM oos_evaluation_ledgers WHERE theme_id='theme_001'"
        ).fetchone()
        assert row is not None
    
    def test_release_after_start_fails(self):
        """Cannot release after execution started."""
        ledger = OOSBudgetLedger(self.db)
        
        rsv = ledger.reserve_oos_draw(
            "theme_001", "hypo_001", "config_001", "data_001", "gate_001", "window_001",
            idempotency_key="k19"
        )
        ledger.start_execution(rsv.reservation_id)
        
        with self.assertRaises(ValueError) as ctx:
            ledger.release_pre_execution(rsv.reservation_id, "reason")
        assert "after execution started" in str(ctx.exception)
    
    def test_state_version_prevents_lost_update(self):
        """State version check prevents lost updates."""
        ledger = OOSBudgetLedger(self.db)
        
        # Reserve to create state with version=1
        rsv = ledger.reserve_oos_draw(
            "theme_001", "hypo_001", "config_001", "data_001", "gate_001", "window_001",
            idempotency_key="kstale1"
        )
        
        # Read state after reserve
        state = self.db.get_oos_budget_state("theme_001", "hypo_001")
        old_version = state["state_version"]
        
        # Start and complete to increment version
        ledger.start_execution(rsv.reservation_id)
        ledger.complete_reservation(rsv.reservation_id, "rejected", evaluation_id="eval1")
        
        # Try to update with stale version (should affect 0 rows)
        self.db.conn.execute("BEGIN IMMEDIATE")
        cursor = self.db.conn.execute(
            "UPDATE oos_budget_state SET consumed_draw_count = 2 WHERE theme_id = ? AND hypothesis_source_snapshot_id = ? AND state_version = ?",
            ("theme_001", "hypo_001", old_version)
        )
        self.db.conn.rollback()
        
        assert cursor.rowcount == 0  # Stale version rejected
    
    def test_audit_rollback_on_insert_failure(self):
        """Audit insert failure rolls back state and reservation."""
        ledger = OOSBudgetLedger(self.db)
        
        # Drop audit table to force insert failure
        self.db.conn.execute("DROP TABLE oos_evaluation_ledgers")
        self.db.conn.commit()
        
        # Reserve should fail due to audit insert
        with self.assertRaises(Exception):
            ledger.reserve_oos_draw(
                "theme_001", "hypo_001", "config_001", "data_001", "gate_001", "window_001",
                idempotency_key="kaudit1"
            )
        
        # Verify no state or reservation written
        new_db = StrategyDB(str(self.db_path))
        state = new_db.get_oos_budget_state("theme_001", "hypo_001")
        assert state is None
        
        row = new_db.conn.execute("SELECT COUNT(*) FROM oos_budget_reservations WHERE theme_id='theme_001'").fetchone()
        assert row[0] == 0
        new_db.close()
    
    def test_audit_rollback_on_complete_failure(self):
        """Complete audit failure rolls back terminal state."""
        ledger = OOSBudgetLedger(self.db)
        
        rsv = ledger.reserve_oos_draw(
            "theme_001", "hypo_001", "config_001", "data_001", "gate_001", "window_001",
            idempotency_key="kaudit2"
        )
        ledger.start_execution(rsv.reservation_id)
        
        # Drop audit table
        self.db.conn.execute("DROP TABLE oos_evaluation_ledgers")
        self.db.conn.commit()
        
        # Complete should fail
        with self.assertRaises(Exception):
            ledger.complete_reservation(rsv.reservation_id, "rejected", evaluation_id="eval1")
        
        # Verify reservation still started, not completed
        new_db = StrategyDB(str(self.db_path))
        row = new_db.conn.execute("SELECT status FROM oos_budget_reservations WHERE reservation_id=?", (rsv.reservation_id,)).fetchone()
        assert row[0] == "started"
        
        state = new_db.get_oos_budget_state("theme_001", "hypo_001")
        assert state["consumed_draw_count"] == 0  # Not incremented
        new_db.close()
    
    def test_owner_version_uniqueness(self):
        """Audit version unique per owner; different hypotheses allowed."""
        ledger = OOSBudgetLedger(self.db)
        
        # Theme A, hypothesis 1, version 1
        rsv1 = ledger.reserve_oos_draw(
            "theme_A", "hypo_1", "config_1", "data_1", "gate_1", "window_1",
            idempotency_key="kown1"
        )
        
        # Theme A, hypothesis 2, version 1 (different owner, OK)
        rsv2 = ledger.reserve_oos_draw(
            "theme_A", "hypo_2", "config_2", "data_2", "gate_2", "window_2",
            idempotency_key="kown2"
        )
        
        # Both should have version 1
        audit1 = self.db.conn.execute(
            "SELECT ledger_version FROM oos_evaluation_ledgers WHERE theme_id='theme_A' AND hypothesis_source_snapshot_id='hypo_1'"
        ).fetchall()
        assert len(audit1) == 1
        assert audit1[0][0] == 1
        
        audit2 = self.db.conn.execute(
            "SELECT ledger_version FROM oos_evaluation_ledgers WHERE theme_id='theme_A' AND hypothesis_source_snapshot_id='hypo_2'"
        ).fetchall()
        assert len(audit2) == 1
        assert audit2[0][0] == 1
        
        # Try duplicate version for same owner (should fail on unique constraint)
        with self.assertRaises(Exception):
            self.db.insert_oos_ledger_tx(
                type('Ledger', (), {
                    'ledger_snapshot_id': 'dup',
                    'theme_id': 'theme_A',
                    'hypothesis_source_snapshot_id': 'hypo_1',
                    'ledger_version': 1,  # Duplicate
                    'oos_evaluation_count': 0,
                    'next_oos_draw_index': 1,
                    'budget_status': 'available',
                    'recorded_at': __import__('datetime').datetime.now(),
                    'model_dump_json': lambda: '{}'
                })()
            )
            self.db.conn.commit()
    
    def test_idempotency_key_same_owner_returns_existing(self):
        """Same owner + same idempotency_key returns existing reservation."""
        ledger = OOSBudgetLedger(self.db)
        
        rsv1 = ledger.reserve_oos_draw(
            "theme_idem", "hypo_idem", "config_1", "data_1", "gate_1", "window_1",
            idempotency_key="shared_key"
        )
        
        # Retry with same key
        rsv2 = ledger.reserve_oos_draw(
            "theme_idem", "hypo_idem", "config_2", "data_2", "gate_2", "window_2",
            idempotency_key="shared_key"
        )
        
        assert rsv1.reservation_id == rsv2.reservation_id
        assert rsv2.strategy_config_hash == "config_1"  # Original hashes, not new ones
    
    def test_idempotency_key_different_owners_allowed(self):
        """Different owners can use same idempotency_key."""
        ledger = OOSBudgetLedger(self.db)
        
        rsv1 = ledger.reserve_oos_draw(
            "theme_1", "hypo_1", "config_1", "data_1", "gate_1", "window_1",
            idempotency_key="same_key"
        )
        
        rsv2 = ledger.reserve_oos_draw(
            "theme_2", "hypo_2", "config_2", "data_2", "gate_2", "window_2",
            idempotency_key="same_key"
        )
        
        assert rsv1.reservation_id != rsv2.reservation_id
        assert rsv1.theme_id == "theme_1"
        assert rsv2.theme_id == "theme_2"
    
    def test_complete_stable_id_idempotency(self):
        """Complete with same stable ID + verdict is idempotent."""
        ledger = OOSBudgetLedger(self.db)
        
        rsv = ledger.reserve_oos_draw(
            "theme_stable", "hypo_stable", "config", "data", "gate", "window",
            idempotency_key="kstable1"
        )
        ledger.start_execution(rsv.reservation_id)
        ledger.complete_reservation(rsv.reservation_id, "rejected", evaluation_id="eval_001")
        
        # Retry with same eval ID + verdict (should be silent success)
        ledger.complete_reservation(rsv.reservation_id, "rejected", evaluation_id="eval_001")
        
        # Should still only consume once
        state = ledger.get_ledger_state("theme_stable", "hypo_stable")
        assert state["completed_draw_count"] == 1
    
    def test_complete_different_stable_id_rejected(self):
        """Complete with different stable ID rejected."""
        ledger = OOSBudgetLedger(self.db)
        
        rsv = ledger.reserve_oos_draw(
            "theme_stable2", "hypo_stable2", "config", "data", "gate", "window",
            idempotency_key="kstable2"
        )
        ledger.start_execution(rsv.reservation_id)
        ledger.complete_reservation(rsv.reservation_id, "rejected", report_id="rpt_001")
        
        # Try with different report ID
        with self.assertRaises(ValueError) as ctx:
            ledger.complete_reservation(rsv.reservation_id, "rejected", report_id="rpt_002")
        assert "already completed" in str(ctx.exception)
    
    def test_fail_after_start_idempotent_on_same_reason(self):
        """Fail with same reason only consumes once."""
        ledger = OOSBudgetLedger(self.db)
        
        rsv = ledger.reserve_oos_draw(
            "theme_fail", "hypo_fail", "config", "data", "gate", "window",
            idempotency_key="kfail1"
        )
        ledger.start_execution(rsv.reservation_id)
        ledger.fail_after_start(rsv.reservation_id, "crash_reason")
        
        # Retry with same reason
        ledger.fail_after_start(rsv.reservation_id, "crash_reason")
        
        # Should still only consume once
        state = ledger.get_ledger_state("theme_fail", "hypo_fail")
        assert state["completed_draw_count"] == 1

    def test_legacy_global_idempotency_constraint_migrates_without_data_loss(self):
        """A legacy global idempotency constraint upgrades to owner-scoped uniqueness."""
        self.db.conn.execute("DROP TABLE oos_budget_reservations")
        self.db.conn.execute(
            """
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
                execution_started_at TEXT,
                terminal_at TEXT,
                verdict TEXT,
                terminal_reason TEXT,
                idempotency_key TEXT NOT NULL UNIQUE,
                evaluation_id TEXT,
                report_id TEXT
            )
            """
        )
        self.db.conn.execute(
            """
            INSERT INTO oos_budget_state
            (theme_id, hypothesis_source_snapshot_id, consumed_draw_count,
             next_oos_draw_index, budget_status, state_version, updated_at)
            VALUES ('legacy_theme', 'legacy_hypothesis', 0, 1, 'available', 1, ?)
            """,
            (datetime.now().isoformat(),),
        )
        self.db.conn.execute(
            """
            INSERT INTO oos_budget_reservations
            (reservation_id, theme_id, hypothesis_source_snapshot_id,
             strategy_config_hash, data_snapshot_hash, gate_criteria_hash,
             shared_oos_window_id, oos_draw_index, status, reserved_at,
             idempotency_key)
            VALUES ('legacy_reservation', 'legacy_theme', 'legacy_hypothesis',
                    'legacy_config', 'legacy_data', 'legacy_gate', 'legacy_window',
                    1, 'released', ?, 'shared_key')
            """,
            (datetime.now().isoformat(),),
        )
        self.db.conn.commit()
        self.db.close()

        self.db = StrategyDB(str(self.db_path))
        preserved = self.db.conn.execute(
            "SELECT reservation_id FROM oos_budget_reservations "
            "WHERE reservation_id = 'legacy_reservation'"
        ).fetchone()
        assert preserved is not None

        reservation = OOSBudgetLedger(self.db).reserve_oos_draw(
            "new_theme", "new_hypothesis", "new_config", "new_data",
            "new_gate", "new_window", idempotency_key="shared_key"
        )
        assert reservation.reservation_id != "legacy_reservation"

    def test_real_busy_retries_once_then_rolls_back_without_writes(self):
        """A second connection holding SQLite's write lock permits one retry only."""
        holder = StrategyDB(str(self.db_path))
        worker_db = StrategyDB(str(self.db_path))
        holder.conn.execute("PRAGMA busy_timeout = 1")
        worker_db.conn.execute("PRAGMA busy_timeout = 1")
        worker = OOSBudgetLedger(worker_db)
        original_reserve_tx = worker._reserve_tx
        attempts = 0

        def counted_reserve_tx(*args, **kwargs):
            nonlocal attempts
            attempts += 1
            return original_reserve_tx(*args, **kwargs)

        worker._reserve_tx = counted_reserve_tx
        holder.conn.execute("BEGIN IMMEDIATE")
        try:
            with self.assertRaisesRegex(RuntimeError, "concurrency unavailable"):
                worker.reserve_oos_draw(
                    "busy_theme", "busy_hypothesis", "busy_config", "busy_data",
                    "busy_gate", "busy_window", idempotency_key="busy_key"
                )
            assert attempts == 2
        finally:
            holder.conn.rollback()
            worker_db.close()
            holder.close()

        observer = StrategyDB(str(self.db_path))
        try:
            assert observer.get_oos_budget_state("busy_theme", "busy_hypothesis") is None
            reservation_count = observer.conn.execute(
                "SELECT COUNT(*) FROM oos_budget_reservations "
                "WHERE theme_id = 'busy_theme'"
            ).fetchone()[0]
            audit_count = observer.conn.execute(
                "SELECT COUNT(*) FROM oos_evaluation_ledgers "
                "WHERE theme_id = 'busy_theme'"
            ).fetchone()[0]
            assert reservation_count == 0
            assert audit_count == 0
        finally:
            observer.close()


if __name__ == "__main__":
    unittest.main()
