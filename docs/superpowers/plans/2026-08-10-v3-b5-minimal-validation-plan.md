# v3 专用最小 B5 验证实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Each step uses checkbox tracking. Shared dirty workspace rules prohibit Git commit/worktree operations; preserve all unrelated user changes.

**Goal:** 在不改变 frozen v3 策略语义、不建设通用验证平台的前提下，形成可独立验证的 base transaction cost、stress transaction cost、theme-then-industry benchmark 和 same-universe control，并让 one-shot 在所有四项通过前保护 OOS。

**Architecture:** 新增 v3-only source inventory、结果类型、producer 和 verifier。source inventory 直接绑定现有 SW2021 L1 formal partitions；benchmark 与 control 共享同一 PIT eligible universe，但产生独立结果。现有 B4 event result 的交易语义保持不变；Task3 使用已验证的 20960 fills ledger 生成 daily observations，Task5 只消费该 verified observation 与正式 PIT source。

**Tech Stack:** Python 3、Pydantic 现有 contract、PyArrow/Pandas 现有 formal partition readers、标准库 SHA-256/canonical JSON、file-backed JSON artifacts。不得引入新依赖、并行框架或持久预计算平台。

---

## Frozen inputs and stop boundary

所有任务都必须 exact-bind：

```text
template_id = relative_strength_rotation_shsz_sw2021_v3
template_version = v3_shsz_sw2021_pit_12m_liquidity20d
template_hash = f7c0fd8123f62f37118cb947e1735861374435f8707e01b06d788a8ec4df39c1
requirements_hash = ef2ab5b1dafe4349f305b52733a7dcb018a2961464dfbc6542a10e34805d041d
revision_id = 6440ffc03a742f4d4632078481cf3abf171eafb1a24f2bc69bc6f352d1b19ebc
protocol_id = 6f7cbdcdeb26f8cdd2611a5450dbab3ff22544b6a66ec8539f5cab9151329111
supplement_id = 680cd55c91254667
formal_snapshot_id = v3ds_d73256081de82e8a
membership_id = pims_traderlens_v2_shsz_sw2021_pit_005
scope_id = acbc49159d989a46
IS = 2025-06-27..2026-03-19
OOS = 2026-03-20..2026-07-10
```

Approved stress contract:

```text
commission_rate = 0.0006
minimum_commission = 5.0
sell_stamp_duty = 0.001
transfer_fee = 0.0
stress_slippage_bps = max(base_slippage_bps * 2, 10)
buy_price = fill_price * 1.001
sell_price = fill_price * 0.999
impact_bps = 0.0, explicitly no independent impact model
same fills/quantity/fill_date/eligibility as B4
```

Approved benchmark/control contract:

```text
benchmark theme = the one approved SH/SZ SW2021 PIT eligible universe
benchmark = equal weight by active SW2021 L1 industry, then equal weight within each industry
control = direct equal weight over the same eligible universe, without industry buckets
PIT classification = in_date <= as_of <= out_date; null out_date is open-ended
execution = same v3 weekly formation/as_of and next executable common-day open
fill/status/cost/force-liquidation = exact 680c semantics
```

The source inventory is the existing formal source:

```text
data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal/sw_l1_membership/manifest.json
manifest_sha256 = a38b3cc6be947b290078fe637466991ee8d13dee2794d398fb709d5c4c3826f3
accepted taxonomy = SW2021
accepted partitions = 61
fields = ts_code,l1_code,l1_name,in_date,out_date,is_new
```

The staged source is physical input only until Task 1 publishes and verifies a v3 B5 source-inventory successor. It must not be passed directly to one-shot or OOS.

## Task 1: Publish and verify the v3 SW2021 classification source inventory

**Files:**
- Create: `backend/services/v3_b5_source_inventory.py`
- Create: `scripts/publish_v3_b5_source_inventory.py`
- Create: `scripts/verify_v3_b5_source_inventory.py`
- Test: `tests/test_v3_b5_source_inventory.py`

- [ ] **Step 1: Write RED tests for source identity and corruption boundaries.**

The tests must invoke the publisher/verifier boundary with a temporary fixture copied from the real source shape and assert rejection for missing `l1_code`, missing effective dates, a declared partition hash mismatch, a missing partition, duplicate `(ts_code,in_date,out_date,l1_code,is_new)`, and overlapping active L1 codes. The production source test must assert all 61 SW2021 partitions are selected and every declared byte hash equals the actual parquet hash.

- [ ] **Step 2: Run the source-inventory RED suite.**

Run:

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_v3_b5_source_inventory -v
```

Expected result before implementation: non-zero exit because the v3 source-inventory publisher/verifier boundary does not exist. Do not run provider/API calls.

- [ ] **Step 3: Implement the minimal source inventory boundary.**

Use these exact producer interfaces:

```python
def publish_source_inventory(repo_root: Path, output_root: Path) -> dict:
    """Read the bound SW2021 source, write once, and return manifest metadata."""

def verify_source_inventory(repo_root: Path, artifact_dir: Path) -> dict:
    """Re-read manifest and all 61 SW2021 partitions; return verified/invalid."""
```

The manifest must bind source manifest path/SHA, accepted partition names/hashes/row counts, required columns, PIT rule, v3 template/version/hash/requirements, membership ID/manifest/records hashes, calendar ID/date-set hash, scope ID/hash, and `not_authorized_for_b6_oos_gate_promotion_signal=true` until the later B5 bundle is verified. Write to `data/pit/v3_b5_source_inventories` under the ID computed from the canonical manifest, with canonical JSON, sidecar, and fail-loud write-once conflict behavior.

- [ ] **Step 4: Run the source-inventory GREEN suite.**

Run the same command. Expected result: exit 0, all source-inventory tests pass; verifier reports 61 SW2021 partitions and no source hash/date/conflict error.

## Task 2: Freeze B5 result payloads and write-once bundle contracts

**Files:**
- Create: `backend/services/v3_b5_types.py`
- Create: `backend/services/v3_b5_bundle.py`
- Test: `tests/test_v3_b5_contracts.py`

- [ ] **Step 1: Write RED tests for exact binding and idempotency.**

Cover canonical payload hashing, deterministic IDs, required lineage fields, missing source rejection, tampered source rejection, same-ID exact reuse, same-ID conflicting payload rejection, sidecar mismatch, and `not_authorized` behavior before all four results are valid.

- [ ] **Step 2: Run the contract RED suite.**

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_v3_b5_contracts -v
```

Expected result before implementation: non-zero exit because the v3 B5 contract types and bundle verifier do not exist.

- [ ] **Step 3: Implement the narrow payload types.**

The four result payloads must contain the exact source identity, date range, daily series hash where applicable, cost assumptions hash, source inventory ID/hash, producer algorithm hash, and verifier status. The bundle publisher must write only metadata JSON and sidecars; it must never copy parquet or write `immutable_backtest_reports`.

- [ ] **Step 4: Run the contract GREEN suite.**

Run the same command. Expected result: exit 0 with every identity/tamper/write-once assertion passing.

## Task 3: Publish v3-only ledger-replayed IS observations

**Files:**
- Create: `backend/services/v3_b5_ledger_observation.py`
- Create: `scripts/publish_v3_b5_ledger_observations.py`
- Create: `scripts/verify_v3_b5_ledger_observations.py`
- Modify only if required by the existing result serializer: `backend/services/b4_protocol_types.py`
- Test: `tests/test_v3_b5_ledger_observation.py`

- [ ] **Step 1: Write RED tests for the ledger replay boundary.**

Assert that the producer consumes only verified `20960e9fd15cdb44/event_result.json`, rejects missing/duplicate fills, order-intent mismatch, fee/cash mismatch, invalid status-aware marks, date gaps and future/OOS dates, and emits the observation schema `date,cash,portfolio_value,gross_exposure,net_exposure,positions_value,daily_return,position_values_by_symbol`. Assert that average_cost/last_price are explicitly derived audit fields and are never claimed as predecessor expected values.

- [ ] **Step 2: Run the ledger RED suite.**

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_v3_b5_ledger_observation -v
```

Expected result before implementation: non-zero exit because the ledger observation producer/publisher/verifier does not exist.

- [ ] **Step 3: Implement the narrow ledger replay and publisher/verifier.**

The replay must consume the original 124 fills exactly once, derive direction from exact order intents, use the existing PortfolioState and transaction-cost primitive, and mark each IS common day through the formal adapter. Suspended positions carry the prior last_price; non-suspended missing bars fail loud. It must not call signal, rank, entry, exit, confirmation, liquidity, or market-regime logic. It must bind the 20960 event and all frozen source hashes, preserve the original event identity, and publish a separate observation artifact with canonical hashes, sidecars and write-once conflict handling.

- [ ] **Step 4: Run the ledger GREEN suite and bounded smoke.**

Run:

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_v3_b5_ledger_observation -v
```

Then run only a non-publishing deterministic ledger replay smoke on a small IS prefix. Expected result: exit 0, exact fill consumption/cost arithmetic, ordered observations, authoritative final-field comparison semantics, and `max_requested_date < 2026-03-20`.

- [ ] **Step 5: Publish and independently verify the one authorized ledger observation artifact.**

After Tasks 1–2 focused suites are GREEN and all source hashes are final, run exactly once:

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m scripts.publish_v3_b5_ledger_observations
```

The publish must use IS `2025-06-27..2026-03-19`, the verified 20960 event, 680c supplement, formal snapshot/PIT membership and production common calendar. It writes one metadata-only ledger observation artifact, then `scripts.verify_v3_b5_ledger_observations` runs once independently. It must not call event backtest or read/reserve/consume OOS. Any data/business/contract failure stops this plan; do not rerun publication.

## Task 4: Implement base and approved transaction-cost stress producers

**Files:**
- Create: `backend/services/v3_b5_costs.py`
- Create: `scripts/publish_v3_b5_costs.py`
- Create: `scripts/verify_v3_b5_costs.py`
- Test: `tests/test_v3_b5_costs.py`

- [ ] **Step 1: Write RED tests for fee arithmetic and stress strictness.**

Use a deterministic fill fixture with buy and sell directions. Assert base commission/minimum commission/stamp/transfer, gross-notional denominator, and no-impact disclosure. Assert stress uses the same fill IDs/quantity/date, commission `.0006`, minimum `5`, sell stamp `.001`, transfer `0`, adverse 10 bps repricing, and `stress_total_cost_bps > base_total_cost_bps`. Assert empty fills, non-positive notional, missing intent direction, and conflicting fill identity fail loud.

- [ ] **Step 2: Run the cost RED suite.**

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_v3_b5_costs -v
```

Expected result before implementation: non-zero exit because the v3 cost producer/verifier is absent.

- [ ] **Step 3: Implement the v3-only cost producer.**

Base and stress must use the same B4 fill set. For each fill, derive direction from the exact order intent. Apply the approved stress price only for stress arithmetic; do not mutate or republish fills. Bind assumptions hash to constants, formulas, source hashes and event/observation hashes.

- [ ] **Step 4: Run the cost GREEN suite and independent verifier.**

Run the same focused command, then:

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m scripts.verify_v3_b5_costs D:\Codex\TraderLens\data\pit\v3_b5_costs\79d198f5fddc4037
```

Expected result: both commands exit 0; verifier recomputes all 124 fills and confirms strict stress.

## Task 5: Implement benchmark and same-universe control producers with P0 daily precedence and approved P2 carry

**Files:**
- Create: `backend/services/v3_b5_comparison.py`
- Create: `scripts/publish_v3_b5_comparisons.py`
- Create: `scripts/verify_v3_b5_comparisons.py`
- Test: `tests/test_v3_b5_comparisons.py`

### Narrow `suspend_d` precedence checkpoint (authorized Task5 correction)

Before changing the comparison producer, update and test the formal source
adapter boundary only. Read the adapter's partition/cache path, its direct
callers, `DailyStatus`, and the existing formal-adapter tests. Then add the
smallest RED tests for the following daily-level contract:

1. `R` plus a valid daily row resolves to `is_suspended=False`, retains reason
   `R`, and leaves the bar usable.
2. `S`/`P` plus a valid daily row and non-empty `suspend_timing` resolves to
   `is_suspended=False`, retains the deterministic type reason, and leaves the
   bar usable. The ordinary intraday timing and the evidence-bound
   `603056.SH/2026-01-09` `13:00-9:30` string are both covered without parsing.
3. `S`/`P` plus a valid daily row and null/empty timing resolves to
   `is_suspended=True`; the comparison daily-plus-formal conflict assertion is
   unchanged.
4. Multiple `S`/`R` rows without daily resolve deterministically to
   `is_suspended=True` with `S` priority, independent of parquet row order;
   the `603056.SH/2026-01-12` boundary is covered.
5. `R`-only without daily is not suspension carry and keeps the existing
   missing/unknown fail-loud behavior.
6. A daily row is valid for tradable precedence only when `open`, `high`,
   `low`, `close`, `amount`, and `vol` are correctly typed, finite, and
   strictly positive, with existing OHLC ordering; invalid source rows are
   P3. Empty/unsupported `suspend_type` is P3 for both daily-present and
   daily-missing rows, never P1. R-only without daily is a P3 formal status
   fault even when qualified coverage exists.

Implement only the formal adapter precedence and directly affected tests. In
`_FormalComparisonSource.mark()` only, narrow the coverage exception branch so
P2 accepts the existing ordinary missing-daily `KeyError` path, while adapter
`ValueError`/`TypeError`/`FileNotFoundError` formal faults remain P3. Keep
`execution()`'s existing KeyError-only P2 boundary unchanged.
Preserve the raw source row as audit evidence through the existing source
partition/hash boundary; do not add a general status model, time parser,
strategy, parameter, or data source. Do not modify
comparison returns, P1 suspension carry, P2 six-condition logic, or conflict
guards; the mark exception split is the only authorized comparison change.
Run the focused RED separately,
then the adapter implementation and focused GREEN/regression suites. A RED
that does not fail specifically on the old precedence, a second independent
root cause, or an adapter-only boundary failure stops this checkpoint.

- [ ] **Step 1: Read the current comparison boundary and write RED tests.**

Read `backend/services/v3_b5_comparison.py` functions `ReadBoundAdapter`, `_FormalComparisonSource.mark`, `_FormalComparisonSource.execution`, `rebalance_fractional`, and `run_fractional_index`, plus both scripts and the existing comparison tests. Reuse `_load_coverage_binding`; do not create a second coverage or availability source.

Add focused tests in `tests/test_v3_b5_comparisons.py` that exercise the real caller boundary, not only an arithmetic helper:

1. A coverage-unavailable row with a valid execution-day formal daily mark uses that daily mark; coverage still excludes the symbol from a new target and does not trigger P2.
2. An existing symbol that is no longer eligible but has a valid formal execution open exits normally and contributes actual turnover; `002348.SZ` on `2025-12-08` is the real boundary fixture.
3. A daily row combined with adapter-unresolved formal `S`/`P` evidence
   (missing/empty timing) or an ambiguous source conflict remains fail loud.
4. A qualified held `688766.SH` unavailable mark is accepted only with the exact coverage key `(execution_date, as_of_date, symbol)`, `status=unavailable`, `reason=required_history_missing`, and `missing_fields` containing `daily.close`.
5. On `2025-12-01`, an existing `688766.SH` position is locked: its units remain unchanged; the comparison does not read its open, create a buy/sell, or add that symbol to turnover; blocked new buys remain zero and their weight is not reallocated.
6. The next valid formal daily mark restores the real mark; the carry day is labelled `unavailable_mark_carry` and its symbol return is zero.
7. Exact formal suspension evidence has precedence over P2 and uses the existing suspension carry path; it is never relabelled as P2 availability carry.
8. Missing coverage, mismatched key/as_of, unknown reason, missing prior mark, inactive/delisted/force-liquidation state, source conflict, and generic missing daily fail loud. A missing daily row with no exact qualifying evidence is not silently carried.
9. Both benchmark and control preserve `cash + positions_value = portfolio_value`, non-negative cash, locked units, common-scale cash-cap accounting, and turnover based only on actual sells and scaled buys. Base/stress haircuts do not mutate gross holdings.

Retain the existing negative coverage/source tests: reject static symbols, 000300, old-v2 and fixture benchmark paths; apply `in_date <= as_of <= out_date`; reject multiple active L1 codes; drop empty industries and renormalize remaining industry weights; keep control as direct equal weight over the same eligible universe; use the 38 v3 weekly dates and next-common-open mapping; use `schema_kind=theoretical_fractional_comparison_index` with normalized NAV 1.0. Preserve unavailable/status rows; only exact P2 rows may be marked `unavailable_mark_carry`, and no missing row may be treated as zero or a tradeable price.

- [ ] **Step 2: Run the comparison RED suite.**

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_v3_b5_comparisons -v
```

Expected result before implementation: non-zero exit from the new P0/P2 assertions because the current mark boundary treats coverage-unavailable plus a present formal daily row as a conflict, while the current P2 path also does not yet lock qualified unavailable held marks before open/status processing. Do not weaken the existing producer assertions to obtain RED.

- [ ] **Step 3: Implement the smallest P0/P2 correction in the existing comparison boundary.**

Use the source-inventory fields `ts_code,l1_code,l1_name,in_date,out_date,is_new`; use the exact v3 lifecycle, ST, suspension/daily availability, verified 20-day liquidity admission, and common calendar. This remains a theoretical fractional index: do not invoke 680c lot/minimum-commission/participation/PositionSizer or create orders/fills.

Implement P0 and P2 in the existing `_FormalComparisonSource.mark` and `.execution` boundary and the existing `rebalance_fractional` caller:

- First resolve the execution-day formal daily/status boundary. If a valid
  finite formal daily row exists after adapter validation and no unresolved
  formal suspension or other ambiguous conflict remains, use that daily mark
  even when coverage is unavailable. Keep coverage-unavailable filtering in
  `members_for` for new targets only; do not trigger P2 or fail the mark. If
  an existing position is no longer eligible but has a valid formal execution
  open/status, process the normal exit and count actual turnover.
- A daily row whose adapter resolution still reports formal `S`/`P` suspension
  (missing/empty timing) or an ambiguous source conflict remains
  `ComparisonError`; P0 must not mask this conflict. Adapter-resolved `R` and
  non-empty-timing `S`/`P` rows are tradable for that daily row and retain
  their source reason/evidence.
- For a daily-missing symbol, resolve exact formal suspension next. If it qualifies, retain the existing suspension carry semantics and never enter P2.
- Unknown/empty/unsupported formal status and R-only/no-daily status faults are
  P3 and cannot enter P2 through coverage. In `mark()`, only the existing
  ordinary missing-daily `KeyError` path may reach the qualified P2 branch;
  formal adapter errors remain fail-loud. `execution()` keeps its existing
  KeyError-only P2 branch.
- For a daily-missing, non-suspended symbol, load the existing exact coverage row and admit P2 only when all six contract conditions in the design are true. Store the reason `unavailable_mark_carry` and the carried mark representation in the audit row.
- During `execution`, process a P2 existing position before any open/status trade lookup. Keep its units and mark, skip its open read and buy/sell, and exclude it from turnover. Do not lock unrelated symbols or reallocate the blocked target weight.
- If no prior valid mark, exact coverage row, active lifecycle, or non-conflict status exists, raise the existing `ComparisonError`; do not add a generic last-price fallback.
- Keep the already-approved sell-first/common-scale cash-cap logic in `rebalance_fractional`: locked positions are unchanged, tradable sells execute first, desired buys use post-sell values, one common scale caps cash, and base/stress haircuts affect only net series.

Benchmark groups eligible members by `l1_code`, equal-weights members inside each group, then equal-weights non-empty groups. Control equal-weights all eligible members directly. Both produce 176 daily gross/base-net/stress rows, 38 rebalance targets/executions, turnover and approved bps haircuts, status/unavailable counts, weights/position values, comparison metrics, source inventory, and algorithm hashes. Apply P0 before P1/P2 resolution; the P0 evidence is bound to `docs/verification/v3_b5_comparison_coverage_daily_semantics_diagnostic.json` with file SHA-256 `e6437e544d145cdd866683933a421fdf20f4139bd54c30e33df7dc19f2ae9424` and payload SHA `a7a72d6f9df39d36c08b97b94020c857577978f8e2217ef00ff029c53fdd6d27`. The existing P2 diagnostic remains bound through exact coverage row/hash fields; neither diagnostic is a runtime authorization shortcut. `_tmp_coverage_scan_result.json` is non-production scratch and must not be consumed or deleted by this plan. A bounded source-read cache is allowed inside one producer invocation; no persistent index or generic platform.

- [ ] **Step 4: Run the focused GREEN suites.**

Run the comparison suite and the direct regressions separately:

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_v3_b5_comparisons -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_v3_b5_contracts -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_v3_b5_ledger_observation -v
```

The GREEN evidence must include the P0–P3 precedence cases, A–G above, and the existing source/tamper/write-once tests. Any new data, coverage, status, or contract fault stops Task5; do not adjust thresholds or broaden carry.

- [ ] **Step 5: Run the bounded real slice without publishing.**

Use the verified production inputs and the non-publishing comparison caller to cover only `2025-11-24..2025-12-09`. The focused slice test is:

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_v3_b5_comparisons.TestV3B5Comparisons.test_real_p2_unavailable_mark_slice_20251124_20251209 -v
```

The slice must cover both benchmark and control, `002348.SZ` P0 formal marking on `2025-12-03`, its normal formal-open exit and turnover on `2025-12-08`, all 14 diagnosed `688766.SH` P2 events, the two `2025-12-01` locked-position execution boundaries, the first valid mark after the P2 gap, and `oos_read_count=0`. Assert no open lookup, trade, or turnover for `688766.SH` on the P2 dates; assert exact NAV/cash arithmetic and no material negative cash. This slice is non-publishing and cannot substitute for the later full publisher.

- [ ] **Step 6: Preflight, publish once, and verify once.**

Before publication, independently recheck source inventory `2fe8321a5f644b9b`, cost artifact `79d198f5fddc4037`, ledger observations `c66cdeb6ffe88933`, B4 `20960e9fd15cdb44`, 680c historical predecessor bindings, formal snapshot, membership, calendar, scope, target absence, no temporary files/processes, and DB/OOS baseline. Bind the P0 diagnostic `docs/verification/v3_b5_comparison_coverage_daily_semantics_diagnostic.json` with file SHA-256 `e6437e544d145cdd866683933a421fdf20f4139bd54c30e33df7dc19f2ae9424` and payload SHA `a7a72d6f9df39d36c08b97b94020c857577978f8e2217ef00ff029c53fdd6d27`; retain the P2 diagnostic `docs/verification/v3_b5_comparison_missing_mark_diagnostic.json` with SHA-256 `ab0e788b69c245d0a405d4f63bd900eb98902a33f170ae060540fbe98325098f`.

After all focused and slice checks are GREEN, run the publisher exactly once:

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m scripts.publish_v3_b5_comparisons
```

If it exits zero, require exactly one new directory under `D:\Codex\TraderLens\data\pit\v3_b5_comparisons`, then run the independent verifier exactly once against that directory:

```powershell
$comparisonDir = (Get-ChildItem -LiteralPath 'D:\Codex\TraderLens\data\pit\v3_b5_comparisons' -Directory | Sort-Object Name | Select-Object -Last 1).FullName
& D:\Codex\TraderLens\.venv\Scripts\python.exe -m scripts.verify_v3_b5_comparisons $comparisonDir
```

The verifier must independently recompute source hashes, P2 admission, all 176 dates, 38 rebalances, 14 events, benchmark/control separation, NAV/turnover/cost arithmetic, and OOS/read guards. Publisher or verifier failure, a second root cause, or any mismatch stops without a second publication or repair.

- [ ] **Step 7: Stop at the Task5 boundary.**

Only after the artifact is stable and independently verified may this plan call Task5 complete. Keep `not_authorized_for_b6_oos_gate_promotion_signal=true`, do not assemble the Task6 bundle, and do not run one-shot, B6, OOS, Gate, Promotion, or Signal.

## Task 6: Assemble and independently verify the four-result B5 bundle

**Files:**
- Modify: `backend/services/v3_b5_bundle.py`
- Create: `scripts/publish_v3_b5_bundle.py`
- Create: `scripts/verify_v3_b5_bundle.py`
- Test: `tests/test_v3_b5_bundle.py`

- [ ] **Step 1: Write RED tests for bundle admission.**

Assert missing base/stress/benchmark/control, source tamper, identity mismatch, observation hash mismatch, future date, daily sequence gap, and conflicting deterministic IDs all fail before bundle publication. Assert exact reuse is idempotent and the old one-shot audit remains unchanged during tests.

- [ ] **Step 2: Run the bundle RED suite.**

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_v3_b5_bundle -v
```

- [ ] **Step 3: Implement atomic write-once bundle assembly.**

The bundle manifest must bind all four result IDs/hashes, the source-inventory successor, B4 event/observation hashes, protocol/revision/snapshot/membership/calendar/scope, and producer/verifier source hashes. Write temp file, flush/fsync, then replace only a new target; an existing same-ID exact payload is reused and an existing conflicting payload fails without overwrite.

- [ ] **Step 4: Run GREEN and independent bundle verification.**

Run the same focused command, then:

```powershell
$bundleDir = (Get-ChildItem -LiteralPath 'D:\Codex\TraderLens\data\pit\v3_b5_validation_bundles' -Directory | Sort-Object Name | Select-Object -Last 1).FullName
& D:\Codex\TraderLens\.venv\Scripts\python.exe -m scripts.verify_v3_b5_bundle $bundleDir
```

Expected result: exit 0 for both and status `verified`; no DB write and no OOS read.

## Task 7: Add one-shot B5 admission before OOS

**Files:**
- Modify: `scripts/run_v3_task4_once.py`
- Test: `tests/test_run_v3_task4_once.py`

- [ ] **Step 1: Write RED tests for the protected boundary.**

Assert missing or invalid bundle returns `hard_block:b5_validation_inputs_missing` before `B6ValidationFlow`, `reserve_oos_draw`, `start_execution`, `immutable_backtest_reports`, task creation, or ledger writes. Assert a verified exact bundle is discovered with all four IDs/hashes and only then returns the next prerequisite. Assert temp audit injection never writes production audit.

- [ ] **Step 2: Run the one-shot RED suite.**

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_run_v3_task4_once -v
```

- [ ] **Step 3: Implement read-only bundle discovery.**

The discovery call must verify the exact v3 bundle and return its IDs, hashes, IS range, source inventory, and four-result status. It must execute before any B6/OOS path and must never consume OOS during discovery.

- [ ] **Step 4: Run GREEN and the direct B6 boundary suite.**

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_run_v3_task4_once tests.test_b6_no_shortcuts -v
```

Expected result: exit 0; missing/tampered bundle remains fail-safe; no B6/OOS writes occur in the tests.

## Task 8: Final focused verification and single production preflight

- [ ] **Step 1: Run every required focused suite separately.**

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_v3_b5_source_inventory -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_v3_b5_contracts -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_v3_b5_observation -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_v3_b5_costs -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_v3_b5_comparisons -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_v3_b5_bundle -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_run_v3_task4_once -v
```

Each command must be reported with exit code, passed/failed count, and warnings. Do not run full pytest/build.

- [ ] **Step 2: Perform one read-only artifact/database preflight before production discovery.**

Record verified source/bundle IDs and hashes, B4 artifact stability, and strategy.db counts. Expected baseline before any OOS node remains protocol=1, B6 task=0, reservation/state/ledger=0, immutable report=0, Gate result=0, and `oos_consumed=false`.

- [ ] **Step 3: Run one production discovery only after all four verifiers pass.**

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m scripts.run_v3_task4_once
```

This is the only production one-shot in this plan. It may update the existing audit only. It must not create B6 task, reserve/start OOS, create immutable report, or run Gate. If any new data/business/contract fault appears, stop without a second run.

- [ ] **Step 4: Verify the stopping boundary.**

Re-read audit and strategy.db counts. The acceptable result is discovery of a verified four-result B5 bundle and the next real prerequisite; OOS remains unread/unreserved/unconsumed. Do not run B6/OOS/Gate/Promotion/Signal in this plan.

## Scope and safety rules

- No provider/API calls, data collection, strategy parameter changes, template/hash changes, Task 3 rerun, liquidity/coverage/B3/market-regime rerun, full test/build, or Git/worktree operation.
- No generic benchmark/control platform, persistent precomputation, parallel framework, or new dependency.
- No rewrite of existing immutable B4, supplement, formal snapshot, membership, calendar, or old B5 artifacts.
- Any source hash mismatch, classification conflict, future read, daily gap, zero denominator, stress non-strictness, or result identity conflict is fail-loud.

## Plan self-review

1. Spec coverage: stress constants and repricing are Task 4; SW2021 source identity and effective dates are Task 1; ledger-replayed daily observations are Task 3; benchmark/control construction, P0 daily precedence, and the approved P2 carry are Task 5; immutable bundle and independent verifier are Tasks 2 and 6; one-shot OOS guard is Task 7; production boundary is Task 8.
2. Task5 completeness: P0 valid daily precedence and normal exit; A qualified held unavailable gap carry; B 2025-12-01 locked-position/no-open/no-trade/zero-turnover boundary; C next-valid-mark restoration; D suspension precedence; E no-prior/coverage-mismatch/unknown/delist fail-loud; F generic missing rejection; G NAV/cash arithmetic; H focused GREEN suites; I bounded 2025-11-24..2025-12-09 non-publishing slice covering 002348 P0 plus 14 P2 events and OOS=0; J one publisher and one verifier maximum after preflight; K stop at Task5 before Task6.
3. Completeness scan: every artifact, hash, file path, function boundary, test name and command is explicit; dynamic artifact directories are selected only after a successful publisher and are checked to be the sole new directory; no step depends on an unassigned value or an open-ended instruction.
4. Type consistency: source inventory ID/hash is used by the contract, cost, comparison, bundle, verifier, and one-shot tasks; observation hash is produced in Task 3 and bound in Tasks 2/6/7; comparison precedence is P0 daily, P1 suspension, P2 qualified unavailable carry, P3 fail-loud; P2 fields are `unavailable_mark_carry`, exact coverage row/hash, prior mark, locked units, turnover exclusion and read audit; all commands use the project Python path.
5. Self-review safety: all requirements are concrete and assigned; no Git/worktree/commit operation, production code change, artifact publication, DB write, OOS read/reservation/consumption, or Task6 execution is authorized by this design-only update.

This plan is design output only. It does not itself publish a source inventory, B5 result, bundle, B6 task, or OOS state.

## Task5 Step6 supplement: narrow publisher blocker and one-shot boundary

The read-only preflight identified one deterministic blocker: at
`scripts/publish_v3_b5_comparisons.py:251`, the lineage construction uses
`INITIAL_NAV`, `BASE_COST_BPS`, and `STRESS_COST_BPS`, but the publisher's
`backend.services.v3_b5_comparison` import list omits all three and the script
has no local definitions. The comparison service exports the approved values,
so the current call path would raise `NameError`. Production comparison
semantics and the frozen strategy contract remain unchanged.

The only authorized correction sequence is:

1. Add one real module-boundary test in
   `tests/test_v3_b5_comparisons.py` and observe the expected RED caused by the
   publisher's missing attributes.
2. Add only the three missing names to the existing publisher import list and
   observe the same test GREEN.
3. Run the specified compile and non-real focused suite checks, then repeat the
   existing read-only Step6 preflight and hash/baseline checks.
4. If and only if all checks pass, run the publisher exactly once; if and only
   if it exits zero and creates exactly one valid new directory, run the
   independent verifier exactly once.

Any new independent root cause, publisher/verifier failure, or mismatch stops
without a second correction or retry. No bounded real-slice rerun, Task6/B6,
OOS, Gate, Promotion, Signal, or other downstream action is authorized here.
