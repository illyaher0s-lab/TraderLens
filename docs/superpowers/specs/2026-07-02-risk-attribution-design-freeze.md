# Risk and Attribution Design Freeze (P0-3)

**Date:** 2026-07-02  
**Status:** DESIGN_FREEZE  
**Purpose:** 冻结风险防护和归因系统设计，补全 Section 10 审计中的缺失功能

---

## Executive Summary

TraderLens V1 需要补全 4 项风险防护功能和 1 项归因系统：

1. **大市极端熔断** (MarketRegimeGuard) — 拦截极端普跌/结构破位/流动性枯竭
2. **单票仓位上限** (PositionLimit) — 按资金池分档，小资金不强制分散，用户不选参数
3. **固定止损** (FixedStopLoss) — 日频固定止损，按板块验证冻结阈值
4. **数据状态独立维度** (DataState) — 数据状态和业务判断永远分开，不混 enum
5. **诚实归因** (HonestAttribution) — 复盘只记录事实类退出原因，不做价值判断

**核心原则：**
- 风控规则由系统验证冻结，不由 LLM 或用户决定
- 用户只提供资金池/试运行金额，不选技术参数
- 大市熔断只拦极端情况，不做择时预测
- 归因是诚实工具，不宣称防纪律、不保证盈利
- 全系统输出必须分成两个正交字段：业务判断 + 数据状态
- 回测成交口径必须按 A 股可执行假设建模，不能用理想收盘价成交

---

## 1. Market Regime Guard (大市极端熔断)

### 1.1 Design Principle

**目标：** 拦截极端市场状态，防止系统在市场崩溃时继续生成信号。

**不做：**
- ❌ 择时预测 (不预测涨跌)
- ❌ 牛熊判断 (不判断趋势方向)
- ❌ 情绪指标 (不依赖 VIX/恐慌指数)

**只拦：**
- ✅ 极端普跌 (大面积个股跌停/重挫)
- ✅ 结构破位 (基准指数短期暴跌)
- ✅ 流动性枯竭 (成交量异常萎缩)

### 1.2 MarketRegimeState Definition

```python
class MarketRegimeState(str, Enum):
    """Market regime state for extreme condition detection."""
    
    ok = "ok"
    # 市场正常，允许信号生成
    
    extreme_breadth_selloff = "extreme_breadth_selloff"
    # 极端普跌：N% 个股跌幅 > X%
    # 例：80% 个股单日跌幅 > 5%
    
    structural_breakdown = "structural_breakdown"
    # 结构破位：基准指数短期暴跌
    # 例：沪深300 单日跌幅 > 5% 或 5 日跌幅 > 10%
    
    liquidity_exhaustion = "liquidity_exhaustion"
    # 流动性枯竭：成交量异常萎缩
    # 例：沪深两市成交额 < 30 日均值 * 30%
```

### 1.2.1 Orthogonal Data State

市场状态和数据状态不是同一个维度，不能放进同一个 enum。

```python
class DataState(str, Enum):
    ok = "ok"
    insufficient = "insufficient"
    fault = "fault"

class MarketRegimeCheck(BaseModel):
    as_of_date: date
    regime_state: MarketRegimeState | None
    data_state: DataState
    check_metrics: dict
    user_visible_reason: str
```

**Rules:**
- `regime_state` 只表达市场判断：ok / extreme_breadth_selloff / structural_breakdown / liquidity_exhaustion
- `data_state` 只表达数据质量：ok / insufficient / fault
- 数据不足时，`regime_state = None`，不能伪装成市场极端
- 下游必须区分：市场极端是硬阻断；数据不足是保守降级并标记数据问题

### 1.3 Detection Rules (Candidate Thresholds)

**候选阈值（需验证冻结）：**

| Condition | Metric | Threshold (Candidate) | Data Source |
|-----------|--------|----------------------|-------------|
| **Extreme Breadth Selloff** | A 股跌幅 > 5% 的个股比例 | > 80% | Tushare daily |
| **Structural Breakdown (1d)** | 沪深300 单日跌幅 | > 5% | Tushare index_daily |
| **Structural Breakdown (5d)** | 沪深300 5 日累计跌幅 | > 10% | Tushare index_daily |
| **Liquidity Exhaustion** | 沪深两市总成交额 | < 30 日均值 * 30% | Tushare daily |

**验证要求：**
- 阈值必须由历史数据验证（例：2015 股灾、2020 三月暴跌）
- 不能过于宽松（频繁误拦）
- 不能过于严格（极端情况漏拦）

**冻结后：**
- 阈值进入配置文件（不可由用户修改）
- UI 不显示技术参数

### 1.4 Insertion Points

**Position 1: Action Plan Generation**

```
Signal Board → Action Plan Builder
  ↓
【Check MarketRegimeState】
  - If ok → Continue to Action Plan
  - If extreme_* → Downgrade recommendation_level to "do_not_execute"
  - If data_state != ok → Downgrade to "pause_observation" and record data issue
  ↓
Action Plan (with regime check result)
```

**Position 2: Daily Signal Generation**

```
Observation Pool → Daily Signal Generator
  ↓
【Check MarketRegimeState】
  - If ok → Continue to deterministic reducer
  - If extreme_* → Force signal_type = "risk" (regardless of position P&L)
  - If data_state != ok → Force data status, not regime status
  ↓
Daily Observation Signal (with regime override)
```

### 1.5 User-Facing Language

**UI 显示：**
- ✅ "市场状态异常，暂停信号生成"
- ✅ "极端行情阻断，建议观望"
- ✅ "市场数据不足，无法判断大盘状态"
- ❌ 不说 "structural_breakdown"
- ❌ 不说 "沪深300 跌幅超过 5%"

**Timeline 记录：**
```json
{
  "type": "market_regime_check",
  "regime_state": "structural_breakdown",
  "data_state": "ok",
  "check_date": "2024-03-15",
  "blocked_action": "action_plan_generation",
  "user_visible_reason": "市场状态异常，暂停信号生成"
}
```

---

## 2. Position Limit (单票仓位上限)

### 2.1 Design Principle

**V1 规则：资金分档，不使用全市场单一比例。**

**用户输入：**
- 资金池总额（例："我有 10 万元可以投资"）
- 或试运行金额（例："先拿 2 万试试"）

**系统计算：**
- 用户只输入 `capital_pool`
- 系统内部按资金池分档
- 输出给用户的是已计算好的金额，不显示百分比

**Small Tier:**
```python
condition: capital_pool < THRESHOLD_SMALL
purpose: 真实反馈验证，不做风险分散
max_open_positions: 1
single_stock_cap_amount: capital_pool  # 不强制分散，不等于鼓励满仓
```

**Normal Tier:**
```python
condition: capital_pool >= THRESHOLD_SMALL
max_open_positions: N
single_stock_cap_amount: capital_pool * CAP_RATIO
```

**待验证冻结参数：**
```python
THRESHOLD_SMALL: float  # 量级约 1-2 万，待验证冻结
N: int                  # 单一整数
CAP_RATIO: float        # 单一小数，不是区间
```

**用户不能选：**
- ❌ 仓位比例
- ❌ 风险等级
- ❌ 激进/保守模式
- ❌ `THRESHOLD_SMALL` / `N` / `CAP_RATIO`

### 2.2 Position Limit Enforcement

**检查位置：** Action Plan Builder

```python
class PositionLimitCheck(BaseModel):
    """Position limit check result."""
    
    status: Literal[
        "within_limit",
        "exceeds_limit",
        "capital_insufficient",
        "min_lot_exceeds_limit",
        "data_fault"
    ]
    
    capital_pool: float  # 用户资金池
    tier: Literal["small", "normal"]
    max_open_positions: int
    single_stock_cap_amount: float  # 单票上限，绝对金额
    planned_position_value: float  # 计划持仓金额
    min_lot_value: float  # 最低 100 股金额
    tier_thresholds_hash: str

    allowed_to_execute: bool
    downgrade_reason: str | None
```

### 2.3 Edge Cases

**Case 1: 资金不足（总资金 < 计划持仓）**

```python
if capital_pool < planned_position_value:
    return PositionLimitCheck(
        status="capital_insufficient",
        allowed_to_execute=False,
        downgrade_reason="资金不足，无法执行"
    )
```

**Case 2: 最低 100 股超过上限**

```python
if min_lot_value > single_stock_cap_amount:
    return PositionLimitCheck(
        status="min_lot_exceeds_limit",
        allowed_to_execute=False,
        downgrade_reason="最低买入金额超过单票限额，建议增加资金池或选择低价股"
    )
```

**Case 3: 在上限内**

```python
if planned_position_value <= single_stock_cap_amount:
    return PositionLimitCheck(
        status="within_limit",
        allowed_to_execute=True,
        downgrade_reason=None
    )
```

### 2.4 Insertion Point

```
Signal → Action Plan Builder
  ↓
Calculate planned position size
  ↓
【Check PositionLimit】
  - If within_limit → Continue
  - If exceeds_limit → Downgrade to "pause_observation"
  - If capital_insufficient → Downgrade to "do_not_execute"
  - If min_lot_exceeds_limit → Downgrade to "do_not_execute" + suggest lower-price stock
  ↓
Action Plan (with position limit result)
```

### 2.5 User-Facing Language

**UI 显示：**
- ✅ "资金约束：单票限额 5,000 元，计划买入 8,000 元，建议减仓或增加资金池"
- ✅ "最低买入金额超过单票限额，建议增加资金池或选择低价股"
- ✅ "小资金试运行：同时只观察 1 只"
- ❌ 不说 "仓位比例"
- ❌ 不说 "CAP_RATIO"
- ❌ 不说 "position_limit_check: exceeds_limit"

**Capital Context Storage:**
```python
class CapitalContext(BaseModel):
    user_id: str
    capital_pool: float  # 用户资金池
    tier: Literal["small", "normal"]
    max_open_positions: int
    single_stock_cap_amount: float  # 绝对金额
    fixed_stop_pct: float
    tier_thresholds_hash: str
    stop_criteria_hash: str
    created_at: datetime
    updated_at: datetime
```

---

## 3. Fixed Stop Loss (固定止损)

### 3.1 Current Implementation Status

**Status:** PARTIAL

`observation_pool.py` 已有固定阈值逻辑，但还没有完成板块区分、OOS 验证冻结、日频滞后口径和配置哈希。因此不能把当前代码视为最终冻结规则。

### 3.2 Candidate Thresholds for Validation

**候选阈值按板块区分：**

```python
main_board_candidates = [0.06, 0.08, 0.10]
growth_board_candidates = [0.10, 0.12, 0.15]
```

**原因：**
- 主板 / 中小板涨跌停通常为 ±10%，6% / 8% 可能被单日跌停击穿，验证时必须统计 `gap_through_rate`
- 创业板 / 科创板涨跌停通常为 ±20%，过窄止损磨损严重，候选整体上移

**验证要求：**
1. 使用与真实策略 alpha 验尸相同的 OOS 窗口
2. 成交假设必须使用 A 股可执行口径：
   - 止损触发日只产生信号，不假设当日收盘成交
   - 实际成交价使用次一交易日开盘价
   - 次日跌停或停牌不可成交时，订单顺延到下一可成交交易日
   - 买卖均扣佣金、印花税和滑点
3. 对每个候选 X 记录：
   - `single_trade_max_loss`
   - `stop_hit_rate`
   - `false_stop_rate`
   - `gap_through_rate`
   - `actual_stop_slippage_distribution`
   - `unfilled_stop_days`
   - `strategy_return_with_stop`
   - `strategy_return_without_stop`
4. 冻结标准不是收益最高，而是在真实成交假设下压低单笔最大亏损、控制误止损的前提下，选择对策略收益伤害最小的 X

**Validation Invalid If:**
- 用触发日收盘价当成交价
- 没有说明成交价取哪根 K 线的哪个字段
- 没有说明跌停 / 停牌时如何顺延
- 没有交回至少一笔跌停或停牌样例的完整执行轨迹

**冻结后：**
- 阈值进入配置文件
- 不可由用户修改
- 不可由 LLM 决定

### 3.3 Stop Loss Rule

**规则：**
```
止损价 = 买入价 * (1 - X%)
X% 由验证冻结，按板块选择候选集
```

**特性：**
- ✅ 固定价格（买入时确定）
- ✅ 不移动（不随股价上涨而调整）
- ✅ 不追踪（不是追踪止损）
- ✅ 日频触发，次日生成卖出信号
- ❌ 用户不能选 X
- ❌ 不是实时保护

**Daily Signal Trigger:**
```python
if daily_close <= entry_price * (1 - fixed_stop_pct):
    return DailySignalType.sell
```

**Trigger Basis:**
```python
trigger_basis = "daily_close"
is_realtime = False
```

分钟线当前为 `adapter_unsupported`，V1 不能宣称实时止损，也不能做移动止损。

### 3.4 Backtest Execution Model

固定止损验证必须使用真实成交模型，不允许用理想成交价。

```python
class StopExecutionAssumption(BaseModel):
    trigger_basis: Literal["daily_close"] = "daily_close"
    signal_date: date
    intended_execution_date: date  # next trading day
    execution_price_basis: Literal["next_trading_day_open"] = "next_trading_day_open"
    blocked_if_limit_down_or_suspended: bool = True
    carry_forward_until_executable: bool = True
    costs_included: bool = True
```

**Execution Rules:**
- 当日收盘触发止损后，只记录 `sell_signal`
- 次一交易日按 `open` 尝试卖出
- 如果次日停牌，订单顺延
- 如果次日跌停且按日线数据无法证明可成交，按保守口径视为不可成交并顺延
- 如果后续仍连续不可成交，继续顺延并记录 `unfilled_stop_days`
- 最终 P&L 使用真实可成交日价格，不使用触发日收盘价

**Evidence Required From Validation:**
- 每个候选 X 的真实成交假设下 `single_trade_max_loss`
- 每个候选 X 的 `actual_stop_slippage_distribution`
- 每个候选 X 的 `gap_through_rate` 和 `unfilled_stop_days`
- 一笔跌停 / 停牌样例交易的完整执行轨迹：触发日、次日 open、是否跌停 / 停牌、顺延天数、最终成交价

没有这些证据，固定止损验证作废。

### 3.5 User-Facing Language

**UI 显示：**
- ✅ "固定失效价已设置：11.28 元（-8%）"
- ✅ "止损为日频，次日生效，非实时保护"
- ✅ "止损触发：收盘价 11.20 元，已跌破失效价，次日生成离场信号"
- ❌ 不说 "止损阈值 -8%"
- ❌ 不说 "stop_loss_threshold"
- ❌ 不说 "实时保护"

---

## 4. Data State Independent Dimension (数据状态独立维度)

### 4.1 Problem Statement

**当前问题：** 信号类型曾经混淆两种含义：
1. 数据不足（MarketDataFault non-ok）
2. 风险条件（例：接近止损但未触发）

**解决方案：** 业务判断和数据状态永远分成两个字段。

### 4.2 Daily Observation Signal Contract

```python
class DailySignalType(str, Enum):
    """Daily observation signal type."""
    
    hold = "hold"
    # 数据足够，继续观察，无触发条件
    
    sell = "sell"
    # 卖出信号（止损/止盈/失效触发）
    
    risk = "risk"
    # 风险警告（接近止损但未触发，或其他风险条件）

    invalidated = "invalidated"
    # 主动平仓触发（外部失效条件）

class DataState(str, Enum):
    ok = "ok"
    insufficient = "insufficient"
    fault = "fault"

class DailyObservationSignal(BaseModel):
    signal_type: DailySignalType | None
    data_state: DataState
    user_visible_reason: str
    rule_trace: dict
```

### 4.3 Mapping Rules

| MarketDataFaultState | data_state | signal_type | User Message |
|----------------------|------------|-------------|--------------|
| `ok` | ok | hold / sell / risk / invalidated | 正常信号 |
| `partial` | insufficient | None | 数据部分缺失，建议暂停操作 |
| `stale_forward` | insufficient | None | 数据更新延迟，建议暂停操作 |
| `stale_backward` | insufficient | None | 历史数据不足，建议暂停操作 |
| `unavailable` | fault | None | 数据不可用，无法生成信号 |
| `source_error` | fault | None | 数据源错误，无法生成信号 |
| `adapter_unsupported` | fault | None | 数据接口不支持，无法生成信号 |

### 4.4 Deterministic Reducer Update

**Priority (updated):**

```python
# Priority 1: MarketDataFault non-ok → downgrade
if market_data_state in [MarketDataFaultState.partial, 
                         MarketDataFaultState.stale_forward, 
                         MarketDataFaultState.stale_backward]:
    return DailyObservationSignal(
        signal_type=None,
        data_state=DataState.insufficient,
        user_visible_reason="数据不足，建议暂停操作",
        rule_trace={"rule": "market_data_insufficient", "fault_state": market_data_state, "hit": True}
    )

if market_data_state in [MarketDataFaultState.unavailable,
                         MarketDataFaultState.source_error,
                         MarketDataFaultState.adapter_unsupported]:
    return DailyObservationSignal(
        signal_type=None,
        data_state=DataState.fault,
        user_visible_reason="数据源错误，无法生成信号",
        rule_trace={"rule": "market_data_fault", "fault_state": market_data_state, "hit": True}
    )

# Priority 2: Invalidation triggers
if external_triggers:
    return (DailySignalType.invalidated, external_triggers, {...})

# Priority 3: Stop loss
if pnl_pct <= stop_loss_threshold:
    return (DailySignalType.sell, [], {"rule": "fixed_stop", ...})

# Priority 4: Profit target (future)
# ...

# Priority 5: Risk warning (future)
# if approaching_stop_loss:
#     return (DailySignalType.risk, [], {"rule": "risk_threshold", ...})

# Priority 6: Default hold
return (DailySignalType.hold, [], {"rule": "default_hold"})
```

### 4.5 User-Facing Language

**UI 显示：**
- ✅ "数据不足，建议暂停操作"
- ✅ "数据源错误，无法生成信号"
- ❌ 不说 "MarketDataFaultState.partial"
- ❌ 不把数据状态显示成买卖信号

---

## 5. Honest Attribution (诚实归因)

### 5.1 Design Principle

**目标：** 复盘时诚实区分退出原因，提供归因工具。

**不宣称：**
- ❌ 防止纪律偏离
- ❌ 保证盈利
- ❌ 改善交易习惯

**只提供：**
- ✅ 退出原因分类
- ✅ 计划偏离事实记录
- ✅ 数据不足标记
- ❌ 不评价用户卖早 / 卖晚 / 忽略信号
- ❌ 不给用户操作打纪律分

### 5.2 ExitAttribution Enum

```python
class ExitAttribution(str, Enum):
    """Exit reason attribution for discipline review."""
    
    fixed_stop_triggered = "fixed_stop_triggered"
    # 固定止损触发（daily signal = sell, rule_trace = "fixed_stop"）
    
    reached_planned_take_profit = "reached_planned_take_profit"
    # 计划止盈触发（rule_trace = "profit_target"）
    
    reached_planned_exit = "reached_planned_exit"
    # 计划退出（invalidation trigger 触发）
    
    user_sold_while_signal_hold = "user_sold_while_signal_hold"
    # 用户在系统信号为 hold 时选择卖出。中性事实，不判断早晚对错。
    
    data_insufficient = "data_insufficient"
    # 数据不足时退出（signal = insufficient_data）
    
    data_fault = "data_fault"
    # 数据故障时退出（signal = data_fault）
    
    unclassified = "unclassified"
    # 无法分类（证据链不完整）
```

### 5.3 Attribution Detection Logic

**Detection rules:**

| Condition | Attribution |
|-----------|-------------|
| Daily signal = sell + rule_trace = "fixed_stop" | `fixed_stop_triggered` |
| Daily signal = sell + rule_trace = "profit_target" | `reached_planned_take_profit` |
| Daily signal = invalidated | `reached_planned_exit` |
| User sold while latest valid signal = hold | `user_sold_while_signal_hold` |
| Exit during insufficient_data period | `data_insufficient` |
| Exit during data_fault period | `data_fault` |
| Cannot determine from timeline | `unclassified` |

**Forbidden Attribution Values:**
- `early_exit`
- `late_exit`
- `ignored_signal`
- `manual_deviation`

这些词带价值判断。系统不接券商，也不知道用户真实决策过程，只能记录“用户在 hold 信号下卖出”等事实。

### 5.4 Implementation Status

**Current (from audit):**
- ✅ `fixed_stop_triggered` — detectable via rule_trace
- ⚠️ `reached_planned_take_profit` — defined but not active (code commented out)
- ✅ `reached_planned_exit` (invalidated) — detectable
- ✅ `data_insufficient` / `data_fault` — detectable via DailySignalType
- ✅ `user_sold_while_signal_hold` — detectable from latest valid signal

### 5.5 User-Facing Language

**UI 显示：**
- ✅ "退出原因：固定止损触发（-8%）"
- ✅ "退出原因：计划止盈达成（+15%）"
- ✅ "退出记录：卖出时系统信号为继续观察"
- ✅ "退出原因：数据不足期间退出"
- ❌ 不说 "ExitAttribution.fixed_stop"
- ❌ 不说 "early_exit / late_exit / ignored_signal"
- ❌ 不说 "你卖早了 / 卖晚了 / 忽略了信号"

**Discipline Review Output:**
```json
{
  "review_id": "rev_abc123",
  "position_id": "pos_xyz789",
  "exit_attribution": "fixed_stop_triggered",
  "exit_date": "2024-03-15",
  "pnl_pct": -0.082,
  "plan_adherence": {
    "followed_plan": true,
    "deviations": []
  },
  "attribution_evidence": {
    "daily_signal_date": "2024-03-15",
    "signal_type": "sell",
    "rule_trace": {"rule": "fixed_stop", "threshold": -0.08, "actual": -0.082}
  }
}
```

---

## 6. Capital Tier + Fixed Stop (Complete Design)

### 6.1 Capital Context Design

**User Input:**
```
用户只提供：capital_pool (资金池总额)
```

**System Internal Calculation:**
```python
class CapitalTier(str, Enum):
    small = "small"
    normal = "normal"

class CapitalContext(BaseModel):
    user_id: str
    capital_pool: float  # 用户输入
    
    # Tier assignment (system-determined)
    tier: CapitalTier
    
    # Tier-specific limits
    max_open_positions: int
    single_stock_cap_amount: float  # 绝对金额，不是百分比
    
    # Fixed stop
    fixed_stop_pct: float  # 由验证冻结
    
    # Configuration hash (审计痕迹)
    tier_thresholds_hash: str
    stop_criteria_hash: str
    
    created_at: datetime
    updated_at: datetime
```

### 6.2 Capital Tier Rules

**Small Tier:**
```python
condition: capital_pool < THRESHOLD_SMALL
purpose: 真实反馈验证，不做风险分散
max_open_positions: 1
single_stock_cap: capital_pool  # 不强制分散，不等于鼓励满仓
```

**Small Tier User Risk Disclosure:**
- 小资金档不是风控充分，而是如实承认无法有效分散
- UI 必须显示："小资金试运行：同时只观察 1 只"
- UI 必须显示："资金较小，无法有效分散，单票判断错误会直接影响资金曲线"
- 不做劝退，不做恐吓，不说“建议满仓”

**Normal Tier:**
```python
condition: capital_pool >= THRESHOLD_SMALL
max_open_positions: N  # 待冻结参数
single_stock_cap: capital_pool * CAP_RATIO  # 待冻结参数
```

**Thresholds to Freeze (via backtest/live validation):**
```python
THRESHOLD_SMALL: float  # 约 1-2 万，待定
N: int  # 单一整数，例如 5 或 10
CAP_RATIO: float  # 单一小数，例如 0.10 或 0.15，不是范围
```

**Red Lines:**
- ✅ `CAP_RATIO` 必须是一个数，不是范围（例：0.10，不是 0.10-0.15）
- ✅ 所有参数走 config（`strategy_template_library` 或独立配置文件）
- ✅ 参数变更必须留痕（config version + hash）
- ✅ 用户界面只显示算好的金额，不显示百分比
- ✅ 小资金档不是鼓励满仓，只是承认资金太小无法有效分散

### 6.3 Capital Context Contract

**Output:**
```json
{
  "capital_pool": 5000,
  "tier": "small",
  "max_open_positions": 1,
  "single_stock_cap_amount": 5000,
  "fixed_stop_pct": 0.08,
  "tier_thresholds_hash": "sha256:abc123...",
  "stop_criteria_hash": "sha256:def456..."
}
```

**UI Display:**
- ✅ "资金池：5,000 元"
- ✅ "小资金试运行：同时只观察 1 只"
- ✅ "单票限额：5,000 元"
- ❌ 不显示 "单票上限 100%"
- ❌ 不显示 "CAP_RATIO = 1.0"

**Normal Tier Example:**
```json
{
  "capital_pool": 50000,
  "tier": "normal",
  "max_open_positions": 5,
  "single_stock_cap_amount": 5000,
  "fixed_stop_pct": 0.08,
  "tier_thresholds_hash": "sha256:abc123...",
  "stop_criteria_hash": "sha256:def456..."
}
```

**UI Display:**
- ✅ "资金池：50,000 元"
- ✅ "同时观察上限：5 只"
- ✅ "单票限额：5,000 元"

### 6.4 Fixed Stop Design (Complete)

**Trigger Basis:**
```python
trigger_basis: Literal["daily_close"] = "daily_close"
is_realtime: bool = False
```

**Trigger Logic:**
```
当日收盘价 <= 买入价 * (1 - X)
  → 次日生成 DailySignalType.sell
```

**Not Real-Time:**
- 分钟线 `adapter_unsupported`
- 不能假装实时止损
- UI 和设计文档必须明确：**止损为日频，滞后一日，不是实时保护**

### 6.5 Fixed Stop Candidates (by Board Type)

**Main Board / 中小板:**
```python
board_type: Literal["main"] = "main"
X ∈ {6%, 8%, 10%}
```

**Growth Board / 创业板 / 科创板:**
```python
board_type: Literal["growth"] = "growth"
X ∈ {10%, 12%, 15%}
```

**Rationale:**
- 主板 6% / 8% 可能被单日跌停（-10%）击穿，验证时必须统计 `gap_through_rate`
- 创业板 / 科创板 ±20% 制度下，过窄止损磨损严重，候选整体上移
- 移动止损不在本设计内

### 6.6 Fixed Stop Validation Method

**不选"收益最高"的 X。**

**Validation Metrics (for each candidate X):**
```python
class StopValidationMetrics(BaseModel):
    candidate_stop_pct: float  # 候选止损百分比
    board_type: Literal["main", "growth"]
    
    # Core metrics
    single_trade_max_loss: float  # 单笔最大亏损
    stop_hit_rate: float  # 止损触发率
    false_stop_rate: float  # 误止损率（止损后反弹 > 15%）
    gap_through_rate: float  # 跌停击穿率（收盘价 < 止损价 - 2%）
    actual_stop_slippage_distribution: dict  # 触发价到真实成交价的滑点分布
    unfilled_stop_days: dict  # 跌停/停牌导致的顺延天数分布
    
    # Strategy impact
    strategy_return_with_stop: float  # 带止损策略收益
    strategy_return_without_stop: float  # 无止损策略收益
    stop_impact: float  # 止损影响（with - without）
    
    # Sample
    oos_window: str  # 验证窗口（例："2022-01-01 to 2023-12-31"）
    sample_size: int  # 样本数
```

**Freezing Criteria:**
```
在真实成交假设下能把 single_trade_max_loss 压到可接受范围，
且 false_stop_rate 不过高的前提下，
选择对 strategy_return 伤害最小的 X。
```

**Not Acceptable:**
- ❌ 选择 `strategy_return_with_stop` 最高的 X（可能过拟合）
- ❌ 选择 `stop_hit_rate` 最低的 X（过宽，失去保护作用）
- ❌ 使用触发日收盘价作为成交价
- ❌ 不建模跌停 / 停牌不可成交顺延

**Acceptable:**
- ✅ 选择在 `single_trade_max_loss < -15%` 且 `false_stop_rate < 30%` 约束下，`stop_impact` 最小的 X

### 6.7 Fixed Stop Contract

**Output:**
```json
{
  "board_type": "main",
  "fixed_stop_pct": 0.08,
  "trigger_basis": "daily_close",
  "is_realtime": false,
  "stop_criteria_hash": "sha256:xyz789...",
  "validation_metrics": {
    "single_trade_max_loss": -0.12,
    "stop_hit_rate": 0.18,
    "false_stop_rate": 0.25,
    "gap_through_rate": 0.08,
    "actual_stop_slippage_distribution": {
      "p50": -0.018,
      "p90": -0.052
    },
    "unfilled_stop_days": {
      "max": 3,
      "mean": 0.2
    },
    "strategy_return_with_stop": 0.15,
    "strategy_return_without_stop": 0.18,
    "stop_impact": -0.03
  }
}
```

**UI Display:**
- ✅ "固定失效价：11.28 元（买入价下方 8%）"
- ✅ "止损为日频，次日生效，非实时保护"
- ❌ 不显示 "fixed_stop_pct: 0.08"
- ❌ 不显示 "trigger_basis: daily_close"

---

## 7. Insertion Points Summary

### 7.1 Action Plan Generation

```
Signal Board → Action Plan Builder
  ↓
【1. Check MarketRegimeState】
  - extreme_* → downgrade to "do_not_execute"
  - data_state != ok → downgrade to "pause_observation" and record data issue
  ↓
【2. Check PositionLimit】
  - exceeds_limit → downgrade to "pause_observation"
  - capital_insufficient → downgrade to "do_not_execute"
  - min_lot_exceeds_limit → downgrade + suggest
  ↓
【3. Calculate Fixed Stop Price】
  - entry_price * (1 - fixed_stop_pct)
  - Record in action_plan
  ↓
Action Plan (with all checks)
```

### 7.2 Daily Signal Generation

```
Observation Pool → Daily Signal Generator
  ↓
【1. Check MarketRegimeState】
  - extreme_* → force signal = "risk"
  - data_state != ok → force data status, not regime status
  ↓
【2. Deterministic Reducer】
  - Priority 1: MarketDataFault → data_state insufficient / fault, signal_type = None
  - Priority 2: Invalidation triggers → invalidated
  - Priority 3: Fixed stop → sell (rule_trace = "fixed_stop")
  - Priority 4: Profit target → sell (rule_trace = "profit_target")
  - Priority 5: Risk warning → risk
  - Priority 6: Default hold
  ↓
Daily Observation Signal (with regime + data + stop checks)
```

### 7.3 Discipline Review

```
Position Close → Discipline Review
  ↓
【1. Calculate P&L】
  - From execution_observation_log
  ↓
【2. Check Plan Adherence】
  - record factual deviation only
  - no early/late/ignored labels
  ↓
【3. Determine ExitAttribution】
  - fixed_stop_triggered / reached_planned_take_profit / reached_planned_exit
  - user_sold_while_signal_hold
  - data_insufficient / data_fault / unclassified
  ↓
Discipline Review (with honest attribution)
```

---

## 8. User-Facing Language Summary

### 8.1 Market Regime

| Internal State | User Message |
|----------------|--------------|
| `ok` | (无特殊提示) |
| `extreme_breadth_selloff` | "市场状态异常，暂停信号生成" |
| `structural_breakdown` | "极端行情阻断，建议观望" |
| `liquidity_exhaustion` | "市场流动性不足，暂停信号生成" |
| data_state = `insufficient` | "市场数据不足，无法判断大盘状态" |
| data_state = `fault` | "市场数据异常，无法判断大盘状态" |

### 8.2 Position Limit

| Internal Status | User Message |
|-----------------|--------------|
| `within_limit` | (无特殊提示) |
| `exceeds_limit` | "资金约束：单票限额 5,000 元，计划买入 8,000 元，建议减仓或增加资金池" |
| `capital_insufficient` | "资金不足，无法执行" |
| `min_lot_exceeds_limit` | "最低买入金额超过单票限额，建议增加资金池或选择低价股" |

### 8.3 Fixed Stop

| Event | User Message |
|-------|--------------|
| Stop price set | "固定失效价已设置：11.28 元（买入价下方 8%）" |
| Stop triggered | "止损触发：收盘价 11.20 元，已跌破失效价，次日生成离场信号" |
| Daily close basis | "止损为日频，次日生效，非实时保护" |

### 8.4 Data State

| Internal Type | User Message |
|---------------|--------------|
| `hold` | "继续持有" |
| data_state = `insufficient` | "数据不足，建议暂停操作" |
| data_state = `fault` | "数据源错误，无法生成信号" |

### 8.5 Exit Attribution

| Attribution | User Message |
|-------------|--------------|
| `fixed_stop_triggered` | "退出原因：固定止损触发（-8%）" |
| `reached_planned_take_profit` | "退出原因：计划止盈达成（+15%）" |
| `user_sold_while_signal_hold` | "退出记录：卖出时系统信号为继续观察" |
| `data_insufficient` | "退出原因：数据不足期间退出" |

---

## 9. Implementation Tasks (仍需实现的任务)

### 9.1 P0-3A: MarketRegimeGuard Service

**File:** `backend/services/market_regime_guard.py`

**Tasks:**
1. Define `MarketRegimeState` enum
2. Define separate `DataState` enum
3. Implement `check_market_regime(as_of_date) -> MarketRegimeCheck`
4. Detection logic:
   - Extreme breadth selloff (Tushare daily 跌幅统计)
   - Structural breakdown (沪深300 index_daily)
   - Liquidity exhaustion (沪深两市成交额)
5. Candidate thresholds (待验证冻结)
6. Configuration file for thresholds

**Contracts:**
```python
class MarketRegimeCheck(BaseModel):
    as_of_date: date
    regime_state: MarketRegimeState | None
    data_state: DataState
    check_metrics: dict  # 检查指标
    user_visible_reason: str
```

**Tests:**
- Unit test: 2015 股灾、2020 三月应返回 extreme_*
- Unit test: 正常日期应返回 ok
- Unit test: Tushare 不可用应返回 data_state = fault and regime_state = None

---

### 9.2 P0-3B: CapitalContext + Tier Assignment

**File:** `backend/services/capital_context.py`

**Tasks:**
1. Define `CapitalTier` enum
2. Define `CapitalContext` model
3. Implement tier assignment logic:
   ```python
   if capital_pool < THRESHOLD_SMALL:
       tier = "small"
       max_open_positions = 1
       single_stock_cap = capital_pool
   else:
       tier = "normal"
       max_open_positions = N
       single_stock_cap = capital_pool * CAP_RATIO
   ```
4. Configuration file for thresholds (THRESHOLD_SMALL, N, CAP_RATIO)
5. Config hash generation (审计痕迹)

**Contracts:**
```python
class CapitalContext(BaseModel):
    user_id: str
    capital_pool: float
    tier: CapitalTier
    max_open_positions: int
    single_stock_cap_amount: float
    fixed_stop_pct: float
    tier_thresholds_hash: str
    stop_criteria_hash: str
```

**Tests:**
- Unit test: capital_pool = 5000 → tier = "small", max_open = 1, cap = 5000
- Unit test: capital_pool = 50000 → tier = "normal", max_open = N, cap = 50000 * CAP_RATIO
- Unit test: config hash consistent

---

### 9.3 P0-3C: PositionLimit Check

**File:** `backend/services/action_plan_builder.py` (modify)

**Tasks:**
1. Add `check_position_limit()` before building action plan
2. Return `PositionLimitCheck` with status + downgrade_reason
3. Handle edge cases:
   - `capital_insufficient`
   - `min_lot_exceeds_limit`
4. Downgrade `recommendation_level` if limit exceeded

**Contracts:**
```python
class PositionLimitCheck(BaseModel):
    status: Literal[
        "within_limit",
        "exceeds_limit",
        "capital_insufficient",
        "min_lot_exceeds_limit",
        "data_fault"
    ]
    user_capital_pool: float
    single_stock_limit: float
    planned_position_value: float
    min_lot_value: float
    allowed_to_execute: bool
    downgrade_reason: str | None
```

**Tests:**
- Unit test: planned = 3000, limit = 5000 → within_limit
- Unit test: planned = 8000, limit = 5000 → exceeds_limit
- Unit test: min_lot = 20000, limit = 5000 → min_lot_exceeds_limit

---

### 9.4 P0-3D: Fixed Stop Validation

**File:** `docs/validation/fixed_stop_validation.md` (design doc)

**Tasks:**
1. Design OOS validation protocol
2. Define metrics:
   - `single_trade_max_loss`
   - `stop_hit_rate`
   - `false_stop_rate`
   - `gap_through_rate`
   - `actual_stop_slippage_distribution`
   - `unfilled_stop_days`
   - `strategy_return_with_stop` / `without_stop`
3. Use A-share executable fill assumptions:
   - sell signal after daily close
   - fill attempt at next trading day open
   - limit-down / suspended days cannot fill and must carry forward
   - commission, stamp tax, and slippage included
4. Run validation for:
   - Main board: X ∈ {6%, 8%, 10%}
   - Growth board: X ∈ {10%, 12%, 15%}
5. Freeze thresholds based on criteria:
   ```
   single_trade_max_loss < -15%
   false_stop_rate < 30%
   minimize stop_impact
   ```
6. Update `strategy_template_library` with frozen values

**Contracts:**
```python
class FixedStopConfig(BaseModel):
    board_type: Literal["main", "growth"]
    fixed_stop_pct: float
    trigger_basis: Literal["daily_close"]
    is_realtime: bool = False
    stop_criteria_hash: str
    validation_metrics: StopValidationMetrics
```

**Deliverable:**
- Validation report (Markdown)
- Frozen config (YAML/JSON)
- One sample trade trace showing trigger date, next open, limit-down/suspension handling, carry-forward days, final fill price, costs, and final P&L

---

### 9.5 P0-3E: Daily Observation Signal Contract Refactor

**File:** `contracts/live_trade.py` (modify)

**Tasks:**
1. Keep `DailySignalType` for business judgment only: hold / sell / risk / invalidated
2. Add separate `DataState` field: ok / insufficient / fault
3. Remove ambiguity from `risk` (reserve for risk warnings only)

**File:** `backend/services/observation_pool.py` (modify)

**Tasks:**
1. Update deterministic reducer:
   - Priority 1: MarketDataFault → data_state insufficient / fault and signal_type = None
   - Priority 2: Invalidation triggers → invalidated
   - Priority 3: Fixed stop → sell
   - Priority 4: Profit target → sell (future)
   - Priority 5: Risk warning → risk (future)
   - Priority 6: Default hold
2. Update rule_trace for new signal types

**Tests:**
- Unit test: market_data_state = partial → data_state = insufficient, signal_type = None
- Unit test: market_data_state = unavailable → data_state = fault, signal_type = None
- Unit test: market_data_state = ok, no triggers → data_state = ok, signal_type = hold
- Unit test: pnl <= stop_threshold → data_state = ok, signal_type = sell

---

### 9.6 P0-3F: ExitAttribution Detection

**File:** `backend/services/discipline_review.py` (modify)

**Tasks:**
1. Add `determine_exit_attribution()` function
2. Detection logic:
   - `fixed_stop_triggered`: daily signal = sell + rule_trace = "fixed_stop"
   - `reached_planned_take_profit`: rule_trace = "profit_target"
   - `reached_planned_exit`: daily signal = invalidated
   - `user_sold_while_signal_hold`: latest valid signal = hold when user sold
   - `data_insufficient` / `data_fault`: signal type
   - `unclassified`: insufficient evidence
3. Update `DisciplineReview` model with `exit_attribution` field

**Contracts:**
```python
class DisciplineReview(BaseModel):
    # ... existing fields ...
    exit_attribution: ExitAttribution
    attribution_evidence: dict
```

**Tests:**
- Unit test: sell signal with "fixed_stop" → fixed_stop_triggered
- Unit test: latest valid signal hold and user sold → user_sold_while_signal_hold
- Unit test: forbidden values early_exit / late_exit / ignored_signal / manual_deviation are not in enum

---

### 9.7 P0-3G: Integration into Action Plan + Daily Signal

**File:** `backend/services/action_plan_builder.py` (modify)

**Tasks:**
1. Call `market_regime_guard.check_market_regime()` before building plan
2. Call `capital_context.check_position_limit()` before building plan
3. Downgrade `recommendation_level` if regime extreme or limit exceeded
4. Record checks in `action_plan.risk_checks` field

**File:** `backend/services/observation_pool.py` (modify)

**Tasks:**
1. Call `market_regime_guard.check_market_regime()` before generating signal
2. Override signal_type if regime extreme
3. Record check in signal metadata

**Tests:**
- Integration test: extreme regime → action plan downgraded
- Integration test: position limit exceeded → action plan downgraded
- Integration test: extreme regime → daily signal = risk

---

## 10. Configuration Management

### 10.1 Configuration Files

**Location:** `backend/config/`

**Files:**
```
market_regime_thresholds.yaml
capital_tier_rules.yaml
fixed_stop_criteria.yaml
```

### 10.2 market_regime_thresholds.yaml

```yaml
version: "1.0"
last_updated: "2026-07-02"
thresholds:
  extreme_breadth_selloff:
    metric: "pct_stocks_down_over_5pct"
    threshold: 0.80
    data_source: "tushare_daily"
  
  structural_breakdown_1d:
    metric: "hs300_daily_return"
    threshold: -0.05
    data_source: "tushare_index_daily"
  
  structural_breakdown_5d:
    metric: "hs300_5day_return"
    threshold: -0.10
    data_source: "tushare_index_daily"
  
  liquidity_exhaustion:
    metric: "total_turnover_vs_30d_mean"
    threshold: 0.30
    data_source: "tushare_daily"

validation_status: "candidate"  # candidate / frozen
validation_date: null
hash: "sha256:..."
```

### 10.3 capital_tier_rules.yaml

```yaml
version: "1.0"
last_updated: "2026-07-02"

tiers:
  small:
    condition: "capital_pool < threshold_small"
    max_open_positions: 1
    single_stock_cap_formula: "capital_pool"
    rationale: "真实反馈验证，不做风险分散"
  
  normal:
    condition: "capital_pool >= threshold_small"
    max_open_positions: 5  # 待冻结
    single_stock_cap_formula: "capital_pool * cap_ratio"

thresholds:
  threshold_small: 15000  # 待冻结，约 1-2 万
  cap_ratio: 0.10  # 待冻结，单一数值

validation_status: "candidate"
validation_date: null
hash: "sha256:..."
```

### 10.4 fixed_stop_criteria.yaml

```yaml
version: "1.0"
last_updated: "2026-07-02"

trigger_basis: "daily_close"
is_realtime: false
execution_price_basis: "next_trading_day_open"
blocked_if_limit_down_or_suspended: true
carry_forward_until_executable: true
costs_included: true

boards:
  main:
    candidates: [0.06, 0.08, 0.10]
    frozen_value: null
    validation_metrics: null
  
  growth:
    candidates: [0.10, 0.12, 0.15]
    frozen_value: null
    validation_metrics: null

validation_criteria:
  single_trade_max_loss_limit: -0.15
  false_stop_rate_limit: 0.30
  objective: "minimize_stop_impact"
  required_metrics:
    - single_trade_max_loss
    - stop_hit_rate
    - false_stop_rate
    - gap_through_rate
    - actual_stop_slippage_distribution
    - unfilled_stop_days
    - strategy_return_with_stop
    - strategy_return_without_stop

validation_status: "candidate"
validation_date: null
hash: "sha256:..."
```

### 10.5 Config Version Control

**Rules:**
- 所有参数变更必须更新 `version` 和 `last_updated`
- 计算 `hash` (sha256 of content) 用于审计痕迹
- `validation_status` 标记参数是否已冻结
- Frozen config 不可修改（需要新 version）

---

## 11. Design Freeze Checklist

- [x] MarketRegimeGuard 设计（状态定义 + 检测规则 + 插入位置）
- [x] PositionLimit 设计（分档规则 + 边界情况 + 用户界面）
- [x] FixedStopLoss 完整设计（日频触发 + 次日开盘成交 + 跌停/停牌顺延 + 板块区分 + 验证方法）
- [x] DataState 独立维度设计（业务判断 + 数据状态两个字段）
- [x] HonestAttribution 设计（事实类归因 + 禁止价值判断标签）
- [x] Capital Tier + Fixed Stop 补充设计（分档规则 + 触发口径）
- [x] 插入链路位置明确（Action Plan + Daily Signal + Discipline Review）
- [x] 用户界面语言定义（不暴露技术参数）
- [x] 实现任务拆解（P0-3A ~ P0-3G）
- [x] 配置文件管理方案（YAML + version + hash）

---

**Design Frozen:** 2026-07-02  
**Next Step:** P0-3 Implementation (code + tests + validation)
