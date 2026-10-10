"""Run the registered migration-005 owner once, with a server-owned backup."""

from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import base64
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from typing import Any, Callable, TextIO

from backend.db.migrations.migration_005_add_b6_successor_attempt import (
    migrate_add_b6_successor_attempt,
)


MIGRATION_ID = "migration_005_add_b6_successor_attempt"
BACKUP_SCHEMA_VERSION = "b6_schema_migration_backup.v1"
PROGRESS_SCHEMA_VERSION = "b6_successor_migration_progress.v1"
RESULT_SCHEMA_VERSION = "b6_successor_migration.cli.v1"
EXIT_OK = 0
EXIT_BLOCKED = 20
EXIT_INVALID_INVOCATION = 64
EXIT_OWNER_FAILURE = 70

_PROGRESS_STAGES = {
    "preflight",
    "backup",
    "migration",
    "terminal",
    "blocked",
    "failed",
}
_PROTECTED_EVIDENCE_TABLES = (
    "oos_budget_state",
    "oos_budget_reservations",
    "oos_evaluation_ledgers",
    "immutable_backtest_reports",
    "prototype_gate_results_v2",
    "strategy_promotions",
    "human_promotion_confirmations",
    "human_confirmation_consumptions",
)
_REQUIRED_TABLE_COLUMNS = {
    "b6_validation_tasks": {
        "task_id",
        "task_key",
        "task_type",
        "task_contract_version",
        "strategy_revision_id",
        "protocol_snapshot_id",
        "status",
        "blocking_reason_code",
        "blocking_reason_detail",
        "payload_json",
        "created_at",
        "claimed_at",
        "completed_at",
        "b5_bundle_id",
        "b5_bundle_manifest_sha256",
    },
    "research_protocol_snapshots": {
        "protocol_snapshot_id",
        "strategy_revision_id",
        "payload_json",
        "strategy_config_hash",
        "data_snapshot_hash",
        "gate_criteria_hash",
        "frozen_at",
        "protocol_profile",
    },
    "oos_evaluation_ledgers": {"hypothesis_source_snapshot_id"},
    "oos_budget_reservations": {"task_key", "protocol_snapshot_id"},
}
_EXPECTED_MIGRATION_004_INDEX = "idx_protocol_b6_profile_per_revision"
_REMOVED_MIGRATION_004_INDEX = "uq_protocol_b6_profile_per_revision"
_SUCCESSOR_COLUMNS = (
    "predecessor_task_id",
    "predecessor_task_key",
    "successor_attempt_number",
)
_EXPECTED_SUCCESSOR_INDEX = "uq_b6_direct_successor_predecessor"
_PRE_MIGRATION_SNAPSHOT_FIELDS = (
    "health",
    "schema_objects",
    "task_snapshot",
    "protected_counts",
    "migration_registry",
    "migration_005_state",
)


class MigrationOwnerBlocked(RuntimeError):
    """A preflight or backup invariant blocks the migration."""

    def __init__(self, reason: str, detail: str | None = None):
        super().__init__(detail or reason)
        self.reason = reason
        self.detail = detail


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _canonical_json(value: dict[str, Any]) -> str:
    return _canonical_bytes(value).decode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _sqlite_ro_uri(path: Path) -> str:
    return f"file:{path.resolve().as_posix()}?mode=ro"


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _encode_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, bytes):
        return {"__bytes__": base64.b64encode(value).decode("ascii")}
    return {"__repr__": repr(value)}


def _schema_objects(conn: sqlite3.Connection) -> list[list[Any]]:
    return [
        [_encode_value(value) for value in row]
        for row in conn.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
        )
    ]


def _table_columns(conn: sqlite3.Connection, table: str) -> list[tuple[Any, ...]]:
    return [tuple(row) for row in conn.execute(f"PRAGMA table_info({_quote_identifier(table)})")]


def _table_rows(conn: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    columns = [row[1] for row in _table_columns(conn, table)]
    if not columns:
        return []
    rows = []
    for row in conn.execute(f"SELECT * FROM {_quote_identifier(table)} ORDER BY rowid"):
        item = {column: _encode_value(value) for column, value in zip(columns, row)}
        if "payload_json" in item and isinstance(row[columns.index("payload_json")], str):
            item["payload_json_bytes"] = base64.b64encode(
                row[columns.index("payload_json")].encode("utf-8")
            ).decode("ascii")
        rows.append(item)
    return rows


def _health(conn: sqlite3.Connection) -> dict[str, Any]:
    quick = conn.execute("PRAGMA quick_check").fetchall()
    foreign_keys = [list(row) for row in conn.execute("PRAGMA foreign_key_check")]
    return {
        "quick_check": quick[0][0] if len(quick) == 1 else [list(row) for row in quick],
        "foreign_key_check": foreign_keys,
    }


def _index_sql(conn: sqlite3.Connection, name: str) -> str | None:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='index' AND name = ?", (name,)
    ).fetchone()
    return None if row is None else row[0]


def _normal_sql(sql: str | None) -> str | None:
    return None if sql is None else " ".join(sql.split())


def _schema_object_map(objects: list[list[Any]]) -> dict[tuple[Any, ...], list[Any]] | None:
    mapped: dict[tuple[Any, ...], list[Any]] = {}
    for row in objects:
        key = tuple(row[:3])
        if key in mapped:
            return None
        mapped[key] = row
    return mapped


def _post_schema_objects_are_exact(
    pre_objects: list[list[Any]], post_objects: list[list[Any]]
) -> bool:
    pre_by_key = _schema_object_map(pre_objects)
    post_by_key = _schema_object_map(post_objects)
    if pre_by_key is None or post_by_key is None:
        return False
    changed_table = ("table", "b6_validation_tasks", "b6_validation_tasks")
    expected_new_index = (
        "index",
        _EXPECTED_SUCCESSOR_INDEX,
        "b6_validation_tasks",
    )
    if set(post_by_key) != set(pre_by_key) | {expected_new_index}:
        return False
    for key, pre_row in pre_by_key.items():
        if key != changed_table and post_by_key[key] != pre_row:
            return False
    return changed_table in pre_by_key


def _protected_counts(conn: sqlite3.Connection) -> dict[str, int]:
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    return {
        table: int(
            conn.execute(
                f"SELECT COUNT(*) FROM {_quote_identifier(table)}"
            ).fetchone()[0]
        )
        for table in _PROTECTED_EVIDENCE_TABLES
        if table in tables
    }


def _task_row_snapshot(conn: sqlite3.Connection) -> dict[str, Any]:
    columns = _table_columns(conn, "b6_validation_tasks")
    names = [row[1] for row in columns]
    rows = _table_rows(conn, "b6_validation_tasks")
    return {
        "columns": [[_encode_value(value) for value in row] for row in columns],
        "column_names": names,
        "rows": rows,
        "sha256": _sha256_bytes(_canonical_bytes({"columns": columns, "rows": rows})),
    }


def _snapshot_connection(conn: sqlite3.Connection) -> dict[str, Any]:
    health = _health(conn)
    if health["quick_check"] != "ok":
        raise MigrationOwnerBlocked(
            "b6_schema_migration_preflight_health_failed",
            f"quick_check={health['quick_check']}",
        )
    if health["foreign_key_check"]:
        raise MigrationOwnerBlocked(
            "b6_schema_migration_preflight_health_failed",
            "foreign_key_check is not empty",
        )
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    for table, required_columns in _REQUIRED_TABLE_COLUMNS.items():
        if table not in tables:
            raise MigrationOwnerBlocked(
                "b6_schema_migration_preflight_shape_invalid",
                f"required table missing: {table}",
            )
        actual_columns = {row[1] for row in _table_columns(conn, table)}
        missing = sorted(required_columns - actual_columns)
        if missing:
            raise MigrationOwnerBlocked(
                "b6_schema_migration_preflight_shape_invalid",
                f"required columns missing from {table}: {missing}",
            )

    if _index_sql(conn, _EXPECTED_MIGRATION_004_INDEX) is None:
        raise MigrationOwnerBlocked(
            "b6_schema_migration_preflight_shape_invalid",
            "migration 004 nonunique index is missing",
        )
    if _index_sql(conn, _REMOVED_MIGRATION_004_INDEX) is not None:
        raise MigrationOwnerBlocked(
            "b6_schema_migration_preflight_shape_invalid",
            "migration 004 partial unique index is still present",
        )

    task_columns = {row[1]: row for row in _table_columns(conn, "b6_validation_tasks")}
    present_successor_columns = set(task_columns).intersection(_SUCCESSOR_COLUMNS)
    successor_index_sql = _index_sql(conn, _EXPECTED_SUCCESSOR_INDEX)
    if not present_successor_columns and successor_index_sql is None:
        state = "not_applied"
    elif (
        present_successor_columns == set(_SUCCESSOR_COLUMNS)
        and _successor_shape_is_exact(conn, task_columns, successor_index_sql)
    ):
        state = "already_applied"
    else:
        raise MigrationOwnerBlocked(
            "b6_schema_migration_partial_or_invalid",
            "migration 005 is partially present or malformed",
        )

    return {
        "health": health,
        "schema_objects": _schema_objects(conn),
        "task_snapshot": _task_row_snapshot(conn),
        "protected_counts": _protected_counts(conn),
        "migration_registry": "absent",
        "migration_005_state": state,
    }


def _successor_shape_is_exact(
    conn: sqlite3.Connection,
    task_columns: dict[str, tuple[Any, ...]],
    index_sql: str | None,
) -> bool:
    expected_types = {
        "predecessor_task_id": "TEXT",
        "predecessor_task_key": "TEXT",
        "successor_attempt_number": "INTEGER",
    }
    for name, expected_type in expected_types.items():
        row = task_columns.get(name)
        if row is None or row[2].upper() != expected_type or row[3] != 0 or row[4] is not None:
            return False
    if _normal_sql(index_sql) != (
        "CREATE UNIQUE INDEX uq_b6_direct_successor_predecessor "
        "ON b6_validation_tasks(predecessor_task_id) "
        "WHERE predecessor_task_id IS NOT NULL"
    ):
        return False
    index_list = {
        row[1]: tuple(row)
        for row in conn.execute("PRAGMA index_list('b6_validation_tasks')")
    }
    listed = index_list.get(_EXPECTED_SUCCESSOR_INDEX)
    if listed is None or listed[2] != 1 or listed[4] != 1:
        return False
    index_columns = [
        row[2]
        for row in conn.execute(
            "PRAGMA index_info('uq_b6_direct_successor_predecessor')"
        )
    ]
    if index_columns != ["predecessor_task_id"]:
        return False
    foreign_keys = [
        tuple(row)
        for row in conn.execute("PRAGMA foreign_key_list('b6_validation_tasks')")
    ]
    return any(
        row[2:5]
        == ("b6_validation_tasks", "predecessor_task_id", "task_id")
        for row in foreign_keys
    )


def _preflight(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise MigrationOwnerBlocked(
            "b6_schema_migration_preflight_missing",
            f"database is missing: {path}",
        )
    stat_before = path.stat()
    source_sha = _sha256_file(path)
    with closing(sqlite3.connect(_sqlite_ro_uri(path), uri=True)) as conn:
        snapshot = _snapshot_connection(conn)
    stat_after = path.stat()
    after_sha = _sha256_file(path)
    if (
        stat_before.st_size != stat_after.st_size
        or stat_before.st_mtime_ns != stat_after.st_mtime_ns
        or source_sha != after_sha
    ):
        raise MigrationOwnerBlocked(
            "b6_schema_migration_source_drift",
            "source database changed during read-only preflight",
        )
    return {
        "path": str(path.resolve()),
        "sha256": source_sha,
        "size_bytes": stat_before.st_size,
        "mtime_ns": stat_before.st_mtime_ns,
        **snapshot,
    }


def _manifest_paths(target: Path) -> tuple[Path, Path]:
    manifest = target.with_name(target.name + ".manifest.json")
    return manifest, manifest.with_name(manifest.name + ".sha256")


def _backup_info_from_files(
    target: Path,
    manifest_path: Path,
    sidecar_path: Path,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    return {
        "backup_id": manifest["backup_id"],
        "backup_path": str(target.resolve()),
        "backup_manifest_path": str(manifest_path.resolve()),
        "backup_manifest_sidecar_path": str(sidecar_path.resolve()),
        "backup_db_sha256": _sha256_file(target),
        "backup_manifest_sha256": _sha256_file(manifest_path),
    }


def _read_existing_backup(
    *,
    target: Path,
    manifest_path: Path,
    sidecar_path: Path,
    preflight: dict[str, Any],
) -> dict[str, Any]:
    if not target.is_file() or not manifest_path.is_file() or not sidecar_path.is_file():
        raise MigrationOwnerBlocked(
            "b6_schema_migration_backup_conflict",
            "migration backup has partial existing files",
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MigrationOwnerBlocked(
            "b6_schema_migration_backup_conflict",
            f"migration backup manifest is invalid: {exc}",
        ) from exc
    expected_id = f"b6_schema_migration:{preflight['sha256']}"
    if (
        manifest.get("schema_version") != BACKUP_SCHEMA_VERSION
        or manifest.get("migration_id") != MIGRATION_ID
        or manifest.get("source_db_sha256") != preflight["sha256"]
        or manifest.get("source_size_bytes") != preflight["size_bytes"]
        or manifest.get("source_mtime_ns") != preflight["mtime_ns"]
        or manifest.get("source_path") != preflight["path"]
        or manifest.get("backup_id") != expected_id
    ):
        raise MigrationOwnerBlocked(
            "b6_schema_migration_backup_conflict",
            "migration backup source identity conflicts",
        )
    manifest_sha = _sha256_file(manifest_path)
    sidecar = sidecar_path.read_text(encoding="utf-8").split()
    if not sidecar or sidecar[0] != manifest_sha:
        raise MigrationOwnerBlocked(
            "b6_schema_migration_backup_conflict",
            "migration backup manifest sidecar mismatch",
        )
    if manifest.get("backup_db_sha256") != _sha256_file(target):
        raise MigrationOwnerBlocked(
            "b6_schema_migration_backup_conflict",
            "migration backup database hash mismatch",
        )
    with closing(sqlite3.connect(_sqlite_ro_uri(target), uri=True)) as conn:
        backup_snapshot = _snapshot_connection(conn)
    if backup_snapshot != {
        key: preflight[key] for key in _PRE_MIGRATION_SNAPSHOT_FIELDS
    }:
        raise MigrationOwnerBlocked(
            "b6_schema_migration_backup_conflict",
            "migration backup snapshot mismatch",
        )
    return _backup_info_from_files(target, manifest_path, sidecar_path, manifest)


def _fsync_file(path: Path) -> None:
    with path.open("r+b") as handle:
        os.fsync(handle.fileno())


def _create_backup(path: Path, backup_root: Path, preflight: dict[str, Any]) -> dict[str, Any]:
    backup_root = Path(backup_root).resolve()
    target = backup_root / f"migration_005.{preflight['sha256']}.sqlite3"
    manifest_path, sidecar_path = _manifest_paths(target)
    if target.exists() or manifest_path.exists() or sidecar_path.exists():
        return _read_existing_backup(
            target=target,
            manifest_path=manifest_path,
            sidecar_path=sidecar_path,
            preflight=preflight,
        )

    try:
        backup_root.mkdir(parents=True, exist_ok=True)
        staging = Path(
            tempfile.mkdtemp(prefix=f".{target.name}.staging-", dir=str(backup_root))
        )
    except OSError as exc:
        raise MigrationOwnerBlocked(
            "b6_schema_migration_backup_failed", str(exc)
        ) from exc
    staged_db = staging / target.name
    staged_manifest = staging / manifest_path.name
    staged_sidecar = staging / sidecar_path.name
    published: list[Path] = []
    try:
        with closing(sqlite3.connect(_sqlite_ro_uri(path), uri=True)) as source_conn:
            with closing(sqlite3.connect(str(staged_db))) as destination_conn:
                source_conn.backup(destination_conn)
                destination_conn.commit()
        _fsync_file(staged_db)
        with closing(sqlite3.connect(_sqlite_ro_uri(staged_db), uri=True)) as backup_conn:
            with closing(sqlite3.connect(_sqlite_ro_uri(path), uri=True)) as source_conn:
                backup_snapshot = _snapshot_connection(backup_conn)
                source_snapshot = _snapshot_connection(source_conn)
        expected_snapshot = {
            key: preflight[key] for key in _PRE_MIGRATION_SNAPSHOT_FIELDS
        }
        if backup_snapshot != expected_snapshot or source_snapshot != expected_snapshot:
            raise MigrationOwnerBlocked(
                "b6_schema_migration_backup_failed",
                "migration backup snapshot differs from source preflight",
            )
        backup_sha = _sha256_file(staged_db)
        manifest = {
            "backup_db_sha256": backup_sha,
            "backup_id": f"b6_schema_migration:{preflight['sha256']}",
            "backup_health": backup_snapshot["health"],
            "backup_size_bytes": staged_db.stat().st_size,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "migration_id": MIGRATION_ID,
            "schema_version": BACKUP_SCHEMA_VERSION,
            "source_db_sha256": preflight["sha256"],
            "source_mtime_ns": preflight["mtime_ns"],
            "source_path": preflight["path"],
            "source_schema_row_snapshot_sha256": _sha256_bytes(
                _canonical_bytes(
                    {
                        "schema_objects": preflight["schema_objects"],
                        "task_snapshot": preflight["task_snapshot"],
                    }
                )
            ),
            "source_size_bytes": preflight["size_bytes"],
        }
        manifest_bytes = json.dumps(
            manifest, ensure_ascii=False, sort_keys=True, indent=2
        ).encode("utf-8") + b"\n"
        staged_manifest.write_bytes(manifest_bytes)
        manifest_sha = _sha256_bytes(manifest_bytes)
        staged_sidecar.write_text(
            f"{manifest_sha}  {manifest_path.name}\n", encoding="utf-8"
        )
        _fsync_file(staged_manifest)
        _fsync_file(staged_sidecar)
        os.replace(staged_db, target)
        published.append(target)
        os.replace(staged_manifest, manifest_path)
        published.append(manifest_path)
        os.replace(staged_sidecar, sidecar_path)
        published.append(sidecar_path)
        return _backup_info_from_files(target, manifest_path, sidecar_path, manifest)
    except MigrationOwnerBlocked:
        raise
    except Exception as exc:
        raise MigrationOwnerBlocked(
            "b6_schema_migration_backup_failed", str(exc)
        ) from exc
    finally:
        for item in (staged_db, staged_manifest, staged_sidecar):
            if item.is_file() or item.is_symlink():
                item.unlink()
        if staging.exists():
            staging.rmdir()


def _post_audit(path: Path, preflight: dict[str, Any]) -> dict[str, Any]:
    with closing(sqlite3.connect(_sqlite_ro_uri(path), uri=True)) as conn:
        health = _health(conn)
        if health["quick_check"] != "ok" or health["foreign_key_check"]:
            raise MigrationOwnerBlocked(
                "b6_schema_migration_post_audit_failed",
                f"health={health}",
            )
        task_columns = {row[1]: row for row in _table_columns(conn, "b6_validation_tasks")}
        if set(_SUCCESSOR_COLUMNS) - set(task_columns):
            raise MigrationOwnerBlocked(
                "b6_schema_migration_post_audit_failed",
                "migration 005 columns are incomplete",
            )
        if not _successor_shape_is_exact(
            conn, task_columns, _index_sql(conn, _EXPECTED_SUCCESSOR_INDEX)
        ):
            raise MigrationOwnerBlocked(
                "b6_schema_migration_post_audit_failed",
                "migration 005 schema/index/FK is not exact",
            )
        post_objects = _schema_objects(conn)
        pre_objects = preflight["schema_objects"]
        if not _post_schema_objects_are_exact(pre_objects, post_objects):
            raise MigrationOwnerBlocked(
                "b6_schema_migration_post_audit_failed",
                "pre-existing schema object changed",
            )
        post_task = _task_row_snapshot(conn)
        pre_task = preflight["task_snapshot"]
        old_columns = pre_task["column_names"]
        if post_task["column_names"][: len(old_columns)] != old_columns:
            raise MigrationOwnerBlocked(
                "b6_schema_migration_post_audit_failed",
                "pre-existing task columns changed",
            )
        if len(post_task["rows"]) != len(pre_task["rows"]):
            raise MigrationOwnerBlocked(
                "b6_schema_migration_post_audit_failed",
                "task row count changed",
            )
        for before, after in zip(pre_task["rows"], post_task["rows"]):
            for column in old_columns:
                if before.get(column) != after.get(column):
                    raise MigrationOwnerBlocked(
                        "b6_schema_migration_post_audit_failed",
                        f"task column changed: {column}",
                    )
            for column in _SUCCESSOR_COLUMNS:
                if after.get(column) is not None:
                    raise MigrationOwnerBlocked(
                        "b6_schema_migration_post_audit_failed",
                        f"historical task has non-null {column}",
                    )
        if any(
            row[0] is not None
            for row in conn.execute(
                "SELECT predecessor_task_id FROM b6_validation_tasks"
            )
        ):
            raise MigrationOwnerBlocked(
                "b6_schema_migration_post_audit_failed",
                "successor row exists after migration",
            )
        protected_counts = _protected_counts(conn)
        if any(value != 0 for value in protected_counts.values()):
            raise MigrationOwnerBlocked(
                "b6_schema_migration_post_audit_failed",
                f"protected evidence is nonzero: {protected_counts}",
            )
        return {
            "health": health,
            "schema_sha256": _sha256_bytes(_canonical_bytes(post_objects)),
            "task_snapshot_sha256": post_task["sha256"],
            "protected_counts": protected_counts,
            "migration_registry": "absent",
        }


def _empty_result(
    *,
    status: str,
    reason: str | None = None,
    detail: str | None = None,
    source: dict[str, Any] | None = None,
    backup: dict[str, Any] | None = None,
    post: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": RESULT_SCHEMA_VERSION,
        "migration_id": MIGRATION_ID,
        "status": status,
        "db_path": None if source is None else source["path"],
        "source_db_sha256": None if source is None else source["sha256"],
        "source_size_bytes": None if source is None else source["size_bytes"],
        "source_mtime_ns": None if source is None else source["mtime_ns"],
        "backup_id": None if backup is None else backup["backup_id"],
        "backup_path": None if backup is None else backup["backup_path"],
        "backup_manifest_path": None if backup is None else backup["backup_manifest_path"],
        "backup_manifest_sidecar_path": None if backup is None else backup["backup_manifest_sidecar_path"],
        "backup_db_sha256": None if backup is None else backup["backup_db_sha256"],
        "backup_manifest_sha256": None if backup is None else backup["backup_manifest_sha256"],
        "post_schema_sha256": None if post is None else post["schema_sha256"],
        "post_task_row_snapshot_sha256": None if post is None else post["task_snapshot_sha256"],
        "post_health": None if post is None else post["health"],
        "post_protected_counts": None if post is None else post["protected_counts"],
        "migration_registry": "absent" if post is None else post["migration_registry"],
        "reason": reason,
        "detail": detail,
    }


def _emit_progress(
    stream: TextIO | None,
    event_seq: int,
    *,
    stage: str,
    status: str,
    source_db_sha256: str | None,
    backup_id: str | None,
) -> int:
    if stream is None:
        return event_seq
    if stage not in _PROGRESS_STAGES:
        raise ValueError(f"unsupported migration progress stage: {stage}")
    stream.write(
        _canonical_json(
            {
                "schema_version": PROGRESS_SCHEMA_VERSION,
                "event_seq": event_seq,
                "stage": stage,
                "migration_id": MIGRATION_ID,
                "status": status,
                "source_db_sha256": source_db_sha256,
                "backup_id": backup_id,
            }
        )
        + "\n"
    )
    stream.flush()
    return event_seq + 1


def _write_result(stream: TextIO | None, payload: dict[str, Any]) -> None:
    if stream is not None:
        stream.write(_canonical_json(payload) + "\n")
        stream.flush()


def run_once(
    *,
    repo_root: Path,
    db_path: Path,
    backup_root: Path,
    connection_factory: Callable[[str], sqlite3.Connection] = sqlite3.connect,
    migration: Callable[[sqlite3.Connection], None] = migrate_add_b6_successor_attempt,
    stdout: TextIO | None = None,
    progress_stream: TextIO | None = None,
) -> tuple[int, dict[str, Any]]:
    del repo_root
    db_path = Path(db_path).resolve()
    event_seq = 1
    event_seq = _emit_progress(
        progress_stream,
        event_seq,
        stage="preflight",
        status="running",
        source_db_sha256=None,
        backup_id=None,
    )
    try:
        preflight = _preflight(db_path)
    except MigrationOwnerBlocked as exc:
        payload = _empty_result(status="blocked", reason=exc.reason, detail=exc.detail)
        _emit_progress(
            progress_stream,
            event_seq,
            stage="blocked",
            status="blocked",
            source_db_sha256=None,
            backup_id=None,
        )
        _write_result(stdout, payload)
        return EXIT_BLOCKED, payload
    if preflight["migration_005_state"] == "already_applied":
        payload = _empty_result(status="already_applied", source=preflight)
        _emit_progress(
            progress_stream,
            event_seq,
            stage="terminal",
            status="already_applied",
            source_db_sha256=preflight["sha256"],
            backup_id=None,
        )
        _write_result(stdout, payload)
        return EXIT_OK, payload

    event_seq = _emit_progress(
        progress_stream,
        event_seq,
        stage="backup",
        status="running",
        source_db_sha256=preflight["sha256"],
        backup_id=None,
    )
    try:
        backup = _create_backup(db_path, Path(backup_root), preflight)
    except MigrationOwnerBlocked as exc:
        payload = _empty_result(
            status="blocked",
            reason=exc.reason,
            detail=exc.detail,
            source=preflight,
        )
        _emit_progress(
            progress_stream,
            event_seq,
            stage="blocked",
            status="blocked",
            source_db_sha256=preflight["sha256"],
            backup_id=None,
        )
        _write_result(stdout, payload)
        return EXIT_BLOCKED, payload

    event_seq = _emit_progress(
        progress_stream,
        event_seq,
        stage="migration",
        status="running",
        source_db_sha256=preflight["sha256"],
        backup_id=backup["backup_id"],
    )
    connection = None
    try:
        connection = connection_factory(str(db_path))
        connection.execute("PRAGMA foreign_keys = ON")
        migration(connection)
    except Exception as exc:
        if connection is not None and connection.in_transaction:
            connection.rollback()
        payload = _empty_result(
            status="failed",
            reason="b6_schema_migration_failed",
            detail=str(exc),
            source=preflight,
            backup=backup,
        )
        _emit_progress(
            progress_stream,
            event_seq,
            stage="failed",
            status="failed",
            source_db_sha256=preflight["sha256"],
            backup_id=backup["backup_id"],
        )
        if connection is not None:
            connection.close()
        _write_result(stdout, payload)
        return EXIT_OWNER_FAILURE, payload
    finally:
        if connection is not None:
            connection.close()

    try:
        post = _post_audit(db_path, preflight)
    except MigrationOwnerBlocked as exc:
        payload = _empty_result(
            status="failed",
            reason=exc.reason,
            detail=exc.detail,
            source=preflight,
            backup=backup,
        )
        _emit_progress(
            progress_stream,
            event_seq,
            stage="failed",
            status="failed",
            source_db_sha256=preflight["sha256"],
            backup_id=backup["backup_id"],
        )
        _write_result(stdout, payload)
        return EXIT_OWNER_FAILURE, payload

    payload = _empty_result(
        status="migrated",
        source=preflight,
        backup=backup,
        post=post,
    )
    _emit_progress(
        progress_stream,
        event_seq,
        stage="terminal",
        status="migrated",
        source_db_sha256=preflight["sha256"],
        backup_id=backup["backup_id"],
    )
    _write_result(stdout, payload)
    return EXIT_OK, payload


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args:
        payload = _empty_result(
            status="invalid_invocation",
            reason="b6_schema_migration_invalid_invocation",
            detail="the migration owner accepts no arguments",
        )
        _write_result(sys.stdout, payload)
        return EXIT_INVALID_INVOCATION
    repo_root = Path(__file__).resolve().parents[1]
    code, _ = run_once(
        repo_root=repo_root,
        db_path=repo_root / "data" / "strategy.db",
        backup_root=repo_root / "data" / "strategy_backups" / "b6_schema_migration",
        stdout=sys.stdout,
        progress_stream=sys.stderr,
    )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
