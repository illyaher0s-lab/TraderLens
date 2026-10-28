"""SQLite persistence for the fixed Card020 strategy review and run records."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone


CONFIRMATION_RECORD = "explicit_page_checkbox"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class Card020Conflict(ValueError):
    pass


class Card020Store:
    """Narrow tables on the existing ResearchDB connection; never touches trade ledgers."""

    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection
        self._lock = threading.RLock()
        self.connection.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self) -> None:
        with self._lock:
            self.connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS card020_parses (
                    parse_id TEXT PRIMARY KEY,
                    protocol_sha256 TEXT NOT NULL,
                    source_sha256 TEXT NOT NULL,
                    source_text TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (status IN ('ready_for_confirmation', 'blocked', 'provider_error')),
                    result_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_card020_parses_created
                    ON card020_parses(created_at DESC);

                CREATE TABLE IF NOT EXISTS card020_preflights (
                    preflight_id TEXT PRIMARY KEY,
                    protocol_sha256 TEXT NOT NULL,
                    input_inventory_sha256 TEXT,
                    execution_bundle_sha256 TEXT,
                    status TEXT NOT NULL,
                    preflight_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_card020_preflights_created
                    ON card020_preflights(created_at DESC);

                CREATE TABLE IF NOT EXISTS card020_frozen_strategies (
                    strategy_id TEXT PRIMARY KEY,
                    freeze_id TEXT NOT NULL UNIQUE,
                    parse_id TEXT NOT NULL UNIQUE REFERENCES card020_parses(parse_id),
                    protocol_sha256 TEXT NOT NULL,
                    source_sha256 TEXT NOT NULL,
                    fields_json TEXT NOT NULL,
                    source_mappings_json TEXT NOT NULL,
                    line_coverage_json TEXT NOT NULL,
                    source_text TEXT NOT NULL,
                    preflight_id TEXT NOT NULL REFERENCES card020_preflights(preflight_id),
                    input_inventory_sha256 TEXT NOT NULL,
                    input_inventory_json TEXT NOT NULL,
                    executor_version TEXT NOT NULL,
                    execution_bundle_sha256 TEXT NOT NULL,
                    execution_files_json TEXT NOT NULL,
                    freeze_sha256 TEXT NOT NULL UNIQUE,
                    confirmed_at TEXT NOT NULL,
                    confirmation_phrase TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS card020_runs (
                    run_id TEXT PRIMARY KEY,
                    freeze_id TEXT NOT NULL REFERENCES card020_frozen_strategies(freeze_id),
                    idempotency_key TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
                    result_json TEXT,
                    error_code TEXT,
                    started_at TEXT NOT NULL,
                    completed_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_card020_runs_started
                    ON card020_runs(started_at DESC);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_card020_runs_freeze
                    ON card020_runs(freeze_id);

                CREATE TRIGGER IF NOT EXISTS card020_frozen_immutable_update
                BEFORE UPDATE ON card020_frozen_strategies
                BEGIN SELECT RAISE(ABORT, 'Card020 frozen strategy is immutable'); END;
                CREATE TRIGGER IF NOT EXISTS card020_frozen_immutable_delete
                BEFORE DELETE ON card020_frozen_strategies
                BEGIN SELECT RAISE(ABORT, 'Card020 frozen strategy is immutable'); END;

                CREATE TRIGGER IF NOT EXISTS card020_completed_run_immutable
                BEFORE UPDATE ON card020_runs
                WHEN OLD.status <> 'running'
                BEGIN SELECT RAISE(ABORT, 'Card020 completed run is immutable'); END;
                CREATE TRIGGER IF NOT EXISTS card020_run_no_delete
                BEFORE DELETE ON card020_runs
                BEGIN SELECT RAISE(ABORT, 'Card020 run history is immutable'); END;
                """
            )
            self._ensure_columns(
                "card020_frozen_strategies",
                {
                    "preflight_id": "TEXT",
                    "input_inventory_sha256": "TEXT",
                    "input_inventory_json": "TEXT",
                    "executor_version": "TEXT",
                    "execution_bundle_sha256": "TEXT",
                    "execution_files_json": "TEXT",
                },
            )
            self.connection.commit()

    def _ensure_columns(self, table: str, columns: dict[str, str]) -> None:
        existing = {row[1] for row in self.connection.execute(f"PRAGMA table_info({table})")}
        for name, declaration in columns.items():
            if name not in existing:
                self.connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")

    @staticmethod
    def _row(row: sqlite3.Row | None) -> dict | None:
        return dict(row) if row is not None else None

    def record_parse(
        self,
        *,
        protocol_sha256: str,
        source_text: str,
        result: dict,
        status: str,
    ) -> dict:
        if status not in {"ready_for_confirmation", "blocked", "provider_error"}:
            raise ValueError("invalid Card020 parse status")
        source_hash = hashlib.sha256(source_text.encode("utf-8")).hexdigest().upper()
        parse_id = f"card020_parse_{uuid.uuid4().hex}"
        created_at = _utc_now()
        with self._lock:
            self.connection.execute(
                """INSERT INTO card020_parses
                   (parse_id, protocol_sha256, source_sha256, source_text, status, result_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (parse_id, protocol_sha256, source_hash, source_text, status, _json(result), created_at),
            )
            self.connection.commit()
        return {
            "parse_id": parse_id,
            "protocol_sha256": protocol_sha256,
            "source_sha256": source_hash,
            "status": status,
            "created_at": created_at,
            "result": result,
        }

    def get_parse(self, parse_id: str) -> dict | None:
        with self._lock:
            row = self.connection.execute(
                "SELECT * FROM card020_parses WHERE parse_id = ?", (parse_id,),
            ).fetchone()
        result = self._row(row)
        if result is not None:
            result["result"] = json.loads(result.pop("result_json"))
        return result

    def record_preflight(self, preflight: dict) -> dict:
        preflight_id = preflight["preflight_id"]
        created_at = _utc_now()
        with self._lock:
            self.connection.execute(
                """INSERT INTO card020_preflights
                   (preflight_id, protocol_sha256, input_inventory_sha256,
                    execution_bundle_sha256, status, preflight_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    preflight_id, preflight.get("protocol_sha256"),
                    preflight.get("input_inventory_sha256"),
                    (preflight.get("execution_fingerprint") or {}).get("bundle_sha256"),
                    preflight["status"], _json(preflight), created_at,
                ),
            )
            self.connection.commit()
        return {**preflight, "created_at": created_at}

    def get_preflight(self, preflight_id: str) -> dict | None:
        with self._lock:
            row = self.connection.execute(
                "SELECT preflight_json, created_at FROM card020_preflights WHERE preflight_id = ?",
                (preflight_id,),
            ).fetchone()
        if row is None:
            return None
        return {**json.loads(row["preflight_json"]), "created_at": row["created_at"]}

    def latest_preflight(self) -> dict | None:
        with self._lock:
            row = self.connection.execute(
                "SELECT preflight_json, created_at FROM card020_preflights ORDER BY created_at DESC LIMIT 1",
            ).fetchone()
        if row is None:
            return None
        return {**json.loads(row["preflight_json"]), "created_at": row["created_at"]}

    def freeze_parse(
        self, parse_id: str, preflight_id: str, confirmed: bool, source_sha256: str,
        protocol_sha256: str,
    ) -> dict:
        if confirmed is not True:
            raise Card020Conflict("confirmation_required")
        with self._lock:
            row = self.connection.execute(
                "SELECT * FROM card020_parses WHERE parse_id = ?", (parse_id,),
            ).fetchone()
            if row is None:
                raise Card020Conflict("parse_not_found")
            parse = dict(row)
            existing = self.connection.execute(
                "SELECT * FROM card020_frozen_strategies WHERE strategy_id = ?",
                ("510880-vol-budget-v1",),
            ).fetchone()
            if existing is not None:
                frozen = dict(existing)
                if frozen["parse_id"] == parse_id:
                    return self._public_freeze(frozen)
                raise Card020Conflict("strategy_already_frozen")
            if parse["status"] != "ready_for_confirmation":
                raise Card020Conflict("parse_not_ready")
            if parse["protocol_sha256"] != protocol_sha256:
                raise Card020Conflict("protocol_hash_mismatch")
            if parse["source_sha256"] != source_sha256:
                raise Card020Conflict("source_hash_mismatch")

            preflight_row = self.connection.execute(
                "SELECT preflight_json FROM card020_preflights WHERE preflight_id = ?",
                (preflight_id,),
            ).fetchone()
            if preflight_row is None:
                raise Card020Conflict("preflight_not_found")
            preflight = json.loads(preflight_row["preflight_json"])
            if (
                preflight.get("status") != "passed_with_disclosed_data_limits"
                or preflight.get("protocol_sha256") != protocol_sha256
                or preflight.get("historical_metrics_computed") is not False
            ):
                raise Card020Conflict("preflight_not_ready")

            result = json.loads(parse["result_json"])
            if result.get("status") != "ready_for_confirmation":
                raise Card020Conflict("parse_not_ready")
            if result.get("source_sha256") != parse["source_sha256"]:
                raise Card020Conflict("source_hash_mismatch")
            parser_hash = result.get("parser_sha256")
            expected_parser_hash = (preflight.get("execution_fingerprint") or {}).get("files", {}).get(
                "backend/services/strategy_idea_flow.py"
            )
            if not parser_hash or parser_hash != expected_parser_hash:
                raise Card020Conflict("parser_code_changed_after_parse")
            confirmed_at = _utc_now()
            freeze_id = f"card020_freeze_{uuid.uuid4().hex}"
            freeze_body = {
                "freeze_id": freeze_id,
                "strategy_id": "510880-vol-budget-v1",
                "parse_id": parse_id,
                "protocol_sha256": protocol_sha256,
                "source_sha256": parse["source_sha256"],
                "fields": result["fields"],
                "source_mappings": result["source_mappings"],
                "line_coverage": result["line_coverage"],
                "preflight_id": preflight_id,
                "input_inventory_sha256": preflight["input_inventory_sha256"],
                "input_inventory": preflight["input_inventory"],
                "executor_version": preflight["execution_fingerprint"]["executor_version"],
                "execution_bundle_sha256": preflight["execution_fingerprint"]["bundle_sha256"],
                "execution_files": preflight["execution_fingerprint"]["files"],
                "confirmed_at": confirmed_at,
                "confirmation_phrase": CONFIRMATION_RECORD,
            }
            freeze_hash = hashlib.sha256(_json(freeze_body).encode("utf-8")).hexdigest().upper()
            self.connection.execute(
                """INSERT INTO card020_frozen_strategies
                   (strategy_id, freeze_id, parse_id, protocol_sha256, source_sha256,
                    fields_json, source_mappings_json, line_coverage_json, source_text,
                    preflight_id, input_inventory_sha256, input_inventory_json,
                    executor_version, execution_bundle_sha256, execution_files_json,
                    freeze_sha256, confirmed_at, confirmation_phrase)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    "510880-vol-budget-v1", freeze_id, parse_id, protocol_sha256,
                    parse["source_sha256"], _json(result["fields"]),
                    _json(result["source_mappings"]), _json(result["line_coverage"]),
                    parse["source_text"], preflight_id, preflight["input_inventory_sha256"],
                    _json(preflight["input_inventory"]), preflight["execution_fingerprint"]["executor_version"],
                    preflight["execution_fingerprint"]["bundle_sha256"],
                    _json(preflight["execution_fingerprint"]["files"]), freeze_hash,
                    confirmed_at, CONFIRMATION_RECORD,
                ),
            )
            self.connection.commit()
            frozen = self.connection.execute(
                "SELECT * FROM card020_frozen_strategies WHERE freeze_id = ?", (freeze_id,),
            ).fetchone()
        return self._public_freeze(dict(frozen))

    @staticmethod
    def _public_freeze(row: dict) -> dict:
        return {
            "strategy_id": row["strategy_id"],
            "freeze_id": row["freeze_id"],
            "parse_id": row["parse_id"],
            "protocol_sha256": row["protocol_sha256"],
            "source_sha256": row["source_sha256"],
            "fields": json.loads(row["fields_json"]),
            "source_mappings": json.loads(row["source_mappings_json"]),
            "line_coverage": json.loads(row["line_coverage_json"]),
            "preflight_id": row.get("preflight_id"),
            "input_inventory_sha256": row.get("input_inventory_sha256"),
            "input_inventory": json.loads(row["input_inventory_json"]) if row.get("input_inventory_json") else None,
            "executor_version": row.get("executor_version"),
            "execution_bundle_sha256": row.get("execution_bundle_sha256"),
            "execution_files": json.loads(row["execution_files_json"]) if row.get("execution_files_json") else None,
            "freeze_sha256": row["freeze_sha256"],
            "confirmed_at": row["confirmed_at"],
        }

    def get_frozen(self, freeze_id: str | None = None) -> dict | None:
        query = "SELECT * FROM card020_frozen_strategies"
        args: tuple = ()
        if freeze_id:
            query += " WHERE freeze_id = ?"
            args = (freeze_id,)
        else:
            query += " WHERE strategy_id = ?"
            args = ("510880-vol-budget-v1",)
        with self._lock:
            row = self.connection.execute(query, args).fetchone()
        if row is None:
            return None
        frozen = dict(row)
        public = self._public_freeze(frozen)
        public["source_text"] = frozen["source_text"]
        return public

    def begin_run(self, freeze_id: str, idempotency_key: str) -> tuple[bool, dict]:
        with self._lock:
            existing = self.connection.execute(
                "SELECT * FROM card020_runs WHERE idempotency_key = ?", (idempotency_key,),
            ).fetchone()
            if existing is not None:
                run = self._public_run(dict(existing))
                if run["freeze_id"] != freeze_id:
                    raise Card020Conflict("idempotency_key_reused")
                return False, run
            existing_for_freeze = self.connection.execute(
                "SELECT * FROM card020_runs WHERE freeze_id = ?", (freeze_id,),
            ).fetchone()
            if existing_for_freeze is not None:
                raise Card020Conflict("freeze_already_run")
            frozen = self.connection.execute(
                "SELECT 1 FROM card020_frozen_strategies WHERE freeze_id = ?", (freeze_id,),
            ).fetchone()
            if frozen is None:
                raise Card020Conflict("freeze_not_found")
            run_id = f"card020_run_{uuid.uuid4().hex}"
            started_at = _utc_now()
            self.connection.execute(
                """INSERT INTO card020_runs
                   (run_id, freeze_id, idempotency_key, status, started_at)
                   VALUES (?, ?, ?, 'running', ?)""",
                (run_id, freeze_id, idempotency_key, started_at),
            )
            self.connection.commit()
            return True, {
                "run_id": run_id, "freeze_id": freeze_id,
                "idempotency_key": idempotency_key, "status": "running",
                "result": None, "error_code": None, "started_at": started_at,
                "completed_at": None,
            }

    def finish_run(self, run_id: str, *, result: dict | None, error_code: str | None = None) -> dict:
        status = "completed" if result is not None else "failed"
        completed_at = _utc_now()
        with self._lock:
            cursor = self.connection.execute(
                """UPDATE card020_runs SET status = ?, result_json = ?, error_code = ?, completed_at = ?
                   WHERE run_id = ? AND status = 'running'""",
                (status, _json(result) if result is not None else None, error_code, completed_at, run_id),
            )
            if cursor.rowcount != 1:
                raise Card020Conflict("run_not_running")
            self.connection.commit()
            row = self.connection.execute(
                "SELECT * FROM card020_runs WHERE run_id = ?", (run_id,),
            ).fetchone()
        return self._public_run(dict(row))

    def get_run(self, run_id: str) -> dict | None:
        with self._lock:
            row = self.connection.execute(
                "SELECT * FROM card020_runs WHERE run_id = ?", (run_id,),
            ).fetchone()
        return self._public_run(dict(row)) if row is not None else None

    def list_runs(self, limit: int = 20) -> list[dict]:
        with self._lock:
            rows = self.connection.execute(
                "SELECT * FROM card020_runs ORDER BY started_at DESC LIMIT ?", (limit,),
            ).fetchall()
        return [self._public_run(dict(row), include_result=False) for row in rows]

    @staticmethod
    def _public_run(row: dict, *, include_result: bool = True) -> dict:
        result = {
            key: row.get(key)
            for key in (
                "run_id", "freeze_id", "idempotency_key", "status",
                "error_code", "started_at", "completed_at",
            )
        }
        if include_result:
            result["result"] = json.loads(row["result_json"]) if row.get("result_json") else None
        return result

    def get_state(self) -> dict:
        frozen = self.get_frozen()
        if frozen is not None:
            frozen.pop("source_text", None)
        with self._lock:
            latest = self.connection.execute(
                "SELECT * FROM card020_parses ORDER BY created_at DESC LIMIT 1",
            ).fetchone()
        latest_parse = self._row(latest)
        if latest_parse is not None:
            latest_parse["result"] = json.loads(latest_parse.pop("result_json"))
            latest_parse.pop("source_text", None)
        return {
            "protocol_sha256": None,
            "latest_parse": latest_parse,
            "latest_preflight": self.latest_preflight(),
            "frozen": frozen,
            "runs": self.list_runs(),
        }
