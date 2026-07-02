"""
Tests for StockIdentityResolver

Focus: Production path bare code inference logic
"""

import pytest
from backend.services.stock_identity_resolver import StockIdentityResolver


def test_bare_code_inference_in_fixture_mode():
    """Test that bare codes are inferred to full ticker in fixture mode."""
    test_fixture = {
        '600519.SH': {
            'ticker': '600519.SH',
            'company_name': '贵州茅台',
            'exchange': 'SSE',
            'list_status': 'L'
        },
        '000858.SZ': {
            'ticker': '000858.SZ',
            'company_name': '五粮液',
            'exchange': 'SZSE',
            'list_status': 'L'
        },
    }
    
    resolver = StockIdentityResolver(test_fixture=test_fixture)
    
    # Test SH inference
    result_sh = resolver.resolve(company_name=None, stock_code='600519')
    assert result_sh.status == 'verified'
    assert result_sh.ticker == '600519.SH'
    assert result_sh.company_name == '贵州茅台'
    assert result_sh.exchange == 'SSE'
    
    # Test SZ inference
    result_sz = resolver.resolve(company_name=None, stock_code='000858')
    assert result_sz.status == 'verified'
    assert result_sz.ticker == '000858.SZ'
    assert result_sz.company_name == '五粮液'
    assert result_sz.exchange == 'SZSE'


def test_bare_code_sh_prefixes():
    """Test all SH prefixes: 600, 601, 603, 605, 688."""
    test_fixture = {
        '600000.SH': {'ticker': '600000.SH', 'company_name': 'Test600', 'exchange': 'SSE', 'list_status': 'L'},
        '601000.SH': {'ticker': '601000.SH', 'company_name': 'Test601', 'exchange': 'SSE', 'list_status': 'L'},
        '603000.SH': {'ticker': '603000.SH', 'company_name': 'Test603', 'exchange': 'SSE', 'list_status': 'L'},
        '605000.SH': {'ticker': '605000.SH', 'company_name': 'Test605', 'exchange': 'SSE', 'list_status': 'L'},
        '688000.SH': {'ticker': '688000.SH', 'company_name': 'Test688', 'exchange': 'SSE', 'list_status': 'L'},
    }
    
    resolver = StockIdentityResolver(test_fixture=test_fixture)
    
    for prefix in ['600', '601', '603', '605', '688']:
        code = f'{prefix}000'
        result = resolver.resolve(company_name=None, stock_code=code)
        assert result.status == 'verified', f'{code} should be verified'
        assert result.ticker == f'{code}.SH', f'{code} should infer to .SH'


def test_bare_code_sz_prefixes():
    """Test all SZ prefixes: 000, 001, 002, 003, 300, 301."""
    test_fixture = {
        '000000.SZ': {'ticker': '000000.SZ', 'company_name': 'Test000', 'exchange': 'SZSE', 'list_status': 'L'},
        '001000.SZ': {'ticker': '001000.SZ', 'company_name': 'Test001', 'exchange': 'SZSE', 'list_status': 'L'},
        '002000.SZ': {'ticker': '002000.SZ', 'company_name': 'Test002', 'exchange': 'SZSE', 'list_status': 'L'},
        '003000.SZ': {'ticker': '003000.SZ', 'company_name': 'Test003', 'exchange': 'SZSE', 'list_status': 'L'},
        '300000.SZ': {'ticker': '300000.SZ', 'company_name': 'Test300', 'exchange': 'SZSE', 'list_status': 'L'},
        '301000.SZ': {'ticker': '301000.SZ', 'company_name': 'Test301', 'exchange': 'SZSE', 'list_status': 'L'},
    }
    
    resolver = StockIdentityResolver(test_fixture=test_fixture)
    
    for prefix in ['000', '001', '002', '003', '300', '301']:
        code = f'{prefix}000' if prefix in ['001', '002', '003', '301'] else f'{prefix}000'
        result = resolver.resolve(company_name=None, stock_code=code)
        assert result.status == 'verified', f'{code} should be verified'
        assert result.ticker == f'{code}.SZ', f'{code} should infer to .SZ'


def test_company_name_query():
    """Test company name lookup in fixture."""
    test_fixture = {
        '600519.SH': {
            'ticker': '600519.SH',
            'company_name': '贵州茅台',
            'exchange': 'SSE',
            'list_status': 'L'
        },
    }
    
    resolver = StockIdentityResolver(test_fixture=test_fixture)
    
    result = resolver.resolve(company_name='贵州茅台', stock_code=None)
    assert result.status == 'verified'
    assert result.ticker == '600519.SH'
    assert result.company_name == '贵州茅台'


def test_not_found():
    """Test not found scenario."""
    test_fixture = {
        '600519.SH': {
            'ticker': '600519.SH',
            'company_name': '贵州茅台',
            'exchange': 'SSE',
            'list_status': 'L'
        },
    }
    
    resolver = StockIdentityResolver(test_fixture=test_fixture)
    
    result = resolver.resolve(company_name='不存在的公司', stock_code=None)
    assert result.status == 'not_found'
    assert result.data_source == 'deterministic_fixture'
    assert '不存在的公司' in result.fault_reason


def test_full_ticker_direct_match():
    """Test that full tickers (with suffix) match directly."""
    test_fixture = {
        '600519.SH': {
            'ticker': '600519.SH',
            'company_name': '贵州茅台',
            'exchange': 'SSE',
            'list_status': 'L'
        },
    }
    
    resolver = StockIdentityResolver(test_fixture=test_fixture)
    
    result = resolver.resolve(company_name=None, stock_code='600519.SH')
    assert result.status == 'verified'
    assert result.ticker == '600519.SH'
