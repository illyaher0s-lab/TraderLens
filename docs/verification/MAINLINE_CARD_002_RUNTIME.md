# TraderLens Mainline Card 002 — Verification

**MAINLINE STAGE:** 阶段1｜成交记录 · **TASK CARD:** 002  
**Budget:** 2 used / 20; 18 remain. Historical work was not charged.

## Journey

- **USER JOURNEY STEP:** 5 — 人工成交记录路径
- **BEFORE:** 页面写入研究库并生成无来源的计划 ID；Workbench 成交意图能写另一套交易库；今日信号使用入场价加 5% 伪行情。
- **AFTER:** 页面买卖记录写入持仓、成交与复盘读者共用的 `LiveTradeDB`。Workbench 成交意图只提示在页面登记。无真实行情时不生成信号。
- **NEW USER CAPABILITY:** 登记已完成的买卖，服务重启后仍可在观察池回读；未关联计划的记录会明确标示。只有买卖两侧手续费均已知时才显示净盈亏。
- **NEXT BLOCKER:** 持仓监控仍缺少可验证的实时行情源。

## Verification

- RED/GREEN: card002 focused tests先以旧行为失败；最终 `tests/test_card002_manual_trade_ledger.py` **8 passed**。
- Backend syntax/import: touched Python modules compiled; `create_research_app` import smoke reported **36 routes**。
- Frontend: `npm run build` exit code **0**，含 TypeScript 类型检查。
- Existing ledger migration: test保留旧成交、持仓、复盘行，并将新增手工记录所需的计划关联列改为可空。

## Five acceptance groups

- **A — Canonical ledger:** `LiveTradeDB` is the holdings, observation, and discipline-review store used by the existing direct readers; page writes now use the same path.
- **B — Page persistence/idempotency:** The final-code UI run recorded buy and sell operations, retried a committed buy after a backend restart, and returned the persisted operation without adding another log or position. Separate identical trades with different operation IDs remain distinct in focused tests.
- **C — Provenance/fees:** Autonomous records carry no plan IDs and are labeled unlinked. Unknown buy/sell fees leave net P&L null with `fees` listed as missing; explicit zero fees produce numeric net P&L. Executed-trade warnings and a required user confirmation remain on the page.
- **D — Fake quote removal:** With an open position, `/daily-signal` returned `market_data_unavailable`, created no signal, and the page stated that no signal was generated without a verifiable quote.
- **E — Agent write guard:** Focused tests exercised trade-intent messages in both new and existing Workbench sessions; both returned the page-recording instruction and left log, position, and review counts at zero. The final-code UI run also showed that reply and the isolated ledger contained only the page-recorded buy/sell events.

## Isolated UI run

The browser run below was repeated against the final source after restoring the pre-card checkpoint and re-applying the authorized changes. It used deterministic local services, no broker, model, market-data call, or credentials. All test symbols were visibly labeled `TEST-*` / “合成验收”. The SQLite file is outside the project and is test-only:

`C:\Users\LEGION\AppData\Local\Temp\traderlens-card002-ui-final-20261007\isolated-live-trade.db`

- The UI submitted a synthetic buy. A test-only middleware discarded the first successful response after the ledger commit. After restarting the backend against the same isolated database, retrying in the unchanged form returned the saved buy. The ledger still had one log and one position, confirming the same operation ID was reused.
- After restart, `/observations` showed the closed synthetic position. It was marked `autonomous_manual`, with no action-plan ID.
- UI buy and sell with unknown fees displayed “手续费：未知”; the saved review had `pnl_amount: null`, `fees: null`, `missing_fields: ["fees"]`, and undetermined plan adherence.
- UI buy and sell with explicit `0` fees displayed net P&L `+200.00` (`+20.00%`); the review stored `fees: 0.0`.
- A trade-intent chat reply said “暂不支持，请在页面记录”; no additional trade row was created.
- With an open position and no quote, the page returned “当前没有可验证的实时行情，暂不生成持仓信号”; the signals table remained empty.

Final isolated database contents: 4 synthetic execution logs, 2 closed autonomous positions, 2 reviews, 0 daily signals. No plan IDs were created.
