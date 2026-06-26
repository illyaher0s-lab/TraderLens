### 2.3 Hypothesis Builder 转规则模块

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
