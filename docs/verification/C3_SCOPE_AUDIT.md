# C3-1 Signal Board Scope Audit and Implementation Boundary

**Purpose:** Record what Signal Board already has, what C3 must not repeat, and minimal C3 file plan.

**Audit Date:** 2026-06-28

**Status:** READY_FOR_REVIEW

---

## 1. Files Read

### Planning and verification docs
- `docs/superpowers/plans/2026-06-29-c3-action-plan-human-execution-boundary.md`
- `docs/verification/C0_VERIFICATION.md`
- `docs/verification/C1_VERIFICATION.md`
- `docs/verification/C2_VERIFICATION.md`

### Backend implementation
- `backend/api/signal_board.py`
- `backend/db/signal_board.py`
- `contracts/signal_board.py`

### Frontend implementation
- `frontend/lib/api-client.ts`
- `frontend/app/signals/page.tsx`
- `frontend/app/signals/[signal_id]/page.tsx`

### Test files
- `tests/test_signal_api.py`
- `tests/test_c2_signal_board_decision_boundary.py`
- `tests/test_signal_board_ux_polish.py`

---

## 2. Keywords Searched

Searched for existing Action Plan implementation:
- `action_plan` / `ActionPlan`: Found only in C3 planning doc and one legacy reference in `contracts/draft.py:172` (unrelated generator field)
- `execution` / `order` / `fill`: Found 107 files (mostly B-module backtest/fill_simulator and strategy_core, no C3 Action Plan)

**Finding:** No existing Action Plan contract, service, API, or database implementation exists in backend or frontend.

---

## 3. What Signal Board Already Has

### 3.1 Existing Pages
- **List page**: `frontend/app/signals/page.tsx`
  - Filters (date, status, direction, strategy)
  - Pagination (limit/offset)
  - Strategy selector
  - Quick review buttons

- **Detail page**: `frontend/app/signals/[signal_id]/page.tsx`
  - Signal metadata display
  - Review status update form
  - C2 disclaimer copy

### 3.2 Existing API Endpoints
From `backend/api/signal_board.py`:
- `GET /api/signals` - List signals with filters
- `GET /api/signals/summary` - Summary statistics
- `GET /api/signals/strategies` - Strategy list
- `GET /api/signals/{signal_id}` - Single signal detail (enforces admission via `get_admitted_signal()`)
- `POST /api/signals/{signal_id}/review` - Update review status (enforces admission)
- `POST /api/signals/batch-review` - Batch review (enforces admission)

### 3.3 Existing Review Statuses
From `contracts/signal_board.py`:
- `pending`
- `ignored`
- `watching`
- `expired`

### 3.4 Admission Enforcement
- C0: `generate_planned_signals.py` enforces `prototype_passed` at generation
- C1: `SignalBoardDB.list_signals()` filters by `lifecycle_state_at_generation == "prototype_passed"` (no audit mode exposed to public API)
- C2: Direct detail lookup uses `get_admitted_signal()` (lines 204, 245, 268, 316 in signal_board.py)
- C2: Review endpoints block unadmitted signals (404)

### 3.5 C2 Copy Boundaries
From `tests/test_c2_signal_board_decision_boundary.py` and `tests/test_signal_board_ux_polish.py`:

**Required phrases:**
- 不是买卖建议
- 不会自动交易
- 仅显示已通过验证的计划信号

**Forbidden phrases:**
- 保证盈利, 稳定盈利, 实盘可用
- 立即买入, 立即卖出, 推荐买入, 推荐卖出
- 一键下单, 最佳策略, 策略排名
- 支持自动交易, 开启自动交易, 自动交易已启用, 一键自动交易, 可自动交易, 自动执行交易

**Exception:** `不会自动交易` is required disclaimer text (not forbidden)

### 3.6 Frontend Type
From `frontend/lib/api-client.ts` (C1/C2):
- `PlannedSignal` includes admission metadata:
  - `strategy_revision_id: string | null`
  - `lifecycle_state_at_generation: string | null`
  - `admission_source: string | null`

---

## 4. What C3 Must Not Repeat

C3 must not:
- Rebuild Signal Board list/detail pages
- Redesign filters or pagination
- Add charts or real-time refresh
- Regenerate signals (signals already exist via `generate_planned_signals.py`)
- Change B3/B4/B5/B6 validation logic
- Loosen C0/C1/C2 admission gates
- Add broker API integration
- Add order/fill/execution records (belongs to C4 Execution Log)
- Add live trading
- Add strategy ranking
- Introduce profit claims or buy/sell recommendation language

---

## 5. C3 Minimal Implementation Plan

### 5.1 New Contracts
**Create:** `contracts/action_plan.py`

Models:
- `ActionPlan` - main deterministic plan from admitted signal
- `ActionCheck` - pre-action and invalidation checks
- `UserActionDecision` - human decision record (execute/skip/partial/expired)
- `ActionPlanDecisionRequest` - POST request body

### 5.2 New Service
**Create:** `backend/services/action_plan_builder.py`

Implements:
- Deterministic ActionPlan builder from `PlannedSignal`
- Freshness rules (fresh/stale/expired)
- Blocking rules (lifecycle_state != prototype_passed, evidence blocked, expired)
- Warning rules (risk_flags, stale, missing price/quantity)
- Pre-action checks (6 checks)
- Invalidation checks (4 checks)
- No LLM, no external data, no broker fields

### 5.3 Backend API
**Modify:** `backend/api/signal_board.py`

Add endpoints:
- `GET /api/signals/{signal_id}/action-plan` - Generate/fetch ActionPlan (must call `get_admitted_signal()` first)
- `POST /api/signals/{signal_id}/action-plan/decision` - Record user decision (must call `get_admitted_signal()` first, require reason for skip/partial/expired)

**Modify:** `backend/db/signal_board.py`

Add table (if persistence needed):
- `action_plan_decisions` - stores latest user decision per signal

### 5.4 Frontend
**Modify:** `frontend/lib/api-client.ts`

Add:
- `ActionPlan`, `ActionCheck`, `UserActionDecision` types
- `getActionPlan(signalId)` function
- `submitActionDecision(signalId, request)` function

**Modify:** `frontend/app/signals/[signal_id]/page.tsx`

Add panel:
- "人工处理计划" section
- Pre-action checks display
- Invalidation checks display
- Risk warnings display
- Decision buttons: 准备执行, 部分执行, 今日放弃, 标记过期
- Reason input field (required for skip/partial/expired)
- Disclaimer: "这是人工处理计划，不是买卖建议，不会自动交易。"

**Optional:** `frontend/components/ActionPlanPanel.tsx` (if cleaner)

### 5.5 Tests
**Create:** `tests/test_c3_action_plan_boundary.py`

Required tests:
1. `test_get_action_plan_requires_admitted_signal` - 404 for unadmitted
2. `test_get_action_plan_for_admitted_signal_returns_checks` - 200 with checks
3. `test_action_plan_blocks_expired_signal` - expired cannot execute
4. `test_action_decision_skip_requires_reason` - 400 if reason missing
5. `test_action_decision_partial_requires_reason` - 400 if reason missing
6. `test_action_decision_does_not_accept_order_fields` - reject/ignore order_id/broker/fill fields
7. `test_action_decision_updates_review_status_mapping` - execute→watching, skip→ignored, etc.
8. `test_action_plan_decision_rejects_unadmitted_direct_id` - POST cannot update unadmitted
9. `test_batch_or_mutation_bypass_not_introduced` - assert no batch action-plan endpoint exists

**Create:** `tests/test_c3_action_plan_copy_boundary.py`

Check:
- Required phrases: 人工处理计划, 不是买卖建议, 不会自动交易
- Forbidden phrases: 推荐买入, 推荐卖出, 立即买入, 立即卖出, 一键下单, 自动执行, 保证盈利, 稳定盈利, 实盘可用, 目标价, 最佳策略, 策略排名
- Do not forbid: 不会自动交易 (required disclaimer)

---

## 6. Files C3 Must Not Touch

Protected files (read-only for C3):
- `backend/services/c_admission_gate.py` (C0)
- `backend/db/strategy.py` (B-module)
- `contracts/strategy.py` (B-module frozen contracts)
- `backend/scripts/generate_planned_signals.py` (C0 entry point, already enforces admission)
- `backend/services/strategy_promotion_reducer.py` (B6)
- All B3/B4/B5/B6 validation files

If C3 must modify any protected file, escalate as scope violation.

---

## 7. C3 Reusable Pieces

From existing Signal Board:
- Reuse detail page structure (`frontend/app/signals/[signal_id]/page.tsx`) - add panel, do not replace
- Reuse admission enforcement pattern (`get_admitted_signal()` at API boundary)
- Reuse existing review_status mapping (execute→watching, skip→ignored, expired→expired)
- Reuse C2 copy boundary tests pattern for C3 copy tests
- Reuse existing `PlannedSignal` contract - ActionPlan builder takes it as input

Do not create:
- New top-level page (add panel to existing detail page)
- New batch endpoints (unless justified, and must enforce admission)
- New review status values beyond existing 4 (use decision mapping)

---

## 8. Forbidden Scope Check

C3 must not introduce:
- ❌ broker API calls
- ❌ order/fill/execution records (belongs to C4)
- ❌ live price fetching
- ❌ LLM-generated trade advice
- ❌ automatic trading
- ❌ profit guarantees or live-trading claims
- ❌ buy/sell recommendation language (use neutral: 入场/离场/处理/放弃)
- ❌ strategy ranking or best-strategy claims
- ❌ "目标价" or other price prediction language
- ❌ loosening C0/C1/C2 admission boundaries

C3 must include:
- ✅ Deterministic rule-based Action Plan builder
- ✅ Admission enforcement on all Action Plan endpoints
- ✅ Neutral user-facing copy (人工处理计划, not 买卖建议)
- ✅ Disclaimer: 不是买卖建议, 不会自动交易
- ✅ Reason required for skip/partial/expired decisions
- ✅ Tests blocking unadmitted direct-id mutation
- ✅ Tests blocking order/broker field introduction

---

## 9. Git Status

```powershell
git status --short
```

**Result:**
```
?? docs/superpowers/plans/2026-06-29-c3-action-plan-human-execution-boundary.md
```

**Note:** Planning doc already exists but is untracked. C3-1 audit creates this scope audit doc only.

---

## 10. Git Log

```powershell
git log --oneline -10
```

**Result:**
```
9dbe4ab docs: update C2 verification with final test results and commit
f4131c0 fix: C2 add review rejection tests and expand forbidden terms
ed7748a fix: C2 enforce admission in review endpoints and expand tests
fa8fcba docs: C2 Signal Board decision boundary verification
295aa3b feat: C2 lock Signal Board user-facing decision boundary
866ca39 feat: C2 expose admission metadata to Signal Board frontend type
fdd5415 feat: C2 enforce admission on Signal Board detail lookup
9e561f1 test: C2 identify Signal Board detail admission bypass
d1b3044 docs: add C2 Signal Board decision boundary plan
289a3c7 docs: update C1 verification - API does not expose audit mode to users
```

---

## 11. Test Results

C2 regression:
```powershell
.venv\Scripts\python.exe -m pytest tests/test_c2_signal_board_decision_boundary.py tests/test_signal_board_ux_polish.py tests/test_signal_api.py -q
```

**Result:**
```
35 passed, 1 warning, 30 subtests passed in 2.44s
```

All C2 boundaries remain intact.

---

## 12. Remaining Risks

### 12.1 Implementation Risks
- C3 Action Plan might accidentally introduce buy/sell recommendation language → Mitigation: `test_c3_action_plan_copy_boundary.py` with forbidden terms list
- C3 might add order/broker/fill fields → Mitigation: `test_action_decision_does_not_accept_order_fields`
- C3 might bypass admission on direct-id → Mitigation: `test_action_plan_decision_rejects_unadmitted_direct_id`
- C3 might add batch endpoint without admission → Mitigation: `test_batch_or_mutation_bypass_not_introduced`

### 12.2 Scope Creep Risks
- C3 might expand into Execution Log (C4) → Guard: C3 only records decision, not actual fills
- C3 might connect to broker → Guard: No broker/order API imports allowed in C3 files
- C3 might use LLM for trade advice → Guard: ActionPlan builder must be deterministic/rule-based
- C3 might loosen C0/C1/C2 admission → Guard: C3 must call `get_admitted_signal()` before all operations

### 12.3 User Confusion Risks
- User might interpret "准备执行" as automatic execution → Mitigation: Disclaimer "不会自动交易"
- User might interpret Action Plan as profit guarantee → Mitigation: Neutral language, no profit claims
- User might miss blocking conditions → Mitigation: Disable execute button when blocked, show blocking reason

---

## 13. Summary

**Existing Action Plan implementation:** None found

**Signal Board reusable pieces:**
- Detail page structure (add panel)
- Admission enforcement pattern (`get_admitted_signal()`)
- Review status mapping
- C2 copy boundaries

**C3 minimal new files:**
- `contracts/action_plan.py`
- `backend/services/action_plan_builder.py`
- `tests/test_c3_action_plan_boundary.py`
- `tests/test_c3_action_plan_copy_boundary.py`
- Modify: `backend/api/signal_board.py`, `backend/db/signal_board.py`, `frontend/lib/api-client.ts`, `frontend/app/signals/[signal_id]/page.tsx`

**Protected files:** C0/C1/C2 verification docs, B-module files, admission gate, strategy DB, signal generation script

**Forbidden scope touched:** No

**Status:** READY_FOR_REVIEW

**Next step:** Implement C3-2 (Action Plan contract and builder) per plan task breakdown.

---

**Audit Completed:** 2026-06-28
