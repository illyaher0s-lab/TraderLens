"""FundamentalsTool - 基本面分析工具

包装 DataFetcher + JudgmentEngine，提供统一的基本面分析接口。
"""

import logging
from datetime import datetime
from typing import Literal

from src.core.data_fetcher import DataFetcher
from src.core.judgment_engine import JudgmentEngine

logger = logging.getLogger(__name__)


def analyze_stock_fundamentals(
    stock_code: str,
    strategy_profile: Literal["trend", "growth", "value"] = "trend",
    include_industry_context: bool = True
) -> dict:
    """分析股票基本面
    
    包装 DataFetcher + JudgmentEngine，提供统一的工具接口。
    
    Args:
        stock_code: 股票代码（如 "000001"）
        strategy_profile: 策略类型（trend/growth/value）
        include_industry_context: 是否包含行业对比（默认 True）
    
    Returns:
        统一格式的工具返回
    """
    logger.info(f"FundamentalsTool: analyzing {stock_code}, strategy={strategy_profile}")
    
    try:
        # 1. 拉取财务数据
        fetcher = DataFetcher()
        financial_data = fetcher.get_financial_data(stock_code)
        
        if financial_data is None:
            raise Exception(f"无法获取财务数据: {stock_code}")
        
        # 2. 拉取行业上下文（可选）
        industry_context = None
        if include_industry_context:
            sector_info = fetcher.get_stock_sector(stock_code)
            if sector_info:
                industry_context = fetcher.get_industry_context(sector_info["sector"])
        
        # 3. 调用判断引擎
        engine = JudgmentEngine()
        judgment = engine.evaluate_fundamentals(
            financial_data=financial_data,
            industry_context=industry_context,
            strategy_profile=strategy_profile
        )
        
        # 4. 生成信号
        signals = _generate_signals(judgment, strategy_profile)
        
        # 5. 构建结果
        result = {
            "stock_code": stock_code,
            "strategy_profile": strategy_profile,
            "absolute_score": judgment["absolute_score"],
            "industry_relative_score": judgment["industry_relative_score"],
            "combined_score": judgment["combined_score"],
            "verdict": judgment["verdict"],
            "key_metrics": judgment["key_metrics"],
            "strengths": judgment["strengths"],
            "weaknesses": judgment["weaknesses"]
        }
        
        # 6. 生成摘要
        summary = judgment["summary"]
        
        logger.info(f"FundamentalsTool: {summary}")
        
        return {
            "tool": "analyze_stock_fundamentals",
            "status": "success",
            "result": result,
            "summary": summary,
            "signals": signals,
            "data_refs": {
                "stock_code": stock_code,
                "source": "akshare" if fetcher.mode != "mock" else "mock",
                "is_stale": False,
                "last_updated": datetime.now().isoformat(),
                "has_industry_context": industry_context is not None
            },
            "error": None,
            "created_at": datetime.now().isoformat()
        }
    
    except Exception as e:
        logger.error(f"FundamentalsTool error: {e}", exc_info=True)
        return {
            "tool": "analyze_stock_fundamentals",
            "status": "error",
            "result": {},
            "summary": f"基本面分析失败: {str(e)}",
            "signals": [],
            "data_refs": {
                "stock_code": stock_code,
                "source": "error",
                "is_stale": True,
                "last_updated": datetime.now().isoformat()
            },
            "error": str(e),
            "created_at": datetime.now().isoformat()
        }


def _generate_signals(judgment: dict, strategy_profile: str) -> list[str]:
    """生成信号列表
    
    Args:
        judgment: JudgmentEngine 的评估结果
        strategy_profile: 策略类型
    
    Returns:
        信号列表
    """
    signals = []
    
    # 1. 综合评分信号
    combined_score = judgment["combined_score"]
    verdict = judgment["verdict"]
    
    if verdict == "优秀":
        signals.append("fundamentals_excellent")
    elif verdict == "良好":
        signals.append("fundamentals_good")
    elif verdict == "差":
        signals.append("fundamentals_poor")
    
    # 2. 估值信号
    metrics = judgment["key_metrics"]
    pe = metrics.get("pe")
    pb = metrics.get("pb")
    
    if pe and pe < 15:
        signals.append("valuation_reasonable")
    elif pe and pe > 30:
        signals.append("valuation_expensive")
    
    if pb and pb < 1.5:
        signals.append("pb_undervalued")
    
    # 3. 盈利能力信号
    roe = metrics.get("roe")
    if roe and roe >= 15:
        signals.append("high_roe")
    elif roe and roe < 8:
        signals.append("low_roe")
    
    # 4. 财务健康信号
    debt_ratio = metrics.get("debt_ratio")
    if debt_ratio and debt_ratio < 40:
        signals.append("low_debt")
    elif debt_ratio and debt_ratio > 70:
        signals.append("high_debt")
    
    # 5. 成长性信号（仅 growth 策略）
    if strategy_profile == "growth":
        revenue_growth = metrics.get("revenue_growth")
        profit_growth = metrics.get("profit_growth")
        
        if revenue_growth and revenue_growth >= 20:
            signals.append("high_revenue_growth")
        if profit_growth and profit_growth >= 20:
            signals.append("high_profit_growth")
        
        if revenue_growth and revenue_growth < 0:
            signals.append("negative_revenue_growth")
        if profit_growth and profit_growth < 0:
            signals.append("negative_profit_growth")
    
    # 6. 行业相对强度信号
    industry_relative_score = judgment.get("industry_relative_score")
    if industry_relative_score:
        if industry_relative_score >= 80:
            signals.append("industry_leader")
        elif industry_relative_score < 40:
            signals.append("industry_laggard")
    
    return signals
