# TraderLens V1 PRD Scope Reset

**Date:** 2026-06-29  
**Purpose:** Re-state TraderLens V1 as an agent-driven A-share research, validation, and live-trading decision assistant. This document supersedes scattered milestone assumptions when they conflict with the product goal below.

---

## 1. Product Statement

TraderLens is an A-share strategy research, validation, and live-trading decision assistant.

The user interacts mainly through an agent conversation and simple approvals. The system performs research, verification, backtests, signal generation, market observation, execution interpretation, and review with deterministic code and auditable evidence.

TraderLens is not a broker, not an automatic order-placement system, and not a profit-guarantee engine.

---

## 2. Primary User

The primary user is a project owner who wants to make real-money A-share trades, but does not want to choose technical trading parameters or maintain structured trading state.

The user can approve or reject understandable outcomes:
- "This research direction is worth continuing."
- "This candidate pool looks reasonable."
- "This strategy passed the required validation gates."
- "Use this system-defined strategy template."
- "Accept or reject this final strategy promotion."
- "Proceed with this action plan."
- "I executed / skipped / partially executed this action."
- "Confirm or reject this agent-generated execution/review summary."

The user must not be asked to decide:
- Top 10% vs top 15%.
- Stop loss 8% vs 10%.
- Exact factor thresholds.
- OOS window dates.
- Technical backtest parameters.
- Manual execution record fields.
- Whether incomplete key market data is "good enough" for trading.

---

## 3. Product Goal

V1 should support this end-to-end user story:

> "I saw a video saying the storage-device industry is heating up. Investigate it, find whether there is an opportunity, screen companies, validate strategies, and if a strategy passes, give me a clear live-trading action plan and follow-up review."

The agent should:
1. Turn the user's theme into a research task.
2. Run Serenity industry-chain research.
3. Verify tickers and hard-filter invalid candidates.
4. Gather sourced evidence and counter-evidence.
5. Ask the user to confirm a forward-only candidate pool.
6. Build strategy hypotheses from the confirmed research snapshot.
7. Choose only system-approved strategy templates and parameters.
8. Run deterministic validation and anti-self-deception checks.
9. Promote only strategies that pass the full B-module gate.
10. Generate Signal Board planned signals only for `prototype_passed` strategies.
11. Build live-trading Action Plans from admitted signals.
12. Produce execution cards with clear recommendation levels.
13. Observe market facts through Tushare or approved data adapters.
14. Let the user execute manually in a broker app.
15. Parse the user's natural-language execution feedback into structured records after user approval.
16. Produce post-market review without asking the user to maintain fields.

---

## 4. Hard Boundaries

### 4.1 LLM Boundaries

LLM may:
- Summarize sourced research.
- Classify evidence.
- Draft human-readable explanations.
- Parse user chat into a proposed structured interpretation for approval.
- Explain validation, signal, action, and review results in plain language.

LLM must not:
- Generate trading signals.
- Invent strategy rules.
- Choose technical thresholds.
- Calculate P&L.
- Decide real-money execution.
- Rewrite failed validation results into passing results.
- Fill missing market data.

### 4.2 Trading Boundaries

The system may give clear strategy-backed recommendations such as:
- Continue research / stop research.
- Candidate accepted / rejected.
- Strategy rejected / needs review / eligible for prototype promotion.
- Signal valid / blocked / expired.
- Action Plan ready / not ready.
- Strongly execute / executable / do not execute / pause observation / abandon.

The system must not:
- Promise profit.
- Claim live-trading readiness without the required data and validation boundaries.
- Connect to broker in V1.
- Place orders automatically.
- Treat Tushare market data as broker fill proof.
- Calculate realized P&L before an explicitly designed accounting module exists.

Clear recommendation is required, but recommendation must come from deterministic rules, validation gates, and cited evidence. It cannot come from LLM intuition.

### 4.3 Live-Trading Boundary

V1 is built for real-money trading decisions, but without broker connection.

The system should provide clear recommendation levels:
- 强建议执行
- 可执行
- 不执行
- 暂停观察
- 放弃

The user executes manually in a broker app. The user then tells the agent in natural language whether the action was executed, skipped, partially executed, or abandoned.

The system must not ask the user to manually maintain execution fields. The agent parses the user's statement, proposes a structured interpretation, and asks the user to approve or correct it in plain language.

### 4.4 Market Data Failure Boundary

Key market data incompleteness is a system failure, not a user judgment task.

When critical data is missing, stale, inconsistent, or unavailable:
- The system must block or suspend the affected trading recommendation.
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
人工确认
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
- user confirmation

### 6.3 User Interaction

The user approves whether the research result is understandable and worth continuing.

The user does not choose factor parameters, liquidity thresholds, or ticker validation rules.

---

## 7. Module B: Strategy Validation

### 7.1 Flow

```text
confirmed_candidate_pool + hypothesis_draft
  ↓
Hypothesis Builder 读取研究快照
  ↓
选择系统策略模板
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
human_required_sync
  ↓
StrategyPromotionReducer
  ↓
prototype_passed
```

### 7.2 User Interaction

The user can approve a final human-readable promotion decision.

The user does not choose OOS dates, threshold values, ranking cuts, stop-loss values, or gate internals.

### 7.3 Output

Only `prototype_passed` strategies may enter C.

---

## 8. Module C: Live-Trading Action and Review

### 8.1 Flow

```text
prototype_passed
  ↓
Signal Board
  ↓
Action Plan
  ↓
盘前/盘中 live-trading execution card
  ↓
用户在券商 App 手动执行 / 放弃 / 部分执行
  ↓
用户用自然语言告诉 agent
  ↓
Agent 生成结构化 Execution Observation Log 草案
  ↓
用户审核确认
  ↓
盘后复盘
```

### 8.2 Signal Board

Signal Board displays strategy_core planned signals from admitted strategies.

It must not generate signals itself.

### 8.3 Action Plan

Action Plan translates an admitted planned signal into a human-readable live-trading handling plan.

It may say:
- 强建议执行
- 可执行
- 不执行
- 暂停观察
- 放弃

It must not:
- Become LLM-generated trade advice.
- Add arbitrary target price or threshold not derived from frozen strategy/action-plan rules.
- Promise profit.
- Auto-execute.

### 8.4 Live-Trading Execution Card

For every actionable signal, the system should present a complete execution card:
- symbol and name
- direction
- recommendation level
- suggested execution price range
- maximum acceptable deviation
- invalidation conditions
- review time
- why this action is suggested
- main risks
- what the agent will record if the user executes, skips, or partially executes

The execution card must be derived from:
- `prototype_passed` strategy state
- admitted planned signal
- frozen Action Plan rules
- current or latest available Tushare market facts
- deterministic risk blockers

The LLM may explain the card but must not invent the card's trading content.

### 8.5 Market Observation

V1 does not require Tushare minute-line support.

Confirmed current data boundary:
- Daily bars and basic market facts are available from the configured Tushare service.
- Current-price observation is available through compatible quote access.
- `rt_min`, `stk_mins`, and `pro_bar(freq="1min")` are not currently available from the configured private Tushare service.

Therefore V1 supports:
- pre-market and post-market daily-level recommendations
- intraday current-price observation
- detecting whether current price appears inside or outside the execution card's allowed range
- detecting plan invalidation when required facts are available

V1 does not claim:
- strict minute-line strategy triggers
- minute-bar backfill from the current Tushare service
- broker-grade execution monitoring

The system may keep an extension point for future minute-line adapters. Until a verified adapter exists, minute-line data must not be treated as available.

### 8.6 User-Provided Intraday Observation

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

### 8.7 Execution Observation

The user must not maintain execution fields.

The agent and system should:
- Observe market facts via Tushare or approved data adapters.
- Explain whether the Action Plan stayed valid.
- Parse the user's natural-language execution statement.
- Ask the user to approve or reject the proposed structured interpretation.
- Store structured records after approval.

Without broker integration, the system must not claim it knows the user's exact broker fill.

### 8.8 Post-Market Review

Post-market review should compare:
- original Action Plan
- observed market data
- user-approved execution confirmation, if any
- user-provided intraday observations, if any
- invalidation conditions
- outcome narrative

It must not calculate realized P&L until a later accounting module defines valid inputs and rules.

---

## 9. Agentic Web App Requirement

V1 must feel like one agent-driven workflow, not disconnected screens.

The agent should be able to:
- Start from a user theme.
- Run research tools.
- Present sourced conclusions.
- Ask for high-level approval.
- Start validation jobs.
- Explain failed gates.
- Promote only through deterministic reducer.
- Open Signal Board context.
- Explain Action Plans.
- Produce execution cards.
- Trigger market observation.
- Parse user execution feedback.
- Draft post-market reviews.

The UI may contain pages and panels, but the primary control surface should be agent conversation plus simple approvals.

---

## 10. Current Implementation Status To Audit

Known implemented areas from verification records:
- A module has research contracts, Serenity candidate pools, evidence snapshots, confirmed candidates, and tests.
- B2-B6 have verification records for StrategyDraft, point-in-time validation, OOS evaluation, reporting, gate logic, and promotion.
- C0-C3 are verified through admission, Signal Board boundary, and Action Plan.

Known incomplete areas:
- Unified agentic workflow across A/B/C.
- Full GAP audit proving which A/B features are product-ready vs contract/test-only.
- C4 Execution Observation Log.
- C5 Post-Market Review.
- Tushare-powered C-module observation loop.
- One conversational entry point that runs the full chain.
- Live-trading execution cards.
- Current-price observation boundary and fault recording.

---

## 11. V1 Acceptance Criteria

V1 is acceptable only when:
- A user can start with a theme in chat.
- The agent can produce a sourced research result.
- The user can confirm a forward-only candidate pool.
- The system can create and validate strategies without user technical parameter selection.
- Only validated `prototype_passed` strategies can create planned signals.
- Signal Board and Action Plan provide clear, rule-backed decisions.
- The agent can produce live-trading execution cards without user technical parameter selection.
- The user can execute manually in a broker app and report the result in natural language.
- The agent can observe market facts and draft execution/review summaries without user field maintenance.
- Critical market-data failures block trading recommendations and create system/data fault records.
- User-provided intraday observations can downgrade but not upgrade trading recommendations.
- All uncertainty is visible.
- No LLM-generated signal, hidden parameter choice, future-data leakage, or overfit shortcut is introduced.

---

## 12. Immediate Next Documents

Before implementing more code:

1. **Full-chain GAP audit**
   - Map A/B/C desired flow to actual files, APIs, tests, and missing product surfaces.

2. **Agent workflow design**
   - Define how the conversation orchestrates research, validation, Signal Board, observation, execution-card handling, and review.

3. **Revised C roadmap**
   - Rewrite C4/C5/C6 after the GAP audit, not before.
   - C roadmap must target live-trading assistance without broker integration.

---

## 13. Open Product Decisions

These are product-level decisions, not technical-parameter decisions:

1. What is the V1 minimum acceptable end-to-end live-trading demo?
2. What exact wording should distinguish 强建议执行 from 可执行?
3. What is the required evidence threshold for the user to approve candidate pools?
4. What level of post-market review is useful before realized P&L exists?
5. Should broker statement import be considered after V1, without automatic order placement?
