# Phase 3A Checkpoint: Streamlit UI 基础框架

**完成时间**: 2025-01-XX  
**状态**: ✅ 完成  
**验收人**: Orion

---

## 1. 交付物清单

### 1.1 核心文件

| 文件路径 | 功能 | 代码行数 | 状态 |
|---------|------|---------|------|
| `src/ui/app.py` | Streamlit 主应用入口 | 274 行 | ✅ |
| `src/ui/pages/research.py` | 投研分析页面 | 267 行 | ✅ |
| `src/ui/pages/__init__.py` | Pages 模块初始化 | 4 行 | ✅ |
| `run_ui.py` | UI 启动脚本 | 23 行 | ✅ |

**总计**: 568 行代码

### 1.2 设计系统

- **风格**: Vercel Design System
- **字体**: Geist Sans (Primary) + Geist Mono (Code)
- **配色**: 
  - Primary: `#171717` (Vercel Black)
  - Background: `#ffffff` (Pure White)
  - Text: `#4d4d4d` (Gray-600)
  - Accent: `#0072f5` (Link Blue)
- **核心特征**:
  - Shadow-as-border 技术（`box-shadow: 0px 0px 0px 1px rgba(0,0,0,0.08)`）
  - 极致负字间距（Display: -2.4px, H2: -1.28px）
  - 三权重系统（400/500/600）
  - 多层阴影栈（border + elevation + ambient + inner highlight）

---

## 2. 功能实现

### 2.1 页面结构

```
TraderLens UI
├── Header（顶部导航）
│   ├── Logo: 📊 TraderLens
│   └── 文档按钮
├── Tab Navigation（5 个 Tab）
│   ├── 🔍 投研分析（Phase 3A 完成）
│   ├── 📈 观察池（占位）
│   ├── 📊 回测历史（占位）
│   ├── 🎯 策略管理（占位）
│   └── ⚙️ 设置（占位）
└── Content Area
    └── research.py 页面内容
```

### 2.2 投研分析页面（Tab 1）

#### 输入区域
- **投资目标**: 多行文本输入框（placeholder: "例如：分析平安银行能不能进观察池"）
- **股票代码**: 单行文本输入（placeholder: "000001"）
- **策略类型**: 下拉选择（trend/growth/value）

#### 控制按钮
- **🚀 启动分析**: Primary 按钮，触发 Agent 分析
- **🗑️ 清空**: Secondary 按钮，清空 session state

#### 结果展示
- **基本信息**:
  - 股票代码（Code badge）
  - 策略类型（Strategy badge）
  - 执行步数（Step count）
  
- **决策链**（可折叠）:
  - 每一步显示：
    - 💭 思考（Thought）
    - 🔧 工具（Action）
    - 📥 输入参数（Action Input, JSON）
    - ✅/❌ 状态（Status badge）
    - 📝 摘要（Summary）
    - 🏷️ 信号（Signals, Pill badges）
    - 详细结果（可折叠，JSON）

- **最终分析**:
  - 📈 市场环境
  - 📊 技术面分析
  - 🏢 板块强度
  - 💰 基本面分析
  - 🔄 回测结果
  - 📋 交易计划（入场价/止损价 Metrics）
  - ⭐ 观察池状态

---

## 3. 技术实现

### 3.1 Vercel 设计系统集成

#### 字体加载
```html
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@300;400;500;600&family=Geist+Mono:wght@400;500&display=swap" rel="stylesheet">
```

#### 核心 CSS 变量
```css
:root {
    --vercel-black: #171717;
    --vercel-white: #ffffff;
    --vercel-gray-900: #171717;
    --vercel-gray-600: #4d4d4d;
    --vercel-gray-400: #808080;
    --vercel-gray-100: #ebebeb;
    --vercel-gray-50: #fafafa;
    --vercel-link-blue: #0072f5;
    --vercel-focus-blue: hsla(212, 100%, 48%, 1);
}
```

#### 标题样式
- **H1**: 48px, weight 600, line-height 1.17, letter-spacing -2.4px
- **H2**: 32px, weight 600, line-height 1.25, letter-spacing -1.28px
- **H3**: 24px, weight 600, line-height 1.33, letter-spacing -0.96px

#### 按钮样式
- **Primary**: `background: #171717`, `color: #ffffff`, `radius: 6px`
- **Secondary**: `background: #ffffff`, `box-shadow: rgba(0,0,0,0.08) 0px 0px 0px 1px`
- **Hover**: `background: #000000`, `box-shadow: 0 4px 12px rgba(0,0,0,0.15)`

#### 卡片样式
```css
.card {
    background-color: #ffffff;
    border-radius: 8px;
    box-shadow: rgba(0,0,0,0.08) 0px 0px 0px 1px,
                rgba(0,0,0,0.04) 0px 2px 2px,
                rgba(230,230,230,1) 0px 0px 0px 1px inset;
    padding: 24px;
}
```

#### Badge/Pill 样式
```css
.badge {
    display: inline-block;
    background-color: #ebf5ff;
    color: #0068d6;
    font-family: 'Geist', sans-serif;
    font-size: 12px;
    font-weight: 500;
    padding: 4px 10px;
    border-radius: 9999px;
}
```

### 3.2 Agent 集成

#### 工作流
1. 用户输入 `goal`, `stock_code`, `strategy_profile`
2. 创建 `AgentState` 初始状态
3. 调用 `run_agent(initial_state)` 同步执行
4. 保存 `final_state` 到 `st.session_state.analysis_result`
5. 渲染结果（决策链 + 最终分析）

#### State 结构
```python
AgentState = {
    "thread_id": str,           # 会话 ID
    "run_id": str,              # 运行 ID
    "goal": str,                # 投资目标
    "stock_code": str,          # 股票代码
    "strategy_profile": str,    # 策略类型
    "observations": dict,       # 工具输出结果
    "decision_history": list,   # 决策链
    "next_action": str,         # 下一步工具
    "next_action_input": dict,  # 下一步输入
    "is_goal_complete": bool,   # 是否完成
    "status": str,              # 运行状态
    "thought_summary": str,     # 最终总结
    "_tool_call_counts": dict   # 工具调用计数
}
```

### 3.3 启动配置

#### 启动脚本 `run_ui.py`
```python
subprocess.run([
    sys.executable,
    "-m", "streamlit", "run", "src/ui/app.py",
    "--server.port=8501",
    "--server.address=0.0.0.0",
    "--theme.base=light",
    "--theme.primaryColor=#171717",
    "--theme.backgroundColor=#ffffff",
    "--theme.secondaryBackgroundColor=#fafafa",
    "--theme.textColor=#171717"
])
```

#### 健康检查
```bash
curl http://localhost:8501/_stcore/health
# 返回: ok
```

---

## 4. 验收测试

### 4.1 UI 启动测试
```bash
cd /home/ubuntu/TraderLens
python run_ui.py
# 或
python -m streamlit run src/ui/app.py --server.port=8501 --server.address=0.0.0.0
```

**预期结果**:
- ✅ Streamlit 启动成功
- ✅ 访问 `http://localhost:8501` 可见界面
- ✅ Health check 返回 `ok`

### 4.2 页面渲染测试

**测试步骤**:
1. 打开浏览器访问 `http://localhost:8501`
2. 检查字体加载（Geist Sans 显示）
3. 检查 5 个 Tab 可见
4. 检查输入框、按钮样式符合 Vercel 规范

**预期结果**:
- ✅ 标题使用 Geist 字体，负字间距明显
- ✅ 按钮为黑色背景白色文字（Primary）
- ✅ 输入框有 shadow-border（无传统 border）
- ✅ Tab 切换正常

### 4.3 Agent 集成测试（手动）

**测试步骤**:
1. 在 "投资目标" 输入: `分析平安银行能不能进观察池`
2. 在 "股票代码" 输入: `000001`
3. 选择策略类型: `趋势策略`
4. 点击 "🚀 启动分析"
5. 等待 Agent 运行完成
6. 检查决策链展示
7. 检查最终分析结果

**预期结果**:
- ✅ Agent 成功启动（显示 Spinner）
- ✅ 决策链正确显示（每步包含 thought/action/result）
- ✅ 最终分析包含所有模块结果
- ✅ Signals 显示为 Pill badges
- ✅ 交易计划显示 Metrics（入场价/止损价）

---

## 5. 已知限制

### 5.1 功能限制
- ❌ Tab 2-5（观察池/回测历史/策略管理/设置）仅占位，未实现
- ❌ Agent 运行过程不显示实时进度（同步阻塞）
- ❌ 无历史记录查询功能
- ❌ 无结果导出功能

### 5.2 UI 限制
- ❌ 无移动端适配
- ❌ 无暗色模式
- ❌ 无加载动画（除 Streamlit 默认 Spinner）
- ❌ 决策链过长时无虚拟滚动优化

### 5.3 集成限制
- ❌ Agent 运行在主线程（长时间运行会阻塞 UI）
- ❌ 无并发分析支持（一次只能分析一只股票）
- ❌ Session state 无持久化（刷新页面清空）

---

## 6. Phase 3B 计划

### 6.1 待实现功能

**P0（必须）**:
- [ ] **观察池管理**（Tab 2）
  - 显示所有已加入观察池的股票
  - 支持删除/批量操作
  - 显示加入时间/理由/当前状态
  
- [ ] **人工确认流程**
  - Watchlist tool 触发时显示确认对话框
  - 显示完整分析结果供用户决策
  - 用户确认后才真正加入观察池
  
- [ ] **实时进度展示**
  - 异步 Agent 运行（后台线程）
  - 实时更新决策链（WebSocket 或轮询）
  - 显示当前执行步骤和耗时

**P1（重要）**:
- [ ] **回测历史**（Tab 3）
  - 显示所有 backtest_tool 执行记录
  - 可视化收益曲线
  - 对比不同策略/参数

- [ ] **策略管理**（Tab 4）
  - 配置 trend/growth/value 策略参数
  - 保存自定义策略
  - 策略回测结果对比

- [ ] **设置页面**（Tab 5）
  - 数据源切换（Mock/Real API）
  - LLM 配置（模型/温度/最大步数）
  - 缓存管理

**P2（可选）**:
- [ ] 移动端适配
- [ ] 暗色模式
- [ ] 结果导出（JSON/PDF/Excel）
- [ ] 历史会话管理
- [ ] 多股票批量分析

### 6.2 技术改进

- [ ] **异步 Agent 运行**
  - 后台线程执行 `run_agent()`
  - 主线程轮询 state 更新 UI
  - 支持取消运行

- [ ] **State 持久化**
  - SQLite 存储历史分析结果
  - 支持查询/检索
  - Session 恢复

- [ ] **性能优化**
  - 决策链虚拟滚动
  - 大数据集分页
  - 缓存结果

- [ ] **错误处理**
  - Agent 失败时友好提示
  - 工具超时重试机制
  - 网络错误恢复

---

## 7. 依赖关系

### 7.1 已有依赖
- `streamlit>=1.32.0` ✅ 已安装
- `plotly>=5.18.0` ✅ 已安装
- `src/agent/harness.py` ✅ 已实现（Phase 2）
- `src/agent/state.py` ✅ 已实现（Phase 2）

### 7.2 新增依赖
无（Phase 3A 未引入新依赖）

---

## 8. 部署说明

### 8.1 本地开发
```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 启动 UI
python run_ui.py
# 或
streamlit run src/ui/app.py

# 3. 访问
open http://localhost:8501
```

### 8.2 生产部署（未来）
```bash
# 使用 Docker
docker build -t traderlens-ui .
docker run -p 8501:8501 traderlens-ui

# 或使用 Streamlit Cloud
streamlit deploy src/ui/app.py
```

---

## 9. 截图占位

（实际使用时在浏览器中截图填充）

### 9.1 主界面
```
[ 截图: 顶部导航 + 5 个 Tab ]
```

### 9.2 投研分析页面
```
[ 截图: 输入区域 + 启动按钮 ]
```

### 9.3 分析结果展示
```
[ 截图: 决策链 + 最终分析 ]
```

---

## 10. 总结

### 10.1 完成情况
- ✅ Streamlit 基础框架搭建完成
- ✅ Vercel 设计系统完整集成
- ✅ 投研分析页面（Tab 1）核心功能实现
- ✅ Agent 同步调用流程打通
- ✅ 决策链可视化展示完成
- ✅ 最终分析结果结构化展示

### 10.2 代码质量
- **可读性**: ⭐⭐⭐⭐⭐ (注释完整，结构清晰)
- **可维护性**: ⭐⭐⭐⭐ (模块化设计，易扩展)
- **设计一致性**: ⭐⭐⭐⭐⭐ (严格遵循 Vercel 规范)
- **性能**: ⭐⭐⭐ (同步阻塞，Phase 3B 优化)

### 10.3 下一步
1. **Phase 3B**: 实现人工确认流程（观察池）
2. **Phase 3C**: 异步 Agent 运行 + 实时进度
3. **Phase 3D**: 历史记录 + 回测可视化
4. **Phase 4**: 生产部署 + 监控

---

**Phase 3A 状态**: ✅ **READY FOR PHASE 3B**
