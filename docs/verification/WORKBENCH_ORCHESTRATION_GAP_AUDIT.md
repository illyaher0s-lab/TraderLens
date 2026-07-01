# Workbench Orchestration Gap Audit

**Date:** 2026-07-01  
**Task:** Task 20  
**Auditor:** Hermes Agent  
**Status:** ✅ Audit Complete, P0 Gaps Identified

---

## Executive Summary

TraderLens V1 Workbench has **2 critical P0 orchestration gaps** where workflow states indicate ongoing work but **no actual business action occurs**. Users see fake progress ("researching...", "validating...") while the system does nothing.

**Critical Findings:**
- ❌ **P0-1:** Friend stock message → workflow_state=`researching`, but NO research triggered
- ❌ **P0-2:** Strategy idea message → workflow_state=`validating`, but NO validation triggered
- ✅ Execution feedback → WORKS (creates real artifacts)
- ✅ Daily signal → WORKS (creates real artifacts)
- ✅ Unknown workflow → NO fake progress (correctly stays in `created` state)

**Impact:**
- User asks: "帮我查一下，宏昌电子是否值得买入？"
- System replies: "我会帮你调查...稍等片刻。" + workflow_state=`researching`
- User waits indefinitely
- **Nothing happens** (no research job, no artifact, no follow-up)

---

## 1. Workbench Workflow States

From `contracts/agent_workbench.py`:

```python
class WorkflowState(str, Enum):
    CREATED = "created"
    RESEARCHING = "researching"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    VALIDATING = "validating"
    LIVE_EXECUTION_PENDING = "live_execution_pending"
    OBSERVING = "observing"
    REVIEWING = "reviewing"
    COMPLETED = "completed"
    STOPPED = "stopped"
```

### State Inventory

| State | Intended Meaning | Currently Used By | Has Backing Action? |
|-------|-----------------|-------------------|---------------------|
| `created` | Session initialized | Unknown workflow | ✅ Yes (no action expected) |
| `researching` | Research in progress | Friend stock | ❌ **NO** (P0 gap) |
| `waiting_for_approval` | Approval card pending | (Not used) | N/A |
| `validating` | Validation in progress | Strategy idea | ❌ **NO** (P0 gap) |
| `live_execution_pending` | Execution card ready | (Not used) | N/A |
| `observing` | Position observation | (Not used) | N/A |
| `reviewing` | Discipline review | (Not used) | N/A |
| `completed` | Workflow finished | (Not used) | N/A |
| `stopped` | Workflow cancelled | (Not used) | N/A |

---

## 2. Endpoint Audit (Static Analysis)

### 2.1. POST `/api/agent/workbench/message`

**Location:** `backend/api/research.py:990-1158`

**Friend Stock Path:**
```python
if session.workflow_kind == WorkflowKind.FRIEND_STOCK:
    agent_reply = "收到，这是朋友推荐的股票。我会帮你调查这家公司的产业链位置、价值和风险。稍等片刻。"
    next_required_user_action = "wait_for_research"
```

**Analysis:**

| Aspect | Value |
|--------|-------|
| User-visible state | `workflow_state = "researching"` |
| Agent reply | "我会帮你调查...稍等片刻。" |
| Next action | `"wait_for_research"` |
| **Actual business action** | ❌ **NONE** |
| Artifact written | `workflow_intent` (intent only, no action) |
| DB table touched | `agent_sessions`, `agent_messages`, `agent_artifact_refs` |
| **Gap** | ❌ **Sets state=researching but triggers nothing** |
| **Severity** | **P0** |

**Missing Actions:**
1. Should call `/api/research/friend-stock/intake` (ticker verification)
2. Should call `/api/research/friend-stock/{flow_id}/run-research` (research execution)
3. Should create approval card
4. Should create `friend_stock_flow` artifact
5. Should create `research_report` artifact
6. Should create `confirmed_candidate_pool` artifact

**Strategy Idea Path:**
```python
elif session.workflow_kind == WorkflowKind.STRATEGY_IDEA:
    agent_reply = "收到，这是一个策略想法。我会帮你验证它的有效性，评估是否可以加入策略库。需要先提取策略规则并进行回测验证。"
    next_required_user_action = "wait_for_validation"
```

**Analysis:**

| Aspect | Value |
|--------|-------|
| User-visible state | `workflow_state = "validating"` |
| Agent reply | "我会帮你验证...需要先提取策略规则并进行回测验证。" |
| Next action | `"wait_for_validation"` |
| **Actual business action** | ❌ **NONE** |
| Artifact written | `workflow_intent` (intent only, no action) |
| DB table touched | `agent_sessions`, `agent_messages`, `agent_artifact_refs` |
| **Gap** | ❌ **Sets state=validating but triggers nothing** |
| **Severity** | **P0** |

**Missing Actions:**
1. Should create `StrategyIdea` (via `StrategyIdeaFlowService`)
2. Should call LLM extraction (`extract_claims`)
3. Should map to template (`map_to_template`)
4. Should create `strategy_idea` artifact
5. Should create `strategy_idea_extraction` artifact
6. Should create `template_mapping` or `rejection_registry` artifact

---

### 2.2. POST `/api/agent/workbench/{conversation_id}/execution-feedback`

**Location:** `backend/api/research.py:1253-1544`

**Analysis:**

| Aspect | Value |
|--------|-------|
| User-visible state | N/A (no state change) |
| **Actual business action** | ✅ **YES** |
| Artifact written | `execution_observation_log`, `observation_position`, `pnl_record`, `discipline_review` |
| DB table touched | `execution_observation_logs`, `observation_positions`, `pnl_records`, `discipline_reviews` |
| **Gap** | ✅ **NONE** (working correctly) |
| **Severity** | N/A |

**Evidence:**
- Creates `ExecutionObservationLog` with confirmed price/quantity
- Creates `ObservationPosition` (for buy) or closes position (for sell)
- Calculates P&L deterministically (no LLM, no mock)
- Creates `DisciplineReview` (for sell)
- All records persisted to DB

---

### 2.3. POST `/api/agent/workbench/{conversation_id}/daily-signal`

**Location:** `backend/api/research.py:1546-1656`

**Analysis:**

| Aspect | Value |
|--------|-------|
| User-visible state | N/A (no state change) |
| **Actual business action** | ✅ **YES** |
| Artifact written | `daily_observation_signal` |
| DB table touched | `daily_observation_signals` |
| **Gap** | ✅ **NONE** (working correctly) |
| **Severity** | N/A |

**Evidence:**
- Queries `observation_positions` for open positions
- Calls `ObservationPool.generate_daily_signal()` (deterministic reducer)
- Persists `DailyObservationSignal` to DB
- Returns signal list with `signal_id`, `position_id`, `symbol`, `signal_type`

---

### 2.4. POST `/api/agent/workbench/{conversation_id}/execution-card`

**Location:** `backend/api/research.py:1237-1251`

**Analysis:**

| Aspect | Value |
|--------|-------|
| User-visible state | N/A (not called from workbench message flow) |
| **Actual business action** | ❌ **Stub** (raises 400) |
| Artifact written | None |
| DB table touched | None |
| **Gap** | ⚠️ **Not implemented** (intentional placeholder) |
| **Severity** | P2 (documented limitation, not fake progress) |

**Evidence:**
```python
raise HTTPException(
    status_code=400,
    detail="No qualified artifact (confirmed_candidate or prototype_passed) found for this conversation"
)
```

This is **intentional** — execution card requires qualified artifact first. Not a gap because it doesn't claim progress.

---

## 3. Timeline Artifact Analysis

### 3.1. Friend Stock Timeline (Current State)

**User Input:**
```
"帮我查一下，宏昌电子是否值得买入？"
```

**Timeline Artifacts:**
1. `user_message` — User's question
2. `agent_message` — "我会帮你调查..."
3. `workflow_intent` — Intent detection artifact

**Missing Artifacts (Expected but Absent):**
- ❌ `friend_stock_flow` — Ticker verification result
- ❌ `research_report` — Serenity research output
- ❌ `confirmed_candidate_pool` — Candidate stock entry
- ❌ `approval_card` — Result-level approval

**Conclusion:** Timeline contains only **intent**, no **action**.

---

### 3.2. Strategy Idea Timeline (Current State)

**User Input:**
```
"我在抖音看到一个策略，下午两点半买入第二天卖出，帮我验证"
```

**Timeline Artifacts:**
1. `user_message` — User's question
2. `agent_message` — "我会帮你验证..."
3. `workflow_intent` — Intent detection artifact

**Missing Artifacts (Expected but Absent):**
- ❌ `strategy_idea` — Strategy idea record
- ❌ `strategy_idea_extraction` — LLM extraction result
- ❌ `template_mapping` — Template match result
- ❌ `rejection_registry` — Rejection record (if no template fits)

**Conclusion:** Timeline contains only **intent**, no **action**.

---

### 3.3. Execution Feedback Timeline (Current State)

**User Input:**
```
POST /execution-feedback { "feedback": "已买入 100 股，成交价 12.34", "symbol": "600123.SH" }
```

**Timeline Artifacts:**
1. `execution_observation_log` — Buy record with confirmed price/quantity
2. `observation_position` — Open position record

**Conclusion:** ✅ Timeline contains **real artifacts** proving action occurred.

---

### 3.4. Daily Signal Timeline (Current State)

**User Input:**
```
POST /daily-signal {}
```

**Timeline Artifacts:**
1. `daily_observation_signal` — Signal record with deterministic reducer result

**Conclusion:** ✅ Timeline contains **real artifacts** proving action occurred.

---

## 4. Root Cause Analysis

### 4.1. Friend Stock Gap

**Root Cause:**  
`/api/agent/workbench/message` endpoint **only sets workflow state** but **does not orchestrate the friend-stock flow**.

**Code Location:** `backend/api/research.py:1091-1094`

```python
if session.workflow_kind == WorkflowKind.FRIEND_STOCK:
    agent_reply = "收到，这是朋友推荐的股票。我会帮你调查这家公司的产业链位置、价值和风险。稍等片刻。"
    next_required_user_action = "wait_for_research"
    # BUT: NO CALL TO ACTUAL RESEARCH FLOW
```

**Why This Happened:**
- Task 13 implemented **intent detection and routing** (✅ done)
- Task 13 did NOT implement **orchestration** (❌ missing)
- Friend-stock API endpoints exist (`/api/research/friend-stock/intake`, `/run-research`) but are **not called** from workbench flow

**Existing Friend-Stock Flow (Outside Workbench):**
```
POST /api/research/friend-stock/intake
  → ticker verification
  → persists friend_stock_flow to DB
  
POST /api/research/friend-stock/{flow_id}/run-research
  → calls Serenity runner
  → persists research_output to DB
  
POST /api/research/friend-stock/{flow_id}/create-pool
  → creates confirmed_candidate_pool
  → creates approval card
```

**The Missing Link:**  
Workbench message endpoint does **not trigger** this flow.

---

### 4.2. Strategy Idea Gap

**Root Cause:**  
`/api/agent/workbench/message` endpoint **only sets workflow state** but **does not orchestrate the strategy-idea flow**.

**Code Location:** `backend/api/research.py:1095-1097`

```python
elif session.workflow_kind == WorkflowKind.STRATEGY_IDEA:
    agent_reply = "收到，这是一个策略想法。我会帮你验证它的有效性，评估是否可以加入策略库。需要先提取策略规则并进行回测验证。"
    next_required_user_action = "wait_for_validation"
    # BUT: NO CALL TO ACTUAL VALIDATION FLOW
```

**Why This Happened:**
- Task 11 implemented **strategy idea service layer** (`StrategyIdeaFlowService`) (✅ done)
- Task 13 implemented **intent detection** (✅ done)
- Task 13 did NOT implement **orchestration** (❌ missing)

**Existing Strategy-Idea Flow (Not Called):**
```python
StrategyIdeaFlowService.create_idea(raw_source_text, source_channel)
  → creates StrategyIdea with trust_status=untrusted
  
StrategyIdeaFlowService.extract_claims(idea)
  → calls LLM to extract claimed_entry, claimed_exit, claimed_edge
  → returns StrategyIdeaExtraction
  
StrategyIdeaFlowService.map_to_template(idea, ...)
  → maps to approved template or rejects
  → returns TemplateMappingResult
```

**The Missing Link:**  
Workbench message endpoint does **not trigger** this flow.

---

## 5. UI Misleading Analysis

### 5.1. Frontend Display

**File:** `frontend/components/WorkflowStatusPanel.tsx`

```typescript
const STATE_LABELS: Record<string, string> = {
  created: "已创建",
  researching: "研究中",           // ← Misleading when no research
  waiting_for_approval: "等待审批",
  validating: "验证中",             // ← Misleading when no validation
  live_execution_pending: "等待实盘",
  observing: "观察中",
  reviewing: "复盘中",
  completed: "已完成",
  stopped: "已停止",
};

const STATE_COLORS: Record<string, { bg: string; text: string; border: string }> = {
  researching: { bg: "#eff6ff", text: "#1d4ed8", border: "rgba(59,130,246,0.2)" },
  validating: { bg: "#f3e8ff", text: "#7c3aed", border: "rgba(168,85,247,0.2)" },
  // ...
};
```

**Impact:**
- User sees **blue badge** "研究中" → implies system is working
- User sees **purple badge** "验证中" → implies system is working
- **Reality:** System is idle, no background task running

**Timeline Panel:**
- Shows only `workflow_intent` artifact
- Does NOT show research progress
- Does NOT show validation progress

**User Experience:**
1. User asks question
2. System replies "我会帮你调查...稍等片刻。"
3. UI shows "研究中" badge
4. User waits
5. **Nothing happens**
6. User refreshes page → still "研究中"
7. User gives up

---

## 6. Severity Classification

### P0: Critical (Fake Progress)

**Definition:** User sees system claiming ongoing work, but system does nothing.

**Identified P0 Issues:**

| ID | Endpoint | Issue | Impact |
|----|----------|-------|--------|
| **P0-1** | `/api/agent/workbench/message` (friend_stock) | Sets `workflow_state=researching`, returns "wait_for_research", but **triggers no research** | User waits indefinitely, no research occurs |
| **P0-2** | `/api/agent/workbench/message` (strategy_idea) | Sets `workflow_state=validating`, returns "wait_for_validation", but **triggers no validation** | User waits indefinitely, no validation occurs |

**Why P0:**
- Breaks fundamental user trust
- User cannot tell system is broken (looks like it's working)
- Completely blocks friend-stock and strategy-idea workflows
- No workaround (user cannot manually trigger research)

---

### P1: Action Occurred But Not Trackable

**Definition:** Action happens, but timeline doesn't show proof.

**Identified P1 Issues:**

None. (Execution feedback and daily signal both create timeline artifacts correctly.)

---

### P2: Action Trackable But UI Unclear

**Definition:** Action happens and is trackable, but UI doesn't communicate clearly.

**Identified P2 Issues:**

None identified in current audit scope.

---

## 7. Recommended Fix Priority

### Fix 1: Friend Stock Orchestration (P0-1)

**Task:** Wire friend-stock flow into workbench message endpoint

**Scope:**
1. Modify `/api/agent/workbench/message` friend_stock path
2. Extract ticker from user message (regex or NER)
3. Call `/api/research/friend-stock/intake` internally
4. Handle verification result (verified / ambiguous / error)
5. If verified: call `/api/research/friend-stock/{flow_id}/run-research` (background or sync)
6. Create timeline artifacts:
   - `friend_stock_flow` artifact (verification result)
   - `research_report` artifact (research output)
   - `approval_card` (if research succeeds)
7. Update `workflow_state` to `waiting_for_approval` (when approval card created)

**Estimated Complexity:** Medium (orchestration logic + async handling)

**Test Coverage:**
- Modify `test_friend_stock_message_routes_to_friend_stock_workflow` to verify artifacts created
- Add new test: `test_friend_stock_message_creates_approval_card`

---

### Fix 2: Strategy Idea Orchestration (P0-2)

**Task:** Wire strategy-idea flow into workbench message endpoint

**Scope:**
1. Modify `/api/agent/workbench/message` strategy_idea path
2. Call `StrategyIdeaFlowService.create_idea(request.message, "workbench")`
3. Call `StrategyIdeaFlowService.extract_claims(idea)` (LLM call)
4. Call `StrategyIdeaFlowService.map_to_template(idea, ...)` (deterministic matching)
5. Create timeline artifacts:
   - `strategy_idea` artifact (idea record)
   - `strategy_idea_extraction` artifact (LLM extraction)
   - `template_mapping` or `rejection_registry` artifact (outcome)
6. If rejected: set `workflow_state=completed`, create system message explaining rejection
7. If mapped to template: set `workflow_state=waiting_for_approval`, create approval card

**Estimated Complexity:** Medium (LLM call + deterministic matching)

**Test Coverage:**
- Modify `test_strategy_video_routes_to_strategy_idea_workflow` to verify artifacts created
- Add new test: `test_strategy_idea_message_creates_rejection_or_approval`

---

### Fix 3: Execution Card (P2)

**Task:** Implement execution card creation from qualified artifact

**Scope:**
1. Implement `/api/agent/workbench/{conversation_id}/execution-card`
2. Check timeline for `confirmed_candidate` or `prototype_passed` artifact
3. If found: create `ExecutionCard` and return
4. If not found: return 400 with clear message (already done)

**Estimated Complexity:** Low

**Priority:** P2 (not blocking, documented limitation)

---

## 8. Task Breakdown

### Task 21: Fix Friend Stock Orchestration (P0-1)

**Goal:** Wire friend-stock flow into workbench message endpoint

**Steps:**
1. Read `backend/api/research.py` friend-stock endpoints (intake, run-research, create-pool)
2. Modify `/api/agent/workbench/message` friend_stock path:
   - Extract ticker from user message
   - Call intake endpoint internally (or call service directly)
   - Handle verification result
   - Trigger research (sync or background)
   - Create timeline artifacts
   - Create approval card (if research succeeds)
3. Update tests:
   - `test_friend_stock_message_routes_to_friend_stock_workflow` → verify artifacts
   - New test: `test_friend_stock_message_creates_approval_card`
4. Update `test_v1_workbench_orchestration_gap.py` → mark P0-1 as fixed
5. Update UI text if needed (already says "我会帮你调查")

**Verification:**
- User sends "帮我查一下，宏昌电子是否值得买入？"
- Timeline shows: `friend_stock_flow`, `research_report`, `approval_card`
- UI shows: "等待审批" (not "研究中")

---

### Task 22: Fix Strategy Idea Orchestration (P0-2)

**Goal:** Wire strategy-idea flow into workbench message endpoint

**Steps:**
1. Read `backend/services/strategy_idea_flow.py`
2. Modify `/api/agent/workbench/message` strategy_idea path:
   - Create `StrategyIdea` via service
   - Extract claims via LLM
   - Map to template (or reject)
   - Create timeline artifacts
   - Create approval card (if template match) or rejection message (if no fit)
3. Update tests:
   - `test_strategy_video_routes_to_strategy_idea_workflow` → verify artifacts
   - New test: `test_strategy_idea_message_creates_rejection_or_approval`
4. Update `test_v1_workbench_orchestration_gap.py` → mark P0-2 as fixed
5. Update UI text if needed (already says "我会帮你验证")

**Verification:**
- User sends "我在抖音看到一个策略，下午两点半买入第二天卖出，帮我验证"
- Timeline shows: `strategy_idea`, `strategy_idea_extraction`, `template_mapping` or `rejection_registry`
- UI shows: "等待审批" (if template match) or "已完成" (if rejected)

---

## 9. Immediate Next Steps

**Recommendation:** Fix P0-1 and P0-2 immediately.

**Execution Order:**
1. **Task 21** (Friend Stock Orchestration) — Higher user demand
2. **Task 22** (Strategy Idea Orchestration) — Complete the validation loop

**Do NOT:**
- Change UI text to hide the problem ("研究中" → "准备研究")
- Add fake artifacts to timeline
- Skip tests

**DO:**
- Wire real orchestration logic
- Create real timeline artifacts
- Update audit tests to verify fixes

---

## 10. Audit Test Results

**Test File:** `tests/test_v1_workbench_orchestration_gap.py`

**Results:**
```
============================= test session starts =============================
tests/test_v1_workbench_orchestration_gap.py::TestWorkbenchOrchestrationGaps::test_friend_stock_message_sets_researching_state_but_no_action PASSED [ 20%]
tests/test_v1_workbench_orchestration_gap.py::TestWorkbenchOrchestrationGaps::test_strategy_idea_message_sets_validating_state_but_no_action PASSED [ 40%]
tests/test_v1_workbench_orchestration_gap.py::TestWorkbenchOrchestrationGaps::test_execution_feedback_does_create_real_artifacts PASSED [ 60%]
tests/test_v1_workbench_orchestration_gap.py::TestWorkbenchOrchestrationGaps::test_daily_signal_does_create_real_artifacts PASSED [ 80%]
tests/test_v1_workbench_orchestration_gap.py::TestWorkbenchOrchestrationGaps::test_unknown_workflow_has_no_fake_progress_state PASSED [100%]

5 passed, 1 warning in 7.55s
```

**Interpretation:**
- ✅ Tests **confirm** P0-1 (friend stock has no action)
- ✅ Tests **confirm** P0-2 (strategy idea has no action)
- ✅ Tests **confirm** execution feedback works correctly
- ✅ Tests **confirm** daily signal works correctly
- ✅ Tests **confirm** unknown workflow does not set fake progress

---

## 11. Conclusion

**Summary:**
- **2 critical P0 gaps** identified (friend stock, strategy idea)
- **0 P1 gaps** identified
- **0 P2 gaps** identified in current scope
- **Live loop endpoints (execution-feedback, daily-signal) work correctly**
- **Audit tests created** to verify gaps and future fixes

**Immediate Action Required:**
- Fix P0-1 (friend stock orchestration) in Task 21
- Fix P0-2 (strategy idea orchestration) in Task 22

**Post-Fix Verification:**
- Re-run `test_v1_workbench_orchestration_gap.py`
- Verify timeline artifacts created
- Verify UI state transitions correctly
- Verify no regression in existing tests

---

## Appendix A: Audit Test Code

See: `tests/test_v1_workbench_orchestration_gap.py`

**Test Coverage:**
1. `test_friend_stock_message_sets_researching_state_but_no_action` — P0-1 verification
2. `test_strategy_idea_message_sets_validating_state_but_no_action` — P0-2 verification
3. `test_execution_feedback_does_create_real_artifacts` — Positive control
4. `test_daily_signal_does_create_real_artifacts` — Positive control
5. `test_unknown_workflow_has_no_fake_progress_state` — Negative control

---

## Appendix B: Related Tests

**Existing Tests (No Changes Needed):**
- `tests/test_v1_agent_workbench_api.py` — Intent detection and routing (✅ passing)
- `tests/test_v1_workbench_live_loop_api.py` — Execution feedback and daily signal (✅ passing)
- `tests/test_v1_friend_stock_api.py` — Friend-stock endpoints (✅ passing, not called from workbench)
- `tests/test_v1_strategy_idea_flow.py` — Strategy-idea service layer (✅ passing, not called from workbench)

**Regression Risk:**
- Low (orchestration logic is additive, existing tests verify endpoint behavior)

---

**End of Audit Report**
