"""OOS Budget Ledger - DB-backed durable state."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from datetime import datetime
from typing import TYPE_CHECKING

from backend.services.b5_oos_types import OOSReservation

if TYPE_CHECKING:
    from backend.db.strategy import StrategyDB


class OOSBudgetLedger:
    """DB-backed OOS budget ledger with a three-draw limit."""

    def __init__(self, db: StrategyDB):
        self.db = db

    def get_ledger_state(
        self,
        theme_id: str,
        hypothesis_source_snapshot_id: str,
    ) -> dict:
        """Return the current owner state without creating it."""
        state = self.db.get_oos_budget_state(
            theme_id,
            hypothesis_source_snapshot_id,
        )
        if state is None:
            return {
                "completed_draw_count": 0,
                "next_oos_draw_index": 1,
                "budget_status": "available",
                "active_reservation_id": None,
            }
        return {
            "completed_draw_count": state["consumed_draw_count"],
            "next_oos_draw_index": state["next_oos_draw_index"],
            "budget_status": state["budget_status"],
            "active_reservation_id": state.get("active_reservation_id"),
        }

    def check_cache(
        self,
        strategy_config_hash: str,
        data_snapshot_hash: str,
        gate_criteria_hash: str,
    ) -> str | None:
        """Return the terminal reservation for a hash tuple, if any."""
        row = self.db.conn.execute(
            """
            SELECT reservation_id FROM oos_budget_reservations
            WHERE strategy_config_hash = ?
              AND data_snapshot_hash = ?
              AND gate_criteria_hash = ?
              AND status IN ('completed', 'failed')
            LIMIT 1
            """,
            (strategy_config_hash, data_snapshot_hash, gate_criteria_hash),
        ).fetchone()
        return row[0] if row else None

    def reserve_oos_draw(
        self,
        theme_id: str,
        hypothesis_source_snapshot_id: str,
        strategy_config_hash: str,
        data_snapshot_hash: str,
        gate_criteria_hash: str,
        shared_oos_window_id: str,
        idempotency_key: str,
        *,
        task_key: str | None = None,
        protocol_snapshot_id: str | None = None,
    ) -> OOSReservation:
        """Reserve a draw atomically; repeated owner/key returns the same row."""
        # ponytail: both or neither, idempotency_key==task_key
        if (task_key is None) != (protocol_snapshot_id is None):
            raise ValueError("task_key and protocol_snapshot_id must both exist or both None")
        if task_key is not None and idempotency_key != task_key:
            raise ValueError(f"B6 binding: idempotency_key must equal task_key, got {idempotency_key}!={task_key}")
        return self._transact_with_retry(
            lambda: self._reserve_tx(
                theme_id,
                hypothesis_source_snapshot_id,
                strategy_config_hash,
                data_snapshot_hash,
                gate_criteria_hash,
                shared_oos_window_id,
                idempotency_key,
                task_key,
                protocol_snapshot_id,
            )
        )

    def _reserve_tx(
        self,
        theme_id: str,
        hypothesis_source_snapshot_id: str,
        strategy_config_hash: str,
        data_snapshot_hash: str,
        gate_criteria_hash: str,
        shared_oos_window_id: str,
        idempotency_key: str,
        task_key: str | None,
        protocol_snapshot_id: str | None,
    ) -> OOSReservation:
        self.db.conn.execute("BEGIN IMMEDIATE")
        try:
            existing = self.db.conn.execute(
                """
                SELECT reservation_id, status, strategy_config_hash,
                       data_snapshot_hash, gate_criteria_hash,
                       oos_draw_index, reserved_at, task_key, protocol_snapshot_id
                FROM oos_budget_reservations
                WHERE theme_id = ?
                  AND hypothesis_source_snapshot_id = ?
                  AND idempotency_key = ?
                """,
                (theme_id, hypothesis_source_snapshot_id, idempotency_key),
            ).fetchone()
            if existing:
                # ponytail: verify binding if provided
                if task_key is not None and (existing[7] != task_key or existing[8] != protocol_snapshot_id):
                    self.db.conn.rollback()
                    raise RuntimeError(f"idempotency conflict: {idempotency_key} bound to task={existing[7]}/protocol={existing[8]}")
                self.db.conn.rollback()
                return OOSReservation(
                    reservation_id=existing[0],
                    theme_id=theme_id,
                    hypothesis_source_snapshot_id=hypothesis_source_snapshot_id,
                    strategy_config_hash=existing[2],
                    data_snapshot_hash=existing[3],
                    gate_criteria_hash=existing[4],
                    oos_draw_index=existing[5],
                    status=existing[1],
                    reserved_at=datetime.fromisoformat(existing[6]),
                )

            hash_row = self.db.conn.execute(
                """
                SELECT reservation_id FROM oos_budget_reservations
                WHERE strategy_config_hash = ?
                  AND data_snapshot_hash = ?
                  AND gate_criteria_hash = ?
                  AND status IN ('reserved', 'started', 'completed', 'failed')
                LIMIT 1
                """,
                (strategy_config_hash, data_snapshot_hash, gate_criteria_hash),
            ).fetchone()
            if hash_row:
                self.db.conn.rollback()
                raise ValueError(
                    f"Hash tuple already used in reservation {hash_row[0]}"
                )

            window_row = self.db.conn.execute(
                """
                SELECT theme_id FROM oos_budget_reservations
                WHERE shared_oos_window_id = ?
                  AND data_snapshot_hash = ?
                  AND status IN ('reserved', 'started', 'completed', 'failed')
                LIMIT 1
                """,
                (shared_oos_window_id, data_snapshot_hash),
            ).fetchone()
            if window_row and window_row[0] != theme_id:
                self.db.conn.rollback()
                raise ValueError(
                    "Cross-theme OOS reuse rejected: "
                    f"window '{shared_oos_window_id}' already used by "
                    f"theme '{window_row[0]}'"
                )

            state = self.db.get_oos_budget_state(
                theme_id,
                hypothesis_source_snapshot_id,
            )
            if state is None:
                self.db.conn.execute(
                    """
                    INSERT INTO oos_budget_state
                    (theme_id, hypothesis_source_snapshot_id,
                     consumed_draw_count, next_oos_draw_index,
                     budget_status, state_version, updated_at)
                    VALUES (?, ?, 0, 1, 'available', 1, ?)
                    """,
                    (
                        theme_id,
                        hypothesis_source_snapshot_id,
                        datetime.now().isoformat(),
                    ),
                )
                state = {
                    "consumed_draw_count": 0,
                    "next_oos_draw_index": 1,
                    "budget_status": "available",
                    "state_version": 1,
                }

            if state["consumed_draw_count"] >= 3:
                self.db.conn.rollback()
                raise ValueError(
                    f"OOS budget exhausted for theme '{theme_id}' (max 3 draws)"
                )

            active_row = self.db.conn.execute(
                """
                SELECT reservation_id FROM oos_budget_reservations
                WHERE theme_id = ?
                  AND hypothesis_source_snapshot_id = ?
                  AND status IN ('reserved', 'started')
                LIMIT 1
                """,
                (theme_id, hypothesis_source_snapshot_id),
            ).fetchone()
            if active_row:
                self.db.conn.rollback()
                raise ValueError(
                    f"Active reservation blocks new draw: {active_row[0]}"
                )

            oos_draw_index = state["next_oos_draw_index"]
            reservation_id = self._generate_reservation_id(
                theme_id,
                oos_draw_index,
            )
            reserved_at = datetime.now()
            self.db.conn.execute(
                """
                INSERT INTO oos_budget_reservations
                (reservation_id, theme_id, hypothesis_source_snapshot_id,
                 strategy_config_hash, data_snapshot_hash, gate_criteria_hash,
                 shared_oos_window_id, oos_draw_index, status, reserved_at,
                 idempotency_key, task_key, protocol_snapshot_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'reserved', ?, ?, ?, ?)
                """,
                (
                    reservation_id,
                    theme_id,
                    hypothesis_source_snapshot_id,
                    strategy_config_hash,
                    data_snapshot_hash,
                    gate_criteria_hash,
                    shared_oos_window_id,
                    oos_draw_index,
                    reserved_at.isoformat(),
                    idempotency_key,
                    task_key,
                    protocol_snapshot_id,
                ),
            )
            cursor = self.db.conn.execute(
                """
                UPDATE oos_budget_state
                SET active_reservation_id = ?,
                    state_version = state_version + 1,
                    updated_at = ?
                WHERE theme_id = ?
                  AND hypothesis_source_snapshot_id = ?
                  AND state_version = ?
                """,
                (
                    reservation_id,
                    datetime.now().isoformat(),
                    theme_id,
                    hypothesis_source_snapshot_id,
                    state["state_version"],
                ),
            )
            if cursor.rowcount != 1:
                self.db.conn.rollback()
                raise RuntimeError(
                    f"State version mismatch for "
                    f"{theme_id}/{hypothesis_source_snapshot_id}"
                )

            self._write_audit_tx(
                theme_id,
                hypothesis_source_snapshot_id,
                state["consumed_draw_count"],
                oos_draw_index,
                "reserved",
            )
            self.db.conn.commit()
            return OOSReservation(
                reservation_id=reservation_id,
                theme_id=theme_id,
                hypothesis_source_snapshot_id=hypothesis_source_snapshot_id,
                strategy_config_hash=strategy_config_hash,
                data_snapshot_hash=data_snapshot_hash,
                gate_criteria_hash=gate_criteria_hash,
                oos_draw_index=oos_draw_index,
                status="reserved",
                reserved_at=reserved_at,
            )
        except Exception:
            self.db.conn.rollback()
            raise

    def start_execution(self, reservation_id: str) -> None:
        """Move a reserved draw to started."""
        self._transact_with_retry(
            lambda: self._start_execution_tx(reservation_id)
        )

    def _start_execution_tx(self, reservation_id: str) -> None:
        self.db.conn.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.conn.execute(
                """
                SELECT status, theme_id, hypothesis_source_snapshot_id
                FROM oos_budget_reservations
                WHERE reservation_id = ?
                """,
                (reservation_id,),
            ).fetchone()
            if not row:
                self.db.conn.rollback()
                raise ValueError(f"Reservation {reservation_id} not found")

            status, theme_id, hypo_id = row
            if status != "reserved":
                self.db.conn.rollback()
                raise ValueError(
                    f"Cannot start: reservation {reservation_id} "
                    f"is {status}, not reserved"
                )

            cursor = self.db.conn.execute(
                """
                UPDATE oos_budget_reservations
                SET status = 'started', execution_started_at = ?
                WHERE reservation_id = ? AND status = 'reserved'
                """,
                (datetime.now().isoformat(), reservation_id),
            )
            if cursor.rowcount != 1:
                self.db.conn.rollback()
                raise RuntimeError(f"Failed to start {reservation_id}")

            state = self.db.get_oos_budget_state(theme_id, hypo_id)
            self._write_audit_tx(
                theme_id,
                hypo_id,
                state["consumed_draw_count"],
                self._get_draw_index(reservation_id),
                "started",
            )
            self.db.conn.commit()
        except Exception:
            self.db.conn.rollback()
            raise

    def complete_reservation(
        self,
        reservation_id: str,
        verdict: str,
        evaluation_id: str | None = None,
        report_id: str | None = None,
    ) -> None:
        """Complete a started draw and consume the budget once."""
        self._transact_with_retry(
            lambda: self._complete_tx(
                reservation_id,
                verdict,
                evaluation_id,
                report_id,
            )
        )

    def _complete_tx(
        self,
        reservation_id: str,
        verdict: str,
        evaluation_id: str | None,
        report_id: str | None,
    ) -> None:
        self.db.conn.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.conn.execute(
                """
                SELECT status, verdict, evaluation_id, report_id,
                       theme_id, hypothesis_source_snapshot_id, oos_draw_index
                FROM oos_budget_reservations
                WHERE reservation_id = ?
                """,
                (reservation_id,),
            ).fetchone()
            if not row:
                self.db.conn.rollback()
                raise ValueError(f"Reservation {reservation_id} not found")

            (
                status,
                existing_verdict,
                existing_eval,
                existing_report,
                theme_id,
                hypo_id,
                draw_idx,
            ) = row
            if status == "completed":
                same_eval = (
                    evaluation_id
                    and existing_eval == evaluation_id
                    and existing_verdict == verdict
                )
                same_report = (
                    report_id
                    and existing_report == report_id
                    and existing_verdict == verdict
                )
                if same_eval or same_report:
                    self.db.conn.rollback()
                    return
                self.db.conn.rollback()
                raise ValueError(
                    f"Reservation {reservation_id} already completed with "
                    "different evaluation_id/report_id or verdict"
                )
            if status != "started":
                self.db.conn.rollback()
                raise ValueError(
                    f"Cannot complete: reservation {reservation_id} "
                    f"is {status}, not started"
                )

            cursor = self.db.conn.execute(
                """
                UPDATE oos_budget_reservations
                SET status = 'completed', verdict = ?, terminal_at = ?,
                    evaluation_id = ?, report_id = ?
                WHERE reservation_id = ? AND status = 'started'
                """,
                (
                    verdict,
                    datetime.now().isoformat(),
                    evaluation_id,
                    report_id,
                    reservation_id,
                ),
            )
            if cursor.rowcount != 1:
                self.db.conn.rollback()
                raise RuntimeError(f"Failed to complete {reservation_id}")

            state = self.db.get_oos_budget_state(theme_id, hypo_id)
            new_consumed = state["consumed_draw_count"] + 1
            new_next_idx = state["next_oos_draw_index"] + 1
            new_status = (
                "oos_budget_exhausted" if new_consumed >= 3 else "available"
            )
            cursor = self.db.conn.execute(
                """
                UPDATE oos_budget_state
                SET consumed_draw_count = ?, next_oos_draw_index = ?,
                    budget_status = ?, active_reservation_id = NULL,
                    state_version = state_version + 1, updated_at = ?
                WHERE theme_id = ?
                  AND hypothesis_source_snapshot_id = ?
                  AND state_version = ?
                """,
                (
                    new_consumed,
                    new_next_idx,
                    new_status,
                    datetime.now().isoformat(),
                    theme_id,
                    hypo_id,
                    state["state_version"],
                ),
            )
            if cursor.rowcount != 1:
                self.db.conn.rollback()
                raise RuntimeError(f"State version mismatch for {theme_id}/{hypo_id}")

            self._write_audit_tx(
                theme_id,
                hypo_id,
                new_consumed,
                draw_idx,
                "completed",
            )
            self.db.conn.commit()
        except Exception:
            self.db.conn.rollback()
            raise

    def fail_after_start(self, reservation_id: str, reason: str) -> None:
        """Fail a started draw and consume the budget once."""
        self._transact_with_retry(
            lambda: self._fail_after_start_tx(reservation_id, reason)
        )

    def _fail_after_start_tx(self, reservation_id: str, reason: str) -> None:
        self.db.conn.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.conn.execute(
                """
                SELECT status, terminal_reason, theme_id,
                       hypothesis_source_snapshot_id, oos_draw_index
                FROM oos_budget_reservations
                WHERE reservation_id = ?
                """,
                (reservation_id,),
            ).fetchone()
            if not row:
                self.db.conn.rollback()
                raise ValueError(f"Reservation {reservation_id} not found")

            status, existing_reason, theme_id, hypo_id, draw_idx = row
            if status == "failed":
                self.db.conn.rollback()
                return
            if status != "started":
                self.db.conn.rollback()
                raise ValueError(
                    f"Cannot fail: reservation {reservation_id} "
                    f"is {status}, not started"
                )

            cursor = self.db.conn.execute(
                """
                UPDATE oos_budget_reservations
                SET status = 'failed', terminal_at = ?, terminal_reason = ?
                WHERE reservation_id = ? AND status = 'started'
                """,
                (datetime.now().isoformat(), reason, reservation_id),
            )
            if cursor.rowcount != 1:
                self.db.conn.rollback()
                raise RuntimeError(f"Failed to fail {reservation_id}")

            state = self.db.get_oos_budget_state(theme_id, hypo_id)
            new_consumed = state["consumed_draw_count"] + 1
            new_next_idx = state["next_oos_draw_index"] + 1
            new_status = (
                "oos_budget_exhausted" if new_consumed >= 3 else "available"
            )
            cursor = self.db.conn.execute(
                """
                UPDATE oos_budget_state
                SET consumed_draw_count = ?, next_oos_draw_index = ?,
                    budget_status = ?, active_reservation_id = NULL,
                    state_version = state_version + 1, updated_at = ?
                WHERE theme_id = ?
                  AND hypothesis_source_snapshot_id = ?
                  AND state_version = ?
                """,
                (
                    new_consumed,
                    new_next_idx,
                    new_status,
                    datetime.now().isoformat(),
                    theme_id,
                    hypo_id,
                    state["state_version"],
                ),
            )
            if cursor.rowcount != 1:
                self.db.conn.rollback()
                raise RuntimeError(f"State version mismatch for {theme_id}/{hypo_id}")

            self._write_audit_tx(
                theme_id,
                hypo_id,
                new_consumed,
                draw_idx,
                "failed",
            )
            self.db.conn.commit()
        except Exception:
            self.db.conn.rollback()
            raise

    def release_pre_execution(self, reservation_id: str, reason: str) -> None:
        """Release a reserved draw without consuming budget."""
        self._transact_with_retry(
            lambda: self._release_pre_execution_tx(reservation_id, reason)
        )

    def _release_pre_execution_tx(
        self,
        reservation_id: str,
        reason: str,
    ) -> None:
        self.db.conn.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.conn.execute(
                """
                SELECT status, execution_started_at, theme_id,
                       hypothesis_source_snapshot_id, oos_draw_index
                FROM oos_budget_reservations
                WHERE reservation_id = ?
                """,
                (reservation_id,),
            ).fetchone()
            if not row:
                self.db.conn.rollback()
                raise ValueError(f"Reservation {reservation_id} not found")

            status, started_at, theme_id, hypo_id, draw_idx = row
            if status == "released":
                self.db.conn.rollback()
                return
            if started_at is not None:
                self.db.conn.rollback()
                raise ValueError("Cannot release after execution started")
            if status != "reserved":
                self.db.conn.rollback()
                raise ValueError(
                    f"Cannot release: reservation {reservation_id} "
                    f"is {status}, not reserved"
                )

            cursor = self.db.conn.execute(
                """
                UPDATE oos_budget_reservations
                SET status = 'released', terminal_at = ?, terminal_reason = ?
                WHERE reservation_id = ? AND status = 'reserved'
                """,
                (datetime.now().isoformat(), reason, reservation_id),
            )
            if cursor.rowcount != 1:
                self.db.conn.rollback()
                raise RuntimeError(f"Failed to release {reservation_id}")

            state = self.db.get_oos_budget_state(theme_id, hypo_id)
            cursor = self.db.conn.execute(
                """
                UPDATE oos_budget_state
                SET active_reservation_id = NULL,
                    state_version = state_version + 1, updated_at = ?
                WHERE theme_id = ?
                  AND hypothesis_source_snapshot_id = ?
                  AND state_version = ?
                """,
                (
                    datetime.now().isoformat(),
                    theme_id,
                    hypo_id,
                    state["state_version"],
                ),
            )
            if cursor.rowcount != 1:
                self.db.conn.rollback()
                raise RuntimeError(f"State version mismatch for {theme_id}/{hypo_id}")

            self._write_audit_tx(
                theme_id,
                hypo_id,
                state["consumed_draw_count"],
                draw_idx,
                "released",
            )
            self.db.conn.commit()
        except Exception:
            self.db.conn.rollback()
            raise

    def release_reservation(self, reservation_id: str, reason: str) -> None:
        """Backward-compatible wrapper for pre-execution release."""
        self.release_pre_execution(reservation_id, reason)

    def fail_reservation_within_tx(
        self,
        conn,
        reservation_id: str,
        reason: str,
    ) -> None:
        """Fail a reservation using only the caller-owned connection."""
        row = conn.execute(
            """
            SELECT status, terminal_reason, theme_id,
                   hypothesis_source_snapshot_id, oos_draw_index
            FROM oos_budget_reservations
            WHERE reservation_id = ?
            """,
            (reservation_id,),
        ).fetchone()
        if not row:
            raise ValueError(f"Reservation {reservation_id} not found")

        status, existing_reason, theme_id, hypo_id, draw_idx = row
        if status == "failed" and existing_reason == reason:
            return
        if status not in ("reserved", "started"):
            raise ValueError(f"Cannot fail reservation with status {status}")

        conn.execute(
            """
            UPDATE oos_budget_reservations
            SET status = 'failed', terminal_at = ?, terminal_reason = ?
            WHERE reservation_id = ?
            """,
            (datetime.now().isoformat(), reason, reservation_id),
        )
        if status != "started":
            return

        state_row = conn.execute(
            """
            SELECT consumed_draw_count, next_oos_draw_index, state_version
            FROM oos_budget_state
            WHERE theme_id = ? AND hypothesis_source_snapshot_id = ?
            """,
            (theme_id, hypo_id),
        ).fetchone()
        consumed, next_idx, version = state_row
        new_consumed = consumed + 1
        new_next_idx = next_idx + 1
        new_status = (
            "oos_budget_exhausted" if new_consumed >= 3 else "available"
        )
        cursor = conn.execute(
            """
            UPDATE oos_budget_state
            SET consumed_draw_count = ?, next_oos_draw_index = ?,
                budget_status = ?, active_reservation_id = NULL,
                state_version = state_version + 1, updated_at = ?
            WHERE theme_id = ?
              AND hypothesis_source_snapshot_id = ?
              AND state_version = ?
            """,
            (
                new_consumed,
                new_next_idx,
                new_status,
                datetime.now().isoformat(),
                theme_id,
                hypo_id,
                version,
            ),
        )
        if cursor.rowcount != 1:
            raise RuntimeError(f"State version mismatch for {theme_id}/{hypo_id}")
        self._insert_audit_within_tx(
            conn,
            theme_id,
            hypo_id,
            new_consumed,
            draw_idx,
            "failed",
        )

    def complete_reservation_within_tx(
        self,
        conn,
        reservation_id: str,
        verdict: str,
        report_id: str,
    ) -> None:
        """Complete a reservation using only the caller-owned connection."""
        row = conn.execute(
            """
            SELECT status, theme_id, hypothesis_source_snapshot_id,
                   oos_draw_index
            FROM oos_budget_reservations
            WHERE reservation_id = ?
            """,
            (reservation_id,),
        ).fetchone()
        if not row:
            raise ValueError(f"Reservation {reservation_id} not found")
        if row[0] != "started":
            raise ValueError(
                f"Reservation {reservation_id} status is {row[0]}, "
                "expected 'started'"
            )

        theme_id, hypo_id, draw_idx = row[1], row[2], row[3]
        state_row = conn.execute(
            """
            SELECT consumed_draw_count, next_oos_draw_index, state_version
            FROM oos_budget_state
            WHERE theme_id = ? AND hypothesis_source_snapshot_id = ?
            """,
            (theme_id, hypo_id),
        ).fetchone()
        consumed, next_idx, version = state_row
        new_consumed = consumed + 1
        new_next_idx = next_idx + 1
        new_status = (
            "oos_budget_exhausted" if new_consumed >= 3 else "available"
        )
        conn.execute(
            """
            UPDATE oos_budget_reservations
            SET status = 'completed', verdict = ?, terminal_at = ?, report_id = ?
            WHERE reservation_id = ? AND status = 'started'
            """,
            (verdict, datetime.now().isoformat(), report_id, reservation_id),
        )
        cursor = conn.execute(
            """
            UPDATE oos_budget_state
            SET consumed_draw_count = ?, next_oos_draw_index = ?,
                budget_status = ?, active_reservation_id = NULL,
                state_version = state_version + 1, updated_at = ?
            WHERE theme_id = ?
              AND hypothesis_source_snapshot_id = ?
              AND state_version = ?
            """,
            (
                new_consumed,
                new_next_idx,
                new_status,
                datetime.now().isoformat(),
                theme_id,
                hypo_id,
                version,
            ),
        )
        if cursor.rowcount != 1:
            raise RuntimeError(f"State version mismatch for {theme_id}/{hypo_id}")
        self._insert_audit_within_tx(
            conn,
            theme_id,
            hypo_id,
            new_consumed,
            draw_idx,
            "completed",
        )

    def _insert_audit_within_tx(
        self,
        conn,
        theme_id: str,
        hypothesis_source_snapshot_id: str,
        consumed_count: int,
        draw_index: int,
        status: str,
    ) -> None:
        from contracts.strategy import OOSEvaluationLedger

        max_version = conn.execute(
            """
            SELECT MAX(ledger_version) FROM oos_evaluation_ledgers
            WHERE theme_id = ? AND hypothesis_source_snapshot_id = ?
            """,
            (theme_id, hypothesis_source_snapshot_id),
        ).fetchone()[0]
        next_version = (max_version or 0) + 1
        if status in ("reserved", "started"):
            budget_status = "reserved"
        elif consumed_count >= 3:
            budget_status = "oos_budget_exhausted"
        else:
            budget_status = "available"
        snapshot = OOSEvaluationLedger(
            ledger_snapshot_id=(
                f"oos_ledger_{theme_id}_"
                f"{hypothesis_source_snapshot_id}_v{next_version}"
            ),
            theme_id=theme_id,
            hypothesis_source_snapshot_id=hypothesis_source_snapshot_id,
            ledger_version=next_version,
            oos_evaluation_count=consumed_count,
            next_oos_draw_index=draw_index,
            budget_status=budget_status,
            recorded_at=datetime.now(),
        )
        conn.execute(
            """
            INSERT INTO oos_evaluation_ledgers
            (ledger_snapshot_id, theme_id, hypothesis_source_snapshot_id,
             ledger_version, payload_json, recorded_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot.ledger_snapshot_id,
                snapshot.theme_id,
                snapshot.hypothesis_source_snapshot_id,
                snapshot.ledger_version,
                snapshot.model_dump_json(),
                snapshot.recorded_at.isoformat(),
            ),
        )

    def _write_audit_tx(
        self,
        theme_id: str,
        hypothesis_source_snapshot_id: str,
        consumed_count: int,
        draw_index: int,
        status: str,
    ) -> None:
        """Write an audit snapshot on the ledger's active transaction."""
        self._insert_audit_within_tx(
            self.db.conn,
            theme_id,
            hypothesis_source_snapshot_id,
            consumed_count,
            draw_index,
            status,
        )

    def get_terminal_metadata(self, reservation_id: str) -> dict:
        """Return durable terminal metadata for idempotent replay."""
        row = self.db.conn.execute(
            """
            SELECT status, verdict, report_id, terminal_reason
            FROM oos_budget_reservations
            WHERE reservation_id = ?
            """,
            (reservation_id,),
        ).fetchone()
        if not row:
            raise ValueError(f"Reservation {reservation_id} not found")
        return {
            "status": row[0],
            "verdict": row[1],
            "report_id": row[2],
            "terminal_reason": row[3],
        }

    def _get_draw_index(self, reservation_id: str) -> int:
        row = self.db.conn.execute(
            """
            SELECT oos_draw_index FROM oos_budget_reservations
            WHERE reservation_id = ?
            """,
            (reservation_id,),
        ).fetchone()
        return row[0] if row else 1

    def _generate_reservation_id(
        self,
        theme_id: str,
        oos_draw_index: int,
    ) -> str:
        payload = {
            "theme_id": theme_id,
            "oos_draw_index": oos_draw_index,
            "timestamp": datetime.now().isoformat(),
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode("utf-8")
        ).hexdigest()[:16]
        return f"rsv_{theme_id}_{oos_draw_index}_{digest}"

    def _transact_with_retry(self, fn):
        """Retry one SQLite busy/locked failure, then fail loudly."""
        try:
            return fn()
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower() and "busy" not in str(exc).lower():
                raise
            time.sleep(0.1)
            try:
                return fn()
            except sqlite3.OperationalError as retry_exc:
                if (
                    "locked" in str(retry_exc).lower()
                    or "busy" in str(retry_exc).lower()
                ):
                    raise RuntimeError(
                        f"OOS ledger concurrency unavailable: {retry_exc}"
                    ) from retry_exc
                raise
