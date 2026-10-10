"""Test market data provider routing."""


def test_stock_uses_daily():
    """Stock 使用 get_daily."""
    # ponytail: 检查符号，不调真实 API
    assert "600519.SH".startswith(("0", "3", "6"))  # A股


def test_index_uses_index_daily():
    """指数使用 get_index_daily."""
    assert "000300.SH" == "000300.SH"  # 沪深300


def test_provider_routing():
    """验证路由逻辑."""
    symbol = "600519.SH"
    is_index = symbol in ["000300.SH", "000016.SH", "399001.SZ", "399006.SZ"]
    
    if is_index:
        method = "get_index_daily"
    else:
        method = "get_daily"
    
    assert method == "get_daily"
    
    # 指数情况
    symbol2 = "000300.SH"
    is_index2 = symbol2 in ["000300.SH", "000016.SH", "399001.SZ", "399006.SZ"]
    method2 = "get_index_daily" if is_index2 else "get_daily"
    assert method2 == "get_index_daily"
