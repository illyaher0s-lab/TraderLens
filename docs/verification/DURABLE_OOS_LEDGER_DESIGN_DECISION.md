# Durable OOS Ledger Design Decision

**Status:** Design accepted for a separate implementation authorization. The B6/OOS mainline remains `validation_unavailable` until that implementation and its verification are complete.

**Date:** 2026-07-13  
**Scope:** Durable ownership of the three-draw OOS budget only. This document does not authorize protocol freezing, B6/OOS execution, result viewing, Gate, Promotion, Signal, or any data work.

---

## Decision

Choose **Option B: a new mutable runtime-state model**. It consists of two related SQLite tables, not a JSON blob in one row:

1. `oos_budget_state` owns the current budget for one `(theme_id, hypothesis_source_snapshot_id)`.
2. `oos_budget_reservations` owns durable reservation facts, hash-result guards, and the cross-theme OOS-window guard.

`oos_evaluation_ledgers` remains append-only audit evidence. It is not the runtime owner and is not rewritten or repurposed.

Two tables are the minimum safe shape. A single state row cannot atomically and queryably enforce the existing global hash-tuple and cross-theme `(shared_oos_window_id, data_snapshot_hash)` rules without scanning or mutating opaque JSON across unrelated owners.

---

## Evidence and option comparison

### Option A: extend `oos_evaluation_ledgers`

Rejected for the runtime owner, not because immutable snapshots are impossible to append, but because safe use would require all of the following anyway:

- a current-state projection or repeated replay query;
- a per-owner versioning rule (the existing unique key is `(theme_id, ledger_version)`, not the owner pair);
- durable representations of active reservations, hash guards, and window claims;
- a serialized append-and-read transaction protocol; and
- new read APIs.

That is a mutable state model plus an event stream, with more failure paths than the required three-draw budget needs. The existing table remains valuable as the audit stream.

### Option B: new mutable runtime-state model

Selected. It has direct current-state lookup, relational reservation facts, one SQLite transaction per state transition, and no replay or projection rebuild path. It preserves the immutable audit contract.

### Option C: snapshots/events plus a rebuildable projection

Rejected. It needs both an event protocol and a projection-consistency/rebuild protocol while offering no required capability beyond Option B. It is disproportionate for a maximum of three consumed draws per owner.

---

## Required data model

The repository has no migration framework; schema creation currently lives in `StrategyDB._create_tables()`. The implementation must follow that convention and add only the following tables and indexes there. No migration is required for pre-existing in-memory ledger state because that state was never durable and therefore cannot be safely migrated.

```sql
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
    FOREIGN KEY (theme_id, hypothesis_source_snapshot_id)
        REFERENCES oos_budget_state(theme_id, hypothesis_source_snapshot_id),
    UNIQUE (theme_id, hypothesis_source_snapshot_id, oos_draw_index)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_oos_one_active_reservation_per_owner
ON oos_budget_reservations(theme_id, hypothesis_source_snapshot_id)
WHERE status IN ('reserved', 'started');

CREATE UNIQUE INDEX IF NOT EXISTS uq_oos_hash_tuple_in_flight_or_terminal
ON oos_budget_reservations(
    strategy_config_hash, data_snapshot_hash, gate_criteria_hash
)
WHERE status IN ('reserved', 'started', 'completed', 'failed');

CREATE INDEX IF NOT EXISTS ix_oos_window_data_theme_status
ON oos_budget_reservations(
    shared_oos_window_id, data_snapshot_hash, theme_id, status
);
```

The hash-tuple index deliberately includes `failed`: once execution might have observed OOS data, the same tuple cannot be re-run to shop for an outcome. `released` is excluded because release is permitted only before OOS execution starts.

The window/data index is queried within the same write transaction. A claim exists when a reservation is `reserved`, `started`, `completed`, or `failed`; a claim is removed only logically by changing the reservation to `released`. Another theme is rejected when an existing claim has the same window and data hash. Reuse by the same theme remains allowed, matching the current rule.

---

## Ownership and injection boundary

The durable owner is the database state, not a Python singleton. `OOSBudgetLedger` becomes a DB-backed service constructed with an explicitly supplied `StrategyDB` connected to the same configured strategy database path.

- `ResearchProtocolFreezer` may receive that service only for a read-only preflight after the later coverage-freeze task is separately resumed.
- The future actual B6/OOS execution composition root must inject a DB-backed ledger into `B6ValidationFlow`; it must never instantiate `OOSBudgetLedger()` without a DB.
- `backend/app/main.py` is not changed merely to create a singleton: no production B6 composition root currently exists there. If one is added later, it must inject `OOSBudgetLedger(StrategyDB(configured_strategy_db_path))`; it must not use `:memory:` or a separate database path.
- Tests may use `:memory:` only for single-connection unit tests. Restart and concurrency tests must use two independent `StrategyDB` connections to the same temporary SQLite file.

This is the only shared-owner guarantee required: different processes may construct separate service instances, but they operate on the same durable database and serialized transactions.

---

## State machine and budget semantics

`consumed_draw_count` is the authoritative budget count. It increases only when a reservation reaches `completed` or `failed` after execution has started. A rejected report is `completed` and consumes a draw.

```text
no row --read--> default available projection (no write)
no row --reserve--> available + reservation(reserved, draw 1)

reserved --start_execution--> started
reserved --release_pre_execution--> released       (does not consume)
started  --complete--> completed                   (consumes one draw)
started  --fail_after_start--> failed              (consumes one draw)

consumed 0..2 --terminal consume--> available, next index + 1
consumed 2    --terminal consume--> exhausted, next index = 4
```

Rules:

1. Only one `reserved` or `started` reservation may exist for one owner.
2. The assigned draw index is `next_oos_draw_index`. It advances only when a draw is consumed, so a verified pre-execution release may reuse the same index.
3. A `reserved` reservation is not a consumed draw, but it blocks another reservation for the same owner.
4. `start_execution` is mandatory and must commit before the executor reads OOS observations or asks a report builder to process OOS data.
5. `release_pre_execution` accepts only `reserved` reservations whose `execution_started_at` is null. It persists a reason and never accepts a post-start failure.
6. `complete` accepts only `started` reservations, records the terminal verdict, and consumes a draw even for `rejected`.
7. `fail_after_start` accepts only `started` reservations and consumes a draw. It is the conservative result for unknown post-start failure.
8. No operation can change a terminal reservation back to active or reduce `consumed_draw_count`.

---

## Exact transaction protocol

SQLite does not provide row-level locks. Every mutating transition must use one `BEGIN IMMEDIATE` transaction on the strategy database connection. That acquires SQLite's single-writer reservation before any state/reservation read; readers may still read their last committed view.

`StrategyDB` must expose a narrow transaction context for this ledger and private non-committing helpers. Existing public `store_oos_ledger()` currently commits, so the implementation must add a private in-transaction insert helper rather than call the public committing method from an active ledger transaction.

For each mutation:

1. `BEGIN IMMEDIATE`.
2. Read the owner state, creating the owner row only in `reserve`.
3. Read relevant reservation rows and enforce owner-active, hash-tuple, and cross-theme window/data rules.
4. Insert or update the reservation and update the owner state with `WHERE state_version = :expected_version`; increment `state_version` exactly once.
5. Build and insert one immutable `OOSEvaluationLedger` audit snapshot in the same transaction. Its `ledger_version` is allocated as `MAX(ledger_version) + 1` for the theme while the write transaction is held.
6. Commit. Any exception rolls back both runtime state and audit snapshot.

The state-version condition is a defensive invariant. `BEGIN IMMEDIATE` is the concurrency mechanism; a zero-row state update is a corruption/protocol error, never a silent retry.

On `SQLITE_BUSY` or `SQLITE_LOCKED`, the service may retry the *entire transaction* once after a bounded delay. A second busy/locked result raises a distinct `OOSLedgerConcurrencyUnavailable` error; it must not reserve a draw, fabricate a result, or fall back to in-memory storage.

### Reserve

In one transaction, reject in this order:

1. an in-flight or terminal hash tuple;
2. a cross-theme active/terminal window-data claim;
3. an active reservation for the owner;
4. `consumed_draw_count == 3`.

Then insert the owner row if absent, insert `reserved`, set `active_reservation_id`, append the audit snapshot, and commit. The count and next draw index do not change.

### Start, complete, fail, and release

- **start:** change only `reserved -> started` and set `execution_started_at`; it does not consume budget.
- **complete:** change `started -> completed`, clear `active_reservation_id`, increment consumed count and next index, set exhausted at three, append audit, commit.
- **fail_after_start:** same state update as complete but terminal status `failed` and a mandatory reason. It consumes budget.
- **release_pre_execution:** change only `reserved -> released`, clear `active_reservation_id`, persist a mandatory reason, append audit, commit. It does not change count or next index.

`get_ledger_state()` is a read-only projection. If no state row exists, it returns an explicit default projection (`consumed_draw_count=0`, `next_oos_draw_index=1`, `budget_status='available'`, `persisted=False`) without inserting a row.

---

## Crash and restart recovery

There is no TTL and no undefined "manual cleanup" path.

On service startup or on the first read for an owner, the ledger does not silently alter a reservation. It returns the persisted active reservation and blocks new execution for that owner until a deterministic recovery transition occurs.

Recovery is defined as follows:

- A persisted `reserved` reservation with `execution_started_at IS NULL` may be released by the explicit recovery path as `release_pre_execution(reason='recovered_pre_execution_interruption')`. This is safe only because the B6 executor is required and tested to write `started` before any OOS read or report construction.
- A persisted `started` reservation is never auto-released. The explicit recovery path must call `fail_after_start(reason='recovered_unknown_post_start_interruption')`, consuming the draw. This conservative outcome prevents OOS shopping when result visibility cannot be disproved.
- A crash before transaction commit leaves no durable transition; SQLite rolls it back. A crash after commit leaves exactly the persisted transition and is handled by the preceding rules.
- If `complete` fails after a report has been generated, the completion transaction rolls back, the reservation stays `started`, and recovery must mark it `failed`/consumed before any later B6 action. The report must not be used for Gate or Promotion through this task.

These rules remove the unsupported assumption that an administrator may freely return a draw after an unknown crash.

---

## Audit consistency

Every durable mutation appends one `OOSEvaluationLedger` snapshot in the same SQLite transaction as the state/reservation write. The snapshot is evidence only; runtime reads never reconstruct current state from it.

If audit insertion fails, the state transaction rolls back. If the state update fails, no audit snapshot is written. Freeze performs no transaction, state mutation, or audit insertion.

The implementation must add a read helper only for test/audit inspection, such as `list_oos_ledger_snapshots(theme_id)`. It must not become the runtime source of truth.

---

## Minimal implementation boundary

This future specialized task may modify only the following, unless a test proves another direct caller is required:

- `backend/db/strategy.py`: schema, ledger transaction context, state/reservation read/write helpers, and audit inspection helper.
- `backend/services/oos_budget_ledger.py`: replace process dictionaries with the DB-backed transitions above; require `StrategyDB` at construction.
- `tests/test_b5_oos_budget.py`: convert existing ledger behavior tests to a temporary file-backed DB where persistence matters.
- `tests/test_b5_vertical_flow.py`: inject the DB-backed ledger; do not execute real OOS data.
- A new focused test module for persistence/concurrency/recovery, for example `tests/test_oos_budget_ledger_persistence.py`.

It must not modify coverage packages, formal qualification, universe construction, data collection, templates, `ResearchProtocolFreezer`, `B6ValidationFlow`, Gate, Promotion, Signal, or `backend/app/main.py` in this specialized task. Those are separate follow-on decisions.

---

## TDD acceptance matrix

Every listed test is written RED first and run with `pytest -p no:cacheprovider`. No real B6/OOS computation is run.

| Test | Required proof |
|---|---|
| `test_read_of_absent_owner_is_default_and_writes_no_row` | freeze-style preflight can read availability without creating state or audit records. |
| `test_reserve_survives_new_service_and_connection` | a reservation written through one service is visible from a new `StrategyDB` connection to the same file. |
| `test_only_one_active_reservation_per_owner` | a second owner-local reserve is rejected while one is reserved or started. |
| `test_start_must_precede_complete` | a reserved reservation cannot complete; start is durable before terminal processing. |
| `test_rejected_completion_consumes_draw` | `rejected` completion increments the count and advances index. |
| `test_pre_execution_release_reuses_index_and_does_not_consume` | only a non-started reservation can release; the next reserve receives the same index. |
| `test_post_start_failure_consumes_draw_and_blocks_same_hash_tuple` | unknown post-start failure is terminal/consuming and cannot be re-run with the same hashes. |
| `test_restart_recovery_of_reserved_and_started_is_conservative` | recovered reserved can release; recovered started must fail/consume and cannot release. |
| `test_hash_tuple_is_persistently_blocked` | completed or started matching hashes are rejected after a new connection is opened. |
| `test_cross_theme_window_data_claim_is_persistently_blocked` | different theme cannot reserve the same window/data; same theme behavior follows the existing rule. |
| `test_three_consumed_draws_exhaust_budget` | the fourth distinct eligible reserve is rejected, including after restart. |
| `test_concurrent_file_connections_allow_exactly_one_same_owner_reserve` | two independent DB connections released by a barrier yield exactly one committed active reservation and no double draw. |
| `test_busy_twice_fails_loud_without_state_change` | exhausted bounded retry surfaces the concurrency error and leaves state/audit unchanged. |
| `test_state_and_audit_are_atomic` | force audit insertion failure and prove neither reservation/state nor audit transition commits. |
| `test_freeze_preflight_path_has_zero_writes` | the injected read-only preflight performs no `INSERT`, `UPDATE`, or audit append. |

Existing semantic tests for cache, three-draw limit, release, rejected-result consumption, and cross-theme reuse must remain and be adapted to the persistent owner. Any incompatible legacy test must be changed only where it relied on an in-memory process-local behavior contradicted by this decision.

---

## Non-goals and release criteria

Non-goals:

- executing B6/OOS or viewing any OOS result;
- protocol coverage freeze and its canonical coverage binding;
- Gate, Promotion, Signal, or live trading;
- data backfill, universe changes, or exception rules;
- event sourcing, TTL auto-release, distributed databases, or a dashboard.

This design is ready to request implementation authorization only when the implementation task agrees to the exact transaction, recovery, and test criteria above. Until then—and until every acceptance test passes—the B6/OOS mainline remains **`validation_unavailable`**. No one may claim structural correctness of a B6/OOS run or authorization to enter B6/OOS.
