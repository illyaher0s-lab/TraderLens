"""Card020's real application routes with isolated durable databases.

Run only through start-card020-validation.bat. The normal Research app and its
configured real LLM client are reused; importing the normal module's unused
default app is redirected to memory before that import can open data/research.db.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


VALIDATION_ROOT = Path(r"D:\TraderLens_validation\card020-20261027").resolve()
RESEARCH_DB_PATH = VALIDATION_ROOT / "research.db"
ISOLATED_LIVE_TRADE_DB_PATH = VALIDATION_ROOT / "live_trade.db"
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _inside_validation_root(path: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(VALIDATION_ROOT):
        raise RuntimeError("Card020 validation database path is outside its isolated directory.")
    return resolved


# Research's module-level default app is created at import time. Make only that
# unused instance in-memory; the active app below gets the persistent isolated DB.
from backend.db import research as research_db_module

_OriginalResearchDB = research_db_module.ResearchDB


class Card020ResearchDB(_OriginalResearchDB):
    def __init__(self, db_path_or_conn="data/research.db", *, db_path=None):
        value = db_path if db_path is not None else db_path_or_conn
        if isinstance(value, sqlite3.Connection):
            super().__init__(value)
            return
        if str(value) == "data/research.db":
            super().__init__(":memory:")
            return
        super().__init__(str(_inside_validation_root(Path(value))))


research_db_module.ResearchDB = Card020ResearchDB

# Keep any live-trade endpoint pointed at the isolated test ledger, and reject
# any constructor path outside this directory before sqlite can open it.
from backend.config import runtime_paths
from backend.db import live_trade as live_trade_module

runtime_paths.get_live_trade_db_path = lambda: str(ISOLATED_LIVE_TRADE_DB_PATH)
_original_live_trade_init = live_trade_module.LiveTradeDB.__init__


def _guarded_live_trade_init(self, db_path):
    _original_live_trade_init(self, _inside_validation_root(Path(db_path)))


live_trade_module.LiveTradeDB.__init__ = _guarded_live_trade_init

# Import only after the database and ledger guards are active.
from backend.api.research import create_research_app
from backend.api.strategy_validations import router as strategy_validations_router

VALIDATION_ROOT.mkdir(parents=True, exist_ok=True)
research_db = Card020ResearchDB(str(RESEARCH_DB_PATH))
research_app = create_research_app(
    db=research_db,
    conversation_mode="real",
    serenity_execution_mode="two_phase",
)

app = FastAPI(title="TraderLens Card020 Isolated Validation API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:3000", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)
app.include_router(strategy_validations_router)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "research_database": str(RESEARCH_DB_PATH),
        "live_trade_database": "isolated_guarded",
        "conversation_mode": "real",
    }


# Keep the catch-all Research mount last so top-level health and validation
# routes remain reachable.
app.mount("/", research_app)
