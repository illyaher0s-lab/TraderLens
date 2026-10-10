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

## Current Product Mainline

**当前整体产品路线**按单标的研究、实际成交记录、持仓复盘、策略验证、有限发现和整体验收分阶段推进，见 [TraderLens_MAINLINE_PLAN.md](TraderLens_MAINLINE_PLAN.md)。Replay-001 已归入[历史计划归档](docs/archive/2026-10-07/TraderLens_PRODUCT_MAINLINE_PLAN.md)。用户确认的未来策略目标仍保存在归档版“未来策略目标与 Discovery 预算”一节，未来 Discovery 前须重审并冻结。

Gate001 remains a historical research record with saved verdict `insufficient_evidence`. The final report review covered historical display and offline economic reconciliation; a separate independent supplemental audit passed the main scenario's seven trade legs and account reconciliation. The original capture status remains preserved, and three exit signal contexts are derived from persisted orders. See [Gate001 protocol and closeout](TraderLens_MAINLINE_ALPHA_PLAN.md), [final research report](docs/verification/GATE001_FINAL_RESEARCH_REPORT.md), [supplemental saved-capture audit](docs/verification/GATE001_SAVED_CAPTURE_AUDIT.json), and [trial/exposure ledger](docs/verification/GATE001_TRIALS.jsonl).

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
1. [TraderLens_Northstar.md](TraderLens_Northstar.md) - Long-term direction and boundaries
2. [TraderLens_MAINLINE_PLAN.md](TraderLens_MAINLINE_PLAN.md) - Current overall route
3. [AGENTS.md](AGENTS.md) - Project execution rules
4. [docs/verification/B4_VERIFICATION.md](docs/verification/B4_VERIFICATION.md) - Historical B4 verification, guarantees, boundaries, and test record
5. [docs/phases/HANDOFF_B4.md](docs/phases/HANDOFF_B4.md) - Historical B4 handoff context
6. [status.md](status.md) - 2026-06-27 B4 historical baseline; not current application acceptance

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
