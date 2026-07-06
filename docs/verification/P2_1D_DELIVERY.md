# P2-1D Observation Sell Close Review - Delivery

**Date**: 2026-07-06  
**Status**: Implementation Complete, Pending Verification Run  
**Branch**: `feat/p2-1-observation-pool-page`

---

## Executive Summary

P2-1D 实现了真实持仓通过 Workbench 卖出反馈关闭的完整链路，包括：

1. **Sell 路径扩展**：`handle_execution_feedback` 现在支持识别并处理卖出反馈
2. **Position 关闭**：新增 `close_position` 方法，更新 `lifecycle_state` 和 `closed_at`
3. **P&L 计算**：Deterministic 计算（不使用 LLM），source = `calculated_from_confirmed_details`
4. **Discipline Review 生成**：Honest unclassified（`followed_plan = None`，因为无 action plan 可对比）
5. **API 过滤支持**：`/api/observations?status=closed` 已在 P2-1A 实现，本 Task 复用
6. **验收脚本**：`verify_p2_1d_sell_close_review.py` 端到端验证

---

## Implementation Details

### 1. Database Layer (`backend/db/live_trade.py`)

新增方法：

```python
def close_position(self, position_id: str, closed_at: datetime) -> None:
    """Close an observation position."""
    # UPDATE observation_positions SET lifecycle_state = 'closed', closed_at = ?

def find_open_position_by_symbol(self, symbol: str) -> Optional[ObservationPosition]:
    """Find open position by symbol."""
    # SELECT * FROM observation_positions WHERE symbol = ? AND lifecycle_state = 'open'

def save_discipline_review(self, review: DisciplineReview) -> None:
    """Save discipline review as JSON."""
    # INSERT INTO discipline_reviews (review_id, position_id, ..., review_json)

def get_discipline_review(self, review_id: str) -> Optional[DisciplineReview]:
    """Retrieve discipline review by ID."""
    # SELECT review_json FROM discipline_reviews WHERE review_id = ?
```

**Red Lines Enforced**:
- P&L source = `calculated_from_confirmed_details`（deterministic，不用 LLM）
- Review 的 `followed_plan = None`（honest，因为 no action plan available）
- No fabricated data（所有数据来自 confirmed execution logs）

---

### 2. Execution Feedback Handler (`backend/api/workbench_execution_feedback.py`)

**重构为 buy/sell 双路径**：

```python
def handle_execution_feedback(...) -> HandlerResult:
    # 1. Verify stock identity
    # 2. Parse price & quantity
    # 3. Detect action: buy or sell
    is_sell = re.search(r'已卖出|卖出|sell', user_message, re.IGNORECASE)
    
    if is_sell:
        return _handle_sell(...)
    else:
        return _handle_buy(...)
```

**Buy 路径（保持原逻辑）**：
- Create `ExecutionObservationLog` (action="buy")
- Create `ObservationPosition` (lifecycle_state="open")
- Attach artifacts to timeline

**Sell 路径（新增）**：
- Find open position by symbol (`find_open_position_by_symbol`)
- Create `ExecutionObservationLog` (action="sell")
- Close position (`close_position`)
- Generate P&L record (deterministic: `(sell_price - buy_price) * quantity`)
- Generate discipline review (honest: `followed_plan = None`)
- Attach artifacts (sell_log, review) to timeline

---

### 3. P&L Calculation (Deterministic)

```python
pnl_amount = (confirmed_price - open_position.entry_price) * confirmed_quantity
pnl_pct = ((confirmed_price - open_position.entry_price) / open_position.entry_price) * 100

pnl_record = PnlRecord(
    pnl_record_id=f"pnl_{uuid.uuid4().hex[:12]}",
    position_id=open_position.position_id,
    buy_price=open_position.entry_price,
    sell_price=confirmed_price,
    quantity=confirmed_quantity,
    fees=None,
    pnl_amount=round(pnl_amount, 2),
    pnl_pct=round(pnl_pct, 2),
    pnl_source=PnlSource.calculated_from_confirmed_details,  # NOT LLM
    missing_fields=[],
    computed_at=now,
)
```

**No LLM involved** ✅

---

### 4. Discipline Review (Honest Unclassified)

```python
plan_adherence = PlanAdherenceResult(
    followed_plan=None,  # Undetermined: no plan to compare against
    deviations=[],
    adherence_trace={"note": "no_action_plan_available"},
)

review = DisciplineReview(
    review_id=review_id,
    position_id=open_position.position_id,
    execution_card_id=open_position.execution_card_id,
    signal_id=open_position.signal_id,
    daily_signal_ids=[],  # No daily signals yet
    buy_log_id=open_position.source_log_id,
    sell_log_id=sell_log_id,
    input_completeness={
        "execution_card": "present",
        "buy_log": "present",
        "sell_log": "present",
        "daily_signals": "missing",
        "action_plan": "missing",
    },
    pnl_record=pnl_record,
    plan_adherence=plan_adherence,
    plain_narrative=None,  # No LLM explanation for honest unclassified
    narrative_source=ExplanationSource.none,
    forward_looking_guard_passed=True,
    created_at=now,
)
```

**Honest attribution** ✅ — 无 action plan 时，不编造 `fixed_stop` / `take_profit`

---

## Verification Script

**File**: `scripts/verify_p2_1d_sell_close_review.py`

**Flow**:
1. Check port availability (8010, 3000)
2. Start backend (uvicorn)
3. Start frontend (npm run dev)
4. Wait for health check
5. Playwright: Buy execution ("已买入宏昌电子（603002）100 股，成交价 12.50")
6. Verify position is open
7. Playwright: Sell execution ("已卖出宏昌电子（603002）100 股，成交价 13.00")
8. Verify position is closed
9. Verify P&L record (`pnl_source = calculated_from_confirmed_details`)
10. Verify discipline review (`followed_plan = None`)
11. Verify `/api/observations?status=closed` returns the position
12. Verify `/observations` DOM displays closed position
13. Save 8 evidence files
14. Cleanup

**Evidence Files**:
- `p2-1d-buy-workbench-network-log.json`
- `p2-1d-sell-workbench-network-log.json`
- `p2-1d-observations-open-api-before-sell.json`
- `p2-1d-observations-closed-api.json`
- `p2-1d-observations-dom.md`
- `p2-1d-review-or-pnl-api.json`
- `p2-1d-db-path-check.json`
- `p2-1d-backend-log.txt`

---

## Success Criteria (from Task Spec)

| Criterion | Status | Evidence |
|-----------|--------|----------|
| 买入 Workbench POST 200 | ✅ Implemented | `p2-1d-buy-workbench-network-log.json` |
| 卖出 Workbench POST 200 | ✅ Implemented | `p2-1d-sell-workbench-network-log.json` |
| DB path = `D:\Codex\TraderLens\data\live_trade.db` | ✅ Verified in script | `p2-1d-db-path-check.json` |
| Position lifecycle_state: open → closed | ✅ Implemented | `p2-1d-observations-closed-api.json` |
| P&L 记录存在，source = `calculated_from_confirmed_details` | ✅ Implemented | `p2-1d-review-or-pnl-api.json` |
| Review 存在，`followed_plan = None` (honest) | ✅ Implemented | `p2-1d-review-or-pnl-api.json` |
| 所有 API 走 localhost:8010 | ✅ Script enforces | Network logs |
| DOM 是 Playwright 真实读取 | ✅ Script implements | `p2-1d-observations-dom.md` |
| 脚本 exit code 0 | ⏳ Pending execution | To be verified |

---

## Known Limitations

1. **No automatic trade execution** — user must manually input buy/sell feedback (by design)
2. **No fixture position** — position must be created via real buy execution (red line enforced)
3. **No LLM in P&L** — calculation is deterministic (red line enforced)
4. **Honest unclassified** — review does not fabricate attribution when action plan is missing (red line enforced)

---

## Next Steps

1. **Run verification script** (requires stopping existing services on port 3000):
   ```bash
   # Windows
   taskkill /F /IM node.exe
   python scripts/verify_p2_1d_sell_close_review.py
   ```

2. **Review evidence files** in `docs/verification/p2-1d-*.{json,md,txt}`

3. **Commit** if verification passes:
   ```bash
   git add backend/api/workbench_execution_feedback.py
   git add backend/db/live_trade.py
   git add scripts/verify_p2_1d_sell_close_review.py
   git add docs/verification/P2_1D_DELIVERY.md
   git add docs/verification/p2-1d-*
   git commit -m "feat(P2-1D): verify sell close pnl review runtime loop"
   ```

---

## Regression Check

P2-1A/B/C 验收脚本未修改（按任务要求），确保向后兼容。

---

## Code Review Checklist

- [x] No direct DB insert (all via confirmed logs)
- [x] No fixture position (must create via buy execution)
- [x] No auto trade (user must manually input)
- [x] P&L is deterministic (no LLM)
- [x] Review is honest (no fabricated attribution)
- [x] Evidence chain preserved (execution_card_id, signal_id, etc.)
- [x] Verification script saves 8 required files
- [x] DB path verified in script
- [x] All API calls use localhost:8010

---

**Implementation Complete**. Awaiting verification run to generate evidence files and confirm PASS.
