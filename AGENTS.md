# AGENTS.md - TraderLens 开发规范

本文档定义 TraderLens 项目的开发规范和最佳实践。

---

## 核心原则

### 1. 真正的 Agent，不是工作流

❌ **不要**把 Agent 当成固定流程：
```python
# 错误示例：预定义固定顺序
step1 = fetch_data()
step2 = analyze_fundamentals()
step3 = analyze_technicals()
step4 = backtest()
```

✅ **应该**让 Agent 自主决策：
```python
# 正确示例：Agent 每一步自己决定
while not goal_complete:
    next_action = agent_reasoner(state)  # LLM 推理
    result = tool_executor(next_action)  # 执行工具
    state = update_state(result)         # 更新状态
```

### 2. 决策链可追溯

每一步都要记录：
- `thought`：LLM 的推理摘要（不是完整思维链）
- `action`：调用了哪个工具
- `action_input`：工具的输入参数
- `result`：工具的返回结果

示例：
```python
decision_history.append({
    "step": 3,
    "thought": "当前已有市场环境和技术面结果，但缺少基本面判断。",
    "action": "analyze_stock_fundamentals",
    "action_input": {"stock_code": "000001", "strategy_profile": "value"},
    "result": {"tool": "analyze_stock_fundamentals", "status": "success", ...}
})
```

### 3. 工具统一输出格式

**统一输出格式**（Phase 2 更新）：
```python
{
    "tool": str,                # 工具名称
    "status": str,              # "success" | "error" | "partial"
    "result": dict,             # 核心结果数据
    "summary": str,             # 一句话摘要（供 LLM 阅读）
    "signals": list[str],       # 关键信号列表（如 ["golden_cross", "volume_surge"]）
    "data_refs": dict,          # 数据引用路径（如 {"cache_path": "...", "raw_data_path": "..."}）
    "error": str | None,        # 错误信息（status="error" 时）
    "created_at": str           # 执行时间（ISO 8601）
}
```

**字段说明**：
- `result`: 工具的核心输出，供其他工具使用（如 trade_plan_tool 需要 technicals_tool 的 result）
- `summary`: 一句话摘要，供 LLM 阅读和推理（如"技术面偏多，MA 金叉，成交量放大"）
- `signals`: 离散信号列表，用于触发条件判断（如观察池的失效条件）
- `data_refs`: 数据引用路径，用于审计和调试（指向缓存文件或原始数据）
- `error`: 仅当 status="error" 时有值，描述失败原因

### 4. 包装现有模块，不重复造轮子

❌ **不要**在工具里重新实现业务逻辑：
```python
def analyze_stock_fundamentals(stock_code):
    # 错误：直接调用 AKShare API
    data = ak.stock_financial_analysis_indicator(stock_code)
    # 错误：重新实现评分逻辑
    score = calculate_score(data)
    return score
```

✅ **应该**包装现有模块：
```python
def analyze_stock_fundamentals(stock_code, strategy_profile):
    # 正确：调用 DataFetcher
    fetcher = DataFetcher()
    financial_data = fetcher.get_financial_data(stock_code)
    
    # 正确：调用 JudgmentEngine
    engine = JudgmentEngine()
    result = engine.evaluate_fundamentals(financial_data, strategy_profile)
    
    return result
```

---

## 代码规范

### 1. 文件组织

```
src/
├── agent/          # Agent 核心（Harness）
│   ├── state.py            # AgentState 定义
│   ├── context_builder.py  # 节点实现
│   ├── reasoner.py
│   ├── executor.py
│   ├── quality_gate.py
│   ├── human_review.py
│   ├── harness.py          # LangGraph 主图
│   └── config.py           # 硬限制配置
│
├── tools/          # Agent 可调用的工具
│   ├── market_regime_tool.py
│   ├── fundamentals_tool.py
│   └── ...
│
├── core/           # 核心模块（底层实现）
│   ├── data_fetcher.py
│   ├── judgment_engine.py
│   └── ...
│
├── memory/         # 记忆层
└── ui/             # Streamlit UI
```

### 2. 命名规范

- **节点函数**：`snake_case`，例如 `context_builder()`, `agent_reasoner()`
- **工具函数**：`snake_case`，例如 `analyze_stock_fundamentals()`
- **类名**：`PascalCase`，例如 `DataFetcher`, `JudgmentEngine`
- **配置常量**：`UPPER_SNAKE_CASE`，例如 `MAX_STEPS`, `MUST_REVIEW_TOOLS`

### 3. 类型注解

所有函数必须有类型注解：
```python
from typing import TypedDict, Literal, Optional

def analyze_stock_fundamentals(
    stock_code: str,
    strategy_profile: Literal["trend", "growth", "value"]
) -> dict:
    """基本面分析工具"""
    pass
```

AgentState 必须用 TypedDict：
```python
class AgentState(TypedDict):
    thread_id: str
    run_id: str
    goal: str
    decision_history: list[dict]
    # ...
```

### 4. 错误处理

❌ **不要**让工具抛异常：
```python
def analyze_stock_fundamentals(stock_code):
    data = fetcher.get_financial_data(stock_code)
    # 如果 API 失败，直接抛异常 → Agent 会崩溃
```

✅ **应该**返回错误状态：
```python
def analyze_stock_fundamentals(stock_code):
    try:
        data = fetcher.get_financial_data(stock_code)
        # 正常逻辑
        return {"tool": "...", "status": "success", "data": result}
    except Exception as e:
        # 捕获异常，返回 error 状态
        return {
            "tool": "analyze_stock_fundamentals",
            "status": "error",
            "message": f"基本面分析失败: {str(e)}",
            "data": {}
        }
```

### 5. 日志记录

使用 Python logging 模块：
```python
import logging

logger = logging.getLogger(__name__)

def agent_reasoner(state: AgentState) -> AgentState:
    logger.info(f"AgentReasoner: goal={state['goal']}, step={len(state['decision_history'])}")
    # ...
    logger.debug(f"AgentReasoner: next_action={state['next_action']}")
    return state
```

---

## Agent 开发规范

### 1. 节点实现

每个节点必须：
- 接受 `AgentState` 作为输入
- 返回更新后的 `AgentState`
- 不修改输入 state（返回新的 dict）

示例：
```python
def context_builder(state: AgentState) -> AgentState:
    """整理上下文"""
    
    # 提取关键信息
    context = {
        "goal": state["goal"],
        "completed_steps": len(state["decision_history"]),
        "available_observations": list(state["observations"].keys())
    }
    
    # 返回新的 state（不修改原 state）
    return {**state, "_context": context}
```

### 2. 工具实现

每个工具必须：
- 独立函数，不依赖全局状态
- 包装底层模块，不重复实现业务逻辑
- 返回统一格式
- 错误处理不抛异常

示例：
```python
from src.core.data_fetcher import DataFetcher
from src.core.judgment_engine import JudgmentEngine
from datetime import datetime

def analyze_stock_fundamentals(stock_code: str, strategy_profile: str) -> dict:
    """基本面分析工具"""
    
    try:
        # 1. 拉取数据
        fetcher = DataFetcher()
        financial_data = fetcher.get_financial_data(stock_code)
        
        # 2. 调用判断引擎
        engine = JudgmentEngine()
        result = engine.evaluate_fundamentals(financial_data, strategy_profile)
        
        # 3. 返回统一格式
        return {
            "tool": "analyze_stock_fundamentals",
            "status": "success",
            "message": "基本面分析完成",
            "data": result,
            "data_ref": f"cache/{stock_code}_financial_{datetime.now().strftime('%Y%m%d')}.json",
            "timestamp": datetime.now().isoformat()
        }
    
    except Exception as e:
        return {
            "tool": "analyze_stock_fundamentals",
            "status": "error",
            "message": f"基本面分析失败: {str(e)}",
            "data": {},
            "data_ref": None,
            "timestamp": datetime.now().isoformat()
        }
```

### 3. 硬限制配置

所有限制定义在 `src/agent/config.py`：
```python
# 最大步数限制
MAX_STEPS = 8

# 每个工具最多调用次数
MAX_TOOL_CALLS_PER_TOOL = 2

# 必须人工确认的工具
MUST_REVIEW_TOOLS = [
    "add_to_watchlist",
    "suggest_framework_update"
]
```

❌ **不要**硬编码在代码里：
```python
if len(state["decision_history"]) >= 8:  # 错误：魔法数字
    pass
```

✅ **应该**引用配置：
```python
from src.agent.config import MAX_STEPS

if len(state["decision_history"]) >= MAX_STEPS:
    pass
```

---

## 测试规范

### 1. 单元测试

每个模块都要有单元测试：
```
tests/
├── agent/
│   ├── test_context_builder.py
│   ├── test_reasoner.py
│   └── test_quality_gate.py
├── tools/
│   ├── test_fundamentals_tool.py
│   └── test_backtest_tool.py
└── core/
    ├── test_data_fetcher.py
    └── test_judgment_engine.py
```

### 2. 测试工具时 Mock 底层模块

❌ **不要**在测试中调用真实 API：
```python
def test_analyze_fundamentals():
    result = analyze_stock_fundamentals("000001", "value")
    # 错误：会真的调用 AKShare API
```

✅ **应该** Mock 底层模块：
```python
from unittest.mock import patch

def test_analyze_fundamentals():
    with patch('src.core.data_fetcher.DataFetcher.get_financial_data') as mock_fetch:
        mock_fetch.return_value = {"pe": 12.5, "pb": 1.8}
        result = analyze_stock_fundamentals("000001", "value")
        assert result["status"] == "success"
```

### 3. 测试 Agent 循环时硬编码工具返回

```python
def test_agent_harness():
    # Mock 所有工具
    with patch('src.tools.fundamentals_tool.analyze_stock_fundamentals') as mock_tool:
        mock_tool.return_value = {"tool": "...", "status": "success", "data": {...}}
        
        state = run_agent(goal="分析平安银行")
        
        # 验证决策链
        assert len(state["decision_history"]) > 0
        assert state["status"] == "completed"
```

---

## Git 提交规范

### 1. Commit Message 格式

```
<type>(<scope>): <subject>

<body>
```

**类型**：
- `feat`: 新功能
- `fix`: 修复 bug
- `refactor`: 重构（不改变功能）
- `docs`: 文档更新
- `test`: 测试相关
- `chore`: 构建/配置相关

**示例**：
```
feat(agent): 实现 AgentReasoner 节点

- 调用 LangChain Agent 推理下一步行动
- 记录 thought_summary 到 decision_history
- 处理 is_goal_complete 逻辑
```

### 2. 分支管理

- `main`: 稳定版本
- `dev`: 开发分支
- `feature/*`: 功能分支
- `fix/*`: 修复分支

---

## 性能优化

### 1. 缓存策略

- **数据缓存**：拉取的行情/财务数据缓存 1 小时
- **内存缓存**：同一 session 内重复调用直接返回
- **文件缓存**：Parquet 格式存储历史数据

### 2. 避免重复拉取

❌ **不要**每次都拉全量数据：
```python
def get_stock_history(stock_code):
    return ak.stock_zh_a_hist(stock_code, period="daily", adjust="qfq")
    # 错误：每次都拉全量数据
```

✅ **应该**增量更新：
```python
def get_stock_history(stock_code, days=365):
    # 先检查缓存
    if cache.exists(cache_key):
        cached_data = cache.get(cache_key)
        # 只拉取增量数据
        return update_incremental(cached_data, days)
    # 缓存未命中，拉取全量
    return fetch_full_data(stock_code, days)
```

---

## 安全规范

### 1. API Keys 管理

❌ **不要**硬编码 API keys：
```python
OPENAI_API_KEY = "sk-xxx..."  # 错误
```

✅ **应该**用环境变量：
```python
import os
from dotenv import load_dotenv

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
```

### 2. 人工确认点

关键决策必须人工确认：
- 加入观察池
- 修改判断框架
- 调整策略权重

在 `src/agent/config.py` 中定义：
```python
MUST_REVIEW_TOOLS = [
    "add_to_watchlist",
    "suggest_framework_update"
]
```

---

## FAQ

### Q1: 为什么不用 LangChain Agent Executor 的默认循环？

A: 我们需要自定义循环逻辑（QualityGate、人工确认点、checkpoint），LangChain 的默认循环不够灵活。

### Q2: 为什么工具要返回统一格式，而不是直接返回数据？

A: 统一格式让 Agent 更容易解析结果，也方便记录到 decision_history 和调试。

### Q3: 为什么第一版不做 RAG？

A: MVP 优先验证 Agent 架构可行性，RAG 是第二阶段的增强功能。

### Q4: 为什么要硬限制最大步数？

A: 防止 Agent 无限循环、控制成本、保证用户体验。第一版 Agent 能力有限，不应过度自主。

---

## 参考资料

- **设计文档**: [docs/specs/2026-06-08-traderlens-agent-design.md](docs/specs/2026-06-08-traderlens-agent-design.md)
- **LangGraph 文档**: https://langchain-ai.github.io/langgraph/
- **LangChain 文档**: https://python.langchain.com/docs/
- **Streamlit 文档**: https://docs.streamlit.io/

---

**最后更新**: 2026-06-08
