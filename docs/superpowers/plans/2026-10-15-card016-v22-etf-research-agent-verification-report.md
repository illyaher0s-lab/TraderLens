## 最新状态（2026-10-16｜run06 与展示修正）

- run06 的唯一真实首页请求返回 HTTP 200、`research_unavailable`、`source_validation_or_model_error`。自动工具选择下观察到两次 `tool_use` 响应；run05 的 HTTP 400 本次未复现。最后诊断为 `ValueError` 且 provider attempt 为 0，具体异常分支未核；最终 `finish_research` 未提交，无 hypothesis、三层报告或研究 sources。
- A｜未通过；B｜未通过；C｜部分验证。失败安全返回且没有升级交易状态，但没有完整可用的 AI 研究报告；Card016 与 A/B/C 待 Illya 本人验收。唯一技术阻塞为最终结构化 `finish_research` 未提交。
- 既有 48 项聚焦测试通过，后端编译/导入及隔离生产构建通过；研究页两段原始 JSON 已改为默认关闭的原生折叠，原始字段保留。当前 SSR 展示脚本与 TypeScript 检查退出码均为 0；未重跑模型或首页。
- Illya 已授权将阶段 014/015/016 当前进度发布到独立开发分支 `codex/etf-research-progress-20261016`；该授权不代表卡通过验收、不允许合并默认分支。以下 run01 内容作为历史记录保留。

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
