"""
Unit tests for Signal Board database layer.

Tests SignalBoardDB CRUD operations with in-memory SQLite.
"""

import unittest
import tempfile
from datetime import date, datetime
from pathlib import Path

from contracts.signal_board import PlannedSignal
from backend.db.signal_board import SignalBoardDB


class TestSignalBoardDB(unittest.TestCase):
    """Test SignalBoardDB operations."""
    
    def setUp(self):
        """Create temporary database for each test."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_signals.db"
        self.db = SignalBoardDB(self.db_path)
    
    def tearDown(self):
        """Clean up temporary database."""
        self.temp_dir.cleanup()
    
    def _create_test_signal(self, signal_id: str = "test-uuid-1", **overrides) -> PlannedSignal:
        """Helper to create test signal with defaults."""
        defaults = {
            "signal_id": signal_id,
            "strategy_id": "momentum_v2",
            "strategy_version": "v2.1.0",
            "strategy_revision_id": "rev_momentum_v2",
            "lifecycle_state_at_generation": "prototype_passed",
            "admission_source": "c_admission_gate",
            "snapshot_hash": "abc123",
            "signal_date": date(2023, 12, 29),
            "intended_execution_date": date(2024, 1, 2),
            "symbol": "600519.SH",
            "direction": "buy",
            "planned_action": "enter",
            "trigger_reason": "Price broke above 5-day high",
            "created_at": datetime(2023, 12, 29, 16, 30)
        }
        defaults.update(overrides)
        return PlannedSignal(**defaults)
    
    def test_create_and_get_signal(self):
        """Test creating and retrieving a signal."""
        signal = self._create_test_signal()
        
        # Create
        self.db.create_signal(signal)
        
        # Retrieve
        retrieved = self.db.get_signal(signal.signal_id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.signal_id, signal.signal_id)
        self.assertEqual(retrieved.symbol, signal.symbol)
        self.assertEqual(retrieved.direction, signal.direction)
        self.assertEqual(retrieved.review_status, "pending")
    
    def test_get_nonexistent_signal(self):
        """Test retrieving non-existent signal returns None."""
        retrieved = self.db.get_signal("nonexistent-uuid")
        self.assertIsNone(retrieved)
    
    def test_create_duplicate_signal_fails(self):
        """Test creating signal with duplicate ID raises error."""
        signal = self._create_test_signal()
        self.db.create_signal(signal)
        
        # Attempt to create duplicate
        with self.assertRaises(Exception):  # sqlite3.IntegrityError
            self.db.create_signal(signal)
    
    def test_list_signals_no_filter(self):
        """Test listing all signals."""
        # Create multiple signals
        signal1 = self._create_test_signal(signal_id="uuid-1", symbol="600519.SH")
        signal2 = self._create_test_signal(signal_id="uuid-2", symbol="000001.SZ")
        signal3 = self._create_test_signal(signal_id="uuid-3", symbol="600036.SH")
        
        self.db.create_signal(signal1)
        self.db.create_signal(signal2)
        self.db.create_signal(signal3)
        
        # List all
        signals = self.db.list_signals()
        self.assertEqual(len(signals), 3)
    
    def test_list_signals_filter_by_date(self):
        """Test listing signals filtered by signal_date."""
        # Create signals on different dates
        signal1 = self._create_test_signal(
            signal_id="uuid-1",
            signal_date=date(2023, 12, 29)
        )
        signal2 = self._create_test_signal(
            signal_id="uuid-2",
            signal_date=date(2023, 12, 30)
        )
        
        self.db.create_signal(signal1)
        self.db.create_signal(signal2)
        
        # Filter by date
        signals = self.db.list_signals(signal_date=date(2023, 12, 29))
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].signal_id, "uuid-1")
    
    def test_list_signals_filter_by_status(self):
        """Test listing signals filtered by review_status."""
        # Create signals with different statuses
        signal1 = self._create_test_signal(
            signal_id="uuid-1",
            review_status="pending"
        )
        signal2 = self._create_test_signal(
            signal_id="uuid-2",
            review_status="watching",
            reviewed_at=datetime.utcnow(),
            reviewed_by="trader1"
        )
        
        self.db.create_signal(signal1)
        self.db.create_signal(signal2)
        
        # Filter by status
        pending = self.db.list_signals(review_status="pending")
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].review_status, "pending")
        
        watching = self.db.list_signals(review_status="watching")
        self.assertEqual(len(watching), 1)
        self.assertEqual(watching[0].review_status, "watching")
    
    def test_list_signals_filter_by_direction(self):
        """Test listing signals filtered by direction."""
        signal1 = self._create_test_signal(signal_id="uuid-1", direction="buy")
        signal2 = self._create_test_signal(signal_id="uuid-2", direction="sell")
        
        self.db.create_signal(signal1)
        self.db.create_signal(signal2)
        
        # Filter by direction
        buy_signals = self.db.list_signals(direction="buy")
        self.assertEqual(len(buy_signals), 1)
        self.assertEqual(buy_signals[0].direction, "buy")
    
    def test_list_signals_pagination(self):
        """Test pagination with limit and offset."""
        # Create 5 signals
        for i in range(5):
            signal = self._create_test_signal(signal_id=f"uuid-{i}")
            self.db.create_signal(signal)
        
        # First page (limit=2)
        page1 = self.db.list_signals(limit=2, offset=0)
        self.assertEqual(len(page1), 2)
        
        # Second page
        page2 = self.db.list_signals(limit=2, offset=2)
        self.assertEqual(len(page2), 2)
        
        # Third page
        page3 = self.db.list_signals(limit=2, offset=4)
        self.assertEqual(len(page3), 1)
    
    def test_update_review_status(self):
        """Test updating review status."""
        signal = self._create_test_signal()
        self.db.create_signal(signal)
        
        # Update to watching
        updated = self.db.update_review_status(
            signal_id=signal.signal_id,
            review_status="watching",
            reviewed_by="trader1"
        )
        self.assertTrue(updated)
        
        # Verify update
        retrieved = self.db.get_signal(signal.signal_id)
        self.assertEqual(retrieved.review_status, "watching")
        self.assertEqual(retrieved.reviewed_by, "trader1")
        self.assertIsNotNone(retrieved.reviewed_at)
    
    def test_update_review_status_with_rejection_reason(self):
        """Test updating review status to ignored with reason."""
        signal = self._create_test_signal()
        self.db.create_signal(signal)
        
        # Update to ignored with reason
        updated = self.db.update_review_status(
            signal_id=signal.signal_id,
            review_status="ignored",
            reviewed_by="trader1",
            rejection_reason="Low liquidity"
        )
        self.assertTrue(updated)
        
        # Verify update
        retrieved = self.db.get_signal(signal.signal_id)
        self.assertEqual(retrieved.review_status, "ignored")
        self.assertEqual(retrieved.rejection_reason, "Low liquidity")
    
    def test_update_nonexistent_signal(self):
        """Test updating non-existent signal returns False."""
        updated = self.db.update_review_status(
            signal_id="nonexistent-uuid",
            review_status="reviewed",
            reviewed_by="trader1"
        )
        self.assertFalse(updated)
    
    def test_batch_update_review_status(self):
        """Test batch updating review status."""
        # Create multiple signals
        signal1 = self._create_test_signal(signal_id="uuid-1")
        signal2 = self._create_test_signal(signal_id="uuid-2")
        signal3 = self._create_test_signal(signal_id="uuid-3")
        
        self.db.create_signal(signal1)
        self.db.create_signal(signal2)
        self.db.create_signal(signal3)
        
        # Batch update
        updated_count = self.db.batch_update_review_status(
            signal_ids=["uuid-1", "uuid-2"],
            review_status="watching",
            reviewed_by="trader1"
        )
        self.assertEqual(updated_count, 2)
        
        # Verify updates
        s1 = self.db.get_signal("uuid-1")
        s2 = self.db.get_signal("uuid-2")
        s3 = self.db.get_signal("uuid-3")
        
        self.assertEqual(s1.review_status, "watching")
        self.assertEqual(s2.review_status, "watching")
        self.assertEqual(s3.review_status, "pending")  # Not updated
    
    def test_batch_update_empty_list(self):
        """Test batch update with empty list returns 0."""
        updated_count = self.db.batch_update_review_status(
            signal_ids=[],
            review_status="reviewed",
            reviewed_by="trader1"
        )
        self.assertEqual(updated_count, 0)
    
    def test_get_summary(self):
        """Test getting summary statistics."""
        signal_date = date(2023, 12, 29)
        
        # Create signals with different statuses and directions
        signals = [
            self._create_test_signal(signal_id="uuid-1", signal_date=signal_date, direction="buy", review_status="pending"),
            self._create_test_signal(signal_id="uuid-2", signal_date=signal_date, direction="buy", review_status="pending"),
            self._create_test_signal(signal_id="uuid-3", signal_date=signal_date, direction="sell", planned_action="exit", review_status="watching", reviewed_at=datetime.utcnow(), reviewed_by="trader1"),
            self._create_test_signal(signal_id="uuid-4", signal_date=signal_date, direction="sell", planned_action="exit", review_status="ignored", reviewed_at=datetime.utcnow(), reviewed_by="trader1"),
        ]
        
        for signal in signals:
            self.db.create_signal(signal)
        
        # Get summary
        summary = self.db.get_summary(signal_date)
        
        self.assertEqual(summary.signal_date, signal_date)
        self.assertEqual(summary.total_count, 4)
        self.assertEqual(summary.pending_count, 2)
        self.assertEqual(summary.by_status["pending"], 2)
        self.assertEqual(summary.by_status["watching"], 1)
        self.assertEqual(summary.by_status["ignored"], 1)
        self.assertEqual(summary.by_direction["buy"], 2)
        self.assertEqual(summary.by_direction["sell"], 2)
    
    def test_get_summary_empty_date(self):
        """Test summary for date with no signals."""
        summary = self.db.get_summary(date(2023, 12, 30))
        
        self.assertEqual(summary.total_count, 0)
        self.assertEqual(summary.pending_count, 0)
        self.assertEqual(summary.by_status, {})
        self.assertEqual(summary.by_direction, {})
    
    def test_metadata_persistence(self):
        """Test that metadata dict is persisted correctly."""
        signal = self._create_test_signal(
            metadata={
                "strategy_params": {"lookback": 5},
                "risk_filters": {"max_position": 10000}
            }
        )
        
        self.db.create_signal(signal)
        
        # Retrieve and verify metadata
        retrieved = self.db.get_signal(signal.signal_id)
        self.assertEqual(retrieved.metadata["strategy_params"]["lookback"], 5)
        self.assertEqual(retrieved.metadata["risk_filters"]["max_position"], 10000)


if __name__ == "__main__":
    unittest.main()
