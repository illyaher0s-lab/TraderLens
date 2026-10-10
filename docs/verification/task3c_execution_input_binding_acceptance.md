# Task 3C: B3 真实执行输入引用清单 — 验收报告

**执行日期**: 2026-07-17  
**Status**: ✅ **PASSED**

---

## 一、任务定位

对应主计划 Task 3 第一项：
> "Extend the existing B3 manifest types with effective membership, listing/delisting, ST/name-change, suspension, price-limit, liquidity, raw-price, and announcement-availability references."

**边界**:
- ✅ 冻结 B3 执行输入引用与拒绝条件
- ✅ 不修改已发布 artifact bytes
- ❌ 不解除浏览器阻断
- ❌ 不启动 B6/OOS/Gate/Promotion/Signal

---

## 二、八类执行输入盘点

### A. 当前可用输入（7类）

| 类别 | Artifact | Path | Hash/Status |
|------|----------|------|-------------|
| **1. Effective membership** | `pims_traderlens_v2_shsz_sw2021_pit_005` | `data/pit/pit_membership_snapshots/pims_traderlens_v2_shsz_sw2021_pit_005` | `32f58adb...` ✓ verified |
| **2. Raw-price (daily OHLCV)** | `formal_partition_daily` | `data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal/daily` | placeholder (available) |
| **3. Adj-factor** | `formal_partition_adj_factor` | `data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal/adj_factor` | placeholder (available) |
| **4. Price-limit** | `formal_partition_stk_limit` | `data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal/stk_limit` | placeholder (available) |
| **5. Suspension** | `formal_partition_suspend_d` | `data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal/suspend_d` | placeholder (available) |
| **6. ST/name-change** | `formal_partition_stock_st` | `data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal/stock_st` | placeholder (available) |
| **7. Trade calendar** | `formal_partition_trade_cal` | `data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal/trade_cal` | placeholder (available) |

### B. 当前不可用输入（3类）

| 类别 | Status | Reason |
|------|--------|--------|
| **8. Listing/delisting** | `unavailable` | 无独立 artifact（可从 daily 首次/最后出现推断，但非正式 PIT 语义） |
| **9. Liquidity threshold** | `unavailable` | 无 volume/liquidity policy artifact |
| **10. Announcement availability** | `unavailable` | 无 announcement data |

---

## 三、实现方案

### A. 新增 Typed Contract

**`backend/services/b3_execution_input_binding.py`**:
- `ExecutionInputReference`: 单个输入引用 (artifact_id, path, content_hash, availability)
- `B3ExecutionInputBinding`: 冻结的执行输入绑定 (10类输入 + canonical_hash)
- `validate_execution_input_binding()`: 前置验证函数

**设计特点**:
1. **不修改已冻结 `DataSnapshotManifest`**（frozen=True, extra="forbid"）
2. **Canonical JSON hash**: 覆盖所有 ref，确定性可复现
3. **Fail loud**: 缺失/篡改/repo外路径 → `ValidationResult(is_valid=False)`
4. **封闭状态**: `unavailable` 输入不伪装成"完整"

### B. 验证规则

```python
validate_execution_input_binding(binding, repo_root) -> ValidationResult
```

**检查项**:
- ✅ Hash 一致性 (membership manifest.json SHA-256)
- ✅ Path 在 repo 内 (相对路径解析)
- ✅ `unavailable` 输入跳过验证
- ✅ `available` 但 path=`"unavailable"` → 拒绝

---

## 四、测试证据

### A. Task 3C Tests (6 passed)

```bash
tests/test_task3c_execution_input_binding.py::TestB3ExecutionInputBinding
```

| Test | Status | 验证内容 |
|------|--------|----------|
| `test_001_binding_with_all_inputs_constructs` | ✅ PASSED | 所有输入齐全可构造 binding |
| `test_002_missing_mandatory_input_fails` | ✅ PASSED | 缺失必需输入 → TypeError/ValueError |
| `test_003_hash_mismatch_rejected` | ✅ PASSED | Hash 篡改 → `is_valid=False` |
| `test_004_repo_external_path_rejected` | ✅ PASSED | Repo 外路径 (`/etc/passwd`) → 拒绝 |
| `test_005_unavailable_inputs_not_validated` | ✅ PASSED | `unavailable` 输入不验证 hash |
| `test_006_canonical_hash_deterministic` | ✅ PASSED | 相同 refs → 相同 canonical_hash |

**Result**: 6 passed, 0 failed, 0 skipped ✓

### B. 回归测试

| 测试套件 | 命令 | Result |
|---------|------|--------|
| **Task 3C** | `tests/test_task3c_execution_input_binding.py` | 6 passed ✓ |
| **Task 3B corrective-2** | `tests/test_task3b_corrective2_completeness.py` | 5 passed ✓ |
| **Task 3B corrective** | `tests/test_task3b_formal_partition_adapter.py` | 8 passed, 3 subtests passed ✓ |
| **Task 3A loader** | `tests/test_task3a_formal_pit_loader.py` | 10 passed ✓ |
| **Task 3A builder** | `tests/test_task3a_corrective_builder_integration.py` | 8 passed ✓ |
| **Task 3A provenance** | `tests/test_task3a_integrity_provenance.py` | 5 passed ✓ |

**Total**: 42 passed, 3 subtests passed, 0 failed ✓

---

## 五、Artifacts 不变性

### A. Manifest SHA-256 (不变)

```
_001: 20a41a626d2b70afa11e7292566702541a143deea2e39be9e3901ae0df691913 ✓
_002: 56a954eaf68ea816004d5652e1fda6425b69daed45f5f754de8922032c8be8b5 ✓
_003: a108474274917015019b7c0d967f4fdfc745b20824b22eef576b5d41d05d1458 ✓
_004: 536c4ab68479b515dad8774e6550376567677cdb514578de4bb51f4fbd1c6437 ✓
_005: 32f58adbca49fb89dfeb54ceeb4ac9b27b6a26c55e0c9cfeae7a8fcaf3683f10 ✓
```

### B. Verifier (exit 0)

```bash
$ python scripts/verify_pit_membership_snapshot.py pims_traderlens_v2_shsz_sw2021_pit_005
Verification status: verified
```

---

## 六、使用示例

### A. 构造合法 binding

```python
from backend.services.b3_execution_input_binding import (
    B3ExecutionInputBinding,
    ExecutionInputReference,
    validate_execution_input_binding,
)

binding = B3ExecutionInputBinding(
    binding_id="b3_exec_traderlens_v2_001",
    membership_ref=ExecutionInputReference(
        artifact_id="pims_traderlens_v2_shsz_sw2021_pit_005",
        path="data/pit/pit_membership_snapshots/pims_traderlens_v2_shsz_sw2021_pit_005",
        content_hash="32f58adbca49fb89dfeb54ceeb4ac9b27b6a26c55e0c9cfeae7a8fcaf3683f10",
        availability="verified",
    ),
    daily_ref=ExecutionInputReference(
        artifact_id="formal_partition_daily",
        path="data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal/daily",
        content_hash="placeholder",
        availability="available",
    ),
    # ... (其他 refs)
)

result = validate_execution_input_binding(binding, REPO_ROOT)
assert result.is_valid
```

### B. 前置拒绝 (伪代码)

```python
# B3 builder 入口（待集成）
def build_backtest_universe(binding: B3ExecutionInputBinding, ...):
    result = validate_execution_input_binding(binding, REPO_ROOT)
    if not result.is_valid:
        raise ValueError(f"Execution input validation failed: {result.error}")
    
    # 零 adapter/B6/ledger 调用
    # ...
```

---

## 七、未实现部分 (Task 3C 范围外)

❌ **不在本任务**:
- B3 前置验证入口集成 (test_011 skipped)
- 完整 `build_universe()` profile 路由
- Formal partition manifest hash 计算（当前 placeholder）
- Task 4 OOS 流程
- 浏览器阻断解除

---

## 八、最终状态声明

✅ **Task 3C**: PASSED (execution input binding 已冻结)  
✅ **Task 3B Corrective-2**: PASSED  
✅ **Task 3B Corrective**: PASSED  
✅ **Task 3A**: PASSED  
❌ **Task 3**: NOT COMPLETE (仅完成输入绑定，OOS/B6 未启动)  
❌ **Task 0 Step 5**: `no_validated_signal_visible_in_dom` (仍被阻断)  
❌ **全局状态**: `validation_unavailable` (保持)  
❌ **不授权**: B6/OOS/Gate/Promotion/Signal

---

## 九、下一步工作 (Task 3C 完成后)

**Task 3 剩余项**:
1. ✅ 输入引用清单冻结 (Task 3C 已完成)
2. ❌ 完整 B3 → B6 正式回测流程 (需实现)
3. ❌ Task 4 OOS 窗口 & 样本分割

**解除浏览器阻断** (Task 0 Step 5):
- 需完成 Task 3 全流程 → Task 4 → Task 5 (Signal 可见性)

---

**验收日期**: 2026-07-17  
**验收状态**: ✅ PASSED  
**签发**: Hermes Agent (Kiro)
