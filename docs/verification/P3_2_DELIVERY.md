# P3-2 Strategy Idea Result Visibility Delivery

Date: 2026-07-07

Status: PASSED after reviewer fix

Verified implementation/evidence commit: `b8b540d`

## Scope

P3-2 makes strategy idea results visible and traceable after the Workbench runtime loop:

- Workbench browser input creates a strategy idea.
- Result APIs expose the idea, extraction, mapping, rejection, and workflow type.
- `/strategy-ideas?conversation_id=...` displays the result in real DOM.
- Verification now checks the real persisted `workflow_route_decision`, not a fallback.

## Fixes Made

1. `npm run build` failure fixed by wrapping `useSearchParams()` in a Suspense boundary in `frontend/app/strategy-ideas/page.tsx`.
2. `GET /api/strategy-ideas` and `GET /api/strategy-ideas/{idea_id}` now return `workflow_type: "strategy_idea"`.
3. `scripts/verify_p3_2_strategy_result_visibility.py` now:
   - verifies `response.workflow_type == "strategy_idea"`;
   - reads `route_decision.workflow_kind` from the real `workflow_route_decision` artifact;
   - fails if that artifact or `workflow_kind` is missing;
   - verifies detail/list API `workflow_type`;
   - captures result page network log as `p3-2-result-network-log.json`;
   - verifies all result page API calls use `localhost:8010`;
   - releases only the process IDs occupying ports 8010/3000.
4. Added regression tests in `tests/test_p3_2_verification_script.py` proving the verifier rejects missing real route decision evidence.

## P3-2 Runtime Acceptance

Command:

```powershell
.venv\Scripts\python.exe scripts\verify_p3_2_strategy_result_visibility.py
```

Exit code: `0`

Run details:

- run_id: `P2RUN_20260707_125840`
- conversation_id: `sess_a60685802896`
- idea_id: `idea_e80224c378e4`
- route_decision.workflow_kind: `strategy_idea`
- response.workflow_type: `strategy_idea`
- detail API workflow_type: `strategy_idea`
- list API workflow_type: `strategy_idea`
- decision: `rejected`
- rejection_reason: `no_approved_template`
- mapping artifact: `mapping_e84803f54849`
- mapped_template_id: `null`
- result page path: `/strategy-ideas?conversation_id=sess_a60685802896`

## Regression Results

`npm run build`

- exit code: `0`

`.venv\Scripts\python.exe -m pytest tests\test_p3_2_verification_script.py -q`

- exit code: `0`
- result: `2 passed`

`.venv\Scripts\python.exe scripts\verify_p3_1_strategy_idea_runtime_loop.py`

- exit code: `0`
- run_id: `P2RUN_20260707_125944`

`.venv\Scripts\python.exe scripts\verify_p2_runtime_regression.py`

- exit code: `0`
- duration: `183.28s`
- P2-1A run_id: `P2RUN_20260707_130030`
- P2-1B run_id: `P2RUN_20260707_130116`
- P2-1C run_id: `P2RUN_20260707_130201`
- P2-1D run_id: `P2RUN_20260707_130247`

## Evidence Files

- `docs/verification/p3-2-workbench-dom.md`
- `docs/verification/p3-2-workbench-response.json`
- `docs/verification/p3-2-workbench-network-log.json`
- `docs/verification/p3-2-result-api-detail.json`
- `docs/verification/p3-2-result-api-list.json`
- `docs/verification/p3-2-result-dom.md`
- `docs/verification/p3-2-result-network-log.json`
- `docs/verification/p3-2-backend-log.txt`
- `docs/verification/p3-2-frontend-log.txt`
- `docs/verification/p3-2-evidence-summary.json`
- `docs/verification/p3-1-evidence-summary.json`
- `docs/verification/p2-runtime-regression-summary.json`

## Red Line Checks

- No fixture evidence used as a browser/runtime substitute.
- No fake DOM: DOM evidence is read with Playwright.
- No fake network log: Workbench and result page logs are captured by Playwright response listeners.
- No API-only acceptance: `/workbench` and `/strategy-ideas` are opened in a real browser.
- No direct DB insert to create the business result.
- No fake accept/reject: no approved template produces honest `rejected`.
- `workflow_type == route_decision.workflow_kind == "strategy_idea"` is verified from persisted route decision evidence.

## Git

Verified implementation/evidence commit: `b8b540d`

Expected final check after committing this report:

```powershell
git status --short
git rev-parse --short HEAD
```
