# TraderLens Status

**Last Updated**: 2026-06-27 CST
**Current Milestone**: B4 Event-Driven Backtest Verification complete

## Current B4 Verification State

B4 is complete as an offline backtest correctness and future-data guard layer.

Accepted verification record:
- `docs/verification/B4_VERIFICATION.md`

Accepted commits:
- B3 prerequisite: `1cfec6b`
- B4 Task 1-4: `d63e94c`
- B4 Task 5: `3db8196`
- B4 Task 6: `1aa3057`
- B4 Task 7: `f7eb491`
- B4 Task 8: `e8d4ced`
- B4 Task 9: `b105dac`
- B4 Task 10: `5854bfc`
- B4 Task 11: `7c17fca`

Verification baseline recorded in B4 verification doc:
- B4 combined suite: 131 tests passing
- Full pytest: 1198 passed, 2 skipped, 3 warnings, 24 subtests passed

B4 does not prove profitability, does not run B5 OOS, does not pass Gate, does not promote to `prototype_passed`, does not enable Signal Board output, and does not make the system live-trading ready.

Formal B4 qualification must use `run_qualification_with_b3_protocol()`. Legacy `run_qualification()` remains only for Task 4 Canary compatibility and is not a formal B4 authorization path.

---

**Last Updated**: 2026-06-25 23:30 CST  
**Current Milestone**: Serenity 双阶段生产入口启用 (Production Entry Enabled) — 完成 ✅

## Current State

**Product Entry Point**: `/themes` - Selection Research Module

**Phase 4 完成**: Serenity 双阶段生产入口已启用 ✅
- 实现：双阶段 LLM (Planner + Synthesizer) + 确定性执行器
- 约束：单次 run 精确 2 次 LLM 调用，最大并发数 = 2
- 生产入口：`conversation_mode="real"` + `serenity_execution_mode="two_phase"`
- 配置矩阵：严格验证，只允许 real+two_phase、deterministic+stub，其他全拒绝
- 边界门禁：conversation_mode 只允许 real/deterministic，注入 runner 严格类型校验

Full test suite passes (896 tests, 2 skipped).

```text
✅ VERIFIED: Serenity 双阶段生产入口 (2026-06-25 23:30 CST)
  ✅ 严格配置矩阵验证 - real+two_phase、deterministic+stub，其他全拒绝
  ✅ conversation_mode 边界 - 只允许 real/deterministic，拒绝 unknown
  ✅ 注入 runner 严格类型校验 - 拒绝任意 Mock 对象
  ✅ main.py 与 create_research_app 一致性 - 执行相同验证规则
  ✅ 端到端测试 - 通过 TestClient 调用真实端点验证 factory 路径
  ✅ 候选池结构验证 - verification_id、supporting_source_ids、hard_filter_flags、red-team 字段
  
  配置矩阵：
  ✅ real + two_phase → 允许（生产模式）
  ✅ real + stub → 拒绝（ValueError: requires two_phase）
  ✅ deterministic + stub → 允许（测试模式）
  ✅ deterministic + two_phase → 拒绝（ValueError: only allows stub）
  ✅ unknown conversation_mode → 拒绝（ValueError: Invalid conversation_mode）
  
  注入 runner 验证：
  ✅ real 模式必须是 SerenityAgentRunner(mode="real", execution_mode="two_phase")
  ✅ deterministic 模式必须是 SerenityStubRunner
  ✅ 任意 Mock 对象立即拒绝
  
  修改文件：
  ✅ backend/app/main.py - 添加 conversation_mode 严格验证
  ✅ backend/api/research.py - 严格类型校验注入 runner
  ✅ tests/test_serenity_production_entry.py - 完全重写，新增边界测试
  
  测试结果：
  ✅ Full Python suite: 896 tests OK (2 skipped)
  ✅ Frontend type check: 0 errors
  ✅ 聚焦测试: 14/14 passed

✅ VERIFIED: Serenity 双阶段重构 (2026-06-25 20:45 CST)
  ✅ Research Planner (LLM 1/2) - 生成结构化 ResearchPlan
  ✅ Deterministic Executor - 并发数据检索 + ticker 验证 + 审计 + red-team
  ✅ Research Synthesizer (LLM 2/2) - 整合研究结果
  ✅ Deterministic Shortlist Gate - 10 条确定性门禁规则
  ✅ 端到端集成 - 完整双阶段流程
  
  架构验证：
  ✅ 单次 run 精确 2 次 LLM 调用
  ✅ 最大并发数 = 2 (ThreadPoolExecutor)
  ✅ 所有门禁确定性 (无 LLM 参与)
  ✅ LLM 不能覆盖 company_name、verification_id、source quality
  ✅ shortlist 由确定性门禁产生，不满足条件时返回空列表
  ✅ 假 source ID 无法进入研究链
  ✅ 假 verification_id 无法进入候选链
  ✅ 无来源或全 weak 来源不能进入 shortlist
  ✅ 缺少 red-team 不能进入 shortlist
  
  新增文件：
  ✅ backend/services/serenity_planner.py
  ✅ backend/services/serenity_executor.py
  ✅ backend/services/serenity_synthesizer.py
  ✅ backend/services/serenity_gate.py
  ✅ tests/test_serenity_planner.py (6 tests)
  ✅ tests/test_serenity_executor.py (9 tests)
  ✅ tests/test_serenity_synthesizer.py (6 tests)
  ✅ tests/test_serenity_shortlist_gate.py (7 tests)
  ✅ tests/test_serenity_two_phase_e2e.py (3 tests)
  
  修改文件：
  ✅ backend/services/serenity_agent.py - 添加 _run_agent_two_phase() 方法

✅ VERIFIED: Serenity Verification Trust Chain (2026-06-25 11:45 CST)
  ✅ propose_add_candidate now enforces complete verification_id trust chain
  ✅ Arbitrary fake verification_id rejected
  ✅ verification_id for different symbol rejected
  ✅ Low confidence verification rejected
  ✅ Unknown listing status rejected
  ✅ Expired verification_id rejected
  ✅ company_name forced from verification record, LLM input ignored
  ✅ CandidateStock.verification_id saves real ID
  ✅ verify_ticker tool auto-stores verification to DB
  ✅ Tests: 7 new tests in test_serenity_verification_trust.py

✅ VERIFIED: Serenity Tool Chain Real Data Context (2026-06-25 11:45 CST)
  ✅ _run_agent maintains run_context with real ResearchSource records
  ✅ retrieve_supply_chain saves real records to context by source_record_id
  ✅ discover_players reads real source records from context
  ✅ audit_sources reads real source and player records from context
  ✅ red_team_falsify reads real source and player records from context
  ✅ Non-existent source_record_ids rejected and audited
  ✅ _reconstruct_sources method deleted (no longer creates fake placeholders)
  ✅ Player records properly passed to audit and red-team tools
  ✅ Tests: 3 new E2E tests in test_serenity_e2e_context.py

✅ VERIFIED: Evidence Hard-Filter Fix (2026-06-24 15:30 CST)
  ✅ CandidateStock contract now has explicit verification_id field
  ✅ ResearchDB persists CandidateStock.verification_id
  ✅ ResearchDB migrates existing SQLite tables with missing verification_id columns
  ✅ Reducer writes CandidateStock.verification_id from verified ticker record
  ✅ Evidence API reads candidate.verification_id, not candidate.args
  ✅ Evidence API rejects missing verification_id
  ✅ Evidence API rejects expired/invalid verification_id
  ✅ Evidence API rejects symbol mismatch
  ✅ ConfirmedCandidate contract now has verification_id field
  ✅ confirmed_candidates table persists frozen verification_id
  ✅ Tests added for candidate verification traceability and confirmed-pool freezing
  
  ✅ NOW VERIFIED:
  ✅ ResearchValidator has HardFilterSnapshot
  ✅ validate_candidate treats unknown listing/ST/suspension/liquidity as blocking flags
  ✅ get_hard_filter_snapshot queries Tushare stock_basic and daily_basic
  ✅ Evidence API calls get_hard_filter_snapshot and passes hard_filter_metadata to EvidenceLightRunner
  ✅ EvidenceLightRunner records hard_filter_metadata in tool_trace and copies hard-filter gaps into evidence_gaps
  ✅ FakeTushareClient supports daily_basic API
  ✅ Test: normal data produces complete HardFilterSnapshot
  ✅ Test: daily_basic missing → avg_daily_volume=None + gap recorded
  ✅ Test: stock_basic missing → is_st=None + gap recorded
  ✅ Test: ST detected from name prefix
  ✅ Test: suspended status maps correctly
  ✅ Test: is_listed=None → unknown_listing_status (blocks)
  ✅ Test: is_st=None → unknown_st_status (blocks)
  ✅ Test: is_suspended=None → unknown_suspension_status (blocks)
  ✅ Test: avg_daily_volume=None → unknown_liquidity (blocks)
  ✅ Test: all-four-unknown produces all 4 flags
  ✅ Test: hard_filter_metadata written to tool_trace in Evidence output
  ✅ Test: hard-filter gaps copied to evidence_gaps
  ✅ Test: data source gaps block candidate default pass
```

## Last Verified Commands

```powershell
.venv\Scripts\python.exe -m pytest tests/ -x --tb=short -q
# 896 tests OK (skipped=2) - 2026-06-25 23:30 CST
# Skipped tests:
#   1. tests/test_signal_reproducibility.py::TestSignalReproducibility::test_same_inputs_produce_identical_signals
#      → @unittest.skipUnless(Path("backend/app/golden_cases").exists(), "Golden case data not available")
#      → Golden case 参考数据文件不存在（测试环境限制，非 bug）
#   2. tests/test_exit_rules.py::TestBreakthroughExit::test_breakthrough_exit_triggers_when_close_below_low_Nd
#      → "No suitable date found in fixture data"
#      → 测试数据中没有符合条件的日期（数据依赖，非 bug）

node_modules\.bin\tsc.cmd -p frontend --noEmit
# 0 errors - 2026-06-25 23:30 CST
```

## Serenity 双阶段架构

### 流程图

```
用户输入 (ThemeInput + manual_candidates)
  ↓
LLM 1: Research Planner
  → ResearchPlan (keywords, seed_symbols, sectors, falsification_questions)
  ↓
确定性执行器 (Deterministic Executor, max_concurrency=2)
  → 并发数据检索 (retrieve_supply_chain)
  → 玩家发现 (discover_players)
  → 批量 ticker 验证 (verify_ticker, max_concurrency=2)
  → 来源审计 (audit_sources)
  → red-team 证伪 (red_team_falsify)
  → SerenityRunContext (sources + verified_candidates)
  ↓
LLM 2: Research Synthesizer
  → ResearchSynthesis (demand_driver, value_chain, bottleneck, hypothesis)
  ↓
确定性门禁 (Deterministic Shortlist Gate)
  → 10 条硬规则过滤
  → candidate_shortlist
  ↓
SerenityOutput
```

### 生产启用方式

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

### 配置矩阵（严格验证）

| conversation_mode | serenity_execution_mode | 结果 | 说明 |
|-------------------|-------------------------|------|------|
| real | two_phase | ✅ 允许 | 生产模式 |
| real | stub | ❌ 拒绝 | ValueError: requires two_phase |
| real | (缺失) | ❌ 拒绝 | RuntimeError: requires two_phase |
| deterministic | stub | ✅ 允许 | 测试模式（默认） |
| deterministic | two_phase | ❌ 拒绝 | ValueError: only allows stub |
| deterministic | (缺失) | ✅ 允许 | 默认 stub |
| **unknown** | **任意** | ❌ **拒绝** | **ValueError: Invalid conversation_mode** |

### Shortlist 门禁规则

候选进入 shortlist 必须满足：
1. 存在于 verified_candidates_by_symbol
2. verification_id 有效并与 symbol 匹配
3. company_name 来自 verification record
4. 至少一个真实 supporting source
5. 至少一个 supporting source 不是 weak
6. source_audit 已完成
7. red_team 已完成
8. 候选拥有 red_team finding 或 unresolved gap
9. 没有身份阻断问题（confidence ≠ low, listing_status = listed）
10. Synthesizer 引用的 source IDs 全部真实存在

不满足条件时返回空列表，不为凑数量放行。

---

## Architecture Overview

### A Module: Selection Research (Serenity + Evidence)

**Status**: ✅ Production Ready (双阶段生产入口已启用)

- Serenity Agent: Supply chain decomposition → candidate discovery
  - **ENABLED**: 双阶段架构（2 次 LLM 调用，确定性执行器）
  - Tool-use whitelisted research tools
  - Verification trust chain enforced
  - Real data context maintained
  - Strict configuration matrix validation
- Evidence Agent: Candidate evidence gathering and classification
  - Hard-filter snapshot integration
  - Verification ID traceability
  - Multi-source evidence aggregation

**Entry**: `/themes` (Theme Board)  
**Output**: Candidate shortlist → Evidence analysis → Confirmed candidates

### B Module: Strategy Design (Criteria Builder)

**Status**: 🟡 Partially Implemented

- Entry criteria GUI
- Exit criteria GUI
- Position sizing selector
- Fixed 1-year backtest period

**Constraints**:
- Single period: always 1 year from today
- Single version: no version history
- Single user: no auth/multi-user
- Single mode: design only, no live deployment

**Entry**: Not exposed in UI yet  
**Output**: Immutable strategy snapshot (JSON)

### C Module: Strategy Validation (Backtest Runner)

**Status**: ✅ Production Ready

- Strategy executor (vectorized NumPy)
- Monthly performance metrics
- Trade journal export
- Holding-days distribution analysis
- Signal timing visualization

**Entry**: `/strategies/:id/backtest`  
**Output**: Interactive performance dashboard + CSV exports

### Frontend

**Status**: ✅ Production Ready

- React 18 + TypeScript
- TanStack Router v1
- TanStack Query for server state
- Jotai for client state
- Tailwind CSS + shadcn/ui

---

## Known Limitations

1. **No Version Control**: Strategy changes overwrite in place
2. **No Multi-User**: Single-user local app (no auth layer)
3. **Fixed Backtest Period**: Always 1 year from today
4. **Manual Theme Creation**: No automated market scanning

---

## Next Steps

### Immediate (Performance Monitoring)

1. **监控生产环境**
   - LLM 调用次数、执行时间、并发行为
   - 候选池质量、shortlist 准确性
   
2. **质量验证**
   - 对比双阶段输出质量
   - 验证门禁规则效果

### Future Enhancements (Not Prioritized)

- Criteria Reviewer
- Automated market scanning
- Multi-version strategy comparison
- Live strategy deployment (B→C integration)
- Multi-user authentication

---

## Development Setup

### Prerequisites

- Python 3.11+
- Node.js 18+
- Tushare Pro account (for real data)

### Quick Start

```powershell
# Backend
cd D:\Codex\TraderLens
.venv\Scripts\activate
python -m backend.main

# Frontend
cd frontend
npm install
npm run dev
```

### Testing

```powershell
# Python tests
.venv\Scripts\python.exe -m pytest tests/ -x --tb=short -q

# Frontend type check
node node_modules\typescript\lib\tsc.js -p frontend --noEmit
```

---

**Milestone**: Serenity 双阶段生产入口启用 ✅  
**Date**: 2026-06-25 23:30 CST
