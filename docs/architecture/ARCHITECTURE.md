# TraderLens 架构文档

最后更新：2026-06-25 (Phase 4: Serenity 双阶段生产入口启用)

本文档是 TraderLens 的稳定架构地图，不是项目进度记录。

- 看当前做到哪一步：读 `status.md`
- 看最初 MVP/V1 设计蓝图：读 `docs/design/`
- 看系统边界、模块关系、数据流：读本文档

## 架构更新记录

**2026-06-25 (Phase 4: Serenity 双阶段生产入口启用)**:
- ✅ Serenity 双阶段架构生产就绪（2 次 LLM + 确定性执行器）
- ✅ 严格配置矩阵验证（real+two_phase, deterministic+stub）
- ✅ 边界门禁闭合（conversation_mode 验证、注入 runner 类型校验）
- ✅ 测试基线：896 tests (2 skipped)

**2026-06-23 (M4 完成)**:
- ✅ 新增 Signal Board v0 模块
- ✅ 新增 PlannedSignal 数据模型
- ✅ 新增 signal generation 脚本
- ✅ 新增 FastAPI signal board endpoints
- ✅ 新增 Next.js Signal Board UI
- ✅ 完整端到端：snapshot → strategy → signals → DB → API → frontend → review

**2026-06-22 (M3 完成)**:
- ✅ TushareDataSource 集成
- ✅ Frozen snapshot 机制
- ✅ Deterministic replay 验证

---

## 1. 系统定位

TraderLens 是一个 A 股策略验证工作台。

它不是：

- 自动交易系统
- 券商 API 接入层
- 股票推荐系统
- LLM 选股或 LLM 下单系统

它的核心链路是：

```text
研究假设 -> 可执行策略规则 -> 确定性回测 -> 人工判断 -> 下一交易日计划信号
```

系统的主角不是“股票”，而是“可验证的策略假设”。所有模块都应该服务于这件事：把研究判断变成可审计、可复现、可回测的规则。

## 2. 不可破坏的边界

这些边界比目录结构更重要。

### LLM 边界

LLM 可以用于：

- 分类
- 总结
- 草稿生成
- 从非结构化文本中提取信息
- 辅助研究判断

LLM 不能用于：

- 生成入场/出场信号
- 计算盈亏
- 计算组合指标
- 决定买卖
- 做路由、重试、状态码处理等确定性逻辑
- 静默修改策略状态

### Evidence 边界

Evidence 可以影响研究池和策略股票池。

Evidence 不能直接变成买卖条件。研究证据必须先经过人工确认和规则化，才能进入 `strategy_core`。

也就是说：

```text
Evidence -> 股票池 / 假设质量
Evidence -X-> 入场信号 / 出场信号
```

### strategy_core 边界

`strategy_core` 是确定性交易逻辑的唯一真相源。

以下逻辑必须属于 `strategy_core`，或属于它明确调用的协议边界：

- 策略解析
- 策略语义校验
- 股票池构建
- 信号生成
- 订单意图生成
- 成交模拟
- 持仓和现金状态
- 交易成本
- 回测结果
- 指标计算
- 原型门槛评估建议

前端、脚本、worker 可以编排这些能力，但不应该复制这些逻辑。

### 人工判断边界

评估模块可以给出 `passed`、`failed`、`needs_review` 之类的建议。

策略状态变化是产品决策，不应该作为指标计算的隐藏副作用发生。

## 3. 架构分层

当前项目可以按下面几层理解：

```text
frontend/
  Next.js 前端壳。
  目标承载 Dashboard、Strategies、Backtest、Report、Signal Board、Tasks、Audit 等页面。

backend/app/
  FastAPI 应用、Pydantic 契约、SQLite 初始化、worker 骨架、本地数据源适配器。

backend/scripts/
  工程脚本。
  用于生成 fixture、校验数据、导出回测结果、比较回测结果、批量跑策略。

strategy_core/
  确定性策略执行核心。
  这一层应该可以脱离 Web、脱离 LLM 单独运行。

tests/
  Golden Cases、固定 fixture、benchmark fixture、单元测试和集成测试。
  这里是当前行为的可执行事实来源。

docs/design/
  MVP/V1 产品设计和未来路线。
  这里描述目标蓝图，不等于当前全部已经接通。
```

当前后端 API 还很薄，核心能力主要在 `strategy_core`、contracts、fixtures、scripts 和 tests 中。后续 Web 和任务系统应该接入这些能力，而不是另写一套交易逻辑。

## 4. 两条主数据流

项目里同时存在“目标产品链路”和“当前确定性链路”。把这两条分开看，可以减少很多混乱。

### 目标产品链路

这是设计文档里的完整产品方向：

```text
主题输入
-> Serenity 产业链研究
-> Evidence 取证 / 证伪
-> 人工确认
-> Hypothesis Builder 转规则
-> StrategyConfig / YAML
-> strategy_core 回测
-> Gate 建议
-> 人工状态决策
-> Signal Board 下一交易日计划信号
-> 可选 Execution Log
```

这条链路应该逐步接通。接通时必须保持“研究辅助”和“确定性交易逻辑”隔离。

### 当前确定性链路

这是目前最重要的实现锚点：

```text
Strategy YAML / dict
-> Pydantic StrategyConfig
-> 策略语义校验
-> Frozen Snapshot (Tushare Parquet) 或 fixture 数据源
-> TushareDataSource (M3) 或 FixedFixtureDataSource
-> 交易日历
-> 股票池构建
-> 信号生成
-> 订单生成
-> 成交模拟
-> 组合状态更新
-> 指标 / FIFO round-trip matching
-> Prototype Gate 建议
-> 导出 / 对比 / suite 报告
```

**M3 新增**：
- TushareDataSource：读取 frozen Parquet snapshot（不调 API）
- Lazy load + cache：按需加载股票数据
- Reproducibility：same snapshot + same strategy = same result

后续 UI、worker、研究模块都应该接入这条链路，而不是绕过它。

## 5. 核心契约层

`backend/app/contracts.py` 是跨模块共享契约。

它定义的对象包括：

- 市场数据：`StockIdentity`、`DailyBar`、`DailyStatus`
- 策略输入：`StrategyConfig`
- 研究输出：`EvidenceOutput`、`HypothesisDraft`
- 执行意图：`Signal`、`Order`、`TradePlan`
- 审计和跟踪：`AuditLog`、`ExecutionLog`、`ForwardCandidate`
- 回测输出：`Trade`、`DailyPortfolioValue`、`RoundTrip`、`BacktestMetrics`、`BacktestResult`

契约层应该偏严格。调用方如果不能产生合法契约，应该在进入边界前适配，而不是让核心逻辑接受松散数据。

## 6. strategy_core 职责划分

`strategy_core` 按职责拆分：

- `dsl_parser.py`：把 YAML / dict 解析成 `StrategyConfig`
- `validator.py`：拒绝不支持或语义非法的策略
- `universe_builder.py`：构建可交易股票池
- `signals.py`：生成确定性入场/出场信号
- `orders.py`：把信号转换为订单意图，并处理冲突
- `position_sizer.py`：计算按 A 股手数约束后的计划数量
- `trading_calendar.py`：提供交易日导航
- `fill_simulator.py`：模拟 A 股成交和拒单
- `portfolio.py`：维护现金、持仓、冻结股数、市值
- `transaction_costs.py`：计算佣金、印花税、现金流
- `backtest_engine.py`：协调事件循环回测
- `lot_matching.py`：用 FIFO 匹配买卖 lot
- `metrics.py`：计算回测指标
- `prototype_gate.py`：给出原型门槛建议

原则：`backtest_engine.py` 负责协调，不应该吞掉所有业务逻辑。新的规则或约束应放到最小负责模块里。

## 7. 数据源边界

核心逻辑应该依赖"数据源行为"，而不是依赖某个具体供应商。

### DataSource Protocol (M2 Frozen)

所有数据源必须实现 8 个方法：

- `get_metadata()` → DataSourceMetadata
- `validate()` → ValidationResult
- `symbols()` → list[str]
- `get_daily_bars(symbol)` → list[DailyBar]
- `get_daily_statuses(symbol)` → list[DailyStatus]
- `get_daily_bar(symbol, date)` → DailyBar
- `get_daily_status(symbol, date)` → DailyStatus
- `get_price(symbol, date)` → float

### 已实现数据源 (M3)

**FixedFixtureDataSource** (M2):
- 读取 tests/golden_cases/ 中的 Parquet 文件
- 用于测试和 golden case 验证

**TushareDataSource** (M3):
- 读取 frozen Parquet snapshot（不调 API）
- Lazy load + cache per-symbol
- 支持 10 stocks × 30 days 或更大规模
- 生成：`python backend/scripts/generate_sample_snapshot.py`

### 数据质量约束

缺失数据或不支持的数据不能静默猜测；要么 fail loud，要么显式标记 degraded。

**Fail-loud 示例**:
- 请求不存在的 symbol → KeyError
- 请求不存在的 date → KeyError
- OHLC 不满足约束 (low > high) → ValidationError on load

**Contract Validation**:
- DailyBar: open/high/low/close > 0, low <= close <= high
- DailyStatus: limit_up 和 limit_down 互斥, ST/suspended boolean

## 8. Gate 语义

当前需要区分两个概念：

### Prototype Gate

Prototype Gate 是基于回测指标的确定性建议。

它可以建议：

- passed
- failed
- needs_review

但它不应该静默修改 `strategy.status`。

### Admission Gate

Admission Gate 是设计文档中更强的产品准入门。

它未来可能成为 Signal Board 之前的正式门槛，但它的状态转换行为必须被明确设计和实现。

不要把 Prototype Gate 和 Admission Gate 平均成一个模糊概念。在 Admission Gate 明确实现前，产品层应把 Prototype Gate 当作建议，而不是状态机。

## 9. Research Module 架构 (Phase 4)

Research Module 是 A 模块（选股研究）的产品入口，负责从主题输入到确认候选池的完整链路。

### 9.1 核心定位

Research Module 是**候选发现与验证**，不是交易决策。

```text
Theme input (manual / market scan)
  ↓
Serenity (supply chain bottleneck analysis)
  ↓
Hard filters (ST, suspended, liquidity)
  ↓
Evidence Agent (support/falsify/conflict)
  ↓
Human confirmation
  ↓
confirmed_candidate_pool (forward-only)
```

**产品入口**: `/themes` (Theme Board)

**核心原则**: AI 提议（propose），人类确认（apply）。Board 是唯一真实来源。

### 9.2 Serenity 双阶段架构

Serenity 采用**双阶段 LLM + 确定性执行器**架构，严格控制 LLM 调用次数和并发度。

**流程图**:

```text
用户输入 (ThemeInput + manual_candidates)
  ↓
LLM 1: Research Planner
  → ResearchPlan (keywords, seed_symbols, sectors, falsification_questions)
  ↓
确定性执行器 (Deterministic Executor, max_concurrency=2)
  → 并发数据检索 (retrieve_supply_chain)
  → 玩家发现 (discover_players)
  → 批量 ticker 验证 (verify_ticker, max_concurrency=2)
  → 来源审计 (audit_sources)
  → red-team 证伪 (red_team_falsify)
  → SerenityRunContext (sources + verified_candidates)
  ↓
LLM 2: Research Synthesizer
  → ResearchSynthesis (demand_driver, value_chain, bottleneck, hypothesis)
  ↓
确定性门禁 (Deterministic Shortlist Gate)
  → 10 条硬规则过滤
  → candidate_shortlist
  ↓
SerenityOutput
```

**硬约束**:
- 单次 run 精确 **2 次 LLM 调用**（Planner + Synthesizer）
- 最大并发数 = **2**（包括 LLM 和数据工具）
- **所有门禁由确定性代码完成**（无 LLM 参与）

**配置矩阵**（严格验证）:

| conversation_mode | serenity_execution_mode | 结果 |
|-------------------|-------------------------|------|
| real | two_phase | ✅ 允许（生产模式） |
| real | stub | ❌ 拒绝 |
| deterministic | stub | ✅ 允许（测试模式） |
| deterministic | two_phase | ❌ 拒绝 |
| unknown | 任意 | ❌ 拒绝 |

**Shortlist 门禁规则**（10 条）:

候选进入 shortlist 必须满足：
1. 存在于 verified_candidates_by_symbol
2. verification_id 有效并与 symbol 匹配
3. company_name 来自 verification record
4. 至少一个真实 supporting source
5. 至少一个 supporting source 不是 weak
6. source_audit 已完成
7. red_team 已完成
8. 候选拥有 red_team finding 或 unresolved gap
9. 没有身份阻断问题（confidence ≠ low, listing_status = listed）
10. Synthesizer 引用的 source IDs 全部真实存在

不满足条件时返回空列表，不为凑数量放行。

**信任链**:
- verification_id 强制来自真实验证记录（拒绝假 ID）
- company_name 强制从 verification record 读取（LLM 不能覆盖）
- supporting_source_ids 必须全部真实存在（拒绝编造来源）
- run_context 维护真实 ResearchSource 记录（禁止临时占位数据）

### 9.3 职责边界

**Research Module 负责**:
- 主题管理（创建、修改、删除）
- 候选发现（Serenity 供应链分析 + 人工输入）
- 硬门槛过滤（ST、停牌、流动性）
- 证据轻检（Evidence Agent 支持/证伪/冲突分析）
- 人工确认（pending → confirmed）
- 会话界面（pending action workflow）

**Research Module 不负责**:
- ❌ 交易决策或买卖建议
- ❌ 策略排名或信号生成
- ❌ 自动执行订单
- ❌ Agent 驱动的状态变更（AI 提议，人类确认）

**硬约束**:
1. **A 模块不输出 buy/sell/recommendation/target price/stop loss/position**
2. **LLM 不创建市场事实、财务数字、公告、ticker identity**
3. **状态写入通过 ProposedAction → reducer → DB → Research Board**
4. **verification_id 信任链不可破坏**
5. **candidate_pool_raw 包含所有进入研究链路的候选（人工 + 已核验），与 shortlist 语义分离**

## 10. Signal Board 架构 (M4)

Signal Board 是 M4 新增的"下一交易日计划信号看板"。

### 核心定位

Signal Board 是**展示层**，不是信号生成器。

```text
Latest EOD Snapshot
  ↓
TushareDataSource (read-only)
  ↓
strategy_core.signals.generate_signals()  ← 信号生成在这里
  ↓
PlannedSignal (data model)  ← Signal Board 从这里开始
  ↓
Signal Board API (FastAPI + SQLite)
  ↓
Signal Board UI (Next.js)
  ↓
Human Review (pending → reviewed/ignored/approved_for_watch)
  ↓
(No execution in M4)
```

### 职责边界

**Signal Board 负责**:
- 展示 `strategy_core` 生成的信号
- 记录人工审核状态（pending/reviewed/ignored/approved_for_watch）
- 提供审计追踪（strategy_id, snapshot_hash, reviewed_by, rejection_reason）

**Signal Board 不负责**:
- ❌ 生成信号（由 `strategy_core` 负责）
- ❌ 修改策略状态（由策略管理模块负责）
- ❌ 执行订单（M4 不执行，M5+ 才考虑）
- ❌ 实时数据更新（只读 frozen/latest EOD snapshot）

### 数据模型

**PlannedSignal**:
- signal_id (UUID)
- strategy_id, strategy_version, snapshot_hash（audit trail）
- symbol, direction (buy/sell), quantity, trigger_reason
- review_status: pending | reviewed | ignored | approved_for_watch
- reviewed_at, reviewed_by, rejection_reason

**存储**: SQLite（嵌入式，无额外基础设施）

**API**: FastAPI (GET /api/signals, POST /api/signals/{id}/review)

**UI**: Next.js (/signals, /signals/[date], /signals/[signal_id])

### 硬约束

1. **所有信号绑定 snapshot_hash + strategy_version**（可复现、可审计）
2. **不输出"买入/卖出建议"**（用"计划动作" + "触发原因"）
3. **不修改 backtest_engine 或 DataSource Protocol**（复用现有能力）
4. **不自动执行订单**（人工审核 only）

## 11. 当前架构断点

这些是架构接线问题，不是进度清单：

- Web 还不是驱动确定性回测链路的主入口。
- worker 目前是基础设施形态，还不是 backtest / evidence / signal / export 的统一编排层。
- Hypothesis Builder、Forward Candidates 主要还是设计目标和契约边界。
- 外部实时或准实时数据源还不是系统基础，fixture 才是当前稳定基础。
- Signal Board 和 Action Plan 应消费确定性结果，不能自建信号逻辑。
- Prototype Gate 到未来 Admission Gate 的产品边界需要先讲清楚，再引入自动状态变化。

## 12. 后续扩展规则

新增能力时遵守这些规则：

1. 交易相关确定性逻辑优先进入 `strategy_core`，并配测试。
2. 供应商相关数据逻辑放在数据源适配边界后面。
3. LLM 输出不得进入买卖、盈亏、Gate 计算。
4. 跨模块传递尽量使用 contracts，不用随意 dict 穿透。
5. 接外部服务前，先用 fixture-backed 测试固定行为。
6. 策略状态变化必须显式、可审计。
7. 不支持的 V1 语义要 fail loud，不要悄悄近似。
8. 前端、脚本、worker 不复制策略执行逻辑。
9. **Signal Board 只展示 `strategy_core` 结果，不自建信号逻辑（M4）**
10. **所有信号必须绑定 snapshot_hash + strategy_version（M4）**
11. **人工审核状态变化必须记录 reviewed_by + reviewed_at（M4）**
12. **Serenity 单次 run 最多 2 次 LLM 调用（Phase 4）**
13. **Serenity 最大并发数 = 2（Phase 4）**
14. **verification_id 信任链不可破坏（Phase 4）**

## 13. 文档阅读顺序

不同问题看不同文件：

- `ARCHITECTURE.md`：系统地图、边界、模块关系
- `status.md`：当前进度、验证记录、近期实现细节
- `docs/design/QUICK-REFERENCE.md`：压缩版产品蓝图
- `docs/design/Part5-Milestones.md`：里程碑路线
- `tests/`：当前行为的可执行事实

如果这些来源互相冲突：

1. 当前行为优先看代码和 tests。
2. 当前进度优先看 `status.md`。
3. 未来方向看 `docs/design/`。
4. 架构边界看本文档。
