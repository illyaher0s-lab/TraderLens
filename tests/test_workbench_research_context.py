"""
V2 credible manual-trading closure — ResearchCase-keyed decision trust boundary.

Deterministic (no real LLM/Tushare). Proves Req 3/4/5:
- a confirmed pool is created ONLY on an explicit user 'continue'
- 'observe' / 'stop' record the decision but create NO pool
- a missing / unknown decision is rejected (400), never silently approved
- candidate creation runs through the deterministic ResearchActionReducer
- the user hypothesis is persisted verbatim as pending-only (never a verified chain)
"""

import unittest
from datetime import date, datetime

from fastapi.testclient import TestClient

from backend.db.research import ResearchDB
from backend.api.research import create_research_app
from tests.fake_serenity_runner import FakeSerenityRunner
from tests.approval_context_fixtures import attach_continued_approval


def fake_market_provider(symbol, as_of):
    """Non-empty daily-basic data so the price snapshot is 'ok'."""
    return {
        "close": 100.0,
        "open": 99.0,
        "high": 101.0,
        "low": 98.0,
        "vol": 1_000_000,
    }


class TestResearchClosureDecisionBoundary(unittest.TestCase):
    def setUp(self):
        self.db = ResearchDB(":memory:")
        self.app = create_research_app(
            self.db,
            conversation_mode="real",
            serenity_execution_mode="two_phase",
            serenity_runner=FakeSerenityRunner(),
            market_data_provider=fake_market_provider,
            allow_test_serenity_runner=True,
        )
        self.client = TestClient(self.app)
        # Create a ResearchCase the way the workbench handler does.
        resp = self.client.post(
            "/api/research/themes",
            json={
                "theme_name": "朋友推荐测试",
                "background": "朋友推荐 600519",
                "source_type": "manual_stock",
            },
        )
        self.theme_id = resp.json()["theme_id"]
        self.approval_card_id = attach_continued_approval(self.db, self.theme_id)
        self.ticker = "600519.SH"
        self.company = "贵州茅台"

    def _research(self):
        return self.client.post(
            f"/api/research/themes/{self.theme_id}/run-research",
            json={"ticker": self.ticker, "company_name": self.company},
        )

    def _decide(self, decision, confirmed_by="user"):
        return self.client.post(
            f"/api/research/themes/{self.theme_id}/decision",
            json={
                "decision": decision,
                "confirmed_by": confirmed_by,
                "decision_loop_id": "loop_test_1",
                "ticker": self.ticker,
                "company_name": self.company,
                "exchange": "SSE",
                "snapshot_date": date.today().isoformat(),
                "approval_card_id": self.approval_card_id,
            },
        )

    def _confirmed_row(self):
        cur = self.db.conn.cursor()
        cur.execute(
            "SELECT * FROM confirmed_candidates WHERE theme_id = ?",
            (self.theme_id,),
        )
        return cur.fetchone()

    def test_hypothesis_persisted_verbatim(self):
        hyp = {
            "upstream_entity": "X",
            "downstream_entity": "Y",
            "relation_type": "supplier",
            "asserted_by": "user",
            "asserted_at": datetime.now().isoformat(),
            "scope_note": "pending",
        }
        r = self.client.post(
            f"/api/research/themes/{self.theme_id}/hypothesis",
            json={"user_industry_chain_hypothesis": hyp},
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "pending_hypothesis_saved")
        theme = self.db.get_theme(self.theme_id)
        # Verbatim, never rewritten as a verified chain edge.
        self.assertEqual(theme.user_industry_chain_hypothesis, hyp)

    def test_missing_decision_rejected(self):
        self._research()
        # Empty / unknown decision -> 400, never silently approved.
        r = self.client.post(
            f"/api/research/themes/{self.theme_id}/decision",
            json={
                "decision": "",
                "ticker": self.ticker,
                "company_name": self.company,
                "exchange": "SSE",
                "snapshot_date": date.today().isoformat(),
            },
        )
        self.assertEqual(r.status_code, 400)
        theme = self.db.get_theme(self.theme_id)
        self.assertIsNone(theme.approval_decision)
        self.assertIsNone(self._confirmed_row())

    def test_observe_does_not_create_pool(self):
        self._research()
        r = self._decide("observe")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["pool_created"])
        theme = self.db.get_theme(self.theme_id)
        self.assertEqual(theme.approval_decision, "observe")
        # Decision recorded but NO confirmed candidate row.
        self.assertIsNone(self._confirmed_row())
        # The research candidate still exists (created at research time) ...
        self.assertEqual(len(self.db.list_candidates(self.theme_id)), 1)
        # ... but it is NOT confirmed into the pool.
        self.assertIsNone(self._confirmed_row())

    def test_stop_does_not_create_pool(self):
        self._research()
        r = self._decide("stop")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["pool_created"])
        self.assertIsNone(self._confirmed_row())

    def test_continue_creates_pool_via_reducer(self):
        self._research()
        r = self._decide("continue")
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        # Forward-only; NOT a buy signal, NOT a historical backtest universe.
        self.assertTrue(body["forward_only"])
        self.assertFalse(body["is_buy_signal"])
        self.assertFalse(body["is_backtest_universe"])
        self.assertEqual(body["approval_decision"], "continue")
        self.assertEqual(body["confirmed_by"], "user")
        self.assertIsNotNone(body.get("confirmed_id"))
        # Deterministic reducer produced the confirmed candidate.
        row = self._confirmed_row()
        self.assertIsNotNone(row)
        self.assertEqual(row["confirmed_by"], "user")
        # Theme decision + approver persisted for audit.
        theme = self.db.get_theme(self.theme_id)
        self.assertEqual(theme.approval_decision, "continue")
        self.assertEqual(theme.confirmed_by, "user")
        self.assertEqual(theme.decision_loop_id, "loop_test_1")


if __name__ == "__main__":
    unittest.main()
