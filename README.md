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
| 策略验证 | `/strategy-validations`；入口/引擎仍需按主线计划核验 |

`/themes` 旧主题研究路由仍在代码中，但不是当前导航或主线入口。`/workbench` AI 对话路由保留，暂未放入导航，等待双入口验收。

## 当前交付状态（截至 2026-10-16）

- 阶段 6｜卡 016，累计 **16/20**、剩余 4。卡 013、014 均已终止且本人验收未通过；卡 015 按 Illya 指令停止于新闻接口预检，A 未达到、B/C 未核。
- 卡 016 的 48 项聚焦测试通过，后端编译/导入、隔离生产构建通过；run06 唯一真实首页请求返回 `research_unavailable`。两次 `tool_use` 响应已观察到，但最终 `finish_research` 未提交，三层 AI 研究报告未形成。
- 卡 016：A/B 未通过、C 部分验证；最终失败的精确 ValueError 分支未核。当前没有完整可用的 AI 研究报告，整卡与 A/B/C 均待 Illya 本人验收。JSON 展示修正的 SSR 与 TypeScript 检查通过，不代表研究链路验收通过。
- 当前唯一技术阻塞：`finish_research` 未提交。Illya 已授权将阶段 014/015/016 当前进度发布到独立开发分支 `codex/etf-research-progress-20261016`；这不代表本人验收通过或允许合并默认分支。
- BACKLOG #18 的正式账本路径仍待只读核实。本 README 不代表应用、实时行情或模型调用已在当前环境通过运行验收；核实前不应据此推断可安全连接正式账本。
- B4 是历史回测正确性验证记录，不代表当前应用验收、策略通过或盈利证明。

当前记录：[总主线计划](TraderLens_MAINLINE_PLAN.md)、[Card016 验证报告](docs/superpowers/plans/2026-10-15-card016-v22-etf-research-agent-verification-report.md)、[V2.2 ETF 研究框架](V2.2研究框架.md)。

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
