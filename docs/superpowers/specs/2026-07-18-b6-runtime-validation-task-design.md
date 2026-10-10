# B6 Runtime Validation Task Design

**Status:** Owner-approved and SOL-reviewed design. This document is not implementation or execution authority. The workflow remains `validation_unavailable`.

**Main-chain anchor:** [credible manual trading decision closure plan](../plans/2026-07-10-credible-manual-trading-decision-closure-plan.md). It supports Task 2's Approval Card request/status UI and Task 4's durable B6 runtime. It does not replace Task 0 browser acceptance or mark Task 3 complete.

**Current user-visible blocker:** the canonical Task 0 run, [`CREDIBLE_RUN_20260715_100308`](../../verification/CREDIBLE_RUN_20260715_100308/), stops at `no_validated_signal_visible_in_dom`. This design may eventually make a validation request observable; it neither creates a signal nor authorizes B6, OOS, Gate, Promotion, or Signal today.

## 1. Purpose and boundaries

The normal user action is **Continue validation** on the server-owned Approval Card. It must create at most one durable B6 validation task for one immutable strategy revision and show an honest state: unavailable, queued, running, blocked, completed, or failed.

The browser submits only `strategy_revision_id` to:

```text
POST /api/strategy-validations/{strategy_revision_id}/continue
```

It may not select a protocol, template, hashes, OOS window, budget, reservation, or human decision. The application service must prove that the revision belongs to the current server-side Approval Card/candidate context before it reads validation state; a user must not be able to validate an unrelated revision by guessing an ID.

The CLI is diagnostics/recovery only and calls this same application service. `generate_planned_signals.py`, static-list universe code, and any direct B6 call are not runtime entry points.

## 2. Immutable protocol selection

The only B6-admissible profile is `b6_coverage_bound` from the existing [B6 freeze binding design](../../verification/B6_PROTOCOL_FREEZE_CONTRACT_BINDING_DESIGN.md). `legacy_b3` remains readable but is never a B6 credential.

`ResearchProtocolSnapshot.protocol_snapshot_id` is the sole protocol identity and write-once conflict owner. Immutable old and new snapshots may coexist with the same `strategy_revision_id` and `protocol_profile="b6_coverage_bound"`; a criteria or bound-artifact change therefore does not require inventing a new strategy revision merely to avoid a database uniqueness constraint. Each stored row still carries the complete frozen binding and is append-only: an existing ID may be reused only after exact payload comparison, and a same-ID/different-payload conflict fails loudly.

The revision/profile lookup is a strict typed helper, not an execution selector. For `(strategy_revision_id, protocol_profile)` it returns exactly one of:

- zero rows: `protocol_snapshot_unavailable`;
- one row: the exact row after frozen-binding validation;
- more than one row: `protocol_snapshot_ambiguous`.

The helper never silently chooses the first row, latest row, database order, `ORDER BY ... LIMIT 1`, or a client-supplied substitute. Every production execution, publication, task-admission, report, and Gate path must carry and validate an explicit server-owned `protocol_snapshot_id`. A revision/profile lookup may be used only where this strict 0/1/>1 result is itself the required preflight evidence; it may not select a protocol when the result is ambiguous. Approval-clicking may not freeze a protocol.

`ResearchProtocolSnapshot` persists `protocol_profile` and all B6 binding fields. The primary key on `protocol_snapshot_id` remains unique. The former migration-002 partial unique index is historical schema state only; the active schema uses a nonunique lookup index:

```sql
CREATE INDEX IF NOT EXISTS idx_protocol_b6_profile_per_revision
ON research_protocol_snapshots(strategy_revision_id, protocol_profile);
```

Migration `004` is the exact, lossless schema transition: inside `BEGIN IMMEDIATE`, `DROP INDEX IF EXISTS uq_protocol_b6_profile_per_revision`, create the nonunique `idx_protocol_b6_profile_per_revision`, then commit; any error rolls back. It does not rebuild the table or alter rows, the primary key, triggers, or foreign keys. Fresh setup applies migration 002 and then 004; upgrade applies 004 to the existing migration-002 schema. Existing tasks/reports/Gates keep their explicit foreign-key binding to the old protocol, and future rows may bind a distinct new protocol under the same revision/profile.

## 3. Single durable owner and task identity

One configured, file-backed `StrategyDB` owns the B6 task, frozen protocol, OOS ledger/reservation, immutable report, and Gate result. They must use the same database identity. Each approved reserve, recovery, and terminal boundary uses an explicit transaction on that same database; no transaction spans OOS execution. `:memory:`, a generic task database, cross-database writes, saga/outbox/reconciliation, and in-process state are prohibited.

The task key is SHA-256 of sorted-key compact canonical JSON:

```json
{
  "protocol_profile": "b6_coverage_bound",
  "protocol_snapshot_id": "...",
  "strategy_revision_id": "...",
  "task_contract_version": "v1",
  "task_type": "b6_validation"
}
```

The durable payload additionally stores values that the worker must revalidate:

```text
theme_id
hypothesis_source_snapshot_id
strategy_config_hash
data_snapshot_hash
gate_criteria_hash
shared_oos_window_id
```

It excludes time, operator, Approval Card/conversation ID, physical path, database path, draw index, reservation ID, and current budget state. A database unique constraint on `task_key` makes duplicate clicks and concurrent inserts converge to the same row.

`task_key` is also the ledger idempotency key, or deterministically maps to one durable equivalent key. A reservation must be uniquely queryable by that key and bind `protocol_snapshot_id`. Immutable report and Gate result must each bind both `task_key` and `protocol_snapshot_id` (a Gate foreign key through the report is acceptable only when that chain is unique and validated). Recovery never uses timestamp, latest-record, or revision-only matching.

## 4. Request ordering and first preflight

The request service follows this exact order:

   1. Read the current Approval Card/candidate context, strategy revision, and an explicit server-owned B6 protocol snapshot ID with its exact frozen bindings; a strict revision/profile helper may supply this only when it returns one validated row.
2. Read the task by `task_key`.
   - `queued`, `running`, `completed`, or `failed`: return that durable task immediately. Current active, exhausted, or consumed ledger state cannot rewrite a repeat click into `validation_unavailable`.
   - `blocked`: run the complete first preflight. If it now passes, atomically transition that same row from `blocked` to `queued`; otherwise return the existing task and the current typed reason.
   - no row: run the complete first preflight. Insert `queued` only if it passes.
3. A concurrent insert conflict reads and returns the winner's task.

The complete first preflight is read-only. It resolves and validates the frozen revision/protocol, formal B3/PIT and execution-input bindings, formal data snapshot, availability-bounded successor and coverage, approved exact template/version/hash/requirements/scope, gate and kill references, plus exactly one `ledger.get_ledger_state()` call. It follows all hard gates and reason codes in the B6 freeze design.

For a nonexistent task, unavailable preflight returns typed `validation_unavailable` and writes **nothing**: no task, protocol, ledger state, reservation, business audit, report, Gate, Promotion, or Signal. The UI must not present a queued/running state. This preserves preflight-before-insert while retaining repeat-click idempotency for every existing task state.

## 5. Task lifecycle, worker, and recovery

The task states are `queued`, `running`, `blocked`, `completed`, and `failed`. Only `completed` and `failed` are terminal. `blocked` means the worker's second preflight failed before a reservation; it consumes no budget and may later be requeued on the same task row/key after a successful first preflight.

Only one worker claims work. Claiming is a conditional update inside a database transaction and must assert exactly one affected row; a separate `SELECT` followed by unconditional `UPDATE` is invalid. Claiming a pre-existing task may write `running`.

After claim, the worker repeats the full read-only preflight. If it fails, the worker may atomically write only `blocked` and its typed reason to the existing task. It must not write protocol, ledger, reservation, report, Gate, Promotion, or Signal. If it passes, B6 repeats binding checks and atomically reserves at the true execution boundary; preflight is not a budget lock.

If that reserve is normally rejected because concurrent state made the budget or reservation unavailable, and no reservation was created or draw consumed, the worker atomically changes the existing `running` task to `blocked` with the typed reason. It leaves no `running` task or partial ledger/reservation write. A binding/hash/database-invariant violation is instead fail-loud: atomically mark the existing task `failed` with `invariant_error` and do not auto-requeue. Only a successful reserve proceeds to the recovery matrix below.

Recovery is deterministic from the durable `task_key` linkage:

| Durable state | Required recovery |
|---|---|
| `queued`, or claim transaction not committed | leave/recover as `queued` |
| `running` with no reservation | requeue the same task |
| `reserved` and never started | atomically `release_pre_execution`, then requeue the same task |
| `started` | do not rerun; atomically `fail_after_start`, consume the draw, and fail the task |
| reservation completed | accept only when matching task/protocol immutable report and Gate exist; otherwise fail loudly as a database invariant violation |
| reservation failed | terminal task failure; do not rerun |

Only worker startup recovery may act on a running task; it may not create another execution attempt.

## 6. Atomic completion and separation of concerns

Reserve and terminal persistence are separate short SQLite transactions:

1. At the true execution boundary, the reserve transaction atomically creates the `task_key`-linked reservation and changes ledger state to reserved. An injected write failure rolls this reserve transaction back completely. It commits before OOS execution begins and is never held open during OOS execution.
2. After OOS returns, every successful validation writes in one terminal transaction:

   1. immutable report and Gate result;
   2. completed ledger/reservation state;
   3. task `completed` state.

If execution started and an error or result-visibility ambiguity occurs, the terminal transaction writes the applicable failure audit, changes the ledger/reservation through `fail_after_start` and consumed state, and marks the task `failed`. A write failure rolls back its own short transaction. A completed ledger state must coexist with a completed task and matching immutable report/Gate chain. A failed/consumed ledger state must coexist with a failed task and matching failure audit; it does not fabricate a report or Gate result.

The B6 validation API and worker do not accept `human_decision`. A successful validation persists its report and Gate even when no Promotion occurs. Promotion is a later, independent human confirmation transaction; Signal admission is a later independent decision. A Gate verdict is not a promotion, signal, or trading authorization.

## 7. Required prerequisites and explicit exclusions

Before an implementation can queue a new task, machine-validated prerequisites must exist:

- an accepted formal PIT membership snapshot and production B3 universe/execution inputs;
- a formal `DataSnapshotManifest` with exact snapshot/input bindings;
- exact availability-bounded successor and canonical coverage bindings for this profile;
- an approved exact template/version/hash/requirements/source scope;
- frozen, real gate and kill snapshots with recomputed canonical content hashes;
- persisted B6 protocol profile/bindings, explicit protocol IDs, and the migration-004 nonunique lookup index;
- a configured shared file-backed `StrategyDB` and DB-backed ledger;
- B6 validation separated from Promotion and durable report/Gate persistence.

This document does not create those artifacts, change data, create a protocol, reserve OOS, run or view OOS, evaluate a Gate, promote a strategy, publish a signal, or alter the Task 0 acceptance chain.

## 8. Implementation acceptance requirements

Later implementation must use focused RED-to-GREEN tests at the real application-service and SQLite boundaries. At minimum, tests must prove:

1. first unavailable request performs zero task and protected-business writes;
2. repeat clicks for queued/running/completed/failed return the same task despite active or consumed ledger state;
3. blocked tasks only requeue on successful fresh first preflight, using the same row/key;
4. concurrent file-backed database connections produce one task and one claim;
5. the worker second preflight writes only `blocked` on failure and calls no protected executor/ledger operation;
6. `task_key` uniquely joins reservation, report, Gate, and protocol, and every mismatched key/profile is rejected;
7. the short reserve transaction rolls back reservation and ledger state together under injected reserve-write failure, while the separate terminal transaction rolls back report/Gate, terminal ledger transition, and terminal task state together under injected terminal-write failure;
8. every recovery-matrix row is exercised using persistent database state, including a started crash that consumes its draw and never reruns;
9. B6 cannot receive `human_decision`, and a successful validation persists report/Gate without Promotion;
10. the browser shows typed unavailable rather than a fictitious job when prerequisites are absent.

All claims of implementation readiness require these tests with no failed, skipped, or xfailed required cases and a renewed Task 0 browser run. Before this v2 admission is implemented and separately verified, the only permitted status is `validation_unavailable`; after it is verified, the explicit queued admission state is also permitted at the task-creation boundary described below.

## 9. B6 validation task contract v2: B5 evidence binding (2026-08-18)

This is an additive contract amendment for new tasks. It does not rewrite, migrate in place, or reinterpret historical v1 rows. A v1 row remains readable as a legacy task, but it is not a B5-bound task and cannot be treated as the v2 admission evidence for a new execution.

### 9.1 Exact v2 model and payload

`B6ValidationTask` remains the Pydantic owner and keeps `extra="forbid"`, frozen values, the existing task fields, and the existing lifecycle statuses. The v2 model adds exactly these two optional-at-the-model-boundary fields:

```text
b5_bundle_id: str | None = None
b5_bundle_manifest_sha256: str | None = None
```

The fields are a pair:

- v2 requires `task_contract_version == "v2"`, `task_type == "b6_validation"`, and both B5 fields present;
- v1 rows are loaded with both fields absent/null and retain `task_contract_version == "v1"`;
- one present and one absent is invalid for every version;
- a new admission never creates a v1 task and never upgrades a historical row in place.

`b5_bundle_id` is a non-empty, path-free opaque identifier. It may not contain a path separator, control character, or traversal component. `b5_bundle_manifest_sha256` is exactly 64 lowercase hexadecimal characters matching `^[0-9a-f]{64}$`. The existing Pydantic extra-field rejection applies to the task and its v2 payload. The persisted v2 `payload_json` contains the existing task contract fields plus these two fields and no B5 result IDs or result hashes. The verified B5 manifest remains the sole immutable commitment to the four results and the B4 lineage.

The B5 manifest security disclosure is unchanged and is checked exactly, not translated:

```text
authorization_scope = "v3_b5_contract_fixture_only"
not_authorized_for_b6_oos_gate_promotion_signal = true
```

Those values are evidence that the bundle is not itself an OOS credential. Formal B6 task admission is the separate authorization boundary for a later controlled worker/OOS path; task creation alone does not authorize that path.

### 9.2 Canonical v1/v2 task identity

The v1 canonical object remains exactly the existing five-field object:

```json
{"protocol_profile":"b6_coverage_bound","protocol_snapshot_id":"...","strategy_revision_id":"...","task_contract_version":"v1","task_type":"b6_validation"}
```

The v2 canonical object has exactly these seven fields—no missing or extra field:

```json
{"b5_bundle_id":"...","b5_bundle_manifest_sha256":"...","protocol_profile":"b6_coverage_bound","protocol_snapshot_id":"...","strategy_revision_id":"...","task_contract_version":"v2","task_type":"b6_validation"}
```

For either version, canonicalization is `json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`, encoded as UTF-8, then hashed with SHA-256 and rendered as 64 lowercase hexadecimal characters. `task_key` is that digest. The v2 B5 ID and manifest hash therefore participate in identity; changing either produces a different key and may not reuse an existing task.

The task ID is deterministically derived from the canonical task key using the existing local canonical-ID convention (`kind="b6_validation_task"`, payload `{"task_key": task_key}`), so a retry can reconstruct the same complete task object. A caller-supplied task ID that disagrees with this identity is an invariant error, not a new task.

### 9.3 Migration and legacy compatibility

The deployed `migration_002_add_b6_runtime_schema.py` is not rewritten. A new additive migration adds nullable `b5_bundle_id` and `b5_bundle_manifest_sha256` columns to `b6_validation_tasks` when absent, inside the existing short `BEGIN IMMEDIATE`/commit/rollback migration boundary. It must work both when upgrading a database containing v1 rows and when applied after fresh creation of the v1 table. Existing rows remain unchanged and have null B5 columns; their original `payload_json`, task key, status, and timestamps are preserved.

The row loader accepts old v1 payloads without the new fields. A v2 row must have the two database columns, the two payload fields, and the v2 version in agreement. A disagreement between live columns and payload is a fail-loud invariant error. No schema operation may drop, rename, rewrite, or backfill historical B6 rows.

### 9.4 B5 admission and B4/protocol lineage

The one-shot admission caller performs read-only verification after the existing criteria, B4, B5, and exact `b6_coverage_bound` protocol evidence are available, and before creating or reconciling a B6 task. It reuses the existing B5 service/verifier (`verify_b5_bundle` through the verified caller path); it does not copy verifier logic or accept publisher output on trust.

Admission must verify:

1. the B5 bundle and manifest/sidecars are exact and the two unchanged security disclosure fields above are present;
2. the discovered B4 artifact ID, manifest SHA-256, and event-result SHA-256 equal `manifest.lineage.b4.artifact_id`, `manifest.lineage.b4.manifest_sha256`, and `manifest.lineage.b4.event_sha256`;
3. the B5 manifest's formal snapshot, membership, calendar, scope, source, protocol, and IS bindings agree with the already verified B4/protocol lineage; and
4. the task stores only `b5_bundle_id` and `b5_bundle_manifest_sha256`, relying on the immutable verified manifest for the four result references and B4 lineage.

Missing, tampered, invalid, or lineage-mismatched B4/B5/protocol evidence returns the existing typed unavailable/hard-block result and creates no B6 task. It must not create a protocol as a side effect of a failed B5 admission.

### 9.5 Exact create-or-get and durable state

The existing `StrategyDB` remains the only durable owner. The v2 path adds a narrow `create_or_get_b6_task` operation in that owner; the legacy `create_b6_task` remains available only for existing v1-compatible callers. The v2 operation accepts a fully validated v2 `B6ValidationTask` and returns `(winner_task, created)`.

The requested object is first validated as a new-admission object: v2, exact B5 field pair, `status="queued"`, and `blocking_reason_code`, `blocking_reason_detail`, `claimed_at`, and `completed_at` all null. A caller may not use create-or-get to inject a running or terminal lifecycle state.

The operation then uses one short `BEGIN IMMEDIATE` write transaction:

1. select by the unique `task_key`;
2. if absent, execute an ordinary `INSERT` for one queued v2 row; `INSERT OR IGNORE` is forbidden. A unique conflict that is not the already-read same-key winner is fail-loud;
3. before commit, select/re-read by `task_key` in the same uncommitted transaction, validate that the persisted columns and payload agree on the immutable fields, and exact-compare the frozen admission identity;
4. commit only after every insert, re-read, storage-consistency, and identity check passes, then return the winner with `created=True` for a new row or `created=False` for an exact existing winner.

SQLite's `BEGIN IMMEDIATE` serializes writers. A second writer waits for the first transaction; after the first commit, its `SELECT` sees the winner. There is no separate post-commit verification or concurrent-insert-after-select branch.

The exact retry identity comparison contains only these immutable admission fields: `task_id`, `task_key`, `task_type`, `task_contract_version`, `strategy_revision_id`, `protocol_snapshot_id`, `b5_bundle_id`, and `b5_bundle_manifest_sha256`. The payload and live columns must agree on those fields. `created_at` is persisted winner metadata: for a new row it must equal the value inserted in that transaction, but it is not compared with a retry request. `status`, `blocking_reason_code`, `blocking_reason_detail`, `claimed_at`, and `completed_at` are lifecycle fields; they do not participate in retry identity, and an existing winner in any legal lifecycle state is returned unchanged. The operation does not require full `payload_json` byte equality; it validates only the immutable payload/column bindings needed by this contract and leaves the existing live-state overlay semantics intact.

A same-key different immutable field, B5 binding, task ID, or task key is an identity conflict and fails loudly; a different `created_at` or already-progressed legal lifecycle state is not a conflict. Insert, migration, re-read, storage-consistency, or identity-validation failure rolls back the still-open transaction and leaves no partial v2 row. An exact retry returns the same durable winner and never creates a second row. The observable admission result identifies `b6_task_created` versus `b6_task_reused`, task ID/key, version, B5 bundle ID/manifest SHA, and the winner's current status. It must never report a created task when the insert or in-transaction check is unknown.

### 9.6 Zero OOS side effects and hard boundary

Task creation is a persistence-only admission stage. It must not instantiate or call an OOS ledger/controller, read ledger state, reserve a draw, start execution, consume a draw, build an immutable report, evaluate a Gate, promote, or publish a Signal. The future independent B6 preflight may perform the one ledger-state read required by the frozen runtime design, but that read is outside v2 task creation and is not part of this amendment's execution.

After exact admission, the one-shot may create or reuse only a `queued` v2 task and then stop. It does not claim a worker or call `B6ValidationFlow.run_minimal_validation`. Worker claim, OOS reserve/read/start/consume, immutable report, Gate, human confirmation, Promotion, and Signal remain separate downstream boundaries and are not authorized here.

## 10. v2 implementation acceptance and stop rules

The implementation must use focused real Pydantic, file-backed SQLite, and one-shot caller tests. Required cases are: paired-field and SHA validation; exact v1/v2 key distinction; fresh-schema and v1-upgrade migration; exact create/reuse; same-key conflict; rollback; concurrent one-winner behavior; B4/B5 lineage rejection before task creation; valid one-shot create/reuse of queued v2; and zero OOS rows/calls during task admission. No full-suite or production execution is implied by these cases.

Stop immediately on a new independent root cause, any B5 authorization-field change, any v1 rewrite, any verifier bypass, any OOS read/reserve/start/consume, any worker/report/Gate/Promotion/Signal call, or any failure of the authorized one-round correction. Until the focused implementation and later separately authorized production task-creation preflight pass, the public status remains `validation_unavailable` or the explicit queued admission state; it is not OOS authorization, Gate approval, Promotion, Signal admission, or a claim of trading readiness.

## 11. Explicit-task worker and same-draw Alpha contract (2026-08-21)

This additive amendment is the design boundary for the next B6 phase. It does not claim, start, or consume the currently queued production task, and it does not authorize a production OOS draw. Where an older section describes the current worker/flow as already complete, this amendment controls: the repository currently has no B6-specific production worker entry, so the worker is a new narrow application owner and the existing B6 flow is reused only after the missing result/report seams are made explicit.

### 11.1 One explicit task owner and API

The only worker application owner is a narrow `B6ValidationWorker` in `backend/services/b6_validation_worker.py`. Its production operation is conceptually:

```text
run_task(task_id: str) -> B6WorkerResult
```

The only CLI is a thin wrapper in `scripts/run_b6_validation_task.py` whose required input is one explicit `task_id`. It calls the application service and prints its deterministic result. The CLI must not accept a protocol ID, revision override, OOS dates, budget, cost/stress parameters, benchmark choice, universe, or user technical parameters. It must not scan for `latest`, choose an arbitrary queued row, poll, or create a second task. The application service and CLI use the same configured file-backed `StrategyDB` as the task, protocol, ledger, report, and Gate.

The worker result exposes the durable task state and typed boundary evidence: `task_id`, `task_key`, `task_status`, `status`, `reason`, and, when present, the exact `reservation_id`, `report_id`, `gate_result_id`, and `explanation_id`. It also exposes `oos_authorized` and `oos_consumed`; these are facts (`false` before reservation, and derived from the durable chain afterward), not caller-controlled flags. `promotion_id` remains absent/null in every B6 result.

State handling is deterministic:

- `queued` is claimed by one conditional `task_id` update that must affect exactly one row; a zero-row update is a typed not-claimed result and never starts work.
- `blocked` and terminal `completed`/`failed` tasks are returned without execution. A later requeue operation, if separately authorized, must use the same task row/key; this worker does not create a retry task.
- `running` is handled only through exact recovery using that task ID, task key, and any task-key-bound reservation. It never creates a new attempt. A running task without a reservation may be requeued as the same task only after the durable absence is proven. A running task with a reservation follows the recovery matrix below.

The generic `backend/app/worker.py::poll_once` is not the B6 owner: it selects the generic `tasks` table, does not accept a B6 task ID, and has no B6 executor. It must not be adapted into a latest/queued scanner.

### 11.2 Claim, second preflight, and reservation boundary

After a successful claim, the worker performs a second read-only preflight before any reservation or execution. It re-verifies, using the explicit task and the already verified immutable inputs:

1. task v2 identity, task key/ID canonicality, `strategy_revision_id`, `protocol_snapshot_id`, and task lifecycle state;
2. the B5 bundle directory, manifest, sidecars, verifier status, exact `b5_bundle_id` and manifest SHA, `authorization_scope="v3_b5_contract_fixture_only"`, and `not_authorized_for_b6_oos_gate_promotion_signal=true`;
3. B5 lineage against the exact B4 artifact ID, B4 manifest SHA, B4 event-result SHA, formal snapshot, membership, calendar, scope, protocol, and revision;
4. the protocol's frozen OOS window and all input identities required by the execution envelope; and
5. the task-to-protocol/revision/B5 binding before any protected write.

For a claim that reaches the budget check, the second preflight performs exactly one `OOSBudgetLedger.get_ledger_state()` read. It does not reserve or create ledger state. If immutable task/B5/protocol/input checks fail before that point, it returns the typed preflight block and performs zero ledger reads; this is still before any OOS side effect. A ledger-state read is never repeated as an optimization or hidden retry.

Preflight failure atomically changes the claimed task from `running` to `blocked` with a stable reason and leaves reservation, ledger, report, Gate, Promotion, and Signal rows untouched. A normal reserve rejection (budget unavailable, active reservation, or other expected availability condition) likewise changes `running` to `blocked` with no reservation and no consumed draw. A binding, hash, schema, task identity, or database invariant violation changes the task to `failed` with `invariant_error`; it is not silently requeued.

Only after the second preflight passes may the worker call the existing `OOSBudgetLedger.reserve_oos_draw` with the task key as the idempotency key and the exact protocol binding. A successful reservation commits before execution. `start_execution` is the next explicit boundary. A start failure before the state becomes `started` releases the pre-execution reservation and blocks the same task. Once the reservation is `started`, every exception or result-visibility ambiguity is `fail_after_start`: the draw is consumed, the task becomes `failed`, and no rerun is allowed.

The B5 fixture-only/not-authorized fields are never flipped or deleted. Creating and claiming a formally admitted B6 task is the separate authorization boundary for the worker path; it does not turn the B5 bundle into an OOS credential.

### 11.3 Reusable B4 execution entry and frozen input envelope

The verified concrete B4 execution entry is the existing:

```text
strategy_core.backtest_engine.run_event_backtest(...)
  -> strategy_core.v3_relative_strength_executor.run_v3_relative_strength_backtest(...)
```

For the v3 strategy branch, the existing caller contract is `V3RelativeStrengthExecutionSpec` plus a cursor-bound formal data source. The production binding must construct that spec from the frozen protocol, with `backtest_start` and `backtest_end` equal to the protocol-owned OOS window, and pass the exact protocol ID, data snapshot hash, initial capital, and independently verified supplement path. The data source is the existing `FormalPITPartitionAdapter` behind the read-bound adapter; its maximum requested date is the protocol OOS end. The common trading calendar and PIT membership are read from the same frozen input identity. No caller-supplied OOS date or source path is accepted.

This is a real engine/input boundary, not a new executor name. The current `run_event_backtest`/`run_v3_relative_strength_backtest` returns the strategy `EventBacktestResult` and embeds the base fill-cost behavior. The current repository does not expose a B4 OOS function that also returns benchmark, same-universe control, and stress-cost results: `BacktestReportBuilder` currently marks those values as unavailable, `CostStressRunner` validates/calculates stress assumptions but does not execute a second portfolio, and `ControlComparison` only validates supplied comparison values. The next implementation therefore adds one narrow callable in `backend/services/b6_same_draw_executor.py`, not a second OOS runner, generic factory registry, or parallel worker.

The production callable has the exact boundary:

```text
execute_production_same_draw(
    envelope: Mapping[str, Any],
    *,
    repo_root: Path,
) -> B6SameDrawOOSResult
```

`repo_root` is server-owned configuration bound by the thin CLI; the caller cannot supply dates, hashes, strategy parameters, benchmark choice, universe, or a data source. The CLI validates that this real callable and its concrete dependencies are available before opening the task database or invoking the worker. The worker invokes the callable once, after `start_execution`, with the already verified envelope. Tests may inject a deterministic fake callable only through the existing worker seam and temporary file-backed databases.

The callable creates one immutable local execution sidecar for the strategy from the existing `V3DailyPortfolioObservation` observer, `EventBacktestResult` fills, frozen initial capital, and the shared read audit. Its exact fields are `starting_nav`, an ordered finite `(date, portfolio_value)` observation tuple covering the OOS execution dates, `ending_nav_base`, the immutable fill tuple, `base_fill_cost_total`, and `stress_fill_cost_total`; the sidecar is local and is not serialized as a historical B4 artifact. A missing observation date or a fill/intents mismatch is a hard error, not a substituted NAV. It does not modify the historical `EventBacktestResult` model or rewrite the B4 artifact. It runs the strategy once through the concrete B4 entry above, then derives benchmark and same-universe control from the pure `industry_weights`, `control_weights`, `rebalance_fractional`, and validation arithmetic in `backend/services/v3_b5_comparison.py`. The three portfolios have independent positions, marks, cash, and last-price state, but share one server-owned `FormalPITPartitionAdapter`, calendar, PIT membership identity, OOS date bound, and read-audit owner. B5 IS loaders, observations, publisher payloads, and numerical result values are never read as OOS results.

The only allowed execution sequence is one callable, one shared OOS envelope, and one already-started reservation. The callable must not reserve, start, consume, release, retry, or read a second OOS draw. A missing source, invalid input identity, future read, missing series, or cost inconsistency fails before a result is returned. The absence of these OOS outputs remains a pre-production implementation gap and is not permission to consume a draw.

#### 11.3.1 Same-draw cost and NAV formula

The result uses the existing frozen cost code; no new cost parameter or estimate is introduced.

For the strategy sidecar, the base engine's `portfolio_value` already includes the existing base fill model (`commission_rate=0.0003`, minimum commission `5.0`, sell stamp duty `0.001`, transfer fee `0.0`, zero slippage). For each strategy fill, direction comes from its immutable order intent. Let `p` be the immutable base fill price and `q` the filled quantity:

```text
base_fill_cost = calculate_transaction_costs(direction, q, p, 0.0003, 5.0, 0.001, 0.0)[4]
stress_price = p * 1.001 if direction == "buy" else p * 0.999
stress_fill_cost = calculate_transaction_costs(direction, q, stress_price, 0.0006, 5.0, 0.001, 0.0)[4]
                 + abs(stress_price - p) * q
```

The executor must recompute both totals from the same fill trace and reject a conflicting fill/intents ledger. `strategy_starting_nav` is the server-owned v3 `initial_capital`; `strategy_ending_nav_base` is the final observed strategy portfolio value after the base engine run; and:

```text
strategy_ending_nav_stress = strategy_ending_nav_base
                           - (stress_fill_cost_total - base_fill_cost_total)
strategy_net_return_base   = strategy_ending_nav_base / strategy_starting_nav - 1
strategy_net_return_stress = strategy_ending_nav_stress / strategy_starting_nav - 1
```

The base amount is not subtracted a second time. A non-positive or non-finite stress NAV is a fail-loud cost/result error.

For benchmark and same-universe control, the executor preserves the existing fractional contract in `rebalance_fractional`: each rebalance records normalized turnover `(sell_proceeds + actual_buy_total) / pre_trade_nav`, then applies the frozen `BASE_COST_BPS` and `STRESS_COST_BPS` constants as `turnover * bps / 10000`; cumulative base/stress costs are subtracted from that portfolio's gross NAV. The comparator starts at the frozen `INITIAL_NAV=1.0`, uses the same OOS dates and shared source, and returns `ending_net_nav / INITIAL_NAV - 1`. The executor must not read the B5 cost artifact's IS aggregate values; it uses only the frozen code-level cost contract and its source/assumption identity. Any missing or conflicting cost-assumption identity blocks before Alpha derivation.

The `BaseCostResult`/`StressCostResult` pair in the B6 result is the strategy fill-trace cost pair, because the only existing immutable fill ledger is the strategy EventBacktestResult. Benchmark/control cost effects are nevertheless included in their two net-return series by the fractional formula above. The report must state this scope; it must not imply that one strategy cost row is a separate benchmark/control execution ledger.

#### 11.3.2 Shared read-audit contract and local sidecar

The executor owns one read-bound wrapper around the shared formal source. Strategy cursor views and comparator reads must delegate through that owner; no second raw source or uncounted direct adapter is allowed. The executor keeps the ordered trace only in memory and persists this canonical summary, not the raw trace:

```text
schema_version: "b6_same_draw_read_audit.v1"
owner: "b6_same_draw_executor"
allowed_end: ISO date equal to envelope.oos_end
max_requested_date: ISO date or null
future_violation_count: non-negative integer, required 0
operation_counts: sorted map of operation name to non-negative integer
read_count: non-negative integer
canonical_trace_sha256: 64 lowercase hex
```

The trace hash is SHA-256 of UTF-8 canonical JSON using `sort_keys=True`, `ensure_ascii=False`, `separators=(',', ':')`, and `allow_nan=False` over the ordered operation records. The summary is valid only when `max_requested_date` is null or `<= envelope.oos_end`, `future_violation_count == 0`, all counts are finite integers, and the owner/schema are exact. The summary is included in the production B6 same-draw result and canonical report payload; the report hash therefore covers the audit summary and trace hash. No raw trace is stored. Gate revalidates owner/schema/bound/hash shape and forwards “read audit verified”; it adds no read-count or Alpha threshold.

The envelope identity is immutable and contains at least:

```text
task_id, task_key, strategy_revision_id, protocol_snapshot_id,
b5_bundle_id, b5_bundle_manifest_sha256, B4 artifact/manifest/event hashes,
formal snapshot identity, PIT membership identity, calendar identity,
data snapshot identity, shared_oos_window_id, oos_start, oos_end,
base/stress cost-assumption identities, result_schema_version
```

Physical paths, current budget state, reservation ID, and timestamps are runtime metadata and are not substitute input identity. If the frozen protocol/input package does not contain a valid benchmark definition, the worker blocks before reservation; it must not choose a new index or data source.

### 11.4 Same-draw result, arithmetic Alpha, and fail-loud semantics

The single execution callable returns one immutable `b6_same_draw_oos_result.v1` payload. All returns are finite decimal fractions over the same frozen OOS window and are net of the named base or stress costs. The payload must contain:

```text
strategy_net_return_base
strategy_net_return_stress
benchmark_net_return_base
benchmark_net_return_stress
same_universe_control_return_base
same_universe_control_return_stress
alpha_vs_benchmark_base
alpha_vs_benchmark_stress
alpha_vs_control_base
alpha_vs_control_stress
base_cost_result
stress_cost_result
```

The only Alpha formulas are arithmetic decompositions:

```text
alpha_vs_benchmark_base  = strategy_net_return_base - benchmark_net_return_base
alpha_vs_benchmark_stress = strategy_net_return_stress - benchmark_net_return_stress
alpha_vs_control_base    = strategy_net_return_base - same_universe_control_return_base
alpha_vs_control_stress  = strategy_net_return_stress - same_universe_control_return_stress
```

The result must also bind the envelope identity, OOS window, input hashes, result schema/version, finite positive strategy starting NAV, finite strategy ending NAVs, and the read-audit summary above. Production uses additive `b6_same_draw_oos_result.v2`/`b6_same_draw_oos_report.v2` payloads with the required audit summary; existing v1 synthetic Phase5A fixtures remain readable but are not eligible for a production terminal chain without the v2 audit. For v2, `BaseCostResult.assumptions_hash` and `StressCostResult.assumptions_hash` must equal the server-owned frozen cost identities used by the executor; the result does not copy B5 IS aggregate cost values. Missing series, mismatched windows/inputs, non-finite values, zero or non-positive starting/stress NAV, invalid cost assumptions, invalid audit bounds, or an arithmetic mismatch are fail-loud. No ratio or contribution percentage is persisted; opposite signs and near-zero total returns make such percentages misleading. The UI may later display the six net-return values and four absolute excess values only as “market movement vs strategy excess (Alpha)”; the word Alpha is not a causal claim.

B5 IS benchmark/control/cost artifacts remain admission evidence only. They cannot fill any OOS result field and cannot be copied into the OOS report.

### 11.5 Report, Gate, explanation, and terminal-chain contract

The immutable report payload, whose canonical JSON is covered by `report_hash`, must include the following in addition to the existing frozen report identity:

```text
schema_version = b6_same_draw_oos_report.v1
task_id, task_key
strategy_revision_id, protocol_snapshot_id
b5_bundle_id, b5_bundle_manifest_sha256
B4 lineage (artifact_id, manifest_sha256, event_result_sha256)
OOS window and shared_oos_window_id
formal/PIT/calendar/data input identities
result_schema_version and the complete same-draw result above
read_audit (the complete canonical summary above)
```

The current database's `payload_json` is the preferred storage surface; no new database columns or migration are authorized merely to duplicate these fields. The report loader/builder must validate the payload before creating the typed report and must hash the canonical payload, not a weaker projection. The existing `ImmutableBacktestReport` top-level binding remains exact for report ID, protocol, revision, data, criteria, draw, and shared window.

`PrototypeGateV2` must revalidate report payload identity, the complete base/stress, benchmark, control, Alpha, and read-audit fields. It may reuse the existing beta-dominated checks and existing Gate criteria; this contract adds no Alpha threshold and no new strategy parameter. Gate checks persist the same-draw comparison/Alpha facts or exact report-field references, and the explanation surfaces the absolute net returns and excess values plus “read audit verified” without issuing buy/sell instructions.

Before terminal commit, the owner must exact-compare one chain:

```text
task.task_id/task_key/protocol/revision/B5 refs
 == reservation.task_key/protocol/revision
 == report payload/task/protocol/revision/B5 refs/lineage/window
 == Gate.report_id/protocol/revision and report hash
 == explanation.report_id/Gate ID
```

The reservation draw index/window and report/Gate payload hashes must be mutually consistent. A successful terminal transaction writes report, Gate, completed reservation/ledger, and completed task atomically; any mismatch or write failure leaves no partial success chain and transitions a started task through the existing consumed-draw failure path. A failed/consumed terminal chain never fabricates a report or Gate. Promotion and Signal remain separate human/application transactions; B6 never calls either.

### 11.6 Recovery and user-visible states

Recovery is selected only by explicit `task_id`, exact `task_key`, and the task-key-bound reservation:

| Durable state | Worker action |
|---|---|
| `queued` | conditional claim, then second preflight |
| `running` without reservation | prove exact absence and requeue the same row, or fail loudly on ambiguity |
| `running` with `reserved`, not started | release that exact reservation, requeue the same row; no new task |
| `running` with `started` | `fail_after_start`, consume the draw, mark task failed; never rerun |
| reservation `completed` | accept only with exact completed report/Gate/task chain; otherwise invariant failure |
| reservation `failed` | terminal failed task; never rerun |
| reservation `released` | same task may remain/re-enter queued only through an explicit recovery transition; no automatic latest scan |
| task `blocked`/`completed`/`failed` | return durable state; do not execute |

The user-visible states are exactly `queued`, `running`, `blocked`, `completed`, and `failed`, with a typed reason and durable evidence. `completed` means the report/Gate/ledger/task chain is verified, not that Promotion or Signal is authorized. `blocked` means no draw was consumed at the blocking boundary; `failed` after `started` means the draw was consumed and must not be retried.

### 11.7 Explicit exclusions

This amendment does not authorize production worker invocation, task claim, ledger-state read, reservation, start, OOS execution, report/Gate write, Promotion, Signal, or any B6 production runner. It adds no data source, strategy, parameter, threshold, precomputed result, parallel framework, or generic worker platform. The first implementation must use a temporary file-backed database and a deterministic fake execution callable; any production preflight and the single production OOS draw require a later independent authorization.

## 12. Criteria evaluator source boundary and Phase5E controls (2026-08-23)

This additive amendment controls the criteria-source repair and the next Phase5E work. It does not reinterpret or overwrite the v1 criteria pair, the v1 execution supplement, the existing B4/B5 artifacts, or the queued v2 B6 task. The old artifacts remain immutable historical evidence. No production OOS draw is authorized by this amendment.

### 12.1 Stable effective-criteria evaluator surface

The only source bound by the new criteria publisher/verifier is the production-only module `backend/services/prototype_gate_criteria_surface.py`. It is a narrow pure evaluator and has no report parser, same-draw parser, read-audit reader, database access, lifecycle write, Gate result builder, Promotion call, or Signal call.

Its public contract is exact:

```text
FrozenEffectiveCriteriaInput(
    future_data_violation_count: int,
    integrity_status: Literal["valid", "invalid"],
    stress_cost_result: JsonValue | None,
    control_comparison: JsonValue | None,
    base_cost_result: JsonValue | None,
    benchmark_comparison: JsonValue | None,
    data_quality_status: str | None,
    beta_dominated: bool | None,
    single_symbol_concentration: JsonValue | None,
    single_month_concentration: JsonValue | None,
)

EffectiveCriteriaDecision(
    blocking_issue_ids: tuple[str, ...],
    verdict: Literal["rejected", "candidate_for_prototype_passed"],
)

is_failed_result(value: JsonValue | None) -> bool
evaluate_effective_criteria(
    inputs: FrozenEffectiveCriteriaInput,
) -> EffectiveCriteriaDecision
```

`JsonValue` means a finite JSON-compatible scalar, array, or object; NaN and infinity are invalid. The model is frozen and `extra="forbid"`. The evaluator applies the six existing effective blocking categories in this deterministic order:

1. `future_data_violation` when `future_data_violation_count > 0`;
2. `invalid_report_integrity` when `integrity_status != "valid"`;
3. `missing_or_failed_b4_result` when any of the four result fields is `None`, `not_available_from_b4_result`, or `is_failed_result(value)`;
4. `invalid_data_quality` when `data_quality_status` is `insufficient` or `invalid`;
5. `beta_dominated` when `beta_dominated is True`;
6. `concentration_risk` when either concentration field satisfies `is_failed_result`.

The decision contains each blocking ID once, in this order, and returns `rejected` when the tuple is non-empty; otherwise it returns `candidate_for_prototype_passed`. It never returns `prototype_passed`, never emits a Promotion or Signal, and introduces no threshold, parameter, ratio, causal Alpha, or data-source choice. The existing `PrototypeGateV2` remains responsible for report parsing, same-draw v2 identity/read-audit/Alpha revalidation, Gate result identity, and evidence checks. It passes only the ten fields above to the stable surface and retains the existing Gate result/report behavior.

### 12.2 Criteria snapshot v2 identity and v1 boundary

The new pair uses these exact constants:

```text
snapshot_schema = "prototype_gate_v2_criteria_snapshot.v2"
envelope_schema = "prototype_gate_v2_criteria_envelope.v2"
criteria_contract_version = "v2"
evaluator_surface_id = "prototype_gate_effective_criteria.v2"
evaluator_algorithm_id = "b6_effective_criteria.v2"
evaluator_repo_relative_path = "backend/services/prototype_gate_criteria_surface.py"
```

For each `kind` in `gate_criteria` and `kill_criteria`, `criteria_content_hash` is SHA-256 of the criteria canonical JSON using `ensure_ascii=False`, `sort_keys=True`, `separators=(",", ":")`, UTF-8, and `allow_nan=False`. The exact identity payload is:

```json
{
  "schema_version": "prototype_gate_v2_criteria_snapshot.v2",
  "criteria_contract_version": "v2",
  "artifact_type": "gate_criteria or kill_criteria",
  "criteria_content_hash": "64 lowercase hex characters",
  "evaluator_surface_id": "prototype_gate_effective_criteria.v2",
  "evaluator_algorithm_id": "b6_effective_criteria.v2",
  "evaluator_source_sha256": "64 lowercase hex characters"
}
```

`identity_sha256` is SHA-256 of that identity payload's canonical UTF-8 JSON. The v2 snapshot ID is `prototype_gate_v2_gate_v2_<identity_sha256[:16]>` or `prototype_gate_v2_kill_v2_<identity_sha256[:16]>`. The v2 manifest stores the complete identity payload, exact evaluator entrypoints, source SHA, criteria content hash, `manifest_content_hash`, `status="published"`, `frozen=true`, and `not_authorized_for_b6_oos_gate_promotion_signal=false`. The v2 manifest hash covers all of those fields. A v2 directory is never selected by a v1 verifier.

The v2 envelope is built from `schema_version`, `criteria_contract_version`, both v2 snapshot IDs, and both criteria content hashes; its `envelope_hash` uses the same canonical JSON rule. The v2 verifier requires exactly one v2 gate and one v2 kill snapshot, exact identity payloads, sidecars, manifest hashes, criteria hashes, source surface, and envelope. It ignores v1 directories only as immutable history. A v1 manifest cannot be upgraded in place, and a v1 artifact cannot be declared v2 by changing a sidecar or copying the current source SHA into it.

The current content-only v1 ID algorithm is not reused for v2. Existing v1 directories remain at their current paths and are never overwritten. Any existing target with a different v2 manifest is a write-once conflict. There is no attestation or exemption path that can preserve a v1 verified status after its bound source has changed.

### 12.3 Required lineage rebuild

The source-only change has a deterministic propagation rule:

| Layer | Required v2 effect |
|---|---|
| Criteria pair | New v2 snapshot IDs, manifest hashes, and envelope identity; old v1 pair unchanged. |
| Execution supplement | Its payload must reference v2 snapshot IDs, v2 manifest hashes, v2 content hashes, and v2 envelope; therefore supplement ID and manifest hash are new. |
| Research protocol | `gate_snapshot_id`, `gate_content_hash`, `kill_content_hash`, and `gate_criteria_hash` must bind the v2 pair. The existing B6 canonical protocol identity therefore produces a new protocol ID; no evaluator source SHA column is added. |
| Strategy revision | May remain unchanged only after a test proves its canonical revision payload does not include criteria evaluator identity. The current revision builder has no such field. |
| B4 | Its manifest binds the new supplement ID/manifest and its artifact ID hashes that payload; the old B4 artifact is not migrated or copied. The EventBacktestResult values may be numerically unchanged, but the new binding must be independently verified. |
| B5 source/cost/ledger/comparison results and bundle | Every result lineage must exact-match the new supplement, protocol, B4, and v2 envelope. A new bundle is required; its fixture-only/not-authorized disclosure is unchanged. |
| B6 task | The old queued task remains immutable. A new v2 task is created only from the new verified B5 bundle and new protocol identity; its task key and task ID are different when either binding changes. |

The rebuild is metadata/lineage work only until a later one-draw authorization. B5 IS numbers are never copied into OOS fields. Each immutable publisher and verifier is run at most once for the new identity; a failure stops the chain and is not retried in the same authorization.

### 12.3.1 Actual E4 operation order and frozen preparation evidence

The actual server-owned operation order is not criteria → supplement → protocol. It is:

```text
criteria v2 verified
  -> pure deterministic candidate protocol payload/ID
  -> freezer v2 criteria-envelope TDD/verification
  -> immutable durable new protocol snapshot
  -> supplement publisher reads the durable protocol binding
  -> supplement publish/verify
  -> B4
  -> B5 four results/bundle
  -> new B6 task
```

There is no identity cycle: the canonical B6 protocol identity does not contain a supplement ID, while the supplement binds the durable protocol ID and its payload SHA. The reviewed candidate is frozen for the next gate: protocol ID `8770c56c5a69ef128442c0f593f9e4b081a6b13c69744b27171b27cc8c8b7bbe` and `model_dump_json` payload SHA `2872d63578d66e6dfc02fd767c4061fd3e291bcb9bbd65f0f2409a4482f6e2a3`. Its only four field differences from the current protocol are `protocol_snapshot_id`, `gate_snapshot_id`, `kill_criteria_snapshot_id`, and `gate_criteria_hash`; revision, formal/successor/coverage/scope/window/data/strategy fields and criteria content hashes are exact reused values.

The current freezer supports only the v1 criteria-envelope calculation. That is the next stop gate: no candidate protocol may be stored until the v2 envelope TDD/verification is green. The new protocol write is a separately authorized, write-once exact operation; a failed insert or exact comparison rolls back, leaves the old protocol and queued task unchanged, and stops before supplement publication. Updating and publishing the v2 supplement is a separate stage that requires the durable new protocol first.

### 12.3.2 E4.4d B5 dependency-order and acceptance amendment (2026-08-26)

This amendment supersedes any earlier E4.4 wording that places cost publication before ledger-observation publication, permits parallel B5 publication, permits reordering, or permits assembling a current result from the old bundle and absent current production targets. The only valid B5 production order is:

```text
current verified B4
  -> ledger observations publish once / official verify once
  -> base/stress costs publish once / official verify once, bound to the verified ledger observation
  -> benchmark/control comparisons publish once / official verify once, bound to the verified ledger observation and cost artifact
  -> bundle pure assembly publish once / official verify once, bound to the four current verified results
```

The ledger artifact is the first B5 result and is the sole upstream observation source. Its verified read-audit must retain `oos_read_count=0`; the clean temporary checkpoint recorded 176 observations and 124 fills. The cost artifact consumes that exact observation directory and exposes the authoritative `fill_count` in its verified manifest; the clean checkpoint verified `fill_count=124`. The comparison builder/verifier consumes the exact ledger and cost bindings and produces the benchmark and same-universe-control results. The bundle publisher performs pure assembly only after all four current result references are independently verified; it must preserve `authorization_scope="v3_b5_contract_fixture_only"` and `not_authorized_for_b6_oos_gate_promotion_signal=true`.

The programmatic comparison verifier has only the trusted temporary-caller seam `verify_artifact(..., *, cost_dir=None, observation_dir=None)`. Those keyword-only paths are not user lineage inputs and are never exposed by the CLI. The CLI accepts only its artifact directory and uses server-owned production defaults. A temporary caller may supply explicit directories solely to verify the serialized chain it just created; it may not use that seam to bypass lineage or substitute a production artifact.

The E4.4 temporary clean-chain evidence is one serialized process in one fresh `TemporaryDirectory`, with `596.917` seconds wall time and `Ran 1`, `OK`. It verified current B4 `cb41dd1dc207642b`, ledger observations `176`, fills `124`, and `read_audit.oos_read_count=0`; cost official verification reported `fill_count=124`; comparison official verification used explicit temporary upstream bindings; and bundle verification accepted the four current results, current lineage, and the fixture-only/not-authorized disclosure. The temporary directory was cleaned by its owner, so stage IDs, manifest hashes, and other temporary artifact identities were not retained. They are intentionally not reconstructed or presented as evidence.

Each production B5 publisher and its official verifier is a separate one-attempt stop gate. The next gate may start only after the previous verifier returns the exact current identity and valid/verified status. Any identity, lineage, mathematics, OOS/read-audit, sidecar, or write-once conflict stops the chain without retry, cleanup, or fallback. Before production B5 completion, Task7 admission, a new task, worker, OOS ledger/state/reservation, report, Gate, Promotion, and Signal remain forbidden. The old bundle `9d388459df4d591e` with manifest `332da22da15acba31a3a5c1c666f7ce5957f439dab538d5bfa98b950b9b2696a` remains immutable historical evidence and is invalid for current admission; it cannot be combined with current or missing production results.

The read-only E4.4 preflight baseline for this amendment is:

| Component | SHA-256 |
|---|---|
| `scripts/publish_v3_b5_ledger_observations.py` | `b4368f3cb90c63cd03c1438209fde2d523e3da339fdf19971ed9350905a83505` |
| `scripts/verify_v3_b5_ledger_observations.py` | `784b861366ac313d4a21b78d76d6512066d14ba43fa6ff2c4cc2f6614676aaaf` |
| `backend/services/v3_b5_costs.py` | `044eac14c8e57131d6da9bd42f5ecd59b450d5fd80e535b5e7202bf6e475900b` |
| `scripts/publish_v3_b5_costs.py` | `417b5cf322bafea26c31d0aad6473ad2a40ae30b0bda865165b49c3df83b3190` |
| `scripts/verify_v3_b5_costs.py` | `482e5ef0576aa02f934bd1e4a3237b5e9ce6df8505325dff70a021da8d1b39ae` |
| `backend/services/v3_b5_comparison.py` | `9f6256dc8d410cb19847983f090bde35e8f95211d78ba450b89f428170e46a79` |
| `scripts/publish_v3_b5_comparisons.py` | `22580677fca1af6b6d8c59ac320061af9fd8c46f638fc6fb93310c3f1eb497d5` |
| `scripts/verify_v3_b5_comparisons.py` | `3292e5a3738b2cdc4b8097df5048bc26a4ccbaaa7f8837c4db44d1cb9df0d778` |
| `backend/services/v3_b5_bundle.py` | `be80a8cd34cdf343898698ba70d02054cfb8e5d357eec53e2fa0bc88134122ae` |
| `scripts/publish_v3_b5_bundle.py` | `6f0489400ace77b5c41842d4c8d5b6b096578effa6ad478b02b06bc64857916c` |
| `scripts/verify_v3_b5_bundle.py` | `e1315949f4cf9ceec8e2e38db26d6eb3f7143777ae1e76e9277f91673eb1f80e` |
| `tests/test_v3_b5_costs.py` | `af04d171f636417c1183192731dd69887a65c3013f7df91f8bcb6cc62206a67f` |
| `tests/test_v3_b5_comparisons.py` | `fa33cce34ceaac10a1102c99c2e2daece3df7220799b41803c239b701f1690f5` |
| `tests/test_v3_b5_bundle.py` | `4ad91e434285746223375895c35d6282d0266ec74a4340ea5c843955ac8b0711` |

The production database read-only baseline is `quick_check=ok`, `foreign_key_check=[]`, and seven-table counts `(2,1,0,0,0,0,0)` for protocol snapshots, B6 tasks, reservations, budget state, evaluation ledgers, reports, and Gate rows. The sole old task remains queued and explicitly bound to protocol `6f7cbdcdeb26f8cdd2611a5450dbab3ff22544b6a66ec8539f5cab9151329111`; all OOS tables remain zero. The current production targets are absent: ledger `acc628b961f2da3b`, costs `53494507dff2f203`, comparisons `3ad1193b3b4a8c0c`, and bundle `3ad1193b3b4a8c0c`. This amendment authorizes no production action and does not execute a publisher or verifier; it stops before the single production ledger publish/verify gate.

### 12.4 Prepared supplement token and second-preflight ordering

The thin CLI may construct a server-owned executor factory before opening the task database, but it must not run the supplement verifier in that factory. After an explicit task has been conditionally claimed, the worker's second preflight must perform all task/B5/B4/protocol/revision checks, then call the official supplement verifier exactly once, before the single ledger-state read and before reserve/start. The verifier must validate the v2 supplement, its sidecars, v2 criteria identity, protocol, revision, B4/B5 lineage, and security disclosures.

The verifier returns a frozen `PreparedSupplementToken` owned by the worker/executor boundary. Its exact fields are `token_schema_version`, `supplement_id`, `manifest_sha256`, `repo_relative_path`, `protocol_snapshot_id`, `strategy_revision_id`, `b5_bundle_id`, `b5_bundle_manifest_sha256`, `criteria_envelope_hash`, `source_bindings`, `verified_manifest_bytes_sha256`, and `prepared_identity_sha256`. The token contains the verified immutable manifest/source-binding representation needed by execution; it is not a caller-supplied path or hash. `prepared_identity_sha256` covers every token field by the canonical JSON rule.

The sequence is fixed: claim → read-only identity checks → one supplement verification → construct token → exactly one `get_ledger_state()` → reserve → start → consume the token exactly once → terminal transaction. The post-start executor consumes the prepared token and must not discover or verify a supplement for the first time. It must not re-read an unverified source or create a second draw. If the prepared token's identity or protected file bytes differ before start, the reservation is released/blocked without a draw. If the difference becomes visible after `started`, the worker uses `fail_after_start`, consumes the draw, marks the task failed, and never reruns. If the existing engine path cannot consume the token's immutable verified representation without a path-based TOCTOU read, Phase5E stops before production; it must not silently fall back to a second verifier call.

The token is runtime preparation evidence, not an OOS credential. The B5 manifest remains `authorization_scope="v3_b5_contract_fixture_only"` and `not_authorized_for_b6_oos_gate_promotion_signal=true` throughout.

### 12.5 Progress, one-time backup, and operator contract

The CLI accepts exactly one explicit `task_id`. It writes no progress to stdout until the final canonical result. Progress is one JSON object per line on stderr with these exact fields:

```text
schema_version: "b6_validation_progress.v1"
event_seq: positive integer, strictly increasing from 1
stage: one of preflight, dependencies_prepared, claimed, second_preflight,
       ledger_state_read, reserved, started, executing, terminal,
       blocked, failed, recovery_required
task_id: exact requested task ID
task_status: queued, running, blocked, completed, or failed
status: running, blocked, completed, failed, or recovery_required
```

An event has no OOS payload, raw trace, source rows, secret, or user-supplied configuration. The final stdout object remains the existing canonical worker result and includes the durable IDs/reason, `oos_authorized`, `oos_consumed`, and null/absent `promotion_id`.

Before claim, the worker performs one server-owned SQLite consistency backup using `sqlite3.Connection.backup`. The target is `data/strategy_backups/b6_preclaim/<task_id>.<source_db_sha256>.sqlite3`; it is written through a sibling temporary file, flushed/fsynced, and atomically replaced. An exact existing backup is reused; a mismatch or failed backup is a hard pre-claim block. The caller cannot supply a backup path. A backup failure performs no claim, ledger read, reservation, start, OOS read, report, Gate, Promotion, or Signal operation.

Operator recovery is explicit and task-scoped: `queued` may claim; `running` without reservation may requeue only after exact absence is proven; `running` with an unstarted reservation releases/requeues the same task; `running` with `started` is `fail_after_start` and never reruns; `completed` requires an exact terminal chain; `failed` is terminal; `blocked` returns durable evidence. No latest scan, polling loop, automatic retry task, or arbitrary queued selection exists.

### 12.6 Final boundary

E1–E7 implementation and synthetic/temp verification do not authorize a production worker invocation or OOS draw. A later production preflight must verify the new criteria pair, supplement, protocol, B4, B5 bundle, task identity, prepared-token path, backup, and progress observer before any claim. A separate final authorization is required for one claim/start/draw. Promotion and Signal remain independent transactions, and downstream decision cards must show market movement versus strategy excess (Alpha) as arithmetic evidence, not causal attribution.

### 12.7 E4.3b successor semantics: formal status precedence and deterministic exits (2026-08-24)

This narrow amendment controls the successor review for the structurally verified but semantically blocked B4 artifact `d3ae7d51690bfef4`, whose manifest SHA is `ad838cc4fa4714867a3a6179f11370b5e6dd842b696fecdacc0a45c5dcdb1b5c` and event-result SHA is `fa097edfbdc3e252b2ffcfe85a01da41d86d7e7e0c233fd0e469125f4f158307`. It does not authorize a new supplement, B4 run, B5 publication, task admission, worker invocation, or OOS operation.

This amendment adds no generation field, semantics registry, user parameter, data source, threshold, Promotion, or Signal behavior.

#### 12.7.1 Current formal status authority

The current FormalPIT adapter contract is authoritative for successor acceptance:

1. An `R`-only `suspend_d` observation with a valid finite daily row is a resumption observation. It returns `is_suspended=false`, preserves `suspend_reason="R"`, and leaves the daily bar usable.
2. If that usable bar has `open == down_limit` under the existing `1e-6` comparison, a sell is rejected as `limit_down`. It is not rejected as `suspended` because the status is not suspended.
3. `S`/`P` with valid daily data and non-empty timing remains non-suspended; `S`/`P` with missing or empty timing remains suspended. `S`/`P` without daily data remains the existing suspension lock/carry boundary.
4. `R`-only without daily data remains a P3 formal status fault, not a suspension carry. Unknown or empty status types remain P3 faults.

The old `suspended` result for the two R-only/usable-bar observations is immutable historical predecessor evidence. It must not be used to reverse the current adapter contract. The combined R-only/usable-bar/open-at-down-limit adapter-plus-fill case is a required focused regression even though its two component contracts already exist independently.

#### 12.7.2 Single deterministic-exit correction

`strategy_core.v3_relative_strength_executor._exit_symbols` remains a set-valued membership helper. Its only consumer must impose the stable key order `sorted(symbols)` with symbol ascending before inserting exits into `pending_exits` and assigning order sequence numbers. The correction is one consumption-boundary ordering change; it does not change the exit multiset, rank rules, holding-period rule, stop rule, quantities, prices, transaction-cost formulas, data source, strategy parameters, or any portfolio eligibility rule. No general sorting framework or semantics registry is introduced.

The reason is identity-bearing order sequence: the current consumer's set iteration determines pending-exit insertion order, order sequence, derived order IDs, fill order, and floating-point cash accumulation order. The correction must make those values independent of process hash seed while preserving the business multiset.

#### 12.7.3 Successor acceptance matrix

The old/new historical comparison is semantic, not a requirement for old and new artifact bytes or sequence-derived records to be identical:

- Compare order intents and fills as business multisets keyed by symbol, side, signal date, execution date, quantity, fill price, and fill quantity. Compare final position symbols and quantities exactly.
- Compare reject identity by symbol, side/direction where present, date, and quantity/order intent identity. Rejection reason is exact except for the contract-authorized R-only/valid-daily case: `suspended` may become `limit_down` when `open == down_limit`.
- Do not require cross-generation exactness for sequence-derived `order_id`, `fill_id`, `signal_id`, or `audit_id`; lineage IDs/hashes, artifact/result IDs, manifest hashes, `frozen_at`, and historical floating-point accumulation tails are not cross-generation exact fields.
- The successor must retain the exact frozen IS window, revision, protocol, formal snapshot, membership, calendar, data, strategy, cost, future-violation, and OOS read-bound identities. `future_violations=0` and `read_audit.oos_read_count=0` remain hard gates.
- Two independent temporary successor processes using the same frozen successor source/lineage and different `PYTHONHASHSEED` values must produce exact equality for order sequence/derived IDs, intents, fills, rejects, final cash/value, and read-audit summary/hash. Any difference outside explicitly run-time metadata is a stop.

The historical artifact's tiny cash/value tail difference is not a waiver for successor nondeterminism. The successor value must equal the stable execution order's current cost arithmetic and must be exact across repeated successor runs. If a future artifact contract requires full artifact-byte equality across different execution dates, `frozen_at` identity must first be separately frozen; this amendment does not silently redefine that field.

#### 12.7.4 Immutable lineage propagation and stop order

Changing the v3 executor source SHA leaves the criteria pair, protocol identity, and strategy revision unchanged. The old supplement `708dbfa1c5601113` and old B4 `d3ae7d51690bfef4` remain immutable predecessors; a successor supplement must bind the new executor SHA and predecessor `708dbfa1c5601113`, and a successor B4 must bind that supplement. No historical sidecar is rewritten.

The authorized design order is:

```text
integrated adapter+fill characterization
  -> multi-exit/hash-seed RED
  -> one-line sorted consumption GREEN
  -> temporary successor supplement publish/verify
  -> production successor supplement publish once / verify once
  -> B4 binding update and temporary verification
  -> production B4 publish once / verify once
  -> successor B4 semantic acceptance
  -> only then consider E4.4 B5 lineage rebuild
```

The integrated adapter-plus-fill test must pass before the multi-exit RED. The multi-exit RED must fail specifically because the current set iteration is unordered. GREEN may touch only the executor's single iteration boundary and its direct tests. A new business multiset difference, cost difference, read-bound difference, or status difference outside 12.7.1 stops the successor chain. B5, new task, worker, OOS, Gate, Promotion, and Signal remain forbidden until the new B4 semantic acceptance passes.

### 12.8 Phase R1: current lineage reconciliation and failed-attempt recovery contract (2026-09-03)

This is a documentation-only amendment. It supersedes stale identity literals that previously described an earlier E4.4d/E4.3b checkpoint only where they were presented as the current runtime target. It preserves those identities as historical evidence and authorizes no code, artifact, database, task, publisher, verifier, worker, CLI, OOS, Promotion, or Signal action.

#### 12.8.1 Current runtime lineage

The current verified runtime chain is:

```text
criteria envelope 94da0dda30af75d663a7d28deb0a15d64a4e068586a1295f3b4f52203a8c4738
protocol 8770c56c5a69ef128442c0f593f9e4b081a6b13c69744b27171b27cc8c8b7bbe
revision 6440ffc03a742f4d4632078481cf3abf171eafb1a24f2bc69bc6f352d1b19ebc
supplement f505099849d497e1 / manifest 503724f0ddc2f0d5cc8bb351a1ecd5fed6c0d5c214484ff319eab91113279231
B4 b34022f7435082d2 / manifest 796dc5d216a5bdf2853499b80948d1e1eccb23d9bbcf322965374e402c905a38 / event f289bf323b17a44a8a330a1878e8345dac712fe105623dd690471227f09c7a09
ledger b8577a9ec56f20fe / manifest 6e936a20e5b4d73f75fdd53c2fd2a268d27fc17fb574d90bcc87ddacb09add98
costs 854c76d2dfd0021f / manifest 82113e141d536e28a27a05ad69cbbe0c428d0babef304781cfd96db93c676dfd
comparisons d606168cc6c5b608 / manifest 03758d7688c0ecfbe1c0be41f37d44a5ffef74d0f1003feecd6edc0b61a8472e
B5 bundle 146b93619fea3cab / manifest f54690a76f3b6a5a874379be876d05153477277d1f3b7ab97a1d03a9e8f6e7de
```

The prior `cb41dd1dc207642b` B4 and `1aed70f1af38a191` supplement literals remain immutable historical evidence. They are no longer the current runtime target. This amendment does not rewrite their historical descriptions.

#### 12.8.2 Separate IS evidence from B6 OOS execution

B4 and B5 event/result artifacts are IS evidence with the frozen event window `2025-06-27..2026-03-19`. The protocol-owned B6 OOS window is `2026-03-20..2026-07-10`. The same-draw executor owns and executes the OOS window once through the concrete engine boundary; B5 IS results, observations, and cost aggregates remain admission evidence only.

The worker second preflight must validate B4's verified IS lineage, artifact identity, and IS range. It must not compare the B4 IS event window to the protocol OOS window. The report builder must retain B4 IS lineage/read evidence and validate the same-draw result identity/window against the protocol OOS window. Its legacy B4-only path remains unchanged. These two erroneous comparisons are one contract-drift fix and must be corrected together before any new draw; a worker-only correction would defer the same failure until after start and incorrectly consume a draw.

#### 12.8.3 Failed target and permitted recovery

The target task `50154863a8e04066c66ef533d8fae9b097ae287f24ce3758ff9e876196d6ffb3` is a failed terminal attempt after claim, with no reservation, OOS consumption, report, or Gate. Its durable row and the healthy preclaim backup are retained as evidence. The recovery rule is not to reset the row, overwrite the live database from the backup, retry automatically, or create an ownerless replacement.

The current schema has `b6_validation_tasks.task_key` unique. The v2 `build_b6_task_key` identity binds the protocol/revision/task contract and B5 bundle ID/manifest, while `StrategyDB.create_or_get_b6_task` reuses the existing key winner. Consequently, a second attempt with the same immutable identity cannot be created through the current public contract. A lawful successor requires an explicit, write-once successor-attempt identity contract and an explicitly owned additive schema/migration/tool boundary. This amendment deliberately does not invent the attempt field, migration, or owner tool.

The preferred recovery decision is therefore: preserve the failed row and use an explicitly authorized successor-attempt contract after the temporary fix and regressions are green. Restoring the preclaim backup is only a possible alternative if a later state owner proves failed-attempt evidence retention, no intervening durable writes would be lost, exact snapshot health, and atomic/recoverable restoration. No silent SQL status reset or backup overwrite is permitted.

#### 12.8.4 A/B/C/D gates

- **A, temporary root-cause gate:** add a temporary file-backed regression with a real IS B4 fixture and a distinct protocol OOS fixture; correct both production comparisons. No production DB, artifact, task, publisher, verifier, worker, CLI, or OOS access.
- **B, temporary full verification gate:** run the direct worker/executor/report/terminal/CLI/B4/B5 admission regressions and fresh compilation. Prove legacy compatibility, one executor, one ledger read, exact recovery, no B5-IS-as-OOS reuse, and no Promotion/Alpha/Signal reachability. No production invocation.
- **C, durable state-owner gate:** the designated StrategyDB/schema owner must explicitly choose and authorize either an additive successor-attempt migration/owner tool that preserves the failed row, or a backup-recovery tool satisfying 12.8.3. It must be explicit-task scoped, write-once, auditable, and followed by raw read-only post-checks. Existing `create_or_get_b6_task` and the production CLI are not such a successor tool.
- **D, new one-shot gate:** after A/B GREEN and C completion, a fresh read-only preflight plus a separate one-draw authorization may permit one explicit claim/start/draw. The post-gate must revalidate the complete task/reservation/ledger/report/Gate chain, preserve zero Promotion/Signal, and prohibit retry.

Phase R1 is review-ready for this written reconciliation only after fresh plan/spec hashes and static readback. It does not make the failed task executable and does not authorize Phase B, successor publication, successor task creation, durable recovery, or a new Phase D attempt.

### 12.9 Phase C0: write-once successor-attempt contract (2026-09-03)

This amendment is the normative design for R1 gate C. It preserves the failed
v2 task and its audit/backup evidence and defines one explicit durable owner
for a successor attempt. It authorizes no implementation, production database
write, artifact write, publisher, verifier, worker, CLI execution, OOS read or
write, backup restore, Promotion, Alpha, Signal, or Phase B/Phase D activity.

#### 12.9.1 Evidence and compatibility decision

The live read-only database is
`D:\\Codex\\TraderLens\\data\\strategy.db`, SHA-256
`520d2933963ee72f74c965d9e9a4235747760ed3168b6711acd695660bfc6b67`, size
233472 bytes, mtime `2026-09-02T04:04:38.116386+00:00`, with
`quick_check=ok` and `foreign_key_check=[]`. The failed predecessor is task
`50154863a8e04066c66ef533d8fae9b097ae287f24ce3758ff9e876196d6ffb3`, v2 key
`2e61682988c3787ced5e1814018b059827b791cfa980e49bc5c2ceba8fea9a25`, bound
to protocol `8770c56c5a69ef128442c0f593f9e4b081a6b13c69744b27171b27cc8c8b7bbe`
and B5 `146b93619fea3cab` /
`f54690a76f3b6a5a874379be876d05153477277d1f3b7ab97a1d03a9e8f6e7de`. Its
live status is `failed` with `invariant_error`; the preserved preclaim backup
has SHA-256
`3f488e2120829684c88c2cbf74ce236d14996b82bae2c14c8d93732815088a1e`, size
233472 bytes, mtime `2026-09-02T04:04:24.123259+00:00`, and contains the same
task as `queued`. Both raw URI `mode=ro` snapshots are healthy. The protected
OOS/report/Gate/Promotion tables are zero in both snapshots.

The v2 `task_key` unique constraint and
`StrategyDB.create_or_get_b6_task` exact winner behavior are intentional. A
current v2 admission request may return the failed winner, but cannot create
an attempt with the same identity. A successor is therefore a new, explicitly
owned v3 task identity. The existing v1/v2 task model, v1/v2 rows,
`create_or_get_b6_task`, Task7 admission, and the explicit worker CLI remain
compatible; Task7 does not implicitly manufacture a successor.

#### 12.9.2 Exact v3 identity

`contracts/b6_task.py` shall add `B6_TASK_CONTRACT_V3 = "v3"` and
`build_b6_successor_task_key`. The v1 and v2 canonical objects and their
serialization are unchanged. The v3 canonical object is exactly the following
ten-field object, with values copied from the failed predecessor except for
the fixed contract/attempt fields:

```json
{
  "attempt_number": 1,
  "b5_bundle_id": "<predecessor.b5_bundle_id>",
  "b5_bundle_manifest_sha256": "<predecessor.b5_bundle_manifest_sha256>",
  "predecessor_task_id": "<predecessor.task_id>",
  "predecessor_task_key": "<predecessor.task_key>",
  "protocol_profile": "b6_coverage_bound",
  "protocol_snapshot_id": "<predecessor.protocol_snapshot_id>",
  "strategy_revision_id": "<predecessor.strategy_revision_id>",
  "task_contract_version": "v3",
  "task_type": "b6_validation"
}
```

Use sorted-key compact JSON, `ensure_ascii=False`, UTF-8, and lowercase
SHA-256. `build_b6_task_id` remains the existing hash of
`{"kind":"b6_validation_task","payload":{"task_key":...}}`. The
`B6ValidationTask` model gains nullable `predecessor_task_id`,
`predecessor_task_key`, and `successor_attempt_number` fields. v1/v2 require
all three to be null. v3 requires all three, a path-free predecessor ID/key,
`successor_attempt_number == 1`, and the complete B5 pair. Extra fields,
half-paired values, a non-one attempt, or a v3 key/task-ID mismatch are
rejected. The one-value ordinal is a direct-successor invariant, not a
general generation field or version registry.

#### 12.9.3 Additive durable schema

Create `backend/db/migrations/migration_005_add_b6_successor_attempt.py`
with `migrate_add_b6_successor_attempt(conn)`. Register it after migration
004 in `StrategyDB._run_migrations`. On fresh and upgraded databases, guarded
`ALTER TABLE` operations add nullable `predecessor_task_id` with a
self-reference to `b6_validation_tasks(task_id)`, nullable
`predecessor_task_key`, and nullable `successor_attempt_number`. Then create:

```sql
CREATE UNIQUE INDEX IF NOT EXISTS uq_b6_direct_successor_predecessor
ON b6_validation_tasks(predecessor_task_id)
WHERE predecessor_task_id IS NOT NULL;
```

The migration is `BEGIN IMMEDIATE`/commit-or-rollback, checks
`PRAGMA table_info` before each column addition, and never drops, renames, or
rebuilds a table. All historical v1/v2 rows remain unchanged with null
successor fields; the existing task-key unique index, triggers, primary key,
and foreign keys remain. `PRAGMA foreign_key_check` must be empty after fresh,
upgrade, reopen, rollback, and concurrent-writer tests.

#### 12.9.4 Single StrategyDB owner and preconditions

`backend/db/strategy.py` shall add
`StrategyDB.create_or_get_b6_successor_attempt(predecessor_task_id)` and no
other public successor-creation path. It accepts only the explicit
predecessor task ID and derives protocol, revision, B5 identity, predecessor
key, and attempt number itself. It does not accept a path, artifact, bundle,
manifest, key, or caller-selected attempt.

Inside one `BEGIN IMMEDIATE` transaction it shall:

1. Load the exact predecessor and validate its persisted payload/columns,
   canonical v2 key/ID, v2 contract, `claimed_at`, protocol profile/revision,
   and complete B5 pair. Missing, malformed, non-v2, or non-failed rows return
   typed stable codes `b6_successor_predecessor_missing`,
   `b6_successor_predecessor_identity_invalid`,
   `b6_successor_predecessor_not_v2`, or
   `b6_successor_predecessor_not_failed`.
2. Derive the expected v3 row/key. First query the direct-successor unique
   index. An existing successor is reusable only when every v3 immutable
   column, payload field, predecessor binding, canonical key, canonical ID,
   and `created_at` agrees; it returns `(winner, False)` in any legal lifecycle
   state. A conflict returns `b6_successor_existing_conflict` and never
   rewrites either row.
3. When no successor exists, prove the predecessor is pre-reservation and
   pre-consumption using read-only owner queries, not
   `OOSBudgetLedger.get_ledger_state`: the owner state is absent or exactly
   zero/first/available/no-active-reservation; no owner or predecessor-key
   reservation exists; and no owner-scoped OOS ledger exists. Any evidence
   returns `b6_successor_oos_evidence_present`.
4. Query report rows bound to the exact protocol/revision and parse the
   canonical payload. A report whose `task_id` or `task_key` binds the
   predecessor, or a Gate bound to such a report, returns
   `b6_successor_report_or_gate_evidence_present`. Invalid evidence in the
   matching scope fails loudly. No report or Gate row may be ignored to permit
   creation.
5. Insert one ordinary queued v3 row with null blocking, claim, and
   completion fields. Re-read with `_load_b6_task`, compare all immutable
   fields and `created_at`, commit, and return `(winner, True)`. A concurrent
   caller waits on the transaction, reads the one exact winner, and returns it;
   a different unique collision rolls back with
   `b6_successor_existing_conflict`.

The owner performs no artifact discovery, B4/B5 verification or publication,
supplement verification, worker call, ledger materialization, reservation,
report, Gate, Promotion, Alpha, or Signal action. `_load_b6_task` compares
the new columns when present while default-null v1/v2 payloads remain
readable. `create_or_get_b6_task` stays v2-only.

#### 12.9.5 Explicit owner CLI and worker boundary

Create `scripts/create_b6_successor_attempt.py` with
`_parse_predecessor_task_id`, `_emit_progress`, `_run_successor`, and `main`.
It accepts exactly one path-free predecessor ID; `latest`, `queued`, extra
arguments, identity/path/OOS/backup overrides, and worker/executor flags are
invalid. It calls the existing server-owned
`backup_strategy_db_once(predecessor_task_id, repo_root=...)` before opening
`StrategyDB` or invoking the owner write. It emits canonical stdout schema
`b6_successor_attempt.cli.v1` containing predecessor/successor identity,
v3/lifecycle status, B5 pair, backup identity, false OOS authorization and
consumption, and null Promotion. It never imports the worker, OOS ledger,
verifier, or executor.

Its stderr progress schema is
`b6_successor_attempt_progress.v1` with exactly
`schema_version`, `event_seq`, `stage`, `predecessor_task_id`,
`successor_task_id`, and `status`; stages are `preflight`, `backup`,
`owner_write`, `terminal`, `blocked`, and `failed`. Backup/precondition
failure maps to exit 20 with no successor write; unexpected owner/database
failure maps to exit 70 after rollback; exact creation or reuse maps to exit
0. Invalid invocation maps to exit 64.

`backend/services/b6_validation_worker.py` shall add only a v3 identity branch
to `_second_preflight`: validate the v3 key/ID and exact failed predecessor
binding before the existing B4/B5/protocol checks. The v2 branch behavior and
the existing `scripts/run_b6_validation_task.py` explicit-ID interface remain
unchanged. v1 remains ineligible. There is no v3-to-v2 fallback, latest scan,
automatic retry, or altered same-draw identity; the existing task ID/key binds
the terminal chain.

#### 12.9.6 Required tests and acceptance order

Create `tests/test_b6_successor_attempt.py` with temporary file-backed
fixtures built through public `StrategyDB` APIs. Add these exact tests:

- `TestB6SuccessorTaskContract.test_v3_requires_predecessor_binding_and_attempt_one`;
- `TestB6SuccessorTaskContract.test_v3_key_is_distinct_and_v1_v2_keys_are_unchanged`;
- `TestB6SuccessorSchema.test_fresh_and_upgrade_migrations_are_additive_idempotent_and_fk_clean`;
- `TestB6SuccessorOwner.test_failed_pre_reservation_v2_creates_one_queued_v3_without_oos`;
- `TestB6SuccessorOwner.test_exact_retry_reuses_successor_in_any_legal_lifecycle_state`;
- `TestB6SuccessorOwner.test_two_file_backed_connections_return_one_successor_winner`;
- `TestB6SuccessorOwner.test_nonfailed_or_v1_predecessor_is_rejected_without_write`;
- `TestB6SuccessorOwner.test_oos_report_or_gate_evidence_blocks_successor_without_write`;
- `TestB6SuccessorOwner.test_insert_failure_rolls_back_and_preserves_failed_predecessor`;
- `TestB6SuccessorWorker.test_v3_successor_reaches_existing_second_preflight_boundary`;
- `TestB6SuccessorCLI.test_cli_requires_one_explicit_predecessor_and_no_overrides`;
- `TestB6SuccessorCLI.test_backup_completes_before_owner_write_and_result_is_canonical`;
- `TestB6SuccessorCLI.test_blocked_backup_or_precondition_has_no_db_write`.

The temporary fixture may use synthetic B4/B5/supplement discovery only at the
existing worker boundary; it may not copy or open production `strategy.db` or
production artifact directories. Durable assertions use an independent
SQLite connection. Public APIs create the predecessor and any negative
evidence; SQL is limited to schema inspection and independent verification.

Run the RED nodes separately before each implementation slice:

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_b6_successor_attempt.TestB6SuccessorTaskContract.test_v3_requires_predecessor_binding_and_attempt_one -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_b6_successor_attempt.TestB6SuccessorTaskContract.test_v3_key_is_distinct_and_v1_v2_keys_are_unchanged -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_b6_successor_attempt.TestB6SuccessorSchema.test_fresh_and_upgrade_migrations_are_additive_idempotent_and_fk_clean -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_b6_successor_attempt.TestB6SuccessorOwner.test_failed_pre_reservation_v2_creates_one_queued_v3_without_oos -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_b6_successor_attempt.TestB6SuccessorOwner.test_two_file_backed_connections_return_one_successor_winner -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_b6_successor_attempt.TestB6SuccessorCLI.test_backup_completes_before_owner_write_and_result_is_canonical -v
```

The RED reason must be missing v3 contract/migration/owner behavior, never a
production lineage or OOS failure. Stop on another reason, a second
independent defect, a schema rewrite, an old-row mutation, or any production
access.

After GREEN, update only the Task7 characterization in
`tests/test_run_v3_task4_once.py`: the current exact v2 identity reuses the
failed winner without creating a row; the unrelated old queued row is never
selected; the progressed-current test uses a fresh temporary queued v2
fixture; and Task7 never auto-creates a successor. Add
`TestRunB6ValidationTask.test_explicit_v3_successor_id_is_forwarded_once` to
`tests/test_run_b6_validation_task.py`; keep the old worker CLI explicit-ID
and no-override contracts.

Run each final check separately:

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_b6_successor_attempt -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_b6_validation_worker -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_b6_task_atomic_claim -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_b6_runtime_persistence_kernel -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_b6_task_state_consistency -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_b6_terminal_transaction -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_reservation_task_binding -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_run_v3_task4_once -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_run_b6_validation_task -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m pytest tests/test_v3_execution_semantics.py -q
D:\Codex\TraderLens\.venv\Scripts\python.exe -m py_compile contracts/b6_task.py backend/db/migrations/migration_005_add_b6_successor_attempt.py backend/db/strategy.py backend/services/b6_validation_worker.py scripts/create_b6_successor_attempt.py tests/test_b6_successor_attempt.py tests/test_b6_validation_worker.py tests/test_run_v3_task4_once.py tests/test_run_b6_validation_task.py
```

Final evidence must include actual tests/pass/fail/error/warning counts,
fresh compilation, old-row equality, exactly one successor and direct
predecessor binding, migration/FK health, zero new OOS/report/Gate evidence at
creation, exact retry/concurrency convergence, v3 worker compatibility, no
fallback/latest selection, and no Promotion/Alpha/Signal reachability. A
fresh raw SQLite URI `mode=ro` post-check records production and retained
backup absolute paths, SHA-256, size, mtime, `quick_check`,
`foreign_key_check`, exact task rows, protected counts, and a no-B6-process
snapshot. This post-check does not create or execute the successor.

Phase C0 is review-ready only after these temporary checks are fresh GREEN and
the production read-only snapshot is unchanged. Successor creation through the
new owner and execution through the existing worker are separate later
authorizations; Phase B and the one-shot OOS attempt remain blocked.

### 12.10 C0.1: registered migration-005 owner design (docs-only, 2026-09-03)

The C2 stop gate found that the repository has no independent production
migration owner. `StrategyDB.__init__` calls `_run_migrations()` and therefore
automatically runs every registered migration; it is not the narrow owner for
this gate. The retained E4 incident explicitly classifies opening production
`StrategyDB` and auto-applying a migration as not being an authorized
production migration checkpoint. This amendment defines the missing owner but
does not implement it, open the production database, or authorize C2.

#### 12.10.1 Owner module and fixed invocation

The only production owner for migration 005 shall be
`scripts/run_b6_successor_migration_once.py`. The only test module added for
it shall be `tests/test_run_b6_successor_migration_once.py`; its fixtures are
temporary file-backed databases and temporary backup roots only. No existing
production code, migration, successor owner, worker, executor, publisher,
verifier, artifact, task, or runbook is changed as part of this owner slice.

The owner shall expose the following temporary-test seam and no broader public
successor or migration API:

```python
run_once(
    *,
    repo_root: Path,
    db_path: Path,
    backup_root: Path,
    connection_factory: Callable[[str], sqlite3.Connection] = sqlite3.connect,
    migration: Callable[[sqlite3.Connection], None] = migrate_add_b6_successor_attempt,
    stdout: TextIO | None = None,
    progress_stream: TextIO | None = None,
) -> tuple[int, dict[str, Any]]
```

The production `main` accepts no arguments. Any argument is invalid and
returns exit 64 before opening a file or connection. It derives the repository
root from the module path and uses only
`repo_root/data/strategy.db` and
`repo_root/data/strategy_backups/b6_schema_migration`. No database path,
backup path, migration selector, dry-run, connection, task, or identity
override is accepted. The exact C2 command is:

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe scripts/run_b6_successor_migration_once.py
```

#### 12.10.2 Raw read-only preflight

Before a writable connection or backup is opened, `run_once` shall use the
fixed database through a raw SQLite URI with `mode=ro`. It must fail closed
unless `quick_check` is exactly `ok`, `foreign_key_check` is empty, all
runtime/B5 schema elements from migrations 001–003 are present, migration
004's nonunique
`idx_protocol_b6_profile_per_revision` exists, and the former partial unique
index is absent. It must also inspect the schema, indexes, foreign keys,
triggers, every `b6_validation_tasks` row, every pre-existing column, raw
`payload_json` bytes, task states, and the failed predecessor identity.

The preflight must prove that all three migration-005 columns
`predecessor_task_id`, `predecessor_task_key`, and
`successor_attempt_number`, and the partial unique index
`uq_b6_direct_successor_predecessor`, are absent. A partial or malformed 005
shape returns stable reason `b6_schema_migration_partial_or_invalid` and exit
20 without self-repair. A complete exact 005 shape is a stable
`already_applied` result with exit 0: it performs no backup, opens no writable
connection, and calls no migration function. Any migration registry is read
only; no registry table is invented, and the current absent registry is
reported as `migration_registry="absent"`.

The preflight counts the seven repository protected tables defined by the
existing backup-owner count set, and also strategy-promotion and human-
confirmation tables when present. All protected evidence counts must be zero;
no v3/successor row may exist. No task is selected through `latest`, `queued`,
database order, `ORDER BY`, `LIMIT 1`, or a scan.

#### 12.10.3 Separate server-owned migration backup

For a valid not-yet-applied pre-state, the owner shall create one
server-owned consistency backup after preflight and before any writable
database connection. The source is a raw read-only connection and the copy
uses SQLite `Connection.backup` into a sibling staging file, followed by
flush/fsync and atomic publication under:

```text
data/strategy_backups/b6_schema_migration/
  migration_005.<source_db_sha256>.sqlite3
  migration_005.<source_db_sha256>.sqlite3.manifest.json
  migration_005.<source_db_sha256>.sqlite3.manifest.json.sha256
```

This is a new owner-specific directory and must never reuse, overwrite, or
delete `data/strategy_backups/b6_preclaim`. The manifest schema is
`b6_schema_migration_backup.v1` and binds migration ID, source absolute path,
source SHA/size/mtime, source schema/row snapshot hash, backup SHA/size,
backup health snapshot, creation time, and owner source SHA. The sidecar binds
the manifest SHA to the manifest filename. A complete exact backup for the
same unchanged source may be validated and reused without recopying; partial,
conflicting, unhealthy, or source-drifted backup files return stable
`b6_schema_migration_backup_conflict` or
`b6_schema_migration_backup_failed` with exit 20. The backup is retained on
all later failures.

The backup implementation is private to the new owner and must not call
`backup_strategy_db_once`, `StrategyDB`, `_run_migrations`, any other migration,
task/successor API, worker, OOS ledger, verifier, publisher, artifact writer,
Promotion, Alpha, or Signal.

#### 12.10.4 One direct migration call

After backup success, the owner shall open exactly one writable
`sqlite3.Connection` to the fixed database, enable foreign keys, and call
`migrate_add_b6_successor_attempt(connection)` exactly once. It shall not
instantiate `StrategyDB`, execute inline migration SQL, import or call
migrations 001–004, create a successor, or touch OOS/artifact state. The
registered function owns its `BEGIN IMMEDIATE`/commit-or-rollback boundary;
the owner rolls back any still-active transaction on an unexpected exception
and closes the connection.

The stderr progress schema is
`b6_successor_migration_progress.v1`. Every JSONL event has exactly
`schema_version`, `event_seq`, `stage`, `migration_id`, `status`,
`source_db_sha256`, and `backup_id`. Stages are `preflight`, `backup`,
`migration`, `terminal`, `blocked`, and `failed`; the sequence starts at one
and is strictly increasing. Events contain no task payload, OOS data, secret,
or user configuration.

The canonical `migration_id` is exactly
`migration_005_add_b6_successor_attempt` in every result and progress event.

The sole stdout object uses sorted-key compact UTF-8 JSON with
`allow_nan=False` and schema `b6_successor_migration.cli.v1`. Its exact fields
are `schema_version`, `migration_id`, `status`, `db_path`,
`source_db_sha256`, `source_size_bytes`, `source_mtime_ns`, `backup_id`,
`backup_path`, `backup_manifest_path`, `backup_manifest_sidecar_path`,
`backup_db_sha256`, `backup_manifest_sha256`, `post_schema_sha256`,
`post_task_row_snapshot_sha256`, `post_health`, `post_protected_counts`,
`migration_registry`, `reason`, and `detail`.

Exit mapping is fixed: 0 for `migrated` or verified `already_applied`, 20 for
preflight/shape/backup blocks, 64 for any command argument, and 70 for an
unexpected migration/database failure after backup. A non-zero result never
retries, restores, deletes, overwrites, or edits the backup.

#### 12.10.5 Post-migration read-only proof

After the writable connection closes, a new raw `mode=ro` connection shall
prove `quick_check=ok`, empty `foreign_key_check`, unchanged pre-existing
tables/triggers/primary key/foreign keys/indexes, and the exact nullable 005
definitions: `predecessor_task_id TEXT` with a self-reference to
`b6_validation_tasks(task_id)`, `predecessor_task_key TEXT`, and
`successor_attempt_number INTEGER`. It shall prove the exact unique partial
index `uq_b6_direct_successor_predecessor` on
`b6_validation_tasks(predecessor_task_id)` with the non-null predicate.

Every pre-existing task row and raw `payload_json` byte must equal the
preflight snapshot, every new column on those rows must be null, and all task
states must be unchanged. There must be no v3/successor row, OOS
state/reservation/ledger, report/Gate, Promotion, Alpha, or Signal evidence;
all protected counts remain zero. The migration backup, manifest, sidecar,
source binding, hash, size, mtime, and health must remain exact. A registry is
only reported if it already exists. A final read-only process snapshot must
show no B6 worker or migration-owner process.

#### 12.10.6 C1c tests and C2 stop gate

The temporary test module shall add these exact tests:

- `test_main_rejects_arguments_without_opening_database`;
- `test_preflight_requires_migrations_001_to_004_and_rejects_partial_005`;
- `test_already_applied_is_stable_without_backup_or_migration_call`;
- `test_backup_precedes_the_only_writable_connection`;
- `test_registered_migration_is_called_exactly_once`;
- `test_post_audit_preserves_rows_and_adds_exact_nullable_schema`;
- `test_migration_failure_is_failed_closed_and_preserves_backup`;
- `test_progress_and_result_are_canonical_for_migrated_and_blocked`.

Each RED node is run separately before implementation and may fail only for
the missing owner module/symbol; a production path, OOS error, or unrelated
fixture failure is a hard stop. Each GREEN node and the full module are then
run separately, followed by fresh compilation of the owner. The tests use
independent SQLite readers for durable assertions and a spy around the real
registered migration function to prove call count one; they never open
production `strategy.db`.

Only after fresh C1c GREEN and compile may the exact zero-argument C2 command
run once. The command is preceded by the raw RO preflight and one
schema-migration backup, and followed by the raw RO post-audit, exact old-row
equality, migration call count one, backup identity, protected counts, and
no-process snapshot. C2 success means only
`C2 production migration verified / eligible for C3 preflight`; it does not
authorize C3 successor creation or Phase D. A failure is terminal for C2 and
leaves the backup for review. No retry, restore, cleanup, successor, worker,
OOS, publisher, verifier, Promotion, Alpha, Signal, or Git operation is
permitted.

### 12.11 Phase D Attempt 2: independent read-only preflight (2026-09-07)

This section records a new authorization; it does not rewrite Attempt 1.
Attempt 1 called the official availability verifier once with caller-supplied
scope, coverage, and evidence roots that were wrong for this repository. It
returned `invalid` because the scope manifest or sidecar was missing before
complete availability binding was evaluated. That authorization is consumed
and is not retryable. It produced no publisher, worker, CLI task, OOS,
artifact, database, Promotion, Alpha, Signal, Git, delete, or cleanup write.

Attempt 2 is limited to one read-only Phase D preflight. The official
availability verifier may run at most once, and its official CLI must use the
server-owned defaults for scope, coverage, and evidence. Passing any of
`--scope-dir`, `--coverage-dir`, or `--evidence-dir` is forbidden. The exact
successor and formal snapshot inputs are:

- successor task:
  `62a25009b5097c76daf2798663d7f84643bdc7af2d49d366114bba47953099de`
- failed predecessor:
  `50154863a8e04066c66ef533d8fae9b097ae287f24ce3758ff9e876196d6ffb3`
- successor directory:
  `D:\Codex\TraderLens\data\pit\v3_availability_bounded_qualification_successors\12f1b9aac73dfcd4`
- formal snapshot directory:
  `D:\Codex\TraderLens\data\pit\v3_formal_data_snapshot_manifests\v3ds_d73256081de82e8a`
- successor manifest SHA-256:
  `082a45061556505d4e3b2613fb1a87ed878481d0d728f73c80a9564c4ebd9f91`

The only permitted official verifier invocation is:

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe scripts/verify_v3_availability_bounded_qualification_successor.py --successor-dir D:\Codex\TraderLens\data\pit\v3_availability_bounded_qualification_successors\12f1b9aac73dfcd4 --formal-snapshot-dir D:\Codex\TraderLens\data\pit\v3_formal_data_snapshot_manifests\v3ds_d73256081de82e8a
```

Because the CLI parser defaults are part of the contract, the omitted defaults
must resolve to:

- scope: `D:\Codex\TraderLens\data\pit\historical_scope_freezes\acbc49159d989a46`
- coverage: `D:\Codex\TraderLens\data\pit\v3_historical_coverage_packages\1e79d26460c0c109`
- evidence: `D:\Codex\TraderLens\data\pit\v3_historical_suspension_evidence\4871f6ba56b40e93`

The expected verifier stdout is JSON containing `status=valid`,
`successor_id=12f1b9aac73dfcd4`, and
`manifest_sha256=082a45061556505d4e3b2613fb1a87ed878481d0d728f73c80a9564c4ebd9f91`.
An exception, non-zero exit, malformed JSON, any non-`valid` status, or any
identity/hash mismatch is a terminal Attempt 2 failure. There is no retry,
fallback, alternate path, publisher, worker/CLI production execution, OOS,
Promotion, Alpha, or Signal action after failure.

The verifier result is not sufficient by itself. The same read-only preflight
must then check migration-005 owner/marker identity, the four relevant task
rows, successor queued/unclaimed state, failed-predecessor immutability, raw
SQLite health, protected reservation/state/ledger/report/Gate counts of zero,
artifact sidecar/manifest bindings, progress/backup state, scratch state, and
the absence of B6 worker/CLI processes. No successor backup is created by this
attempt; an absent or already complete reusable backup is acceptable. Only
when the verifier and every fresh dependency/database/protected/backup/process
check passes may the outcome be recorded as `PHASE D PRECHECK READY`. That
outcome does not authorize one-draw execution; one-draw remains a separate
later authorization.

### 12.12 Phase D Attempt 3: module-entry read-only preflight (2026-09-07)

Attempt 2 is historical and consumed. Its direct-path command reached the
V3 verifier file but failed at the top-level `from scripts...` import with
`ModuleNotFoundError: scripts`; verifier business logic was not entered. All
artifact, database, task, protected-state, and process prechecks preceding
that call had passed. Attempt 2 was not retried and caused no publisher,
worker/CLI task, OOS, artifact, database, Promotion, Alpha, Signal, Git,
delete, or cleanup action. The direct-path command in the Attempt 2 record is
historical evidence only and is not a reusable Attempt 3 command.

The V3 verifier CLI entry contract is now minimally closed without changing
`verify_successor`, its defaults, or its business bindings: the module has a
`main(argv=None) -> int` entry, emits one JSON object, returns 0 only for
`status=valid`, returns 1 for an invalid result, and exits through
`SystemExit(main())`. Temporary no-production CLI tests cover module
`--help` loading and invalid-result JSON/exit semantics; the target CLI has
freshly compiled successfully. These facts authorize preparation only, not a
verifier run.

Attempt 3 is a new, independent authorization for one read-only Phase D
preflight. It must start from the repository root and use the module entry
below. The official availability verifier may be called at most once. Passing
any of `--scope-dir`, `--coverage-dir`, or `--evidence-dir` is forbidden; the
server-owned defaults must remain in force.

```powershell
Set-Location -LiteralPath D:\Codex\TraderLens
& D:\Codex\TraderLens\.venv\Scripts\python.exe -m scripts.verify_v3_availability_bounded_qualification_successor --successor-dir D:\Codex\TraderLens\data\pit\v3_availability_bounded_qualification_successors\12f1b9aac73dfcd4 --formal-snapshot-dir D:\Codex\TraderLens\data\pit\v3_formal_data_snapshot_manifests\v3ds_d73256081de82e8a
```

The exact successor task remains
`62a25009b5097c76daf2798663d7f84643bdc7af2d49d366114bba47953099de`, the
failed predecessor remains
`50154863a8e04066c66ef533d8fae9b097ae287f24ce3758ff9e876196d6ffb3`, and the
expected successor manifest SHA-256 remains
`082a45061556505d4e3b2613fb1a87ed878481d0d728f73c80a9564c4ebd9f91`.
The expected result is process exit 0 and one JSON object containing
`status=valid`, `successor_id=12f1b9aac73dfcd4`, and that exact manifest hash.
Any exception, non-zero exit, malformed or extra stdout, non-`valid` status,
or identity/hash mismatch is terminal for Attempt 3 and must not be retried.

After the single verifier call, perform the fresh read-only artifact,
sidecar/identity, migration-005, task, raw SQLite, protected reservation/
state/ledger/report/Gate, backup/progress, scratch, and process checks required
by Phase D. Do not publish, create a backup, run worker/CLI task execution,
run OOS, or invoke Promotion, Alpha, or Signal. Only if every dependency and
fresh state check passes may the outcome be recorded as
`PHASE D PRECHECK READY`; that outcome does not authorize one-draw, which
remains a separate later authorization.
