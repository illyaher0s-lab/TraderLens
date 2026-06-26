"""
Tests for Multi-Strategy Selector (M4.1 Phase 3)

Verifies that:
1. list_signals() can filter by strategy_id
2. list_signals() can filter by strategy_version
3. Combined strategy_id + strategy_version filtering works
4. Combined status + strategy_id filtering works
5. list_strategies() returns unique strategy/version combinations
6. list_strategies() counts signals correctly
7. API endpoint /api/signals?strategy_id=... works
8. API endpoint /api/signals/strategies works
9. Non-existent strategy_id returns empty list (no crash)
10. Sorting is stable (signal_date DESC, strategy_id ASC, strategy_version ASC, symbol ASC)
"""

import unittest
import tempfile
from datetime import date, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from backend.api.signal_board import router, init_signal_board_api
from backend.db.signal_board import SignalBoardDB
from contracts.signal_board import PlannedSignal


class TestMultiStrategySelector(unittest.TestCase):
    """Test multi-strategy selector functionality."""
    
    def _make_signal(
        self,
        signal_id: str,
        strategy_id: str,
        strategy_version: str,
        symbol: str = "600519.SH",
        signal_date: date = date(2023, 12, 29),
        review_status: str = "pending"
    ) -> PlannedSignal:
        """Create a test signal."""
        return PlannedSignal(
            signal_id=signal_id,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            snapshot_hash="test_hash",
            signal_date=signal_date,
            intended_execution_date=date(2024, 1, 2),
            symbol=symbol,
            direction="buy",
            planned_action="enter",
            quantity=100,
            trigger_reason="Test trigger",
            review_status=review_status,
            created_at=datetime(2023, 12, 29, 16, 0, 0)
        )
    
    def test_filter_by_strategy_id(self):
        """Filter signals by strategy_id."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = SignalBoardDB(db_path)
            
            # Create signals with different strategy_id
            signal_a = self._make_signal(
                signal_id="signal_a",
                strategy_id="momentum_v2",
                strategy_version="v2.1.0"
            )
            signal_b = self._make_signal(
                signal_id="signal_b",
                strategy_id="mean_reversion",
                strategy_version="v1.0.0"
            )
            signal_c = self._make_signal(
                signal_id="signal_c",
                strategy_id="momentum_v2",
                strategy_version="v2.2.0"
            )
            
            db.create_signal(signal_a)
            db.create_signal(signal_b)
            db.create_signal(signal_c)
            
            # Filter by momentum_v2
            signals = db.list_signals(strategy_id="momentum_v2")
            
            self.assertEqual(len(signals), 2)
            signal_ids = {s.signal_id for s in signals}
            self.assertEqual(signal_ids, {"signal_a", "signal_c"})
    
    def test_filter_by_strategy_version(self):
        """Filter signals by strategy_version."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = SignalBoardDB(db_path)
            
            # Create signals with different strategy_version
            signal_a = self._make_signal(
                signal_id="signal_a",
                strategy_id="momentum_v2",
                strategy_version="v2.1.0"
            )
            signal_b = self._make_signal(
                signal_id="signal_b",
                strategy_id="momentum_v2",
                strategy_version="v2.2.0"
            )
            signal_c = self._make_signal(
                signal_id="signal_c",
                strategy_id="mean_reversion",
                strategy_version="v2.1.0"
            )
            
            db.create_signal(signal_a)
            db.create_signal(signal_b)
            db.create_signal(signal_c)
            
            # Filter by v2.1.0
            signals = db.list_signals(strategy_version="v2.1.0")
            
            self.assertEqual(len(signals), 2)
            signal_ids = {s.signal_id for s in signals}
            self.assertEqual(signal_ids, {"signal_a", "signal_c"})
    
    def test_filter_by_strategy_id_and_version(self):
        """Filter by strategy_id AND strategy_version together."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = SignalBoardDB(db_path)
            
            # Create signals
            signal_a = self._make_signal(
                signal_id="signal_a",
                strategy_id="momentum_v2",
                strategy_version="v2.1.0"
            )
            signal_b = self._make_signal(
                signal_id="signal_b",
                strategy_id="momentum_v2",
                strategy_version="v2.2.0"
            )
            signal_c = self._make_signal(
                signal_id="signal_c",
                strategy_id="mean_reversion",
                strategy_version="v2.1.0"
            )
            
            db.create_signal(signal_a)
            db.create_signal(signal_b)
            db.create_signal(signal_c)
            
            # Filter by momentum_v2 + v2.1.0
            signals = db.list_signals(
                strategy_id="momentum_v2",
                strategy_version="v2.1.0"
            )
            
            self.assertEqual(len(signals), 1)
            self.assertEqual(signals[0].signal_id, "signal_a")
    
    def test_filter_by_status_and_strategy_id(self):
        """Combined status + strategy_id filtering."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = SignalBoardDB(db_path)
            
            # Create signals with different status and strategy
            signal_a = self._make_signal(
                signal_id="signal_a",
                strategy_id="momentum_v2",
                strategy_version="v2.1.0",
                review_status="pending"
            )
            signal_b = self._make_signal(
                signal_id="signal_b",
                strategy_id="momentum_v2",
                strategy_version="v2.1.0",
                review_status="watching"
            )
            signal_c = self._make_signal(
                signal_id="signal_c",
                strategy_id="mean_reversion",
                strategy_version="v1.0.0",
                review_status="pending"
            )
            
            db.create_signal(signal_a)
            db.create_signal(signal_b)
            db.create_signal(signal_c)
            
            # Filter by pending + momentum_v2
            signals = db.list_signals(
                review_status="pending",
                strategy_id="momentum_v2"
            )
            
            self.assertEqual(len(signals), 1)
            self.assertEqual(signals[0].signal_id, "signal_a")
    
    def test_list_strategies_returns_unique_combinations(self):
        """list_strategies() returns unique strategy/version combinations."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = SignalBoardDB(db_path)
            
            # Create multiple signals with same strategy/version
            for i in range(3):
                signal = self._make_signal(
                    signal_id=f"signal_{i}",
                    strategy_id="momentum_v2",
                    strategy_version="v2.1.0",
                    symbol=f"60051{i}.SH"
                )
                db.create_signal(signal)
            
            # Create signals with different strategy
            signal_b = self._make_signal(
                signal_id="signal_b",
                strategy_id="mean_reversion",
                strategy_version="v1.0.0"
            )
            db.create_signal(signal_b)
            
            # List strategies
            strategies = db.list_strategies()
            
            self.assertEqual(len(strategies), 2)
            
            # Check structure
            strategy_ids = {s["strategy_id"] for s in strategies}
            self.assertEqual(strategy_ids, {"momentum_v2", "mean_reversion"})
    
    def test_list_strategies_counts_signals_correctly(self):
        """list_strategies() counts signal_count correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = SignalBoardDB(db_path)
            
            # Create 3 signals for momentum_v2 v2.1.0
            for i in range(3):
                signal = self._make_signal(
                    signal_id=f"momentum_signal_{i}",
                    strategy_id="momentum_v2",
                    strategy_version="v2.1.0",
                    symbol=f"60051{i}.SH"
                )
                db.create_signal(signal)
            
            # Create 2 signals for mean_reversion v1.0.0
            for i in range(2):
                signal = self._make_signal(
                    signal_id=f"mr_signal_{i}",
                    strategy_id="mean_reversion",
                    strategy_version="v1.0.0",
                    symbol=f"00000{i}.SZ"
                )
                db.create_signal(signal)
            
            # List strategies
            strategies = db.list_strategies()
            
            # Check counts
            by_id = {s["strategy_id"]: s for s in strategies}
            
            self.assertEqual(by_id["momentum_v2"]["signal_count"], 3)
            self.assertEqual(by_id["mean_reversion"]["signal_count"], 2)
    
    def test_list_strategies_includes_latest_signal_date(self):
        """list_strategies() includes latest_signal_date."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = SignalBoardDB(db_path)
            
            # Create signals with different dates
            signal_old = self._make_signal(
                signal_id="signal_old",
                strategy_id="momentum_v2",
                strategy_version="v2.1.0",
                signal_date=date(2023, 12, 25)
            )
            signal_new = self._make_signal(
                signal_id="signal_new",
                strategy_id="momentum_v2",
                strategy_version="v2.1.0",
                signal_date=date(2023, 12, 29)
            )
            
            db.create_signal(signal_old)
            db.create_signal(signal_new)
            
            # List strategies
            strategies = db.list_strategies()
            
            self.assertEqual(len(strategies), 1)
            self.assertEqual(strategies[0]["latest_signal_date"], "2023-12-29")
    
    def test_nonexistent_strategy_id_returns_empty_list(self):
        """Non-existent strategy_id returns empty list (no crash)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = SignalBoardDB(db_path)
            
            # Create signal
            signal = self._make_signal(
                signal_id="signal_a",
                strategy_id="momentum_v2",
                strategy_version="v2.1.0"
            )
            db.create_signal(signal)
            
            # Query non-existent strategy
            signals = db.list_signals(strategy_id="nonexistent_strategy")
            
            self.assertEqual(signals, [])
    
    def test_sorting_is_stable(self):
        """Sorting is stable: signal_date DESC, strategy_id ASC, strategy_version ASC, symbol ASC."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = SignalBoardDB(db_path)
            
            # Create signals with different dates/strategies/symbols
            signals_to_create = [
                ("s1", "mean_reversion", "v1.0.0", "600519.SH", date(2023, 12, 28)),
                ("s2", "momentum_v2", "v2.1.0", "600036.SH", date(2023, 12, 29)),
                ("s3", "momentum_v2", "v2.2.0", "600519.SH", date(2023, 12, 29)),
                ("s4", "momentum_v2", "v2.1.0", "000001.SZ", date(2023, 12, 29)),
            ]
            
            for signal_id, strategy_id, strategy_version, symbol, signal_date in signals_to_create:
                signal = self._make_signal(
                    signal_id=signal_id,
                    strategy_id=strategy_id,
                    strategy_version=strategy_version,
                    symbol=symbol,
                    signal_date=signal_date
                )
                db.create_signal(signal)
            
            # Query all signals
            signals = db.list_signals(limit=10)
            
            # Expected order:
            # 1. 2023-12-29, momentum_v2, v2.1.0, 000001.SZ (s4)
            # 2. 2023-12-29, momentum_v2, v2.1.0, 600036.SH (s2)
            # 3. 2023-12-29, momentum_v2, v2.2.0, 600519.SH (s3)
            # 4. 2023-12-28, mean_reversion, v1.0.0, 600519.SH (s1)
            
            actual_order = [s.signal_id for s in signals]
            expected_order = ["s4", "s2", "s3", "s1"]
            
            self.assertEqual(actual_order, expected_order)
    
    def test_api_filter_by_strategy_id(self):
        """API endpoint /api/signals?strategy_id=... works."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            init_signal_board_api(str(db_path))
            
            db = SignalBoardDB(db_path)
            
            # Create signals
            signal_a = self._make_signal(
                signal_id="signal_a",
                strategy_id="momentum_v2",
                strategy_version="v2.1.0"
            )
            signal_b = self._make_signal(
                signal_id="signal_b",
                strategy_id="mean_reversion",
                strategy_version="v1.0.0"
            )
            
            db.create_signal(signal_a)
            db.create_signal(signal_b)
            
            # Test API
            from fastapi import FastAPI
            app = FastAPI()
            app.include_router(router)
            client = TestClient(app)
            
            response = client.get("/api/signals?strategy_id=momentum_v2")
            
            self.assertEqual(response.status_code, 200)
            signals = response.json()["items"]
            self.assertEqual(len(signals), 1)
            self.assertEqual(signals[0]["strategy_id"], "momentum_v2")
    
    def test_api_list_strategies(self):
        """API endpoint /api/signals/strategies works."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            init_signal_board_api(str(db_path))
            
            db = SignalBoardDB(db_path)
            
            # Create signals
            signal_a = self._make_signal(
                signal_id="signal_a",
                strategy_id="momentum_v2",
                strategy_version="v2.1.0"
            )
            signal_b = self._make_signal(
                signal_id="signal_b",
                strategy_id="mean_reversion",
                strategy_version="v1.0.0"
            )
            
            db.create_signal(signal_a)
            db.create_signal(signal_b)
            
            # Test API
            from fastapi import FastAPI
            app = FastAPI()
            app.include_router(router)
            client = TestClient(app)
            
            response = client.get("/api/signals/strategies")
            
            self.assertEqual(response.status_code, 200)
            strategies = response.json()
            self.assertEqual(len(strategies), 2)
            
            strategy_ids = {s["strategy_id"] for s in strategies}
            self.assertEqual(strategy_ids, {"momentum_v2", "mean_reversion"})


if __name__ == "__main__":
    unittest.main()
