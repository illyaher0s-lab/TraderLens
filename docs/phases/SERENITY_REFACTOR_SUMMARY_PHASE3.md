# Serenity 双阶段重构 - 执行总结

**日期**: 2026-06-25  
**当前基线**: 768 tests OK (skipped=2), 0 frontend errors  
**状态**: 方案就绪，等待实施

---

## 一、重构目标

将 Serenity 从多轮 LLM 工具调用改为：

```
LLM 1: Research Planner → 生成 ResearchPlan
  ↓
确定性执行器 → 并发数据检索 + ticker 核验 + 审计 + red-team (max_concurrency=2)
  ↓
LLM 2: Research Synthesizer → 整合研究结果
  ↓
确定性门禁 → 生成 candidate_shortlist
```

**硬约束：**
- 单次 run 最多 2 次 LLM 调用
- 最大并发数 = 2
- 所有门禁确定性

---

## 二、快速开始

### 详细方案
见 `SERENITY_REFACTOR_PLAN.md`（611 行完整实施指南）

### 实施步骤
1. 运行基线测试（✅ 已完成）
2. 实现 `SerenityRunContext` + `VerifiedResearchCandidate`
3. 实现 `ResearchPlanner` (LLM 1/2)
4. 实现 `DeterministicExecutor` (并发限制 2)
5. 实现来源审计 + red-team
6. 实现 `ResearchSynthesizer` (LLM 2/2)
7. 实现 shortlist 门禁
8. 修复 audit 元数据
9. 编写 30+ 新测试
10. 全量测试验证

### 时间估算
约 28 小时（保守估算）

---

## 三、关键数据结构

### ResearchPlan (Planner 输出)
```python
@dataclass
class ResearchPlan:
    keywords: list[str]          # 最多 20
    seed_symbols: list[str]      # 最多 10
    sectors_to_check: list[str]  # 最多 5
    start_date: str | None
    end_date: str | None
    falsification_questions: list[str]  # 最多 10
```

### VerifiedResearchCandidate
```python
@dataclass
class VerifiedResearchCandidate:
    symbol: str
    company_name: str  # 来自 verification record
    verification_id: str
    exchange: str
    listing_status: str
    confidence: str  # high/medium
    supporting_source_ids: list[str]  # 必须非空
    red_team_findings: list[str]
    unresolved_gaps: list[str]
```

### SerenityRunContext
```python
@dataclass
class SerenityRunContext:
    sources_by_id: dict[str, ResearchSource]
    verified_candidates_by_symbol: dict[str, VerifiedResearchCandidate]
    completed_checks: set[str]  # {"source_audit", "red_team"}
```

---

## 四、Shortlist 门禁规则

候选进入 `candidate_shortlist` 必须满足：

1. ✅ 存在于 `verified_candidates_by_symbol`
2. ✅ verification_id 有效并与 symbol 匹配
3. ✅ company_name 来自 verification record
4. ✅ 至少一个真实 supporting source
5. ✅ 至少一个 supporting source 不是 weak
6. ✅ source_audit 已完成
7. ✅ red_team 已完成
8. ✅ 候选拥有 red_team finding 或 unresolved gap
9. ✅ 没有身份阻断问题
10. ✅ Synthesizer 引用的 source IDs 全部真实存在

**不满足时：**
- 可进入 evidence_gaps
- 不进入 shortlist
- 不为凑数量放行
- 没有可靠候选时返回空列表

---

## 五、新增文件清单

### 核心实现
- `backend/services/serenity_planner.py` - Research Planner
- `backend/services/serenity_executor.py` - 确定性执行器
- `backend/services/serenity_synthesizer.py` - Research Synthesizer

### 测试文件
- `tests/test_serenity_planner.py`
- `tests/test_serenity_executor.py`
- `tests/test_serenity_synthesizer.py`
- `tests/test_serenity_shortlist_gate.py`
- `tests/test_serenity_two_phase_e2e.py`

### 修改文件
- `backend/services/serenity_agent.py` - 重写 `_run_agent` 为双阶段
- `tests/test_serenity_agent.py` - 重写弱测试

---

## 六、必须编写的测试（至少 30 个）

### Planner (5)
1. `test_planner_single_llm_call`
2. `test_planner_produces_valid_schema`
3. `test_planner_malformed_json_fails`
4. `test_different_themes_produce_different_plans`
5. `test_planner_limits_enforced`

### Executor (8)
6. `test_executor_max_concurrency_is_2`
7. `test_executor_saves_real_sources_to_context`
8. `test_executor_single_tool_failure_does_not_cancel_others`
9. `test_seed_without_real_source_rejected`
10. `test_discover_players_uses_real_sources`
11. `test_verify_ticker_batch_concurrency_limited`
12. `test_audit_detects_all_weak_sources`
13. `test_red_team_detects_data_gaps`

### Synthesizer (5)
14. `test_synthesizer_single_llm_call`
15. `test_synthesizer_validates_source_ids`
16. `test_synthesizer_rejects_non_existent_ids`
17. `test_synthesizer_malformed_json_fails`
18. `test_llm_cannot_override_company_name`

### Shortlist Gate (7)
19. `test_no_sources_rejected_from_shortlist`
20. `test_all_weak_sources_rejected_from_shortlist`
21. `test_missing_red_team_rejected_from_shortlist`
22. `test_low_confidence_rejected_from_shortlist`
23. `test_valid_candidate_passes_shortlist`
24. `test_empty_shortlist_when_no_valid_candidates`
25. `test_verification_id_saved_in_candidate_stock`

### E2E (3)
26. `test_full_two_phase_flow_with_real_data`
27. `test_total_llm_calls_exactly_two`
28. `test_output_no_trading_fields`

### Audit (2)
29. `test_audit_provider_accurate`
30. `test_audit_hash_stable`

---

## 七、完成标准

只有以下全部成立才能宣布完成：

- ✅ 单次 real Serenity 最多 2 次 LLM 调用
- ✅ 运行并发不超过 2
- ✅ 不再存在 `_reconstruct_sources()`（已完成）
- ✅ 下游处理使用真实 ResearchSource
- ✅ 假 source ID 无法进入研究链
- ✅ 假 verification_id 无法进入候选链
- ✅ 无来源或全 weak 来源不能进入 shortlist
- ✅ 缺少 red-team 时不能进入 shortlist
- ✅ LLM 不能覆盖 company_name、verification_id、source quality
- ✅ shortlist 由确定性门禁产生
- ✅ 完整双阶段真实数据链测试通过
- ✅ 原有 A 模块信任链测试继续通过（768 tests）
- ✅ Python 全量测试通过
- ✅ 前端类型检查通过
- ✅ status.md 与 HANDOFF_PROMPT.md 准确反映实际状态

---

## 八、验证命令

```bash
# 聚焦测试
.venv\Scripts\python.exe -m unittest tests.test_serenity_agent tests.test_serenity_tools tests.test_evidence_agent tests.test_vertical_flow

# 全量测试
.venv\Scripts\python.exe -m unittest discover -s tests

# 前端类型检查
node node_modules/typescript/lib/tsc.js -p frontend --noEmit
```

---

## 九、风险与应对

### 风险 1: LLM Planner 失败率
- 应对：Pydantic 严格验证 + 明确失败（不静默 fallback）

### 风险 2: 并发控制复杂性
- 应对：ThreadPoolExecutor 逐批处理（每批最多 2）

### 风险 3: 数据工具失败
- 应对：独立捕获错误 + 记录 gaps + 不阻断其他任务

### 风险 4: 测试覆盖不足
- 应对：至少 30 个新测试 + 保持现有 768 tests 通过

---

## 十、当前已完成工作

**日期**: 2026-06-25  
**完成项：**
1. ✅ Serenity verification trust chain（第一优先级）
   - 7 个新测试
   - propose_add_candidate 强制验证完整信任链
   - company_name 从 verification record 读取
   
2. ✅ Serenity tool chain real data context（第二优先级）
   - 3 个新端到端测试
   - run_context 建立
   - `_reconstruct_sources()` 删除
   - 工具使用真实 ResearchSource

**测试基线：**
- Python 全量：768 tests OK (skipped=2)
- 前端类型检查：0 errors
- 新增测试文件：
  - `tests/test_serenity_verification_trust.py` (7 tests)
  - `tests/test_serenity_tool_chain_context.py` (4 tests)
  - `tests/test_serenity_e2e_context.py` (3 tests)

---

## 十一、下一步

从 `SERENITY_REFACTOR_PLAN.md` 的 **Step 2** 开始执行。

每完成一步后汇报：
```
✅ Step X 完成
- 修改了什么：xxx
- 新增测试：yyy (N tests)
- 当前 LLM 调用次数：N
- 当前最大并发数：N
- 聚焦测试：XX tests OK
- 还剩什么：zzz
```

**预计总耗时：约 28 小时**

---

*详细实施方案见 `SERENITY_REFACTOR_PLAN.md`*
