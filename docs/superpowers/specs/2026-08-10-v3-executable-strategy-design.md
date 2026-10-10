# v3 Executable Strategy Design

## Objective

Make the approved `relative_strength_rotation_shsz_sw2021_v3` strategy executable by the existing B4 qualification path without creating a general strategy platform or changing the approved template, revision, parameters, data artifacts, or OOS state.

## Architecture

Add one immutable execution-semantics supplement and one dedicated v3 executor/adapter. The supplement binds the exact approved v3 identity, protocol, qualified data chain, market-regime owner approval, and reused B4 execution primitives. The executor implements only this strategy and returns the existing B4 result contract.

The generic StrategyConfig DSL is not extended. Existing fill, cost, order-conflict, status, and force-liquidation primitives are reused through their tested public boundaries and source hashes.

## Exact strategy semantics

### Schedule and PIT boundary

- The execution date is the first SH/SZ common open trading day of each ISO week.
- The signal `as_of` date is the immediately preceding completed SH/SZ common open trading day.
- All ranks, confirmations, liquidity decisions, membership, status, and market-regime inputs use only information available as of that date.
- Entry confirmation requires the frozen top-15-percent condition on three consecutive independent PIT as-of dates ending on the current as-of date.

### Ranking and eligibility

- Momentum, adjustment, ranking population, entry threshold, exit threshold, and missing-data behavior are consumed exactly from the approved v3 template and verified historical coverage; the supplement does not restate or alter their formulas.
- Entry requires top-15-percent confirmed rank, qualified 20-common-day liquidity, active PIT membership, tradable status, and no active market-regime entry block.
- Rank exit is generated when the symbol is outside the top 40 percent on the as-of date.

### Portfolio construction

- Initial backtest capital: CNY `100,000`, matching the existing event-backtest default.
- Maximum concurrent positions: 5.
- Target weight: 20 percent of current portfolio equity per selected symbol.
- Buy quantity is rounded down to a board lot of 100 shares.
- Insufficient cash reduces or eliminates the order; residual cash remains cash and is not redistributed through a second sizing pass.
- Entry candidates are ordered by momentum rank from strongest to weakest; exact rank ties are broken by symbol ascending.
- When entry and exit target the same symbol on one execution date, exit wins.

### Exit semantics

- Maximum holding period is 15 completed common trading sessions, counting the entry session as session 1. A holding-period exit detected at an as-of close executes on the next executable session.
- Stop loss triggers when the completed-day raw close is at or below 92 percent of the position's actual average fill cost. It executes on the next executable session.
- Market-regime rules block new entries only; they never suppress exits.
- Exit orders blocked by suspension or exchange execution constraints are retried on subsequent common trading days until filled or handled by the existing formal status/force-liquidation contract.
- Entry orders that cannot fill on their scheduled execution day expire; they are not carried to a later day without a new qualified signal.

### Fill and cost contract

Bind the existing B4 primitives without changing their behavior:

- execution price: execution-day open;
- commission rate: `0.0003`;
- minimum commission: `5`;
- sell stamp duty: `0.001`;
- transfer fee: `0`;
- slippage: `0`;
- maximum participation: `0.10`;
- existing suspension, price-limit, same-symbol conflict, and formal force-liquidation behavior.

If the existing tested public boundary cannot uniquely provide one of these behaviors, implementation must stop at that first mismatch rather than add a second simulator.

## Market-regime binding

The supplement binds owner approval `6170c11c8068f407` and qualification `be92ad203fc0f2cd`. Runtime evaluation uses the exact v1.2 rules and thresholds. The market-regime approval authorizes only entry blocking for this v3 manual-trading path.

## Data adapter

Provide the smallest adapter required by the existing event-backtest caller:

- PIT symbols from membership snapshot `pims_traderlens_v2_shsz_sw2021_pit_005`;
- daily bars and single-bar lookup from formal partitions;
- daily status from formal PIT status sources;
- SH/SZ common-calendar iteration;
- explicit execution-date/as-of-date mapping;
- exact v3 revision ID in every result.

No static symbol list, watchlist, future membership, or generic data-platform interface is allowed.

## Artifact and verification

Publish one write-once supplement that binds:

- v3 template/version/template hash/requirements hash;
- strategy revision `6440ffc03a742f4d4632078481cf3abf171eafb1a24f2bc69bc6f352d1b19ebc`;
- protocol `6f7cbdcdeb26f8cdd2611a5450dbab3ff22544b6a66ec8539f5cab9151329111`;
- scope, coverage, formal snapshot, availability successor, B3, lifecycle, liquidity, membership, criteria, and market-regime approval exact identities and hashes;
- executor, adapter, fill, order, cost, status, and force-liquidation source hashes;
- every semantic choice in this document.

An independent verifier recomputes the artifact identity, referenced hashes, exact semantic payload, and source bindings. Any mismatch fails loud.

## Execution sequence and acceptance

1. Focused RED-to-GREEN tests for schedule, PIT cutoff, momentum/rank/confirmation, liquidity admission, sizing, exits, market-regime entry blocking, fill/status behavior, and result revision binding.
2. Run the existing official B4 Canary qualification. All required canaries must reach their expected blocked outcomes and the valid path must pass exact binding.
3. Run one real IS event backtest over `2025-06-27..2026-03-19` using the frozen protocol and PIT universe.
4. Publish and independently verify the B4 IS artifact only if the run completes without data faults or contract drift.
5. Run one production one-shot discovery to identify the next prerequisite.

OOS dates and results must not be read, reserved, or consumed in this node. No Gate, Promotion, or Signal execution occurs here.

## Scope boundary

This design does not add a strategy DSL, new strategy, new validation platform, alternative fill simulator, parameter tuning, market-data collection, Task 3 retry, full test/build run, or Git operation.
