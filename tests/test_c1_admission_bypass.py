"""
C1 Task 4: Block Signal Board Admission Bypasses

Tests to ensure Signal Board API/DB cannot be bypassed to display
signals from non-prototype_passed strategies.

Coverage:
1. prototype_passed signal visible
2. candidate_for_prototype_passed signal hidden/rejected
3. draft/rejected/needs_review hidden/rejected
4. missing admission metadata hidden by default
5. old DB rows do not become accepted by default
6. API /api/signals defaults to not returning unadmitted signals
7. API /api/signals/strategies defaults to not counting unadmitted strategies
8. no LLM dependency
9. no broker/live trading dependency
"""
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.signal_board import init_signal_board_api, router
from backend.db.signal_board import SignalBoardDB
from contracts.signal_board import PlannedSignal


class TestC1AdmissionBypass(unittest.TestCase):
    """Test Signal Board admission bypass prevention."""

    def _make_signal(
        self,
        signal_id: str,
        lifecycle_state_at_generation: str | None = "prototype_passed",
        admission_source: str | None = "c_admission_gate",
        strategy_revision_id: str | None = "rev_001",
    ) -> PlannedSignal:
        """Create signal with configurable admission metadata."""
        return PlannedSignal(
            signal_id=signal_id,
            strategy_id="test_strategy",
            strategy_version="v1.0.0",
            strategy_revision_id=strategy_revision_id,
            lifecycle_state_at_generation=lifecycle_state_at_generation,
            admission_source=admission_source,
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

    def test_prototype_passed_signal_visible(self):
        """Signals from prototype_passed strategies are visible by default."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = SignalBoardDB(db_path)

            signal = self._make_signal(
                "sig_prototype",
                lifecycle_state_at_generation="prototype_passed",
            )
            db.create_signal(signal)

            # Default query returns prototype_passed signals
            result = db.list_signals()
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0].signal_id, "sig_prototype")

    def test_candidate_for_prototype_passed_signal_hidden(self):
        """Signals from candidate_for_prototype_passed are hidden by default."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = SignalBoardDB(db_path)

            signal = self._make_signal(
                "sig_candidate",
                lifecycle_state_at_generation="candidate_for_prototype_passed",
            )
            db.create_signal(signal)

            # Default query does not return candidate signals
            result = db.list_signals()
            self.assertEqual(len(result), 0)

            # Audit query with include_missing_admission=True returns it
            result_audit = db.list_signals(include_missing_admission=True)
            self.assertEqual(len(result_audit), 1)

    def test_draft_signal_hidden(self):
        """Signals from draft strategies are hidden by default."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = SignalBoardDB(db_path)

            signal = self._make_signal(
                "sig_draft",
                lifecycle_state_at_generation="draft",
            )
            db.create_signal(signal)

            # Default query does not return draft signals
            result = db.list_signals()
            self.assertEqual(len(result), 0)

    def test_rejected_signal_hidden(self):
        """Signals from rejected strategies are hidden by default."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = SignalBoardDB(db_path)

            signal = self._make_signal(
                "sig_rejected",
                lifecycle_state_at_generation="rejected",
            )
            db.create_signal(signal)

            # Default query does not return rejected signals
            result = db.list_signals()
            self.assertEqual(len(result), 0)

    def test_needs_review_signal_hidden(self):
        """Signals from needs_review strategies are hidden by default."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = SignalBoardDB(db_path)

            signal = self._make_signal(
                "sig_needs_review",
                lifecycle_state_at_generation="needs_review",
            )
            db.create_signal(signal)

            # Default query does not return needs_review signals
            result = db.list_signals()
            self.assertEqual(len(result), 0)

    def test_missing_admission_metadata_hidden_by_default(self):
        """Signals without admission metadata are hidden by default."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = SignalBoardDB(db_path)

            # Old signal (pre-C0) with None admission metadata
            signal = self._make_signal(
                "sig_old",
                lifecycle_state_at_generation=None,
                admission_source=None,
                strategy_revision_id=None,
            )
            db.create_signal(signal)

            # Default query does not return old signals
            result = db.list_signals()
            self.assertEqual(len(result), 0)

            # Audit query returns old signals
            result_audit = db.list_signals(include_missing_admission=True)
            self.assertEqual(len(result_audit), 1)

    def test_old_db_rows_do_not_become_accepted_by_default(self):
        """
        Old signals (generated before C0) do not default to accepted.

        Old signals have lifecycle_state_at_generation=None.
        Default query filters them out (not displayed as valid).
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = SignalBoardDB(db_path)

            # Create mix of old and new signals
            old_signal = self._make_signal(
                "sig_old",
                lifecycle_state_at_generation=None,
                admission_source=None,
            )
            new_signal = self._make_signal(
                "sig_new",
                lifecycle_state_at_generation="prototype_passed",
            )

            db.create_signal(old_signal)
            db.create_signal(new_signal)

            # Default query only returns new signal
            result = db.list_signals()
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0].signal_id, "sig_new")

    def test_api_signals_default_no_unadmitted_signals(self):
        """API /api/signals defaults to not returning unadmitted signals."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            init_signal_board_api(str(db_path))

            db = SignalBoardDB(db_path)

            # Create signals with different admission states
            db.create_signal(
                self._make_signal("sig_prototype", "prototype_passed")
            )
            db.create_signal(
                self._make_signal("sig_candidate", "candidate_for_prototype_passed")
            )
            db.create_signal(self._make_signal("sig_draft", "draft"))

            # Test API
            app = FastAPI()
            app.include_router(router)
            client = TestClient(app)

            response = client.get("/api/signals")
            self.assertEqual(response.status_code, 200)

            signals = response.json()["items"]
            self.assertEqual(len(signals), 1)
            self.assertEqual(signals[0]["signal_id"], "sig_prototype")

    def test_api_signals_with_include_missing_admission(self):
        """API /api/signals?include_missing_admission=true returns all signals."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            init_signal_board_api(str(db_path))

            db = SignalBoardDB(db_path)

            db.create_signal(
                self._make_signal("sig_prototype", "prototype_passed")
            )
            db.create_signal(
                self._make_signal("sig_draft", "draft")
            )

            # Test API with audit mode
            app = FastAPI()
            app.include_router(router)
            client = TestClient(app)

            response = client.get("/api/signals?include_missing_admission=true")
            self.assertEqual(response.status_code, 200)

            signals = response.json()["items"]
            self.assertEqual(len(signals), 2)

    def test_api_strategies_default_no_unadmitted_strategies(self):
        """API /api/signals/strategies defaults to not counting unadmitted strategies."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            init_signal_board_api(str(db_path))

            db = SignalBoardDB(db_path)

            # Create signals for different strategies
            prototype_signal = self._make_signal(
                "sig_prototype",
                lifecycle_state_at_generation="prototype_passed",
            )
            prototype_signal.strategy_id = "strat_prototype"
            db.create_signal(prototype_signal)

            draft_signal = self._make_signal(
                "sig_draft",
                lifecycle_state_at_generation="draft",
            )
            draft_signal.strategy_id = "strat_draft"
            db.create_signal(draft_signal)

            # Test API
            app = FastAPI()
            app.include_router(router)
            client = TestClient(app)

            response = client.get("/api/signals/strategies")
            self.assertEqual(response.status_code, 200)

            strategies = response.json()
            self.assertEqual(len(strategies), 1)
            self.assertEqual(strategies[0]["strategy_id"], "strat_prototype")

    def test_no_llm_dependency(self):
        """Signal Board admission filtering has no LLM dependency."""
        import backend.db.signal_board as signal_board_module
        import backend.api.signal_board as api_module
        import inspect

        # Check imports
        signal_board_source = inspect.getsource(signal_board_module)
        api_source = inspect.getsource(api_module)

        self.assertNotIn("openai", signal_board_source)
        self.assertNotIn("anthropic", signal_board_source)
        self.assertNotIn("langchain", signal_board_source)

        self.assertNotIn("openai", api_source)
        self.assertNotIn("anthropic", api_source)
        self.assertNotIn("langchain", api_source)

    def test_no_broker_live_trading_dependency(self):
        """Signal Board admission filtering has no broker/live trading dependency."""
        import backend.db.signal_board as signal_board_module
        import backend.api.signal_board as api_module
        import inspect

        signal_board_source = inspect.getsource(signal_board_module)
        api_source = inspect.getsource(api_module)

        forbidden_keywords = [
            "broker",
            "live_trading",
            "order_submission",
            "execution_venue",
            "real_time_feed",
        ]

        for keyword in forbidden_keywords:
            self.assertNotIn(keyword, signal_board_source)
            self.assertNotIn(keyword, api_source)


if __name__ == "__main__":
    unittest.main()
