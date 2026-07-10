# TraderLens Credible Manual Trading Decision Closure Plan (V2)

> **For agentic workers:** REQUIRED SUB-SKILL: use `subagent-driven-development` or `executing-plans` task by task. Check each checkbox only with fresh evidence. This document is a plan only; it does not authorize a release, a commit, a vendor purchase, or live trading.

**Supersedes:** `docs/superpowers/plans/2026-07-01-v1-product-closure-rebuild-plan.md` and replaces the previous revision of this file as the implementation plan for decision closure.

**Goal:** Deliver one browser-proven, personal A-share manual-decision loop: natural-language friend recommendation → evidence-backed ResearchCase → approved forward candidate → signal from a separately validated strategy → Action Plan → user-confirmed buy → Observation Pool → Daily Signal → user-confirmed sell → P&L → Discipline Review; or show the precise gate that prevents it.

**Architecture:** Start with one deliberately failing browser journey, then repair only its earliest failed business step. Gate 0 proves the exact research, alpha, and point-in-time data inputs before any formal backtest wiring. Reuse Workbench, ResearchCase, `StrategyTemplateDefinition`, B3 PIT protocol types, the OOS ledger, B6/OOS/Gate/Promotion, Signal Board, Action Plan, execution logs, Observation Pool, and reviews. An Execution Card is an Action Plan view only; it is not a second persisted state machine.

**Tech stack:** FastAPI, SQLite, Pydantic, `strategy_core`, Tushare Pro, local Parquet/JSON manifests, Next.js, Playwright, pytest.

---

## 1. Product truth and non-goals

- TraderLens is personal research and manual decision support. It does not connect to a broker, submit orders, promise returns, or infer actual execution, price, quantity, or P&L.
- The `v1.0.0` tag remains an internal UI/degraded-flow snapshot. It is not product acceptance and must not be represented as such.
- `confirmed_candidate_pool` is a forward-only research output. It may be consumed by current Signal Board generation only after a strategy has separately reached `prototype_passed`; it must never be converted to a historical backtest universe.
- A data fault, insufficient data, missing provenance, unconfigured guard, failed Gate, or exhausted OOS budget returns a visible blocking state. No fallback list, LLM guess, or synthetic data may upgrade it.
- `self_reported` is the only V2 evidence level. Attachment storage and hashes are deferred; the UI must state that self-reported evidence is not broker verification.

> **V2 scope reduction — reviewer accepted on 2026-07-10:** V2 replaces the earlier goal of Serenity automatic industry-chain discovery with user-proposed industry-chain hypothesis verification. It does not deliver automatic chain discovery or a verified industry-chain dataset.

### Retained, removed, and migrated design

| Decision | V2 rule |
|---|---|
| Keep | Workbench, ResearchCase, template governance, PIT qualification, B6/OOS/Gate/Promotion, Market Guard, capital context, fixed-stop logic, Signal Board data object, Action Plan, execution log, Observation Pool, P&L, Discipline Review. |
| Remove from the prior revision | New `contracts/template_governance.py`, `contracts/validation_data.py`, research-budget contract/service, execution-observation contract/service, attachment/hash subsystem, separate persisted Execution Card, and three disconnected acceptance scripts. |
| Extend instead | `contracts/strategy.py` / `strategy_template_library.py`; `backend/services/b3_protocol_types.py`; `backend/services/oos_budget_ledger.py`; existing research, execution, observation, and review contracts/services. |
| Migrate | The four hard-coded templates lose implicit `approved` status. They become `candidate` until their source dossier and frozen rule mapping pass Task 4. Existing persisted records stay readable and are labelled `legacy_ungoverned`, never promoted. |

## 2. Gate 0 — inputs that must be proved before formal validation

Gate 0 is a two-level data gate, not a documentation exercise. `feasibility_probe_passed` proves only provider access, fields, and landing format for 2019–2025. `formal_qualified` proves complete 2010-to-last-closed-trading-day coverage and is the only status accepted by B6/OOS/Gate, Promotion, and Market Guard freeze. A failing probe stops at `validation_unavailable` or `research_unavailable` with its stored reason.

### 2.1 V2 industry-chain hypothesis verification boundary

V2 does **not** claim that TraderLens automatically completes industry-chain research, and it does not define a user statement as a dataset, source, or evidence. A user may submit `user_industry_chain_hypothesis` with `upstream_entity`, `downstream_entity`, `relation_type` (`supplier`, `customer`, `competitor`, `component`, `channel`, `other`), `asserted_by`, `asserted_at`, `scope_note`, and `research_case_id`. This is a pending hypothesis only, stored in the existing ResearchCase evidence/counter-evidence payload.

- `stock_basic` may resolve listed-company identity; `income`, `anns`, and company facts may be displayed as supporting facts, counter-evidence, or gaps. They do not verify a chain edge.
- The existing `stock_basic` peer list, LLM summaries, and symbol heuristics may not create, confirm, or rank a chain edge.
- The hypothesis is current-research context only. It has no historical membership claim and cannot enter `BacktestUniverseSpec`, template selection, OOS inputs, or a trading decision.
- A case with no user hypothesis displays `research_requires_chain_hypothesis`; a case with a hypothesis displays `用户产业链假设（待验证）` and the available facts/counter-evidence. Neither state may display “产业链研究完成” or “产业链已验证”.

A later version may add official company-disclosure corpus or an authorised chain-data provider only under a new plan that names its licence, document/effective dates, coverage, extraction rule, and evidence status. That work is intentionally outside this V2 closure plan.

### 2.2 PIT vendor, interfaces, permissions, coverage, and local format

**Candidate formal-validation provider:** Tushare Pro, using the account token configured for the local owner. It becomes the formal-validation source only after Gate 0 has made successful, non-empty probes and recorded the account’s observed permission result. Tushare exposes a permission error as HTTP/API code `2002`; this must be recorded as a failed gate, not retried as a different source. [Tushare HTTP API documentation](https://www.tushare.pro/document/2?doc_id=130)

**Required interface bundle and purpose:**

| Purpose | Required Tushare Pro interfaces | Minimum history to prove |
|---|---|---|
| Trading calendar and listed/de-listed identity | `trade_cal`, `stock_basic` for `L`, `D`, and `P`, `namechange` | 2010-01-01 through the last fully closed trading day |
| Raw executable market data | `daily`, `stk_limit`, `suspend_d`, `adj_factor` | same range; all listed A-share symbols sampled across every calendar year |
| Liquidity and market guard inputs | `daily_basic`, `index_daily`, `index_member_all` | same range; HS300 and all required members/dates |
| PIT financial facts | `income`, `balancesheet`, `cashflow`, `fina_indicator`, using `ann_date` as availability date | reports announced from 2010-01-01 through the last fully closed trading day |
| Industry classification / themed membership support | `index_classify`, `index_member_all`, plus the documented THS/SW endpoints actually granted to the account | effective membership dates for every used index; current-only classifications fail PIT qualification |

`adj_factor` is captured as raw vendor output but V1 validation uses raw OHLC execution prices. No present-day forward-adjusted series may be treated as a past observable value; any future adjusted-price feature needs an explicit future-data proof before use. Tushare’s own documentation notes that its adjusted data depend on the selected end date. [Tushare adjustment documentation](https://www.tushare.pro/document/2?doc_id=146)

**Local immutable landing format:** `data/pit/tushare/<snapshot_id>/` with one Parquet file per interface and retrieval partition (`daily/trade_date=YYYYMMDD/*.parquet`, analogous partitions for other dated datasets), `manifest.json`, and `manifest.sha256`. The manifest must list interface, exact requested fields and parameters, retrieval UTC time, source response row count, earliest/latest effective date, missing-date/symbol counts, raw-file SHA-256 values, token-free permission result, adjustment policy, and source-version string. `b3_protocol_types.py` owns the manifest reference and qualification result; no new validation-data contract is created.

**Gate 0 PIT acceptance has two explicit outcomes:**

- `feasibility_probe_passed`: one command downloads/probes every required interface for 2019-01-01 through 2025-12-31, writes a manifest, samples at least one main-board, ChiNext, STAR, suspended, ST/name-changed, and delisted symbol, and proves the manifest hash replays unchanged. It authorizes no formal validation.
- `formal_qualified`: a separate full acquisition covers 2010-01-01 through the last fully closed trading day under interface-specific expected-row rules. `daily`, `stk_limit`, and `daily_basic` require rows only for stocks that are listed and normally trading on that date; a missing market row for a suspended stock is valid only when `suspend_d` explicitly explains it, and no market row is required before listing or after delisting. `income`, `balancesheet`, `cashflow`, and `fina_indicator` require report-period records with their `ann_date` availability, not daily records. `namechange` and `suspend_d` are sparse event tables, so a legal empty result is not a gap. Index-membership data must cover each member’s effective period. Only a missing value that these rules cannot explain is a blocking gap. The replayed full manifest must have the same hash and no blocking gaps. Only this outcome may enter formal B6/OOS/Gate, Promotion, or the Market Guard candidate-to-frozen replay.

### 2.3 First alpha sources and lifecycle

The first source dossiers are fixed before any template can be `approved`:

| Existing template | Initial source dossier | V2 initial state |
|---|---|---|
| `relative_strength_rotation_v1` | Jegadeesh & Titman (1993), *Returns to Buying Winners and Selling Losers*, DOI `10.1111/j.1540-6261.1993.tb04702.x` | candidate |
| `theme_momentum_breakout_v1` | Moskowitz & Grinblatt (1999), *Do Industries Explain Momentum?*, DOI `10.1111/0022-1082.00146` | candidate |
| `volume_breakout_followthrough_v1` | Lee & Swaminathan (2000), *Price Momentum and Trading Volume*, DOI `10.1111/0022-1082.00280` | candidate |
| `trend_pullback_watch_v1` | no source dossier | retired for V2; it cannot be mapped or validated |

Each candidate becomes `approved` only when the extended `StrategyTemplateDefinition` records: source citation and retrieval date; a one-to-one source-claim-to-frozen-rule mapping; market-scope differences from the source; required PIT fields; a deterministic implementation hash; independent reviewer identity/date; and review due date. The reviewer approves provenance and fidelity, never an expected return. A source mismatch, failed PIT qualification, failed Gate, or expired review retires the version for new mapping but preserves historic reports. New template/version proposals repeat this process; paraphrases and rule changes create a new candidate and consume the existing family’s OOS budget through `oos_budget_ledger.py`.

### 2.4 Market Guard candidate-to-frozen path

Reuse the candidate rules frozen in `docs/superpowers/specs/2026-07-02-risk-attribution-design-freeze.md`; do not invent or tune another guard. `backend/config/market_regime_thresholds.yaml` starts with `validation_status: candidate` and these exact pre-registered rules:

| State | PIT metric and source | Candidate trigger |
|---|---|---|
| `extreme_breadth_selloff` | proportion of eligible A shares with `daily.pct_chg <= -5`, from qualified `daily` plus listing/suspension data | greater than `0.80` |
| `structural_breakdown` | `000300.SH` return from qualified `index_daily` | one day `<= -0.05` or compounded five trading days `<= -0.10` |
| `liquidity_exhaustion` | qualified all-A-share `daily.amount` divided by its preceding 30 completed trading-day mean | less than `0.30` |

`trade_cal`, `daily`, `index_daily`, listing/delisting and suspension data from the same qualified PIT manifest are mandatory. Missing any required daily aggregation input after applying the `formal_qualified` expected-row rules produces `data_insufficient`/`data_fault`, never `ok`; the zero-gap rule does not require every stock to have a market row on every date. The configuration contains its semantic SHA-256, version, candidate values, source manifest hash, validation-report hash, `validation_status`, `validated_at`, `frozen_at`, and `approved_by`.

The following windows and product-usability rule are pre-registered before reading replay results: stress window A is 2015-06-15 through 2015-08-31; stress window B is 2020-03-09 through 2020-03-23; normal window is 2017-09-01 through 2017-11-30. An acceptable data gap is **zero** missing required daily aggregation inputs after applying the `formal_qualified` expected-row rules on any `trade_cal` trading day; dates declared non-trading by `trade_cal` are not gaps. In the normal window, `block_new_entry` caused by an extreme market state may occur on at most `floor(0.05 * normal_window_trading_day_count)` days. `data_insufficient` and `data_fault` are reported separately and cannot be hidden in that ratio.

The guard becomes `frozen` only after a `formal_qualified` replay from 2010-01-01 to the last fully closed trade day proves: the registered zero-gap rule; no value read after its `as_of_date`; stable output from two independent replays of the same full manifest; at least one extreme-market block in each registered stress window; the registered normal-window block-ratio limit; and an immutable report containing per-rule trigger counts, blocked-day count, normal-window denominator/ratio, data-gap count, manifest hash, configuration hash, and source code revision. A human approval may freeze this unchanged candidate configuration only after those checks pass. Any changed threshold, metric, universe, data policy, window, or usability limit is a new candidate and blocks new entries until it completes the same path. Freezing validates deterministic survival behaviour, not market-timing alpha.

## 3. Decision and agent boundaries

### 3.1 Open cognition, white-listed tools, black-listed decisions

The LLM may understand free-form messages, summarize retrieved evidence, relate prior cases, and draft explanations. It receives only these read-only, audited tools: `find_research_cases`, `read_research_case`, `find_strategy_history`, `read_strategy_report`, `read_open_action_plans`, `read_positions`, and `read_reviews`.

The LLM may not call a side-effect tool. Deterministic services, plus explicit user confirmation where required, exclusively decide identity confirmation, template/rule selection, PIT qualification, OOS budget reservation, Gate verdict, promotion, signal generation, market state, Action Plan eligibility, execution facts, P&L, and review attribution. These are a hard blacklist even if an LLM explanation names a different conclusion.

### 3.2 Durable context and latency budget

Replace “latest ten messages plus positions” with a deterministic context assembler in the existing Workbench/research query path. It loads, in this order and with stable identifiers: the current message; last 10 messages; identity claims; open positions; the three most recent same-symbol/theme ResearchCases with approval and evidence/counter-evidence summaries; up to five same-template/family rejected or retired strategies with reason and report ID; open Action Plans; and the three most recent relevant reviews. Older records remain discoverable through the white-listed history tools, so “the strategy rejected before” has a record-based answer rather than a summary guess.

V2 is a single-backend-process personal deployment: every supported startup and acceptance command launches `backend.app.main:app` with `--workers 1`; `WEB_CONCURRENCY` and `UVICORN_WORKERS` must be unset or equal to `1`; multiple backend processes are out of scope. The shared startup helper and main browser script must assert these values and fail before testing if they differ.

Every provider call goes through `backend/services/llm_client.py`. Its process-wide `threading.BoundedSemaphore(2)` is acquired before `create_message()` and released in `finally`; a third simultaneous request returns `llm_concurrency_exhausted` without queuing or retrying. Together with the single-worker deployment rule, this is a global V2 limit rather than a per-conversation convention.

The Workbench creates one `decision_loop_id` on the initial recommendation and persists its call counter/timestamps in existing conversation/artifact metadata. The entire friend-recommendation-to-review loop has a hard **three-call** budget; after the third call the loop returns `llm_budget_exhausted` and must not start a fourth call. Template matching, validation, promotion, signal, guard, Action Plan, user confirmation, observation, P&L, and review remain deterministic. Natural-language execution feedback uses the existing deterministic interpreter; ambiguous wording asks for clarification and never invokes the LLM.

| Friend-loop stage | Maximum LLM calls | Rule |
|---|---:|---|
| Initial friend recommendation | 1 | intent/entity extraction only |
| ResearchCase evidence synthesis | 2 | existing two-phase Serenity planner and synthesizer; deterministic tools run between them |
| Research approval and candidate pool | 0 | user action plus deterministic persistence |
| Existing promoted-strategy signal, Market Guard, Action Plan | 0 | deterministic services only |
| Buy/sell/skip/partial confirmation | 0 | structured confirmation or deterministic interpreter only |
| Observation, Daily Signal, P&L, Discipline Review | 0 | deterministic reducers and template text only |
| **Whole loop** | **3** | no overflow, retry, or extra explanation call |

Each call has an 8-second timeout and no retry loop. For 30 production-equivalent complete loops, record stage call counts, semaphore rejections, and elapsed time. Measure automated end-to-end elapsed time from initial submission to final automated result, subtracting each user-wait interval (`approval_shown_at`→`approval_received_at`, `action_plan_shown_at`→buy confirmation, and sell request→sell confirmation). Acceptance requires automated-loop P50 ≤ 25 seconds and P95 ≤ 45 seconds, plus per-stage P50/P95. A timeout returns an explicit recoverable unavailable state, never a guessed route.

## 4. Delivery sequence — cover the chain first, then deepen it

### Task 0: Write and run the one failing browser acceptance chain

**Files:** create `scripts/verify_credible_manual_trade_closure.py`, `docs/verification/CREDIBLE_PRODUCT_ACCEPTANCE.md`; modify `scripts/runtime_process_helpers.py`.

- [ ] Drive a real browser against the local frontend and backend, with no direct database insert and no API-only substitute, through this exact sequence:

  ```text
  朋友推荐 XX
  → ResearchCase → user chain hypothesis + facts/counter-evidence → approval
  → confirmed_candidate_pool → separately validated strategy signal
  → Market Guard → Action Plan → confirm buy → Observation Pool
  → Daily Signal → confirm sell → P&L → Discipline Review
  ```

- [ ] The script uses an explicitly supplied real snapshot ID and a real self-reported ResearchCase assertion. It creates no synthetic market rows, template results, signals, executions, or reviews. Missing Gate 0 input fails with the exact first missing business step.
- [ ] Launch the backend only as `.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8010 --workers 1`; fail if `WEB_CONCURRENCY` or `UVICORN_WORKERS` is set to a value other than `1`.
- [ ] Run it before any module repair, save DOM/network/run-ID evidence, and record only the first failure in `CREDIBLE_PRODUCT_ACCEPTANCE.md`.

**Acceptance:** the initial run fails loudly at its actual first missing product step; it does not split into friend/strategy/execution scripts or label a partial path as E2E.

### Task 1: Complete Gate 0 before formal validation wiring

**Files:** modify `backend/services/data_tools.py`, `backend/services/b3_protocol_types.py`, `backend/services/strategy_template_library.py`, `contracts/strategy.py`; create `scripts/verify_gate0_data_feasibility.py`; test `tests/test_gate0_data_feasibility.py`.

- [ ] Implement the `user_industry_chain_hypothesis` schema in the existing ResearchCase payload, label it pending verification, and disable peer/symbol inference as chain evidence.
- [ ] Implement the exact Tushare interface probe, Parquet landing manifest, content hashes, and qualification outcome in the existing B3 types.
- [ ] Persist and expose `feasibility_probe_passed` and `formal_qualified`, with the latter superseding the former for the same provider/data policy; record observed permissions, missing coverage, and all queries without the token. Reject formal validation unless the full-range manifest is `formal_qualified`.
- [ ] Extend the existing template definition/library with the source dossier and lifecycle fields from section 2.3. Migrate the four templates to the stated candidate/retired states.
- [ ] Re-run the browser chain. Repair only its first now-failing step; do not begin OOS wiring when Gate 0 is red.

**Acceptance:** the chain can create an honest ResearchCase under the declared V2 hypothesis boundary. Formal validation is mechanically impossible without a replayable `formal_qualified` PIT manifest and an approved source-backed template; `feasibility_probe_passed` alone is rejected.

### Task 2: Connect Workbench to ResearchCase and persistent context

**Files:** modify `backend/api/workbench_handlers.py`, `backend/api/research.py`, `backend/db/agent_workbench.py`, `backend/services/llm_client.py`, `scripts/runtime_process_helpers.py`, `frontend/app/workbench/page.tsx`; create `frontend/app/research/page.tsx`, `frontend/app/research/[research_id]/page.tsx`; test `tests/test_workbench_research_context.py`, `tests/test_llm_client_limits.py`.

- [ ] Add the deterministic context assembler and the read-only history-tool audit records described in section 3.2.
- [ ] Route a verified recommendation to a ResearchCase, capture the user chain hypothesis and Tushare facts/counter-evidence without calling either proof, and require explicit `continue`, `stop`, or `observe` approval.
- [ ] Persist a forward-only `confirmed_candidate_pool` only after approval. It must display its research provenance and explicit non-backtest boundary.
- [ ] Extend the existing `LLMClient` with the process-wide concurrency-two semaphore, enforce the three-call `decision_loop_id` budget, and record the stage/automated-loop latency telemetry in section 3.2. Make the shared startup helper enforce the single-worker command/environment rule. A data or LLM failure renders `research_unavailable`, never an invented conclusion.
- [ ] Re-run the one browser chain and repair only its first remaining failure.

**Acceptance:** the user can retrieve a prior rejection/case by context or history tool, and a friend recommendation reaches a traceable candidate pool without becoming a buy signal.

### Task 3: Qualify PIT universe and real execution inputs

**Files:** modify `strategy_core/universe_builder.py`, `strategy_core/data_source_protocol.py`, `backend/services/b6_validation_flow.py`, `backend/services/b3_protocol_types.py`; test `tests/test_universe_builder.py`, `tests/test_b3_pit_manifest.py`, `tests/test_fill_simulator.py`.

- [ ] Extend the existing B3 manifest types with effective membership, listing/delisting, ST/name-change, suspension, price-limit, liquidity, raw-price, and announcement-availability references.
- [ ] Make `build_universe()` accept only a `formal_qualified` point-in-time universe for formal OOS. `static_list`, `confirmed_candidate_pool`, and `feasibility_probe_passed` remain rejected for historical validation.
- [ ] Replay T+1, T+1 sellability, price limits, suspension, liquidity, board lots, costs, delisting, and overnight next-open fills from the qualified local snapshot.
- [ ] Re-run the one browser chain and repair only its first remaining failure.

**Acceptance:** no formal report can be created from static/current membership, future-adjusted price assumptions, or an incomplete manifest.

### Task 4: Govern alpha, OOS reuse, and promotion using existing objects

**Files:** modify `contracts/strategy.py`, `backend/services/strategy_template_library.py`, `backend/services/template_matcher.py`, `backend/services/oos_budget_ledger.py`, `backend/services/b6_validation_flow.py`, `backend/services/strategy_promotion_reducer.py`; test `tests/test_template_governance.py`, `tests/test_oos_budget_ledger.py`, `tests/test_b6_validation_flow.py`.

- [ ] Make matching deterministic against the approved frozen rule schema; LLM extraction cannot choose parameters, version, family, or status.
- [ ] Use the existing append-only OOS ledger for `(hypothesis_family_id, frozen_template_hash, strategy_config_hash, data_snapshot_hash, protocol_hash)`. Identical replay returns its immutable report; any rule/version change consumes the family budget.
- [ ] Keep the pre-frozen three-draw OOS limit and enforce source status, `formal_qualified` PIT status, Canary, controls, base/stress costs, Gate, and explicit human confirmation before `StrategyPromotionReducer` alone writes `prototype_passed`.
- [ ] Admit only the promoted revision to the existing Signal Board. Rejected/candidate/retired strategies remain discoverable in history and cannot create signals.
- [ ] Re-run the one browser chain and repair only its first remaining failure.

**Acceptance:** the first source-backed template can either truthfully reach a promoted signal through real qualified data or visibly stop at its exact Gate; no hard-coded `approved` template bypasses that evidence.

### Task 5: Enforce Action Plan, user-confirmed execution, observation, and review

**Files:** create `backend/services/market_regime_guard.py`, `backend/config/market_regime_thresholds.yaml`; modify `backend/services/capital_context.py`, `backend/services/action_plan_builder.py`, `backend/api/workbench_execution_feedback.py`, `backend/services/observation_pool.py`, `backend/services/discipline_review.py`, `contracts/live_trade.py`; test `tests/test_market_regime_guard.py`, `tests/test_v1_capital_context.py`, `tests/test_c3_action_plan_boundary.py`, `tests/test_v1_observation_pool.py`, `tests/test_v1_discipline_review.py`.

- [ ] Create `market_regime_thresholds.yaml` from the exact candidate rules in section 2.4; calculate and persist its semantic hash, candidate status, PIT manifest reference, and validation-report reference.
- [ ] Implement the section 2.4 guard replay and freeze checks using only a `formal_qualified` manifest. Only an unchanged, human-approved `frozen` configuration may report `ok` for a new-entry decision; candidate, missing, failed, or mismatched configuration exposes `block_new_entry`.
- [ ] Require `formal_qualified` market data, frozen guard, capital check, and frozen invalidation/stop data before an existing Action Plan can be `eligible_for_manual_entry`; otherwise expose `block_new_entry` or `observe_only` with reason.
- [ ] Render the Action Plan as the only execution decision state. User buy/sell/skip/partial confirmation writes the existing execution log with `evidence_level=self_reported`; no separate Execution Card record is introduced.
- [ ] Preserve deterministic Daily Signal priority: data fault/insufficient → invalidation → fixed-stop sell → risk → hold. Market risk cannot fabricate a sell fill.
- [ ] Compute P&L only from confirmed log facts and generate factual discipline attribution. Neither live P&L nor a review changes Gate, template approval, or promotion.
- [ ] Re-run the one browser chain and repair only its first remaining failure.

**Acceptance:** a promoted signal cannot bypass the survival checks, and every buy/sell/P&L/review fact visible in the chain is linked to user confirmation and its evidence level.

### Task 6: Add the no-trade weekly value view by aggregation, not a new subsystem

**Files:** modify existing dashboard API and `frontend/app/page.tsx`; test `tests/test_no_trade_weekly_summary.py`.

- [ ] Aggregate existing ResearchCases, candidate pools, validation/Gate reports, market/data checks, Action Plans, observations, and reviews for the current week.
- [ ] Show: why no executable trade existed; each candidate and its blocking gate; conditions close to trigger with the actual unmet condition; changed evidence/counter-evidence; open-position risk; data quality; discipline statistics; and the specific next re-evaluation condition/date.
- [ ] The view contains no new persistence, background workflow, tuning control, or recommendation. Empty data says which source is unavailable, not “all clear.”
- [ ] Re-run the one browser chain and the no-trade scenario through the same script using a valid no-entry condition.

**Acceptance:** a no-trade week produces an evidence-based decision summary rather than an empty dashboard or generic `observe_only` label.

### Task 7: Final one-script acceptance and release evidence

**Files:** modify `scripts/verify_credible_manual_trade_closure.py`, `docs/verification/CREDIBLE_PRODUCT_ACCEPTANCE.md`, `docs/verification/V1_RELEASE_NOTES.md`, `docs/verification/V1_RELEASE_MANIFEST.md`; test `tests/test_llm_client_limits.py`.

- [ ] Run the single browser script from a clean local state against qualified real snapshot data and preserve its browser DOM/network logs and all IDs: ResearchCase, candidate snapshot, template/version/hash, PIT manifest hash, Market Guard configuration/report hashes, report, Gate, strategy revision, signal, Action Plan, execution logs, position, daily signal, P&L, and review.
- [ ] Assert the spawned backend command includes `--workers 1` and the worker environment is valid before browser steps. A second backend process or any worker setting other than one is an acceptance failure.
- [ ] In the same script assert negative branches: missing chain assertion, non-qualified PIT data, retired/unapproved template, exhausted OOS budget, unconfigured/data-fault market guard, and unconfirmed execution. Each must stop at its own declared state.
- [ ] Add a process-level concurrency test that starts three simultaneous `LLMClient.create_message()` attempts and proves at most two provider calls enter; add loop-budget tests proving the fourth call under one `decision_loop_id` is rejected and buy/sell confirmations consume zero calls.
- [ ] Record the 30-loop per-stage and user-wait-excluded automated P50/P95 report. Do not pass acceptance if P50 exceeds 25 seconds, P95 exceeds 45 seconds, any call exceeds eight seconds, or a budget/concurrency rejection is mislabelled as normal research failure.
- [ ] Run focused pytest suites, existing regression gates, and the production build. Record every command and result; do not claim pass if any required run was skipped or blocked.

**Acceptance:** one fresh browser run proves the whole successful chain when all gates are available, and one script proves its critical negative boundaries. Release readiness remains false until this evidence exists.

## 5. Implementation invariants

- Do not add a contract/service/page when an existing owned object can carry the state.
- Do not call an LLM for deterministic routing retries, status changes, price/quantity/P&L, template parameters, budgets, Gate, promotion, market state, or signal decisions.
- Do not use a static symbol list, current classification, `confirmed_candidate_pool`, or invented fixture as a formal historical universe.
- Do not call a Tushare financial value PIT-valid unless its `ann_date` is on or before the decision date.
- Do not show an LLM “researching”/“validating” state without a real recorded job.
- Do not claim industry-chain completeness, alpha validity, data coverage, or profitable behavior beyond the captured evidence.

## 6. Plan self-review record

| Review | Result |
|---|---|
| Adversarial blocking items 1–3 | V2 limits industry-chain handling to user-hypothesis verification; Gate 0 names Tushare interfaces/permission probe/history/format, and source-backed alpha lifecycle. |
| Items 4–6 | Existing fill semantics are requalified from PIT data; no-trade weekly value is an aggregate view. |
| Items 7, 10 | The first and final artifact is one browser script spanning friend input through Discipline Review. |
| Items 8–9 | Deterministic durable context plus open cognition/read-only tool whitelist and hard decision blacklist. |
| Item 11 | Three-call whole-loop budget, process-wide concurrency two, stage table, timeout, and user-wait-excluded P50/P95 requirements are explicit. |
| Market Guard freeze | Candidate metrics, PIT inputs, replay criteria, configuration/report hashes, and human freeze approval are explicit. |
| Item 12 and deletion test | Supersession and retained/removed/migrated components are explicit; prohibited new contracts/services are absent. |
| Paths and placeholders | All planned paths are existing or explicitly created; no unresolved placeholder marker or unnamed data source remains. |
| Complexity | One main acceptance script, existing contracts/services extended, no attachment subsystem, no duplicate execution state, and no separate no-trade subsystem. |

## 7. Definition of done

TraderLens is ready for limited personal manual decision support only when a fresh qualified-data browser run demonstrates the complete chain above, a no-trade week explains its gates and re-evaluation triggers, and every unavailable/rejected path names the evidence or data condition that stopped it. Profit is not a completion criterion.
