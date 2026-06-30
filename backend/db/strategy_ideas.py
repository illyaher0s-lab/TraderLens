"""
Strategy Ideas Database Layer

Stores strategy ideas, extractions, mappings, and candidate evaluations.
"""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional
from contextlib import contextmanager

from contracts.strategy_idea import (
    StrategyIdea,
    StrategyIdeaExtraction,
    TemplateMappingResult,
    CandidateTemplateEvaluation,
)


class StrategyIdeasDB:
    """SQLite database for strategy ideas."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _get_conn(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self):
        """Initialize database schema."""
        with self._get_conn() as conn:
            # Strategy ideas
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS strategy_ideas (
                    idea_id TEXT PRIMARY KEY,
                    raw_source_text TEXT NOT NULL,
                    source_channel TEXT NOT NULL,
                    trust_status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

            # Extractions
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS strategy_idea_extractions (
                    extraction_id TEXT PRIMARY KEY,
                    idea_id TEXT NOT NULL,
                    claimed_entry TEXT NOT NULL,
                    claimed_exit TEXT NOT NULL,
                    claimed_edge TEXT,
                    extraction_source TEXT NOT NULL,
                    extracted_at TEXT NOT NULL,
                    FOREIGN KEY (idea_id) REFERENCES strategy_ideas(idea_id)
                )
                """
            )

            # Template mappings
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS template_mapping_results (
                    mapping_id TEXT PRIMARY KEY,
                    idea_id TEXT NOT NULL,
                    path_type TEXT NOT NULL,
                    matched_template_id TEXT,
                    template_version TEXT,
                    mapping_reason TEXT NOT NULL,
                    live_eligible INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (idea_id) REFERENCES strategy_ideas(idea_id)
                )
                """
            )

            # Candidate evaluations
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS candidate_template_evaluations (
                    candidate_id TEXT PRIMARY KEY,
                    idea_id TEXT NOT NULL,
                    is_approved_template INTEGER NOT NULL CHECK(is_approved_template = 0),
                    evaluation_status TEXT NOT NULL,
                    stored_separately_from_live INTEGER NOT NULL CHECK(stored_separately_from_live = 1),
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (idea_id) REFERENCES strategy_ideas(idea_id)
                )
                """
            )

    def save_idea(self, idea: StrategyIdea) -> None:
        """Save strategy idea."""
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO strategy_ideas (idea_id, raw_source_text, source_channel, trust_status, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (idea.idea_id, idea.raw_source_text, idea.source_channel, idea.trust_status.value, idea.created_at.isoformat()),
            )
