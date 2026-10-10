# v3 B5 Comparison Performance and Progress Design

Status: `performance_gate_accepted_pending_bounded_slice`

This document is a performance-only supplement to
`2026-08-10-v3-b5-minimal-validation-design.md`. It does not change the
Task5 benchmark/control contract, P0-P3 precedence, portfolio accounting,
costs, inputs, hashes, IS/OOS boundary, or publication authority.

## 1. Verified problem boundary

The interrupted non-publishing real-slice test produced no pass/fail result.
Task5 therefore remains `blocked/watch`; no comparison artifact exists and no
Task6, OOS reservation, OOS read, or OOS consumption occurred.

Read-only profiling on the IS boundary `2025-06-26 -> 2025-06-27` found:

- one real `members_for()` call returned 3,902 members in 55.922 seconds;
- `derive_liquidity()` ran 4,625 times and consumed about 52.0 seconds;
- `_read_partition()` received 203,612 logical calls, including 97,153 calls
  each for `daily` and `suspend_d`, while only 44 calls missed the existing
  partition cache;
- benchmark and control use separate eligibility caches and repeat the same
  immutable eligibility/liquidity work;
- the real-slice test observer's `bar_count()` rescans its complete growing
  call list before and after each execution/mark operation, creating test-only
  O(N^2) work and retaining unnecessary call history.

The root cause is repeated Python-level 20-day window work plus the test-only
quadratic observer. It is not repeated physical Parquet I/O and is not an OOS,
database, or external-service wait.

## 2. Approved outcome

Implement significant acceleration plus live, flushed phase progress. An
interrupted process restarts from the beginning. Do not add durable checkpoints,
partial artifacts, resume logic, a generic cache service, parallel execution,
or a new dependency.

Acceptance targets are:

1. remove the observer's O(N^2) scan and unbounded general call history;
2. make the same real single-rebalance boundary at least 2x faster than the
   55.922-second baseline before another full real-slice attempt;
3. preserve exact benchmark/control payload semantics and failure behavior;
4. emit progress at each completed rebalance and an immediately flushed
   phase-verification message after benchmark and control assertions;
5. keep Task5 blocked/watch until the complete bounded real slice passes.

## 3. Minimal architecture

### 3.1 Test observer

`_RecordingReadBoundAdapter` keeps a monotonic integer bar counter. `_observe()`
increments it only for `bar`; `bar_count()` returns the integer in O(1). The
observer does not retain a complete list of lifecycle, status, liquidity, and
bar calls. The existing narrow execution/mark observations needed by the P0/P2
assertions remain unchanged.

### 3.2 Per-execution-date liquidity preparation

`FormalPITPartitionAdapter` prepares the frozen 20-day liquidity result for an
execution date once per adapter instance. For each of the 20 prior common days,
it reads the existing `suspend_d` partition map first and separates suspended
symbols from still-active symbols. Suspended symbols contribute zero and do not
require that day's `daily` partition or row. Only still-active, non-faulted
symbols consume the day's `daily` partition map. This preserves the scalar
source-precedence rule while applying the existing amount-unit conversion and
building immutable per-symbol results. The cache key is the exact
`execution_date`; the adapter instance itself already binds the formal root,
verified calendar, membership, and lifecycle inputs.

`derive_liquidity(symbol, execution_date)` remains the public boundary. It
returns the prepared result for that symbol and date. Its output vocabulary and
semantics remain exact:

- inactive or fewer than 20 completed common days since listing:
  `unavailable_ineligible`;
- missing/invalid required source evidence: `data_fault`;
- otherwise the same 50,000,000-yuan threshold produces `qualified` or
  `ineligible`, with the same `average_amount_yuan`.

The in-process cache may be reused by benchmark and control because both share
the same formal adapter and the cached value is independent of holdings,
weights, cash, marks, and comparison kind. `_last_prices`, positions, cash,
turnover, and result audit state remain separate. No eligible-universe cache is
shared in this change.

A missing `suspend_d` partition remains a `data_fault` for every otherwise
eligible symbol because the scalar path cannot establish suspension precedence.
A missing `daily` partition faults only symbols that are active on that day;
symbols with exact same-day suspension evidence remain zero for that day. A
missing daily row or invalid amount faults only that active symbol and is
terminal for the remainder of its prepared window. Amount zero remains valid;
bool, non-Real, non-finite, and negative values remain invalid. The existing
early eligibility guard continues to map unknown/malformed symbols and short
listing history to `unavailable_ineligible` before prepared results are read.

### 3.3 Progress boundary

`run_fractional_index()` accepts an optional progress callback. With no callback,
behavior and output are unchanged. After each scheduled rebalance completes, it
emits a non-persistent event containing only:

```text
kind, phase=rebalance_completed, completed_rebalances,
total_rebalances, execution_date, elapsed_seconds
```

The real-slice test prints each event with `flush=True`. It runs and validates
benchmark first, prints `benchmark verified`, then runs and validates control
and prints `control verified`. These messages are visibility only: neither an
event nor a completed first phase is a Task5 pass, artifact, or authorization.

Progress callback errors fail loud. Progress is not hashed, persisted, included
in result payloads, or consumed by the verifier.

## 4. Error and recovery behavior

All existing source, status, P0-P3, NAV, turnover, read-bound, and OOS failures
retain their current exception types and stopping behavior. Cached preparation
must not convert missing partitions, missing symbols, invalid amounts, or
unsupported status evidence into defaults.

An interrupted run has no resumable state and no partial production result.
After interruption, Task5 remains `blocked/watch`; a new full run requires a
fresh pre-gate and explicit authorization. Publisher, verifier, Task6, and OOS
remain prohibited until the bounded slice is fully GREEN.

## 4.1 Task6P first bounded run and Task6P2 scope

The first bounded non-publishing run provided the following evidence and is retained as historical evidence: the benchmark completed 25/25 rebalances in 358.264 seconds, then failed at `tests/test_v3_b5_comparisons.py:685` for `688766.SH` on 2025-12-08 because the actual mark reason was `suspended_carry` while the assertion expected `close`; the control run did not start.

The read-only root cause is a test assertion error, not a production defect. On 2025-12-08 the `688766.SH` daily symbol row is absent and `suspend_d` contains `S` with null timing, so the frozen P1 contract correctly produces `suspended_carry`. The next valid mark is 2025-12-09 with `close=136.42`. The old assertion conflated the 2025-12-08 P0 boundary for `002348.SZ` with the separate `688766.SH` P1 boundary. Production remains unchanged.

Task6P2 is a narrow continuation authorized only for the test assertion correction, focused verification, and one bounded non-publishing rerun. It does not authorize publication, OOS access, preflight, verifier, promotion, or any downstream Task6/B6 work.

## 5. TDD and verification design

Implementation uses RED -> GREEN in this order:

1. prove the observer counter no longer iterates stored call history and still
   reports exact per-operation bar deltas;
2. prove multiple symbols on the same execution date cause only one 20-day
   `daily`/`suspend_d` preparation, while results match the current scalar
   qualified/ineligible/unavailable/data-fault cases;
   characterization tests must first preserve suspended-day-without-daily,
   exact-20-day listing history, 19-day short history, and delisting behavior;
3. prove progress event order and counts without changing the returned result;
4. run the existing adapter, comparison, contract, and ledger focused suites;
5. run the exact real single-rebalance profiling boundary once and require at
   least 2x speedup with identical member output and no OOS read;
6. only after those checks pass, prepare a new read-only pre-gate for one
   explicitly authorized bounded real-slice run.

No runtime timing assertion is added to the ordinary unit suite. The 2x target
is recorded as controlled profiling evidence on the same machine and boundary;
deterministic unit acceptance is based on exact results, event sequence, and
partition-preparation counts.

The single controlled probe completed in 26.215987399977166 seconds with 3,902
members and zero OOS reads. On 2026-08-17 the user approved the balanced 2x
threshold (`55.922 / 2 = 27.961` seconds) rather than adding a second independent
optimization root. This existing probe passes the revised threshold; it must
not be rerun merely to obtain a different exit code.

## 6. Explicit exclusions

- no strategy, benchmark, control, liquidity threshold, cost, P0-P3, or data
  source change;
- no persistent precomputation, checkpoint/resume, multiprocessing, thread pool,
  generic platform, schema migration, or dependency;
- no artifact publication, database write, Git/worktree operation, Task6, B6,
  OOS, Gate, Promotion, or Signal action;
- no deletion or consumption of `_tmp_coverage_scan_result.json`.
