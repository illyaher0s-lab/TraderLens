"""
Unit tests for Signal Board REST API.

Tests FastAPI endpoints with mock database.
"""

import unittest
import tempfile
from datetime import date, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from fastapi import FastAPI

from contracts.signal_board import PlannedSignal
from backend.api.signal_board import router, init_signal_board_api, get_db


class TestSignalBoardAPI(unittest.TestCase):
    """Test Signal Board API endpoints."""
    
    def setUp(self):
        """Set up test client with temporary database."""
        # Create temporary database
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_signals.db"
        
        # Initialize API
        init_signal_board_api(str(self.db_path))
        
        # Create FastAPI app with router
        self.app = FastAPI()
        self.app.include_router(router)
        
        # Create test client
        self.client = TestClient(self.app)
        
        # Get DB instance for setup
        self.db = get_db()
    
    def tearDown(self):
        """Clean up temporary database."""
        self.temp_dir.cleanup()
    
    def _create_test_signal(self, signal_id: str = "test-uuid-1", **overrides) -> PlannedSignal:
        """Helper to create test signal."""
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
    
    def test_list_signals_empty(self):
        """Test listing signals when database is empty."""
        response = self.client.get("/api/signals")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["items"], [])
        self.assertEqual(data["total"], 0)
        self.assertFalse(data["has_more"])
    
    def test_list_signals(self):
        """Test listing signals."""
        # Create test signals
        signal1 = self._create_test_signal(signal_id="uuid-1")
        signal2 = self._create_test_signal(signal_id="uuid-2")
        
        self.db.create_signal(signal1)
        self.db.create_signal(signal2)
        
        # List all
        response = self.client.get("/api/signals")
        self.assertEqual(response.status_code, 200)
        
        signals = response.json()["items"]
        self.assertEqual(len(signals), 2)
    
    def test_list_signals_filter_by_status(self):
        """Test listing signals filtered by status."""
        # Create signals with different statuses
        signal1 = self._create_test_signal(signal_id="uuid-1", review_status="pending")
        signal2 = self._create_test_signal(
            signal_id="uuid-2",
            review_status="watching",
            reviewed_at=datetime.utcnow(),
            reviewed_by="trader1"
        )
        
        self.db.create_signal(signal1)
        self.db.create_signal(signal2)
        
        # Filter by pending
        response = self.client.get("/api/signals?status=pending")
        self.assertEqual(response.status_code, 200)
        signals = response.json()["items"]
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["review_status"], "pending")
    
    def test_list_signals_filter_by_date(self):
        """Test listing signals filtered by signal_date."""
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
        response = self.client.get("/api/signals?signal_date=2023-12-29")
        self.assertEqual(response.status_code, 200)
        signals = response.json()["items"]
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["signal_date"], "2023-12-29")
    
    def test_list_signals_pagination(self):
        """Test pagination."""
        # Create 5 signals
        for i in range(5):
            signal = self._create_test_signal(signal_id=f"uuid-{i}")
            self.db.create_signal(signal)
        
        # First page
        response = self.client.get("/api/signals?limit=2&offset=0")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        signals = data["items"]
        self.assertEqual(len(signals), 2)
        self.assertEqual(data["total"], 5)
        self.assertTrue(data["has_more"])
        
        # Second page
        response = self.client.get("/api/signals?limit=2&offset=2")
        self.assertEqual(response.status_code, 200)
        signals = response.json()["items"]
        self.assertEqual(len(signals), 2)

    def test_list_signals_rejects_limit_above_500(self):
        """Signal list rejects limits above the supported page size."""
        response = self.client.get("/api/signals?limit=501")
        self.assertEqual(response.status_code, 400)

    def test_list_signals_rejects_negative_offset(self):
        """Signal list rejects negative offsets."""
        response = self.client.get("/api/signals?offset=-1")
        self.assertEqual(response.status_code, 400)

    def test_list_signals_invalid_date_returns_400(self):
        """Invalid date filter returns 400 instead of a server error."""
        response = self.client.get("/api/signals?signal_date=not-a-date")
        self.assertEqual(response.status_code, 400)
    
    def test_get_signal(self):
        """Test getting a single signal."""
        signal = self._create_test_signal(signal_id="uuid-1")
        self.db.create_signal(signal)
        
        response = self.client.get("/api/signals/uuid-1")
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertEqual(data["signal_id"], "uuid-1")
        self.assertEqual(data["symbol"], "600519.SH")
    
    def test_get_signal_not_found(self):
        """Test getting non-existent signal returns 404."""
        response = self.client.get("/api/signals/nonexistent-uuid")
        self.assertEqual(response.status_code, 404)
    
    def test_review_signal(self):
        """Test reviewing a signal."""
        signal = self._create_test_signal(signal_id="uuid-1")
        self.db.create_signal(signal)
        
        # Review signal
        response = self.client.post(
            "/api/signals/uuid-1/review",
            json={
                "review_status": "watching",
                "reviewed_by": "trader1"
            }
        )
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertEqual(data["review_status"], "watching")
        self.assertEqual(data["reviewed_by"], "trader1")
        self.assertIsNotNone(data["reviewed_at"])
    
    def test_review_signal_with_rejection_reason(self):
        """Test reviewing signal with rejection reason."""
        signal = self._create_test_signal(signal_id="uuid-1")
        self.db.create_signal(signal)
        
        # Ignore signal with reason
        response = self.client.post(
            "/api/signals/uuid-1/review",
            json={
                "review_status": "ignored",
                "reviewed_by": "trader1",
                "rejection_reason": "Low liquidity"
            }
        )
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertEqual(data["review_status"], "ignored")
        self.assertEqual(data["rejection_reason"], "Low liquidity")
    
    def test_review_signal_ignored_without_reason_fails(self):
        """Test that ignoring signal without reason returns 400."""
        signal = self._create_test_signal(signal_id="uuid-1")
        self.db.create_signal(signal)
        
        # Attempt to ignore without reason
        response = self.client.post(
            "/api/signals/uuid-1/review",
            json={
                "review_status": "ignored",
                "reviewed_by": "trader1"
                # Missing rejection_reason
            }
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("rejection_reason", response.json()["detail"].lower())
    
    def test_review_signal_not_found(self):
        """Test reviewing non-existent signal returns 404."""
        response = self.client.post(
            "/api/signals/nonexistent-uuid/review",
            json={
                "review_status": "watching",
                "reviewed_by": "trader1"
            }
        )
        self.assertEqual(response.status_code, 404)
    
    def test_batch_review_signals(self):
        """Test batch reviewing signals."""
        # Create test signals
        signal1 = self._create_test_signal(signal_id="uuid-1")
        signal2 = self._create_test_signal(signal_id="uuid-2")
        signal3 = self._create_test_signal(signal_id="uuid-3")
        
        self.db.create_signal(signal1)
        self.db.create_signal(signal2)
        self.db.create_signal(signal3)
        
        # Batch review
        response = self.client.post(
            "/api/signals/batch-review",
            json={
                "signal_ids": ["uuid-1", "uuid-2"],
                "review_status": "watching",
                "reviewed_by": "trader1"
            }
        )
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertEqual(data["updated_count"], 2)
        self.assertEqual(len(data["signal_ids"]), 2)
        
        # Verify updates
        s1 = self.db.get_signal("uuid-1")
        s2 = self.db.get_signal("uuid-2")
        s3 = self.db.get_signal("uuid-3")
        
        self.assertEqual(s1.review_status, "watching")
        self.assertEqual(s2.review_status, "watching")
        self.assertEqual(s3.review_status, "pending")  # Not updated
    
    def test_batch_review_with_rejection_reason(self):
        """Test batch review with rejection reason."""
        signal1 = self._create_test_signal(signal_id="uuid-1")
        signal2 = self._create_test_signal(signal_id="uuid-2")
        
        self.db.create_signal(signal1)
        self.db.create_signal(signal2)
        
        # Batch ignore with reason
        response = self.client.post(
            "/api/signals/batch-review",
            json={
                "signal_ids": ["uuid-1", "uuid-2"],
                "review_status": "ignored",
                "reviewed_by": "trader1",
                "rejection_reason": "End of day, no time"
            }
        )
        self.assertEqual(response.status_code, 200)
        
        # Verify rejection reasons
        s1 = self.db.get_signal("uuid-1")
        self.assertEqual(s1.rejection_reason, "End of day, no time")
    
    def test_batch_review_ignored_without_reason_fails(self):
        """Test batch ignore without reason returns 400."""
        signal1 = self._create_test_signal(signal_id="uuid-1")
        self.db.create_signal(signal1)
        
        response = self.client.post(
            "/api/signals/batch-review",
            json={
                "signal_ids": ["uuid-1"],
                "review_status": "ignored",
                "reviewed_by": "trader1"
                # Missing rejection_reason
            }
        )
        self.assertEqual(response.status_code, 400)
    
    def test_get_summary(self):
        """Test getting summary statistics."""
        signal_date = date(2023, 12, 29)
        
        # Create signals
        signals = [
            self._create_test_signal(signal_id="uuid-1", signal_date=signal_date, direction="buy", review_status="pending"),
            self._create_test_signal(signal_id="uuid-2", signal_date=signal_date, direction="buy", review_status="pending"),
            self._create_test_signal(
                signal_id="uuid-3",
                signal_date=signal_date,
                direction="sell",
                planned_action="exit",
                review_status="watching",
                reviewed_at=datetime.utcnow(),
                reviewed_by="trader1"
            ),
        ]
        
        for signal in signals:
            self.db.create_signal(signal)
        
        # Get summary
        response = self.client.get("/api/signals/summary?signal_date=2023-12-29")
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertEqual(data["signal_date"], "2023-12-29")
        self.assertEqual(data["total_count"], 3)
        self.assertEqual(data["pending_count"], 2)
        self.assertEqual(data["by_status"]["pending"], 2)
        self.assertEqual(data["by_status"]["watching"], 1)
        self.assertEqual(data["by_direction"]["buy"], 2)
        self.assertEqual(data["by_direction"]["sell"], 1)
    
    def test_get_summary_empty_date(self):
        """Test summary for date with no signals."""
        response = self.client.get("/api/signals/summary?signal_date=2023-12-30")
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertEqual(data["total_count"], 0)
        self.assertEqual(data["pending_count"], 0)


if __name__ == "__main__":
    unittest.main()
