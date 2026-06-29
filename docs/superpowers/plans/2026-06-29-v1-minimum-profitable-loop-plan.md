# V1 Minimum Profitable Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build one Web UI with an embedded agent that can run the two V1 profitable loops end to end: friend-recommended single stock and short-video strategy idea validation.

**Architecture:** Add a unified Agent Workbench layer above the existing research, validation, Signal Board, and Action Plan services. Keep deterministic trading decisions in reducers/services, keep LLM usage limited to extraction, mapping, explanation, and summary drafting, and store every approval, artifact ID, market-data state, execution interpretation, position observation, and review record for audit.

**Tech Stack:** FastAPI, SQLite, Pydantic contracts, existing Serenity research services, existing B-module strategy validation services, existing Signal Board/Action Plan APIs, Tushare adapters, Next.js frontend, pytest/unittest.

---

## 0. Scope Decision

This plan intentionally stops using A/B/C as delivery boundaries. The delivery boundary is now:

1. Friend-recommended single-stock profitable loop.
2. Short-video strategy idea validation loop.
3. One Web UI agent conversation that can drive both loops.

Existing A/B/C code remains reusable infrastructure, but the user-facing product must feel like one agent workflow.

---

## 1. Current Chain Audit

### Existing And Reusable

- Research theme, conversation, Serenity candidate discovery, evidence, ticker verification:
  - `backend/api/research.py`
  - `backend/db/research.py`
  - `backend/services/serenity_agent.py`
  - `backend/services/serenity_tools.py`
  - `backend/services/research_validation.py`
  - `contracts/research.py`
- Strategy template and B validation foundation:
  - `backend/services/strategy_template_library.py`
  - `contracts/strategy.py`
  - `backend/db/strategy.py`
  - `backend/services/strategy_promotion_reducer.py`
  - `backend/services/research_protocol_freezer.py`
- Signal Board and Action Plan foundation:
  - `contracts/signal_board.py`
  - `contracts/action_plan.py`
  - `backend/api/signal_board.py`
  - `backend/db/signal_board.py`
  - `backend/services/action_plan_builder.py`
  - `frontend/app/signals/page.tsx`
  - `frontend/components/ActionPlanPanel.tsx`
- Tushare foundation:
  - `backend/app/tushare/tushare_client.py`
  - `backend/app/tushare/tushare_data_source.py`

### Gaps Blocking V1

- No unified agent workbench API.
- No Web UI chat surface that can drive research, validation, execution cards, observation pool, and review.
- No result-level approval card contract.
- Existing research confirmation still asks for technical snapshot fields.
- Strategy Template Library lacks full PRD fields: `market_fit`, `forbidden_market`, `entry_rules`, `exit_rules`, `risk_rules`, `position_sizing_rules`, `validation_gate_profile`, `frozen_template_hash`.
- No `RejectedStrategyRegistry`.
- No short-video `strategy_idea` intake and validation path.
- No candidate-template evaluation path.
- No deterministic recommendation reducer for `强建议执行 / 可执行 / 暂停观察 / 不执行 / 放弃`.
- No `MarketDataFault` state machine.
- No live observation Tushare adapter separate from frozen backtest data.
- No Capital Context.
- No execution card contract.
- No Execution Observation Log with natural-language interpretation.
- No observation pool after buy.
- No daily hold/sell/risk/invalidated signal records.
- No sell feedback capture.
- No user-approved P&L record.
- No discipline review.
- Existing C3 UI and several docs contain mojibake Chinese copy; user-facing copy must be fixed before final acceptance.

---

## 2. File Structure To Add Or Modify

### Contracts

- Create `contracts/approval_card.py`: result-level approval card states and decisions.
- Create `contracts/agent_workbench.py`: agent session, message, artifact reference, workflow state.
- Create `contracts/strategy_idea.py`: short-video strategy idea, extracted claim, validation status.
- Create `contracts/rejected_strategy.py`: rejected/blocked/needs-review registry item.
- Create `contracts/live_trade.py`: Capital Context, MarketDataFault, Execution Card, Execution Observation Log, Observation Position, Daily Observation Signal, P&L Record, Discipline Review.
- Modify `contracts/action_plan.py`: add V1 execution-card linkage without broker/order fields.
- Modify `contracts/signal_board.py`: ensure planned signal metadata can link to approved template, capital context, and observation position.

### Backend Services

- Create `backend/services/approval_card_reducer.py`: deterministic approval-card state transitions.
- Create `backend/services/agent_workbench_orchestrator.py`: top-level workflow orchestration.
- Create `backend/services/friend_stock_flow.py`: friend-recommended stock workflow.
- Create `backend/services/strategy_idea_flow.py`: short-video strategy workflow.
- Create `backend/services/rejected_strategy_registry.py`: persistence-facing registry service.
- Create `backend/services/template_candidate_evaluator.py`: candidate template gate; never live until approved.
- Create `backend/services/recommendation_reducer.py`: deterministic recommendation level reducer.
- Create `backend/services/capital_context.py`: derive cash amount, share count, and insufficient-funds result.
- Create `backend/services/live_market_data.py`: Tushare current-price/daily facts adapter and MarketDataFault mapping.
- Create `backend/services/execution_interpreter.py`: parse user execution feedback into draft structured record.
- Create `backend/services/observation_pool.py`: position lifecycle and daily observation signals.
- Create `backend/services/discipline_review.py`: final review and P&L record from approved execution details.
- Modify `backend/services/strategy_template_library.py`: extend frozen template metadata.
- Modify `backend/services/action_plan_builder.py`: stop at Action Plan; let execution card/recommendation reducer handle live recommendation.

### Backend DB

- Create `backend/db/agent_workbench.py`: sessions, messages, artifact refs, approval cards.
- Create `backend/db/live_trade.py`: capital contexts, execution cards, execution logs, observation positions, daily signals, P&L records, discipline reviews.
- Create `backend/db/rejected_strategy.py`: rejected strategy registry.
- Modify `backend/db/research.py`: add approval-card linkage for confirmed candidate pool.
- Modify `backend/db/strategy.py`: store extended template metadata and rejected-strategy references if not already present.

### Backend API

- Create `backend/api/agent_workbench.py`: single chat and workflow endpoint surface.
- Create `backend/api/live_trade.py`: execution card, observation pool, daily signal, sell feedback, discipline review endpoints.
- Create `backend/api/strategy_ideas.py`: short-video strategy idea endpoints.
- Modify `backend/app/main.py`: include new routers and initialize new databases.
- Keep `backend/api/research.py` and `backend/api/signal_board.py` as internal/reused APIs, not the user's primary surface.

### Frontend

- Create `frontend/app/workbench/page.tsx`: primary agent workbench page.
- Create `frontend/components/AgentChatPanel.tsx`: chat surface.
- Create `frontend/components/ApprovalCard.tsx`: result-level approvals only.
- Create `frontend/components/ResearchSummaryCard.tsx`: company/industry value, potential, risks, counter-evidence.
- Create `frontend/components/StrategyValidationCard.tsx`: plain-language validation result and artifact IDs.
- Create `frontend/components/ExecutionCard.tsx`: live recommendation card.
- Create `frontend/components/ObservationPoolPanel.tsx`: bought positions and daily signal state.
- Create `frontend/components/DisciplineReviewPanel.tsx`: sell review, P&L record, plan adherence.
- Create `frontend/components/StrategyIdeaCard.tsx`: short-video strategy parsing and validation status.
- Modify `frontend/lib/api-client.ts`: add agent workbench, live trade, and strategy idea clients.
- Modify `frontend/app/page.tsx` if present: redirect or link to `/workbench`.
- Modify existing Signal Board pages only where needed to link to workbench context.

### Tests

- Create `tests/test_v1_approval_card.py`.
- Create `tests/test_v1_agent_workbench_api.py`.
- Create `tests/test_v1_friend_stock_flow.py`.
- Create `tests/test_v1_strategy_idea_flow.py`.
- Create `tests/test_v1_rejected_strategy_registry.py`.
- Create `tests/test_v1_template_library_prd_fields.py`.
- Create `tests/test_v1_recommendation_reducer.py`.
- Create `tests/test_v1_market_data_fault.py`.
- Create `tests/test_v1_capital_context.py`.
- Create `tests/test_v1_execution_interpreter.py`.
- Create `tests/test_v1_observation_pool.py`.
- Create `tests/test_v1_discipline_review.py`.
- Create `tests/test_v1_e2e_profitable_loop.py`.
- Create or update frontend tests for workbench rendering and no technical approval prompts.

---

## 3. Implementation Tasks

### Task 1: Add Approval Card Contract And Reducer

**Files:**
- Create: `contracts/approval_card.py`
- Create: `backend/services/approval_card_reducer.py`
- Create: `tests/test_v1_approval_card.py`

- [ ] **Step 1: Write failing tests**

Test that allowed decisions are exactly:
- `continue`
- `stop`
- `downgrade_to_observation`
- `enter_risk_capped_live_execution`
- `accept_execution_record_interpretation`

Test that approval cards cannot ask for:
- candidate technical quality
- strategy parameters
- OOS windows
- thresholds
- stop-loss
- liquidity rules
- manual execution fields

Run:
```powershell
.venv\Scripts\python.exe -m pytest tests/test_v1_approval_card.py -q
```

Expected before implementation: import or attribute failure.

- [ ] **Step 2: Implement contracts**

`ApprovalCard` must include:
- `approval_card_id`
- `workflow_id`
- `stage`
- `title`
- `plain_language_summary`
- `allowed_decisions`
- `blocked_technical_decisions`
- `artifact_ids`
- `created_at`
- `decided_at`
- `decision`
- `decided_by`

- [ ] **Step 3: Implement reducer**

The reducer must:
- reject unknown decisions
- reject technical-decision labels
- require an artifact ID for every approval card
- be deterministic and not call LLM

- [ ] **Step 4: Verify**

Run:
```powershell
.venv\Scripts\python.exe -m pytest tests/test_v1_approval_card.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add contracts/approval_card.py backend/services/approval_card_reducer.py tests/test_v1_approval_card.py
git commit -m "feat: add V1 result approval cards"
```

### Task 2: Add Unified Agent Workbench Persistence

**Files:**
- Create: `contracts/agent_workbench.py`
- Create: `backend/db/agent_workbench.py`
- Create: `tests/test_v1_agent_workbench_db.py`

- [ ] **Step 1: Write failing DB tests**

Cover:
- create session
- append user/agent messages
- attach artifact references
- attach approval cards
- retrieve full session timeline in insertion order
- no technical approval payload is accepted

Run:
```powershell
.venv\Scripts\python.exe -m pytest tests/test_v1_agent_workbench_db.py -q
```

- [ ] **Step 2: Implement contracts**

Required contracts:
- `AgentSession`
- `AgentMessage`
- `ArtifactRef`
- `WorkflowKind`: `friend_stock` or `strategy_idea`
- `WorkflowState`

- [ ] **Step 3: Implement SQLite tables**

Tables:
- `agent_sessions`
- `agent_messages`
- `agent_artifact_refs`
- `agent_approval_cards`

All tables must preserve timestamps and stable IDs.

- [ ] **Step 4: Verify**

Run:
```powershell
.venv\Scripts\python.exe -m pytest tests/test_v1_agent_workbench_db.py -q
```

- [ ] **Step 5: Commit**

```powershell
git add contracts/agent_workbench.py backend/db/agent_workbench.py tests/test_v1_agent_workbench_db.py
git commit -m "feat: add V1 agent workbench persistence"
```

### Task 3: Harden Strategy Template Library For PRD Fields

**Files:**
- Modify: `backend/services/strategy_template_library.py`
- Modify: `contracts/strategy.py`
- Create: `tests/test_v1_template_library_prd_fields.py`

- [ ] **Step 1: Write failing tests**

Every approved template must expose:
- `template_id`
- `version`
- `market_fit`
- `forbidden_market`
- `entry_rules`
- `exit_rules`
- `risk_rules`
- `position_sizing_rules`
- `validation_gate_profile`
- `frozen_template_hash`

Also test:
- hash changes when semantic fields change
- LLM/user cannot override parameters through payload
- candidate templates are not approved templates

Run:
```powershell
.venv\Scripts\python.exe -m pytest tests/test_v1_template_library_prd_fields.py tests/test_b2_template_library.py tests/test_b2_template_selection_contract.py -q
```

- [ ] **Step 2: Extend template model**

Preserve existing template IDs and fixed parameters. Add PRD metadata without changing existing behavior.

- [ ] **Step 3: Update conversion to B contracts**

Ensure `StrategyDraft` still freezes template ID, version, and hash.

- [ ] **Step 4: Verify**

Run:
```powershell
.venv\Scripts\python.exe -m pytest tests/test_v1_template_library_prd_fields.py tests/test_b2_template_library.py tests/test_b2_template_selection_contract.py -q
```

- [ ] **Step 5: Commit**

```powershell
git add backend/services/strategy_template_library.py contracts/strategy.py tests/test_v1_template_library_prd_fields.py
git commit -m "feat: harden strategy template library for V1"
```

### Task 4: Add RejectedStrategyRegistry

**Files:**
- Create: `contracts/rejected_strategy.py`
- Create: `backend/db/rejected_strategy.py`
- Create: `backend/services/rejected_strategy_registry.py`
- Create: `tests/test_v1_rejected_strategy_registry.py`

- [ ] **Step 1: Write failing tests**

Cover:
- rejected strategy recorded with failed gate and reason
- needs_review strategy recorded
- blocked strategy recorded
- data quality status stored
- retest eligibility stored
- immutable report/evidence IDs stored
- registry can answer counts by gate/status

Run:
```powershell
.venv\Scripts\python.exe -m pytest tests/test_v1_rejected_strategy_registry.py -q
```

- [ ] **Step 2: Implement contract and DB**

Required fields:
- `registry_id`
- `strategy_revision_id`
- `template_id`
- `template_version`
- `status`
- `failed_gate`
- `rejection_reason`
- `data_quality_status`
- `market_context_snapshot`
- `cost_stress_result_id`
- `future_retest_allowed`
- `retest_eligibility_reason`
- `artifact_ids`
- `created_at`
- `actor`

- [ ] **Step 3: Implement registry service**

Service must be append-only. It must not delete failed ideas.

- [ ] **Step 4: Verify**

Run:
```powershell
.venv\Scripts\python.exe -m pytest tests/test_v1_rejected_strategy_registry.py -q
```

- [ ] **Step 5: Commit**

```powershell
git add contracts/rejected_strategy.py backend/db/rejected_strategy.py backend/services/rejected_strategy_registry.py tests/test_v1_rejected_strategy_registry.py
git commit -m "feat: add rejected strategy registry"
```

### Task 5: Add MarketDataFault And Live Market Data Adapter

**Files:**
- Create: `contracts/live_trade.py`
- Create: `backend/services/live_market_data.py`
- Create: `tests/test_v1_market_data_fault.py`

- [ ] **Step 1: Write failing tests**

Test states:
- `ok`
- `stale`
- `partial`
- `inconsistent`
- `unavailable`
- `source_error`
- `adapter_unsupported`

Test current known boundary:
- daily bars/basic market facts can be read
- current quote can be represented
- minute-line trigger returns `adapter_unsupported`
- missing critical data blocks execution recommendation

Run:
```powershell
.venv\Scripts\python.exe -m pytest tests/test_v1_market_data_fault.py -q
```

- [ ] **Step 2: Implement contracts**

Add:
- `MarketDataFault`
- `MarketFactSnapshot`
- `CurrentPriceObservation`

- [ ] **Step 3: Implement adapter**

Adapter must:
- use `TushareClient` only for live observation
- not use `TushareDataSource`, which is frozen backtest snapshot only
- convert API failures to explicit MarketDataFault states
- mark unsupported minute-line data as `adapter_unsupported`

- [ ] **Step 4: Verify**

Run:
```powershell
.venv\Scripts\python.exe -m pytest tests/test_v1_market_data_fault.py tests/test_tushare_config.py -q
```

- [ ] **Step 5: Commit**

```powershell
git add contracts/live_trade.py backend/services/live_market_data.py tests/test_v1_market_data_fault.py
git commit -m "feat: add live market data fault model"
```

### Task 6: Add Capital Context

**Files:**
- Modify: `contracts/live_trade.py`
- Create: `backend/services/capital_context.py`
- Create: `tests/test_v1_capital_context.py`

- [ ] **Step 1: Write failing tests**

Cover:
- user provides plain amount or named pool
- user cannot choose sizing formula
- service derives planned cash amount
- service derives board-lot share count for A shares
- insufficient funds produces skip/block state
- output links to template position sizing rule

Run:
```powershell
.venv\Scripts\python.exe -m pytest tests/test_v1_capital_context.py -q
```

- [ ] **Step 2: Implement service**

Use approved template `position_sizing_rules` and current price. Round to valid A-share lot size where applicable.

- [ ] **Step 3: Verify**

Run:
```powershell
.venv\Scripts\python.exe -m pytest tests/test_v1_capital_context.py -q
```

- [ ] **Step 4: Commit**

```powershell
git add contracts/live_trade.py backend/services/capital_context.py tests/test_v1_capital_context.py
git commit -m "feat: add V1 capital context"
```

### Task 7: Add Deterministic Recommendation Reducer And Execution Card

**Files:**
- Modify: `contracts/live_trade.py`
- Create: `backend/services/recommendation_reducer.py`
- Create: `backend/services/execution_card_builder.py`
- Create: `tests/test_v1_recommendation_reducer.py`

- [ ] **Step 1: Write failing tests**

Cover each recommendation:
- `strongly_execute`
- `executable`
- `pause_observation`
- `do_not_execute`
- `abandon`

Test inputs:
- `prototype_passed`
- signal validity
- price range
- MarketDataFault
- risk blockers
- market status
- base/stress cost
- capital context
- user intraday observation downgrade only

Run:
```powershell
.venv\Scripts\python.exe -m pytest tests/test_v1_recommendation_reducer.py -q
```

- [ ] **Step 2: Implement reducer**

Reducer must be pure deterministic Python. It must not call LLM, Tushare, DB, or random/time APIs.

- [ ] **Step 3: Implement execution card builder**

Execution card must include:
- symbol/name
- direction
- recommendation level
- planned cash amount
- planned share count
- allowed price range
- invalidation conditions
- review time
- reasons
- risks
- market data state
- artifact IDs

- [ ] **Step 4: Verify**

Run:
```powershell
.venv\Scripts\python.exe -m pytest tests/test_v1_recommendation_reducer.py tests/test_c3_action_plan_boundary.py -q
```

- [ ] **Step 5: Commit**

```powershell
git add contracts/live_trade.py backend/services/recommendation_reducer.py backend/services/execution_card_builder.py tests/test_v1_recommendation_reducer.py
git commit -m "feat: add deterministic live recommendation reducer"
```

### Task 8: Add Execution Observation Log

**Files:**
- Modify: `contracts/live_trade.py`
- Create: `backend/db/live_trade.py`
- Create: `backend/services/execution_interpreter.py`
- Create: `tests/test_v1_execution_interpreter.py`

- [ ] **Step 1: Write failing tests**

Cover natural-language examples:
- "我买了"
- "没买"
- "只买了一半"
- "卖了"
- "忘了执行"
- "价格太高没追"

Expected behavior:
- agent proposes structured draft
- draft requires user acceptance before persistence
- no broker certainty is claimed
- missing price/quantity can be requested in plain language
- no manual field maintenance UI is required

Run:
```powershell
.venv\Scripts\python.exe -m pytest tests/test_v1_execution_interpreter.py -q
```

- [ ] **Step 2: Implement draft contract**

Add:
- `ExecutionObservationDraft`
- `ExecutionObservationLog`
- `ExecutionInterpretationStatus`

- [ ] **Step 3: Implement interpreter**

Use deterministic parsing for obvious phrases first. Use LLM only when the phrase is ambiguous and only to propose a draft for user approval.

- [ ] **Step 4: Implement DB methods**

Tables:
- `execution_observation_drafts`
- `execution_observation_logs`

- [ ] **Step 5: Verify**

Run:
```powershell
.venv\Scripts\python.exe -m pytest tests/test_v1_execution_interpreter.py -q
```

- [ ] **Step 6: Commit**

```powershell
git add contracts/live_trade.py backend/db/live_trade.py backend/services/execution_interpreter.py tests/test_v1_execution_interpreter.py
git commit -m "feat: add execution observation log"
```

### Task 9: Add Observation Pool And Daily Signals

**Files:**
- Modify: `contracts/live_trade.py`
- Modify: `backend/db/live_trade.py`
- Create: `backend/services/observation_pool.py`
- Create: `tests/test_v1_observation_pool.py`

- [ ] **Step 1: Write failing tests**

Cover:
- accepted buy log creates observation position
- daily observation produces hold/sell/risk/invalidated signal
- blocked market data produces risk or pause state
- user-provided intraday observation can downgrade only
- accepted sell closes position
- closed position no longer emits daily signals

Run:
```powershell
.venv\Scripts\python.exe -m pytest tests/test_v1_observation_pool.py -q
```

- [ ] **Step 2: Implement contracts**

Add:
- `ObservationPosition`
- `DailyObservationSignal`
- `PositionLifecycleState`

- [ ] **Step 3: Implement service and DB**

The service reads:
- execution logs
- original execution card
- current market facts
- template exit/risk rules

The service writes:
- daily observation signal
- invalidation state
- position lifecycle update

- [ ] **Step 4: Verify**

Run:
```powershell
.venv\Scripts\python.exe -m pytest tests/test_v1_observation_pool.py -q
```

- [ ] **Step 5: Commit**

```powershell
git add contracts/live_trade.py backend/db/live_trade.py backend/services/observation_pool.py tests/test_v1_observation_pool.py
git commit -m "feat: add V1 observation pool"
```

### Task 10: Add Discipline Review And P&L Record

**Files:**
- Modify: `contracts/live_trade.py`
- Modify: `backend/db/live_trade.py`
- Create: `backend/services/discipline_review.py`
- Create: `tests/test_v1_discipline_review.py`

- [ ] **Step 1: Write failing tests**

Cover:
- review requires original plan
- review requires accepted execution logs
- review includes user-approved buy/sell details
- P&L is labeled user-reported or calculated-from-approved-details
- review compares plan adherence
- review records mistakes and follow-up observation decision
- broker-verified claim is forbidden

Run:
```powershell
.venv\Scripts\python.exe -m pytest tests/test_v1_discipline_review.py -q
```

- [ ] **Step 2: Implement contracts**

Add:
- `PnlRecord`
- `DisciplineReview`
- `PlanAdherenceResult`

- [ ] **Step 3: Implement service**

Calculate P&L only from approved details:
- buy price
- sell price
- quantity
- optional fees

Clearly mark source.

- [ ] **Step 4: Verify**

Run:
```powershell
.venv\Scripts\python.exe -m pytest tests/test_v1_discipline_review.py -q
```

- [ ] **Step 5: Commit**

```powershell
git add contracts/live_trade.py backend/db/live_trade.py backend/services/discipline_review.py tests/test_v1_discipline_review.py
git commit -m "feat: add discipline review and pnl record"
```

### Task 11: Add Short-Video Strategy Idea Flow

**Files:**
- Create: `contracts/strategy_idea.py`
- Create: `backend/db/strategy_ideas.py`
- Create: `backend/services/strategy_idea_flow.py`
- Create: `backend/services/template_candidate_evaluator.py`
- Create: `backend/api/strategy_ideas.py`
- Create: `tests/test_v1_strategy_idea_flow.py`

- [ ] **Step 1: Write failing tests**

Scenario:
```text
我在抖音看到一个股票策略：下午两点半后买入，第二天早上卖出。帮我评估它到底能不能赚钱，能不能加入策略里。
```

Expected:
- idea artifact created
- claim/entry/exit extracted
- idea marked untrusted
- no live signal generated
- approved template mapping or candidate-template path required
- failed idea enters RejectedStrategyRegistry
- passing idea cannot enter live library without frozen approval path

Run:
```powershell
.venv\Scripts\python.exe -m pytest tests/test_v1_strategy_idea_flow.py -q
```

- [ ] **Step 2: Implement contracts and DB**

Contracts:
- `StrategyIdea`
- `StrategyIdeaExtraction`
- `TemplateMappingResult`
- `CandidateTemplateEvaluation`

- [ ] **Step 3: Implement flow**

LLM may extract and explain. Deterministic services decide trust status, validation path, and live eligibility.

- [ ] **Step 4: Add API**

Endpoints:
- `POST /api/strategy-ideas`
- `GET /api/strategy-ideas/{idea_id}`
- `POST /api/strategy-ideas/{idea_id}/validate`

- [ ] **Step 5: Verify**

Run:
```powershell
.venv\Scripts\python.exe -m pytest tests/test_v1_strategy_idea_flow.py tests/test_v1_rejected_strategy_registry.py -q
```

- [ ] **Step 6: Commit**

```powershell
git add contracts/strategy_idea.py backend/db/strategy_ideas.py backend/services/strategy_idea_flow.py backend/services/template_candidate_evaluator.py backend/api/strategy_ideas.py tests/test_v1_strategy_idea_flow.py
git commit -m "feat: add short-video strategy idea flow"
```

### Task 12: Add Friend-Recommended Single Stock Flow

**Files:**
- Create: `backend/services/friend_stock_flow.py`
- Create: `tests/test_v1_friend_stock_flow.py`
- Modify: `backend/api/research.py`
- Modify: `backend/db/research.py`

- [ ] **Step 1: Write failing tests**

Scenario:
```text
朋友给我推荐了这家公司/这只股票，说是产业链挖掘出来的。帮我调查它值不值得关注，如果值得，帮我看有没有入场机会。
```

Expected:
- company/ticker intake
- industry-chain research task
- sourced company value/potential/risk/counter-evidence summary
- result-level approval card
- no technical field confirmation required from user
- continued path creates forward-only confirmed candidate snapshot

Run:
```powershell
.venv\Scripts\python.exe -m pytest tests/test_v1_friend_stock_flow.py tests/test_research_api.py tests/test_research_db.py -q
```

- [ ] **Step 2: Implement flow service**

Flow service composes existing research APIs/services. It must not duplicate Serenity logic.

- [ ] **Step 3: Replace manual technical confirmation path for agent workflow**

The user sees an approval card. The system fills snapshot fields from evidence, Tushare, and research artifacts.

- [ ] **Step 4: Verify**

Run:
```powershell
.venv\Scripts\python.exe -m pytest tests/test_v1_friend_stock_flow.py tests/test_research_api.py tests/test_research_db.py -q
```

- [ ] **Step 5: Commit**

```powershell
git add backend/services/friend_stock_flow.py backend/api/research.py backend/db/research.py tests/test_v1_friend_stock_flow.py
git commit -m "feat: add friend recommended stock flow"
```

### Task 13: Add Unified Agent Workbench API

**Files:**
- Create: `backend/api/agent_workbench.py`
- Modify: `backend/app/main.py`
- Create: `tests/test_v1_agent_workbench_api.py`

- [ ] **Step 1: Write failing tests**

Cover:
- start friend-stock session from chat
- start strategy-idea session from chat
- agent returns message plus artifact refs
- agent returns approval card when human decision is needed
- user approval advances workflow
- technical approvals are never requested

Run:
```powershell
.venv\Scripts\python.exe -m pytest tests/test_v1_agent_workbench_api.py -q
```

- [ ] **Step 2: Implement orchestrator API**

Endpoints:
- `POST /api/workbench/sessions`
- `GET /api/workbench/sessions/{session_id}`
- `POST /api/workbench/sessions/{session_id}/messages`
- `POST /api/workbench/sessions/{session_id}/approval-cards/{card_id}/decide`

- [ ] **Step 3: Wire routers**

Modify `backend/app/main.py` to initialize new DBs and include routers.

- [ ] **Step 4: Verify**

Run:
```powershell
.venv\Scripts\python.exe -m pytest tests/test_v1_agent_workbench_api.py -q
```

- [ ] **Step 5: Commit**

```powershell
git add backend/api/agent_workbench.py backend/app/main.py tests/test_v1_agent_workbench_api.py
git commit -m "feat: add V1 agent workbench API"
```

### Task 14: Build Web UI Agent Workbench

**Files:**
- Create: `frontend/app/workbench/page.tsx`
- Create: `frontend/components/AgentChatPanel.tsx`
- Create: `frontend/components/ApprovalCard.tsx`
- Create: `frontend/components/ResearchSummaryCard.tsx`
- Create: `frontend/components/StrategyValidationCard.tsx`
- Create: `frontend/components/ExecutionCard.tsx`
- Create: `frontend/components/ObservationPoolPanel.tsx`
- Create: `frontend/components/DisciplineReviewPanel.tsx`
- Create: `frontend/components/StrategyIdeaCard.tsx`
- Modify: `frontend/lib/api-client.ts`

- [ ] **Step 1: Add frontend API client methods**

Add methods for workbench sessions, messages, approval decisions, live-trade records, observation pool, discipline review, and strategy ideas.

- [ ] **Step 2: Build workbench page**

Page must show:
- chat panel
- current workflow state
- latest approval card
- artifacts
- execution card
- observation pool
- discipline review

- [ ] **Step 3: Enforce user-facing boundary**

UI must not ask for:
- OOS dates
- thresholds
- stop-loss
- liquidity parameters
- template parameters
- manual execution fields

- [ ] **Step 4: Add frontend tests or component smoke tests**

Run the repo's frontend test/build command. If none exists, run:
```powershell
npm --prefix frontend run build
```

Expected: build succeeds.

- [ ] **Step 5: Commit**

```powershell
git add frontend/app/workbench/page.tsx frontend/components/AgentChatPanel.tsx frontend/components/ApprovalCard.tsx frontend/components/ResearchSummaryCard.tsx frontend/components/StrategyValidationCard.tsx frontend/components/ExecutionCard.tsx frontend/components/ObservationPoolPanel.tsx frontend/components/DisciplineReviewPanel.tsx frontend/components/StrategyIdeaCard.tsx frontend/lib/api-client.ts
git commit -m "feat: add V1 agent workbench UI"
```

### Task 15: Fix User-Facing Chinese Copy And Encoding

**Files:**
- Modify: `contracts/action_plan.py`
- Modify: `contracts/signal_board.py`
- Modify: `backend/services/action_plan_builder.py`
- Modify: `frontend/components/ActionPlanPanel.tsx`
- Modify: `docs/verification/C3_VERIFICATION.md` if referenced by current docs
- Create: `tests/test_v1_copy_encoding.py`

- [ ] **Step 1: Write failing copy tests**

Search production files for known mojibake fragments from old UTF-8/GBK decoding mistakes. Keep the exact bad-fragment list inside the test file, not in user-facing docs.

The test must fail if these appear in production UI/contracts.

Run:
```powershell
.venv\Scripts\python.exe -m pytest tests/test_v1_copy_encoding.py -q
```

- [ ] **Step 2: Replace mojibake with readable Chinese**

Use PRD-approved wording:
- `人工处理计划`
- `这不是自动交易，不连接券商，不保证盈利`
- `准备执行`
- `部分执行`
- `今日放弃`
- `标记过期`

- [ ] **Step 3: Preserve no-auto-trading boundary**

Tests must still reject automatic order/profit guarantee wording.

- [ ] **Step 4: Verify**

Run:
```powershell
.venv\Scripts\python.exe -m pytest tests/test_v1_copy_encoding.py tests/test_c3_action_plan_copy_boundary.py -q
```

- [ ] **Step 5: Commit**

```powershell
git add contracts/action_plan.py contracts/signal_board.py backend/services/action_plan_builder.py frontend/components/ActionPlanPanel.tsx docs/verification/C3_VERIFICATION.md tests/test_v1_copy_encoding.py
git commit -m "fix: restore readable V1 Chinese copy"
```

### Task 16: Add V1 E2E Profitable Loop Tests

**Files:**
- Create: `tests/test_v1_e2e_profitable_loop.py`

- [ ] **Step 1: Write E2E test for friend-recommended stock**

The test must verify:
- chat starts session
- research artifact created
- evidence/counter-evidence artifact created
- approval card created
- confirmed candidate snapshot created
- template mapping created
- validation artifacts created or deterministic test doubles represent them
- signal admitted only after `prototype_passed`
- execution card created
- accepted buy creates observation position
- daily signal created
- accepted sell closes position
- discipline review and P&L record created

- [ ] **Step 2: Write E2E test for short-video strategy idea**

The test must verify:
- strategy idea artifact created
- extraction artifact created
- untrusted status before validation
- template mapping or candidate-template path
- no live signal before approval/freeze/validation/promotion
- rejected path enters registry
- passing path enters approved frozen template process

- [ ] **Step 3: Run E2E tests**

Run:
```powershell
.venv\Scripts\python.exe -m pytest tests/test_v1_e2e_profitable_loop.py -q
```

- [ ] **Step 4: Commit**

```powershell
git add tests/test_v1_e2e_profitable_loop.py
git commit -m "test: add V1 profitable loop acceptance tests"
```

### Task 17: Full Regression And Verification Document

**Files:**
- Create: `docs/verification/V1_MINIMUM_PROFITABLE_LOOP_VERIFICATION.md`

- [ ] **Step 1: Run focused backend tests**

Run:
```powershell
.venv\Scripts\python.exe -m pytest tests/test_v1_*.py -q
```

- [ ] **Step 2: Run existing research tests**

Run:
```powershell
.venv\Scripts\python.exe -m pytest tests/test_research_*.py tests/test_serenity_*.py -q
```

- [ ] **Step 3: Run existing B-module tests**

Run:
```powershell
.venv\Scripts\python.exe -m unittest tests.test_b5_oos_budget tests.test_b5_oos_controller tests.test_b5_report_builder tests.test_b5_cost_stress tests.test_b5_control_comparison tests.test_b5_gate_v2 tests.test_b5_gate_explanation tests.test_b5_promotion_boundary tests.test_b5_vertical_flow tests.test_b5_compatibility -v
```

- [ ] **Step 4: Run existing signal/action tests**

Run:
```powershell
.venv\Scripts\python.exe -m pytest tests/test_signal_*.py tests/test_c*_*.py -q
```

- [ ] **Step 5: Run full backend test suite**

Run:
```powershell
.venv\Scripts\python.exe -m pytest tests/ -x --tb=short -q
```

- [ ] **Step 6: Run frontend build**

Run:
```powershell
npm --prefix frontend run build
```

- [ ] **Step 7: Write verification document**

Document:
- commit list
- test commands and outputs
- two E2E script evidence chains
- artifact IDs produced in test fixtures
- known limitations
- explicit no-broker/no-auto-order boundary

- [ ] **Step 8: Commit**

```powershell
git add docs/verification/V1_MINIMUM_PROFITABLE_LOOP_VERIFICATION.md
git commit -m "docs: verify V1 minimum profitable loop"
```

---

## 4. Execution Order

Execute in this order:

1. Approval Card.
2. Agent Workbench persistence.
3. Strategy Template Library hardening.
4. RejectedStrategyRegistry.
5. MarketDataFault and live market data adapter.
6. Capital Context.
7. Recommendation Reducer and Execution Card.
8. Execution Observation Log.
9. Observation Pool and daily signals.
10. Discipline Review and P&L record.
11. Short-video Strategy Idea flow.
12. Friend-recommended Stock flow.
13. Unified Agent Workbench API.
14. Web UI Agent Workbench.
15. Chinese copy and encoding fix.
16. E2E profitable loop tests.
17. Full verification.

Reasoning:
- Deterministic contracts and reducers come first.
- User-facing agent/workbench comes after backend contracts exist.
- UI comes after API is stable.
- E2E acceptance comes after both loops are implemented.

---

## 5. Non-Negotiable Acceptance Criteria

The plan is complete only when:

- The user can open Web UI and chat with one agent.
- Friend-recommended stock can complete:
  - industry-chain research
  - worth-attention decision
  - strategy validation
  - entry/no-entry execution card
  - accepted buy
  - observation pool
  - daily hold/sell/risk signal
  - accepted sell
  - P&L and discipline review
- Short-video strategy can complete:
  - strategy understanding
  - hypothesis extraction
  - approved frozen template or candidate-template path
  - backtest/OOS/cost/control/multiple-comparison validation
  - approved strategy-library admission or rejected registry
- The user is never asked for technical trading parameters.
- LLM never creates signals, thresholds, strategy rules, recommendation levels, or P&L.
- All rejected/blocked/needs-review strategies are retained.
- Critical data faults block or downgrade recommendations.
- Current Tushare minute-line unsupported state is represented as `adapter_unsupported`.
- Frontend Chinese copy is readable.
- Verification document proves artifact IDs, DB records, logs, and test output for both E2E scripts.

---

## 6. Self-Review Notes

Spec coverage:
- Approval-card model: Tasks 1, 13, 14.
- Strategy Template Library: Task 3.
- Recommendation deterministic rules: Task 7.
- Capital Context: Task 6.
- MarketDataFault: Task 5.
- Discipline Review and P&L: Task 10.
- RejectedStrategyRegistry: Task 4.
- Friend-recommended stock loop: Tasks 12, 13, 14, 16.
- Short-video strategy loop: Tasks 11, 13, 14, 16.
- Web UI embedded agent: Tasks 13 and 14.

Known plan risk:
- This is a large cross-cutting V1. Execute with subagents or strict task-by-task checkpoints; do not batch multiple tasks in one commit.
