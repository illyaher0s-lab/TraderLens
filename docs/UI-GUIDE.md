# TraderLens UI 使用指南

## 快速启动

### 1. 安装依赖
```bash
pip install -r requirements.txt
```

### 2. 启动 UI
```bash
python run_ui.py
```

或者：
```bash
streamlit run src/ui/app.py
```

### 3. 访问界面
打开浏览器访问：**http://localhost:8501**

---

## 功能说明

### 🔍 投研分析（Tab 1）

这是主要功能页面，使用 Goal-driven ReAct Agent 进行股票分析。

#### 输入参数
1. **投资目标**（必填）
   - 自然语言描述你的分析目标
   - 示例：`分析平安银行能不能进观察池`
   - 示例：`评估贵州茅台的投资价值`

2. **股票代码**（必填）
   - 6 位股票代码
   - 示例：`000001`（平安银行）
   - 示例：`600519`（贵州茅台）

3. **策略类型**（必选）
   - **趋势策略**（trend）：关注价格趋势和动量
   - **成长策略**（growth）：关注营收增长和市场扩张
   - **价值策略**（value）：关注估值和分红

#### 启动分析
点击 **🚀 启动分析** 按钮后，Agent 将：
1. 自动调用 8 个分析工具
2. 实时展示决策链
3. 生成最终分析报告

#### 结果展示

**决策链**（可展开查看每一步）：
- 💭 思考：Agent 的推理过程
- 🔧 工具：调用的工具名称
- 📥 输入参数：传给工具的参数（JSON 格式）
- ✅/❌ 状态：执行成功/失败
- 📝 摘要：工具返回的简要总结
- 🏷️ 信号：识别的交易信号（如 `MA金叉`, `超卖区`, `板块领先`）

**最终分析**：
- 📈 **市场环境**：当前市场状态（牛市/熊市/震荡）
- 📊 **技术面分析**：MA、RSI、成交量等技术指标
- 🏢 **板块强度**：所属板块表现和个股排名
- 💰 **基本面分析**：财务评分和行业对比
- 🔄 **回测结果**：策略历史表现
- 📋 **交易计划**：建议操作、入场价、止损价
- ⭐ **观察池**：是否加入观察池

---

## 设计特色

### Vercel 设计系统
UI 严格遵循 Vercel 设计规范：

- **字体**：Geist Sans（主字体）+ Geist Mono（代码）
- **配色**：
  - Primary: `#171717`（Vercel Black）
  - Background: `#ffffff`（Pure White）
  - Text: `#4d4d4d`（Gray-600）
  - Accent: `#0072f5`（Link Blue）

- **核心特征**：
  - Shadow-as-border 技术（无传统 border）
  - 极致负字间距（Display: -2.4px）
  - 多层阴影栈（border + elevation + ambient）

---

## 技术架构

### 前端
- **框架**：Streamlit 1.32+
- **设计系统**：Vercel Design System
- **字体**：Google Fonts (Geist)

### 后端
- **Agent 框架**：LangGraph
- **工具集**：8 个分析工具（market_regime, technicals, sector_strength, fundamentals, backtest, trade_plan, watchlist, research_memory）
- **数据源**：AKShare/Tushare/BaoStock（Mock 模式）

### 数据流
```
用户输入 → AgentState → run_agent() → LangGraph 循环 → 最终结果 → UI 展示
```

---

## 开发模式

### 启动开发服务器
```bash
streamlit run src/ui/app.py --server.runOnSave=true
```

### 文件结构
```
src/ui/
├── app.py              # 主应用入口
├── pages/
│   ├── __init__.py
│   └── research.py     # 投研分析页面
```

### 添加新页面
1. 在 `src/ui/pages/` 创建新文件
2. 实现 `render()` 函数
3. 在 `app.py` 中导入并添加到对应 Tab

---

## 故障排查

### 问题：无法访问 UI
**检查**：
```bash
curl http://localhost:8501/_stcore/health
```
应返回 `ok`

**解决**：
```bash
# 1. 检查 Streamlit 是否运行
ps aux | grep streamlit

# 2. 重启 UI
pkill -f streamlit
python run_ui.py
```

### 问题：Agent 运行失败
**检查日志**：
```bash
tail -f logs/agent.log
```

**常见原因**：
- 股票代码格式错误（应为 6 位数字）
- 数据源不可用（Mock 模式应始终可用）
- LLM API 配置错误

### 问题：样式显示异常
**检查**：
1. 浏览器是否支持 CSS custom properties
2. Google Fonts 是否加载成功（检查 Network 面板）
3. 清除浏览器缓存后刷新

---

## 性能优化

### 当前限制
- Agent 运行在主线程（同步阻塞）
- 长时间运行会阻塞 UI
- 无并发分析支持

### 未来改进（Phase 3B+）
- [ ] 异步 Agent 运行（后台线程）
- [ ] 实时进度展示（WebSocket）
- [ ] 并发分析支持（多股票）
- [ ] 结果缓存和持久化

---

## 待实现功能

### Phase 3B
- [ ] 观察池管理（Tab 2）
- [ ] 人工确认流程
- [ ] 实时进度展示

### Phase 3C
- [ ] 回测历史（Tab 3）
- [ ] 策略管理（Tab 4）
- [ ] 设置页面（Tab 5）

### Phase 3D
- [ ] 移动端适配
- [ ] 暗色模式
- [ ] 结果导出（JSON/PDF/Excel）
- [ ] 历史会话管理

---

## 测试

### 运行验收测试
```bash
python test_phase3a.py
```

**预期输出**：
```
============================================================
Phase 3A UI 验收测试
============================================================
🔍 测试 1: Streamlit 健康检查...
✅ Streamlit 健康检查通过

🔍 测试 2: 主页面加载...
✅ 主页面返回 200 OK

🔍 测试 3: UI 模块导入...
✅ research 模块导入成功
✅ research.render() 函数存在

🔍 测试 4: Agent 集成...
✅ Agent 模块导入成功
✅ run_agent() 函数签名正确

============================================================
通过率: 4/4 (100%)
============================================================

🎉 所有测试通过！Phase 3A UI 验收完成
```

---

## 联系方式

- **项目地址**：`/home/ubuntu/TraderLens`
- **文档目录**：`docs/`
- **Checkpoint**：`docs/checkpoints/phase3a-checkpoint.md`

---

**Version**: Phase 3A  
**Last Updated**: 2025-01-XX  
**Status**: ✅ Ready for Phase 3B
