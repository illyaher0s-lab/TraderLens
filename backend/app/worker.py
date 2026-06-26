from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from contextlib import closing
import sqlite3
from pathlib import Path


@dataclass(frozen=True)
class ClaimedTask:
    task_id: str
    task_type: str


def poll_once(db_path: str | Path) -> ClaimedTask | None:
    now = datetime.utcnow().isoformat()

    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT task_id, task_type
            FROM tasks
            WHERE status = 'queued'
            ORDER BY created_at
            LIMIT 1
            """
        ).fetchone()
        if row is None:
            return None

        conn.execute(
            """
            UPDATE tasks
            SET status = 'running', started_at = ?
            WHERE task_id = ?
            """,
            (now, row["task_id"]),
        )
        conn.execute(
            """
            UPDATE tasks
            SET status = 'failed',
                completed_at = ?,
                error_message = ?,
                retry_count = retry_count + 1
            WHERE task_id = ?
            """,
            (
                datetime.utcnow().isoformat(),
                f"no executor registered for task_type={row['task_type']}",
                row["task_id"],
            ),
        )
        conn.commit()
        return ClaimedTask(task_id=row["task_id"], task_type=row["task_type"])
