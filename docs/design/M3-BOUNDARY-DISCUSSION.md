# M3 Boundary Discussion

**Status**: LOCKED  
**Last Updated**: 2026-06-22  
**Prerequisites**: M2 CLOSED ✅ (299 tests pass)

---

## Context

M2 delivered stable contracts, frozen DataSource Protocol, and working backtest engine. However, the system still relies on mock/fixture data. M3 must enable real A-share historical data backtest execution to validate strategy_core on real scenarios and provide foundation for future Evidence/Signal Board features.

**M2 Achievement**:
- 299 tests pass (baseline)
- 25 stable contracts + 11 draft contracts
- CSV schema locked (4 files)
- DataSource Protocol frozen (8 methods, fail-loud)
- TaskRecord state machine documented

**M3 Direction**: Real Data Integration First

---

## IN SCOPE (M3 Must Deliver)

### Primary: Real Data Integration

**Goal**: Enable backtest execution on frozen real A-share historical data.

**Deliverables**:
1. **TushareDataSource** or **AKShareDataSource** implementation
   - Implements all 8 DataSource Protocol methods
   - Provides: daily bars, fundamentals, universe metadata, snapshot hash
   - Fail-loud on missing data or API errors
   - Returns `is_frozen=True` snapshots only

2. **Frozen Snapshot Generation**
   - Download real data → save as Parquet snapshot
   - Include: source, updated_at, snapshot_hash, is_frozen
   - Snapshot metadata embedded in Parquet schema
   - Snapshot validation (detect corruption, missing fields)

3. **Real Backtest Execution**
   - strategy_core consumes real data snapshot
   - At least 1 real stock pool strategy runs full backtest
   - Export to CSV (M2 format, 4 files)
   - Backtest reproducibility verified (same snapshot → same result)

4. **Smoke Tests for Real Data**
   - Tests use frozen small sample (10 stocks × 30 days)
   - No live API calls during test execution
   - Validates: data loading, schema compliance, snapshot hash

### Secondary: Basic Evidence light_check Skeleton

**Goal**: Establish Evidence module structure without full implementation.

**Deliverables**:
1. **EvidenceTask contract** (draft)
   - Fields: task_id, hypothesis, check_type, params, output
   - States: pending, running, completed, failed

2. **light_check implementation** (basic only)
   - Identity verification (company name, stock code)
   - Announcement keyword search (ST, delisting, fraud)
   - Basic financials (debt ratio, ROE, revenue growth)
   - ST/suspension/liquidity check

3. **EvidenceOutput contract** (draft)
   - Structured output: pass/fail/warning, reason, evidence_items
   - No LLM interpretation (just structured data)

4. **Evidence does NOT**:
   - Participate in entry/exit signals
   - Compute PnL or Gate logic
   - Call LLM for judgment (only rule-based checks)
   - Block backtest execution (only log warnings)

---

## DEFERRED (M4+)

**Explicitly NOT in M3**:

1. **Complete Evidence deep_check**
   - LLM-based company analysis
   - Cross-source evidence synthesis
   - Complex reasoning workflows

2. **Serenity Task Type**
   - Industry chain bottleneck mapping
   - Thesis generation from macro trends

3. **Signal Board**
   - Live signal monitoring UI
   - Real-time alert system

4. **Async Task Queue**
   - Background worker process
   - Task dependencies and retry logic
   - Progress streaming (WebSocket)

5. **Live Execution / Broker Integration**
   - Real-time data feeds
   - Order placement
   - Position tracking

**Rationale**: M3 focuses on data foundation. These features require stable real data pipeline first.

---

## OUT OF SCOPE (Never)

**Hard Boundaries** (will never be in scope):

1. **LLM Signals / PnL / Gate Logic**
   - LLM never computes entry/exit signals
   - LLM never calculates profit/loss
   - LLM never decides position sizing

2. **Real-time Data for Backtest**
   - Backtest ONLY reads frozen snapshots
   - No API calls during backtest execution
   - Deterministic replay required

3. **Stock Recommendations**
   - System outputs testable hypotheses, not buy/sell advice
   - Evidence provides research support, not predictions

**Rationale**: Core design principle — LLM for research, not trading logic.

---

## M3 Constraints (Inherited from M2)

### Must Preserve

1. **M2 Contracts Stability**
   - 25 stable contracts remain unchanged
   - No breaking changes to contract fields/types
   - CSV schema locked (column order fixed)

2. **DataSource Protocol Frozen**
   - 8 methods remain unchanged
   - fail-loud behavior required
   - `is_frozen=True` for all snapshots

3. **TaskRecord Schema Stable**
   - State machine unchanged (5 states)
   - 16 fields remain backward compatible

4. **Test Suite Green**
   - All 299 M2 tests must pass
   - M3 adds tests, does not break existing

### Can Extend

1. **New Contracts**
   - Add EvidenceTask, EvidenceOutput (draft status OK)
   - Add data source specific contracts (TushareConfig, etc.)

2. **New Task Types**
   - Add evidence task type (light_check only)

3. **New Data Sources**
   - Add TushareDataSource, AKShareDataSource
   - Implement DataSource Protocol (8 methods)

4. **New Tests**
   - Real data smoke tests
   - Evidence light_check tests
   - Snapshot validation tests

### Cannot Break

1. **M2 Test Suite**
   - 299 tests → M3 baseline
   - Green status required before M3 close

2. **M2 Documentation**
   - Remains accurate
   - M3 additive only (no contradiction)

3. **Backward Compatibility**
   - M2 exports remain readable
   - M2 snapshots remain loadable

---

## M3 Success Criteria

### Acceptance Tests

- [ ] **Real Data Adapter**
  - TushareDataSource or AKShareDataSource implemented
  - All 8 DataSource Protocol methods working
  - Implements `get_metadata()`, returns `is_frozen=True`
  - Deterministic hash for snapshots

- [ ] **Frozen Snapshot**
  - Can generate Parquet snapshot from real data
  - Snapshot includes: source, updated_at, snapshot_hash, is_frozen
  - Snapshot validation detects corruption

- [ ] **Real Backtest Execution**
  - At least 1 real stock pool strategy completes backtest
  - Consumes frozen snapshot (no live API calls)
  - Exports to CSV (M2 format, 4 files)
  - Reproducible (same snapshot → same CSV output)

- [ ] **Basic Evidence light_check**
  - EvidenceTask contract defined (draft)
  - light_check implements 4 basic checks (identity, announcement, financials, ST/liquidity)
  - Outputs structured EvidenceOutput (pass/fail/warning + reason)
  - Does NOT participate in signals or PnL

- [ ] **Test Suite**
  - All M2 tests pass (299 → M3 baseline)
  - New smoke tests for real data (frozen sample)
  - New tests for Evidence light_check
  - No degradation in M2 test coverage

- [ ] **Documentation**
  - M3 scope doc written
  - Real data integration guide
  - Evidence light_check usage guide
  - M3 closeout report (like M2)

---

## M3 Execution Phases

### M3.1 Real Data Adapter

**Goal**: Implement data source adapter for Tushare or AKShare.

**Tasks**:
1. Choose data provider (Tushare vs AKShare)
   - API stability comparison
   - Data coverage comparison
   - Rate limit analysis

2. Implement DataSource Protocol (8 methods)
   - `get_daily_bars(symbols, start, end)`
   - `get_fundamentals(symbols, date)`
   - `get_universe(category, date)`
   - `get_adjustments(symbols, start, end)`
   - `get_metadata()`
   - `validate_snapshot()`
   - `export_snapshot(path)`
   - `load_snapshot(path)`

3. Unit tests for adapter
   - Mock API responses
   - Test all 8 methods
   - Test error handling (API down, missing data)

**Deliverable**: Working data adapter with tests.

---

### M3.2 Frozen Snapshot + Validation

**Goal**: Generate and validate frozen data snapshots.

**Tasks**:
1. Snapshot generation script
   - Download data from API
   - Save as Parquet with metadata
   - Compute snapshot hash (deterministic)

2. Snapshot validation
   - Check schema compliance
   - Detect missing fields
   - Verify hash integrity

3. Snapshot metadata
   - source: "tushare" or "akshare"
   - updated_at: ISO timestamp
   - snapshot_hash: SHA256 of content
   - is_frozen: True

4. Smoke test data
   - 10 stocks × 30 days sample
   - Include edge cases (ST, suspension, split)
   - Frozen sample for CI tests

**Deliverable**: Script to generate snapshots + validation logic + frozen smoke test data.

---

### M3.3 Real Backtest Closeout

**Goal**: Run full backtest on real data and validate reproducibility.

**Tasks**:
1. Select 1 real stock pool strategy
   - Simple logic (e.g., momentum, value)
   - Testable on 1-year historical data

2. Run backtest on frozen snapshot
   - Load snapshot (no API calls)
   - Execute strategy_core
   - Export to CSV (M2 format)

3. Verify reproducibility
   - Run backtest twice
   - Compare CSV outputs (identical hash)

4. Document results
   - Backtest summary (trades, PnL, stats)
   - Snapshot metadata
   - Execution time

**Deliverable**: Real backtest execution verified + reproducibility proof.

---

### M3.4 Basic Evidence light_check

**Goal**: Implement basic Evidence checks without LLM.

**Tasks**:
1. Define EvidenceTask contract (draft)
   - Fields: task_id, hypothesis, check_type, params, output
   - States: pending, running, completed, failed

2. Define EvidenceOutput contract (draft)
   - pass/fail/warning
   - reason (string)
   - evidence_items (list of structured facts)

3. Implement 4 basic checks
   - Identity: verify company name matches stock code
   - Announcement: search for keywords (ST, delisting, fraud)
   - Financials: check debt ratio, ROE, revenue growth thresholds
   - ST/liquidity: check status flags, trading volume

4. Integration test
   - Run light_check on 10 stocks
   - Verify structured output
   - Confirm no LLM calls

**Deliverable**: Basic Evidence module + light_check tests.

---

## M3 Risks and Mitigations

### Risk 1: API Rate Limits

**Risk**: Tushare/AKShare may throttle requests during snapshot generation.

**Mitigation**:
- Use frozen snapshot for tests (no live API calls during CI)
- Implement exponential backoff for API retries
- Cache API responses locally
- Document rate limit constraints

### Risk 2: Data Quality Issues

**Risk**: Real data may contain errors (missing bars, wrong prices, outliers).

**Mitigation**:
- Fail-loud on missing data (no silent fallback)
- Snapshot validation (schema check, range check)
- Log data quality warnings
- Document known data issues

### Risk 3: Storage and Caching Complexity

**Risk**: Large snapshots may cause storage/memory issues.

**Mitigation**:
- Use Parquet compression
- Document storage requirements
- Provide snapshot pruning script (keep last N versions)
- Test memory usage with large snapshots

### Risk 4: Evidence Scope Creep

**Risk**: Basic Evidence may expand beyond light_check.

**Mitigation**:
- Strict contract: light_check only (no deep_check in M3)
- No LLM calls in M3 Evidence code
- Explicitly defer deep_check to M4
- Code review for scope violations

---

## M3 Timeline Estimate

**Total Effort**: ~3-4 weeks (assumes 1 developer, part-time)

- M3.1 Real Data Adapter: 1 week
- M3.2 Frozen Snapshot + Validation: 1 week
- M3.3 Real Backtest Closeout: 3-5 days
- M3.4 Basic Evidence light_check: 3-5 days

**Milestone Checkpoints**:
- Week 1: Data adapter working, tests pass
- Week 2: Snapshot generation + validation working
- Week 3: Real backtest complete + reproducible
- Week 4: Basic Evidence working, M3 closeout

---

## M3 Decision Locks

**Locked Decisions** (cannot change during M3):

1. **M3 focuses on Real Data Integration**
   - No async queue
   - No Signal Board
   - No complete Evidence deep_check

2. **M3 uses frozen snapshots only**
   - No real-time data during backtest
   - Deterministic replay required

3. **M3 Evidence is light_check only**
   - No LLM calls
   - Rule-based checks only
   - No signal participation

4. **M3 preserves M2 contracts**
   - No breaking changes
   - 299 tests must pass

**Open Decisions** (can decide during M3):

1. **Data provider choice** (Tushare vs AKShare)
   - Defer decision to M3.1 execution
   - Document comparison in M3.1

2. **Snapshot storage format** (Parquet vs other)
   - Prefer Parquet (columnar, compressed)
   - Can change if technical issues arise

3. **Evidence check priorities** (which 4 checks first)
   - Identity, announcement, financials, ST/liquidity (suggested)
   - Can adjust based on data availability

---

## M3 Out of Scope Justification

### Why NOT Async Queue in M3?

**Reason**: Web UI not ready, no immediate value.

- Async queue provides value when UI needs responsiveness
- M3 backtest is CLI-based (blocking is acceptable)
- Defer to M4 when Web UI is ready

### Why NOT Complete Evidence in M3?

**Reason**: LLM integration is complex and risky.

- light_check provides 80% value with 20% effort
- deep_check requires LLM workflow design
- M3 establishes Evidence contract, M4 expands

### Why NOT Signal Board in M3?

**Reason**: Depends on real data pipeline and Web UI.

- Signal Board requires live data (M3 is backtest only)
- UI complexity not justified before real data works
- Defer to M4 after M3 data pipeline stable

### Why NOT Serenity in M3?

**Reason**: Serenity is research automation, not data infrastructure.

- M3 focuses on data foundation
- Serenity depends on stable Evidence and data pipeline
- Defer to M4 after Evidence is proven

---

## M3 Success Definition

**M3 is successful if**:

1. A user can download real A-share data snapshot
2. A user can run a real strategy backtest on frozen snapshot
3. Backtest is reproducible (same input → same output)
4. Basic Evidence light_check provides structured research support
5. All M2 tests continue to pass (299 → M3 baseline)
6. M3 documentation is complete and accurate

**M3 is NOT successful if**:

1. Real data requires manual intervention (must be scriptable)
2. Backtest is non-deterministic (random results)
3. Evidence calls LLM or participates in signals
4. M2 contracts are broken (test failures)
5. Data quality issues are hidden (must fail-loud)

---

## Next Steps

1. **Review and Approve M3 Boundary** ✅ (this doc)
2. **Write M3-SCOPE.md** (lock commitment)
3. **Start M3.1 Execution** (Real Data Adapter)
4. **Weekly progress checkpoints** (track against timeline)
5. **M3 Closeout Report** (like M2, document lessons learned)

---

## Approval

**M3 Boundary Approved**: [Pending user confirmation]

**Date**: 2026-06-22

**Approver**: Illya (TraderLens owner)

---

**M2 is CLOSED. M3 Boundary is LOCKED. Execution begins after approval.**
