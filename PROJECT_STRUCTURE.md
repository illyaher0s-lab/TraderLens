# TraderLens 项目结构说明

本文档详细说明 TraderLens 项目的文件结构和各模块职责。

---

## 完整目录树

```
TraderLens/
├── config/                                  # 配置文件
│   └── judgment_framework.yaml              # 判断框架配置（策略权重、评分规则）
│
├── src/                                     # 源代码
│   ├── agent/                               # Agent 核心（Harness）
│   │   ├── __init__.py
│   │   ├── state.py                         # AgentState 定义
│   │   ├── context_builder.py              # ContextBuilder 节点
│   │   ├── reasoner.py                      # AgentReasoner 节点（LLM 推理）
│   │   ├── executor.py                      # ToolExecutor 节点（工具执行）
│   │   ├── quality_gate.py                  # QualityGate 节点（安全检查）
│   │   ├── human_review.py                  # HumanReview 节点（人工确认）
│   │   ├── harness.py                       # LangGraph 主图定义
│   │   └── config.py                        # 硬限制配置（MAX_STEPS 等）
│   │
│   ├── tools/                               # Agent 可调用的工具（8个）
│   │   ├── __init__.py
│   │   ├── market_regime_tool.py            # 评估市场环境
│   │   ├── sector_strength_tool.py          # 分析板块强度
│   │   ├── fundamentals_tool.py             # 基本面分析
│   │   ├── technicals_tool.py               # 技术面分析
│   │   ├── backtest_tool.py                 # 策略回测
│   │   ├── trade_plan_tool.py               # 生成交易计划
│   │   ├── watchlist_tool.py                # 加入观察池（需人工确认）
│   │   └── research_memory_tool.py          # 检索历史记录（第一版占位）
│   │
│   ├── core/                                # 核心模块（底层实现）
│   │   ├── __init__.py
│   │   ├── data_fetcher.py                  # 数据获取（AKShare、Tushare、BaoStock）
│   │   ├── cache_manager.py                 # 缓存管理（文件 + 内存）
│   │   ├── judgment_engine.py               # 判断引擎（基于 YAML 配置）
│   │   ├── backtest_engine.py               # 回测引擎（严格防未来函数）
│   │   ├── watchlist_manager.py             # 观察池管理
│   │   └── db_init.py                       # 数据库初始化脚本
│   │
│   ├── memory/                              # 记忆层（为第二阶段预留）
│   │   ├── __init__.py
│   │   └── research_memory.py               # 研究记忆（第一版占位，返回空）
│   │
│   └── ui/                                  # Streamlit UI
│       ├── app.py                           # 主入口
│       └── pages/
│           ├── research.py                  # Tab 1: 投研分析
│           ├── backtest.py                  # Tab 2: 策略回测
│           ├── watchlist.py                 # Tab 3: 观察池
│           ├── review.py                    # Tab 4: 复盘优化
│           └── settings.py                  # Tab 5: 系统配置
│
├── data/                                    # 数据目录
│   ├── cache/                               # 本地缓存（行情、财务数据）
│   ├── investment_agent.db                  # SQLite 数据库
│   └── checkpoints.db                       # LangGraph checkpoints
│
├── tests/                                   # 测试（按模块划分）
│   ├── agent/
│   │   ├── test_context_builder.py
│   │   ├── test_reasoner.py
│   │   ├── test_executor.py
│   │   └── test_quality_gate.py
│   ├── tools/
│   │   ├── test_fundamentals_tool.py
│   │   ├── test_backtest_tool.py
│   │   └── ...
│   └── core/
│       ├── test_data_fetcher.py
│       ├── test_judgment_engine.py
│       └── ...
│
├── docs/                                    # 设计文档
│   └── specs/
│       └── 2026-06-08-traderlens-agent-design.md
│
├── requirements.txt                         # Python 依赖
├── .env.example                             # 环境变量模板
├── .gitignore
├── README.md                                # 项目简介
├── AGENTS.md                                # 开发规范
└── PROJECT_STRUCTURE.md                     # 本文档
```

---

## 模块职责详解

### 1. `src/agent/` - Agent 核心（Harness）

**职责**：LangGraph 主图定义和节点实现，不包含业务逻辑。

| 文件 | 职责 | 关键函数/类 |
|------|------|------------|
| `state.py` | AgentState 类型定义 | `AgentState` (TypedDict) |
| `context_builder.py` | 整理上下文，提取关键信息给 LLM | `context_builder(state) -> state` |
| `reasoner.py` | LLM 推理下一步行动 | `agent_reasoner(state) -> state` |
| `executor.py` | 执行工具调用 | `tool_executor(state) -> state` |
| `quality_gate.py` | 安全检查 + 质量门（6 个检查点） | `quality_gate(state) -> state` |
| `human_review.py` | 人工确认节点（中断点） | `human_review(state) -> state` |
| `harness.py` | LangGraph 主图编译和执行入口 | `create_agent_graph()`, `run_agent()` |
| `config.py` | 硬限制配置（最大步数、单工具调用次数） | `MAX_STEPS`, `MUST_REVIEW_TOOLS` |

**依赖关系**：
- `reasoner.py` 依赖 LangChain Agent
- `executor.py` 依赖 `src/tools/`
- `harness.py` 依赖所有节点

---

### 2. `src/tools/` - 工具层

**职责**：Agent 可调用的 8 个粗粒度工具，包装底层模块。

| 文件 | 职责 | 输入 | 输出 | 是否需要人工确认 |
|------|------|------|------|-----------------|
| `market_regime_tool.py` | 评估市场环境 | `index_code` | 市场环境 + 置信度 | 否 |
| `sector_strength_tool.py` | 分析板块强度 | `stock_code` | 板块强度 + 相对排名 | 否 |
| `fundamentals_tool.py` | 基本面分析 | `stock_code, strategy_profile` | 基本面评分 + 关键指标 | 否 |
| `technicals_tool.py` | 技术面分析 | `stock_code` | 技术面评分 + 关键信号 | 否 |
| `backtest_tool.py` | 策略回测 | `stock_code, strategy_profile, period` | 回测结果 | 否 |
| `trade_plan_tool.py` | 生成交易计划 | `stock_code, observations` | 交易计划 | 否 |
| `watchlist_tool.py` | 加入观察池 | `stock_code, entry_trigger, invalid_condition` | 成功/失败 | **是** |
| `research_memory_tool.py` | 检索历史记录 | `query, limit` | 历史记录（第一版空） | 否 |

**统一输出格式**：
```python
{
    "tool": str,               # 工具名称
    "status": str,             # "success" | "error"
    "message": str,            # 说明信息
    "data": dict,              # 核心数据
    "data_ref": str | None,    # 数据引用路径
    "timestamp": str           # 执行时间
}
```

**依赖关系**：
- 所有工具依赖 `src/core/`（DataFetcher、JudgmentEngine、BacktestEngine）
- 不直接调用外部 API，通过 DataFetcher 统一拉取

---

### 3. `src/core/` - 核心模块

**职责**：底层业务逻辑实现，保留自旧架构。

| 文件 | 职责 | 关键方法 |
|------|------|---------|
| `data_fetcher.py` | 数据获取（AKShare、Tushare、BaoStock） | `get_stock_history()`, `get_financial_data()`, `get_valuation_data()` |
| `cache_manager.py` | 缓存管理（文件 + 内存） | `get()`, `set()`, `exists()`, `clear()` |
| `judgment_engine.py` | 判断引擎（基于 YAML 配置） | `evaluate_market_regime()`, `evaluate_fundamentals()`, `evaluate_technicals()` |
| `backtest_engine.py` | 回测引擎（严格防未来函数） | `run_backtest()` |
| `watchlist_manager.py` | 观察池管理（SQLite CRUD） | `add_to_watchlist()`, `get_watchlist()`, `update_status()` |
| `db_init.py` | 数据库初始化脚本 | `init_database()` |

**依赖关系**：
- `data_fetcher.py` 依赖 `cache_manager.py`
- `judgment_engine.py` 依赖 `config/judgment_framework.yaml`
- 所有模块独立，不依赖 `src/agent/` 或 `src/tools/`

---

### 4. `src/memory/` - 记忆层

**职责**：历史研究记录检索（第一版占位，第二版接 RAG）。

| 文件 | 职责 | 状态 |
|------|------|------|
| `research_memory.py` | 检索历史研究记录 | 第一版返回空，第二版接向量数据库 |

**第二阶段扩展**：
- 向量数据库（Chroma / Qdrant）
- Embedding 模型（text-embedding-3-small / bge-large-zh）
- 语义检索 + 过滤条件 + 时间衰减

---

### 5. `src/ui/` - Streamlit UI

**职责**：用户界面，5 个 Tab。

| 文件 | 职责 | MVP v0.1 状态 |
|------|------|--------------|
| `app.py` | 主入口，Tab 导航 | ✅ 实现 |
| `pages/research.py` | Tab 1: 投研分析（用户输入 goal → Agent 执行 → 展示决策链） | ✅ 实现 |
| `pages/backtest.py` | Tab 2: 策略回测 | ❌ 第二阶段 |
| `pages/watchlist.py` | Tab 3: 观察池 | ❌ 第二阶段 |
| `pages/review.py` | Tab 4: 复盘优化 | ❌ 第二阶段 |
| `pages/settings.py` | Tab 5: 系统配置 | ❌ 第二阶段 |

---

### 6. `config/` - 配置文件

| 文件 | 职责 | 格式 |
|------|------|------|
| `judgment_framework.yaml` | 判断框架配置（策略权重、评分规则、行业相对分位等） | YAML |

**示例结构**：
```yaml
strategies:
  trend:
    technical_weight: 0.6
    fundamental_weight: 0.4
  growth:
    technical_weight: 0.4
    fundamental_weight: 0.6
  value:
    technical_weight: 0.3
    fundamental_weight: 0.7

scoring_rules:
  fundamentals:
    pe_ratio: {...}
    pb_ratio: {...}
  technicals:
    ma_crossover: {...}
    macd_signal: {...}
```

---

### 7. `data/` - 数据目录

| 文件/目录 | 职责 |
|----------|------|
| `cache/` | 本地缓存（行情、财务数据，Parquet 格式） |
| `investment_agent.db` | SQLite 数据库（research_history、watchlist、backtest_results 表） |
| `checkpoints.db` | LangGraph checkpoints（中断恢复） |

---

### 8. `tests/` - 测试

| 目录 | 职责 |
|------|------|
| `agent/` | Agent 节点测试 |
| `tools/` | 工具测试（Mock 底层模块） |
| `core/` | 核心模块测试 |

---

## 数据流

```
用户输入 goal
    ↓
Streamlit UI (src/ui/app.py)
    ↓
Agent Harness (src/agent/harness.py)
    ↓
ContextBuilder → AgentReasoner → ToolExecutor → QualityGate
    ↓                  ↓              ↓
    |            LangChain Agent    src/tools/
    |                               ↓
    |                          src/core/ (DataFetcher, JudgmentEngine, BacktestEngine)
    |                               ↓
    |                          AKShare / Tushare / BaoStock
    |                               ↓
    |                          data/cache/
    ↓
decision_history 记录到 SQLite
    ↓
Streamlit UI 展示决策链 + 最终结果
```

---

## 依赖关系图

```
src/ui/
  ├─→ src/agent/harness.py
  
src/agent/harness.py
  ├─→ src/agent/state.py
  ├─→ src/agent/context_builder.py
  ├─→ src/agent/reasoner.py
  ├─→ src/agent/executor.py
  ├─→ src/agent/quality_gate.py
  └─→ src/agent/human_review.py

src/agent/executor.py
  └─→ src/tools/*.py

src/tools/*.py
  ├─→ src/core/data_fetcher.py
  ├─→ src/core/judgment_engine.py
  ├─→ src/core/backtest_engine.py
  └─→ src/core/watchlist_manager.py

src/core/data_fetcher.py
  └─→ src/core/cache_manager.py

src/core/judgment_engine.py
  └─→ config/judgment_framework.yaml
```

---

## 添加新工具的步骤

1. **定义工具函数**（`src/tools/new_tool.py`）
   ```python
   def new_tool(param1: str, param2: int) -> dict:
       """新工具说明"""
       # 1. 调用底层模块
       # 2. 返回统一格式
       return {"tool": "new_tool", "status": "success", ...}
   ```

2. **注册到 ToolExecutor**（`src/agent/executor.py`）
   ```python
   elif tool_name == "new_tool":
       from src.tools.new_tool import new_tool
       result = new_tool(**tool_input)
       state["observations"]["new_tool"] = result
   ```

3. **更新 AgentReasoner 的 prompt**（`src/agent/reasoner.py`）
   ```python
   可用工具：
   - new_tool: 新工具说明
   ```

4. **编写测试**（`tests/tools/test_new_tool.py`）

---

## 常见问题

### Q: 为什么 `src/agent/` 和 `src/tools/` 分开？
A: `src/agent/` 是通用的 Agent Harness，不包含业务逻辑。`src/tools/` 是具体的投研工具，包含业务逻辑。分离后 Agent 框架可以复用。

### Q: 为什么工具要包装 `src/core/`，而不是直接实现？
A: 复用现有代码，避免重复造轮子。底层模块已经实现了数据拉取、判断引擎、回测引擎，工具只需要包装。

### Q: 为什么 `research_memory_tool` 第一版返回空？
A: MVP 优先验证 Agent 架构可行性，RAG 是第二阶段的增强功能。第一版占位，接口预留。

---

**最后更新**: 2026-06-08
