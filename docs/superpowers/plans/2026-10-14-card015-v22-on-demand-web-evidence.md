# 阶段 6｜卡 015：V2.2 单标的按需外部证据检索与原文阅读

## 任务准入与冻结范围

- 用户链路：在首页输入 510880 → 查看研究判断、支持/反证及来源。
- 新增能力：当 AI 识别到影响判断的关键证据缺口时，优先复用 Illya 称已购买的 Tushare 新闻接口或现有 SSE 官方公告来源，读取最多两条经核验的来源正文，并在现有首页展示来源和实际读取内容。新闻列表、标题或摘要不能冒充原始来源正文。
- 本卡计入阶段 6｜卡 015｜累计 **15/20**，剩余 **5 张卡**。卡 014 已终止且本人验收未通过；不重开、不把其结论或代码历史改写为通过。
- 仅处理现有首页的 510880 单标的研究。先核查 Illya 称已购买的 Tushare 新闻接口，同时评估现有 SSE 公告目录、公告 PDF URL 和可复用的正文读取路径。不默认新增供应商或购买套餐；Tavily 暂缓，既不是唯一前提也未获批准。若现有路径不足，先向 Illya 提出具体现成服务及 key/费用，再决定是否接入。
- 实施可先依据官方 API 契约与 fake focused tests 完成最小接线和边界验证；账户权限及真实响应字段在唯一一次正常首页运行中核验。若实际权限、URL 或正文不可用，必须走 C 的明确缺口分支，A 不通过，不得猜测通过。
- Illya 要求先核现有 Tushare 新闻/SSE 路径。若它们不足以完成 A/B/C，可提出现成搜索服务及新 key/费用供 Illya 决定；Tavily 目前暂缓、未批准，但不是永久禁止或卡 015 的唯一前提。未获其选择前，不实现新供应商接线或索取密钥。
- 投入上限：一次最小实现；语法/编译/导入冒烟；一组聚焦测试；最多一次真实首页研究验证。错误或权限失败按缺口记录，不为“碰运气”重复真实运行。

## 冻结验收标准

**A｜真实来源读取：** AI 在本次 510880 研究中识别出关键证据缺口，主动调用搜索工具，找到并读取至少一条相关、权威、可追溯到原始 URL 的来源正文。只预载 feed、得到标题/列表/摘要或不能确定原始来源的转载内容，不算通过。Tushare 新闻 feed 可补充研究证据，但不自动等于一般网页搜索；专门的 SSE 公告目录只能标作官方公告检索，不能冒充通用网页搜索。

**B｜证据连接：** 研究将来源内容连接到具体假说的支持或反驳。每条记录保留实际类型（feed 内容、摘要或正文摘录）、标题、来源名、原始 URL（如实际返回）、发布时间、文中统计期间（没有则“未知”）、检索时间和相关正文文本。资料缺失/过期只能标记证据缺口，不能充当经济反证；不得强制看多、看空或生成买卖建议。外部文字中的数字只作为未核验来源摘录展示，不创建已验证金融事实、不进入确定性估值或收益计算。

**C｜失败与边界：** 权限拒绝、空结果、正文或 URL 缺失、来源无法核验时，首页明确展示未获得原文及具体缺口；不影响行情、策略、交易、持仓或正式账本。用户可在现有首页查看新证据；不新建新闻数据库、通用搜索框、爬虫平台或全站扫描。

## Tushare 接口盘点（官方文档；账户实授未核）

总控于 2026-10-14 核对 Tushare 官方接口说明。接口名与字段为公开 API 契约，不能证明当前账户具备权限。

| API | 官方契约摘要 | 对本卡的边界 |
|---|---|---|
| `news`（doc143，新闻快讯） | 可取 `content`、`title`、`datetime`；按 `src` 与起止时间过滤。 | 是新闻 feed，不是通用网页搜索；文档字段未提供原始 URL 契约。真实返回是否有 URL、`content` 是快讯正文还是摘要，需经正常路径核实。 |
| `major_news`（doc195，长篇通讯） | `content` 默认不返回；请求字段可用 `title,content,pub_time,src`；最多 400 条；参数为来源和起止时间，未见公开关键词查询参数。 | 是较长新闻内容候选；是否实际返回原文 URL、每条正文是否可单独选取，尚未核验。若一次请求带回大量正文，不能满足“最多读取两条”的上限，不能先取全量再只展示两条。 |
| `cctv_news`（doc154，新闻联播文字稿） | 提供新闻联播文字稿。 | 特定广播文字稿源，不是通用搜索；须核实际字段、来源标识和 URL，不能直接作为任意主题的原始网页。 |
| `anns_d`（doc176，公告列表） | 公告权限单独开通；返回公告元数据和原 PDF URL。 | 不等同新闻权限。项目当前只提取公告元数据；本地源码/依赖中未发现 PDF 正文读取器。现有 SSE 公告目录也只取元数据并标记 `full_text_unavailable`。官方 PDF 是可复用候选，但其可读性必须经现有正常运行路径真实核验；不得凭 URL 认定正文已读取。 |

doc290 另列新闻资讯套餐，年费 1000 元；Illya 表示已购买，**不得建议重复购买**。15000 Tushare 积分与独立新闻接口授权不是同一证明；当前账号是否有上述 endpoint 权限未核。此次不读取 token、环境变量值、账户余额或鉴权响应，不发真实 API 请求。

## 只读能力盘点与可复用边界

| 能力 | 源码证据 | 状态 |
|---|---|---|
| Tushare API 客户端 | `TushareClient.query(api_name, fields, **kwargs)` 可按给定 API 名调用；配置只有既有 token 与单一 `api_url` 路径。 | 可复用客户端代码；不代表账号对 `news`/`major_news`/`cctv_news` 有权限。当前配置值未查看。 |
| 现有新闻调用 | `backend/services/data_tools.py` 目前实现公告 `anns_d`、SSE 公告目录等；本轮代码检索未发现上述三种新闻 API 的接线。 | 无现成新闻接口动作。 |
| Agent 工具调用协议 | `LLMClient.create_message(..., tools=...)` 和 `SerenityAgentRunner` 有服务端工具循环、白名单及工具结果回传。当前工具包括产业链/财务/公告等。 | 协议在代码中；当前模型供应商是否支持/启用该工具协议未在实例中核验。白名单没有新闻 API、网页搜索或正文读取工具。 |
| 现有公告工具 | 白名单 `retrieve_supply_chain` 会用 `DataToolsService` 取财务、公告和行业记录。`anns_d` 记录含标题、日期、URL；SSE 目录记录明确带 `full_text_unavailable`。 | 只能证明有公告元数据路径；不能验证新闻权限或读取公告/网页正文。 |
| 单标的首页路径 | `/api/research/single-security` 的 510880 V2.1 分支读取固定快照，并直接调用 `synthesize_single_security_v21`；该调用没有 LLM tools 参数。首页目前为 510880 发送 `research_version: v2.1`。 | 当前单标的路径没有按需搜索/正文读取。真实首页实例状态未核。 |
| 测试 | `tests/test_data_tools.py`、`tests/test_serenity_tools.py`、`tests/test_serenity_synthesizer.py` 覆盖公告元数据、`anns_d` 字段和 `full_text_unavailable` 缺口；Tushare 客户端测试用 fake provider。 | 本轮仅读取测试；未运行测试；没有新闻 API 的接线或真实权限测试。 |
| PDF 正文读取 | 在本地 `backend`、`tests`、`pyproject.toml`、`uv.lock` 中检索常见 PDF 解析器，没有发现实现/依赖。 | 未发现现成 PDF 正文读取能力；不据此扩建解析器。 |

**结论：** Tushare 新闻 feed 可能是现有账户内的可复用内容源；SSE/`anns_d` 可能提供官方公告原 PDF URL，但都不会自动满足“AI主动搜索 + 权威原始资料正文 + 原始 URL + 每次最多两条正文”。当前主题研究白名单只有 `retrieve_supply_chain`，它取公告元数据，不调用新闻 API、不读取正文；single-security 首页也没有搜索/阅读工具。当前没有 Agent 可实测新闻权限的既有白名单动作。fake focused tests 可以先验证最终接线的确定性边界；真实权限、字段实值、URL 与 PDF 读取能力只在集成后的唯一正常首页运行中核验，不能由代理另起真实客户端或做临时 probe。

## 最小实施方案（接口契约与上限确认后）

1. 保持 V2.1 路径不变；在同一首页研究入口增加独立 V2.2 分支，复用 `ResearchValidator.tushare_client` 与现有 `LLMClient`。不构造第二个真实 Tushare 客户端，不新增临时 HTTP endpoint。
2. 优先复用 Tushare/SSE 现有来源路径，并接入实际白名单搜索工具；SSE 公告目录只作为专门公告搜索。若现有路径没有可读正文，可在本卡内增加完成验收所需的最小 URL/PDF 正文读取能力或复用已安装库，不扩成通用 PDF 平台。服务端每次研究最多发起 3 个搜索、最多读取并传入综合 2 条正文；如何避免 `major_news` 批量响应带回超限正文，作为实现前的设计检查，不能静默扩大或降低上限。
3. 在单标的 V2.2 综合器增加专用白名单工具循环。保留现有工具协议，不把新闻 feed 描述为一般网页搜索；服务端强制限制调用次数，外部文本只作为不可信数据，不能修改系统指令、工具白名单、权限或执行路径。复用现有 LLM 并发 `BoundedSemaphore(2)`，不新增限流器。
4. 将新闻 feed 原始字段与实际正文摘录分开传递/展示。保存本次响应的标题、`src`、时间、实际返回的 URL、摘录类型和检索时间；来源 URL/统计期间缺失时标“未知”。新闻文字中的数值不转成 snapshot fact ID，不用于权威估值或数值计算。
5. 首页显示可读的证据卡片与“feed 摘要 / 提供商正文 / 原文摘录”准确标签、来源、时间和链接；无链接时不得伪装成可核验原文。只在现有首页展示，不建持久化新闻账本。

**预计最小文件范围（实现前按真实接口结果再冻结）：**

- `backend/services/data_tools.py`：优先复用既有公告元数据；只有实际采用 Tushare 新闻 API 时才加一个受限包装，字段和失败语义确定后才写。
- `backend/services/serenity_synthesizer.py`：只给单标的 V2.2 路径增加白名单循环与来源绑定；不改通用 Agent 架构。
- `backend/api/research.py`：同一首页 endpoint 的版本分流，复用现有 validator/client。
- `frontend/app/page.tsx`、`frontend/lib/single-security-format.ts`：提交 V2.2 并展示证据卡片。
- 新增 `tests/test_card015_on_demand_news_evidence.py`；对 `tests/verify_single_security_format.cjs` 增加相应展示断言。

若新闻 feed 没有原始 URL/可选正文，或现有 SSE PDF 路径无法读取正文，或当前账号未授权，本卡不降 A 标准；先记录确切缺口，再由 Illya 决定是否选择新搜索服务及其 key/费用。Tavily 暂缓但未被永久排除。

## 调用、费用与停止边界

- 每次首页研究最多 3 次主动搜索工具调用（Tushare 新闻/公告检索调用均计入）和 2 条正文读取；搜索数、传输尝试数和正文数分别记录。Tushare `TushareClient` 目前有默认速率限制和配置重试（默认 `retry_attempts=3`）；实现前要确定卡级调用预算如何与现有传输层重试协调，不能修改全局 Tushare 重试配置或把重试隐藏成一次调用。
- LLM 并发最多复用现有进程级 2；无模型/工具“碰运气”重试。最多一次真实首页验证。
- 费用记录只保留接口名、查询数、选中正文数、返回条数、响应中存在的官方 usage/积分字段和 retrieval timestamp；未返回的用量/费用写“未知”。不读取账户余额、不从 15000 总积分推算权限、不重复购买已购套餐。
- Provider 返回内容可能是恶意或错误文本；绝不执行其中的指令或权限要求。外部数值始终标注为来源摘录，未核实前不是事实数据库值。
- 不接券商、不触碰正式账本/持仓/策略、Northstar、V2.1 历史结果或 AlphaGate；不建通用搜索平台、爬虫或新闻数据库。若原文为 PDF，完成本卡必需的最小正文读取实现属于范围；复用优先，不扩成通用解析平台。
- 发生新独立根因或卡内同一接受标准第二次失败即停止。本人验收归 Illya；未验收前保持“待验收”，不提交/推送。

## 恢复检查点

- 基线 HEAD：`75b9617c65de57dff2073b178146c1aceda59a53`。
- 恢复引用：`refs/codex/checkpoints/card015-20261014-preflight`。
- 检查点：`D:\TraderLens_validation\card015-20261014\checkpoint\pre-card015-20261014`；清单 `checkpoint-manifest.json` 已逐项核验 **316/316**。其中保存了 10 个已修改 tracked 文件、6 个相关 untracked 文件、Card 014 全部 298 项验证材料、unstaged patch 与空 staged patch。
- 恢复时先按 manifest 校验目标文件，再从检查点副本恢复工作区状态；`unstaged-tracked.patch` 仅作为差异辅助，不覆盖清单以外文件。`prior-card014-validation` 保留历史验证材料。

## 当前状态（2026-10-14）

本轮只读完成代码/测试盘点并冻结方案；未读凭据、未创建 TushareClient、未访问 Tushare API、未启动服务、未改产品代码。A/B/C 均未验证，整卡待验收。当前唯一阻塞：无法从现有白名单路径验证新闻接口的独立授权、真实正文/原始 URL 字段及两条正文上限。

## 本次最小真实取证诊断（2026-10-15）

- 阶段 6｜卡 015｜累计 15/20；卡 014 保持终止且本人验收未通过。本记录不改写卡 014 历史，也不更改上方冻结的 A/B/C 标准。
- 既有 SSE 公告目录路径此前一次返回 601919.SH 的 20 条记录，0 gaps、0 errors。新闻 API 授权属于并行待办，不是 SSE 正文读取的前置条件。
- 标准 `TushareConfig.from_env()` → `TushareClient` 在本次诊断进程初始化为 `missing_configuration`；`major_news`、`news` 均未调用。该结果只描述本诊断进程，不证明账户或其他运行环境未配置，也不是权限拒绝。
- 对目录返回的 SSE 原始地址 `https://static.sse.com.cn/disclosure/listedinfo/announcement/c/new/2026-08-29/601919_20260829_V0B6.pdf` 本轮发出两次请求；第二次仅纠正第一次响应样本输出时的终端编码错误。两次均 HTTP 200、0 跳转、`text/html`。第一次 3,871 bytes，SHA-256 `48419b76c8e3cdd863b5f218baa4ae0aa07b95d39b05e3854a72419d1e76a993`；响应未保存，输出时发生 `UnicodeEncodeError`。第二次 3,872 bytes，SHA-256 `8f420d9c57c52d65e2a902288e46887260286d0a0822efdb520e4d8650824c2c`，原始响应保存在 `D:\TraderLens_validation\card015-20261015\verification\sse-url-read-20261015-02\response.html`。
- 第二次响应原始字节有 gzip magic；离线解压后是脚本 HTML 外壳，没有可见公告正文。访问挑战机制仅为疑似；没有 401/403，没有执行 JS、处理 cookie 或尝试绕过。不能据此断言该 PDF 本身不可读、链接失效或遭遇权限拒绝。本次未取得公告正文。
- 项目 `.venv` 无 `pypdf`，Codex 随附 Python 有该库；曾在项目诊断运行时导入失败（`ModuleNotFoundError`），只定位到运行时不一致，本轮未修复、未安装依赖，也不据此声称 TraderLens 已集成 PDF 阅读。
- 510880 现有快照记录一条巨潮资讯发行人半年报来源：`中远海控2026年半年度报告`，披露日 `2026-08-29`，URL `https://static.cninfo.com.cn/finalpage/2026-08-29/1225531118.PDF`，历史 SHA-256 `0265a4ca61fb24ff15e14b53b258d7febc03bdb7349f379e42e2c28476dd2ff1`。本轮未访问、未读取；它不是本轮新增证据。
- 本次结果：A 未达到（未取得正文，AI 主动取证未运行）；B/C 未核。LLM 调用 0 次、首页验证 0 次；无产品代码、依赖或测试改动。卡 015 保持待验收。
- 停止边界：不再请求该 URL、不抓取替代来源、不处理挑战、不启动产品实现/首页验证；不更改卡 014 冻结结果，不提交或推送。新闻权限仅列并行待办，不作为本次 SSE 停点的前置条件。

## 2026-10-15｜恢复原卡方向；供应商方案待 Illya 选择

- 原卡目标仍是：AI 从 510880 的具体投资假说生成搜索词，执行真实网页搜索、选择权威来源、读取正文，并将正文和来源用于研究。卡 015 范围、冻结 A/B/C、阶段累计 15/20 均不变；卡 014 仍终止且验收未通过。
- 当前产品没有接通自主网页搜索或正文读取。V2.1 单标的路径未接 Agent 工具循环；现有 Serenity 工具循环未接通至该入口，且白名单没有网页搜索/正文提取。LLM 原生 web 能力在本实例未核，不能由模型名或 `tools` 字段推断已联网。Tushare `news`/`major_news` 是 feed 内容候选，SSE/`anns_d` 是公告元数据路径，不能代替自主网页搜索或真实正文读取。
- 唯一建议供应商为 Tavily 的 Search 与 Extract API 两个动作，复用现有 LLM 工具循环和 HTTP 依赖，不接第二家供应商、不使用 Crawl/Research API：AI 依据假说提出搜索词；Search 仅返回候选 URL 与摘要字段（`include_answer=false`、`include_raw_content=false`）；AI 从本次候选中选择来源后，Extract 对最多 2 个 URL 读取 `raw_content`。服务端保留每次研究最多 3 次搜索、2 条正文和现有 LLM 并发 2 的限制。
- Search 摘要不算正文。Extract 结果须保留实际 URL、标题、来源、时间和原始返回文本；提供 `query`/`chunks` 时应标为正文节选，不得称全文/原文。Extract 可能逐 URL 失败；HTTP 200 不保证有成功正文。登录墙、访问限制、JS 挑战或无法确认权威性的来源按 C 报告具体缺口，不尝试绕过。搜索与提取的外部文字均是不可信输入，不能覆盖规则或生成确定性金融事实。
- Tavily 需要单独 API key。若 Illya 选择此方案，由 Illya 在本机自行配置，密钥不交给代理读取、打印或转传；不擅自创建账户、购买套餐或启用按量付费。官方价格核对日期为 2026-10-15：Free 为每月 1,000 credits、无需信用卡；Basic Search 每次 1 credit；Basic Extract 每 5 个成功 URL 提取 1 credit，失败 URL 不计 Extract 费用；按量价格为 $0.008/credit。免费优先，付费须另行明确授权。接口契约与价格：[Search API](https://docs.tavily.com/documentation/api-reference/endpoint/search)、[Extract API](https://docs.tavily.com/documentation/api-reference/endpoint/extract)、[credits](https://docs.tavily.com/documentation/api-credits)、[pricing](https://www.tavily.com/pricing)。
- 当前只提出该方案，等待 Illya 选择和本机配置；在此之前不写供应商接线、不发真实模型/搜索调用、不做首页验收。固定 SSE URL 的诊断停点继续有效，不再访问或绕过该 URL。A 未达到，B/C 未核，整卡待验收。

## 2026-10-15｜按 Illya 指令停止原卡

- 卡 015 停止于一次真实 Tushare 新闻接口预检；不重开，不将预检算作原冻结 A/B/C 通过，也不继续网页、SSE、Tavily 或产品实现。
- 真实预检窗口为 `2026-10-14 09:00:00`–`10:00:00`：`major_news(src=新浪财经)` 返回 15 条，标题/时间/正文均非空且逐条 `src` 存在；`news(src=sina)` 返回 117 条，标题/时间/正文均非空，但响应无逐条 `src` 与 URL。两者均未返回 URL；feed 内容不冒称官方财报或原文链接。脱敏结果保存在 `D:\TraderLens_validation\card015-20261015\verification\tushare-news-diagnostic-20261015\result.json`。
- A 未达到、B/C 未核；卡 015 未获 Illya 本人验收，不宣称完成或通过。之后获准的 ETF Agent 工作另计阶段 6｜卡 016，不改写卡 015 冻结标准和历史证据。
