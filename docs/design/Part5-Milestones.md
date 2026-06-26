# Part 5: 实现路径和里程碑

## 总体时间线

总计：**12-13 周**（约 3 个月）

- Milestone 0: Week 1
- Milestone 1: Week 2-4
- Milestone 2: Week 5-7
- Milestone 3: Week 8-9
- Milestone 4: Week 10-11
- Milestone 5: Week 12-13

## Milestone 0：接口契约 + 项目骨架 + Golden Cases + 任务队列骨架（Week 1）

**目标**：定义模块边界和数据契约，搭建项目骨架，准备黄金测试用例，保证后续并行开发能集成。

### 交付物

1. **Schema 定义**（JSON Schema / Pydantic）：
   - `StockIdentity`、`DailyBar`、`DailyStatus`
   - `StrategyConfig`、`BacktestTask`、`BacktestReport`
   - `EvidenceOutput`、`HypothesisDraft`、`AuditLog`

2. **API 契约**（OpenAPI spec）

3. **项目骨架**（目录结构、环境配置）

4. **基础设施**：
   - SQLite 数据库初始化脚本
   - Parquet 缓存目录结构
   - 审计日志目录结构

5. **Golden Cases（黄金测试用例）**：
   ```
   tests/golden_cases/
     ├── strategy_config.yaml       # 一个手工策略配置
     ├── test_stocks.json           # 5 只固定测试股票（000001.SZ, 600000.SH, ...）
     ├── data_snapshot/             # 固定历史数据快照（2024-01-01 to 2025-12-31）
     │   ├── 000001.SZ_daily.parquet
     │   ├── 000001.SZ_status.parquet
     │   └── ...
     ├── expected_backtest_output.json  # 预期回测输出
     ├── limit_up_case.json         # 涨停买不进案例
     ├── limit_down_case.json       # 跌停卖不出案例
     ├── suspended_case.json        # 停牌不成交案例
     └── oos_failed_case.json       # OOS failed 案例
   ```

6. **任务队列骨架**：
   ```python
   # SQLite tasks 表
   CREATE TABLE tasks (
       task_id TEXT PRIMARY KEY,
       task_type TEXT,  -- serenity / evidence / backtest / signal_generation
       status TEXT,     -- queued / running / success / failed
       created_at TIMESTAMP,
       started_at TIMESTAMP,
       completed_at TIMESTAMP,
       config BLOB,
       result_path TEXT,
       error_message TEXT,
       retry_count INTEGER
   );
   
   # 后台 worker 轮询执行
   # 单机单 worker 起步
   # LLM 并发全局限制 = 2
   ```

### 验收标准

- [ ] 所有 schema 定义完成，通过 Pydantic 校验
- [ ] API 契约文档生成（Swagger UI 可访问）
- [ ] 项目骨架搭建完成，`npm run dev` 和 `uvicorn` 能启动
- [ ] SQLite 数据库表创建成功
- [ ] Golden Cases 数据快照可加载并通过 schema 校验
- [ ] Golden Cases 预期输出文件存在并格式正确
- [ ] 涨停、跌停、停牌、OOS failed 案例的数据快照准备完毕
- [ ] 任务队列表创建成功，worker 能轮询执行任务
- [ ] 团队成员能从 schema 定义看懂模块边界

**时间**：5-7 天

**关键输出**：
- 完整 schema 定义（所有 Pydantic models）
- Golden Cases 数据快照（5 只股票 + 4 个约束案例）
- 预期输出文件（expected_backtest_output.json 等）
- 空 worker 能接收任务（实际执行逻辑在 M1 实现）

---

## Milestone 1：数据层 + Web 壳 + strategy_core + 原型回测最小闭环（Week 2-4）

**目标**：跑通"手工 YAML 策略配置 → 回测 → 原始报告 JSON"闭环。

### 并行轨道 A：数据层（Week 2-3）

**交付物**：
1. Tushare Pro 封装
2. 缓存管理器（SQLite metadata + Parquet 文件，TTL 按类型区分）
3. 数据适配器：
   - `get_stock_identity()`
   - `get_trading_calendar()`
   - `get_daily_bars()`（raw + hfq，记录 adjust_snapshot_date）
   - `get_daily_status()`（ST、停牌、涨跌停）
   - `check_data_quality()`
4. 数据质量检查

**M1 验收数据范围（收缩）**：
- 先支持 **20 只固定测试股票**（包含 Golden Cases 的 5 只）
- 再支持用户输入股票列表（最多 50 只）
- 全市场扫描后置（Milestone 3+）
### 验收标准

- [ ] 能从 Tushare 拉取 20 只固定测试股票 2024-2026 日线数据
- [ ] 数据缓存到 Parquet 文件，metadata 存 SQLite
- [ ] 能查询停牌、涨跌停、ST 状态（每日状态）
- [ ] 数据质量报告能标记 degraded / insufficient
- [ ] 能手工触发缓存刷新
- [ ] Golden Cases 数据快照能加载并通过回测
- [ ] 写单元测试：缓存命中、缓存过期、数据质量检查
- [ ] **Golden Case 回测能跑通，输出与预期一致**
- [ ] **涨停、跌停、停牌、OOS failed 案例能复现**

### 并行轨道 B：strategy_core + 回测引擎（Week 2-4）

**交付物**：
1. DSL 解析器
2. 股票池构建器（支持 sector_plus_filters，硬门槛过滤）
3. 信号生成器（突破、放量、相对强度、均线条件、市场状态过滤）
4. 成交模拟器（T+1、涨跌停、停牌、流动性、100 股 floor、佣金印花税滑点）
5. 事件循环回测器（pending_orders 模式）
6. 持仓管理器
7. 盈亏计算器

**验收标准**：
- [ ] 能手工编写一个 YAML 策略配置（突破 + 放量）
- [ ] DSL 解析器能校验配置并生成内部表示
- [ ] 能对 Golden Cases 的 5 只股票跑原型回测
- [ ] 能对 20 只固定测试股票、2024-2025 数据跑原型回测
- [ ] 回测输出包含：交易明细、收益率、最大回撤、胜率
- [ ] 成交约束生效：涨停买不进、跌停卖不出、停牌不成交
- [ ] Golden Cases 中的 4 个约束案例能复现
- [ ] 每笔交易记录 signal_date / intended_execution_date / actual_execution_date
- [ ] 写集成测试：完整回测流程，检查交易笔数、盈亏计算

### 并行轨道 C：Web 壳（Week 2-3）

**交付物**：
1. Next.js 项目搭建
2. 页面框架：Dashboard、策略库页、回测页、任务状态页、回测报告页（显示原始 JSON）
3. FastAPI 后端：策略 CRUD、回测任务提交

**验收标准**：
- [ ] 能在 Web 页面创建策略（手工填写 YAML 或上传文件）
- [ ] 能在 Web 页面提交回测任务（后台 worker 执行）
- [ ] 任务状态页能显示 queued / running / success / failed
- [ ] 回测完成后能跳转到报告页（先显示原始 JSON）

### 集成点（Week 4 末）

**验收标准**：
- [ ] 在 Web 页面手工创建策略配置
- [ ] 提交回测任务，后台 worker 调用 strategy_core + 回测引擎
- [ ] 回测引擎从数据层拉取缓存数据
- [ ] 回测完成后，Web 页面展示原始 JSON 报告
- [ ] 能看到交易明细和成交约束统计
- [ ] Golden Cases 能在 Web 端完整跑通

**时间**：15 天（3 周）

**最大风险**：
- Tushare API 限流或数据质量问题
- 回测引擎性能问题（大样本慢）
- 前后端数据结构不一致

**降级方案**：
- 准备备用数据源（AKShare）
- 回测引擎先支持小样本（20 只股票 * 1 年），性能优化后置
- Week 1 的 schema 契约必须严格执行

---

（续下页，Milestone 2-5）

## Milestone 2：完整回测报告 + OOS + Benchmark + Admission Gate + Audit + Signal Board v0（Week 5-7）

**目标**：完善回测报告（7 块内容），增加样本外切分、基准对比、**Admission Gate 准入检查**、审计功能，做 Signal Board v0。

### 交付物

1. **回测报告完整版**（7 块内容）：
   - 概览：策略名、版本、backtest_level（prototype_with_constraints）、基准、**Admission Gate 结果**
   - 基础指标：收益率、回撤、夏普、胜率、盈亏比、**benchmark_return、excess_return**
   - 样本内外对比：IS 指标 vs OOS 指标、OOS 状态
   - 交易明细：每笔交易、出场原因、约束影响
   - 成交约束统计：触发信号数、成交数、未成交数、约束原因
   - 数据质量报告：数据源、degraded 股票、缺失字段
   - **Admission Gate 准入检查**（新增）：
     - 准入结果（prototype_passed / rejected / needs_review）
     - 所有检查项明细（pass / fail / warning）
     - blocking_issues 列表
     - warnings 列表
     - 不通过原因解释
   - 失败原因分析（规则化标签）
   - 年份分组分析

2. **样本外切分**（`oos_split.py`）：
   - in_sample_end 和 out_of_sample_start 配置
   - 分别计算 IS / OOS 指标
   - OOS 降级检测（收益、回撤、交易笔数）
   - OOS 状态：oos_ok / oos_degraded / oos_insufficient_trades / oos_failed

3. **基准对比**（`benchmark.py`）：
   - 支持 index（沪深300、中证500）/ sector / custom_universe
   - 计算基准收益率
   - 计算超额收益
   - IS / OOS 分别对比

4. **幸存者偏差警告**：
   ```yaml
   survivorship_bias_warning:
     include_delisted: partial  # none / partial / full
     policy: warn_only  # V1 默认，不用 strict
     coverage_note: "当前退市股票覆盖不完整，本次回测存在幸存者偏差风险"
     delisted_count_in_universe: 2
     total_universe_count: 20
   ```

5. **Admission Gate 模块**（新增，M2 必做）：
   - `backtest/admission_gate.py`：策略准入检查
   - 门槛配置文件：`config/admission_gate.yaml`
   - 检查项实现：
     - `min_oos_trades`（最低交易笔数）
     - `min_oos_excess_return`（样本外超额收益）
     - `max_drawdown_limit`（最大回撤上限）
     - `min_profit_factor`（最低盈亏比）
     - `cost_sensitivity`（成本敏感性测试：滑点扩大 2 倍）
     - `execution_block_ratio`（成交阻止率）
     - `data_quality`（数据质量检查）
     - `survivorship_bias`（幸存者偏差策略，默认 warn_only）
     - `oos_degraded_acceptance`（OOS 降级接受条件）
   - 输出结构：`admission_gate_result`（包含所有检查项、blocking_issues、warnings、next_strategy_status）
   - 策略状态自动更新：根据 Admission Gate 结果更新 `strategy.status`
   - 硬边界：LLM 不参与 Admission Gate 判断

6. **Audit 模块**（`audit/`）：
   - `audit_logger.py`：记录所有关键操作
   - 审计日志落文件：`audit/runs/{run_id}.json`
   - SQLite metadata：run_id、timestamp、task_type、status、file_path、content_hash
   - 支持 deterministic replay 和 LLM re-run

7. **Audit 页面**：
   - 审计日志列表
   - 详情展示：输入、输出、配置 hash、数据快照路径
   - 操作：下载产物、重放运行

8. **Tasks 页面增强**：
   - 失败原因分类显示
   - 产物链接（回测报告）
   - 查看 Audit 链接
   - 重试、取消操作

9. **Signal Board v0**（新增，提前到 M2）：
   - 只支持手工策略配置
   - **只读取 `strategy.status == prototype_passed` 的策略**（由 Admission Gate 决定）
   - strategy_core 对最新 EOD 数据生成下一交易日计划信号
   - 展示内容：
     - 股票、策略、状态、信号触发日期、计划执行日期
     - 触发条件、入场/出场规则
     - 回测摘要、风险状态
     - **Admission Gate 警告**（如果有）
   - 明确标注：这是计划信号，不是实盘建议
   - **不含 Action Plan 详情**（M3 实现）
   - 不接 Evidence Agent
   - 不做执行记录

10. **市场状态（红黄绿灯）简化版**：
   - 第一版配置为常量或人工设置
   - 支持手工切换（配置文件或 Web 页面）

### 验收标准

- [ ] 回测报告包含完整 7 块内容
- [ ] 样本内外对比正确，OOS 状态判断准确
- [ ] 基准对比功能可用，能计算超额收益
- [ ] 回测报告包含 survivorship_bias_warning（policy: warn_only）
- [ ] **Admission Gate 自动运行，检查所有门槛项**
- [ ] **Admission Gate 配置文件可修改门槛值**
- [ ] **Admission Gate 输出包含所有检查项明细、blocking_issues、warnings**
- [ ] **策略状态根据 Admission Gate 结果自动更新为 prototype_passed / rejected / needs_review**
- [ ] **回测报告页面展示 Admission Gate 完整结果**
- [ ] **OOS 降级但可接受的策略能通过（pass_with_warning）**
- [ ] **幸存者偏差 warn_only 模式工作正常，不阻止策略通过**
- [ ] **LLM 不参与 Admission Gate 判断**
- [ ] 回测报告可导出 JSON / Markdown / HTML
- [ ] 每次回测都生成审计日志
- [ ] Audit 页面能查看完整 trace
- [ ] 能基于审计日志 deterministic replay 回测
- [ ] Tasks 页面显示失败原因和产物链接
- [ ] **Signal Board v0 只展示 strategy.status == prototype_passed 的策略**
- [ ] **Signal Board 展示 Admission Gate 警告（如果有）**
- [ ] **用户能在 Web 端看到"明天应该关注哪些股票"**
- [ ] Signal Board 明确标注"计划信号，不是实盘建议"
- [ ] **不含 Action Plan 详情展示**（M3 实现）

**时间**：15 天（3 周）

**关键变化**：
- Signal Board 提前到 Milestone 2，用户能更早看到计划信号
- Action Plan 详情推迟到 Milestone 3，保持 M2 交付范围可控
- **Admission Gate 在 M2 实现，作为回测报告和 Signal Board 之间的闸门**
- 增加 survivorship_bias_warning，默认 warn_only 不阻止策略通过
- OOS 降级接受条件允许部分策略通过（pass_with_warning）

---

## Milestone 3：Serenity + Hypothesis Builder v0 + Evidence light_check + Forward Candidates + Action Plan v0（Week 8-9）

**目标**：接入 Serenity 主题研究模块、Hypothesis Builder 和 Evidence light_check，**增加 Forward Candidates 向前跟踪**，用户可以从主题生成策略配置。**增加 Action Plan 详情展示**。

### 交付物

1. **Serenity 模块**（`agents/serenity.py`）：
   - 主题输入（theme_name、background、research_mode）
   - 8 步固定工作流（LLM 推理 + 数据匹配）
   - 候选公司池生成（raw pool + shortlist）
   - hypothesis_draft（可规则化部分 + 不可规则化部分）
   - **证伪条件草案生成**（主题/产业链层面）
   - 输出 JSON，包含 hypothesis_source_snapshot

2. **Evidence Agent light_check**（新增，从 M4 提前）：
   - 只实现 light_check（最多 5 步）
   - 工具白名单：
     - `get_stock_identity()`
     - `get_announcements()`（近一年关键词）
     - `get_financials()`（基础摘要）
     - `get_price_history()`（流动性、停牌、ST）
   - 输出：evidence_level 初评、blocking_issues
   - **证伪条件补强**（公司层面）
   - 只对 Serenity 输出的 shortlist（3-5 只）运行

3. **Forward Candidates 模块**（新增）：
   - `forward_candidates/manager.py`：Forward Candidate 管理
   - 数据表：SQLite `forward_candidates` 表
   - **草稿生成**：Evidence 完成后自动生成 Forward Candidate 草稿
     - thesis（研究判断）
     - invalidation_rules（Serenity 主题层面 + Evidence 公司层面）
     - price_snapshot（当日完整 OHLC + volume + amount）
     - benchmark（默认规则：主题策略优先用 sector/custom_universe）
   - **用户确认**：用户确认后加入 Forward Candidates，锁定 thesis / invalidation_rules / price_snapshot / benchmark
   - **复盘逻辑**（V1 简化版）：
     - 默认 30 天复盘
     - 更新 alpha_vs_benchmark
     - 检查 invalidation_rule 是否触发
     - 更新 status
   - **状态管理**：active / converted_to_strategy / downgraded / removed
   - 历史记录保留（removed 不物理删除）

4. **Forward Candidates 页面**：
   - `/forward-candidates` 页面
   - 表格展示（theme / symbol / evidence_level / date_added / alpha_vs_benchmark / status / review_date）
   - 筛选：按 status / theme / evidence_level
   - 详情抽屉：thesis、invalidation_rules、price_snapshot、复盘历史
   - 操作：查看详情、触发复盘、转入 Hypothesis Builder、更新 status

5. **主题详情页增强**：
   - Evidence 完成后展示 Forward Candidate 草稿
   - 用户确认加入按钮

6. **Hypothesis Builder v0**：
   - 左侧：结构化表单
   - 右侧：假设草案和证据摘要（只读参考）
   - "生成草稿"按钮（LLM 辅助）
   - 保存前校验
   - **页面必须标记：Evidence 未完成**
   - **未取证或 evidence_level = unknown 的股票池只能保存为 draft，不能进入 prototype_passed**

7. **主题研究页面**（`/themes`）

8. **本地公司标签库**

9. **Action Plan v0（新增）**：
   - `action_plan.py` 模块实现（Part 3 设计）
   - signal → trade_plan 转换逻辑
   - position_plan 计算（max / current / planned / available）
   - invalid_if 结构化条件生成（market_state / stock_status / price_limit / liquidity）
   - fallback_action + next_check_date 计算
   - Signal Board 详情抽屉增加 Action Plan 展示（Part 4 设计）
   - execution_log 字段预留（数据结构定义，不实现录入功能）

### 验收标准

- [ ] 能在 Web 页面输入主题，触发 Serenity 分析
- [ ] Serenity 输出包含产业链层级、瓶颈环节、shortlist（3-5 只）
- [ ] **Serenity 生成主题/产业链层面的证伪条件草案**
- [ ] hypothesis_draft 包含可规则化部分和不可规则化部分
- [ ] hypothesis_source_snapshot 记录完整来源信息
- [ ] **Serenity 输出的 shortlist 自动触发 Evidence light_check**
- [ ] **Evidence light_check 能调用 4 个工具，tool trace 记录完整**
- [ ] **Evidence 输出包含 evidence_level、blocking_issues、pipeline_suggestion**
- [ ] **Evidence 生成公司层面的证伪条件补强**
- [ ] **Evidence 完成后自动生成 Forward Candidate 草稿**
- [ ] **Forward Candidate 草稿包含 thesis、invalidation_rules（主题层面 + 公司层面）、price_snapshot、benchmark**
- [ ] **用户能在主题详情页确认加入 Forward Candidates**
- [ ] **用户确认后，thesis / invalidation_rules / price_snapshot / benchmark 锁定**
- [ ] **Forward Candidates 表能正确记录和展示**
- [ ] **Forward Candidates 页面能筛选、查看详情、触发复盘**
- [ ] **复盘逻辑能更新 alpha_vs_benchmark 和 status**
- [ ] **removed 状态保留历史记录，不物理删除**
- [ ] Hypothesis Builder 能从 hypothesis_draft 预填充表单
- [ ] "生成草稿"按钮能调用 LLM 生成 YAML 配置
- [ ] **未完成取证的策略只能保存为 draft 状态**
- [ ] 保存策略配置时，hypothesis_source_snapshot 写入策略文件
- [ ] 本地公司标签库能被 Serenity 读取和更新
- [ ] Serenity 和 Evidence light_check 运行记录写入 Audit 日志
- [ ] **action_plan.py 模块能根据 signal 生成 trade_plan**
- [ ] **position_plan 计算正确（max / current / planned / available）**
- [ ] **invalid_if 条件生成正确，结构化字段完整**
- [ ] **fallback_action 和 next_check_date 逻辑正确**
- [ ] **Signal Board 详情抽屉展示 Action Plan 完整内容**
- [ ] **execution_log 数据结构定义完成，字段预留**

**时间**：10 天（2 周）

**关键变化**：
- Evidence light_check 提前到 Milestone 3，保证主链路完整（Serenity → Evidence → Hypothesis Builder）
- 未完成取证的策略不能进入 prototype_passed，保证策略质量
- **Action Plan v0 在 M3 实现，用户能看到完整执行计划**
- **Forward Candidates 在 M3 实现，越早加越能开始积累真实样本**

---

## Milestone 4：Evidence deep_check + Builder 联动 + Execution Log v0（Week 10-11）

**目标**：补充 Evidence deep_check，完善 Builder 联动，**实现 Execution Log 用户录入功能**。

### 交付物

1. **Evidence Agent deep_check**：
   - 实现 deep_check（最多 15 步）
   - 补充工具：
     - `get_sector_and_peers()`（同行对照）
     - `get_money_flow()`（资金数据，可选）
     - `summarize_evidence_pack()`
   - 只对用户指定公司或 Evidence light_check 结果为 `need_more_evidence` 的公司运行

2. **Hypothesis Builder 联动增强**：
   - Evidence 完成后，用户可以确认候选进入策略股票池
   - 股票池定义支持 Evidence 筛选结果（evidence_level >= medium）
   - 策略状态可以从 draft 提升到可回测

3. **Execution Log v0（新增，从 M5 提前）**：
   - 用户录入界面：
     - 选择 trade_plan
     - 记录实际执行情况（executed / skipped / modified / not_recorded）
     - 记录实际价格、数量
     - 标记 manual_override 和 override_reason
     - 计算 drift_type（price_drift / quantity_drift / timing_drift / skip）
   - 历史记录展示：
     - 按时间倒序展示
     - 筛选：按策略、按股票、按执行状态
     - 对比计划 vs 实际
   - 数据持久化（SQLite + Audit）

4. **Signal Board 完整版增强**：
   - 接入 Evidence 结果
   - 展示每只股票的证据等级、排雷项
   - Audit 链接完整
   - 支持筛选：按策略、按状态、按证据等级
   - **Execution Log 入口激活**（从 Action Plan 详情进入）

5. **Evidence Agent 页面**（对话式界面）：
   - 展示取证过程（tool call trace）
   - 展示证据等级、排雷项、blocking_issues
   - 支持人工确认后继续 / 停止

### 验收标准

- [ ] 用户可以手动触发 Evidence deep_check
- [ ] Evidence deep_check 能调用 7 个工具，tool trace 记录完整
- [ ] Evidence 输出包含完整证据包、反证、排雷项
- [ ] Evidence 运行记录写入 Audit 日志，支持 replay
- [ ] Hypothesis Builder 能基于 Evidence 结果筛选股票池
- [ ] Evidence 完成的候选可以进入策略股票池并提升状态
- [ ] **用户能从 Action Plan 详情进入 Execution Log 录入界面**
- [ ] **Execution Log 能记录 executed / skipped / modified / not_recorded**
- [ ] **能记录实际价格、数量、manual_override、override_reason**
- [ ] **drift_type 自动计算正确**
- [ ] **历史 Execution Log 按时间倒序展示，支持筛选**
- [ ] **能对比计划 vs 实际执行情况**
- [ ] Signal Board 展示证据等级和 Audit 链接
- [ ] Signal Board 支持按证据等级筛选
- [ ] **完整链路跑通：主题 → Serenity → Evidence (light + deep) → Hypothesis Builder → 回测 → Signal Board → Action Plan → Execution Log**

**时间**：10 天（2 周）

**关键变化**：
- **Execution Log v0 提前到 M4，用户能记录实际执行情况**
- Shadow Account 后置到 V2（M4 只做人工录入，不做自动对账）

---

## Milestone 5：收尾、降级路径、体验优化、文档（Week 12-13）

**目标**：你作为用户能稳定每天打开使用。

### 交付物

1. **用户文档**：
   - 系统定位和核心概念
   - 快速开始指南
   - 各页面使用说明
   - 常见问题 FAQ

2. **部署文档**：
   - 环境要求
   - 安装步骤
   - 配置说明
   - 备份和恢复

3. **降级路径测试**：
   - Tushare API 失败时切换到缓存
   - LLM 超时时重试和降级
   - 回测引擎性能问题时限制样本量
   - Evidence Agent 成本失控时限制步骤数

4. **体验优化**：
   - 页面加载优化
   - 错误提示优化
   - 操作引导优化
   - Dashboard 信息密度优化

5. **数据备份和迁移**：
   - SQLite 备份脚本
   - Parquet 文件归档
   - Audit 日志归档
   - 策略配置版本管理

6. **监控和告警**：
   - 任务失败告警
   - 数据质量告警
   - LLM 成本监控
   - 系统资源监控

### 验收标准

- [ ] 用户文档完整，新用户能独立上手
- [ ] 部署文档完整，能在新环境部署成功
- [ ] 降级路径全部测试通过
- [ ] 页面响应时间 < 2s（正常情况）
- [ ] 错误提示清晰，用户能理解问题
- [ ] Dashboard 能一眼看到关键信息
- [ ] 数据备份脚本能正常运行
- [ ] 监控和告警能及时发现问题
- [ ] **你能每天稳定使用系统完成主题研究 → 策略配置 → 回测 → 查看信号的完整流程**

**时间**：10 天（2 周）

---

## 明确不做项（MVP V1）

- 完整 EOD 模拟盘自动对账（M4 只做人工录入 Execution Log，不做 Shadow Account）
- Review Agent 复盘诊断
- 小资金实盘对接
- 券商 API 对接、实盘下单
- 盘中实时监控
- 复杂市场状态自动判断（红黄绿灯第一版人工设置）
- 历史时点板块成分动态还原
- 基本面策略（财务数据不进入 strategy_core 信号）
- 多策略组合回测
- 复杂仓位管理（动态仓位、止盈移动）
- 分批买入/卖出（V1 signal 和 trade_plan 1:1，不拆分）
- PDF 导出（第一版 JSON / Markdown / HTML）
- 完整退市股票全样本覆盖（第一版部分退市股票）

---

## 最大风险和降级方案

**风险 1：Tushare API 限流或数据质量问题**
- **降级方案**：准备 AKShare 备用数据源，数据质量标记机制保证降级可见

**风险 2：LLM 输出不稳定（Serenity / Evidence Agent）**
- **降级方案**：Pydantic 严格校验，失败时人工介入，增加重试机制

**风险 3：回测引擎性能问题**
- **降级方案**：第一版限制样本量（20 只股票 * 2 年），性能优化后置

**风险 4：Evidence Agent 成本失控**
- **降级方案**：Agent Harness 严格限制步骤数和 token budget，第一版只对 3-5 只股票运行

**风险 5：前后端数据结构不一致**
- **降级方案**：Milestone 0 的 schema 契约必须严格执行，增加集成测试

**风险 6：OOS 切分逻辑错误（样本泄露）**
- **降级方案**：增加单元测试，确保时间边界正确，Audit 日志记录样本切分配置

**风险 7：用户不理解系统定位（误认为自动交易系统）**
- **降级方案**：所有页面明确标注"计划信号，不是实盘建议"，Dashboard 增加系统定位说明

---

完整 Part 5 内容已保存。

