# Task 4 V3 AI Technical Review

**Decision:** approved for owner authorization
**Reviewer:** `ai_reviewer_openai_codex_gpt5`
**Reviewer kind:** `ai_technical_reviewer`
**Review date:** 2026-08-04
**Scope:** Task 4 only; no parameter changes and no new strategy.

## Exact Frozen Identity

- Template ID: `relative_strength_rotation_shsz_sw2021_v3`
- Version: `v3_shsz_sw2021_pit_12m_liquidity20d`
- Template hash: `f7c0fd8123f62f37118cb947e1735861374435f8707e01b06d788a8ec4df39c1`
- Data requirements hash: `ef2ab5b1dafe4349f305b52733a7dcb018a2961464dfbc6542a10e34805d041d`

## Reviewed Contract

The review confirms the existing frozen payload contains the relative-strength rules, SH/SZ scope, PIT SW2021 universe, 252-trading-day lookback, next executable day, 3-day confirmation, fixed exits, and the complete liquidity contract:

- Algorithm: `avg_amount_20d_shsz_common_v1`
- Window: 20 completed SH/SZ common trading days before execution day
- Execution day excluded
- Source: `daily.amount`
- Source unit: thousand yuan; multiplier 1000
- Suspension evidence: `suspend_d`; suspended-day amount is 0
- Minimum history: 20 trading days
- Partial mean and window extension: forbidden
- Missing data: `data_fault`

No threshold, holding period, ranking rule, or other strategy parameter was changed.

## Data and Artifact Boundary

The bounded lifecycle successor `49b09326f35936c6` was independently verified for Task 4 lifecycle binding. It is explicitly vendor evidence, not an official-source claim. It is not itself a B6/OOS/Gate/Promotion/Signal authorization.

This review does not claim B3 readiness, OOS validity, promotion, signal, profitability, or trading advice.
