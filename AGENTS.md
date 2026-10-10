# TraderLens Project Execution Rules

These rules specialize the global Codex engineering rules for TraderLens.
They do not weaken correctness requirements for trading decisions.

**All actions must align with the North Star document: `TraderLens_Northstar.md`.**

## 1. Product mainline is the top-level priority

TraderLens exists to help a novice A-share user make and review real trading decisions.

Primary user journey:

1. Market regime:
   Can I open a new position today?
   -> allow / caution / block

2. Sector focus:
   If entry is allowed, which few sectors deserve attention?

3. Stock decision:
   For a discovered or user-supplied stock:
   -> candidate / wait / watch / reject

4. Trade plan:
   Using a previously validated strategy:
   -> entry condition
   -> position size
   -> invalidation / stop
   -> exit condition

5. Manual simulated execution:
   User records actual simulated buy.

6. Position monitoring:
   -> hold / risk rising / exit

7. Post-trade review:
   -> P&L
   -> strategy attribution
   -> market/sector contribution
   -> execution/discipline deviation

Every implementation task MUST state which numbered step it advances.

If a task cannot explain what new user-visible ability it unlocks on this journey,
do not implement it unless it protects a mandatory correctness boundary.

## 2. Reuse before rebuild

Existing research, Serenity, strategy validation, B6/OOS/Gate, Signal Board,
Action Plan, CapitalContext, Observation, P&L and Discipline Review components
must be reused when they are fundamentally sound.

Do not replace an existing module because its architecture or naming is imperfect.

Prefer:
existing capability -> minimal connection -> end-to-end use

over:
new abstraction -> new infrastructure -> migration.

## 3. Classify failures before stopping

When any failure appears, classify it first.

### A. Mainline blocker — must stop and fix

Examples:

- fabricated or unverifiable market/company data
- broken current user workflow
- incorrect routing/state transition on the current journey
- look-ahead or data leakage
- invalid backtest assumptions
- T+1 / suspension / price-limit / transaction-cost errors
- incorrect position sizing
- incorrect entry/exit logic
- incorrect P&L
- trade not bound to its actual Action Plan
- syntax/import/runtime failure in code touched by the current task
- secrets exposed by the current runtime path

These require focused root-cause repair before proceeding.

### B. Relevant technical debt — record, do not block

Examples:

- unrelated historical test fixture failure
- obsolete compatibility path
- unrelated dirty data in an old database
- architecture inconsistency outside the current journey
- missing UI polish
- old module tests not exercised by the authorized path

Record the issue and continue the authorized mainline.

### C. Enhancement — defer

Examples:

- broader observability
- generalized frameworks
- additional providers
- additional financial fields
- broader market coverage
- refactoring for elegance

Do not implement during a mainline closure task.

## 4. Trading correctness cannot be relaxed

The MVP may be narrow, but it may not fake correctness.

Never relax:

- real source attribution
- no fabricated financial/market/news facts
- no look-ahead
- no data leakage
- no survivorship bias where relevant
- A-share T+1
- suspension and price-limit behavior
- transaction costs
- deterministic P&L
- deterministic position sizing
- strategy provenance
- evidence gaps

Missing information must be explicit.

The system may still form a decision when some non-critical information is missing,
but must state the missing evidence and reduce evidence strength accordingly.

Do not invent numeric confidence percentages.

Use:
- high evidence
- medium evidence
- low evidence
- insufficient data

## 5. LLM boundaries

LLMs may:

- understand user intent
- research and summarize evidence
- identify supporting and counter evidence
- form a research-layer verdict
- explain deterministic trading outputs

LLMs must not:

- invent current facts
- calculate authoritative numerical outputs
- create strategy parameters ad hoc
- decide whether a backtest passed
- calculate P&L
- override deterministic gates
- override position/risk constraints

Routing, parsing, retry policy, state transitions and numerical calculations belong in code.

## 6. Narrow vertical slice first

Before expanding breadth, complete one narrow journey:

user supplies one stock
-> real research
-> research verdict
-> one validated strategy
-> executable Action Plan
-> manual simulated buy
-> position monitoring
-> manual sell
-> P&L and review

Automatic market-wide sector discovery and broad stock screening may come later.

## 7. Change discipline

Before modifying code:

1. establish a recoverable git checkpoint;
2. inspect target code, direct callers, contracts and relevant tests;
3. define focused acceptance criteria.

After modifying code:

1. run syntax / compile / import smoke first;
2. run focused tests for touched behavior;
3. run the relevant user-path verification.

Do not begin expensive E2E verification while touched files do not compile.

Do not modify unrelated dirty files.

## 8. Task scope

One task should fix one verified mainline blocker.

If a new independent blocker appears:

- if it blocks the current mainline or violates trading correctness -> stop and report it;
- otherwise record it as technical debt and continue the authorized task.

Do not bundle multiple root causes into one patch.

## 9. Definition of progress

Progress is not:

- more tests
- more abstractions
- more reports
- more services
- cleaner architecture

unless they directly protect correctness.

Progress is:

the user journey can move one verified step farther using real or explicitly
identified test inputs.

At the end of every task report:

阶段 <阶段编号>｜卡 <三位卡号>
BEFORE: <where the user journey stopped>
AFTER: <where it now stops>
新增能力: <what the user can now actually do>
下一阻塞: <one blocker only>

阶段和卡号表示项目工作进度，与用户旅程步骤编号（1-7）不同。用户旅程步骤如需说明，只写在任务卡的范围说明中，不得用作进度标题。
