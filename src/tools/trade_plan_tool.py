"""TradePlanTool - 生成交易计划

基于市场环境和技术面分析，生成具体的交易计划。
"""

import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


def trade_plan_tool(
    stock_code: str,
    market_regime: Optional[dict] = None,
    technicals: Optional[dict] = None,
    strategy_profile: str = "trend"
) -> dict:
    """生成交易计划
    
    基于市场环境和技术面分析，生成包含以下内容的交易计划：
    - 建议仓位
    - 入场价格区间
    - 止损位
    - 止盈位
    - 持仓逻辑
    
    Args:
        stock_code: 股票代码
        market_regime: 市场环境分析结果（来自 market_regime_tool）
        technicals: 技术面分析结果（来自 technicals_tool）
        strategy_profile: 策略风格
    
    Returns:
        统一格式的工具返回
    """
    logger.info(f"TradePlanTool: generating plan for {stock_code}")
    
    try:
        # 1. 检查输入
        if not technicals or not technicals.get("latest_close"):
            raise ValueError("Missing technicals data")
        
        current_price = technicals["latest_close"]
        tech_score = technicals.get("score", 50)
        tech_verdict = technicals.get("verdict", "中性")
        
        # 2. 判断是否适合建仓
        should_enter, reason = _should_enter(market_regime, technicals)
        
        if not should_enter:
            # 不适合建仓
            summary = f"不建议建仓: {reason}"
            return {
                "tool": "trade_plan_tool",
                "status": "success",
                "result": {
                    "action": "hold",
                    "reason": reason,
                    "stock_code": stock_code
                },
                "summary": summary,
                "signals": ["action_hold"],
                "data_refs": {},
                "error": None,
                "created_at": datetime.now().isoformat()
            }
        
        # 3. 计算建议仓位
        position_size = _calculate_position_size(market_regime, technicals, strategy_profile)
        
        # 4. 计算入场价格区间
        entry_low, entry_high = _calculate_entry_range(current_price, technicals)
        
        # 5. 计算止损位
        stop_loss = _calculate_stop_loss(current_price, technicals)
        
        # 6. 计算止盈位
        take_profit = _calculate_take_profit(current_price, technicals, strategy_profile)
        
        # 7. 生成持仓逻辑
        rationale = _generate_rationale(market_regime, technicals)
        
        # 8. 生成摘要和信号
        summary = f"建议建仓 {position_size:.0%}, 入场 {entry_low:.2f}-{entry_high:.2f}, 止损 {stop_loss:.2f}, 止盈 {take_profit:.2f}"
        signals = _generate_signals(position_size, tech_verdict)
        
        result = {
            "action": "buy",
            "position_size": position_size,
            "entry_price_low": entry_low,
            "entry_price_high": entry_high,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "risk_reward_ratio": (take_profit - current_price) / (current_price - stop_loss),
            "rationale": rationale,
            "stock_code": stock_code,
            "current_price": current_price
        }
        
        logger.info(f"TradePlanTool: {summary}")
        
        return {
            "tool": "trade_plan_tool",
            "status": "success",
            "result": result,
            "summary": summary,
            "signals": signals,
            "data_refs": {
                "stock_code": stock_code,
                "tech_score": tech_score
            },
            "error": None,
            "created_at": datetime.now().isoformat()
        }
    
    except Exception as e:
        logger.error(f"TradePlanTool failed for {stock_code}: {e}", exc_info=True)
        return {
            "tool": "trade_plan_tool",
            "status": "error",
            "result": {},
            "summary": f"交易计划生成失败: {str(e)}",
            "signals": [],
            "data_refs": {},
            "error": str(e),
            "created_at": datetime.now().isoformat()
        }


def _should_enter(market_regime: Optional[dict], technicals: dict) -> tuple[bool, str]:
    """判断是否适合建仓
    
    规则：
    - 技术面评分 < 40: 不建议
    - 技术面评分 >= 40: 建议
    - 市场环境为熊市 + 技术面弱势: 不建议
    
    Returns:
        (should_enter, reason)
    """
    tech_score = technicals.get("score", 50)
    tech_verdict = technicals.get("verdict", "中性")
    
    # 技术面太弱
    if tech_score < 40:
        return False, f"技术面偏弱（评分 {tech_score:.0f}），不建议建仓"
    
    # 市场环境 + 技术面双弱
    if market_regime:
        regime = market_regime.get("regime", "sideways")
        if regime == "bear" and tech_verdict in ["偏空", "弱势"]:
            return False, "市场环境偏空且技术面偏弱，不建议建仓"
    
    return True, "技术面符合建仓条件"


def _calculate_position_size(
    market_regime: Optional[dict],
    technicals: dict,
    strategy_profile: str
) -> float:
    """计算建议仓位（0-1）
    
    基础仓位 + 市场环境调整 + 技术面调整
    """
    # 基础仓位（根据策略风格）
    base_position = {
        "trend": 0.15,
        "growth": 0.20,
        "value": 0.25
    }.get(strategy_profile, 0.15)
    
    position = base_position
    
    # 市场环境调整
    if market_regime:
        regime = market_regime.get("regime", "sideways")
        volatility = market_regime.get("volatility", "medium")
        
        if regime == "bull":
            position += 0.05
        elif regime == "bear":
            position -= 0.05
        
        if volatility == "high":
            position -= 0.05
    
    # 技术面调整
    tech_score = technicals.get("score", 50)
    if tech_score >= 75:
        position += 0.05
    elif tech_score < 50:
        position -= 0.05
    
    return max(0.05, min(0.30, position))


def _calculate_entry_range(current_price: float, technicals: dict) -> tuple[float, float]:
    """计算入场价格区间
    
    当前价 ± 2% 作为合理入场区间
    """
    entry_low = current_price * 0.98
    entry_high = current_price * 1.02
    
    return entry_low, entry_high


def _calculate_stop_loss(current_price: float, technicals: dict) -> float:
    """计算止损位
    
    规则：
    - 基础止损：-8%
    - 如果有明确支撑位（MA20），可以适当放宽
    """
    # 简单规则：当前价 * 0.92 (止损 8%)
    stop_loss = current_price * 0.92
    
    return stop_loss


def _calculate_take_profit(
    current_price: float,
    technicals: dict,
    strategy_profile: str
) -> float:
    """计算止盈位
    
    规则：
    - trend 策略：+15%
    - growth 策略：+20%
    - value 策略：+25%
    """
    profit_target = {
        "trend": 1.15,
        "growth": 1.20,
        "value": 1.25
    }.get(strategy_profile, 1.15)
    
    take_profit = current_price * profit_target
    
    return take_profit


def _generate_rationale(market_regime: Optional[dict], technicals: dict) -> str:
    """生成持仓逻辑"""
    parts = []
    
    # 市场环境
    if market_regime:
        regime = market_regime.get("regime", "sideways")
        trend = market_regime.get("trend", "flat")
        parts.append(f"市场环境{regime}，趋势{trend}")
    
    # 技术面
    tech_verdict = technicals.get("verdict", "中性")
    ma_signal = technicals.get("ma_signal", "neutral")
    parts.append(f"技术面{tech_verdict}，均线{ma_signal}")
    
    # 综合判断
    parts.append("符合建仓条件")
    
    return "；".join(parts)


def _generate_signals(position_size: float, tech_verdict: str) -> list[str]:
    """生成离散信号"""
    signals = ["action_buy"]
    
    # 仓位信号
    if position_size >= 0.25:
        signals.append("position_heavy")
    elif position_size >= 0.15:
        signals.append("position_medium")
    else:
        signals.append("position_light")
    
    # 技术面信号
    if tech_verdict in ["强势", "偏多"]:
        signals.append("tech_bullish")
    
    return signals
