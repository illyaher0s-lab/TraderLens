# V1 Product Closure Baseline Audit

**Date:** 2026-07-02  
**Auditor:** Hermes Agent  
**Purpose:** 按产品流程审计现有实现，识别两条核心用户旅程的完成度和缺口

---

## Executive Summary

TraderLens V1 has **significant module-level implementation** but **incomplete product-level integration**. The two required user journeys (friend-stock → P&L, strategy-idea → library/rejection) are **not yet runnable end-to-end from a unified product interface**.

**Critical Findings:**

- ✅ **Backend services exist:** Research, strategy validation, signal board, action plan, observation pool, discipline review
- ✅ **Frontend pages exist:** Workbench, Signal Board, Themes
- ❌ **P0 Gap:** Agent orchestration has fake progress states (researching/validating without real action)
- ❌ **P0 Gap:** No observation pool UI (positions exist in DB, but no user-facing pages)
- ❌ **P0 Gap:** No strategy library UI (ideas/templates/rejections exist in DB, but no pages)
- ❌ **P1 Gap:** Daily dashboard does not show actionable items
- ❌ **P1 Gap:** Execution card → buy/sell feedback → observation flow not wired

**Product Readiness:**

| Workflow Step | Backend | API | Frontend | Status |
|---------------|---------|-----|----------|--------|
| Friend stock intake | ✅ | ✅ | ⚠️ (workbench) | PARTIAL |
| Research execution | ✅ | ✅ | ❌ (fake) | SERVICE_ONLY |
| Candidate pool | ✅ | ✅ | ❌ | SERVICE_ONLY |
| Strategy idea intake | ✅ | ✅ | ⚠️ (workbench) | PARTIAL |
| Template mapping | ✅ | ✅ | ❌ | SERVICE_ONLY |
| Rejection registry | ✅ | ✅ | ❌ | SERVICE_ONLY |
| Signal board | ✅ | ✅ | ✅ | DONE |
| Action plan | ✅ | ✅ | ⚠️ | PARTIAL |
| Execution feedback | ✅ | ✅ | ❌ | SERVICE_ONLY |
| Observation pool | ✅ | ❌ | ❌ | SERVICE_ONLY |
| Daily signals | ✅ | ❌ | ❌ | SERVICE_ONLY |
| Discipline review | ✅ | ❌ | ❌ | SERVICE_ONLY |

---

## 1. Current Page Inventory

### 1.1 Existing Pages

| Route | File | Purpose | Status | Missing |
|-------|------|---------|--------|---------|
| `/` | `page.tsx` | Home | ⚠️ PARTIAL | Daily items |
| `/workbench` | `workbench/page.tsx` | Agent chat | ⚠️ PARTIAL | Real orchestration |
| `/signals` | `signals/page.tsx` | Signal list | ✅ DONE | - |
| `/signals/[id]` | `signals/[id]/page.tsx` | Signal detail | ✅ DONE | - |
| `/themes` | `themes/page.tsx` | Themes list | ✅ DONE | - |
| `/themes/[id]` | `themes/[id]/page.tsx` | Theme detail | ✅ DONE | - |

### 1.2 Missing Pages (P0)

- ❌ `/observations` — Observation pool list
- ❌ `/observations/[position_id]` — Position detail
- ❌ `/strategies` — Strategy library
- ❌ `/strategy-ideas` — Ideas list
- ❌ `/strategy-ideas/[idea_id]` — Idea detail
- ❌ `/rejected-strategies` — Rejection registry

---

## 2. Backend API Inventory

### 2.1 Research API (research.py)

**Implemented:**
- POST /api/research/themes ✅
- GET /api/research/themes ✅
- POST /api/research/friend-stock/intake ✅
- POST /api/research/friend-stock/{id}/run-research ✅
- POST /api/agent/workbench/message ✅
- GET /api/agent/workbench/{id} ✅

**Gaps:**
- ❌ GET /api/research/cases (no list)
- ❌ Workbench message has fake progress

### 2.2 Signal Board API (signal_board.py)

**Status:** ✅ Complete (8 endpoints, C0-C3 verified)

### 2.3 Strategy Ideas API (strategy_ideas.py)

**Implemented:**
- POST /api/strategy-ideas ✅
- GET /api/strategy-ideas/{id} ✅

**Gaps:**
- ❌ GET /api/strategy-ideas (no list)
- ❌ GET /api/rejected-strategies
- ❌ GET /api/strategy-templates

### 2.4 Missing APIs (P0)

- ❌ GET /api/observations
- ❌ GET /api/observations/{position_id}
- ❌ GET /api/strategy-ideas
- ❌ GET /api/strategy-templates
- ❌ GET /api/rejected-strategies

---

## 3. Database & Service Assets

### 3.1 Database Tables

**All required tables exist:**
- agent_sessions ✅
- confirmed_candidate_pool ✅
- strategy_ideas ✅
- rejected_strategy_registry ✅
- planned_signals ✅
- observation_positions ✅
- daily_observation_signals ✅
- discipline_reviews ✅

### 3.2 Service Layer

**All required services exist:**
- friend_stock_flow.py ✅
- stock_identity_resolver.py ✅
- strategy_idea_flow.py ✅
- observation_pool.py ✅
- execution_interpreter.py ✅
- discipline_review.py ✅
- action_plan_builder.py ✅

**Gap:** Services isolated, orchestration incomplete.

---

## 4. Product Flow Status

### 4.1 Flow A: Friend Stock → P&L

**User Steps:**

| Step | Backend | API | Frontend | Status |
|------|---------|-----|----------|--------|
| 1. User asks agent | ✅ | ✅ | ✅ | DONE |
| 2. Agent understands | ✅ | ✅ | ✅ | DONE |
| 3. Tushare verifies ticker | ✅ | ✅ | ⚠️ | PARTIAL |
| 4. Research runs | ✅ | ✅ | ❌ | **BROKEN** |
| 5. Candidate pool created | ✅ | ✅ | ❌ | SERVICE_ONLY |
| 6. User approves | ⚠️ | ⚠️ | ⚠️ | UNKNOWN |
| 7. Execution card | ✅ | ❌ | ❌ | SERVICE_ONLY |
| 8. User records buy | ✅ | ✅ | ❌ | SERVICE_ONLY |
| 9. Position created | ✅ | ❌ | ❌ | SERVICE_ONLY |
| 10. Daily signal | ✅ | ❌ | ❌ | SERVICE_ONLY |
| 11. User records sell | ✅ | ✅ | ❌ | SERVICE_ONLY |
| 12. P&L review | ✅ | ❌ | ❌ | SERVICE_ONLY |

**Status:** ❌ **PARTIAL** (Steps 1-3 work, 4 broken, 5-12 not wired)

**Critical Gap:** Step 4 (Research execution) has **FAKE PROGRESS** — workbench shows "研究中" but triggers no research.

---

### 4.2 Flow B: Strategy Idea → Library/Rejection

**User Steps:**

| Step | Backend | API | Frontend | Status |
|------|---------|-----|----------|--------|
| 1. User submits idea | ✅ | ✅ | ✅ | DONE |
| 2. Agent extracts | ✅ | ✅ | ✅ | DONE |
| 3. Template mapping | ✅ | ✅ | ❌ | SERVICE_ONLY |
| 4. Validation runs | ✅ | ⚠️ | ❌ | SERVICE_ONLY |
| 5. Passed → library | ✅ | ❌ | ❌ | SERVICE_ONLY |
| 6. Failed → rejection | ✅ | ❌ | ❌ | SERVICE_ONLY |
| 7. User sees status | ❌ | ❌ | ❌ | **MISSING** |

**Status:** ❌ **PARTIAL** (Steps 1-3 work, 4-7 not visible)

**Critical Gap:** No UI to see strategy library or rejection registry.

---

## 5. Agent Entry Audit (P0-1 Critical Issue)

### 5.1 Current Workbench Behavior

**File:** `backend/api/research.py:990-1158`

**Friend Stock Path:**
```python
if session.workflow_kind == WorkflowKind.FRIEND_STOCK:
    agent_reply = "我会帮你调查...稍等片刻。"
    next_required_user_action = "wait_for_research"
    # BUT: NO ACTUAL RESEARCH TRIGGERED
```

**Problem:** Sets `workflow_state = "researching"` but **does not call research APIs**.

**User sees:**
- Blue badge "研究中"
- Message "我会帮你调查..."
- **Nothing happens** (no background job, no artifact creation)

**Evidence:** WORKBENCH_ORCHESTRATION_GAP_AUDIT.md confirms P0-1 and P0-2 gaps.

### 5.2 Strategy Idea Path

**Same issue:**
```python
elif session.workflow_kind == WorkflowKind.STRATEGY_IDEA:
    agent_reply = "我会帮你验证..."
    next_required_user_action = "wait_for_validation"
    # BUT: NO ACTUAL VALIDATION TRIGGERED
```

**Problem:** Sets `workflow_state = "validating"` but **does not call validation services**.

### 5.3 Root Cause

Task 13 implemented **intent detection and routing** but **not orchestration**.

**Missing wiring:**
1. Workbench → friend_stock_flow intake
2. Workbench → research execution
3. Workbench → candidate pool creation
4. Workbench → strategy_idea_flow
5. Workbench → template mapping
6. Workbench → rejection registry

---

## 6. Signal Board vs Observation Pool

**Current confusion:**

| Concept | Purpose | Current State |
|---------|---------|---------------|
| Signal Board | System-generated planned signals from admitted strategies | ✅ Complete (C0-C3) |
| Observation Pool | User-observed/held positions with daily follow-up | ❌ No UI |

**Critical distinction:**
- Signal Board = **计划信号** (from validated strategies)
- Observation Pool = **观察池/持仓** (after manual execution)

**Current gap:** Observation pool exists in DB but has no pages.

---

## 7. Strategy Library Audit

### 7.1 Where User Should See Strategies

**Current:** No pages exist.

**Required:**
- `/strategies` — Approved templates
- `/strategy-ideas` — Incoming ideas (untrusted → candidate → approved)
- `/strategy-ideas/[id]` — Idea detail (extraction, mapping, validation)
- `/rejected-strategies` — Failed/blocked/needs-review

### 7.2 Can User See Validation Status?

**Answer:** ❌ No

**Evidence:** Strategy ideas API has detail endpoint but no list. Rejection registry has DB table but no API endpoint.

---

## 8. Recommended Task Order

Based on audit findings:

### P0-2: Agent Entry Orchestration Fix
**Goal:** Wire friend-stock and strategy-idea flows into workbench message endpoint.

**Scope:**
1. Modify `/api/agent/workbench/message` friend_stock path
2. Call `friend_stock_flow.intake()` → `run_research()` → `create_pool()`
3. Create timeline artifacts (friend_stock_flow, research_report, confirmed_candidate)
4. Modify strategy_idea path
5. Call `strategy_idea_flow.create_idea()` → `extract_claims()` → `map_to_template()`
6. Create timeline artifacts (strategy_idea, extraction, template_mapping/rejection)

**Priority:** **P0** (blocks both core workflows)

### P0-3: Observation Pool Pages
**Goal:** User can see and manage observed/held positions.

**Scope:**
1. Build `/observations` list page
2. Build `/observations/[position_id]` detail page
3. Add API endpoints (GET /api/observations, GET /api/observations/{id})
4. Connect to workbench execution feedback
5. Show daily signals

**Priority:** **P0** (blocks Flow A completion)

### P0-4: Strategy Library Pages
**Goal:** User can see strategy ideas, templates, and rejections.

**Scope:**
1. Build `/strategy-ideas` list page
2. Build `/strategy-ideas/[id]` detail page
3. Build `/strategies` approved template list
4. Build `/rejected-strategies` registry page
5. Add API endpoints (GET /api/strategy-ideas, GET /api/rejected-strategies)

**Priority:** **P0** (blocks Flow B completion)

### P1-1: Daily Dashboard
**Goal:** User opens one page and knows today's actions.

**Scope:**
1. Replace current home page with daily dashboard
2. Show open observations, today's signals, pending approvals
3. Add links to observation pool, signal board, strategy library

**Priority:** **P1** (important for usability, not blocking core flows)

### P2-1: Browser E2E Acceptance
**Goal:** Verify both flows work end-to-end in browser.

**Scope:**
1. Start backend + frontend
2. Test Flow A: friend stock → candidate pool → (manual approval) → observation
3. Test Flow B: strategy idea → extraction → rejection/mapping
4. Document acceptance evidence

**Priority:** **P2** (verification after P0 tasks complete)

---

## 9. Git Status

```
(no changes — audit doc not yet written)
```

**After audit completion:**
- New file: `docs/verification/V1_PRODUCT_CLOSURE_BASELINE_AUDIT.md`

---

## Summary

### Current Product Closure State

**Module completion:** ~80%  
**Product integration:** ~40%  
**User journey completion:** ~20%

**Biggest gaps:**
1. Agent orchestration fake progress (P0-1, P0-2)
2. No observation pool UI (P0)
3. No strategy library UI (P0)
4. Daily dashboard not actionable (P1)

### Next Steps

1. **Fix P0-2** (agent orchestration) — unblocks both flows
2. **Build P0-3** (observation pool pages) — completes Flow A
3. **Build P0-4** (strategy library pages) — completes Flow B
4. **Enhance P1-1** (daily dashboard) — improves UX
5. **Verify P2-1** (browser E2E) — confirms acceptance

### Verification Standard

"We're done when user can complete both flows from browser without seeing fake progress, missing pages, or service-only features."

**Current answer:** ❌ Not done (3 P0 gaps block acceptance)

---

## 10. Risk Guard and Attribution Audit

### 10.1 Market Regime Guard (大市极端熔断)

**Question:** 当前是否已有大市极端熔断 / MarketRegimeGuard？

**Answer:** ❌ **MISSING**

**Evidence:** 
- Searched `backend/` for `MarketRegimeGuard`, `market_regime`, `熔断` — no results
- No service file for market regime detection
- No contract definition for regime states (bull/bear/crash/calm)

**Where it should be inserted in Flow A:**
- **Position:** After Step 9 (Position created), before Step 10 (Daily signal generation)
- **Purpose:** Block or downgrade daily signals when market-wide crash/panic detected
- **Implementation:** 
  - Check 沪深300 or benchmark intraday drop > threshold (e.g., -5%)
  - If regime = crash → daily signal downgraded to `risk` or `pause_observation`

**Status:** **MISSING**

---

### 10.2 Position Limit (单票仓位上限)

**Question:** 当前是否已有单票仓位上限？

**Answer:** ❌ **MISSING**

**Evidence:**
- Searched `backend/` for `position_limit`, `仓位上限`, `max_position` — no results
- No capital context validation for per-position limits
- `capital_context.py` exists but does not enforce position size caps

**Where it should be inserted in Flow A:**
- **Position:** After Step 7 (Execution card), before Step 8 (User records buy)
- **Purpose:** Block execution if position exceeds user-defined single-stock limit
- **Implementation:**
  - User defines max single-stock position (e.g., 20% of total capital)
  - Execution card checks planned position size vs. limit
  - If exceeded → recommendation_level downgraded to `pause_observation` or `do_not_execute`

**Status:** **MISSING**

---

### 10.3 Fixed Stop Loss (固定止损)

**Question:** 当前是否已有固定止损？

**Answer:** ✅ **DONE**

**Evidence:**
- `backend/services/observation_pool.py:188` — `stop_loss_threshold = template_rules.get("risk_rules", {}).get("stop_loss", -0.08)`
- `observation_pool.py:208-218` — Stop loss hit → `DailySignalType.sell`
- Logic: `if pnl_pct <= stop_loss_threshold: return (DailySignalType.sell, [], {...})`
- Default threshold: -8% (configurable via template rules)

**Where it is in Flow A:**
- **Position:** Step 10 (Daily signal generation)
- **Trigger:** Deterministic reducer checks `(current_price - entry_price) / entry_price <= stop_loss_threshold`
- **Result:** Daily signal = `sell`, rule_trace = `{"rule": "stop_rule", "threshold": -0.08, "actual": pnl_pct, "hit": True}`

**Status:** **DONE**

---

### 10.4 Signal Type: insufficient_data vs hold

**Question:** 当前 observation signal 是否区分 insufficient_data 和 hold？

**Answer:** ⚠️ **PARTIAL**

**Evidence:**

**DailySignalType enum** (`contracts/live_trade.py:34-40`):
```python
class DailySignalType(str, Enum):
    hold = "hold"
    sell = "sell"
    risk = "risk"
    invalidated = "invalidated"
```

**Current behavior:**
- ✅ **`risk` is used for data faults:** When `market_data_state != MarketDataFaultState.ok`, signal = `risk` (line 174-184)
- ❌ **No `insufficient_data` enum value:** `DailySignalType` does not have `insufficient_data`
- ⚠️ **`risk` conflates two meanings:**
  1. Market data fault (partial/stale/unavailable data)
  2. Risk conditions (e.g., approaching stop loss but not yet triggered)

**Analysis:**
- Current implementation **does distinguish** data insufficiency (via `risk` + rule_trace showing `market_data_fault`)
- But **naming is ambiguous** — `risk` could mean "risky to hold" or "data unavailable"
- Rule trace provides clarity: `{"rule": "market_data_fault", "fault_state": "...", "hit": True}`

**Recommendation:**
- Keep current behavior (functional separation exists)
- Consider renaming in future: `risk` → `caution`, add explicit `insufficient_data` signal type
- Or keep `risk` but ensure rule_trace always distinguishes `market_data_fault` from `risk_threshold`

**Status:** **PARTIAL** (functionally separate, semantically ambiguous)

---

### 10.5 Discipline Review Attribution

**Question:** 当前复盘是否能区分固定止损、止盈、手动偏离、数据不足等归因？

**Answer:** ⚠️ **PARTIAL**

**Evidence:**

**Exit attribution sources available:**

1. **Daily signal type** (`DailySignalType`):
   - `sell` (includes stop_rule, profit_target, invalidated triggers)
   - `risk` (data fault)
   - `invalidated` (external triggers)

2. **Rule trace** (`observation_pool.py:213-217`):
   ```python
   {
       "rule": "stop_rule",
       "threshold": -0.08,
       "actual": pnl_pct,
       "hit": True
   }
   ```
   - Distinguishes **stop_rule** (固定止损) from other sell reasons

3. **Plan adherence** (`discipline_review.py:113-146`):
   - Detects `late_exit` (迟卖) — compares signal_date vs actual_action_date
   - Does NOT yet detect:
     - ❌ Early exit (未到止损/止盈就提前卖出)
     - ❌ Ignored signal (信号提示卖出但用户未卖)
     - ❌ Manual deviation (用户自行决策卖出，无对应信号)

4. **P&L source** (`PnlSource` enum):
   - `calculated_from_confirmed_details` (完整数据)
   - `incomplete` (数据不足)
   - `user_reported` (用户报告)

**Current attribution capability:**

| Exit Reason | Can Detect? | Evidence Source | Status |
|-------------|-------------|-----------------|--------|
| 固定止损 (stop_rule) | ✅ | rule_trace: "stop_rule" | DONE |
| 止盈 (profit_target) | ⚠️ | Code commented out (line 221-223) | PARTIAL |
| 主动平仓 (invalidated) | ✅ | DailySignalType.invalidated + triggers | DONE |
| 数据不足 (data fault) | ✅ | DailySignalType.risk + market_data_fault | DONE |
| 迟卖 (late_exit) | ✅ | PlanAdherenceResult.deviations | DONE |
| 早卖 (early_exit) | ❌ | Not implemented | MISSING |
| 忽略信号 (ignored_signal) | ❌ | Not implemented | MISSING |
| 手动偏离 (manual_override) | ❌ | Not implemented | MISSING |

**Status:** **PARTIAL** (止损/止盈/invalidated/数据不足 can be attributed, 手动偏离 cannot)

---

### 10.6 Insertion Points in Flow A

**Summary of where each feature should be inserted:**

| Feature | Insertion Point | Purpose | Current Status |
|---------|----------------|---------|----------------|
| **Market Regime Guard** | Step 9 → 10 (Position → Daily signal) | Block signals during market crash | ❌ MISSING |
| **Position Limit** | Step 7 → 8 (Execution card → Record buy) | Cap single-stock position size | ❌ MISSING |
| **Fixed Stop Loss** | Step 10 (Daily signal generation) | Auto-exit on loss threshold | ✅ DONE |
| **insufficient_data signal** | Step 10 (Daily signal generation) | Distinguish data fault from risk | ⚠️ PARTIAL (uses `risk`) |
| **Exit attribution** | Step 12 (P&L review) | Classify exit reasons (止损/止盈/手动偏离) | ⚠️ PARTIAL (止损✅, 手动偏离❌) |

---

### 10.7 Summary Table

| Risk Guard / Attribution Feature | Status | Location | Notes |
|----------------------------------|--------|----------|-------|
| **Market Regime Guard** | ❌ MISSING | N/A | Should check benchmark drop before daily signal |
| **Position Limit (仓位上限)** | ❌ MISSING | N/A | Should validate in execution card builder |
| **Fixed Stop Loss (固定止损)** | ✅ DONE | `observation_pool.py:208` | Threshold -8%, deterministic |
| **insufficient_data vs hold** | ⚠️ PARTIAL | `observation_pool.py:174-184` | Uses `risk` for data fault, functional but ambiguous |
| **Exit attribution (止损)** | ✅ DONE | rule_trace: "stop_rule" | Distinguishable in discipline review |
| **Exit attribution (止盈)** | ⚠️ PARTIAL | Code commented out | Template defined, not active |
| **Exit attribution (手动偏离)** | ❌ MISSING | N/A | Cannot detect manual override yet |
| **Exit attribution (忽略信号)** | ❌ MISSING | N/A | Cannot detect ignored signals yet |
| **Exit attribution (数据不足)** | ✅ DONE | DailySignalType.risk + market_data_fault | Distinguishable |

---

**Audit Completed:** 2026-07-02
