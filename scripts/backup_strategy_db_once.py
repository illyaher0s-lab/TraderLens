"""Create one server-owned, consistent SQLite backup without opening StrategyDB."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from contextlib import closing
from typing import Any


INCIDENT_RELATIVE_PATH = Path(
    "docs/verification/v3_e4_protocol_migration_incident_20260823.json"
)
BACKUP_RELATIVE_ROOT = Path("data/strategy_backups/b6_preclaim")
KNOWN_COUNT_TABLES = (
    "research_protocol_snapshots",
    "b6_validation_tasks",
    "oos_budget_reservations",
    "oos_budget_state",
    "oos_evaluation_ledgers",
    "immutable_backtest_reports",
    "prototype_gate_results_v2",
)


class BackupError(RuntimeError):
    """A backup could not be created without a partial final result."""


class BackupConflictError(BackupError):
    """An existing deterministic backup is not an exact reusable backup."""


def _canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        .encode("utf-8")
    )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _sqlite_uri(path: Path) -> str:
    return f"file:{path.resolve().as_posix()}?mode=ro"


def _validate_task_id(task_id: str) -> None:
    if not isinstance(task_id, str) or not task_id:
        raise BackupError("task_id must be non-empty")
    if task_id in {".", ".."} or any(
        token in task_id for token in ("/", "\\", "\x00")
    ):
        raise BackupError("task_id must be path-free")
    if any(ord(char) < 32 for char in task_id):
        raise BackupError("task_id must not contain control characters")


def _rows_for_table(conn: sqlite3.Connection, table: str) -> list[list[Any]]:
    quoted = '"' + table.replace('"', '""') + '"'
    rows = [list(row) for row in conn.execute(f"SELECT * FROM {quoted}")]
    rows.sort(key=lambda row: _canonical_bytes(row))
    return rows


def _snapshot_connection(conn: sqlite3.Connection) -> dict[str, Any]:
    quick_check = conn.execute("PRAGMA quick_check").fetchone()[0]
    if quick_check != "ok":
        raise BackupError(f"sqlite quick_check failed: {quick_check}")
    foreign_key_check = [list(row) for row in conn.execute("PRAGMA foreign_key_check")]
    if foreign_key_check:
        raise BackupError("sqlite foreign_key_check is not empty")

    schema_rows = [
        list(row)
        for row in conn.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
        )
    ]
    tables = [
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]
    table_rows = {table: _rows_for_table(conn, table) for table in tables}
    row_fingerprints = {
        table: hashlib.sha256(_canonical_bytes(rows)).hexdigest()
        for table, rows in table_rows.items()
        if table in {"research_protocol_snapshots", "b6_validation_tasks"}
    }
    counts = {
        table: int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
        for table in KNOWN_COUNT_TABLES
        if table in tables
    }
    return {
        "schema": schema_rows,
        "schema_fingerprint": hashlib.sha256(_canonical_bytes(schema_rows)).hexdigest(),
        "tables": tables,
        "counts": counts,
        "protocol_task_row_fingerprints": row_fingerprints,
        "quick_check": quick_check,
        "foreign_key_check": foreign_key_check,
    }


def _source_snapshot(source_db: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    before_stat = source_db.stat()
    before_sha = _file_sha256(source_db)
    with closing(sqlite3.connect(_sqlite_uri(source_db), uri=True)) as source_conn:
        snapshot = _snapshot_connection(source_conn)
        tasks = _rows_for_table(source_conn, "b6_validation_tasks")
    after_stat = source_db.stat()
    after_sha = _file_sha256(source_db)
    if (
        before_stat.st_mtime_ns != after_stat.st_mtime_ns
        or before_stat.st_size != after_stat.st_size
        or before_sha != after_sha
    ):
        raise BackupError("source database changed during pre-backup read")
    return (
        {
            "db_sha256": before_sha,
            "mtime_ns": before_stat.st_mtime_ns,
            "size_bytes": before_stat.st_size,
            "snapshot": snapshot,
        },
        {"task_ids": [row[0] for row in tasks]},
    )


def _fsync_file(path: Path) -> None:
    with path.open("r+b") as handle:
        os.fsync(handle.fileno())


def _cleanup_staging(staging: Path, backup_root: Path) -> None:
    if staging.resolve().parent != backup_root.resolve():
        raise BackupError("refusing to clean staging outside backup root")
    if not staging.exists():
        return
    for child in staging.iterdir():
        if child.is_file() or child.is_symlink():
            child.unlink()
    staging.rmdir()


def _manifest_paths(target: Path) -> tuple[Path, Path]:
    manifest = target.with_name(target.name + ".manifest.json")
    return manifest, manifest.with_name(manifest.name + ".sha256")


def _read_existing(
    *,
    target: Path,
    manifest_path: Path,
    sidecar_path: Path,
    source_identity: dict[str, Any],
    task_id: str,
    incident_id: str,
    incident_sha256: str,
    tool_sha256: str,
) -> dict[str, Any]:
    if not target.is_file() or not manifest_path.is_file() or not sidecar_path.is_file():
        raise BackupConflictError("deterministic backup has partial existing files")
    manifest_bytes = manifest_path.read_bytes()
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    sidecar_tokens = sidecar_path.read_text(encoding="utf-8").split()
    if not sidecar_tokens or sidecar_tokens[0] != manifest_sha256:
        raise BackupConflictError("existing backup manifest sidecar mismatch")
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise BackupConflictError("existing backup manifest is invalid JSON") from exc
    if set(manifest) != {
        "backup_db_sha256",
        "backup_id",
        "backup_snapshot",
        "created_at",
        "incident_id",
        "incident_manifest_sha256",
        "schema_version",
        "source_db_sha256",
        "source_mtime_ns",
        "source_snapshot",
        "source_size_bytes",
        "task_id",
        "tool_source_sha256",
    }:
        raise BackupConflictError("existing backup manifest fields conflict")
    expected = {
        "task_id": task_id,
        "incident_id": incident_id,
        "incident_manifest_sha256": incident_sha256,
        "tool_source_sha256": tool_sha256,
        "source_db_sha256": source_identity["db_sha256"],
        "source_mtime_ns": source_identity["mtime_ns"],
        "source_size_bytes": source_identity["size_bytes"],
        "source_snapshot": source_identity["snapshot"],
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise BackupConflictError(f"existing backup field conflict: {key}")
    backup_sha256 = _file_sha256(target)
    if manifest["backup_db_sha256"] != backup_sha256:
        raise BackupConflictError("existing backup database hash conflict")
    with closing(sqlite3.connect(_sqlite_uri(target), uri=True)) as backup_conn:
        backup_snapshot = _snapshot_connection(backup_conn)
    if backup_snapshot != manifest["backup_snapshot"] or backup_snapshot != source_identity["snapshot"]:
        raise BackupConflictError("existing backup snapshot conflict")
    return {
        "status": "reused",
        "backup_path": str(target),
        "manifest_path": str(manifest_path),
        "manifest_sidecar_path": str(sidecar_path),
        "manifest_sha256": manifest_sha256,
    }


def _backup_strategy_db_once(
    task_id: str,
    *,
    repo_root: Path,
    _fault: str | None = None,
) -> dict[str, Any]:
    _validate_task_id(task_id)
    repo_root = Path(repo_root).resolve()
    source_db = repo_root / "data" / "strategy.db"
    backup_root = repo_root / BACKUP_RELATIVE_ROOT
    incident_path = repo_root / INCIDENT_RELATIVE_PATH
    if not source_db.is_file() or not incident_path.is_file():
        raise BackupError("server-owned source or incident evidence is missing")

    incident_bytes = incident_path.read_bytes()
    incident_sha256 = hashlib.sha256(incident_bytes).hexdigest()
    incident = json.loads(incident_bytes.decode("utf-8"))
    incident_id = incident_path.stem
    if incident.get("status") != "contained_not_yet_recovered":
        raise BackupError("incident evidence is not in the required contained state")
    source_identity, task_identity = _source_snapshot(source_db)
    if task_id not in task_identity["task_ids"]:
        raise BackupError("explicit task_id is not present in the source database")

    target = backup_root / f"{task_id}.{source_identity['db_sha256']}.sqlite3"
    manifest_path, sidecar_path = _manifest_paths(target)
    tool_sha256 = _file_sha256(Path(__file__).resolve())
    if target.exists() or manifest_path.exists() or sidecar_path.exists():
        return _read_existing(
            target=target,
            manifest_path=manifest_path,
            sidecar_path=sidecar_path,
            source_identity=source_identity,
            task_id=task_id,
            incident_id=incident_id,
            incident_sha256=incident_sha256,
            tool_sha256=tool_sha256,
        )

    backup_root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}.staging-", dir=str(backup_root)))
    staged_db = staging / target.name
    staged_manifest = staging / manifest_path.name
    staged_sidecar = staging / sidecar_path.name
    published: list[Path] = []
    try:
        if _fault == "backup":
            raise BackupError("injected backup failure")
        with closing(sqlite3.connect(_sqlite_uri(source_db), uri=True)) as source_conn:
            with closing(sqlite3.connect(staged_db)) as destination_conn:
                source_conn.backup(destination_conn)
                destination_conn.commit()
        _fsync_file(staged_db)
        with closing(sqlite3.connect(_sqlite_uri(staged_db), uri=True)) as copied_conn:
            backup_snapshot = _snapshot_connection(copied_conn)
        if backup_snapshot != source_identity["snapshot"]:
            raise BackupError("backup snapshot does not exactly match source snapshot")
        if _fault == "verify":
            raise BackupError("injected backup verification failure")

        backup_sha256 = _file_sha256(staged_db)
        manifest = {
            "backup_db_sha256": backup_sha256,
            "backup_id": f"b6_preclaim:{task_id}:{source_identity['db_sha256']}",
            "backup_snapshot": backup_snapshot,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "incident_id": incident_id,
            "incident_manifest_sha256": incident_sha256,
            "schema_version": "b6_strategy_db_backup.v1",
            "source_db_sha256": source_identity["db_sha256"],
            "source_mtime_ns": source_identity["mtime_ns"],
            "source_snapshot": source_identity["snapshot"],
            "source_size_bytes": source_identity["size_bytes"],
            "task_id": task_id,
            "tool_source_sha256": tool_sha256,
        }
        manifest_bytes = json.dumps(
            manifest, ensure_ascii=False, sort_keys=True, indent=2
        ).encode("utf-8") + b"\n"
        staged_manifest.write_bytes(manifest_bytes)
        manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
        staged_sidecar.write_text(
            f"{manifest_sha256}  {manifest_path.name}\n", encoding="utf-8"
        )
        _fsync_file(staged_manifest)
        _fsync_file(staged_sidecar)
        if _fault == "rename":
            raise BackupError("injected atomic rename failure")
        os.replace(staged_db, target)
        published.append(target)
        os.replace(staged_manifest, manifest_path)
        published.append(manifest_path)
        os.replace(staged_sidecar, sidecar_path)
        published.append(sidecar_path)
        return {
            "status": "published",
            "backup_path": str(target),
            "manifest_path": str(manifest_path),
            "manifest_sidecar_path": str(sidecar_path),
            "manifest_sha256": manifest_sha256,
        }
    except BackupError:
        raise
    except Exception as exc:
        raise BackupError(str(exc)) from exc
    finally:
        if _fault in {"backup", "verify", "rename"} or len(published) != 3:
            for path in reversed(published):
                if path.parent == backup_root and path.exists():
                    path.unlink()
        _cleanup_staging(staging, backup_root)


def backup_strategy_db_once(task_id: str, *, repo_root: Path | None = None) -> dict[str, Any]:
    """Create or reuse the server-owned backup for one explicit task."""
    return _backup_strategy_db_once(
        task_id,
        repo_root=Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[1],
    )


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print(json.dumps({"reason": "exactly one explicit task_id is required", "status": "invalid_invocation"}, sort_keys=True, separators=(",", ":")))
        return 2
    try:
        result = backup_strategy_db_once(args[0])
    except BackupConflictError as exc:
        print(json.dumps({"reason": str(exc), "status": "conflict"}, sort_keys=True, separators=(",", ":")))
        return 1
    except BackupError as exc:
        print(json.dumps({"reason": str(exc), "status": "blocked"}, sort_keys=True, separators=(",", ":")))
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
