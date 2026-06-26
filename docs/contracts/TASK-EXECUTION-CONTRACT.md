# M2 Task Execution Boundaries

**Status**: In Progress  
**Last Updated**: 2026-06-22  
**Scope**: Task definition and execution contracts (no async queue implementation)

---

## Overview

Tasks represent user/system-initiated long-running operations in TraderLens. M2 defines:
- What constitutes a Task
- Task lifecycle and state machine
- Progress, error, and artifact recording
- Clear boundaries for what workers can/cannot do

**M2 Scope**:
- ✅ Define Task schema and state machine
- ✅ Document task types and their contracts
- ✅ Specify progress and error tracking
- ✅ Define artifact management
- ✅ Document synchronous execution model (current)

**M2 Does NOT Include**:
- ❌ Async task queue (Redis/Celery/asyncio)
- ❌ Parallel task execution
- ❌ Real-time progress streaming
- ❌ Task retry logic
- ❌ Task dependencies/workflows
- ❌ Evidence/Serenity/Signal Board tasks

---

## 1. Task Definition

### What is a Task?

A **Task** is a user/system-initiated operation that:
1. Takes longer than 5 seconds
2. Produces artifacts (files, exports, reports)
3. Can fail and needs error tracking
4. Has meaningful progress updates

### M2 Supported Task Types

| Task Type | Description | Input | Output |
|-----------|-------------|-------|--------|
| `backtest_run` | Run single strategy backtest | Strategy config | BacktestResult + exports |
| `strategy_suite_run` | Run multiple strategies | Strategy directory | Suite summary + exports |
| `export_backtest_result` | Export backtest to CSV/JSON/PNG | BacktestResult JSON | Export directory |
| `compare_backtests` | Compare multiple backtest results | Export directories | Comparison report |

### M2 Deferred Task Types (M3+)

- `evidence` (Evidence Agent research)
- `serenity` (Bottleneck mapping)
- `signal_board` (Live signal monitoring)
- `live_watch` (Real-time position tracking)
- `real_data_fetch` (Tushare/AKShare)
- `broker_execution` (Live trading)

**Rationale**: M2 focuses on deterministic backtest pipeline. Research and live execution are M3+ concerns.

---

## 2. Task Schema

### TaskRecord

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

@dataclass
class TaskRecord:
    """
    Task execution record.
    
    M2 Contract: This structure is frozen after M2 closeout.
    """
    # Identification
    task_id: str  # Unique ID (e.g., "task_20260622_123456_abc123")
    task_type: Literal["backtest_run", "strategy_suite_run", "export_backtest_result", "compare_backtests"]
    
    # Status
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    
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
```

### Field Constraints

- `task_id`: Must be unique, non-empty
- `task_type`: Must be one of M2 supported types
- `status`: Must follow state machine transitions
- `progress_pct`: Must be 0.0-100.0 (inclusive)
- `created_at`: Always set
- `started_at`: Set when status → running
- `finished_at`: Set when status → succeeded/failed/cancelled
- `artifact_paths`: Empty list if no artifacts produced

---

## 3. Task State Machine

### States

1. **queued**: Task created, waiting to start
2. **running**: Task execution in progress
3. **succeeded**: Task completed successfully
4. **failed**: Task failed with error
5. **cancelled**: Task manually cancelled

### Valid Transitions

```
queued → running → succeeded
              ↓
              ↓ → failed
              ↓
              ↓ → cancelled

queued → cancelled
```

### Invalid Transitions

- ❌ succeeded → running (cannot restart)
- ❌ failed → succeeded (cannot fix retroactively)
- ❌ cancelled → running (cannot resume)

### Transition Rules

1. **queued → running**: Set `started_at`, `progress_pct=0`, `current_step`
2. **running → succeeded**: Set `finished_at`, `progress_pct=100`, populate `artifact_paths`
3. **running → failed**: Set `finished_at`, populate `error_type`, `error_message`, `error_traceback`
4. **running → cancelled**: Set `finished_at`, `error_message="Task cancelled by user"`
5. **queued → cancelled**: Set `finished_at`, no `started_at`

---

## 4. Progress Tracking

### Progress Reporting

Tasks SHOULD report progress at meaningful checkpoints:

**backtest_run**:
- 0%: Task queued
- 10%: Strategy validated
- 20%: Data loaded
- 30-90%: Backtest execution (per trading day)
- 95%: Metrics calculated
- 100%: Export complete

**strategy_suite_run**:
- 0%: Task queued
- 10%: Strategies enumerated
- 20-90%: Per-strategy progress (divided evenly)
- 95%: Suite summary generated
- 100%: Comparison complete

**export_backtest_result**:
- 0%: Task queued
- 25%: metrics.json written
- 50%: trades.csv written
- 75%: Charts generated
- 100%: Export complete

### Current Step Examples

- "Validating strategy config"
- "Loading fixture data"
- "Running backtest: 123/487 days"
- "Calculating metrics"
- "Exporting CSV files"
- "Generating charts"

---

## 5. Error Tracking

### Error Types

M2 tracks errors at three levels:

1. **error_type**: Python exception class name
   - `FileNotFoundError`
   - `ValueError`
   - `KeyError`
   - `ValidationError`
   - `DataIntegrityError`

2. **error_message**: Human-readable short description
   - "Strategy file not found: examples/strategies/strategy_001.yaml"
   - "Invalid strategy config: missing entry_conditions"
   - "Data validation failed: 3 OHLC violations"

3. **error_traceback**: Full Python traceback (optional, for debugging)

### Error Handling Policy

**M2 Default**: Fail-loud, no retry

- Tasks do NOT automatically retry on failure
- Worker does NOT catch and suppress errors
- Errors propagate to task record and user

**M3+**: Retry logic (optional)

- Transient errors (network, timeout) may retry
- Deterministic errors (validation, missing file) do NOT retry

---

## 6. Artifact Management

### Artifact Types

**backtest_run** produces:
- `backtest_result.json` (BacktestResult)
- `metrics.json` (performance summary)
- `trades.csv` (all trades)
- `round_trips.csv` (matched pairs)
- `equity_curve.csv` (daily portfolio)
- `order_generation_events.csv` (audit trail)
- `equity_curve.png` (chart, optional)
- `drawdown_curve.png` (chart, optional)

**strategy_suite_run** produces:
- `suite_summary.json` (all strategies)
- `suite_comparison/comparison.json`
- `suite_comparison/comparison.csv`
- `<strategy_name>/` (per-strategy exports)

**export_backtest_result** produces:
- (same as backtest_run exports)

**compare_backtests** produces:
- `comparison.json`
- `comparison.csv`

### Artifact Path Policy

- **Relative paths**: Relative to task output directory
- **Absolute paths**: Full filesystem path (discouraged)
- **Missing artifacts**: Empty list (not error)

**M2 Behavior**: Artifact paths are recorded, not validated

- Worker does NOT verify artifact existence after task
- Validation is caller's responsibility

---

## 7. Execution Model

### M2 Execution: Synchronous Scripts

**Current behavior** (M2):
- Tasks run synchronously in foreground
- `backend/scripts/run_backtest.py` executes immediately
- Progress is printed to stdout (not recorded)
- No task queue, no worker pool

**M2 Goal**: Define contracts, not implement queue

- TaskRecord schema enables future async execution
- State machine documents expected behavior
- Progress tracking prepares for UI integration

### M2 Worker Contract

**Worker responsibilities** (conceptual):
1. Validate task input before starting
2. Update task status at state transitions
3. Report progress at checkpoints
4. Record artifacts produced
5. Catch and record errors with traceback

**M2 does NOT implement**:
- Actual worker process
- Task queue (Redis/Celery)
- Progress streaming
- Parallel execution

**Rationale**: M2 establishes contracts for M3+ async implementation.

---

## 8. Task Validation

### Pre-Execution Validation

Before running, task worker MUST validate:

**backtest_run**:
- Strategy file exists
- Fixture path exists
- Output directory writable

**strategy_suite_run**:
- Strategies directory exists
- Fixture path exists
- Output directory writable

**export_backtest_result**:
- Result JSON file exists and valid
- Output directory writable

**compare_backtests**:
- All input directories exist
- Each has metrics.json
- Output directory writable

### Validation Failure Handling

- Set `status=failed`
- Set `error_type="ValidationError"`
- Set `error_message` with specific issue
- Do NOT execute task
- Record zero artifacts

---

## 9. Unsupported Operations (M2)

### What M2 Does NOT Support

1. **Task cancellation during execution**
   - M2 scripts run to completion or fail
   - Cancellation is conceptual (state machine only)

2. **Task retry**
   - Failed tasks stay failed
   - User must manually re-run

3. **Task dependencies**
   - Tasks run independently
   - No "run B after A succeeds"

4. **Progress streaming**
   - Progress not pushed to client
   - Client must poll task status

5. **Parallel execution**
   - Suite runs strategies sequentially
   - No worker pool

6. **Persistent task store**
   - No database/Redis
   - Task records are ephemeral (in-memory)

**Rationale**: M2 focuses on contracts, not infrastructure.

---

## 10. Success Criteria

M2 Task Execution Boundaries is complete when:

1. ✅ `TaskRecord` schema is defined and documented
2. ✅ Task state machine is documented (5 states, valid transitions)
3. ✅ Supported task types are enumerated (4 types)
4. ✅ Progress tracking convention is documented
5. ✅ Error tracking structure is defined (type, message, traceback)
6. ✅ Artifact management policy is documented
7. ✅ Execution model is clarified (M2 sync, M3+ async)
8. ✅ Validation requirements are specified
9. ✅ Tests validate TaskRecord schema and state machine
10. ✅ Documentation updated (TASK-EXECUTION-CONTRACT.md, ARCHITECTURE.md)

---

## 11. Out of Scope (Explicit)

- ❌ Async task queue implementation
- ❌ Redis/Celery/asyncio worker
- ❌ Real-time progress streaming
- ❌ Task retry logic
- ❌ Task dependencies/workflows
- ❌ Web UI integration
- ❌ Evidence/Serenity/Signal Board tasks
- ❌ Live execution tasks
- ❌ Persistent task storage
- ❌ Worker lifecycle management

M2 provides contracts and documentation only. Implementation is M3+.
