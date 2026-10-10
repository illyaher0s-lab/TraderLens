"""Create or reuse one server-owned B6 v3 successor attempt."""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any, Callable, Sequence

from backend.db.strategy import B6SuccessorPreconditionError, StrategyDB
from scripts.backup_strategy_db_once import backup_strategy_db_once


EXIT_OK = 0
EXIT_INVALID_INVOCATION = 64
EXIT_BLOCKED = 20
EXIT_OWNER_FAILURE = 70

_PROGRESS_STAGES = {"preflight", "backup", "owner_write", "terminal", "blocked", "failed"}


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _parse_predecessor_task_id(argv: Sequence[str]) -> str:
    if len(argv) != 1:
        raise ValueError("exactly one explicit predecessor_task_id is required")
    task_id = argv[0]
    if (
        not isinstance(task_id, str)
        or not task_id
        or task_id != task_id.strip()
        or task_id.startswith("-")
        or any(character.isspace() for character in task_id)
        or task_id in {"latest", "queued", "scan"}
        or any(separator in task_id for separator in ("/", "\\", "\x00"))
        or any(ord(character) < 32 for character in task_id)
    ):
        raise ValueError("predecessor_task_id must be one explicit path-free identifier")
    return task_id


def _emit_progress(
    stream,
    event_seq: int,
    *,
    stage: str,
    predecessor_task_id: str,
    successor_task_id: str | None,
    status: str,
) -> int:
    if stage not in _PROGRESS_STAGES:
        raise ValueError(f"unsupported successor progress stage: {stage}")
    stream.write(
        _canonical_json(
            {
                "schema_version": "b6_successor_attempt_progress.v1",
                "event_seq": event_seq,
                "stage": stage,
                "predecessor_task_id": predecessor_task_id,
                "successor_task_id": successor_task_id,
                "status": status,
            }
        )
        + "\n"
    )
    stream.flush()
    return event_seq + 1


def _error_payload(
    predecessor_task_id: str,
    *,
    status: str,
    reason: str,
    detail: str | None = None,
    backup: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": "b6_successor_attempt.cli.v1",
        "predecessor_task_id": predecessor_task_id,
        "predecessor_task_key": None,
        "successor_task_id": None,
        "successor_task_key": None,
        "task_contract_version": None,
        "successor_attempt_number": None,
        "task_status": None,
        "b5_bundle_id": None,
        "b5_bundle_manifest_sha256": None,
        "backup": backup,
        "oos_authorized": False,
        "oos_consumed": False,
        "promotion_id": None,
        "status": status,
        "reason": reason,
        "detail": detail,
    }


def _result_payload(predecessor_task_id: str, successor, backup: dict[str, Any], created: bool) -> dict[str, Any]:
    return {
        "schema_version": "b6_successor_attempt.cli.v1",
        "predecessor_task_id": predecessor_task_id,
        "predecessor_task_key": successor.predecessor_task_key,
        "successor_task_id": successor.task_id,
        "successor_task_key": successor.task_key,
        "task_contract_version": successor.task_contract_version,
        "successor_attempt_number": successor.successor_attempt_number,
        "task_status": successor.status,
        "b5_bundle_id": successor.b5_bundle_id,
        "b5_bundle_manifest_sha256": successor.b5_bundle_manifest_sha256,
        "backup": backup,
        "oos_authorized": False,
        "oos_consumed": False,
        "promotion_id": None,
        "status": "created" if created else "reused",
        "reason": None,
        "detail": None,
    }


def _run_successor(
    predecessor_task_id: str,
    *,
    repo_root: Path,
    db_factory: Callable[[Path], StrategyDB] = StrategyDB,
    backup_factory: Callable[..., dict[str, Any]] = backup_strategy_db_once,
    stdout=None,
    progress_stream=None,
) -> tuple[int, dict[str, Any]]:
    event_seq = 1

    def progress(
        stage: str,
        successor_task_id: str | None,
        status: str,
    ) -> None:
        nonlocal event_seq
        if progress_stream is not None:
            event_seq = _emit_progress(
                progress_stream,
                event_seq,
                stage=stage,
                predecessor_task_id=predecessor_task_id,
                successor_task_id=successor_task_id,
                status=status,
            )

    progress("preflight", None, "running")
    progress("backup", None, "running")
    try:
        backup = backup_factory(predecessor_task_id, repo_root=Path(repo_root))
    except Exception as exc:
        payload = _error_payload(
            predecessor_task_id,
            status="blocked",
            reason="b6_successor_backup_failed",
            detail=str(exc),
        )
        progress("blocked", None, "blocked")
        if stdout is not None:
            stdout.write(_canonical_json(payload) + "\n")
            stdout.flush()
        return EXIT_BLOCKED, payload

    progress("owner_write", None, "running")
    db = None
    try:
        db = db_factory(Path(repo_root) / "data" / "strategy.db")
        successor, created = db.create_or_get_b6_successor_attempt(predecessor_task_id)
    except B6SuccessorPreconditionError as exc:
        payload = _error_payload(
            predecessor_task_id,
            status="blocked",
            reason=exc.reason_code,
            detail=str(exc),
            backup=backup,
        )
        progress("blocked", None, "blocked")
        if stdout is not None:
            stdout.write(_canonical_json(payload) + "\n")
            stdout.flush()
        return EXIT_BLOCKED, payload
    except Exception as exc:
        payload = _error_payload(
            predecessor_task_id,
            status="failed",
            reason="b6_successor_owner_failed",
            detail=str(exc),
            backup=backup,
        )
        progress("failed", None, "failed")
        if stdout is not None:
            stdout.write(_canonical_json(payload) + "\n")
            stdout.flush()
        return EXIT_OWNER_FAILURE, payload
    finally:
        if db is not None:
            db.close()

    payload = _result_payload(predecessor_task_id, successor, backup, created)
    progress("terminal", successor.task_id, successor.status)
    if stdout is not None:
        stdout.write(_canonical_json(payload) + "\n")
        stdout.flush()
    return EXIT_OK, payload


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        predecessor_task_id = _parse_predecessor_task_id(args)
    except ValueError as exc:
        payload = _error_payload(
            args[0] if len(args) == 1 else "",
            status="invalid_invocation",
            reason="b6_successor_invalid_invocation",
            detail=str(exc),
        )
        print(_canonical_json(payload))
        return EXIT_INVALID_INVOCATION
    code, _ = _run_successor(
        predecessor_task_id,
        repo_root=Path(__file__).resolve().parents[1],
        stdout=sys.stdout,
        progress_stream=sys.stderr,
    )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
