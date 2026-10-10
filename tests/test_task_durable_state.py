"""Test task state is durable (reads current columns, not stale payload)."""
import sqlite3
import tempfile
import unittest
from datetime import datetime, date
from pathlib import Path

from backend.db.strategy import StrategyDB
from contracts.b6_task import B6ValidationTask


class TestTaskStateDurable(unittest.TestCase):
    def test_getters_read_current_status_not_payload(self):
        """After update_b6_task_status, getters return DB columns not payload."""
        temp = tempfile.TemporaryDirectory()
        path = Path(temp.name)/"t.db"
        db = StrategyDB(str(path))
        
        # ponytail: FK setup
        from contracts.strategy import BacktestUniverseSpec, StrategyDraft, StrategyLifecycleState, ResearchProtocolSnapshot
        db.store_backtest_universe(BacktestUniverseSpec(
            universe_spec_id="u", universe_rule_type="point_in_time_membership",
            membership_source="t", membership_effective_from=date(2024,1,1),
            membership_effective_to=date(2024,12,31), snapshot_date=date(2024,1,1),
            membership_snapshot_ids=("s",), quality_status="ok"
        ))
        draft = StrategyDraft(
            strategy_revision_id="r1", theme_id="t", hypothesis_id="h",
            strategy_template_id="tpl", strategy_template_version="v1",
            strategy_template_hash="hash", hypothesis_source_snapshot_id="hs",
            backtest_universe_spec_id="u", strategy_config_json="{}",
            sample_split_rule_id="split", created_at=datetime.now()
        )
        protocol = ResearchProtocolSnapshot(
            protocol_snapshot_id="p1", theme_id="t", hypothesis_source_snapshot_id="hs",
            strategy_revision_id="r1", sample_split_rule_id="split",
            oos_window_rule_id="w", oos_window_rule_params_json="{}",
            oos_window_start=date(2024,1,1), oos_window_end=date(2024,12,31),
            shared_oos_window_id="w", backtest_universe_spec_id="u",
            strategy_config_hash="ch", data_snapshot_id="d", data_snapshot_hash="dh",
            kill_criteria_snapshot_id="k", prototype_gate_thresholds_json="{}",
            gate_criteria_hash="gh", frozen_at=datetime.now(), frozen_by="test"
        )
        db.create_strategy_draft(draft, StrategyLifecycleState(
            lifecycle_state_id="ls", strategy_revision_id="r1", state_version=1,
            state="draft", source_record_id="init", recorded_at=datetime.now(), recorded_by="test"
        ))
        db.store_protocol_snapshot(protocol)
        
        # create running
        db.create_b6_task(B6ValidationTask(
            task_id="t1", task_key="k1", task_type="b6_validation",
            strategy_revision_id="r1", protocol_snapshot_id="p1",
            status="running", created_at=datetime.now()
        ))
        
        # update to completed
        db.update_b6_task_status("t1", "completed", datetime.now(), "done", "ok")
        db.conn.commit()
        
        # second connection
        db2 = StrategyDB(str(path))
        
        t_by_id = db2.get_b6_task_by_id("t1")
        self.assertEqual(t_by_id.status, "completed")
        self.assertEqual(t_by_id.blocking_reason_code, "done")
        self.assertIsNotNone(t_by_id.completed_at)
        
        t_by_key = db2.get_b6_task_by_key("k1")
        self.assertEqual(t_by_key.status, "completed")
        self.assertEqual(t_by_key.blocking_reason_code, "done")
        
        db2.close()
        db.close()
        temp.cleanup()


if __name__ == "__main__":
    unittest.main()
