# 阶段 6｜卡 019：510880 最小投资闭环

状态：Illya 于 2026-10-25 本人验收通过，确认“验收完成，没有问题”。阶段 A 已核对，阶段 B 工程检查及阶段 C 浏览器用户路径已完成。卡 019 计为阶段 6 第 19/20 张卡，预算不增加；卡 016/017/018 状态不变，策略资格未授予。

## 1. 任务准入

- Northstar 用户链路：指定 ETF → 研究与证据 → 策略验证 → 入场判断／观察或不交易 → 自主成交记录 → 持仓监控 → 卖出复盘。
- 可验证能力：从 510880 研究页面进入现有策略验证，并看懂“资格未确认／资料不可核，所以观察、不交易”；用户仍可在无策略资格时记录自主成交并查看持仓和复盘。
- 范围：仅 510880 的现有页面和正式业务动作接线、必要的研究缺陷提示、隔离测试标识，以及隔离验证。现有研究语义、资格规则、Card017 结果、成交规则及数据库持久化逻辑不改。
- 冻结验收标准见第 2 节；未经 Illya 本人确认，不标为通过。

## 2. 冻结验收标准

1. 用户从 510880 研究入口进入现有策略验证页，并得到明确的入场判断。复用 Card016 研究和现有资格验证；提示已知研究证据缺陷，不修复研究语义。
2. 资格未确认、状态不可核或没有可用信号时，显示可执行的观察／不交易理由；不创建正式 Action Plan、不授予资格。零验证案例不能只显示空白。
3. 复用现有成交录入和持仓复盘：隔离合成自主买入 → 持仓 → 卖出 → 费用／盈亏复盘。重启隔离后端并刷新页面后，隔离磁盘库记录仍可读。合成数据不得进入正式 LiveTradeDB，也不得被表示为策略驱动的正式模拟交易。
4. 缺数据、缺失或陈旧行情、未知费用和未核分红要明确显示；不造价格或净盈亏，不放松 T+1、停牌、涨跌停和成本规则。
5. 提供 Illya 可操作的 UI 路径和证据。所有验收保持“待本人验收”，直至 Illya 确认。

## 3. 现有能力、来源与缺口

| 位置 | 已核能力 | 卡 019 最小增量 |
|---|---|---|
| frontend/app/page.tsx | 首页已提供 510880 V2.2 研究入口、研究失败提示、“仅研究参考”与本次交易状态。 | 在已有研究结果附近补 510880 策略验证直达链接和基于 run07 的必要证据缺陷提醒；不新增生产历史研究入口。 |
| frontend/app/strategy-validations/page.tsx | 只读展示资格状态；Card017 历史结果与资格状态分区，已有 MA250 结果和限制展示。 | 保留现有 Card017 展示，带入 510880 上下文，增加明确的确定性入场判断和“自主成交另一路径”的入口说明。 |
| frontend/components/StrategyValidationStatusCard.tsx | 已显示 watch/unavailable、不可作为买卖依据；没有创建计划的按钮。 | 复用，不改资格语义。 |
| frontend/components/TopNav.tsx | 已有“策略验证”链接，另有记录成交和持仓入口。 | 保留现有导航；隔离测试环境下增加醒目的隔离数据标识。 |
| backend/api/strategy_validations.py 与 backend/services/strategy_validation_status.py | 验证 API 只读，返回 0 个当前验证案例；固定审计加载器按内容和 SHA 校验并安全失败。 | 不改 API、审计内容、固定哈希或资格规则。 |
| frontend/components/LiveLoopPanel.tsx、frontend/app/trades/record/page.tsx、frontend/app/observations/page.tsx、backend/api/research.py、backend/api/observations.py | 已有自主成交记录、持仓和纪律复盘；卖出须选择现有持仓。 | 复用；不改正式交易路径和账本逻辑。 |

### 资格判断边界

- 本工作副本的策略审计加载器期望 SHA-256 为 db67a92283867f311f5758ccb6e9b18f45d8fdde14980b4e88f87ed1a35be78b；指定审计文件内容 SHA-256 为 b886dd1b4132ac23ac2ccb8a9144a37021b9b1d0a0e1401d498a1968de2b9236，内容状态为 queued:b6_validation_task。现有固定加载器会将这份来源安全降级为 unavailable。这是已知旧投影边界，不在本卡修复。
- Card017 投影明确 formal_qualification=未授予，acceptance_status=待确认。它是独立历史比较，不能替代当前资格或入场信号。
- 因此 UI 文案只能说：“当前未确认 510880 合格策略、没有正式入场信号，资格资料不可核，所以观察／不交易。”不得声称全系统没有合格策略。现有状态源没有可靠的核验时间时，显示“核验时点未知”。

### 历史证据边界

- Card016 run07 报告记录：510880 V2.2 研究链路运行；支持证据 12 个来源 ID；新闻 feed 返回 0 行；最终输出存在收益差被误称跟踪误差、费率比较缺少同类依据、估值说法与缺失分位数冲突等缺陷。首页只补必要提醒，不改研究结论算法。
- 隔离浏览器验收使用既有脱敏响应 D:\TraderLens_validation\card016-20261015\verification\home-preflight-run-07\api-public-response.json，SHA-256 412DE0A1A4B680F47DFFBB2FF1553D62F423602A7A8A3819A956C74AC4B804C7。它只由验收 harness 在内存中注入现有研究 UI，标为“2026-10-16 历史研究回放，研究待核”。不显示 provider attempts、tool IDs 等诊断；不保存新报告，不发真实模型请求。该回放只验证卡 019 UI 接线，不验证今日研究质量或模型稳定性。
- Card017 MA250 协议在原项目路径已存在，SHA-256 为 CC1A313AC30A83AEDE8F96DBF5C89D90A2839BC3C647039D6BADE2F9CB29A8DD，本卡只读，不复制。八份外部 Card017 材料保持原位只读，由现有固定来源加载器核验；不复制或改写。

## 4. 最小实施步骤（原冻结计划；执行记录见第 6、9 节）

1. 在 frontend/app/page.tsx 的现有 510880 结果区添加到 /strategy-validations?symbol=510880.SH 的链接和简短、面向 Illya 的研究限制提醒。保留原有 V2.2 研究请求、失败状态与交易状态。
2. 在 frontend/app/strategy-validations/page.tsx 读取 510880 上下文；根据现有只读资格状态区分 watch、unavailable、载入中和请求失败。当前未确认 510880 合格策略时显示原因、观察／不交易、核验日期未知和“本页未提供正式入场信号”。不在判断区推导全系统资格，也不创建 Action Plan。保留 Card017 历史结果分区。
3. 在 frontend/components/TopNav.tsx 仅当 NEXT_PUBLIC_CARD019_ISOLATED_TEST=1 时显示“2026-10-16 历史研究回放，研究待核 · 合成测试成交 · 不代表实时行情、真实账户或正式模拟结果”。
4. frontend/next.config.js 当前不存在，而 frontend/.next 已存在。新增配置只允许用 CARD019_NEXT_DIST_DIR 环境变量选择独立 distDir，未设置时默认仍为 .next；隔离运行使用此前确认不存在的 .next-card019-20261025，不覆盖现存 .next。该配置只解决本卡验收输出隔离。
5. 扩展 tests/test_strategy_validation_status_ui.py 验证 510880 入口、失效关闭的观察／不交易文案、Card017 分区及无 Action Plan。交易后端不改；使用现有 Card002/行情监控测试覆盖既有规则。
6. 在 D:\TraderLens_validation\card019-20261025\isolated_api.py 建立一次性验收服务 harness，不放入产品路径。服务采用 create_research_app(db=ResearchDB(":memory:"), conversation_mode="deterministic", serenity_execution_mode="stub")，只包含研究、策略验证和观察所需路由，不导入 backend.app.main。
7. 浏览器侧仅拦截 510880 单标的研究 POST，读取上述脱敏 run07 响应并在内存返回；验证、成交和持仓 API 连到隔离 harness。CORS 测试配置仅放行此次选择的 loopback UI origin。
8. 使用单个隔离合成自主买卖记录验证浏览器路径。数据库位于 D:\TraderLens_validation\card019-20261025\live_trade.db；购买和卖出都明确标为隔离测试输入，不产生正式交易或策略信号。

## 5. 隔离、恢复与副作用限制

- 原项目 backend/config/runtime_paths.py 在导入时只执行 DATA_DIR.mkdir(exist_ok=True)；本机 data 目录已存在。它不在模块导入时构造 LiveTradeDB。观察和成交路由在请求时才读取 get_live_trade_db_path 并构造 LiveTradeDB。
- harness 在创建任何客户端前将 get_live_trade_db_path 指向上述隔离数据库，并用 LiveTradeDB 构造器守卫断言路径解析后仍在卡 019 验证目录内；任何默认正式路径立即失败。ResearchDB 显式使用内存库。测试不读、不复制、不挂载、不比较正式 data 内容；不导入会初始化 signal_board/traderlens 默认库的 backend.app.main。
- 运行前只读检查待选 loopback 端口归属，3010 路径禁止使用；不关闭未知进程。专用 API 仅绑定 loopback 和唯一测试 origin。前端以 CARD019_NEXT_DIST_DIR=.next-card019-20261025、NEXT_PUBLIC_CARD019_ISOLATED_TEST=1 和 NEXT_PUBLIC_API_BASE_URL 等进程级测试值运行，不写 .env.local。Next 环境加载器在 NODE_ENV=test 时跳过 .env.local；启动子进程时使用明确的非敏感环境白名单，并启用对该文件的读取拦截。
- 只凭本卡启动时记录的 PID、进程创建时间、可执行文件路径、端口、固定安全启动参数和 harness 哈希识别本卡进程；不读取命令行或环境变量。浏览器流程完成后只停止本卡自有进程，再用同一隔离磁盘库重启并刷新页面。若归属不清或端口不可用，停止 UI 服务动作，不切换正式应用。
- 原项目恢复点：.codex_snapshots/card019_original_scope_20261025/。包含目标文件逐字节前像、Git index 前像及 SHA、目标文件 staged/unstaged patch 和清单。checkpoint manifest SHA-256 为 78FF5460E5ECC53E87B59463B1CE3E7F3DCB0720CAED0740B75F126DECFFF112。目标已有 018/知识收尾 hunk 保持原样。
- 验收前的执行限制为不提交、不推送、不合并。Illya 已于 2026-10-25 本人验收通过；后续仅按本次授权将本卡目标文件提交并推送至独立开发分支，不合并默认分支。

## 6. RED → GREEN 与用户路径验收

阶段 A 已核对后执行了以下前置验证。以下 1–9 项记录首次阶段 C 尝试的历史过程；其中浏览器用户路径、隔离服务重启和本人验收的当前结果见第 9 节。

1. RED：已运行 tests/test_strategy_validation_status_ui.py；新增两项契约分别失败于 510880 链接和隔离标识，既有状态卡测试通过（2 failed, 1 passed）。
2. GREEN：UI 接线已实现；后续按 watch/unavailable/error 的实际渲染证据复核，不以静态字符串测试代替用户路径验证。
3. 类型检查与 Next 编译：隔离 basetemp 下 UI 契约测试 3 passed；tsc --noEmit --incremental false -p frontend/tsconfig.json 退出码 0；Next 14.2.35 使用固定 distDir `.next-card019-20261025` 编译成功并生成 16 个静态页面。frontend/.env.local 存在且未读取；构建进程采用 NODE_ENV=test 和非敏感环境白名单。Next 环境加载源码在 test 模式跳过 `.env.local`；初版读取 guard 的纯字符串 RED 暴露 `.env.local` 匹配缺陷，修正后 `.env*` 路径和内存 sentinel GREEN。构建自动格式化 tsconfig 并附加隔离类型目录，之后已移除附加项并恢复压缩格式；当前 Git 规范化 blob 与 HEAD 相同，文本 diff 为空。Git 状态仍报告 tsconfig M；仅针对该文件的 index stat refresh 被既有 `.git/index.lock` 拒绝，未移除锁或改写 index。构建前像已根据当时终端输出重建为文本证据，非字节级副本。
4. 聚焦业务回归：项目 `.venv` 下、pytest basetemp 位于验证目录的三项现有测试通过：actual 交易类型可登记并复盘、模拟 510880 同日卖出继续受 T+1 阻断、actual 未知费用保持未知（3 passed）。首轮额外同日 actual 边界探针为 1 failed / 2 passed；失败来自 `get_sellable_quantity` 通用可售量检查，该检查不计同日买入。临时测试与首轮输出保存在验证目录，未更改后端，也不将此异常记录边界记作通过。正式交易规则不属于本卡可改范围。
5. 隔离 API 曾由本卡进程 PID 48832 绑定 127.0.0.1:18371，固定 UI Origin 为 127.0.0.1:3000；健康检查证实 ResearchDB 为内存库、正式 LiveTradeDB 构造被守卫阻断、模型调用关闭、行情源禁用，错误 Origin／非 510880 请求被拒绝。run07 页面 RED 后，外部 harness 加入当前 UI 契约的空值适配；旧 API 已按记录停止，新的 API 启动命令被执行策略拒绝。隔离 LiveTradeDB 文件现存于验证目录（86,016 字节，仅核对元数据，未读取内容）。当前没有已核验的验收服务。
6. 浏览器用户路径尚未完成：真实浏览器提交 510880 后出现客户端异常，未到达策略验证、成交、持仓或复盘页面。总控已释放阶段 C，但本轮执行因 API 重启被拒绝而停点。Card017 历史结果是否完整展示来源限制、资格状态是否明确观察／不交易、正式 Action Plan 是否被阻断，均未完成浏览器核验。
7. 重启证明未完成：没有启动新的 API 进程，也未用浏览器验证买卖、持仓、费用状态和复盘跨重启可读。
8. 安全异常浏览器核验未完成：unknown 费用、分红未核、缺失／陈旧行情及 watch/unavailable/API error 三种资格显示，本轮均未逐项走完页面路径。
9. 最终由 Illya 操作并确认 UI 路径；在其确认前汇报为“待验收”。

## 7. 明确不做

- 不修复 BACKLOG #32 的研究语义、模型稳定性、研究持久化、卡 016/017/018 状态或旧审计 SHA。
- 不增加产品历史研究入口、报告存储、策略资格／信号／Action Plan，不做新 ETF、新策略、新数据源、回测或分红覆盖。
- 不把历史回放日期更新成今日，不将合成交易表述成真实成交或正式策略模拟收益。
- 不读取凭据或正式 LiveTradeDB 内容，不连接券商；提交与推送仅按 2026-10-25 本人验收后的授权执行至独立开发分支，不合并默认分支。

## 8. 初次阶段 C 停点与未核边界（历史；当前验收见第 9 节）

以下记录首次停点时的状态；其中“未完成”“没有已核验的验收服务”“尚待验收”及“本轮没有提交或推送”等表述仅指当时状态，不代表当前状态。

- 工程验证状态为“未完成，尚不具备本人验收入口”；本人验收状态继续为“待验收”。前端曾在 127.0.0.1:3000 提供页面，但真实提交后 run07 公共投影缺少五个生产响应字段，触发 `undefined.map` 客户端异常。外部隔离 harness 已加入字段适配并标明顶层投影缺口；此修正未被重新启动的服务加载，未经过浏览器复验。RED 证据见 `D:\TraderLens_validation\card019-20261025\evidence\browser-run07-ui-red.md`。
- 新 API 启动通过 `functions.exec` → `exec_command` 被工具执行策略拒绝；旧 API 与已记录的前端进程已停止。3000/18371 在最后一次端口核对时均无回环监听。此地址不作为 Illya 的验收入口。未生成：该外部文件写入被执行策略拒绝；完整命令及拒绝原文保留在执行对话本轮收尾。
- 隔离 `live_trade.db` 保留于验证目录，当前文件大小 86,016 字节；未读取或删除。合成买入、下一交易日模拟卖出、独立核账及跨进程持久化均未执行。
- 已有通过证据仍限于：UI 契约测试 3 passed、TypeScript 检查退出码 0、Next 构建成功生成 16 个静态页面、三项既有成交回归 3 passed、隔离 API TestClient 的固定回放与 Origin 拒绝检查通过、修正后的 no-env guard 纯字符串及 sentinel 检查通过。真实浏览器端到端未通过，也未宣称今日研究质量或全系统通过。
- 同日 actual 卖出边界探针曾失败：`get_sellable_quantity` 通用可售量检查不计同日买入，导致该笔卖出未登记；保留证据 `D:\TraderLens_validation\card019-20261025\evidence\actual-same-day-sale-boundary.md`。本卡未修改账本规则，也不把该边界包装成所有 actual 异常均可登记。
- 先前一次递归 `Get-ChildItem` 已返回 exit 0、耗时 50.979 秒；是否触及禁入目录或抑制了错误未核。本轮没有重扫或补证。
- `.git/index` SHA-256 仍为恢复点值 `F8C9313F6F54B387DE1F78BED80447957160EBE1AC238F607E29183C604231B2`。本轮没有提交或推送。

## 9. 后续浏览器路径与本人验收（2026-10-25）

- Illya 重启隔离 API 后，在同一浏览器的 `/observations` 页面刷新并读回同一组记录；隔离 API 的 PID 47884 持有 `127.0.0.1:18371`。健康状态确认使用隔离验证目录、ResearchDB 为内存库、正式 LiveTradeDB 构造被阻断、确定性模型 stub／禁用、行情 provider 禁用。隔离前端 PID 11880 持有 3000 端口并留待本人检查。
- 浏览器记录为两笔隔离自主合成交易：买入日志 `log_ddf79f13c548`，日期 2026-10-20，4.000 × 1,000；卖出日志 `log_861f730e45d8`，日期 2026-10-21，4.100 × 1,000；持仓 `pos_99edb543c1fe` 已关闭。共 2 条有效日志、0 条作废、0 个未平仓持仓、1 条已关闭复盘。
- 两笔记录均为 `autonomous_manual` 与 `simulated`，`plan_linked=false`；action_plan_id、execution_card_id、signal_id、capital_context_id 均为空。该路径没有正式 Action Plan 或策略信号。
- 买卖费用各估算 ¥5，确认费用为空，基金印花税为 0；毛收益 +¥100，按估算费用 ¥10 后为 +¥90。该值属于隔离合成记录的估算复盘；分红未核，不代表实际成交或正式策略模拟收益。
- 本人验收原话：“验收完成，没有问题”。验收结论仅适用于本卡冻结范围及上述可见路径；卡 019 不授予策略资格。
- 证据边界：研究内容是 Card016 run07 历史回放，不代表今日研究或实时行情；未配置或验证真实市场 provider，也没有验证 SSE 交易日历。缺失／陈旧行情、停牌／涨跌停等异常成交边界以及每一种 watch／unavailable／API error 状态未逐项进行浏览器验收；未知费用与未核分红仍须按页面所示保持未知。不得把该次验收扩写为上述情形均已通过。
- 后续外部测试入口在路由导入前将 ResearchDB 绑定到内存库，并仅在浏览器内存注入无 token 的脱敏 run07 回放以适配页面响应；修正版外部 harness SHA-256 为 E0FB3C215E7A9FED5861C96EC4551AE997D102452F342ACDE2DB0BB276528B17。本次提交不包含该 harness、隔离测试库、run07 回放文件或 Card017 外部材料；未验证新机器从仓库独立运行。
