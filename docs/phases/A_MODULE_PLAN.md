# A 模块计划文档

**模块**：选股研究模块（Selection Research Module）  
**产品入口**：`/themes`  
**文档用途**：统一记录 A 模块边界、当前状态、后续实施顺序，以及向 B 模块交付的候选池契约。

---

## 1. 三模块边界

```text
A. 选股研究模块
主题输入 / 市场扫描 / 人工股票
  -> Serenity
  -> 数据校验 + 硬门槛过滤
  -> Evidence Agent
  -> 人工确认
  -> confirmed_candidate_pool

B. 策略验证模块
confirmed_candidate_pool
  -> Hypothesis Builder
  -> strategy_core
  -> 原型回测器
  -> rejected / prototype_passed / needs_review

C. 行动计划模块
prototype_passed
  -> Signal Board / Action Plan
  -> 下一交易日计划信号
```

A 模块只负责形成可信、可审计、可证伪的候选池。B 模块负责把候选转化为可验证的策略假设并回测；C 模块负责把通过验证的策略转化为下一交易日行动计划。

A 模块不得承担 B/C 的职责，也不得提前生成 B/C 的输出。

---

## 2. A 模块目标

A 模块负责把主题或人工输入的股票转化为可审计、可证伪、由用户确认的候选股票池：

```text
主题 / 人工股票输入
  -> 可信数据源核验证券身份
  -> 确定性硬过滤
  -> Serenity 产业链研究
  -> Evidence 来源化证据与反证
  -> ProposedAction 待处理卡片
  -> 用户确认
  -> confirmed_candidate_pool
```

核心原则：

```text
界面可以像对话，但 AI 不驱动业务状态。
AI 只读取、解释、归纳和提出动作。
代码负责核验、约束和写入。
Research Board 是 A 模块候选状态的唯一事实来源。
```

---

### 2.1 A 模块输入

- 人工主题。
- 市场扫描产生的主题或研究方向。
- 人工输入的股票代码。

### 2.2 A 模块唯一出口

```text
confirmed_candidate_pool
```

该候选池是 B 模块 `Hypothesis Builder` 的输入。它不是普通收藏夹，也不是买卖清单。

---

## 3. 范围边界

### 3.1 必须支持

- 创建研究主题，来源包括 `manual_theme`、`manual_stock`、`market_scan`。
- 在 Serenity 运行前人工添加股票。
- 核验 ticker、公司名、交易所、上市状态及身份置信度。
- 执行 ST、停牌、退市、流动性等确定性硬过滤。
- 存储 Serenity 的产业链、瓶颈假设、候选池和证据缺口。
- 存储 Evidence 的支持证据、反证、冲突、时效、来源质量和阻断原因。
- 对话 Agent 读取上下文、调用白名单工具并创建 `ProposedAction`。
- 用户从 Research Board 应用或拒绝待处理动作。
- 生成可查询的 `confirmed_candidate_pool`。
- 确认时冻结研究理由、失效条件、价格快照、基准快照和证据等级。

### 3.2 明确不支持

- Hypothesis Builder、`strategy_core` 和原型回测器。
- `rejected`、`prototype_passed`、`needs_review` 策略验证结论。
- Signal Board、Action Plan 和下一交易日计划信号。
- 买入、卖出、目标价、止损价、推荐、最佳股票或策略排名。
- 仓位比例、资金分配、订单或券商执行。
- LLM 生成交易信号、计算盈亏或决定买卖、仓位。
- Evidence 直接改变入场或出场规则。
- Agent 绕过 reducer 直接修改数据库状态。
- 将当前确认池冒充历史时点股票池进行普通回测。

`Hypothesis Builder`、`strategy_core`、原型回测器和 Signal Board 均不属于 A 模块修改范围。

---

## 4. 当前状态

### 4.1 已完成

- 主题、候选、对话、Serenity、Evidence、动作审计和确认池的基础契约。
- SQLite 持久化、研究 API、主题页面和左右分栏工作区。
- `ProposedAction -> reducer -> DB -> Research Board` 状态写入链路。
- theme 级 `board_version` 乐观并发控制和动作幂等处理。
- Serenity stub 与 Evidence light-check 的结构化接口。
- 真实 LLM 对话模式与确定性测试模式。
- 对话工具白名单及 ticker 核验后再提出新增候选的流程。
- LLM API Key 与 Tushare Token 已移出源码，只从环境或显式参数读取。
- 缺少真实模式凭据时明确失败，不静默回退为假研究。
- 测试使用 Fake LLM / Fake Tushare 客户端，可离线运行。
- `verification_id` 信任链：
  - `verify_ticker()` 生成并持久化有时效的核验记录。
  - `propose_add_candidate` 必须提交有效 `verification_id`。
  - 公司名来自核验记录，不采信 LLM 输入。
  - 无效、过期或 symbol 不匹配的核验记录会被拒绝。
- `confirmed_candidate_pool` 为 forward-only，并保存快照日期。

### 4.2 尚未完成

当前框架与安全护栏基本成立，但真实研究能力仍不完整：

1. Evidence API 仍存在硬编码的“默认通过”过滤数据。
2. Evidence 数据工具尚未补齐：
   - `get_financials`
   - `get_announcements`
   - `get_sector_and_peers`
   - 可选的 `get_money_flow`
3. `EvidenceItem` 尚需完整支持 `source_type` 与 `source_quality`。
4. Evidence Agent 尚未形成“只能归纳工具结果、不能创造事实”的完整执行链。
5. Serenity 仍是 stub，不是真实的目标驱动研究 Agent。
6. 自动市场扫描和可信候选生成尚未实现。

因此当前状态应表述为：

```text
研究框架、状态边界和 ticker 信任链：已完成。
来源化 Evidence 与真实 Serenity 研究：未完成。
```

---

## 5. A1：Ticker Verification 候选准入契约

Ticker verification 不是新增能力。`verification_id` 信任链已经完成，但它必须作为候选准入和确认池出口的持续强制契约。

```yaml
A_module_candidate_admission:
  required_before_candidate_add:
    - verify_ticker(symbol)
    - verification_id exists
    - verification_id not_expired
    - verification_id matches symbol
    - company_name from verification_record
    - exchange from verification_record
    - listing_status from verification_record

  reject_if:
    - confidence == low
    - status == unknown
    - verification_id missing
    - verification_id expired
    - symbol mismatch
```

实现要求：

- 所有候选股票必须先调用 `verify_ticker(symbol)`。
- `verify_ticker` 只能读取 Tushare、本地可信缓存或其他确定性数据源。
- `verification_id` 必须可持久化、可追溯、有时效且与 symbol 唯一匹配。
- 公司名、交易所和上市状态只能来自 verification record。
- reducer 在应用新增候选动作时再次核验 verification record。
- `confidence == "medium"` 时进入人工复核，不得静默视为高置信身份。
- `confidence == "low"`、`status == "unknown"` 或信任链不完整时直接拒绝。
- LLM 可以建议“查询某股票身份”，但不能确认“某公司代码是 XXX”。

---

## 6. A2：Evidence 必须来源化

这是 A 模块当前最高优先级。没有来源化 Evidence，B 模块得到的仍然可能是脏候选池。

`EvidenceItem` 目标契约：

```yaml
EvidenceItem:
  source: string
  source_type: announcement | financial_report | prospectus | interaction_platform | news | social_media | unknown
  source_quality: first_hand | second_hand | weak
  published_at: date | null
  retrieved_at: datetime
  expiry_days: int | null
  valid_until: date | null
  description: string
  supports: string[]
  falsifies: string[]
  conflicts: string[]
```

```yaml
evidence_rules:
  - no_source_cannot_support_confirmation
  - weak_source_cannot_be_strong_evidence
  - expired_evidence_must_be_visible
  - unresolved_conflict_blocks_auto_confirmation
  - evidence_must_include_support_and_counter_evidence
```

实现要求：

- Evidence API 删除所有硬编码的默认通过数据。
- 上市、ST、停牌、流动性和价格事实必须来自真实数据源。
- 实现 `get_financials`、`get_announcements` 和 `get_sector_and_peers`。
- 数据缺失时返回 unknown、`None`、空集合或 evidence gap，不得默认通过。
- 每条主张必须能追溯到具体来源。
- 弱来源不得被归类为强证据。
- 过期证据、未解决冲突和缺失的一手来源必须在 Research Board 可见。
- Evidence 必须同时包含支持信息与反证信息。
- LLM 只能总结和分类工具结果，不得创造财务数字、公告、身份或硬过滤结果。
- `baseline_kill_criteria` 与 `kill_criteria_hash` 继续由确定性代码维护。

Evidence Agent 工具白名单：

1. `get_stock_identity`
2. `get_price_history`
3. `get_financials`
4. `get_announcements`
5. `get_sector_and_peers`
6. `get_money_flow`（可选）
7. `summarize_evidence_pack`

工具 1-6 只能返回数据源结果，内部不得调用 LLM。工具 7 只能整理工具 1-6 的结果。

---

## 7. A3：Confirmed Candidate Pool 冻结快照

`confirmed_candidate_pool` 是 A 模块出口，也是 B 模块唯一候选输入。人工确认时必须冻结当时可见的研究事实，防止未来函数和事后改写理由。

```yaml
confirmed_candidate_snapshot:
  symbol: string
  company_name: string
  verification_id: string
  theme_id: string
  thesis: string
  evidence_level: strong | medium | weak | unknown
  evidence_snapshot_ids: []
  invalidation_rules: []
  price_snapshot:
    date: YYYY-MM-DD
    close: number
    volume: number
    amount: number
    is_limit_up: bool
    is_limit_down: bool
    is_suspended: bool
  benchmark_snapshot:
    benchmark_type: index | sector | custom_universe
    benchmark_code: string
    snapshot_value: number
  pool_snapshot_date: YYYY-MM-DD
```

冻结规则：

- `verification_id` 必须有效并与 symbol 匹配。
- `company_name` 必须来自 verification record。
- `evidence_snapshot_ids` 指向确认时使用的不可变 Evidence 快照。
- thesis、evidence level、invalidation rules、price snapshot 和 benchmark snapshot 确认后不得被后续复核覆盖。
- `pool_snapshot_date` 必填。
- 候选池保持 `forward_only = true`。
- B 模块若将候选池用于 `pool_snapshot_date` 之前的历史区间，必须自行降级验证；A 模块只负责暴露快照日期和 forward-only 标记。

研究层面的 `invalidation_rules` 可以包括：

- 公司财报连续两期无法证明该业务收入。
- 公告显示核心产品认证失败。
- 出现重大问询函且未解释清楚。
- 主题瓶颈逻辑被替代路线削弱。

---

## 8. A4：禁止向 B/C 越界

A 模块不得输出：

```yaml
entry_price: 10.20
stop_loss: 8.90
position_pct: 20%
buy_tomorrow: true
```

边界判断：

- “什么事实会推翻研究假设”属于 A。
- “如何编码交易规则并回测”属于 B。
- “下一交易日是否行动、如何行动”属于 C。
- 价格快照属于研究确认时的客观事实，不是入场价。
- benchmark snapshot 属于候选确认基线，不是策略收益目标。

---

## 9. 不可违反的公共约束

### 9.1 状态写入边界

- `ProposedAction -> reducer -> Research Board` 是唯一业务状态写入路径。
- LLM 永不直接新增、确认、拒绝或重新打开候选。
- Chat 可以说“已创建待处理动作”，不能在动作应用前说“已添加”或“已确认”。
- Research Board 从数据库重新加载后的候选状态是 A 模块唯一事实。
- LangGraph 如被引入，只能作为 Agent Harness，不得成为业务状态机。

### 9.2 A 模块行为边界

- LLM 不产交易信号、不计算盈亏、不决定买卖、止损或仓位。
- Evidence 只能影响候选池，不能影响确定性的入场或出场逻辑。
- A 模块只向 B 模块交付冻结候选快照，不调用 `strategy_core` 或回测器。
- A 模块不生成 Signal Board 或下一交易日动作。
- Research Board 与 C 模块的 Signal Board 是两个不同组件；前者管理候选研究状态，后者管理行动计划。

### 9.3 确定性事实边界

凡是能够从数据源取得的事实，都不得由 LLM 断言，包括：

- ticker、公司名、交易所。
- 上市、退市、停牌、ST、收购、私有化状态。
- 流动性、价格、成交量和涨跌停状态。
- 营收、净利润、ROE、负债率等财务数字。
- 公告标题、发布日期和公告编号。

这些字段必须来自确定性工具或数据源适配层。数据缺失时返回 `None`、空集合或 unknown，不得补写。

### 9.4 保守默认值

以下情况默认停在 `blocked` 或 `needs_evidence`：

- ticker 核验置信度低或身份未解决。
- 所有证据均为弱来源。
- Evidence 只有弱证据。
- 证据冲突未解决。
- 存在硬过滤标记。
- `invalidation_rules` 为空。

需要允许 override 的场景，必须由用户提供明确原因并完整记录操作者、原因和时间；身份无法确认的情况不得通过 override 绕过。

### 9.5 Agent 隔离

- Serenity 与 Evidence 必须是两个独立 Agent。
- 两者不得共享 LLM run context。
- Serenity 负责生成假设；Evidence 负责证据与证伪。
- Criteria Reviewer 必须使用不同于生成方的模型家族。
- Criteria Reviewer 只输出风险 flag，不输出 `approve`、`ready` 或 `pass`。

Criteria Reviewer 至少检查：

- 过软的 kill criteria。
- 证据等级是否相对来源质量虚高。
- 来源冲突。
- 缺少一手来源。
- 未解决的 ticker 身份。

---

## 10. 对话 Agent 工具边界

允许：

- 读取主题、候选、待处理动作、Serenity、Evidence 和确认池。
- 调用 ticker 核验。
- 请求来源化证据摘要。
- 创建 `ProposedAction`。

禁止：

- 任意 SQL 或写句柄。
- 非白名单工具。
- 直接应用动作或改变状态。
- 从用户文本、网页或证据内容中扩展工具权限。

---

## 11. 状态与 reducer 规则

- 新主题的 `board_version = 0`。
- `ProposedAction` 创建时保存当前 theme `board_version`。
- 每次成功应用状态变更后，版本精确增加 1。
- 对话、Serenity、Evidence、校验失败和拒绝待处理动作不增加版本。
- 版本过期的动作必须拒绝。
- 相同 `action_id` 重复应用不得产生重复状态。
- 所有成功、拒绝和校验失败结果均保留审计记录。
- 拒绝、重新打开和 override 必须记录操作者、原因和时间。
- `run_serenity` 与 `run_evidence` 是分析命令，不属于 `ResearchAction`。
- 分析命令可以保存分析产物，但不得暗中改变候选或主题状态。

确认候选前，reducer 至少检查：

- ticker 核验记录有效且身份匹配。
- 硬过滤结果来自真实数据，不是默认值。
- Evidence 来源与质量满足规则。
- 弱证据、冲突和硬过滤的处理符合保守默认值。
- `invalidation_rules` 非空。
- confirmation 快照字段完整。

---

## 12. 后续实施顺序

`verification_id` 信任链已经完成，后续工作不得把它重新列为未实现功能。当前最高优先级是来源化 Evidence 和冻结出口契约。

```text
人工股票输入
  -> 已完成的 verification_id 身份链
  -> 真实硬过滤
  -> 来源化 Evidence
  -> ProposedAction
  -> 用户确认
  -> 冻结的 confirmed_candidate_pool
```

### P0：修复 Evidence 硬过滤并完成来源化

目标：删除 Evidence API 中硬编码的默认通过数据。

- [ ] Evidence 路由调用真实 validator 和数据源。
- [ ] 获取真实上市、ST、停牌和流动性结果。
- [ ] 数据缺失时标记 unknown，不得默认通过。
- [ ] 删除 `is_listed=True`、`is_st=False`、`is_suspended=False` 等假值。
- [ ] 测试证明数据源缺失不会产生安全通过结果。
- [ ] 测试证明 LLM 无权修改硬过滤结果。
- [ ] 实现 `get_financials`、`get_announcements` 和 `get_sector_and_peers`。
- [ ] 统一工具错误、空结果、来源标识和获取时间。
- [ ] 为 `EvidenceItem` 增加 `source_type`、`source_quality`、`supports`、`falsifies` 和 `conflicts`。
- [ ] 只把真实工具结果交给 `summarize_evidence_pack`。
- [ ] 缺失数据返回 unknown 或 gap，不允许 LLM 填充。
- [ ] 全部为弱来源时阻断确认。
- [ ] 来源冲突、证据过期和缺少一手来源在 Research Board 可见。
- [ ] 测试证明 LLM 不能编造财务数字、公告或证券身份。

### P1：冻结 confirmed_candidate_pool 出口

- [ ] reducer 检查 Evidence 等级与来源质量的一致性。
- [ ] 弱证据、冲突、硬过滤和空失效规则按保守默认值处理。
- [ ] 确认时冻结 verification、thesis、invalidation、price、benchmark 和 evidence 快照。
- [ ] 保存 `verification_id` 与 `evidence_snapshot_ids`。
- [ ] price snapshot 保存日期、收盘价、成交量、成交额、涨跌停和停牌状态。
- [ ] benchmark snapshot 保存类型、代码和快照值。
- [ ] forward-only 与 `pool_snapshot_date` 不可被关闭或改写。
- [ ] override 仅用于允许人工承担的风险，不用于绕过身份核验。

### P2：升级真实 Serenity

仅在 P0-P1 完成后开始。

Serenity 必须是目标驱动的 tool-use Agent，而不是固定步骤的 LLM 流水线。它需要：

- 反向拆解下游需求到上游约束。
- 识别供应商数量、扩产速度、认证周期、替代难度和传导关系。
- 审计上市公司、私有公司、子公司、收购或退市公司及无交易标的环节。
- 每个候选进入 shortlist 前完成 ticker 核验。
- 对强候选执行 red-team 证伪。
- 输出研究优先级，不输出投资推荐。
- 对低置信身份、证据不足环节和未检查数据源明确留白。

### P3：Criteria Reviewer

- [ ] 使用与 Serenity / Hypothesis Builder 不同的模型家族。
- [ ] 仅输出结构化风险 flag。
- [ ] 检查软 kill criteria、证据等级虚高、来源冲突、一手来源缺失和身份问题。
- [ ] 不拥有通过权，不直接改变状态。

### P4：自动市场扫描

仅在人工输入纵向链路和真实 Serenity 均通过验收后考虑。扫描结果仍须进入同一契约、核验、Evidence 和人工确认流程。

---

## 13. 测试与验收

### 13.1 必须通过的测试类别

- 契约与持久化。
- ticker 核验及 `verification_id` 信任链。
- 硬过滤与数据缺失保守处理。
- 对话 Agent 工具白名单。
- ProposedAction、幂等、过期版本和审计。
- Evidence 来源、质量、冲突、时效和反证。
- 确认门禁及快照冻结。
- A 到 B 的交接契约不包含买卖、止损、仓位或下一交易日动作。
- Serenity 输出契约与禁止交易语言。
- 前端类型检查及假模式、工具错误、缺少凭据的可见性。

推荐完整验证：

```powershell
node_modules\.bin\tsc.cmd -p frontend --noEmit
.venv\Scripts\python.exe -m unittest discover -s tests
```

### 13.2 最终验收标准

- 人工股票从输入到确认全程使用可信数据和可追溯证据。
- LLM 不能伪造 ticker、公司名、硬过滤结果、财务数字或公告。
- Agent 只能创建待处理动作，不能改变业务状态。
- reducer 是状态修改的唯一门禁。
- Research Board 是 A 模块候选状态的唯一事实来源。
- 弱证据、冲突、过期证据和数据缺失不会被静默放行。
- 确认候选具有有效 verification、完整研究失效规则和冻结快照。
- `confirmed_candidate_pool` 明确为 forward-only。
- A 模块出口可直接供 B 模块读取，但不包含 B/C 决策。
- Serenity 与 Evidence 独立，Criteria Reviewer 不拥有批准权。
- A 模块不生成交易信号、买卖建议、止损、仓位或下一交易日动作，不调用或修改 `strategy_core`。

---

## 14. 自动拒绝条件

出现以下任一情况，停止实现并先修正：

1. LLM 输出未经数据源核验的证券身份或市场事实。
2. Evidence 主张缺少来源。
3. 弱来源被标记为强证据。
4. ticker 核验或 `verification_id` 信任链被绕过。
5. 数据缺失被默认解释为通过。
6. 无失效规则的候选进入确认池。
7. Agent、LangGraph 或分析路由直接写业务状态。
8. Serenity 与 Evidence 合并或共享 LLM 上下文。
9. Criteria Reviewer 与生成方使用同一模型家族或输出批准结论。
10. 固定 LLM 流水线被包装成目标驱动研究 Agent。
11. A 模块输出入场价、止损价、仓位比例或下一交易日动作。
