# v3 B5 Comparison Performance and Progress Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the real-slice test's quadratic observer overhead, batch the frozen 20-day liquidity calculation per execution date, and emit live rebalance/phase progress without changing any Task5 result semantics.

**Architecture:** Keep the existing public comparison and adapter boundaries. `FormalPITPartitionAdapter` adds one process-local, exact-execution-date cache containing scalar-equivalent liquidity results; `run_fractional_index` adds an optional callback whose events never enter result payloads. The real-slice test uses an O(1) bar counter and validates benchmark before starting control so partial phase progress is visible but never treated as Task5 completion.

**Tech Stack:** Python 3.11, stdlib `collections.OrderedDict`, `time.perf_counter`, existing `unittest`/`pytest`, PyArrow-backed formal PIT adapter.

**Execution authority:** `D:\Codex\TraderLens\AGENTS.md` overrides the generic skill's commit advice. Do not create a worktree, run Git, commit, publish, run the bounded real slice, or touch Task6/OOS while executing Tasks 1-5 below.

---

## File map

- Modify `backend/services/formal_pit_partition_adapter.py`: process-local per-execution-date liquidity preparation/cache; no contract change.
- Modify `backend/services/v3_b5_comparison.py`: optional non-persistent rebalance progress callback.
- Modify `tests/test_task3b_formal_partition_adapter.py`: scalar-equivalence and one-preparation RED/GREEN evidence.
- Modify `tests/test_v3_b5_comparisons.py`: O(1) observer RED/GREEN evidence, progress event test, and sequential real-slice phase reporting.
- Read only `scripts/publish_v3_b5_comparisons.py`: confirm both comparison sources still share the same raw adapter; do not edit it.

## Task 1: Replace the test-only quadratic observer

**Files:**
- Modify: `tests/test_v3_b5_comparisons.py:107-170`

- [ ] **Step 1: Add the failing O(1)-counter behavior test.**

Add this helper above `TestV3B5Comparisons` and this test inside the class:

```python
class _ExplodingCalls:
    def __iter__(self):
        raise AssertionError("bar_count scanned retained call history")


def test_real_slice_observer_bar_count_does_not_scan_call_history(self):
    adapter = _RecordingReadBoundAdapter(_P2Adapter(), date(2025, 12, 9))
    adapter._observe("liquidity", "A.SH", date(2025, 12, 1))
    adapter._observe("bar", "A.SH", date(2025, 12, 1))
    adapter.calls = _ExplodingCalls()

    self.assertEqual(adapter.bar_count(), 1)
```

This is intentionally test-helper behavior: the current `bar_count()` iterates
`calls` and must fail with `bar_count scanned retained call history`.

- [ ] **Step 2: Run the focused RED test separately.**

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_v3_b5_comparisons.TestV3B5Comparisons.test_real_slice_observer_bar_count_does_not_scan_call_history -v
```

Expected: exit non-zero with the exact `AssertionError`; no production file has changed.

- [ ] **Step 3: Implement the minimal O(1) observer.**

Replace the general retained call list with an integer:

```python
class _RecordingReadBoundAdapter(ReadBoundAdapter):
    """Transparent production adapter observer used only by the real-slice test."""

    def __init__(self, raw, allowed_end):
        super().__init__(raw, allowed_end)
        self._bar_count = 0

    def _observe(self, operation, symbol=None, day=None):
        if operation == "bar":
            self._bar_count += 1

    # Existing adapter delegation methods remain byte-for-byte unchanged.

    def bar_count(self):
        return self._bar_count
```

Do not retain non-bar calls in a replacement collection. The superclass
`ReadBoundAdapter` remains the authoritative read/OOS audit.

- [ ] **Step 4: Run the same focused test GREEN.**

Expected: exit 0, one test passed.

## Task 2: Batch frozen liquidity once per execution date

**Files:**
- Modify: `tests/test_task3b_formal_partition_adapter.py:385-459`
- Modify: `backend/services/formal_pit_partition_adapter.py:61-69,217-260`

- [ ] **Step 1: Add and run scalar characterization tests before the performance RED.**

Extend `_temporary_liquidity_fixture` with an optional
`list_date_overrides=None`, normalize it with `dict(...)`, and use
`list_date_overrides.get(row["ts_code"], row["list_date"])` when writing
`stock_basic`. Add these tests to `TestFormalLiquidityDerivation`:

```python
def test_suspended_day_does_not_require_daily_partition(self):
    from backend.services.formal_pit_partition_adapter import FormalPITPartitionAdapter

    day = self.EXECUTION_DATE - timedelta(days=3)
    with self._temporary_liquidity_fixture(
        common_count=20,
        common_amount=50000.0,
        suspended_dates={day},
        missing_daily_dates={day},
    ) as root:
        result = FormalPITPartitionAdapter(root).derive_liquidity(
            "AAA.SZ", self.EXECUTION_DATE
        )
    self.assertEqual(
        result,
        {"status": "ineligible", "average_amount_yuan": 47_500_000.0},
    )

def test_exact_twenty_day_listing_history_is_eligible_but_nineteen_is_not(self):
    from backend.services.formal_pit_partition_adapter import FormalPITPartitionAdapter

    exact_first = self.EXECUTION_DATE - timedelta(days=22)
    with self._temporary_liquidity_fixture(
        common_count=20,
        common_amount=50000.0,
        list_date_overrides={"AAA.SZ": exact_first.strftime("%Y%m%d")},
    ) as root:
        exact = FormalPITPartitionAdapter(root).derive_liquidity(
            "AAA.SZ", self.EXECUTION_DATE
        )
    with self._temporary_liquidity_fixture(
        common_count=20,
        common_amount=50000.0,
        list_date_overrides={
            "AAA.SZ": (exact_first + timedelta(days=1)).strftime("%Y%m%d")
        },
    ) as root:
        short = FormalPITPartitionAdapter(root).derive_liquidity(
            "AAA.SZ", self.EXECUTION_DATE
        )
    self.assertEqual(
        exact,
        {"status": "qualified", "average_amount_yuan": 50_000_000.0},
    )
    self.assertEqual(
        short,
        {"status": "unavailable_ineligible", "average_amount_yuan": None},
    )
```

The test module already imports `timedelta` and `FormalPITPartitionAdapter`
inside each test; retain that local import style. Run both tests before any
production edit:

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_task3b_formal_partition_adapter.TestFormalLiquidityDerivation.test_suspended_day_does_not_require_daily_partition tests.test_task3b_formal_partition_adapter.TestFormalLiquidityDerivation.test_exact_twenty_day_listing_history_is_eligible_but_nineteen_is_not -v
```

Expected: exit 0, two tests passed. A failure means the characterization or
date boundary is wrong; stop and repair only the tests before proceeding.

- [ ] **Step 2: Add a RED test proving scalar-equivalent results and one preparation.**

Add to `TestFormalLiquidityDerivation`:

```python
def test_same_execution_date_prepares_liquidity_partitions_once(self):
    from backend.services.formal_pit_partition_adapter import FormalPITPartitionAdapter

    with self._temporary_liquidity_fixture(common_count=20, common_amount=50000.0) as root:
        adapter = FormalPITPartitionAdapter(root)
        calls = Counter()
        original = adapter._read_partition

        def counted(partition_name, execution_date):
            calls[partition_name] += 1
            return original(partition_name, execution_date)

        adapter._read_partition = counted
        self.assertEqual(
            adapter.derive_liquidity("AAA.SZ", self.EXECUTION_DATE),
            {"status": "qualified", "average_amount_yuan": 50_000_000.0},
        )
        self.assertEqual(
            adapter.derive_liquidity("P.SZ", self.EXECUTION_DATE),
            {"status": "data_fault", "average_amount_yuan": None},
        )
        self.assertEqual(
            adapter.derive_liquidity("AAA.SZ", self.EXECUTION_DATE),
            {"status": "qualified", "average_amount_yuan": 50_000_000.0},
        )

    self.assertEqual(calls["daily"], 20)
    self.assertEqual(calls["suspend_d"], 20)
```

The existing scalar implementation must fail because the second symbol causes
additional logical `_read_partition()` calls.

- [ ] **Step 3: Run the focused RED test separately.**

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_task3b_formal_partition_adapter.TestFormalLiquidityDerivation.test_same_execution_date_prepares_liquidity_partitions_once -v
```

Expected: exit non-zero; at least one count is greater than 20. If it fails for
fixture construction or a different reason, repair only the test and repeat RED.

- [ ] **Step 4: Add the exact-date process-local cache.**

In `FormalPITPartitionAdapter.__init__`, add:

```python
self._liquidity_cache: OrderedDict[
    date, dict[str, tuple[str, float | None]]
] = OrderedDict()
self._liquidity_cache_max_entries = 64
```

Add this helper immediately above `derive_liquidity`:

```python
def _prepare_liquidity(self, execution_date: date) -> dict[str, tuple[str, float | None]]:
    cached = self._liquidity_cache.get(execution_date)
    if cached is not None:
        self._liquidity_cache.move_to_end(execution_date)
        return cached

    window = [day for day in self._common_trading_dates if day < execution_date][-20:]
    results: dict[str, tuple[str, float | None]] = {}
    if len(window) == 20:
        first_day = window[0]
        candidates = {
            symbol
            for symbol, (list_date, delist_date) in self._stock_basic.items()
            if list_date <= first_day
            and (delist_date is None or execution_date < delist_date)
        }
        totals = {symbol: 0.0 for symbol in candidates}
        faults: set[str] = set()
        for day in window:
            try:
                suspended = self._read_partition("suspend_d", day)
            except (FileNotFoundError, OSError, KeyError, TypeError, ValueError):
                faults.update(candidates)
                break
            active = candidates.difference(faults, suspended)
            if not active:
                continue
            try:
                daily = self._read_partition("daily", day)
            except (FileNotFoundError, OSError, KeyError, TypeError, ValueError):
                faults.update(active)
                continue
            for symbol in active:
                try:
                    amount = daily[symbol]["amount"]
                except (KeyError, TypeError):
                    faults.add(symbol)
                    continue
                if isinstance(amount, bool) or not isinstance(amount, Real):
                    faults.add(symbol)
                    continue
                numeric = float(amount)
                if not math.isfinite(numeric) or numeric < 0:
                    faults.add(symbol)
                    continue
                totals[symbol] += numeric * 1000
        for symbol in candidates:
            if symbol in faults:
                results[symbol] = ("data_fault", None)
                continue
            average = totals[symbol] / 20
            results[symbol] = (
                "qualified" if average >= 50_000_000 else "ineligible",
                average,
            )

    if len(self._liquidity_cache) >= self._liquidity_cache_max_entries:
        self._liquidity_cache.popitem(last=False)
    self._liquidity_cache[execution_date] = results
    return results
```

Replace the scalar 20-day partition loop in `derive_liquidity` while preserving
its existing docstring and early eligibility behavior:

```python
unavailable = {"status": "unavailable_ineligible", "average_amount_yuan": None}
try:
    if not self.is_eligible(symbol, execution_date):
        return unavailable
    list_date = self._stock_basic[symbol][0]
except (KeyError, TypeError, ValueError):
    return unavailable

window = [day for day in self._common_trading_dates if day < execution_date][-20:]
if len(window) != 20 or list_date > window[0]:
    return unavailable
status, average = self._prepare_liquidity(execution_date).get(
    symbol, ("data_fault", None)
)
return {"status": status, "average_amount_yuan": average}
```

The small per-call calendar slice is permitted only as an eligibility guard;
all partition aggregation is date-cached. The ordering above is load-bearing:
`suspend_d` is read first, suspended symbols are removed from `active`, and a
missing `daily` partition faults only `active`. Do not alter the suspension-zero,
amount multiplier, threshold, missing-data, or listing/delisting rules.

- [ ] **Step 5: Run the focused liquidity test GREEN.**

Expected: exit 0, one test passed, exactly 20 logical calls per source partition.

- [ ] **Step 6: Run the complete frozen liquidity matrix separately.**

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_task3b_formal_partition_adapter.TestFormalLiquidityDerivation -v
```

Expected: exit 0; qualified, ineligible, unavailable, suspended-zero and every
data-fault case remain exact.

## Task 3: Add optional rebalance progress without changing results

**Files:**
- Modify: `tests/test_v3_b5_comparisons.py:399-432`
- Modify: `backend/services/v3_b5_comparison.py:1-20,512-639`

- [ ] **Step 1: Add the progress RED test.**

Add to `TestV3B5Comparisons`:

```python
def test_fractional_index_reports_completed_rebalances_without_changing_result(self):
    dates = (
        date(2025, 11, 26), date(2025, 11, 27),
        date(2025, 12, 1), date(2025, 12, 9),
    )
    schedule = [
        {"formation_date": "2025-11-26", "as_of_date": "2025-11-25", "execution_date": "2025-11-26"},
        {"formation_date": "2025-12-01", "as_of_date": "2025-11-28", "execution_date": "2025-12-01"},
    ]
    observations = [
        {"date": day.isoformat(), "portfolio_value": value,
         "daily_return": 0.0 if index == 0 else value / (value - 0.01) - 1.0}
        for index, (day, value) in enumerate(zip(dates, (1.0, 1.01, 1.02, 1.04)))
    ]
    baseline = run_fractional_index(
        kind="control", source=_p2_source(), dates=dates,
        schedule=schedule, strategy_observations=observations,
    )
    events = []
    observed = run_fractional_index(
        kind="control", source=_p2_source(), dates=dates,
        schedule=schedule, strategy_observations=observations,
        progress=events.append,
    )

    self.assertEqual(observed, baseline)
    self.assertEqual(
        [
            {key: event[key] for key in (
                "kind", "phase", "completed_rebalances",
                "total_rebalances", "execution_date",
            )}
            for event in events
        ],
        [
            {"kind": "control", "phase": "rebalance_completed",
             "completed_rebalances": 1, "total_rebalances": 2,
             "execution_date": "2025-11-26"},
            {"kind": "control", "phase": "rebalance_completed",
             "completed_rebalances": 2, "total_rebalances": 2,
             "execution_date": "2025-12-01"},
        ],
    )
    self.assertTrue(all(event["elapsed_seconds"] >= 0 for event in events))
```

- [ ] **Step 2: Run the progress RED test separately.**

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_v3_b5_comparisons.TestV3B5Comparisons.test_fractional_index_reports_completed_rebalances_without_changing_result -v
```

Expected: exit non-zero because `run_fractional_index` does not accept
`progress`.

- [ ] **Step 3: Implement the optional callback.**

Import `perf_counter` and `Callable`, then extend the function signature:

```python
from time import perf_counter
from typing import Any, Callable, Iterable

def run_fractional_index(
    *,
    kind: str,
    source: _FormalComparisonSource,
    dates: tuple[date, ...],
    schedule: list[dict[str, str]],
    strategy_observations: list[dict[str, Any]],
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
```

Immediately after `schedule_by_day`, initialize:

```python
started_at = perf_counter()
total_rebalances = sum(day in schedule_by_day for day in dates)
completed_rebalances = 0
```

Immediately after the existing `rebalances.append(...)` completes:

```python
completed_rebalances += 1
if progress is not None:
    progress({
        "kind": kind,
        "phase": "rebalance_completed",
        "completed_rebalances": completed_rebalances,
        "total_rebalances": total_rebalances,
        "execution_date": day.isoformat(),
        "elapsed_seconds": max(perf_counter() - started_at, 0.0),
    })
```

Do not catch callback errors, print inside the service, or include progress in
the returned result.

- [ ] **Step 4: Run the same progress test GREEN.**

Expected: exit 0, one test passed; `observed == baseline` exactly.

## Task 4: Make the real-slice phases visible without running them

**Files:**
- Modify: `tests/test_v3_b5_comparisons.py:471-651`

- [ ] **Step 1: Add a flushed formatter inside the real-slice test.**

Immediately before running benchmark/control, add:

```python
def print_progress(event):
    print(
        f"[{event['kind']}] rebalance "
        f"{event['completed_rebalances']}/{event['total_rebalances']} "
        f"{event['execution_date']} elapsed={event['elapsed_seconds']:.3f}s",
        flush=True,
    )
```

- [ ] **Step 2: Run and validate each comparison phase sequentially.**

Replace the eager `results = (...)` tuple with:

```python
total_p2_events = 0
for kind, source in (
    ("benchmark", benchmark_source),
    ("control", control_source),
):
    result = run_fractional_index(
        kind=kind,
        source=source,
        dates=dates,
        schedule=schedule,
        strategy_observations=observations,
        progress=print_progress,
    )
```

Move the current assertion body from the existing `for source, result in
results:` loop directly under this loop without changing any assertion. Keep
`total_p2_events += ...` in the loop. At the end of each successful assertion
body add:

```python
print(f"[{kind}] verified", flush=True)
```

Keep the final `total_p2_events == 14` and output-directory equality assertions
after the loop. Do not execute this real test in Task 4.

- [ ] **Step 3: Perform static verification only.**

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m py_compile tests/test_v3_b5_comparisons.py backend/services/formal_pit_partition_adapter.py backend/services/v3_b5_comparison.py
```

Expected: exit 0. This command must not execute the bounded slice.

## Task 5: Focused GREEN regression and controlled performance gate

**Files:**
- Verify only; no new production change after the gate starts.

- [ ] **Step 1: Run each focused suite separately.**

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m pytest tests/test_v3_b5_comparisons.py -q -k "not real_p2_unavailable_mark_slice_20251124_20251209"
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_task3b_formal_partition_adapter -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m pytest tests/test_v3_formal_pit_execution_adapter.py -q
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_v3_b5_contracts -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_v3_b5_ledger_observation -v
```

Report each exact command, exit code, pass/fail count, duration, and warnings.
Any semantic failure is a new independent root cause: stop without running the
performance gate or changing another file.

- [x] **Step 2: Record the already-executed single-rebalance performance probe.**

This command was run exactly once from `D:\Codex\TraderLens` and remained
entirely inside the IS. Do not run it again:

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -c "from datetime import date; from pathlib import Path; from time import perf_counter; from backend.services.formal_pit_partition_adapter import FormalPITPartitionAdapter; from backend.services.v3_b5_comparison import ReadBoundAdapter,_FormalComparisonSource; from scripts.publish_v3_b5_comparisons import DEFAULT_LIFECYCLE_MANIFEST,_load_coverage_binding,_load_industry_index,_load_lifecycle; root=Path.cwd(); raw=FormalPITPartitionAdapter(root); guarded=ReadBoundAdapter(raw,date(2025,6,27)); lifecycle,_=_load_lifecycle(raw.formal_root/'stock_basic',DEFAULT_LIFECYCLE_MANIFEST); coverage,_=_load_coverage_binding(root); source=_FormalComparisonSource(guarded,_load_industry_index(root),lifecycle=lifecycle,coverage_unavailable=coverage); started=perf_counter(); members=source.members_for(date(2025,6,26),date(2025,6,27)); elapsed=perf_counter()-started; print({'elapsed_seconds':elapsed,'member_count':len(members),'oos_read_count':source.audit()['read_audit']['oos_read_count']}); raise SystemExit(0 if elapsed <= 27.961 and len(members)==3902 and source.audit()['read_audit']['oos_read_count']==0 else 1)"
```

Revised acceptance: elapsed at most 27.961 seconds (2x faster than 55.922),
member count 3,902, and OOS reads 0. The recorded evidence is
26.215987399977166 seconds, 3,902 members, and zero OOS reads. Its original exit
code was 1 only because the then-current 5x threshold was stricter; the user
approved the revised 2x threshold on 2026-08-17. Reclassify the evidence without
rerunning the probe.

- [ ] **Step 3: Recheck the protected boundary.**

Fresh read-only checks must show:

```text
data/pit/v3_b5_comparisons absent
research_protocol_snapshots=1
b6_validation_tasks=0
oos_budget_reservations=0
oos_budget_state=0
oos_evaluation_ledgers=0
immutable_backtest_reports=0
prototype_gate_results_v2=0
```

Also report SHA-256 for the four modified implementation/test files and both
performance spec/plan files. `_tmp_coverage_scan_result.json` remains untouched.

- [x] **Step 4: Record the completed stop before the bounded real slice.**

If every focused check and the 2x gate pass, report only:

```text
performance/progress checkpoint verified;
Task5 remains blocked/watch;
bounded real slice requires a new explicit one-shot authorization;
publisher/verifier/Task6/OOS not run.
```

That checkpoint stopped without the bounded real slice. The user subsequently
approved Task 6P below. Preflight, publisher, verifier, the mainline Task6
bundle, B6, OOS, Gate, Promotion, and Signal remain prohibited.

## Plan self-review

1. The plan covers every approved design item: O(1) observer, exact-date batch
   liquidity, live rebalance progress, phase verification output, semantic
   regressions, 2x controlled gate, and explicit no-resume behavior.
2. The only production behavior changes are an internal scalar-equivalent
   cache and an optional callback with a `None` default. No strategy or result
   field changes.
3. Tests observe real adapter/result boundaries. Counts, exact values, result
   equality, callback events, failures, OOS guard, and the real timing gate are
   all asserted separately.
4. Tasks 1-5 honored RED -> GREEN and stopped before a complete slice. Task 6P
   is a later, explicit one-shot authorization; publication, Git, database
   writes, and OOS actions remain prohibited.

## Task 6P: Run the newly authorized bounded real slice once

**Files:**
- Verify only; no file modification is authorized in this task.

- [ ] **Step 1: Perform a fresh read-only pre-gate.**

Confirm the current hashes of the four implementation/test files match the
checkpoint report, the target test compiles, no process is already running that
test method, `data/pit/v3_b5_comparisons` is absent, and the seven DB counts are
exactly `(1,0,0,0,0,0,0)`. Confirm no OOS reservation or consumption occurred.
Any mismatch stops without running the test.

- [ ] **Step 2: Run exactly one bounded, non-publishing real slice.**

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_v3_b5_comparisons.TestV3B5Comparisons.test_real_p2_unavailable_mark_slice_20251124_20251209 -v
```

This single run must print each completed rebalance and print
`[benchmark] verified` before starting control. Do not interrupt, retry, edit,
or start a second process. A non-zero exit stops Task5 blocked/watch.

- [ ] **Step 3: Perform the read-only post-gate.**

Record the exact exit code, test count, duration, progress boundary reached,
OOS read audit, seven DB counts, output-root absence, and current hashes. On
exit 0, report `bounded real slice verified; Task5 remains unpublished and
awaits independent preflight`. Do not run preflight, publisher, verifier,
Task6 bundle work, B6, OOS, Gate, Promotion, or Signal.

## Task 6P2: Correct the 688766 assertion and rerun once

This narrow continuation records the first bounded-run result without rewriting its history. The benchmark completed 25/25 rebalances in 358.264 seconds, then failed at `tests/test_v3_b5_comparisons.py:685` for `688766.SH` on 2025-12-08 (`actual='suspended_carry'`, `expected='close'`); the control run did not start. Read-only source evidence shows that the 2025-12-08 daily row is absent and `suspend_d=S` with null timing, so the frozen P1 contract correctly requires `suspended_carry`. The next valid mark is 2025-12-09 `close=136.42`; the old assertion confused this boundary with the separate 002348.SZ P0 case.

Scope is limited to:

1. Change `tests/test_v3_b5_comparisons.py` so `688766.SH` explicitly expects `suspended_carry` on 2025-12-08 and expects the next valid `close` mark on 2025-12-09.
2. Run the required compile and non-real focused suite checks.
3. After fresh read-only pre-gates pass, run the exact bounded non-publishing test once.

No production change, artifact publication, OOS read/reservation/consumption, preflight, publisher, verifier, mainline Task6/B6, Gate, Promotion, or Signal work is authorized by this continuation. Any new independent failure stops the run without a second correction or retry.
