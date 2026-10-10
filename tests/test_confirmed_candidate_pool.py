"""
Test Phase 4: Confirmed Candidate Pool
"""

import unittest
from datetime import date, datetime, timedelta
from fastapi.testclient import TestClient
from backend.db.research import ResearchDB
from backend.api.research import create_research_app
from contracts.research import TickerVerificationRecord
from tests.approval_context_fixtures import attach_continued_approval


class TestConfirmedCandidatePool(unittest.TestCase):
    """Test confirmed candidate pool functionality."""

    def setUp(self):
        """Set up test client with in-memory database."""
        self.db = ResearchDB(":memory:")
        self.app = create_research_app(self.db)
        self.client = TestClient(self.app)
        self.approval_cards = {}

    def approval_for(self, theme_id: str) -> str:
        if theme_id not in self.approval_cards:
            self.approval_cards[theme_id] = attach_continued_approval(self.db, theme_id)
        return self.approval_cards[theme_id]

    def store_verification(self, symbol: str, company_name: str = "Verified Company") -> str:
        """Store a valid ticker identity snapshot for confirmation flow tests."""
        now = datetime.now()
        verification_id = f"verify_{symbol.replace('.', '_')}"
        self.db.store_ticker_verification(
            TickerVerificationRecord(
                verification_id=verification_id,
                symbol=symbol,
                company_name=company_name,
                exchange="SSE" if symbol.endswith(".SH") else "SZSE",
                status="listed",
                confidence="high",
                source="test_fixture",
                notes="Verified for confirmation test",
                verified_at=now,
                expires_at=now + timedelta(hours=24),
            )
        )
        return verification_id

    def test_confirm_locks_snapshots(self):
        """Confirm locks thesis, invalidation_rules, price_snapshot, and benchmark_snapshot."""
        # Create theme
        create_response = self.client.post(
            "/api/research/themes",
            json={
                "theme_name": "测试主题",
                "background": "测试",
                "source_type": "manual_theme",
            },
        )
        theme_id = create_response.json()["theme_id"]
        verification_id = self.store_verification("300750.SZ", "宁德时代")

        # Add candidate
        add_response = self.client.post(
            f"/api/research/themes/{theme_id}/candidates",
            json={
                "symbol": "300750.SZ",
                "verification_id": verification_id,
                "match_reason": "手动添加",
                "source_type": "manual_stock",
            },
        )
        candidate_id = add_response.json()["candidate_id"]

        # Store an evidence snapshot (required for confirmation)
        snap_id = "snap_test_locks"
        self.db.store_evidence_snapshot(
            snapshot_id=snap_id,
            candidate_id=candidate_id,
            verification_id=verification_id,
            snapshot_date="20260624",
            symbol="300750.SZ",
            evidence_output={"evidence_level": "strong", "blocking_issues": []},
        )

        # Confirm candidate with snapshots
        confirm_response = self.client.post(
            f"/api/research/candidates/{candidate_id}/confirm",
            json={
                "approval_card_id": self.approval_for(theme_id),
                "confirmation_reason": "基本面稳健",
                "evidence_level": "strong",
                "confirmed_by": "user_001",
                "pool_snapshot_date": date.today().isoformat(),
                "thesis_snapshot": "锂电池龙头企业",
                "invalidation_rules": [
                    {"type": "price_drop", "threshold": -0.2},
                    {"type": "earnings_miss", "threshold": -0.1},
                ],
                "price_snapshot": {"close": 500.0, "volume": 10000000},
                "benchmark_snapshot": {"index": "399006.SZ", "close": 3000.0},
                "evidence_snapshot_ids": [snap_id],
            },
        )
        self.assertEqual(confirm_response.status_code, 200)

        # Retrieve confirmed candidates
        list_response = self.client.get(f"/api/research/themes/{theme_id}/confirmed-candidates")
        self.assertEqual(list_response.status_code, 200)
        confirmed_list = list_response.json()
        self.assertEqual(len(confirmed_list), 1)

        confirmed = confirmed_list[0]
        self.assertEqual(confirmed["thesis_snapshot"], "锂电池龙头企业")
        self.assertEqual(len(confirmed["invalidation_rules"]), 2)
        self.assertEqual(confirmed["price_snapshot"]["close"], 500.0)
        self.assertEqual(confirmed["benchmark_snapshot"]["index"], "399006.SZ")

    def test_forward_only_and_pool_snapshot_date(self):
        """Confirmed candidates have forward_only=True and pool_snapshot_date."""
        # Create theme
        create_response = self.client.post(
            "/api/research/themes",
            json={
                "theme_name": "测试主题",
                "background": "测试",
                "source_type": "manual_theme",
            },
        )
        theme_id = create_response.json()["theme_id"]
        verification_id = self.store_verification("002594.SZ")

        # Add candidate
        add_response = self.client.post(
            f"/api/research/themes/{theme_id}/candidates",
            json={
                "symbol": "002594.SZ",
                "verification_id": verification_id,
                "match_reason": "手动添加",
                "source_type": "manual_stock",
            },
        )
        candidate_id = add_response.json()["candidate_id"]

        # Store an evidence snapshot
        snap_id = "snap_test_fwd"
        self.db.store_evidence_snapshot(
            snapshot_id=snap_id,
            candidate_id=candidate_id,
            verification_id=verification_id,
            snapshot_date="20260624",
            symbol="002594.SZ",
            evidence_output={"evidence_level": "medium", "blocking_issues": []},
        )

        # Confirm candidate
        snapshot_date = date.today().isoformat()
        confirm_response = self.client.post(
            f"/api/research/candidates/{candidate_id}/confirm",
            json={
                "approval_card_id": self.approval_for(theme_id),
                "confirmation_reason": "测试确认",
                "evidence_level": "medium",
                "confirmed_by": "user_001",
                "pool_snapshot_date": snapshot_date,
                "thesis_snapshot": "测试",
                "invalidation_rules": [],
                "price_snapshot": {},
                "benchmark_snapshot": {},
                "evidence_snapshot_ids": [snap_id],
            },
        )
        self.assertEqual(confirm_response.status_code, 200)

        # Retrieve confirmed candidates
        list_response = self.client.get(f"/api/research/themes/{theme_id}/confirmed-candidates")
        confirmed_list = list_response.json()
        
        confirmed = confirmed_list[0]
        self.assertTrue(confirmed["forward_only"])
        self.assertEqual(confirmed["pool_snapshot_date"], snapshot_date)

    def test_confirmed_pool_queryable(self):
        """Confirmed candidate pool is queryable by theme."""
        # Create theme
        create_response = self.client.post(
            "/api/research/themes",
            json={
                "theme_name": "测试主题",
                "background": "测试",
                "source_type": "manual_theme",
            },
        )
        theme_id = create_response.json()["theme_id"]

        # Add multiple candidates
        candidates = []
        for i, symbol in enumerate(["600000.SH", "000001.SZ", "688005.SH"]):
            verification_id = self.store_verification(symbol)
            add_response = self.client.post(
                f"/api/research/themes/{theme_id}/candidates",
                json={
                    "symbol": symbol,
                    "verification_id": verification_id,
                    "match_reason": "手动添加",
                    "source_type": "manual_stock",
                },
            )
            candidates.append(add_response.json()["candidate_id"])

        # Confirm first two (each needs a snapshot)
        for i, candidate_id in enumerate(candidates[:2]):
            symbol = ["600000.SH", "000001.SZ"][i]
            snap_id = f"snap_test_pool_{i}"
            self.db.store_evidence_snapshot(
                snapshot_id=snap_id,
                candidate_id=candidate_id,
                verification_id=None,
                snapshot_date="20260624",
                symbol=symbol,
                evidence_output={"evidence_level": "medium", "blocking_issues": []},
            )
            self.client.post(
                f"/api/research/candidates/{candidate_id}/confirm",
                json={
                    "approval_card_id": self.approval_for(theme_id),
                    "confirmation_reason": "测试",
                    "evidence_level": "medium",
                    "confirmed_by": "user_001",
                    "pool_snapshot_date": date.today().isoformat(),
                    "thesis_snapshot": "测试",
                    "invalidation_rules": [],
                    "price_snapshot": {},
                    "benchmark_snapshot": {},
                    "evidence_snapshot_ids": [snap_id],
                },
            )

        # Query confirmed pool
        list_response = self.client.get(f"/api/research/themes/{theme_id}/confirmed-candidates")
        confirmed_list = list_response.json()
        
        self.assertEqual(len(confirmed_list), 2)
        confirmed_symbols = {c["symbol"] for c in confirmed_list}
        self.assertEqual(confirmed_symbols, {"600000.SH", "000001.SZ"})


if __name__ == "__main__":
    unittest.main()
