# Documentation Index

This index intentionally excludes Signal Board process docs and milestone closeout notes.

## Latest Verification

- `verification/B4_VERIFICATION.md` - B4 event-driven backtest verification. B4 is correctness/future-data protection only; it is not profitability proof, B5 OOS, Gate pass, promotion, Signal Board output, or live trading readiness.
- `verification/B3_VERIFICATION.md` - B3 point-in-time data protocol verification.
- `verification/B2_VERIFICATION.md` - B2 hypothesis builder verification.

## Read First

1. `../README.md`
2. `../HANDOFF_PROMPT.md` - Latest handoff (Phase 4: Production entry enabled)
3. `../status.md` ⭐ **UPDATED: Serenity 双阶段生产入口启用（896 tests）**
4. `design/MVP-V1-Design.md`
5. `design/QUICK-REFERENCE.md`

## Phase Documentation

Historical phase plans, reports, and handoffs:
- `phases/SERENITY_REFACTOR_PLAN_PHASE3.md` - Phase 3: Two-phase refactor plan
- `phases/SERENITY_REFACTOR_SUMMARY_PHASE3.md` - Phase 3: Refactor summary
- `phases/A_MODULE_PLAN.md` - A Module (Selection Research) plan
- `phases/WORK_REPORT_2026-06-25.md` - Work report

## Research Module (NEW - 2026-06-23)

**Product Entry Point**: `/themes`

The research module is the upstream candidate-selection workflow:

- Theme creation and management
- Manual stock input or Serenity candidate generation
- Hard filters (ST, suspended, liquidity)
- Evidence light-check (support/falsify/conflict)
- Human confirmation into forward-only pool
- Conversation interface with pending action workflow
- Board-version optimistic concurrency control

**Key Principle**: AI proposes, human applies. Board is the only source of truth.

**Components**:
- `contracts/research.py` - Data models
- `backend/db/research.py` - SQLite persistence
- `backend/services/research_action_reducer.py` - State machine
- `backend/services/research_conversation.py` - Conversation service
- `backend/services/serenity_stub.py` - Serenity runner (stub)
- `backend/services/evidence_light.py` - Evidence runner (light-check)
- `backend/api/research.py` - API routes
- `frontend/app/themes/` - Frontend pages
- `frontend/lib/research-api-client.ts` - API client

**Tests**: 59 tests in `tests/test_research*.py`

## Core Product Design

- `design/MVP-V1-Design.md` - complete product chain and module definitions
- `design/QUICK-REFERENCE.md` - concise chain, boundaries, and page list
- `design/SUMMARY.md` - design document summary
- `design/README.md` - design folder guide

## Candidate Selection / Research Chain

- `design/Part2-Evidence-Agent.md` - Evidence Agent design
- `design/Part2-3-Hypothesis-Builder.md` - Hypothesis Builder design
- `design/Part4-Data-Web.md` - data adapter and web page design
- `design/Part5-Milestones.md` - intended implementation path

## Strategy And Data Foundation

- `design/Part3-Strategy-Core.md` - strategy_core, DSL, and backtest design
- `contracts/M2-CONTRACTS.md` - stable contract policy
- `contracts/DATA-SOURCE-CONTRACT.md` - data source contract
- `contracts/TASK-EXECUTION-CONTRACT.md` - task execution contract
- `contracts/CSV-SCHEMA.md` - export schema

## Current Backlog

- `DEFERRED-BACKLOG.md` - deferred items and revisiting criteria

## Historical Context

- `design/M2-BOUNDARY-DISCUSSION.md`
- `design/M3-BOUNDARY-DISCUSSION.md`
- `design/M3-PLANNING.md`
- `architecture/ARCHITECTURE.md`

These are secondary. Prefer the core product design files above when deciding what to build next.
