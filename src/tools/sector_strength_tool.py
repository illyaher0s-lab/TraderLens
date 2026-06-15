"""SectorStrengthTool - 分析板块强度

识别股票所属板块，计算板块整体表现，给出相对排名。
"""

import logging
from datetime import datetime
from typing import Literal
import pandas as pd

from src.core.data_fetcher import DataFetcher

logger = logging.getLogger(__name__)


def sector_strength_tool(
    stock_code: str
) -> dict:
    """分析股票所属板块的强度
    
    识别股票所属的行业板块，计算板块整体涨跌幅，给出相对排名。
    
    Args:
        stock_code: 股票代码（如 "000001"）
    
    Returns:
        统一格式的工具返回
    """
    logger.info(f"SectorStrengthTool: analyzing sector strength for {stock_code}")
    
    try:
        # 1. 识别股票所属板块
        fetcher = DataFetcher()
        sector_info = fetcher.get_stock_sector(stock_code)
        
        if sector_info is None:
            raise Exception(f"Cannot identify sector for stock {stock_code}")
        
        sector_name = sector_info.get("sector", "未知板块")
        industry_name = sector_info.get("industry", "未知行业")
        
        # 2. 获取板块内所有股票列表
        sector_stocks = fetcher.get_sector_constituents(sector_name)
        
        if sector_stocks is None or len(sector_stocks) == 0:
            raise Exception(f"No stocks found in sector {sector_name}")
        
        # 3. 计算板块整体表现（近 20 日涨跌幅均值）
        sector_performance = _calculate_sector_performance(fetcher, sector_stocks)
        
        # 4. 计算该股票在板块内的相对排名
        stock_rank = _calculate_stock_rank(fetcher, stock_code, sector_stocks)
        
        # 5. 判断板块强度（强/中/弱）
        strength = _determine_strength(sector_performance["avg_change_pct"])
        
        # 6. 生成摘要和信号
        summary = (
            f"板块: {sector_name}, 行业: {industry_name}, "
            f"强度: {strength}, 近20日涨跌: {sector_performance['avg_change_pct']:.2f}%, "
            f"个股排名: {stock_rank['rank']}/{stock_rank['total']}"
        )
        signals = _generate_signals(strength, stock_rank, sector_performance)
        
        result = {
            "stock_code": stock_code,
            "sector": sector_name,
            "industry": industry_name,
            "strength": strength,
            "sector_performance": sector_performance,
            "stock_rank": stock_rank,
            "top_stocks": sector_performance.get("top_stocks", [])[:5]  # 板块内前5强
        }
        
        logger.info(f"SectorStrengthTool: {summary}")
        
        return {
            "tool": "sector_strength_tool",
            "status": "success",
            "result": result,
            "summary": summary,
            "signals": signals,
            "data_refs": {
                "stock_code": stock_code,
                "sector": sector_name,
                "constituent_count": len(sector_stocks),
                "source": "akshare" if fetcher.mode != "mock" else "mock",
                "is_stale": False,
                "last_updated": datetime.now().isoformat()
            },
            "error": None,
            "created_at": datetime.now().isoformat()
        }
    
    except Exception as e:
        logger.error(f"SectorStrengthTool error: {e}", exc_info=True)
        return {
            "tool": "sector_strength_tool",
            "status": "error",
            "result": {},
            "summary": f"板块分析失败: {str(e)}",
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


def _calculate_sector_performance(fetcher: DataFetcher, sector_stocks: list) -> dict:
    """计算板块整体表现
    
    Args:
        fetcher: DataFetcher 实例
        sector_stocks: 板块内股票列表 [{"code": "000001", "name": "平安银行"}, ...]
    
    Returns:
        {
            "avg_change_pct": float,  # 近20日平均涨跌幅
            "median_change_pct": float,  # 近20日中位数涨跌幅
            "top_stocks": list  # 涨幅前10的股票
        }
    """
    logger.debug(f"Calculating sector performance for {len(sector_stocks)} stocks")
    
    stock_changes = []
    
    for stock in sector_stocks[:50]:  # 限制最多计算 50 只（性能优化）
        stock_code = stock["code"]
        try:
            df, _ = fetcher.get_stock_daily_kline(stock_code, period="1m")
            if df is not None and len(df) >= 20:
                # 计算近 20 日涨跌幅
                change_pct = ((df.iloc[-1]["close"] - df.iloc[-20]["close"]) / df.iloc[-20]["close"]) * 100
                stock_changes.append({
                    "code": stock_code,
                    "name": stock.get("name", stock_code),
                    "change_pct": change_pct
                })
        except Exception as e:
            logger.warning(f"Failed to get data for {stock_code}: {e}")
            continue
    
    if len(stock_changes) == 0:
        # 无有效数据，返回默认值
        return {
            "avg_change_pct": 0.0,
            "median_change_pct": 0.0,
            "top_stocks": []
        }
    
    # 计算均值和中位数
    changes_list = [s["change_pct"] for s in stock_changes]
    avg_change = sum(changes_list) / len(changes_list)
    median_change = sorted(changes_list)[len(changes_list) // 2]
    
    # 找出涨幅前 10
    top_stocks = sorted(stock_changes, key=lambda x: x["change_pct"], reverse=True)[:10]
    
    return {
        "avg_change_pct": avg_change,
        "median_change_pct": median_change,
        "top_stocks": top_stocks
    }


def _calculate_stock_rank(fetcher: DataFetcher, stock_code: str, sector_stocks: list) -> dict:
    """计算股票在板块内的相对排名
    
    Args:
        fetcher: DataFetcher 实例
        stock_code: 目标股票代码
        sector_stocks: 板块内所有股票
    
    Returns:
        {
            "rank": int,  # 排名（1 = 最强）
            "total": int,  # 板块内总股票数
            "percentile": float  # 百分位（0-1）
        }
    """
    logger.debug(f"Calculating rank for {stock_code} in sector")
    
    stock_changes = []
    target_change = None
    
    for stock in sector_stocks[:50]:  # 限制最多 50 只
        code = stock["code"]
        try:
            df, _ = fetcher.get_stock_daily_kline(code, period="1m")
            if df is not None and len(df) >= 20:
                change_pct = ((df.iloc[-1]["close"] - df.iloc[-20]["close"]) / df.iloc[-20]["close"]) * 100
                stock_changes.append({"code": code, "change_pct": change_pct})
                
                if code == stock_code:
                    target_change = change_pct
        except Exception as e:
            logger.warning(f"Failed to get data for {code}: {e}")
            continue
    
    if target_change is None or len(stock_changes) == 0:
        # 无法排名
        return {
            "rank": 0,
            "total": len(sector_stocks),
            "percentile": 0.5
        }
    
    # 按涨跌幅降序排列
    stock_changes.sort(key=lambda x: x["change_pct"], reverse=True)
    
    # 找到目标股票的排名
    rank = next((i + 1 for i, s in enumerate(stock_changes) if s["code"] == stock_code), 0)
    percentile = rank / len(stock_changes)
    
    return {
        "rank": rank,
        "total": len(stock_changes),
        "percentile": percentile
    }


def _determine_strength(avg_change_pct: float) -> Literal["强", "中", "弱"]:
    """判断板块强度
    
    Args:
        avg_change_pct: 板块平均涨跌幅（%）
    
    Returns:
        "强" | "中" | "弱"
    """
    if avg_change_pct >= 5.0:
        return "强"
    elif avg_change_pct >= 0.0:
        return "中"
    else:
        return "弱"


def _generate_signals(
    strength: str,
    stock_rank: dict,
    sector_performance: dict
) -> list[str]:
    """生成信号列表
    
    Args:
        strength: 板块强度
        stock_rank: 股票排名信息
        sector_performance: 板块表现
    
    Returns:
        信号列表
    """
    signals = []
    
    # 板块强度信号
    if strength == "强":
        signals.append("sector_strong")
    elif strength == "弱":
        signals.append("sector_weak")
    
    # 个股排名信号
    if stock_rank["percentile"] <= 0.3:  # 前 30%
        signals.append("stock_top_in_sector")
    elif stock_rank["percentile"] >= 0.7:  # 后 30%
        signals.append("stock_bottom_in_sector")
    
    # 板块整体信号
    if sector_performance["avg_change_pct"] >= 5.0:
        signals.append("sector_bullish")
    elif sector_performance["avg_change_pct"] <= -5.0:
        signals.append("sector_bearish")
    
    return signals
