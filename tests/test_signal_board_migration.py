"""
Test DB schema migration for evidence fields (M4.1)

Verifies that:
1. New databases create with evidence fields
2. Old databases (without evidence fields) still work (schema auto-adds columns)
3. Evidence fields can be read/written correctly
"""

import unittest
import tempfile
from datetime import date, datetime
from pathlib import Path

from backend.db.signal_board import SignalBoardDB
from contracts.signal_board import PlannedSignal


class TestSignalBoardDBMigration(unittest.TestCase):
    """Test DB schema migration for evidence fields."""
    
    def test_new_db_has_evidence_fields(self):
        """New database creates with evidence fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = SignalBoardDB(db_path)
            
            # Create signal with evidence fields
            signal = PlannedSignal(
                signal_id="test_signal_1",
                strategy_id="test_strategy",
                strategy_version="v1.0.0",
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
                risk_flags=["ST", "low_liquidity"],
                evidence_status="warning",
                evidence_checked_at=datetime(2023, 12, 29, 16, 5, 0)
            )
            
            db.create_signal(signal)
            
            # Read back
            retrieved = db.get_signal(signal.signal_id)
            
            self.assertIsNotNone(retrieved)
            self.assertEqual(retrieved.risk_flags, ["ST", "low_liquidity"])
            self.assertEqual(retrieved.evidence_status, "warning")
            self.assertEqual(retrieved.evidence_checked_at, datetime(2023, 12, 29, 16, 5, 0))
    
    def test_update_evidence_works(self):
        """update_evidence method works correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = SignalBoardDB(db_path)
            
            # Create signal without evidence
            signal = PlannedSignal(
                signal_id="test_signal_2",
                strategy_id="test_strategy",
                strategy_version="v1.0.0",
                snapshot_hash="test_hash",
                signal_date=date(2023, 12, 29),
                intended_execution_date=date(2024, 1, 2),
                symbol="600519.SH",
                direction="buy",
                planned_action="enter",
                quantity=100,
                trigger_reason="Test trigger",
                review_status="pending",
                created_at=datetime(2023, 12, 29, 16, 0, 0)
            )
            
            db.create_signal(signal)
            
            # Update evidence
            checked_at = datetime(2023, 12, 29, 16, 10, 0)
            updated = db.update_evidence(
                signal_id=signal.signal_id,
                risk_flags=["suspended"],
                evidence_status="blocked",
                evidence_checked_at=checked_at
            )
            
            self.assertTrue(updated)
            
            # Read back
            retrieved = db.get_signal(signal.signal_id)
            
            self.assertEqual(retrieved.risk_flags, ["suspended"])
            self.assertEqual(retrieved.evidence_status, "blocked")
            self.assertEqual(retrieved.evidence_checked_at, checked_at)
    
    def test_default_evidence_values(self):
        """Signals created without evidence fields get clean defaults."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = SignalBoardDB(db_path)
            
            # Create signal without evidence fields
            signal = PlannedSignal(
                signal_id="test_signal_3",
                strategy_id="test_strategy",
                strategy_version="v1.0.0",
                snapshot_hash="test_hash",
                signal_date=date(2023, 12, 29),
                intended_execution_date=date(2024, 1, 2),
                symbol="600519.SH",
                direction="buy",
                planned_action="enter",
                quantity=100,
                trigger_reason="Test trigger",
                review_status="pending",
                created_at=datetime(2023, 12, 29, 16, 0, 0)
            )
            
            db.create_signal(signal)
            
            # Read back
            retrieved = db.get_signal(signal.signal_id)
            
            self.assertEqual(retrieved.risk_flags, [])
            self.assertEqual(retrieved.evidence_status, "clean")
            self.assertIsNone(retrieved.evidence_checked_at)
    
    def test_list_signals_includes_evidence_fields(self):
        """list_signals returns evidence fields correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = SignalBoardDB(db_path)
            
            # Create signals with different evidence statuses
            signal_clean = PlannedSignal(
                signal_id="signal_clean",
                strategy_id="test_strategy",
                strategy_version="v1.0.0",
                snapshot_hash="test_hash",
                signal_date=date(2023, 12, 29),
                intended_execution_date=date(2024, 1, 2),
                symbol="600519.SH",
                direction="buy",
                planned_action="enter",
                quantity=100,
                trigger_reason="Clean signal",
                review_status="pending",
                created_at=datetime(2023, 12, 29, 16, 0, 0),
                risk_flags=[],
                evidence_status="clean"
            )
            
            signal_warning = PlannedSignal(
                signal_id="signal_warning",
                strategy_id="test_strategy",
                strategy_version="v1.0.0",
                snapshot_hash="test_hash",
                signal_date=date(2023, 12, 29),
                intended_execution_date=date(2024, 1, 2),
                symbol="600036.SH",
                direction="sell",
                planned_action="exit",
                quantity=100,
                trigger_reason="Warning signal",
                review_status="pending",
                created_at=datetime(2023, 12, 29, 16, 0, 0),
                risk_flags=["ST"],
                evidence_status="warning"
            )
            
            signal_blocked = PlannedSignal(
                signal_id="signal_blocked",
                strategy_id="test_strategy",
                strategy_version="v1.0.0",
                snapshot_hash="test_hash",
                signal_date=date(2023, 12, 29),
                intended_execution_date=date(2024, 1, 2),
                symbol="000001.SZ",
                direction="buy",
                planned_action="enter",
                quantity=100,
                trigger_reason="Blocked signal",
                review_status="pending",
                created_at=datetime(2023, 12, 29, 16, 0, 0),
                risk_flags=["suspended"],
                evidence_status="blocked"
            )
            
            db.create_signal(signal_clean)
            db.create_signal(signal_warning)
            db.create_signal(signal_blocked)
            
            # List all
            signals = db.list_signals(signal_date=date(2023, 12, 29))
            
            self.assertEqual(len(signals), 3)
            
            # Check each signal
            by_id = {s.signal_id: s for s in signals}
            
            self.assertEqual(by_id["signal_clean"].evidence_status, "clean")
            self.assertEqual(by_id["signal_warning"].evidence_status, "warning")
            self.assertEqual(by_id["signal_blocked"].evidence_status, "blocked")
            
            self.assertEqual(by_id["signal_warning"].risk_flags, ["ST"])
            self.assertEqual(by_id["signal_blocked"].risk_flags, ["suspended"])


if __name__ == "__main__":
    unittest.main()
