# B5 OOS Validation and Gate Design

**Date:** 2026-06-27
**Status:** Draft design
**Upstream:** B2 StrategyDraft, B3 ResearchProtocolSnapshot, B4 event-driven backtest
**Downstream:** Human promotion decision, then C module Signal Board only after `prototype_passed`

---

## 1. Highest Principle

B5 exists to prevent self-deception before real money is at risk.

The system target is profitable live execution, but B5 does not prove future profit. B5 is the final historical validation layer that rejects most weak or fake-good hypotheses before they can become executable strategies.

The user does not understand stocks or programming. No B5 workflow may ask the user to choose technical parameters, strategy rules, OOS windows, thresholds, rank cutoffs, stop-loss percentages, holding periods, benchmark formulas, cost assumptions, or Gate criteria.

The user may only confirm things at the understandable decision layer:

- whether the plain-language result is acceptable;
- whether to approve a strategy that the system has already marked as `candidate_for_prototype_passed`;
- whether to reject or defer a strategy;
- whether to ask the agent for an explanation, rerun from a new frozen hypothesis, or stop.

The user must never be asked questions like:

- "top 10% or top 15%?"
- "stop loss 8% or 10%?"
- "use 252 trading days or 180 days?"
- "minimum Sharpe 1.0 or 1.5?"
- "use benchmark A or benchmark B?"

Those are system policy decisions. They must be frozen before the OOS run and included in `gate_criteria_hash`.

---

## 2. Product Interaction Model

The intended product interaction is conversational.

Example target flow:

```text
User:
  I watched a video saying storage devices are hot recently. Help me investigate.

Agent:
  Performs industry-chain research.
  Checks evidence, contradictions, and data quality.
  Screens companies and stocks.
  Builds a hypothesis.
  Maps it to a registered strategy template.
  Freezes data/protocol.
  Runs B4-safe backtest.
  Runs B5 OOS validation and Gate.
  Explains whether the hypothesis is rejected, needs review, or can be considered for promotion.
  Only after human approval and promotion can later modules generate action plans.
```

The user talks to the agent and performs simple approvals. The agent operates the complex research, validation, report, and backtest workflow.

B5 must therefore produce plain-language verdicts and evidence summaries, but all trading logic, OOS logic, and Gate logic must be deterministic code.

---

## 3. What B5 Is

B5 is the OOS validation, budget, immutable report, and Gate layer.

It consumes:

- B2 `StrategyDraft`;
- B3 `ResearchProtocolSnapshot`;
- B3 `DataSnapshotManifest`;
- B3 `PointInTimeMembershipSnapshot`;
- B4 formal qualification result;
- B4 event-driven backtest result.

It produces:

- `OOSEvaluationLedger` snapshots;
- OOS budget reservations and completed draw records;
- `ImmutableBacktestReport`;
- `PrototypeGateResultV2`;
- optional `HumanPromotionConfirmation`;
- no promotion by itself.

B5 may call `StrategyPromotionReducer` only in the explicit human-approved promotion path. Gate itself must not change lifecycle state.

---

## 4. What B5 Is Not

B5 is not:

- live trading;
- Signal Board;
- broker integration;
- order execution;
- parameter optimization;
- strategy search;
- profitability proof;
- LLM scoring;
- manual technical-parameter tuning;
- a way to make a bad backtest look acceptable.

B5 must not:

- generate buy/sell recommendations directly to the user;
- mark `prototype_passed` without human confirmation;
- change B2 strategy parameters;
- change B3 protocol snapshots;
- change B4 backtest semantics;
- run extra OOS attempts outside budget;
- hide rejected reports;
- delete or overwrite failed results.

---

## 5. Core Design Decisions

### 5.1 Theme-Level OOS Budget

The OOS budget belongs to the theme/hypothesis, not to individual stocks.

```text
one theme
  = one hypothesis family
  = one strategy family
  = one OOS budget
```

The default budget is three OOS draws. The system must enforce:

- same `(strategy_config_hash, data_snapshot_hash, gate_criteria_hash)` returns cached result and does not consume a new draw;
- any change to one of the three hashes consumes a new draw;
- failed infrastructure runs release reservation and do not consume a draw;
- completed formal reports consume one draw even if the Gate rejects;
- after draw 3, new OOS attempts are rejected;
- cross-theme reuse of the same OOS window and same data snapshot is rejected unless explicitly represented as the same shared OOS window protocol.

### 5.2 Frozen Gate Criteria

Gate criteria are frozen before OOS execution.

The frozen policy includes:

- minimum OOS sample coverage;
- minimum completed round trips;
- minimum active trading months;
- max single-month PnL contribution;
- max single-symbol PnL contribution;
- benchmark comparison rules;
- control group comparison rules;
- base/stress cost requirements;
- data quality blocking rules;
- stricter thresholds for draw 2 and draw 3.

The user, LLM, API request, and UI must not modify these thresholds.

### 5.3 B4 Is Mandatory

B5 cannot run unless B4 formal qualification has passed through `run_qualification_with_b3_protocol()`.

Legacy B4 `run_qualification()` is compatibility-only and is not a valid B5 prerequisite.

B5 must reject:

- missing B3 protocol;
- missing data snapshot hash;
- B4 result without protocol/data IDs;
- B4 result containing Gate/promotion fields;
- any B4 run using a forward watchlist or static current symbols.

### 5.4 Reports Are Append-Only

Every formal OOS attempt must produce an immutable report or an explicit failed reservation record.

Rejected strategies remain visible. Failed reports are not deleted, hidden, overwritten, or "cleaned up" into success.

### 5.5 Gate Is Deterministic

Gate reads only frozen artifacts:

- `ResearchProtocolSnapshot`;
- `ImmutableBacktestReport`;
- frozen gate criteria;
- OOS ledger snapshot.

Gate outputs only:

```text
rejected
needs_review
candidate_for_prototype_passed
```

Gate never outputs `prototype_passed`.

---

## 6. Main Workflow

```text
B2 StrategyDraft
  -> B3 ResearchProtocolSnapshot
  -> B4 formal qualification
  -> B5 OOS reservation
  -> B4 event-driven OOS run
  -> base cost report
  -> stress cost report
  -> benchmark/control comparisons
  -> immutable report
  -> deterministic Gate
  -> plain-language explanation
  -> optional human confirmation
  -> StrategyPromotionReducer
  -> prototype_passed
```

B5 must preserve a hard separation:

- OOS controller reserves and routes.
- B4 executes time-safe backtest.
- Report builder records immutable facts.
- Gate computes verdict.
- Human confirmation records approval/rejection.
- Promotion reducer is the only writer of `prototype_passed`.

---

## 7. Proposed Components

### 7.1 `OOSEvaluationController`

Responsible for:

- loading frozen B3 protocol;
- verifying B4 qualification metadata;
- checking and reserving OOS budget;
- running or retrieving cached OOS evaluation;
- coordinating report and Gate creation;
- releasing reservation on infrastructure failure.

It must not:

- compute signals itself;
- change strategy config;
- change OOS dates;
- change Gate thresholds;
- write `prototype_passed`.

### 7.2 `OOSBudgetLedger`

Responsible for:

- append-only ledger snapshots;
- reservation IDs;
- completed draw IDs;
- draw index 1/2/3;
- cache keys;
- budget exhaustion.

Cache key:

```text
(strategy_config_hash, data_snapshot_hash, gate_criteria_hash)
```

Cross-theme reuse guard:

```text
(shared_oos_window_id, data_snapshot_hash)
```

### 7.3 `BacktestReportBuilder`

Responsible for converting B4 run output into `ImmutableBacktestReport`.

Report must include:

- protocol IDs;
- all three hashes;
- OOS draw index;
- shared OOS window ID;
- B4 read trace summary;
- future-data violations count;
- base cost result;
- stress cost result;
- benchmark comparison;
- control group comparison;
- concentration metrics;
- data quality status;
- adjustment mode/fingerprint;
- delisting/liquidation impact;
- report hash.

Report must include a fixed disclaimer:

```text
This report is historical OOS validation under frozen data, frozen strategy, and frozen Gate policy.
It is not a future profit guarantee, not a live trading instruction, and not a promotion by itself.
```

### 7.4 `ControlComparisonEngine`

Responsible for deterministic comparisons against:

- frozen benchmark;
- equal-weight same-universe control;
- weakened or rule-disabled control where applicable.

It must answer:

- did the strategy beat benchmark after costs?
- did it beat a simple same-universe baseline?
- is performance mostly beta exposure?
- is performance dominated by one symbol or one month?

No LLM may score or override these comparisons.

### 7.5 `CostStressRunner`

Runs base and stress cost variants using frozen policy.

Stress cost may increase:

- commission;
- slippage;
- liquidity haircut;
- suspension/delisting penalty;
- delayed execution assumptions.

Stress policy cannot be lowered at runtime. If base passes but stress fails, Gate can be at most `needs_review`.

### 7.6 `PrototypeGateV2Evaluator`

Responsible for deterministic verdict generation.

Gate checks must include:

- B4 qualification passed;
- protocol/report/hash consistency;
- no future-data violation;
- OOS budget draw valid;
- OOS sample size sufficient;
- active trading months sufficient;
- completed round trips sufficient;
- data quality not insufficient;
- base and stress cost availability;
- benchmark/control comparison;
- beta domination;
- single-symbol and single-month concentration;
- draw-specific stricter thresholds.

Gate must not use absolute return alone as pass criterion. A high return that fails benchmark/control/stress/concentration checks must be rejected or `needs_review`.

### 7.7 `GateExplanationBuilder`

Responsible for plain-language explanation for the user.

Allowed:

- summarizing deterministic Gate facts;
- explaining why strategy was rejected or needs review;
- translating metrics into understandable language;
- listing non-technical decision choices.

Forbidden:

- changing verdict;
- recommending trades;
- inventing reasons not in the report;
- overriding deterministic checks;
- asking user to tune technical thresholds.

---

## 8. Data Contracts

Existing contracts should be reused first:

- `OOSEvaluationLedger`;
- `ImmutableBacktestReport`;
- `PrototypeGateResultV2`;
- `HumanPromotionConfirmation`;
- `StrategyPromotionRecord`;
- `StrategyLifecycleState`.

Add new B5-local types only if existing contracts cannot express:

- reservation lifecycle;
- report payload schema;
- Gate check item schema;
- control comparison result;
- stress cost result;
- user-facing explanation snapshot.

Any new type must be:

- frozen;
- append-only;
- explicit about failure/degraded states;
- free of buy/sell action instructions;
- free of LLM-generated trading logic.

---

## 9. Error Handling

B5 must fail loud.

Hard reject:

- no B3 protocol;
- no B4 formal qualification;
- hash mismatch;
- OOS budget exhausted;
- active reservation conflict;
- forward watchlist or static symbol list;
- missing B4 read trace;
- future data violation;
- missing base/stress cost result;
- missing benchmark/control comparison;
- report hash mismatch;
- Gate criteria hash mismatch;
- attempt to write `prototype_passed` outside reducer.

Explicit degraded or needs review:

- partial but non-blocking data gaps;
- low trade count;
- narrow active trading months;
- high concentration;
- base passes but stress fails;
- control comparison inconclusive.

Never fallback to:

- static current symbols;
- current confirmed candidate pool;
- weaker Gate thresholds;
- user-selected OOS windows;
- filled missing data;
- LLM judgment.

---

## 10. User Decision Surface

The user sees:

```text
Verdict:
  rejected | needs_review | candidate_for_prototype_passed

Plain reason:
  "Rejected because the strategy did not beat the benchmark after stress costs."

Evidence:
  - OOS draw used: 1 of 3
  - Data quality: ok/degraded/insufficient
  - Stress cost: pass/fail
  - Benchmark/control result: pass/fail
  - Concentration risk: pass/fail

Allowed actions:
  - reject
  - ask agent to explain
  - approve promotion only if verdict is candidate_for_prototype_passed
```

The user does not see or edit:

- threshold values as editable controls;
- strategy parameter controls;
- OOS date pickers;
- benchmark selectors;
- cost model sliders.

---

## 11. LLM Policy

B5 uses no LLM for computation.

LLM may only be used after deterministic Gate output exists, for:

- summarizing report;
- explaining rejection in plain language;
- drafting user-facing text;
- answering questions about what the deterministic result means.

LLM must not:

- run routing;
- decide retries;
- choose OOS windows;
- choose thresholds;
- score Gate;
- edit verdict;
- edit report payload;
- create `prototype_passed`;
- create trade instructions.

If LLM summary conflicts with deterministic report, deterministic report wins.

---

## 12. File Ownership Proposal

Likely new files:

- `backend/services/b5_oos_types.py`
- `backend/services/oos_budget_ledger.py`
- `backend/services/oos_evaluation_controller.py`
- `backend/services/backtest_report_builder.py`
- `backend/services/control_comparison.py`
- `backend/services/cost_stress_runner.py`
- `backend/services/prototype_gate_v2.py`
- `backend/services/gate_explanation_builder.py`

Likely tests:

- `tests/test_b5_oos_budget.py`
- `tests/test_b5_oos_controller.py`
- `tests/test_b5_report_builder.py`
- `tests/test_b5_control_comparison.py`
- `tests/test_b5_cost_stress.py`
- `tests/test_b5_gate_v2.py`
- `tests/test_b5_promotion_boundary.py`
- `tests/test_b5_compatibility.py`
- `tests/test_b5_vertical_flow.py`

Modify only if needed:

- `backend/db/strategy.py` for append-only reservation/report read helpers;
- `contracts/strategy.py` only if existing B1 contracts are insufficient, and only after explicit review.

Do not modify without escalation:

- B4 time cursor and future-data guard semantics;
- B3 data snapshot semantics;
- old `strategy_core/prototype_gate.py` stable gate;
- A-module research storage;
- Signal Board action generation.

---

## 13. Acceptance Criteria

B5 is acceptable only if all are true:

1. Formal OOS cannot run without B3 protocol and B4 formal qualification.
2. User/LLM/API cannot choose OOS dates.
3. User/LLM/API cannot modify Gate thresholds.
4. OOS budget max is enforced at three completed draws.
5. Cache replay does not consume budget.
6. Any hash change consumes budget.
7. Concurrent reservations cannot create a fourth draw.
8. Cross-theme OOS reuse is blocked or explicitly shared.
9. Base and stress cost results are both present.
10. Benchmark and control comparisons are present.
11. Gate uses relative performance, stress cost, controls, and concentration, not absolute profit alone.
12. Gate verdict never equals `prototype_passed`.
13. Gate never changes lifecycle state.
14. Only `StrategyPromotionReducer` can write `prototype_passed`.
15. Rejected reports stay visible.
16. Failed infrastructure runs release reservation and do not create fake success.
17. Data insufficiency cannot produce `candidate_for_prototype_passed`.
18. Future-data violations hard reject.
19. LLM cannot compute or override Gate.
20. User-facing explanation is derived from deterministic report only.
21. B5 does not generate buy/sell action plans.
22. B5 does not touch live trading or broker integration.

---

## 14. Suggested Task Breakdown

Task 1: B5 contracts and fixtures.

Task 2: OOS budget ledger and atomic reservation.

Task 3: B4/B3 prerequisite boundary for OOS controller.

Task 4: Report builder from B4 event backtest result.

Task 5: Base/stress cost orchestration.

Task 6: Benchmark and control comparison.

Task 7: PrototypeGateV2 evaluator.

Task 8: User-facing explanation builder with deterministic source binding.

Task 9: Human confirmation and promotion boundary.

Task 10: Vertical flow test from frozen protocol to Gate result.

Task 11: Compatibility tests proving no Signal Board, no live trading, no LLM Gate, no parameter tuning.

Task 12: Verification documentation.

---

## 15. Stop Conditions

Stop and escalate if implementation appears to require:

- asking the user to choose a technical parameter;
- using LLM to score Gate;
- changing B4 time semantics;
- weakening B3/B4 future-data guards;
- allowing forward watchlists into formal OOS;
- increasing OOS budget silently;
- deleting rejected reports;
- letting Gate write lifecycle state;
- generating Signal Board actions before `prototype_passed`;
- introducing live trading or broker execution.

---

## 16. Success Definition

B5 succeeds when the agent can tell the user, in plain language:

```text
This hypothesis was tested on frozen out-of-sample data under frozen rules.
It was rejected / needs review / is a candidate for promotion.
Here is why.
Here is what risk remains.
You may approve promotion only if the deterministic Gate produced candidate_for_prototype_passed.
This is still not a live trading instruction.
```

The system should reject borderline strategies by default. B5 is allowed to kill potentially good ideas. It is not allowed to pass fake-good results.
