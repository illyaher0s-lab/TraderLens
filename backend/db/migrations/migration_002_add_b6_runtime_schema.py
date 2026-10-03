"""
Migration 002: Add B6 Runtime Schema (ADDITIVE ONLY)

Adds B6-specific persistent task capability and protocol profile support.
Data-preserving: uses ALTER TABLE ADD COLUMN (additive), no DROP/RENAME.
"""
from __future__ import annotations

import sqlite3


def migrate_add_b6_runtime_schema(conn: sqlite3.Connection) -> None:
    """
    Add B6 runtime schema: b6_validation_tasks table and protocol_profile field.

    ADDITIVE ONLY: No DROP TABLE, no RENAME, preserves all FKs.

    Changes:
    1. CREATE TABLE b6_validation_tasks (deterministic task_key, typed status, frozen payload)
    2. ALTER research_protocol_snapshots ADD protocol_profile (default 'legacy_b3')
    3. Partial unique constraint on (strategy_revision_id, protocol_profile='b6_coverage_bound')
    4. ALTER oos_budget_reservations ADD task_key, protocol_snapshot_id for recovery

    Data-preserving: existing protocols get default profile, existing reservations nullable extensions.
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        _create_b6_validation_tasks_table(conn)
        _add_protocol_profile_field_additive(conn)
        _extend_reservations_for_task_linkage(conn)
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _create_b6_validation_tasks_table(conn: sqlite3.Connection) -> None:
    """
    Create b6_validation_tasks table (separate from generic app/db.py tasks).

    Key design:
    - task_key: deterministic SHA-256 of (revision, protocol, task_type, contract_version)
    - status: queued/running/blocked/completed/failed
    - typed blocking_reason_code for unavailable conditions
    - frozen payload_json for full task state
    - protocol_snapshot_id FK for recovery
    """
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS b6_validation_tasks (
            task_id TEXT PRIMARY KEY,
            task_key TEXT NOT NULL UNIQUE,
            task_type TEXT NOT NULL CHECK (task_type = 'b6_validation'),
            task_contract_version TEXT NOT NULL DEFAULT 'v1',
            strategy_revision_id TEXT NOT NULL,
            protocol_snapshot_id TEXT NOT NULL,
            status TEXT NOT NULL CHECK (
                status IN ('queued', 'running', 'blocked', 'completed', 'failed')
            ),
            blocking_reason_code TEXT,
            blocking_reason_detail TEXT,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            claimed_at TEXT,
            completed_at TEXT,
            FOREIGN KEY (strategy_revision_id)
                REFERENCES strategy_drafts(strategy_revision_id),
            FOREIGN KEY (protocol_snapshot_id)
                REFERENCES research_protocol_snapshots(protocol_snapshot_id)
        );

        CREATE UNIQUE INDEX IF NOT EXISTS uq_b6_task_key
        ON b6_validation_tasks(task_key);

        CREATE INDEX IF NOT EXISTS idx_b6_tasks_status_created
        ON b6_validation_tasks(status, created_at);
        """
    )


def _add_protocol_profile_field_additive(conn: sqlite3.Connection) -> None:
    """
    Add protocol_profile field to research_protocol_snapshots (ADDITIVE ONLY).

    Strategy: ALTER TABLE ADD COLUMN (SQLite supports this for nullable or default-valued columns)
    - Check if protocol_profile already exists
    - If not, ALTER TABLE ADD COLUMN with DEFAULT 'legacy_b3'
    - Add partial unique index for b6_coverage_bound profile

    NO DROP TABLE, NO RENAME - preserves all inbound FKs.

    Data-preserving: existing rows get default 'legacy_b3' profile.
    """
    # Check if protocol_profile already exists
    columns = [row[1] for row in conn.execute(
        "PRAGMA table_info(research_protocol_snapshots)"
    )]

    if "protocol_profile" in columns:
        # Already migrated, just ensure unique index exists
        _ensure_b6_protocol_unique_index(conn)
        return

    # Add protocol_profile column (additive)
    conn.execute(
        """
        ALTER TABLE research_protocol_snapshots
        ADD COLUMN protocol_profile TEXT NOT NULL DEFAULT 'legacy_b3'
        CHECK (protocol_profile IN ('legacy_b3', 'b6_coverage_bound'))
        """
    )

    # Add partial unique index for b6_coverage_bound
    _ensure_b6_protocol_unique_index(conn)


def _ensure_b6_protocol_unique_index(conn: sqlite3.Connection) -> None:
    """
    Add partial unique index: at-most-one b6_coverage_bound protocol per revision.

    Index: (strategy_revision_id, protocol_profile) WHERE protocol_profile='b6_coverage_bound'
    """
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_protocol_b6_profile_per_revision
        ON research_protocol_snapshots(strategy_revision_id, protocol_profile)
        WHERE protocol_profile = 'b6_coverage_bound'
        """
    )


def _extend_reservations_for_task_linkage(conn: sqlite3.Connection) -> None:
    """
    Add task_key and protocol_snapshot_id to oos_budget_reservations for recovery.

    ADDITIVE: ALTER TABLE ADD COLUMN (nullable, no default required).

    Data-preserving: existing reservations get NULL (pre-B6-runtime reservations).
    """
    # Check if fields already exist
    columns = [row[1] for row in conn.execute(
        "PRAGMA table_info(oos_budget_reservations)"
    )]

    if "task_key" not in columns:
        conn.execute(
            "ALTER TABLE oos_budget_reservations ADD COLUMN task_key TEXT"
        )

    if "protocol_snapshot_id" not in columns:
        conn.execute(
            "ALTER TABLE oos_budget_reservations ADD COLUMN protocol_snapshot_id TEXT"
        )
