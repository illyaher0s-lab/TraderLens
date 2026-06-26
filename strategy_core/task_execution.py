"""
Task Execution Contracts - M2

Defines task schema, state machine, and execution boundaries.
M2 provides contracts only, not async queue implementation.
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Literal


# M2 Supported Task Types
TaskType = Literal[
    "backtest_run",
    "strategy_suite_run", 
    "export_backtest_result",
    "compare_backtests"
]

# Task Status
TaskStatus = Literal[
    "queued",
    "running",
    "succeeded",
    "failed",
    "cancelled"
]


@dataclass
class TaskRecord:
    """
    Task execution record.
    
    M2 Contract: This structure is frozen after M2 closeout.
    Breaking changes require schema version bump.
    
    A Task represents a user/system-initiated long-running operation
    that produces artifacts and needs progress/error tracking.
    """
    # Identification
    task_id: str  # Unique ID (e.g., "task_20260622_123456_abc123")
    task_type: TaskType
    
    # Status
    status: TaskStatus
    
    # Timestamps
    created_at: datetime
    started_at: datetime | None  # None if not started yet
    finished_at: datetime | None  # None if not finished
    
    # Progress
    progress_pct: float  # 0.0 - 100.0
    current_step: str  # Human-readable current step
    
    # Input/Output
    input_payload: dict  # Task-specific input (strategy path, export dirs, etc.)
    artifact_paths: list[str]  # Output files produced (relative or absolute paths)
    
    # Error tracking
    error_type: str | None  # Error class name (e.g., "FileNotFoundError")
    error_message: str | None  # Human-readable error
    error_traceback: str | None  # Full traceback (for debugging)


def validate_task_record(task: TaskRecord) -> None:
    """
    Validate TaskRecord structure and constraints.
    
    Raises:
        ValueError: If task record is invalid.
    """
    # task_id must be non-empty
    if not task.task_id:
        raise ValueError("task_id cannot be empty")
    
    # progress_pct must be 0.0-100.0
    if not (0.0 <= task.progress_pct <= 100.0):
        raise ValueError(f"progress_pct must be 0.0-100.0, got {task.progress_pct}")
    
    # created_at always required
    if task.created_at is None:
        raise ValueError("created_at is required")
    
    # Timestamp consistency
    if task.started_at and task.started_at < task.created_at:
        raise ValueError("started_at cannot be before created_at")
    
    if task.finished_at and task.started_at and task.finished_at < task.started_at:
        raise ValueError("finished_at cannot be before started_at")
    
    # Status-specific validations
    if task.status == "running":
        if task.started_at is None:
            raise ValueError("running task must have started_at")
        if task.finished_at is not None:
            raise ValueError("running task cannot have finished_at")
    
    if task.status in ("succeeded", "failed", "cancelled"):
        if task.finished_at is None:
            raise ValueError(f"{task.status} task must have finished_at")
    
    if task.status == "succeeded":
        if task.progress_pct != 100.0:
            raise ValueError("succeeded task must have progress_pct=100.0")
    
    if task.status == "failed":
        if not task.error_message:
            raise ValueError("failed task must have error_message")
    
    # artifact_paths must be list (can be empty)
    if not isinstance(task.artifact_paths, list):
        raise ValueError("artifact_paths must be a list")


def is_valid_state_transition(from_status: TaskStatus, to_status: TaskStatus) -> bool:
    """
    Check if state transition is valid according to M2 state machine.
    
    Valid transitions:
    - queued → running → succeeded
    - queued → running → failed
    - queued → running → cancelled
    - queued → cancelled
    
    Invalid transitions:
    - succeeded → running (cannot restart)
    - failed → succeeded (cannot fix retroactively)
    - cancelled → running (cannot resume)
    """
    valid_transitions = {
        "queued": {"running", "cancelled"},
        "running": {"succeeded", "failed", "cancelled"},
        "succeeded": set(),  # Terminal state
        "failed": set(),  # Terminal state
        "cancelled": set(),  # Terminal state
    }
    
    return to_status in valid_transitions.get(from_status, set())
