# TraderLens Status

**Last Updated**: 2026-06-27 CST  
**Current Milestone**: B4 Event-Driven Backtest Verification complete

## Current B4 Verification State

B4 is complete as an offline backtest correctness and future-data guard layer.

**Accepted verification record**: [docs/verification/B4_VERIFICATION.md](docs/verification/B4_VERIFICATION.md)

**Accepted commits**:
- B3 prerequisite: `1cfec6b`
- B4 Task 1-4: `d63e94c`
- B4 Task 5: `3db8196`
- B4 Task 6: `1aa3057`
- B4 Task 7: `f7eb491`
- B4 Task 8: `e8d4ced`
- B4 Task 9: `b105dac`
- B4 Task 10: `5854bfc`
- B4 Task 11: `7c17fca`

**Verification baseline**:
- B4 combined suite: 131 tests passing
- Full pytest: 1198 passed, 2 skipped, 3 warnings, 24 subtests passed

**B4 does NOT**:
- Prove strategy profitability
- Run B5 OOS validation
- Pass Gate or promote to `prototype_passed`
- Enable Signal Board output
- Make the system live-trading ready

Formal B4 qualification must use `run_qualification_with_b3_protocol()`. Legacy `run_qualification()` remains only for Task 4 Canary compatibility.

---

## Architecture Overview

### A Module: Selection Research (Serenity + Evidence)

**Status**: ✅ Production Ready (Phase 4 双阶段生产入口已启用)

- Serenity Agent: Supply chain decomposition → candidate discovery
  - 双阶段架构（2 次 LLM 调用，确定性执行器）
  - Tool-use whitelisted research tools
  - Verification trust chain enforced
  - Real data context maintained
- Evidence Agent: Candidate evidence gathering and classification
  - Hard-filter snapshot integration
  - Verification ID traceability
  - Multi-source evidence aggregation

**Entry**: `/themes` (Theme Board)  
**Output**: Candidate shortlist → Evidence analysis → Confirmed candidates

### B Module: Strategy Design (Hypothesis Builder)

**Status**: ✅ Implemented (B2 verified)

- Entry criteria GUI
- Exit criteria GUI
- Position sizing selector
- Deterministic validator with 12+ rejection rules
- Bounded repair loop (max 2 attempts)

**Entry**: `/strategies/new`  
**Output**: Immutable strategy config (StrategyConfig)

### C Module: Strategy Validation (Backtest Runner)

**Status**: ✅ B4 Verified (Event-driven backtest + future-data guard)

- B4 event-driven backtest engine with time cursor
- A-share execution constraints (T+1, limit up/down, suspension, slippage, liquidity)
- Rolling normalization guard
- Adjustment snapshot guard
- Delisting & liquidation policy
- B3 protocol integration (frozen snapshot + PIT universe)

**Entry**: `/strategies/:id/backtest`  
**Output**: EventBacktestResult (order intents, fills, violations, read trace)

### Frontend

**Status**: ✅ Production Ready

- React 18 + TypeScript
- TanStack Router v1 + Query
- Jotai for client state
- Tailwind CSS + shadcn/ui

---

## Test Commands

```powershell
# B4 combined suite
.venv\Scripts\python.exe -m unittest tests.test_b4_time_cursor tests.test_b4_future_data_guard tests.test_b4_canary_qualification tests.test_b4_event_backtest_loop tests.test_b4_ashare_fill_constraints tests.test_b4_normalization_guard tests.test_b4_adjustment_snapshot tests.test_b4_delisting_liquidation tests.test_b4_b3_integration tests.test_b4_compatibility -v

# Full test suite
.venv\Scripts\python.exe -m pytest tests/ -x --tb=short -q

# Frontend type check
node_modules\.bin\tsc.cmd -p frontend --noEmit
```

**Last verified**: 2026-06-27 CST
- B4 combined: 131 tests OK
- Full pytest: 1198 passed, 2 skipped
- Frontend type check: 0 errors

---

## Known Limitations

1. **No Version Control**: Strategy changes overwrite in place
2. **No Multi-User**: Single-user local app (no auth layer)
3. **Fixed Backtest Period**: Configured per strategy, not hard-coded to 1 year
4. **Manual Theme Creation**: No automated market scanning

---

## Next Steps

**B5: OOS Validation & Gate Logic** (out of B4 scope):
- Sample split enforcement (in-sample vs out-of-sample)
- OOS budget tracking (prevent over-fitting)
- Formal Gate evaluation (`PrototypeGateResult` with verdict)
- Strategy promotion to `prototype_passed`

See [docs/verification/B4_VERIFICATION.md](docs/verification/B4_VERIFICATION.md) Section 9 for full list of future work.

---

## Development Setup

### Prerequisites

- Python 3.11+
- Node.js 18+
- Tushare Pro account (for real data)

### Quick Start

```powershell
# Backend
cd D:\Codex\TraderLens
.venv\Scripts\activate
python -m backend.main

# Frontend
cd frontend
npm install
npm run dev
```

---

**Milestone**: B4 Event-Driven Backtest Verification complete ✅  
**Date**: 2026-06-27 CST
