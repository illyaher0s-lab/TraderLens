# TraderLens

**TraderLens** 是一个基于 LangGraph 的 A 股投资研究智能体系统，旨在帮助个人投资者进行系统化的投资分析和决策辅助。

---

## 核心特性

### 真正的 AI Agent（不是固定工作流）

- **Goal-driven（目标驱动）**：用户给出目标（"分析平安银行能不能进观察池"），Agent 自主拆解任务
- **自主决策**：Agent 每一步自己选择调用哪个工具、是否继续、是否完成
- **工具使用**：8 个粗粒度工具（市场环境、基本面、技术面、回测、交易计划等）
- **决策链可追溯**：每一步记录 observe → thought → action → result
- **人工确认点**：关键决策（加入观察池）需要人工确认

### MVP v0.1 功能

- ✅ Agent Harness（5 个节点 + 循环逻辑）
- ✅ 8 个投研工具（市场环境、基本面、技术面、回测、交易计划、观察池等）
- ✅ 决策链完整记录（可追溯、可复盘）
- ✅ 硬限制（最大步数 8、单工具最多调用 2 次）
- ✅ Streamlit UI（投研分析界面）
- ✅ SQLite 存储（研究记录持久化）
- ✅ LangGraph checkpoint（中断恢复）

---

## 架构设计

### Agent Harness（LangGraph）

```
Start
  ↓
ContextBuilder（整理上下文）
  ↓
AgentReasoner（LLM 推理下一步）
  ↓
ToolExecutor（执行工具）
  ↓
QualityGate（安全检查 + 质量门）
  ├── running → ContextBuilder（继续循环）
  ├── waiting_human → HumanReview → ContextBuilder
  ├── completed → End
  └── error → End
```

### 工具层（8 个粗粒度工具）

**观察类工具**（获取事实）：
- `evaluate_market_regime` - 评估市场环境
- `analyze_sector_strength` - 分析板块强度
- `analyze_stock_fundamentals` - 基本面分析
- `analyze_stock_technicals` - 技术面分析
- `search_research_memory` - 检索历史记录（占位）

**验证类工具**（检验假设）：
- `run_strategy_backtest` - 策略回测

**决策类工具**（生成结果）：
- `generate_trade_plan` - 生成交易计划
- `add_to_watchlist` - 加入观察池（需人工确认）

### 核心模块

- `DataFetcher` - 数据获取（AKShare、Tushare、BaoStock）
- `JudgmentEngine` - 判断引擎（基于 YAML 配置）
- `BacktestEngine` - 回测引擎（严格防未来函数）
- `CacheManager` - 缓存管理（文件 + 内存）

---

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入 API keys
```

### 3. 初始化数据库

```bash
python -m src.core.db_init
```

### 4. 启动 Streamlit UI

```bash
streamlit run src/ui/app.py
```

---

## 项目结构

```
TraderLens/
├── config/                  # 判断框架配置
├── src/
│   ├── agent/              # Agent 核心（Harness）
│   ├── tools/              # 8 个粗粒度工具
│   ├── core/               # 底层模块（DataFetcher、JudgmentEngine 等）
│   ├── memory/             # 记忆层（第一版占位）
│   └── ui/                 # Streamlit UI
├── data/                   # 数据目录
├── tests/                  # 测试
├── docs/                   # 设计文档
└── requirements.txt
```

详细结构参见 [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md)。

---

## 设计文档

完整设计文档：[docs/specs/2026-06-08-traderlens-agent-design.md](docs/specs/2026-06-08-traderlens-agent-design.md)

包含：
- Part 1: 项目概述与架构变更
- Part 2: AgentState 设计
- Part 3: Agent Harness 节点设计
- Part 4: 工具层设计
- Part 5: 核心模块
- Part 6: 记忆层设计（占位）
- Part 7: 文件结构
- Part 8: MVP 实现计划

---

## 技术栈

- **Agent 框架**：LangGraph + LangChain
- **LLM**：OpenAI GPT-4 / Anthropic Claude Sonnet
- **数据源**：AKShare、Tushare、BaoStock
- **UI**：Streamlit + Plotly
- **数据库**：SQLite（第一版）
- **缓存**：本地文件缓存 + 内存缓存

---

## Roadmap

### MVP v0.1（当前）
- [x] Agent Harness 基础框架
- [x] 8 个投研工具
- [ ] Streamlit UI（Tab 1: 投研分析）
- [ ] 决策链可视化
- [ ] 人工确认流程

### v0.2（第二阶段）
- [ ] RAG 接入（向量数据库 + Embedding）
- [ ] 回测结果影响策略权重
- [ ] 复盘模块自动生成优化建议
- [ ] Tab 2-5 完整实现（策略回测、观察池、复盘、配置）
- [ ] 更多工具（suggest_framework_update、compare_strategies）

---

## 开发规范

参见 [AGENTS.md](AGENTS.md)

---

## License

MIT

---

## 联系方式

- GitHub Issues: [TraderLens/issues](https://github.com/yourusername/TraderLens/issues)
