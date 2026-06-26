"""
Unit tests for Signal Board data models.

Tests PlannedSignal validation, defaults, and serialization.
"""

import unittest
from datetime import date, datetime

from contracts.signal_board import (
    PlannedSignal,
    SignalReviewRequest,
    SignalBatchReviewRequest,
    SignalSummary
)


class TestPlannedSignal(unittest.TestCase):
    """Test PlannedSignal model validation."""
    
    def test_minimal_signal(self):
        """Test creating signal with minimal required fields."""
        signal = PlannedSignal(
            signal_id="test-uuid",
            strategy_id="momentum_v2",
            strategy_version="v2.1.0",
            snapshot_hash="abc123",
            signal_date=date(2023, 12, 29),
            intended_execution_date=date(2024, 1, 2),
            symbol="600519.SH",
            direction="buy",
            planned_action="enter",
            trigger_reason="Price broke above 5-day high",
            created_at=datetime(2023, 12, 29, 16, 30)
        )
        
        self.assertEqual(signal.signal_id, "test-uuid")
        self.assertEqual(signal.direction, "buy")
        self.assertEqual(signal.planned_action, "enter")
        self.assertEqual(signal.review_status, "pending")  # Default
        self.assertIsNone(signal.quantity)  # Optional
        self.assertIsNone(signal.reviewed_at)
        self.assertEqual(signal.metadata, {})  # Default empty dict
    
    def test_full_signal(self):
        """Test creating signal with all fields."""
        signal = PlannedSignal(
            signal_id="test-uuid",
            strategy_id="momentum_v2",
            strategy_version="v2.1.0",
            snapshot_hash="abc123",
            signal_date=date(2023, 12, 29),
            intended_execution_date=date(2024, 1, 2),
            symbol="600519.SH",
            direction="sell",
            planned_action="exit",
            quantity=100,
            trigger_reason="Price fell below 10-day low",
            review_status="watching",
            reviewed_at=datetime(2023, 12, 29, 17, 0),
            reviewed_by="trader1",
            rejection_reason=None,
            current_price=1850.0,
            position_before=200,
            created_at=datetime(2023, 12, 29, 16, 30),
            metadata={"confidence": 0.75}
        )
        
        self.assertEqual(signal.quantity, 100)
        self.assertEqual(signal.review_status, "watching")
        self.assertEqual(signal.reviewed_by, "trader1")
        self.assertEqual(signal.metadata["confidence"], 0.75)
    
    def test_direction_validation(self):
        """Test direction field only accepts 'buy' or 'sell'."""
        with self.assertRaises(ValueError):
            PlannedSignal(
                signal_id="test-uuid",
                strategy_id="momentum_v2",
                strategy_version="v2.1.0",
                snapshot_hash="abc123",
                signal_date=date(2023, 12, 29),
                intended_execution_date=date(2024, 1, 2),
                symbol="600519.SH",
                direction="hold",  # Invalid
                planned_action="enter",
                trigger_reason="Test",
                created_at=datetime.utcnow()
            )
    
    def test_review_status_validation(self):
        """Test review_status field only accepts valid values."""
        with self.assertRaises(ValueError):
            PlannedSignal(
                signal_id="test-uuid",
                strategy_id="momentum_v2",
                strategy_version="v2.1.0",
                snapshot_hash="abc123",
                signal_date=date(2023, 12, 29),
                intended_execution_date=date(2024, 1, 2),
                symbol="600519.SH",
                direction="buy",
                planned_action="enter",
                trigger_reason="Test",
                review_status="approved_for_execution",  # Invalid (not in M4)
                created_at=datetime.utcnow()
            )
    
    def test_serialization(self):
        """Test signal can be serialized to/from JSON."""
        signal = PlannedSignal(
            signal_id="test-uuid",
            strategy_id="momentum_v2",
            strategy_version="v2.1.0",
            snapshot_hash="abc123",
            signal_date=date(2023, 12, 29),
            intended_execution_date=date(2024, 1, 2),
            symbol="600519.SH",
            direction="buy",
            planned_action="enter",
            quantity=100,
            trigger_reason="Price broke above 5-day high",
            created_at=datetime(2023, 12, 29, 16, 30),
            metadata={"test": "value"}
        )
        
        # Serialize to dict
        signal_dict = signal.model_dump()
        self.assertIsInstance(signal_dict, dict)
        self.assertEqual(signal_dict["signal_id"], "test-uuid")
        
        # Deserialize from dict
        signal_restored = PlannedSignal(**signal_dict)
        self.assertEqual(signal_restored.signal_id, signal.signal_id)
        self.assertEqual(signal_restored.metadata, signal.metadata)
    
    def test_json_export(self):
        """Test signal can be exported to JSON string."""
        signal = PlannedSignal(
            signal_id="test-uuid",
            strategy_id="momentum_v2",
            strategy_version="v2.1.0",
            snapshot_hash="abc123",
            signal_date=date(2023, 12, 29),
            intended_execution_date=date(2024, 1, 2),
            symbol="600519.SH",
            direction="buy",
            planned_action="enter",
            trigger_reason="Test",
            created_at=datetime(2023, 12, 29, 16, 30)
        )
        
        json_str = signal.model_dump_json()
        self.assertIsInstance(json_str, str)
        self.assertIn("test-uuid", json_str)
        self.assertIn("600519.SH", json_str)


class TestSignalReviewRequest(unittest.TestCase):
    """Test SignalReviewRequest model validation."""
    
    def test_valid_review_request(self):
        """Test creating valid review request."""
        request = SignalReviewRequest(
            review_status="watching",
            reviewed_by="trader1"
        )
        self.assertEqual(request.review_status, "watching")
        self.assertIsNone(request.rejection_reason)
    
    def test_review_with_rejection_reason(self):
        """Test review request with rejection reason."""
        request = SignalReviewRequest(
            review_status="ignored",
            reviewed_by="trader1",
            rejection_reason="Low liquidity"
        )
        self.assertEqual(request.rejection_reason, "Low liquidity")
    
    def test_cannot_set_pending_status(self):
        """Test that review_status cannot be set back to 'pending'."""
        with self.assertRaises(ValueError):
            SignalReviewRequest(
                review_status="pending",  # Not allowed in review request
                reviewed_by="trader1"
            )


class TestSignalBatchReviewRequest(unittest.TestCase):
    """Test SignalBatchReviewRequest model validation."""
    
    def test_valid_batch_request(self):
        """Test creating valid batch review request."""
        request = SignalBatchReviewRequest(
            signal_ids=["uuid1", "uuid2", "uuid3"],
            review_status="watching",
            reviewed_by="trader1"
        )
        self.assertEqual(len(request.signal_ids), 3)
        self.assertEqual(request.review_status, "watching")
    
    def test_empty_signal_ids(self):
        """Test batch request with empty signal_ids list."""
        request = SignalBatchReviewRequest(
            signal_ids=[],
            review_status="watching",
            reviewed_by="trader1"
        )
        self.assertEqual(len(request.signal_ids), 0)


class TestSignalSummary(unittest.TestCase):
    """Test SignalSummary model."""
    
    def test_summary_creation(self):
        """Test creating signal summary."""
        summary = SignalSummary(
            signal_date=date(2023, 12, 29),
            total_count=15,
            by_status={"pending": 10, "reviewed": 5},
            by_direction={"buy": 8, "sell": 7},
            pending_count=10
        )
        
        self.assertEqual(summary.total_count, 15)
        self.assertEqual(summary.pending_count, 10)
        self.assertEqual(summary.by_status["pending"], 10)
        self.assertEqual(summary.by_direction["buy"], 8)


if __name__ == "__main__":
    unittest.main()
