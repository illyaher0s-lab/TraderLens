"""Upgrade durable OOS tables without losing existing snapshots or reservations."""
from __future__ import annotations

import json
import sqlite3


def migrate_oos_evaluation_ledgers_add_hypothesis(conn: sqlite3.Connection) -> None:
    """Upgrade legacy audit ownership and reservation idempotency constraints."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        _migrate_audit_owner_identity(conn)
        _migrate_reservation_idempotency_constraint(conn)
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _table_columns(conn: sqlite3.Connection, table_name: str) -> list[str]:
    return [row[1] for row in conn.execute(f"PRAGMA table_info({table_name})")]


def _has_unique_columns(
    conn: sqlite3.Connection,
    table_name: str,
    expected_columns: list[str],
) -> bool:
    for index in conn.execute(f"PRAGMA index_list({table_name})"):
        if not index[2]:
            continue
        index_columns = [
            row[2]
            for row in conn.execute(f"PRAGMA index_info({index[1]})")
        ]
        if index_columns == expected_columns:
            return True
    return False


def _migrate_audit_owner_identity(conn: sqlite3.Connection) -> None:
    """Rebuild audit snapshots only when their legacy unique key is present."""
    columns = _table_columns(conn, "oos_evaluation_ledgers")
    needs_rebuild = (
        "hypothesis_source_snapshot_id" not in columns
        or _has_unique_columns(conn, "oos_evaluation_ledgers", ["theme_id", "ledger_version"])
    )
    if not needs_rebuild:
        return

    old_rows = conn.execute(
        "SELECT ledger_snapshot_id, theme_id, ledger_version, payload_json, recorded_at "
        "FROM oos_evaluation_ledgers"
    ).fetchall()
    migrated_rows = []
    for ledger_snapshot_id, theme_id, ledger_version, payload_json, recorded_at in old_rows:
        try:
            hypothesis_id = json.loads(payload_json)["hypothesis_source_snapshot_id"]
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError(
                f"Cannot migrate audit snapshot {ledger_snapshot_id}: "
                "missing hypothesis_source_snapshot_id"
            ) from exc
        migrated_rows.append(
            (
                ledger_snapshot_id,
                theme_id,
                hypothesis_id,
                ledger_version,
                payload_json,
                recorded_at,
            )
        )

    conn.execute("DROP TRIGGER IF EXISTS prevent_oos_evaluation_ledgers_update")
    conn.execute("DROP TRIGGER IF EXISTS prevent_oos_evaluation_ledgers_delete")
    conn.execute("ALTER TABLE oos_evaluation_ledgers RENAME TO oos_evaluation_ledgers_old")
    conn.execute(
        """
        CREATE TABLE oos_evaluation_ledgers (
            ledger_snapshot_id TEXT PRIMARY KEY,
            theme_id TEXT NOT NULL,
            hypothesis_source_snapshot_id TEXT NOT NULL,
            ledger_version INTEGER NOT NULL,
            payload_json TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            UNIQUE (theme_id, hypothesis_source_snapshot_id, ledger_version)
        )
        """
    )
    conn.executemany(
        """
        INSERT INTO oos_evaluation_ledgers
        (ledger_snapshot_id, theme_id, hypothesis_source_snapshot_id,
         ledger_version, payload_json, recorded_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        migrated_rows,
    )
    conn.execute("DROP TABLE oos_evaluation_ledgers_old")
    _create_audit_immutable_triggers(conn)


def _migrate_reservation_idempotency_constraint(conn: sqlite3.Connection) -> None:
    """Replace legacy global idempotency uniqueness with owner-scoped uniqueness."""
    columns = _table_columns(conn, "oos_budget_reservations")
    if not columns or not _has_unique_columns(
        conn, "oos_budget_reservations", ["idempotency_key"]
    ):
        return

    required_columns = [
        "reservation_id",
        "theme_id",
        "hypothesis_source_snapshot_id",
        "strategy_config_hash",
        "data_snapshot_hash",
        "gate_criteria_hash",
        "shared_oos_window_id",
        "oos_draw_index",
        "status",
        "reserved_at",
        "execution_started_at",
        "terminal_at",
        "verdict",
        "terminal_reason",
        "idempotency_key",
        "evaluation_id",
        "report_id",
    ]
    missing = set(required_columns) - set(columns)
    if missing:
        raise ValueError(
            "Cannot migrate legacy oos_budget_reservations; missing columns: "
            + ", ".join(sorted(missing))
        )

    rows = conn.execute(
        "SELECT " + ", ".join(required_columns) + " FROM oos_budget_reservations"
    ).fetchall()
    conn.execute("ALTER TABLE oos_budget_reservations RENAME TO oos_budget_reservations_old")
    _create_reservations_table(conn)
    placeholders = ", ".join("?" for _ in required_columns)
    conn.executemany(
        "INSERT INTO oos_budget_reservations ("
        + ", ".join(required_columns)
        + ") VALUES ("
        + placeholders
        + ")",
        rows,
    )
    conn.execute("DROP TABLE oos_budget_reservations_old")
    _create_reservation_indexes(conn)


def _create_reservations_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE oos_budget_reservations (
            reservation_id TEXT PRIMARY KEY,
            theme_id TEXT NOT NULL,
            hypothesis_source_snapshot_id TEXT NOT NULL,
            strategy_config_hash TEXT NOT NULL,
            data_snapshot_hash TEXT NOT NULL,
            gate_criteria_hash TEXT NOT NULL,
            shared_oos_window_id TEXT NOT NULL,
            oos_draw_index INTEGER NOT NULL CHECK (oos_draw_index BETWEEN 1 AND 3),
            status TEXT NOT NULL
                CHECK (status IN ('reserved', 'started', 'completed', 'released', 'failed')),
            reserved_at TEXT NOT NULL,
            execution_started_at TEXT,
            terminal_at TEXT,
            verdict TEXT,
            terminal_reason TEXT,
            idempotency_key TEXT NOT NULL,
            evaluation_id TEXT,
            report_id TEXT,
            FOREIGN KEY (theme_id, hypothesis_source_snapshot_id)
                REFERENCES oos_budget_state(theme_id, hypothesis_source_snapshot_id)
        )
        """
    )


def _create_reservation_indexes(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE UNIQUE INDEX uq_oos_active_draw_per_owner
        ON oos_budget_reservations(theme_id, hypothesis_source_snapshot_id, oos_draw_index)
        WHERE status IN ('reserved', 'started', 'completed', 'failed');

        CREATE UNIQUE INDEX uq_oos_one_active_reservation_per_owner
        ON oos_budget_reservations(theme_id, hypothesis_source_snapshot_id)
        WHERE status IN ('reserved', 'started');

        CREATE UNIQUE INDEX uq_oos_hash_tuple_in_flight_or_terminal
        ON oos_budget_reservations(
            strategy_config_hash, data_snapshot_hash, gate_criteria_hash
        )
        WHERE status IN ('reserved', 'started', 'completed', 'failed');

        CREATE UNIQUE INDEX uq_oos_idempotency_per_owner
        ON oos_budget_reservations(theme_id, hypothesis_source_snapshot_id, idempotency_key);
        """
    )


def _create_audit_immutable_triggers(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TRIGGER prevent_oos_evaluation_ledgers_update
        BEFORE UPDATE ON oos_evaluation_ledgers
        BEGIN
            SELECT RAISE(ABORT, 'oos_evaluation_ledgers is append-only');
        END
        """
    )
    conn.execute(
        """
        CREATE TRIGGER prevent_oos_evaluation_ledgers_delete
        BEFORE DELETE ON oos_evaluation_ledgers
        BEGIN
            SELECT RAISE(ABORT, 'oos_evaluation_ledgers is append-only');
        END
        """
    )
