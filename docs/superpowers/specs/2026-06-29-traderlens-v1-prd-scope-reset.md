# TraderLens V1 PRD Scope Reset

**Date:** 2026-06-29  
**Purpose:** Re-state TraderLens V1 as an agent-driven A-share research, validation, and execution-decision workbench. This document supersedes scattered milestone assumptions when they conflict with the product goal below.

---

## 1. Product Statement

TraderLens is an A-share strategy research and execution-decision workbench.

The user interacts mainly through an agent conversation and simple approvals. The system performs research, verification, backtests, signal generation, observation, and review with deterministic code and auditable evidence.

TraderLens is not a broker, not an automatic trading system, and not a profit-guarantee engine.

---

## 2. Primary User

The primary user is a project owner who does not want to choose technical trading parameters or maintain structured trading state.

The user can approve or reject understandable outcomes:
- "This research direction is worth continuing."
- "This candidate pool looks reasonable."
- "This strategy passed the required validation gates."
- "Use this system-defined strategy template."
- "Accept or reject this final strategy promotion."
- "Proceed with this action plan."
- "Confirm or reject this agent-generated execution/review summary."

The user must not be asked to decide:
- Top 10% vs top 15%.
- Stop loss 8% vs 10%.
- Exact factor thresholds.
- OOS window dates.
- Technical backtest parameters.
- Manual execution record fields.

---

## 3. Product Goal

V1 should support this end-to-end user story:

> "I saw a video saying the storage-device industry is heating up. Investigate it, find whether there is an opportunity, screen companies, validate strategies, and if a strategy passes, give me a clear action plan and follow-up review."

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
11. Build Action Plans from admitted signals.
12. Use market data to observe what happened.
13. Produce post-market review without asking the user to maintain structured fields.

---

## 4. Hard Boundaries

### 4.1 LLM Boundaries

LLM may:
- Summarize sourced research.
- Classify evidence.
- Draft human-readable explanations.
- Parse user chat into a proposed structured interpretation for approval.
- Explain validation results in plain language.

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
- Action Plan ready for user approval / not ready.

The system must not:
- Promise profit.
- Claim live-trading readiness without the required execution infrastructure.
- Connect to broker in V1.
- Place orders automatically.
- Treat Tushare market data as broker fill proof.
- Calculate realized P&L before an explicitly designed accounting module exists.

Clear recommendation is required, but recommendation must come from deterministic rules, validation gates, and cited evidence. It cannot come from LLM intuition.

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
Hypothesis Builder reads research snapshot
  ↓
System strategy template selection
  ↓
Freeze StrategyDraft
  ↓
Construct BacktestUniverseSpec(point-in-time)
  ↓
Deterministic Validator
  ↓
Canary future-data defense
  ↓
IS backtest
  ↓
Deterministic OOS window generation
  ↓
Freeze ResearchProtocolSnapshot
  ↓
Freeze gate_criteria_hash
  ↓
OOS Evaluation Controller
  ↓
Record oos_draw_index + shared_oos_window_id
  ↓
strategy_core formal OOS backtest
  ↓
base_cost_result + stress_cost_result
  ↓
ImmutableBacktestReport
  ↓
Control Comparison
  ↓
Prototype Gate
  ↓
Multiple-comparison correction + alpha gate + trade distribution checks
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

## 8. Module C: Action and Review

### 8.1 Flow

```text
prototype_passed
  ↓
Signal Board
  ↓
Action Plan
  ↓
Agent-guided user approval
  ↓
Market observation
  ↓
Execution Observation Log
  ↓
Post-market review
```

### 8.2 Signal Board

Signal Board displays strategy_core planned signals from admitted strategies.

It must not generate signals itself.

### 8.3 Action Plan

Action Plan translates an admitted planned signal into a human-readable handling plan.

It may say:
- ready for human handling
- blocked
- stale
- expired
- skip recommended by deterministic rule

It must not:
- Become LLM-generated trade advice.
- Add target price.
- Promise profit.
- Auto-execute.

### 8.4 Execution Observation

The user must not maintain execution fields.

The agent and system should:
- Observe market facts via Tushare or approved data adapters.
- Explain whether the Action Plan stayed valid.
- Ask the user to approve or reject natural-language interpretations.
- Store structured records after approval.

Without broker integration, the system must not claim it knows the user's exact broker fill.

### 8.5 Post-Market Review

Post-market review should compare:
- original Action Plan
- observed market data
- user-approved execution confirmation, if any
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
- Trigger market observation.
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

---

## 11. V1 Acceptance Criteria

V1 is acceptable only when:
- A user can start with a theme in chat.
- The agent can produce a sourced research result.
- The user can confirm a forward-only candidate pool.
- The system can create and validate strategies without user technical parameter selection.
- Only validated `prototype_passed` strategies can create planned signals.
- Signal Board and Action Plan provide clear, rule-backed decisions.
- The agent can observe market facts and draft review summaries without user field maintenance.
- All uncertainty is visible.
- No LLM-generated signal, hidden parameter choice, future-data leakage, or overfit shortcut is introduced.

---

## 12. Immediate Next Documents

Before implementing more code:

1. **Full-chain GAP audit**
   - Map A/B/C desired flow to actual files, APIs, tests, and missing product surfaces.

2. **Agent workflow design**
   - Define how the conversation orchestrates research, validation, Signal Board, observation, and review.

3. **Revised C roadmap**
   - Rewrite C4/C5/C6 after the GAP audit, not before.

---

## 13. Open Product Decisions

These are product-level decisions, not technical-parameter decisions:

1. What is the V1 minimum acceptable end-to-end demo?
2. Should V1 stop at paper/observation review, or include broker-read-only import later?
3. Should strategy suggestions be phrased as "建议进入人工处理" rather than "买入/卖出" in V1?
4. What is the required evidence threshold for the user to approve candidate pools?
5. What level of post-market review is useful before realized P&L exists?

