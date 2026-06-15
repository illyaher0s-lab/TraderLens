"""数据库初始化模块

创建 SQLite 数据库和表结构。
"""

import sqlite3
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def init_database(db_path: str = "data/investment_agent.db") -> None:
    """初始化数据库
    
    创建以下表：
    - watchlist: 观察池
    - research_history: 投研历史（Phase 3）
    - backtest_results: 回测结果（Phase 3）
    
    Args:
        db_path: 数据库文件路径
    """
    # 创建 data 目录
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # === watchlist 表 ===
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS watchlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                stock_code TEXT NOT NULL,
                stock_name TEXT,
                strategy_profile TEXT,
                status TEXT NOT NULL DEFAULT 'watching',
                entry_trigger TEXT,
                invalid_condition TEXT,
                stop_loss TEXT,
                take_profit TEXT,
                position_plan TEXT,
                reason_summary TEXT,
                risk_summary TEXT,
                source_run_id TEXT,
                next_review_date DATE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 索引
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_watchlist_stock_code 
            ON watchlist(stock_code)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_watchlist_status 
            ON watchlist(status)
        """)
        
        # === research_history 表（Phase 3 预留）===
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS research_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL UNIQUE,
                thread_id TEXT,
                goal TEXT,
                stock_code TEXT,
                strategy_profile TEXT,
                status TEXT,
                decision_history TEXT,
                observations TEXT,
                final_result TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP
            )
        """)
        
        # === backtest_results 表（Phase 3 预留）===
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS backtest_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                stock_code TEXT NOT NULL,
                strategy_profile TEXT,
                start_date DATE,
                end_date DATE,
                total_return REAL,
                sharpe_ratio REAL,
                max_drawdown REAL,
                win_rate REAL,
                trade_count INTEGER,
                result_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.commit()
        logger.info(f"Database initialized: {db_path}")
    
    except Exception as e:
        conn.rollback()
        logger.error(f"Failed to initialize database: {e}")
        raise
    
    finally:
        conn.close()


def get_connection(db_path: str = "data/investment_agent.db") -> sqlite3.Connection:
    """获取数据库连接
    
    Args:
        db_path: 数据库文件路径
    
    Returns:
        sqlite3.Connection
    """
    # 确保数据库已初始化
    if not Path(db_path).exists():
        init_database(db_path)
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # 返回字典风格的行
    return conn


if __name__ == "__main__":
    # 初始化数据库
    logging.basicConfig(level=logging.INFO)
    init_database()
    print("Database initialized successfully.")
