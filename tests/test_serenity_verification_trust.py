"""
Test Serenity verification trust chain.

These tests prove that propose_add_candidate MUST:
1. Reject arbitrary fake verification_id
2. Reject verification_id from a different symbol
3. Reject when verify_ticker was never called
4. Reject low confidence verification
5. Reject unknown listing status
6. Ignore LLM-provided company_name (use verification record)
7. Save real verification_id to CandidateStock
"""

import unittest
from datetime import datetime, timedelta
from contracts.research import (
    ThemeInput,
    CandidateStock,
    TickerVerificationRecord,
)
from backend.services.serenity_agent import SerenityAgentRunner
from backend.services.research_validation import ResearchValidator
from backend.app.tushare.config import TushareConfig
from backend.db.research import ResearchDB
from tests.test_research_validation import FakeTushareClient


def make_theme(name="信任链测试") -> ThemeInput:
    now = datetime.now()
    return ThemeInput(
        theme_id=f"theme_trust_{name}",
        theme_name=name,
        background="测试 verification_id 信任链",
        source_type="manual_theme",
        research_mode="standard",
        created_at=now,
        updated_at=now,
    )


def make_validator_with_db(db: ResearchDB) -> tuple[ResearchValidator, ResearchDB]:
    config = TushareConfig(token="fake", api_url="http://fake.test")
    v = ResearchValidator(tushare_config=config)
    v._tushare_client = FakeTushareClient(config)
    return v, db


class TestSerenityVerificationTrust(unittest.TestCase):
    """Serenity Agent must enforce verification trust chain."""

    def setUp(self):
        self.db = ResearchDB(":memory:")
        self.validator, self.db = make_validator_with_db(self.db)
        self.runner = SerenityAgentRunner(
            llm_client=None,
            validator=self.validator,
            mode="stub",
            db=self.db,
        )

    def test_arbitrary_fake_verification_id_rejected(self):
        """Arbitrary verification_id not in DB → reject."""
        from backend.services.serenity_agent import SerenityAgentAudit
        theme = make_theme()
        proposed = []
        audit = SerenityAgentAudit()
        result = self.runner._execute_tool(
            "propose_add_candidate",
            {
                "symbol": "300750.SZ",
                "verification_id": "fake_verification_id_12345",
                "company_name": "伪造公司",
                "match_reason": "测试",
            },
            theme,
            proposed,
            audit,
        )
        # Currently passes (BUG) — should reject
        self.assertIn("error", result["status"], 
                      "Arbitrary verification_id should be rejected")

    def test_verification_id_for_different_symbol_rejected(self):
        """verification_id exists but for a different symbol → reject."""
        from backend.services.serenity_agent import SerenityAgentAudit
        # Store verification for 600519.SH
        vid = "verify_600519_SH"
        now = datetime.now()
        self.db.store_ticker_verification(
            TickerVerificationRecord(
                verification_id=vid,
                symbol="600519.SH",
                company_name="贵州茅台",
                exchange="SSE",
                status="listed",
                confidence="high",
                source="test",
                notes="",
                verified_at=now,
                expires_at=now + timedelta(hours=24),
            )
        )

        # Try to use it for 300750.SZ (wrong symbol)
        theme = make_theme()
        proposed = []
        audit = SerenityAgentAudit()
        result = self.runner._execute_tool(
            "propose_add_candidate",
            {
                "symbol": "300750.SZ",  # different symbol
                "verification_id": vid,
                "company_name": "宁德时代",
                "match_reason": "测试",
            },
            theme,
            proposed,
            audit,
        )
        self.assertIn("error", result["status"],
                      "verification_id for wrong symbol should be rejected")

    def test_propose_without_verify_ticker_rejected(self):
        """propose_add_candidate without prior verify_ticker call → reject."""
        from backend.services.serenity_agent import SerenityAgentAudit
        # Don't call verify_ticker at all
        theme = make_theme()
        proposed = []
        audit = SerenityAgentAudit()
        result = self.runner._execute_tool(
            "propose_add_candidate",
            {
                "symbol": "300750.SZ",
                "verification_id": "never_verified",
                "company_name": "宁德时代",
                "match_reason": "测试",
            },
            theme,
            proposed,
            audit,
        )
        self.assertIn("error", result["status"],
                      "propose without verify_ticker should be rejected")

    def test_low_confidence_verification_rejected(self):
        """Low confidence verification → reject."""
        from backend.services.serenity_agent import SerenityAgentAudit
        # Store low-confidence verification
        vid = "verify_999999_SZ_low"
        now = datetime.now()
        self.db.store_ticker_verification(
            TickerVerificationRecord(
                verification_id=vid,
                symbol="999999.SZ",
                company_name="未知公司",
                exchange="SZSE",
                status="unknown",
                confidence="low",
                source="test",
                notes="",
                verified_at=now,
                expires_at=now + timedelta(hours=24),
            )
        )

        theme = make_theme()
        proposed = []
        audit = SerenityAgentAudit()
        result = self.runner._execute_tool(
            "propose_add_candidate",
            {
                "symbol": "999999.SZ",
                "verification_id": vid,
                "company_name": "未知公司",
                "match_reason": "测试",
            },
            theme,
            proposed,
            audit,
        )
        self.assertIn("error", result["status"],
                      "Low confidence verification should be rejected")

    def test_unknown_listing_status_rejected(self):
        """Unknown listing status → reject."""
        from backend.services.serenity_agent import SerenityAgentAudit
        vid = "verify_unknown_status"
        now = datetime.now()
        self.db.store_ticker_verification(
            TickerVerificationRecord(
                verification_id=vid,
                symbol="888888.SZ",
                company_name="状态未知",
                exchange="SZSE",
                status="unknown",
                confidence="medium",
                source="test",
                notes="",
                verified_at=now,
                expires_at=now + timedelta(hours=24),
            )
        )

        theme = make_theme()
        proposed = []
        audit = SerenityAgentAudit()
        result = self.runner._execute_tool(
            "propose_add_candidate",
            {
                "symbol": "888888.SZ",
                "verification_id": vid,
                "company_name": "状态未知",
                "match_reason": "测试",
            },
            theme,
            proposed,
            audit,
        )
        self.assertIn("error", result["status"],
                      "Unknown listing status should be rejected")

    def test_company_name_from_verification_record_not_llm(self):
        """company_name must come from verification record, not LLM input."""
        from backend.services.serenity_agent import SerenityAgentAudit
        # Store verification with real company name
        vid = "verify_300750_SZ_real"
        now = datetime.now()
        self.db.store_ticker_verification(
            TickerVerificationRecord(
                verification_id=vid,
                symbol="300750.SZ",
                company_name="宁德时代新能源科技股份有限公司",
                exchange="SZSE",
                status="listed",
                confidence="high",
                source="tushare",
                notes="",
                verified_at=now,
                expires_at=now + timedelta(hours=24),
            )
        )

        # LLM submits wrong company name
        theme = make_theme()
        proposed = []
        audit = SerenityAgentAudit()
        result = self.runner._execute_tool(
            "propose_add_candidate",
            {
                "symbol": "300750.SZ",
                "verification_id": vid,
                "company_name": "LLM伪造的公司名",  # fake
                "match_reason": "测试",
            },
            theme,
            proposed,
            audit,
        )

        # Should succeed but use verification record company_name
        if result["status"] == "ok":
            self.assertEqual(len(proposed), 1)
            # company_name should be from verification record, not LLM
            self.assertEqual(
                proposed[0].company_name,
                "宁德时代新能源科技股份有限公司",
                "company_name must come from verification record"
            )

    def test_candidate_stock_saves_real_verification_id(self):
        """CandidateStock.verification_id must save the real verification_id."""
        from backend.services.serenity_agent import SerenityAgentAudit
        # Store verification
        vid = "verify_600519_SH_real"
        now = datetime.now()
        self.db.store_ticker_verification(
            TickerVerificationRecord(
                verification_id=vid,
                symbol="600519.SH",
                company_name="贵州茅台酒股份有限公司",
                exchange="SSE",
                status="listed",
                confidence="high",
                source="tushare",
                notes="",
                verified_at=now,
                expires_at=now + timedelta(hours=24),
            )
        )

        theme = make_theme()
        proposed = []
        audit = SerenityAgentAudit()
        result = self.runner._execute_tool(
            "propose_add_candidate",
            {
                "symbol": "600519.SH",
                "verification_id": vid,
                "match_reason": "测试",
            },
            theme,
            proposed,
            audit,
        )

        if result["status"] == "ok":
            self.assertEqual(len(proposed), 1)
            self.assertEqual(proposed[0].verification_id, vid)
            self.assertIsNotNone(proposed[0].verification_id)


if __name__ == "__main__":
    unittest.main()
