"""
Tests for Signal Board pagination, date filters, and stable ordering.

These tests exercise the database layer directly so pagination behavior is
API-free and deterministic.
"""

import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

from backend.db.signal_board import SignalBoardDB
from contracts.signal_board import PlannedSignal


class TestSignalPagination(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = SignalBoardDB(Path(self.temp_dir.name) / "signals.db")

    def tearDown(self):
        self.temp_dir.cleanup()

    def _signal(self, signal_id: str, **overrides) -> PlannedSignal:
        defaults = {
            "signal_id": signal_id,
            "strategy_id": "momentum",
            "strategy_version": "v1",
            "snapshot_hash": "snapshot",
            "signal_date": date(2024, 1, 3),
            "intended_execution_date": date(2024, 1, 4),
            "symbol": "000001.SZ",
            "direction": "buy",
            "planned_action": "enter",
            "quantity": 100,
            "trigger_reason": f"test signal {signal_id}",
            "review_status": "pending",
            "current_price": 10.0,
            "position_before": 0,
            "created_at": datetime(2024, 1, 3, 16, 0),
            "metadata": {},
        }
        defaults.update(overrides)
        return PlannedSignal(**defaults)

    def _seed(self, signals: list[PlannedSignal]) -> None:
        for signal in signals:
            self.db.create_signal(signal)

    def test_limit_is_applied(self):
        self._seed([self._signal(f"id-{i}", symbol=f"00000{i}.SZ") for i in range(5)])

        result = self.db.list_signals(limit=2)

        self.assertEqual(len(result["items"]), 2)
        self.assertEqual(result["limit"], 2)
        self.assertEqual(result["total"], 5)

    def test_offset_is_applied(self):
        self._seed([self._signal(f"id-{i}", symbol=f"00000{i}.SZ") for i in range(5)])

        first = self.db.list_signals(limit=1, offset=0)
        second = self.db.list_signals(limit=1, offset=1)

        self.assertNotEqual(first["items"][0].signal_id, second["items"][0].signal_id)
        self.assertEqual(second["offset"], 1)

    def test_limit_and_offset_combination_returns_expected_page(self):
        self._seed([self._signal(f"id-{i}", symbol=f"00000{i}.SZ") for i in range(5)])

        result = self.db.list_signals(limit=2, offset=2)

        self.assertEqual([s.symbol for s in result["items"]], ["000002.SZ", "000003.SZ"])

    def test_limit_above_maximum_is_rejected(self):
        with self.assertRaises(ValueError):
            self.db.list_signals(limit=501)

    def test_negative_offset_is_rejected(self):
        with self.assertRaises(ValueError):
            self.db.list_signals(offset=-1)

    def test_signal_date_filter_is_applied(self):
        self._seed([
            self._signal("old", signal_date=date(2024, 1, 2)),
            self._signal("new", signal_date=date(2024, 1, 3)),
        ])

        result = self.db.list_signals(signal_date=date(2024, 1, 2))

        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0].signal_id, "old")

    def test_intended_execution_date_filter_is_applied(self):
        self._seed([
            self._signal("jan4", intended_execution_date=date(2024, 1, 4)),
            self._signal("jan5", intended_execution_date=date(2024, 1, 5)),
        ])

        result = self.db.list_signals(intended_execution_date=date(2024, 1, 5))

        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0].signal_id, "jan5")

    def test_status_strategy_and_pagination_combine_correctly(self):
        self._seed([
            self._signal("a1", strategy_id="alpha", review_status="pending", symbol="000001.SZ"),
            self._signal("a2", strategy_id="alpha", review_status="pending", symbol="000002.SZ"),
            self._signal("a3", strategy_id="alpha", review_status="pending", symbol="000003.SZ"),
            self._signal("ignored", strategy_id="alpha", review_status="ignored", symbol="000004.SZ"),
            self._signal("beta", strategy_id="beta", review_status="pending", symbol="000005.SZ"),
        ])

        result = self.db.list_signals(
            review_status="pending",
            strategy_id="alpha",
            limit=2,
            offset=1,
        )

        self.assertEqual(result["total"], 3)
        self.assertEqual([s.signal_id for s in result["items"]], ["a2", "a3"])

    def test_total_counts_all_filtered_rows_not_page_size(self):
        self._seed([self._signal(f"id-{i}", symbol=f"00000{i}.SZ") for i in range(4)])

        result = self.db.list_signals(limit=2)

        self.assertEqual(result["total"], 4)
        self.assertEqual(len(result["items"]), 2)

    def test_has_more_reflects_remaining_rows(self):
        self._seed([self._signal(f"id-{i}", symbol=f"00000{i}.SZ") for i in range(3)])

        first = self.db.list_signals(limit=2, offset=0)
        last = self.db.list_signals(limit=2, offset=2)

        self.assertTrue(first["has_more"])
        self.assertFalse(last["has_more"])

    def test_stable_sort_allows_continuous_pages_without_duplicates(self):
        self._seed([
            self._signal("b", signal_date=date(2024, 1, 3), intended_execution_date=date(2024, 1, 4), strategy_id="b", strategy_version="v1", symbol="000001.SZ"),
            self._signal("a2", signal_date=date(2024, 1, 3), intended_execution_date=date(2024, 1, 4), strategy_id="a", strategy_version="v2", symbol="000001.SZ"),
            self._signal("a1-2", signal_date=date(2024, 1, 3), intended_execution_date=date(2024, 1, 4), strategy_id="a", strategy_version="v1", symbol="000001.SZ"),
            self._signal("a1-1", signal_date=date(2024, 1, 3), intended_execution_date=date(2024, 1, 4), strategy_id="a", strategy_version="v1", symbol="000001.SZ"),
            self._signal("older", signal_date=date(2024, 1, 2), intended_execution_date=date(2024, 1, 5), strategy_id="a", strategy_version="v1", symbol="000001.SZ"),
            self._signal("newer-exec", signal_date=date(2024, 1, 3), intended_execution_date=date(2024, 1, 5), strategy_id="a", strategy_version="v1", symbol="000001.SZ"),
        ])

        page1 = self.db.list_signals(limit=3, offset=0)
        page2 = self.db.list_signals(limit=3, offset=3)
        ids = [s.signal_id for s in page1["items"] + page2["items"]]

        self.assertEqual(ids, ["newer-exec", "a1-1", "a1-2", "a2", "b", "older"])
        self.assertEqual(len(ids), len(set(ids)))

    def test_empty_result_returns_empty_items_and_zero_total(self):
        self._seed([self._signal("existing")])

        result = self.db.list_signals(signal_date=date(1999, 1, 1))

        self.assertEqual(result["items"], [])
        self.assertEqual(result["total"], 0)
        self.assertFalse(result["has_more"])


if __name__ == "__main__":
    unittest.main()
