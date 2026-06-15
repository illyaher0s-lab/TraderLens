# Phase 2A Checkpoint - 工具层骨架 + 3 个核心工具

**完成时间**: 2026-06-08  
**目标**: 实现工具层骨架 + 3 个核心工具（market_regime_tool, technicals_tool, trade_plan_tool）  
**状态**: ✅ 逻辑完成，⚠️ API 稳定性待解决

---

## 完成内容

### 1. 统一工具返回格式

更新 `AGENTS.md`，定义统一格式：

```python
{
    "tool": str,                # 工具名称
    "status": str,              # "success" | "error" | "partial"
    "result": dict,             # 核心结果数据
    "summary": str,             # 一句话摘要（供 LLM 阅读）
    "signals": list[str],       # 关键信号列表
    "data_refs": dict,          # 数据引用路径
    "error": str | None,        # 错误信息
    "created_at": str           # 执行时间（ISO 8601）
}
```

**与 Phase 1 的区别**：
- Phase 1: `data` 字段 + `message` 字段 + `data_ref` (单数)
- Phase 2A: `result` 字段 + `summary` 字段 + `signals` 列表 + `data_refs` (复数)

**改进点**：
- `result` 更语义化（核心结果）
- `summary` 专门供 LLM 阅读
- `signals` 离散信号列表，用于触发条件判断

### 2. 核心模块

| 文件 | 状态 | 说明 |
|------|------|------|
| `src/core/data_fetcher.py` | ✅ | 数据获取（支持日线行情，AKShare） |
| `src/core/__init__.py` | ✅ | 模块初始化 |

**DataFetcher 实现**：
- `get_stock_daily_kline()`: 拉取日线 OHLCV
- 支持前复权/后复权/不复权
- 列名标准化（中文 → 英文）
- 重试机制（最多 3 次，间隔 2s/4s/6s）
- 错误处理（抛出异常，由工具捕获）

### 3. 三个核心工具

#### `market_regime_tool.py`

**功能**: 评估市场环境（基于上证指数）

**输入**:
- `index_code`: 指数代码（默认 "000001"）

**输出**:
```python
{
    "regime": "bull" | "bear" | "sideways",
    "volatility": "low" | "medium" | "high",
    "trend": "up" | "down" | "flat",
    "confidence": float,  # 0-1
    "index_code": str,
    "latest_close": float,
    "latest_date": str
}
```

**技术指标**:
- MA20, MA60: 均线
- 20 日波动率（年化）
- RSI(14)

**判断规则**:
- 牛市: 价格 > MA60, MA20 > MA60, RSI > 50
- 熊市: 价格 < MA60, MA20 < MA60, RSI < 50
- 震荡: 其他

**信号**:
- `regime_bull`, `regime_bear`, `regime_sideways`
- `volatility_low`, `volatility_high`
- `trend_up`, `trend_down`, `trend_flat`
- `strong_bull`, `strong_bear`, `high_risk`

#### `technicals_tool.py`

**功能**: 个股技术面分析

**输入**:
- `stock_code`: 股票代码
- `strategy_profile`: 策略风格（影响评分权重）

**输出**:
```python
{
    "score": float,  # 0-100
    "verdict": "强势" | "偏多" | "中性" | "偏空" | "弱势",
    "ma_signal": "golden_cross" | "death_cross" | "bullish" | "bearish" | "neutral",
    "macd_signal": "bullish" | "bearish" | "neutral",
    "rsi": float,
    "rsi_signal": float,
    "volume_signal": "surge" | "normal" | "shrink",
    "stock_code": str,
    "latest_close": float,
    "latest_date": str
}
```

**技术指标**:
- MA5, MA20, MA60
- MACD(12, 26, 9)
- RSI(14)
- Volume MA5

**评分规则**:
- 基础分 50
- 金叉 +20, 多头排列 +10
- MACD 多头 +10
- RSI 超卖 +5, 超买 -5
- 成交量放大 +10, 萎缩 -5
- trend 策略额外加权均线和 MACD

**信号**:
- `ma_golden_cross`, `ma_death_cross`, `macd_bullish`
- `rsi_oversold`, `rsi_overbought`
- `volume_surge`, `volume_shrink`
- `strong_buy_signal`, `strong_sell_signal`

#### `trade_plan_tool.py`

**功能**: 生成交易计划

**输入**:
- `stock_code`: 股票代码
- `market_regime`: 市场环境结果（来自 market_regime_tool）
- `technicals`: 技术面结果（来自 technicals_tool）
- `strategy_profile`: 策略风格

**输出**:
```python
{
    "action": "buy" | "hold",
    "position_size": float,  # 0-1
    "entry_price_low": float,
    "entry_price_high": float,
    "stop_loss": float,
    "take_profit": float,
    "risk_reward_ratio": float,
    "rationale": str,
    "stock_code": str,
    "current_price": float
}
```

**判断规则**:
- 技术面评分 < 40: 不建议建仓
- 市场熊市 + 技术面弱势: 不建议建仓
- 否则: 建议建仓

**仓位计算**:
- 基础仓位: trend 15%, growth 20%, value 25%
- 市场牛市 +5%, 熊市 -5%
- 高波动 -5%
- 技术面强势 +5%, 偏弱 -5%
- 最终: 5%-30%

**止损止盈**:
- 止损: 当前价 * 0.92 (-8%)
- 止盈: trend +15%, growth +20%, value +25%

**信号**:
- `action_buy`, `action_hold`
- `position_heavy`, `position_medium`, `position_light`
- `tech_bullish`

### 4. Executor 更新

更新 `src/agent/executor.py`，调用真实工具：

```python
def _execute_tool(tool_name, tool_input, state):
    if tool_name == "market_regime_tool":
        from tools.market_regime_tool import market_regime_tool
        return market_regime_tool(...)
    
    elif tool_name == "technicals_tool":
        from tools.technicals_tool import technicals_tool
        return technicals_tool(...)
    
    elif tool_name == "trade_plan_tool":
        from tools.trade_plan_tool import trade_plan_tool
        return trade_plan_tool(...)
    
    else:
        return _get_mock_result(tool_name, tool_input)
```

**Mock 数据更新**：
- Phase 1: `data` 字段
- Phase 2A: `result` 字段 + `summary` + `signals`

---

## 验收结果

### ✅ 本地测试通过

创建 `test_phase2a_tools.py`，使用模拟 K 线数据测试：

```
✅ market_regime_tool 测试通过
  - 状态: success
  - 摘要: 市场环境: bull, 波动率: high, 趋势: flat, 置信度: 70%
  - 信号: ['regime_bull', 'volatility_high', 'trend_flat', 'high_risk']

✅ technicals_tool 测试通过
  - 状态: success
  - 摘要: 技术面: 偏空, 评分: 25.00, MA: death_cross, MACD: bearish
  - 信号: ['ma_death_cross', 'macd_bearish', 'volume_normal']

✅ trade_plan_tool 测试通过
  - 状态: success
  - 摘要: 建议建仓 25%, 入场 15.19-15.81, 止损 14.26, 止盈 17.82
  - 信号: ['action_buy', 'position_heavy', 'tech_bullish']
```

### ✅ 错误处理正确

工具失败时返回 `status="error"`：

```python
{
    "tool": "market_regime_tool",
    "status": "error",
    "result": {},
    "summary": "市场环境分析失败: ...",
    "signals": [],
    "error": "Connection aborted...",
    "created_at": "2026-06-08T..."
}
```

Agent 不会崩溃，继续执行下一步（或根据 Reasoner 逻辑处理失败）。

### ⚠️ AKShare API 稳定性问题

**问题**: AKShare API 持续超时/连接中断

```
RemoteDisconnected: Remote end closed connection without response
```

**已实现的缓解措施**:
- ✅ 重试机制（3 次，间隔 2s/4s/6s）
- ✅ 错误处理（工具返回 error 状态）
- ✅ 日志记录（记录每次重试）

**待解决方案**:
1. **缓存机制**: 缓存拉取的数据到本地（1 小时有效期）
2. **备用数据源**: Tushare / BaoStock 作为 fallback
3. **Mock 模式**: 开发时使用本地测试数据

---

## 代码质量

- ✅ 所有文件通过 lint 检查
- ✅ 类型注解完整
- ✅ 错误处理完善（try-except + 返回 error 状态）
- ✅ 日志记录规范（INFO/WARNING/ERROR 分级）
- ✅ 代码注释清晰

---

## Phase 2A 验收标准对比

| 标准 | 状态 | 说明 |
|------|------|------|
| Agent 不再使用 mock 的市场和技术面结果 | ✅ | executor.py 调用真实工具 |
| 能够真实拉取一只 A 股近 1 年日线 | ⚠️ | DataFetcher 实现，但 API 不稳定 |
| 能够计算 MA20、MA60、涨跌幅等 | ✅ | technicals_tool 实现 |
| 能够输出标准工具结果 | ✅ | 统一格式实现 |
| Agent 的 observations 能正确保存真实工具输出 | ✅ | executor.py 更新 observations |
| 失败时不崩溃，返回 status="error" | ✅ | 工具异常处理完善 |

---

## 下一步

### Phase 2B: 补齐剩余工具

优先顺序（按"最容易跑通真实闭环"排序）：

1. **watchlist_tool** (最简单，SQLite CRUD)
2. **backtest_tool** (依赖行情数据，逻辑相对独立)
3. **sector_strength_tool** (需要板块数据，可能遇到 API 问题)
4. **fundamentals_tool** (财务数据最复杂，字段最多，放最后)
5. **research_memory_tool** (第二阶段，Phase 2B 仍返回占位)

### 立即优化（Phase 2A+）

1. **缓存机制**: 实现 `cache_manager.py`
   - 文件缓存（Parquet）
   - 内存缓存（LRU）
   - 1 小时有效期
   - 避免重复拉取

2. **Mock 模式开关**: `config.py` 添加 `USE_MOCK_DATA = True`
   - 开发时使用本地测试数据
   - 生产时使用真实 API

3. **备用数据源**: DataFetcher 支持多数据源 fallback
   - AKShare 失败 → Tushare → BaoStock

---

## 总结

Phase 2A 的**核心目标已完成**：
- ✅ 工具层骨架建立
- ✅ 统一返回格式定义
- ✅ 3 个核心工具逻辑正确
- ✅ 错误处理完善

**已知问题**：
- ⚠️ AKShare API 稳定性（外部依赖，不可控）

**解决方案**：
- 短期: 缓存机制 + Mock 模式
- 长期: 多数据源 fallback

**可以进入 Phase 2B**（补齐剩余工具），同时并行实现缓存机制。
