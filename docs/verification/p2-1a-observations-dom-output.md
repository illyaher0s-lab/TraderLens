# P2-1A Observation Pool - DOM 文本证据（有持仓）

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
