# P4-2 Dashboard Drilldown Consistency - Delivery Report

Status: PASSED

P4-2 verifies that Daily Command Center dashboard counts match their drilldown API counts AND that all drilldown pages display real data or honest empty states in their DOM. Verification includes Playwright browser testing with network log validation.

## Root Cause Fixed

The timeout was not a WSL-only issue and not caused by `/api/strategy-ideas`.

Actual blockers:

- `data/signal_board.db` used an older `planned_signals` schema missing `strategy_revision_id`, `lifecycle_state_at_generation`, and `admission_source`.
- `/api/signals?signal_date=...` filtered on `lifecycle_state_at_generation`, causing HTTP 500 and blocking later drilldown checks.
- Dashboard strategy counts used the wrong mapping artifact type: `strategy_idea_mapping` instead of `strategy_template_mapping`.
- Dashboard rejected count did not use `strategy_idea_rejected` artifacts.
- `/api/strategy-ideas` truncated the list to 50 items while dashboard counted all ideas.

Fixes:

- Added SignalBoardDB schema migration for the missing nullable columns.
- Updated dashboard strategy count aggregation to use real mapping and rejection artifacts.
- Removed the default 50-item truncation from `/api/strategy-ideas`.
- Updated P4-2 verification so signals API failures fail loud instead of being treated as zero.
- Added Playwright DOM verification for all drilldown pages.
- Added network log capture and validation (all requests must be localhost).

## Verification Results

| Check | Result |
| --- | --- |
| `scripts/verify_p4_2_dashboard_drilldown_consistency.py` | exit code 0, run_id `P4_2_RUN_20260708_155833` |
| `scripts/verify_p4_1_daily_command_center.py` | exit code 0, run_id `P4_1_RUN_20260708_160100` |
| `scripts/verify_p3_10_strategy_product_flow_e2e.py` | exit code 0, run_id `P3_10_E2E_20260708_160210` |
| `scripts/verify_p2_runtime_regression.py` | exit code 0, 175.04s |
| `npm run build` from Windows PowerShell repo root `D:\Codex\TraderLens` | exit code 0, 35.9s |

## Dashboard API Counts

Latest dashboard counts:

- as_of_date: `2026-07-08`
- open_observations.count: `30`
- today_signals.count: `0`
- strategy_workspace.ideas_count: `72`
- strategy_workspace.candidates_count: `15`
- strategy_workspace.rejected_count: `71`
- strategy_workspace.validations_count: `0`
- strategy_workspace.approved_strategies_count: `0`
- strategy_workspace.templates_count: `4`
- recent_reviews.count: `0`

## Drilldown API Validation

Validated drilldowns:

- `/api/observations?status=open`: `30` ✓
- `/api/signals?signal_date=2026-07-08`: `0` ✓
- `/api/strategy-ideas`: `72` ✓
- `/api/strategy-ideas?candidate_status=candidate_unapproved`: `15` ✓
- rejected from strategy ideas API: `71` ✓
- `/api/strategy-validations`: `0` ✓
- `/api/strategies`: `0` ✓
- `/api/strategy-templates`: `4` ✓

All API counts match.

## DOM Verification

Verified pages with Playwright:

- `/` - Dashboard page shows real observation counts and navigation links ✓
- `/observations` - Shows real observation data (603002.SH) ✓
- `/signals` - Shows real empty state ("没有找到符合条件的信号") ✓
- `/strategy-ideas` - Shows real strategy idea data ✓
- `/candidate-strategies` - Shows real candidate data ✓
- `/rejected-strategies` - Shows real rejected data ✓
- `/strategy-validations` - Shows real empty state (count=0) ✓
- `/strategies` - Shows real empty state (count=0) ✓
- `/strategy-templates` - Shows real template data (theme_momentum) ✓

All DOM checks passed (10/10).

## Network Log Validation

- Total network requests: `90`
- API requests (fetch/xhr): `28`
  - Backend (localhost:8010): `20`
  - Frontend (localhost:3000): `8`
- External API requests: `0` ✓

All API requests point to localhost. No external API calls.

## Evidence Files

API evidence:

- `docs/verification/p4-2-dashboard-api.json`
- `docs/verification/p4-2-observations-api.json`
- `docs/verification/p4-2-signals-api.json`
- `docs/verification/p4-2-strategy-ideas-api.json`
- `docs/verification/p4-2-candidates-api.json`
- `docs/verification/p4-2-validations-api.json`
- `docs/verification/p4-2-strategies-api.json`
- `docs/verification/p4-2-templates-api.json`

DOM evidence:

- `docs/verification/p4-2-dashboard-dom.md`
- `docs/verification/p4-2-observations-dom.md`
- `docs/verification/p4-2-signals-dom.md`
- `docs/verification/p4-2-strategy-ideas-dom.md`
- `docs/verification/p4-2-candidates-dom.md`
- `docs/verification/p4-2-rejected-dom.md`
- `docs/verification/p4-2-validations-dom.md`
- `docs/verification/p4-2-strategies-dom.md`
- `docs/verification/p4-2-templates-dom.md`

Network log:

- `docs/verification/p4-2-dashboard-drilldown-network-log.json`

Summary:

- `docs/verification/p4-2-verification-summary.json`
- `docs/verification/p4-2-frontend-log.txt`
- `docs/verification/p4-1-evidence-summary.json`
- `docs/verification/p3-10-evidence-summary.json`
- `docs/verification/p2-runtime-regression-summary.json`

## Red Lines

- No fake count.
- No fake DOM or network evidence.
- No API-only downgrade for P4-1/P3/P2 browser gates.
- No direct DB insert as business flow.
- No fake strategy, validation, or signal.
- No risk guard, capital guard, or market regime work.
- No runtime_process_helpers change.
- No WSL build timeout treated as success.

## Git

- Agent delivery commit: see repository HEAD after this report commit.
- Git status at delivery: clean after commit.
