# Serenity 审计准确性分析报告

**日期**: 2026-06-25  
**阶段**: TDD 红灯阶段  
**测试文件**: `tests/test_serenity_audit_accuracy.py`  

---

## 测试结果概览

**总计**: 10 tests  
**通过**: 9 tests  
**失败**: 1 test  

```
FAILED: test_token_usage_aggregates_both_calls
```

---

## 当前审计字段的真实来源

### 1. `provider` 字段

**位置**: `backend/services/serenity_agent.py:923`  
**当前值**: 硬编码 `"langgraph"`  
**问题**: 伪装为 langgraph，但实际不是  

```python
harness=AgentHarnessConfig(
    provider="langgraph",  # ❌ 硬编码错误值
    ...
)
```

**应该来自**: `llm_client.get_provider_name()` 或明确配置

---

### 2. `replayable` 字段

**位置**: `backend/services/serenity_agent.py:927`  
**当前值**: 硬编码 `True`  
**问题**: 声称可回放，但实际没有持久化回放数据包  

```python
replayable=True,  # ❌ 未持久化回放包
```

**应该**: 只有在实际持久化后才设为 `True`

---

### 3. `token_usage` 字段

**位置**: `backend/services/serenity_agent.py:843-937` (整个 `_run_agent_two_phase` 方法)  
**当前值**: `{}` (空字典)  
**问题**: **未从 Planner 和 Synthesizer 的响应中提取和汇总 token 使用量**  

**失败测试**:
```python
FAIL: test_token_usage_aggregates_both_calls
AssertionError: None != 300
```

**应该**:
- Planner 响应: `{"input_tokens": 100, "output_tokens": 50}`
- Synthesizer 响应: `{"input_tokens": 200, "output_tokens": 100}`
- 审计汇总: `{"input_tokens": 300, "output_tokens": 150}`

**缺失的代码**: 在 Phase 1 和 Phase 3 之后，需要提取 `usage` 字段并汇总

---

### 4. `model` 字段

**位置**: `backend/services/serenity_agent.py:843-937`  
**当前值**: 未设置 (可能为空或默认值)  
**问题**: 未从实际 LLM 客户端获取模型名称  

**应该来自**: `llm_client.get_model_name()` 或响应中的 `model` 字段

---

### 5. `tool_calls_hash` 字段

**位置**: `backend/services/serenity_agent.py:933-935`  
**当前值**: 基于长度的简单 hash  

```python
audit.tool_calls_hash = hashlib.sha256(
    f"two_phase:{len(context.sources_by_id)}:{len(context.verified_candidates_by_symbol)}".encode("utf-8")
).hexdigest()
```

**问题**: 
- ✅ 对数量变化敏感（通过测试）
- ✅ 相同轨迹产生相同 hash（通过测试）
- ⚠️ 但不包含实际调用参数和结果内容

**建议**: 当前实现足够，但可以考虑包含 `plan` 和 `synthesis` 的序列化内容以提高准确性

---

### 6. LLM 调用次数

**位置**: `backend/services/serenity_agent.py:874-901`  
**当前值**: 精确 2 次（Planner + Synthesizer）  
**状态**: ✅ 通过测试  

---

### 7. 线程清理

**位置**: `backend/services/serenity_executor.py`  
**状态**: ✅ 通过测试（无线程泄漏）  

---

## 需要修改的函数和最小方案

### 修改 1: 修复 `provider` 字段

**文件**: `backend/services/serenity_agent.py`  
**函数**: `_run_agent_two_phase` (行 843-937)  
**位置**: 行 923  

**最小方案**:
```python
# 从 llm_client 获取 provider
provider_name = getattr(self.llm_client, 'get_provider_name', lambda: "unknown")()

harness=AgentHarnessConfig(
    provider=provider_name,  # ✅ 使用实际 provider
    ...
)
```

---

### 修改 2: 修复 `token_usage` 汇总（**失败测试**）

**文件**: `backend/services/serenity_agent.py`  
**函数**: `_run_agent_two_phase` (行 843-937)  
**位置**: Phase 1 之后（行 876）和 Phase 3 之后（行 898）  

**最小方案**:

```python
# Phase 1: Research Planner (LLM 1/2)
planner = ResearchPlanner(self.llm_client)
try:
    plan = planner.plan(theme, manual_candidates)
    # ✅ 提取 Planner token usage
    planner_response = planner.last_response  # 需要 ResearchPlanner 保存响应
    if planner_response and "usage" in planner_response:
        usage = planner_response["usage"]
        audit.token_usage["input_tokens"] = audit.token_usage.get("input_tokens", 0) + usage.get("input_tokens", 0)
        audit.token_usage["output_tokens"] = audit.token_usage.get("output_tokens", 0) + usage.get("output_tokens", 0)
except Exception as exc:
    audit.errors.append(f"Planner failed: {exc}")
    raise ValueError(f"Research Planner failed: {exc}") from exc

# ... Phase 2 (Executor) ...

# Phase 3: Research Synthesizer (LLM 2/2)
synthesizer = ResearchSynthesizer(self.llm_client)
try:
    synthesis = synthesizer.synthesize(theme, context, audit)
    # ✅ 提取 Synthesizer token usage
    synthesizer_response = synthesizer.last_response  # 需要 ResearchSynthesizer 保存响应
    if synthesizer_response and "usage" in synthesizer_response:
        usage = synthesizer_response["usage"]
        audit.token_usage["input_tokens"] = audit.token_usage.get("input_tokens", 0) + usage.get("input_tokens", 0)
        audit.token_usage["output_tokens"] = audit.token_usage.get("output_tokens", 0) + usage.get("output_tokens", 0)
except Exception as exc:
    audit.errors.append(f"Synthesizer failed: {exc}")
    raise ValueError(f"Research Synthesizer failed: {exc}") from exc
```

**额外需要**:
- `ResearchPlanner.plan()` 需要保存 `self.last_response`
- `ResearchSynthesizer.synthesize()` 需要保存 `self.last_response`

---

### 修改 3: 修复 `model` 字段

**文件**: `backend/services/serenity_agent.py`  
**函数**: `_run_agent_two_phase` (行 843-937)  
**位置**: 行 868 之后  

**最小方案**:
```python
# Compute input hash
input_raw = f"{theme.theme_id}:{theme.theme_name}:{theme.research_mode}"
audit.input_hash = hashlib.sha256(input_raw.encode("utf-8")).hexdigest()
audit.mode = "real_two_phase"

# ✅ 设置 model 和 provider
audit.model = getattr(self.llm_client, 'get_model_name', lambda: "unknown")()
audit.provider = getattr(self.llm_client, 'get_provider_name', lambda: "unknown")()
```

---

### 修改 4: 修复 `replayable` 字段

**文件**: `backend/services/serenity_agent.py`  
**函数**: `_run_agent_two_phase` (行 843-937)  
**位置**: 行 927  

**最小方案**:
```python
# 默认 replayable=False，除非实际持久化了回放包
replayable = False
# TODO: 如果实现了持久化，在持久化成功后设为 True

harness=AgentHarnessConfig(
    provider=provider_name,
    tool_whitelist=["research_planner", "deterministic_executor", "research_synthesizer"],
    max_steps=2,
    token_budget=3072,
    replayable=replayable,  # ✅ 基于实际持久化状态
),
```

---

## 依赖修改

### `backend/services/serenity_planner.py`

**函数**: `ResearchPlanner.plan()`  
**需要添加**: 保存 `self.last_response`  

```python
def plan(self, theme, manual_candidates: list) -> ResearchPlan:
    ...
    response = self.llm_client.create_message(
        messages=[{"role": "user", "content": prompt}],
        system=self.SYSTEM_PROMPT,
        max_tokens=1024,
    )
    
    # ✅ 保存响应用于审计
    self.last_response = response
    
    # Extract text from response
    text = self._extract_text(response)
    ...
```

---

### `backend/services/serenity_synthesizer.py`

**函数**: `ResearchSynthesizer.synthesize()`  
**需要添加**: 保存 `self.last_response`  

```python
def synthesize(self, theme: ThemeInput, context: SerenityRunContext, audit: SerenityAgentAudit) -> ResearchSynthesis:
    ...
    response = self.llm_client.create_message(
        messages=[{"role": "user", "content": research_pack}],
        system=self.SYSTEM_PROMPT,
        max_tokens=2048,
    )
    
    # ✅ 保存响应用于审计
    self.last_response = response
    
    # Extract text from response
    text = self._extract_text(response)
    ...
```

---

## 修改优先级

### P0（必须修复）
1. ✅ **token_usage 汇总** - 当前失败测试
2. ⚠️ **provider 字段** - 伪装问题

### P1（应该修复）
3. **model 字段** - 准确性
4. **replayable 字段** - 诚实性

### P2（可选优化）
5. **tool_calls_hash** - 已通过测试，但可以更准确

---

## 实施建议

1. **先修复 token_usage**（使测试通过）
2. **修复 provider/model 字段**（准确性）
3. **修复 replayable 字段**（诚实性）
4. **运行完整测试套件验证无回归**

---

## 不允许的修改（本阶段）

- ❌ 修改 `serenity_agent.py` 之外的生产代码逻辑
- ❌ 修改现有测试文件
- ❌ 修改 `status.md`
- ❌ 运行全量测试

---

**报告生成时间**: 2026-06-25 17:46  
**TDD 阶段**: 🔴 红灯 → 准备进入绿灯阶段
