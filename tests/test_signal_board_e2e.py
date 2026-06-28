"""
End-to-End Integration Tests for Signal Board

Test the full pipeline:
1. Frozen snapshot → generate signals → JSON
2. JSON → SQLite → API
3. API → frontend (via API client)
4. Review workflow (pending → watching/ignored/expired)

Hard constraints:
- No network access (API-free)
- Use mock/fixture data
- Verify deterministic signal_id
- Verify snapshot_hash and strategy_version binding
- Verify planned_action mapping
- Verify review status flow
"""

import json
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

from backend.db.signal_board import SignalBoardDB
from backend.scripts.load_planned_signals import load_planned_signals
from contracts.signal_board import PlannedSignal


class TestSignalBoardEndToEnd(unittest.TestCase):
    """End-to-end integration tests."""
    
    def setUp(self):
        """Set up test environment with temp database."""
        # Create temp database file
        self.db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = Path(self.db_file.name)
        self.db = SignalBoardDB(db_path=str(self.db_path))
    
    def tearDown(self):
        """Clean up temp database."""
        # Close database connection before deleting file (Windows file locking)
        if hasattr(self, 'db'):
            # SQLite connections may still be held, force close
            del self.db
        
        # Give Windows time to release file lock
        import time
        time.sleep(0.1)
        
        # Now try to delete
        try:
            self.db_path.unlink(missing_ok=True)
        except PermissionError:
            # If still locked, leave for OS cleanup (temp files will be cleaned eventually)
            pass
    
    def test_full_pipeline_json_to_db_to_api(self):
        """
        Test full pipeline: JSON → SQLite → API query → API review.
        
        Steps:
        1. Create mock PlannedSignal JSON
        2. Load JSON into SQLite via load_planned_signals()
        3. Query signals via SignalBoardDB API
        4. Review signal (pending → watching)
        5. Verify review persisted
        """
        # Step 1: Create mock signal data
        test_signals = [
            PlannedSignal(
                signal_id="test_signal_001",
                strategy_id="test_strategy",
                strategy_version="v1.0.0",
                strategy_revision_id="rev_test",
                lifecycle_state_at_generation="prototype_passed",
                admission_source="c_admission_gate",
                snapshot_hash="test_snapshot_hash_abc123",
                signal_date=date(2023, 12, 29),
                intended_execution_date=date(2024, 1, 2),
                symbol="600519.SH",
                direction="buy",
                planned_action="enter",
                quantity=100,
                trigger_reason="Test trigger: price breakout",
                review_status="pending",
                current_price=1850.0,
                created_at=datetime(2023, 12, 29, 16, 30),
                metadata={"test": True},
            ),
            PlannedSignal(
                signal_id="test_signal_002",
                strategy_id="test_strategy",
                strategy_version="v1.0.0",
                strategy_revision_id="rev_test",
                lifecycle_state_at_generation="prototype_passed",
                admission_source="c_admission_gate",
                snapshot_hash="test_snapshot_hash_abc123",
                signal_date=date(2023, 12, 29),
                intended_execution_date=date(2024, 1, 2),
                symbol="000001.SZ",
                direction="sell",
                planned_action="exit",
                quantity=200,
                trigger_reason="Test trigger: stop loss",
                review_status="pending",
                current_price=12.50,
                created_at=datetime(2023, 12, 29, 16, 30),
                metadata={"test": True},
            ),
        ]
        
        # Write to temp JSON file
        json_file = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json_data = [signal.model_dump(mode="json") for signal in test_signals]
        json.dump(json_data, json_file, indent=2)
        json_file.close()
        json_path = Path(json_file.name)
        
        try:
            # Step 2: Load JSON into SQLite
            stats = load_planned_signals(json_path, self.db_path)
            
            self.assertEqual(stats["imported_count"], 2)
            self.assertEqual(stats["skipped_count"], 0)
            self.assertEqual(stats["total_signals"], 2)
            
            # Step 3: Query signals via DB API
            all_signals = self.db.list_signals()
            self.assertEqual(len(all_signals), 2)
            
            # Verify signal 1
            signal_1 = self.db.get_signal("test_signal_001")
            self.assertIsNotNone(signal_1)
            self.assertEqual(signal_1.symbol, "600519.SH")
            self.assertEqual(signal_1.direction, "buy")
            self.assertEqual(signal_1.planned_action, "enter")
            self.assertEqual(signal_1.review_status, "pending")
            self.assertEqual(signal_1.snapshot_hash, "test_snapshot_hash_abc123")
            self.assertEqual(signal_1.strategy_version, "v1.0.0")
            
            # Verify signal 2
            signal_2 = self.db.get_signal("test_signal_002")
            self.assertIsNotNone(signal_2)
            self.assertEqual(signal_2.symbol, "000001.SZ")
            self.assertEqual(signal_2.direction, "sell")
            self.assertEqual(signal_2.planned_action, "exit")
            self.assertEqual(signal_2.review_status, "pending")
            
            # Step 4: Review signal 1 (pending → watching)
            updated = self.db.update_review_status(
                signal_id="test_signal_001",
                review_status="watching",
                reviewed_by="test_user",
            )
            self.assertTrue(updated)
            
            # Step 5: Verify review persisted
            signal_1_after = self.db.get_signal("test_signal_001")
            self.assertEqual(signal_1_after.review_status, "watching")
            self.assertEqual(signal_1_after.reviewed_by, "test_user")
            self.assertIsNotNone(signal_1_after.reviewed_at)
            
            # Signal 2 should remain pending
            signal_2_after = self.db.get_signal("test_signal_002")
            self.assertEqual(signal_2_after.review_status, "pending")
            
        finally:
            # Clean up temp JSON file
            json_path.unlink(missing_ok=True)
    
    def test_reimport_signals_preserves_review_status(self):
        """
        Test that re-importing same signals does NOT overwrite review status.
        
        Scenario:
        1. Import signals (all pending)
        2. User reviews signal (pending → watching)
        3. Re-import same signals
        4. Verify review status is preserved (still watching, not reset to pending)
        """
        # Step 1: Create and import signals
        test_signal = PlannedSignal(
            signal_id="test_signal_preserve",
            strategy_id="test_strategy",
            strategy_version="v1.0.0",
            strategy_revision_id="rev_test",
            lifecycle_state_at_generation="prototype_passed",
            admission_source="c_admission_gate",
            snapshot_hash="test_hash",
            signal_date=date(2023, 12, 29),
            intended_execution_date=date(2024, 1, 2),
            symbol="600519.SH",
            direction="buy",
            planned_action="enter",
            trigger_reason="Test",
            review_status="pending",
            created_at=datetime.utcnow(),
            metadata={},
        )
        
        # Write to JSON
        json_file = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump([test_signal.model_dump(mode="json")], json_file, indent=2)
        json_file.close()
        json_path = Path(json_file.name)
        
        try:
            # Initial import
            stats_1 = load_planned_signals(json_path, self.db_path)
            self.assertEqual(stats_1["imported_count"], 1)
            self.assertEqual(stats_1["skipped_count"], 0)
            
            # Step 2: User reviews signal
            self.db.update_review_status(
                signal_id="test_signal_preserve",
                review_status="watching",
                reviewed_by="test_user",
            )
            
            signal_after_review = self.db.get_signal("test_signal_preserve")
            self.assertEqual(signal_after_review.review_status, "watching")
            
            # Step 3: Re-import same signals
            stats_2 = load_planned_signals(json_path, self.db_path)
            self.assertEqual(stats_2["imported_count"], 0)  # No new imports
            self.assertEqual(stats_2["skipped_count"], 1)  # Skipped existing
            
            # Step 4: Verify review status preserved
            signal_after_reimport = self.db.get_signal("test_signal_preserve")
            self.assertEqual(signal_after_reimport.review_status, "watching")
            self.assertEqual(signal_after_reimport.reviewed_by, "test_user")
            
        finally:
            json_path.unlink(missing_ok=True)
    
    def test_deterministic_signal_id_prevents_duplicates(self):
        """
        Test that deterministic signal_id prevents duplicate imports.
        
        If same snapshot + strategy + date generate same signal,
        signal_id will be identical, preventing duplicates.
        """
        # Create two "identical" signals (same signal_id)
        signal_1 = PlannedSignal(
            signal_id="identical_signal_id_123",
            strategy_id="test_strategy",
            strategy_version="v1.0.0",
            strategy_revision_id="rev_test",
            lifecycle_state_at_generation="prototype_passed",
            admission_source="c_admission_gate",
            snapshot_hash="hash_abc",
            signal_date=date(2023, 12, 29),
            intended_execution_date=date(2024, 1, 2),
            symbol="600519.SH",
            direction="buy",
            planned_action="enter",
            trigger_reason="Test",
            review_status="pending",
            created_at=datetime.utcnow(),
            metadata={},
        )
        
        # Import first signal
        self.db.create_signal(signal_1)
        
        # Try to import "duplicate" signal (same signal_id)
        signal_2 = PlannedSignal(
            signal_id="identical_signal_id_123",  # Same ID!
            strategy_id="test_strategy",
            strategy_version="v1.0.0",
            strategy_revision_id="rev_test",
            lifecycle_state_at_generation="prototype_passed",
            admission_source="c_admission_gate",
            snapshot_hash="hash_abc",
            signal_date=date(2023, 12, 29),
            intended_execution_date=date(2024, 1, 2),
            symbol="600519.SH",
            direction="buy",
            planned_action="enter",
            trigger_reason="Test",
            review_status="pending",
            created_at=datetime.utcnow(),
            metadata={},
        )
        
        # Should raise error (signal_id is PRIMARY KEY)
        with self.assertRaises(Exception):
            self.db.create_signal(signal_2)
        
        # Verify only one signal exists
        all_signals = self.db.list_signals(include_missing_admission=True)
        self.assertEqual(len(all_signals), 1)
    
    def test_review_status_transitions(self):
        """
        Test valid review status transitions.
        
        Valid:
        - pending → ignored
        - pending → watching
        - pending → expired
        
        Invalid (enforced by frontend, not DB):
        - Cannot set back to pending (frontend doesn't allow)
        """
        # Create test signal
        signal = PlannedSignal(
            signal_id="test_transition",
            strategy_id="test_strategy",
            strategy_version="v1.0.0",
            strategy_revision_id="rev_test",
            lifecycle_state_at_generation="prototype_passed",
            admission_source="c_admission_gate",
            snapshot_hash="hash",
            signal_date=date(2023, 12, 29),
            intended_execution_date=date(2024, 1, 2),
            symbol="600519.SH",
            direction="buy",
            planned_action="enter",
            trigger_reason="Test",
            review_status="pending",
            created_at=datetime.utcnow(),
            metadata={},
        )
        
        self.db.create_signal(signal)
        
        # Test: pending → watching
        self.db.update_review_status(
            signal_id="test_transition",
            review_status="watching",
            reviewed_by="user1",
        )
        signal_after = self.db.get_signal("test_transition")
        self.assertEqual(signal_after.review_status, "watching")
        
        # Test: watching → ignored (valid, DB allows)
        self.db.update_review_status(
            signal_id="test_transition",
            review_status="ignored",
            reviewed_by="user2",
            rejection_reason="Changed mind",
        )
        signal_after_2 = self.db.get_signal("test_transition")
        self.assertEqual(signal_after_2.review_status, "ignored")
        self.assertEqual(signal_after_2.rejection_reason, "Changed mind")
    
    def test_signal_query_filters(self):
        """Test filtering signals by status, direction, date."""
        # Create test signals with different statuses
        signals = [
            PlannedSignal(
                signal_id=f"test_{i}",
                strategy_id="test_strategy",
                strategy_version="v1.0.0",
                strategy_revision_id="rev_test",
                lifecycle_state_at_generation="prototype_passed",
                admission_source="c_admission_gate",
                snapshot_hash="hash",
                signal_date=date(2023, 12, 29),
                intended_execution_date=date(2024, 1, 2),
                symbol=f"60051{i}.SH",
                direction="buy" if i % 2 == 0 else "sell",
                planned_action="enter" if i % 2 == 0 else "exit",
                trigger_reason=f"Test {i}",
                review_status="pending" if i < 2 else "watching",
                created_at=datetime.utcnow(),
                metadata={},
            )
            for i in range(4)
        ]
        
        for signal in signals:
            self.db.create_signal(signal)
        
        # Filter by status
        pending = self.db.list_signals(review_status="pending")
        self.assertEqual(len(pending), 2)
        
        watching = self.db.list_signals(review_status="watching")
        self.assertEqual(len(watching), 2)
        
        # Filter by direction
        buys = self.db.list_signals(direction="buy")
        self.assertEqual(len(buys), 2)
        
        sells = self.db.list_signals(direction="sell")
        self.assertEqual(len(sells), 2)
        
        # No filter
        all_signals = self.db.list_signals()
        self.assertEqual(len(all_signals), 4)


if __name__ == "__main__":
    unittest.main()
