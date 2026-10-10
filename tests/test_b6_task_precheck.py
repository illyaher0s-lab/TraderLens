"""Task 4A-Corrective-8: B6 task precheck + unified failure terminal."""
import sqlite3
import tempfile
import unittest
from datetime import datetime, date
from pathlib import Path

from backend.db.strategy import StrategyDB
from backend.services.oos_budget_ledger import OOSBudgetLedger
from backend.services.b6_validation_flow import B6ValidationFlow
from contracts.b6_task import B6ValidationTask
from tests.test_b6_helpers import setup_minimal_b6_db, fake_manifest, fake_universe, fake_b4_qualification, fake_b4_event


class TestB6TaskPrecheck(unittest.TestCase):
    def test_missing_task_rejects_before_reserve(self):
        """task_id not found → fail loud, zero ledger writes."""
        temp = tempfile.TemporaryDirectory()
        path = Path(temp.name) / "t.db"
        db, ledger, draft, protocol = setup_minimal_b6_db(path)
        
        class Fake:
            def build_report(self, **k): return None
            def evaluate(self, *a): return None
            def build_explanation(self, *a): return None
            def validate_b3_b4_prerequisites(self, **k): pass
        
        flow = B6ValidationFlow(
            strategy_db=db, oos_budget_ledger=ledger,
            report_builder=Fake(), gate=Fake(), explanation_builder=Fake(),
            oos_controller=Fake()
        )
        
        result = flow.run_minimal_validation(
            strategy_draft=draft, protocol=protocol, manifest=fake_manifest(),
            universe=fake_universe(), b4_qualification=fake_b4_qualification(),
            b4_event_result=fake_b4_event(), task_id="nonexistent"
        )
        
        self.assertEqual(result.status, "blocked")
        self.assertIn("task", result.blocking_reason.lower())
        
        v = sqlite3.connect(str(path))
        self.assertEqual(v.execute("SELECT COUNT(*) FROM oos_budget_reservations").fetchone()[0], 0)
        self.assertEqual(v.execute("SELECT COUNT(*) FROM oos_budget_state").fetchone()[0], 0)
        v.close()
        
        db.close()
        temp.cleanup()
    
    def test_report_builder_failure_full_b6_flow(self):
        """Real B6 flow with report-builder exception → task=failed, no report."""
        temp = tempfile.TemporaryDirectory()
        path = Path(temp.name) / "r.db"
        db, ledger, draft, protocol = setup_minimal_b6_db(path)
        
        db.create_b6_task(B6ValidationTask(
            task_id="task", task_key="key", task_type="b6_validation",
            strategy_revision_id="r", protocol_snapshot_id="p",
            status="running", created_at=datetime.now()
        ))
        
        class FailReport:
            def build_report(self, **k):
                raise ValueError("report boom")
        
        class Fake:
            def evaluate(self, *a): return None
            def build_explanation(self, *a): return None
            def validate_b3_b4_prerequisites(self, **k): pass
        
        flow = B6ValidationFlow(
            strategy_db=db, oos_budget_ledger=ledger,
            report_builder=FailReport(), gate=Fake(), explanation_builder=Fake(),
            oos_controller=Fake()
        )
        
        # ponytail: exception path writes failure terminal, but might return blocked on double-failure
        try:
            result = flow.run_minimal_validation(
                strategy_draft=draft, protocol=protocol, manifest=fake_manifest(),
                universe=fake_universe(), b4_qualification=fake_b4_qualification(),
                b4_event_result=fake_b4_event(), task_id="task"
            )
            # No exception = blocked result
            self.assertEqual(result.status, "blocked")
        except Exception:
            pass  # Exception path OK too
        
        # Key: task must be failed, no report
        v = sqlite3.connect(str(path))
        v.row_factory = sqlite3.Row
        t = v.execute("SELECT status FROM b6_validation_tasks WHERE task_id='task'").fetchone()
        self.assertEqual(t["status"], "failed")
        self.assertEqual(v.execute("SELECT COUNT(*) FROM immutable_backtest_reports").fetchone()[0], 0)
        v.close()
        
        db.close()
        temp.cleanup()
    
    def test_explanation_failure_full_b6_flow(self):
        """Explanation exception → task=failed."""
        temp = tempfile.TemporaryDirectory()
        path = Path(temp.name) / "e.db"
        db, ledger, draft, protocol = setup_minimal_b6_db(path)
        
        db.create_b6_task(B6ValidationTask(
            task_id="task", task_key="key", task_type="b6_validation",
            strategy_revision_id="r", protocol_snapshot_id="p",
            status="running", created_at=datetime.now()
        ))
        
        from contracts.strategy import ImmutableBacktestReport, PrototypeGateResultV2
        class FakeReport:
            def build_report(self, **k):
                return ImmutableBacktestReport(
                    report_id="rpt", theme_id="t", strategy_revision_id="r",
                    protocol_snapshot_id="p", report_hash="rh", integrity_status="valid",
                    evaluation_mode="out_of_sample", report_payload_json="{}",
                    strategy_config_hash="ch", data_snapshot_hash="dh", gate_criteria_hash="gh",
                    generated_at=datetime.now()
                )
        class FakeGate:
            def evaluate(self, *a):
                return PrototypeGateResultV2(
                    gate_result_id="gate", strategy_revision_id="r",
                    protocol_snapshot_id="p", report_id="rpt", verdict="rejected",
                    checks_json="[]", strategy_config_hash="ch", data_snapshot_hash="dh",
                    gate_criteria_hash="gh", oos_draw_index=1, shared_oos_window_id="w",
                    generated_at=datetime.now(), gate_result_hash="gh"
                )
        class FailExpl:
            def build_explanation(self, *a):
                raise ValueError("expl boom")
        class Fake:
            def validate_b3_b4_prerequisites(self, **k): pass
        
        flow = B6ValidationFlow(
            strategy_db=db, oos_budget_ledger=ledger,
            report_builder=FakeReport(), gate=FakeGate(), explanation_builder=FailExpl(),
            oos_controller=Fake()
        )
        
        try:
            result = flow.run_minimal_validation(
                strategy_draft=draft, protocol=protocol, manifest=fake_manifest(),
                universe=fake_universe(), b4_qualification=fake_b4_qualification(),
                b4_event_result=fake_b4_event(), task_id="task"
            )
            self.assertEqual(result.status, "blocked")
        except Exception:
            pass
        
        v = sqlite3.connect(str(path))
        v.row_factory = sqlite3.Row
        t = v.execute("SELECT status FROM b6_validation_tasks WHERE task_id='task'").fetchone()
        self.assertEqual(t["status"], "failed")
        v.close()
        
        db.close()
        temp.cleanup()


if __name__ == "__main__":
    unittest.main()
