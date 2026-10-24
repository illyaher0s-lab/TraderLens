# 阶段 6｜卡 018：应用内策略验证结果查询

状态：Illya 于 2026-10-21 确认“重启刷新后正常，卡 018 验收通过”。验收实现提交 `bf0f6c2062f3ac7187b6aef7fe630c8f419620ad` 位于独立分支 `codex/card018-strategy-validation-results-20261021`，未合并默认分支。阶段 6 为 18/20、剩余 2 张；卡 016、017 仍待本人验收，策略资格未授予。

说明：页面中的“待确认”表示卡 017 历史验证成果的本人验收待确认；原报告另写“待 Illya 权衡”，那是研究取舍意见。二者均不表示卡 018 本人应用验收仍待确认。卡 018 验收通过也不等于正式采用该策略或授予资格。冻结计划中的实施前约束仅记录当时状态；提交与推送遵循当前 [AGENTS.md 第 8 节](../../../AGENTS.md) 的长期授权。

## 任务准入

- **Northstar 链路：**B｜提出策略 → 规则化 → 可信验证 → 给出研究层结论。依据 [TraderLens_Northstar.md](../../../TraderLens_Northstar.md) 第 2、3、4 节。
- **当前阻塞：**现有策略验证页仅展示模板匹配后的资格验证案例，卡 017 的固定历史模拟结果未进入应用查询路径。
- **新增能力：**Illya 可从正常应用入口查看已保存的卡 017 比较结果、口径、来源和状态；这不增加策略资格、正式计划或交易能力。
- **范围与投入：**只授权阶段 6 一张卡，无工时上限；不自动扩功能或另开卡。卡 016、017仍待本人验收；卡 018交付后待本人验收。未经 Illya 验收不提交、不推送。

## 冻结范围

复用现有 `/strategy-validations` 页面及只读 `GET /api/strategy-validations`。保留 `validations` / `count` 对“通过已批准模板映射的资格验证案例”的原语义；在响应中增加独立的 `historical_results` 区块，仅含卡 017。该结果不得伪装成资格案例，不使用旧 B4 投影授予资格，也不修复旧 audit hash 投影。

页面通过 TopNav 的“策略验证”入口进入；卡 017 详情同页展开。展示三窗口（full、2018–2019、2020）× 两种费用情景（基础 5bp、压力 10bp），候选与买入持有并列，使用现有窗口汇总与比较表中的值：

- 页面概览明确列出初始本金 5,000 元、评估区间 2018-01-02 至 2020-12-31、以及 V2 佣金模型 `max(成交金额×0.0003, 5元/笔)`（印花税和过户费为 0）；各窗口同时标明实际起止日期。

- 净收益金额：分别呈现实际账户值与 5,000 元等值；不把 2020 两种口径混为一列，也不新算收益率/CAGR。
- 最大回撤金额与比例：金额明确标为协议使用的 5,000 元等值账面 NAV 口径；比例按原文件字段呈现。
- 费用：佣金、滑点及估算期末退出成本，明确实际/等值口径。
- 平均仓位敞口、ΔW、ΔD、六格原始程序分类及协议版本/批次/核账状态。

不展示 `underwater_trading_days` / underwater sessions，避免把谷底至恢复或窗口末的时长误说成“恢复更快”。保留模拟边界：日线开盘成交、前日成交量 10% 容量、基础/压力滑点均是模拟假设；行情状态 `downloaded_unverified_for_research_use`、分红标签 `raw_unverified` 原样保留；2020 不是独立 OOS。V2 正式核账仍为 Decimal precision 28、ROUND_HALF_UP 至 10 位后逐字段精确比较；页面读取已保存数值，不重算或重跑。

Illya 已再次确认核账精度：维持 V2 的 10 位小数逐字段精确比较；旧摘要 6 位仅为展示精度。本卡只展示已保存结果，不修订协议、不重跑卡 017 批次。

展示状态严格分离：

1. **历史程序分类：**“风险改善伴收益让步”（卡 017 六个窗口/费用格的原始分类）。
2. **原报告研究结论：**保留原文“存在收益让步与风险改善的取舍，待 Illya 权衡”，标注来源为卡 017 阶段 C 报告（报告生成时间 `2026-10-20T03:46:17.258489+00:00`）。
3. **独立顾问研究建议：**“Arden：暂不采用”，来源注明为 Illya 在卡 018 启动指令中给出的独立顾问意见；明确这不是 Illya 已作出的正式采用决定，也不是 App 算法结论。与原报告并列，说明来源和时间不同，不改写原报告。
4. **Illya 本人验收：**待确认。
5. **正式策略资格：**未授予，不可生成正式 Action Plan。

## 固定来源与完整性边界

只读文件白名单如下。后端只接受固定 artifact ID，不接受用户提供的路径或文件名；哈希以大写十六进制比较。服务端缺失、损坏、哈希不符、协议/批次/账单交叉绑定不符时，整个 `historical_results` 返回通用 `unavailable`，不返回部分或未经验证的数值。不得在响应、错误、链接、下载头或 UI 中暴露服务器路径。

| 固定 artifact ID | 文件 | 预先固定 SHA-256 |
|---|---|---|
| protocol_v2 | `2026-10-20-card017-510880-month-end-ma250-v2.md` | `CC1A313AC30A83AEDE8F96DBF5C89D90A2839BC3C647039D6BADE2F9CB29A8DD` |
| batch_ledger_json | `batch-001-ledger.json`（模拟账单） | `04A6CDF8D65FF16D580A23FD69868BB9491146BE5854DFF07DD3AFC0155939E3` |
| summary_provenance | `card017-summary-provenance.json` | `A92279959ACFD54A025CE86455C64B571C6EC194E1A0EA4A4103FD455C3D6DBD` |
| window_summary | `card017-window-summary.csv` | `FC4D5191A78FC4E61F17F312FF4263FAF8C3B66CE886BC99B51CE0848A0168AA` |
| comparison | `card017-v2-comparison.csv` | `FC241D008D051B8CA3155FA097C5F1BB0E42C8F515A7CE75453DC23B11B111E7` |
| daily_ledger | `card017-daily-ledger.csv`（模拟账单） | `756ED96A342C2C646DFEE9BCB745BDE943764233CE16CE5F0F7041DA016911F5` |
| attempt_ledger | `card017-attempt-ledger.csv`（模拟账单） | `AF5CC86546EC841C6159BC7DC4BA6CBB3B4AF063E223E501F35566BB85C9CC6E` |
| dividend_ledger | `card017-dividend-ledger.csv`（模拟账单） | `7284B8A54895BB124D236E21B5E8FA33ECC77ED91C30F2F97505FFFBFB339081` |
| review_report | `card017-illya-review.md` | `6297B28DB2C7DFA6FC7B25D243B8C8F9AC571D0E8F861DCA9CFA98B6CFC8BA34` |

上述协议、原始结果、provenance 和 6 个 provenance 输出的当前哈希已逐项只读核对一致；原件不得改写。每个请求对固定白名单逐文件读取一次；校验后的同一份 bytes 用于解析和下载响应，不校验后重新打开文件。Provenance 原文包含本机绝对路径，API 只返回从已验哈希原文提取的安全字段投影（批次、协议/结果哈希、来源标签、核账状态、输出名/哈希/行数、分类、原报告结论），剔除 `result_path`、`summary_builder` 及每项 `outputs.*.path`。Provenance 不提供原文下载；其余允许文件经固定 ID 下载，下载名只用白名单基名，并明确标注为模拟材料。若任何允许文件含服务器路径，则该文件不提供原文下载，只保留安全投影。

服务端来源根目录必须由服务端固定配置，不能由请求参数控制。当前文件位于仓库之外，应用服务身份能否读取尚未验证；阶段 B 必须在最小单机部署下实测。读取失败即 fail closed，不复制原件进仓库、不改原始成果、不读正式交易账本。

## 验收标准

1. Illya 从应用 TopNav 进入验证页，可展开卡 017 并查看六格比较及来源；页面保留现有资格验证区块和原状态投影。
2. 六格数据来自固定文件的哈希验证后解析/安全投影；各金额、比例、成本、仓位、ΔW/ΔD口径清楚。页面不声称策略通过、可交易或独立 OOS。
3. 五种状态分别展示，来源时点不同则标明，不将 Arden 建议写成 Illya 的正式采用决定。
4. 在隔离 fixture 中证明：允许文件缺失/损坏/任一哈希不符时不返回任何历史数值；未列入白名单及路径穿越 artifact ID 被拒；每个固定来源文件只读取一次，哈希校验、解析或下载复用同一字节；响应、错误与 UI 不包含服务器目录；查询不写 signal、Action Plan、正式交易账本或卡 017 原件。
5. 以未获资格信号 ID 请求现有 `GET /api/signals/{id}/action-plan`，服务端仍拒绝（404）；仅隐藏前端按钮不算验收。沿用现有 `get_admitted_signal` / `prototype_passed` 守卫，不修改晋级路径。
6. 应用服务身份可读取已配置目录；正常页面刷新与应用重启后仍能显示同一经校验结果。UI 只走验证查询，不触发研究、行情或监控请求。
7. Illya 本人在正常应用 UI 完成验收；通过之前状态保持“待验收”，不提交/推送。

## 实施接线提要（待总控复核）

- 新增 `backend/services/card017_validation_artifacts.py`：固定 artifact 映射/哈希、只读校验、安全 provenance 投影和 CSV 配对；不含业务资格判定。
- 修改 `backend/api/strategy_validations.py`：在现有只读 GET 中附加 `historical_results`；仅新增固定 artifact ID 的 GET 下载路由。路由不调用 DB、信号、Action Plan 或策略晋级模块。
- 修改 `frontend/app/strategy-validations/page.tsx` 与 `frontend/components/TopNav.tsx`：同页呈现并加正常导航，不新建页面/组件平台；无需改 `frontend/lib/api-client.ts`，当前页面直接请求此 API。
- 新增 `tests/test_card017_validation_artifacts.py`，用隔离临时文件和 stub 验证白名单、哈希失败、路径拒绝、无路径输出及无 DB/写入调用；复用现有未资格 Action Plan 404 测试，不改其守卫。
- `backend/app/main.py` 已挂载验证 router，不需改；不改旧 `strategy_validation_status.py`、signal/action-plan/晋级模块、正式账本、Card017 协议/账单/摘要或报告生成器。
- 分阶段验证：先跑新增 RED→GREEN 聚焦用例；再做 Python 导入/语法与前端类型/构建冒烟；然后在隔离 DB 和本机只读材料目录启动应用，用浏览器从 TopNav 完成 UI 与重启路径。只运行卡 018 聚焦检查，不跑无关历史测试、模型、行情 API 或 Card017 批次。阶段 B 代码与聚焦证据先交总控复核，复核前不启动正常 UI 或应用服务。

### 已知旧测试边界

`tests/test_strategy_validation_status.py` 有既有注入不一致风险：测试 monkeypatch API 模块的 `DEFAULT_AUDIT_PATH`，但生产 wrapper 将 `None` 交给 service，service 自己使用固定默认路径/哈希。若需要运行该旧测试组，先记录基线；失败按既有相关技术债处理，不借卡 018 修改旧路径或 hash。新增接口测试通过替换明确的 loader 依赖或注入隔离 artifact root，不依赖该旧 monkeypatch。

## 历史：阶段 A 保护记录（实施前）

> 以下是 2026-10-20 实施前的保护及停止点记录，不代表当前实现或验收状态。

可恢复检查点：`.codex_snapshots/card018_20261020_stageA/`。含原 Git index、涉及目标文件的字节前像、`TraderLens_MAINLINE_PLAN.md` 原 staged/unstaged patch、基线 status 和排除清单。阶段 A 只新增本卡冻结计划，并在主线计划末尾追加启动登记；原 staged/unstaged 改动保持未暂存/未重排。外部 Card017 原件仅读取并哈希验证，未复制或修改。

阶段 A 停止点：提交此冻结计划供总控内部复核；复核前不实施业务代码或测试。
