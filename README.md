# TraderLens

A-share research, candidate selection, strategy validation, and action-planning workspace.

## Current Reality

**Product Entry Point**: `/themes` (Research Module)

**Latest verification milestone**: B4 Event-Driven Backtest Verification is complete. See [docs/verification/B4_VERIFICATION.md](docs/verification/B4_VERIFICATION.md).

B4 is an offline backtest correctness layer. It does not prove profitability, does not run B5 OOS, does not pass Gate, does not promote to `prototype_passed`, and does not make the system live-trading ready.

The full product chain is:

```text
Theme input (manual / market scan)
  -> Serenity industry-chain bottleneck analysis
  -> data validation + hard filters
  -> Evidence Agent evidence and falsification
  -> human confirmation
  -> confirmed_candidate_pool (forward-only)
  -> Hypothesis Builder (future)
  -> strategy_core
  -> prototype backtest
  -> Signal Board / Action Plan
```

**Implemented**:
- ✅ Research Module (Theme input → Serenity → Evidence → Confirmation)
- ✅ Signal Board (Strategy signals → Human review)
- ✅ Data Layer (Frozen snapshots + Tushare integration)
- ✅ Strategy Core (Signal generation, no auto-execution)

**What the Research Module does**:
- Create research themes
- Add manual stocks or run Serenity to find candidates
- Run hard filters (ST, suspended, low liquidity)
- Run Evidence light-check (support/falsify/conflict evidence)
- Confirm candidates into forward-only pool
- Conversation interface with pending action workflow
- Board as single source of truth (AI proposes, human applies)

**What it cannot do**:
- Trading decisions or buy/sell recommendations
- Strategy ranking
- Automatic broker execution
- Agent-driven state mutation

## Important Documents

**Core documents (read first)**:
1. [AGENTS.md](AGENTS.md) - Development rules
2. [status.md](status.md) - Current status and verification baseline
3. [HANDOFF_PROMPT.md](HANDOFF_PROMPT.md) - Latest handoff
4. [docs/verification/B4_VERIFICATION.md](docs/verification/B4_VERIFICATION.md) - B4 accepted commits, guarantees, boundaries, and test record

**Phase documentation**:
- [docs/phases/](docs/phases/) - Historical phase plans and reports

**Design documents**:
- [docs/design/MVP-V1-Design.md](docs/design/MVP-V1-Design.md)
- [docs/design/QUICK-REFERENCE.md](docs/design/QUICK-REFERENCE.md)
- [docs/design/Part2-Evidence-Agent.md](docs/design/Part2-Evidence-Agent.md)
- [docs/design/Part2-3-Hypothesis-Builder.md](docs/design/Part2-3-Hypothesis-Builder.md)
- [docs/design/Part4-Data-Web.md](docs/design/Part4-Data-Web.md)
- [docs/design/Part5-Milestones.md](docs/design/Part5-Milestones.md)
- [docs/contracts/](docs/contracts/) - API contracts

## Development Commands

```powershell
# Frontend type check
node_modules\.bin\tsc.cmd -p frontend --noEmit

# Python tests
.venv\Scripts\python.exe -m pytest tests/ -x --tb=short -q
```

## Constraints

- Do not turn research output into buy/sell recommendations.
- Do not let LLMs generate trading signals, calculate PnL, or decide execution.
- Evidence can affect candidate pools, not entry/exit signal rules.
- `strategy_core` remains the deterministic execution layer.
- Signal Board is not the product entry point; it is the downstream action-plan surface.
