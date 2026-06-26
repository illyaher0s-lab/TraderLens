# TraderLens MVP V1 设计文档 - 文件索引

## 文档结构

设计文档已按模块拆分为多个文件，便于查阅和维护。

### 主文档

**`MVP-V1-Design.md`** - 主设计文档
- 系统定位与核心架构（Part 1）
- 核心模块设计（Part 2）
  - Serenity 产业链瓶颈分析模块
  - Evidence Agent 取证模块
  - Hypothesis Builder 转规则模块

### 独立模块文档

**`Part3-Strategy-Core.md`** - strategy_core + DSL + 回测引擎设计
- Strategy DSL 完整 schema 定义
- strategy_core 模块架构
- 原型回测器事件循环设计（pending_orders 模式）
- A 股成交约束实现细节
- 回测报告 6 块内容设计

**`Part4-Data-Web.md`** - 数据适配层 + Web 页面设计
- Parquet + SQLite metadata 缓存架构
- stock_identity vs daily_status 拆分
- 日线数据 raw + adj_factor 设计
- 板块成分处理（第一版当前快照）
- Cache TTL 按类型区分
- Web 页面结构（Dashboard、Themes、Strategies、Backtest、Signal Board、Tasks、Audit）
- Audit 页面设计（LLM trace、tool trace、data snapshot、replay）

**`Part5-Milestones.md`** - 实现路径和里程碑
- Milestone 0: 接口契约 + Golden Cases + 任务队列骨架（Week 1）
- Milestone 1: 数据层 + Web 壳 + strategy_core + 原型回测闭环（Week 2-4）
- Milestone 2: 完整回测报告 + OOS + Audit + Signal Board v0（Week 5-7）
- Milestone 3: Serenity + Hypothesis Builder + Evidence light_check（Week 8-9）
- Milestone 4: Evidence deep_check + Signal Board 完整版（Week 10-11）
- Milestone 5: 收尾、降级路径、体验优化（Week 12-13）
- 每个里程碑的详细验收标准
- 明确不做项
- 最大风险和降级方案

**`Part2-Evidence-Agent.md`** - Evidence Agent 详细设计（已合并到主文档）

**`Part2-3-Hypothesis-Builder.md`** - Hypothesis Builder 详细设计（已合并到主文档）

### 已删除的待补充说明

Part 4（数据适配层 + Web 页面设计）和 Part 5（实现路径和里程碑）的详细内容已补充完成。

## 文档使用指南

1. **快速了解系统**：阅读主文档 Part 1（系统定位与核心架构）
2. **理解研究链路**：阅读主文档 Part 2（核心模块设计）
3. **理解回测实现**：阅读 `Part3-Strategy-Core.md`
4. **规划开发路径**：查阅主文档 Part 5 要点或原始 brainstorming 记录

## 关键设计决策

1. **LLM 不产信号、不算盈亏**：strategy_core 是唯一真相源
2. **样本外检验强制执行**：防过拟合
3. **A 股约束从第一天写死**：T+1、涨跌停、停牌、流动性
4. **数据质量严格标记**：不推断、不填充
5. **研究证据与交易信号隔离**：Evidence 只能影响股票池
6. **Audit 可重放**：deterministic replay + LLM re-run
7. **pending_orders 模式**：防结构性未来函数
8. **幸存者偏差警告**：回测报告必须标注退市股票覆盖情况

## 后续工作

- [ ] 补充 Part 4 完整数据适配层设计
- [ ] 补充 Part 5 完整里程碑验收标准
- [ ] 创建 API 契约文档（OpenAPI spec）
- [ ] 创建数据库 schema 文档
- [ ] 创建 Golden Cases 测试用例文档

---

**版本**: V1.0  
**日期**: 2026-06-20  
**作者**: Orion + Illya  
**状态**: Draft - 核心设计已完成，待补充实现细节
