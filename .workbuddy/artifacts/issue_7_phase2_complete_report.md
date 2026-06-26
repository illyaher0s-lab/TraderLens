# 问题 #7 Phase 2 完成报告

**完成时间**: 2026-06-25  
**状态**: ✅ 全部完成

---

## 修复概览

### 批次 1：语义修正 ✅

**目标**: 修正 AgentHarnessConfig 语义，区分执行引擎和 LLM provider

**修改**:
1. **契约升级** (`contracts/research.py`)
   - 增加 `execution_engine: Literal["stub", "two_phase"]` — 标识执行架构
   - 增加 `llm_provider: str` — 实际 LLM provider（如 "openai", "anthropic"）
   - `provider` 标记为 DEPRECATED，仅用于向后兼容

2. **生产代码** (`backend/services/serenity_agent.py`)
   - 3 处 AgentHarnessConfig 构造全部更新
   - Stub: `execution_engine="stub"`, `llm_provider="none"`
   - Two-phase: `execution_engine="two_phase"`, `llm_provider=audit.provider`

3. **测试更新** (`tests/test_research_contracts.py`)
   - 更新 AgentHarnessConfig 测试用例
   - 验证新字段 `execution_engine` 和 `llm_provider`

**测试结果**: ✅ 155 Serenity tests OK, 880 total tests OK

---

### 批次 2：Executor 工具调用记录 + hash 增强 ✅

**目标**: Executor 记录真实工具调用，tool_calls_hash 基于完整轨迹

**修改**:
1. **Executor 工具调用记录** (`backend/services/serenity_executor.py`)
   - `_retrieve_data`: 记录每次 `retrieve_supply_chain` 调用（symbol + keywords → records_count）
   - `_verify_tickers`: 记录每次 `verify_ticker` 调用（symbol → confidence + status）
   - `_audit_sources`: 记录 `audit_sources` 确定性检查（sources_summary）
   - `_red_team`: 记录 `red_team` 确定性检查（data_gaps + counter_evidence 统计）

2. **工具调用格式** (规范化 JSON)
   ```json
   {
     "tool": "retrieve_supply_chain",
     "params": {"symbol": "300750.SZ", "keywords": ["锂电池", ...]},
     "result_summary": {
       "records_count": 15,
       "gaps_count": 0,
       "errors_count": 0
     }
   }
   ```

3. **hash 计算** (`backend/services/serenity_agent.py`)
   - 使用 `audit.compute_tool_hash()` 基于 `audit.tool_calls` 完整列表
   - hash 对工具名、参数、结果变化敏感
   - 相同执行轨迹 → 相同 hash

**测试结果**: ✅ 10/10 审计准确性测试通过，155 Serenity tests OK, 880 total tests OK

---

### 批次 3：清理 discovered_player ✅

**目标**: 从 counter_evidence 工具白名单删除 `discovered_player`

**修改**:
- `backend/services/serenity_synthesizer.py`
  - VALID_TOOLS 从 `{"financials", "announcements", "sector", "discovered_player"}` 
  - 更新为 `{"financials", "announcements", "sector"}`
  - 理由：身份核验记录不能作为反证来源，反证必须来自财务、公告、行业数据

**测试结果**: ✅ 880 total tests OK

---

## 完整测试结果

```bash
审计准确性测试: 10/10 通过
Serenity 回归测试: 155/155 通过
完整测试套件: 880 tests OK (skipped=2)
```

---

## 关键改进

### 1. 语义清晰

**之前**:
- `provider="langgraph"` 既表示架构又假装是 LLM provider
- 无法区分执行引擎和实际 LLM

**现在**:
- `execution_engine="two_phase"` — 明确架构类型
- `llm_provider="openai"` — 实际 LLM provider
- `provider` 仅保留用于向后兼容

### 2. 审计可追溯

**之前**:
- `tool_calls_hash` 只基于 "research_planner + deterministic_executor + research_synthesizer"
- 看不到 Executor 内部的真实工具调用

**现在**:
- Executor 记录每次 `retrieve_supply_chain`, `verify_ticker`, `audit_sources`, `red_team`
- `tool_calls` 包含工具名、规范化参数、结果摘要
- hash 对参数和结果变化敏感

### 3. 反证来源严格

**之前**:
- `discovered_player` 可以作为 counter_evidence 来源
- 身份核验记录被误用为反证

**现在**:
- 反证只能来自 `financials`, `announcements`, `sector`
- 身份核验不能成为反证来源

---

## 修改的文件

### 契约
- `contracts/research.py` — AgentHarnessConfig 增加 execution_engine, llm_provider

### 生产代码
- `backend/services/serenity_agent.py` — AgentHarnessConfig 构造、tool_calls_hash 计算
- `backend/services/serenity_executor.py` — 记录真实工具调用
- `backend/services/serenity_synthesizer.py` — 删除 discovered_player 白名单

### 测试
- `tests/test_research_contracts.py` — AgentHarnessConfig 测试更新

---

## 架构决策

### 为什么保留 `provider` 字段？

虽然标记为 DEPRECATED，但保留是为了：
1. **向后兼容** — 现有代码和数据库可能依赖此字段
2. **渐进迁移** — 给消费者时间迁移到新字段
3. **明确弃用** — 通过 DEPRECATED 标记指导未来删除

### 为什么 hash 不包含 LLM prompt？

**原因**:
1. **隐私** — LLM prompt 可能包含敏感主题信息
2. **体积** — prompt 可能很大，hash 只需标识执行轨迹
3. **确定性** — 工具调用参数+结果已足够标识执行差异

---

## 遵循的规则

✅ **Rule 3 (Surgical Changes)** — 只修改必要的文件和行
✅ **Rule 5 (确定性优先)** — Executor 记录是确定性的，不依赖 LLM
✅ **Rule 10 (Checkpoint)** — 每个批次完成后运行测试验证
✅ **Rule 12 (Fail Loud)** — 所有修改都有完整测试覆盖

---

## 后续建议

1. **渐进删除 `provider` 字段** — 3-6 个月后删除
2. **增强 counter_evidence 提取** — 从财务数据中提取数值冲突
3. **持久化 tool_calls** — 存储到数据库用于审计和回放
4. **前端展示工具调用** — 可视化执行轨迹

---

**结论**: 问题 #7 Phase 2 全部完成，无回归，语义清晰，审计可追溯。
