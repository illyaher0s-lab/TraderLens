# TraderLens V1 Release Notes

## Verdict

✅ **V1 PASSED**

Final acceptance commit: `2a895b5`

## What This Release Is

A-share strategy research and execution decision workspace. User talks to Agent about friend-recommended stocks or short-video strategies. Agent researches, extracts, maps to templates, rejects/approves honestly. User reviews signals, makes manual execution decisions, records P&L and discipline.

**Not automatic trading. Not profit guarantee. Approved strategy library empty by design.**

## Runtime

- Backend: `localhost:8010`
- Frontend: `localhost:3010`
- DB: `backend/database/live_trade.db`, `backend/database/strategy_brain.db`

## What Was Verified

### Demo A: Friend Stock Full E2E (P7-2)

Dashboard → Workbench → Observation → Manual Buy → Daily Signal → Manual Sell → P&L + Review

- Run ID: `P7_2_RUN_20260709_184333`
- Position closed: `pos_9f5b1c5417b4`
- P&L: `10000.0`
- Review: `review_afe9055a69bb`

### Demo B: Strategy Full E2E (P7-3)

Dashboard → Workbench → Strategy Idea → Extraction → Template Mapping → Rejection

- Run ID: `P7_3_RUN_20260709_192733`
- Idea: `idea_3a980db86a0b`
- Decision: `rejected` (no template fit, honest)
- Approved count: `0`

### Boundary & UI Smoke (P7-4)

10 pages checked, all boundary tests passed, no external requests.

## Known Limitations (Acceptable V1)

1. **Approved strategy library empty:** 4 approved templates exist, but no approved strategies
2. **Risk guard display-only:** `not_configured` state
3. **Daily signal may be null:** When `data_state != ok`
4. **Observation ≠ position:** Friend stock and manual buy create separate records
5. **No automatic trading:** All execution manual
6. **Template mapping rejects common patterns:** Short-video strategies don't match existing templates (honest rejection)

## Explicit Non-Goals

- Automatic trading
- Profit guarantee
- Risk elimination
- Strategy auto-approval
- Direct market access

## Evidence

See [V1_FINAL_PRODUCT_ACCEPTANCE.md](./V1_FINAL_PRODUCT_ACCEPTANCE.md) for full evidence index (31 files).
