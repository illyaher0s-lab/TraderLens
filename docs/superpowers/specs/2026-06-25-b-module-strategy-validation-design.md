# B 模块（策略验证模块）V1 设计

**日期：** 2026-06-25  
**修订：** 2026-06-26（模板化策略、确定性 OOS、多重比较与对照组加严）  
**状态：** 已确认设计  
**方案：** 在现有 `strategy_core` 上增加薄控制层  
**上游：** A 模块 `confirmed_candidate_pool`、`hypothesis_draft`  
**下游：** C 模块只接收经人工同步确认后的 `prototype_passed` 策略

---

## 1. 目标与最高原则

B 模块不是“能跑回测”的展示系统，而是在投入真实资金前，用历史数据淘汰无效假设的验证系统。

V1 的优先级如下：

1. 防止自欺：防过拟合、防未来函数、防幸存者偏差、防虚假成交、防静默数据填充。
2. 宁可误杀潜在好策略，也不能放行由偏差制造的好结果。
3. 负责人不需要懂股票或技术指标。系统不得要求负责人选择参数、制定交易规则或确认技术细节。
4. LLM 只负责把非结构化假设分类到已注册的策略模板，不自由生成技术参数，也不参与信号、成交、盈亏、Gate、预算、缓存或状态流转。
5. 回测、模拟盘和实盘必须共用同一套 `strategy_core` 信号与执行语义。

负责人的职责只有一项：

- 阅读系统翻译后的 Gate 结论，在 `promote_to_prototype_passed` 操作中同步确认或拒绝。

Gate 的技术阈值由系统 baseline 决定，不要求负责人设置最低收益、最大回撤、最低交易数或其他统计参数。

负责人不确认以下技术参数：

- 指标周期和排名分位数；
- 止损比例、持有期、成交细节；
- 具体 entry、exit、risk 规则；
- 样本内参数调整过程。

---

## 2. V1 范围

### 2.1 输入

- A 模块冻结的 `confirmed_candidate_pool`：
  - `theme_id`
  - 候选股票
  - 研究判断
  - Evidence 快照引用
  - 价格和基准快照
- A 模块的 `hypothesis_draft`：
  - 可规则化的 entry 候选
  - 可规则化的 exit 候选
  - 可规则化的 risk 候选
  - 不可规则化的研究背景
- Tushare 历史行情、交易状态、财务公告日期和历史成分数据。

### 2.2 输出

- 不可变的回测报告；
- 不可变的 `PrototypeGateResult`；
- Gate 只能给出：
  - `rejected`
  - `needs_review`
  - `candidate_for_prototype_passed`
- 人工同步确认后，`StrategyPromotionReducer` 才能把状态从 `draft` 改为 `prototype_passed`。

### 2.3 明确不做

- 参数搜索、网格搜索、贝叶斯优化或自动调参；
- 参数敏感性扫描或参数扰动；
- 同一策略生成多个变体后择优；
- 每个 confirmed candidate 单独生成策略；
- 跨候选、跨主题或跨策略组合关系；
- Evidence 事件直接触发交易信号；
- 让负责人确认技术参数；
- Gate 自动晋升或自动修改策略状态；
- LLM 综合评分或多 Agent 风险委员会参与 Gate；
- 独立失败原因知识库；
- 复杂策略相似度检索；
- 目标价、券商接口或自动下单；
- 为 V2 功能预留抽象层或复杂插件接口。

V2 如增加参数邻域检查，只能命名为 `fragility_check`，用于标记脆弱性，不能用于选择更优参数。

---

## 3. 核心研究单位

V1 采用 theme-level 单策略：

```text
one theme
  = one hypothesis
  = one strategy family
  = one OOS evaluation budget
```

同一主题的候选股票不能拆成多个独立策略反复试验。否则会：

- 打碎样本量；
- 降低每套策略的交易笔数；
- 形成多重比较；
- 绕过主题级 OOS 预算；
- 在相同数据上反复挑选好看的结果。

允许在同一 theme 下生成新的策略修订版，但每个修订版都保留自己的语义 hash。新 revision 只能来自更新后的 hypothesis snapshot、模板选择重跑或确定性校验修复；禁止一次生成全部模板并按 IS/OOS 结果择优。样本内运行不消耗预算；新 revision 再次查看 OOS，若三元组发生变化，则消耗一次新的 OOS 评估预算并提高 `oos_draw_index`。

---

## 4. 总体架构

采用“薄控制层扩展”：

```text
confirmed_candidate_pool + hypothesis_draft
                 │
                 ▼
Hypothesis Builder
LLM 只选择 strategy_template_id
                 │
                 ▼
Strategy Template Library
系统填充冻结的默认参数
                 │
                 ▼
确定性 Validator + 定向 repair loop
                 │
                 ▼
生成并冻结 StrategyDraft
                 │
                 ▼
Canary Engine Qualification
未来数据访问必须被阻断
                 │
                 ▼
        ┌────────┴────────┐
        ▼                 ▼
无限 IS 回测       Freeze ResearchProtocolSnapshot
不扣预算                    │
                            ▼
                  确定性生成 OOS Window
                            │
                            ▼
                 OOS Evaluation Controller
             缓存 / 预算 / 防重复立项 / 原子预留
                            │
                            ▼
                   strategy_core
             确定性事件驱动回测执行
                            │
                            ▼
            Base Cost + Stress Cost + Controls
                            │
                            ▼
               ImmutableBacktestReport
                            │
                            ▼
                 Prototype Gate
        多重比较 / Alpha / 分布检查 / 只读建议
                            │
               ┌────────────┴────────────┐
               ▼                         ▼
   rejected / needs_review      candidate_for_prototype_passed
                                         │
                                 人工同步确认
                                         │
                                         ▼
                              StrategyPromotionReducer
                                         │
                                         ▼
                                prototype_passed
```

薄控制层负责：

- 策略模板注册、模板选择与草稿合法性校验；
- 研究协议冻结；
- OOS 窗口确定性生成；
- hash 生成；
- IS/OOS 路由；
- OOS 预算与缓存；
- OOS draw index 与多重比较规则；
- 对照组和成本压力编排；
- 报告不可变存储；
- Gate 结果存储；
- 人工晋升状态机。

`strategy_core` 只负责：

- 解析合法策略配置；
- 读取只读快照；
- 构建历史时点 universe；
- 按时间游标生成信号；
- 模拟成交；
- 计算盈亏和指标；
- 返回确定性回测结果。

控制层不能修改 `strategy_core` 内部执行结果，`strategy_core` 也不能修改控制层的研究协议、预算、Gate 或策略状态。

---

## 5. 核心对象与硬边界

### 5.1 StrategyTemplateLibrary

Hypothesis Builder 不“创造参数”，只从系统注册表选择一个模板。

V1 初始模板严格限制为：

- `theme_momentum_breakout_v1`
- `relative_strength_rotation_v1`
- `volume_breakout_followthrough_v1`
- `trend_pullback_watch_v1`

每个模板由确定性代码定义：

- 支持的 hypothesis 类型；
- entry、exit、risk 和 rebalance 规则；
- 指标周期、分位数、止损和持有期等默认值；
- fill model 和成本模型；
- 允许使用的 point-in-time universe 规则；
- 默认 benchmark 选择规则；
- 支持的确定性 OOS window rule；
- 模板版本和模板内容 hash。

LLM 只输出：

```text
strategy_template_id
template_selection_reason
unmapped_hypothesis_elements
```

LLM 不得决定：

- 前 10% 还是前 15%；
- 止损 8% 还是 10%；
- 持有 10 天还是 20 天；
- 均线 20 日还是 60 日；
- OOS 起止日期；
- Gate 阈值。

新增模板属于代码和测试变更，不允许通过运行时 prompt 临时生成。

### 5.2 StrategyDraft

Hypothesis Builder 的确定性输出容器。

包含：

- `theme_id`
- `hypothesis_id`
- `strategy_revision_id`
- `strategy_template_id`
- `strategy_template_version`
- `strategy_template_hash`
- `hypothesis_source_snapshot`
- `backtest_universe_spec`
- entry、exit、risk、rebalance、fill、cost 规则
- 注册的 sample split rule
- `status = draft`
- `frozen_at`
- `editable = false`

约束：

- 系统根据模板一次生成一组冻结默认值；
- 不生成参数变体；
- Evidence 事件规则不得进入 entry、exit 或 risk；
- LLM 不得写 hash、预算、Gate 结果或状态；
- LLM 输出必须经过确定性 validator；
- repair loop 只接收明确校验错误，不做盲重试。
- StrategyDraft 生成后立即冻结；
- 重跑 LLM 必须创建新的 `strategy_revision_id`；
- 新 revision 不得覆盖或静默替换旧 StrategyDraft；
- 同一 hypothesis 的所有 revision 必须保持可见。

### 5.3 BacktestUniverseSpec

历史回测专用、point-in-time 的 universe 类型。

至少包含：

- `universe_rule_type = sector_plus_tags | point_in_time_membership`
- `sector`
- `chain_layer_tags`
- `membership_source`
- `membership_effective_from`
- `membership_effective_to`
- `snapshot_date`
- `include_delisted = true`
- `membership_snapshot_ids`
- `quality_status`
- `gaps`

正式历史验证不得接受静态的 `confirmed_candidate_pool` symbol 列表。

### 5.4 ForwardWatchlistSnapshot

A 模块 `confirmed_candidate_pool` 的前向只读映射，只供 C 模块对最新 EOD 数据生成计划信号。

它与 `BacktestUniverseSpec` 必须是两个不可互相转换的类型：

- 不存在公共基类提供隐式 universe 转换；
- 不提供 `to_backtest_universe()`；
- 回测 API 的类型签名只接受 `BacktestUniverseSpec`；
- `ForwardWatchlistSnapshot` 传入回测入口时必须立即失败；
- 不允许通过展开 symbols 后绕过类型边界。

如果研究人员明确使用当前候选池做历史试跑，报告必须标为：

```text
prototype_sanity_check_only
```

并禁止产生正式 OOS Gate 判决或历史有效性声明。

### 5.5 ResearchProtocolSnapshot

第一次 OOS 评估前必须冻结的研究协议。

包含：

- `protocol_snapshot_id`
- `theme_id`
- `hypothesis_source_snapshot_id`
- `strategy_revision_id`
- `sample_split`
- `oos_window_rule_id`
- `oos_window_rule_params`
- `oos_window_start`
- `oos_window_end`
- `shared_oos_window_id`
- `backtest_universe_spec_id`
- `data_snapshot_id`
- `kill_criteria_snapshot`
- `prototype_gate_thresholds`
- `strategy_config_hash`
- `data_snapshot_hash`
- `gate_criteria_hash`
- `frozen_at`
- `frozen_by`
- `editable = false`

硬边界：

- 三个 hash 在冻结时生成；
- 冻结必须发生在第一次 OOS 评估前；
- 冻结后 `strategy_core` 只读；
- 不存在原地编辑；
- 任何字段变化必须创建新的 `ResearchProtocolSnapshot`；
- 新 snapshot 不覆盖旧 snapshot；
- 控制层不能反向修改已经进入 `strategy_core` 的 snapshot；
- OOS 请求缺少任意一个 hash 时立即拒绝。
- API 不接受用户或 LLM 自由输入 OOS `start/end`；
- OOS 窗口必须由注册的确定性规则生成；
- 重新立项更换窗口只能通过注册规则平移或更换数据快照，不能人工挑选有利区间。

### 5.6 OOSEvaluationLedger

主题级 OOS 预算、缓存和防绕过账本。

包含：

- `theme_id`
- `hypothesis_source_snapshot_id`
- `oos_evaluation_count`
- `oos_budget_limit = 3`
- `next_oos_draw_index = 1 | 2 | 3`
- `budget_status = available | reserved | oos_budget_exhausted`
- 已完成评估三元组
- 进行中预留
- 报告引用
- 重立项历史

必须建立两类唯一约束：

```text
evaluation cache key:
(strategy_config_hash, data_snapshot_hash, gate_criteria_hash)

cross-theme OOS reuse guard:
(oos_window_start, oos_window_end, data_snapshot_hash)
```

第二个唯一约束跨 theme 生效。新 `theme_id` 如果复用已经使用过的 OOS 区间和相同数据快照，必须拒绝。重新立项必须至少改变 OOS 区间或数据快照。

### 5.7 ImmutableBacktestReport

报告只追加，不修改、不覆盖、不删除。

至少包含：

- `report_id`
- `theme_id`
- `strategy_revision_id`
- `protocol_snapshot_id`
- 三个 hash
- `oos_draw_index`
- `shared_oos_window_id`
- `multiple_comparison_flag`
- `evaluation_mode = in_sample | out_of_sample | prototype_sanity_check_only`
- 完整回测指标
- `base_cost_result`
- `stress_cost_result`
- `control_comparison`
- `excess_return_vs_benchmark`
- `excess_drawdown_vs_benchmark`
- `cost_adjusted_alpha`
- `beta_dominated_flag`
- `oos_calendar_months`
- `active_trading_months`
- `max_single_month_pnl_contribution_pct`
- `max_single_symbol_pnl_contribution_pct`
- 交易明细
- 成交阻塞统计
- 数据质量
- `survivorship_bias_warning`
- 调整价格口径及计算时点
- 缺失数据和 degraded 原因
- `generated_at`
- `report_hash`

正式 OOS 报告必须包含固定声明：

> 本策略仅表示：在当前单一策略配置、冻结数据快照、冻结 OOS 规则、冻结 Gate 标准下通过原型验证。
>
> 这不表示参数邻域稳健、未来收益可复制、策略已经适合自动交易，也不表示可以跳过人工执行判断。

失败策略和失败报告必须保持可见，禁止物理删除或隐藏归档。

### 5.8 PrototypeGateResult

Gate 结果只读、不可变。

包含：

- `gate_result_id`
- `report_id`
- `verdict`
- `checks`
- `blocking_issues`
- `warnings`
- 三个 hash
- `oos_draw_index`
- `shared_oos_window_id`
- `multiple_comparison_flag`
- `generated_at`
- `gate_result_hash`

`verdict` 只能为：

- `rejected`
- `needs_review`
- `candidate_for_prototype_passed`

Gate 不得输出 `prototype_passed`。

### 5.9 StrategyPromotionReducer

这是 `draft → prototype_passed` 的唯一写入口。

Reducer 只有在以下条件全部满足时才允许晋升：

- 存在不可变 Gate 结果；
- verdict 为 `candidate_for_prototype_passed`；
- Gate 三个 hash 与报告及冻结协议一致；
- 报告没有完整性错误；
- 用户完成 `human_required_sync`；
- 当前策略状态仍为 `draft`；
- 晋升请求未被重复消费。

以下组件一律没有策略状态写权限：

- Hypothesis Builder；
- repair loop；
- strategy_core；
- 回测器；
- OOS Controller；
- Prototype Gate；
- 报告生成器；
- 异步 review 队列。

测试必须证明：除 `StrategyPromotionReducer` 外，任何代码路径尝试写入 `prototype_passed` 都失败。

---

## 6. Hypothesis Builder

### 6.1 生成方式

LLM 读取 `hypothesis_draft` 和研究快照，只选择一个已注册的 `strategy_template_id`。

系统根据模板确定性生成：

- 策略结构和默认数值；
- point-in-time universe 规则；
- entry、exit、risk、rebalance、fill 和成本设置；
- sample split rule；
- benchmark rule。

负责人不逐项确认。

### 6.2 确定性校验

Validator 必须检查：

- 指标和操作符是否被 `strategy_core` 支持；
- 所有参数是否与注册模板完全一致；
- template ID、版本和 hash 是否存在且匹配；
- entry、exit 和 risk 是否完整；
- 是否使用 T 日收盘信号、T+1 执行；
- universe 是否为 `BacktestUniverseSpec`；
- sample split rule 是否已注册且无重叠；
- 成本假设是否完整；
- 是否包含公告关键词、订单、客户认证等 Evidence 事件；
- 是否包含未支持的基本面触发条件；
- 是否试图生成参数搜索、变体列表或候选级策略；
- 是否试图直接填写 OOS 起止日期；
- 是否试图写状态、hash、预算或 Gate 结论。

### 6.3 Repair loop

- 校验失败后，将结构化错误返回给模型；
- 模型只修正失败字段；
- 每次修复重新执行完整确定性校验；
- `max_repairs = 2`；
- 两次修复仍失败则明确结束并保留失败草稿；
- 不允许相同输入无错误信息地盲重试；
- repair 不消耗 OOS 预算。

---

## 7. Hash 与确定性回放

### 7.1 strategy_config_hash

只覆盖影响信号和执行结果的语义字段：

- strategy template ID、版本和内容 hash；
- `BacktestUniverseSpec` 的历史规则；
- entry 条件；
- exit 条件；
- risk filters；
- rebalance；
- fill model；
- 成本和滑点；
- sample split；
- OOS window rule ID 和参数；
- backtest range；
- benchmark；
- 调整价格口径。

排除：

- strategy name；
- notes；
- created_at、updated_at；
- UI 字段顺序；
- 状态；
- 自动生成 ID；
- Gate 阈值。

字段规范化和 hash 算法必须放在 `strategy_core` 的单一共享实现中，Hypothesis Builder、回测器、OOS Controller 和缓存不得自行计算不同版本。

### 7.2 data_snapshot_hash

覆盖：

- point-in-time 成分；
- 历史行情；
- 每日 ST、停牌和涨跌停状态；
- 交易日历；
- 退市股覆盖；
- 基准数据；
- 财务 `ann_date` 数据；
- 调整因子口径；
- 数据供应商及修订版本；
- 可见的数据缺口。

### 7.3 gate_criteria_hash

覆盖：

- 系统 baseline Gate 阈值；
- 按 `oos_draw_index` 收紧的预注册阈值表；
- 数据质量 Gate；
- 最低统计有效性门槛；
- 成本敏感性要求；
- 对照组和 alpha 要求；
- 交易收益分布集中度要求；
- 幸存者偏差政策。

Gate 阈值不进入 `strategy_config_hash`。

### 7.4 缓存语义

OOS 评估身份为：

```text
(strategy_config_hash, data_snapshot_hash, gate_criteria_hash)
```

- 三者完全相同：返回缓存报告，不扣预算；
- 任一变化：新的 OOS 评估；
- 缺少任一 hash：拒绝；
- 相同输入必须得到相同输出，否则报告标记完整性失败；
- 缓存只保存成功生成并通过完整性校验的报告。

---

## 8. OOS 预算与并发

### 8.1 OOS 窗口确定性生成

禁止人工或 LLM 手填 OOS 起止日期。V1 只允许注册规则，例如：

```yaml
oos_window_rule:
  type: latest_contiguous_trading_days
  length: 252
```

或：

```yaml
oos_window_rule:
  type: fixed_ratio_split
  train_ratio: 0.7
  test_ratio: 0.3
```

规则必须根据冻结的交易日历和数据可用区间确定性生成 `oos_window_start/end`。相同输入必须生成相同窗口。

### 8.2 计数规则

- IS 回测不限次数，不扣预算；
- 每个 theme 最多 3 次新的 OOS 报告；
- 预算在成功生成新的 OOS 报告时计数；
- 提交任务本身不扣预算；
- 缓存命中不扣预算；
- strategy、data 或 Gate hash 任一变化都算新评估；
- 第 3 次成功后状态置 `oos_budget_exhausted`；
- 已耗尽的 theme 不得继续生成新的 OOS 报告。
- 每次新评估依次写入 `oos_draw_index = 1, 2, 3`；
- 同一 OOS window 的第 2、3 次评估视为多重比较，不能与第一次直接通过等价展示。

### 8.3 多重比较修正

Gate 必须使用预注册并进入 `gate_criteria_hash` 的收紧表：

```text
draw 1 → baseline thresholds
draw 2 → stricter thresholds
draw 3 → strictest thresholds
```

具体数值由系统配置和测试固定，不由负责人、LLM 或运行时请求修改。

第 2、3 次报告和 UI 必须显示：

- 这是同一 OOS 窗口下第几次评估；
- Gate 已按多重比较规则收紧；
- 统计含金量弱于第一次直接通过；
- 不得把第 3 次通过展示成与第 1 次通过同等强度。

### 8.4 原子预留

为防止并发请求同时越过上限：

1. Worker 开始执行前按三元组查询缓存；
2. 缓存未命中时，在事务中预留一个 budget slot；
3. 同一三元组只能存在一个进行中预留；
4. 报告成功且完整性校验通过后，预留转换为已消耗计数；
5. 执行失败或报告未生成时释放预留，不扣预算；
6. 第 3 个 slot 被预留时，其他新三元组请求必须等待或失败，不能形成第 4 次评估。

SQLite 实现必须满足：

- slot 的预留、消耗和释放在单写事务内完成；
- ledger 的主题预算行是唯一争用点；
- 禁止在应用层执行“先读计数、再写计数”；
- 唯一约束负责阻止同一三元组重复预留。

### 8.5 重新立项

预算耗尽后，继续研究必须：

- 人工重新立项；
- 创建新 `theme_id`；
- 创建新 `hypothesis_source_snapshot`；
- 创建新 `ResearchProtocolSnapshot`；
- 更换 OOS 区间或数据快照；
- 保留旧 theme 的全部策略、报告和 Gate 结果。

通过唯一索引禁止新 theme 复用相同：

```text
(oos_window_start, oos_window_end, data_snapshot_hash)
```

---

## 9. Point-in-time Universe 与数据边界

### 9.1 历史 universe

每个交易日的可交易 universe 只能由当日已经可得的信息构建：

- 当时有效的行业成分；
- 当时有效的产业链标签；
- 当时已经上市的股票；
- 当时尚未退市的股票；
- 历史上后来退市的股票仍必须出现在其有效期间；
- 当时已知的 ST 和交易状态。

`snapshot_date` 晚于 `backtest_start_date` 的过滤条件不得影响历史 universe。

禁止使用：

- 当前板块成分回填历史；
- 当前 confirmed candidate；
- 当前 Evidence 结论；
- 当前本地标签；
- 使用未来财务数据的筛选；
- 已知最终存活结果的 symbol 清单。

### 9.2 财务数据

财务数据按 `ann_date` 进入时间游标，不按报告期 `end_date`。

在某交易日 T：

```text
usable_financial_records = records where ann_date <= T
```

未知 `ann_date` 的记录不能用于历史信号或 universe 过滤。

### 9.3 标准化与排名

任何标准化、排名、分位数和相对强弱只能使用截至 T 日的可见横截面或滚动窗口。

禁止：

- 全样本均值和标准差；
- 全区间分位数；
- 用未来成分计算过去排名；
- 先计算完整结果再切 IS/OOS。

### 9.4 退市和长期无法交易的清算

`include_delisted = true` 不能等同于“退市前按最后收盘价顺利卖出”。

V1 必须使用冻结的确定性规则：

```yaml
delisting_liquidation_policy:
  type: actual_tradable_exit_if_available
  fallback: last_tradable_price_with_penalty
  penalty_pct: system_default
```

执行顺序：

1. 若退市前存在真实可交易日，按当日成交约束尝试退出；
2. 若长期停牌或没有可执行退出日，按最后可交易价格施加系统惩罚；
3. 无法确定价格时标记 `insufficient`，不得假设零损失或干净退出；
4. 惩罚比例属于系统 baseline，不允许运行时调低。

报告必须展示：

- 退市、长停和无法成交标的；
- 实际或模拟退出日期；
- 是否使用惩罚价格；
- 惩罚比例；
- 无法退出导致的损失估计；
- 该处理对总收益和回撤的影响。

---

## 10. 事件驱动回测

### 10.1 时间语义

- 信号只能读取截至 T 日收盘的数据；
- T 日收盘后生成订单；
- 订单最早在 T+1 执行；
- T+1 的成交数据不能反向影响 T 日信号；
- pending order、成交、拒绝和延期都必须记录。

### 10.2 A 股成交约束

必须建模：

- 涨停买不进；
- 跌停卖不出；
- 停牌无法成交；
- T+1 可卖限制；
- 100 股整数手；
- 佣金；
- 印花税；
- 滑点；
- 最低佣金和其他已启用费用；
- 流动性不足导致拒绝或降级。

成本不能默认为零。未配置完整成本模型时，正式 OOS 评估必须拒绝。

### 10.3 价格调整口径

报告必须固定并记录：

- raw / qfq / hfq；
- 调整因子来源；
- 计算时点；
- 数据快照版本。

不允许在同一回测内因后来发生的除权事件重写已冻结数据。

### 10.4 成本压力测试

每次正式 OOS 在同一次执行、同一信号和成交轨迹上同时计算：

- `base_cost_result`
- `stress_cost_result`

V1 压力成本固定为：

- 滑点乘数 `1.5x`；
- 费用乘数 `1.5x`。

压力成本属于同一次 OOS 评估，不产生新的三元组，不额外扣预算。

Gate 规则：

- base 通过、stress 不通过：最高只能 `needs_review`；
- stress 通过：才有资格成为 `candidate_for_prototype_passed`；
- 不允许只展示 base 结果隐藏 stress 结果。

### 10.5 正式 OOS 对照组

每份正式 OOS 报告必须在相同数据快照、point-in-time universe、成本口径和 OOS 窗口下运行：

- 策略组：正式策略规则；
- 对照组 A：同一 universe 固定周期等权调仓；
- 对照组 B：冻结 benchmark，优先主题指数、行业指数或自定义主题等权组合；
- 对照组 C：去掉核心 entry 条件的弱化策略。

每个策略模板必须预先声明 `core_entry_rule_id`，对照组 C 只允许确定性删除该规则，不能由 LLM 临时解释“核心条件”。

对照组是固定报告组成部分，不是可选变体，也不能用于择优。

报告和 Gate 必须回答：

- 策略规则是否贡献了超额收益；
- 收益是否主要来自股票池或主题整体上涨；
- 去掉核心 entry 后结果是否基本不变；
- 扣除成本后 alpha 是否仍为正。

主题策略不得默认使用沪深 300。Benchmark 的确定性优先级为：

1. 可用且可信的主题指数；
2. 对应行业指数；
3. point-in-time 主题 universe 的冻结等权组合；
4. 上述均不可用时标记数据不足，不静默回退到宽基指数。

---

## 11. Canary 验收

Canary 是阶段四的第一个强制验收用例，不是可选测试。

Canary 策略必须故意尝试：

- 读取 T+1 或更晚数据生成 T 日信号；
- 用全样本统计量计算过去分位数；
- 用未来成分或未来财务公告构建历史 universe。

正确结果是：

- 配置校验阶段拒绝；或
- 时间游标在运行阶段抛出明确的 future-data-access 错误。

若 Canary 能正常完成回测，无论收益高低，都说明未来数据访问没有被可靠拦截，阶段四失败。

若 Canary 产生异常优秀结果而未被阻断，必须视为最高级别引擎故障。

阶段四退出条件：

- Canary 被确定性阻断；
- 阻断原因可审计；
- 合法策略仍能完成回测；
- 时间游标测试覆盖行情、财务、universe 和标准化；
- 在上述条件满足前不得进入 OOS 预算和 Gate 阶段。

---

## 12. 数据质量与报告降级

原则：不推断、不填充、不静默修复。

数据缺失必须产生：

- `quality_status = degraded | insufficient`
- 具体 gap；
- 受影响 symbol、日期和字段；
- 对指标和 Gate 的影响；
- `survivorship_bias_warning`。

正式 OOS Gate 的基本规则：

- `insufficient`：不能产生 `candidate_for_prototype_passed`；
- point-in-time membership 不完整：最多 `needs_review`，不得伪装为无偏历史验证；
- 使用 forward watchlist：只能 `prototype_sanity_check_only`，不得执行正式 OOS Gate；
- 未包含退市股或覆盖未知：报告必须醒目标记，Gate 按冻结政策处理；
- 缺失字段不能用零、均值、前值或模型推断静默填充。

---

## 13. Gate 与状态机

### 13.1 阈值冻结

`prototype_gate_thresholds` 与 `kill_criteria_snapshot` 同级，在第一次 OOS 评估前冻结。

所有 Gate 技术阈值由系统提供。负责人、LLM 和 API 都不能设置或修改。至少包括：

- 最低 OOS 有效交易数；
- 最低 completed round trips；
- 最低 OOS 日历跨度；
- 最低有交易月份数；
- 单一月份 PnL 贡献上限；
- 单一标的 PnL 贡献上限；
- 数据质量底线；
- 成本必须开启；
- 压力成本必须通过；
- `excess_return_vs_benchmark`；
- `excess_drawdown_vs_benchmark`；
- `cost_adjusted_alpha`；
- `beta_dominated_flag`；
- 对照组比较要求；
- future-data-access 必须为零；
- 正式报告不得使用 forward watchlist。

第 1、2、3 次 OOS 对应的收紧表必须在第一次 OOS 前一并冻结并进入 `gate_criteria_hash`。

Gate 不以绝对收益作为主要通过依据。绝对收益可以展示，但正式判决必须优先判断：

- 相对冻结 benchmark 的超额收益；
- 相对 benchmark 的回撤改善或恶化；
- 扣成本后的 alpha；
- 对照组 A/C 是否说明策略规则确实有增量；
- 收益是否被主题 beta 支配；
- 收益是否过度集中在单月或单一股票。

`beta_dominated_flag` 由确定性规则计算：若压力成本后的策略无法同时超过冻结 benchmark、等权对照组和弱化策略的系统最低增量要求，则标记为 true。该标记不由 LLM 解释或覆盖。

### 13.2 Gate 行为

Gate 只读取：

- 冻结协议；
- 不可变报告；
- 冻结阈值；
- 三个 hash。
- `oos_draw_index` 和冻结的收紧表；
- base/stress cost 结果；
- control comparison；
- 交易收益分布指标。

Gate 不写状态。

结果处理：

- `rejected`：报告挂到 draft，策略仍为 draft；
- `needs_review`：报告挂到 draft，进入 `human_review_async`；
- `candidate_for_prototype_passed`：报告挂到 draft，等待 `human_required_sync`；
- 不删除、不覆盖、不隐藏失败记录；
- UI 必须明确区分“候选通过”和“已经人工晋升”。

负责人看到的是系统翻译后的结论，例如：

- 样本外是否通过 baseline；
- 是否按第 k 次 OOS 收紧；
- 压力成本后是否仍跑赢对照组；
- 是否主要由主题 beta 驱动；
- 收益是否过度集中；
- 是否存在未来函数、幸存者偏差或数据质量阻断。

负责人只确认是否晋升，不判断统计细节，也不调整 Gate。

### 13.3 唯一晋升路径

```text
draft
  └─ StrategyPromotionReducer + human_required_sync
       └─ prototype_passed
```

不存在：

- Gate 自动晋升；
- 回测成功自动晋升；
- LLM 建议自动晋升；
- API 直接更新状态；
- 数据库通用 update 绕过 reducer。

### 13.4 C 模块最小执行闭环

B 模块只把真正的 `prototype_passed` 策略交给 C。C 的 V1 最小闭环为：

```text
prototype_passed
  → Signal Board
  → Action Plan
  → Human Execution Decision
  → Execution Log
  → Post-trade Review
```

`planned_action` 至少记录：

- `strategy_id`
- `signal_id`
- `symbol`
- `planned_date`
- `planned_action`
- `trigger_reason`
- `invalidation_before_open`
- `cannot_execute_conditions`

`execution_decision` 至少记录：

- `executed | skipped | partially_executed`
- `reason`
- `actual_price_optional`
- `notes`

C 模块不接券商、不自动下单；Signal Board 只展示 `strategy_core` 结果，不自建信号。

---

## 14. 错误处理

必须 fail loud：

- universe 类型错误：拒绝；
- 未注册 template 或 template hash 不匹配：拒绝；
- 请求自由指定 OOS start/end：拒绝；
- snapshot 未冻结：拒绝 OOS；
- snapshot 试图原地修改：拒绝；
- hash 缺失或不一致：拒绝；
- OOS budget exhausted：拒绝新三元组；
- OOS 窗口复用：拒绝重新立项；
- 数据快照不完整：降级或拒绝，并写清原因；
- LLM 生成非法 config：进入定向 repair；
- repair 耗尽：保留失败草稿和错误；
- 回测异常：不扣预算，不生成成功报告；
- 对照组、压力成本或分布指标缺失：不生成正式 Gate；
- Gate 输入报告 hash 不匹配：拒绝；
- 非 reducer 写 `prototype_passed`：拒绝并审计。

任何错误都不能触发：

- 自动 fallback 到静态 universe；
- 自动使用 confirmed candidate pool；
- 自动降低 Gate；
- 自动填补数据；
- 自动重置预算；
- 自动创建新 theme 绕过限制。

---

## 15. 测试策略

### 15.1 契约测试

- `BacktestUniverseSpec` 与 `ForwardWatchlistSnapshot` 不可互相赋值；
- 回测入口拒绝 forward watchlist；
- `ResearchProtocolSnapshot.editable` 永远为 false；
- 修改冻结字段必须创建新 snapshot；
- 三个 hash 缺一不可；
- Gate verdict 不包含 `prototype_passed`；
- 只有 reducer 能写 `prototype_passed`。

### 15.2 Hypothesis Builder 测试

- LLM 一次只选择一个已注册 template；
- 系统从模板确定性生成默认 config；
- LLM 尝试修改模板参数时被拒绝；
- 不生成多变体；
- Evidence 事件条件被拒绝；
- 非支持指标被拒绝；
- repair 接收明确错误并只修复失败字段；
- LLM 输出的 status、hash、预算和 Gate 字段被拒绝或忽略；
- 重跑 LLM 创建新 revision，不覆盖旧草稿；
- repair 最多两次，耗尽后保留失败草稿；
- 不要求负责人逐项确认技术参数。

### 15.3 Universe 与未来函数测试

- 历史成分按有效日期变化；
- 后来退市股票在历史有效期出现；
- 当前候选池不能进入历史回测；
- `ann_date > T` 的财务记录不可见；
- 全样本归一化被拒绝；
- 当前板块成分不能回填过去；
- Canary 是阶段四首个验收用例并被明确阻断。
- OOS start/end 不能由 API、用户或 LLM 自由输入；
- 相同窗口规则和数据生成相同 OOS window；
- 退市和长期停牌按冻结清算政策处理。

### 15.4 成交测试

- T 日信号不能在 T 日成交；
- T+1 开盘成交；
- 涨停买入失败；
- 跌停卖出延期或失败；
- 停牌不成交；
- T+1 可卖限制；
- 100 股整数手；
- 佣金、印花税、滑点和最低佣金；
- 调整价格口径在报告中冻结。
- base/stress 成本在同次 OOS 内生成且不额外扣预算；
- 对照组 A/B/C 使用相同数据、universe、窗口和成本口径。

### 15.5 Budget 与缓存测试

- IS 无限运行不扣预算；
- 新三元组成功报告扣一次；
- 相同三元组返回缓存不扣；
- 任一 hash 变化扣一次；
- 失败任务释放预留不扣；
- 并发请求不能产生第 4 次评估；
- 第 3 次后状态为 `oos_budget_exhausted`；
- draw index 严格为 1、2、3；
- 第 2、3 次使用冻结的更严格 Gate；
- 换 theme 但复用相同 OOS window 和 data hash 被拒绝；
- SQLite 并发预留使用单写事务，不允许应用层读改写；
- 旧报告不可删除或覆盖。

### 15.6 Gate 与状态测试

- Gate 三种 verdict 都不修改 strategy status；
- rejected 仍可见且保持 draft；
- needs_review 只进入异步队列；
- candidate 仍显示为候选而非已通过；
- reducer 在人工确认后晋升；
- 除 reducer 外任何写 `prototype_passed` 的路径失败；
- report、Gate 和 protocol 三个 hash 不一致时不能晋升。
- Gate 主要使用相对 benchmark 指标而非绝对收益；
- base 通过但 stress 失败时最高为 needs_review；
- beta dominated 或收益过度集中时不能候选通过；
- 缺少任一对照组时不能产生 candidate verdict；
- 负责人不能修改技术 Gate 阈值。

### 15.7 C 模块交接测试

- 非 `prototype_passed` 策略不能进入 Signal Board；
- Signal Board 不自行生成或修改信号；
- Action Plan 可记录人工执行、放弃和部分执行；
- Execution Log 不触发自动下单；
- 盘后复盘引用原 signal 和 strategy revision。

### 15.8 纵向测试

完整流程必须覆盖：

```text
A 模块输入
→ theme-level Hypothesis Builder
→ strategy template selection
→ 确定性校验
→ IS 回测
→ 确定性生成 OOS window
→ 冻结 ResearchProtocolSnapshot
→ OOS budget reservation
→ point-in-time 回测
→ base/stress cost + control comparison
→ immutable report
→ multiple-comparison + alpha Gate
→ human sync
→ reducer promotion
```

并证明：

- 全程没有 candidate-level 策略分叉；
- 全程没有 forward watchlist 进入历史 universe；
- LLM 未生成信号、盈亏、Gate 或状态；
- 失败报告没有被删除；
- C 模块只能读取真正的 `prototype_passed`。

---

## 16. 六阶段实施顺序

### 阶段一：契约、状态边界和不可变存储

实现：

- `StrategyTemplateDefinition`
- `StrategyDraft`
- `BacktestUniverseSpec`
- `ForwardWatchlistSnapshot`
- `ResearchProtocolSnapshot`
- `OOSEvaluationLedger`
- `ImmutableBacktestReport`
- 新版 `PrototypeGateResult`
- `StrategyPromotionReducer`

阶段退出条件：

- 两种 universe 在类型层面不可转换；
- snapshot 不可原地编辑；
- append-only 存储成立；
- `prototype_passed` 只有 reducer 能写；
- 旧 Gate 自动状态更新路径被测试锁死为不可用。

### 阶段二：Hypothesis Builder 与确定性校验

实现：

- Strategy Template Library 首批四个模板；
- LLM 只选择 template ID；
- 系统从模板生成并冻结 config；
- validator；
- 最多两次的定向 repair loop；
- 重跑生成新 revision，旧 draft 不覆盖；
- theme-level 单策略约束；
- 禁止 Evidence 事件规则；
- 禁止参数搜索和多变体。

阶段退出条件：

- 非技术负责人不需要确认参数；
- LLM 无法决定技术参数；
- 合法 config 可交给已通过 Canary qualification 的回测引擎；
- 非法 config 明确失败；
- LLM 无法写关键确定性字段。

### 阶段三：Point-in-time universe 与数据快照

实现：

- 历史成分；
- 退市股覆盖；
- `ann_date` 对齐；
- data snapshot hash；
- 注册的 OOS window rule 和确定性窗口生成器；
- 数据质量和降级；
- forward watchlist 拒绝路径。

阶段退出条件：

- 当前候选池不能进入历史回测；
- 当前成分不能回填历史；
- 数据缺口全部可见；
- snapshot 可确定性重放。
- API 无法自由填写 OOS start/end。

### 阶段四：事件驱动回测和防未来函数

实现：

- 严格时间游标；
- T 日信号、T+1 成交；
- A 股成交约束；
- rolling normalization；
- 调整价格快照；
- 退市和长期停牌清算规则；
- Canary。

阶段退出条件：

- 第一个验收用例是 Canary；
- Canary 的未来数据访问被确定性阻断；
- 合法策略能够正常运行；
- Canary 未通过前不得开始阶段五。

### 阶段五：OOS 预算、对照报告和冻结 Gate

实现：

- Research Protocol freeze；
- 三类共享 hash；
- OOS ledger；
- 原子预留；
- 三元组缓存；
- `oos_draw_index` 和 `shared_oos_window_id`；
- 多重比较收紧表；
- 防跨 theme 复用 OOS；
- 系统 baseline Gate 冻结；
- base/stress 成本结果；
- 对照组 A/B/C；
- 相对 benchmark 与 alpha Gate；
- beta dominated 和收益集中度检查。

阶段退出条件：

- 同输入 replay 不扣预算；
- 任一 hash 改变扣预算；
- 并发不能超 3 次；
- 换 theme 无法复用相同 OOS；
- 第 2、3 次 OOS 使用更严格 Gate；
- Gate 阈值不能由负责人、LLM 或 API 修改；
- 压力成本和三个对照组全部进入正式报告。

### 阶段六：Gate、人工晋升和纵向测试

实现：

- 只读 Gate；
- 三类 verdict；
- human review queue；
- human sync；
- reducer promotion；
- UI 状态语义；
- C 模块最小 Action Plan / Execution Log；
- A → B → C 纵向测试。

阶段退出条件：

- Gate 永不改状态；
- 失败策略和报告始终可见；
- 只有人工同步确认后可晋升；
- C 只接收真实 `prototype_passed`；
- 全量回归测试通过。

---

## 17. 与旧设计的冲突处理

本设计覆盖旧文档中以下规则：

- “用户逐项确认 Hypothesis Builder 技术参数”被删除；
- “LLM 自由生成一组默认数值”被替换为“LLM 只选择系统模板”；
- “负责人事前设置 Gate 技术阈值”被删除，改为系统 baseline；
- “人工或 LLM 指定 OOS 起止日期”被禁止；
- `static_list` / confirmed candidate symbols 不再是正式历史 universe；
- Gate 不再返回或写入 `prototype_passed`；
- `passed / failed` Gate 命名改为业务 verdict；
- Gate 配置不再作为可随意编辑的普通 `StrategyConfig` 字段；
- `strategy.status = backtesting / rejected` 不再由回测器或 Gate 自动写入；
- 幸存者偏差不允许仅靠一个普通 warning 后继续宣称正式历史有效；
- V1 不实现参数优化或多策略择优。
- 正式 Gate 不再主要依赖绝对收益，改为相对 benchmark、alpha、对照组和分布稳定性。

现有 `strategy_core` 的 DSL、信号、成交、盈亏和指标能力优先复用。只有与本设计硬边界冲突的部分才做外科式调整。

---

## 18. 成功标准

B 模块 V1 完成时，必须同时满足：

- 一个 theme 只产生一个策略家族和一套 OOS 预算；
- 负责人不需要确认任何技术参数；
- LLM 只能选择已注册策略模板；
- StrategyDraft 重跑生成新 revision，不能覆盖旧版本；
- 历史 universe 是 point-in-time 且包含退市股覆盖信息；
- 退市和长期无法交易有确定性清算政策；
- forward watchlist 无法进入正式历史回测；
- strategy、data、Gate 三个 hash 可重放；
- OOS 最多 3 次且不能换 theme 绕过；
- OOS window 只能由确定性注册规则生成；
- 第 2、3 次 OOS 使用冻结的多重比较收紧 Gate；
- T 日信号、T+1 成交；
- 财务数据按 `ann_date` 可见；
- 全样本归一化被禁止；
- A 股成交限制和成本被建模；
- 正式 OOS 同时生成 base/stress 成本结果；
- 正式 OOS 包含三个固定对照组；
- Gate 使用相对收益、alpha、beta 和收益集中度；
- Canary 能阻断未来数据访问；
- 数据缺失不填充并明确降级；
- 报告和 Gate 结果不可变；
- Gate 永不修改状态；
- 只有 `StrategyPromotionReducer` 能写 `prototype_passed`；
- 失败假设和报告永久保留；
- C 模块只读取人工确认后的策略；
- C 模块记录人工执行、放弃或部分执行，不自动下单。
