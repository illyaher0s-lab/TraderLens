# Phase 2B-3 Checkpoint: sector_strength_tool

**完成时间**: 2026-06-09

---

## 目标

实现 `sector_strength_tool` — 板块强度分析工具，识别股票所属板块，计算板块整体表现，给出相对排名。

---

## 完成的工作

### 1. 板块强度工具 (`src/tools/sector_strength_tool.py`)

**职责**: 分析股票所属板块的强度和相对排名

**核心功能**:
- 识别股票所属板块和行业
- 获取板块内所有成分股列表
- 计算板块整体表现（近 20 日平均/中位数涨跌幅）
- 计算个股在板块内的相对排名
- 判断板块强度（强/中/弱）

**输入参数**:
- `stock_code`: 股票代码（如 "000001"）

**输出格式**（统一工具返回）:
```python
{
    "tool": "sector_strength_tool",
    "status": "success",
    "result": {
        "stock_code": "000001",
        "sector": "银行",
        "industry": "金融",
        "strength": "中",
        "sector_performance": {
            "avg_change_pct": 4.56,
            "median_change_pct": 4.20,
            "top_stocks": [...]  # 板块内涨幅前10
        },
        "stock_rank": {
            "rank": 1,
            "total": 5,
            "percentile": 0.2
        },
        "top_stocks": [...]  # 板块内前5强
    },
    "summary": "板块: 银行, 行业: 金融, 强度: 中, 近20日涨跌: 4.56%, 个股排名: 1/5",
    "signals": ["stock_top_in_sector"],
    "data_refs": {
        "stock_code": "000001",
        "sector": "银行",
        "constituent_count": 5,
        "source": "mock",
        "is_stale": false,
        "last_updated": "2026-06-09T11:00:00"
    },
    "error": null,
    "created_at": "2026-06-09T11:00:00"
}
```

**板块强度判断规则**:
- `强`: 板块平均涨跌幅 >= 5.0%
- `中`: 板块平均涨跌幅 >= 0.0%
- `弱`: 板块平均涨跌幅 < 0.0%

**信号生成规则**:
- `sector_strong`: 板块强度为 "强"
- `sector_weak`: 板块强度为 "弱"
- `stock_top_in_sector`: 个股排名前 30%
- `stock_bottom_in_sector`: 个股排名后 30%
- `sector_bullish`: 板块平均涨跌 >= 5.0%
- `sector_bearish`: 板块平均涨跌 <= -5.0%

**性能优化**:
- 限制最多计算 50 只成分股（避免大型板块计算过慢）
- 只返回板块内前 5 强股票（减少数据量）

### 2. DataFetcher 扩展 (`src/core/data_fetcher.py`)

**新增方法 1: `get_stock_sector()`**
- 识别股票所属板块和行业
- Mock 模式：返回固定值（"银行", "金融"）
- 真实模式：调用 AKShare `stock_individual_info_em()` API

**新增方法 2: `get_sector_constituents()`**
- 获取板块内所有成分股列表
- Mock 模式：返回固定列表（5 只银行股）
- 真实模式：调用 AKShare `stock_board_industry_cons_em()` API

**改进: `get_stock_daily_kline()` 支持 `period` 参数**
- 新增 `period` 参数（"1m", "3m", "6m", "1y", "2y"）
- 自动转换为 `start_date`（方便工具调用）
- 向后兼容（`start_date` 仍然有效）

### 3. 集成到 Agent (`src/agent/executor.py`)

**修改内容**:
- 在 `_execute_tool()` 中添加 `sector_strength_tool` 分支
- 直接调用 `sector_strength_tool(stock_code)`

**依赖关系**:
- 依赖 `DataFetcher.get_stock_sector()`
- 依赖 `DataFetcher.get_sector_constituents()`
- 依赖 `DataFetcher.get_stock_daily_kline(period="1m")`

---

## 验收标准

✅ **1. 独立测试 sector_strength_tool**
- 能正确识别股票所属板块和行业
- 计算板块整体涨跌幅（平均值和中位数）
- 给出个股在板块内的相对排名（排名/总数/百分位）
- 判断板块强度（强/中/弱）

✅ **2. Mock 模式下能正常工作**
- Mock 数据返回固定板块（"银行", "金融"）
- Mock 数据返回固定成分股列表（5 只）
- data_refs.source 标记为 "mock"

✅ **3. 信号生成正确**
- 根据板块强度生成信号（sector_strong/sector_weak）
- 根据个股排名生成信号（stock_top_in_sector/stock_bottom_in_sector）
- 根据板块涨跌生成信号（sector_bullish/sector_bearish）

✅ **4. DataFetcher 新增方法可用**
- `get_stock_sector()` 返回板块和行业信息
- `get_sector_constituents()` 返回成分股列表
- `get_stock_daily_kline(period="1m")` 支持简写周期

---

## 测试结果

### 测试 1: 独立测试 sector_strength_tool
```
✓ 板块分析完成
  - 状态: success
  - 板块: 银行
  - 行业: 金融
  - 强度: 中
  - 板块平均涨跌: 4.56%
  - 个股排名: 1/5
  - Summary: 板块: 银行, 行业: 金融, 强度: 中, 近20日涨跌: 4.56%, 个股排名: 1/5
  - Signals: ['stock_top_in_sector']
  - Data source: mock
```

### 测试 2: Mock 模式验证
```
✓ Mock 模式正常工作
  - data_refs.source: mock
  - 板块: 银行
  - 成分股数量: 5
```

### 测试 3: 信号生成测试
```
✓ 信号生成测试
  - 生成了 1 个信号
  - 信号列表: ['stock_bottom_in_sector']
```

### 测试 4: DataFetcher 方法测试
```
✓ DataFetcher 方法测试通过
  - get_stock_sector(): 板块=银行, 行业=金融
  - get_sector_constituents(): 5 只成分股
```

---

## 关键设计决策

### 1. 限制计算 50 只成分股

**选择**: 最多计算 50 只成分股的涨跌幅

**理由**:
- 大型板块（如 "银行"、"保险"）可能有上百只股票
- 计算所有股票会导致工具响应时间过长
- 前 50 只已经足够代表板块整体表现
- Phase 3+ 可以优化为并行计算或缓存

### 2. 使用近 20 日涨跌幅评估板块

**选择**: 计算近 20 日（约 1 个月）涨跌幅，而不是更短或更长周期

**理由**:
- 20 日（1 个月）既能反映短期趋势，又不会过度波动
- 与技术面分析的 MA20 指标保持一致
- 避免用日涨跌（噪音太大）或年涨跌（反应太慢）

### 3. 返回板块内前 5 强股票

**选择**: 只返回板块内涨幅前 5 的股票

**理由**:
- 用户关心板块内哪些股票表现最好
- 限制为 5 只避免数据过载
- 可以作为"同板块替代标的"参考

### 4. 板块强度三档划分（强/中/弱）

**选择**: 简单的三档划分，而不是更细的五档或连续分数

**理由**:
- MVP 目标是简单可用，不是精细评分系统
- 三档划分足够用于决策（买入强势板块/避开弱势板块）
- Phase 3+ 可以扩展为更细的评分体系

---

## 发现的问题

### 1. DataFetcher 缺少 `period` 参数支持

**问题**: `get_stock_daily_kline()` 不支持 "1m", "3m" 等简写周期

**原因**: 原有接口只支持 `start_date` 和 `end_date`

**解决方案**: 添加 `period` 参数，自动转换为 `start_date`

**影响**: 向后兼容，现有代码不受影响

### 2. 错误使用 `fetcher.cache.mock_mode`

**问题**: `DataFetcher` 对象没有 `cache` 属性

**原因**: 属性名是 `cache_manager`，不是 `cache`

**解决方案**: 直接使用 `fetcher.mode` 判断模式

---

## 下一步

### Phase 2B-4: fundamentals_tool

**目标**: 实现基本面分析工具

**输入**: `stock_code`, `strategy_profile`

**输出**: 基本面评分、关键指标（PE, PB, ROE, 负债率）、评级（优秀/良好/一般/差）

**数据源**: AKShare 财务指标接口（或 mock 数据）

**验收标准**:
1. 能正确拉取财务数据（PE, PB, ROE, 负债率等）
2. 根据策略类型（trend/growth/value）调整评分权重
3. 生成基本面评级（优秀/良好/一般/差）
4. Mock 模式下能正常工作
5. data_refs 正确标注数据来源

---

## 技术债务

1. **性能优化**（Phase 3+）:
   - 并行计算板块内成分股的涨跌幅
   - 缓存板块成分股列表（减少 API 调用）
   - 缓存板块整体表现（避免重复计算）

2. **板块分类优化**（Phase 3+）:
   - 支持多种板块分类标准（申万一级/二级/三级，中信行业）
   - 支持自定义板块（如 "新能源"、"芯片"）
   - 板块热度排行榜（当日涨幅最大的板块）

3. **排名算法优化**（Phase 3+）:
   - 使用更多维度排名（涨幅 + 成交量 + 资金流入）
   - 计算板块内 Alpha（个股超额收益）
   - 历史排名趋势（排名上升/下降）

4. **测试数据优化**（Phase 3+）:
   - 使用真实 API 测试（缓存到 data/test_data/）
   - 生成更真实的 mock 数据（板块轮动、个股分化）
   - 添加边界案例测试（板块只有 1 只股票、板块全部涨停）

---

## 文件清单

### 新增文件

- `src/tools/sector_strength_tool.py` - 板块强度分析工具
- `test_phase2b3.py` - Phase 2B-3 验收测试
- `docs/checkpoints/phase2b3-checkpoint.md` - 本文档

### 修改文件

- `src/core/data_fetcher.py` - 新增 `get_stock_sector()` 和 `get_sector_constituents()`，`get_stock_daily_kline()` 支持 `period` 参数
- `src/agent/executor.py` - 集成 `sector_strength_tool`

---

## Phase 完成状态

- Phase 1: ✅ 完成（Agent 循环、interrupt、安全检查）
- Phase 2A: ✅ 完成（3 个核心工具 + 真实逻辑）
- Phase 2A+: ✅ 完成（缓存、mock 模式、data_refs）
- Phase 2B-1: ✅ 完成（watchlist_tool + 人工确认流程）
- Phase 2B-2: ✅ 完成（backtest_tool + 回测引擎）
- **Phase 2B-3: ✅ 完成（sector_strength_tool + 板块分析）**
- Phase 2B-4: 待开始（fundamentals_tool）
- Phase 2B-5: 待开始（search_research_memory_tool）

---

**最后更新**: 2026-06-09
