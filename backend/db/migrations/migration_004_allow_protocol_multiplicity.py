"""Migration 004: allow immutable protocol snapshots to coexist by profile."""
from __future__ import annotations

import sqlite3


def migrate_allow_protocol_multiplicity(conn: sqlite3.Connection) -> None:
    """Replace migration-002's partial unique lookup with a nonunique index."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("DROP INDEX IF EXISTS uq_protocol_b6_profile_per_revision")
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_protocol_b6_profile_per_revision
            ON research_protocol_snapshots(strategy_revision_id, protocol_profile)
            """
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
