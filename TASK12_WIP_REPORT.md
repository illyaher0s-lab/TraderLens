# Task 12 问题修复进度报告

## Commit
- **SHA**: `fa6e5cf`
- **状态**: WIP (工作进行中)

---

## 问题1：run-research 真实路径修复 (部分完成)

### 已完成修复
1. ✅ `run_industry_research()` 使用 `source_type="manual_stock"` (不再是 "friend_recommendation")
2. ✅ 添加 `created_at` / `updated_at` 字段
3. ✅ 创建 `FakeSerenityRunner` 用于测试
4. ✅ 创建 `FakeValidator` 避免 LLM API key 检查
5. ✅ 修改 `create_research_app` 在提供 `serenity_runner` 时跳过 API key 验证
6. ✅ 添加 `candidate_pool_raw` list→dict 转换逻辑

### 仍在进行
- ❌ `test_friend_stock_api_run_research_persists_output` 失败
- **原因**: `SerenityOutput` schema 复杂，`FakeSerenityRunner` 返回结构不完全匹配
- **错误**: Pydantic 验证失败 (value_chain_layers/suspected_bottleneck_layers 需要 dict，candidate_pool_raw 需要 list，缺少 candidate_shortlist/harness 字段)

### 下一步
需要参考真实 `SerenityOutput` 定义完善 `FakeSerenityRunner` 结构。

---

## 问题2：market data fault 阻断 (已完成逻辑，测试待验证)

### 已完成修复
1. ✅ 在 `create_confirmed_pool()` 添加 fault 检查
2. ✅ 检查 `price_result.fault.state == MarketDataFaultState.ok`
3. ✅ 检查 `benchmark_result.fault.state == MarketDataFaultState.ok`
4. ✅ 非 ok 时抛出 `ValueError` (端点转为 503)

**位置**: `backend/services/friend_stock_flow.py:354-364`

```python
# Check market data faults - must be ok to create pool
from backend.services.live_market_data import MarketDataFaultState
if price_result.fault.state != MarketDataFaultState.ok:
    raise ValueError(
        f"Price data fault: {price_result.fault.state.value} - {price_result.fault.description}"
    )

if benchmark_result.fault.state != MarketDataFaultState.ok:
    raise ValueError(
        f"Benchmark data fault: {benchmark_result.fault.state.value} - {benchmark_result.fault.description}"
    )
```

### 已添加测试 (待验证)
1. `test_friend_stock_api_create_pool_blocks_price_provider_empty_data`
2. `test_friend_stock_api_create_pool_blocks_price_provider_exception`
3. `test_friend_stock_api_create_pool_blocks_benchmark_provider_fault`

### 测试状态
- ❌ 所有 fault 测试失败
- **原因**: 依赖 `FakeSerenityRunner` 工作正常 (需要先修复问题1)

---

## 当前测试结果

```bash
$ .venv/Scripts/python.exe -m pytest tests/test_v1_friend_stock_flow.py tests/test_v1_friend_stock_api.py tests/test_research_api.py tests/test_research_db.py -q

6 failed, 59 passed, 1 warning in 19.55s
```

**失败测试**:
1. `test_friend_stock_api_run_research_persists_output` (SerenityOutput schema)
2. `test_friend_stock_api_create_pool_does_not_use_mock_market_price` (依赖 run-research)
3. `test_friend_stock_api_create_pool_persists_and_reads_back_confirmed_candidate` (依赖 run-research)
4. `test_friend_stock_api_create_pool_blocks_price_provider_empty_data` (依赖 run-research)
5. `test_friend_stock_api_create_pool_blocks_price_provider_exception` (依赖 run-research)
6. `test_friend_stock_api_create_pool_blocks_benchmark_provider_fault` (依赖 run-research)

**根本原因**: 所有失败测试都依赖 `FakeSerenityRunner` 返回正确结构的 `SerenityOutput`。

---

## 阻塞原因分析

### SerenityOutput Schema 复杂性
从错误消息推断，`SerenityOutput` 要求：
- `value_chain_layers`: list of dict (不是 list of str)
- `suspected_bottleneck_layers`: list of dict (不是 list of str)
- `candidate_pool_raw`: list (不是 dict)
- 必填字段: `candidate_shortlist`, `harness`

### 当前 FakeSerenityRunner 问题
已尝试修复但仍不完整。需要：
1. 查看 `backend/services/serenity_agent.py` 中 `SerenityOutput` 的完整定义
2. 确认每个字段的精确类型
3. 更新 `FakeSerenityRunner` 以匹配

---

## 修复建议

### 立即行动
1. **读取 SerenityOutput 定义**:
   ```python
   read_file("backend/services/serenity_agent.py")  # 找到 SerenityOutput class
   ```

2. **完善 FakeSerenityRunner**:
   - 匹配所有必填字段
   - 使用正确的数据结构

3. **验证 run-research 测试通过**

4. **验证 fault 阻断测试通过**

### 预计完成时间
- 修复 `FakeSerenityRunner`: 15分钟
- 运行并验证所有测试: 10分钟
- **总计**: ~25分钟

---

## git status

```bash
$ git status --short

(clean - all changes committed)
```

---

## grep 检查

```bash
$ grep -rn "friend_recommendation\|created_at=.*missing\|would execute\|mock_provider\|TODO" backend/api/research.py backend/services/friend_stock_flow.py tests/test_v1_friend_stock_api.py

(需要运行以确认)
```

---

## 结论

**问题1**: 90% 完成，仅剩 `FakeSerenityRunner` schema 匹配  
**问题2**: 100% 逻辑完成，测试验证依赖问题1

**下一步**: 修复 `FakeSerenityRunner` → 所有测试应该通过
