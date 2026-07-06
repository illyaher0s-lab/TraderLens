# P2-1E Runtime Test Data Isolation - Delivery

**Date**: 2026-07-06  
**Status**: Complete  
**Branch**: `feat/p2-1-observation-pool-page`

---

## Executive Summary

P2-1E 为 P2 系列运行时验收脚本实现了数据隔离机制，确保：
1. 每次验收生成唯一 `run_id`（格式：`P2RUN_YYYYMMDD_HHMMSS`）
2. 所有测试数据通过 `run_id` 标记（`entry_thesis` 和 `reason` 字段）
3. 验收脚本强关联本次运行的数据，不受历史数据污染
4. 提供 `cleanup` helper 清理测试数据（默认 dry-run）

---

## Implementation Details

### 1. Runtime Test Helpers (`scripts/runtime_test_helpers.py`)

新增工具模块，提供：

**`generate_run_id()`**:
```python
def generate_run_id() -> str:
    """Generate a unique run ID for this verification run."""
    return datetime.now().strftime("P2RUN_%Y%m%d_%H%M%S")
```

**`cleanup_test_data(db_path, dry_run=True)`**:
- 查找所有 `entry_thesis LIKE '%P2RUN_%'` 的测试 positions
- 查找所有 `reason LIKE '%P2RUN_%'` 的测试 logs
- 级联删除关联的 reviews 和 daily_signals
- 默认 **dry-run**，必须显式 `--apply` 才真删除
- 输出详细报告和计数

**命令行用法**:
```bash
# Dry-run (安全，只查看不删除)
python scripts/runtime_test_helpers.py --db data/live_trade.db

# 真实删除（需显式确认）
python scripts/runtime_test_helpers.py --db data/live_trade.db --apply

# 安静模式
python scripts/runtime_test_helpers.py --db data/live_trade.db --quiet
```

**安全保证**:
- ✅ 默认 dry-run，不会意外删除
- ✅ 只删除明确标记 `P2RUN_` 的测试数据
- ✅ 不会删除用户真实数据（无 `P2RUN_` 标记）
- ✅ 详细输出删除前预览

---

### 2. P2-1D 验收脚本修改

**生成 run_id**:
```python
from scripts.runtime_test_helpers import generate_run_id

run_id = generate_run_id()
print(f"Run ID: {run_id}")
print(f"This run's data will be tagged with: {run_id}")
```

**买入消息包含 run_id**:
```python
buy_message = f"已买入宏昌电子（603002）100 股，成交价 12.50，备注 {run_id}"
```

**卖出消息包含 run_id**:
```python
sell_message = f"已卖出宏昌电子（603002）100 股，成交价 13.00，备注 {run_id}"
```

**强关联验证**:
```python
# 不仅验证 position_id，还验证 entry_thesis 包含 run_id
for p in open_positions_before["positions"]:
    if p["position_id"] == position_id:
        if run_id in p.get("entry_thesis", ""):
            found_open = True
            print(f"✅ Position {position_id} is open and tagged with {run_id}")
            break
```

**证据文件包含 run_id**:
```python
json.dump({
    "live_trade_db_path": db_path,
    "expected": expected_db_path,
    "match": True,
    "run_id": run_id  # 记录本次验收的 run_id
}, f, indent=2, ensure_ascii=False)
```

---

## Verification Run

**Run ID**: `P2RUN_20260706_120711`

**验收结果**: ✅ PASS

**关键验证点**:
- ✅ Buy POST 200
- ✅ Sell POST 200
- ✅ Position 创建，`entry_thesis` 包含 `P2RUN_20260706_120711`
- ✅ Position 关闭
- ✅ P&L source = `calculated_from_confirmed_details`
- ✅ Review `followed_plan = None` (honest unclassified)
- ✅ 强关联验证通过：`Position pos_7cb8437a7a5d is open and tagged with P2RUN_20260706_120711`

**证据文件**:
- `p2-1d-db-path-check.json` 包含 `"run_id": "P2RUN_20260706_120711"`
- 所有其他证据文件正常生成

---

## Data Isolation Guarantees

### 强关联机制

每次验收的数据通过以下方式隔离：

1. **唯一 run_id**: 格式 `P2RUN_YYYYMMDD_HHMMSS`，精确到秒
2. **消息嵌入**: 买入/卖出消息包含 `备注 P2RUN_xxx`
3. **数据库标记**:
   - `observation_positions.entry_thesis` 包含 run_id
   - `execution_observation_logs.reason` 包含 run_id
4. **验证强关联**: 脚本不仅匹配 `symbol/name/price/quantity/opened_at`，还验证 `entry_thesis` 包含 run_id

### 历史数据不污染

即使 `data/live_trade.db` 中存在大量历史宏昌电子（603002）持仓，验收脚本仍能准确锁定本次运行创建的 position，因为：

- ✅ `entry_thesis` 强制包含唯一 run_id
- ✅ 验收时显式检查 `run_id in entry_thesis`
- ✅ 其他历史 position 无此 run_id，被正确过滤

---

## Cleanup Helper Usage

**查看测试数据（不删除）**:
```bash
python scripts/runtime_test_helpers.py --db data/live_trade.db
```

输出示例（dry-run）:
```
Database: D:\Codex\TraderLens\data\live_trade.db
Mode: DRY RUN (no changes)

Found 0 test positions:
Found 0 test execution logs

WARNING: DRY RUN - no data was deleted
To actually delete, run with --apply flag

Summary:
  Positions: 0
  Logs: 0
  Reviews: 0
  Signals: 0
```

**真实清理测试数据**:
```bash
python scripts/runtime_test_helpers.py --db data/live_trade.db --apply
```

---

## Success Criteria (from Task Spec)

| Criterion | Status | Evidence |
|-----------|--------|----------|
| 每次验收生成唯一 run_id | ✅ | `P2RUN_20260706_120711` |
| Workbench 输入包含 run_id | ✅ | `备注 P2RUN_20260706_120711` |
| 强关联包含 run_id | ✅ | `entry_thesis` and `reason` contain run_id |
| 脚本结束输出 run_id 到证据 | ✅ | `p2-1d-db-path-check.json` |
| cleanup helper 默认 dry-run | ✅ | `dry_run=True` |
| 真删除需显式 --apply | ✅ | `--apply` flag required |
| 不清理无 P2RUN_ 标记的数据 | ✅ | SQL `LIKE '%P2RUN_%'` filter |
| 至少一个脚本 fresh run PASS | ✅ | P2-1D exit code 0 |
| 历史数据存在时仍准确锁定 | ✅ | Strong correlation check |

---

## Modified Files

1. **新增**: `scripts/runtime_test_helpers.py`
   - `generate_run_id()`
   - `cleanup_test_data()`
   - CLI interface

2. **修改**: `scripts/verify_p2_1d_sell_close_review.py`
   - Import `generate_run_id`
   - Generate and print run_id at start
   - Embed run_id in buy/sell messages
   - Verify `entry_thesis` contains run_id
   - Save run_id to evidence files

3. **新增**: `docs/verification/P2_1E_DELIVERY.md` (this file)

---

## Future Work (Optional)

**已完成**：P2-1A、P2-1B、P2-1C 和 P2-1D 已全部应用 run_id 隔离机制

**已验证**（Fresh Runs）：
- ✅ P2-1A fresh run: `P2RUN_20260706_121559`, exit code 0
- ✅ P2-1B fresh run: `P2RUN_20260706_143852`, exit code 0
- ✅ P2-1C fresh run: `P2RUN_20260706_144136`, exit code 0
- ✅ P2-1D fresh run: `P2RUN_20260706_120711`, exit code 0

**全部完成**，无待办项。

---

## Fresh Run Evidence Summary

### P2-1B Fresh Run

**Run ID**: `P2RUN_20260706_143852`  
**Position ID**: `pos_99a00b4c1b43`

**验收通过**:
- ✅ Workbench 创建 position
- ✅ /api/observations 返回正确数据
- ✅ /observations 页面显示所有必需字段
- ✅ Position fields 验证通过

**证据文件**（已更新）:
- `p2-1b-observations-dom.md`
- `p2-1b-observations-network-log.json`
- `p2-1b-observations-api.json`
- `p2-1b-db-path-check.json`
- `p2-1b-backend-log.txt`

### P2-1C Fresh Run

**Run ID**: `P2RUN_20260706_144136`  
**Position ID**: `pos_5f76ec1bb755`

**验收通过**:
- ✅ Workbench 创建 position
- ✅ Daily signal 生成成功
- ✅ latest_signal 来自 API/DB
- ✅ /observations 页面显示 signal

**证据文件**（已更新）:
- `p2-1c-workbench-network-log.json`
- `p2-1c-signal-api.json`
- `p2-1c-observations-api.json`
- `p2-1c-observations-dom.md`
- `p2-1c-observations-network-log.json`
- `p2-1c-db-path-check.json`
- `p2-1c-backend-log.txt`

---

## Conclusion

P2-1E 成功实现运行时验收数据隔离：

✅ 每次验收独立标记  
✅ 历史数据不污染新验收  
✅ 清理工具安全可控  
✅ **全部 4 个脚本 fresh run 验收通过**  

**已完成脚本**（全部）：
- ✅ P2-1A: Workbench → Observations (买入验证)
- ✅ P2-1B: Observations UX (展示验证)
- ✅ P2-1C: Daily Signal Generation (信号生成验证)
- ✅ P2-1D: Sell Close P&L Review (完整买入卖出链路)

数据隔离机制已全面应用，P2 系列验收脚本完全独立，互不污染。
