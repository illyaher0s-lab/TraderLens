"""Phase 2A 测试 - 使用本地测试数据

验证工具逻辑是否正确，不依赖外部 API。
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta


def create_mock_kline_data(stock_code: str, days: int = 250) -> pd.DataFrame:
    """创建模拟 K 线数据
    
    生成一个上涨趋势的 K 线数据用于测试。
    """
    dates = pd.date_range(end=datetime.now(), periods=days, freq='D')
    
    # 生成模拟价格（上涨趋势 + 随机波动）
    base_price = 10.0
    trend = np.linspace(0, 5, days)  # 上涨 5 元
    noise = np.random.normal(0, 0.3, days)  # 随机波动
    close_prices = base_price + trend + noise
    
    # 生成 OHLC
    open_prices = close_prices + np.random.normal(0, 0.1, days)
    high_prices = np.maximum(open_prices, close_prices) + np.abs(np.random.normal(0, 0.1, days))
    low_prices = np.minimum(open_prices, close_prices) - np.abs(np.random.normal(0, 0.1, days))
    
    # 生成成交量（随机 + 近期放大）
    volume = np.random.randint(10000000, 50000000, days).astype(float)
    volume[-5:] = volume[-5:] * 1.8  # 最近 5 天成交量放大
    
    df = pd.DataFrame({
        'date': dates,
        'open': open_prices,
        'close': close_prices,
        'high': high_prices,
        'low': low_prices,
        'volume': volume,
        'amount': volume * close_prices,
        'amplitude': ((high_prices - low_prices) / close_prices * 100).round(2),
        'change_pct': (np.concatenate([[0], np.diff(close_prices) / close_prices[:-1] * 100])).round(2),
        'change_amount': np.concatenate([[0], np.diff(close_prices)]).round(2),
        'turnover_rate': (volume / 1000000000 * 100).round(2)  # 假设总股本 10 亿
    })
    
    return df


def test_market_regime_tool():
    """测试 market_regime_tool（用假数据）"""
    print("\n" + "="*60)
    print("测试 market_regime_tool")
    print("="*60)
    
    # Monkey patch DataFetcher.get_stock_daily_kline
    from core import data_fetcher
    original_method = data_fetcher.DataFetcher.get_stock_daily_kline
    
    def mock_get_stock_daily_kline(self, stock_code, start_date=None, end_date=None, adjust="qfq"):
        print(f"  [Mock] 返回模拟数据: {stock_code}, {len(create_mock_kline_data(stock_code))} 行")
        return create_mock_kline_data(stock_code)
    
    data_fetcher.DataFetcher.get_stock_daily_kline = mock_get_stock_daily_kline
    
    try:
        from tools.market_regime_tool import market_regime_tool
        result = market_regime_tool(index_code="000001")
        
        print(f"\n状态: {result['status']}")
        print(f"摘要: {result['summary']}")
        print(f"信号: {result['signals']}")
        print(f"\n核心结果:")
        for key, value in result['result'].items():
            print(f"  {key}: {value}")
        
        assert result['status'] == 'success', "工具执行失败"
        assert 'regime' in result['result'], "缺少 regime 字段"
        assert 'confidence' in result['result'], "缺少 confidence 字段"
        
        print("\n✅ market_regime_tool 测试通过")
    
    finally:
        # 恢复原方法
        data_fetcher.DataFetcher.get_stock_daily_kline = original_method


def test_technicals_tool():
    """测试 technicals_tool（用假数据）"""
    print("\n" + "="*60)
    print("测试 technicals_tool")
    print("="*60)
    
    # Monkey patch DataFetcher.get_stock_daily_kline
    from core import data_fetcher
    original_method = data_fetcher.DataFetcher.get_stock_daily_kline
    
    def mock_get_stock_daily_kline(self, stock_code, start_date=None, end_date=None, adjust="qfq"):
        print(f"  [Mock] 返回模拟数据: {stock_code}, {len(create_mock_kline_data(stock_code))} 行")
        return create_mock_kline_data(stock_code)
    
    data_fetcher.DataFetcher.get_stock_daily_kline = mock_get_stock_daily_kline
    
    try:
        from tools.technicals_tool import technicals_tool
        result = technicals_tool(stock_code="000001", strategy_profile="trend")
        
        print(f"\n状态: {result['status']}")
        print(f"摘要: {result['summary']}")
        print(f"信号: {result['signals']}")
        print(f"\n核心结果:")
        for key, value in result['result'].items():
            print(f"  {key}: {value}")
        
        assert result['status'] == 'success', "工具执行失败"
        assert 'score' in result['result'], "缺少 score 字段"
        assert 'verdict' in result['result'], "缺少 verdict 字段"
        
        print("\n✅ technicals_tool 测试通过")
    
    finally:
        # 恢复原方法
        data_fetcher.DataFetcher.get_stock_daily_kline = original_method


def test_trade_plan_tool():
    """测试 trade_plan_tool（用假数据）"""
    print("\n" + "="*60)
    print("测试 trade_plan_tool")
    print("="*60)
    
    # 模拟 observations
    mock_market_regime = {
        "regime": "bull",
        "volatility": "low",
        "trend": "up",
        "confidence": 0.85
    }
    
    mock_technicals = {
        "score": 78.0,
        "verdict": "偏多",
        "ma_signal": "golden_cross",
        "macd_signal": "bullish",
        "rsi": 65.0,
        "volume_signal": "surge",
        "latest_close": 15.50
    }
    
    from tools.trade_plan_tool import trade_plan_tool
    result = trade_plan_tool(
        stock_code="000001",
        market_regime=mock_market_regime,
        technicals=mock_technicals,
        strategy_profile="trend"
    )
    
    print(f"\n状态: {result['status']}")
    print(f"摘要: {result['summary']}")
    print(f"信号: {result['signals']}")
    print(f"\n核心结果:")
    for key, value in result['result'].items():
        if isinstance(value, float):
            print(f"  {key}: {value:.2f}")
        else:
            print(f"  {key}: {value}")
    
    assert result['status'] == 'success', "工具执行失败"
    assert result['result']['action'] == 'buy', "应该建议买入"
    assert 'position_size' in result['result'], "缺少 position_size 字段"
    
    print("\n✅ trade_plan_tool 测试通过")


if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent / "src"))
    
    print("\n" + "="*60)
    print("Phase 2A 工具测试（本地数据）")
    print("="*60)
    
    test_market_regime_tool()
    test_technicals_tool()
    test_trade_plan_tool()
    
    print("\n" + "="*60)
    print("所有测试通过 ✅")
    print("="*60)
