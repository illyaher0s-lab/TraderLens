# TraderLens MVP V1 设计文档 - 精简框架

## 系统定位
A 股策略验证工作台。不自动下单，输出下一交易日计划信号。
主角是"策略假设 → 可执行规则 → 信号"，不是股票推荐。

## 核心链路
```
主题输入 → Serenity(产业链拆解) → Evidence(取证+证伪) → 人工确认 
→ Hypothesis Builder(转规则) → strategy_core(执行) → 原型回测 
→ 判断(rejected/prototype_passed) → Signal Board(下一交易日计划信号)
```

## 核心边界（焊死）
- LLM **不产信号、不算盈亏、不决策买卖**
- 策略信号/成交/盈亏全部由 `strategy_core` 代码执行
- 样本外检验强制：假设生成区间 ≠ 回测判定区间
- Evidence 只能影响股票池，不能直接生成买卖信号
- A 股约束从第一天写死：T+1、涨跌停、停牌、pending_orders 模式

## 3 个核心模块

### 1. Serenity (产业链瓶颈分析)
- 输入：主题名 + research_mode(quick_scan/standard/deep_research)
- 8步固定流程：主题来源 → 产业链拆解 → 瓶颈判断 → 候选池(raw/shortlist) → 证据分级 → 可验证假设草案
- 输出：candidate_shortlist(3-10只) + hypothesis_draft(可规则化部分+不可规则化部分)
- 约束：候选数量严格受 research_mode 控制

### 2. Evidence Agent (取证+证伪)
- 两档：light_check(5步) / deep_check(15步)
- 工具白名单7个：身份/行情/财务/公告/板块/资金/证据包
- Agent Harness：白名单+步骤数+token budget+schema+可replay
- 输出：evidence_items(含expiry_days) + pipeline_suggestion(含blocking_issues)
- 边界：只影响股票池，不影响入场/出场信号

### 3. Hypothesis Builder (转规则)
- 主路径：结构化表单(股票池/入场/出场/风险/回测配置)
- 辅助：LLM生成草稿 → 回填表单 → 人工确认
- 硬约束：Evidence证据不能直接变入场条件，只能影响股票池
- 输出：YAML策略配置 + hypothesis_source_snapshot(假设来源追踪)

## strategy_core + 回测引擎

### DSL 最小集 (V1)
- 股票池：sector_plus_filters(对象形式)
- 入场：突破/放量/相对强度/均线 + 市场状态
- 出场：止损/时间/信号失效
- 风险：涨跌停/停牌/流动性(用amount)/仓位上限
- 成交：T+1, floor到100股, 佣金/印花税/滑点

### 回测引擎 (pending_orders模式)
```python
pending_orders = []
while current_date <= end_date:
    current_date = next_trading_day()
    execution_data = get_data_on(current_date)  # 当日数据，用于成交
    history_data = get_data_until(current_date)  # 历史数据，用于信号
    
    # T+1 处理上一日订单
    filled, rejected, deferred = simulate_fills(pending_orders, execution_data)
    pending_orders = deferred  # 保留跌停顺延订单
    
    # T 日生成新订单
    signals = strategy_core.generate_signals(current_date, history_data, universe, portfolio)
    new_orders = portfolio.generate_orders(signals, current_date)
    pending_orders.extend(new_orders)
```

### 回测报告 (6块)
1. 概览：backtest_level(prototype_with_constraints), 结论(ready_for_next_stage)
2. 基础指标：收益/回撤/夏普/胜率 + benchmark_return + excess_return
3. 样本内外对比：IS vs OOS + oos_status
4. 交易明细：每笔交易 + signal_date/actual_execution_date
5. 成交约束统计：涨停买不进/跌停卖不出/停牌次数
6. 数据质量报告 + survivorship_bias_warning(退市股票覆盖情况)

## 数据层

### 缓存架构
- **不用pickle**，用 Parquet + SQLite metadata
- 日线：同时保存 raw_price + adj_factor，记录 adjust_snapshot_date
- 拆分：stock_identity(公司身份) vs daily_status(每日ST/停牌/涨跌停)
- 板块：第一版只支持当前快照，回测报告必须标注未来函数风险
- 财务：按ann_date对齐，V1只给Evidence用，不进strategy_core信号
- TTL：按数据类型区分(日线近期1天/历史90天/财务30天/公告7天)
- 引擎：固定用pyarrow

## Web 页面 (8个)

1. **Dashboard**: 市场状态/策略状态/主题数/信号数/最近任务/审计入口
2. **Themes**: 主题列表 + 详情(Serenity输出+Evidence取证)
3. **Strategies**: 策略列表(按状态筛选) + 详情
4. **Hypothesis Builder**: 左侧表单 + 右侧假设草案 + "生成草稿"按钮 + 未取证只能保存draft
5. **Backtest**: 配置表单 + 提交任务
6. **Backtest Report**: 6块内容 + 失败原因标签
7. **Signal Board**: 下一交易日计划信号 + 明确标注"不是实盘建议" + Audit链接
8. **Tasks**: 任务列表(失败原因/产物链接/Audit链接) + 重试/取消
9. **Audit** (MVP必需): LLM trace + tool trace + data snapshot + deterministic replay + LLM re-run

## 实现路径 (12-13周)

### M0 (Week 1): 接口契约 + Golden Cases + 任务队列骨架
验收：schema定义完成 + Golden Cases能复现 + 任务队列可用

### M1 (Week 2-4): 数据层 + Web壳 + strategy_core + 原型回测闭环
并行3轨道：数据层(20只固定股票) || strategy_core+回测 || Web壳
验收：手工YAML → 回测 → 原始JSON报告

### M2 (Week 5-7): 完整回测报告 + OOS + Audit + **Signal Board v0**
验收：6块报告 + Audit可replay + Signal Board能展示下一交易日信号

### M3 (Week 8-9): Serenity + Hypothesis Builder v0 + **Evidence light_check**
验收：主题 → Serenity → Evidence light → Builder → draft策略

### M4 (Week 10-11): Evidence deep_check + Signal Board完整版
验收：完整链路 + Signal Board接入Evidence结果

### M5 (Week 12-13): 收尾 + 降级路径 + 体验优化
验收：你能每天稳定使用

## 明确不做 (V1)
完整EOD模拟盘执行记录 / Review Agent / 券商API / 盘中实时 / 历史时点板块成分 / 基本面策略 / 多策略组合 / 复杂仓位管理 / PDF导出

## 关键修正点 (工程落地)
1. Parquet不用pickle
2. 日线保存raw+adj_factor
3. 停牌不在股票池永久过滤，是每日状态过滤
4. 事件循环用pending_orders模式
5. 流动性用amount不用volume
6. 买入数量floor不用round
7. 成交结果拆成gross_amount/commission/stamp_tax/net_cash_delta
8. 订单拆成signal_date/intended_execution_date/actual_execution_date
9. 基准支持custom
10. result_label(ready_for_next_stage) vs strategy_status(prototype_passed)
11. Signal Board提前到M2
12. Evidence light_check提前到M3
13. 未取证策略不能进prototype_passed

---

**总计**: 约8万字设计文档，84KB，已全部保存到 `D:\Codex\TraderLens\docs\design\`
