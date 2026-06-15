"""
回测工具

职责：
- 包装 BacktestEngine，提供统一的工具接口
- 保存回测结果到 SQLite
- 返回统一格式
"""

import sqlite3
import json
from typing import Literal
from datetime import datetime, timedelta
import logging

from src.core.data_fetcher import DataFetcher
from src.core.backtest_engine import run_backtest

logger = logging.getLogger(__name__)


def backtest_tool(
    stock_code: str,
    strategy_profile: Literal["trend", "growth", "value"],
    period: str = "1y",
    db_path: str = "data/investment_agent.db"
) -> dict:
    """
    策略回测工具
    
    Args:
        stock_code: 股票代码（如 "000001"）
        strategy_profile: 策略类型（trend/growth/value）
        period: 回测周期（"1y", "6m", "3m"）
        db_path: 数据库路径
    
    Returns:
        统一格式的工具返回
    """
    
    try:
        # 1. 解析周期参数
        period_days_map = {
            "3m": 90,
            "6m": 180,
            "1y": 250,
            "2y": 500
        }
        days = period_days_map.get(period, 250)
        
        # 2. 获取历史数据
        logger.info(f"Fetching {days} days of data for {stock_code}")
        
        # 计算起止日期
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        
        fetcher = DataFetcher()
        df, metadata = fetcher.get_stock_daily_kline(
            stock_code=stock_code,
            start_date=start_date,
            end_date=end_date
        )
        
        if df is None or len(df) == 0:
            return {
                "tool": "backtest_tool",
                "status": "error",
                "result": {},
                "summary": f"无法获取 {stock_code} 的历史数据",
                "signals": [],
                "data_refs": {
                    "source": metadata.get("source", "unknown") if metadata else "unknown",
                    "is_stale": True,
                    "last_updated": None
                },
                "error": "数据获取失败",
                "created_at": datetime.now().isoformat()
            }
        
        # 3. 运行回测
        logger.info(f"Running backtest: {stock_code}, {strategy_profile}, {period}")
        backtest_result = run_backtest(df, strategy_profile, initial_capital=100000.0)
        
        # 4. 保存回测结果到数据库
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 递归转换所有 Timestamp 为字符串
        def convert_timestamps(obj):
            """递归转换对象中的所有 Timestamp 为字符串"""
            if isinstance(obj, dict):
                return {k: convert_timestamps(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_timestamps(item) for item in obj]
            elif hasattr(obj, 'isoformat'):  # pd.Timestamp 有 isoformat 方法
                return obj.isoformat()
            else:
                return obj
        
        result_for_db = convert_timestamps(backtest_result)
        
        cursor.execute("""
            INSERT INTO backtest_results (
                stock_code, strategy_profile, start_date, end_date,
                total_return, sharpe_ratio, max_drawdown, win_rate,
                trade_count, result_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            stock_code,
            strategy_profile,
            str(backtest_result['start_date']),
            str(backtest_result['end_date']),
            backtest_result['total_return'],
            backtest_result['sharpe_ratio'],
            backtest_result['max_drawdown'],
            backtest_result['win_rate'],
            backtest_result['trade_count'],
            json.dumps(result_for_db, ensure_ascii=False)
        ))
        
        conn.commit()
        result_id = cursor.lastrowid
        conn.close()
        
        logger.info(f"Backtest result saved: id={result_id}")
        
        # 5. 生成信号
        signals = []
        if backtest_result['total_return'] > 0.1:
            signals.append("positive_return")
        if backtest_result['sharpe_ratio'] > 1.0:
            signals.append("good_sharpe")
        if backtest_result['max_drawdown'] > -0.2:
            signals.append("low_drawdown")
        if backtest_result['win_rate'] > 0.5:
            signals.append("high_winrate")
        
        # 6. 返回结果
        return {
            "tool": "backtest_tool",
            "status": "success",
            "result": {
                "stock_code": stock_code,
                "strategy_profile": strategy_profile,
                "period": period,
                "total_return": backtest_result['total_return'],
                "total_return_pct": backtest_result['total_return_pct'],
                "sharpe_ratio": backtest_result['sharpe_ratio'],
                "max_drawdown": backtest_result['max_drawdown'],
                "max_drawdown_pct": backtest_result['max_drawdown_pct'],
                "win_rate": backtest_result['win_rate'],
                "trade_count": backtest_result['trade_count'],
                "start_date": backtest_result['start_date'],
                "end_date": backtest_result['end_date'],
                "result_id": result_id
            },
            "summary": f"回测完成：收益率 {backtest_result['total_return_pct']:.2f}%，夏普 {backtest_result['sharpe_ratio']:.2f}，最大回撤 {backtest_result['max_drawdown_pct']:.2f}%，胜率 {backtest_result['win_rate']:.1%}，交易 {backtest_result['trade_count']} 次",
            "signals": signals,
            "data_refs": {
                "source": metadata.get("source", "unknown") if metadata else "unknown",
                "is_stale": metadata.get("is_stale", False) if metadata else False,
                "last_updated": metadata.get("last_updated") if metadata else None,
                "db_record_id": result_id
            },
            "error": None,
            "created_at": datetime.now().isoformat()
        }
    
    except Exception as e:
        logger.error(f"Backtest tool failed: {e}", exc_info=True)
        return {
            "tool": "backtest_tool",
            "status": "error",
            "result": {},
            "summary": f"回测失败：{str(e)}",
            "signals": [],
            "data_refs": {
                "source": "unknown",
                "is_stale": True,
                "last_updated": None
            },
            "error": str(e),
            "created_at": datetime.now().isoformat()
        }
