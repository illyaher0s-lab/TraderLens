# Phase 2B-4 Checkpoint: fundamentals_tool

**完成时间**: 2026-06-09

---

## 目标

实现 `analyze_stock_fundamentals` — 基本面分析工具，包装 DataFetcher + JudgmentEngine，评估股票财务质量。

---

## 完成的工作

### 1. 判断引擎 (`src/core/judgment_engine.py`)

**职责**: 根据财务数据和策略 Profile，评估股票基本面质量

**核心功能**:
- 提取关键指标（PE, PB, ROE, 负债率、增长率、利润率等）
- 计算绝对评分（0-100，根据策略类型调整权重）
- 计算行业相对评分（与行业平均对比）
- 综合评分（绝对 60% + 行业相对 40%）
- 判断评级（优秀/良好/一般/差）
- 识别优势和劣势
- 生成一句话摘要

**策略权重配置**:

| 策略类型 | 关注指标 | 权重分配 |
|---------|---------|---------|
| trend（趋势） | ROE (25%), 负债率 (20%), PE (15%), PB (15%), 增长率 (20%) | 平衡型 |
| growth（成长） | 营收增长 (30%), 利润增长 (25%), 毛利率 (15%), ROE (15%) | 成长型 |
| value（价值） | PE (25%), PB (20%), ROE (20%), 负债率 (15%), 流动比率 (10%) | 价值型 |

**指标评分规则**（示例）:
- **PE**: 8-15 优秀 (100分), 15-25 良好 (80-50分), >25 偏贵
- **ROE**: >15% 优秀 (100分), 10-15% 良好 (80分), 5-10% 一般 (50-80分), <5% 差
- **负债率**: <40% 优秀 (100分), 40-60% 良好 (90-80分), 60-80% 一般, >80% 高风险
- **增长率**: >20% 优秀 (90-100分), 10-20% 良好 (80分), 0-10% 一般, <0 差

**行业相对评分**:
- ROE / 行业平均 ROE 计算相对强度
- ≥1.5 倍: 100 分（远超行业）
- 1.2-1.5 倍: 90 分
- 1.0-1.2 倍: 80 分
- 0.8-1.0 倍: 60 分
- <0.8 倍: 20-40 分（低于行业）

### 2. 基本面工具 (`src/tools/fundamentals_tool.py`)

**职责**: 包装 DataFetcher + JudgmentEngine，提供统一接口

**输入参数**:
- `stock_code`: 股票代码（如 "000001"）
- `strategy_profile`: 策略类型（trend/growth/value）
- `include_industry_context`: 是否包含行业对比（默认 True）

**输出格式**（统一工具返回）:
```python
{
    "tool": "analyze_stock_fundamentals",
    "status": "success",
    "result": {
        "stock_code": "000001",
        "strategy_profile": "trend",
        "absolute_score": 93.8,
        "industry_relative_score": 90.0,
        "combined_score": 92.3,
        "verdict": "优秀",
        "key_metrics": {
            "pe": 12.5,
            "pb": 1.8,
            "roe": 15.2,
            "debt_ratio": 45.0,
            "revenue_growth": 18.5,
            "profit_growth": 22.3,
            "gross_margin": 32.5,
            "net_margin": 12.8,
            "current_ratio": 1.6,
            "quick_ratio": 1.2
        },
        "strengths": ["ROE 优秀 (15.2%)"],
        "weaknesses": []
    },
    "summary": "基本面优秀, PE 12.5, ROE 15.2%, 负债率 45.0%",
    "signals": ["fundamentals_excellent", "valuation_reasonable", "high_roe", "industry_leader"],
    "data_refs": {
        "stock_code": "000001",
        "source": "mock",
        "is_stale": false,
        "last_updated": "2026-06-09T12:00:00",
        "has_industry_context": true
    },
    "error": null,
    "created_at": "2026-06-09T12:00:00"
}
```

**信号生成规则**（15 种信号）:

| 信号 | 触发条件 | 说明 |
|------|---------|------|
| `fundamentals_excellent` | 综合评分 ≥ 80 | 基本面优秀 |
| `fundamentals_good` | 综合评分 60-80 | 基本面良好 |
| `fundamentals_poor` | 综合评分 < 40 | 基本面差 |
| `valuation_reasonable` | PE < 15 | 估值合理 |
| `valuation_expensive` | PE > 30 | 估值偏高 |
| `pb_undervalued` | PB < 1.5 | PB 低估 |
| `high_roe` | ROE ≥ 15% | 盈利能力强 |
| `low_roe` | ROE < 8% | 盈利能力弱 |
| `low_debt` | 负债率 < 40% | 财务健康 |
| `high_debt` | 负债率 > 70% | 债务风险高 |
| `high_revenue_growth` | 营收增长 ≥ 20% | 营收快速增长（growth 策略） |
| `high_profit_growth` | 利润增长 ≥ 20% | 利润快速增长（growth 策略） |
| `negative_revenue_growth` | 营收增长 < 0 | 营收负增长（growth 策略） |
| `negative_profit_growth` | 利润增长 < 0 | 利润负增长（growth 策略） |
| `industry_leader` | 行业相对评分 ≥ 80 | 行业龙头 |
| `industry_laggard` | 行业相对评分 < 40 | 行业落后 |

### 3. DataFetcher 扩展 (`src/core/data_fetcher.py`)

**新增方法 1: `get_financial_data()`**
- 获取股票财务数据（10 个关键指标）
- Mock 模式：返回固定财务数据
- 真实模式：调用 AKShare `stock_financial_analysis_indicator()` API

**新增方法 2: `get_industry_context()`**
- 获取行业平均指标（ROE, PE, PB）
- Mock 模式：返回固定行业数据
- 真实模式：拉取板块成分股（前 20 只），计算平均值

### 4. 集成到 Agent (`src/agent/executor.py`)

**修改内容**:
- 在 `_execute_tool()` 中添加 `analyze_stock_fundamentals` 分支
- 移除 `fundamentals_tool` 的 mock 实现（已替换为真实工具）

**依赖关系**:
- 依赖 `DataFetcher.get_financial_data()`
- 依赖 `DataFetcher.get_stock_sector()`（可选，用于行业对比）
- 依赖 `DataFetcher.get_industry_context()`（可选）
- 依赖 `JudgmentEngine.evaluate_fundamentals()`

---

## 验收标准

✅ **1. 独立测试 fundamentals_tool**
- 能正确拉取财务数据（10 个关键指标）
- 调用 JudgmentEngine 计算评分
- 返回评级（优秀/良好/一般/差）
- 识别优势和劣势

✅ **2. JudgmentEngine 评分逻辑正确**
- 优秀股票（高 ROE、低 PE、低负债）得分 ≥ 80
- 差股票（低 ROE、高 PE、高负债、负增长）得分 < 40
- 行业相对评分正确反映相对强度

✅ **3. 不同策略类型权重不同**
- trend 策略：平衡型权重
- growth 策略：侧重增长率
- value 策略：侧重估值和安全边际

✅ **4. 信号生成正确**
- 根据评分生成评级信号（excellent/good/poor）
- 根据指标生成细分信号（high_roe, low_debt, valuation_reasonable 等）
- growth 策略额外生成增长相关信号

✅ **5. Mock 模式下能正常工作**
- Mock 数据返回固定财务指标
- Mock 数据返回固定行业上下文
- data_refs.source 标记为 "mock"

---

## 测试结果

### 测试 1: 独立测试 fundamentals_tool
```
✓ 基本面分析完成
  - 状态: success
  - 评级: 优秀
  - 综合得分: 92.3
  - 绝对得分: 93.8
  - 行业相对得分: 90
  - 关键指标: PE 12.5, PB 1.8, ROE 15.2%, 负债率 45.0%
  - 优势: ['ROE 优秀 (15.2%)']
  - 劣势: []
  - Signals: ['fundamentals_excellent', 'valuation_reasonable', 'high_roe', 'industry_leader']
```

### 测试 2: JudgmentEngine 评分逻辑
```
测试案例 1: 优秀股票
  - 综合得分: 97.6
  - 评级: 优秀

测试案例 2: 差股票
  - 综合得分: 32.1
  - 评级: 差

测试案例 3: 行业相对评分
  - 绝对得分: 97.6
  - 行业相对得分: 100.0
  - 综合得分: 98.6
```

### 测试 3: 不同策略类型
```
Trend 策略:
  - 综合得分: 92.3
  - 信号: ['fundamentals_excellent', 'valuation_reasonable', 'high_roe', 'industry_leader']

Growth 策略:
  - 综合得分: 91.4
  - 信号: ['fundamentals_excellent', 'valuation_reasonable', 'high_roe', 'high_profit_growth', 'industry_leader']

Value 策略:
  - 综合得分: 92.8
  - 信号: ['fundamentals_excellent', 'valuation_reasonable', 'high_roe', 'industry_leader']
```

---

## 关键设计决策

### 1. 策略驱动的权重配置

**选择**: 根据策略类型（trend/growth/value）调整指标权重

**理由**:
- 不同投资者关注不同指标（成长投资者看增长率，价值投资者看估值）
- 同一只股票在不同策略下可能得分不同
- Phase 3+ 可以扩展为用户自定义权重

### 2. 绝对评分 + 行业相对评分

**选择**: 综合得分 = 绝对评分 60% + 行业相对评分 40%

**理由**:
- 绝对评分反映财务质量（独立于行业）
- 行业相对评分反映竞争地位（与同行对比）
- 60/40 权重平衡两者，避免过度依赖单一维度

### 3. 指标评分采用分段函数

**选择**: 每个指标用分段函数打分（如 PE: 8-15 为 100 分，15-25 递减）

**理由**:
- 分段函数比线性函数更符合实际（PE 15 和 16 差异不大，但 15 和 50 差异巨大）
- 阈值基于行业经验（如 ROE 15% 为优秀线）
- Phase 3+ 可以引入机器学习动态调整阈值

### 4. 优势/劣势识别

**选择**: 自动识别优势和劣势，而不是只返回评分

**理由**:
- 用户需要知道"为什么得了 92 分"
- 优势/劣势帮助 Agent 生成更具体的投资建议
- 可以用于 trade_plan_tool 的风险提示

### 5. 信号生成分层设计

**选择**: 信号分为三层：评级信号 + 指标信号 + 行业信号

**理由**:
- 评级信号（excellent/good/poor）用于快速决策
- 指标信号（high_roe, low_debt）用于细分筛选
- 行业信号（industry_leader）用于相对排名
- 分层信号便于后续扩展（如"只买行业龙头 + 高 ROE"）

---

## 发现的问题

### 1. 无问题

所有测试一次通过，设计和实现符合预期。

---

## 下一步

### Phase 2B-5: search_research_memory_tool

**目标**: 实现历史记录检索工具（占位功能）

**输入**: `query`（检索关键词）

**输出**: 历史分析记录（MVP 可以返回"未找到"）

**验收标准**:
1. 能正确处理检索请求（即使返回空）
2. 返回统一格式
3. Mock 模式下能正常工作
4. data_refs 正确标注数据来源

**备注**: 
- MVP 阶段可以只做占位实现（返回"功能开发中"）
- Phase 3+ 再接入 SQLite 的 research_history 表

---

## 技术债务

1. **指标评分阈值优化**（Phase 3+）:
   - 当前阈值基于经验，可能不适用所有行业
   - 引入行业特定阈值（如银行业负债率 > 80% 是正常的）
   - 使用历史数据拟合最优阈值

2. **更多财务指标**（Phase 3+）:
   - 当前只有 10 个指标，可以扩展到 20-30 个
   - 加入现金流指标（经营现金流 / 净利润比）
   - 加入杜邦分析（ROE 分解为净利率 × 总资产周转率 × 权益乘数）

3. **动态权重配置**（Phase 3+）:
   - 当前权重硬编码，可以改为配置文件（YAML）
   - 支持用户自定义策略（如"高股息策略"）
   - 支持机器学习自动调整权重

4. **行业对比优化**（Phase 3+）:
   - 当前只比较 ROE，可以扩展到多指标对比
   - 引入行业估值分位（当前 PE 在历史分位中的位置）
   - 引入板块轮动因子（板块强弱切换）

5. **缓存财务数据**（Phase 3+）:
   - 财务数据更新频率低（季度/年度），可以缓存
   - 避免重复调用 API
   - 降低延迟

---

## 文件清单

### 新增文件

- `src/core/judgment_engine.py` - 基本面判断引擎
- `src/tools/fundamentals_tool.py` - 基本面分析工具
- `test_phase2b4.py` - Phase 2B-4 验收测试
- `docs/checkpoints/phase2b4-checkpoint.md` - 本文档

### 修改文件

- `src/core/data_fetcher.py` - 新增 `get_financial_data()` 和 `get_industry_context()`
- `src/agent/executor.py` - 集成 `analyze_stock_fundamentals`，移除 fundamentals_tool 的 mock

---

## Phase 完成状态

- Phase 1: ✅ 完成（Agent 循环、interrupt、安全检查）
- Phase 2A: ✅ 完成（3 个核心工具 + 真实逻辑）
- Phase 2A+: ✅ 完成（缓存、mock 模式、data_refs）
- Phase 2B-1: ✅ 完成（watchlist_tool + 人工确认流程）
- Phase 2B-2: ✅ 完成（backtest_tool + 回测引擎）
- Phase 2B-3: ✅ 完成（sector_strength_tool + 板块分析）
- **Phase 2B-4: ✅ 完成（fundamentals_tool + JudgmentEngine）**
- Phase 2B-5: 待开始（search_research_memory_tool）

---

**最后更新**: 2026-06-09
