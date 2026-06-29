# TraderLens V1 PRD Scope Reset

**Date:** 2026-06-29  
**Purpose:** Re-state TraderLens V1 as an agent-driven A-share research, validation, and live-trading decision assistant. This document supersedes scattered milestone assumptions when they conflict with the product goal below.

---

## 1. Product Statement

TraderLens is an A-share strategy research, validation, and live-trading decision assistant.

The user interacts mainly through an agent conversation and result-level approval cards. The system performs research, verification, backtests, signal generation, market observation, execution interpretation, and discipline review with deterministic code and auditable evidence.

TraderLens is not a broker, not an automatic order-placement system, and not a profit-guarantee engine.

---

## 2. Primary User and Approval Boundary

The primary user is a project owner who wants to make real-money A-share trades, but does not want to choose technical trading parameters or maintain structured trading state.

All user approvals must be downgraded to result-level approval cards.

Allowed approval card actions:
- Continue.
- Stop.
- Downgrade to observation.
- Enter small-capital live observation.
- Accept execution-record interpretation.

The user must not be asked to judge:
- Candidate pool technical quality.
- Strategy parameters.
- OOS windows.
- Thresholds.
- Stop-loss levels.
- Liquidity rules.
- Ranking cutoffs.
- Position sizing formulas.
- Whether incomplete key market data is usable.
- Manual execution record fields.

The user may provide understandable context:
- A theme or idea to research.
- A small-capital trial amount or capital pool.
- Natural-language execution feedback.
- User-observed intraday behavior from the broker app.

The system must convert that context into structured data only after agent interpretation and user approval.

---

## 3. Product Goal

V1 should support this end-to-end user story:

> "I saw a video saying the storage-device industry is heating up. Investigate it, find whether there is an opportunity, screen companies, validate strategies, and if a strategy passes, give me a clear live-trading action plan and follow-up review."

The agent should:
1. Turn the user's theme into a research task.
2. Run Serenity industry-chain research.
3. Verify tickers and hard-filter invalid candidates.
4. Gather sourced evidence and counter-evidence.
5. Present a result-level approval card for continuing, stopping, or downgrading observation.
6. Build strategy hypotheses from the confirmed research snapshot.
7. Map hypotheses only to system-approved frozen strategy templates.
8. Run deterministic validation and anti-self-deception checks.
9. Promote only strategies that pass the full B-module gate.
10. Preserve rejected, blocked, and needs-review strategies in the rejection registry.
11. Generate Signal Board planned signals only for `prototype_passed` strategies.
12. Build live-trading Action Plans from admitted signals.
13. Produce execution cards with deterministic recommendation levels.
14. Observe market facts through Tushare or approved data adapters.
15. Let the user execute manually in a broker app.
16. Parse the user's natural-language execution feedback into structured records after user approval.
17. Produce discipline review without asking the user to maintain fields.

---

## 4. Hard Boundaries

### 4.1 LLM Boundaries

LLM may:
- Summarize sourced research.
- Classify evidence.
- Draft human-readable explanations.
- Map a research hypothesis to an approved strategy template.
- Parse user chat into a proposed structured interpretation for approval.
- Explain validation, signal, action, and review results in plain language.

LLM must not:
- Generate trading signals.
- Invent strategy rules.
- Choose technical thresholds.
- Modify template parameters.
- Add temporary trading conditions.
- Calculate P&L.
- Decide real-money execution.
- Rewrite failed validation results into passing results.
- Fill missing market data.

### 4.2 Trading Boundaries

The system may give clear strategy-backed recommendations such as:
- Continue research / stop research.
- Downgrade to observation.
- Strategy rejected / needs review / eligible for prototype promotion.
- Signal valid / blocked / expired.
- Action Plan ready / not ready.
- Strongly execute / executable / do not execute / pause observation / abandon.
- Enter small-capital live observation.

The system must not:
- Promise profit.
- Claim live-trading readiness without required data and validation boundaries.
- Connect to broker in V1.
- Place orders automatically.
- Treat Tushare market data as broker fill proof.
- Calculate realized P&L before an explicitly designed accounting module exists.

Clear recommendation is required, but recommendation must come from deterministic rules, validation gates, approved templates, and cited evidence. It cannot come from LLM intuition.

### 4.3 Live-Trading Boundary

V1 is built for real-money trading decisions, but without broker connection.

The user executes manually in a broker app. The user then tells the agent in natural language whether the action was executed, skipped, partially executed, or abandoned.

The system must not ask the user to manually maintain execution fields. The agent parses the user's statement, proposes a structured interpretation, and asks the user to approve or correct it in plain language.

### 4.4 Market Data Failure Boundary

Key market data incompleteness is a system failure, not a user judgment task.

When critical data is missing, stale, inconsistent, unavailable, or unsupported:
- The system must block or downgrade the affected trading recommendation.
- The system must record a data/system fault.
- The system must explain the issue in plain language.
- The system must not ask the user to decide whether incomplete data is usable.

Non-critical display data may be missing only if deterministic trading eligibility is unaffected and the missing data is clearly shown.

---

## 5. Anti-Self-Deception Principles

TraderLens prefers false negatives over false positives.

The system should kill or block strategies when evidence is incomplete, contaminated, or suspicious.

Required defenses:
- Point-in-time universe construction.
- Future-data guards.
- Canary tests.
- Frozen StrategyDraft.
- Frozen ResearchProtocolSnapshot.
- Frozen gate criteria hash.
- OOS budget control.
- Shared OOS window tracking.
- Cost stress testing.
- Control comparison.
- Multiple-comparison correction.
- Alpha gate.
- Trade distribution checks.
- Human-required sync before promotion.
- RejectedStrategyRegistry for failed, blocked, and needs-review strategies.

No agent may bypass these defenses for convenience.

---

## 6. Module A: Selection Research

### 6.1 Flow

```text
主题输入 / 市场扫描 / 人工股票
  ↓
Serenity 产业链研究
  ↓
ticker verification + 硬过滤
  ↓
来源化 Evidence + 反证
  ↓
结果层 approval card
  ↓
confirmed_candidate_pool
```

### 6.2 Output

`confirmed_candidate_pool` is a forward-only research snapshot. It is not a historical backtest universe.

It must preserve:
- confirmation date
- thesis snapshot
- invalidation rules
- price snapshot
- benchmark snapshot
- evidence snapshot IDs
- source provenance
- approval card decision

### 6.3 User Interaction

The user approves whether to continue, stop, or downgrade to observation.

The user does not approve candidate pool technical quality and does not choose factor parameters, liquidity thresholds, or ticker validation rules.

---

## 7. Strategy Template Library

Only system-approved and version-frozen strategy templates may generate `StrategyDraft`.

LLM may:
- Map a research hypothesis to an approved template.
- Explain why the mapping is plausible.
- Explain why no approved template fits.

LLM must not:
- Create a new strategy rule.
- Modify parameters.
- Add a temporary market condition.
- Choose a threshold.
- Override a template's forbidden market.

Every template must define:
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

If no approved frozen template fits the research hypothesis, the system must stop or downgrade to observation. It must not let the LLM improvise a strategy.

---

## 8. Module B: Strategy Validation

### 8.1 Flow

```text
confirmed_candidate_pool + hypothesis_draft
  ↓
Hypothesis Builder 读取研究快照
  ↓
LLM maps to approved Strategy Template
  ↓
系统选择版本冻结模板
  ↓
生成并冻结 StrategyDraft
  ↓
构造 BacktestUniverseSpec(point-in-time)
  ↓
确定性 Validator
  ↓
Canary 防未来函数
  ↓
IS 回测
  ↓
按确定性规则生成 OOS window
  ↓
Freeze ResearchProtocolSnapshot
  ↓
冻结 gate_criteria_hash
  ↓
OOS Evaluation Controller
  ↓
记录 oos_draw_index + shared_oos_window_id
  ↓
strategy_core 正式 OOS 回测
  ↓
base_cost_result + stress_cost_result
  ↓
ImmutableBacktestReport
  ↓
Control Comparison 对照组报告
  ↓
Prototype Gate
  ↓
多重比较修正 + alpha Gate + 交易分布检查
  ↓
rejected / needs_review / candidate_for_prototype_passed
  ↓
RejectedStrategyRegistry records all failures and review states
  ↓
human_required_sync result-level approval card
  ↓
StrategyPromotionReducer
  ↓
prototype_passed
```

### 8.2 User Interaction

The user can approve a result-level promotion card:
- Stop.
- Downgrade to observation.
- Enter small-capital live observation.

The user does not choose OOS dates, threshold values, ranking cuts, stop-loss values, or gate internals.

### 8.3 Output

Only `prototype_passed` strategies may enter C.

Rejected, blocked, and needs-review strategies must not disappear from records.

---

## 9. RejectedStrategyRegistry

All rejected, needs-review, and blocked strategies must be preserved to prevent survivorship bias.

Each registry item must include:
- strategy identifier
- template identifier and version
- failure status
- failed gate or blocker
- rejection reason
- data quality status
- market context snapshot
- cost stress result, if applicable
- whether future retest is allowed
- retest eligibility reason
- immutable evidence/report IDs
- timestamp and actor/source

The registry must support future audits that answer:
- How many ideas failed before one passed?
- Which gates kill most strategies?
- Whether a later passing strategy reused a previously rejected idea.
- Whether the user or agent is selectively remembering only successes.

---

## 10. Capital Context

V1 supports live trading with a user-understandable capital context.

The user may provide:
- a small-capital trial amount
- a named capital pool
- a maximum amount they are willing to observe live

The user must not choose:
- position sizing formula
- per-trade risk percentage
- technical risk multiplier
- number of shares by hand
- skip rules for insufficient funds

The system must derive from the frozen template and current market facts:
- planned cash amount
- planned share count
- maximum single-trade risk
- whether funds are insufficient
- whether the action should be skipped
- whether only observation is allowed

If the capital context is missing for a real-money action, the system may ask for a plain-language amount or capital pool. It must not ask the user for technical sizing parameters.

---

## 11. Recommendation Level Deterministic Rules

Recommendation levels must be deterministic.

Inputs may include only:
- `prototype_passed` state
- admitted signal validity
- frozen Action Plan rules
- approved strategy template rules
- price range status
- MarketDataFault status
- risk blockers
- market status
- base cost result
- stress cost result
- capital context
- user-provided intraday observation, downgrade only

LLM must not decide the recommendation level.

### 11.1 Strongly Execute

`强建议执行` is allowed only when:
- strategy is `prototype_passed`
- planned signal is admitted, active, and not stale
- Action Plan is valid
- required market data is `ok`
- current price is inside allowed range
- no risk blocker is active
- market status allows execution
- base and stress cost results remain acceptable under the frozen gate profile
- capital context can fund the minimum executable plan
- no user-provided intraday observation downgrades the action

### 11.2 Executable

`可执行` is allowed when:
- all hard eligibility checks pass
- no blocker is active
- data quality is sufficient for execution
- price is within allowed or tolerable range
- cost stress remains within the template's allowed profile
- at least one non-critical caution exists, or the setup is valid but not top-confidence

### 11.3 Pause Observation

`暂停观察` is required when:
- non-critical data is partial
- current price is near but not clearly inside allowed range
- user-provided intraday observation introduces downside or execution risk
- market state is abnormal but not a hard blocker
- capital context is incomplete for live execution
- the system needs updated daily/current-price facts before allowing action

### 11.4 Do Not Execute

`不执行` is required when:
- signal is inactive, stale, expired, or not admitted
- price is outside allowed range
- key data is stale, inconsistent, unavailable, source_error, or adapter_unsupported for a required fact
- risk blocker is active
- cost stress violates the frozen gate profile
- capital is insufficient and template rules do not allow a smaller valid execution

### 11.5 Abandon

`放弃` is required when:
- strategy is rejected or blocked
- Action Plan is invalidated
- template forbidden market applies
- critical evidence or data contamination is found
- the opportunity has expired under frozen rules
- human approval card explicitly stops the path

---

## 12. MarketDataFault State Machine

Market data state must be explicit.

States:
- `ok`: Required data is current, complete, and internally consistent.
- `stale`: Required data is older than the allowed freshness window.
- `partial`: Non-critical data is missing, while all critical execution facts are present.
- `inconsistent`: Data sources or fields conflict.
- `unavailable`: Required data cannot be retrieved.
- `source_error`: Provider returned an error or malformed response.
- `adapter_unsupported`: The requested data type is not supported by the configured adapter.

Execution impact:
- `ok`: Recommendations may proceed if all other checks pass.
- `partial`: May downgrade to `暂停观察`; may proceed only when missing fields are non-critical.
- `stale`: Blocks `强建议执行` and `可执行`; normally results in `暂停观察` or `不执行`.
- `inconsistent`: Must block execution and create a fault record.
- `unavailable`: Must block execution and create a fault record.
- `source_error`: Must block execution and create a fault record.
- `adapter_unsupported`: Must block any recommendation that depends on the unsupported data, and must not ask the user to judge whether it is acceptable.

Current V1 data boundary:
- Daily bars and basic market facts are available from the configured Tushare service.
- Current-price observation is available through compatible quote access.
- `rt_min`, `stk_mins`, and `pro_bar(freq="1min")` are not currently available from the configured private Tushare service.
- Minute-line triggers must be marked `adapter_unsupported` until a verified adapter exists.

---

## 13. Module C: Live-Trading Action and Discipline Review

### 13.1 Flow

```text
prototype_passed
  ↓
Signal Board
  ↓
Action Plan
  ↓
Capital Context
  ↓
盘前/盘中 live-trading execution card
  ↓
用户在券商 App 手动执行 / 放弃 / 部分执行
  ↓
用户用自然语言告诉 agent
  ↓
Agent 生成结构化 Execution Observation Log 草案
  ↓
用户接受/修正 execution-record interpretation
  ↓
盘后纪律复盘
```

### 13.2 Signal Board

Signal Board displays strategy_core planned signals from admitted strategies.

It must not generate signals itself.

### 13.3 Action Plan

Action Plan translates an admitted planned signal into a human-readable live-trading handling plan.

It may output:
- 强建议执行
- 可执行
- 不执行
- 暂停观察
- 放弃

It must not:
- Become LLM-generated trade advice.
- Add arbitrary target price or threshold not derived from frozen strategy/action-plan/template rules.
- Promise profit.
- Auto-execute.

### 13.4 Live-Trading Execution Card

For every actionable signal, the system should present a complete execution card:
- symbol and name
- direction
- recommendation level
- planned cash amount
- planned share count
- suggested execution price range
- maximum acceptable deviation
- invalidation conditions
- review time
- why this action is suggested
- main risks
- market data state
- what the agent will record if the user executes, skips, or partially executes

The execution card must be derived from:
- `prototype_passed` strategy state
- admitted planned signal
- approved frozen template
- frozen Action Plan rules
- current or latest available Tushare market facts
- deterministic risk blockers
- capital context

The LLM may explain the card but must not invent the card's trading content.

### 13.5 Market Observation

V1 supports:
- pre-market and post-market daily-level recommendations
- intraday current-price observation
- detecting whether current price appears inside or outside the execution card's allowed range
- detecting plan invalidation when required facts are available

V1 does not claim:
- strict minute-line strategy triggers
- minute-bar backfill from the current Tushare service
- broker-grade execution monitoring

The system may keep an extension point for future minute-line adapters. Until a verified adapter exists, minute-line data must not be treated as available.

### 13.6 User-Provided Intraday Observation

The user may inspect minute-line behavior in the broker app and tell the agent what they saw.

User-provided intraday observation may:
- Be stored as user observation.
- Explain why the user executed, skipped, or partially executed.
- Downgrade a recommendation from 强建议执行/可执行 to 暂停观察/不执行 when it introduces risk.

User-provided intraday observation must not:
- Upgrade 不执行/暂停观察/放弃 into a buy or sell recommendation.
- Override deterministic blockers.
- Replace missing system market data.
- Rewrite validation or backtest results.

### 13.7 Execution Observation

The user must not maintain execution fields.

The agent and system should:
- Observe market facts via Tushare or approved data adapters.
- Explain whether the Action Plan stayed valid.
- Parse the user's natural-language execution statement.
- Ask the user to accept or correct the proposed structured interpretation.
- Store structured records after approval.

Without broker integration, the system must not claim it knows the user's exact broker fill.

### 13.8 Discipline Review

V1 post-market review is a discipline review, not realized P&L accounting.

The review must compare:
- original Action Plan
- execution card
- market facts
- MarketDataFault state
- user-approved execution feedback
- user-provided intraday observations, if any
- invalidation conditions
- whether the user followed the plan
- skip or partial-execution reason
- whether future observation should continue, downgrade, or stop

It must not calculate realized P&L until a later accounting module defines valid inputs and rules.

---

## 14. Agentic Web App Requirement

V1 must feel like one agent-driven workflow, not disconnected screens.

The agent should be able to:
- Start from a user theme.
- Run research tools.
- Present sourced conclusions.
- Present result-level approval cards.
- Start validation jobs.
- Explain failed gates.
- Record rejected and blocked strategies.
- Promote only through deterministic reducer.
- Open Signal Board context.
- Explain Action Plans.
- Produce execution cards.
- Apply capital context.
- Trigger market observation.
- Parse user execution feedback.
- Draft discipline reviews.

The UI may contain pages and panels, but the primary control surface should be agent conversation plus simple approval cards.

---

## 15. Current Implementation Status To Audit

Known implemented areas from verification records:
- A module has research contracts, Serenity candidate pools, evidence snapshots, confirmed candidates, and tests.
- B2-B6 have verification records for StrategyDraft, point-in-time validation, OOS evaluation, reporting, gate logic, and promotion.
- C0-C3 are verified through admission, Signal Board boundary, and Action Plan.

Known incomplete areas:
- Unified agentic workflow across A/B/C.
- Full GAP audit proving which A/B features are product-ready vs contract/test-only.
- Approval card model.
- Strategy Template Library hard boundary.
- RejectedStrategyRegistry.
- Capital Context.
- Deterministic recommendation reducer.
- MarketDataFault state machine.
- C4 Execution Observation Log.
- C5 Discipline Review.
- Tushare-powered C-module observation loop.
- One conversational entry point that runs the full chain.
- Live-trading execution cards.
- Current-price observation boundary and fault recording.

---

## 16. V1 Acceptance Criteria

V1 is acceptable only when:
- A user can start with a theme in chat.
- The agent can produce a sourced research result.
- The user sees only result-level approval cards.
- The system can create and validate strategies without user technical parameter selection.
- Only approved frozen strategy templates can generate StrategyDraft.
- All rejected, blocked, and needs-review strategies are retained.
- Only validated `prototype_passed` strategies can create planned signals.
- Signal Board and Action Plan provide clear, rule-backed decisions.
- Recommendation levels are produced by deterministic rules, not LLM judgment.
- Capital context converts user-understandable amount/pool into system-calculated plan amount and share count.
- The agent can produce live-trading execution cards without user technical parameter selection.
- The user can execute manually in a broker app and report the result in natural language.
- The agent can observe market facts and draft execution/review summaries without user field maintenance.
- Critical market-data failures block or downgrade trading recommendations and create system/data fault records.
- User-provided intraday observations can downgrade but not upgrade trading recommendations.
- Discipline review compares plan, market facts, execution feedback, invalidation conditions, and plan adherence.
- All uncertainty is visible.
- No LLM-generated signal, hidden parameter choice, future-data leakage, overfit shortcut, or survivorship-only record is introduced.

---

## 17. E2E Demo Acceptance Script

V1 minimum demo starts from this exact user message:

> "存储设备行业最近很火，帮我调查一下有没有机会，如果有机会，帮我筛选公司、验证策略，最后给我今天能不能实盘观察的行动建议。"

The demo must produce audit evidence at every step. User-facing UI may stay simple, but acceptance must verify artifacts, database records, logs, and test output.

Required acceptance path:
1. Theme intake creates a research task artifact ID.
2. Serenity research creates sourced evidence artifact IDs.
3. Ticker verification and hard filters create validation records.
4. Evidence and counter-evidence are attached to the candidate snapshot.
5. Approval card records continue/stop/downgrade decision.
6. `confirmed_candidate_pool` snapshot is stored as forward-only research state.
7. Hypothesis Builder reads the research snapshot and maps to an approved frozen template.
8. StrategyDraft stores template ID, version, and frozen template hash.
9. BacktestUniverseSpec is point-in-time.
10. Validator and canary records are stored.
11. IS and OOS backtests produce immutable reports.
12. OOS controller records `oos_draw_index` and `shared_oos_window_id`.
13. Cost stress and control comparison reports are stored.
14. Prototype Gate result is stored.
15. RejectedStrategyRegistry stores all rejected, blocked, or needs-review paths.
16. StrategyPromotionReducer produces `prototype_passed` only after required sync.
17. Signal Board displays only admitted planned signals.
18. Action Plan is generated from admitted signal.
19. Capital Context produces planned cash amount and share count.
20. MarketDataFault state is recorded.
21. Execution card recommendation level is produced by deterministic reducer.
22. User natural-language execution feedback is parsed into Execution Observation Log draft.
23. User accepts or corrects the execution-record interpretation.
24. Discipline Review compares original plan, market facts, execution feedback, invalidation conditions, and plan adherence.

For each step, acceptance evidence must include:
- artifact ID
- database record or immutable snapshot reference
- log entry
- relevant test or verification output

The demo must not be accepted with text-only explanation.

---

## 18. Immediate Next Documents

Before implementing more code:

1. **Full-chain GAP audit**
   - Map A/B/C desired flow to actual files, APIs, tests, and missing product surfaces.

2. **Agent workflow design**
   - Define how the conversation orchestrates research, validation, approval cards, Signal Board, observation, execution-card handling, and discipline review.

3. **Revised C roadmap**
   - Rewrite C4/C5/C6 after the GAP audit, not before.
   - C roadmap must target live-trading assistance without broker integration.

---

## 19. Open Product Decisions

These are product-level decisions, not technical-parameter decisions:

1. What exact wording should distinguish 强建议执行 from 可执行 in approval-card UI?
2. What is the smallest acceptable live-observation capital context for V1 demos?
3. What level of discipline review is useful before realized P&L exists?
4. Should broker statement import be considered after V1, without automatic order placement?
