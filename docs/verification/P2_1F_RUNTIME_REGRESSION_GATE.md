# P2-1F Runtime Regression Gate

**Date**: 2026-07-06  
**Status**: Complete  
**Branch**: `feat/p2-1-observation-pool-page`

---

## Executive Summary

P2-1F 创建了统一的运行时回归门禁入口 `scripts/verify_p2_runtime_regression.py`，顺序执行全部 4 个 P2 真实运行时验收脚本，作为 P2 系列功能可信性的唯一验收标准。

---

## 统一入口命令

```bash
python scripts/verify_p2_runtime_regression.py
```

**单一命令，全链路验证**：
- 自动顺序执行 P2-1A/B/C/D
- 任一失败立即中止
- 生成统一证据文件
- Exit code 0 = P2 可信，非 0 = P2 不可信

---

## 覆盖链路

### P2-1A: Workbench → Observations (买入验证)
- 真实浏览器打开 /workbench
- 输入买入信息（含 run_id）
- 验证 position 创建
- 验证 /api/observations 返回
- 验证 /observations 页面显示
- 强关联验证（symbol/name/price/quantity/opened_at/run_id）

### P2-1B: Observations UX (展示验证)
- 复用 P2-1A 创建 position
- 验证 /observations 页面显示所有必需字段
- 验证 position 字段：股票名称、代码、开仓、数量、价格
- 强关联验证（含 run_id）

### P2-1C: Daily Signal Generation (信号生成验证)
- 创建真实 open position
- 调用真实 daily signal 生成 API
- 验证 latest_signal 来自 API/DB
- 验证 data_state != ok 时 signal_type 为 null
- 强关联验证（含 run_id）

### P2-1D: Sell Close P&L Review (完整买入卖出链路)
- 真实浏览器创建 buy position
- 真实浏览器提交 sell execution
- 验证 position 从 open 变 closed
- 验证 P&L 计算（deterministic，不用 LLM）
- 验证 discipline review 生成（honest unclassified）
- 强关联验证（含 run_id）

---

## 证据文件

### 主证据文件

**`docs/verification/p2-runtime-regression-summary.json`**:
```json
{
  "timestamp": "2026-07-06T15:13:44.590949",
  "overall_success": true,
  "overall_duration": 158.32,
  "scripts": [
    {
      "name": "P2-1A: Workbench → Observations",
      "exit_code": 0,
      "duration": 40.84,
      "run_id": "P2RUN_20260706_151106",
      "success": true
    },
    ...
  ],
  "api_check": {
    "checked_files": 5,
    "all_use_8010": true,
    "non_8010_calls": []
  },
  "log_check": {
    "checked_files": 4,
    "clean": true,
    "errors_found": []
  }
}
```

**`docs/verification/p2-runtime-regression-log.txt`**:
- 每个子脚本的完整 stdout/stderr
- Exit code 和 duration
- Run ID 记录

### 子脚本证据文件

每个子脚本生成独立证据：
- P2-1A: 6 个文件（workbench, observations, API, DOM, network, db-path, backend-log）
- P2-1B: 5 个文件（observations, API, DOM, network, db-path, backend-log）
- P2-1C: 7 个文件（workbench, signal, observations, API, DOM, network, db-path, backend-log）
- P2-1D: 8 个文件（buy/sell workbench, observations open/closed, review/pnl, DOM, db-path, backend-log）

**总计**: 26+ 个证据文件 + 2 个统一证据文件

---

## 失败策略

### Fail-Fast 机制

门禁采用 **fail-fast** 策略：

1. **子脚本失败** → 立即中止，不执行后续脚本
2. **API 检查失败** → 整体失败（发现非 localhost:8010 请求）
3. **Log 检查失败** → 整体失败（发现 500/Traceback/ERROR）
4. **超时** → 单脚本 300 秒超时，整体 900 秒超时

### Exit Code 语义

- **0**: 全部通过，P2 可信
- **1**: 至少一项失败，P2 不可信
- **-1**: 超时或异常

### 失败诊断

查看失败详情：
```bash
# 查看概要
cat docs/verification/p2-runtime-regression-summary.json

# 查看完整日志
cat docs/verification/p2-runtime-regression-log.txt

# 查看具体子脚本证据
cat docs/verification/p2-1a-backend-log.txt
cat docs/verification/p2-1b-observations-api.json
...
```

---

## 为什么它是 P2 后续唯一验收入口

### 1. 全链路覆盖

不是单元测试，不是 fixture，是真实端到端链路：
- ✅ 真实浏览器交互（Playwright）
- ✅ 真实前后端通信（localhost:8010/3000）
- ✅ 真实数据库读写（live_trade.db）
- ✅ 真实 LLM 调用（deterministic mode）
- ✅ 真实 P&L 计算
- ✅ 真实 signal 生成

### 2. 强关联验证

每次运行生成唯一 run_id，强制匹配：
- symbol + name + price + quantity + opened_at + **run_id**
- 历史数据不污染新验收
- 无 run_id 的 position 不会被误匹配

### 3. 数据隔离

- 每个子脚本独立 run_id
- 不依赖历史数据
- 可重复运行
- 清理工具安全可控（`runtime_test_helpers.py`）

### 4. 失败即中止

任一子脚本失败 → 整体失败 → **P2 不可信**

这避免了部分功能正常、部分功能损坏时的"部分可信"误判。

### 5. 证据完整

- 26+ 个子证据文件
- 2 个统一证据文件
- 全部 run_id 记录
- API/Log 自动检查

### 6. 单一命令

开发者、CI/CD、QA 只需要：
```bash
python scripts/verify_p2_runtime_regression.py
```

Exit code 0 = 可发布，非 0 = 不可发布。

---

## Fresh Run 验收结果

**执行时间**: 2026-07-06 15:11:06 - 15:13:44  
**总耗时**: 158.32 秒 (~2.6 分钟)  
**主脚本 Exit Code**: **0** ✅

### 子脚本结果

| 脚本 | Exit Code | Duration | Run ID |
|------|-----------|----------|--------|
| P2-1A | **0** ✅ | 40.84s | `P2RUN_20260706_151106` |
| P2-1B | **0** ✅ | 35.40s | `P2RUN_20260706_151147` |
| P2-1C | **0** ✅ | 41.80s | `P2RUN_20260706_151222` |
| P2-1D | **0** ✅ | 40.28s | `P2RUN_20260706_151304` |

### 检查结果

- ✅ **API Check**: 5 个文件检查，全部使用 localhost:8010
- ✅ **Log Check**: 4 个文件检查，无 500/Traceback/ERROR

---

## 技术实现

### 子进程管理

```python
subprocess.run(
    [python, script_path],
    capture_output=True,
    text=True,
    encoding='utf-8',
    errors='replace',  # 处理编码错误
    timeout=300,
)
```

### Run ID 提取

从 stdout 解析：
```python
for line in result.stdout.split('\n'):
    if 'Run ID:' in line:
        run_id = line.split('Run ID:')[-1].strip()
```

### API 证据检查

扫描所有 `*-network-log.json` 文件，验证 `/api/` 请求全部包含 `:8010`。

### Backend Log 检查

扫描所有 `*-backend-log.txt` 文件，查找错误模式：
- `500`
- `Traceback`
- `sqlite`
- `Internal Server Error`
- `ERROR:`

---

## 未来扩展

如果添加新的 P2 验收脚本（如 P2-1E、P2-1F...），只需：

1. 在 `verify_p2_runtime_regression.py` 的 `scripts` 列表中添加
2. 确保新脚本遵循相同约定：
   - 打印 `Run ID: <run_id>`
   - Exit code 0 = 成功，非 0 = 失败
   - 生成证据文件到 `docs/verification/`

门禁会自动包含新脚本。

---

## Conclusion

P2-1F 运行时回归门禁是 P2 系列功能的**唯一可信验收标准**：

✅ 全链路真实验证  
✅ 强关联数据隔离  
✅ Fail-fast 失败策略  
✅ 单一命令入口  
✅ 完整证据链  

**一次运行，全链路验证，P2 可信与否，一目了然。**
