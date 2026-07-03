# P2-1A 问题修复报告

## 当前状态：PARTIAL (2/3 问题已修复)

---

## ✅ 问题 1：Workbench execution_feedback 已实现

**文件：** `backend/api/workbench_execution_feedback.py` (新建)

**实现：**
- 完整的 `handle_execution_feedback()` 实现
- 解析用户消息提取 price/quantity (regex)
- 创建 `execution_observation_log`
- 创建 `observation_position`
- Timeline 记录 artifact (`execution_observation_log`, `observation_position`, `workflow_action_completed`)

**清理：**
- 从 `backend/api/workbench_handlers.py` 删除占位实现
- `backend/api/research.py` 导入新的 handler

**测试：**
```bash
# 用户输入："我已经买入 100 股，成交价 12.34"
# → 创建 log + position
# → timeline 包含 execution_observation_log artifact
# → /api/observations 返回该持仓
```

---

## ✅ 问题 2：daily signal 合同已修复

### 合同层修改
**文件：** `contracts/live_trade.py`

```python
class DailyObservationSignal:
    signal_type: Optional[DailySignalType]  # None when market_data_state != ok
    
    @model_validator(mode="after")
    def validate_signal_type_null_when_data_fault(self):
        """When market_data_state != ok, signal_type must be None."""
        if self.market_data_state != MarketDataFaultState.ok:
            if self.signal_type is not None:
                raise ValueError(...)
        return self
```

### DB 层修改
**文件：** `backend/db/live_trade.py`

1. Schema: `signal_type TEXT` (允许 NULL)
2. `save_daily_signal()`: `signal.signal_type.value if signal.signal_type else None`
3. `list_daily_signals()`: `DailySignalType(row["signal_type"]) if row["signal_type"] else None`
4. `get_latest_daily_signal()`: 同上

### API 层修改
**文件：** `backend/api/observations.py`

```python
"signal_type": sig.signal_type.value if sig.signal_type else None
```

### 前端适配
**文件：** `frontend/app/observations/page.tsx`

```typescript
interface LatestSignal {
  signal_type: SignalType | null;  // 允许 null
  // ...
}

const getSignalBadge = (signal: LatestSignal | null) => {
  // Data state takes precedence
  if (market_data_state === "unavailable" || market_data_state === "partial") {
    return <span>数据不足</span>;
  }
  
  // Business signal (only when data_state === "ok")
  if (!signal_type) {
    return <span>无业务判断</span>;
  }
  // ...
}
```

### 测试验证
```bash
$ pytest tests/test_v1_observations_api.py -q
4 passed, 3 warnings in 6.51s  ✓
```

### JSON 证据
**文件：** `docs/verification/p2-1a-observations-detail.json`

```json
{
  "daily_signals": [
    {
      "signal_record_id": "sig_record_9ddd7a3e27ef",
      "signal_type": null,  ← 正确！
      "market_data_state": "unavailable",
      "plain_explanation": "市场数据不足，无法生成可靠信号"
    },
    {
      "signal_record_id": "sig_record_6b3e6c8fc55a",
      "signal_type": "hold",
      "market_data_state": "ok"
    }
  ]
}
```

✅ **验证通过：** `market_data_state="unavailable"` → `signal_type=null`

---

## ❌ 问题 3：DOM 证据仍为手写 markdown

**当前状态：** `docs/verification/p2-1a-observations-dom-output.md` 由 `generate_dom_output()` 手写生成，不是真实浏览器读取。

**要求：**
- 用 Playwright 或现有 browser fixture 打开 `http://localhost:3000/observations`
- 读取页面实际 `textContent`
- 保存真实DOM文本

**下一步：**
1. 启动前后端服务
2. 用浏览器脚本读取页面文本
3. 验证信号 badge 和今日动作显示
4. 保存真实 DOM 输出

---

## Git Commit

**Branch:** `feat/p2-1-observation-pool-page`
**Commit:** `b7b46b2` - fix(P2-1A): implement execution_feedback + signal_type=null when data fault - PARTIAL

**变更统计:**
```
10 files changed, 246 insertions(+), 150 deletions(-)
create mode 100644 backend/api/workbench_execution_feedback.py
```

---

## 测试运行

### 后端测试 ✅
```bash
$ pytest tests/test_v1_observations_api.py -q
4 passed, 3 warnings in 6.51s
```

### 前端编译 ✅
```bash
$ cd frontend && npx tsc -p tsconfig.json --noEmit --skipLibCheck
Exit code 0
```

### P1-3 回归 (待运行)
```bash
$ python scripts/verify_p1_3_browser_with_fixture.py
```

---

## 交付状态

**PARTIAL (2/3 问题已修复)**

✅ 问题 1：Workbench execution_feedback 已实现  
✅ 问题 2：daily signal 合同已修复（signal_type=null when data_fault）  
❌ 问题 3：DOM 证据仍为手写，非真实浏览器读取

**下一步：** 解决问题 3 后可 PASS
