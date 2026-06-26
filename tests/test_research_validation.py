"""
Tests for research validation service.

Test ticker verification with fake Tushare client.
Test hard filters.
"""

import unittest
from datetime import datetime
from backend.services.research_validation import (
    ResearchValidator,
    ValidationResult,
    TickerVerificationResult,
)
from backend.app.tushare.config import TushareConfig


class FakeTushareClient:
    """Fake Tushare client for testing."""
    
    def __init__(self, config):
        self.config = config
    
    def query(self, api_name, **kwargs):
        """Fake query returns predefined data."""
        if api_name == "stock_basic":
            ts_code = kwargs.get("ts_code")
            
            # Known stocks
            if ts_code == "300750.SZ":
                import pandas as pd
                return pd.DataFrame([{
                    "ts_code": "300750.SZ",
                    "name": "宁德时代",
                    "area": "福建",
                    "industry": "电气设备",
                    "market": "创业板",
                    "list_status": "L",
                    "list_date": "20180611",
                    "delist_date": None,
                }])
            elif ts_code == "600519.SH":
                import pandas as pd
                return pd.DataFrame([{
                    "ts_code": "600519.SH",
                    "name": "贵州茅台",
                    "area": "贵州",
                    "industry": "食品饮料",
                    "market": "主板",
                    "list_status": "L",
                    "list_date": "20010827",
                    "delist_date": None,
                }])
            elif ts_code == "600000.SH":
                import pandas as pd
                return pd.DataFrame([{
                    "ts_code": "600000.SH",
                    "name": "浦发银行",
                    "area": "上海",
                    "industry": "银行",
                    "market": "主板",
                    "list_status": "L",
                    "list_date": "19991110",
                    "delist_date": None,
                }])
            elif ts_code == "000001.SZ":  # Known but daily_basic is missing
                import pandas as pd
                return pd.DataFrame([{
                    "ts_code": "000001.SZ",
                    "name": "平安银行",
                    "area": "深圳",
                    "industry": "银行",
                    "market": "主板",
                    "list_status": "L",
                    "list_date": "19910403",
                    "delist_date": None,
                }])
            elif ts_code == "000002.SZ":  # Known + ST
                import pandas as pd
                return pd.DataFrame([{
                    "ts_code": "000002.SZ",
                    "name": "ST万科",
                    "area": "深圳",
                    "industry": "房地产",
                    "market": "主板",
                    "list_status": "L",
                    "list_date": "19910129",
                    "delist_date": None,
                }])
            elif ts_code == "002594.SZ":
                import pandas as pd
                return pd.DataFrame([{
                    "ts_code": "002594.SZ",
                    "name": "比亚迪",
                    "area": "深圳",
                    "industry": "汽车",
                    "market": "主板",
                    "list_status": "L",
                    "list_date": "20110630",
                    "delist_date": None,
                }])
            else:
                # Industry-based query (for get_sector_and_peers)
                industry = kwargs.get("industry")
                if industry:
                    import pandas as pd
                    if industry == "电气设备":
                        return pd.DataFrame([
                            {"ts_code": "300750.SZ", "name": "宁德时代", "industry": "电气设备", "list_status": "L"},
                            {"ts_code": "600406.SH", "name": "国电南瑞", "industry": "电气设备", "list_status": "L"},
                            {"ts_code": "002074.SZ", "name": "国轩高科", "industry": "电气设备", "list_status": "L"},
                            {"ts_code": "002129.SZ", "name": "中环股份", "industry": "电气设备", "list_status": "L"},
                        ])
                    elif industry == "食品饮料":
                        return pd.DataFrame([
                            {"ts_code": "600519.SH", "name": "贵州茅台", "industry": "食品饮料", "list_status": "L"},
                            {"ts_code": "000858.SZ", "name": "五粮液", "industry": "食品饮料", "list_status": "L"},
                            {"ts_code": "600809.SH", "name": "山西汾酒", "industry": "食品饮料", "list_status": "L"},
                            {"ts_code": "002304.SZ", "name": "洋河股份", "industry": "食品饮料", "list_status": "L"},
                        ])
                    elif industry == "银行":
                        return pd.DataFrame([
                            {"ts_code": "600000.SH", "name": "浦发银行", "industry": "银行", "list_status": "L"},
                            {"ts_code": "000001.SZ", "name": "平安银行", "industry": "银行", "list_status": "L"},
                            {"ts_code": "601398.SH", "name": "工商银行", "industry": "银行", "list_status": "L"},
                            {"ts_code": "600036.SH", "name": "招商银行", "industry": "银行", "list_status": "L"},
                        ])
                    elif industry == "汽车":
                        return pd.DataFrame([
                            {"ts_code": "002594.SZ", "name": "比亚迪", "industry": "汽车", "list_status": "L"},
                            {"ts_code": "000625.SZ", "name": "长安汽车", "industry": "汽车", "list_status": "L"},
                            {"ts_code": "601238.SH", "name": None, "industry": "汽车", "list_status": "L"},  # missing name
                            {"ts_code": "600104.SH", "name": "上汽集团", "industry": "汽车", "list_status": "L"},
                        ])
                    elif industry == "房地产":
                        return pd.DataFrame([
                            {"ts_code": "000002.SZ", "name": "ST万科", "industry": "房地产", "list_status": "L"},
                            {"ts_code": "001979.SZ", "name": "招商蛇口", "industry": "房地产", "list_status": "L"},
                            {"ts_code": "600048.SH", "name": "保利发展", "industry": "房地产", "list_status": "L"},
                        ])
                    else:
                        return pd.DataFrame()
                # Unknown stock by ts_code
                import pandas as pd
                return pd.DataFrame()
        
        if api_name == "daily_basic":
            ts_code = kwargs.get("ts_code")
            import pandas as pd
            if ts_code == "300750.SZ":
                # 5 days of trading data with amounts
                return pd.DataFrame({
                    "ts_code": ["300750.SZ"] * 5,
                    "trade_date": [
                        "20260619", "20260620", "20260622",
                        "20260623", "20260624",
                    ],
                    "amount": [
                        5000000000.0, 4800000000.0, 5200000000.0,
                        4900000000.0, 5100000000.0,
                    ],
                })
            elif ts_code == "600519.SH":
                return pd.DataFrame({
                    "ts_code": ["600519.SH"] * 3,
                    "trade_date": ["20260620", "20260623", "20260624"],
                    "amount": [8000000000.0, 7500000000.0, 8200000000.0],
                })
            elif ts_code == "600000.SH":
                return pd.DataFrame({
                    "ts_code": ["600000.SH"] * 4,
                    "trade_date": [
                        "20260619", "20260620", "20260623", "20260624",
                    ],
                    "amount": [
                        300000000.0, 280000000.0, 290000000.0, 310000000.0,
                    ],
                })
            elif ts_code == "000002.SZ":
                # ST stock but with valid daily_basic
                return pd.DataFrame({
                    "ts_code": ["000002.SZ"] * 3,
                    "trade_date": ["20260619", "20260620", "20260623"],
                    "amount": [2000000000.0, 2100000000.0, 1900000000.0],
                })
            else:
                # Missing daily_basic data (e.g., 000001.SZ)
                import pandas as pd
                return pd.DataFrame()
        
        if api_name == "income":
            ts_code = kwargs.get("ts_code")
            import pandas as pd
            if ts_code == "300750.SZ":
                # Normal financial data — 4 quarters
                return pd.DataFrame({
                    "ts_code": ["300750.SZ"] * 4,
                    "end_date": ["20251231", "20250930", "20250630", "20250331"],
                    "ann_date": ["20260320", "20251028", "20250825", "20250426"],
                    "report_type": ["1", "1", "1", "1"],
                    "total_revenue": [4.2e10, 3.1e10, 2.0e10, 1.0e10],
                    "revenue": [4.1e10, 3.0e10, 1.9e10, 9.5e9],
                    "oper_cost": [3.2e10, 2.3e10, 1.5e10, 7.5e9],
                    "operate_profit": [5.0e9, 3.8e9, 2.5e9, 1.2e9],
                    "total_profit": [4.8e9, 3.6e9, 2.4e9, 1.1e9],
                    "n_income": [4.2e9, 3.1e9, 2.1e9, 1.0e9],
                    "n_income_attr_p": [4.1e9, 3.0e9, 2.0e9, 9.8e8],
                    "basic_eps": [8.5, 6.4, 4.3, 2.1],
                    "diluted_eps": [8.4, 6.3, 4.2, 2.0],
                    "ebit": [5.2e9, 4.0e9, 2.7e9, 1.3e9],
                    "ebitda": [6.0e9, 4.5e9, 3.0e9, 1.5e9],
                })
            elif ts_code == "600519.SH":
                return pd.DataFrame({
                    "ts_code": ["600519.SH"] * 2,
                    "end_date": ["20251231", "20250930"],
                    "ann_date": ["20260325", "20251030"],
                    "report_type": ["1", "1"],
                    "total_revenue": [1.5e11, 1.1e11],
                    "revenue": [1.48e11, 1.08e11],
                    "oper_cost": [2.5e10, 1.8e10],
                    "operate_profit": [9.0e10, 6.5e10],
                    "total_profit": [8.9e10, 6.4e10],
                    "n_income": [7.5e10, 5.4e10],
                    "n_income_attr_p": [7.4e10, 5.3e10],
                    "basic_eps": [50.0, 36.0],
                    "diluted_eps": [49.8, 35.8],
                    "ebit": [9.2e10, 6.7e10],
                    "ebitda": [9.5e10, 7.0e10],
                })
            elif ts_code == "002594.SZ":
                # Partial data — some fields are NaN/missing
                df = pd.DataFrame({
                    "ts_code": ["002594.SZ"] * 2,
                    "end_date": ["20251231", "20250930"],
                    "ann_date": ["20260318", "20251025"],
                    "report_type": ["1", "1"],
                    "total_revenue": [6.0e10, 4.5e10],
                    "revenue": [5.8e10, 4.3e10],
                    "oper_cost": [4.0e10, 3.0e10],
                    "operate_profit": [8.0e9, 6.0e9],
                    "total_profit": [7.5e9, 5.8e9],
                    "n_income": [None, 2.5e9],  # missing for first row
                    "n_income_attr_p": [None, 2.4e9],
                    "basic_eps": [None, 0.85],
                    "diluted_eps": [None, 0.84],
                    "ebit": [8.5e9, 6.2e9],
                    "ebitda": [9.0e9, 6.5e9],
                })
                return df
            elif ts_code == "000001.SZ":
                # Empty result
                return pd.DataFrame()
            else:
                return pd.DataFrame()
        
        if api_name == "anns":
            ts_code = kwargs.get("ts_code")
            import pandas as pd
            if ts_code == "300750.SZ":
                return pd.DataFrame({
                    "ts_code": ["300750.SZ"] * 5,
                    "ann_date": [
                        "20260620", "20260615", "20260610",
                        "20260605", "20260601",
                    ],
                    "title": [
                        "关于收到政府补助的公告",
                        "2025年年度报告",
                        "关于控股股东增持计划的公告",
                        "关于对外投资设立子公司的公告",
                        "关于签署战略合作协议的公告",
                    ],
                    "ann_type": [
                        "800001", "01010101", "800005",
                        "150001", "800030",
                    ],
                    "pub_date": [
                        "20260620", "20260615", "20260610",
                        "20260605", "20260601",
                    ],
                    "content_type": [
                        "PDF", "PDF", "PDF", "PDF", "PDF",
                    ],
                })
            elif ts_code == "600519.SH":
                return pd.DataFrame({
                    "ts_code": ["600519.SH"] * 3,
                    "ann_date": ["20260622", "20260618", "20260612"],
                    "title": [
                        "关于产品价格调整的公告",
                        "2025年度利润分配预案",
                        "关于董事会换届选举的公告",
                    ],
                    "ann_type": ["01030101", "01030301", "800201"],
                    "pub_date": ["20260622", "20260618", "20260612"],
                    "content_type": ["PDF", "PDF", "PDF"],
                })
            elif ts_code == "002594.SZ":
                # Partial data — some rows missing title
                import numpy as np
                return pd.DataFrame({
                    "ts_code": ["002594.SZ"] * 4,
                    "ann_date": [
                        "20260624", "20260620", "20260615", "20260610",
                    ],
                    "title": [
                        "关于回购股份进展的公告", None,
                        "关于变更部分募集资金用途的公告", None,
                    ],
                    "ann_type": [
                        "800007", "01010101", "150002", "800005",
                    ],
                    "pub_date": [
                        "20260624", "20260620", "20260615", "20260610",
                    ],
                    "content_type": ["PDF", "PDF", "PDF", "PDF"],
                })
            elif ts_code == "000001.SZ":
                # Empty result
                return pd.DataFrame()
            else:
                return pd.DataFrame()
        
        raise ValueError(f"Unsupported API: {api_name}")


class TestTickerVerification(unittest.TestCase):
    """Test ticker verification with fake Tushare client."""

    def setUp(self):
        """Set up validator with fake Tushare client."""
        config = TushareConfig(
            token="fake_token_for_testing",
            api_url="http://fake.test",
        )
        self.validator = ResearchValidator(tushare_config=config)
        # Inject fake client
        self.validator._tushare_client = FakeTushareClient(config)

    def test_verify_ticker_listed_stock(self):
        """Valid listed stock passes with high confidence."""
        result = self.validator.verify_ticker("300750.SZ")
        
        self.assertIsInstance(result, TickerVerificationResult)
        self.assertIsNotNone(result.verification_id)
        self.assertTrue(result.verification_id.startswith("verify_"))
        self.assertEqual(result.ticker, "300750.SZ")
        self.assertEqual(result.company_name, "宁德时代")
        self.assertEqual(result.exchange, "SZSE")
        self.assertEqual(result.status, "listed")
        self.assertEqual(result.confidence, "high")
        self.assertEqual(result.source, "tushare")
        self.assertIn("Listed", result.notes)

    def test_verify_ticker_unknown_stock(self):
        """Unknown stock returns low confidence."""
        result = self.validator.verify_ticker("999999.SZ")
        
        self.assertIsInstance(result, TickerVerificationResult)
        self.assertIsNotNone(result.verification_id)
        self.assertTrue(result.verification_id.startswith("verify_"))
        self.assertEqual(result.ticker, "999999.SZ")
        self.assertEqual(result.company_name, "")
        self.assertEqual(result.exchange, "")
        self.assertEqual(result.status, "unknown")
        self.assertEqual(result.confidence, "low")
        self.assertEqual(result.source, "tushare")
        self.assertIn("not found", result.notes)

    def test_verify_ticker_shanghai_stock(self):
        """Shanghai stock has SSE exchange."""
        result = self.validator.verify_ticker("600519.SH")
        
        self.assertIsNotNone(result.verification_id)
        self.assertTrue(result.verification_id.startswith("verify_"))
        self.assertEqual(result.ticker, "600519.SH")
        self.assertEqual(result.company_name, "贵州茅台")
        self.assertEqual(result.exchange, "SSE")
        self.assertEqual(result.status, "listed")
        self.assertEqual(result.confidence, "high")


class TestHardFilters(unittest.TestCase):
    """Test hard filter validation."""

    def setUp(self):
        """Set up validator."""
        self.validator = ResearchValidator(liquidity_threshold=1000000.0)

    def test_valid_stock_passes(self):
        """Valid listed stock passes with no flags."""
        result = self.validator.validate_candidate(
            symbol="300750.SZ",
            company_name="宁德时代",
            is_listed=True,
            is_st=False,
            is_suspended=False,
            avg_daily_volume=5000000.0,
        )
        
        self.assertEqual(result.flags, [])
        self.assertTrue(result.is_valid)

    def test_st_stock_flagged(self):
        """ST stock is flagged."""
        result = self.validator.validate_candidate(
            symbol="600123.SH",
            company_name="某ST公司",
            is_listed=True,
            is_st=True,
            is_suspended=False,
            avg_daily_volume=2000000.0,
        )
        
        self.assertIn("is_st", result.flags)
        self.assertFalse(result.is_valid)

    def test_suspended_stock_flagged(self):
        """Suspended stock is flagged."""
        result = self.validator.validate_candidate(
            symbol="600456.SH",
            company_name="某停牌公司",
            is_listed=True,
            is_st=False,
            is_suspended=True,
            avg_daily_volume=2000000.0,
        )
        
        self.assertIn("is_suspended", result.flags)
        self.assertFalse(result.is_valid)

    def test_unknown_symbol_flagged(self):
        """Missing identity is flagged."""
        result = self.validator.validate_candidate(
            symbol="999999.SZ",
            company_name=None,
            is_listed=False,
            is_st=False,
            is_suspended=False,
            avg_daily_volume=0.0,
        )
        
        self.assertIn("unknown_symbol", result.flags)
        self.assertFalse(result.is_valid)

    def test_not_listed_flagged(self):
        """Not listed stock is flagged."""
        result = self.validator.validate_candidate(
            symbol="600789.SH",
            company_name="某退市公司",
            is_listed=False,
            is_st=False,
            is_suspended=False,
            avg_daily_volume=0.0,
        )
        
        self.assertIn("not_listed", result.flags)
        self.assertFalse(result.is_valid)

    def test_low_liquidity_flagged(self):
        """Low liquidity is flagged by amount threshold."""
        result = self.validator.validate_candidate(
            symbol="300123.SZ",
            company_name="某低流动性公司",
            is_listed=True,
            is_st=False,
            is_suspended=False,
            avg_daily_volume=500000.0,  # Below 1M threshold
        )
        
        self.assertIn("low_liquidity", result.flags)
        self.assertFalse(result.is_valid)


class TestHardFilterSnapshot(unittest.TestCase):
    """Test get_hard_filter_snapshot with fake Tushare client."""

    def setUp(self):
        config = TushareConfig(
            token="fake_token_for_testing",
            api_url="http://fake.test",
        )
        self.validator = ResearchValidator(tushare_config=config)
        self.validator._tushare_client = FakeTushareClient(config)

    def test_normal_data_produces_complete_snapshot(self):
        """Normal stock with both stock_basic and daily_basic returns complete HardFilterSnapshot."""
        from backend.services.research_validation import HardFilterSnapshot
        snapshot = self.validator.get_hard_filter_snapshot("300750.SZ", "listed")

        self.assertIsInstance(snapshot, HardFilterSnapshot)
        self.assertTrue(snapshot.is_listed)
        self.assertFalse(snapshot.is_st)
        self.assertFalse(snapshot.is_suspended)
        self.assertIsNotNone(snapshot.avg_daily_volume)
        self.assertGreater(snapshot.avg_daily_volume, 0)
        self.assertEqual(snapshot.source, "tushare")
        self.assertEqual(snapshot.gaps, [])

    def test_daily_basic_missing_produces_none_liquidity_and_gap(self):
        """When daily_basic returns empty, avg_daily_volume is None and gap is recorded."""
        snapshot = self.validator.get_hard_filter_snapshot("000001.SZ", "listed")

        self.assertIsNone(snapshot.avg_daily_volume)
        self.assertIn("daily_basic_amount_missing", snapshot.gaps)
        # is_listed from verified_status, not from daily_basic
        self.assertTrue(snapshot.is_listed)

    def test_stock_basic_missing_produces_st_none_and_gap(self):
        """When stock_basic is missing, is_st is None and gap is recorded."""
        snapshot = self.validator.get_hard_filter_snapshot("999999.SZ", "unknown")

        self.assertIsNone(snapshot.is_st)
        self.assertIn("stock_basic_missing", snapshot.gaps)
        self.assertIsNone(snapshot.is_listed)

    def test_st_stock_name_detected_from_stock_basic(self):
        """ST stock is detected from name prefix in stock_basic."""
        snapshot = self.validator.get_hard_filter_snapshot("000002.SZ", "listed")

        self.assertTrue(snapshot.is_st)
        self.assertTrue(snapshot.is_listed)
        self.assertIsNotNone(snapshot.avg_daily_volume)

    def test_suspended_status_maps_is_suspended_true(self):
        """Verified status 'suspended' maps to is_suspended=True."""
        snapshot = self.validator.get_hard_filter_snapshot("300750.SZ", "suspended")

        self.assertTrue(snapshot.is_suspended)
        self.assertFalse(snapshot.is_listed)
        self.assertTrue(snapshot.is_st is False)


class TestHardFilterUnknownFlags(unittest.TestCase):
    """Test validate_candidate produces unknown flags when data is None."""

    def setUp(self):
        self.validator = ResearchValidator(liquidity_threshold=1000000.0)

    def test_is_listed_none_produces_unknown_listing_status(self):
        """is_listed=None is NOT a pass — it produces unknown_listing_status."""
        result = self.validator.validate_candidate(
            symbol="300750.SZ",
            company_name="宁德时代",
            is_listed=None,
            is_st=False,
            is_suspended=False,
            avg_daily_volume=5000000.0,
        )
        self.assertIn("unknown_listing_status", result.flags)
        self.assertFalse(result.is_valid)

    def test_is_st_none_produces_unknown_st_status(self):
        """is_st=None is NOT a pass — it produces unknown_st_status."""
        result = self.validator.validate_candidate(
            symbol="300750.SZ",
            company_name="宁德时代",
            is_listed=True,
            is_st=None,
            is_suspended=False,
            avg_daily_volume=5000000.0,
        )
        self.assertIn("unknown_st_status", result.flags)
        self.assertFalse(result.is_valid)

    def test_is_suspended_none_produces_unknown_suspension_status(self):
        """is_suspended=None is NOT a pass — it produces unknown_suspension_status."""
        result = self.validator.validate_candidate(
            symbol="300750.SZ",
            company_name="宁德时代",
            is_listed=True,
            is_st=False,
            is_suspended=None,
            avg_daily_volume=5000000.0,
        )
        self.assertIn("unknown_suspension_status", result.flags)
        self.assertFalse(result.is_valid)

    def test_avg_daily_volume_none_produces_unknown_liquidity(self):
        """avg_daily_volume=None is NOT a pass — it produces unknown_liquidity."""
        result = self.validator.validate_candidate(
            symbol="300750.SZ",
            company_name="宁德时代",
            is_listed=True,
            is_st=False,
            is_suspended=False,
            avg_daily_volume=None,
        )
        self.assertIn("unknown_liquidity", result.flags)
        self.assertFalse(result.is_valid)

    def test_everything_unknown_produces_all_four_flags(self):
        """When all hard-filter inputs are None, all four unknown flags are produced."""
        result = self.validator.validate_candidate(
            symbol="999999.SZ",
            company_name="未知公司",
            is_listed=None,
            is_st=None,
            is_suspended=None,
            avg_daily_volume=None,
        )
        self.assertIn("unknown_listing_status", result.flags)
        self.assertIn("unknown_st_status", result.flags)
        self.assertIn("unknown_suspension_status", result.flags)
        self.assertIn("unknown_liquidity", result.flags)
        self.assertEqual(len(result.flags), 4)
        self.assertFalse(result.is_valid)


if __name__ == "__main__":
    unittest.main()
