"""MarketRegimeTool - 评估市场环境

基于指数（如上证指数）的技术指标判断当前市场环境。
"""

import logging
from datetime import datetime
from typing import Literal
import pandas as pd

from src.core.data_fetcher import DataFetcher

logger = logging.getLogger(__name__)


def market_regime_tool(
    index_code: str = "000001"  # 默认上证指数
) -> dict:
    """评估市场环境
    
    通过上证指数的技术指标判断当前市场处于什么环境：
    - 牛市/熊市/震荡
    - 波动率高/中/低
    - 趋势向上/向下/横盘
    
    Args:
        index_code: 指数代码（默认 "000001" 上证指数）
    
    Returns:
        统一格式的工具返回
    """
    logger.info(f"MarketRegimeTool: analyzing market regime for index {index_code}")
    
    try:
        # 1. 拉取指数数据（近 1 年）
        fetcher = DataFetcher()
        df, metadata = fetcher.get_index_daily_kline(
            index_code=index_code
        )
        
        if df is None or len(df) < 60:
            raise Exception(f"Insufficient data for {index_code}: {len(df)} rows")
        
        # 2. 计算技术指标
        df = _calculate_indicators(df)
        
        # 3. 判断市场环境
        latest = df.iloc[-1]
        regime = _determine_regime(latest)
        volatility = _determine_volatility(df)
        trend = _determine_trend(df)
        
        # 4. 计算置信度
        confidence = _calculate_confidence(df, regime, trend)
        
        # 5. 生成摘要和信号
        summary = f"市场环境: {regime}, 波动率: {volatility}, 趋势: {trend}, 置信度: {confidence:.0%}"
        signals = _generate_signals(regime, volatility, trend)
        
        result = {
            "regime": regime,
            "volatility": volatility,
            "trend": trend,
            "confidence": confidence,
            "index_code": index_code,
            "latest_close": float(latest["close"]),
            "latest_date": latest["date"].strftime("%Y-%m-%d")
        }
        
        logger.info(f"MarketRegimeTool: {summary}")
        
        return {
            "tool": "market_regime_tool",
            "status": "success",
            "result": result,
            "summary": summary,
            "signals": signals,
            "data_refs": {
                "index_code": index_code,
                "data_points": len(df),
                "source": metadata.get("source", "unknown"),
                "is_stale": metadata.get("is_stale", False),
                "last_updated": metadata.get("last_updated")
            },
            "error": None,
            "created_at": datetime.now().isoformat()
        }
    
    except Exception as e:
        logger.error(f"MarketRegimeTool failed: {e}", exc_info=True)
        return {
            "tool": "market_regime_tool",
            "status": "error",
            "result": {},
            "summary": f"市场环境分析失败: {str(e)}",
            "signals": [],
            "data_refs": {},
            "error": str(e),
            "created_at": datetime.now().isoformat()
        }


def _calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """计算技术指标
    
    - MA20, MA60: 均线
    - volatility_20d: 20 日波动率（收益率标准差）
    - rsi_14: 14 日 RSI
    """
    df = df.copy()
    
    # 均线
    df["ma20"] = df["close"].rolling(20).mean()
    df["ma60"] = df["close"].rolling(60).mean()
    
    # 20 日波动率（收益率标准差 * sqrt(252) 年化）
    df["daily_return"] = df["close"].pct_change()
    df["volatility_20d"] = df["daily_return"].rolling(20).std() * (252 ** 0.5)
    
    # RSI
    delta = df["close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df["rsi_14"] = 100 - (100 / (1 + rs))
    
    return df


def _determine_regime(latest: pd.Series) -> Literal["bull", "bear", "sideways"]:
    """判断市场状态（牛市/熊市/震荡）
    
    规则：
    - 牛市：价格 > MA60，MA20 > MA60，RSI > 50
    - 熊市：价格 < MA60，MA20 < MA60，RSI < 50
    - 震荡：其他情况
    """
    close = latest["close"]
    ma20 = latest["ma20"]
    ma60 = latest["ma60"]
    rsi = latest["rsi_14"]
    
    if close > ma60 and ma20 > ma60 and rsi > 50:
        return "bull"
    elif close < ma60 and ma20 < ma60 and rsi < 50:
        return "bear"
    else:
        return "sideways"


def _determine_volatility(df: pd.DataFrame) -> Literal["low", "medium", "high"]:
    """判断波动率水平
    
    规则：
    - 低波动：< 15%
    - 中波动：15%-25%
    - 高波动：> 25%
    """
    latest_vol = df.iloc[-1]["volatility_20d"]
    
    if pd.isna(latest_vol):
        return "medium"
    
    if latest_vol < 0.15:
        return "low"
    elif latest_vol < 0.25:
        return "medium"
    else:
        return "high"


def _determine_trend(df: pd.DataFrame) -> Literal["up", "down", "flat"]:
    """判断趋势方向
    
    规则：
    - 向上：MA20 斜率 > 0 且 近 20 日涨幅 > 5%
    - 向下：MA20 斜率 < 0 且 近 20 日跌幅 > 5%
    - 横盘：其他情况
    """
    latest_20 = df.tail(20)
    
    if len(latest_20) < 20:
        return "flat"
    
    ma20_change = (latest_20.iloc[-1]["ma20"] - latest_20.iloc[0]["ma20"]) / latest_20.iloc[0]["ma20"]
    close_change = (latest_20.iloc[-1]["close"] - latest_20.iloc[0]["close"]) / latest_20.iloc[0]["close"]
    
    if ma20_change > 0 and close_change > 0.05:
        return "up"
    elif ma20_change < 0 and close_change < -0.05:
        return "down"
    else:
        return "flat"


def _calculate_confidence(
    df: pd.DataFrame,
    regime: str,
    trend: str
) -> float:
    """计算置信度
    
    规则：
    - 基础置信度：0.5
    - regime 和 trend 一致（bull+up, bear+down）：+0.3
    - 近 5 日趋势稳定（涨跌方向一致）：+0.2
    """
    confidence = 0.5
    
    # regime 和 trend 一致
    if (regime == "bull" and trend == "up") or (regime == "bear" and trend == "down"):
        confidence += 0.3
    
    # 近 5 日趋势稳定
    last_5_returns = df.tail(5)["daily_return"]
    if len(last_5_returns) == 5:
        positive_count = (last_5_returns > 0).sum()
        if positive_count >= 4 or positive_count <= 1:  # 4 涨 1 跌 或 1 涨 4 跌
            confidence += 0.2
    
    return min(confidence, 1.0)


def _generate_signals(
    regime: str,
    volatility: str,
    trend: str
) -> list[str]:
    """生成离散信号
    
    供后续工具使用（如观察池失效条件）
    """
    signals = [
        f"regime_{regime}",
        f"volatility_{volatility}",
        f"trend_{trend}"
    ]
    
    # 组合信号
    if regime == "bull" and trend == "up":
        signals.append("strong_bull")
    elif regime == "bear" and trend == "down":
        signals.append("strong_bear")
    
    if volatility == "high":
        signals.append("high_risk")
    
    return signals
