"""Migration 003: add the immutable B5 binding columns to B6 tasks."""
from __future__ import annotations

import sqlite3


def migrate_add_b5_binding_to_b6_tasks(conn: sqlite3.Connection) -> None:
    """Add nullable v2 B5 columns without rewriting legacy v1 rows."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(b6_validation_tasks)")
        }
        if "b5_bundle_id" not in columns:
            conn.execute(
                "ALTER TABLE b6_validation_tasks ADD COLUMN b5_bundle_id TEXT"
            )
        if "b5_bundle_manifest_sha256" not in columns:
            conn.execute(
                "ALTER TABLE b6_validation_tasks "
                "ADD COLUMN b5_bundle_manifest_sha256 TEXT"
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
