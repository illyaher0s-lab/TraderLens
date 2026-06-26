# Milestone 2 Boundary Discussion

**Status**: Open  
**Last Updated**: 2026-06-22  
**Context**: M1 deterministic validation closed successfully. Before building Web UI or research modules, establish M2 stability boundaries.

---

## M2 Scope Constraint

**In scope**:
- Contracts stability review
- Export format finalization
- Audit requirements
- Task execution boundaries
- Data source interface contracts

**Out of scope** (deferred to M3+):
- Web UI implementation
- Serenity research module
- Evidence Agent
- Signal Board
- Admission Gate (distinct from Prototype Gate)
- Real-time data integration
- External broker API

---

## 1. Contracts Stability Review

### Current State

`backend/app/contracts.py` defines 20+ Pydantic models covering:
- Market data (`StockIdentity`, `DailyBar`, `DailyStatus`)
- Strategy input (`StrategyConfig`, `PrototypeGateConfig`)
- Execution artifacts (`Signal`, `Order`, `Trade`, `Position`)
- Backtest output (`BacktestResult`, `BacktestMetrics`, `RoundTrip`)
- Research (reserved: `EvidenceOutput`, `HypothesisDraft`, `ForwardCandidate`)

### Questions for M2

1. **Breaking change policy**: Should M2 freeze contracts for external consumers?
   - If yes: introduce versioning (`StrategyConfigV1`, migration path)
   - If no: continue iterating, but document breaking vs. additive changes

2. **Reserved contracts**: `EvidenceOutput`, `HypothesisDraft`, `ExecutionLog`, `ForwardCandidate` exist but are not used.
   - Keep as placeholders (signals future intent)?
   - Remove until needed (reduce cognitive load)?
   - Move to `contracts_draft.py` (separate stability tier)?

3. **Field optionality**: Some fields are `Optional[X]` but always populated in current code.
   - Example: `Trade.actual_execution_date` is always set by fill simulator.
   - Should we tighten contracts (required fields) or keep loose for future flexibility?

4. **Serialization guarantees**: Current exports use `model_dump()` → JSON.
   - Should M2 define canonical JSON schema files for external tools?
   - Should we support alternate formats (Parquet for trades, CSV for round trips)?

5. **Contract ownership**: Who can modify contracts?
   - `strategy_core` should not import from `backend.app`.
   - Should contracts move to `strategy_core/contracts.py` or a new `contracts/` package?

---

## 2. Export Format Finalization

### Current State

`backend/scripts/export_backtest_result.py` exports:
- `metrics.json` (performance summary)
- `trades.csv` (all trades with cost breakdown)
- `round_trips.csv` (matched buy-sell pairs)
- `equity_curve.csv` (daily portfolio values)
- `order_generation_events.csv` (T+1 audit events)
- `equity_curve.png` + `drawdown_curve.png` (matplotlib charts)

### Questions for M2

1. **Export stability**: Are current CSV column names/order stable?
   - If yes: document column schema, treat as external API
   - If no: mark as experimental, allow changes

2. **PNG charts**: Matplotlib backend currently uses Agg (headless).
   - Should charts be optional (flag-controlled)?
   - Should we generate interactive HTML (Plotly) instead of static PNG?
   - Should chart generation be moved to a separate tool?

3. **Large backtest handling**: Current exports write full trades list.
   - If a strategy produces 10k+ trades, should we:
     - Paginate CSV exports?
     - Add summary-only mode?
     - Compress outputs (gzip)?

4. **Backtest comparison**: `compare_backtests.py` reads `metrics.json` from multiple directories.
   - Should comparison output be part of export contract (e.g., `comparison.json` schema)?
   - Should we support diff view (strategy A vs B parameter changes)?

5. **Audit trail**: T+1 events, rejected orders, partial exits are exported separately.
   - Should these be consolidated into a single `audit_log.jsonl` stream?
   - Should we add timestamps (wall-clock time, not just trade_date)?

---

## 3. Audit Requirements

### Current State

Audit trail currently spans:
- `Trade` records (buy/sell with cost breakdown)
- `RoundTrip` (FIFO matched segments)
- `BacktestResult.rejected_orders` (with rejection reasons)
- `BacktestResult.order_generation_events` (T+1 pre-check events)
- `BacktestMetrics` (win rate, profit factor, T+1 stats)
- `PrototypeGateResult` (failed_checks, warning_checks)

### Questions for M2

1. **Audit completeness**: What questions must be answerable from backtest exports?
   - "Why did this stock not trigger entry signal on date X?"
   - "Why was this sell order rejected?"
   - "Which exit rule triggered for this position?"
   - "How much commission was paid on this round trip?"

2. **Signal audit**: Currently signals are not exported, only orders.
   - Should we export `signals.csv` (all entry/exit/hold signals with reasons)?
   - Pro: full transparency. Con: large files, sensitive to strategy logic exposure.

3. **Replay capability**: Can we reconstruct portfolio state at any date from exports?
   - Currently: partial (trades + equity curve, but not daily positions)
   - Should we export `positions_daily.csv` (symbol, quantity, cost_basis, unrealized_pnl per day)?

4. **Error logs**: Fill simulator rejection reasons are in `rejected_orders`.
   - Should validator errors (unsupported rules) also be exported?
   - Should we log partial capital exhaustion (reduced quantity fills)?

5. **Human-readable summary**: Current `metrics.json` is JSON.
   - Should we generate `backtest_summary.txt` (markdown table for quick review)?
   - Should suite summary include human-readable status (not just JSON)?

---

## 4. Task Execution Boundaries

### Current State

- `strategy_core` is synchronous, deterministic, single-threaded.
- `backend/scripts/run_strategy_suite.py` runs multiple strategies sequentially.
- `backend/app/worker.py` exists but has no real executors (claims task → fails loudly).
- No queue, no parallelism, no progress tracking.

### Questions for M2

1. **Task abstraction**: What is a "task"?
   - Option A: Task = one backtest run (strategy + fixture + date range)
   - Option B: Task = any long-running operation (backtest, evidence, export, comparison)
   - Option C: Task = user-initiated action (create strategy, run suite, generate report)

2. **Execution model**: Should M2 introduce async/parallel execution?
   - Current: scripts run in foreground, block terminal, no progress updates
   - Option A: Keep scripts synchronous, add progress bars (`tqdm`)
   - Option B: Introduce task queue (SQLite-backed), worker polls and executes
   - Option C: Introduce async worker (asyncio), but keep strategy_core sync

3. **Progress tracking**: How should long-running backtests report progress?
   - Current: silent until complete
   - Option A: Log to stdout (date milestones every N days)
   - Option B: Update database row (`tasks.progress_pct`, `tasks.current_step`)
   - Option C: Emit events to separate log stream (e.g., `task_events` table)

4. **Cancellation**: Can a running backtest be stopped?
   - Current: no (Ctrl+C kills script)
   - If yes: introduce checkpoint/resume logic or just abort-and-cleanup

5. **Resource limits**: Should M2 enforce limits?
   - Max concurrent tasks (e.g., 4 backtests in parallel)
   - Max memory per task (detect large strategy universes)
   - Timeout (fail if backtest takes > 5 minutes)

---

## 5. Data Source Interface Contracts

### Current State

Data sources provide:
- `symbols()` → list of tradable symbols
- `get_daily_bars(symbol)` → list of `DailyBar`
- `get_daily_statuses(symbol)` → list of `DailyStatus`
- `get_daily_bar(symbol, date)` → single bar
- `get_daily_status(symbol, date)` → single status
- `get_price(symbol, date)` → float (for `PriceProvider` protocol)

Implementations:
- `GoldenCaseDataSource` (5 stocks, synthetic)
- `FixedFixtureDataSource` (20 stocks, Mock v2.1, with caching)
- `BenchmarkDataSource` (2 indexes, Mock v2.1)

### Questions for M2

1. **Data source versioning**: Should data sources declare schema version?
   - Example: fixture manifest includes `schema_version: "1.0"`, reject mismatches
   - Protects against Parquet column rename or type change

2. **Missing data semantics**: Current behavior is fail-loud (KeyError).
   - Should some missing data be recoverable?
     - Example: missing status → assume not suspended/not limit (degraded mode)
     - Example: missing bar → skip signal generation for that symbol on that date
   - If yes: introduce `DataQualityWarning` and allow strategy to declare tolerance

3. **Data validation**: `validate_fixed_fixture.py` checks OHLC relationships, date continuity.
   - Should validation be mandatory before backtest?
   - Should backtest engine detect data issues mid-run (e.g., OHLC violated on single bar)?

4. **Caching layer**: `FixedFixtureDataSource` caches bars/statuses in memory.
   - Should caching be explicit (opt-in) or transparent?
   - Should cache be shared across multiple strategy runs (in-memory vs. SQLite)?
   - Should cache key include data source version/hash (invalidate on data change)?

5. **Real data preparation**: When M3+ introduces Tushare/AKShare:
   - Should `strategy_core` depend on real data source directly?
   - Or should M2 define `DataWarehouse` abstraction (fetch → store → serve)?
   - Should backtest always run against fixed snapshot (no live data mid-run)?

---

## 6. Success Criteria for M2

M2 is closed when:

1. **Contracts are documented**: Each contract has docstring explaining semantics, required vs. optional fields, and stability tier (stable/draft/reserved).
2. **Export schema is versioned**: JSON/CSV column order is locked, changes are documented as breaking/additive.
3. **Audit trail is complete**: All M1 design questions ("why was this rejected?") are answerable from exports.
4. **Task model is defined**: Clear answer to "what is a task, who creates it, how is it executed, how is progress tracked."
5. **Data source contract is stable**: PriceProvider + data validation + caching semantics are documented.

M2 does **not** require:
- Web UI implementation
- Async/parallel execution (decision can be "defer to M3")
- Real data integration
- Research module contracts

---

## Next Steps

1. **Review this doc**: Identify which questions are M2-critical vs. deferrable.
2. **Make decisions**: Choose options for each question (can be "keep current behavior, document as stable").
3. **Update contracts**: Add docstrings, move reserved contracts if needed.
4. **Lock export schema**: Bump version, write schema docs.
5. **Write M2 closeout criteria**: Specific checklist before declaring M2 complete.

---

## Open Questions Log

Add new questions here as they arise during M2 work:

- (None yet)
