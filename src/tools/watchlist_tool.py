"""WatchlistTool - 观察池管理

支持：
- add_to_watchlist: 添加到观察池（需人工确认）
- list_watchlist: 列出观察池
- update_watchlist_status: 更新状态
- get_watchlist_item: 获取单条记录
"""

import logging
from datetime import datetime
from typing import Literal, Optional
import json

from src.core.db_init import get_connection

logger = logging.getLogger(__name__)


def add_to_watchlist(
    stock_code: str,
    trade_plan: dict,
    strategy_profile: str = "trend",
    stock_name: Optional[str] = None,
    source_run_id: Optional[str] = None
) -> dict:
    """添加股票到观察池
    
    **注意**: 此工具需要人工确认，不会自动执行。
    
    Args:
        stock_code: 股票代码
        trade_plan: 交易计划（来自 trade_plan_tool）
        strategy_profile: 策略风格
        stock_name: 股票名称（可选）
        source_run_id: 来源 run_id（可选）
    
    Returns:
        统一格式的工具返回
    """
    logger.info(f"WatchlistTool: adding {stock_code} to watchlist")
    
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # 提取交易计划字段
        entry_trigger = f"{trade_plan.get('entry_price_low', 0):.2f}-{trade_plan.get('entry_price_high', 0):.2f}"
        stop_loss = f"{trade_plan.get('stop_loss', 0):.2f}"
        take_profit = f"{trade_plan.get('take_profit', 0):.2f}"
        position_plan = f"{trade_plan.get('position_size', 0):.0%}"
        reason_summary = trade_plan.get('rationale', '')
        
        # 生成失效条件
        invalid_condition = f"跌破止损位 {stop_loss}"
        
        # 插入记录
        cursor.execute("""
            INSERT INTO watchlist (
                stock_code, stock_name, strategy_profile, status,
                entry_trigger, invalid_condition, stop_loss, take_profit,
                position_plan, reason_summary, source_run_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            stock_code, stock_name, strategy_profile, "watching",
            entry_trigger, invalid_condition, stop_loss, take_profit,
            position_plan, reason_summary, source_run_id
        ))
        
        watchlist_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        result = {
            "watchlist_id": watchlist_id,
            "stock_code": stock_code,
            "status": "watching"
        }
        
        summary = f"已将 {stock_code} 加入观察池（ID: {watchlist_id}）"
        
        logger.info(f"WatchlistTool: {summary}")
        
        return {
            "tool": "add_to_watchlist",
            "status": "success",
            "result": result,
            "summary": summary,
            "signals": ["added_to_watchlist"],
            "data_refs": {
                "source": "sqlite",
                "table": "watchlist",
                "row_id": watchlist_id
            },
            "error": None,
            "created_at": datetime.now().isoformat()
        }
    
    except Exception as e:
        logger.error(f"WatchlistTool failed: {e}", exc_info=True)
        return {
            "tool": "add_to_watchlist",
            "status": "error",
            "result": {},
            "summary": f"添加到观察池失败: {str(e)}",
            "signals": [],
            "data_refs": {},
            "error": str(e),
            "created_at": datetime.now().isoformat()
        }


def list_watchlist(
    status: Optional[Literal["watching", "triggered", "invalid", "archived"]] = None,
    limit: int = 20
) -> dict:
    """列出观察池
    
    Args:
        status: 筛选状态（None 表示所有）
        limit: 最大返回数量
    
    Returns:
        统一格式的工具返回
    """
    logger.info(f"WatchlistTool: listing watchlist, status={status}, limit={limit}")
    
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        if status:
            cursor.execute("""
                SELECT * FROM watchlist
                WHERE status = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (status, limit))
        else:
            cursor.execute("""
                SELECT * FROM watchlist
                ORDER BY created_at DESC
                LIMIT ?
            """, (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        # 转换为字典列表
        items = []
        for row in rows:
            items.append({
                "id": row["id"],
                "stock_code": row["stock_code"],
                "stock_name": row["stock_name"],
                "strategy_profile": row["strategy_profile"],
                "status": row["status"],
                "entry_trigger": row["entry_trigger"],
                "stop_loss": row["stop_loss"],
                "take_profit": row["take_profit"],
                "created_at": row["created_at"]
            })
        
        result = {
            "items": items,
            "count": len(items)
        }
        
        summary = f"观察池共 {len(items)} 只股票"
        if status:
            summary += f"（状态: {status}）"
        
        logger.info(f"WatchlistTool: {summary}")
        
        return {
            "tool": "list_watchlist",
            "status": "success",
            "result": result,
            "summary": summary,
            "signals": [],
            "data_refs": {
                "source": "sqlite",
                "table": "watchlist",
                "count": len(items)
            },
            "error": None,
            "created_at": datetime.now().isoformat()
        }
    
    except Exception as e:
        logger.error(f"WatchlistTool list failed: {e}", exc_info=True)
        return {
            "tool": "list_watchlist",
            "status": "error",
            "result": {},
            "summary": f"查询观察池失败: {str(e)}",
            "signals": [],
            "data_refs": {},
            "error": str(e),
            "created_at": datetime.now().isoformat()
        }


def update_watchlist_status(
    watchlist_id: int,
    new_status: Literal["watching", "triggered", "invalid", "archived"]
) -> dict:
    """更新观察池状态
    
    Args:
        watchlist_id: 观察池记录 ID
        new_status: 新状态
    
    Returns:
        统一格式的工具返回
    """
    logger.info(f"WatchlistTool: updating watchlist_id={watchlist_id} to status={new_status}")
    
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # 更新状态
        cursor.execute("""
            UPDATE watchlist
            SET status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (new_status, watchlist_id))
        
        if cursor.rowcount == 0:
            raise ValueError(f"Watchlist ID {watchlist_id} not found")
        
        conn.commit()
        conn.close()
        
        result = {
            "watchlist_id": watchlist_id,
            "new_status": new_status
        }
        
        summary = f"观察池 ID {watchlist_id} 状态已更新为 {new_status}"
        
        logger.info(f"WatchlistTool: {summary}")
        
        return {
            "tool": "update_watchlist_status",
            "status": "success",
            "result": result,
            "summary": summary,
            "signals": [f"status_{new_status}"],
            "data_refs": {
                "source": "sqlite",
                "table": "watchlist",
                "row_id": watchlist_id
            },
            "error": None,
            "created_at": datetime.now().isoformat()
        }
    
    except Exception as e:
        logger.error(f"WatchlistTool update failed: {e}", exc_info=True)
        return {
            "tool": "update_watchlist_status",
            "status": "error",
            "result": {},
            "summary": f"更新观察池状态失败: {str(e)}",
            "signals": [],
            "data_refs": {},
            "error": str(e),
            "created_at": datetime.now().isoformat()
        }


def get_watchlist_item(
    watchlist_id: int
) -> dict:
    """获取观察池单条记录
    
    Args:
        watchlist_id: 观察池记录 ID
    
    Returns:
        统一格式的工具返回
    """
    logger.info(f"WatchlistTool: getting watchlist_id={watchlist_id}")
    
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM watchlist WHERE id = ?
        """, (watchlist_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            raise ValueError(f"Watchlist ID {watchlist_id} not found")
        
        result = {
            "id": row["id"],
            "stock_code": row["stock_code"],
            "stock_name": row["stock_name"],
            "strategy_profile": row["strategy_profile"],
            "status": row["status"],
            "entry_trigger": row["entry_trigger"],
            "invalid_condition": row["invalid_condition"],
            "stop_loss": row["stop_loss"],
            "take_profit": row["take_profit"],
            "position_plan": row["position_plan"],
            "reason_summary": row["reason_summary"],
            "risk_summary": row["risk_summary"],
            "source_run_id": row["source_run_id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"]
        }
        
        summary = f"观察池记录: {row['stock_code']} (ID: {watchlist_id})"
        
        logger.info(f"WatchlistTool: {summary}")
        
        return {
            "tool": "get_watchlist_item",
            "status": "success",
            "result": result,
            "summary": summary,
            "signals": [],
            "data_refs": {
                "source": "sqlite",
                "table": "watchlist",
                "row_id": watchlist_id
            },
            "error": None,
            "created_at": datetime.now().isoformat()
        }
    
    except Exception as e:
        logger.error(f"WatchlistTool get failed: {e}", exc_info=True)
        return {
            "tool": "get_watchlist_item",
            "status": "error",
            "result": {},
            "summary": f"获取观察池记录失败: {str(e)}",
            "signals": [],
            "data_refs": {},
            "error": str(e),
            "created_at": datetime.now().isoformat()
        }
