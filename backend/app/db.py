from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path


def initialize_database(db_path: str | Path, enable_wal: bool = True) -> None:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with closing(sqlite3.connect(path)) as conn:
        if enable_wal:
            conn.execute("PRAGMA journal_mode=WAL").fetchone()
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                task_type TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'success', 'failed')),
                created_at TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT,
                config BLOB,
                result_path TEXT,
                error_message TEXT,
                retry_count INTEGER NOT NULL DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_tasks_status_created
            ON tasks(status, created_at);

            CREATE TABLE IF NOT EXISTS data_cache_metadata (
                cache_key TEXT PRIMARY KEY,
                file_path TEXT NOT NULL,
                data_type TEXT NOT NULL,
                symbol TEXT,
                start_date TEXT,
                end_date TEXT,
                source TEXT,
                adjust_method TEXT,
                adjust_snapshot_date TEXT,
                quality_status TEXT,
                created_at TEXT,
                ttl_days INTEGER,
                schema_version TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_cache_symbol ON data_cache_metadata(symbol);
            CREATE INDEX IF NOT EXISTS idx_cache_type ON data_cache_metadata(data_type);
            CREATE INDEX IF NOT EXISTS idx_cache_quality ON data_cache_metadata(quality_status);
            """
        )
        if enable_wal:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        conn.commit()
