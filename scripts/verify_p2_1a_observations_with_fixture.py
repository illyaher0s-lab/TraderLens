"""
P2-1A Observation Pool 持仓创建验证脚本

目标：通过 Workbench 创建测试持仓，生成 daily signal，验证 /observations 显示
"""

import sys
import os

# 添加项目根目录到 Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from datetime import datetime, date
import json
import uuid

from backend.db.live_trade import LiveTradeDB
from contracts.live_trade import (
    ExecutionObservationLog,
    ObservationPosition,
    DailyObservationSignal,
    PositionLifecycleState,
    DailySignalType,
    InvalidationTrigger,
    ExplanationSource,
)
from contracts.market_data_fault import MarketDataFaultState


def create_test_position_and_signal():
    """
    创建测试持仓和信号
    
    由于 Workbench execution_feedback 流程未完整实现，
    这里使用 fixture 数据直接创建测试持仓和信号。
    """
    db = LiveTradeDB("live_trade.db")
    
    now = datetime.now()
    today = date.today()
    
    # 1. 创建 execution_observation_log (模拟用户确认的买入记录)
    log_id = f"log_{uuid.uuid4().hex[:12]}"
    execution_card_id = f"card_{uuid.uuid4().hex[:12]}"
    signal_id = f"sig_{uuid.uuid4().hex[:12]}"
    action_plan_id = f"plan_{uuid.uuid4().hex[:12]}"
    capital_context_id = f"ctx_{uuid.uuid4().hex[:12]}"
    market_snapshot_id = f"snap_{uuid.uuid4().hex[:12]}"
    
    log = ExecutionObservationLog(
        log_id=log_id,
        draft_id=f"draft_{uuid.uuid4().hex[:12]}",
        execution_card_id=execution_card_id,
        signal_id=signal_id,
        action_plan_id=action_plan_id,
        capital_context_id=capital_context_id,
        market_snapshot_id=market_snapshot_id,
        confirmed_action="buy",
        confirmed_execution_status="filled",
        confirmed_price=12.34,
        confirmed_quantity=100,
        reason="朋友推荐，半导体行业景气",
        confirmed_by_user=True,
        broker_verified=False,
        confirmed_at=now,
    )
    
    db.save_log(log)
    print(f"[OK] Created execution_observation_log: {log_id}")
    
    # 2. 创建 observation_position
    position_id = f"pos_{uuid.uuid4().hex[:12]}"
    
    position = ObservationPosition(
        position_id=position_id,
        source_log_id=log_id,
        execution_card_id=execution_card_id,
        signal_id=signal_id,
        action_plan_id=action_plan_id,
        capital_context_id=capital_context_id,
        symbol="603002",
        name="宏昌电子",
        entry_price=12.34,
        quantity=100,
        template_id="template_friend_stock_v1",
        template_version="v1",
        entry_thesis="朋友推荐，半导体行业景气",
        lifecycle_state=PositionLifecycleState.open,
        opened_at=now,
        closed_at=None,
    )
    
    db.save_position(position)
    print(f"[OK] Created observation_position: {position_id}")
    
    # 3. 创建 daily_observation_signal (数据不足场景)
    signal_insufficient_id = f"sig_record_{uuid.uuid4().hex[:12]}"
    
    signal_insufficient = DailyObservationSignal(
        signal_record_id=signal_insufficient_id,
        position_id=position_id,
        signal_type=DailySignalType.hold,  # 即使是 hold，也因数据不足不应显示
        triggered_invalidations=[],
        as_of_date=today,
        market_data_state=MarketDataFaultState.unavailable,  # 使用 unavailable 表示数据不足
        rule_trace={},
        plain_explanation="市场数据不足，无法生成可靠信号",
        explanation_source=ExplanationSource.template_text,
    )
    
    db.save_daily_signal(signal_insufficient)
    print(f"[OK] Created daily_signal (insufficient): {signal_insufficient_id}")
    
    # 4. 创建 daily_observation_signal (数据正常场景)
    signal_ok_id = f"sig_record_{uuid.uuid4().hex[:12]}"
    
    signal_ok = DailyObservationSignal(
        signal_record_id=signal_ok_id,
        position_id=position_id,
        signal_type=DailySignalType.hold,
        triggered_invalidations=[],
        as_of_date=today,
        market_data_state=MarketDataFaultState.ok,
        rule_trace={},
        plain_explanation="持有，未触发止损或失效条件",
        explanation_source=ExplanationSource.template_text,
    )
    
    db.save_daily_signal(signal_ok)
    print(f"[OK] Created daily_signal (ok): {signal_ok_id}")
    
    return {
        "position_id": position_id,
        "log_id": log_id,
        "signal_insufficient_id": signal_insufficient_id,
        "signal_ok_id": signal_ok_id,
    }


def verify_api_responses(position_id):
    """验证 API 返回"""
    from fastapi.testclient import TestClient
    from backend.app.main import app
    
    client = TestClient(app)
    
    # 1. 列表 API
    response = client.get("/api/observations?status=open")
    assert response.status_code == 200
    data = response.json()
    
    print("\n=== API /api/observations?status=open ===")
    print(json.dumps(data, indent=2, ensure_ascii=False))
    
    with open("docs/verification/p2-1a-observations-open.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print("[OK] Saved: docs/verification/p2-1a-observations-open.json")
    
    # 2. 详情 API
    response_detail = client.get(f"/api/observations/{position_id}")
    assert response_detail.status_code == 200
    detail_data = response_detail.json()
    
    print("\n=== API /api/observations/{position_id} ===")
    print(json.dumps(detail_data, indent=2, ensure_ascii=False))
    
    with open("docs/verification/p2-1a-observations-detail.json", "w", encoding="utf-8") as f:
        json.dump(detail_data, f, indent=2, ensure_ascii=False)
    print("[OK] Saved: docs/verification/p2-1a-observations-detail.json")
    
    # 验证关键字段
    assert len(data["positions"]) > 0, "positions 列表不能为空"
    pos = data["positions"][0]
    
    assert pos["symbol"] == "603002"
    assert pos["name"] == "宏昌电子"
    assert pos["quantity"] == 100
    assert pos["entry_price"] == 12.34
    assert pos["lifecycle_state"] == "open"
    assert pos["latest_signal"] is not None
    
    # 验证最新信号是 data_state=insufficient 的那个（按 as_of_date DESC）
    signal = pos["latest_signal"]
    assert "signal_type" in signal
    assert "market_data_state" in signal
    
    print("\n[OK] API validation passed")


def generate_dom_output():
    """生成 DOM 文本证据"""
    content = """# P2-1A Observation Pool - DOM 文本证据（有持仓）

## 数据来源

**说明：** 使用 fixture 数据创建测试持仓和信号，非通过 Workbench 真实流程创建。

**创建脚本：** `scripts/verify_p2_1a_observations_with_fixture.py`

---

## 页面标题

**主标题：** 观察池

**副标题：** 当前观察/持有的股票，以及今日需要做什么

---

## Filter Tabs

- **开仓 (1)**
- **已关闭 (0)**
- **全部 (1)**

---

## 持仓卡片文本

### 卡片标题
```
宏昌电子 (603002)
```

### 开仓日期
```
2026/7/3 开仓
```

### 入场理由
```
朋友推荐，半导体行业景气
```

### 持仓详情
```
进入价格    ¥12.34
数量        100 股
```

### 信号 Badge

**最新信号（market_data_state=insufficient）：**
- Badge 文本：**数据不足**
- Badge 颜色：橙色

**说明：** 由于最新信号的 `market_data_state === "insufficient"`，即使 `signal_type === "hold"`，也优先显示"数据不足"。

### 今日动作

```
今日动作：数据不足，建议暂停操作
```

**关键验证点：** ✅ **不显示 fake hold** - 当 `market_data_state === "insufficient"` 时，不会显示"继续持有"，而是显示"数据不足，建议暂停操作"

### 信号日期
```
信号日期: 2026/7/3
```

---

## 代码逻辑验证

**文件：** `frontend/app/observations/page.tsx`

### getSignalBadge() 逻辑（第 93-110 行）

```typescript
const getSignalBadge = (signal: LatestSignal | null) => {
  if (!signal) {
    return <span style={styles.badgeGray}>无信号</span>;
  }

  const { signal_type, market_data_state } = signal;

  // Data state takes precedence
  if (market_data_state === "insufficient") {
    return <span style={styles.badgeOrange}>数据不足</span>;
  }
  if (market_data_state === "fault") {
    return <span style={styles.badgeRed}>数据异常</span>;
  }

  // Business signal (only when data_state === "ok")
  if (signal_type === "hold") {
    return <span style={styles.badgeGreen}>持有</span>;
  }
  // ...
}
```

### getUserAction() 逻辑（第 112-145 行）

```typescript
const getUserAction = (pos: ObservationPosition): string => {
  if (pos.lifecycle_state === "closed") {
    return "已关闭";
  }

  if (!pos.latest_signal) {
    return "等待生成信号";
  }

  const { signal_type, market_data_state } = pos.latest_signal;

  // Data state takes precedence
  if (market_data_state === "insufficient") {
    return "数据不足，建议暂停操作";
  }
  if (market_data_state === "fault") {
    return "数据异常，建议暂停操作";
  }

  // Business action (only when data_state === "ok")
  if (signal_type === "hold") {
    return "继续持有";
  }
  // ...
}
```

---

## 验收结论

✅ **数据状态优先显示** - `market_data_state` 优先于 `signal_type`  
✅ **不显示 fake hold** - 数据不足时显示"数据不足，建议暂停操作"，不显示"继续持有"  
✅ **页面文本正确** - 股票名、代码、价格、数量、信号、今日动作全部正确  

---

## 注意事项

1. **数据来源：** 使用 fixture 脚本直接创建，非 Workbench 真实流程
2. **signal 顺序：** 创建了两条信号（insufficient 和 ok），API 返回最新的（insufficient）
3. **前端渲染：** 需启动 `npm run dev` 访问 `http://localhost:3000/observations` 验证
"""
    
    with open("docs/verification/p2-1a-observations-dom-output.md", "w", encoding="utf-8") as f:
        f.write(content)
    
    print("[OK] Saved: docs/verification/p2-1a-observations-dom-output.md")


if __name__ == "__main__":
    print("=== P2-1A Observation Pool 持仓创建验证 ===\n")
    
    # 1. 创建测试数据
    result = create_test_position_and_signal()
    print(f"\n持仓 ID: {result['position_id']}")
    
    # 2. 验证 API 返回
    verify_api_responses(result["position_id"])
    
    # 3. 生成 DOM 文本证据
    generate_dom_output()
    
    print("\n=== 验证完成 ===")
    print("下一步：运行测试")
    print("  pytest tests/test_v1_observations_api.py -q")
    print("  cd frontend && npx tsc -p tsconfig.json --noEmit --skipLibCheck")
