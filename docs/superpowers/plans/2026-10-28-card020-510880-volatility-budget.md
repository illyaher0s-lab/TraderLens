# 阶段 6｜卡 020：510880 低频波动预算策略

**状态：Illya 于 2026-10-28 按冻结的单策略范围网页验收通过。** 本卡为阶段 6 的第 20/20 张卡；本验收不授予正式交易资格，也不扩展到其他策略或参数。

## 任务准入与冻结范围

- **Northstar 用户链路：** 策略验证闭环：固定策略稿 → 真实 LLM 逐项解析 → 固定输入预检 → 本人确认冻结 → 六路径确定性回测与独立核账 → 持久化查询。
- **新增的可验证能力：** Illya 可在策略验证页提交完整 510880 策略，看到模型来源映射和输入限制，亲自确认冻结后运行六条固定路径，并从保存记录复查结果。
- **范围：** 仅策略 `510880-vol-budget-v1`、协议修订 3、2018-01-02 至 2020-12-31；候选／买入持有／静态半仓 × 基础／压力成本。结果是研究参考，不能授予正式交易资格或生成交易信号。
- **冻结协议 SHA-256：** `969903D59F949DA0024448128404266C0059EA1A7BEF901B6496045BFDDE8D9D`。
- **验收标准：** 固定稿的真实模型解析及逐项引用；固定输入和执行版本预检；用户勾选后不可变冻结；六路径按冻结规则运行并独立核账；分段活动、佣金、滑点、分红权利／到账／应收和结果哈希可核对；同一冻结只允许一个运行；刷新和进程重启后可读取保存结果。策略参数与 R3 判据不在本卡改动范围。

## 本轮改动

- 后端：`backend/api/card020.py`、`backend/api/research.py`、`backend/services/strategy_idea_flow.py`、`backend/services/card020_preflight.py`、`backend/services/card020_store.py`、`backend/services/card020_vol_budget.py`。
- 页面与隔离运行入口：`frontend/app/strategy-validations/page.tsx`、`frontend/next.config.js`、`frontend/tsconfig.card020.json`、`scripts/card020_validation_app.py`、`scripts/card020_validation_launcher.cjs`、`scripts/start-card020-validation.bat`。
- 回归用例：`tests/test_card020_strategy_parser.py`、`tests/test_card020_preflight.py`、`tests/test_card020_persistence.py`、`tests/test_card020_vol_budget.py`、`tests/test_card020_api.py`、`tests/test_card020_validation_app_entrypoint.py`。
- `scripts/card020_validation_app.py` 将根路径 `/` 的研究应用挂载放到 `/health` 路由之后；测试用静态 AST 顺序核对，没有导入真实运行入口或启动服务。
- API 不再把 `run_id` 或其他运行记录字段追加到 runner 已签名的结果体；`run_id` 只保留在外层运行记录。合成 API 用例经 SQLite 写入、读取及重新连接后，使用同一 `_json_sha256` 算法重新计算并匹配结果 SHA-256。
- 启动器用项目已安装的 Next `@next/env` 加载配置，不再使用批处理逐行解析；只设置本卡真实模式、端口、API base 与独立 build 目录。它仅检查既有必需变量 `RESEARCH_LLM_API_KEY`、`TUSHARE_TOKEN` 是否存在，不打印其值。配置的 `TUSHARE_API_URL` 与代理变量保持原样；Tushare 地址沿用现有 `TushareConfig.from_env` 缺省逻辑，启动器不注入、不要求。它先检查端口，不终止已有进程；前端使用独立 `.next-card020-20261027` 和 `tsconfig.card020.json`。Card019 的 `.next-card019-20261025` 配置保持可用。

## 验证记录（2026-10-28）

- 新增健康路由与持久结果哈希回归先按预期失败：健康路由排在根挂载后；保存结果包含了哈希生成之后追加的 `run_id`。最小修正后两项通过。
- Card020 与旧路径定向测试命令：

  ```text
  .venv\Scripts\python.exe -m pytest -q tests\test_card020_strategy_parser.py tests\test_card020_preflight.py tests\test_card020_persistence.py tests\test_card020_vol_budget.py tests\test_card020_api.py tests\test_card020_validation_app_entrypoint.py tests\test_card017_validation_artifacts.py tests\test_strategy_validation_status_ui.py
  ```

  结果：**52 passed，1 条 Starlette/httpx 弃用警告**。卡020六路径合成组合用例覆盖跨期未到账分红、字符串分段投影和独立重算；合成环境断言验证 Tushare 地址、代理及 Card019 环境值原样保留，缺失 Tushare 地址时不新增且仍按生产必需变量检查通过；Card017 历史产物与现有资格状态页定向回归也在本次运行内通过。
- 生产 `.venv` 对本卡后端、研究路由、解析器、隔离入口及测试文件的 `py_compile`：退出码 0。
- 安全导入冒烟：仅导入 Card020 API／服务模块，输出 `Card020 backend imports OK`；没有导入会创建持久库并加载真实研究应用的 `scripts.card020_validation_app`。
- 前端 `tsc --noEmit --project tsconfig.json` 与 `tsc --noEmit --project tsconfig.card020.json`：均退出码 0。
- `node --check scripts/card020_validation_launcher.cjs`：退出码 0。隔离 Next 配置用静态 Node 检查通过；Card019 固定构建目录检查通过。
- 冻结策略文件当前实测哈希与代码常量一致：`969903D59F949DA0024448128404266C0059EA1A7BEF901B6496045BFDDE8D9D`。

以上是 2026-10-28 的代码级验证记录：这些检查本身没有调用真实 LLM、没有运行固定历史批次，也没有建立 HTTP 服务。随后本人网页验收实际完成了真实模型解析、冻结、固定六路径模拟及重启后读回，见下方验收记录。

## 发布前服务启动拒绝记录（2026-10-28 历史）

- 上一轮曾由 `functions.exec` → `tools.exec_command` 尝试一次 PowerShell `Start-Process`，目标是隔离预览 API 和 Next 页面。完整命令及完整原始工具响应在保存记录中不可取得；中间内容已被截断。本记录不重建命令，不把拒绝定性为自动审核。
- 当时可确认的拒绝片段仅为：`CreateProcess`／`Rejected`，结尾可见 `rejected: blocked by policy`。**完整命令：未取得；完整原始错误：未取得。** 此后没有换工具、启动器或路径重试。
- 2026-10-28 当时的总控 Codex 对目标页做只读浏览器导航，返回 `net::ERR_CONNECTION_REFUSED`：`http://127.0.0.1:3000/strategy-validations?symbol=510880.SH`。这是当时没有可连接页面的证据，不是策略或权限拒绝；没有继续探测其他 URL。
- 截至 2026-10-28 的验收记录，临时复制预览目录未纳入产品实现或验收证据，也未由该轮修改或清理。

## 本人网页验收记录（2026-10-28）

以下入口、页面与步骤是 2026-10-28 编制的验收操作说明，作为事前流程记录保留；本人网页验收已完成，结果见本节末。

唯一启动入口：

```text
D:\Codex\TraderLens\scripts\start-card020-validation.bat
```

页面 URL：

```text
http://127.0.0.1:3000/strategy-validations?symbol=510880.SH
```

最短步骤：

1. 手动运行上述批处理入口；启动器只在 8010 和 3000 都空闲时启动。它使用原始项目源码、真实模式配置、持久隔离 ResearchDB `D:\TraderLens_validation\card020-20261027\research.db`，并将 LiveTradeDB 限定在隔离目录。
2. 打开上述 URL。固定修订 3 策略稿会从 API 载入到页面文本框；核对全文后点击“真实模型解析并自动核验输入”。
3. 等待映射和预检完成；查看逐项来源及已披露数据限制。勾选页面确认框，点击“确认并冻结”。
4. 点击“在页面运行固定六路径”，核对类别、独立核账、三窗口成本／分红及六条路径结果。未完成运行前不要重复提交。
5. 刷新页面确认冻结与结果仍显示。再按 Ctrl+C 关闭本启动器，重新运行同一入口并打开相同 URL，确认同一批次和结果可查、不能重跑。

**验收结论：** Illya 于 2026-10-28 明确按原定单策略范围验收卡 020 通过。实际流程完成了真实 LLM 对固定策略稿的解析与 44 项来源核对、本人确认冻结、固定六路径历史模拟，以及应用重启后读回同一冻结版本和同一批次；未运行第二套策略或更换参数。

- **批次结论：** A 类、独立核账通过；策略资格未获授予，结果仅作研究参考，证据强度低；2020 为已使用历史样本，不是独立样本外。
- **运行核对：** 记录显示本次批次起止约 1.07 秒；六条路径各保存 730 个交易日账户记录，合计 26 笔模拟成交；六条路径独立核账均通过。重启后结果哈希与原批次一致。
- **候选策略结果：** 基础成本期末净值 5,365.60 元，较 5,000 元起始资金模拟盈利 365.60 元，最大回撤 16.98%；压力成本期末净值 5,355.40 元，模拟盈利 355.40 元，最大回撤 17.01%。
- **追溯值：** 协议 SHA-256 969903D59F949DA0024448128404266C0059EA1A7BEF901B6496045BFDDE8D9D；冻结 SHA-256 4BE607DE11C53EEB7639E3083E77C31CF17F5A685DEF292F3F785CDBA34D6E93；结果 SHA-256 178AD47DEE87DE330337137E4925E8B735F0D412A6C0E579FBAAAC06292469A7。

验收仅覆盖上述固定策略、协议修订与数据范围；其他策略和参数未核。运行结果不构成正式交易信号或资格。

## Git 与保护点

发布前保护点核验（2026-10-28，原 checkout）：分支 rescue/2026-10-10，HEAD 75b9617c65de57dff2073b178146c1aceda59a53；staged 24 项、unstaged 19 项、untracked 97 项（porcelain 条目数，staged 与 unstaged 可重叠）；index SHA-256 F8C9313F6F54B387DE1F78BED80447957160EBE1AC238F607E29183C604231B2。这是发布前快照；当时卡 020 尚未提交或推送。

本人网页验收已于 2026-10-28 完成；卡 020 按冻结的单策略范围验收通过。
