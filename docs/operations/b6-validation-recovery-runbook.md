# B6 Validation Recovery Runbook

This runbook is for one explicitly supplied `task_id` only. An operator must
complete the read-only production preflight and receive the separate execution
authorization before invoking the worker. Do not select `latest` or `queued`,
poll for work, create a replacement task, retry automatically, or provide a
user-controlled backup path.

## Pre-claim safety

The CLI performs one server-owned consistency backup before claim. The backup
is written beneath
`data/strategy_backups/b6_preclaim/<task_id>.<source_db_sha256>.sqlite3`
with its manifest and manifest sidecar. A byte- and snapshot-equivalent
existing backup is reused. A missing, partial, conflicting, or failed backup
is a hard block: the task remains `queued` and no claim, ledger read,
reservation, start, consume, report, Gate, Promotion, or Signal operation may
occur.

## Durable state matrix

| Observed state | Required operator interpretation and action |
| --- | --- |
| `queued` | The task has not been claimed. After the pre-claim backup succeeds, the explicit task may be claimed once. |
| `running` | Inspect the durable reservation before acting. If exact absence of a reservation is proven, the same task may be requeued; do not create a replacement task. |
| `reserved` | This is an unstarted reservation. `release` the reservation and requeue the same task atomically; no draw is consumed and execution must not start. |
| `started` | Execution may have had an external effect. Run `fail_after_start` once, consume the draw exactly once, and mark the task `failed`; never rerun the executor. |
| `completed` | The task is terminal only when the exact started-to-terminal ledger, report, and binding chain is present. Do not rerun or consume again. |
| `failed` | The task is terminal. Preserve the durable evidence and do not retry automatically or create another task. |

The `reserved` and `started` rows above refer to the OOS reservation state
associated with a `running` task. A `running` task without a reservation and a
`running` task with an unstarted `reserved` reservation are different recovery
cases. Any ambiguity about reservation ownership is a hard stop.

## Invocation and progress

Only an exact invocation containing exactly one explicit task_id is valid. The
argument is an explicit `task_id`; no other argument is accepted. The final
canonical result is the only stdout object. Progress is JSONL on stderr using
`b6_validation_progress.v1`; every event has a strictly increasing
`event_seq`, the exact task ID, a permitted task status, and no OOS payload,
source rows, secrets, or operator configuration.

Keep the final result and all durable evidence with the task record. This
runbook does not authorize production OOS execution, Promotion, Alpha, Signal,
or any change to historical artifacts or lineage.

## Successor-attempt owner and recovery

The failed v2 predecessor is preserved as terminal evidence. The only creator
of a successor is the server-owned owner CLI, invoked with exactly one explicit
failed predecessor ID:

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe scripts/create_b6_successor_attempt.py <failed_v2_predecessor_task_id>
```

The owner performs the consistency backup before opening the database, then
creates or exactly reuses one immutable v3 successor. A backup, precondition,
or identity failure is a hard block; it does not reset the predecessor or
create a task. Do not use `latest`, `queued`, path or identity overrides, or a
user-supplied backup path. Do not retry automatically.

The successor remains `queued` with OOS authorization and consumption both
false. After the required production C2 migration and C3 successor-owner
checkpoint, and only after the separate Gate B review and one-draw
authorization, the existing worker may be invoked with the exact successor ID:

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe scripts/run_b6_validation_task.py <successor_task_id>
```

The worker must not scan for a task, fall back to v2, create another
successor, or rerun a failed predecessor. Recovery remains task-scoped: a
started attempt is handled by `fail_after_start` and is never rerun; a failed
attempt remains terminal. This section does not authorize production
publisher, verifier, worker, OOS, report, Gate, Promotion, Alpha, or Signal
execution.

## Phase D Attempt 2 read-only preflight (2026-09-07)

Attempt 1 is historical and consumed: the official availability verifier was
called once with incorrect caller overrides for scope, coverage, and evidence,
then returned `invalid` because the scope manifest or sidecar was missing
before complete availability binding. Attempt 1 was not retried and caused no
publisher, worker, CLI task, OOS, artifact, database, Promotion, Alpha,
Signal, Git, delete, or cleanup write.

Attempt 2 is a new authorization for one read-only Phase D preflight only. The
official availability verifier may be called at most once. Run it with the
server-owned defaults for scope, coverage, and evidence; do not pass
`--scope-dir`, `--coverage-dir`, or `--evidence-dir`. Use the exact successor
and formal snapshot paths below, not a latest/queued scan:

- successor task:
  `62a25009b5097c76daf2798663d7f84643bdc7af2d49d366114bba47953099de`
- failed predecessor:
  `50154863a8e04066c66ef533d8fae9b097ae287f24ce3758ff9e876196d6ffb3`
- successor directory:
  `D:\Codex\TraderLens\data\pit\v3_availability_bounded_qualification_successors\12f1b9aac73dfcd4`
- formal snapshot directory:
  `D:\Codex\TraderLens\data\pit\v3_formal_data_snapshot_manifests\v3ds_d73256081de82e8a`
- expected successor manifest SHA-256:
  `082a45061556505d4e3b2613fb1a87ed878481d0d728f73c80a9564c4ebd9f91`

The only permitted verifier command is:

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe scripts/verify_v3_availability_bounded_qualification_successor.py --successor-dir D:\Codex\TraderLens\data\pit\v3_availability_bounded_qualification_successors\12f1b9aac73dfcd4 --formal-snapshot-dir D:\Codex\TraderLens\data\pit\v3_formal_data_snapshot_manifests\v3ds_d73256081de82e8a
```

Its omitted defaults must resolve to:

- scope: `D:\Codex\TraderLens\data\pit\historical_scope_freezes\acbc49159d989a46`
- coverage: `D:\Codex\TraderLens\data\pit\v3_historical_coverage_packages\1e79d26460c0c109`
- evidence: `D:\Codex\TraderLens\data\pit\v3_historical_suspension_evidence\4871f6ba56b40e93`

Expected stdout is JSON containing `status=valid`,
`successor_id=12f1b9aac73dfcd4`, and
`manifest_sha256=082a45061556505d4e3b2613fb1a87ed878481d0d728f73c80a9564c4ebd9f91`.
Any exception, non-zero exit, malformed output, non-`valid` status, or
identity/hash mismatch is terminal: stop, do not retry, and do not invoke
publisher, worker/CLI production execution, OOS, Promotion, Alpha, or Signal.

After that single verifier call, perform fresh read-only checks for
migration-005 owner/marker identity, the four relevant task rows, successor
queued/unclaimed state, failed-predecessor immutability, artifact
sidecar/manifest bindings, raw SQLite health, protected reservation/state/
ledger/report/Gate counts of zero, progress/backup state, scratch state, and
absence of B6 worker/CLI processes. Do not create a successor backup; an
absent or complete reusable backup is acceptable. Record
`PHASE D PRECHECK READY` only if every artifact, database, protected, backup,
and process check passes. This does not authorize one-draw execution; that
step requires a separate later authorization.

## Phase D Attempt 3 module-entry read-only preflight (2026-09-07)

Attempt 2 is historical and consumed. Its direct-path command reached the V3
verifier file but failed at the top-level `from scripts...` import with
`ModuleNotFoundError: scripts`; verifier business logic was not entered. All
artifact, database, task, protected-state, and process prechecks preceding
that call had passed. Attempt 2 was not retried and caused no publisher,
worker/CLI task, OOS, artifact, database, Promotion, Alpha, Signal, Git,
delete, or cleanup action. The direct-path command in the Attempt 2 record is
historical evidence only and is not a reusable Attempt 3 command.

The V3 verifier CLI now has the minimal stable entry contract: a
`main(argv=None) -> int` entry, one JSON stdout object, exit 0 only for
`status=valid`, exit 1 for an invalid result, and `SystemExit(main())`.
Temporary no-production tests cover module `--help` loading and invalid-result
JSON/exit semantics; the target CLI has freshly compiled successfully. This
prepares, but does not execute, Attempt 3.

Attempt 3 is a new authorization for one read-only Phase D preflight. Start
from the repository root and use the module entry below. Do not pass
`--scope-dir`, `--coverage-dir`, or `--evidence-dir`; use the server-owned
defaults. The official availability verifier may be called at most once.

```powershell
Set-Location -LiteralPath D:\Codex\TraderLens
& D:\Codex\TraderLens\.venv\Scripts\python.exe -m scripts.verify_v3_availability_bounded_qualification_successor --successor-dir D:\Codex\TraderLens\data\pit\v3_availability_bounded_qualification_successors\12f1b9aac73dfcd4 --formal-snapshot-dir D:\Codex\TraderLens\data\pit\v3_formal_data_snapshot_manifests\v3ds_d73256081de82e8a
```

The exact successor task is
`62a25009b5097c76daf2798663d7f84643bdc7af2d49d366114bba47953099de`; the
failed predecessor is
`50154863a8e04066c66ef533d8fae9b097ae287f24ce3758ff9e876196d6ffb3`; and the
expected successor manifest SHA-256 is
`082a45061556505d4e3b2613fb1a87ed878481d0d728f73c80a9564c4ebd9f91`.
Require process exit 0 and one JSON object containing `status=valid`,
`successor_id=12f1b9aac73dfcd4`, and that exact manifest hash. Any exception,
non-zero exit, malformed or extra stdout, non-`valid` status, or identity/hash
mismatch is terminal; stop and do not retry.

After the single verifier call, perform fresh read-only artifact,
sidecar/identity, migration-005, task, raw SQLite, protected reservation/
state/ledger/report/Gate, backup/progress, scratch, and process checks. Do not
publish, create a backup, run worker/CLI task execution, run OOS, or invoke
Promotion, Alpha, or Signal. Record `PHASE D PRECHECK READY` only if every
dependency and fresh state check passes. That record does not authorize
one-draw; one-draw remains a separate later authorization.
