# Handoff Prompt

You are taking over `D:\Codex\TraderLens`.

## Latest Accepted State

**Date**: 2026-06-27 CST
**Milestone**: B4 Event-Driven Backtest Verification complete

Read first:
- `AGENTS.md`
- `status.md`
- `docs/verification/B4_VERIFICATION.md`

B4 accepted commits:
- B3 prerequisite: `1cfec6b`
- B4 Task 1-4: `d63e94c`
- B4 Task 5: `3db8196`
- B4 Task 6: `1aa3057`
- B4 Task 7: `f7eb491`
- B4 Task 8: `e8d4ced`
- B4 Task 9: `b105dac`
- B4 Task 10: `5854bfc`
- B4 Task 11: `7c17fca`

Recorded verification baseline:
- B4 combined suite: 131 tests passing
- Full pytest: 1198 passed, 2 skipped, 3 warnings, 24 subtests passed

B4 is not profitability proof, B5 OOS, Gate pass, promotion, `prototype_passed`, Signal Board output, or live trading readiness.

Formal B4 qualification must use `run_qualification_with_b3_protocol()`. Legacy `run_qualification()` is Task 4 Canary compatibility only.

---

## Current Status

**Date**: 2026-06-25 23:30 CST  
**Milestone**: Serenity 双阶段生产入口启用 ✅

### Phase 4 完成 ✅

**Serenity 双阶段生产入口已启用**

实现内容：
- ✅ 严格配置矩阵验证 - real+two_phase、deterministic+stub，其他全拒绝
- ✅ conversation_mode 边界 - 只允许 real/deterministic，拒绝 unknown
- ✅ 注入 runner 严格类型校验 - 拒绝任意 Mock 对象
- ✅ main.py 与 create_research_app 一致性 - 执行相同验证规则
- ✅ 端到端测试 - 通过 TestClient 调用真实端点验证 factory 路径
- ✅ 候选池结构验证 - verification_id、supporting_source_ids、hard_filter_flags、red-team 字段

**当前基线：**
```bash
Python 全量：896 tests OK (skipped=2)
前端类型检查：0 errors
聚焦测试：14/14 passed
```

**Skipped 测试原因：**
1. `tests/test_signal_reproducibility.py::TestSignalReproducibility::test_same_inputs_produce_identical_signals`
   - 原因：`@unittest.skipUnless(Path("backend/app/golden_cases").exists(), "Golden case data not available")`
   - 说明：Golden case 参考数据文件不存在（测试环境限制，非 bug）

2. `tests/test_exit_rules.py::TestBreakthroughExit::test_breakthrough_exit_triggers_when_close_below_low_Nd`
   - 原因：`"No suitable date found in fixture data"`
   - 说明：测试数据中没有符合条件的日期（数据依赖，非 bug）

**配置矩阵（严格验证）：**

| conversation_mode | serenity_execution_mode | 结果 | 说明 |
|-------------------|-------------------------|------|------|
| real | two_phase | ✅ 允许 | 生产模式 |
| real | stub | ❌ 拒绝 | ValueError: requires two_phase |
| real | (缺失) | ❌ 拒绝 | RuntimeError: requires two_phase |
| deterministic | stub | ✅ 允许 | 测试模式（默认） |
| deterministic | two_phase | ❌ 拒绝 | ValueError: only allows stub |
| deterministic | (缺失) | ✅ 允许 | 默认 stub |
| unknown | 任意 | ❌ 拒绝 | ValueError: Invalid conversation_mode |

---

## 生产启用方式

双阶段架构已在生产入口启用，通过配置参数控制：

```python
# backend/api/research.py - create_research_app()
app = create_research_app(
    conversation_mode="real",              # 生产模式
    serenity_execution_mode="two_phase",  # 双阶段架构
)

# backend/app/main.py - 环境变量
os.environ["RESEARCH_CONVERSATION_MODE"] = "real"
os.environ["SERENITY_EXECUTION_MODE"] = "two_phase"
```

### 双阶段流程

```
LLM 1: Research Planner → ResearchPlan
  ↓
确定性执行器 → 并发数据检索 + ticker 核验 + 审计 + red-team (max_concurrency=2)
  ↓
LLM 2: Research Synthesizer → ResearchSynthesis
  ↓
确定性门禁 → candidate_shortlist
```

### 修改文件（Phase 4）

**生产入口：**
- `backend/app/main.py` - 添加 conversation_mode 严格验证
- `backend/api/research.py` - 严格类型校验注入 runner

**测试：**
- `tests/test_serenity_production_entry.py` - 完全重写，新增边界测试

**移除：**
- 删除所有 `runner._use_two_phase` 私有属性引用
- 迁移所有测试使用公开 `execution_mode="two_phase"` 参数

---

## Phase 3 完成 ✅

**Serenity 双阶段重构已完成并验证**

实现内容：
- ✅ Research Planner (LLM 1/2) - 生成结构化研究计划
- ✅ Deterministic Executor - 并发数据检索（max_concurrency=2）+ ticker 验证 + 审计 + red-team
- ✅ Research Synthesizer (LLM 2/2) - 整合研究结果
- ✅ Deterministic Shortlist Gate - 10 条确定性门禁规则
- ✅ 端到端集成 - 完整双阶段流程

**架构验证：**
- ✅ 单次 run 精确 2 次 LLM 调用
- ✅ 最大并发数 = 2
- ✅ 所有门禁确定性
- ✅ LLM 不能覆盖 company_name、verification_id、source quality
- ✅ shortlist 由确定性门禁产生，不满足条件时返回空列表

### 新增文件（Phase 3）

**核心实现：**
- `backend/services/serenity_planner.py` - Research Planner
- `backend/services/serenity_executor.py` - Deterministic Executor
- `backend/services/serenity_synthesizer.py` - Research Synthesizer
- `backend/services/serenity_gate.py` - Shortlist Gate

**测试文件：**
- `tests/test_serenity_planner.py` (6 tests)
- `tests/test_serenity_executor.py` (9 tests)
- `tests/test_serenity_synthesizer.py` (6 tests)
- `tests/test_serenity_shortlist_gate.py` (7 tests)
- `tests/test_serenity_two_phase_e2e.py` (3 tests)

**修改文件：**
- `backend/services/serenity_agent.py` - 添加 `_run_agent_two_phase()` 方法

---

## Phase 1-2 已完成 ✅

**第一优先级：Serenity Verification Trust Chain** ✅
- `propose_add_candidate` 强制验证完整 verification_id 信任链
- 拒绝假 verification_id、错误 symbol、低置信度、unknown 状态、过期记录
- company_name 强制从 verification record 读取
- 7 个新测试 (`test_serenity_verification_trust.py`)

**第二优先级：Serenity Tool Chain Real Data Context** ✅
- `_run_agent` 维护 run_context 存储真实 ResearchSource 记录
- `retrieve_supply_chain` 保存真实 records 到 context
- `discover_players`、`audit_sources`、`red_team_falsify` 从 context 读取真实记录
- 删除 `_reconstruct_sources()` 方法
- 3 个新端到端测试 (`test_serenity_e2e_context.py`)

---

## 验证命令

```powershell
# 聚焦测试（生产入口）
.venv\Scripts\python.exe -m unittest tests.test_serenity_production_entry tests.test_research_main_startup tests.test_startup_config -v

# 双阶段测试
.venv\Scripts\python.exe -m unittest tests.test_serenity_planner tests.test_serenity_executor tests.test_serenity_synthesizer tests.test_serenity_shortlist_gate tests.test_serenity_two_phase_e2e

# 全量测试
.venv\Scripts\python.exe -m pytest tests/ -x --tb=short -q

# 前端类型检查
node node_modules/typescript/lib/tsc.js -p frontend --noEmit
```

---

## 项目约束

### 必须遵守
- A 模块不输出 buy/sell/recommendation/target price/stop loss/position
- LLM 不创建市场事实、财务数字、公告、ticker identity
- 状态写入通过 ProposedAction → reducer → DB → Research Board
- `strategy_core` 不修改

### 禁止开发
- Criteria Reviewer
- 自动市场扫描
- UI 润色
- B/C 模块修改

---

## 文件结构

### 核心文件（已存在）
- `backend/services/serenity_agent.py` - 主入口（双阶段架构）
- `backend/services/serenity_tools.py` - 工具实现
- `backend/services/serenity_planner.py` - Research Planner
- `backend/services/serenity_executor.py` - Deterministic Executor
- `backend/services/serenity_synthesizer.py` - Research Synthesizer
- `backend/services/serenity_gate.py` - Shortlist Gate
- `backend/api/research.py` - 生产入口（严格配置验证）
- `backend/app/main.py` - 启动入口（环境变量验证）
- `contracts/research.py` - 公共契约

### 测试文件（已存在）
- `tests/test_serenity_production_entry.py` (9 tests) - 生产入口边界测试
- `tests/test_serenity_verification_trust.py` (7 tests)
- `tests/test_serenity_e2e_context.py` (3 tests)
- `tests/test_serenity_planner.py` (6 tests)
- `tests/test_serenity_executor.py` (9 tests)
- `tests/test_serenity_synthesizer.py` (6 tests)
- `tests/test_serenity_shortlist_gate.py` (7 tests)
- `tests/test_serenity_two_phase_e2e.py` (3 tests)

---

## 下一步建议

### 1. 性能监控

监控双阶段模式的关键指标：
- LLM 调用次数（应为 2）
- 执行时间
- 并发行为
- shortlist 质量

### 2. 质量验证

对比双阶段输出质量，验证门禁规则效果。

---

## 完成标准验证

所有完成标准已满足：

- ✅ 单次 real Serenity 最多 2 次 LLM 调用
- ✅ 运行并发不超过 2
- ✅ 假 source ID 无法进入研究链
- ✅ 假 verification_id 无法进入候选链
- ✅ 无来源或全 weak 来源不能进入 shortlist
- ✅ 缺少 red-team 不能进入 shortlist
- ✅ LLM 不能覆盖 company_name、verification_id、source quality
- ✅ shortlist 由确定性门禁产生
- ✅ 完整双阶段真实数据链测试通过
- ✅ 严格配置矩阵验证（real+two_phase, deterministic+stub）
- ✅ conversation_mode 边界闭合（只允许 real/deterministic）
- ✅ 注入 runner 严格类型校验（拒绝任意 Mock）
- ✅ 端到端测试通过 TestClient 验证生产 factory
- ✅ Python 全量测试通过（896 tests, 2 skipped）
- ✅ 前端类型检查通过（0 errors）
- ✅ status.md 准确反映实际状态

---

**生产入口已启用！🚀**
