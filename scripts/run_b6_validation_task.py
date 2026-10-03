"""Thin explicit-task entry point for the B6 validation worker."""

from __future__ import annotations

from dataclasses import asdict
from functools import partial
import json
from pathlib import Path
import sys
from typing import Any, Callable, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from backend.db.strategy import StrategyDB
from backend.services.b6_validation_worker import B6ValidationWorker, B6WorkerResult
from scripts.backup_strategy_db_once import backup_strategy_db_once


EXIT_OK = 0
EXIT_INVALID_INVOCATION = 64
EXIT_DEPENDENCY_FAILURE = 70
EXIT_WORKER_FAILURE = 71
EXIT_BY_STATUS = {
    "completed": EXIT_OK,
    "blocked": 20,
    "failed": 21,
    "recovery_required": 22,
    "ready_for_reservation": 23,
    "not_found": 24,
    "not_claimed": 25,
}


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _emit_progress(
    stream,
    event_seq: int,
    *,
    stage: str,
    task_id: str,
    task_status: str,
    status: str,
) -> int:
    stream.write(
        _canonical_json(
            {
                "schema_version": "b6_validation_progress.v1",
                "event_seq": event_seq,
                "stage": stage,
                "task_id": task_id,
                "task_status": task_status,
                "status": status,
            }
        )
        + "\n"
    )
    stream.flush()
    return event_seq + 1


def _invalid_payload(reason: str, task_id: str | None = None, detail: str | None = None) -> dict[str, Any]:
    return {
        "schema_version": "b6_validation_task.cli.v1",
        "task_id": task_id,
        "task_key": None,
        "task_status": "invalid",
        "status": "invalid_invocation",
        "reason": reason,
        "detail": detail,
        "oos_authorized": False,
        "oos_consumed": False,
        "promotion_id": None,
    }


def _parse_task_id(argv: Sequence[str]) -> str:
    if len(argv) != 1:
        raise ValueError("exactly one explicit task_id is required")
    task_id = argv[0]
    if (
        not isinstance(task_id, str)
        or not task_id.strip()
        or task_id != task_id.strip()
        or task_id.startswith("-")
        or any(character.isspace() for character in task_id)
        or task_id in {"latest", "queued"}
    ):
        raise ValueError("task_id is invalid")
    return task_id


def _build_production_executor(repo_root: Path) -> Callable[[dict[str, Any]], Any]:
    """Build the server-owned real executor before opening the task database."""
    from backend.services.b6_same_draw_executor import (
        _load_industry_index,
        execute_production_same_draw,
    )
    from backend.services.formal_pit_partition_adapter import FormalPITPartitionAdapter

    if not callable(execute_production_same_draw):
        raise TypeError("production same-draw executor is not callable")
    FormalPITPartitionAdapter(repo_root)
    _load_industry_index(repo_root)
    supplement_root = repo_root / "data/pit/v3_execution_semantics_supplements"
    if not supplement_root.is_dir():
        raise FileNotFoundError(f"same-draw supplement root missing: {supplement_root}")
    return partial(execute_production_same_draw, repo_root=repo_root)


def _result_payload(result: B6WorkerResult) -> dict[str, Any]:
    if not isinstance(result, B6WorkerResult):
        raise TypeError("B6 worker returned an invalid result type")
    return {"schema_version": "b6_validation_task.cli.v1", **asdict(result)}


def _run_task(
    task_id: str,
    *,
    repo_root: Path,
    dependency_factory: Callable[[Path], Callable[[dict[str, Any]], Any]],
    db_factory: Callable[[Path], StrategyDB] = StrategyDB,
    worker_factory: Callable[..., B6ValidationWorker] = B6ValidationWorker,
    backup_factory: Callable[..., dict[str, Any]] = backup_strategy_db_once,
    progress_stream=None,
) -> tuple[int, dict[str, Any]]:
    """Run one explicit task; dependency construction precedes DB ownership."""
    event_seq = 1

    def progress(stage: str, task_status: str, status: str) -> None:
        nonlocal event_seq
        if progress_stream is not None:
            event_seq = _emit_progress(
                progress_stream,
                event_seq,
                stage=stage,
                task_id=task_id,
                task_status=task_status,
                status=status,
            )

    progress("preflight", "queued", "running")
    try:
        execute_same_draw = dependency_factory(repo_root)
    except Exception as exc:
        progress("failed", "queued", "failed")
        return EXIT_DEPENDENCY_FAILURE, {
            **_invalid_payload("b6_dependency_failed", task_id),
            "status": "dependency_failed",
            "reason": "b6_dependency_failed",
            "detail": str(exc),
        }

    progress("dependencies_prepared", "queued", "running")
    try:
        backup_factory(task_id, repo_root=repo_root)
    except Exception as exc:
        progress("blocked", "queued", "blocked")
        return EXIT_BY_STATUS["blocked"], {
            **_invalid_payload("b6_preclaim_backup_failed", task_id),
            "task_status": "queued",
            "status": "blocked",
            "reason": "b6_preclaim_backup_failed",
            "detail": str(exc),
        }

    progress("executing", "queued", "running")
    db = None
    try:
        db = db_factory(repo_root / "data" / "strategy.db")
        worker = worker_factory(db, repo_root=repo_root)
        result = worker.run_task(task_id=task_id, execute_same_draw=execute_same_draw)
        payload = _result_payload(result)
        code = EXIT_BY_STATUS.get(result.status)
        if code is None:
            raise ValueError(f"unsupported B6 worker status: {result.status}")
        _canonical_json(payload)
        if result.status == "completed":
            progress("terminal", result.task_status, "completed")
        elif result.status == "blocked":
            progress("blocked", result.task_status, "blocked")
        elif result.status == "failed":
            progress("failed", result.task_status, "failed")
        elif result.status == "recovery_required":
            progress("recovery_required", result.task_status, "recovery_required")
        else:
            progress("terminal", result.task_status, "running")
        return code, payload
    except Exception as exc:
        progress("failed", "running", "failed")
        return EXIT_WORKER_FAILURE, {
            **_invalid_payload("b6_worker_failed", task_id),
            "task_status": "unknown",
            "status": "failed",
            "reason": "b6_worker_failed",
            "detail": str(exc),
        }
    finally:
        if db is not None:
            db.close()


def main(argv: Sequence[str] | None = None) -> int:
    raw_argv = tuple(sys.argv[1:] if argv is None else argv)
    try:
        task_id = _parse_task_id(raw_argv)
    except ValueError as exc:
        payload = _invalid_payload("invalid task invocation", detail=str(exc))
        print(_canonical_json(payload))
        return EXIT_INVALID_INVOCATION

    repo_root = Path(__file__).resolve().parents[1]
    code, payload = _run_task(
        task_id,
        repo_root=repo_root,
        dependency_factory=_build_production_executor,
        progress_stream=sys.stderr,
    )
    print(_canonical_json(payload))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
