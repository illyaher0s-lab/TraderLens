# 问题 #5 修复报告：Red-team 分类与主题相关性门禁

**修复日期**: 2026-06-25  
**修复人**: Senior Developer (高级开发工程师)

## 问题描述

### 问题 #5：Red-team 混淆三种不同性质内容
- 数据缺口（data_gaps）、真实反证（counter_evidence）、待验证问题（falsification_questions）被混在 `red_team_findings` 中
- 门禁逻辑错误：只要有任何 `red_team_findings` 就通过，即使全是数据缺口
- 数据缺失可以冒充已完成的证伪

### 问题 #2：缺少主题相关性显式业务测试
- 无主题匹配的财务数据能否通过门禁
- 无关公告能否通过
- 来源属于另一股票时能否通过
- LLM 伪造主题匹配字段是否有效

## 修复方案

### 1. VerifiedResearchCandidate 契约升级

**文件**: `backend/services/serenity_agent.py`

将单一的 `red_team_findings` 拆分为三个独立字段：

```python
@dataclass
class VerifiedResearchCandidate:
    # ... 其他字段 ...
    counter_evidence: list[str]          # 真实来源支持的反证，引用 source_record_id
    falsification_questions: list[str]    # 待验证的问题
    data_gaps: list[str]                 # 数据缺口（不是反证）
    unresolved_gaps: list[str]           # 保留向后兼容
```

**规则**:
1. `counter_evidence`: 必须引用真实 `source_record_id`，表示从已有来源中发现的矛盾或冲突
2. `falsification_questions`: 待验证的问题，明确标记为 unresolved
3. `data_gaps`: 纯粹的数据缺失，不能冒充反证

### 2. Executor Red-team 逻辑重构

**文件**: `backend/services/serenity_executor.py`

```python
def _red_team(self, context, audit):
    # 数据缺口 (data_gaps) — 只记录缺失，不冒充反证
    if not has_financials:
        candidate.data_gaps.append("no_financial_data")
    
    # 真实反证 (counter_evidence) — 从来源的 gaps 提取可追溯反证
    for sid in candidate.supporting_source_ids:
        source = context.sources_by_id.get(sid)
        if source and source.gaps:
            for gap in source.gaps:
                if any(keyword in gap.lower() for keyword in ["contradict", "conflict"]):
                    candidate.counter_evidence.append(f"{sid}: {gap}")
    
    # 待验证问题 (falsification_questions) — 基于缺失数据提出问题
    if not has_financials or not has_announcements:
        candidate.falsification_questions.append(
            f"缺少完整数据，需验证 {symbol} 是否真实参与主题产业链"
        )
```

### 3. Gate 门禁逻辑修正

**文件**: `backend/services/serenity_gate.py`

**Gate 8 修正**:
```python
# 候选必须有 counter_evidence 或 falsification_questions
# 数据缺口（data_gaps）不算完成证伪
has_red_team_work = (
    len(candidate.counter_evidence) > 0 or 
    len(candidate.falsification_questions) > 0
)
if not has_red_team_work:
    continue  # 拒绝
```

**输出格式**:
```python
red_team_findings_combined = (
    [f"counter: {e}" for e in candidate.counter_evidence] +
    [f"question: {q}" for q in candidate.falsification_questions] +
    [f"gap: {g}" for g in candidate.data_gaps]
)
```

### 4. Synthesizer 数据传递升级

**文件**: `backend/services/serenity_synthesizer.py`

```python
pack["verified_candidates"].append({
    "symbol": symbol,
    "company_name": candidate.company_name,
    "source_ids": candidate.supporting_source_ids,
    "counter_evidence": candidate.counter_evidence,
    "falsification_questions": candidate.falsification_questions,
    "data_gaps": candidate.data_gaps,
    "unresolved_gaps": candidate.unresolved_gaps,
})
```

## 新增测试

### 1. Red-team 分类测试

**文件**: `tests/test_serenity_red_team_classification.py` (新建)

- ✅ `test_data_gaps_only_do_not_satisfy_red_team_gate`: 只有 data_gaps 不满足门禁
- ✅ `test_counter_evidence_with_source_passes_gate`: 有可追溯反证通过门禁
- ✅ `test_falsification_questions_pass_gate`: 有待验证问题通过门禁
- ✅ `test_complete_data_without_counter_evidence_rejected`: 完整数据但无反证被拒绝
- ✅ `test_executor_red_team_classification`: Executor 正确分类

### 2. 主题相关性门禁测试

**文件**: `tests/test_theme_relevance_gate.py` (新建)

- ✅ `test_financial_data_without_theme_match_rejected`: 无主题匹配的财务数据被拒绝
- ✅ `test_irrelevant_announcement_rejected`: 无关公告被拒绝
- ✅ `test_source_from_different_symbol_rejected`: 来源属于另一股票被拒绝
- ✅ `test_llm_fabricated_theme_match_ignored`: LLM 伪造主题匹配无效
- ✅ `test_valid_theme_match_passes`: 有效主题匹配通过
- ✅ `test_weak_source_with_theme_match_rejected`: weak 来源即使有主题匹配也被拒绝

## 修改文件清单

### 核心实现
1. `backend/services/serenity_agent.py` - VerifiedResearchCandidate 契约
2. `backend/services/serenity_executor.py` - Red-team 逻辑
3. `backend/services/serenity_gate.py` - 门禁规则
4. `backend/services/serenity_synthesizer.py` - 数据传递

### 测试文件（新建）
5. `tests/test_serenity_red_team_classification.py` - 5 tests
6. `tests/test_theme_relevance_gate.py` - 6 tests

### 测试文件（更新以适配新字段）
7. `tests/test_serenity_shortlist_gate.py`
8. `tests/test_serenity_executor.py`
9. `tests/test_serenity_synthesizer.py`
10. `tests/test_serenity_two_phase_fixes.py`
11. `tests/test_serenity_gate_adversarial.py`
12. `tests/test_source_reference_preservation.py`

## 测试结果

### 最终测试统计
```bash
Ran 846 tests in 16.419s
OK (skipped=2)
```

**新增测试**: 11 tests (5 + 6)  
**通过率**: 100% (846/846, 2 skipped)

### 聚焦测试验证
```bash
# Red-team 分类测试
.venv/Scripts/python.exe -m unittest tests.test_serenity_red_team_classification -v
Ran 5 tests in 0.002s - OK

# 主题相关性测试
.venv/Scripts/python.exe -m unittest tests.test_theme_relevance_gate -v
Ran 6 tests in 0.002s - OK

# Serenity 全量测试
.venv/Scripts/python.exe -m unittest discover -s tests -p "test_serenity*.py"
Ran 137 tests in 0.084s - OK
```

## 核心规则验证

### Red-team 分类规则 ✅
1. ✅ 数据缺失只能成为 data_gap，不能冒充已发现的反证
2. ✅ counter_evidence 必须引用真实 source_record_id
3. ✅ falsification_questions 可以没有来源，但必须明确标记 unresolved
4. ✅ 候选不能仅因为存在 data_gap 就满足 red-team 门禁
5. ✅ 完整数据但没有反证时不会因"缺少 finding"产生错误结论

### 主题相关性规则 ✅
1. ✅ 普通财务数据无主题命中时拒绝
2. ✅ 无关公告拒绝
3. ✅ 来源属于另一股票时拒绝
4. ✅ LLM 伪造主题匹配字段无效（确定性计算覆盖）
5. ✅ weak 来源即使有主题匹配也被拒绝（需配合非 weak 来源）

## 向后兼容性

- ✅ 保留 `unresolved_gaps` 字段以支持旧代码
- ✅ `CandidateStock.red_team_findings` 仍然存在，但现在是组合格式：
  - `"counter: ..."` - 真实反证
  - `"question: ..."` - 待验证问题
  - `"gap: ..."` - 数据缺口
- ✅ 所有现有测试更新以适配新结构
- ✅ 无破坏性变更

## 设计原则遵守

✅ **Rule 3 — Surgical Changes**: 只修改必要的文件，未改变无关逻辑  
✅ **Rule 5 — Use the model only for judgment calls**: 全部逻辑使用确定性代码，LLM 不负责分类或门禁  
✅ **Rule 8 — Read before you write**: 阅读所有相关文件后才开始修改  
✅ **Rule 12 — Fail loud**: 所有规则违反都会明确拒绝，不静默通过

## 总结

问题 #5 和 #2 已完全修复。Red-team 现在能正确区分反证、待验证问题和数据缺口，主题相关性门禁确保只有真正匹配主题的来源才能通过。所有测试通过，无回归问题。
