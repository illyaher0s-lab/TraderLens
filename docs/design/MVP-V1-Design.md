# TraderLens MVP V1 设计文档

**版本**: V1.0  
**日期**: 2026-06-20  
**状态**: Draft

---

## 文档结构

- [Part 1: 系统定位与核心架构](#part-1-系统定位与核心架构)
- [Part 2: 核心模块设计](#part-2-核心模块设计)
- [Part 3: strategy_core + DSL + 回测引擎设计](#part-3-strategy_core--dsl--回测引擎设计)
- [Part 4: 数据适配层 + Web 页面设计](#part-4-数据适配层--web-页面设计)
- [Part 5: 实现路径和里程碑](#part-5-实现路径和里程碑)

---

## 设计原则

1. **LLM 不产信号、不算盈亏、不决策买卖**：策略信号、成交假设、盈亏计算全部由 `strategy_core` 代码规则完成
2. **样本外检验**：假设生成用的数据区间 ≠ 最终判定用的回测区间
3. **A 股约束从第一天写死**：T+1、涨跌停、停牌、流动性、100 股整数手
4. **数据质量严格标记**：不推断、不填充、degraded 必须可见
5. **审计可重放**：所有关键操作记录完整 trace，支持 deterministic replay
6. **研究证据与交易信号隔离**：Evidence 只能影响股票池，不能直接生成买卖信号

---

## Part 1: 系统定位与核心架构

### 1.1 系统定位

TraderLens 是一个面向 A 股实盘前验证的策略研究与执行决策工作台，不是自动交易系统。

**核心定位**：
- 终点是提高真实交易胜率和执行质量
- 第一阶段不接券商、不自动下单
- 主角是"策略假设 → 可执行规则 → 信号 → 复盘"
- 机会输出不是泛泛研究结论，而是可验证、可回测、可生成计划信号的规则假设

**MVP V1 边界**：
- 做到主题研究 + 原型回测闭环 + Signal Board
- Signal Board 展示 strategy_core 生成的下一交易日计划信号
- 用户可以据此做模拟盘或小资金实盘前人工决策
- 不做完整执行记录、Review Agent、券商下单、自动交易

**MVP V1 能力定义**：
- 用户可以输入主题，系统生成研究优先级和可验证假设
- 用户可以把假设转成策略配置并回测
- 原型回测通过后，strategy_core 对最新 EOD 数据生成下一交易日计划信号
- 用户可以看到：关注什么、为什么触发、计划动作是什么、什么情况下不执行、风险在哪里
- 系统不自动下单，不承诺收益

### 1.2 核心链路

```
主题输入（市场扫描 / 人工）
  ↓
Serenity 产业链瓶颈分析
  ↓
数据校验 + 硬门槛过滤
  ↓
Evidence Agent 取证 + 证伪
  ↓
人工确认
  ↓
Hypothesis Builder 转规则
  ↓
strategy_core 读配置执行
  ↓
原型回测器
  ↓
回测报告
  ↓
判断：rejected / prototype_passed / needs_review
  ↓
如果 prototype_passed
  ↓
Signal Board / Action Plan
  ↓
展示下一交易日计划信号
```

### 1.3 核心边界（焊死）

- LLM **不生成**交易信号
- LLM **不计算**盈亏
- LLM **不决定**实盘买卖
- 策略信号、成交假设、盈亏计算，全部由 `strategy_core` 代码规则完成
- 机会发现的输出是**可验证假设**，不是"买/不买"
- 样本外检验：假设生成用的数据区间 ≠ 最终判定用的回测区间
- Evidence Agent 是 tool-use loop，不是固定查表流程
- Agent 受 Harness 约束：白名单、步骤数、token budget、schema、可 replay

### 1.4 Signal Board 展示内容

- 股票代码 / 名称
- 策略名称 / 版本
- 当前状态：计划买入 / 计划卖出 / 继续观察 / 暂不操作
- 信号触发日期
- 计划执行日期
- 触发条件
- 入场/出场规则
- 失效条件
- 不可成交处理：涨停、跌停、停牌、流动性不足
- 回测摘要：OOS 表现、最大回撤、交易笔数、数据质量
- 风险状态：市场红黄绿灯

### 1.5 技术架构

| 层 | 选型 | 备注 |
|---|---|---|
| 前端 | Next.js + React + Tailwind | 混合模式：核心页面用表单，研究用对话 |
| 后端 | FastAPI | Python 3.11+ |
| 数据库 | SQLite + WAL | MVP 阶段，后期 PostgreSQL |
| 数据源 | Tushare Pro + 本地缓存 | 数据质量标记 + 退市股票保留 |
| 回测 | Python + pandas 自研事件循环 | 不引入 backtrader/zipline |
| Agent | Anthropic SDK 原生 tool-use loop | 受 Harness 约束（白名单、schema、budget、replay）|
| LLM 并发 | 全局上限 = 2 | 默认串行，全部进任务队列 |
| 策略核心 | `strategy_core/` | 回测/模拟盘/实盘共用的唯一真相源 |

---

## Part 2: 核心模块设计

### 2.1 Serenity 产业链瓶颈分析模块

**定位**：把主题拆成产业链结构，找出更值得验证的瓶颈环节，输出研究优先级和可验证假设草案。

**输入**：
- `theme_name`：主题名称（如"机器人"、"AI 算力"、"低空经济"）
- `background`：用户为什么关注它
- `source_type`：新闻 / 政策 / 板块异动 / 个股异动 / 用户想法
- `research_mode`：quick_scan / standard / deep_research
- `urgency`：普通 / 需要尽快研究
- `notes`：用户的主观问题或假设

**Research Mode 限制**：

```yaml
quick_scan:
  candidate_pool_raw: <= 15
  candidate_shortlist: <= 3
  默认只跑 light_check

standard:
  candidate_pool_raw: <= 30
  candidate_shortlist: <= 5-10
  重点公司可 deep_check

deep_research:
  candidate_pool_raw: <= 50
  candidate_shortlist: <= 10
  需要用户手动确认后才跑 deep_check
```

**工作流程（固定 8 步）**：
1. 主题来源判断：政策推动 / 企业资本开支 / 国产替代 / 消费需求 / 技术升级 / 周期修复
2. 产业链逆向拆解：下游应用 → 系统/整机 → 核心零部件 → 设备 → 材料 → 测试/认证 → 基础设施
3. 瓶颈环节判断：供应商少 / 验证周期长 / 扩产慢 / 技术替代难 / 客户认证严格 / 下游需求能直接传导
4. 候选公司池生成（两级）：
   - `candidate_pool_raw`：根据 research_mode 限制数量
   - `candidate_shortlist`：根据 research_mode 限制数量，经过股票身份校验
5. 初步证据分级：Strong / Medium / Weak / Unknown
6. 标记证据缺口：下一步该查什么
7. 生成可验证假设草案：拆成可规则化部分和不可规则化部分
8. 输出下一步 Evidence Agent 取证任务

**输出 Schema**（示例）：

```yaml
research_mode: standard
demand_driver: 政策推动
value_chain_layers:
  - layer_name: 下游应用
    description: 工业自动化、服务机器人
  - layer_name: 核心零部件
    description: 减速器、伺服电机、控制器

suspected_bottleneck_layers:
  - layer_name: 减速器
    reasoning: 供应商少、验证周期长、客户认证严格

candidate_pool_raw:  # 最多 30 只
  - symbol: 000000
    company_name: XX公司
    chain_layer: 减速器
    match_source: 概念板块
    match_confidence: high

candidate_shortlist:  # 最多 5-10 只
  - symbol: 000000
    company_name: XX公司
    chain_layer: 减速器
    match_confidence: high
    evidence_status: unknown
    evidence_gaps: [收入纯度, 订单, 客户认证]
    needs_evidence_check: deep

hypothesis_draft:
  - statement: 当机器人板块相对强度进前10%，且瓶颈环节公司放量突破60日新高时，进入观察信号
    target_layer: 减速器
    universe_hint:
      type: sector_plus_tags
      sector: 机器人
      chain_layer: 减速器
    entry_rule_candidates:
      - relative_strength_rank <= 10%
      - close >= high_60d
      - volume >= ma_volume_20d * 1.5
    exit_rule_candidates:
      - holding_days >= 10
      - close < ma20
      - loss_pct <= -8%
    risk_filters:
      - market_regime != red
      - not_st
      - not_suspended
      - liquidity_ok
    verification_needed:
      - 收入纯度
      - 订单
      - 客户认证
    unsupported_parts:
      - 订单数据不能直接进入V1策略信号，只能作为取证依据

uncertainty: [瓶颈环节判断需要进一步验证]
evidence_gaps: [收入纯度证据不足]
next_steps: [对shortlist运行Evidence Agent light_check]
```

**实现方式**：
- 前 3 步用 1 次 LLM 调用完成（结构化 prompt + 固定 schema）
- 第 4 步先生成 raw pool，再筛选成 shortlist，数量根据 research_mode 限制
- 候选公司必须来自 Tushare 行业分类 / 概念板块 / 本地标签库
- hypothesis_draft 必须拆成可规则化部分和不可规则化部分

**约束**：
- 不输出买入/卖出建议
- 不输出目标价
- 候选数量严格受 research_mode 控制，防止成本失控

---
### 2.2 Evidence Agent 取证模块

**定位**：对 Serenity 输出的候选公司进行深度取证和主动证伪，不只是补齐证据，还要找反证。

**输入**：
- 候选公司列表（shortlist，3-10 只）
- 待验证问题（Evidence gaps from Serenity）
- 瓶颈环节定义
- 取证深度：light / deep

**工作方式**：
- Tool-use loop，不是固定查表流程
- Agent 根据上一步结果决定下一步调用哪个工具
- 受 Agent Harness 约束
- 分两档：light_check（最多 5 步）/ deep_check（最多 15 步）

**两档取证**：

**light_check（最多 5 步）**：
- 股票身份校验
- 近一年公告关键词
- 基础财务摘要
- 流动性/停牌/ST
- 输出 evidence_level 初评
- 用于快速筛掉蹭概念和明显有问题的公司

**deep_check（最多 15 步）**：
- 只对 shortlist 或用户指定公司运行
- 公告细查、财务质量、同行对照、反证检查
- 输出完整证据包和排雷报告

**工具白名单（5-7 个）**：
1. `get_stock_identity(symbol)` - 公司名、代码、交易所、上市状态、ST/退市/停牌
2. `get_price_history(symbol, start, end, fields, adjust)` - 行情、成交量、涨跌停、停牌
3. `get_financials(symbol, periods, fields)` - 财务数据，必须按 ann_date 对齐
4. `get_announcements(symbol, start, end, keywords)` - 公告、业绩预告、问询函、减持、定增
5. `get_sector_and_peers(symbol, date_range)` - 行业/概念、同板块对照、指数表现
6. `get_money_flow(symbol, start, end)` - 资金数据（可选）
7. `summarize_evidence_pack(inputs)` - 整理成结构化证据包

**Agent Harness 约束**：
- 工具白名单：只能调用以上 7 个工具
- 最大步骤数：light_check = 5 步，deep_check = 15 步
- Token budget：每次 agent run 上限
- 输出 schema：必须返回结构化结果
- 数据来源记录：每次工具调用记录 source、updated_at、quality_status
- 失败处理：不能静默跳过，必须标记 evidence_status = degraded
- 可 replay：保存完整 tool call trace，支持事后审计和重放

**输出 Schema**（示例）：

```yaml
symbol: 000000
company_name: XX公司
check_depth: light

identity_check: 
  status: confirmed
  issues: []

data_quality: ok

evidence_items:
  - type: annual_report
    source: 定期报告
    content_summary: XX收入占比60%
    published_at: 2026-04-20
    retrieved_at: 2026-06-20
    evidence_level: strong
    expiry_days: 180
    stale_after: 2026-10-20
  - type: announcement
    source: 重大合同公告
    content_summary: 与XX客户签订5000万订单
    published_at: 2026-05-15
    retrieved_at: 2026-06-20
    evidence_level: strong
    expiry_days: 90
    stale_after: 2026-08-15

evidence_summary:
  strong: [定期报告显示XX收入占比60%, 重大合同XX]
  medium: [公告提及XX客户认证]
  weak: [互动易回复XX]

counter_evidence:
  - 问询函：XX
  - 减持记录：XX
  - 财务风险：应收账款占比过高

red_flags: []

relation_to_bottleneck:
  confidence: high
  reasoning: 收入纯度高，订单证据充分

evidence_level: strong

missing_evidence: []
next_check: []

pipeline_suggestion:
  suggested_status: hypothesis_candidate
  confidence: high
  reason: 证据充分，可进入策略股票池
  blocking_issues: []
  human_confirmation_required: true

tool_trace: [...]
```

**Evidence 的作用边界**：

**只能影响**：
- 是否进入研究池
- 是否进入策略股票池
- hypothesis 的背景说明
- 后续人工复核问题

**不能影响**：
- 入场信号
- 出场信号
- 盈亏计算
- 仓位变化

**禁止输出**：
- 买入 / 卖出
- 目标价
- 确定性推荐
- 用股价上涨倒推基本面逻辑
- 用互动易或新闻替代公告和财报

---

### 2.3 Forward Candidates 向前跟踪模块

**定位**：Serenity + Evidence 完成后，将值得跟踪的候选固化为 Forward Candidate，记录当时的研究判断、价格快照、证伪条件，定期复盘验证研究能力的 alpha，防止事后解释和改历史理由。

**核心目的**：
- 不是扩大股票池，而是留下"当时系统认为值得跟踪的候选"的证据
- 验证 Serenity/Evidence 到底有没有研究 alpha
- 防止事后归因和过度拟合

**数据流**：

```
Serenity 输出 shortlist (3-5 只)
  ↓
Evidence light_check 初评
  ↓
系统生成 Forward Candidate 草稿
  ↓
用户确认加入 Forward Candidates（人工确认，不自动加入）
  ↓
定期复盘（review_date）
  ↓
更新 latest_review_result / alpha_vs_benchmark / status
```

**关键约束**：
- **人工确认加入**：不自动加入，用户确认相当于打上"当时我认可这个研究判断，愿意向前跟踪"的时间戳
- **版本锁定**：用户确认后，thesis / invalidation_rules / price_snapshot / benchmark 锁定，不允许悄悄改历史
- **历史记录保留**：`removed` 状态不是物理删除，保留记录防止幸存者偏差

**数据结构**：

```yaml
forward_candidate:
  id: str
  date_added: date
  theme_id: str
  theme_name: str
  source_run_id: str  # Serenity run_id
  evidence_pack_id: str  # Evidence run_id
  
  # 基础信息
  symbol: str
  company_name: str
  chain_layer: str  # 产业链层级
  evidence_level: str  # high / medium / low / unknown
  
  # 研究判断（锁定）
  thesis: str  # 当时的研究判断
  invalidation_rules:
    - type: str  # fundamental / event / market
      rule: str
      check_frequency: str  # quarterly / on_announcement / daily
      created_by: str  # serenity / evidence / user
      locked: bool  # 用户确认后锁定
  
  # 价格快照（锁定）
  price_snapshot:
    snapshot_date: date
    open: float
    high: float
    low: float
    close: float  # 后续计算 alpha 的基准
    volume: int64
    amount: float
    market_cap: float | None
    is_limit_up: bool
    is_limit_down: bool
    is_suspended: bool
  
  # Benchmark（锁定）
  benchmark:
    type: str  # index / sector / custom_universe
    code: str
    name: str
    snapshot_value: float  # 加入时 benchmark 的值
  
  # 复盘策略
  review_policy:
    review_date: date  # 下一次复盘日期
    default_review_days: int  # 30 / 60 / 90
    event_triggers:
      - earnings_report
      - major_announcement
      - abnormal_price_move
      - invalidation_rule_triggered
  
  # 跟踪状态
  status: str  # active / converted_to_strategy / downgraded / removed
  latest_review_result: dict | None
  alpha_vs_benchmark: float | None  # 相对 benchmark 的超额收益
  converted_to_strategy_id: str | None
  
  # 审计
  audit:
    created_by: str
    created_at: datetime
    locked_at: datetime  # 用户确认时间
```

**证伪条件（invalidation_rules）生成流程**：

1. **Serenity**：生成主题/产业链层面的证伪条件
   - 示例：`该瓶颈环节被替代` / `下游需求证伪` / `主题热度退潮`

2. **Evidence**：生成公司层面的证伪条件
   - 示例：`收入纯度不足` / `订单不兑现` / `问询函暴露问题` / `财务质量恶化`

3. **用户**：确认最终版本，确认后锁定，不允许悄悄改历史

**证伪条件分类**：

```yaml
invalidation_rules:
  - type: fundamental
    rule: "后续两期财报中，该业务收入或订单证据仍无法确认"
    check_frequency: quarterly
    created_by: evidence
    locked: true
  
  - type: event
    rule: "公告显示相关产品线停产、终止合作或客户认证失败"
    check_frequency: on_announcement
    created_by: evidence
    locked: true
  
  - type: market
    rule: "相对所属主题指数连续20个交易日跑输超过10%"
    check_frequency: daily
    created_by: user
    locked: true
```

**Benchmark 选择规则**：

- **大盘/宽基策略**：沪深300 或 中证500
- **主题策略**：主题指数 / 行业指数 / 自定义板块池
- **小盘风格明显**：中证1000 或自定义候选池等权组合

对 Serenity 主题研究，优先用 `sector` 或 `custom_universe` benchmark。否则很多主题候选跑赢沪深300没有意义，因为整个主题本身可能都涨了。

**复盘策略**：

V1 支持两种复盘触发：
1. **默认固定复盘**：30 / 60 / 90 天
2. **事件触发复盘**：公告、财报、重大异动、证伪条件触发

复盘时只做四件事：
1. 更新 `alpha_vs_benchmark`
2. 检查 `invalidation_rule` 是否触发
3. 更新 `latest_review_result`
4. 决定 `status`：active / converted_to_strategy / downgraded / removed

**不要让 Review 变成重新写一篇研究报告**。Forward Candidates 的复盘是检验当初判断，不是重新找理由。

**状态转换规则**：

| 状态 | 含义 | 触发条件 |
|------|------|----------|
| `active` | 已加入向前跟踪，尚未转策略，也未证伪 | 初始状态 |
| `converted_to_strategy` | 已被用户转成策略假设或股票池的一部分 | 用户在 Hypothesis Builder 中引用该候选 |
| `downgraded` | 证据变弱、alpha显著差、证伪条件部分触发，但仍保留记录 | 证据变弱、blocking_issues 未解决、alpha_vs_benchmark 持续为负、部分证伪条件触发 |
| `removed` | 不再作为有效候选继续跟踪，但历史记录保留 | 核心证伪条件触发、连续两个 review 周期没有修复、确认是蹭概念/业务不相关 |

**转换路径**：

```
active → converted_to_strategy：
  用户在 Hypothesis Builder 中引用该候选，生成策略配置或股票池

active → downgraded：
  证据变弱、blocking_issues 未解决、alpha_vs_benchmark 持续为负、部分证伪条件触发

downgraded → removed：
  核心证伪条件触发，或连续两个 review 周期没有修复，或确认是蹭概念/业务不相关

active → removed：
  身份校验失败、退市/重大风险、用户明确放弃继续跟踪
```

**关键原则**：
- Forward Candidates 不产生交易信号，也不是观察池垃圾桶
- 它是研究能力的向前记分牌
- 必须保留所有历史记录，不能因为 alpha 差就删除（防止幸存者偏差）

---

### 2.4 Hypothesis Builder 转规则模块

**定位**：把 Evidence Agent 的取证结果和可验证假设草案，转成 strategy_core 可执行的 YAML/JSON 配置。

**输入**：
- Serenity 的 hypothesis_draft（已拆分可规则化部分和不可规则化部分）
- Evidence Agent 的 evidence_summary
- 用户补充的策略想法

**工作方式（混合模式）**：

**主路径：结构化表单**
- 页面右侧展示假设草案和证据摘要（只读参考）
- 页面左侧是结构化表单，用户逐项填写：
  - 策略名称
  - 股票池定义（静态列表 / 板块 + 过滤 / shortlist 公司）
  - 入场条件（技术指标组合，从 entry_rule_candidates 选择或自定义）
  - 出场条件（止损 / 时间 / 信号失效，从 exit_rule_candidates 选择或自定义）
  - 风险过滤（市场状态 / 涨跌停 / 流动性）
  - 调仓频率 / 持有周期
  - 成本假设（佣金、印花税、滑点）
  - 样本内/样本外区间
- 表单自动生成 YAML/JSON 配置

**辅助路径：LLM 生成草稿**
- "生成草稿"按钮
- LLM 读取 hypothesis_draft 的可规则化部分，生成一版 YAML/JSON draft
- Draft 回填到结构化表单，用户逐项确认
- 不允许 LLM 直接保存正式策略

**硬约束：研究证据不能直接变成入场条件**

Evidence Agent 的证据（公告、订单、客户认证、财报细节）**只能影响**：
- 是否进入股票池
- hypothesis 的背景说明
- 后续人工复核问题

**第一版不能直接影响**：
- 入场信号（V1 只支持技术指标 + 市场状态）
- 出场信号
- 盈亏计算
- 仓位变化

这能防止系统变成"公告关键词交易器"。

**保存前校验**：
- 字段合法性（strategy_core 是否支持该指标）
- 是否定义股票池、入场条件、出场条件
- 是否设置 T 日信号 / T+1 成交
- 是否设置样本外验证区间
- 是否记录假设来源：人工 / LLM / Evidence Agent / 使用的数据区间
- 入场/出场条件不包含 Evidence 特有的事件条件（公告关键词、订单数据）

**输出**：
```yaml
strategy_name: ...
version: v1
status: draft

hypothesis_source_snapshot:
  source_type: serenity
  source_run_id: ...
  evidence_pack_ids: [...]
  generated_at: YYYY-MM-DD HH:MM:SS
  data_range_used_for_generation:
    start: YYYY-MM-DD
    end: YYYY-MM-DD
  llm_model: claude-sonnet-4
  prompt_version: v1.0

universe: ...
entry_conditions: ...
exit_conditions: ...
risk_filters: ...
cost_assumptions: ...
sample_split:
  in_sample_end: YYYY-MM-DD
  out_of_sample_start: YYYY-MM-DD
```

---

## 2.5 Agent 可靠性补丁：证伪、时间一致性、审计、评测与人工门控

**定位**：这是硬约束，不是后续优化。所有涉及 Serenity、Evidence Agent、Hypothesis Builder、回测和 Signal Board 的模块都必须遵守。

### 2.5.1 kill_criteria：预注册证伪标准

**为什么要做**：

Evidence Agent 不能只是"顺便找找反面证据"。如果同一个 agent 先生成假设，再自己写证伪标准，再自己取证，很容易产生确认偏误。

所以 V1 必须引入**预注册 kill_criteria**。

**kill_criteria 的意思是**：

> 在 Evidence Agent 开始取证前，先写死"出现什么证据，就说明这个候选或假设要降级、剔除或不能进入策略股票池"。

Evidence Agent 的任务不是评价"这家公司好不好"，而是**逐条检查这些 kill_criteria 是否被触发**。

**生成和审核流程**：

```
Serenity / Hypothesis Builder 生成 hypothesis_draft
  ↓
系统自动挂 baseline_kill_criteria
  ↓
LLM 只能追加 theme_specific_kill_criteria，不能删除或修改 baseline
  ↓
criteria_validator.py 做确定性校验
  ↓
Criteria Reviewer Agent 检查是否存在软标准、模糊标准、放水标准
  ↓
用户可在异步队列中批量确认高风险项
  ↓
freeze kill_criteria_snapshot
  ↓
生成 criteria_hash
  ↓
Evidence Agent 才能开始取证
```

**关键约束**：
- kill_criteria 必须在 Evidence run 之前冻结
- Evidence run 开始后不能修改
- 如果要修改，必须生成新的 criteria_version
- 每个 criteria_snapshot 必须保存 hash
- Evidence run 必须引用对应的 criteria_hash

**kill_criteria 分两类**：

**1. code_checkable**：由代码判断，不交给 LLM

适合：
- ST / *ST
- 退市 / 退市风险
- 停牌
- 涨跌停不可成交
- 流动性不足
- 上市天数不足
- 数据质量不足
- 日均成交额不达标

这些必须由 `strategy_core`、`data_quality` 或 `daily_status` 判断。

**2. evidence_checkable**：由 Evidence Agent 调工具查证

适合：
- 公司是否真的属于该产业链环节
- 年报/半年报/公告中是否有相关业务证据
- 是否只是概念板块归类
- 收入纯度是否无法确认
- 是否存在问询函、减持、财务风险、监管风险
- 是否存在业务逻辑反证

**kill_criteria Schema**：

```yaml
kill_criteria_snapshot:
  hypothesis_id: "hypothesis_001"
  criteria_version: "v1"
  frozen_at: "2026-06-21 18:00:00"
  frozen_by: "system/user"
  criteria_hash: "sha256..."
  editable: false

  code_checkable:
    - id: "liquidity_min_amount"
      description: "日均成交额低于策略最低要求，不能进入策略股票池"
      category: "liquidity"
      data_required:
        - "daily_bars.amount"
      lookback_days: 20
      trigger_rule:
        metric: "avg_amount_20d"
        operator: "<"
        threshold: 50000000
      action_on_trigger: "exclude_from_strategy_universe"
      evaluator: "strategy_core"

    - id: "st_or_delisting_risk"
      description: "ST、*ST、退市整理或退市风险标记，不能进入策略股票池"
      category: "tradability"
      data_required:
        - "daily_status.is_st"
        - "stock_identity.current_status"
      trigger_rule:
        any_true:
          - "is_st"
          - "current_status in [delisted, delisting_risk]"
      action_on_trigger: "exclude_from_strategy_universe"
      evaluator: "strategy_core"

  evidence_checkable:
    - id: "no_primary_source_business_evidence"
      description: "公司被归入主题/概念，但公告或财报中找不到该业务明确证据"
      category: "business_exposure"
      data_required:
        - "annual_report"
        - "interim_report"
        - "exchange_announcement"
      trigger_rule:
        condition: "no_primary_source_evidence_found"
        acceptable_sources:
          - "annual_report"
          - "interim_report"
          - "exchange_announcement"
      action_on_trigger: "downgrade_or_exclude"
      evaluator: "evidence_agent"

    - id: "revenue_purity_unverified"
      description: "最近两期定期报告中无法确认该主题相关业务收入或产品归属"
      category: "revenue_purity"
      data_required:
        - "annual_report"
        - "interim_report"
        - "segment_revenue"
      trigger_rule:
        condition: "no_segment_or_product_disclosure_found"
        lookback_reports: 2
      acceptable_sources:
        - "annual_report"
        - "interim_report"
        - "exchange_announcement"
      action_on_trigger: "downgrade_to_research_pool_only"
      evaluator: "evidence_agent"
```

**baseline_kill_criteria**：系统内置，不允许 LLM 删除

```yaml
baseline_kill_criteria:
  code_checkable:
    - st_or_delisting_risk
    - suspended_or_untradable
    - liquidity_below_minimum
    - listed_days_too_short
    - data_quality_insufficient
    - limit_up_buy_unavailable
    - limit_down_sell_unavailable

  evidence_checkable:
    - no_primary_source_business_evidence
    - concept_tag_without_announcement_or_report_support
    - revenue_purity_unverified
    - material_counter_evidence_found
    - regulatory_inquiry_or_financial_red_flag_unresolved
    - major_shareholder_reduction_or_pledge_risk_unresolved
```

Serenity / Hypothesis Builder 只能追加主题特有 kill_criteria，不能删除、替换或放松 baseline。

### 2.5.2 criteria_validator.py：kill_criteria 质量闸

新增：`backend/agents/criteria_validator.py`

每条 kill_criteria 保存前必须通过校验。

**必填字段**：

```yaml
required_fields:
  - id
  - description
  - category
  - data_required
  - trigger_rule
  - action_on_trigger
  - evaluator
  - frozen_before_run
  - criteria_hash
```

**校验规则**：

```yaml
validation_rules:
  - must_have_observable_data_source
  - must_have_trigger_condition
  - must_have_action_on_trigger
  - must_not_use_vague_language
  - must_not_depend_on_future_data
  - must_not_be_editable_after_evidence_run_starts
  - code_checkable_must_not_be_routed_to_llm
```

**不合格表达**（以下表达不能作为有效 kill_criteria）：

```
如果证据明显不足，则降级
如果业务逻辑不清晰，则继续观察
如果风险较大，则不纳入
如果没有足够材料，则谨慎处理
如果市场反馈不好，则降级
```

原因：没有明确数据源、触发条件、阈值或动作。

### 2.5.3 Criteria Reviewer Agent

新增一个轻量角色：`Criteria Reviewer Agent`

**职责**：
- 不支持假设
- 不评价股票好坏
- 只检查 kill_criteria 是否太软、太模糊、不可执行
- 目标是防止假设生成方给自己写"杀不死"的证伪标准

**输入**：

```yaml
hypothesis_draft
baseline_kill_criteria
theme_specific_kill_criteria
criteria_validator_result
```

**输出**：

```yaml
criteria_review:
  status: pass / need_revision / fail
  soft_criteria_found:
    - criteria_id: "..."
      reason: "触发条件过于模糊"
      suggested_fix: "补充具体数据源和触发阈值"
  missing_baseline_criteria:
    - "revenue_purity_unverified"
  final_decision: "can_freeze / cannot_freeze"
```

只有 `status = pass` 才允许 freeze。

### 2.5.4 Evidence Agent 的运行前置条件

Evidence Agent 不能直接跑。必须满足：

```yaml
evidence_run_preconditions:
  - kill_criteria_snapshot.frozen == true
  - criteria_hash exists
  - criteria_validator.status == pass
  - criteria_review.status == pass
  - identity_check.status == confirmed
```

deep_check 更严格：

```yaml
deep_check_preconditions:
  required:
    - light_check_status == passed
    - baseline_kill_criteria_triggered == false
    - identity_check.status == confirmed
    - data_quality != insufficient
```

未通过 light_check 或已触发 baseline kill criteria 的候选，不允许进入 deep_check。

### 2.5.5 Evidence 不能回灌历史回测 universe

**硬边界**：

```
今天取到的 Evidence 不能用于清洗历史回测股票池。
```

历史回测 universe 只能来自：
1. 历史时点可得的股票池
2. 本地标签快照，并记录 snapshot_date
3. 静态列表，但必须记录 universe_snapshot_date

如果静态列表或当前标签快照的生成日期晚于回测起点，则该回测存在前视偏差。

此时必须降级：

```yaml
universe_temporal_check:
  universe_source_type: "static_list"
  universe_snapshot_date: "2026-06-21"
  backtest_start_date: "2024-01-01"

  temporal_status: "contaminated"
  reason: "universe_snapshot_date > backtest_start_date"

  allowed_backtest_level: "prototype_sanity_check_only"
  forbidden_claims:
    - historical_alpha_validated
    - strategy_has_positive_expectancy
    - ready_for_next_stage
```

回测报告必须展示：

```
本次回测使用的股票池构造日期晚于回测起点，因此存在前视/幸存者偏差。
本结果只能作为 prototype sanity check，不能作为策略历史有效性的证据。
```

并写入：

```yaml
survivorship_bias_warning:
  include_delisted: partial / true / false
  universe_temporal_status: clean / contaminated / unknown
  universe_snapshot_date: "YYYY-MM-DD"
  backtest_start_date: "YYYY-MM-DD"
  warning_text: "..."
```

### 2.5.6 任何 filter 都要做时间一致性检查

回测引擎必须检查：

```
任何 filter，只要它的输入数据日期晚于 backtest_start_date，就不允许影响历史回测 universe。
```

适用范围：
- Evidence 过滤
- kill_criteria 过滤
- 本地标签过滤
- 当前板块成分过滤
- 用户今天手工构造的静态列表
- 财务数据过滤
- 概念标签过滤

如果时间不一致，只能用于：
1. 当前研究池
2. 前向 Signal Board
3. prototype_sanity_check

不能用于宣称历史策略有效。

### 2.5.7 evidence_conflict 不是失败，要高亮

不要把 `evidence_conflict` 放入 `degradation_reason`。

证据冲突是研究价值点，不是系统故障。

Schema：

```yaml
evidence_conflicts:
  has_conflict: true
  conflict_items:
    - source_a: "annual_report"
      source_b: "media_report"
      conflict_type: "business_exposure_mismatch"
      description: "年报未披露该业务收入，但媒体称其为核心业务"
  action_required: "human_review"
```

页面上要高亮。

### 2.5.8 run_status / degradation / failure

Agent run 必须明确区分：

```yaml
run_status: success / degraded_success / failed
```

```yaml
degradation_reason:
  - tool_empty_result
  - token_budget_exceeded
  - schema_validation_failed
  - insufficient_candidates
  - data_source_unavailable
  - model_refused_or_invalid_output
```

注意：
- `evidence_conflict` 不属于 degradation_reason
- 冲突单独走 `evidence_conflicts`
- 只找出 2 只候选但 research_mode 要求至少 5 只，应为 `degraded_success`，不能假装成功

### 2.5.9 retry_policy：区分 transient retry 和 repair retry

不能对 schema_validation_failed 盲重试。

Schema：

```yaml
retry_policy:
  transient_retry:
    retry_on:
      - llm_timeout
      - tool_transient_error
    max_retries: 2
    backoff: exponential

  repair_retry:
    retry_on:
      - schema_validation_failed
    max_repairs: 2
    method: feed_validation_error_back_to_model

  no_retry:
    - impossible_task
    - unsupported_data
    - permission_denied
    - budget_exhausted
```

schema 校验失败时，要把校验错误喂回模型做 repair loop。

### 2.5.10 human gate 分级

不要所有动作都卡人工确认。

**auto_pass**：低风险、低成本、只读或草稿动作

```yaml
auto_pass:
  - run_backtest
  - run_light_check
  - save_draft
  - generate_llm_draft
  - save_serenity_draft
```

注意：提交回测是只读动作，不需要 human_required。

**human_review_async**：会改变研究状态，但不直接产生下一交易日计划信号

采用异步批处理队列，不同步阻塞 pipeline。

```yaml
human_review_async:
  - approve_research_pool_candidate
  - run_deep_check
  - save_strategy_yaml_as_draft
  - approve_kill_criteria_snapshot
```

pipeline 跑到安全 checkpoint 后 park，用户之后批量处理。

**human_required_sync**：会影响 Signal Board 或策略状态晋升，必须同步确认

```yaml
human_required_sync:
  - promote_to_prototype_passed
  - enable_signal_board
  - change_strategy_status_to_execution_validating
```

### 2.5.11 deterministic replay vs LLM re-run

必须区分两个概念。

**deterministic replay**：用于代码路径

- strategy_core
- 回测
- DSL 校验
- Signal Board 生成
- 数据质量检查

要求：

```
冻结 YAML + 数据快照 + 配置 hash + 代码版本 → 结果应可复现
```

**LLM re-run**：用于 Agent 路径

- Serenity
- Evidence Agent
- Criteria Reviewer
- Review Agent

LLM re-run 不承诺逐字一致，不承诺完全复现。它只是"在相同上下文下重新跑一次，用于审查和对比"。

并且：

```
LLM re-run 默认使用冻结的工具返回值，不重新访问实时工具。
```

只有用户明确选择 `refresh_data_and_rerun` 才重新取实时数据。此时是一个新的 run，不是 replay。

### 2.5.12 Audit 必须保存工具返回快照

因为 LLM re-run 依赖工具结果。如果只保存 prompt，不保存工具返回值，re-run 没有可比性。

每次 tool call 必须保存：

```yaml
tool_call_snapshot:
  tool_name: "get_announcements"
  tool_args_hash: "sha256..."
  response_body_path: "data/audit/tool_responses/run_001_step_003.json"
  response_hash: "sha256..."
  source: "tushare"
  retrieved_at: "2026-06-21 18:10:00"
  quality_status: "ok"
  schema_version: "v1"
```

LLM trace 必须保存：

```yaml
llm_trace:
  model_provider: "anthropic"
  model_id: "claude-sonnet-4"
  model_version: "..."
  prompt_version: "v1.0"
  tool_spec_version: "v1.0"
  schema_version: "v1.0"
  temperature: 0
  max_tokens: 4000
  input_hash: "sha256..."
  output_hash: "sha256..."
  created_at: "2026-06-21 18:10:00"
```

注意：模型可能被厂商下线，所以真正的存档是冻结 output + trace，而不是"以后还能重新调起来"。

### 2.5.13 Agent output cache

Serenity / Evidence 这类 agent 输出要缓存，避免重复烧 token。

Cache key：

```yaml
agent_output_cache_key:
  theme: "机器人"
  research_mode: "standard"
  data_snapshot_hash: "sha256..."
  model_id: "claude-sonnet-4"
  prompt_version: "v1.0"
  tool_spec_version: "v1.0"
  schema_version: "v1.0"
```

只要其中任何一项变化，就视为新 run。

### 2.5.14 Evidence level 统一口径

Serenity 和 Evidence 必须使用同一套证据分级标准。

```yaml
evidence_level_standard:
  strong:
    - 定期报告
    - 临时公告
    - 交易所文件
    - 官方订单
    - 中标公告
    - 客户认证
    - 项目备案
    - 专利/标准文件

  medium:
    - 可信财经媒体
    - 行业协会资料
    - 公司官网
    - 产品页
    - 可交叉验证的券商/专家资料

  weak:
    - 互动易
    - 社媒
    - KOL
    - 论坛
    - 截图
    - 单纯股价异动
    - 无来源调研
```

禁止：把互动易、KOL、论坛、截图、单纯股价异动当作 strong evidence。

### 2.5.15 Agent Eval Harness

Golden Cases 只覆盖确定性路径，不覆盖 agent 质量。因此需要新增 agent eval harness。

目录：

```
backend/agent_evals/
  serenity_cases/
    case_001_robotics.yaml
    case_002_concept_hype_negative.yaml
    case_003_temporal_leakage.yaml

  evidence_cases/
    case_001_pure_play.yaml
    case_002_concept_hype.yaml
    case_003_conflicting_evidence.yaml
    case_004_missing_data.yaml
    case_005_weak_source_trap.yaml

  judge/
    rubric.yaml
    run_eval.py
```

评测类型必须包含：

```yaml
required_case_types:
  - positive_case
  - concept_hype_negative_case
  - conflicting_evidence_case
  - missing_data_case
  - temporal_leakage_case
  - weak_source_trap_case
```

**Serenity Eval 重点**：
- 是否先排产业链层级，而不是先列股票
- 是否识别瓶颈环节
- 是否限制候选数量
- 是否标出不可规则化部分
- 是否生成 kill_criteria
- 是否避免买卖建议

**Evidence Eval 重点**：
- 是否正确区分 strong / medium / weak
- 是否查了反证
- 是否标出 blocking_issues
- 是否触发应触发的 kill criteria
- 是否没有把新闻/互动易当强证据
- 是否没有把今天证据回灌历史回测

**LLM-as-judge 可以用，但必须有人工作为校准锚**：

```yaml
eval_harness:
  judge_mode: "llm_as_judge"
  human_anchor_cases: true
  min_human_anchor_cases: 20

  judge_calibration:
    metric: "agreement_with_human"
    min_agreement_rate: 0.75
    if_below_threshold: "judge_score_informational_only"
```

注意：
- judge 和被测 agent 尽量不要使用完全相同模型
- 小样本分数只看方向，不用 1-2 分差异卡发布
- 每套 eval 必须有专门让 agent 失败的负例和对抗案例

### 2.5.16 需要新增或调整的工程文件

**建议新增**：

```
backend/agents/criteria_validator.py
backend/agents/criteria_reviewer_agent.py
backend/agents/kill_criteria_schema.py
backend/agents/evidence_level_standard.py
backend/agent_evals/
backend/audit/tool_response_store.py
backend/audit/llm_trace_store.py
backend/audit/replay.py
backend/workflows/human_gate.py
```

**建议调整**：

```
backend/agents/evidence_agent.py
backend/hypotheses/hypothesis_schema.py
backend/backtest/universe.py
backend/backtest/report_generator.py
backend/audit/run_log.py
frontend/app/audit/
frontend/app/tasks/
```

### 2.5.17 验收标准

这部分完成后，至少要能做到：

1. [ ] 每个 hypothesis 在 Evidence 前都有 frozen kill_criteria_snapshot
2. [ ] baseline kill criteria 不能被 LLM 删除
3. [ ] 不合格 kill_criteria 不能进入 Evidence run
4. [ ] code_checkable criteria 不会被路由给 LLM
5. [ ] Evidence 不能回灌历史回测 universe
6. [ ] universe_snapshot_date 晚于 backtest_start_date 时，回测报告自动降级
7. [ ] evidence_conflict 会高亮，而不是被当作失败吞掉
8. [ ] schema_validation_failed 走 repair loop，不盲重试
9. [ ] run_backtest 不需要同步人工确认
10. [ ] promote_to_prototype_passed 和 enable_signal_board 必须人工同步确认
11. [ ] LLM re-run 使用冻结工具返回值
12. [ ] Audit 保存 tool response snapshot、llm trace、hash 和 schema_version
13. [ ] Serenity 和 Evidence 使用统一 evidence_level_standard
14. [ ] deep_check 必须先通过 light_check
15. [ ] agent eval harness 至少有 20 个人工校准案例

---

## Part 3: strategy_core + DSL + 回测引擎设计

由于 Part 3 内容非常详细且包含大量代码示例，已单独保存到 `Part3-Strategy-Core.md`。

核心内容包括：
- Strategy DSL 完整 schema 定义
- strategy_core 模块架构
- 原型回测器事件循环设计
- A 股成交约束实现细节
- 样本内外切分逻辑
- 回测报告 6 块内容设计

详见：`docs/design/Part3-Strategy-Core.md`

---
