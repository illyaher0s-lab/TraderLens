"""
Tests for Signal Expiration Script (M4.1 Phase 2)

Verifies that:
1. pending signals with intended_execution_date < as_of_date are expired
2. pending signals with intended_execution_date >= as_of_date are NOT expired
3. watching / ignored / expired signals are NOT modified
4. reviewed_by is set correctly
5. reviewed_at is set
6. rejection_reason is NOT filled
7. Script is idempotent (repeated runs are safe)
8. Missing DB fails loud
"""

import unittest
import tempfile
from datetime import date, datetime
from pathlib import Path

from backend.db.signal_board import SignalBoardDB
from backend.scripts.expire_signals import expire_signals
from contracts.signal_board import PlannedSignal


class TestSignalExpiration(unittest.TestCase):
    """Test signal expiration logic."""
    
    def _make_signal(
        self,
        signal_id: str,
        intended_execution_date: date,
        review_status: str = "pending",
        symbol: str = "600519.SH"
    ) -> PlannedSignal:
        """Create a test signal."""
        return PlannedSignal(
            signal_id=signal_id,
            strategy_id="test_strategy",
            strategy_version="v1.0.0",
            snapshot_hash="test_hash",
            signal_date=date(2023, 12, 29),
            intended_execution_date=intended_execution_date,
            symbol=symbol,
            direction="buy",
            planned_action="enter",
            quantity=100,
            trigger_reason="Test trigger",
            review_status=review_status,
            created_at=datetime(2023, 12, 29, 16, 0, 0)
        )
    
    def test_pending_signal_before_date_is_expired(self):
        """Pending signal with intended_execution_date < as_of_date is expired."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = SignalBoardDB(db_path)
            
            # Create pending signal with old intended_execution_date
            signal = self._make_signal(
                signal_id="old_pending",
                intended_execution_date=date(2023, 12, 30)
            )
            db.create_signal(signal)
            
            # Expire as of 2024-01-02 (after 2023-12-30)
            expired_count, skipped_count = expire_signals(
                db_path=db_path,
                as_of_date=date(2024, 1, 2)
            )
            
            self.assertEqual(expired_count, 1)
            
            # Verify signal is now expired
            retrieved = db.get_signal(signal.signal_id)
            self.assertEqual(retrieved.review_status, "expired")
            self.assertEqual(retrieved.reviewed_by, "system_expiration")
            self.assertIsNotNone(retrieved.reviewed_at)
            self.assertIsNone(retrieved.rejection_reason)
    
    def test_pending_signal_on_date_is_not_expired(self):
        """Pending signal with intended_execution_date == as_of_date is NOT expired."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = SignalBoardDB(db_path)
            
            # Create pending signal for exactly as_of_date
            signal = self._make_signal(
                signal_id="today_pending",
                intended_execution_date=date(2024, 1, 2)
            )
            db.create_signal(signal)
            
            # Expire as of 2024-01-02 (same day)
            expired_count, _ = expire_signals(
                db_path=db_path,
                as_of_date=date(2024, 1, 2)
            )
            
            self.assertEqual(expired_count, 0)
            
            # Verify signal is still pending
            retrieved = db.get_signal(signal.signal_id)
            self.assertEqual(retrieved.review_status, "pending")
    
    def test_pending_signal_after_date_is_not_expired(self):
        """Pending signal with intended_execution_date > as_of_date is NOT expired."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = SignalBoardDB(db_path)
            
            # Create pending signal with future intended_execution_date
            signal = self._make_signal(
                signal_id="future_pending",
                intended_execution_date=date(2024, 1, 5)
            )
            db.create_signal(signal)
            
            # Expire as of 2024-01-02 (before 2024-01-05)
            expired_count, _ = expire_signals(
                db_path=db_path,
                as_of_date=date(2024, 1, 2)
            )
            
            self.assertEqual(expired_count, 0)
            
            # Verify signal is still pending
            retrieved = db.get_signal(signal.signal_id)
            self.assertEqual(retrieved.review_status, "pending")
    
    def test_ignored_signal_not_modified(self):
        """Ignored signals are NOT modified."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = SignalBoardDB(db_path)
            
            # Create ignored signal with old intended_execution_date
            signal = self._make_signal(
                signal_id="ignored_signal",
                intended_execution_date=date(2023, 12, 30),
                review_status="ignored"
            )
            signal.reviewed_by = "human_user"
            signal.reviewed_at = datetime(2023, 12, 30, 10, 0, 0)
            signal.rejection_reason = "User decided not to follow"
            
            db.create_signal(signal)
            
            # Expire as of 2024-01-02
            expired_count, _ = expire_signals(
                db_path=db_path,
                as_of_date=date(2024, 1, 2)
            )
            
            self.assertEqual(expired_count, 0)
            
            # Verify signal is still ignored with original metadata
            retrieved = db.get_signal(signal.signal_id)
            self.assertEqual(retrieved.review_status, "ignored")
            self.assertEqual(retrieved.reviewed_by, "human_user")
            self.assertEqual(retrieved.rejection_reason, "User decided not to follow")
    
    def test_watching_signal_not_modified(self):
        """Watching signals are NOT modified."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = SignalBoardDB(db_path)
            
            # Create watching signal with old intended_execution_date
            signal = self._make_signal(
                signal_id="watching_signal",
                intended_execution_date=date(2023, 12, 30),
                review_status="watching"
            )
            signal.reviewed_by = "human_user"
            signal.reviewed_at = datetime(2023, 12, 30, 10, 0, 0)
            
            db.create_signal(signal)
            
            # Expire as of 2024-01-02
            expired_count, _ = expire_signals(
                db_path=db_path,
                as_of_date=date(2024, 1, 2)
            )
            
            self.assertEqual(expired_count, 0)
            
            # Verify signal is still watching
            retrieved = db.get_signal(signal.signal_id)
            self.assertEqual(retrieved.review_status, "watching")
            self.assertEqual(retrieved.reviewed_by, "human_user")
    
    def test_already_expired_signal_not_modified(self):
        """Already expired signals are NOT modified."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = SignalBoardDB(db_path)
            
            # Create expired signal
            signal = self._make_signal(
                signal_id="expired_signal",
                intended_execution_date=date(2023, 12, 30),
                review_status="expired"
            )
            signal.reviewed_by = "previous_expiration"
            signal.reviewed_at = datetime(2023, 12, 31, 10, 0, 0)
            
            db.create_signal(signal)
            
            # Expire as of 2024-01-02
            expired_count, _ = expire_signals(
                db_path=db_path,
                as_of_date=date(2024, 1, 2)
            )
            
            self.assertEqual(expired_count, 0)
            
            # Verify signal metadata not changed
            retrieved = db.get_signal(signal.signal_id)
            self.assertEqual(retrieved.review_status, "expired")
            self.assertEqual(retrieved.reviewed_by, "previous_expiration")
            self.assertEqual(retrieved.reviewed_at, datetime(2023, 12, 31, 10, 0, 0))
    
    def test_reviewed_by_is_set_correctly(self):
        """reviewed_by is set to system_expiration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = SignalBoardDB(db_path)
            
            signal = self._make_signal(
                signal_id="test_signal",
                intended_execution_date=date(2023, 12, 30)
            )
            db.create_signal(signal)
            
            # Expire with default reviewed_by
            expire_signals(
                db_path=db_path,
                as_of_date=date(2024, 1, 2)
            )
            
            retrieved = db.get_signal(signal.signal_id)
            self.assertEqual(retrieved.reviewed_by, "system_expiration")
    
    def test_reviewed_by_custom_value(self):
        """reviewed_by can be customized."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = SignalBoardDB(db_path)
            
            signal = self._make_signal(
                signal_id="test_signal",
                intended_execution_date=date(2023, 12, 30)
            )
            db.create_signal(signal)
            
            # Expire with custom reviewed_by
            expire_signals(
                db_path=db_path,
                as_of_date=date(2024, 1, 2),
                reviewed_by="manual_cleanup"
            )
            
            retrieved = db.get_signal(signal.signal_id)
            self.assertEqual(retrieved.reviewed_by, "manual_cleanup")
    
    def test_reviewed_at_is_set(self):
        """reviewed_at is set when signal is expired."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = SignalBoardDB(db_path)
            
            signal = self._make_signal(
                signal_id="test_signal",
                intended_execution_date=date(2023, 12, 30)
            )
            db.create_signal(signal)
            
            # Expire
            expire_signals(
                db_path=db_path,
                as_of_date=date(2024, 1, 2)
            )
            
            retrieved = db.get_signal(signal.signal_id)
            self.assertIsNotNone(retrieved.reviewed_at)
    
    def test_rejection_reason_not_filled(self):
        """rejection_reason is NOT filled for expired signals."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = SignalBoardDB(db_path)
            
            signal = self._make_signal(
                signal_id="test_signal",
                intended_execution_date=date(2023, 12, 30)
            )
            db.create_signal(signal)
            
            # Expire
            expire_signals(
                db_path=db_path,
                as_of_date=date(2024, 1, 2)
            )
            
            retrieved = db.get_signal(signal.signal_id)
            self.assertIsNone(retrieved.rejection_reason)
    
    def test_idempotent_repeated_runs(self):
        """Repeated runs are idempotent (no duplicate updates)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = SignalBoardDB(db_path)
            
            signal = self._make_signal(
                signal_id="test_signal",
                intended_execution_date=date(2023, 12, 30)
            )
            db.create_signal(signal)
            
            # First run
            expired_count_1, _ = expire_signals(
                db_path=db_path,
                as_of_date=date(2024, 1, 2)
            )
            self.assertEqual(expired_count_1, 1)
            
            # Second run (should be idempotent)
            expired_count_2, _ = expire_signals(
                db_path=db_path,
                as_of_date=date(2024, 1, 2)
            )
            self.assertEqual(expired_count_2, 0)
            
            # Third run (still idempotent)
            expired_count_3, _ = expire_signals(
                db_path=db_path,
                as_of_date=date(2024, 1, 2)
            )
            self.assertEqual(expired_count_3, 0)
    
    def test_missing_db_fails_loud(self):
        """Missing DB raises FileNotFoundError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "nonexistent.db"
            
            with self.assertRaises(FileNotFoundError):
                expire_signals(
                    db_path=db_path,
                    as_of_date=date(2024, 1, 2)
                )
    
    def test_multiple_signals_expired_together(self):
        """Multiple pending signals are expired together."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = SignalBoardDB(db_path)
            
            # Create 3 pending signals with old dates
            for i in range(3):
                signal = self._make_signal(
                    signal_id=f"old_signal_{i}",
                    intended_execution_date=date(2023, 12, 28 + i),
                    symbol=f"60051{i}.SH"
                )
                db.create_signal(signal)
            
            # Create 1 pending signal with future date
            future_signal = self._make_signal(
                signal_id="future_signal",
                intended_execution_date=date(2024, 1, 5)
            )
            db.create_signal(future_signal)
            
            # Expire as of 2024-01-02
            expired_count, _ = expire_signals(
                db_path=db_path,
                as_of_date=date(2024, 1, 2)
            )
            
            self.assertEqual(expired_count, 3)
            
            # Verify 3 old signals are expired
            for i in range(3):
                retrieved = db.get_signal(f"old_signal_{i}")
                self.assertEqual(retrieved.review_status, "expired")
            
            # Verify future signal is still pending
            future_retrieved = db.get_signal("future_signal")
            self.assertEqual(future_retrieved.review_status, "pending")


if __name__ == "__main__":
    unittest.main()
