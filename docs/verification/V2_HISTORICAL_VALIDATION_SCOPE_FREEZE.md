# V2 Historical Validation Scope Freeze

**Status:** Owner-approved scope freeze, 2026-07-13  
**Applies to:** All V2 historical strategy screening, OOS validation, coverage reporting, and future data work.  
**Does not authorize:** Broker connection, automatic orders, live trading, B6/OOS/Promotion completion, or a Market Guard freeze.

## Decision

TraderLens V2 is a **Shanghai/Shenzhen A-share current-tradable-security research and manual-decision assistant**. It is not an institutional, survivorship-free, full-market historical-security master or delisting-event database.

Historical validation uses only the security-date observations that the existing immutable local data package can support without inventing, backfilling, or leaking information. A missing observation is recorded as unavailable; it is never reconstructed from future data and never presented as an all-market result.

This document supersedes the V2 plan's full-market identity and retired-security zero-gap expectation for historical validation. It retains all prohibitions on future information, date misalignment, synthetic prices, silent fallback data, and overstated claims.

## Supported scope

- Current-tradable Shanghai/Shenzhen A-share research and manual-decision support.
- Historical strategy screening on the existing local daily-data coverage from 2016-01-04 through the last closed trading day in the bound snapshot.
- Pre-registered strategy rules and strict time-based train/OOS splits.
- Simulation and forward observation after historical screening, with coverage limitations carried into every report.
- Current symbol, price, and research workflows only where their required inputs are actually available at the decision time.

## Explicitly unsupported scope

- Complete historical coverage of every delisted, suspended, ST, transferred, or otherwise unavailable security.
- A complete cross-code `security_id` master, code-change continuity, or reconstructed corporate-action history.
- A complete PIT database of delisting-risk or delisting-arrangement events.
- Survivorship-free, institution-grade, whole-market historical returns or coverage claims.
- Treating the available subset as the historical A-share market, or treating missing rows as proof that a security was ineligible.
- Further per-code announcement research, per-date exception tables, identity aliases, lifecycle overrides, supplier purchases, or data-system expansion for V2.

## Three-layer historical-validation policy

### 1. Product scope

The live-facing product scope is current-tradable `.SH` and `.SZ` securities. `.BJ`/BSE and predecessor-market coverage are outside V2 and require a separately qualified future data package.

### 2. Historical availability mask

For each strategy run, the immutable data package records an **availability mask**: the security-date inputs that are present and time-valid for that run. The mask is a reporting and computation boundary, not an alpha feature, ranking input, or retrospective eligibility rule.

An unavailable observation:

- cannot receive an imputed price, indicator, limit, lifecycle status, or identity mapping;
- cannot become a signal merely because another security is unavailable;
- must be counted and disclosed by date, field, and security where available;
- makes the result conditional on the supported observations, not representative of all historical A shares.

### 3. Historical evaluation

Strategies may be screened only on this availability-bounded history. Rules, parameters, split dates, benchmarks, and evaluation protocol are frozen before observing OOS results. Missing coverage cannot be used to retune a rule or rerun a preferred result.

## Permitted and prohibited conclusions

| Permitted | Prohibited |
|---|---|
| “This rule produced these results on the documented supported observations.” | “This rule produced these results for the whole A-share market.” |
| “OOS result is conditional on the frozen split and coverage manifest.” | “The result is survivorship-free or institution-grade.” |
| “Unavailable observations were excluded from computation and disclosed.” | “Unavailable observations were ineligible securities.” |
| “Forward observation is needed before relying on a signal.” | “Historical validation establishes future profitability.” |

## Minimum conditions before B6/OOS

B6/OOS may begin only when one candidate template has all of the following:

1. An immutable template hash, data-requirements hash, snapshot hash, and coverage-manifest hash.
2. A frozen time split and OOS budget recorded before OOS metrics are viewed.
3. A generated availability mask and a report of supported and unavailable security-date observations.
4. No detected future-information use, timestamp/date misalignment, duplicate-security counting, arithmetic error, or schema mismatch in the supported observations.
5. Explicit report language that results are coverage-limited and are not full-market returns.

Market Guard, Promotion, Signal Board entry conclusions, and live-facing Action Plans retain their separate safety requirements. This scope freeze does not make a candidate Guard frozen and does not authorize a trading signal.

## Data-stage completion criteria

The V2 data-processing stage is complete when:

1. The existing local snapshot, hashes, field provenance, and coverage manifest are bound to the validation run.
2. The historical availability mask is reproducible from that snapshot.
3. Known gaps, code changes, delisting states, and unsupported securities are disclosed rather than patched.
4. No unresolved defect can cause future leakage, date misalignment, duplicate-security counting, or wrong calculations in the supported observations.
5. The required historical-validation coverage report is generated.

Ordinary remaining coverage gaps do not reopen data engineering. A new data task is allowed only when it demonstrates one of the four defects in item 4, or when the owner explicitly changes the product scope or approves a new data source.

## Work explicitly stopped for V2

- Searching for or purchasing a security-master supplier.
- Per-security identity aliases or code-change mappings.
- Per-security delisting/retirement date tables.
- Pursuing a zero blocking-gap count for all historical securities.
- Expanding the qualification system whenever a new historical anomaly appears.

## Risk disclosure

The system must disclose that historical results may have coverage, survivorship, delisting, code-continuity, and market-state bias. These limitations reduce what can be inferred from backtests. They do not justify hidden imputations, unstated exclusions, or profitability claims.

## Next and only recommendation

Implement the smallest reproducible availability-mask and coverage-report path for the frozen V2 scope, then begin the separately frozen B6/OOS workflow. Do not revisit individual historical anomalies unless they demonstrate future leakage, date misalignment, duplicate counting, or an incorrect calculation in the supported subset.
