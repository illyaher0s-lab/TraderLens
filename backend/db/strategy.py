from __future__ import annotations

import sqlite3
import hashlib
import json
from datetime import datetime

from contracts.strategy import (
    BacktestUniverseSpec,
    ForwardWatchlistSnapshot,
    HumanConfirmationConsumption,
    HumanPromotionConfirmation,
    ImmutableBacktestReport,
    OOSEvaluationLedger,
    PrototypeGateResultV2,
    ResearchProtocolSnapshot,
    StrategyDraft,
    StrategyLifecycleState,
    StrategyPromotionRecord,
    StrategyTemplateDefinition,
)
from contracts.b6_task import (
    B6ValidationTask,
    build_b6_successor_task_key,
    build_b6_task_id,
    build_b6_task_key,
)


IMMUTABLE_TABLES = (
    "strategy_template_definitions",
    "backtest_universe_specs",
    "forward_watchlist_snapshots",
    "strategy_drafts",
    "strategy_lifecycle_states",
    "research_protocol_snapshots",
    "oos_evaluation_ledgers",
    "immutable_backtest_reports",
    "prototype_gate_results_v2",
    "human_promotion_confirmations",
    "human_confirmation_consumptions",
    "strategy_promotions",
)


class ProtocolSnapshotLookupError(ValueError):
    """Typed strict revision/profile lookup failure."""

    def __init__(self, reason_code: str):
        if reason_code not in {
            "protocol_snapshot_unavailable",
            "protocol_snapshot_ambiguous",
        }:
            raise ValueError(f"unsupported protocol snapshot lookup reason: {reason_code}")
        self.reason_code = reason_code
        super().__init__(reason_code)


class B6SuccessorPreconditionError(ValueError):
    """Typed refusal to create a v3 successor attempt."""

    _REASON_CODES = {
        "b6_successor_predecessor_missing",
        "b6_successor_predecessor_identity_invalid",
        "b6_successor_predecessor_not_v2",
        "b6_successor_predecessor_not_failed",
        "b6_successor_existing_conflict",
        "b6_successor_oos_evidence_present",
        "b6_successor_report_or_gate_evidence_present",
    }

    def __init__(self, reason_code: str, detail: str | None = None):
        if reason_code not in self._REASON_CODES:
            raise ValueError(f"unsupported B6 successor reason: {reason_code}")
        self.reason_code = reason_code
        super().__init__(reason_code if detail is None else f"{reason_code}: {detail}")


class StrategyDB:
    def __init__(self, db_path: str = "data/strategy.db"):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._initialize_schema()
        self._run_migrations()

    def _run_migrations(self):
        """Run schema migrations if needed."""
        from backend.db.migrations.migration_001_add_hypothesis_to_audit import (
            migrate_oos_evaluation_ledgers_add_hypothesis,
        )
        migrate_oos_evaluation_ledgers_add_hypothesis(self.conn)

        from backend.db.migrations.migration_002_add_b6_runtime_schema import (
            migrate_add_b6_runtime_schema,
        )
        if not self._protocol_multiplicity_migration_is_active():
            migrate_add_b6_runtime_schema(self.conn)

        from backend.db.migrations.migration_003_add_b5_binding_to_b6_tasks import (
            migrate_add_b5_binding_to_b6_tasks,
        )
        migrate_add_b5_binding_to_b6_tasks(self.conn)

        from backend.db.migrations.migration_004_allow_protocol_multiplicity import (
            migrate_allow_protocol_multiplicity,
        )
        migrate_allow_protocol_multiplicity(self.conn)

        from backend.db.migrations.migration_005_add_b6_successor_attempt import (
            migrate_add_b6_successor_attempt,
        )
        migrate_add_b6_successor_attempt(self.conn)

    def _protocol_multiplicity_migration_is_active(self) -> bool:
        """Return whether migration 004 already owns protocol multiplicity."""
        columns = {
            row[1]
            for row in self.conn.execute(
                "PRAGMA table_info(research_protocol_snapshots)"
            )
        }
        if "protocol_profile" not in columns:
            return False
        return (
            self.conn.execute(
                """
                SELECT 1
                FROM sqlite_master
                WHERE type = 'index'
                  AND name = 'idx_protocol_b6_profile_per_revision'
                """
            ).fetchone()
            is not None
        )

    def close(self) -> None:
        self.conn.close()

    # === B6 Task CRUD API ===

    def create_b6_task(self, task: B6ValidationTask) -> None:
        """
        Create B6 validation task. Idempotent on task_key.

        Uses INSERT OR IGNORE to handle concurrent task creation.
        """
        self.conn.execute(
            """
            INSERT OR IGNORE INTO b6_validation_tasks
            (task_id, task_key, task_type, task_contract_version,
             strategy_revision_id, protocol_snapshot_id, status,
             blocking_reason_code, blocking_reason_detail,
             payload_json, created_at, claimed_at, completed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task.task_id,
                task.task_key,
                task.task_type,
                task.task_contract_version,
                task.strategy_revision_id,
                task.protocol_snapshot_id,
                task.status,
                task.blocking_reason_code,
                task.blocking_reason_detail,
                self._json(task),
                task.created_at.isoformat(),
                task.claimed_at.isoformat() if task.claimed_at else None,
                task.completed_at.isoformat() if task.completed_at else None,
            ),
        )
        self.conn.commit()

    def create_or_get_b6_task(self, task: B6ValidationTask) -> tuple[B6ValidationTask, bool]:
        """Create or reuse a v2 queued task by exact immutable admission identity."""
        if (
            task.task_contract_version != "v2"
            or task.status != "queued"
            or task.blocking_reason_code is not None
            or task.blocking_reason_detail is not None
            or task.claimed_at is not None
            or task.completed_at is not None
            or task.b5_bundle_id is None
        or task.b5_bundle_manifest_sha256 is None
        ):
            raise ValueError("create_or_get_b6_task requires a queued v2 admission task")

        expected_task_key = build_b6_task_key(
            strategy_revision_id=task.strategy_revision_id,
            protocol_snapshot_id=task.protocol_snapshot_id,
            task_contract_version=task.task_contract_version,
            b5_bundle_id=task.b5_bundle_id,
            b5_bundle_manifest_sha256=task.b5_bundle_manifest_sha256,
        )
        if task.task_key != expected_task_key:
            raise ValueError("B6 task key does not match frozen identity")
        if task.task_id != build_b6_task_id(task.task_key):
            raise ValueError("B6 task ID does not match canonical task key")

        immutable_fields = (
            "task_id",
            "task_key",
            "task_type",
            "task_contract_version",
            "strategy_revision_id",
            "protocol_snapshot_id",
            "b5_bundle_id",
            "b5_bundle_manifest_sha256",
            "predecessor_task_id",
            "predecessor_task_key",
            "successor_attempt_number",
        )

        def identity(candidate: B6ValidationTask) -> tuple:
            return tuple(getattr(candidate, field) for field in immutable_fields)

        try:
            self.conn.execute("BEGIN IMMEDIATE")
            row = self.conn.execute(
                "SELECT * FROM b6_validation_tasks WHERE task_key = ?",
                (task.task_key,),
            ).fetchone()
            created = row is None
            if created:
                self.conn.execute(
                    """
                    INSERT INTO b6_validation_tasks
                    (task_id, task_key, task_type, task_contract_version,
                     strategy_revision_id, protocol_snapshot_id, status,
                     blocking_reason_code, blocking_reason_detail,
                     payload_json, created_at, claimed_at, completed_at,
                     b5_bundle_id, b5_bundle_manifest_sha256)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        task.task_id,
                        task.task_key,
                        task.task_type,
                        task.task_contract_version,
                        task.strategy_revision_id,
                        task.protocol_snapshot_id,
                        task.status,
                        task.blocking_reason_code,
                        task.blocking_reason_detail,
                        self._json(task),
                        task.created_at.isoformat(),
                        task.claimed_at.isoformat() if task.claimed_at else None,
                        task.completed_at.isoformat() if task.completed_at else None,
                        task.b5_bundle_id,
                        task.b5_bundle_manifest_sha256,
                    ),
                )

            persisted = self.conn.execute(
                "SELECT * FROM b6_validation_tasks WHERE task_key = ?",
                (task.task_key,),
            ).fetchone()
            if persisted is None:
                raise RuntimeError("B6 task disappeared before commit")
            winner = self._load_b6_task(persisted)
            if identity(winner) != identity(task):
                raise ValueError("B6 task immutable identity conflict")
            if created and winner.created_at != task.created_at:
                raise ValueError("B6 task created_at persistence mismatch")

            self.conn.commit()
            return winner, created
        except Exception:
            self.conn.rollback()
            raise

    def create_or_get_b6_successor_attempt(
        self,
        predecessor_task_id: str,
    ) -> tuple[B6ValidationTask, bool]:
        """Create or reuse the single queued v3 successor for a failed v2 task."""
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            predecessor_row = self.conn.execute(
                "SELECT * FROM b6_validation_tasks WHERE task_id = ?",
                (predecessor_task_id,),
            ).fetchone()
            if predecessor_row is None:
                raise B6SuccessorPreconditionError(
                    "b6_successor_predecessor_missing",
                    predecessor_task_id,
                )
            try:
                predecessor = self._load_b6_task(predecessor_row)
            except Exception as exc:
                raise B6SuccessorPreconditionError(
                    "b6_successor_predecessor_identity_invalid",
                    str(exc),
                ) from exc

            if predecessor.task_contract_version != "v2":
                raise B6SuccessorPreconditionError(
                    "b6_successor_predecessor_not_v2",
                    predecessor.task_contract_version,
                )
            if predecessor.status != "failed" or predecessor.claimed_at is None:
                raise B6SuccessorPreconditionError(
                    "b6_successor_predecessor_not_failed",
                    f"status={predecessor.status}, claimed_at={predecessor.claimed_at}",
                )

            try:
                expected_predecessor_key = build_b6_task_key(
                    strategy_revision_id=predecessor.strategy_revision_id,
                    protocol_snapshot_id=predecessor.protocol_snapshot_id,
                    task_contract_version="v2",
                    b5_bundle_id=predecessor.b5_bundle_id,
                    b5_bundle_manifest_sha256=predecessor.b5_bundle_manifest_sha256,
                )
            except Exception as exc:
                raise B6SuccessorPreconditionError(
                    "b6_successor_predecessor_identity_invalid",
                    str(exc),
                ) from exc
            if (
                predecessor.task_key != expected_predecessor_key
                or predecessor.task_id != build_b6_task_id(predecessor.task_key)
            ):
                raise B6SuccessorPreconditionError(
                    "b6_successor_predecessor_identity_invalid",
                    "predecessor task ID/key is not canonical",
                )

            try:
                protocol = self.get_protocol_snapshot(predecessor.protocol_snapshot_id)
            except Exception as exc:
                raise B6SuccessorPreconditionError(
                    "b6_successor_predecessor_identity_invalid",
                    str(exc),
                ) from exc
            if (
                protocol is None
                or protocol.strategy_revision_id != predecessor.strategy_revision_id
                or protocol.protocol_profile != "b6_coverage_bound"
            ):
                raise B6SuccessorPreconditionError(
                    "b6_successor_predecessor_identity_invalid",
                    "protocol/revision/profile binding is invalid",
                )

            successor_key = build_b6_successor_task_key(
                predecessor_task_id=predecessor.task_id,
                predecessor_task_key=predecessor.task_key,
                strategy_revision_id=predecessor.strategy_revision_id,
                protocol_snapshot_id=predecessor.protocol_snapshot_id,
                b5_bundle_id=predecessor.b5_bundle_id,
                b5_bundle_manifest_sha256=predecessor.b5_bundle_manifest_sha256,
                attempt_number=1,
            )

            existing_row = self.conn.execute(
                "SELECT * FROM b6_validation_tasks WHERE predecessor_task_id = ?",
                (predecessor.task_id,),
            ).fetchone()
            if existing_row is not None:
                try:
                    existing = self._load_b6_task(existing_row)
                except Exception as exc:
                    raise B6SuccessorPreconditionError(
                        "b6_successor_existing_conflict",
                        str(exc),
                    ) from exc
                expected_identity = (
                    build_b6_task_id(successor_key),
                    successor_key,
                    "b6_validation",
                    "v3",
                    predecessor.strategy_revision_id,
                    predecessor.protocol_snapshot_id,
                    predecessor.b5_bundle_id,
                    predecessor.b5_bundle_manifest_sha256,
                    predecessor.task_id,
                    predecessor.task_key,
                    1,
                )
                actual_identity = (
                    existing.task_id,
                    existing.task_key,
                    existing.task_type,
                    existing.task_contract_version,
                    existing.strategy_revision_id,
                    existing.protocol_snapshot_id,
                    existing.b5_bundle_id,
                    existing.b5_bundle_manifest_sha256,
                    existing.predecessor_task_id,
                    existing.predecessor_task_key,
                    existing.successor_attempt_number,
                )
                if actual_identity != expected_identity:
                    raise B6SuccessorPreconditionError(
                        "b6_successor_existing_conflict",
                        "successor immutable identity mismatch",
                    )
                self.conn.commit()
                return existing, False

            state = self.conn.execute(
                """
                SELECT consumed_draw_count, next_oos_draw_index,
                       budget_status, active_reservation_id
                FROM oos_budget_state
                WHERE theme_id = ? AND hypothesis_source_snapshot_id = ?
                """,
                (protocol.theme_id, protocol.hypothesis_source_snapshot_id),
            ).fetchone()
            if state is not None and tuple(state) != (0, 1, "available", None):
                raise B6SuccessorPreconditionError(
                    "b6_successor_oos_evidence_present",
                    "non-pristine OOS budget state",
                )

            reservation = self.conn.execute(
                """
                SELECT reservation_id
                FROM oos_budget_reservations
                WHERE (theme_id = ? AND hypothesis_source_snapshot_id = ?)
                   OR task_key IN (?, ?)
                   OR protocol_snapshot_id = ?
                LIMIT 1
                """,
                (
                    protocol.theme_id,
                    protocol.hypothesis_source_snapshot_id,
                    predecessor.task_key,
                    successor_key,
                    predecessor.protocol_snapshot_id,
                ),
            ).fetchone()
            if reservation is not None:
                raise B6SuccessorPreconditionError(
                    "b6_successor_oos_evidence_present",
                    f"reservation={reservation[0]}",
                )

            ledger = self.conn.execute(
                """
                SELECT ledger_snapshot_id
                FROM oos_evaluation_ledgers
                WHERE theme_id = ? AND hypothesis_source_snapshot_id = ?
                LIMIT 1
                """,
                (protocol.theme_id, protocol.hypothesis_source_snapshot_id),
            ).fetchone()
            if ledger is not None:
                raise B6SuccessorPreconditionError(
                    "b6_successor_oos_evidence_present",
                    f"ledger={ledger[0]}",
                )

            report_rows = self.conn.execute(
                """
                SELECT report_id, payload_json
                FROM immutable_backtest_reports
                WHERE strategy_revision_id = ? AND protocol_snapshot_id = ?
                LIMIT 1
                """,
                (predecessor.strategy_revision_id, predecessor.protocol_snapshot_id),
            ).fetchall()
            if report_rows:
                try:
                    json.loads(report_rows[0][1])
                except Exception as exc:
                    raise B6SuccessorPreconditionError(
                        "b6_successor_report_or_gate_evidence_present",
                        f"invalid report payload: {exc}",
                    ) from exc
                raise B6SuccessorPreconditionError(
                    "b6_successor_report_or_gate_evidence_present",
                    f"report={report_rows[0][0]}",
                )

            gate = self.conn.execute(
                """
                SELECT gate_result_id
                FROM prototype_gate_results_v2
                WHERE strategy_revision_id = ? AND protocol_snapshot_id = ?
                LIMIT 1
                """,
                (predecessor.strategy_revision_id, predecessor.protocol_snapshot_id),
            ).fetchone()
            if gate is not None:
                raise B6SuccessorPreconditionError(
                    "b6_successor_report_or_gate_evidence_present",
                    f"gate={gate[0]}",
                )

            created_at = datetime.now()
            successor = B6ValidationTask(
                task_id=build_b6_task_id(successor_key),
                task_key=successor_key,
                task_type="b6_validation",
                task_contract_version="v3",
                strategy_revision_id=predecessor.strategy_revision_id,
                protocol_snapshot_id=predecessor.protocol_snapshot_id,
                status="queued",
                created_at=created_at,
                b5_bundle_id=predecessor.b5_bundle_id,
                b5_bundle_manifest_sha256=predecessor.b5_bundle_manifest_sha256,
                predecessor_task_id=predecessor.task_id,
                predecessor_task_key=predecessor.task_key,
                successor_attempt_number=1,
            )
            try:
                self.conn.execute(
                    """
                    INSERT INTO b6_validation_tasks
                    (task_id, task_key, task_type, task_contract_version,
                     strategy_revision_id, protocol_snapshot_id, status,
                     blocking_reason_code, blocking_reason_detail, payload_json,
                     created_at, claimed_at, completed_at, b5_bundle_id,
                     b5_bundle_manifest_sha256, predecessor_task_id,
                     predecessor_task_key, successor_attempt_number)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        successor.task_id,
                        successor.task_key,
                        successor.task_type,
                        successor.task_contract_version,
                        successor.strategy_revision_id,
                        successor.protocol_snapshot_id,
                        successor.status,
                        successor.blocking_reason_code,
                        successor.blocking_reason_detail,
                        self._json(successor),
                        successor.created_at.isoformat(),
                        None,
                        None,
                        successor.b5_bundle_id,
                        successor.b5_bundle_manifest_sha256,
                        successor.predecessor_task_id,
                        successor.predecessor_task_key,
                        successor.successor_attempt_number,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise B6SuccessorPreconditionError(
                    "b6_successor_existing_conflict",
                    str(exc),
                ) from exc

            persisted_row = self.conn.execute(
                "SELECT * FROM b6_validation_tasks WHERE predecessor_task_id = ?",
                (predecessor.task_id,),
            ).fetchone()
            if persisted_row is None:
                raise RuntimeError("B6 successor disappeared before commit")
            winner = self._load_b6_task(persisted_row)
            if (
                winner.task_id != successor.task_id
                or winner.task_key != successor.task_key
                or winner.created_at != successor.created_at
                or winner.predecessor_task_id != successor.predecessor_task_id
                or winner.predecessor_task_key != successor.predecessor_task_key
                or winner.successor_attempt_number != successor.successor_attempt_number
            ):
                raise B6SuccessorPreconditionError(
                    "b6_successor_existing_conflict",
                    "successor persistence identity mismatch",
                )
            self.conn.commit()
            return winner, True
        except Exception:
            self.conn.rollback()
            raise

    def _validate_b6_terminal_bindings(
        self,
        *,
        report: ImmutableBacktestReport,
        gate_result: PrototypeGateResultV2,
        reservation_id: str,
        task_id: str,
    ) -> None:
        task_row = self.conn.execute(
            "SELECT * FROM b6_validation_tasks WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        if task_row is None:
            raise ValueError("B6 terminal task is missing")
        task = self._load_b6_task(task_row)
        if task.status != "running":
            raise ValueError("B6 terminal task must be running")

        reservation = self.conn.execute(
            """
            SELECT status, task_key, protocol_snapshot_id,
                   strategy_config_hash, data_snapshot_hash,
                   gate_criteria_hash, shared_oos_window_id,
                   oos_draw_index, report_id
            FROM oos_budget_reservations
            WHERE reservation_id = ?
            """,
            (reservation_id,),
        ).fetchone()
        if reservation is None or reservation[0] != "started":
            raise ValueError("B6 terminal reservation must be started")
        if reservation[1] != task.task_key or reservation[2] != task.protocol_snapshot_id:
            raise ValueError("B6 terminal reservation task/protocol mismatch")
        protocol = self.get_protocol_snapshot(task.protocol_snapshot_id)
        if protocol is None or protocol.strategy_revision_id != task.strategy_revision_id:
            raise ValueError("B6 terminal protocol/revision mismatch")
        for actual, expected, label in (
            (reservation[3], protocol.strategy_config_hash, "strategy config"),
            (reservation[4], protocol.data_snapshot_hash, "data snapshot"),
            (reservation[5], protocol.gate_criteria_hash, "Gate criteria"),
            (reservation[6], protocol.shared_oos_window_id, "OOS window"),
        ):
            if actual != expected:
                raise ValueError(f"B6 terminal {label} mismatch")
        if report.report_id != reservation[8]:
            if reservation[8] is not None:
                raise ValueError("B6 terminal report ID mismatch")
        if report.strategy_revision_id != task.strategy_revision_id or report.protocol_snapshot_id != task.protocol_snapshot_id:
            raise ValueError("B6 terminal report task/protocol mismatch")
        if report.strategy_config_hash != protocol.strategy_config_hash or report.data_snapshot_hash != protocol.data_snapshot_hash or report.gate_criteria_hash != protocol.gate_criteria_hash:
            raise ValueError("B6 terminal report hash binding mismatch")
        if report.shared_oos_window_id != protocol.shared_oos_window_id or report.oos_draw_index != reservation[7]:
            raise ValueError("B6 terminal report window/draw mismatch")

        payload = json.loads(report.report_payload_json)
        same_draw = payload.get("same_draw_result")
        identity = same_draw.get("identity") if isinstance(same_draw, dict) else None
        if not isinstance(identity, dict):
            raise ValueError("B6 terminal report missing same-draw identity")
        for field, expected in (
            ("task_id", task.task_id),
            ("task_key", task.task_key),
            ("strategy_revision_id", task.strategy_revision_id),
            ("protocol_snapshot_id", task.protocol_snapshot_id),
            ("b5_bundle_id", task.b5_bundle_id),
            ("b5_bundle_manifest_sha256", task.b5_bundle_manifest_sha256),
            ("shared_oos_window_id", protocol.shared_oos_window_id),
            ("data_snapshot_hash", protocol.data_snapshot_hash),
        ):
            if identity.get(field) != expected:
                raise ValueError(f"B6 terminal same-draw {field} mismatch")
        if payload.get("task_id") != task.task_id or payload.get("task_key") != task.task_key:
            raise ValueError("B6 terminal report task identity mismatch")
        if payload.get("protocol_snapshot_id") != task.protocol_snapshot_id or payload.get("b5_bundle_id") != task.b5_bundle_id or payload.get("b5_bundle_manifest_sha256") != task.b5_bundle_manifest_sha256:
            raise ValueError("B6 terminal report payload binding mismatch")
        expected_report_hash = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        if report.report_hash != expected_report_hash:
            raise ValueError("B6 terminal report hash mismatch")

        if gate_result.report_id != report.report_id or gate_result.strategy_revision_id != task.strategy_revision_id or gate_result.protocol_snapshot_id != task.protocol_snapshot_id:
            raise ValueError("B6 terminal Gate identity mismatch")
        if gate_result.strategy_config_hash != report.strategy_config_hash or gate_result.data_snapshot_hash != report.data_snapshot_hash or gate_result.gate_criteria_hash != report.gate_criteria_hash:
            raise ValueError("B6 terminal Gate binding mismatch")
        if gate_result.oos_draw_index != report.oos_draw_index or gate_result.shared_oos_window_id != report.shared_oos_window_id:
            raise ValueError("B6 terminal Gate window mismatch")
        checks = json.loads(gate_result.checks_json)
        expected_gate_hash = hashlib.sha256(
            json.dumps(
                {"report_id": report.report_id, "verdict": gate_result.verdict, "checks": checks},
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        if gate_result.gate_result_hash != expected_gate_hash:
            raise ValueError("B6 terminal Gate hash mismatch")

    def get_b6_task_by_id(self, task_id: str):
        """Read task by ID. Returns None if not found."""
        row = self.conn.execute(
            "SELECT * FROM b6_validation_tasks WHERE task_id = ?", (task_id,)
        ).fetchone()
        if row is None:
            return None
        return self._load_b6_task(row)

    def get_b6_task_by_key(self, task_key: str) -> B6ValidationTask | None:
        """Read B6 validation task by deterministic task_key. Returns None if task does not exist."""
        row = self.conn.execute(
            "SELECT * FROM b6_validation_tasks WHERE task_key = ?", (task_key,)
        ).fetchone()
        if row is None:
            return None
        return self._load_b6_task(row)

    def _load_b6_task(self, row):
        """ponytail: load from payload, overlay live columns"""
        base = B6ValidationTask.model_validate_json(row["payload_json"])
        immutable_fields = (
            "task_id",
            "task_key",
            "task_type",
            "task_contract_version",
            "strategy_revision_id",
            "protocol_snapshot_id",
            "b5_bundle_id",
            "b5_bundle_manifest_sha256",
        )
        if all(field in row.keys() for field in immutable_fields):
            for field in immutable_fields:
                if getattr(base, field) != row[field]:
                    raise ValueError(f"B6 task payload/column mismatch: {field}")
        if "created_at" in row.keys():
            if datetime.fromisoformat(row["created_at"]) != base.created_at:
                raise ValueError("B6 task payload/column mismatch: created_at")
        return base.model_copy(update={
            "status": row["status"],
            "blocking_reason_code": row["blocking_reason_code"],
            "blocking_reason_detail": row["blocking_reason_detail"],
            "claimed_at": datetime.fromisoformat(row["claimed_at"]) if row["claimed_at"] else None,
            "completed_at": datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
        })

    def claim_b6_task(self, task_id: str) -> B6ValidationTask | None:
        """ponytail: atomic queued→running, rowcount=1 or None."""
        cursor = self.conn.execute(
            "UPDATE b6_validation_tasks SET status='running', claimed_at=? WHERE task_id=? AND status='queued'",
            (datetime.now().isoformat(), task_id)
        )
        self.conn.commit()
        return self.get_b6_task_by_id(task_id) if cursor.rowcount == 1 else None

    def update_b6_task_status(
        self,
        task_id: str,
        status: str,
        completed_at: datetime | None = None,
        blocking_reason_code: str | None = None,
        blocking_reason_detail: str | None = None,
    ):
        """Update task status. Returns cursor for rowcount check."""
        cursor = self.conn.execute(
            """
            UPDATE b6_validation_tasks
            SET status = ?, completed_at = ?, blocking_reason_code = ?, blocking_reason_detail = ?
            WHERE task_id = ?
            """,
            (status, completed_at.isoformat() if completed_at else None, blocking_reason_code, blocking_reason_detail, task_id),
        )
        return cursor

    def store_b6_terminal_result_tx(
        self,
        report: ImmutableBacktestReport,
        gate_result: PrototypeGateResultV2,
        reservation_id: str,
        verdict: str,
        task_id: str,
        oos_budget_ledger,  # OOSBudgetLedger instance
    ) -> None:
        """
        ONE terminal transaction: report + Gate + ledger completed + task completed.

        Design requirement (2026-07-18-b6-runtime-validation-task-design.md):
        After OOS returns, every successful validation writes in one terminal transaction:
        1. immutable report and Gate result
        2. completed ledger/reservation state
        3. task completed state

        Any failure rolls back ALL writes.
        Inline OOSBudgetLedger UPDATE logic (no nested transaction).
        """
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            self._validate_b6_terminal_bindings(
                report=report,
                gate_result=gate_result,
                reservation_id=reservation_id,
                task_id=task_id,
            )

            # 1. Insert immutable report
            self.conn.execute(
                """
                INSERT INTO immutable_backtest_reports
                (report_id, strategy_revision_id, protocol_snapshot_id,
                 payload_json, report_hash, integrity_status, generated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report.report_id,
                    report.strategy_revision_id,
                    report.protocol_snapshot_id,
                    self._json(report),
                    report.report_hash,
                    report.integrity_status,
                    report.generated_at.isoformat(),
                ),
            )

            # 2. Insert Gate result
            self.conn.execute(
                """
                INSERT INTO prototype_gate_results_v2
                (gate_result_id, strategy_revision_id, report_id, protocol_snapshot_id,
                 payload_json, gate_result_hash, verdict, generated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    gate_result.gate_result_id,
                    gate_result.strategy_revision_id,
                    gate_result.report_id,
                    gate_result.protocol_snapshot_id,
                    self._json(gate_result),
                    gate_result.gate_result_hash,
                    gate_result.verdict,
                    gate_result.generated_at.isoformat(),
                ),
            )

            # 3. Complete reservation + audit (via ledger no-commit primitive)
            oos_budget_ledger.complete_reservation_within_tx(
                self.conn, reservation_id, verdict, report.report_id
            )

            # 4. Update task status
            cursor = self.update_b6_task_status(
                task_id=task_id,
                status="completed",
                completed_at=datetime.now(),
            )
            if cursor.rowcount != 1:
                raise RuntimeError(f"Task {task_id} UPDATE affected {cursor.rowcount} rows, expected 1")

            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def _initialize_schema(self):
        cursor = self.conn.cursor()
        cursor.executescript(
            """
            CREATE TABLE IF NOT EXISTS strategy_template_definitions (
                template_id TEXT NOT NULL,
                version TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                template_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (template_id, version)
            );

            CREATE TABLE IF NOT EXISTS backtest_universe_specs (
                universe_spec_id TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS forward_watchlist_snapshots (
                watchlist_snapshot_id TEXT PRIMARY KEY,
                theme_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS strategy_drafts (
                strategy_revision_id TEXT PRIMARY KEY,
                theme_id TEXT NOT NULL,
                hypothesis_id TEXT NOT NULL,
                backtest_universe_spec_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (backtest_universe_spec_id)
                    REFERENCES backtest_universe_specs(universe_spec_id)
            );

            CREATE TABLE IF NOT EXISTS strategy_lifecycle_states (
                lifecycle_state_id TEXT PRIMARY KEY,
                strategy_revision_id TEXT NOT NULL,
                state_version INTEGER NOT NULL,
                state TEXT NOT NULL CHECK (state IN ('draft', 'prototype_passed')),
                source_record_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                UNIQUE (strategy_revision_id, state_version),
                FOREIGN KEY (strategy_revision_id)
                    REFERENCES strategy_drafts(strategy_revision_id)
            );

            CREATE UNIQUE INDEX IF NOT EXISTS
                uq_strategy_one_prototype_passed
            ON strategy_lifecycle_states(strategy_revision_id)
            WHERE state = 'prototype_passed';

            CREATE TABLE IF NOT EXISTS research_protocol_snapshots (
                protocol_snapshot_id TEXT PRIMARY KEY,
                strategy_revision_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                strategy_config_hash TEXT NOT NULL,
                data_snapshot_hash TEXT NOT NULL,
                gate_criteria_hash TEXT NOT NULL,
                frozen_at TEXT NOT NULL,
                FOREIGN KEY (strategy_revision_id)
                    REFERENCES strategy_drafts(strategy_revision_id)
            );

            CREATE TABLE IF NOT EXISTS oos_evaluation_ledgers (
                ledger_snapshot_id TEXT PRIMARY KEY,
                theme_id TEXT NOT NULL,
                hypothesis_source_snapshot_id TEXT NOT NULL,
                ledger_version INTEGER NOT NULL,
                payload_json TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                UNIQUE (theme_id, hypothesis_source_snapshot_id, ledger_version)
            );

            CREATE TABLE IF NOT EXISTS immutable_backtest_reports (
                report_id TEXT PRIMARY KEY,
                strategy_revision_id TEXT NOT NULL,
                protocol_snapshot_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                report_hash TEXT NOT NULL UNIQUE,
                integrity_status TEXT NOT NULL CHECK (integrity_status IN ('valid', 'invalid')),
                generated_at TEXT NOT NULL,
                FOREIGN KEY (strategy_revision_id)
                    REFERENCES strategy_drafts(strategy_revision_id),
                FOREIGN KEY (protocol_snapshot_id)
                    REFERENCES research_protocol_snapshots(protocol_snapshot_id)
            );

            CREATE TABLE IF NOT EXISTS prototype_gate_results_v2 (
                gate_result_id TEXT PRIMARY KEY,
                strategy_revision_id TEXT NOT NULL,
                report_id TEXT NOT NULL,
                protocol_snapshot_id TEXT NOT NULL,
                verdict TEXT NOT NULL CHECK (
                    verdict IN (
                        'rejected',
                        'needs_review',
                        'candidate_for_prototype_passed'
                    )
                ),
                payload_json TEXT NOT NULL,
                gate_result_hash TEXT NOT NULL UNIQUE,
                generated_at TEXT NOT NULL,
                FOREIGN KEY (strategy_revision_id)
                    REFERENCES strategy_drafts(strategy_revision_id),
                FOREIGN KEY (report_id)
                    REFERENCES immutable_backtest_reports(report_id),
                FOREIGN KEY (protocol_snapshot_id)
                    REFERENCES research_protocol_snapshots(protocol_snapshot_id)
            );

            CREATE TABLE IF NOT EXISTS human_promotion_confirmations (
                human_confirmation_id TEXT PRIMARY KEY,
                strategy_revision_id TEXT NOT NULL,
                gate_result_id TEXT NOT NULL,
                decision TEXT NOT NULL CHECK (decision IN ('approve', 'reject')),
                payload_json TEXT NOT NULL,
                confirmed_at TEXT NOT NULL,
                FOREIGN KEY (strategy_revision_id)
                    REFERENCES strategy_drafts(strategy_revision_id),
                FOREIGN KEY (gate_result_id)
                    REFERENCES prototype_gate_results_v2(gate_result_id)
            );

            CREATE TABLE IF NOT EXISTS strategy_promotions (
                promotion_id TEXT PRIMARY KEY,
                strategy_revision_id TEXT NOT NULL UNIQUE,
                gate_result_id TEXT NOT NULL,
                report_id TEXT NOT NULL,
                protocol_snapshot_id TEXT NOT NULL,
                human_confirmation_id TEXT NOT NULL UNIQUE,
                payload_json TEXT NOT NULL,
                promoted_at TEXT NOT NULL,
                FOREIGN KEY (strategy_revision_id)
                    REFERENCES strategy_drafts(strategy_revision_id),
                FOREIGN KEY (gate_result_id)
                    REFERENCES prototype_gate_results_v2(gate_result_id),
                FOREIGN KEY (report_id)
                    REFERENCES immutable_backtest_reports(report_id),
                FOREIGN KEY (protocol_snapshot_id)
                    REFERENCES research_protocol_snapshots(protocol_snapshot_id),
                FOREIGN KEY (human_confirmation_id)
                    REFERENCES human_promotion_confirmations(human_confirmation_id)
            );

            CREATE TABLE IF NOT EXISTS human_confirmation_consumptions (
                consumption_id TEXT PRIMARY KEY,
                human_confirmation_id TEXT NOT NULL UNIQUE,
                strategy_revision_id TEXT NOT NULL,
                gate_result_id TEXT NOT NULL,
                promotion_id TEXT NOT NULL UNIQUE,
                payload_json TEXT NOT NULL,
                consumed_at TEXT NOT NULL,
                FOREIGN KEY (human_confirmation_id)
                    REFERENCES human_promotion_confirmations(human_confirmation_id),
                FOREIGN KEY (promotion_id)
                    REFERENCES strategy_promotions(promotion_id)
            );

            CREATE TABLE IF NOT EXISTS oos_budget_state (
                theme_id TEXT NOT NULL,
                hypothesis_source_snapshot_id TEXT NOT NULL,
                consumed_draw_count INTEGER NOT NULL DEFAULT 0
                    CHECK (consumed_draw_count BETWEEN 0 AND 3),
                next_oos_draw_index INTEGER NOT NULL DEFAULT 1
                    CHECK (next_oos_draw_index BETWEEN 1 AND 4),
                budget_status TEXT NOT NULL DEFAULT 'available'
                    CHECK (budget_status IN ('available', 'oos_budget_exhausted')),
                active_reservation_id TEXT,
                state_version INTEGER NOT NULL DEFAULT 1 CHECK (state_version >= 1),
                updated_at TEXT NOT NULL,
                PRIMARY KEY (theme_id, hypothesis_source_snapshot_id),
                CHECK (
                    (budget_status = 'available' AND consumed_draw_count < 3)
                    OR
                    (budget_status = 'oos_budget_exhausted' AND consumed_draw_count = 3)
                )
            );

            CREATE TABLE IF NOT EXISTS oos_budget_reservations (
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
            );

            CREATE UNIQUE INDEX IF NOT EXISTS uq_oos_active_draw_per_owner
            ON oos_budget_reservations(theme_id, hypothesis_source_snapshot_id, oos_draw_index)
            WHERE status IN ('reserved', 'started', 'completed', 'failed');

            CREATE UNIQUE INDEX IF NOT EXISTS uq_oos_one_active_reservation_per_owner
            ON oos_budget_reservations(theme_id, hypothesis_source_snapshot_id)
            WHERE status IN ('reserved', 'started');

            CREATE UNIQUE INDEX IF NOT EXISTS uq_oos_hash_tuple_in_flight_or_terminal
            ON oos_budget_reservations(
                strategy_config_hash, data_snapshot_hash, gate_criteria_hash
            )
            WHERE status IN ('reserved', 'started', 'completed', 'failed');

            CREATE UNIQUE INDEX IF NOT EXISTS uq_oos_idempotency_per_owner
            ON oos_budget_reservations(theme_id, hypothesis_source_snapshot_id, idempotency_key);

            CREATE TRIGGER IF NOT EXISTS
                guard_prototype_passed_lifecycle_insert
            BEFORE INSERT ON strategy_lifecycle_states
            WHEN NEW.state = 'prototype_passed'
            BEGIN
                SELECT CASE WHEN NOT EXISTS (
                    SELECT 1
                    FROM strategy_promotions p
                    JOIN human_confirmation_consumptions c
                      ON c.promotion_id = p.promotion_id
                    WHERE p.strategy_revision_id = NEW.strategy_revision_id
                      AND p.promotion_id = NEW.source_record_id
                ) THEN RAISE(
                    ABORT,
                    'prototype_passed requires promotion and consumed confirmation'
                ) END;
            END;
            """
        )
        for table_name in IMMUTABLE_TABLES:
            cursor.execute(
                f"""
                CREATE TRIGGER IF NOT EXISTS prevent_{table_name}_update
                BEFORE UPDATE ON {table_name}
                BEGIN
                    SELECT RAISE(ABORT, '{table_name} is append-only');
                END
                """
            )
            cursor.execute(
                f"""
                CREATE TRIGGER IF NOT EXISTS prevent_{table_name}_delete
                BEFORE DELETE ON {table_name}
                BEGIN
                    SELECT RAISE(ABORT, '{table_name} is append-only');
                END
                """
            )
        self.conn.commit()

    def list_table_names(self) -> set[str]:
        rows = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
        return {row["name"] for row in rows}

    @staticmethod
    def _json(model) -> str:
        return model.model_dump_json()

    def store_strategy_template(self, item: StrategyTemplateDefinition) -> None:
        self.conn.execute(
            """
            INSERT INTO strategy_template_definitions
            (template_id, version, payload_json, template_hash, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                item.template_id,
                item.version,
                self._json(item),
                item.template_hash,
                item.created_at.isoformat(),
            ),
        )
        self.conn.commit()

    def get_strategy_template(self, template_id: str, version: str):
        row = self.conn.execute(
            """
            SELECT payload_json FROM strategy_template_definitions
            WHERE template_id = ? AND version = ?
            """,
            (template_id, version),
        ).fetchone()
        return self._load(StrategyTemplateDefinition, row)

    def store_backtest_universe(self, item: BacktestUniverseSpec) -> None:
        self.conn.execute(
            """
            INSERT INTO backtest_universe_specs
            (universe_spec_id, payload_json, created_at)
            VALUES (?, ?, ?)
            """,
            (
                item.universe_spec_id,
                self._json(item),
                datetime.now().isoformat(),
            ),
        )
        self.conn.commit()

    def get_backtest_universe(self, universe_spec_id: str):
        row = self.conn.execute(
            """
            SELECT payload_json FROM backtest_universe_specs
            WHERE universe_spec_id = ?
            """,
            (universe_spec_id,),
        ).fetchone()
        return self._load(BacktestUniverseSpec, row)

    @staticmethod
    def _models_exact(expected, actual) -> bool:
        return expected.model_dump(mode="json") == actual.model_dump(mode="json")

    def materialize_strategy_provenance(
        self,
        template: StrategyTemplateDefinition,
        universe: BacktestUniverseSpec,
        draft: StrategyDraft,
        initial_state: StrategyLifecycleState,
    ) -> dict[str, dict[str, str]]:
        """Atomically get-or-create the four durable provenance records.

        Existing records are reusable only when their typed payloads are exact.
        Any same-key conflict aborts the whole transaction without overwriting.
        """
        if initial_state.strategy_revision_id != draft.strategy_revision_id:
            raise ValueError("initial lifecycle state must match draft")
        if initial_state.state != "draft" or initial_state.state_version != 1:
            raise ValueError("initial lifecycle state must be draft version 1")
        if draft.backtest_universe_spec_id != universe.universe_spec_id:
            raise ValueError("draft/universe binding mismatch")

        created: dict[str, str] = {}
        reused: dict[str, str] = {}

        def exact_or_missing(table: str, where: str, params: tuple, model_type, expected, label: str):
            row = self.conn.execute(
                f"SELECT payload_json FROM {table} WHERE {where}", params
            ).fetchone()
            if row is None:
                return False
            try:
                actual = model_type.model_validate_json(row["payload_json"])
            except Exception as exc:
                raise ValueError(f"strategy provenance conflict: {label} payload invalid: {exc}") from exc
            if not self._models_exact(expected, actual):
                raise ValueError(f"strategy provenance conflict: {label} content mismatch")
            reused[label] = (
                expected.template_id
                if label == "template"
                else expected.universe_spec_id
                if label == "universe"
                else expected.strategy_revision_id
                if label == "strategy_revision"
                else expected.lifecycle_state_id
            )
            return True

        try:
            self.conn.execute("BEGIN IMMEDIATE")

            if not exact_or_missing(
                "strategy_template_definitions",
                "template_id = ? AND version = ?",
                (template.template_id, template.version),
                StrategyTemplateDefinition,
                template,
                "template",
            ):
                self.conn.execute(
                    """
                    INSERT INTO strategy_template_definitions
                    (template_id, version, payload_json, template_hash, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        template.template_id,
                        template.version,
                        self._json(template),
                        template.template_hash,
                        template.created_at.isoformat(),
                    ),
                )
                created["template"] = template.template_id

            if not exact_or_missing(
                "backtest_universe_specs",
                "universe_spec_id = ?",
                (universe.universe_spec_id,),
                BacktestUniverseSpec,
                universe,
                "universe",
            ):
                self.conn.execute(
                    """
                    INSERT INTO backtest_universe_specs
                    (universe_spec_id, payload_json, created_at)
                    VALUES (?, ?, ?)
                    """,
                    (
                        universe.universe_spec_id,
                        self._json(universe),
                        universe.snapshot_date.isoformat(),
                    ),
                )
                created["universe"] = universe.universe_spec_id

            if not exact_or_missing(
                "strategy_drafts",
                "strategy_revision_id = ?",
                (draft.strategy_revision_id,),
                StrategyDraft,
                draft,
                "strategy_revision",
            ):
                self.conn.execute(
                    """
                    INSERT INTO strategy_drafts
                    (strategy_revision_id, theme_id, hypothesis_id,
                     backtest_universe_spec_id, payload_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        draft.strategy_revision_id,
                        draft.theme_id,
                        draft.hypothesis_id,
                        draft.backtest_universe_spec_id,
                        self._json(draft),
                        draft.created_at.isoformat(),
                    ),
                )
                created["strategy_revision"] = draft.strategy_revision_id

            if not exact_or_missing(
                "strategy_lifecycle_states",
                "strategy_revision_id = ? AND state_version = ?",
                (initial_state.strategy_revision_id, initial_state.state_version),
                StrategyLifecycleState,
                initial_state,
                "lifecycle",
            ):
                self.conn.execute(
                    """
                    INSERT INTO strategy_lifecycle_states
                    (lifecycle_state_id, strategy_revision_id, state_version,
                     state, source_record_id, payload_json, recorded_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        initial_state.lifecycle_state_id,
                        initial_state.strategy_revision_id,
                        initial_state.state_version,
                        initial_state.state,
                        initial_state.source_record_id,
                        self._json(initial_state),
                        initial_state.recorded_at.isoformat(),
                    ),
                )
                created["lifecycle"] = initial_state.lifecycle_state_id

            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

        return {"created_ids": created, "reused_ids": reused}

    def store_forward_watchlist(self, item: ForwardWatchlistSnapshot) -> None:
        self.conn.execute(
            """
            INSERT INTO forward_watchlist_snapshots
            (watchlist_snapshot_id, theme_id, payload_json, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                item.watchlist_snapshot_id,
                item.theme_id,
                self._json(item),
                item.created_at.isoformat(),
            ),
        )
        self.conn.commit()

    def create_strategy_draft(
        self,
        draft: StrategyDraft,
        initial_state: StrategyLifecycleState,
    ) -> None:
        if initial_state.strategy_revision_id != draft.strategy_revision_id:
            raise ValueError("initial lifecycle state must match draft")
        if initial_state.state != "draft" or initial_state.state_version != 1:
            raise ValueError("initial lifecycle state must be draft version 1")
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            self.conn.execute(
                """
                INSERT INTO strategy_drafts
                (strategy_revision_id, theme_id, hypothesis_id,
                 backtest_universe_spec_id, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    draft.strategy_revision_id,
                    draft.theme_id,
                    draft.hypothesis_id,
                    draft.backtest_universe_spec_id,
                    self._json(draft),
                    draft.created_at.isoformat(),
                ),
            )
            self.conn.execute(
                """
                INSERT INTO strategy_lifecycle_states
                (lifecycle_state_id, strategy_revision_id, state_version,
                 state, source_record_id, payload_json, recorded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    initial_state.lifecycle_state_id,
                    initial_state.strategy_revision_id,
                    initial_state.state_version,
                    initial_state.state,
                    initial_state.source_record_id,
                    self._json(initial_state),
                    initial_state.recorded_at.isoformat(),
                ),
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def store_protocol_snapshot(self, item: ResearchProtocolSnapshot) -> None:
        self.conn.execute(
            """
            INSERT INTO research_protocol_snapshots
            (protocol_snapshot_id, strategy_revision_id, payload_json,
             strategy_config_hash, data_snapshot_hash, gate_criteria_hash, frozen_at, protocol_profile)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.protocol_snapshot_id,
                item.strategy_revision_id,
                self._json(item),
                item.strategy_config_hash,
                item.data_snapshot_hash,
                item.gate_criteria_hash,
                item.frozen_at.isoformat(),
                item.protocol_profile,
            ),
        )
        self.conn.commit()

    def store_protocol_snapshot_exact(self, item: ResearchProtocolSnapshot) -> str:
        """Insert an immutable protocol, or reuse the exact deterministic payload."""
        row = self.conn.execute(
            "SELECT payload_json FROM research_protocol_snapshots WHERE protocol_snapshot_id = ?",
            (item.protocol_snapshot_id,),
        ).fetchone()
        if row is not None:
            try:
                existing = ResearchProtocolSnapshot.model_validate_json(row["payload_json"])
            except Exception as exc:
                raise ValueError(f"protocol snapshot conflict: existing payload invalid: {exc}") from exc
            if not self._models_exact(item, existing):
                raise ValueError("protocol snapshot conflict: content mismatch")
            return "reused"

        try:
            self.conn.execute("BEGIN IMMEDIATE")
            row = self.conn.execute(
                "SELECT payload_json FROM research_protocol_snapshots WHERE protocol_snapshot_id = ?",
                (item.protocol_snapshot_id,),
            ).fetchone()
            if row is not None:
                existing = ResearchProtocolSnapshot.model_validate_json(row["payload_json"])
                if not self._models_exact(item, existing):
                    raise ValueError("protocol snapshot conflict: content mismatch")
                self.conn.commit()
                return "reused"
            self.conn.execute(
                """
                INSERT INTO research_protocol_snapshots
                (protocol_snapshot_id, strategy_revision_id, payload_json,
                 strategy_config_hash, data_snapshot_hash, gate_criteria_hash, frozen_at, protocol_profile)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.protocol_snapshot_id,
                    item.strategy_revision_id,
                    self._json(item),
                    item.strategy_config_hash,
                    item.data_snapshot_hash,
                    item.gate_criteria_hash,
                    item.frozen_at.isoformat(),
                    item.protocol_profile,
                ),
            )
            self.conn.commit()
            return "created"
        except Exception:
            self.conn.rollback()
            raise

    def store_oos_ledger(self, item: OOSEvaluationLedger) -> None:
        """Store audit snapshot and commit. Use insert_oos_ledger_tx for transaction control."""
        self.insert_oos_ledger_tx(item)
        self.conn.commit()

    def insert_oos_ledger_tx(self, item: OOSEvaluationLedger) -> None:
        """Insert audit snapshot within caller's transaction (no commit)."""
        self.conn.execute(
            """
            INSERT INTO oos_evaluation_ledgers
            (ledger_snapshot_id, theme_id, hypothesis_source_snapshot_id, ledger_version, payload_json, recorded_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                item.ledger_snapshot_id,
                item.theme_id,
                item.hypothesis_source_snapshot_id,
                item.ledger_version,
                self._json(item),
                item.recorded_at.isoformat(),
            ),
        )

    def store_backtest_report(self, item: ImmutableBacktestReport) -> None:
        self.conn.execute(
            """
            INSERT INTO immutable_backtest_reports
            (report_id, strategy_revision_id, protocol_snapshot_id, payload_json,
             report_hash, integrity_status, generated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.report_id,
                item.strategy_revision_id,
                item.protocol_snapshot_id,
                self._json(item),
                item.report_hash,
                item.integrity_status,
                item.generated_at.isoformat(),
            ),
        )
        self.conn.commit()

    def store_gate_result(self, item: PrototypeGateResultV2) -> None:
        self.conn.execute(
            """
            INSERT INTO prototype_gate_results_v2
            (gate_result_id, strategy_revision_id, report_id,
             protocol_snapshot_id, verdict, payload_json,
             gate_result_hash, generated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.gate_result_id,
                item.strategy_revision_id,
                item.report_id,
                item.protocol_snapshot_id,
                item.verdict,
                self._json(item),
                item.gate_result_hash,
                item.generated_at.isoformat(),
            ),
        )
        self.conn.commit()

    def store_human_confirmation(self, item: HumanPromotionConfirmation) -> None:
        self.conn.execute(
            """
            INSERT INTO human_promotion_confirmations
            (human_confirmation_id, strategy_revision_id, gate_result_id,
             decision, payload_json, confirmed_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                item.human_confirmation_id,
                item.strategy_revision_id,
                item.gate_result_id,
                item.decision,
                self._json(item),
                item.confirmed_at.isoformat(),
            ),
        )
        self.conn.commit()

    def get_oos_budget_state(self, theme_id: str, hypothesis_source_snapshot_id: str) -> dict | None:
        """Get OOS budget state for owner. Returns None if not exists."""
        row = self.conn.execute(
            """
            SELECT consumed_draw_count, next_oos_draw_index, budget_status,
                   active_reservation_id, state_version, updated_at
            FROM oos_budget_state
            WHERE theme_id = ? AND hypothesis_source_snapshot_id = ?
            """,
            (theme_id, hypothesis_source_snapshot_id),
        ).fetchone()

        if row is None:
            return None

        return {
            "consumed_draw_count": row[0],
            "next_oos_draw_index": row[1],
            "budget_status": row[2],
            "active_reservation_id": row[3],
            "state_version": row[4],
            "updated_at": row[5],
        }

    @staticmethod
    def _load(model_type, row):
        if row is None:
            return None
        return model_type.model_validate_json(row["payload_json"])

    def get_strategy_draft(self, strategy_revision_id: str):
        row = self.conn.execute(
            """
            SELECT payload_json FROM strategy_drafts
            WHERE strategy_revision_id = ?
            """,
            (strategy_revision_id,),
        ).fetchone()
        return self._load(StrategyDraft, row)

    def get_protocol_snapshot(self, protocol_snapshot_id: str):
        row = self.conn.execute(
            """
            SELECT payload_json FROM research_protocol_snapshots
            WHERE protocol_snapshot_id = ?
            """,
            (protocol_snapshot_id,),
        ).fetchone()
        return self._load(ResearchProtocolSnapshot, row)

    def get_protocol_snapshot_by_revision_profile(
        self,
        strategy_revision_id: str,
        protocol_profile: str,
    ) -> ResearchProtocolSnapshot:
        """Resolve a revision/profile only when exactly one validated row exists."""
        rows = self.conn.execute(
            """
            SELECT payload_json
            FROM research_protocol_snapshots
            WHERE strategy_revision_id = ? AND protocol_profile = ?
            """,
            (strategy_revision_id, protocol_profile),
        ).fetchmany(2)
        if not rows:
            raise ProtocolSnapshotLookupError("protocol_snapshot_unavailable")
        if len(rows) > 1:
            raise ProtocolSnapshotLookupError("protocol_snapshot_ambiguous")
        snapshot = self._load(ResearchProtocolSnapshot, rows[0])
        if snapshot is None:
            raise ProtocolSnapshotLookupError("protocol_snapshot_unavailable")
        if (
            snapshot.strategy_revision_id != strategy_revision_id
            or snapshot.protocol_profile != protocol_profile
        ):
            raise ValueError("protocol snapshot lookup identity mismatch")
        return snapshot

    def get_backtest_report(self, report_id: str):
        row = self.conn.execute(
            """
            SELECT payload_json FROM immutable_backtest_reports
            WHERE report_id = ?
            """,
            (report_id,),
        ).fetchone()
        return self._load(ImmutableBacktestReport, row)

    def get_gate_result(self, gate_result_id: str):
        row = self.conn.execute(
            """
            SELECT payload_json FROM prototype_gate_results_v2
            WHERE gate_result_id = ?
            """,
            (gate_result_id,),
        ).fetchone()
        return self._load(PrototypeGateResultV2, row)

    def get_human_confirmation(self, human_confirmation_id: str):
        row = self.conn.execute(
            """
            SELECT payload_json FROM human_promotion_confirmations
            WHERE human_confirmation_id = ?
            """,
            (human_confirmation_id,),
        ).fetchone()
        return self._load(HumanPromotionConfirmation, row)

    def get_latest_lifecycle_state(self, strategy_revision_id: str):
        row = self.conn.execute(
            """
            SELECT payload_json
            FROM strategy_lifecycle_states
            WHERE strategy_revision_id = ?
            ORDER BY state_version DESC
            LIMIT 1
            """,
            (strategy_revision_id,),
        ).fetchone()
        return self._load(StrategyLifecycleState, row)

    def _get_promotion_by_strategy(self, strategy_revision_id: str):
        row = self.conn.execute(
            """
            SELECT payload_json FROM strategy_promotions
            WHERE strategy_revision_id = ?
            """,
            (strategy_revision_id,),
        ).fetchone()
        return self._load(StrategyPromotionRecord, row)

    def _confirmation_is_consumed(self, human_confirmation_id: str) -> bool:
        row = self.conn.execute(
            """
            SELECT 1 FROM human_confirmation_consumptions
            WHERE human_confirmation_id = ?
            """,
            (human_confirmation_id,),
        ).fetchone()
        return row is not None

    def _commit_validated_promotion(
        self,
        promotion: StrategyPromotionRecord,
        consumption: HumanConfirmationConsumption,
        lifecycle_state: StrategyLifecycleState,
    ) -> None:
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            self.conn.execute(
                """
                INSERT INTO strategy_promotions
                (promotion_id, strategy_revision_id, gate_result_id, report_id,
                 protocol_snapshot_id, human_confirmation_id, payload_json,
                 promoted_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    promotion.promotion_id,
                    promotion.strategy_revision_id,
                    promotion.gate_result_id,
                    promotion.report_id,
                    promotion.protocol_snapshot_id,
                    promotion.human_confirmation_id,
                    self._json(promotion),
                    promotion.promoted_at.isoformat(),
                ),
            )
            self.conn.execute(
                """
                INSERT INTO human_confirmation_consumptions
                (consumption_id, human_confirmation_id, strategy_revision_id,
                 gate_result_id, promotion_id, payload_json, consumed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    consumption.consumption_id,
                    consumption.human_confirmation_id,
                    consumption.strategy_revision_id,
                    consumption.gate_result_id,
                    consumption.promotion_id,
                    self._json(consumption),
                    consumption.consumed_at.isoformat(),
                ),
            )
            self.conn.execute(
                """
                INSERT INTO strategy_lifecycle_states
                (lifecycle_state_id, strategy_revision_id, state_version,
                 state, source_record_id, payload_json, recorded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    lifecycle_state.lifecycle_state_id,
                    lifecycle_state.strategy_revision_id,
                    lifecycle_state.state_version,
                    lifecycle_state.state,
                    lifecycle_state.source_record_id,
                    self._json(lifecycle_state),
                    lifecycle_state.recorded_at.isoformat(),
                ),
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
