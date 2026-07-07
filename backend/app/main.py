from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .db import initialize_database
from backend.api.signal_board import router as signal_board_router, init_signal_board_api
from backend.api.observations import router as observations_router
from backend.api.research import create_research_app
from backend.api.strategy_ideas import router as strategy_ideas_router
from backend.db.research import ResearchDB


app = FastAPI(title="TraderLens API", version="0.1.0")

# CORS middleware for frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Next.js dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(signal_board_router)
app.include_router(observations_router)
app.include_router(strategy_ideas_router)

# Runtime health
from backend.api.runtime_health import router as runtime_health_router
app.include_router(runtime_health_router)


@app.on_event("startup")
def startup() -> None:
    db_path = Path("data") / "signal_board.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Initialize Signal Board API
    init_signal_board_api(str(db_path))
    
    # Initialize main database (if needed)
    initialize_database(Path("data") / "traderlens.sqlite3")
    
    # Initialize Research Module
    research_mode = os.getenv("RESEARCH_CONVERSATION_MODE", "real")
    serenity_mode = os.getenv("SERENITY_EXECUTION_MODE", "")
    
    # Validate RESEARCH_CONVERSATION_MODE (same as create_research_app)
    if research_mode not in ("real", "deterministic"):
        raise RuntimeError(
            f"Invalid RESEARCH_CONVERSATION_MODE='{research_mode}'. "
            "Allowed values: 'real', 'deterministic'"
        )
    
    # Validate SERENITY_EXECUTION_MODE
    if serenity_mode not in ("stub", "two_phase", ""):
        raise RuntimeError(
            f"Invalid SERENITY_EXECUTION_MODE='{serenity_mode}'. "
            "Allowed values: 'stub', 'two_phase'"
        )
    
    # Enforce strict mode compatibility (same as create_research_app)
    if research_mode == "real":
        if serenity_mode == "":
            raise RuntimeError(
                "RESEARCH_CONVERSATION_MODE=real requires SERENITY_EXECUTION_MODE=two_phase. "
                "Set SERENITY_EXECUTION_MODE=two_phase for production."
            )
        if serenity_mode != "two_phase":
            raise RuntimeError(
                f"RESEARCH_CONVERSATION_MODE=real requires SERENITY_EXECUTION_MODE=two_phase, "
                f"but got '{serenity_mode}'. No silent fallback allowed."
            )
    
    if research_mode == "deterministic":
        if serenity_mode == "":
            # Default to stub for deterministic mode
            serenity_mode = "stub"
        if serenity_mode != "stub":
            raise RuntimeError(
                f"RESEARCH_CONVERSATION_MODE=deterministic only allows SERENITY_EXECUTION_MODE='stub', "
                f"but got '{serenity_mode}'. Use RESEARCH_CONVERSATION_MODE=real for two_phase."
            )
    
    if research_mode == "real":
        # Check required credentials for real mode
        llm_key = os.getenv("RESEARCH_LLM_API_KEY")
        tushare_token = os.getenv("TUSHARE_TOKEN")
        
        if not llm_key:
            raise RuntimeError(
                "Research API in real mode requires RESEARCH_LLM_API_KEY environment variable. "
                "Set the variable or use RESEARCH_CONVERSATION_MODE=deterministic for testing."
            )
        
        if not tushare_token:
            raise RuntimeError(
                "Research API in real mode requires TUSHARE_TOKEN environment variable. "
                "Set the variable or use RESEARCH_CONVERSATION_MODE=deterministic for testing."
            )
        
        print(f"Research API starting in REAL mode (LLM + Tushare enabled, Serenity={serenity_mode})")
    else:
        print(f"Research API starting in DETERMINISTIC mode (fake agents for testing, Serenity={serenity_mode})")
    
    # Create Research DB
    research_db_path = Path("data") / "research.db"
    research_db = ResearchDB(str(research_db_path))
    
    # Default stock resolver fixture for deterministic mode
    stock_resolver_fixture = None
    if research_mode == "deterministic":
        stock_resolver_fixture = {
            "603002.SH": {
                "ticker": "603002.SH",
                "company_name": "宏昌电子",
                "exchange": "SSE",
                "list_status": "L",
            },
            "000001.SZ": {
                "ticker": "000001.SZ",
                "company_name": "平安银行",
                "exchange": "SZSE",
                "list_status": "L",
            },
            "600519.SH": {
                "ticker": "600519.SH",
                "company_name": "贵州茅台",
                "exchange": "SSE",
                "list_status": "L",
            },
        }
    
    # Mount Research API
    research_app = create_research_app(
        db=research_db,
        conversation_mode=research_mode,
        serenity_execution_mode=serenity_mode,
        stock_resolver_fixture=stock_resolver_fixture,
    )
    app.mount("/", research_app)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "traderlens"}
