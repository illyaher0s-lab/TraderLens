# INFRA-VERIFY-RUNTIME-STARTUP-STABILITY

Status: PASSED
Verified at: 2026-07-07 14:56 Asia/Shanghai

## Root Cause

1. Backend startup path had to use `backend.app.main:app`.
2. `GET /api/strategy-ideas` queried artifact `content` but later read `artifact_id`.
3. Runtime scripts had duplicated port cleanup and startup logic.
4. `Popen.pid` is not always the listener PID on Windows. Backend and frontend listeners can be child processes.
5. Frontend shutdown could leave the Next.js node process on port 3000.

## Changes

1. `scripts/runtime_process_helpers.py`
   - Added shared backend/frontend startup helpers.
   - Uses PowerShell `Get-NetTCPConnection` for precise port owner lookup.
   - Validates listener ownership against the started process tree.
   - Releases exact listener PIDs instead of killing all Python or Node processes.
   - Stops processes and verifies ports are released.

2. `scripts/verify_p3_2_strategy_result_visibility.py`
   - Uses `runtime_process_helpers` for port cleanup, backend startup, frontend startup, and shutdown.
   - Keeps real `workflow_route_decision` DB verification.

3. `scripts/verify_p3_3_strategy_rejection_registry.py`
   - Uses `runtime_process_helpers` for port cleanup, backend startup, frontend startup, and shutdown.
   - Uses the same real `workflow_route_decision` verification as P3-2.
   - Sets deterministic/stub runtime env for backend verification.
   - Replaced non-ASCII status output that broke Windows console encoding.

4. `backend/api/strategy_ideas.py`
   - `list_ideas()` extraction and mapping queries include `artifact_id`.

5. `tests/test_runtime_process_helper_usage.py`
   - Guards against P3 runtime verifiers reintroducing local port/startup helpers.

## Verification

| Check | Result |
| --- | --- |
| `python -m pytest tests/test_runtime_process_helper_usage.py tests/test_p3_2_verification_script.py -q` | exit code 0, 3 passed |
| `python -m py_compile scripts/runtime_process_helpers.py scripts/verify_p3_2_strategy_result_visibility.py scripts/verify_p3_3_strategy_rejection_registry.py` | exit code 0 |
| `python scripts/verify_p3_2_strategy_result_visibility.py` | exit code 0, run_id `P2RUN_20260707_144944` |
| `python scripts/verify_p3_2_strategy_result_visibility.py` | exit code 0, run_id `P2RUN_20260707_145527` |
| `python scripts/verify_p3_3_strategy_rejection_registry.py` | exit code 0, run_id `P2RUN_20260707_144812` |
| `python scripts/verify_p3_1_strategy_idea_runtime_loop.py` | exit code 0, run_id `P2RUN_20260707_145108` |
| `python scripts/verify_p2_runtime_regression.py` | exit code 0, duration 163.32s |
| `npm run build` from repository root | exit code 0 |

## Runtime Evidence

P3-2 latest:
- run_id: `P2RUN_20260707_145527`
- conversation_id: `sess_f909c4298bad`
- idea_id: `idea_61a5bb49707c`
- workflow_type: `strategy_idea`
- route_decision.workflow_kind: `strategy_idea`
- decision: `rejected`

P3-3 latest:
- run_id: `P2RUN_20260707_144812`
- conversation_id: `sess_38871adaea83`
- idea_id: `idea_1f3c8e0e4b43`
- workflow_type: `strategy_idea`
- route_decision.workflow_kind: `strategy_idea`
- decision: `rejected`
- rejection_reason: `no_approved_template`
- mapping_artifact_id: `mapping_2dfbe7e7dedc`

P2 regression latest:
- P2-1A: `P2RUN_20260707_145147`
- P2-1B: `P2RUN_20260707_145238`
- P2-1C: `P2RUN_20260707_145311`
- P2-1D: `P2RUN_20260707_145353`

## Evidence Files

- `docs/verification/p3-2-evidence-summary.json`
- `docs/verification/p3-2-workbench-network-log.json`
- `docs/verification/p3-2-result-network-log.json`
- `docs/verification/p3-2-result-dom.md`
- `docs/verification/p3-3-evidence-summary.json`
- `docs/verification/p3-3-workbench-network-log.json`
- `docs/verification/p3-3-detail-network-log.json`
- `docs/verification/p3-3-rejected-registry-network-log.json`
- `docs/verification/p3-3-detail-dom.md`
- `docs/verification/p3-3-rejected-registry-dom.md`
- `docs/verification/p3-1-evidence-summary.json`
- `docs/verification/p2-runtime-regression-summary.json`

## Final Judgment

INFRA startup stability is accepted for P3 runtime verification.

P3-2 and P3-3 now use the shared process helper. Backend and frontend startup verify real port ownership. Frontend shutdown no longer relies on parent process termination only; it releases the actual listener on port 3000.

