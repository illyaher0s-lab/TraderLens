# P2-1 Observation Pool - DOM 文本证据

## 测试方式

访问 `http://localhost:3000/observations`（前端开发服务器）

---

## 页面标题

**主标题：** 观察池

**副标题：** 当前观察/持有的股票，以及今日需要做什么

---

## Filter Tabs

- **开仓 (0)**
- **已关闭 (0)**
- **全部 (0)**

---

## 空状态文本

**标题：** 暂无观察/持仓

**提示文本：**
```
去 Workbench 输入：
- "朋友推荐了某某股票"
- "我已经买入 XX 股，成交价 XX 元"
```

**去 Workbench 添加入口：** ✅ 存在（链接到 `/workbench`）

---

## 有持仓卡片文本（预期格式）

### 卡片标题
```
宏昌电子 (603002)
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

### 信号 Badge（根据 data_state + signal_type）

**数据状态优先：**
- `market_data_state === "insufficient"` → **数据不足**（橙色 badge）
- `market_data_state === "fault"` → **数据异常**（红色 badge）

**业务信号（data_state === "ok" 时）：**
- `signal_type === "hold"` → **持有**（绿色 badge）
- `signal_type === "sell"` → **卖出**（蓝色 badge）
- `signal_type === "risk"` → **风险**（橙色 badge）
- `signal_type === "invalidated"` → **失效**（灰色 badge）

### 今日动作

**数据状态优先逻辑：**
```typescript
if (market_data_state === "insufficient") 
  → "数据不足，建议暂停操作"

if (market_data_state === "fault") 
  → "数据异常，建议暂停操作"

if (signal_type === "hold" && market_data_state === "ok") 
  → "继续持有"

if (signal_type === "sell") 
  → "建议卖出"

if (signal_type === "risk") 
  → "注意风险"

if (signal_type === "invalidated") 
  → "论据失效"
```

**关键约束验证：**
✅ **不显示 fake hold** - 当 `market_data_state !== "ok"` 时，不会显示"继续持有"，而是显示"数据不足/异常，建议暂停操作"

### 信号日期
```
信号日期: 2026/7/3
```

---

## 返回首页链接

**链接文本：** ← 返回首页

**链接目标：** `/`

---

## 实际页面验证（空状态）

由于当前 `live_trade.db` 为空，访问 `/observations` 显示：

```
观察池
当前观察/持有的股票，以及今日需要做什么

[开仓 (0)] [已关闭 (0)] [全部 (0)]

暂无观察/持仓

去 Workbench 输入：
- "朋友推荐了某某股票"
- "我已经买入 XX 股，成交价 XX 元"
```

---

## 关键验收点

✅ **页面标题存在**  
✅ **Filter tabs 存在（开仓/已关闭/全部）**  
✅ **空状态文本清晰**  
✅ **去 Workbench 添加入口存在**  
✅ **数据状态独立于业务信号**（代码逻辑验证）  
✅ **不显示 fake hold**（当 data_state !== ok 时）

---

## 代码验证（数据状态优先逻辑）

**文件：** `frontend/app/observations/page.tsx` 第 93-110 行

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

  // Business signal
  if (signal_type === "hold") {
    return <span style={styles.badgeGreen}>持有</span>;
  }
  // ...
}
```

**验证：** ✅ 数据状态（insufficient/fault）优先于业务信号（hold/sell/risk）
