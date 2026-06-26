# Part 3: strategy_core + DSL + 回测引擎设计

## 3.1 Strategy DSL 设计（最小集）

**定位**：第一版只支持日线 EOD 策略，技术指标 + 市场状态，不支持基本面、事件、盘中策略。

**完整 DSL Schema 示例**：

```yaml
strategy_name: "机器人减速器突破策略"
version: "v1"
status: draft  # draft / backtesting / rejected / prototype_passed / execution_validating

# 假设来源追踪
hypothesis_source_snapshot:
  source_type: serenity
  source_run_id: "serenity_run_20260620_001"
  evidence_pack_ids: ["evidence_000000_20260620"]
  generated_at: "2026-06-20 14:30:00"
  data_range_used_for_generation:
    start: "2024-01-01"
    end: "2026-05-31"
  llm_model: "claude-sonnet-4"
  prompt_version: "v1.0"

# 股票池定义
universe:
  type: sector_plus_filters  # static_list / sector_plus_filters / custom_list
  sector: "机器人"  # 申万行业 / 概念板块
  chain_layer: "减速器"  # 可选，用于标注
  filters:
    not_st: true
    not_delisted: true
    min_liquidity_amount: 50000000  # 日均成交额 >= 5000万（用 amount，不用 volume）
    min_listed_days: 252  # 上市满一年
    data_quality: ok  # ok / degraded
  # 注意：停牌不在此过滤，停牌作为每日交易状态过滤

# 入场条件（技术指标 + 市场状态）
entry_conditions:
  logic: AND  # AND / OR
  rules:
    - type: breakthrough
      field: close
      benchmark: high_60d
      operator: ">="
    - type: volume_surge
      field: volume
      benchmark: ma_volume_20d
      multiplier: 1.5
      operator: ">="
    - type: relative_strength
      field: sector_relative_strength_rank
      percentile: 10
      operator: "<="
    - type: ma_condition
      field: close
      ma_period: 20
      operator: ">"
  market_state_filter:
    allowed_states: [green, yellow]  # red / yellow / green
    block_on_red: true

# 出场条件
exit_conditions:
  logic: OR  # 任一条件满足即出场
  rules:
    - type: time_exit
      holding_days: 10
    - type: ma_breakdown
      field: close
      ma_period: 20
      operator: "<"
    - type: stop_loss
      loss_pct: -8.0

# 风险过滤
risk_filters:
  max_position_per_stock: 0.2  # 单只股票最大仓位 20%
  max_total_position: 0.8  # 总仓位上限 80%
  restrict_limit_up_buy: true  # 涨停不买入
  restrict_limit_down_sell: true  # 跌停不卖出
  restrict_suspended: true  # 停牌不成交（每日交易状态过滤，不是股票池永久过滤）
  min_liquidity_for_trade: 10000000  # 单笔成交最小流动性（成交额 amount）

# 调仓频率
rebalance:
  frequency: daily  # daily / weekly / monthly
  check_time: close  # T 日收盘后检查信号

# 成交模型（A 股约束）
fill_model:
  signal_to_execution: T+1  # T 日收盘后信号，T+1 执行
  execution_price: open  # open / vwap / conservative
  commission: 0.0003  # 佣金 0.03%
  stamp_tax: 0.001  # 印花税 0.1%（卖出）
  slippage: 0.002  # 滑点 0.2%
  lot_size: 100  # 100 股整数手
  lot_rounding: floor  # floor（向下取整到 100 股整数手）
  handling:
    limit_up_buy: skip  # 涨停买不进：skip / defer_next_day
    limit_down_sell: defer_next_day  # 跌停卖不出：顺延
    suspended: skip  # 停牌不成交

# 回测配置
backtest_config:
  initial_capital: 1000000  # 初始资金 100 万
  start_date: "2024-01-01"
  end_date: "2026-05-31"
  sample_split:
    in_sample_end: "2025-12-31"
    out_of_sample_start: "2026-01-01"
  benchmark:
    type: index  # index / sector / custom_universe
    code: "000905.SH"
    name: "中证500"
  data_source: tushare_pro
  include_delisted: partial  # none / partial / full

# 审计记录
audit:
  created_at: "2026-06-20 15:00:00"
  created_by: user
  last_modified_at: "2026-06-20 15:00:00"
  config_hash: "abc123..."
```

**支持的指标类型（第一版）**：

- **突破类**：`breakthrough` - close >= high_Nd / low_Nd
- **成交量类**：`volume_surge` - volume >= ma_volume_Nd * multiplier
- **均线类**：`ma_condition` - close > / < ma_N
- **相对强度类**：`relative_strength` - 个股/板块相对基准排名
- **市场状态**：`market_regime` - red / yellow / green

**暂不支持（V1）**：
- 基本面条件（PE、PB、ROE、营收增速）
- 事件触发（公告关键词、财报公布）
- 复杂组合逻辑（嵌套 OR/AND）
- 动态仓位管理
- 止盈移动

---

## 3.2 strategy_core 架构

**定位**：策略配置的唯一执行引擎，回测/模拟盘/实盘共用同一份代码。

**模块划分**：

```
strategy_core/
  ├── dsl_parser.py          # DSL 解析器，YAML → 内部表示
  ├── universe_builder.py    # 股票池构建
  ├── signals.py             # 信号生成逻辑
  ├── screening.py           # 硬门槛过滤（ST、退市、流动性）
  ├── market_regime.py       # 市场状态判断（红黄绿灯）
  ├── fill_model.py          # A 股成交约束（涨跌停、停牌、T+1、滑点）
  ├── portfolio.py           # 持仓管理、资金分配
  ├── pnl.py                 # 盈亏计算
  ├── validator.py           # DSL 校验、防未来函数检查
  ├── action_plan.py         # 信号 → 执行计划转换（新增）
  └── executor.py            # 策略执行入口
```

**核心原则**：
- T 日只能访问 T 日及以前的数据
- T 日收盘后产生信号，T+1 执行
- 信号、成交、盈亏全部由代码规则完成，LLM 不介入
- 所有决策可审计、可重放

---

## 3.3 原型回测器设计

**定位**：事件循环架构 + A 股核心约束，第一版做 prototype 级别，但底层架构必须正确。

**回测引擎架构**：

```
backtest/
  ├── engine.py              # 事件循环主引擎
  ├── event.py               # 事件定义（BarEvent, SignalEvent, OrderEvent, FillEvent）
  ├── data_handler.py        # 数据迭代器（逐日推进，防未来函数）
  ├── universe.py            # 股票池管理（含退市股票）
  ├── execution_simulator.py # 成交模拟（涨跌停、停牌、流动性）
  ├── metrics.py             # 指标计算（收益、回撤、夏普、胜率、超额收益）
  ├── oos_split.py           # 样本内/样本外切分
  ├── report_generator.py    # 回测报告生成（6 块内容）
  └── audit_logger.py        # 审计日志
```

**事件循环流程（pending_orders 模式）**：

```python
pending_orders = []  # T 日生成的订单，等待 T+1 处理

while current_date <= end_date:
    # 1. 推进到下一个交易日
    current_date = next_trading_day(current_date)
    
    # 2. 获取当日数据（用于成交）
    execution_data = data_handler.get_data_on(current_date)
    
    # 3. 获取截至当日的历史数据（用于信号）
    history_data = data_handler.get_data_until(current_date)
    
    # 4. 处理上一日生成的订单（T+1 执行 T 日订单）
    if pending_orders:
        filled, rejected, deferred = execution_simulator.simulate_fills(
            pending_orders, 
            execution_data,  # 只用当日数据
            fill_model
        )
        portfolio.update(filled, current_date)
        audit_logger.log_fills(current_date, filled, rejected, deferred)
        pending_orders = deferred  # 保留跌停顺延订单
    
    # 5. 更新股票池（剔除退市、ST，停牌不在此剔除）
    universe = universe_builder.update(current_date, history_data)
    
    # 6. 计算信号（用历史数据）
    signals = strategy_core.generate_signals(
        current_date, 
        history_data, 
        universe, 
        portfolio
    )
    
    # 7. 生成订单（T 日生成，T+1 执行）
    new_orders = portfolio.generate_orders(signals, current_date)
    pending_orders.extend(new_orders)
    audit_logger.log_orders(current_date, new_orders)
```

**关键修正点**：
1. **区分 execution_data 和 history_data**：成交只能用当日数据，信号只能用截至当日收盘的数据
2. **pending_orders 模式**：T 日生成订单，T+1 处理上一日订单，避免结构性未来函数
3. **deferred 订单不丢弃**：跌停卖不出顺延到下一交易日

---

（续下页）

## 3.4 A 股成交约束实现

**订单结构**：

```python
class Order:
    signal_date: date  # 信号触发日期
    intended_execution_date: date  # 预期成交日期（T+1）
    actual_execution_date: date | None  # 实际成交日期（可能因顺延而晚于预期）
    symbol: str
    direction: str  # buy / sell
    quantity: int
    reason: str  # 触发原因
    strategy_version: str
```

**成交模拟逻辑**：

```python
def simulate_fill(order, market_data, fill_model):
    """
    模拟 A 股成交，受约束：
    1. T+1
    2. 涨停买不进
    3. 跌停卖不出
    4. 停牌不成交（每日交易状态过滤）
    5. 流动性不足不成交或降级（用成交额 amount）
    6. 100 股整数手（floor 向下取整）
    7. 佣金、印花税、滑点
    """
    
    # 1. 检查停牌（每日交易状态过滤，不是股票池永久过滤）
    if market_data.is_suspended(order.symbol, order.date):
        return Fill(status='rejected', reason='suspended')
    
    # 2. 检查涨跌停
    if order.direction == 'buy' and market_data.is_limit_up(order.symbol, order.date):
        if fill_model.limit_up_buy == 'skip':
            return Fill(status='rejected', reason='limit_up')
        elif fill_model.limit_up_buy == 'defer_next_day':
            return Fill(status='deferred', next_attempt_date=next_trading_day(order.date))
    
    if order.direction == 'sell' and market_data.is_limit_down(order.symbol, order.date):
        return Fill(status='deferred', next_attempt_date=next_trading_day(order.date))
    
    # 3. 检查流动性（用成交额 amount，不用 volume）
    if market_data.get_amount(order.symbol, order.date) < fill_model.min_liquidity_for_trade:
        return Fill(status='rejected', reason='insufficient_liquidity')
    
    # 4. 计算成交价
    if fill_model.execution_price == 'open':
        price = market_data.get_open(order.symbol, order.date)
    elif fill_model.execution_price == 'vwap':
        price = market_data.get_vwap(order.symbol, order.date)
    
    # 5. 加滑点
    if order.direction == 'buy':
        price *= (1 + fill_model.slippage)
    else:
        price *= (1 - fill_model.slippage)
    
    # 6. 整数手（floor 向下取整到 100 股，不用 round）
    quantity = int(order.quantity // fill_model.lot_size) * fill_model.lot_size
    if quantity == 0:
        return Fill(status='rejected', reason='quantity_too_small')
    
    # 7. 计算成本（拆成 gross_amount / commission / stamp_tax / net_cash_delta）
    gross_amount = price * quantity  # 成交总额
    commission = gross_amount * fill_model.commission
    stamp_tax = gross_amount * fill_model.stamp_tax if order.direction == 'sell' else 0
    
    if order.direction == 'buy':
        net_cash_delta = -(gross_amount + commission + stamp_tax)  # 买入：现金流出
    else:
        net_cash_delta = gross_amount - commission - stamp_tax  # 卖出：现金流入
    
    return Fill(
        status='filled',
        symbol=order.symbol,
        direction=order.direction,
        quantity=quantity,
        price=price,
        gross_amount=gross_amount,
        commission=commission,
        stamp_tax=stamp_tax,
        net_cash_delta=net_cash_delta,
        fill_date=order.date
    )
```

---

## 3.5 回测报告设计（7 块内容）

### 报告概览

- 策略名称、版本、backtest_level（**prototype_with_constraints**）
- 股票池、回测区间、样本内外区间
- 初始资金、成本假设、滑点假设
- 基准指数：沪深300 / 中证500 / 行业指数
- **Admission Gate 结果**：prototype_passed / rejected / needs_review

**策略状态机**：
- 回测报告只提供原始结论（`result_label: ready_for_next_stage` 作为展示 label）
- 策略状态由 **Admission Gate** 决定（`strategy_status_next: prototype_passed`）
- Signal Board 只读取 `strategy.status == prototype_passed` 的策略

### 基础指标

- 总收益率、年化收益、最大回撤、夏普比率
- **基准收益率（benchmark_return）**
- **超额收益（excess_return = 策略收益 - 基准收益）**
- 交易笔数、胜率、平均盈亏比、平均持有天数
- 成本前收益、成本后收益

### 样本内外对比

- In-sample 指标 vs Out-of-sample 指标
- 包含 benchmark_return 和 excess_return 对比
- OOS 状态：oos_ok / oos_degraded / oos_insufficient_trades / oos_failed

### 交易明细

- 每笔交易：股票、入场日期、出场日期、收益率
- 是否受涨停/跌停/停牌影响
- 出场原因：止损 / 持有到期 / 信号失效

### 成交约束统计

- 触发信号数、成功成交数、未成交数
- 涨停买不进次数、跌停卖不出次数
- 停牌无法成交次数、流动性不足过滤次数

### 数据质量报告

```yaml
data_quality:
  source: tushare_pro
  date_range: 2024-01-01 to 2026-05-31
  universe_count: 20
  degraded_stocks:
    - symbol: 000001.SZ
      issues: [缺失 5 个交易日数据]
  missing_fields: []
  quality_status: ok

survivorship_bias_warning:
  include_delisted: partial  # none / partial / full
  coverage_note: "当前退市股票覆盖不完整，本次回测存在幸存者偏差风险"
  delisted_count_in_universe: 2
  total_universe_count: 20
```

### 失败原因分析（规则化标签）

- `negative_expectancy`：平均单笔收益 <= 0
- `cost_killed`：成本前盈利、成本后亏损
- `insufficient_trades`：交易笔数不足
- `oos_failed`：样本外明显失效
- `drawdown_too_large`：最大回撤超阈值
- `execution_blocked`：大量信号因约束无法成交
- `data_degraded`：数据质量不足
- `no_excess_return`：相对基准无超额收益

### Admission Gate（策略准入检查）

**定位**：回测完成后自动运行，检查策略是否满足准入门槛，决定策略状态更新为 `prototype_passed` / `rejected` / `needs_review`。

**流程**：

```
Backtest Engine
  ↓
Backtest Report（原始结论 + 指标）
  ↓
Admission Gate（门槛检查）
  ↓
strategy_status 更新
  ↓
Signal Board 只读取 prototype_passed 策略
```

**触发时机**：
- 每次回测完成后自动运行
- 门槛配置在 `config/admission_gate.yaml`
- 检查逻辑完全由代码规则完成，LLM 不参与
- Admission Gate 的输入只能来自：回测结果、数据质量报告、成交约束统计、样本外指标、benchmark 对比

**配置样例**：

```yaml
admission_gate:
  enabled: true
  
  # 样本外最低交易笔数
  min_oos_trades: 20
  
  # 样本外最低超额收益
  min_oos_excess_return: 0.0
  
  # 最大回撤上限
  max_drawdown_limit: 0.25
  
  # 最低盈亏比
  min_profit_factor: 1.1
  
  # 成本敏感性测试
  cost_sensitivity:
    enabled: true
    slippage_multiplier: 2.0  # 滑点扩大 2 倍
    require_positive_after_stress: true
  
  # 成交约束统计
  execution_constraints:
    max_execution_block_ratio: 0.3  # 最多 30% 信号被约束阻止
    fail_if_limit_or_suspension_blocks_too_many: true
  
  # 数据质量要求
  data_quality:
    allowed_status:
      - ok
      - degraded
    fail_on_insufficient: true
  
  # 幸存者偏差策略
  survivorship_bias_policy:
    mode: warn_only  # strict / warn_only
    require_include_delisted: true
  
  # OOS 降级接受条件
  oos_degraded_acceptance:
    enabled: true
    max_return_drop_pct: 0.4  # OOS 收益相对 IS 下降不超过 40%
    require_oos_excess_return_positive: true
    require_drawdown_within_limit: true
  
  # 结果映射
  result_mapping:
    hard_fail: rejected
    soft_warning: prototype_passed
    manual_check_required: needs_review
```

**OOS 状态二次判断**：

保持 Part 3.5 的 OOS 基础枚举简单：
- `oos_ok`
- `oos_degraded`
- `oos_insufficient_trades`
- `oos_failed`

在 Admission Gate 层做二次判断：

```yaml
oos_gate_result:
  raw_oos_status: oos_degraded
  gate_decision: pass_with_warning
  display_label: oos_degraded_but_acceptable
  reason:
    - OOS 收益下降，但仍为正
    - OOS 超额收益仍大于 0
    - 最大回撤未超过门槛
    - 交易笔数满足最低要求
```

**幸存者偏差策略**：

- `strict`：退市股票覆盖不完整，Admission Gate 直接 fail，策略不能进入 prototype_passed
- `warn_only`（V1 默认）：退市股票覆盖不完整，可以 pass_with_warning，但报告必须显示 `survivorship_bias_warning`

**V1 默认用 `warn_only`**，原因：第一版很难保证退市股覆盖完整，如果用 `strict` 会被数据工程卡死。但必须在报告里显眼标注：

```yaml
survivorship_bias_warning:
  include_delisted: partial
  policy: warn_only
  impact: 本次回测存在幸存者偏差风险，结果只能作为原型验证，不能视为正式回测结论
```

**Admission Gate 输出**：

```yaml
admission_gate_result:
  result: prototype_passed  # rejected / needs_review / prototype_passed
  passed: true
  checks:
    - name: min_oos_trades
      status: pass
      value: 34
      threshold: 20
    
    - name: oos_excess_return
      status: pass
      value: 0.08
      threshold: "> 0"
    
    - name: max_drawdown
      status: pass
      value: 0.18
      threshold: "< 0.25"
    
    - name: profit_factor
      status: pass
      value: 1.3
      threshold: "> 1.1"
    
    - name: survivorship_bias
      status: warning
      value: partial
      policy: warn_only
      message: 退市股票覆盖不完整，本次结果存在幸存者偏差风险
    
    - name: cost_sensitivity
      status: pass
      message: 滑点扩大 2 倍后仍为正收益
    
    - name: execution_block_ratio
      status: pass
      value: 0.12
      threshold: "< 0.3"
    
    - name: data_quality
      status: pass
      value: ok
      allowed: [ok, degraded]
  
  blocking_issues: []
  warnings:
    - 退市股票覆盖不完整
  next_strategy_status: prototype_passed
```

**检查项说明**：

| 检查项 | 说明 | 不通过行为 |
|--------|------|------------|
| `min_oos_trades` | 样本外交易笔数 >= 20 | rejected |
| `min_oos_excess_return` | 样本外超额收益 > 0 | rejected |
| `max_drawdown_limit` | 最大回撤 < 25% | rejected |
| `min_profit_factor` | 盈亏比 > 1.1 | rejected |
| `cost_sensitivity` | 滑点扩大 2 倍后仍为正 | rejected |
| `execution_block_ratio` | 成交阻止率 < 30% | needs_review |
| `data_quality` | 数据质量 ok 或 degraded | rejected（insufficient）/ warning（degraded）|
| `survivorship_bias` | 退市股票覆盖检查 | warning（warn_only）/ rejected（strict）|
| `oos_degraded_acceptance` | OOS 降级但仍可接受 | pass_with_warning |

**硬边界**：
- LLM 不参与 Admission Gate 结果判断
- LLM 最多在报告页解释"为什么没过"
- 所有检查项必须基于回测输出的量化指标

---

## 3.6 Action Plan Generator（信号 → 执行计划转换）

**定位**：将 strategy_core 产生的策略信号转换为下一交易日可执行计划，完全由确定性规则完成，LLM 不参与。

### 模块架构

```
strategy_core/action_plan.py
```

**输入**：
- `signals`：strategy_core 生成的策略信号列表
- `fill_model`：成交模型配置
- `risk_filters`：风险过滤配置
- `market_regime`：当前市场状态
- `daily_status`：个股每日状态（停牌、涨跌停）
- `portfolio_state`：当前持仓状态（paper_portfolio / manual_input / unavailable）

**输出**：
- `trade_plans`：执行计划列表

### 对象关系

```
Signal（策略信号）
  ↓
TradePlan（执行计划）
  ↓
ExecutionLog（执行记录，V1 预留字段）
```

**关系约束**：
- V1：signal 和 trade_plan **1:1** 映射，不做分批
- V2+：预留 `parent_signal_id` 字段，支持一个 signal 拆成多个 child plans（分批买入/卖出）

### 数据结构

**Signal**：

```python
class Signal:
    signal_id: str
    strategy_id: str
    strategy_version: str
    symbol: str
    signal_date: date  # 信号触发日期（T 日）
    signal_type: str  # entry / exit / hold
    triggered_rules: List[str]  # 触发的规则列表
    generated_by: str = "strategy_core"
    audit_id: str
```

**TradePlan**：

```python
class TradePlan:
    trade_plan_id: str
    signal_id: str
    
    # 执行时间
    planned_trade_date: date  # T+1
    planned_action: str  # plan_buy / plan_sell / hold / no_action
    execution_window: str  # open_next_day / close_next_day / conservative
    
    # 仓位计划
    position_plan: PositionPlan
    
    # 执行前检查条件
    invalid_if: List[InvalidCondition]
    
    # 失败处理
    fallback_action: str  # cancel / defer_next_day / manual_review
    next_check_date: date | None  # 如果顺延/人工复核，下一次检查日期
    post_trade_review_date: date | None  # 如果执行成功，未来复盘日期
    
    # 审计
    generated_by: str = "action_plan_generator"
    audit_id: str
```

**PositionPlan**：

```python
class PositionPlan:
    max_position_pct: float  # 来自策略配置 risk_filters.max_position_per_stock
    current_position_pct: float  # 来自当前持仓
    planned_position_pct: float  # 本次计划执行后的目标仓位
    available_position_pct: float  # 本次最多还能增加的仓位
    portfolio_source: str  # paper_portfolio / manual_input / unavailable
```

**InvalidCondition**（结构化检查条件）：

```python
class InvalidCondition:
    type: str  # market_state / stock_status / price_limit / liquidity
    scope: str  # market / stock
    rule: str  # 条件描述（例如：market_regime == red）
    
# 示例
invalid_if = [
    InvalidCondition(
        type="market_state",
        scope="market",
        rule="market_regime == red"
    ),
    InvalidCondition(
        type="stock_status",
        scope="stock",
        rule="is_suspended == true"
    ),
    InvalidCondition(
        type="price_limit",
        scope="stock",
        rule="is_limit_up == true and planned_action == plan_buy"
    ),
    InvalidCondition(
        type="liquidity",
        scope="stock",
        rule="daily_amount < min_daily_amount_for_trade"
    )
]
```

### 执行窗口定义

**V1 只保留三个枚举，定义为"人工执行参考窗口"，不是系统自动下单时间**：

```python
ExecutionWindow:
    open_next_day:
        meaning: 下一交易日开盘后人工检查并执行
        price_model_in_backtest: next_day_open_with_slippage
    
    close_next_day:
        meaning: 下一交易日尾盘人工检查并执行
        price_model_in_backtest: next_day_close_or_conservative_close
        note: V1 可先不启用，只预留
    
    conservative:
        meaning: 使用更保守的成交假设，不绑定具体时间段
        price_model_in_backtest:
            buy: next_day_high_or_open_plus_slippage
            sell: next_day_low_or_open_minus_slippage
```

**V1 默认只启用**：`execution_window: open_next_day`

### 转换逻辑

```python
def generate_trade_plan(
    signal: Signal,
    fill_model: FillModel,
    risk_filters: RiskFilters,
    market_regime: str,
    daily_status: Dict[str, DailyStatus],
    portfolio_state: PortfolioState
) -> TradePlan:
    """
    Signal → TradePlan 转换
    
    硬边界：
    - LLM 不生成 trade_plan
    - LLM 不修改 trade_plan
    - 完全由确定性规则生成
    """
    
    # 1. signal_type → planned_action 映射
    if signal.signal_type == "entry":
        planned_action = "plan_buy"
    elif signal.signal_type == "exit":
        planned_action = "plan_sell"
    elif signal.signal_type == "hold":
        planned_action = "hold"
    else:
        planned_action = "no_action"
    
    # 2. 读取策略 risk_filters.max_position_per_stock
    max_position_pct = risk_filters.max_position_per_stock
    
    # 3. 计算 position_plan
    current_position_pct = portfolio_state.get_position_pct(signal.symbol)
    
    if planned_action == "plan_buy":
        planned_position_pct = max_position_pct
        available_position_pct = max_position_pct - current_position_pct
    elif planned_action == "plan_sell":
        planned_position_pct = 0.0
        available_position_pct = 0.0
    else:
        planned_position_pct = current_position_pct
        available_position_pct = 0.0
    
    position_plan = PositionPlan(
        max_position_pct=max_position_pct,
        current_position_pct=current_position_pct,
        planned_position_pct=planned_position_pct,
        available_position_pct=available_position_pct,
        portfolio_source=portfolio_state.source
    )
    
    # 4. 生成 invalid_if 检查条件
    invalid_if = []
    
    # 市场状态检查
    if risk_filters.block_on_red:
        invalid_if.append(InvalidCondition(
            type="market_state",
            scope="market",
            rule="market_regime == red"
        ))
    
    # 停牌检查
    if risk_filters.restrict_suspended:
        invalid_if.append(InvalidCondition(
            type="stock_status",
            scope="stock",
            rule="is_suspended == true"
        ))
    
    # 涨跌停检查
    if planned_action == "plan_buy" and risk_filters.restrict_limit_up_buy:
        invalid_if.append(InvalidCondition(
            type="price_limit",
            scope="stock",
            rule="is_limit_up == true and planned_action == plan_buy"
        ))
    
    if planned_action == "plan_sell" and risk_filters.restrict_limit_down_sell:
        invalid_if.append(InvalidCondition(
            type="price_limit",
            scope="stock",
            rule="is_limit_down == true and planned_action == plan_sell"
        ))
    
    # 流动性检查
    if risk_filters.min_liquidity_for_trade:
        invalid_if.append(InvalidCondition(
            type="liquidity",
            scope="stock",
            rule=f"daily_amount < {risk_filters.min_liquidity_for_trade}"
        ))
    
    # 5. 配置 fallback_action
    if planned_action == "plan_buy":
        # 涨停买不进：取消
        fallback_action = "cancel"
    elif planned_action == "plan_sell":
        # 跌停卖不出：顺延
        fallback_action = "defer_next_day"
    else:
        fallback_action = "cancel"
    
    # 6. 计算 next_check_date
    planned_trade_date = next_trading_day(signal.signal_date)
    
    if fallback_action == "defer_next_day":
        next_check_date = next_trading_day(planned_trade_date)
    elif fallback_action == "manual_review":
        next_check_date = planned_trade_date
    else:
        next_check_date = None
    
    # 7. 计算 post_trade_review_date（如果执行成功）
    # V1 简化：持有期结束日或成交后第 1 个交易日
    if planned_action in ["plan_buy", "plan_sell"]:
        post_trade_review_date = next_trading_day(planned_trade_date)
    else:
        post_trade_review_date = None
    
    return TradePlan(
        trade_plan_id=generate_id(),
        signal_id=signal.signal_id,
        planned_trade_date=planned_trade_date,
        planned_action=planned_action,
        execution_window="open_next_day",  # V1 默认
        position_plan=position_plan,
        invalid_if=invalid_if,
        fallback_action=fallback_action,
        next_check_date=next_check_date,
        post_trade_review_date=post_trade_review_date,
        generated_by="action_plan_generator",
        audit_id=generate_audit_id()
    )
```

### ExecutionLog（V1 预留字段）

```python
class ExecutionLog:
    execution_log_id: str
    trade_plan_id: str
    
    # 用户实际执行情况
    user_actual_action: str  # executed / skipped / modified / not_recorded
    actual_price: float | None
    actual_quantity: int | None
    
    # 人工覆盖
    manual_override: bool
    override_reason: str | None
    
    # 偏差类型
    drift_type: str | None  # price_drift / quantity_drift / timing_drift / skip
    
    # 备注
    note: str | None
    
    # 审计
    recorded_at: datetime
    audit_id: str
```

**V1 不实现完整 ExecutionLog**，只预留字段，M4 实现。

---

完整 Part 3 内容已保存。Part 4（数据适配层 + Web 页面）和 Part 5（实现路径和里程碑）内容较多，建议单独查阅主文档。


