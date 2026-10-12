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

## 当前交付状态

- 主线计划登记为阶段 6｜卡 013，累计 **13/20**。卡 013 已有实现提交，但 Illya 本人验收仍待完成。
- 卡 014 有单独提交；是否另占 20 卡预算待 Illya 确认，不按卡号推算。
- BACKLOG #18 的正式账本路径仍待只读核实。本 README 不代表应用、实时行情或模型调用已在当前环境通过运行验收；核实前不应据此推断可安全连接正式账本。
- B4 是历史回测正确性验证记录，不代表当前应用验收、策略通过或盈利证明。

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
