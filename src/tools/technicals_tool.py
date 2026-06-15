"""TechnicalsTool - 技术面分析

基于个股的技术指标进行分析。
"""

import logging
from datetime import datetime
from typing import Literal
import pandas as pd

from src.core.data_fetcher import DataFetcher

logger = logging.getLogger(__name__)


def technicals_tool(
    stock_code: str,
    strategy_profile: Literal["trend", "growth", "value"] = "trend"
) -> dict:
    """技术面分析
    
    分析个股的技术指标：
    - MA 均线：金叉/死叉
    - MACD: 多头/空头
    - RSI: 超买/超卖
    - 成交量: 放大/萎缩
    - 综合评分
    
    Args:
        stock_code: 股票代码（6 位数字）
        strategy_profile: 策略风格（影响权重）
    
    Returns:
        统一格式的工具返回
    """
    logger.info(f"TechnicalsTool: analyzing {stock_code} with {strategy_profile} strategy")
    
    try:
        # 1. 拉取股票数据（近 1 年，前复权）
        fetcher = DataFetcher()
        df, metadata = fetcher.get_stock_daily_kline(
            stock_code=stock_code,
            adjust="qfq"
        )
        
        if df is None or len(df) < 60:
            raise Exception(f"Insufficient data for {stock_code}: {len(df)} rows")
        
        # 2. 计算技术指标
        df = _calculate_indicators(df)
        
        # 3. 分析信号
        latest = df.iloc[-1]
        ma_signal = _analyze_ma(df)
        macd_signal = _analyze_macd(df)
        rsi_signal = _analyze_rsi(latest)
        volume_signal = _analyze_volume(df)
        
        # 4. 计算综合评分（根据策略风格调整权重）
        score = _calculate_score(
            ma_signal, macd_signal, rsi_signal, volume_signal, strategy_profile
        )
        
        # 5. 判断结论
        verdict = _generate_verdict(score)
        
        # 6. 生成摘要和信号
        summary = f"技术面: {verdict}, 评分: {score:.2f}, MA: {ma_signal}, MACD: {macd_signal}, RSI: {rsi_signal:.0f}, 成交量: {volume_signal}"
        signals = _generate_signals(ma_signal, macd_signal, rsi_signal, volume_signal, verdict)
        
        result = {
            "score": score,
            "verdict": verdict,
            "ma_signal": ma_signal,
            "macd_signal": macd_signal,
            "rsi": float(latest["rsi_14"]),
            "rsi_signal": rsi_signal,
            "volume_signal": volume_signal,
            "stock_code": stock_code,
            "latest_close": float(latest["close"]),
            "latest_date": latest["date"].strftime("%Y-%m-%d")
        }
        
        logger.info(f"TechnicalsTool: {summary}")
        
        return {
            "tool": "technicals_tool",
            "status": "success",
            "result": result,
            "summary": summary,
            "signals": signals,
            "data_refs": {
                "stock_code": stock_code,
                "data_points": len(df),
                "source": metadata.get("source", "unknown"),
                "is_stale": metadata.get("is_stale", False),
                "last_updated": metadata.get("last_updated")
            },
            "error": None,
            "created_at": datetime.now().isoformat()
        }
    
    except Exception as e:
        logger.error(f"TechnicalsTool failed for {stock_code}: {e}", exc_info=True)
        return {
            "tool": "technicals_tool",
            "status": "error",
            "result": {},
            "summary": f"技术面分析失败: {str(e)}",
            "signals": [],
            "data_refs": {},
            "error": str(e),
            "created_at": datetime.now().isoformat()
        }


def _calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """计算技术指标
    
    - MA5, MA20, MA60
    - MACD (12, 26, 9)
    - RSI (14)
    - Volume MA5
    """
    df = df.copy()
    
    # 均线
    df["ma5"] = df["close"].rolling(5).mean()
    df["ma20"] = df["close"].rolling(20).mean()
    df["ma60"] = df["close"].rolling(60).mean()
    
    # MACD
    ema12 = df["close"].ewm(span=12, adjust=False).mean()
    ema26 = df["close"].ewm(span=26, adjust=False).mean()
    df["macd_dif"] = ema12 - ema26
    df["macd_dea"] = df["macd_dif"].ewm(span=9, adjust=False).mean()
    df["macd_histogram"] = (df["macd_dif"] - df["macd_dea"]) * 2
    
    # RSI
    delta = df["close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df["rsi_14"] = 100 - (100 / (1 + rs))
    
    # 成交量均线
    df["volume_ma5"] = df["volume"].rolling(5).mean()
    
    return df


def _analyze_ma(df: pd.DataFrame) -> Literal["golden_cross", "death_cross", "bullish", "bearish", "neutral"]:
    """分析均线信号
    
    规则：
    - 金叉: MA5 上穿 MA20（近 3 日内）
    - 死叉: MA5 下穿 MA20（近 3 日内）
    - 多头排列: MA5 > MA20 > MA60
    - 空头排列: MA5 < MA20 < MA60
    - 中性: 其他
    """
    last_3 = df.tail(3)
    
    if len(last_3) < 3:
        return "neutral"
    
    # 检查金叉/死叉
    ma5_yesterday = last_3.iloc[-2]["ma5"]
    ma20_yesterday = last_3.iloc[-2]["ma20"]
    ma5_today = last_3.iloc[-1]["ma5"]
    ma20_today = last_3.iloc[-1]["ma20"]
    
    if ma5_yesterday <= ma20_yesterday and ma5_today > ma20_today:
        return "golden_cross"
    elif ma5_yesterday >= ma20_yesterday and ma5_today < ma20_today:
        return "death_cross"
    
    # 检查排列
    latest = df.iloc[-1]
    ma5 = latest["ma5"]
    ma20 = latest["ma20"]
    ma60 = latest["ma60"]
    
    if pd.notna(ma5) and pd.notna(ma20) and pd.notna(ma60):
        if ma5 > ma20 > ma60:
            return "bullish"
        elif ma5 < ma20 < ma60:
            return "bearish"
    
    return "neutral"


def _analyze_macd(df: pd.DataFrame) -> Literal["bullish", "bearish", "neutral"]:
    """分析 MACD 信号
    
    规则：
    - 多头: DIF > DEA 且柱状图为正
    - 空头: DIF < DEA 且柱状图为负
    - 中性: 其他
    """
    latest = df.iloc[-1]
    dif = latest["macd_dif"]
    dea = latest["macd_dea"]
    histogram = latest["macd_histogram"]
    
    if pd.notna(dif) and pd.notna(dea) and pd.notna(histogram):
        if dif > dea and histogram > 0:
            return "bullish"
        elif dif < dea and histogram < 0:
            return "bearish"
    
    return "neutral"


def _analyze_rsi(latest: pd.Series) -> float:
    """返回 RSI 值（用于超买超卖判断）"""
    rsi = latest["rsi_14"]
    return float(rsi) if pd.notna(rsi) else 50.0


def _analyze_volume(df: pd.DataFrame) -> Literal["surge", "normal", "shrink"]:
    """分析成交量信号
    
    规则：
    - 放大: 最近成交量 > 5 日均量 * 1.5
    - 萎缩: 最近成交量 < 5 日均量 * 0.7
    - 正常: 其他
    """
    latest = df.iloc[-1]
    volume = latest["volume"]
    volume_ma5 = latest["volume_ma5"]
    
    if pd.notna(volume) and pd.notna(volume_ma5) and volume_ma5 > 0:
        ratio = volume / volume_ma5
        if ratio > 1.5:
            return "surge"
        elif ratio < 0.7:
            return "shrink"
    
    return "normal"


def _calculate_score(
    ma_signal: str,
    macd_signal: str,
    rsi: float,
    volume_signal: str,
    strategy_profile: str
) -> float:
    """计算综合评分（0-100）
    
    根据策略风格调整权重：
    - trend: MA 和 MACD 权重高
    - growth/value: 均衡权重
    """
    score = 50.0  # 基础分
    
    # MA 信号得分
    if ma_signal == "golden_cross":
        score += 20
    elif ma_signal == "bullish":
        score += 10
    elif ma_signal == "death_cross":
        score -= 20
    elif ma_signal == "bearish":
        score -= 10
    
    # MACD 信号得分
    if macd_signal == "bullish":
        score += 10
    elif macd_signal == "bearish":
        score -= 10
    
    # RSI 得分（中性区 40-60 为正常）
    if rsi < 30:  # 超卖
        score += 5
    elif rsi > 70:  # 超买
        score -= 5
    elif 40 <= rsi <= 60:  # 中性
        score += 5
    
    # 成交量得分
    if volume_signal == "surge":
        score += 10
    elif volume_signal == "shrink":
        score -= 5
    
    # 策略风格权重调整
    if strategy_profile == "trend":
        # trend 策略更看重均线和 MACD
        if ma_signal in ["golden_cross", "bullish"]:
            score += 5
        if macd_signal == "bullish":
            score += 5
    
    return max(0.0, min(100.0, score))


def _generate_verdict(score: float) -> Literal["强势", "偏多", "中性", "偏空", "弱势"]:
    """生成技术面结论"""
    if score >= 75:
        return "强势"
    elif score >= 60:
        return "偏多"
    elif score >= 40:
        return "中性"
    elif score >= 25:
        return "偏空"
    else:
        return "弱势"


def _generate_signals(
    ma_signal: str,
    macd_signal: str,
    rsi: float,
    volume_signal: str,
    verdict: str
) -> list[str]:
    """生成离散信号"""
    signals = [
        f"ma_{ma_signal}",
        f"macd_{macd_signal}",
        f"volume_{volume_signal}",
        f"verdict_{verdict}"
    ]
    
    # RSI 信号
    if rsi < 30:
        signals.append("rsi_oversold")
    elif rsi > 70:
        signals.append("rsi_overbought")
    
    # 组合信号
    if ma_signal == "golden_cross" and volume_signal == "surge":
        signals.append("strong_buy_signal")
    elif ma_signal == "death_cross" and volume_signal == "surge":
        signals.append("strong_sell_signal")
    
    return signals
