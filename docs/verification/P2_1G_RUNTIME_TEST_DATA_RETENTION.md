# P2-1G Runtime Test Data Retention

**Date**: 2026-07-06  
**Status**: Complete  
**Branch**: `feat/p2-1-observation-pool-page`

---

## Executive Summary

P2-1G 为 P2 运行时回归门禁添加了自动测试数据清理机制，确保每次运行前清空历史 `P2RUN_*` 测试数据，防止 `live_trade.db` 被验收数据污染，同时保留本次运行产生的数据用于证据追踪。

---

## 问题背景

每次运行 P2 运行时验收脚本都会在 `live_trade.db` 中创建：
- `observation_positions` (带 `P2RUN_*` 标记)
- `execution_observation_logs` (带 `P2RUN_*` 标记)
- `discipline_reviews` (关联 positions)
- `daily_observation_signals` (关联 positions)

多次运行后，数据库累积大量测试数据（本次 pre-clean 删除了 23 positions + 28 logs + 5 reviews + 62 signals），可能：
- 干扰手动查询和分析
- 增加数据库体积
- 混淆"当前验收"和"历史验收"数据

---

## 解决方案

### 1. 加固 `runtime_test_helpers.py`

**Cleanup 机制**:
- 只删除 `entry_thesis LIKE '%P2RUN_%'` 的 positions
- 只删除 `reason LIKE '%P2RUN_%'` 的 logs
- 级联删除关联的 reviews 和 signals
- 默认 **dry-run**，`--apply` 才真实删除
- 输出详细删除计数

**安全保证**:
```python
# 强制只清理测试数据
WHERE entry_thesis LIKE '%P2RUN_%'
WHERE reason LIKE '%P2RUN_%'
```

**CLI 用法**:
```bash
# Dry-run (安全预览)
python scripts/runtime_test_helpers.py --db data/live_trade.db

# 真实删除
python scripts/runtime_test_helpers.py --db data/live_trade.db --apply
```

### 2. 修改 `verify_p2_runtime_regression.py`

**Pre-Clean 阶段**:
```python
# Step 0: 运行 4 个子脚本前清理历史数据
cleanup_result = cleanup_test_data(
    db_path=str(PROJECT_ROOT / "data" / "live_trade.db"),
    dry_run=False,  # 真实删除
    verbose=True
)
```

**不做 Post-Clean**:
- 本次运行的 4 个 positions 保留
- 证据文件可追溯到真实 DB 记录
- 下次运行前才清理

**Summary 写入**:
```json
{
  "cleanup": {
    "positions": 23,
    "logs": 28,
    "reviews": 5,
    "signals": 62
  },
  ...
}
```

---

## Dry-Run 验证

**命令**:
```bash
python scripts/runtime_test_helpers.py --db data/live_trade.db
```

**结果**:
```
Found 23 test positions
Found 28 test execution logs
Found 5 test reviews
Found 62 test daily signals

WARNING: DRY RUN - no data was deleted
To actually delete, run with --apply flag

Summary:
  Positions: 23
  Logs: 28
  Reviews: 5
  Signals: 62
```

**验证要点**:
- ✅ 全部 23 个 positions 都包含 `P2RUN_*` 标记
- ✅ 未发现任何非测试数据被误命中
- ✅ 清理安全可控

---

## Fresh Run 验证

**命令**:
```bash
python scripts/verify_p2_runtime_regression.py
```

**Pre-Clean 实际删除**:
- **Positions**: 23 → 0
- **Logs**: 28 → 0
- **Reviews**: 5 → 0
- **Signals**: 62 → 0

**四个新 Run ID**:
1. P2-1A: `P2RUN_20260706_154758` (38.81s)
2. P2-1B: `P2RUN_20260706_154837` (33.63s)
3. P2-1C: `P2RUN_20260706_154910` (38.38s)
4. P2-1D: `P2RUN_20260706_154949` (38.16s)

**主脚本 Exit Code**: **0** ✅

**验收结果**:
- ✅ 四个子脚本全部 exit code 0
- ✅ 7 个 network evidence 文件全部通过
- ✅ Backend logs 全部 clean (无 500/Traceback/ERROR)
- ✅ 总耗时: 149.03 秒

**运行后 DB 状态**:
- ✅ 存在 4 个新 positions (本次运行)
- ✅ 带有对应 run_id 标记
- ✅ 历史 23 个测试 positions 已清除

---

## 证据文件

**Summary**:
```json
{
  "timestamp": "2026-07-06T15:50:27.145989",
  "overall_success": true,
  "overall_duration": 149.03,
  "cleanup": {
    "positions": 23,
    "logs": 28,
    "reviews": 5,
    "signals": 62
  },
  "scripts": [...],
  "api_check": {...},
  "log_check": {...}
}
```

**Log**:
```
====================================================================================================
Pre-Cleanup Results
====================================================================================================
Positions removed: 23
Logs removed: 28
Reviews removed: 5
Signals removed: 62
```

---

## 数据保留策略

### Pre-Clean (执行)

运行 4 个子脚本**前**清理：
- 删除全部历史 `P2RUN_*` 数据
- 确保验收从干净状态开始

### Post-Clean (不执行)

运行**后不清理**：
- 保留本次 4 个 positions
- 保留本次 logs/reviews/signals
- 证据文件可追溯到真实 DB 记录

### 下次运行

下次运行时 pre-clean 会清理：
- 本次运行的 4 个 positions
- 成为"历史数据"

---

## 为什么不 Post-Clean

### 1. 证据可追溯

证据文件 (API JSON, backend log, DOM) 记录了具体的 position_id 和 run_id。保留 DB 记录可以：
- 手动查询验证
- 调试失败原因
- 交叉验证证据链

### 2. 避免证据不一致

如果 post-clean：
- 证据文件说 "position pos_xxx 存在"
- 但 DB 中查询不到
- 造成证据与现实不一致

### 3. 下次自动清理

下次运行前 pre-clean 会自动清理，无需手动维护。

---

## 技术实现

### Cleanup 函数

```python
def cleanup_test_data(db_path: str, dry_run: bool = True) -> dict:
    # 只删除明确标记的测试数据
    cursor.execute("""
        DELETE FROM observation_positions 
        WHERE entry_thesis LIKE '%P2RUN_%'
    """)
    
    cursor.execute("""
        DELETE FROM execution_observation_logs 
        WHERE reason LIKE '%P2RUN_%'
    """)
    
    # 级联删除关联数据
    cursor.execute("""
        DELETE FROM discipline_reviews 
        WHERE position_id IN (test_position_ids)
    """)
    
    cursor.execute("""
        DELETE FROM daily_observation_signals 
        WHERE position_id IN (test_position_ids)
    """)
    
    if not dry_run:
        conn.commit()
    
    return counts
```

### Pre-Clean 集成

```python
def main():
    # Step 0: Pre-clean
    cleanup_result = cleanup_test_data(
        db_path=str(PROJECT_ROOT / "data" / "live_trade.db"),
        dry_run=False,
        verbose=True
    )
    
    # Step 1-4: 运行子脚本
    ...
    
    # Step 5: 保存 summary (包含 cleanup_result)
    summary = {
        "cleanup": cleanup_result,
        ...
    }
```

---

## 安全保证

### 1. 只删除测试数据

强制 SQL `LIKE '%P2RUN_%'` 过滤，非测试数据不会被误删。

### 2. 默认 Dry-Run

CLI 工具默认 `dry_run=True`，必须显式 `--apply` 才真删。

### 3. Verbose 输出

Pre-clean 打印每个被删除的 position 详情，便于审计。

### 4. 统计报告

Summary 和 Log 记录精确删除计数，可追溯。

---

## 对比：Before vs After

### Before P2-1G

**问题**:
- 每次运行累积测试数据
- 23 个历史 positions 遗留
- 62 个 signals 占用空间
- 手动查询混乱

**清理**:
```bash
# 手动清理（容易误删用户数据）
DELETE FROM observation_positions WHERE ...;
```

### After P2-1G

**改进**:
- 每次运行前自动 pre-clean
- 只保留本次 4 个 positions
- 干净的验收起点
- 安全可控

**清理**:
```python
# 自动 pre-clean（regression gate 内置）
python scripts/verify_p2_runtime_regression.py
```

---

## Conclusion

P2-1G 实现了运行时测试数据的自动清理与保留机制：

✅ **Pre-Clean**: 每次运行前清空历史测试数据  
✅ **保留本次**: 本次运行数据保留用于证据追踪  
✅ **安全可控**: 只删除 `P2RUN_*` 标记数据  
✅ **自动化**: 无需手动维护，regression gate 内置  

**一次运行，自动清理，数据干净，证据完整。**
