"""
Runtime health check endpoint.

Provides diagnostic information about the running backend instance.
"""

from fastapi import APIRouter
import os
import sys
from pathlib import Path

router = APIRouter()


@router.get("/api/health/runtime")
def runtime_health():
    """
    Runtime health check.
    
    Returns diagnostic information including:
    - Import status (contracts, backend)
    - Database paths (absolute)
    - Configuration (mode, port, API base URL)
    """
    # Test imports
    contracts_import = False
    backend_import = False
    
    try:
        import contracts
        contracts_import = True
    except ImportError:
        pass
    
    try:
        import backend.app.main
        backend_import = True
    except ImportError:
        pass
    
    # Get paths from config
    try:
        from backend.config.runtime_paths import (
            PROJECT_ROOT,
            get_live_trade_db_path,
            get_research_db_path,
            get_signal_board_db_path,
            API_BASE_URL,
            BACKEND_PORT,
            MODE,
        )
        
        status = "ok" if (contracts_import and backend_import) else "degraded"
        
        return {
            "status": status,
            "cwd": os.getcwd(),
            "project_root": str(PROJECT_ROOT),
            "mode": MODE,
            "backend_port": BACKEND_PORT,
            "api_base_url": API_BASE_URL,
            "contracts_import": contracts_import,
            "backend_import": backend_import,
            "live_trade_db_path": get_live_trade_db_path(),
            "research_db_path": get_research_db_path(),
            "signal_board_db_path": get_signal_board_db_path(),
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "cwd": os.getcwd(),
            "sys_path": sys.path[:5],
            "contracts_import": contracts_import,
            "backend_import": backend_import,
        }
