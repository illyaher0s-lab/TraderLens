"""
Task 24A: Friend Stock Natural Language Extraction Tests

Test that the system can extract ticker codes and company names from
natural language user input.

Required inputs to support:
1. "帮我看一下宏昌电子是否值得买入?603002"
2. "帮我看一下宏昌电子是否值得买入？603002"
3. "宏昌电子 603002"
4. "603002"
5. "603002.SH"
6. "朋友推荐宏昌电子，代码603002，帮我看看"
7. "帮我查一下宏昌电子是否值得买入"
"""

import pytest
from backend.services.friend_stock_flow import extract_ticker_and_company_from_natural_language


class TestFriendStockNaturalLanguageExtraction:
    """Test natural language ticker and company extraction."""
    
    def test_extract_company_and_bare_code_with_question_mark(self):
        """
        Input: "帮我看一下宏昌电子是否值得买入?603002"
        Expected: ("603002.SH", "宏昌电子")
        """
        raw_code, raw_company = extract_ticker_and_company_from_natural_language(
            "帮我看一下宏昌电子是否值得买入?603002"
        )
        
        assert raw_code == "603002.SH", f"Expected 603002.SH, got {raw_code}"
        assert raw_company == "宏昌电子", f"Expected 宏昌电子, got {raw_company}"
    
    def test_extract_company_and_bare_code_with_chinese_question_mark(self):
        """
        Input: "帮我看一下宏昌电子是否值得买入？603002"
        Expected: ("603002.SH", "宏昌电子")
        """
        raw_code, raw_company = extract_ticker_and_company_from_natural_language(
            "帮我看一下宏昌电子是否值得买入？603002"
        )
        
        assert raw_code == "603002.SH"
        assert raw_company == "宏昌电子"
    
    def test_extract_company_and_bare_code_simple(self):
        """
        Input: "宏昌电子 603002"
        Expected: ("603002.SH", "宏昌电子")
        """
        raw_code, raw_company = extract_ticker_and_company_from_natural_language(
            "宏昌电子 603002"
        )
        
        assert raw_code == "603002.SH"
        assert raw_company == "宏昌电子"
    
    def test_extract_bare_code_only(self):
        """
        Input: "603002"
        Expected: ("603002.SH", None)
        """
        raw_code, raw_company = extract_ticker_and_company_from_natural_language(
            "603002"
        )
        
        assert raw_code == "603002.SH"
        assert raw_company is None
    
    def test_extract_code_with_suffix(self):
        """
        Input: "603002.SH"
        Expected: ("603002.SH", None)
        """
        raw_code, raw_company = extract_ticker_and_company_from_natural_language(
            "603002.SH"
        )
        
        assert raw_code == "603002.SH"
        assert raw_company is None
    
    def test_extract_company_and_code_with_noise(self):
        """
        Input: "朋友推荐宏昌电子，代码603002，帮我看看"
        Expected: ("603002.SH", "宏昌电子")
        """
        raw_code, raw_company = extract_ticker_and_company_from_natural_language(
            "朋友推荐宏昌电子，代码603002，帮我看看"
        )
        
        assert raw_code == "603002.SH"
        assert raw_company == "宏昌电子"
    
    def test_extract_company_only(self):
        """
        Input: "帮我查一下宏昌电子是否值得买入"
        Expected: (None, "宏昌电子")
        """
        raw_code, raw_company = extract_ticker_and_company_from_natural_language(
            "帮我查一下宏昌电子是否值得买入"
        )
        
        assert raw_code is None
        assert raw_company == "宏昌电子"
    
    def test_extract_shenzhen_stock(self):
        """
        Input: "000001"
        Expected: ("000001.SZ", None)
        """
        raw_code, raw_company = extract_ticker_and_company_from_natural_language(
            "000001"
        )
        
        assert raw_code == "000001.SZ"
        assert raw_company is None
    
    def test_extract_shenzhen_stock_300(self):
        """
        Input: "300750"
        Expected: ("300750.SZ", None)
        """
        raw_code, raw_company = extract_ticker_and_company_from_natural_language(
            "300750"
        )
        
        assert raw_code == "300750.SZ"
        assert raw_company is None
    
    def test_extract_shanghai_stock_688(self):
        """
        Input: "688001"
        Expected: ("688001.SH", None)
        """
        raw_code, raw_company = extract_ticker_and_company_from_natural_language(
            "688001"
        )
        
        assert raw_code == "688001.SH"
        assert raw_company is None
    
    def test_extract_beijing_stock(self):
        """
        Input: "430001"
        Expected: ("430001.BJ", None)
        
        Beijing Stock Exchange - should be detected and rejected later
        """
        raw_code, raw_company = extract_ticker_and_company_from_natural_language(
            "430001"
        )
        
        assert raw_code == "430001.BJ"
        assert raw_company is None
    
    def test_extract_code_with_lowercase_suffix(self):
        """
        Input: "603002.sh"
        Expected: ("603002.SH", None)
        """
        raw_code, raw_company = extract_ticker_and_company_from_natural_language(
            "603002.sh"
        )
        
        assert raw_code == "603002.SH"
        assert raw_company is None
