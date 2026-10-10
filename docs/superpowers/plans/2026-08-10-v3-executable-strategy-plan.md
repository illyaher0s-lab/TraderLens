# v3 Executable Strategy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the exact approved v3 strategy executable through B4 Canary and one real IS event backtest without touching OOS.

**Architecture:** Publish one immutable execution-semantics supplement, add a dedicated v3 executor selected by a narrow dispatch in the existing event-backtest entry point, and complete the missing PIT adapter methods. Reuse existing fill, cost, order-conflict, status, and force-liquidation primitives; do not extend the generic DSL.

**Tech Stack:** Python 3.12, Pydantic contracts, PyArrow formal partitions, SQLite read-only discovery, pytest.

**Execution constraint:** Do not use Git/worktrees, do not overwrite immutable artifacts, and stop on the first new independent root cause.

**Authoritative execution order:** Task 1 adapter → Task 2 executor focused GREEN → Task 3 supplement publication and production dispatch → Task 4 Canary/IS. The Task 3 section appears first only because it contains the shared frozen payload reference; it must not be executed before Tasks 1 and 2 are complete and their source bytes are stable.

---

### Task 3: Immutable execution-semantics supplement and production dispatch

**Files:**
- Create: `scripts/publish_v3_execution_semantics.py`
- Create: `scripts/verify_v3_execution_semantics.py`
- Create: `tests/test_v3_execution_semantics.py`
- Modify: `strategy_core/backtest_engine.py`

Do not start this task until the adapter and executor focused suites are GREEN. The supplement must bind their final source hashes; publishing against pre-change or placeholder hashes is forbidden.

- [ ] Write focused RED tests proving publication/verification, exact market-regime approval binding, source tamper rejection, semantic tamper rejection, and write-once conflict rejection.

The canonical semantics payload must contain the values approved in `docs/superpowers/specs/2026-08-10-v3-executable-strategy-design.md`, including:

```python
semantics = {
    "schedule": {
        "execution_day": "first_shsz_common_open_day_of_iso_week",
        "as_of_day": "immediately_previous_completed_shsz_common_open_day",
    },
    "confirmation": {"independent_pit_days": 3, "entry_rank_percentile_max": 15},
    "exit": {
        "rank_percentile_min": 40,
        "max_holding_common_sessions": 15,
        "entry_session_counts_as_one": True,
        "stop_loss_pct": 8,
        "stop_reference": "completed_day_raw_close_vs_actual_average_fill_cost",
    },
    "portfolio": {
        "initial_capital_cny": 100000,
        "max_positions": 5,
        "target_weight": 0.20,
        "board_lot": 100,
        "residual_cash": "retain",
        "tie_break": "momentum_desc_symbol_asc",
    },
    "orders": {
        "same_symbol_conflict": "exit_wins",
        "blocked_exit": "retry_each_common_open_day",
        "blocked_entry": "expire_after_scheduled_execution_day",
        "market_regime": "block_new_entries_only",
    },
    "fill": {
        "price": "execution_day_open",
        "commission_rate": 0.0003,
        "minimum_commission": 5,
        "sell_stamp_duty": 0.001,
        "transfer_fee": 0,
        "slippage": 0,
        "maximum_participation": 0.10,
    },
}
```

The artifact must bind exact v3 template/revision/protocol/data/criteria IDs and hashes plus market-regime approval `6170c11c8068f407` manifest SHA `75aeb703f09a6876e329466b435e78574c24922ea56a9ba987b0ab7d17165b50`.

- [ ] Run RED:

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m pytest tests/test_v3_execution_semantics.py -q
```

Expected: non-zero exit because publisher/verifier modules are absent.

- [ ] Implement the smallest canonical publisher and independent verifier. The verifier must recompute all referenced hashes, including the final adapter and executor bytes, and invoke the existing owner-approval verifier.

- [ ] Run GREEN with the same command; require exit `0` and report the exact pass count.

- [ ] Before the final GREEN run and publication, add the narrow production dispatch to `run_event_backtest()`: retain the legacy `StrategyConfig` path unchanged; accept only the exact v3 execution spec plus a supplement path that passes the independent verifier at call time; route it to `run_v3_relative_strength_backtest()`. Focused tests use a temporary supplement created from the final source bytes. Run `tests/test_b4_event_backtest_loop.py` to prove legacy compatibility.

- [ ] Publish once and independently verify once. Capture the returned artifact ID/path instead of predicting or hardcoding it. Stop if its source bindings do not match the final code bytes and approved design.

### Task 1: Complete only the PIT adapter boundary required by v3

**Files:**
- Modify: `backend/services/formal_pit_partition_adapter.py`
- Create: `tests/test_v3_formal_pit_execution_adapter.py`

- [ ] Write focused RED tests for these exact public methods:

```python
adapter.symbols_as_of(as_of_date)       # PIT membership active on date
adapter.get_daily_bars(symbol, end, n)  # n completed common-day bars through end
adapter.get_bar(symbol, date_)           # alias of exact daily-bar read
adapter.get_status(symbol, date_)        # alias of exact daily-status read
adapter.common_trading_dates(start, end)
```

Tests must use a real-shaped temporary membership `records.parquet` with effective intervals and real-shaped formal partitions. They must prove no future membership/date is returned and missing required partitions fail loud.

- [ ] Run RED:

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m pytest tests/test_v3_formal_pit_execution_adapter.py -q
```

Expected: non-zero exit because the required boundary is incomplete.

- [ ] Implement only these methods. Load membership snapshot `pims_traderlens_v2_shsz_sw2021_pit_005`; use `effective_from <= as_of` and `effective_to is null or as_of < effective_to`; never use a static list. Reuse the existing partition/cache functions.

- [ ] Run GREEN and the existing focused adapter suite separately:

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m pytest tests/test_v3_formal_pit_execution_adapter.py -q
D:\Codex\TraderLens\.venv\Scripts\python.exe -m pytest tests/test_formal_pit_partition_adapter.py -q
```

If the second file does not exist, use `rg --files tests | rg "formal_pit.*adapter"` and run the single existing matching suite; report the exact selected path.

### Task 2: Dedicated v3 executor core

**Files:**
- Create: `strategy_core/v3_relative_strength_executor.py`
- Create: `tests/test_v3_relative_strength_executor.py`

- [ ] Define one frozen dispatch contract; it is not a DSL:

```python
@dataclass(frozen=True)
class V3RelativeStrengthExecutionSpec:
    strategy_revision_id: str
    protocol_snapshot_id: str
    data_snapshot_hash: str
    supplement_id: str
    backtest_start: date
    backtest_end: date
    initial_capital: float = 100000.0
```

This task implements and tests `run_v3_relative_strength_backtest()` directly against the explicit frozen semantics in the approved design. It must not modify `run_event_backtest()` and must not publish a supplement. Production admission and dispatch are added only in Task 3 after source hashes are final.

- [ ] Write RED tests with a deterministic in-memory/common-calendar fixture proving:

  - first-common-day weekly execution and previous-common-day as-of mapping;
  - 252-day adjusted momentum and three independent PIT confirmations;
  - top-15 entry, outside-top-40 exit, and symbol-ascending tie break;
  - qualified liquidity and market-regime entry block;
  - maximum five positions, 20% sizing, 100-share rounding, residual cash;
  - exit-wins conflict, 15-common-session exit, and 8% stop loss;
  - blocked entry expires and blocked exit retries;
  - result uses revision `6440ffc03a742f4d4632078481cf3abf171eafb1a24f2bc69bc6f352d1b19ebc` rather than a strategy name;
  - future reads fail through the existing cursor guard.

- [ ] Run RED:

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m pytest tests/test_v3_relative_strength_executor.py -q
```

- [ ] Implement the dedicated loop by composing existing `PortfolioState`, `PositionSizer`, order/fill functions, status handling, transaction costs, and force-liquidation functions. Do not copy their formulas or add alternative simulators. Focused tests call this core with the explicit approved semantics; they do not claim production authorization.

- [ ] Run GREEN and legacy event-loop compatibility separately:

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m pytest tests/test_v3_relative_strength_executor.py -q
D:\Codex\TraderLens\.venv\Scripts\python.exe -m pytest tests/test_b4_event_backtest_loop.py -q
D:\Codex\TraderLens\.venv\Scripts\python.exe -m pytest tests/test_b4_delisting_liquidation.py -q
```

Stop if an approved semantic cannot be supplied by the existing tested primitive; do not create a second implementation.

### Task 4: Official Canary and one real IS run

**Files:**
- Create: `scripts/run_v3_b4_is_once.py`
- Create: `tests/test_run_v3_b4_is_once.py`
- Modify: `scripts/run_v3_task4_once.py`

- [ ] Write RED tests proving the one-shot runner:

  - loads the exact persisted protocol, formal snapshot, PIT membership records, supplement, market approval, and adapter;
  - calls `BacktestEngineQualification.run_qualification_with_b3_protocol()` before the executor;
  - refuses to execute IS if Canary is not `pass` or any of six cases is not `blocked`;
  - uses only IS dates `2025-06-27..2026-03-19`;
  - never opens OOS ledger/reservation/result paths;
  - writes a new immutable B4 IS artifact only after a complete valid result;
  - isolates test audit paths from production audit.

- [ ] Run RED:

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m pytest tests/test_run_v3_b4_is_once.py -q
```

- [ ] Implement a single operational entry point. Its B4 IS manifest must bind the EventBacktestResult canonical hash, supplement, revision, protocol, snapshot, universe, market approval, IS range, source inventory, and Canary qualification result. Include a sidecar and a read-only independent verifier in the same module only if no reusable verifier boundary exists.

- [ ] Run focused GREEN:

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m pytest tests/test_run_v3_b4_is_once.py -q
D:\Codex\TraderLens\.venv\Scripts\python.exe -m pytest tests/test_v3_b4_production_boundary.py -q
D:\Codex\TraderLens\.venv\Scripts\python.exe -m pytest tests/test_b4_canary_qualification.py -q
```

- [ ] Record DB/OOS counts and immutable hashes, then run exactly once:

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m scripts.run_v3_b4_is_once
```

If the real run fails, report the first complete error and stop. Do not retry a business/data failure. One mechanical path/quoting correction is allowed only if the runner did not start Canary or IS.

- [ ] If the real run succeeds, independently verify the B4 IS artifact and then run production discovery exactly once:

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m scripts.run_v3_task4_once
```

The discovery may record/reuse the B4 context but must not create a B6 task, reserve OOS, read OOS results, run Gate, Promotion, or Signal. Report the next exact prerequisite and stop.

### Final evidence

Report every changed file, supplement/B4 artifact ID and SHA, focused command/exit/pass count, Canary result, IS range/result summary, production audit path/hash, DB row counts before/after, and explicit confirmation that OOS was not read/reserved/consumed.
