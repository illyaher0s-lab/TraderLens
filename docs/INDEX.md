# Documentation Index

This index intentionally excludes Signal Board process docs and milestone closeout notes.

## Historical Verification (not current product acceptance)

- `verification/B4_VERIFICATION.md` - Historical B4 event-driven backtest verification. B4 is correctness/future-data protection only; it is not profitability proof, B5 OOS, Gate pass, promotion, current app acceptance, or live trading readiness.
- `../status.md` - 2026-06-27 B4 historical baseline; does not represent current application acceptance.
- `verification/B3_VERIFICATION.md` - B3 point-in-time data protocol verification.
- `verification/B2_VERIFICATION.md` - B2 hypothesis builder verification.

## Current Product Mainline and Gate001 History

- `../TraderLens_MAINLINE_PLAN.md` - current overall six-stage product route.
- `BACKLOG.md` - current pending work and verification boundaries.
- `DEFERRED-BACKLOG.md` is supplemental; `BACKLOG.md` remains the authority for current pending work.
- `superpowers/plans/2026-10-20-card018-strategy-validation-results.md` - Card 018 frozen scope and owner acceptance status.
- `verification/2026-10-24-knowledge-closeout.md` - dated evidence boundaries, workspace inventory coverage, and recovery/cleanup preview; current status remains in the mainline plan.
- `archive/2026-10-07/TraderLens_PRODUCT_MAINLINE_PLAN.md` - archived Replay-001 topic; confirmed future strategy targets remain in its future-goals section.
- `verification/GATE001_FINAL_RESEARCH_REPORT.md` - historical saved `insufficient_evidence` result; independent acceptance is limited to historical display and offline economic reconciliation, not current strategy or product acceptance.
- `verification/GATE001_SAVED_CAPTURE_AUDIT.json` - independently accepted supplemental audit for the primary scenario's seven trade legs and account reconciliation; three exit contexts are derived from persisted orders, and the original capture history remains intact.
- `verification/GATE001_TRIALS.jsonl` - Gate001 attempt ledger and recorded Holdout-exposure event; that event does not change research counters.

## Read First

1. `../TraderLens_Northstar.md`
2. `../TraderLens_MAINLINE_PLAN.md`
3. `../AGENTS.md`
4. `../README.md`

## Phase Documentation

Historical phase plans, reports, and handoffs:
- `phases/SERENITY_REFACTOR_PLAN_PHASE3.md` - Phase 3: Two-phase refactor plan
- `phases/SERENITY_REFACTOR_SUMMARY_PHASE3.md` - Phase 3: Refactor summary
- `phases/A_MODULE_PLAN.md` - A Module (Selection Research) plan
- `phases/WORK_REPORT_2026-06-25.md` - Work report

## Current Web Routes in Source

These paths describe routes present in the current source tree; route presence alone does not establish runtime readiness or owner acceptance.

- `/` and `/#research` - today page and single-stock/ETF research (`../frontend/app/page.tsx`).
- `/trades/record` - record-trade page (`../frontend/app/trades/record/page.tsx`).
- `/observations` - holdings and observations page (`../frontend/app/observations/page.tsx`).
- `/research` and `/research/[research_id]` - research list and detail routes.
- `/strategy-validations` - Card 018's read-only Card 017 historical-results view was owner-accepted on 2026-10-21 in commit `bf0f6c2062f3ac7187b6aef7fe630c8f419620ad` on an independent branch; it is not merged into the default branch and grants no strategy qualification.
- `/themes` remains as an older theme route; it is not the current navigation entry.
- `/workbench` remains in source but is hidden from navigation pending Agent dual-entry acceptance.

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

- `BACKLOG.md` - authoritative current pending work and verification boundaries.
- `DEFERRED-BACKLOG.md` - supplementary deferred items and revisit criteria; it does not replace the current backlog.

## Historical Context

- `design/M2-BOUNDARY-DISCUSSION.md`
- `design/M3-BOUNDARY-DISCUSSION.md`
- `design/M3-PLANNING.md`
- `architecture/ARCHITECTURE.md`

These are secondary. Historical design files are implementation references only; current decisions follow Northstar, the overall mainline, and the active phase task card.
