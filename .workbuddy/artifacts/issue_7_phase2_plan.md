# 问题 #7 进一步修复计划

**当前状态**: 基础审计修复已完成（880 tests pass）  
**待完成**: 语义修正、完整工具调用记录、hash 敏感性增强

---

## 需要修复的问题

### 1. AgentHarnessConfig 语义错误 ❌
**问题**: 当前将双阶段执行器标记为 "langgraph"，这是错误的
**方案**: 
- 增加 `execution_engine: Literal["stub", "two_phase"]`
- 增加 `llm_provider: str` 使用实际 provider
- `provider` 字段标记为 DEPRECATED

**已完成**: ✅ 契约已修改

**待修改位置**:
- `backend/services/serenity_agent.py:234` (stub 模式)
- `backend/services/serenity_agent.py:418` (legacy 模式)
- `backend/services/serenity_agent.py:1036` (two_phase 模式) ⭐
- 所有测试中的 AgentHarnessConfig 构造

---

### 2. test_audit_model_from_client 不完整 ❌
**问题**: 当前只检查 output 存在，未捕获 audit 验证 model 字段
**方案**: 使用 wrapper 捕获 audit，断言 `audit.model == llm_client.get_model_name()`

---

### 3. Executor 未记录真实工具调用 ❌
**问题**: 当前 tool_calls 只有 3 个阶段摘要，缺少真实工具调用
**方案**: Executor 执行时记录：
- `retrieve_supply_chain(keywords, symbols)` → 结果摘要
- `verify_ticker(symbol)` → verification_id
- `audit_sources` → 结果
- `red_team_falsify` → 结果

**修改位置**: `backend/services/serenity_executor.py`
- `_retrieve_data` 方法
- `_verify_tickers` 方法
- `_audit_sources` 方法
- `_red_team` 方法

需要在 `execute()` 方法中收集这些调用，添加到 `audit.tool_calls` 或返回给 caller。

---

### 4. tool_calls_hash 不够敏感 ⚠️
**问题**: 当前只基于 3 个阶段摘要，不包含 Executor 内部的真实工具调用
**方案**: hash 必须基于：
- Planner 输入/输出
- Executor 所有工具调用（retrieve, verify, audit, red-team）
- Synthesizer 输入/输出

**依赖**: 修复 #3 后才能实现

---

### 5. 测试不完整 ⚠️
**当前测试**:
- ✅ 参数变化（不同主题）→ hash 不同
- ✅ 相同输入 → hash 相同

**缺少测试**:
- ❌ 工具结果变化（相同主题，不同数据检索结果）→ hash 不同
- ❌ 只有主题 ID 变化但执行轨迹相同 → hash 不变（需要 mock 数据工具）

---

### 6. discovered_player 在 counter_evidence 白名单 ❌
**问题**: 身份核验记录（discovered_player）不应作为反证来源
**方案**: 从反证工具白名单删除

**修改位置**: 查找所有 counter_evidence 验证逻辑中的工具白名单

---

## 实施顺序

### Phase 1: 语义修正（高优先级）
1. ✅ 修改 `contracts/research.py` - AgentHarnessConfig
2. ⏳ 修改 `backend/services/serenity_agent.py` - 3 处 AgentHarnessConfig 构造
3. ⏳ 修改所有测试中的 AgentHarnessConfig 构造
4. ⏳ 运行测试验证兼容性

### Phase 2: Executor 工具调用记录（中优先级）
1. ⏳ 修改 `backend/services/serenity_executor.py`
   - 添加 `self.tool_calls_log = []`
   - 在每个方法中记录工具调用
   - `execute()` 方法返回 tool_calls 或写入 audit
2. ⏳ 修改 `backend/services/serenity_agent.py`
   - 收集 Executor 的 tool_calls
   - 合并到最终 audit.tool_calls
3. ⏳ 重新计算 tool_calls_hash

### Phase 3: 测试增强（中优先级）
1. ⏳ 修改 `test_audit_model_from_client` - 捕获 audit
2. ⏳ 添加工具结果变化的 hash 测试
3. ⏳ 添加主题 ID 不影响 hash 的测试（需要 mock）

### Phase 4: discovered_player 清理（低优先级）
1. ⏳ 查找 counter_evidence 验证逻辑
2. ⏳ 删除 discovered_player 白名单项
3. ⏳ 运行相关测试

---

## 技术细节

### Executor 工具调用格式
```python
{
    "tool": "retrieve_supply_chain",
    "input": {
        "keywords": ["锂电池"],
        "symbols": ["300750.SZ"],
    },
    "output_summary": {
        "sources_count": 5,
        "source_types": ["financial_report", "announcement"],
    }
}
```

### tool_calls_hash 计算
```python
# 完整调用链
tool_calls = [
    # Planner
    {"tool": "research_planner", ...},
    # Executor - 真实工具调用
    {"tool": "retrieve_supply_chain", ...},
    {"tool": "retrieve_supply_chain", ...},
    {"tool": "verify_ticker", ...},
    {"tool": "verify_ticker", ...},
    {"tool": "audit_sources", ...},
    {"tool": "red_team_falsify", ...},
    # Synthesizer
    {"tool": "research_synthesizer", ...},
]

# 规范化 JSON hash
import json
tool_calls_json = json.dumps(tool_calls, sort_keys=True, ensure_ascii=False)
audit.tool_calls_hash = hashlib.sha256(tool_calls_json.encode("utf-8")).hexdigest()
```

---

## 风险和依赖

### 风险
1. ⚠️ AgentHarnessConfig 修改可能影响前端解析
2. ⚠️ Executor 工具调用记录可能增加内存占用
3. ⚠️ 旧数据库记录可能不兼容新契约

### 依赖
- Phase 2 依赖 Phase 1 完成
- Phase 3 部分测试依赖 Phase 2 完成

---

## 下一步

**建议**: 由于修改范围较大，建议分批实施：
1. **批次 1**: Phase 1（语义修正）→ 运行全量测试
2. **批次 2**: Phase 2（Executor 记录）→ 运行聚焦测试
3. **批次 3**: Phase 3 + 4（测试增强 + 清理）→ 最终验证

当前已完成契约修改，等待指令继续。
