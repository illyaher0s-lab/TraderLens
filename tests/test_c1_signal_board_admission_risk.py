"""
C1 Task 1: Identify Signal Board Admission Display Risk

Tests to identify if current Signal Board API/DB can return signals
without admission proof (strategy_revision_id, lifecycle_state, admission_source).

Current state:
- PlannedSignal has strategy_id + strategy_version (user-facing identifiers)
- PlannedSignal lacks strategy_revision_id (B-module lifecycle tracking ID)
- PlannedSignal lacks lifecycle_state or admission_status field
- Signal Board API/DB cannot retroactively filter by lifecycle_state

Risk scenarios:
1. Old signals generated before C0 (no admission metadata) displayed as valid
2. Manual DB insertion bypassing generate_planned_signals.py admission gate
3. API returns signals from draft/rejected strategies if somehow inserted
"""
import unittest
import tempfile
from datetime import date, datetime
from pathlib import Path

from backend.db.signal_board import SignalBoardDB
from contracts.signal_board import PlannedSignal


class TestC1SignalBoardAdmissionRisk(unittest.TestCase):
    """Identify Signal Board admission display risks."""

    def _make_signal_without_admission_metadata(
        self,
        signal_id: str,
        strategy_id: str = "test_strategy",
        strategy_version: str = "v1.0.0",
    ) -> PlannedSignal:
        """Create signal without admission metadata (mimics old/bypass signals)."""
        return PlannedSignal(
            signal_id=signal_id,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            snapshot_hash="test_hash",
            signal_date=date(2023, 12, 29),
            intended_execution_date=date(2024, 1, 2),
            symbol="600519.SH",
            direction="buy",
            planned_action="enter",
            quantity=100,
            trigger_reason="Test trigger",
            review_status="pending",
            created_at=datetime(2023, 12, 29, 16, 0, 0),
        )

    def test_planned_signal_lacks_admission_metadata_fields(self):
        """
        Risk (C1 Task 1): PlannedSignal contract has no strategy_revision_id or lifecycle_state.
        
        Resolution (C1 Task 2): PlannedSignal now has admission metadata fields.
        This test verifies the fields were added.
        """
        signal = self._make_signal_without_admission_metadata("sig_001")
        
        # Verify admission metadata fields exist (C1 Task 2 added them)
        self.assertTrue(hasattr(signal, "strategy_revision_id"))
        self.assertTrue(hasattr(signal, "lifecycle_state_at_generation"))
        self.assertTrue(hasattr(signal, "admission_source"))

    def test_signal_board_db_stores_signals_without_admission_check(self):
        """
        Risk: SignalBoardDB.create_signal() accepts signals without admission proof.
        
        Attack vector: Manual DB insertion or script bypass can create signals
        for draft/rejected strategies. DB has no admission validation.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = SignalBoardDB(db_path)
            
            # Create signal without admission metadata
            signal = self._make_signal_without_admission_metadata("sig_no_admission")
            
            # DB accepts signal without admission validation
            db.create_signal(signal)
            
            # Signal is retrievable
            retrieved = db.get_signal("sig_no_admission")
            self.assertIsNotNone(retrieved)
            self.assertEqual(retrieved.signal_id, "sig_no_admission")

    def test_signal_board_api_list_signals_has_no_admission_filter(self):
        """
        Risk (C1 Task 1): SignalBoardDB.list_signals() has no admission_status filter.
        
        Resolution (C1 Task 3): list_signals() now filters by lifecycle_state_at_generation='prototype_passed' by default.
        This test verifies unadmitted signals are hidden.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = SignalBoardDB(db_path)
            
            # Create signals without admission metadata
            signal_a = self._make_signal_without_admission_metadata("sig_a", "strat_A", "v1.0")
            signal_b = self._make_signal_without_admission_metadata("sig_b", "strat_B", "v2.0")
            
            db.create_signal(signal_a)
            db.create_signal(signal_b)
            
            # list_signals() now filters out unadmitted signals (C1 Task 3)
            result = db.list_signals()
            self.assertEqual(len(result), 0)
            
            # Audit mode returns all signals
            result_audit = db.list_signals(include_missing_admission=True)
            self.assertEqual(len(result_audit), 2)

    def test_signal_board_api_list_strategies_has_no_admission_filter(self):
        """
        Risk (C1 Task 1): SignalBoardDB.list_strategies() returns all strategies in DB.
        
        Resolution (C1 Task 3): list_strategies() now filters by lifecycle_state_at_generation='prototype_passed' by default.
        This test verifies unadmitted strategies are hidden.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = SignalBoardDB(db_path)
            
            # Create signals for different strategies without admission metadata
            signal_a = self._make_signal_without_admission_metadata("sig_a", "draft_strat", "v1.0")
            signal_b = self._make_signal_without_admission_metadata("sig_b", "prototype_strat", "v2.0")
            
            db.create_signal(signal_a)
            db.create_signal(signal_b)
            
            # list_strategies() now filters out unadmitted strategies (C1 Task 3)
            strategies = db.list_strategies()
            self.assertEqual(len(strategies), 0)
            
            # Audit mode returns all strategies
            strategies_audit = db.list_strategies(include_missing_admission=True)
            self.assertEqual(len(strategies_audit), 2)
            
            strategy_ids = {s["strategy_id"] for s in strategies_audit}
            self.assertEqual(strategy_ids, {"draft_strat", "prototype_strat"})

    def test_old_signals_without_admission_metadata_default_to_displayed(self):
        """
        Risk: Old signals (generated before C0) have no admission metadata.
        
        Scenario: Signals generated before C0 have strategy_id + strategy_version,
        but no strategy_revision_id or lifecycle_state.
        
        Current behavior: These signals are displayed as valid (no filter).
        Expected behavior: Old signals should be marked as missing_admission,
        not default to accepted.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = SignalBoardDB(db_path)
            
            # Simulate old signal (no admission metadata)
            old_signal = self._make_signal_without_admission_metadata(
                "old_signal_pre_c0",
                strategy_id="legacy_strategy",
                strategy_version="v0.9.0"
            )
            
            db.create_signal(old_signal)
            
            # Old signal is retrievable and displayed
            retrieved = db.get_signal("old_signal_pre_c0")
            self.assertIsNotNone(retrieved)
            
            # Cannot distinguish old signal from admitted signal
            # This is the risk: old signals default to displayed


if __name__ == "__main__":
    unittest.main()
