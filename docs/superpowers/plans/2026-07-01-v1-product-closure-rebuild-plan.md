# TraderLens V1 Product Closure Rebuild Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. This plan is product-flow first. Do not implement isolated modules unless they move one accepted user journey closer to completion.

**Goal:** Rebuild TraderLens V1 into a usable product that can run two user journeys end to end: friend-recommended stock to observation/P&L review, and short-video strategy idea to strategy library or rejection registry.

**Architecture:** Keep existing research, strategy-validation, Signal Board, action-plan, live-observation, and review services as reusable infrastructure. Add a real agent orchestration layer above them, with Tushare-backed stock identity, LLM-assisted intent understanding, deterministic workflow routing, visible activity state, product pages for observation, strategy library, daily decisions, and system-owned survival constraints.

**Tech Stack:** FastAPI, SQLite, Pydantic contracts, existing Serenity research services, existing B-module strategy validation services, existing Signal Board/Action Plan APIs, existing live-trade/observation services, Tushare, existing LLMClient, Next.js frontend, pytest.

---

## 1. Why This Plan Exists

The previous plan said the two V1 workflows must run end to end, but execution drifted into scattered module delivery. The result is not useless, but it is not yet a usable product:

- Backend pieces exist.
- Some UI pages exist.
- Workbench chat exists.
- Signal Board exists.
- Execution feedback and observation logic exist.
- Strategy templates and validation pieces exist.
- But the user cannot reliably complete the two required workflows from one coherent product surface.

This plan resets implementation around product closure, not module count.

## 2. Non-Negotiable Product Outcomes

### Outcome A: Friend-Recommended Stock Loop

The user must be able to say:

```text
朋友推荐了宏昌电子，帮我看看值不值得买入
```

The product must support:

```text
Agent understands request
-> Tushare verifies stock identity
-> industry/company research runs or clearly fails
-> system decides whether it is worth watching
-> strategy validation/action plan runs if eligible
-> survival constraints are checked
-> user sees entry/no-entry result
-> user records manual buy
-> stock appears in observation pool
-> user sees daily signal
-> user records manual sell
-> system records P&L and discipline review
```

### Outcome B: Short-Video Strategy Idea Loop

The user must be able to say:

```text
我刷到一个策略，下午两点半买入，第二天早上卖出，帮我验证
```

The product must support:

```text
Agent understands strategy idea
-> extracts testable hypothesis
-> maps to approved frozen template or records candidate/rejection
-> runs validation path if template exists
-> stores OOS/cost/control/gate result
-> passed strategy enters strategy library
-> failed/blocked strategy enters rejection registry
-> user can inspect status and reason in UI
```

## 3. Current Assets Already Built

These are useful and should be reused when correct.

### Agent / Workbench

- `contracts/agent_workbench.py` exists.
- `backend/db/agent_workbench.py` exists.
- `POST /api/agent/workbench/message` exists.
- `GET /api/agent/workbench/{conversation_id}` exists.
- Approval-card decision endpoint exists.
- `/workbench` frontend page exists.
- Timeline/artifact model exists.

Current gap:

- The agent entry has repeatedly been too brittle.
- Product must not rely on keyword-only routing.
- A message must never show fake progress such as `researching` unless a real workflow action or queued job exists.

### Friend Stock / Research

- Friend-stock flow and candidate-pool concepts exist.
- Research APIs and DB tests exist.
- Serenity runner modes exist.
- Ticker verification exists but must be audited for production Tushare usage.

Current gap:

- Workbench to real research orchestration has been unstable.
- Stock identity must be Tushare-backed, not hardcoded.
- Research result must become a user-visible research case, not only hidden artifacts.

### Strategy Idea / Strategy Validation

- `backend/services/strategy_idea_flow.py` exists.
- Strategy template library exists.
- Rejected strategy registry exists.
- Strategy DB/promotion/gate pieces exist.
- B-module validation pieces exist.

Current gap:

- There is no complete strategy-library UI.
- Strategy idea submission from Workbench must not stop at `recorded/rejected` unless that is the deterministic result.
- The user needs to see accepted, validating, blocked, rejected, and approved strategies.

### Signal Board / Action Plan

- `/signals` list page exists.
- `/signals/{signal_id}` detail page exists.
- Signal Board API exists.
- Action Plan builder exists.
- Admission and copy-boundary work exists.

Current gap:

- Signal Board currently behaves like a planned-signal table.
- It is not enough for `my observation pool`.
- It must be integrated with current observation positions and daily decisions.

### Live Observation / Execution / Review

- Workbench execution feedback endpoint exists.
- Manual buy/sell parsing exists.
- Observation positions table exists.
- Daily observation signal generation exists.
- P&L and discipline review logic exists.
- `LiveLoopPanel` exists.

Current gap:

- This is buried inside Workbench.
- The user needs a first-class observation page and trade/review history page.
- Daily signal states must distinguish `hold`, `insufficient_data`, `data_fault`, `risk`, `invalidated`, and `exit`.
- Review attribution must explain whether exit happened because of fixed stop, planned take-profit, planned exit, data fault, insufficient data, or manual deviation.

### Risk Guards / Attribution

- Some risk-related reducers exist, but V1 does not yet have a product-level survival guard layer.
- Market regime blocking, single-position cap, and fixed stop must be system constraints, not user-selected parameters.
- These controls must be validated or justified independently before being allowed to block or modify action plans.

Current gap:

- No first-class `MarketRegimeGuard`.
- No fixed single-position cap wired into capital context and action planning.
- No fixed-stop plan wired from entry plan into observation and review.
- Data insufficiency can be semantically confused with a normal hold state.
- Stop-loss/take-profit wording is not yet a formal attribution system.

### UI / Navigation

- `/workbench`, `/signals`, `/themes` exist.
- Home page exists but has had mojibake and does not behave as the daily product dashboard.

Current gap:

- No daily command center.
- No observation-pool page.
- No strategy-library page.
- No clear product hierarchy.

## 4. Product Information Architecture

V1 must have these top-level surfaces.

### 4.1 Daily Dashboard

Route: `/`

Purpose:

- The first screen the user opens every trading day.
- Shows what needs attention now.

Must show:

- Open observation positions.
- Today's generated signals.
- Market survival guard status when it blocks or downgrades an action.
- Pending approvals.
- Active research cases.
- Active strategy validations.
- Recent execution/P&L review items.
- Clear empty states.

Must not show:

- Technical strategy parameters.
- Raw OOS/threshold/stop-loss controls.
- Broker/order automation claims.

### 4.2 Agent Workbench

Route: `/workbench`

Purpose:

- Natural-language command center.
- User talks; agent orchestrates.

Must show:

- Chat.
- Agent activity stream, step by step.
- Current workflow state.
- Approval cards.
- Links to created research case, strategy case, observation position, signal, or review.

Agent architecture:

```text
User message
-> deterministic prescan for obvious structure
-> LLM intent extraction for semantic understanding
-> Tushare stock identity resolver when stock/entity is present
-> deterministic workflow router
-> workflow action or waiting state
-> artifact/timeline record for every step
```

LLM is allowed to:

- Classify user intent.
- Extract company name, stock code candidate, strategy text, execution feedback text.
- Draft user-facing explanations.

LLM is not allowed to:

- Confirm stock identity.
- Decide trading action.
- Decide strategy pass/fail.
- Calculate P&L.
- Override deterministic gates.

### 4.3 Research Cases

Routes:

- `/research`
- `/research/{research_id}`

Purpose:

- Show friend-stock/company/theme research cases.

Must show:

- Company/ticker identity.
- Research status.
- Industry-chain conclusion.
- Evidence and counter-evidence.
- Whether it is worth watching.
- Candidate-pool snapshot ID.
- Link to strategy validation/action-plan status when created.

### 4.4 Risk Guard and Capital Context

Routes:

- No standalone user parameter page in V1.
- Risk guard status appears inside dashboard, action plan, signal detail, and observation detail.

Purpose:

- Apply survival constraints before action plans become executable.

Must enforce:

- Market extreme circuit guard: blocks only broad selloff, structural breakdown, or liquidity exhaustion. It must not become market timing.
- Single-stock position cap: V1 default is system-owned. The user may provide a plain-language capital pool or trial amount, but must not choose sizing parameters.
- Fixed stop: set at entry as a fixed price below confirmed entry price. It does not trail or move.

Validation rules:

- Market extreme thresholds must be backtested/validated independently.
- Fixed-stop candidates must be validated before becoming the frozen system default.
- Single-stock position cap is a survival constraint and does not need alpha proof, but it must be auditable and deterministic.

User-facing rules:

- The UI shows result-level language: `市场状态阻断`, `资金约束跳过`, `固定失效价已设置`.
- The UI must not ask the user to pick thresholds, stop-loss percentages, or sizing formulas.

### 4.5 Observation Pool

Routes:

- `/observations`
- `/observations/{position_id}`

Purpose:

- Show stocks the user actually observes or holds after manual execution.

Must show:

- Symbol and company.
- Position status: open/closed.
- Entry record.
- Current daily signal.
- Signal state: hold / insufficient_data / data_fault / risk / invalidated / exit.
- Original thesis.
- Invalidation reasons.
- User actions needed today.
- P&L summary after closed.
- Discipline review link.

This is separate from Signal Board.

### 4.6 Signal Board

Routes:

- `/signals`
- `/signals/{signal_id}`

Purpose:

- Show validated planned signals from admitted strategies.

Must show:

- Strategy-generated planned signals.
- Admission metadata.
- Action Plan.
- Human review state.
- Link to create/record manual execution.

Signal Board is not the same as Observation Pool:

- Signal Board = system-generated planned signals.
- Observation Pool = user-observed/held positions and daily follow-up.

### 4.7 Strategy Library

Routes:

- `/strategies`
- `/strategies/{strategy_id}`
- `/strategy-ideas`
- `/strategy-ideas/{idea_id}`
- `/rejected-strategies`

Purpose:

- Show where strategies live.

Must show:

- Approved frozen templates.
- Incoming strategy ideas.
- Template mapping result.
- Validation state.
- Gate outcome.
- Approved strategies.
- Rejected/blocked strategies and reasons.
- Whether future retest is allowed.

### 4.8 Trade Records and Reviews

Routes:

- `/trades`
- `/trades/{trade_id}`
- `/reviews/{review_id}`

Purpose:

- Show user execution feedback, closed trades, realized P&L, and discipline review.

Must show:

- Manual buy/sell records.
- Quantity and confirmed price.
- Realized P&L.
- Exit attribution: fixed stop, planned take-profit, planned exit, manual deviation, data fault, insufficient data, or unclassified.
- Whether plan was followed.
- Skip/deviation reasons.
- Follow-up adjustment.

## 5. Implementation Phases

### Phase 0: Repo Hygiene and Baseline Audit

Goal:

- Make the project easier to reason about before more implementation.

Tasks:

- Remove root-level obsolete Task reports.
- Remove generated caches from the working tree.
- Keep generated files ignored.
- Write a current-state audit that maps existing code to product flows.

Acceptance:

- Root directory contains only active project files.
- No hidden deletion of source/test files.
- Audit names which pages/API/services exist and which user step each supports.

### Phase 1: Agent Entry Rebuild

Goal:

- Make `/workbench` a real agent entry, not keyword routing with a chat UI.

Tasks:

- Define `AgentIntentExtraction` contract.
- Define `StockIdentityResolution` contract.
- Define `WorkflowRouteDecision` contract.
- Implement Tushare-backed stock resolver with deterministic fixture injection for tests.
- Use existing LLMClient for semantic extraction in production mode.
- Keep deterministic final routing separate from LLM extraction.
- Add activity artifacts for every stage.
- Prevent fake `researching` states.

Acceptance examples:

```text
宏昌电子是否值得买入
帮我看一下 603002
朋友推荐了宏昌电子
买入宏昌电子可以吗
我刷到一个策略，下午两点半买入第二天卖出
我已经买入 100 股，成交价 12.34
今天要不要继续拿
```

Each message must route correctly or ask a plain-language clarification.

### Phase 2: Risk Guard and Attribution Foundation

Goal:

- Add survival constraints and honest attribution into the profitable loop before action/observation pages are finalized.

Tasks:

- Design `MarketRegimeGuard` as an independent validation path.
- Define the market states it can return: `ok`, `extreme_breadth_selloff`, `structural_breakdown`, `liquidity_exhaustion`, `data_insufficient`, `data_fault`.
- Define how each state affects action plans: allow, downgrade to observation, or block.
- Add single-position cap as a deterministic capital-context rule. V1 default: one stock may not exceed 10% of the user-provided trading/trial capital pool unless future validation changes the product default.
- Add fixed-stop plan as a frozen entry-plan field. V1 candidate set for validation: 6%, 8%, 10%, 12% below confirmed entry price. The final default must be selected by validation and frozen, not by the user or LLM.
- Add `insufficient_data` as a first-class observation signal state, distinct from `hold`.
- Add exit attribution vocabulary for review: fixed stop, planned take-profit, planned exit, manual deviation, data fault, insufficient data, unclassified.

Acceptance:

```text
action plan requested
-> market survival guard checked
-> capital cap checked
-> fixed stop attached if entry is allowed
-> observation signal never says hold when required data is insufficient
-> review records why an exit happened without claiming discipline enforcement
```

### Phase 3: Friend Stock Product Flow

Goal:

- A friend-recommended stock can move from chat to research case to decision to observation.

Tasks:

- Create or harden a `ResearchCase` API surface.
- From Workbench, verified stock must create a research case.
- Research case must run Serenity or return a clear failed/waiting state.
- Research output must create candidate snapshot only after evidence/counter-evidence exists.
- User approval must be result-level only.
- Survival constraints must run before action plan becomes executable.
- Eligible result must create an action-plan or explicit no-entry decision.
- Action plan must be reachable from UI.

Acceptance:

```text
User: 朋友推荐了宏昌电子，帮我看看
System:
1. identifies and verifies stock
2. creates research case
3. shows research progress
4. shows conclusion
5. creates result-level approval card
6. checks market/capital/fixed-stop constraints
7. creates next action: enter / observe / reject / needs_review
```

### Phase 4: Observation Pool Product Flow

Goal:

- The user can see and manage stocks being observed/held.

Tasks:

- Build `/observations` list page.
- Build `/observations/{position_id}` detail page.
- Connect Workbench manual buy/sell feedback to observation pages.
- Connect daily signal generation to observation pages.
- Display `insufficient_data` separately from `hold`.
- Show open/closed status and P&L.
- Link discipline review.

Acceptance:

```text
record buy
-> position appears in /observations
-> generate daily signal
-> signal appears on dashboard and observation detail
-> record sell
-> position closes
-> P&L, fixed-stop/take-profit/manual attribution, and discipline review become visible
```

### Phase 5: Strategy Product Flow

Goal:

- Strategy ideas are visible from submission to approval/rejection.

Tasks:

- Build `/strategy-ideas` list/detail pages.
- Build `/strategies` approved strategy library.
- Build `/rejected-strategies` registry page.
- Connect Workbench strategy messages to strategy idea records.
- Run template mapping visibly.
- If approved template fits, create validation case.
- If not, create candidate/rejection record with reason.
- Display B-module validation artifacts when available.

Acceptance:

```text
User: 下午两点半买入，第二天早上卖出，这个策略能不能做
System:
1. extracts strategy idea
2. maps to approved template or rejects/candidates it
3. records validation state
4. shows status in strategy UI
5. passed strategies appear in /strategies
6. failed strategies appear in /rejected-strategies
```

### Phase 6: Daily Dashboard

Goal:

- The user opens one page and knows today's required actions.

Tasks:

- Replace current home page with daily dashboard.
- Show open observations, today's signals, survival guard blocks/downgrades, pending approvals, active research, active strategy validations, and recent reviews.
- Add links to Workbench, Observation Pool, Signal Board, Strategy Library.
- Fix any mojibake on home/workbench pages.

Acceptance:

- User does not need to know which module to open first.
- Empty state explains what to ask the Agent.
- Non-technical wording only.

### Phase 7: E2E Product Acceptance

Goal:

- Prove the product, not just services.

Required tests:

1. Friend-stock E2E:

```text
chat input
-> verified stock identity
-> research case
-> result-level approval
-> action/no-action result
-> market/capital/fixed-stop guard result
-> manual buy
-> observation pool
-> daily signal
-> manual sell
-> P&L and discipline review
```

2. Strategy idea E2E:

```text
chat input
-> strategy idea
-> extraction
-> template mapping
-> validation or rejection
-> strategy library or rejected registry
-> visible UI/API state
```

3. UI smoke:

```text
dashboard
workbench
research case
observations
signals
strategies
rejected strategies
trade review
```

4. Boundary tests:

- No technical approval fields.
- No profit guarantee.
- No automatic trading claims.
- No fake progress state.
- Tushare data fault blocks or downgrades clearly.
- Market/data insufficiency is not mislabeled as hold.
- Fixed-stop and take-profit are recorded as attribution, not profit promises or discipline guarantees.
- LLM failure asks clarification or records extraction failure; it does not randomly route.

## 6. Definition of Done

V1 is not done until both workflows can be demonstrated from the browser:

### Browser Demo A

```text
Open dashboard
-> ask Agent about a friend-recommended stock
-> see Agent activity
-> see research case
-> approve result-level next step
-> see survival guard result
-> record buy
-> see stock in observation pool
-> generate/view daily signal
-> record sell
-> see P&L and discipline review
```

### Browser Demo B

```text
Open dashboard
-> ask Agent to evaluate a short-video strategy
-> see strategy idea extraction
-> see template mapping
-> see validation/rejection result
-> see approved strategy or rejected registry entry
```

If either demo requires database poking, manual field editing, hidden scripts, or interpreting technical parameters, V1 is not done.

## 7. Anti-Patterns to Block

- Do not add another isolated backend module without a page/API that advances one user journey.
- Do not mark a workflow `researching`, `validating`, or `running` unless a real job/action exists.
- Do not treat keyword matching as the Agent brain.
- Do not let LLM verify stock identity.
- Do not let LLM decide trading action, strategy pass/fail, or P&L.
- Do not bury observation status in chat timeline only.
- Do not treat Signal Board as the observation pool.
- Do not call service-layer tests `product E2E`.
- Do not ask the user to choose market guard thresholds, position cap, or stop-loss percentage.
- Do not describe stop-loss/take-profit attribution as proof of discipline or profit protection.
- Do not label missing or stale data as hold.

## 8. Immediate Next Tasks

### Task P0-1: Baseline Product Audit

Create a document listing:

- Each product step.
- Existing files/API/page that support it.
- Missing files/API/page.
- Current test coverage.
- Whether a user can perform the step in browser.
- Where market guard, position cap, fixed stop, insufficient-data state, and attribution should fit.

### Task P0-2: Agent Entry Design Freeze

Write a short design for:

- LLM intent extraction.
- Tushare stock identity.
- Deterministic routing.
- Activity timeline.
- Failure/clarification handling.

No implementation until design is reviewed.

### Task P0-3: Risk and Attribution Design Freeze

Write a short design for:

- Market extreme circuit guard.
- Single-stock position cap.
- Fixed stop validation and freeze rule.
- `insufficient_data` versus `hold`.
- Exit attribution vocabulary and review display.

No implementation until design is reviewed.

### Task P1-1: Agent Entry Implementation

Implement only after P0-2 approval.

### Task P1-2: Risk Guard and Attribution Implementation

Implement only after P0-3 approval.

### Task P2-1: Observation Pool Page

Build the page that answers:

```text
我现在观察/持有哪些股票？今天要做什么？
```

### Task P3-1: Strategy Library Pages

Build the pages that answer:

```text
我们的策略在哪里？哪个通过了？哪个失败了？为什么？
```

### Task P4-1: Dashboard

Make `/` the daily operating page.

## 9. Current Cleanup Notes

The root-level Task12 report files were obsolete process reports and should not remain in the project root. Future task reports should either be summarized in the final assistant response or placed under `docs/verification/` when they are durable verification artifacts.

Generated caches such as `.pytest_cache/`, `frontend/.next/`, and `*.tsbuildinfo` are not source.

`nul` has been removed from Git tracking and ignored. Do not recreate it.
