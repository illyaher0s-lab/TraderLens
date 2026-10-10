# TraderLens 主线启动盘点｜卡 001

**日期：**2026-10-07　**方式：**只读源码/历史材料核对　**卡账：**已用 1/20，剩余 19。未启动服务、未跑测试、未调用行情或模型接口；当前运行状态与源码/旧证据分列。

| 能力 | 源码事实 | 历史验收证据 | 当前运行/结论 |
|---|---|---|---|
| 页面、Agent、成交记录 | `/workbench` 的聊天走 `/api/agent/workbench/message`；`LiveLoopPanel` 另走 `/execution-feedback`。Agent handler 写 `LiveTradeDB`，页面专用端点写 `db.conn`，代码路径不同；Agent 路径还生成随机 Action Plan 等关联 ID。见 `frontend/components/LiveLoopPanel.tsx:61-77`、`backend/api/research.py:1397-1454,1997-2053`、`backend/api/workbench_execution_feedback.py:108-109,148-197`、`backend/api/observations.py:27-42`。 | 2026-07-09 有 Workbench DOM、买卖请求和复盘 API 记录（`p2-1a-*`、`p2-1d-*`）；相关测试文件存在，但本卡未运行，也未核到当前通过记录。 | 3000/3001/8010 无监听。真实 Agent 当前链未验证；源码不足以证明页面与 Agent 共用记录。**阶段 1 阻塞：成交入口未共用可信、规范的成交动作/记录。** |
| 持仓、行情、P&L、复盘 | `LiveTradeDB`/Observation 列表和手动信号入口存在。信号端点用 `entry_price * 1.05` 合成现价，却标为 `market_data_state=ok`（`backend/api/research.py:2292-2370`）。P&L 中费用设为 `None`，计算时按 0 扣且不列为缺失（`backend/services/discipline_review.py:44-89`）。 | 2026-07-09 有一次买卖与复盘输出；该样本费用为空、`missing_fields` 为空，不能证明净收益正确或当前可用。相关测试文件存在，未在本卡运行。 | 当前未验证。合成行情不能作为持仓风险提示；费用未知的 P&L 不能称净收益。属阶段 2 核验项。 |
| 单标的研究与持仓页 | Research 页面/API、证据快照与实时 Tushare 查询代码存在；运行时研究入口和 Agent 同记录未验证。Observation 页面只读最新持仓信号，未见读取/显示该标的最新研究结论。 | Gate001 报告/审计存在，结论为 `insufficient_evidence`；不代表策略通过，也不验证当前研究链路。 | 当前未验证；阶段 3 需将研究结论写入共用记录并在持仓页显示。 |
| 策略验证 | 验证页面是空壳；`GET /api/strategy-validations` 固定返回空案例（`frontend/app/strategy-validations/page.tsx:1-5`、`backend/api/strategy_validations.py:29-49`）。B6/OOS/Gate 源码与测试存在。 | Gate001 最终结论 `insufficient_evidence`；相关历史测试文件存在，本卡未运行。 | 当前无可确认的有效验证入口/通过策略；有限发现准入尚不满足，不启动阶段 5。 |
| 日终行情、分红与提醒 | Research 的真实模式可按需查 Tushare `daily`/`index_daily`；监控适配器未注入 provider 时返回 unavailable（`backend/api/research.py:202-251`、`backend/services/live_market_data.py:20-54`）。持仓信号由 Workbench 按钮手动生成。 | 2026-10-06 Gate001 分红审计为有限范围；来源捕获状态 `mismatch_stop`、研究结论 `insufficient_evidence`。这是审计，不是每日行情/分红更新记录。 | 本次直接调用链未核到每日行情/分红来源的更新责任人、任务、触发方式或最近更新时间；均记“未核”。未见日终自动生成并在下次打开时显示的醒目提醒；只保留应用内可见方案、用户需每日打开，不接企微/邮件。 |

## 卡 001 结论与唯一下一步

**唯一阶段 1 阻塞：**页面专用成交端点与 Agent 成交处理是两条写入路径，且 Agent 侧使用无证据的随机计划/信号关联 ID；目前无法证明两入口写入同一条真实、可追溯的用户成交记录。

**卡 002 最小建议：**只处理阶段 1 成交记录：核实并统一页面与 Agent 到同一规范记录动作/存储；保留用户确认的自主成交，不伪造 Action Plan 关联。先核验当前分歧，再做最小修复；本卡未改代码。

阶段 2 后续需单独核对真实日终数据更新与费用/分红缺口。不要把合成现价或未知费用当成真实行情/净收益。卡 002 尚未开始，须由根决定后再开。
