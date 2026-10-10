# v3 专用最小 B5 验证合同设计

状态：`design_ready_for_v3_only_implementation`

本文件只定义 v3 的 B5 最小合同，不实现代码、不发布 artifact、不写数据库，也不授权 OOS。它不是 B5 完成报告，也不表示 Task 4 完成。

## 1. 结论

推荐一条窄的 v3-only 路径：保留当前 v3 模板、revision、protocol、PIT 数据和执行 supplement；新增一个只服务于该 exact identity 的 B5 validation bundle，并让 B4 结果增加足以重算日收益的紧凑观测字段。B5 bundle 由基础成本、压力成本、benchmark、same-universe control 四个不可变结果组成，统一绑定同一 B4 event result、protocol、revision、formal snapshot、membership、calendar 和 source hashes。

用户已批准本节点的 transaction-cost stress 和 benchmark resolution；设计可进入 v3-only 实现计划，但尚未发布 B5 artifact，也未授权 OOS。

批准的 stress 是 deterministic transaction-cost stress：复用 `SYSTEM_STRESS_MULTIPLIER=2.0`，commission rate 从 `.0003` 加倍为 `.0006`，minimum commission `5.0`、sell stamp `.001`、transfer `0` 保持不变；slippage 为 `max(base_slippage_bps * 2, 10)`，当前 base=0 时按成交方向不利地重定价 10 bps；impact 为 `0` 且必须声明没有独立 impact model。只重算同一 124 fills，不改变 fills、数量、成交日或成交资格；它只称 transaction-cost stress，不称 capacity/liquidity/delay stress。

批准的 benchmark resolution 是：theme 层等于当前批准策略的单一 SH/SZ SW2021 PIT eligible universe；每个 frozen weekly formation/as_of 依据同一 PIT membership、lifecycle、ST、suspension/daily 和 v3 liquidity admission 构造 eligible members；使用 as_of 有效的正式 SW2021 L1 classification，按有成员的行业等权，行业内再等权，空行业剔除后归一；下一可执行 common day open 执行，复用 680c fill/cost/status/force-liquidation。benchmark 不使用 momentum/rank/top15/max5/3-day confirmation。same-universe control 使用同一 eligible universe 直接全股票等权，其他日期、PIT、fill、cost 规则相同。

## 2. 当前 frozen 输入边界

| 输入 | exact value |
|---|---|
| template | `relative_strength_rotation_shsz_sw2021_v3` |
| template version | `v3_shsz_sw2021_pit_12m_liquidity20d` |
| template hash | `f7c0fd8123f62f37118cb947e1735861374435f8707e01b06d788a8ec4df39c1` |
| requirements hash | `ef2ab5b1dafe4349f305b52733a7dcb018a2961464dfbc6542a10e34805d041d` |
| revision | `6440ffc03a742f4d4632078481cf3abf171eafb1a24f2bc69bc6f352d1b19ebc` |
| protocol | `6f7cbdcdeb26f8cdd2611a5450dbab3ff22544b6a66ec8539f5cab9151329111` |
| execution supplement | `680cd55c91254667` |
| supplement manifest SHA-256 | `c7bff428da948b54389c6c7415072de6ca5df4ebe777d251d1a06d08e6e8fb39` |
| formal snapshot | `v3ds_d73256081de82e8a` |
| snapshot semantic hash | `d73256081de82e8a764ea2394d613af820fd1b82e773c48156ca2463a452c80e` |
| scope | `acbc49159d989a46` / manifest `cef48909b7b7bb05bc952a19ff8e50702540b427c58fd21eb1670afcaf675c67` |
| membership | `pims_traderlens_v2_shsz_sw2021_pit_005` |
| B4 artifact | `20960e9fd15cdb44` |
| B4 manifest SHA-256 | `7b76000efaa9d709095ccb5a0c424e71432b933404ca68d35e08383a1cd04d30` |
| B4 event SHA-256 | `dec8460a98c6ebea243f069643f662fa80fa58db64ae10b7a87d9e38345a801c` |
| B4 IS | `2025-06-27..2026-03-19` |
| B4 result | canary `6/6 blocked`, qualification `pass`, future violations `0`, OOS reads `0` |

The one-shot audit is `docs/verification/task4_v3_one_shot_audit.json`, SHA-256 `db67a92283867f311f5758ccb6e9b18f45d8fdde14980b4e88f87ed1a35be78b`, and records the current four missing inputs: `base_cost`, `stress_cost`, `benchmark_comparison`, and `same_universe_control_comparison`.

## 3. 方案比较

### 方案 A：扩展现有 generic B5 validator/DB report

拒绝。`CostStressRunner` 目前只检查结果是否存在，并把 base slippage 乘以 2；`ControlComparison` 只做比较结果和 Gate 约束检查；`BacktestReportBuilder` 明确把 B4 结果的 cost/control 标成 `not_available_from_b4_result`。把这些校验器接到 B6 不会产生数据，反而会在 OOS reservation/start 后才暴露缺字段。

### 方案 B：直接从 20960 的最终持仓或固定 benchmark fixture 补字段

拒绝。20960 的 event result 只有 order intents、fills、rejections、future violations 和 final portfolio。它没有 daily equity/return 序列，不能诚实计算 beta、correlation、月度贡献或 same-day benchmark comparison。`backend/app/benchmark_data.py` 只加载 `tests/fixed_fixture/benchmarks`，不能成为生产输入；市场状态用的 000300 source 也明确不是 B6/OOS benchmark。固定股票列表会破坏 PIT 合同。

### 方案 C：v3-only instrumented validation bundle（推荐）

推荐。它只增加 v3 需要的观测和四个结果 artifact，不改变 generic StrategyConfig、策略规则、B4 fill/status 语义或 Gate。第一阶段从已 verified 的 20960 fills ledger 重放现金、持仓和正式日终 mark；不再次运行 signal/rank/order/fill。B5 的 admission 在四项独立 verifier 全部通过前停止在 preflight，不创建 B6 task、不 reserve/start OOS。

## 4. A：Base cost 合同

### 4.1 输入与绑定

Base result 必须绑定：

- exact protocol/revision/template/requirements/supplement/formal snapshot；
- B4 event result ID、manifest SHA 和 event SHA；
- `680cd55c91254667` 中的 fill/transaction-cost source hashes；
- IS/OOS window、calendar、PIT membership 和 data snapshot hashes；
- canonical assumptions payload hash。

允许使用现有 `20960` fills 做基础费用重算：每个 fill 已有 `fill_date/symbol/fill_price/fill_quantity/order_id`，并可通过同 ID order intent 得到 buy/sell 方向。现有 fill count 是 124，intents 是 136，rejections 是 12。该结果足以计算已成交订单的费用，不足以生成日收益序列。

### 4.2 固定计算

基础费用使用现有 `calculate_transaction_costs()` 的真实行为：

- commission rate `0.0003`，minimum commission `5.0`；
- sell stamp duty `0.001`；
- transfer fee `0.0`；
- fill slippage `0.0`；
- no separate impact model；因此 `impact_bps=0.0` 仅表示当前 frozen fill policy 没有独立 impact 项，不表示 impact 被估计为不存在。

B5 result 的分母必须是全体已成交 fills 的 gross notional：

`gross_notional = sum(fill_quantity * fill_price)`。

分别聚合 commission、stamp duty、transfer fee，并定义：

- `commission_bps = commission_total / gross_notional * 10000`；
- `slippage_bps = 0.0`；
- `impact_bps = 0.0`；
- `total_cost_bps = (commission_total + stamp_total + transfer_total) / gross_notional * 10000`。

空 fills 或零 gross notional 必须 fail loud；不得返回 0 作为缺失替代。`assumptions_hash` 是上述公式、常数、source hashes、event result hash 的 canonical hash。

### 4.3 是否需要 B4 successor

只发布 base cost 时，20960 fills 足够；不需要为 base 单独重跑。若 B5 还要求日收益、symbol/month contribution 或 strategy-vs-control 的相关序列，使用一个 v3-only ledger-observation artifact，从 20960 fills 重建日序列，不生成新的交易结果：

```text
daily_portfolio_observations:
  date, cash, portfolio_value, gross_exposure, net_exposure,
  positions_value, daily_return, position_values_by_symbol
```

这些字段由 immutable fills、冻结费用 primitive、正式 status/bar 和 common calendar 确定性重算；不改变交易决策。最终权威验收只比较 20960 实际序列化的 cash、positions(symbol/quantity)、portfolio_value、snapshot_date。average_cost/last_price 如写入 audit，只能标为 derived_not_predecessor_asserted，因为 20960 snapshot schema 不包含这两个 predecessor expected 字段。

### 4.4 Task 3 ledger-observation pivot

Task 3 的正式 observation producer 使用 `20960e9fd15cdb44` 作为唯一交易事件 predecessor。它按原始 fill 顺序恰好消费 124 笔 fills，以 order intent 核对方向，调用现有 `PortfolioState` 与 `calculate_transaction_costs()`，并在 176 个 IS common dates 上执行 status-aware EOD mark：正式停牌缺 bar 时保留最近 last_price，非停牌缺 bar fail loud。producer 不调用 rank、entry、exit、confirmation、liquidity 或 market-regime。

producer 与 verifier 必须绑定 B4 manifest/event、680c supplement、protocol/revision/formal snapshot、membership、calendar、scope 和 source hashes；输出 canonical JSON、sidecars、deterministic ID、write-once 语义，并声明 `not_authorized_for_b6_oos_gate_promotion_signal=true`直到最终 B5 bundle verified。失败的 instrumented runner、69866 observation seam 和 feasibility diagnostic 都不是交易 predecessor；feasibility diagnostic 仅作为设计证据。

## 5. B：Stress cost 合同

### 5.1 已证实的仓库边界

`backend/services/cost_stress_runner.py` 的现有实现只计算 `stress_slippage_bps = base_slippage_bps * 2.0`，且 strictness validator 允许与 base 相等。它本身不足以完成批准的 stress contract；本设计把批准的 floor 和 doubled commission 作为 v3-only producer 规则，不修改 generic runner 的 legacy 语义。

B5 计划允许压力提高 commission、slippage、liquidity haircut、停牌/退市 penalty 或延迟；本次批准只选择 transaction-cost stress，不引入 capacity、liquidity 或 delay 模型。

### 5.2 批准的 v3 transaction-cost stress contract

stress result 只对 B4 已成交的相同 124 fills 做 deterministic repricing。它必须逐项绑定：

```text
commission_rate = 0.0006
minimum_commission = 5.0
stamp_duty_rate = 0.001 for sells
transfer_fee_rate = 0.0
slippage_bps = max(base_slippage_bps * 2, 10)
impact_bps = 0.0, explicitly no independent impact model
fills/quantity/fill_date/fill_eligibility = identical to B4
liquidity_haircut/delay/suspension/delist stress = not modeled
```

买入 stress price 为 `fill_price * 1.001`，卖出 stress price 为 `fill_price * 0.999`。base 和 stress 都使用 gross traded notional 作为成本率分母；每个 result 的分母按其对应的重算成交价格确定。空 fills、非正分母或 `stress_total_cost_bps <= base_total_cost_bps` 必须 fail loud。该 policy 不改变 fills、数量、成交日或成交资格，也不声称模拟 capacity、liquidity、delay 或 impact。

## 6. C：Benchmark 合同

### 6.1 现有事实与正式 source

approved template 冻结 `benchmark_rule_id=theme_then_industry_then_equal_weight`。底层正式 SW2021 L1 source 已存在，但尚未作为 B5 result 发布。它是 `data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal/sw_l1_membership/manifest.json`，manifest SHA-256 为 `a38b3cc6be947b290078fe637466991ee8d13dee2794d398fb709d5c4c3826f3`，status=`collected_verified`，共 114 partitions，其中 61 个 SW2021 partitions、7,804 rows、31 个 L1 codes/names。每个 SW2021 partition 的 manifest hash 与实际 parquet bytes 独立匹配；source fields 包含 `ts_code,l1_code,l1_name,in_date,out_date,is_new`。manifest coverage checks 在 2016-01-04、2020-03-09、2024-10-17、2026-07-10 均 conflicts=0。

对 v3 IS 2025-06-27..2026-03-19 的只读复算覆盖 176 common dates：每个日期均有有效 L1 membership，未发现多 L1 conflict 或无行业成员；active source members 范围为 5,732..5,820。该 source 是当前 `_005` membership snapshot 的 exact upstream source，当前 snapshot 的 source_partition_audit 已保存 61 个 SW2021 partition hashes；因此可以作为 v3 B5 classification source inventory 精确绑定。它仍不是 B5 result，必须由后续 v3-only publisher 以 manifest/actual partition hashes 和 scope/template bindings 形成新的不可变 source binding。

formal snapshot 的 `benchmark_fingerprint` 仍为空，当前 v3 membership records schema 只有：

```text
symbol, effective_from, effective_to, source, snapshot_id
```

它能支持 PIT member inclusion，但行业层级必须从上述已 hash 绑定的 SW2021 source partitions 重新读取，不能只信 records parquet 的 source 字符串。

旧 `docs/verification/industry_control_group_pit_preflight.md` 只描述 `index_member_all` 的 SW2021 L1 industry PIT 规则，并绑定旧 v2 identity；它不是当前 v3 approved benchmark artifact。tests/fixed_fixture/benchmarks 也不属于 formal v3 source。

### 6.2 必须冻结的字段

一个可消费 benchmark result 必须绑定并明确：

- `benchmark_rule_id` exact string，且不能改名；
- theme source artifact、industry source artifact、两者的 PIT effective rule 和 source hashes；
- 每个 as_of 的 member set、theme/industry selection and conflict policy；
- equal-weight rule、空组/缺失分类规则；
- 与 v3 相同的 common calendar、as_of/execution mapping、IS/OOS boundary；
- raw/adjusted price choice、suspension/limit/delist rule、base/stress cost choice；
- daily benchmark equity/return series、result hash、artifact ID。

因此原 benchmark product blocker 已由用户批准的 resolution 消除；剩余工作是实现 source inventory、benchmark/control producer 和独立 verifier。不能把 000300、旧 v2 artifact 或测试 benchmark 当成替代物。

source inventory 的最小 exact binding 为：

```text
source_manifest_path:
  data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal/sw_l1_membership/manifest.json
source_manifest_sha256:
  a38b3cc6be947b290078fe637466991ee8d13dee2794d398fb709d5c4c3826f3
accepted_source_taxonomy: SW2021
accepted_partition_count: 61
source_fields: ts_code,l1_code,l1_name,in_date,out_date,is_new
pit_rule: in_date <= as_of <= out_date, with null out_date open-ended
```

Publisher 必须重读 61 个 SW2021 partitions，核对 manifest-declared hash 与 bytes hash、row count、required columns、date interval 和 duplicate/conflict rules；只能把该 inventory 的新 immutable successor 交给 B5 benchmark/control producer。当前 `_005` membership snapshot 的 `source_partition_audit` 可作为 lineage，但不能替代该 B5-specific source inventory。

## 7. D：Same-universe control 合同

该项可以在不引入静态股票列表的前提下形成窄 v3-only runner，并与 benchmark producer 共享同一 eligible universe，但输出和 verifier 必须保持独立。

Control universe 在每个 `as_of` 是 membership manifest 中满足：

`effective_from <= as_of AND (effective_to IS NULL OR effective_to >= as_of)`

且通过正式 lifecycle、ST、suspend/daily 可交易资格检查的 SH/SZ common members。它使用 `pims_traderlens_v2_shsz_sw2021_pit_005` records、现有 formal calendar、lifecycle and daily/status source；不使用 watchlist、top-5、当前股票列表或未来 membership。

Control 的唯一组合规则：在每个 v3 formation/rebalance execution date，以前一 completed common day 为 as_of，等权持有当日完整 eligible control universe；下一 rebalance 重新等权。它是 theoretical fractional comparison，不调用 680c 的 lot、minimum-commission、participation 或 PositionSizer；只复用 680c 已冻结的 status、suspension、mark 和 force-liquidation 边界，以及批准的 bps haircut。结果必须至少包含 daily equity、daily return、member count、rebalances、unavailable/status counts、cost summary 和 source hashes。

这个 control 不复用策略的 top-15%/rank/3-day confirmation，也不限制 max-5；它是 same-universe equal-weight comparison。它不是现有 `ControlComparison` validator 的输入，必须有一个 v3-only deterministic producer。若产品选择不接受该语义，control 也保持缺失；本文件不以旧 preflight 的“可用”状态替代批准。

### 7.1 Formal daily mark precedence

Coverage `status=unavailable` and `reason=required_history_missing` describe the
required historical window through `as_of_date`; they do not assert that the
execution-date formal daily mark is absent. Therefore the comparison source must
resolve a finite formal daily row before applying P2:

- **P0:** if the execution-date formal daily mark is present and the formal
  adapter resolves the day as tradable under the suspension precedence below,
  use that formal daily mark. A coverage-unavailable row may exclude the
  symbol from a new target in `members_for`, but it must not override the
  mark, trigger `unavailable_mark_carry`, or fail the existing position's
  valuation.
- If an existing position is no longer eligible because of coverage, but the
  execution-day formal daily/open and status are valid, process its ordinary
  exit using the formal execution open and include the actual trade in turnover.
- A daily row together with unresolved formal suspension evidence or an
  ambiguous source conflict remains a fail-loud conflict; P0 does not mask it.

The complete resolution matrix is:

| Priority | Required evidence | Comparison result |
|---|---|---|
| P0 | finite formal daily mark present; adapter-resolved tradable status; no unresolved or ambiguous conflict | use the formal daily mark; coverage may only exclude a new target; an existing no-longer-eligible holding exits normally when the formal open/status is tradable |
| P1 | daily mark missing and exact formal `S`/`P` evidence | use the existing suspension carry/lock path; do not synthesize a price or enter P2 |
| P2 | daily mark missing; no P1 evidence; all six qualified availability conditions below | use `unavailable_mark_carry` for an existing held position only; lock units and exclude the symbol from turnover |
| P3 | any other missing mark, imprecise coverage, no prior mark, unknown/conflicting status, or delist/force-liquidation boundary | fail loud; never apply generic last-price carry |

Daily-present plus unresolved formal suspension or ambiguous source conflict is
an explicit fail-loud source-conflict guard before P0, rather than a reason to
reinterpret the row as P2.

For this precedence, a valid daily row must have correctly typed, finite,
strictly positive `open`, `high`, `low`, `close`, `amount`, and `vol` values,
with the existing local OHLC ordering constraints. Any invalid daily source
row is a P3 source fault; suspension precedence must not make it tradable.

### 7.1.1 Narrow `suspend_d` daily-level precedence

The formal adapter must resolve `suspend_d` deterministically before the
comparison P0/P1 boundary. This is a daily-level rule for the existing
`DailyStatus` contract, not a general intraday status model or time parser:

- When a valid finite daily row exists, `R` is a resumption observation and does not
  make the day full-day suspended. The adapter returns `is_suspended=False`,
  preserves `suspend_reason="R"`, and the existing daily bar is usable.
- When a valid finite daily row exists and every same-day `S`/`P` suspension row has
  non-empty `suspend_timing`, the day is treated as an intraday or verified
  cross-session observation. The adapter returns `is_suspended=False`,
  preserves the deterministic `S`/`P` reason, and the daily row is usable for
  that day's next-open fill/mark. The raw `suspend_d` row and source hash
  remain the audit evidence; no new `DailyStatus` field is introduced.
- When a finite daily row exists and any same-day `S`/`P` row has missing or
  empty `suspend_timing`, the adapter returns `is_suspended=True`; the
  comparison's existing daily-plus-formal conflict guard remains fail-loud.
- When no daily row exists, any same-day `S`/`P` row returns
  `is_suspended=True` and keeps the existing P1 lock/carry path. This
  `S`/`P` evidence has deterministic priority over same-day `R` rows and does
  not depend on parquet row order. `R`-only with no daily row is a P3 formal
  status fault, not a suspension carry, and cannot be downgraded by coverage.
- Empty, unsupported, or otherwise unknown `suspend_type` is a P3 formal
  status fault for both daily-present and daily-missing rows; it must never be
  mapped to P1 suspension.
- Multiple same-symbol same-day `suspend_d` rows are resolved by explicit
  type/timing precedence, never by a dictionary's final-row overwrite. The
  adapter only tests whether `suspend_timing` is non-empty; it does not parse
  arbitrary time strings or infer `end < start`. The 603056 cross-session row
  is evidence-bound, not a generic parser rule.

The read-only evidence for this precedence is
`docs/verification/v3_b5_comparison_coverage_daily_semantics_diagnostic.json`,
file SHA-256 `e6437e544d145cdd866683933a421fdf20f4139bd54c30e33df7dc19f2ae9424`,
payload self-check SHA `a7a72d6f9df39d36c08b97b94020c857577978f8e2217ef00ff029c53fdd6d27`.
The diagnostic is evidence only and is not a runtime authorization source.
`_tmp_coverage_scan_result.json` is a non-production diagnostic scratch file;
the comparison producer must not consume it, and this design update does not
delete it.

### 7.2 已批准的 P2 unavailable-mark carry corrective

P2 只适用于 `schema_kind=theoretical_fractional_comparison_index` 的 benchmark/control，不能用于 v3 strategy、B4、真实交易或 OOS。它是对已诊断的精确 availability 缺口的窄 comparison accounting 规则；P0 正常 daily precedence 和 P1 exact formal suspension 优先于 P2；P3（任意 missing 都 carry）明确拒绝。

一个 execution-date/as_of/symbol 只有同时满足以下条件，才可进入 P2：

1. symbol 在该日已经是 existing held position；
2. 该 position 有正且 finite 的 units 与上一有效 comparison mark；
3. lifecycle active，且没有 delist 或 force-liquidation 边界；
4. 存在 exact verified coverage row，键为 execution_date、as_of_date、symbol，且 `status=unavailable`、`reason=required_history_missing`、`missing_fields` 明确包含 `daily.close`；
5. formal daily mark 在该日确实缺失；
6. 没有 suspension、source conflict、ambiguous status 或其它优先合同冲突。

P2 输出标记固定为 `unavailable_mark_carry`。它不是 suspension，不是真实价格，也不可交易。估值只沿用同一 raw 或 adjusted representation 的上一有效 mark，禁止 raw/adjusted 混用；缺口日该 symbol 的 return 记为零，下一有效 daily mark 到达后立即恢复真实 formal mark。

P2 日的 existing position 必须 locked：units 不变，不读取该 symbol 的 execution-day open，不产生 buy/sell，不计该 symbol turnover。blocked new buy 仍为零，不把其权重重分配给其它 symbols，现金保留。exact formal suspension 继续使用既有 suspension carry，且优先于 P2；P2 不覆盖 suspension 规则。coverage 不精确、无 prior mark、lifecycle delist/force-liquidation、unknown missing 或其它冲突都继续 P3 fail-loud，绝不使用 generic last-price carry。

P2 每日必须保持 `cash + positions_value = portfolio_value`、finite/positive NAV、无 material negative cash；gross holdings、cash、turnover 不受 base/stress haircut 改写，haircut 只作用于各自 net series。P2 的 lineage 必须消费现有 coverage binding 的 exact row/hash 字段，并把 `docs/verification/v3_b5_comparison_missing_mark_diagnostic.json`（SHA-256 `ab0e788b69c245d0a405d4f63bd900eb98902a33f170ae060540fbe98325098f`）作为审计证据绑定；诊断本身不是运行时授权 source。OOS guard 保持不变。

## 8. Result 与 source contract

### 8.1 最小不可变结果

四项结果建议统一放在新的 metadata-only bundle 目录 `data/pit/v3_b5_validation_bundles` 下，并使用 canonical manifest 计算出的 deterministic ID：

```text
data/pit/v3_b5_validation_bundles/
  manifest.json
  manifest.json.sha256
  base_cost.json
  stress_cost.json
  benchmark_comparison.json
  same_universe_control.json
  result.json
  result.json.sha256
```

文件不复制 parquet。每个子结果和 bundle manifest 使用 canonical UTF-8 JSON、`sort_keys=True`、紧凑 separators、deterministic ID、write-once 和 sidecar。相同 canonical payload 必须复用 ID；同 ID 不同 payload 必须 fail loud，不覆盖旧文件。

Bundle exact binds：

```text
template_id/version/template_hash/requirements_hash
strategy_revision_id
protocol_snapshot_id
execution_supplement_id + manifest_sha256
formal_snapshot_id + semantic_hash + manifest_sha256
B4 artifact_id + manifest_sha256 + event_sha256
scope_id + scope_manifest_sha256
membership_id + manifest/records hashes
common_calendar id/manifest/parquet/date-set hashes
gate criteria envelope hash
IS/OOS range and shared OOS window id
source file hashes and algorithm hashes for every producer
```

### 8.2 Independent verifier

verifier 必须从源文件和 B4 event result 重新计算：

1. all identity and lineage bindings；
2. canonical payload hash、artifact ID、sidecar；
3. base gross notional and fee arithmetic；
4. stress strictness and all policy fields；
5. benchmark/control member sets, dates, returns and source hashes；
6. no future reads, no out-of-window rows, no static universe；
7. write-once and conflict behavior。

manifest 自报字段不能作为唯一证据。任何 tamper、missing source、未知 policy、daily sequence gap、unavailable 误当 0 或 benchmark/control mismatch 都必须 fail loud。

## 9. Orchestration and OOS safety

one-shot 的 B5 discovery 必须在调用 `B6ValidationFlow` 前顺序执行：

```text
load protocol and B4 exact artifact
verify four B5 result artifacts and all bindings
if any missing/invalid: hard_block:b5_validation_inputs_missing
only after all four verified: permit B6 task/OOS reservation path
```

当前四项任意一项缺失都必须在 `reserve_oos_draw()`、`start_execution()`、`BacktestReportBuilder.build_report()` 之前返回。不能先创建 `immutable_backtest_reports` 来承载 IS，也不能让 B6 先消耗 OOS 再由 Gate 报缺字段。

Signal Board/Action Plan 不在本设计修改范围。B5 blocked 继续由已有 validation-status UI 显示 `watch`、`actionable=false`、`candidate_is_signal=false`，不创建 PlannedSignal、Execution Log 或 Action Plan。

## 10. 实现任务拆分（后续节点，不在本节点执行）

1. **Contract types and publisher**：定义 bundle/sub-result payload、canonical hash、sidecar、write-once；先覆盖 exact binding、tamper、conflict。
2. **Instrumented v3 result**：在 v3 dedicated executor 只增加 daily observation，不改变 signal/order/fill/status；用 focused test 证明现有 fills/order/future guard 不变；源稳定后只允许一次完整授权运行。
3. **Base cost producer**：从 fills+intents 真实重算费用，验证 gross-notional denominator、minimum commission、stamp/transfer、zero-impact disclosure。
4. **Stress producer**：按批准的 doubled commission、10 bps adverse repricing、同 fills/write-once policy 实现；不得扩展成 capacity/liquidity/delay simulator。
5. **Control producer**：使用正式 PIT membership/calendar/source，验证 no static list、as_of boundary、等权、status/delist 和 daily series；先执行 P0 formal daily precedence，再对 exact six-condition P2 held unavailable mark 执行 locked/carry/no-turnover，否则 fail-loud。
6. **Benchmark producer**：从已 hash 绑定的 SW2021 L1 partitions 构造 PIT industry groups，按批准的 industry-equal-weight resolution 生成 benchmark；source inventory 必须先独立 verified，并与 control 共用但独立验证 P0 precedence 与 P2 admission。
7. **One-shot admission**：新增四项独立 verify 及 audit 摘要；测试确认缺失/篡改都在 OOS guard 前 fail。

建议的 focused RED→GREEN 边界：

```text
tests/test_v3_b5_contracts.py
tests/test_v3_b5_base_cost.py
tests/test_v3_b5_stress_policy.py
tests/test_v3_b5_control.py
tests/test_v3_b5_benchmark.py
tests/test_run_v3_task4_once.py
tests/test_b6_no_shortcuts.py
```

生产执行只允许：所有 focused suites GREEN、所有 source hashes final、四项 artifact 各独立 verifier verified 后，一次 v3 B5 preflight；成功才允许后续 B6/OOS 节点决定是否运行。任何真实数据/业务/合同错误停止，不修改 frozen strategy 以绕过。

## 11. 方案与范围自审

- 未新增策略、generic DSL、持久预计算平台、并行框架或依赖。
- 未修改 v3 template/hash/requirements、protocol、B4 artifact、supplement、formal snapshot、membership、calendar 或 DB。
- 未把测试 fixture、旧 v2 control preflight、market-regime 000300 source 或当前 D snapshot 当作 v3 B5 输入。
- P0 formal daily mark 优先于 coverage-unavailable eligibility；coverage 不得覆盖有效 execution-day mark。P2 只对 exact verified availability row 的 existing held position 生效；suspension、delist、无 prior mark、source conflict 和 generic missing 仍 fail-loud，P3 不进入合同。
- 未把 `OOS_DRAW_POLICIES` 中声明但未被 `PrototypeGateV2.evaluate()` 执行的 Sharpe/trades/drawdown 规则伪装成 B5 effective result。
- 未创建 B6 task、reservation、ledger、immutable report、Gate result 或 Signal。
- 本文没有空缺路径、未赋值的 hash、默认费用或隐式 benchmark fallback；stress 和 benchmark 规则均已记录为批准的 exact contract，B5 artifact 仍须经过后续独立 verifier。

## 12. 只读证据索引

| path | SHA-256 | 证据 |
|---|---|---|
| `docs/verification/task4_v3_one_shot_audit.json` | `db67a92283867f311f5758ccb6e9b18f45d8fdde14980b4e88f87ed1a35be78b` | current hard block and four missing inputs |
| `data/pit/v3_b4_is_results/20960e9fd15cdb44/manifest.json` | `7b76000efaa9d709095ccb5a0c424e71432b933404ca68d35e08383a1cd04d30` | verified v3 B4 IS binding |
| `data/pit/v3_b4_is_results/20960e9fd15cdb44/event_result.json` | `dec8460a98c6ebea243f069643f662fa80fa58db64ae10b7a87d9e38345a801c` | 124 fills, 136 intents, final-only result |
| `data/pit/v3_execution_semantics_supplements/680cd55c91254667/manifest.json` | `c7bff428da948b54389c6c7415072de6ca5df4ebe777d251d1a06d08e6e8fb39` | exact fees, fill/status/order semantics |
| `data/pit/v3_formal_data_snapshot_manifests/v3ds_d73256081de82e8a/manifest.json` | `57067e15e6ad1a92b23b42b48173b6cf1af2e7e23f3357320288fb7e109c2680` | formal v3 snapshot; empty benchmark fingerprint |
| `data/pit/pit_membership_snapshots/pims_traderlens_v2_shsz_sw2021_pit_005/manifest.json` | `32f58adbca49fb89dfeb54ceeb4ac9b27b6a26c55e0c9cfeae7a8fcaf3683f10` | frozen PIT membership metadata |
| `data/pit/pit_membership_snapshots/pims_traderlens_v2_shsz_sw2021_pit_005/records.parquet` | `2e8c922de9f198ab18a6b38743a01f4343fbf52b876da84026389d3ffd11eec0` | symbol/effective interval records; no theme/industry fields |
| `data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal/sw_l1_membership/manifest.json` | `a38b3cc6be947b290078fe637466991ee8d13dee2794d398fb709d5c4c3826f3` | collected_verified SW2021 L1 source; 61 partitions/7,804 rows; source fields include effective dates and L1 classification |
| `backend/services/cost_stress_runner.py` | `473c5d3ae28a7230e6a60bac47813311a175fd1faf70a26fc710f24a3ead522d` | multiplier-only stress validator |
| `backend/services/control_comparison.py` | `338ad35385e69ae11675db715e1a0658ac5e1619d690ac3a03a4bcf99c8fceeb` | comparison validators, no runner |
| `backend/services/backtest_report_builder.py` | `86fd87b3e8d124de6df99633bc31702ca0f1c5c86ec6a8016626ba2cd4c9a9a3` | B4 result fields unavailable for B5 |
| `backend/services/b6_validation_flow.py` | `82ee063958fbd0c32a0ec3f91a2198059996a72abb6ab3ff6d591507a3fb17ac` | reserve/start before report/Gate |
| `backend/services/prototype_gate_v2.py` | `90b7866c709197ed65ba0d5d9b3a7dd56d67c5801ce6e9d5da1ccc0b8ce2a8b7` | missing B5 fields block Gate |
| `backend/services/b4_protocol_types.py` | `10eb75f2cec6e5df23eab08be656baef0b487a2c5a7f13feecd44aa64862d0c3` | final-only EventBacktestResult contract |
| `strategy_core/transaction_costs.py` | `936026bd4334d452204e76b473f03a424937a1866078fa8fb4c9fce1d54552c2` | exact base fee calculation |
| `strategy_core/fill_simulator.py` | `050f0fd9a235ddb6c833131ce7a172655fab0341a03060cd47ae1290f03734b4` | fill defaults and status/participation behavior |
| `docs/verification/industry_control_group_pit_preflight.md` | `73a23bb37c61a0ab54975d95d504989de3a341a7a7527def348de25bb72f454a` | old v2 preflight only; not v3 admission |
| `docs/verification/v3_b5_comparison_missing_mark_diagnostic.json` | `ab0e788b69c245d0a405d4f63bd900eb98902a33f170ae060540fbe98325098f` | 14/14 qualified B-class unavailable-mark events; comparison-only evidence |

## 13. Task5 approved theoretical-fractional comparison contract

`benchmark_comparison` and `same_universe_control_comparison` use
`schema_kind=theoretical_fractional_comparison_index`. Initial NAV is the normalized
index unit `1.0`; this is not a renminbi account and is not executable. The producer
must not use 100-share lots, minimum commissions, max participation, `PositionSizer`,
`OrderIntent`, `Fill`, or `PlannedSignal`.

The exact IS is `2025-06-27..2026-03-19`. Reuse the v3 38 weekly formation/as_of
pairs: the first IS execution day is the initial formation; each later ISO week uses
its first common open day as execution, with the previous completed common day as as_of.
Weights are formed at as_of and become effective at execution-day open.

Eligibility is the intersection of SH/SZ scope, closed PIT membership intervals,
formal lifecycle, ST, formal daily/status availability, and the verified v3 20-day
liquidity admission. SW2021 L1 is read only from source-inventory successor
`2fe8321a5f644b9b`; missing or multiple active L1 codes, static lists, 000300, old-v2
or fixture benchmark inputs fail loud. Benchmark equal-weights non-empty L1 industries
and then members within each industry. Control directly equal-weights the same final
eligible symbols. Target weights must sum to one.

Fractional units are `allocated_nav / formal execution-day open`. A new target with a
missing or non-buyable open keeps its target cash and is not reallocated. Exact formal
suspension uses the existing suspension carry path. A non-suspended missing bar is
admitted only by the six-condition P2 contract in Section 7.2: an already-held active
position with an exact verified `required_history_missing` coverage row containing
`daily.close`, a prior valid mark, and no conflict. On that day it is locked, carries
the same raw/adjusted mark representation, and cannot trade or add turnover. A missing
bar without that exact evidence, ambiguous status, source conflict, or unresolved
delist is a data fault. Delist uses the existing formal lifecycle/force-liquidation
boundary and never invents a price. Execution-day and ordinary-day valid marks use
formal close; the P2 mark is restored to formal close at the next valid daily row.

Turnover is the sum over symbols of
`abs(executed_target_weight - pre_trade_weight)` using pre-trade NAV normalization,
without a second cash term. Base and stress haircuts are respectively
`turnover*8.0431006062/10000` and `turnover*20.8425059905/10000`, exact-bound to cost
artifact `79d198f5fddc4037`. Gross NAV is unhaircut; base-net is the primary series and
stress-net is pressure evidence. Each result publishes ordered daily rows, 38
rebalance target/executed weight sets, turnover/cost rows, status/unavailable counts,
and source/read audit.

Metrics are deterministic: cumulative return=`last_nav/first_nav-1`; relative return=
strategy cumulative minus comparator cumulative; daily beta=`cov(strategy_returns,
comparator_returns)/var(comparator_returns)`; correlation is Pearson correlation over
the same 176 daily rows. Insufficient samples or non-finite values fail loud. Ordered
weights and daily position values remain in the result for symbol/month concentration
audit; symbol and `YYYY-MM` marked-value contribution series must reconcile to the
comparator NAV movement. These comparison artifacts remain
`not_authorized_for_b6_oos_gate_promotion_signal=true` until Task6 bundle verification.

## Task5 Step6 preflight supplement: publisher import boundary

The independent read-only Step6 preflight found a deterministic publisher blocker
at `scripts/publish_v3_b5_comparisons.py:251`. The lineage payload references
`INITIAL_NAV`, `BASE_COST_BPS`, and `STRESS_COST_BPS`, while the existing import
list from `backend.services.v3_b5_comparison` does not bind those names and the
publisher defines none locally. The comparison service exports the existing
approved values. Executing the lineage construction would therefore raise
`NameError`; this is a publisher binding defect, not a change to comparison
semantics or the frozen strategy contract.

The authorized TDD correction is limited to one real module-boundary test that
compares the publisher's three bindings with the comparison service constants,
followed by the minimal three-name import addition. After focused verification
and a fresh read-only preflight, this supplement permits at most one publisher
attempt and, only after a sole valid artifact directory exists, at most one
independent verifier attempt. It does not authorize a bounded real-slice rerun,
Task6/B6, OOS, Gate, Promotion, Signal, or any other downstream action.
