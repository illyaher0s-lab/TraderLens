# P7-2 Browser Demo A: Friend Stock Full E2E

## Status

PASSED.

This closeout records the P7 Browser Demo A run from 2026-07-09. It verifies the user-facing flow from dashboard and Workbench through observation, manual buy, daily signal attempt, manual sell, P&L, and discipline review.

## Verification Results

- Run ID: `P7_2_RUN_20260709_184333`
- P7-2 exit code: `0`
- npm build exit code: `0`
- P7-1 regression exit code: `0`
- Network requests: `46`
- External requests: `0`

## Entity Chain

- Stock: `600519.SH` / `贵州茅台`
- Observation position ID: `pos_fbf2e4ecf025`
- Closed buy position ID: `pos_9f5b1c5417b4`
- P&L: `10000.0`
- Review ID: `review_afe9055a69bb`
- Signal ID: `null`

The two position IDs are expected to differ in the current product flow:

- `pos_fbf2e4ecf025` is the friend-stock observation record created by the Workbench two-step "加入观察" flow.
- `pos_9f5b1c5417b4` is the separate manual-buy position created from the Workbench buy message and then closed by the Workbench sell message.
- Both records are tied to the same run ID and stock. The closed position entry thesis contains `P7_2_RUN_20260709_184333`, symbol `600519.SH`, entry price `1500`, quantity `100`, and closed_at is populated.

This proves the browser demo chain, but it also documents a product behavior: observation and manual-buy currently create separate position records rather than converting one observation record into a held position.

## Flow Results

- Dashboard loaded and DOM evidence was captured.
- Friend stock was added to observations through real Workbench browser input.
- Manual buy created an open position through real Workbench browser input.
- Daily signal API call succeeded; no signal was generated because the data state was not ok in this runtime.
- Manual sell closed the manual-buy position through real Workbench browser input.
- P&L and discipline review were verified in `live_trade.db` because the observations API does not expose review details.

## Sell Blocker Resolution

The earlier P7-2 blocker was caused by message format mismatch, not missing close-position business logic.

- Parser-compatible sell message: `已卖出 600519 贵州茅台 100股，成交价 1600，备注 P7_2_RUN_20260709_184333`
- The Workbench sell handler closed `pos_9f5b1c5417b4`.
- Discipline review was generated as `review_afe9055a69bb`.

No direct DB insert or fake close was used.

## Evidence Files

- `docs/verification/p7-2-dashboard-dom.md`
- `docs/verification/p7-2-observations-dom.md`
- `docs/verification/p7-2-network-log.json`
- `docs/verification/p7-2-verification-summary.json`
- `docs/verification/p7-2-backend-log.txt`
- `docs/verification/p7-2-frontend-log.txt`

Regression evidence updated by the closeout run:

- `docs/verification/p7-1-api-evidence.json`
- `docs/verification/p7-1-candidate-dom.md`
- `docs/verification/p7-1-dashboard-dom.md`
- `docs/verification/p7-1-network-log.json`
- `docs/verification/p7-1-observations-dom.md`
- `docs/verification/p7-1-rejected-dom.md`
- `docs/verification/p7-1-strategies-dom.md`
- `docs/verification/p7-1-strategy-ideas-dom.md`
- `docs/verification/p7-1-summary.json`
- `docs/verification/p7-1-verification-summary.json`
- `docs/verification/p7-1-workbench-friend-dom.md`
- `docs/verification/p7-1-workbench-strategy-dom.md`
- `docs/verification/p2-1d-backend-log.txt`
- `docs/verification/p2-1d-db-path-check.json`

## Closeout

- The report no longer claims `P7-2 ACCEPTED` while the worktree is dirty.
- Final git status is checked after the closeout evidence commit.
- The final commit hash is reported by `git rev-parse --short HEAD` in the closeout response.
