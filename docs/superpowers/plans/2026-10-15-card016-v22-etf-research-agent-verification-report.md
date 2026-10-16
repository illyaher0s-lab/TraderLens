## 最新状态（2026-10-16｜run07）

- run07 唯一受保护首页请求返回 HTTP 200、V2.2 `success`。真实轨迹为 `read_etf_evidence`（12 source IDs）→ `search_major_news`（真实请求但 0 行）→ `finish_research`（submitted）；3 次模型调用共 3 provider attempts、0 retry。守卫拦截了非研究 `market-check` API，交易状态保持未评估/无信号。
- A｜自主工具链与三层结构本轮通过。B｜未通过：季度收益差被误写为跟踪误差、费率比较无同类依据、历史估值说法与缺失分位数冲突。C｜部分验证：结构化 finish 和安全边界现场通过，错误/预算路径未现场触发；证据语义质量仍不合格。
- Card016 与 A/B/C 保持“待 Illya 验收”。run07 未改产品代码、未再次请求、未追加测试；下一阻塞是输出证据语义/质量问题。
- Illya 已授权把必要脱敏进度同步到独立开发分支 `codex/etf-research-progress-20261016`；此授权不代表验收通过或允许合并默认分支。

# 阶段 6｜卡 016 真实预检记录

## 范围与结果

- 只执行了冻结的一次首页请求：`510880`、`research_version=v2.2`。响应 HTTP 200，子应用报告版本 `v2.2`，研究状态为 `unavailable`。
- 模型调用 1 次；脱敏记录显示响应已收到并进入解析，失败类别为 `response_schema_or_source_validation_failed`，不是超时。现有脱敏证据没有保留可定位根因的具体校验字段；格式、枚举、来源 ID 等细因均未核。
- `tool_trace=[]`、`news_feed_calls=[]`；没有 `major_news`、`news`、`finish_research` 调用，没有三层 AI 研究结论。Illya 后续确认的 601919.SH 公告读取也未执行，因为该卡的一次真实预检额度已用完；不重发请求、不改走其他调用路径。

## A/B/C

- **A｜未通过。** AI 未执行 `tool_use` 取证或生成三层研究；无新闻引用可核验。
- **B｜整体未通过。** 真实页面清楚显示研究未完成，保留确定性中性参考及“本次未评估交易资格/本次未提供交易信号”。错误降级和信号边界已核；AI 研究结论、理由、反面证据与来源展示未形成。
- **C｜部分验证。** 本次失败安全返回具体失败类别，没有升级交易状态；守卫拦截额外的 `/api/observations/market-check` 请求。主动 `finish_research` 和预算耗尽路径未经过本次运行验证。

## 留存证据

- 摘要：`D:\TraderLens_validation\card016-20261015\verification\home-preflight-run-01\preflight-summary.json`
- 脱敏 API 响应：`D:\TraderLens_validation\card016-20261015\verification\home-preflight-run-01\api-public-response.json`
- 页面可见文字：`D:\TraderLens_validation\card016-20261015\verification\home-preflight-run-01\homepage-visible.txt`
- 页面截图：`D:\TraderLens_validation\card016-20261015\verification\home-preflight-run-01\homepage.png`
- 运行前保护检查的 Playwright harness：`D:\TraderLens_validation\card016-20261015\verification\home-preflight-once-card016.cjs`

## 验收状态

真实运行已确认 V2.2 路由可达，OpenAPI 父 schema 未合并挂载子应用的 schema。唯一剩余阻塞是首轮模型响应的结构/来源校验失败根因未定位。A/B/C 与整卡保持“待验收”，改动未提交、未推送。

## 2026-10-16 离线预算根因修复（未运行真实预检）

- **准入与范围：**Northstar 第 2 节 A（股票/ETF）研究验证链路。目标是让 V2.2 在共享 provider attempt 预算内仍有机会提交结构化 `finish_research`，并在提交失败时保留已有工具轨迹。范围限于 LLMClient attempt 预算、V2.2 Agent 路由/诊断及离线回归；没有运行模型 API、服务、首页、账本或策略。
- **根因：**每次真实 provider attempt（含 timeout retry）共用每循环 3 次上限。旧行为允许非最终调用的 timeout retry 消耗最后一格，之后 Agent 的 `finish_research` 调用在请求前被预算 guard 拒绝；该预算异常没有 `call_diagnostic`，V2.2 catch 又无条件读取 `source_diagnostic.get(...)`，导致二次 `AttributeError`，覆盖原错误并使 API 侧丢失此前工具轨迹。run06 历史 artifact 只证实两次成功诊断共计 3 次 attempts、第三次诊断为 `ValueError`/0 attempts；没有保留工具名、原异常文本或实际执行轨迹，因此这段历史不证明发生了何种具体工具动作。离线假 SDK 回归复现了代码路径。
- **最小修复：**LLMClient 支持为后续调用保留 attempt 槽位；V2.2 普通轮保留 1 次、最终轮保留 0 次。非最终 timeout 的 retry 若会占用保留槽位则停止，并由 Agent 下一轮只暴露 `finish_research`；预算拒绝现在在诊断初始化后记录，已有 timeout/attempt history 保留。V2.2 对无诊断异常采用安全 fallback，投影 `failure_class`、`failure_stage`、`failure_type`，不输出原始异常消息。最终提交超时会返回 unavailable 和现有 `tool_trace`，不再发第四次 provider call，也不伪造 finish。
- **边界保持：**每循环最多 3 次真实 provider attempts、进程并发最多 2、最多 3 个工具动作；工具白名单、只读边界、结构化 finish 要求不变。未生成任何代码报告或替代研究结果。
- **RED：**离线假 SDK 初始回归为 4 failed、1 passed、1 条既有 Starlette deprecation warning。两个预算路由用例和无诊断异常用例复现 `NoneType.get` 二次异常；最终 timeout 用例复现诊断缺失 `failure_stage`；常规 read/news/finish 路径通过。完整脱敏输出：`D:\TraderLens_validation\card016-20261015\verification\offline-budget-fix-red-20261016.txt`（只含离线 fake provider；已替换测试 sentinel/key）。
- **GREEN：**项目 `.venv` 对 `tests/test_card016_etf_research_agent.py`、`tests/test_llm_client_limits.py`、`tests/test_card014_single_security_research.py` 执行 **53 passed**，1 条既有 Starlette `TestClient` deprecation warning；修改目标 `py_compile` 通过，`git diff --check` 退出码 0。没有运行全库测试、前端构建或真实预检。
- **新增回归覆盖：**非最终 timeout 不能花掉 finish 保留槽；首轮 timeout→retry 成功后，剩余一格强制下一轮只调用 finish；已有 read/news/finish 三次 attempts 正常结构化提交；最终 finish 的第 3 次 attempt timeout 后安全返回已有 trace 且无第 4 次 provider 调用；原始异常没有 diagnostic 时仍安全返回并保留 trace。
- **下一次真实预检准入（本轮未执行）：**run06 已消耗卡片原定的一次真实预检额度；需要 Illya 明确新增真实预检额度。随后按现有准入规则正常重启并由 Illya 确认首页关闭，重新只读核验 launcher state、runner 固定无凭据模板哈希及 3000/8010 进程所有权/创建时间，确认运行实例加载本轮源码；仅在该门槛通过后，使用既有 API 白名单做一次精确 `{code:"510880", research_version:"v2.2"}` 请求并阻断其他 API。以上条件本轮均未执行或声称通过。
- **验收状态：**Card016 与 A/B/C 继续“待 Illya 验收”。当前唯一下一阻塞是：真实首页可用性尚未核验，且原预检额度已耗尽；必须先由 Illya 明确新增额度再安排真实运行。


## 2026-10-16 run07 受保护首页预检

- 重新通过版本准入后，仅执行一次 510880/V2.2 研究 POST：HTTP 200、`success`。请求守卫仅放行该研究请求，并实际拦截 `/api/observations/market-check`。
- 工具轨迹：`read_etf_evidence`（12 source IDs）→ `search_major_news`（真实请求，0 行/0 正文）→ `finish_research`（submitted）。3 次模型调用均成功；每次 1 provider attempt、0 retry，共 3 attempts；停止原因为 `finish_research`。交易状态仍为“本次未评估交易资格 / 本次未提供交易信号”。脱敏 API 响应于 15:25:57.544+08 保存，早于 15:25:58.450+08 的首页截图。
- **A｜本轮通过（限自主取证链路）：**假说、只读证据选择、news 请求及三层结构均有现场记录；新闻 feed 为空。
- **B｜未通过：**界面呈现结论与交易状态，但产品层将季度收益差误称跟踪误差；费率“行业低位/成本优势”缺同类比较依据，净资产/份额快照不足以支持“规模稳定”；指数估值“历史可接受”同时标记其历史 PE/PB 分位缺失。
- **C｜部分验证：**主动结构化 finish、工具与 API 守卫及不升级交易状态均实证；错误/预算耗尽路径本次没有现场触发。证据语义问题未通过本轮输出质量核验。
- 卡 016 与 A/B/C 均保持“待 Illya 验收”；没有代码修改、再次请求或新增测试。唯一未解决项是报告证据语义/质量。
- 证据：`D:\TraderLens_validation\card016-20261015\verification\home-preflight-run-07\`；版本准入：`D:\TraderLens_validation\card016-20261015\verification\home-preflight-run-07-version-preflight.json`。
