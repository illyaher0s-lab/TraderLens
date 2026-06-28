# C3 Action Plan Human Execution Boundary Implementation Plan

> For agentic workers: REQUIRED SUB-SKILL: Use superpowers:executing-plans or superpowers:subagent-driven-development. Implement task by task. Do not collapse tasks into one broad rewrite.

## Goal

C3 turns an admitted Signal Board planned signal into a human-readable Action Plan.

C3 does not generate new signals, does not change strategy rules, does not connect to brokers, does not auto-execute, and does not claim profit or live-trading readiness.

The goal is to answer one practical user question:

> “这个已通过验证的计划信号，今天如果我要人工处理，我该看哪些条件、什么情况下放弃、怎么记录我的决定？”

C3 is the first bridge from Signal Board to human execution discipline.

## Architecture Position

Current mainline:

```text
prototype_passed
  ↓
Signal Board
  ↓
Action Plan
  ↓
人工执行 / 放弃 / 部分执行记录
  ↓
Execution Log
  ↓
盘后复盘
```

C3 covers only:

```text
Signal Board
  ↓
Action Plan
  ↓
人工确认：准备执行 / 放弃 / 部分执行 / 过期
```

C3 does not implement full Execution Log or post-market review. Those are C4/C5.

## Current State To Preserve

Already implemented and must not be rebuilt:

* Signal Board list page exists at `frontend/app/signals/page.tsx`.
* Signal Board detail page exists at `frontend/app/signals/[signal_id]/page.tsx`.
* Signal Board REST API exists in `backend/api/signal_board.py`.
* `PlannedSignal` contract exists in `contracts/signal_board.py`.
* Manual review states already exist:

  * `pending`
  * `ignored`
  * `watching`
  * `expired`
* Existing review endpoints already enforce admission.
* Existing Signal Board UI already supports:

  * filters
  * pagination
  * strategy selector
  * list/detail
  * quick review
  * ignore reason
  * C2 disclaimer copy
* C0/C1/C2 admission boundary is accepted and must not be loosened.

Do not repeat:

* Do not rebuild Signal Board layout.
* Do not redesign filters or pagination.
* Do not add charts.
* Do not add broker API.
* Do not add live trading.
* Do not add real-time refresh.
* Do not add strategy ranking.
* Do not change B-module validation logic.
* Do not change C0/C1/C2 semantics.

## Existing Implementation Risk

Current Signal Board review action can mark a signal as `watching`, `ignored`, or `expired`, but it does not yet create a structured Action Plan.

This is not enough for the project endpoint.

A planned signal without a structured Action Plan leaves too much ambiguity:

* user may not know what to check before action
* user may not know what makes the signal invalid today
* user may not know whether the signal is still fresh
* user may not record skip / partial execution reason
* future review cannot tell whether the user followed the plan or improvised

C3 fixes that by adding a deterministic Action Plan layer.

## Core Design Rule

Action Plan is generated from existing `PlannedSignal` and its metadata.

Action Plan must be deterministic or rule-based as much as possible.

LLM is not allowed to invent trade conditions, prices, quantities, stop loss, take profit, or position sizing.

Allowed sources:

* `PlannedSignal`
* `strategy_core` output fields already stored in signal metadata
* signal date
* intended execution date
* current price snapshot stored at signal generation
* risk flags
* evidence status
* snapshot hash
* strategy id / version / revision id
* review status

Forbidden sources:

* LLM memory
* current market guesses
* unverified news
* live price assumptions
* user-facing “AI thinks this is good”
* any broker or order placement API

## C3 Output Concept

Action Plan is not a buy/sell recommendation.

Action Plan is a structured checklist for a human to decide whether and how to handle an already admitted planned signal.

User-facing language must use neutral terms:

Allowed:

* 计划动作
* 入场 / 离场
* 处理条件
* 放弃条件
* 不可执行原因
* 人工确认
* 记录处理结果
* 部分执行记录
* 今日不处理

Forbidden:

* 推荐买入
* 推荐卖出
* 立即买入
* 立即卖出
* 保证盈利
* 稳定盈利
* 实盘可用
* 一键下单
* 自动交易
* 最佳策略
* 策略排名
* 目标价
* AI建议买入
* AI建议卖出

Important exception:

* Required disclaimer may contain `不会自动交易`.
* Do not ban this phrase.

## Data Model

Create a new contract:

`contracts/action_plan.py`

### ActionPlan

```python
class ActionPlan(BaseModel):
    action_plan_id: str
    signal_id: str

    strategy_id: str
    strategy_version: str
    strategy_revision_id: str | None
    snapshot_hash: str

    symbol: str
    planned_action: Literal["enter", "exit"]

    signal_date: date
    intended_execution_date: date
    action_plan_date: date

    status: Literal[
        "draft",
        "ready_for_human",
        "user_marked_execute",
        "user_marked_skip",
        "user_marked_partial",
        "expired"
    ]

    freshness_status: Literal[
        "fresh",
        "stale",
        "expired"
    ]

    execution_window:
        planned_date: date
        valid_for_date: date
        expires_after_date: date

    pre_action_checks: list[ActionCheck]
    invalidation_checks: list[ActionCheck]
    risk_warnings: list[str]

    user_decision: UserActionDecision | None

    created_at: datetime
    updated_at: datetime
```

### ActionCheck

```python
class ActionCheck(BaseModel):
    check_id: str
    label: str
    source: Literal[
        "strategy_core",
        "signal_metadata",
        "risk_flag",
        "system_rule"
    ]
    status: Literal[
        "pass",
        "warning",
        "blocked",
        "unknown"
    ]
    blocking: bool
    detail: str
```

### UserActionDecision

```python
class UserActionDecision(BaseModel):
    decision: Literal["execute", "skip", "partial", "expired"]
    decided_at: datetime
    decided_by: str
    reason: str | None
    manual_notes: str | None
```

## Deterministic C3 Rules

Implement these rules in code. Do not ask the user to choose thresholds.

### Freshness Rule

```text
if today <= intended_execution_date:
    freshness_status = fresh
elif today == intended_execution_date + 1 trading day:
    freshness_status = stale
else:
    freshness_status = expired
```

MVP simplification:

* If trading calendar helper exists, use it.
* If not, use date comparison and mark calendar precision as `unknown`.
* Do not invent trading days through LLM.

### Blocking Rules

Action Plan is blocked if any of the following is true:

```text
signal.lifecycle_state_at_generation != prototype_passed
signal.evidence_status == blocked
signal.review_status == ignored
signal.review_status == expired
freshness_status == expired
```

### Warning Rules

Action Plan shows warning if any of the following is true:

```text
signal.evidence_status == warning
signal.risk_flags is not empty
freshness_status == stale
signal.quantity is None
signal.current_price is None
```

### Pre-action Checks

Every Action Plan must include at least these checks:

```text
1. Signal admission check
   source: signal_metadata
   pass only if lifecycle_state_at_generation == prototype_passed

2. Date freshness check
   source: system_rule
   pass / warning / blocked according to freshness_status

3. Evidence status check
   source: risk_flag
   pass if clean, warning if warning, blocked if blocked

4. Risk flags check
   source: risk_flag
   pass if empty, warning if non-empty

5. Snapshot linkage check
   source: signal_metadata
   pass if snapshot_hash exists

6. Strategy revision linkage check
   source: signal_metadata
   pass if strategy_revision_id exists
```

### Invalidation Checks

Every Action Plan must include:

```text
1. expired_signal
   blocking if freshness_status == expired

2. blocked_by_evidence
   blocking if evidence_status == blocked

3. already_ignored
   blocking if review_status == ignored

4. already_expired
   blocking if review_status == expired
```

## API Design

Modify or add under existing Signal Board backend. Do not create a second unrelated app.

### New endpoints

```text
GET /api/signals/{signal_id}/action-plan
POST /api/signals/{signal_id}/action-plan/decision
```

### GET /api/signals/{signal_id}/action-plan

Behavior:

* Must call `db.get_admitted_signal(signal_id)` first.
* If not admitted, return 404.
* Builds Action Plan from admitted signal.
* Does not mutate signal.
* Does not mutate review_status.
* Returns `ActionPlan`.

This endpoint can generate Action Plan on read, but if persistence is implemented, persisted data must be upserted deterministically.

MVP recommendation:

* Generate on read.
* Persist only user decision.
* Do not create unnecessary storage unless decision recording requires it.

### POST /api/signals/{signal_id}/action-plan/decision

Behavior:

* Must call `db.get_admitted_signal(signal_id)` first.
* If not admitted, return 404.
* Accepts one of:

  * execute
  * skip
  * partial
  * expired
* Must require `reason` for skip / partial / expired.
* Must not place orders.
* Must not call broker APIs.
* Must update or insert user Action Plan decision.
* Should update Signal Board review status using existing mapping:

  * execute → watching
  * partial → watching
  * skip → ignored
  * expired → expired
* Must return updated ActionPlan.

Decision mapping:

```text
execute:
  review_status = watching
  reason optional

partial:
  review_status = watching
  reason required

skip:
  review_status = ignored
  reason required

expired:
  review_status = expired
  reason required
```

Do not add `approved_for_execution`.
Do not add `executed`.
Do not add `filled`.
Do not add `order_id`.

Those belong to Execution Log, not C3.

## Database Design

MVP preferred storage:

Create table:

```sql
CREATE TABLE IF NOT EXISTS action_plan_decisions (
    action_plan_id TEXT PRIMARY KEY,
    signal_id TEXT NOT NULL,
    decision TEXT NOT NULL,
    reason TEXT,
    manual_notes TEXT,
    decided_by TEXT NOT NULL,
    decided_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

Constraints:

* `signal_id` must reference an admitted planned signal by API check.
* Do not rely only on database foreign key to enforce admission.
* The API must still call `get_admitted_signal`.
* One latest decision per signal is enough for C3.
* Full append-only execution history belongs to C4.

If the current project already has a generic audit/event table, use it only if it is simple. Do not build a full ledger in C3.

## Frontend Design

Use existing Signal Board detail page.

Modify:

`frontend/app/signals/[signal_id]/page.tsx`

Add one panel:

```text
Action Plan / 人工处理计划
```

Do not create a new top-level page unless implementation is simpler.

The panel should show:

```text
- 计划动作：入场 / 离场
- 计划处理日期
- 新鲜度：fresh / stale / expired 的中文标签
- 执行前检查
- 放弃条件 / 阻断条件
- 风险提示
- 人工处理按钮：
  - 准备执行
  - 部分执行
  - 今日放弃
  - 标记过期
- 原因输入框
- 免责声明：
  这是人工处理计划，不是买卖建议，不会自动交易。
```

Button language:

Allowed:

```text
准备执行
部分执行
今日放弃
标记过期
```

Forbidden:

```text
买入
卖出
一键下单
立即执行
自动执行
```

If an Action Plan is blocked:

* disable `准备执行`
* show blocking reason
* allow `今日放弃` and `标记过期`

If stale:

* show warning
* do not block by default unless expired

If expired:

* disable `准备执行`
* show expired reason

## API Client

Modify:

`frontend/lib/api-client.ts`

Add:

```ts
export interface ActionCheck { ... }
export interface UserActionDecision { ... }
export interface ActionPlan { ... }

export async function getActionPlan(signalId: string): Promise<ActionPlan>
export async function submitActionDecision(signalId: string, request: ActionPlanDecisionRequest): Promise<ActionPlan>
```

Do not remove existing `reviewSignal`.
Do not break current Signal Board quick review.

## Tests

Create:

`tests/test_c3_action_plan_boundary.py`

Add API tests.

### Required API tests

1. `test_get_action_plan_requires_admitted_signal`

   * legacy / missing admission signal returns 404

2. `test_get_action_plan_for_admitted_signal_returns_checks`

   * admitted signal returns 200
   * contains signal_id
   * contains pre_action_checks
   * contains invalidation_checks
   * contains disclaimer-safe fields only

3. `test_action_plan_blocks_expired_signal`

   * expired freshness produces blocked check
   * cannot be marked execute if expired

4. `test_action_decision_skip_requires_reason`

   * skip without reason returns 400

5. `test_action_decision_partial_requires_reason`

   * partial without reason returns 400

6. `test_action_decision_does_not_accept_order_fields`

   * request with order_id / broker / fill_price / fill_qty is rejected or ignored with test asserting no such fields are stored

7. `test_action_decision_updates_review_status_mapping`

   * execute → watching
   * partial → watching
   * skip → ignored
   * expired → expired

8. `test_action_plan_decision_rejects_unadmitted_direct_id`

   * POST direct-id mutation cannot update unadmitted signal

9. `test_batch_or_mutation_bypass_not_introduced`

   * if no batch action-plan endpoint exists, assert no such public route exists or no client function exists
   * if added, must enforce admitted-only

### Required frontend/copy tests

Modify or create:

`tests/test_c3_action_plan_copy_boundary.py`

Check detail page and API client source.

Required phrases:

```text
人工处理计划
不是买卖建议
不会自动交易
```

Forbidden phrases:

```text
推荐买入
推荐卖出
立即买入
立即卖出
一键下单
自动执行
保证盈利
稳定盈利
实盘可用
目标价
最佳策略
策略排名
```

Do not forbid:

```text
不会自动交易
```

### Regression tests

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_c3_action_plan_boundary.py tests/test_c3_action_plan_copy_boundary.py -q
.venv\Scripts\python.exe -m pytest tests/test_c2_signal_board_decision_boundary.py tests/test_signal_board_ux_polish.py tests/test_signal_api.py -q
.venv\Scripts\python.exe -m pytest tests/test_c1_signal_board_admission_risk.py tests/test_c1_admission_bypass.py -q
.venv\Scripts\python.exe -m pytest tests/test_c0_admission_boundary.py tests/test_c0_anti_bypass.py -q
.venv\Scripts\python.exe -m pytest tests/test_b6_validation_flow.py tests/test_b6_c_admission_gate.py tests/test_b6_no_shortcuts.py -q
.venv\Scripts\python.exe -m unittest tests.test_b5_oos_budget tests.test_b5_oos_controller tests.test_b5_report_builder tests.test_b5_cost_stress tests.test_b5_control_comparison tests.test_b5_gate_v2 tests.test_b5_gate_explanation tests.test_b5_promotion_boundary tests.test_b5_vertical_flow tests.test_b5_compatibility -v
.venv\Scripts\python.exe -m unittest discover -s tests -p "test_b4*.py" -v
.venv\Scripts\python.exe -m pytest tests/ -x --tb=short -q
```

## File Map

Expected files.

Modify:

```text
contracts/signal_board.py
frontend/lib/api-client.ts
frontend/app/signals/[signal_id]/page.tsx
backend/api/signal_board.py
backend/db/signal_board.py
```

Create if needed:

```text
contracts/action_plan.py
tests/test_c3_action_plan_boundary.py
tests/test_c3_action_plan_copy_boundary.py
docs/verification/C3_VERIFICATION.md
```

Do not modify unless clearly necessary:

```text
backend/services/c_admission_gate.py
backend/db/strategy.py
contracts/strategy.py
backend/scripts/generate_planned_signals.py
B-module validation files
C0/C1/C2 verification docs
```

If any protected file must be touched, final report must explain why.

## Task C3-1: Inspect Current Signal Board and Freeze Scope

Files:

* Read only:

  * `backend/api/signal_board.py`
  * `backend/db/signal_board.py`
  * `contracts/signal_board.py`
  * `frontend/lib/api-client.ts`
  * `frontend/app/signals/page.tsx`
  * `frontend/app/signals/[signal_id]/page.tsx`
  * C0/C1/C2 verification docs

Steps:

* [ ] Confirm existing Signal Board list/detail/review works.
* [ ] Confirm C2 admission enforcement is still present.
* [ ] Confirm no existing Action Plan implementation exists.
* [ ] Write short implementation note:

  * existing pieces to reuse
  * missing pieces to add
  * files that must not be touched

Commit only if a planning note is created. Otherwise no commit.

## Task C3-2: Add Action Plan Contract and Deterministic Builder

Files:

* Create: `contracts/action_plan.py`
* Modify or create focused service:

  * recommended: `backend/services/action_plan_builder.py`

Steps:

* [ ] Add `ActionPlan`, `ActionCheck`, `UserActionDecision`, `ActionPlanDecisionRequest`.
* [ ] Implement deterministic builder:

  * input: admitted `PlannedSignal`
  * output: `ActionPlan`
* [ ] Add freshness rule.
* [ ] Add blocking rules.
* [ ] Add warning rules.
* [ ] Add pre-action checks.
* [ ] Add invalidation checks.
* [ ] No LLM calls.
* [ ] No external data calls.
* [ ] No broker fields.

Tests:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_c3_action_plan_boundary.py -q
```

Commit:

```powershell
git add contracts/action_plan.py backend/services/action_plan_builder.py tests/test_c3_action_plan_boundary.py
git commit -m "feat: C3 add deterministic Action Plan builder"
```

## Task C3-3: Add Action Plan API Endpoints

Files:

* Modify: `backend/api/signal_board.py`
* Modify: `backend/db/signal_board.py` if persistence needed
* Test: `tests/test_c3_action_plan_boundary.py`

Steps:

* [ ] Add `GET /api/signals/{signal_id}/action-plan`.
* [ ] Add `POST /api/signals/{signal_id}/action-plan/decision`.
* [ ] Both endpoints must call `get_admitted_signal(signal_id)` first.
* [ ] POST must require reason for skip / partial / expired.
* [ ] POST must not accept broker/order/fill fields.
* [ ] POST must map decision to existing review_status.
* [ ] POST must return updated ActionPlan.
* [ ] No batch endpoint unless explicitly justified.

Tests:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_c3_action_plan_boundary.py -q
.venv\Scripts\python.exe -m pytest tests/test_signal_api.py -q
```

Commit:

```powershell
git add backend/api/signal_board.py backend/db/signal_board.py tests/test_c3_action_plan_boundary.py
git commit -m "feat: C3 expose admitted Action Plan endpoints"
```

## Task C3-4: Add Action Plan Panel to Existing Detail Page

Files:

* Modify: `frontend/lib/api-client.ts`
* Modify: `frontend/app/signals/[signal_id]/page.tsx`
* Create/modify component if useful:

  * `frontend/components/ActionPlanPanel.tsx`

Steps:

* [ ] Add Action Plan client types.
* [ ] Add `getActionPlan`.
* [ ] Add `submitActionDecision`.
* [ ] Load Action Plan on signal detail page.
* [ ] Render Action Plan panel.
* [ ] Keep existing ReviewForm.
* [ ] Do not remove existing audit info.
* [ ] Disable prepare-execute button when blocked.
* [ ] Require reason UI for skip / partial / expired.
* [ ] Use neutral labels only.

UI copy required:

```text
人工处理计划
这是人工处理计划，不是买卖建议，不会自动交易。
```

Tests:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_c3_action_plan_copy_boundary.py -q
```

Commit:

```powershell
git add frontend/lib/api-client.ts frontend/app/signals/[signal_id]/page.tsx frontend/components/ActionPlanPanel.tsx tests/test_c3_action_plan_copy_boundary.py
git commit -m "feat: C3 add Action Plan panel to Signal detail"
```

## Task C3-5: Guardrails and Regression

Files:

* Modify:

  * `tests/test_c3_action_plan_boundary.py`
  * `tests/test_c3_action_plan_copy_boundary.py`
  * `tests/test_c2_signal_board_decision_boundary.py` only if needed

Steps:

* [ ] Add direct-id mutation bypass tests.
* [ ] Add forbidden order/broker field tests.
* [ ] Add copy guard tests.
* [ ] Add no-broker/no-auto-execution assertions.
* [ ] Re-run C3 focused tests.
* [ ] Re-run C2/C1/C0/B6/B5/B4 focused regressions.
* [ ] Run full pytest.

Commit:

```powershell
git add tests/test_c3_action_plan_boundary.py tests/test_c3_action_plan_copy_boundary.py
git commit -m "test: C3 lock Action Plan execution boundary"
```

## Task C3-6: Verification Documentation

Files:

* Create: `docs/verification/C3_VERIFICATION.md`

Required sections:

```markdown
# C3 Action Plan Human Execution Boundary Verification

## Status

## Accepted Commits

## What C3 Proves

## What C3 Does Not Prove

## Existing Signal Board Reused

## New Files

## Modified Files

## API Boundary

## UI Boundary

## Test Results

## Git Status

## Known Boundaries

## Next Work
```

What C3 proves:

* Admitted planned signals can produce Action Plan.
* Unadmitted direct-id cannot produce or mutate Action Plan.
* Action Plan is checklist/discipline layer, not new signal generation.
* User decision can be recorded as execute / skip / partial / expired.
* Existing review_status mapping remains compatible.
* No broker/order/fill fields are introduced.
* No auto-trading or profit language is introduced.

What C3 does not prove:

* It does not prove strategy profitability.
* It does not execute orders.
* It does not connect to broker.
* It does not record actual fill.
* It does not calculate realized P&L.
* It does not perform post-market review.
* It does not replace B-module validation.

Verification commands must include real outputs:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_c3_action_plan_boundary.py tests/test_c3_action_plan_copy_boundary.py -q
.venv\Scripts\python.exe -m pytest tests/test_c2_signal_board_decision_boundary.py tests/test_signal_board_ux_polish.py tests/test_signal_api.py -q
.venv\Scripts\python.exe -m pytest tests/test_c1_signal_board_admission_risk.py tests/test_c1_admission_bypass.py -q
.venv\Scripts\python.exe -m pytest tests/test_c0_admission_boundary.py tests/test_c0_anti_bypass.py -q
.venv\Scripts\python.exe -m pytest tests/test_b6_validation_flow.py tests/test_b6_c_admission_gate.py tests/test_b6_no_shortcuts.py -q
.venv\Scripts\python.exe -m unittest tests.test_b5_oos_budget tests.test_b5_oos_controller tests.test_b5_report_builder tests.test_b5_cost_stress tests.test_b5_control_comparison tests.test_b5_gate_v2 tests.test_b5_gate_explanation tests.test_b5_promotion_boundary tests.test_b5_vertical_flow tests.test_b5_compatibility -v
.venv\Scripts\python.exe -m unittest discover -s tests -p "test_b4*.py" -v
.venv\Scripts\python.exe -m pytest tests/ -x --tb=short -q
git status --short
git log --oneline -10
```

Commit:

```powershell
git add docs/verification/C3_VERIFICATION.md
git commit -m "docs: C3 Action Plan boundary verification"
```

## Acceptance Criteria

C3 can be accepted only if all are true:

* Existing Signal Board UI is reused, not rebuilt.
* `GET /api/signals/{signal_id}/action-plan` rejects unadmitted signals.
* `POST /api/signals/{signal_id}/action-plan/decision` rejects unadmitted signals.
* Action Plan is deterministic and does not use LLM.
* Action Plan does not create new trading signals.
* Action Plan does not modify strategy rules.
* Action Plan does not use broker/order/fill fields.
* User decision requires reason for skip / partial / expired.
* Decision maps to existing review_status without adding execution status.
* UI copy contains:

  * 人工处理计划
  * 不是买卖建议
  * 不会自动交易
* UI copy does not contain:

  * 推荐买入
  * 推荐卖出
  * 立即买入
  * 立即卖出
  * 一键下单
  * 自动执行
  * 保证盈利
  * 稳定盈利
  * 实盘可用
  * 目标价
  * 最佳策略
  * 策略排名
* C3 focused tests pass.
* C2/C1/C0/B6/B5/B4 regressions pass.
* Full pytest passes.
* `git status --short` is clean.
* Verification doc has real commit hashes and real command outputs.

## Forbidden Scope

C3 must not:

* connect to broker
* create order records
* create fill records
* calculate realized P&L
* implement post-market review
* add automatic trading
* add live price dependency
* add LLM-generated trade advice
* change B-module validation
* loosen C0/C1/C2 admission
* rename neutral `planned_action` labels into buy/sell recommendation language

## Reporting Requirement For Implementing Agent

Final report must not say ACCEPT.

Only allowed final status:

```text
READY_FOR_REVIEW
NEEDS_FIX
```

Final report must include:

```text
- status
- commit hashes
- changed files
- existing files reused
- protected files touched or not touched
- test commands and exact outputs
- git status --short
- git log --oneline -10
- forbidden scope check
- remaining risks
```

If report claims a test exists, the test must exist in the repository.

If report and files disagree, status must be NEEDS_FIX.
