# 旧Manifest取证与恢复报告

**Date**: 2026-07-13  
**Package**: 35d996036cc04179  
**Status**: **Recovery Failed - invalid_overwritten_manifest**

---

## 执行摘要

**结论**: 无法恢复旧manifest。旧package标记为`invalid_overwritten_manifest`，当前文件为未验证的循环修复候选结果。

---

## 1. 旧Manifest是否字节级恢复成功

**❌ 否**

---

## 2. 候选来源及SHA-256

### 搜索位置

| 来源 | 路径/命令 | 结果 | Hash |
|------|----------|------|------|
| Git index | `git ls-files --stage` | ❌ 文件从未被track | - |
| Git history | `git log --all` | ❌ 无提交历史 | - |
| Git diff | `git diff` | ❌ 无staged变化 | - |
| 其他packages | `data/pit/formal_packages/*/manifest.json` | ❌ 无相关字段 | - |
| docs报告 | `docs/verification/FORMAL_SW2021_PIT_QUALIFICATION.md` | ❌ 已被新值覆盖 | - |
| qualification日志 | `docs/verification/formal_sw2021_qualification.stdout.log` | ❌ 无21:57运行记录 | - |
| Session history | `session_search` | ❌ 无c758d51d...记录 | - |

### 已知Hash

| 版本 | SHA-256 | expected_stock_days | blocking_gap_count | 状态 |
|------|---------|--------------------|--------------------|------|
| 旧（首次创建）| `c758d51d67230201801a28d2fd01df3e8ea5f62198ebbcdd7e02bc82360e3022` | 10,477,160 | 896 | **丢失** |
| 新（循环修复后）| `3d0333042dcafa0214d31627275266d31f7feb4560f7e63ca1a8693393d8dcbb` | 10,659,050 | 4,413 | 当前 |

### 文件时间戳

```
Birth:  2026-07-12 21:57:12 (首次创建)
Modify: 2026-07-13 11:15:05 (覆盖)
```

**时间窗口**: 16小时（21:57 → 11:15）

---

## 3. 恢复或隔离后的路径

### 隔离（当前文件）
- **路径**: `data/pit/formal_packages/.invalid_overwrites/35d996036cc04179_circular_fix_unverified_20260713_112607.json`
- **Hash**: `3d0333042dcafa0214d31627275266d31f7feb4560f7e63ca1a8693393d8dcbb` ✅
- **内容**: 循环修复后的未验证候选结果

### 原位置状态
- **路径**: `data/pit/formal_packages/35d996036cc04179/manifest.json`
- **Hash**: `3d0333042dcafa0214d31627275266d31f7feb4560f7e63ca1a8693393d8dcbb`
- **STATUS.txt**: 已添加，标记为`invalid_overwritten_manifest`

---

## 4. 旧Package最终状态

**`invalid_overwritten_manifest`**

### 禁止用途
- ❌ 作为对比baseline
- ❌ 输入到B6/OOS
- ❌ 证明旧资格通过
- ❌ 引用旧expected universe

### 当前文件代表
- ✅ 循环依赖修复结果（`eligible_codes_independent`）
- ✅ 未冻结候选（无版本控制）
- ✅ 更高expected universe（lifecycle+membership独立于daily行）
- ✅ 更诚实gap报告（无循环缩小）

### 根因
`qualify_sw2021_pit_package.py` Line 225-227:
```python
output = ROOT / "data/pit/formal_packages" / scope_hash
output.mkdir(parents=True, exist_ok=True)
(output / "manifest.json").write_text(json.dumps(result, indent=2))
```

**问题**: 写入同一个`scope_hash`目录，无版本/时间戳隔离。

---

## 5. 实际发生写入的文件

1. ✅ `data/pit/formal_packages/35d996036cc04179/manifest.json` (覆盖)
2. ✅ `data/pit/formal_packages/35d996036cc04179/STATUS.txt` (新增)
3. ✅ `data/pit/formal_packages/.invalid_overwrites/35d996036cc04179_circular_fix_unverified_20260713_112607.json` (隔离备份)
4. ✅ `docs/verification/FORMAL_SW2021_PIT_QUALIFICATION.md` (覆盖)

**未修改**:
- ✅ 所有输入数据（formal/, vendor/, stock_basic等）
- ✅ 模板配置
- ✅ 资格代码逻辑
- ✅ 其他package

---

## 6. 下一步唯一建议

**冻结并废止该被覆盖package，先修正输出不可覆盖机制，再在新scope/package路径重新运行。**

### 实施步骤

1. **修正输出隔离机制**（qualify_sw2021_pit_package.py）:
   ```python
   # 旧（覆盖）
   output = ROOT / "data/pit/formal_packages" / scope_hash
   
   # 新（隔离）
   run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
   output = ROOT / "data/pit/formal_packages" / scope_hash / f"run_{run_id}"
   # 或
   output = ROOT / "data/pit/formal_packages" / f"{scope_hash}_{run_id}"
   ```

2. **重新运行完整资格**:
   - 使用修复后的`eligible_codes_independent`
   - 输出到新隔离目录
   - 验证expected universe独立性
   - 记录完整gap统计

3. **测试与调用方迁移**:
   - 完成pytest测试套件GREEN
   - 迁移audit_*.py脚本到新函数
   - 验证无路径仍使用`eligible_codes(daily_codes, ...)`

4. **唯一允许的下一步**:
   - ✅ 修正输出目录/版本绑定设计
   - ✅ 完成循环修复的测试与调用方迁移
   - ✅ 在新scope/package路径重新运行

**禁止**:
- ❌ 伪造或重建旧manifest
- ❌ 将当前文件称作旧baseline
- ❌ 回滚循环依赖修复（修复本身正确）

---

## 附录：取证命令记录

```bash
# Git检查
git ls-files --stage data/pit/formal_packages/35d996036cc04179/manifest.json
git log --all -- data/pit/formal_packages/35d996036cc04179/manifest.json
git status --short

# 文件时间戳
stat data/pit/formal_packages/35d996036cc04179/manifest.json

# 其他package搜索
for f in data/pit/formal_packages/*/manifest.json; do
  sha256sum "$f"
  python -c "import json; print(json.load(open('$f')).get('expected_stock_days_after_market_scope'))"
done

# 日志搜索
find docs/verification -name "*.log" -newermt "2026-07-12 21:50" ! -newermt "2026-07-12 22:10"
grep -r "10477160" docs/verification/

# Session搜索
session_search(query="c758d51d67230201801a28d2fd01df3e8ea5f62198ebbcdd7e02bc82360e3022")
```

**结论**: 所有来源均无法恢复c758d51d...的字节内容。
