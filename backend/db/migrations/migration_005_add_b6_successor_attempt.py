"""Migration 005: add the immutable B6 successor-attempt binding."""
from __future__ import annotations

import sqlite3


def migrate_add_b6_successor_attempt(conn: sqlite3.Connection) -> None:
    """Add nullable successor columns and their owner-scoped uniqueness index."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(b6_validation_tasks)")
        }
        if "predecessor_task_id" not in columns:
            conn.execute(
                "ALTER TABLE b6_validation_tasks "
                "ADD COLUMN predecessor_task_id TEXT "
                "REFERENCES b6_validation_tasks(task_id)"
            )
        if "predecessor_task_key" not in columns:
            conn.execute(
                "ALTER TABLE b6_validation_tasks ADD COLUMN predecessor_task_key TEXT"
            )
        if "successor_attempt_number" not in columns:
            conn.execute(
                "ALTER TABLE b6_validation_tasks ADD COLUMN successor_attempt_number INTEGER"
            )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_b6_direct_successor_predecessor "
            "ON b6_validation_tasks(predecessor_task_id) "
            "WHERE predecessor_task_id IS NOT NULL"
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
