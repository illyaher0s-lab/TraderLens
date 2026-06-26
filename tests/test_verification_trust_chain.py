"""
Test verification_id trust chain.

Tests that:
- LLM cannot fabricate company names
- LLM cannot bypass verify_ticker
- propose_add_candidate requires valid verification_id
- Expired verification_id is rejected
- Mismatched symbol is rejected
"""

import unittest
from datetime import datetime, timedelta
from backend.db.research import ResearchDB
from backend.services.research_conversation import ResearchConversationService
from backend.services.research_validation import ResearchValidator
from backend.app.tushare.config import TushareConfig
from contracts.research import ThemeInput, TickerVerificationRecord


class FakeTushareClient:
    """Fake Tushare client for testing."""
    
    def __init__(self, config):
        self.config = config
    
    def query(self, api_name, **kwargs):
        """Fake query returns predefined data."""
        if api_name == "stock_basic":
            ts_code = kwargs.get("ts_code")
            if ts_code == "300750.SZ":
                import pandas as pd
                return pd.DataFrame([{
                    "ts_code": "300750.SZ",
                    "name": "宁德时代",
                    "list_status": "L",
                    "delist_date": None,
                }])
            else:
                import pandas as pd
                return pd.DataFrame()
        raise ValueError(f"Unsupported API: {api_name}")


class TestVerificationIDTrustChain(unittest.TestCase):
    """Test verification_id trust chain prevents LLM fabrication."""

    def setUp(self):
        """Set up in-memory database and services."""
        self.db = ResearchDB(":memory:")
        
        # Create fake validator
        config = TushareConfig(token="fake", api_url="http://fake.test")
        self.validator = ResearchValidator(tushare_config=config)
        self.validator._tushare_client = FakeTushareClient(config)
        
        self.service = ResearchConversationService(
            self.db,
            mode="deterministic",
        )
        
        # But inject real validator for verification tests
        self.service.validator = self.validator

    def test_verification_id_is_stored_in_db(self):
        """verify_ticker stores verification record in DB."""
        result = self.validator.verify_ticker("300750.SZ")
        
        # Store in DB
        record = TickerVerificationRecord(
            verification_id=result.verification_id,
            symbol=result.ticker,
            company_name=result.company_name,
            exchange=result.exchange,
            status=result.status,
            confidence=result.confidence,
            source=result.source,
            notes=result.notes,
            verified_at=result.verified_at,
            expires_at=result.verified_at + timedelta(hours=24),
        )
        self.db.store_ticker_verification(record)
        
        # Verify it can be retrieved
        retrieved = self.db.get_ticker_verification(result.verification_id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.symbol, "300750.SZ")
        self.assertEqual(retrieved.company_name, "宁德时代")

    def test_invalid_verification_id_is_rejected(self):
        """propose_add_candidate rejects invalid verification_id."""
        # Call propose_add_candidate tool with invalid verification_id
        from backend.services.research_conversation import ResearchConversationService
        
        # Create theme
        now = datetime.now()
        theme = ThemeInput(
            theme_id="theme_001",
            theme_name="测试主题",
            background="测试背景",
            source_type="manual_theme",
            board_version=0,
            created_at=now,
            updated_at=now,
        )
        self.db.create_theme(theme)
        
        # Try to execute propose_add_candidate with fake verification_id
        result = self.service._execute_tool(
            "propose_add_candidate",
            {
                "theme_id": "theme_001",
                "symbol": "300750.SZ",
                "verification_id": "fake_invalid_id",
                "match_reason": "测试",
            },
            theme,
            now,
        )
        
        self.assertFalse(result["success"])
        self.assertIn("Invalid or expired verification_id", result["error"])

    def test_expired_verification_id_is_rejected(self):
        """propose_add_candidate rejects expired verification_id."""
        # Create expired verification
        now = datetime.now()
        expired_record = TickerVerificationRecord(
            verification_id="expired_verify_123",
            symbol="300750.SZ",
            company_name="宁德时代",
            exchange="SZSE",
            status="listed",
            confidence="high",
            source="tushare",
            notes="Test",
            verified_at=now - timedelta(hours=25),
            expires_at=now - timedelta(hours=1),  # Expired
        )
        self.db.store_ticker_verification(expired_record)
        
        # Create theme
        theme = ThemeInput(
            theme_id="theme_002",
            theme_name="测试主题",
            background="测试背景",
            source_type="manual_theme",
            board_version=0,
            created_at=now,
            updated_at=now,
        )
        self.db.create_theme(theme)
        
        # Try to use expired verification_id
        result = self.service._execute_tool(
            "propose_add_candidate",
            {
                "theme_id": "theme_002",
                "symbol": "300750.SZ",
                "verification_id": "expired_verify_123",
                "match_reason": "测试",
            },
            theme,
            now,
        )
        
        self.assertFalse(result["success"])
        self.assertIn("Invalid or expired verification_id", result["error"])

    def test_mismatched_symbol_is_rejected(self):
        """propose_add_candidate rejects verification_id for different symbol."""
        # Create verification for one symbol
        now = datetime.now()
        result = self.validator.verify_ticker("300750.SZ")
        record = TickerVerificationRecord(
            verification_id=result.verification_id,
            symbol=result.ticker,
            company_name=result.company_name,
            exchange=result.exchange,
            status=result.status,
            confidence=result.confidence,
            source=result.source,
            notes=result.notes,
            verified_at=result.verified_at,
            expires_at=result.verified_at + timedelta(hours=24),
        )
        self.db.store_ticker_verification(record)
        
        # Create theme
        theme = ThemeInput(
            theme_id="theme_003",
            theme_name="测试主题",
            background="测试背景",
            source_type="manual_theme",
            board_version=0,
            created_at=now,
            updated_at=now,
        )
        self.db.create_theme(theme)
        
        # Try to use verification_id for different symbol
        tool_result = self.service._execute_tool(
            "propose_add_candidate",
            {
                "theme_id": "theme_003",
                "symbol": "600519.SH",  # Different symbol!
                "verification_id": result.verification_id,
                "match_reason": "测试",
            },
            theme,
            now,
        )
        
        self.assertFalse(tool_result["success"])
        self.assertIn("Symbol mismatch", tool_result["error"])

    def test_company_name_comes_from_verification_not_llm(self):
        """Company name in ProposedAction comes from verification record, not LLM input."""
        # Verify ticker and store
        now = datetime.now()
        result = self.validator.verify_ticker("300750.SZ")
        record = TickerVerificationRecord(
            verification_id=result.verification_id,
            symbol=result.ticker,
            company_name=result.company_name,
            exchange=result.exchange,
            status=result.status,
            confidence=result.confidence,
            source=result.source,
            notes=result.notes,
            verified_at=result.verified_at,
            expires_at=result.verified_at + timedelta(hours=24),
        )
        self.db.store_ticker_verification(record)
        
        # Create theme
        theme = ThemeInput(
            theme_id="theme_004",
            theme_name="测试主题",
            background="测试背景",
            source_type="manual_theme",
            board_version=0,
            created_at=now,
            updated_at=now,
        )
        self.db.create_theme(theme)
        
        # Execute propose_add_candidate
        tool_result = self.service._execute_tool(
            "propose_add_candidate",
            {
                "theme_id": "theme_004",
                "symbol": "300750.SZ",
                "verification_id": result.verification_id,
                "match_reason": "测试",
            },
            theme,
            now,
        )
        
        self.assertTrue(tool_result["success"])
        # Company name should come from verification record
        self.assertEqual(tool_result["company_name"], "宁德时代")
        # Verification ID should be returned
        self.assertEqual(tool_result["verification_id"], result.verification_id)


if __name__ == "__main__":
    unittest.main()
