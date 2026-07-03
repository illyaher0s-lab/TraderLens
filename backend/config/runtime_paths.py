"""
Runtime paths configuration for TraderLens.

Provides canonical paths for databases and data directories.
All code must use these paths instead of hardcoded relative paths.
"""

from pathlib import Path
import os

# Project root: parent of backend/
PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()

# Data directory
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Database paths
LIVE_TRADE_DB_PATH = DATA_DIR / "live_trade.db"
RESEARCH_DB_PATH = DATA_DIR / "research.db"
SIGNAL_BOARD_DB_PATH = DATA_DIR / "signal_board.db"
TRADERLENS_DB_PATH = DATA_DIR / "traderlens.sqlite3"

# API base URL (for frontend)
API_BASE_URL = os.getenv("NEXT_PUBLIC_API_BASE_URL", "http://localhost:8010")

# Backend port
BACKEND_PORT = int(os.getenv("BACKEND_PORT", "8010"))

# Mode
MODE = os.getenv("RESEARCH_CONVERSATION_MODE", "deterministic")

def get_project_root() -> Path:
    """Get project root directory."""
    return PROJECT_ROOT

def get_live_trade_db_path() -> str:
    """Get canonical LiveTradeDB path."""
    return str(LIVE_TRADE_DB_PATH)

def get_research_db_path() -> str:
    """Get canonical ResearchDB path."""
    return str(RESEARCH_DB_PATH)

def get_signal_board_db_path() -> str:
    """Get canonical SignalBoardDB path."""
    return str(SIGNAL_BOARD_DB_PATH)
