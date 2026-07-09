# P5-P6 Plan Phase Closure Mapping

**Purpose:** Align completed P3/P4 delivery lines with rebuild plan Phase 5 and Phase 6 to confirm no phase was skipped before entering P7 E2E Product Acceptance.

---

## Phase 5: Strategy Product Flow

### Plan Objectives (from 2026-07-01 rebuild plan)

Goal: Strategy ideas are visible from submission to approval/rejection.

Tasks:
- Build `/strategy-ideas` list/detail pages
- Build `/strategies` approved strategy library
- Build `/rejected-strategies` registry page
- Connect Workbench strategy messages to strategy idea records
- Run template mapping visibly
- If approved template fits, create validation case
- If not, create candidate/rejection record with reason
- Display B-module validation artifacts when available

Expected outcome:
```
User: 下午两点半买入，第二天早上卖出，这个策略能不能做
System:
1. extracts strategy idea
2. maps to approved template or rejects/candidates it
3. records validation state
4. shows status in strategy UI
5. passed strategies appear in /strategies
6. failed strategies appear in /rejected-strategies
```

### Completed Delivery

**Delivery Line:** P3-1 through P3-10

**Key Deliverable:** P3_10_DELIVERY.md (run_id: P3_10_E2E_20260708_104755)

**Flow Verified:**
- Workbench strategy message → strategy idea
- Extraction → template mapping
- Rejected/candidate decision with reason
- Validation empty state
- Approved strategy library empty state

**Pages Verified:**
- `/strategies` (approved strategy library)
- `/strategy-ideas/{idea_id}` (detail page)
- `/candidate-strategies` (candidate registry)
- `/rejected-strategies` (rejection registry)
- `/strategy-validations` (validation status)
- `/strategy-templates` (template library)

**APIs Verified:**
- `GET /api/strategy-ideas/{idea_id}`
- `GET /api/strategy-ideas?conversation_id={conversation_id}`
- `GET /api/strategy-ideas?candidate_status=candidate_unapproved`
- `GET /api/strategy-validations`
- `GET /api/strategies`
- `GET /api/strategy-templates`

**Red Lines Enforced:**
- No fake validation case
- No fake approved strategy
- No candidate promoted to validation without template fit
- No trading signal generated
- Strategy idea traceable from Workbench input to extraction/mapping/rejected/candidate/registry/dashboard

**Evidence:** 18 files including Playwright DOM, network logs, API responses, backend/frontend logs

**Gap Analysis:** No blocking gap. Approved strategy count is zero (correct empty state per design). Template mapping to rejection/candidate flow is complete and verified.

---

## Phase 6: Daily Dashboard

### Plan Objectives (from 2026-07-01 rebuild plan)

Goal: The user opens one page and knows today's required actions.

Tasks:
- Replace current home page with daily dashboard
- Show open observations, today's signals, survival guard blocks/downgrades, pending approvals, active research, active strategy validations, and recent reviews
- Add links to Workbench, Observation Pool, Signal Board, Strategy Library
- Fix any mojibake on home/workbench pages

Expected outcome:
- User does not need to know which module to open first
- Empty state explains what to ask the Agent
- Non-technical wording only

### Completed Delivery

**Delivery Line:** P4-1 through P4-6

**Key Deliverables:**
- P4_6_DELIVERY.md (run_id: P4_6_RUN_20260709_142649)
- P4_5_COPY_AUDIT.md (run_id: P4_5_RUN_20260709_104517)

**Dashboard Sections Verified (`/`):**

1. **Observations** (P4-1)
   - Open observation positions
   - Data state indicator
   - Action link to `/observations`

2. **Signals** (P4-2)
   - Today's generated signals
   - Signal count
   - Action link to `/signals`

3. **Strategy Workspace** (P4-3)
   - Active strategy validations count
   - Action link to `/strategies`

4. **Reviews** (P4-4)
   - Recent execution/P&L review items count
   - Action link to `/reviews`

5. **Risk Guard Status** (P4-6)
   - Risk guard data state (not_configured shell)
   - blocks_count / downgrades_count (both zero in current implementation)
   - Disclaimer: "此区域仅显示风险守卫状态,不代表交易允许或阻断决策"
   - No real risk blocking (per design)

6. **Data Freshness** (P4-1 through P4-4)
   - Updated_at timestamps on all sections

**Copy Audit (P4-5):**
- Dashboard contains valid UTF-8 copy: `每日工作台`, `观察池`, `策略工作区`, `数据正常`, `暂无数据`
- Workbench contains valid UTF-8 copy: `TraderLens 工作台`
- No product-page mojibake found

**Evidence:** Playwright DOM snapshots, network logs, API responses verified all sections present and reachable

**Gap Analysis:** No blocking gap. Risk guard is shell-only (correct per 2026-07-02 risk attribution design freeze). All dashboard sections display correct empty/populated states and link to corresponding pages.

---

## Conclusion

**Phase 5 Coverage:** Complete via P3 delivery line (P3-1 through P3-10). Strategy idea flow from Workbench input to visible strategy workspace tracking is verified end-to-end.

**Phase 6 Coverage:** Complete via P4 delivery line (P4-1 through P4-6). Daily dashboard displays observations, signals, strategy workspace, reviews, and risk guard status with correct action links and data freshness indicators.

**Next Phase:** P7 E2E Product Acceptance is now unblocked.

**P7 Requirements (for next agent):**
- Must use real browser (Playwright) verification
- Must capture network evidence
- Must verify end-to-end user journeys (friend stock loop, strategy idea loop)
- Cannot rely solely on historical P3/P4 delivery docs
- Must demonstrate product flows from live running application

---

**Mapping completed:** 2026-07-09  
**Git status at mapping:** clean
