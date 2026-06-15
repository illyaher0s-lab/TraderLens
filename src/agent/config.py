"""Agent 硬限制配置

所有限制和常量定义在这里，避免魔法数字。
"""

# === 执行限制 ===
MAX_STEPS = 8
"""最大步数限制（防止无限循环）"""

MAX_TOOL_CALLS_PER_TOOL = 2
"""每个工具最多调用次数（防止重复调用）"""

# === 人工确认 ===
MUST_REVIEW_TOOLS = [
    "watchlist_tool",
    "suggest_framework_update"
]
"""必须人工确认的工具列表"""

# === 工具列表 ===
AVAILABLE_TOOLS = [
    "market_regime_tool",
    "sector_strength_tool",
    "fundamentals_tool",
    "technicals_tool",
    "backtest_tool",
    "trade_plan_tool",
    "watchlist_tool",
    "research_memory_tool"
]
"""所有可用工具列表"""

# === LLM 配置 ===
LLM_MODEL = "gpt-4o-mini"
"""LLM 模型名称（用于 AgentReasoner）"""

LLM_TEMPERATURE = 0.0
"""LLM 温度（推理任务使用 0 保证稳定性）"""

# === 日志级别 ===
LOG_LEVEL = "INFO"
"""日志级别（DEBUG/INFO/WARNING/ERROR）"""
