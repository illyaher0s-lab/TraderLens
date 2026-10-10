"""B6 reservation binds task_key+protocol."""
import tempfile, unittest
from datetime import datetime, date
from pathlib import Path
from backend.db.strategy import StrategyDB
from backend.services.oos_budget_ledger import OOSBudgetLedger
from contracts.b6_task import B6ValidationTask
from contracts.strategy import *

def _setup_db(path):
    """ponytail: FK boilerplate"""
    db = StrategyDB(str(path))
    db.store_backtest_universe(BacktestUniverseSpec(
        universe_spec_id="u", universe_rule_type="point_in_time_membership",
        membership_source="t", membership_effective_from=date(2024,1,1),
        membership_effective_to=date(2024,12,31), snapshot_date=date(2024,1,1),
        membership_snapshot_ids=("s",), quality_status="ok"))
    draft = StrategyDraft(
        strategy_revision_id="r", theme_id="t", hypothesis_id="h",
        strategy_template_id="tpl", strategy_template_version="v1",
        strategy_template_hash="hash", hypothesis_source_snapshot_id="hs",
        backtest_universe_spec_id="u", strategy_config_json="{}",
        sample_split_rule_id="split", created_at=datetime.now())
    protocol = ResearchProtocolSnapshot(
        protocol_snapshot_id="p", theme_id="t", hypothesis_source_snapshot_id="hs",
        strategy_revision_id="r", sample_split_rule_id="split",
        oos_window_rule_id="w", oos_window_rule_params_json="{}",
        oos_window_start=date(2024,1,1), oos_window_end=date(2024,12,31),
        shared_oos_window_id="w", backtest_universe_spec_id="u",
        strategy_config_hash="ch", data_snapshot_id="d", data_snapshot_hash="dh",
        kill_criteria_snapshot_id="k", prototype_gate_thresholds_json="{}",
        gate_criteria_hash="gh", frozen_at=datetime.now(), frozen_by="test")
    db.create_strategy_draft(draft, StrategyLifecycleState(
        lifecycle_state_id="ls", strategy_revision_id="r", state_version=1,
        state="draft", source_record_id="init", recorded_at=datetime.now(), recorded_by="test"))
    db.store_protocol_snapshot(protocol)
    return db, protocol

class TestReservationTaskBinding(unittest.TestCase):
    def test_b6_reserve_binds_task_key_protocol(self):
        temp = tempfile.TemporaryDirectory()
        db, protocol = _setup_db(Path(temp.name)/"1.db")
        ledger = OOSBudgetLedger(db)
        task = B6ValidationTask(
            task_id="t", task_key="k", task_type="b6_validation",
            strategy_revision_id="r", protocol_snapshot_id="p",
            status="running", created_at=datetime.now())
        db.create_b6_task(task)
        
        rsv = ledger.reserve_oos_draw("t", "hs", "ch", "dh", "gh", "w",
                                       idempotency_key=task.task_key,
                                       task_key=task.task_key, protocol_snapshot_id=protocol.protocol_snapshot_id)
        
        row = db.conn.execute("SELECT idempotency_key, task_key, protocol_snapshot_id FROM oos_budget_reservations WHERE reservation_id=?", (rsv.reservation_id,)).fetchone()
        self.assertEqual(row[0], task.task_key)
        self.assertEqual(row[1], task.task_key)
        self.assertEqual(row[2], protocol.protocol_snapshot_id)
        db.close()
        temp.cleanup()
    
    def test_identity_mismatch_rejects(self):
        """idempotency_key != task_key → ValueError, zero writes."""
        temp = tempfile.TemporaryDirectory()
        db, protocol = _setup_db(Path(temp.name)/"2.db")
        ledger = OOSBudgetLedger(db)
        
        before = ledger.get_ledger_state("t", "hs")
        with self.assertRaises(ValueError) as ctx:
            ledger.reserve_oos_draw("t", "hs", "ch", "dh", "gh", "w",
                                     idempotency_key="wrong_key",
                                     task_key="task_key", protocol_snapshot_id="p")
        self.assertIn("idempotency_key must equal task_key", str(ctx.exception))
        after = ledger.get_ledger_state("t", "hs")
        self.assertEqual(before, after)
        self.assertEqual(db.conn.execute("SELECT COUNT(*) FROM oos_budget_reservations").fetchone()[0], 0)
        db.close()
        temp.cleanup()
    
    def test_half_binding_rejects(self):
        """Only task_key or only protocol → ValueError, zero writes."""
        temp = tempfile.TemporaryDirectory()
        db, _ = _setup_db(Path(temp.name)/"3.db")
        ledger = OOSBudgetLedger(db)
        
        s1 = ledger.get_ledger_state("t", "hs")
        with self.assertRaises(ValueError):
            ledger.reserve_oos_draw("t", "hs", "ch", "dh", "gh", "w",
                                     idempotency_key="k", task_key="k", protocol_snapshot_id=None)
        s2 = ledger.get_ledger_state("t", "hs")
        self.assertEqual(s1, s2)
        
        with self.assertRaises(ValueError):
            ledger.reserve_oos_draw("t", "hs", "ch", "dh", "gh", "w",
                                     idempotency_key="k", task_key=None, protocol_snapshot_id="p")
        s3 = ledger.get_ledger_state("t", "hs")
        self.assertEqual(s1, s3)
        self.assertEqual(db.conn.execute("SELECT COUNT(*) FROM oos_budget_reservations").fetchone()[0], 0)
        db.close()
        temp.cleanup()
    
    def test_idempotent_retry_same_row(self):
        """Same task/protocol → same reservation, DB has 1 row."""
        temp = tempfile.TemporaryDirectory()
        db, protocol = _setup_db(Path(temp.name)/"4.db")
        ledger = OOSBudgetLedger(db)
        task = B6ValidationTask(
            task_id="t", task_key="k", task_type="b6_validation",
            strategy_revision_id="r", protocol_snapshot_id="p",
            status="running", created_at=datetime.now())
        db.create_b6_task(task)
        
        r1 = ledger.reserve_oos_draw("t", "hs", "ch", "dh", "gh", "w",
                                      idempotency_key="k", task_key="k", protocol_snapshot_id="p")
        r2 = ledger.reserve_oos_draw("t", "hs", "ch", "dh", "gh", "w",
                                      idempotency_key="k", task_key="k", protocol_snapshot_id="p")
        self.assertEqual(r1.reservation_id, r2.reservation_id)
        self.assertEqual(db.conn.execute("SELECT COUNT(*) FROM oos_budget_reservations").fetchone()[0], 1)
        db.close()
        temp.cleanup()
    
    def test_protocol_conflict_rejects(self):
        """Same key, different protocol → RuntimeError, zero new records, zero budget."""
        temp = tempfile.TemporaryDirectory()
        db, protocol = _setup_db(Path(temp.name)/"5.db")
        ledger = OOSBudgetLedger(db)
        task = B6ValidationTask(
            task_id="t", task_key="k", task_type="b6_validation",
            strategy_revision_id="r", protocol_snapshot_id="p",
            status="running", created_at=datetime.now())
        db.create_b6_task(task)
        
        ledger.reserve_oos_draw("t", "hs", "ch", "dh", "gh", "w",
                                idempotency_key="k", task_key="k", protocol_snapshot_id="p")
        state_after_reserve = ledger.get_ledger_state("t", "hs")
        rsv_count_after_reserve = db.conn.execute("SELECT COUNT(*) FROM oos_budget_reservations").fetchone()[0]
        
        with self.assertRaises(RuntimeError) as ctx:
            ledger.reserve_oos_draw("t", "hs", "ch", "dh", "gh", "w",
                                     idempotency_key="k", task_key="k", protocol_snapshot_id="p_different")
        self.assertIn("idempotency conflict", str(ctx.exception))
        state_after_conflict = ledger.get_ledger_state("t", "hs")
        self.assertEqual(state_after_reserve, state_after_conflict)
        self.assertEqual(db.conn.execute("SELECT COUNT(*) FROM oos_budget_reservations").fetchone()[0], rsv_count_after_reserve)
        db.close()
        temp.cleanup()

if __name__ == "__main__": unittest.main()
