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
