# Serenity 审计准确性修复报告（问题 #7）

**日期**: 2026-06-25  
**状态**: ✅ 完成  
**TDD 流程**: RED → GREEN  

---

## 修复概览

完成 Serenity 审计字段准确性修复，所有审计信息现在真实反映执行状态。

### 测试结果

```
审计准确性测试: 10/10 通过
Serenity 回归测试: 155/155 通过
完整测试套件: 880 tests OK (skipped=2)
```

---

## RED 阶段发现的问题

### 1. `provider` 字段 ❌
- **问题**: 硬编码为 "langgraph"
- **失败测试**: `test_audit_provider_from_client`

### 2. `replayable` 字段 ❌
- **问题**: 硬编码为 `True`，但未持久化回放包
- **失败测试**: `test_replayable_false_without_persistence`

### 3. `token_usage` 字段 ❌
- **问题**: 空字典，未汇总 Planner 和 Synthesizer 的真实返回值
- **失败测试**: `test_token_usage_aggregates_both_calls`
- **期望**: `{"input_tokens": 300, "output_tokens": 150}`

### 4. `model` 字段 ❌
- **问题**: 未从实际客户端获取

### 5. `tool_calls_hash` 字段 ⚠️
- **问题**: 只基于来源/候选数量，不敏感参数变化
- **失败测试**: `test_hash_sensitive_to_parameter_changes`

---

## GREEN 阶段实施方案

### 修改 1: `serenity_planner.py`

**添加响应元数据保存**:
```python
def __init__(self, llm_client):
    self.llm_client = llm_client
    self.last_response_metadata = None  # 保存响应元数据（不包含敏感 prompt）

def plan(self, theme, manual_candidates: list) -> ResearchPlan:
    ...
    response = self.llm_client.create_message(...)
    
    # 保存响应元数据用于审计
    self.last_response_metadata = {
        "model": response.get("model"),
        "usage": response.get("usage"),
    }
    ...
```

---

### 修改 2: `serenity_synthesizer.py`

**添加响应元数据保存**:
```python
def __init__(self, llm_client):
    self.llm_client = llm_client
    self.last_response_metadata = None  # 保存响应元数据

def synthesize(self, theme, context, audit) -> ResearchSynthesis:
    ...
    response = self.llm_client.create_message(...)
    
    # 保存响应元数据用于审计
    self.last_response_metadata = {
        "model": response.get("model"),
        "usage": response.get("usage"),
    }
    ...
```

---

### 修改 3: `serenity_executor.py`

**线程池生命周期管理**:
```python
def __init__(self, serenity_tools, validator, db):
    ...
    self._executor = None  # 延迟初始化

def execute(self, plan, context, audit, theme_name="", theme_background=""):
    try:
        # 初始化线程池
        self._executor = ThreadPoolExecutor(max_workers=MAX_RESEARCH_CONCURRENCY)
        
        # 执行所有步骤...
        
    finally:
        # 确保关闭线程池
        if self._executor:
            self._executor.shutdown(wait=True)
            self._executor = None
```

**原因**: 防止线程泄漏，确保每次执行后线程池正确关闭。

---

### 修改 4: `serenity_agent.py` - 核心修改

**4.1 设置 model 和 provider**:
```python
audit.mode = "real_two_phase"

# 从 llm_client 获取
audit.model = getattr(self.llm_client, 'get_model_name', lambda: "unknown")()
audit.provider = getattr(self.llm_client, 'get_provider_name', lambda: "unknown")()

# 初始化 token_usage
audit.token_usage = {}
```

---

**4.2 汇总 token usage**:
```python
# Phase 1: Planner
planner = ResearchPlanner(self.llm_client)
plan = planner.plan(theme, manual_candidates)

# 汇总 Planner token usage
if planner.last_response_metadata and planner.last_response_metadata.get("usage"):
    usage = planner.last_response_metadata["usage"]
    audit.token_usage["input_tokens"] = audit.token_usage.get("input_tokens", 0) + usage.get("input_tokens", 0)
    audit.token_usage["output_tokens"] = audit.token_usage.get("output_tokens", 0) + usage.get("output_tokens", 0)

# Phase 3: Synthesizer
synthesizer = ResearchSynthesizer(self.llm_client)
synthesis = synthesizer.synthesize(theme, context, audit)

# 汇总 Synthesizer token usage
if synthesizer.last_response_metadata and synthesizer.last_response_metadata.get("usage"):
    usage = synthesizer.last_response_metadata["usage"]
    audit.token_usage["input_tokens"] = audit.token_usage.get("input_tokens", 0) + usage.get("input_tokens", 0)
    audit.token_usage["output_tokens"] = audit.token_usage.get("output_tokens", 0) + usage.get("output_tokens", 0)
```

---

**4.3 基于真实 tool calls 计算 hash**:
```python
# 收集 tool calls 用于 hash
tool_calls_for_hash = []

# Phase 1: 记录 Planner 调用
tool_calls_for_hash.append({
    "tool": "research_planner",
    "input": {
        "theme_name": theme.theme_name,
        "research_mode": theme.research_mode,
    },
    "output_summary": {
        "keywords_count": len(plan.keywords),
        "seed_symbols_count": len(plan.seed_symbols),
        "falsification_questions_count": len(plan.falsification_questions),
    }
})

# Phase 2: 记录 Executor 结果
tool_calls_for_hash.append({
    "tool": "deterministic_executor",
    "input": {
        "seed_symbols": plan.seed_symbols,
        "keywords": plan.keywords,
    },
    "output_summary": {
        "sources_count": len(context.sources_by_id),
        "candidates_count": len(context.verified_candidates_by_symbol),
    }
})

# Phase 3: 记录 Synthesizer 调用
tool_calls_for_hash.append({
    "tool": "research_synthesizer",
    "input": {
        "candidates_count": len(context.verified_candidates_by_symbol),
    },
    "output_summary": {
        "demand_driver": synthesis.demand_driver[:50] if synthesis.demand_driver else "",
        "value_chain_layers_count": len(synthesis.value_chain_layers),
        "candidate_rationales_count": len(synthesis.candidate_rationales),
    }
})

# 计算 hash（基于规范化 JSON）
import json
tool_calls_json = json.dumps(tool_calls_for_hash, sort_keys=True, ensure_ascii=False)
audit.tool_calls_hash = hashlib.sha256(tool_calls_json.encode("utf-8")).hexdigest()
audit.tool_calls = tool_calls_for_hash
```

**原因**: 
- 包含工具名、确定性输入参数、结果摘要
- 使用 `sort_keys=True` 确保相同轨迹产生相同 hash
- 对参数或结果变化敏感

---

**4.4 修复 replayable 字段**:
```python
harness=AgentHarnessConfig(
    provider="langgraph",  # harness provider 固定为架构类型（契约限制）
    tool_whitelist=["research_planner", "deterministic_executor", "research_synthesizer"],
    max_steps=2,
    token_budget=3072,
    replayable=False,  # 未持久化回放包
),
```

**说明**: 
- `harness.provider` 受契约约束，只能是 "stub" 或 "langgraph"（架构类型）
- 实际 LLM provider 保存在 `audit.provider`
- `replayable=False` 直到实现持久化

---

## 测试策略调整

### 关键点
1. 所有测试通过真实 `SerenityAgentRunner._run_agent_two_phase()` 验证
2. 使用 wrapper 捕获 `audit` 对象（因为 `run()` 不直接返回）
3. `harness.provider` 保持为 "langgraph"（架构类型）
4. `audit.provider` 验证实际 LLM provider

### 测试覆盖
- ✅ audit.provider == llm_client.get_provider_name()
- ✅ audit.model == llm_client.get_model_name()
- ✅ output.harness.replayable is False
- ✅ 完整 run 精确 2 次 LLM 调用
- ✅ audit.token_usage 汇总两次真实返回值
- ✅ audit.tool_calls_hash 基于真实内容
- ✅ 参数变化时 hash 不同
- ✅ 相同轨迹 hash 相同
- ✅ run 后无线程泄漏
- ✅ 输出不含交易字段

---

## 文件修改清单

**生产代码**:
1. `backend/services/serenity_planner.py` - 保存响应元数据
2. `backend/services/serenity_synthesizer.py` - 保存响应元数据
3. `backend/services/serenity_executor.py` - 线程池生命周期管理
4. `backend/services/serenity_agent.py` - 汇总 token、计算准确 hash、设置 provider/model

**测试文件**:
5. `tests/test_serenity_audit_accuracy.py` - 重写为完整链路测试

---

## 架构决策

### 为什么 harness.provider 保持 "langgraph"？

`AgentHarnessConfig.provider` 字段定义为 `Literal["stub", "langgraph"]`，这是一个**架构类型标识**，不是 LLM provider：

- `"stub"` = 确定性模板模式
- `"langgraph"` = 双阶段 LLM 架构

实际的 LLM provider（如 "openai", "anthropic", "fake-provider"）保存在 `audit.provider`。

---

## 验证结果

```bash
# 审计准确性测试
Ran 10 tests in 0.173s
OK

# Serenity 回归测试
Ran 155 tests in 0.207s
OK

# 完整测试套件
Ran 880 tests in 12.313s
OK (skipped=2)
```

**无回归，所有修改符合 Rule 3（Surgical Changes）。**

---

## 遵循的约束

✅ 只修改允许的文件  
✅ 不修改 serenity_agent.py 的 Agent 1 相关代码  
✅ 不修改 status.md  
✅ Executor 自行关闭线程池  
✅ 最大并发仍为 2  
✅ token_usage 汇总真实值  
✅ provider/model 来自实际客户端  
✅ replayable=False（未持久化）  
✅ tool_calls_hash 基于真实内容  

---

**报告生成时间**: 2026-06-25 18:01  
**完成状态**: ✅ GREEN - 所有测试通过
