# TraderLens

面向 Illya 的单人 A 股投资研究与交易记录 Web 应用，当前产品主线以 ETF 为主。券商交易由 Illya 自行执行；TraderLens 不连接券商下单接口。

## 当前产品入口

以下是当前代码中的页面入口。路由存在不等于该功能已通过 Illya 本人验收。

| 用途 | 页面 |
|---|---|
| 今天与单标的研究 | `/`，研究区位于 `/#research`，可输入股票或 ETF 六位代码并查看带来源和日期的结果 |
| 记录成交 | `/trades/record` |
| 我的持仓 | `/observations` |
| 研究记录 | `/research` 与研究详情页 |
| 策略验证 | `/strategy-validations`；Card 018 的 Card 017 历史结果只读展示已于 2026-10-21 验收，仍在未合并默认分支的独立分支上；不授予策略资格 |

`/themes` 旧主题研究路由仍在代码中，但不是当前导航或主线入口。`/workbench` AI 对话路由保留，暂未放入导航，等待双入口验收。

## 当前交付状态（截至 2026-10-24）

- 阶段 6 累计 **18/20**、剩余 2 张。卡 016、017 仍待 Illya 本人验收；策略资格未授予。追加至 24 张仅为建议，尚未批准。
- 卡 016 最新受保护预检为 run07：A（自主取证链路）通过，B（证据语义质量）未通过，C 部分验证；新闻请求返回 0 行、0 正文。报告及 A/B/C 均待本人验收，质量约束登记为 BACKLOG #32 待排期。
- 卡 017 固定批次的四条路径均独立核账为 `RECONCILED`，仍待本人验收。程序分类为“风险改善伴收益让步”；Arden 建议暂不采用，但这不是 Illya 的正式采用决定，也未授予策略资格。
- 卡 018 于 2026-10-21 经本人确认“重启刷新后正常，卡 018 验收通过”。验收提交 `bf0f6c2062f3ac7187b6aef7fe630c8f419620ad` 位于独立分支 `codex/card018-strategy-validation-results-20261021`，尚未合并默认分支；其能力仅为只读展示卡 017 历史结果。
- BACKLOG #4 模型调用稳定性工作暂缓。#18 已于 2026-10-12 完成静态路径核实；未观察应用运行时连接，正式账本未读取或修改。
- B4 是历史回测正确性验证记录，不代表当前应用验收、策略通过或盈利证明。

当前记录：[总主线计划](TraderLens_MAINLINE_PLAN.md)、[BACKLOG](docs/BACKLOG.md)、[Card016 run07 验证报告](docs/superpowers/plans/2026-10-15-card016-v22-etf-research-agent-verification-report.md)、Card017 任务计划（仅本地，未纳入本次发布；路径 `docs/superpowers/plans/2026-10-20-card017-510880-month-end-ma250.md`）、[Card018 冻结计划与验收状态](docs/superpowers/plans/2026-10-20-card018-strategy-validation-results.md)、[知识收尾记录](docs/verification/2026-10-24-knowledge-closeout.md)、[V2.2 ETF 研究框架](V2.2研究框架.md)。

## 产品边界

- AI 辅助研究与解释；行情、财务、仓位、交易成本、收益和策略资格以可追溯数据及确定性规则为准。
- 计划、模拟成交与实际成交必须区分；未知费用、数据缺口和证据不足必须明示。
- 系统不自动下单，不承诺收益；没有已验证策略时，不应把研究结论包装成买卖许可。

## 项目文档

- [Northstar：产品目标与边界](TraderLens_Northstar.md)
- [产品总主线计划与当前进度](TraderLens_MAINLINE_PLAN.md)
- [BACKLOG：待验收项与阻塞](docs/BACKLOG.md)
- [项目执行规则](AGENTS.md)
- [文档索引与历史验证记录](docs/INDEX.md)
- [Gate001 历史研究报告](docs/verification/GATE001_FINAL_RESEARCH_REPORT.md)
- [B4 历史验证记录](docs/verification/B4_VERIFICATION.md)
