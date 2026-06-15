# Phase 3B Checkpoint: 人工确认流程 + 观察池管理

**完成时间**: 2025-01-XX  
**状态**: ✅ 完成  
**验收人**: Orion

---

## 1. 交付物清单

### 1.1 核心文件

| 文件路径 | 功能 | 代码行数 | 状态 |
|---------|------|---------|------|
| `src/ui/pages/research_simple.py` | 投研分析页面 v2（人工确认） | 350 行 | ✅ |
| `src/ui/pages/watchlist.py` | 观察池管理页面 | 270 行 | ✅ |
| `add_sample_watchlist.py` | 添加示例数据脚本 | 80 行 | ✅ |

**总计**: 700 行代码

### 1.2 数据存储

- **观察池数据文件**: `~/.hermes/traderlens/watchlist.json`
- **格式**: JSON
- **字段**:
  ```json
  {
    "items": [
      {
        "stock_code": "000001",
        "stock_name": "平安银行",
        "reason": "加入理由",
        "strategy_profile": "trend",
        "analysis_summary": {...},
        "trade_plan": {...},
        "status": "active",
        "added_at": "2025-01-XX",
        "updated_at": "2025-01-XX",
        "removed_at": null
      }
    ],
    "last_updated": "2025-01-XX"
  }
  ```

---

## 2. 功能实现

### 2.1 人工确认流程（Tab 1）

#### 状态机设计

```
idle (输入表单)
  ↓ [启动分析]
running (执行工具)
  ↓ [需要确认的工具]
waiting_approval (确认对话框)
  ↓ [批准] / [拒绝]
running (继续) / completed (结束)
  ↓
completed (显示结果)
```

#### 三种状态界面

**1. idle 状态**（输入表单）:
- 投资目标（文本框）
- 股票代码（文本框）
- 策略类型（下拉选择）
- 🚀 启动分析按钮

**2. waiting_approval 状态**（确认对话框）:
- 显示待确认的操作（action + action_input）
- 显示 Agent 的思考过程（thought）
- 显示已完成的步骤（decision_history）
- ✅ 批准按钮
- ❌ 拒绝按钮
- 🗑️ 取消分析按钮

**3. completed 状态**（结果展示）:
- 基本信息（股票代码 / 策略类型 / 状态）
- 决策链（可展开查看每一步）
- 工具输出（observations）
- 🔄 新分析按钮

#### 核心函数

```python
# 启动分析
start_analysis(goal, stock_code, strategy_profile)
  → 创建 initial_state
  → 设置 analysis_state = "running"
  → 调用 simulate_next_step()

# 请求人工确认
request_approval(action, action_input, thought)
  → 保存 pending_action 到 session_state
  → 设置 analysis_state = "waiting_approval"

# 批准/拒绝操作
approve_action(approved)
  → 如果批准: 执行 execute_action() → 继续 simulate_next_step()
  → 如果拒绝: 记录拒绝 → 设置 status = "failed" → 结束

# 执行工具（模拟）
execute_action(action, action_input)
  → 模拟工具执行
  → 记录到 decision_history
  → 保存到 observations
```

#### 需要确认的工具（MUST_REVIEW_TOOLS）

根据 `src/agent/config.py`：
- `watchlist_tool` - 加入观察池

其他工具默认自动执行，无需确认。

---

### 2.2 观察池管理（Tab 2）

#### 页面结构

```
观察池管理
├── 顶部操作栏
│   ├── 🔄 刷新按钮
│   └── 🗑️ 清空按钮（需二次确认）
├── 统计信息
│   ├── 总数（Metric）
│   ├── 活跃（Metric）
│   └── 已移除（Metric）
├── 过滤器
│   └── 状态筛选（全部 / 活跃 / 已移除）
└── 观察池列表
    └── 每个股票项（可展开）
        ├── 基本信息
        │   ├── 股票代码
        │   ├── 股票名称
        │   ├── 策略类型
        │   ├── 加入时间
        │   └── 状态
        ├── 加入理由
        ├── 分析摘要
        │   ├── 市场环境
        │   ├── 技术面
        │   └── 基本面
        ├── 交易计划（Metrics）
        │   ├── 建议操作
        │   ├── 入场价格
        │   └── 止损价格
        └── 操作按钮
            ├── 🗑️ 移除（活跃状态）
            └── ♻️ 恢复（已移除状态）
```

#### 核心函数

```python
# 加载观察池
load_watchlist() -> list
  → 读取 watchlist.json
  → 返回 items 列表

# 保存观察池
save_watchlist(items: list)
  → 写入 watchlist.json
  → 更新 last_updated 时间戳

# 添加到观察池
add_to_watchlist(stock_code, stock_name, reason, strategy_profile, 
                 analysis_summary, trade_plan)
  → 检查是否已存在
  → 如果存在: 更新现有项
  → 如果不存在: 添加新项
  → 保存到文件

# 从观察池移除（软删除）
remove_from_watchlist(stock_code)
  → 设置 status = "removed"
  → 设置 removed_at 时间戳

# 恢复到观察池
restore_to_watchlist(stock_code)
  → 设置 status = "active"
  → 清除 removed_at
  → 更新 updated_at

# 清空观察池
clear_watchlist()
  → 保存空列表
```

#### 数据字段说明

| 字段 | 类型 | 说明 |
|-----|------|------|
| `stock_code` | str | 股票代码（6 位数字） |
| `stock_name` | str | 股票名称 |
| `reason` | str | 加入理由（Agent 生成） |
| `strategy_profile` | str | 策略类型（trend/growth/value） |
| `analysis_summary` | dict | 分析摘要（market/technicals/fundamentals） |
| `trade_plan` | dict | 交易计划（action/entry_price/stop_loss/take_profit） |
| `status` | str | 状态（active/removed） |
| `added_at` | str | 加入时间（ISO 8601） |
| `updated_at` | str | 更新时间（ISO 8601） |
| `removed_at` | str\|null | 移除时间（ISO 8601 或 null） |

---

## 3. 技术实现

### 3.1 状态管理（Session State）

#### research_simple.py 使用的 session state

```python
st.session_state.analysis_state  # "idle" / "running" / "waiting_approval" / "completed"
st.session_state.pending_action  # 待确认的操作 {action, action_input, thought}
st.session_state.current_state   # 当前 AgentState
```

#### 状态转换规则

```python
# idle → running
start_analysis() 被调用

# running → waiting_approval
request_approval() 被调用（遇到需要确认的工具）

# waiting_approval → running
approve_action(approved=True) 被调用

# waiting_approval → completed
approve_action(approved=False) 被调用

# running → completed
simulate_next_step() 完成所有步骤

# completed → idle
用户点击 "新分析" 按钮
```

### 3.2 文件存储（JSON）

#### 观察池数据文件位置

```
~/.hermes/traderlens/watchlist.json
```

#### 为什么选择 JSON 而非 SQLite

**优势**：
- 简单直观，便于调试
- 无需数据库引擎
- 数据量小（< 100 只股票）
- 便于备份和迁移

**劣势**：
- 并发写入不安全（MVP 单用户可接受）
- 查询性能较低（数据量小可接受）
- 无索引、无事务

**未来改进**（Phase 4+）：
- 迁移到 SQLite
- 支持多用户
- 添加历史记录表

### 3.3 模拟执行（临时实现）

当前 `research_simple.py` 使用 `simulate_next_step()` 模拟 Agent 执行，未真正调用 LangGraph。

#### 模拟逻辑

```python
def simulate_next_step():
    if step_count == 0:
        execute_action("market_regime_tool", {...})
        simulate_next_step()  # 继续
    
    elif step_count == 1:
        execute_action("technicals_tool", {...})
        simulate_next_step()
    
    elif step_count == 2:
        request_approval("watchlist_tool", {...}, thought="...")
        # 等待用户确认
    
    else:
        analysis_state = "completed"
```

#### 真实集成（Phase 3C）

需要替换为：
```python
from src.agent.harness import run_agent

# 使用真实 Agent
final_state = run_agent(initial_state)
```

并处理 LangGraph 的 interrupt 机制。

---

## 4. 验收测试

### 4.1 人工确认流程测试

**测试步骤**:
1. 打开 http://localhost:8501
2. 切换到 Tab 1（投研分析）
3. 输入：
   - 投资目标: `分析平安银行能不能进观察池`
   - 股票代码: `000001`
   - 策略类型: `趋势策略`
4. 点击 "🚀 启动分析"
5. 等待执行到步骤 3（watchlist_tool）
6. 检查确认对话框显示：
   - ✅ 显示 "人工确认" 标题
   - ✅ 显示待确认的操作（watchlist_tool）
   - ✅ 显示思考过程
   - ✅ 显示操作参数
   - ✅ 显示已完成的步骤（步骤 1-2）
   - ✅ 显示 "批准" 和 "拒绝" 按钮

**场景 1: 批准操作**
7. 点击 "✅ 批准"
8. 检查：
   - ✅ 工具被执行
   - ✅ 分析完成
   - ✅ 显示最终结果

**场景 2: 拒绝操作**
7. 点击 "❌ 拒绝"
8. 检查：
   - ✅ 分析中止
   - ✅ 状态显示 "failed"
   - ✅ 决策链记录拒绝操作

### 4.2 观察池管理测试

**测试步骤**:
1. 运行 `python add_sample_watchlist.py` 添加示例数据
2. 打开 http://localhost:8501
3. 切换到 Tab 2（观察池）
4. 检查页面：
   - ✅ 显示统计信息（总数=3, 活跃=3, 已移除=0）
   - ✅ 显示 3 只股票（平安银行 / 贵州茅台 / 宁德时代）
   - ✅ 每只股票显示完整信息

**测试移除功能**:
5. 展开 "平安银行" 项
6. 点击 "🗑️ 移除" 按钮
7. 检查：
   - ✅ 状态变为 "已移除"
   - ✅ 统计信息更新（活跃=2, 已移除=1）
   - ✅ "移除" 按钮变为 "♻️ 恢复" 按钮

**测试恢复功能**:
8. 点击 "♻️ 恢复" 按钮
9. 检查：
   - ✅ 状态变回 "活跃"
   - ✅ 统计信息更新（活跃=3, 已移除=0）

**测试过滤功能**:
10. 移除一只股票
11. 在 "状态筛选" 选择 "已移除"
12. 检查：
    - ✅ 只显示已移除的股票

**测试清空功能**:
13. 点击 "🗑️ 清空" 按钮
14. 检查：
    - ✅ 显示警告 "再次点击确认清空"
15. 再次点击 "🗑️ 清空"
16. 检查：
    - ✅ 观察池被清空
    - ✅ 显示 "观察池为空" 提示

---

## 5. 已知限制

### 5.1 功能限制

- ❌ Agent 未真正集成（使用模拟执行）
- ❌ 只支持 watchlist_tool 的人工确认
- ❌ 无实时进度展示（未实现异步）
- ❌ 观察池无搜索功能
- ❌ 观察池无排序功能
- ❌ 无导出功能（JSON/CSV/Excel）

### 5.2 技术限制

- ❌ JSON 存储不支持并发写入
- ❌ 无数据校验（可能存储无效数据）
- ❌ 无备份机制
- ❌ Session state 无持久化（刷新页面丢失）
- ❌ 模拟执行逻辑硬编码（难以扩展）

### 5.3 UI/UX 限制

- ❌ 确认对话框无法取消单个操作（只能取消整个分析）
- ❌ 无撤销功能
- ❌ 移除股票需要二次确认（用户体验待优化）
- ❌ 无历史记录查询（无法回溯某只股票何时被移除）

---

## 6. Phase 3C 计划

### 6.1 待实现功能

**P0（必须）**:
- [ ] **真实 Agent 集成**
  - 替换 simulate_next_step() 为真实 run_agent()
  - 处理 LangGraph interrupt 机制
  - 支持多个工具的人工确认

- [ ] **实时进度展示**
  - 异步 Agent 运行（后台线程）
  - 实时更新决策链（轮询或 WebSocket）
  - 显示当前步骤和耗时

- [ ] **观察池集成到 Agent**
  - watchlist_tool 批准后自动调用 add_to_watchlist()
  - 传递完整的分析结果到观察池

**P1（重要）**:
- [ ] 回测历史页面（Tab 3）
- [ ] 策略管理页面（Tab 4）
- [ ] 设置页面（Tab 5）

**P2（可选）**:
- [ ] 观察池搜索功能
- [ ] 观察池排序功能
- [ ] 导出功能（JSON/CSV/Excel）
- [ ] 历史记录查询

### 6.2 技术改进

- [ ] **数据存储迁移到 SQLite**
  - 创建表结构（watchlist / analysis_history）
  - 支持事务和并发
  - 添加索引优化查询

- [ ] **Session State 持久化**
  - 保存到本地文件或数据库
  - 支持会话恢复

- [ ] **错误处理增强**
  - Agent 执行失败的友好提示
  - 文件 IO 错误处理
  - 网络超时重试

---

## 7. 依赖关系

### 7.1 已有依赖

- `streamlit>=1.32.0` ✅
- `src/agent/state.py` ✅
- `src/agent/config.py` ✅

### 7.2 新增依赖

无（Phase 3B 未引入新依赖）

---

## 8. 部署说明

### 8.1 启动 UI

```bash
# 1. 确保在项目根目录
cd /home/ubuntu/TraderLens

# 2. 启动 Streamlit
python run_ui.py

# 3. 访问
open http://localhost:8501
```

### 8.2 添加示例数据

```bash
# 添加 3 只示例股票到观察池
python add_sample_watchlist.py
```

### 8.3 观察池数据文件

```bash
# 查看观察池数据
cat ~/.hermes/traderlens/watchlist.json

# 备份观察池
cp ~/.hermes/traderlens/watchlist.json ~/watchlist_backup.json

# 恢复观察池
cp ~/watchlist_backup.json ~/.hermes/traderlens/watchlist.json
```

---

## 9. 总结

### 9.1 完成情况

- ✅ 人工确认流程 UI 框架完成
- ✅ 三种状态界面实现（idle / waiting_approval / completed）
- ✅ 观察池管理页面完成
- ✅ 观察池 CRUD 操作实现
- ✅ JSON 文件存储实现
- ✅ 示例数据脚本完成

### 9.2 代码质量

- **可读性**: ⭐⭐⭐⭐⭐ (注释完整，结构清晰)
- **可维护性**: ⭐⭐⭐⭐ (模块化设计，易扩展)
- **设计一致性**: ⭐⭐⭐⭐⭐ (严格遵循 Vercel 规范)
- **功能完整性**: ⭐⭐⭐ (核心功能完成，真实集成待 Phase 3C)

### 9.3 下一步

**Phase 3C**: 真实 Agent 集成 + 实时进度 + 完整的人工确认流程

---

**Phase 3B 状态**: ✅ **READY FOR PHASE 3C**
