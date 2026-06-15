"""AgentState 定义

TraderLens Agent 的状态定义，使用 TypedDict 确保类型安全。
"""

from typing import TypedDict, Literal, Optional


class AgentState(TypedDict):
    """Agent 状态定义
    
    每个节点接收 AgentState 作为输入，返回 partial update。
    LangGraph 会自动 merge 这些 updates。
    """
    
    # === 基础信息 ===
    thread_id: str
    """会话 ID，用于 checkpoint 恢复"""
    
    run_id: str
    """本次执行的唯一 ID"""
    
    goal: str
    """用户的投研目标（自然语言）"""
    
    stock_code: Optional[str]
    """股票代码（可选，如果用户指定）"""
    
    strategy_profile: Literal["trend", "growth", "value"]
    """策略风格"""
    
    # === 决策链 ===
    decision_history: list[dict]
    """决策历史，每一步记录：
    {
        "step": int,
        "thought": str,          # LLM 推理摘要
        "action": str,           # 工具名称
        "action_input": dict,    # 工具输入参数
        "result": dict,          # 工具返回结果（统一格式）
        "timestamp": str
    }
    """
    
    # === 观察结果（工具返回的数据） ===
    observations: dict[str, dict]
    """工具返回的数据，key 为工具名称，value 为 tool 返回的 data 字段
    
    例如：
    {
        "market_regime_tool": {"regime": "bull", "volatility": "low", ...},
        "fundamentals_tool": {"pe": 12.5, "roe": 0.15, ...}
    }
    """
    
    # === 当前决策 ===
    next_action: Optional[str]
    """AgentReasoner 决定的下一步行动（工具名称或 'complete'）"""
    
    next_action_input: Optional[dict]
    """下一步行动的输入参数"""
    
    thought_summary: Optional[str]
    """AgentReasoner 的推理摘要"""
    
    is_goal_complete: bool
    """目标是否已完成"""
    
    # === 质量门控 ===
    quality_check_passed: bool
    """质量检查是否通过"""
    
    quality_check_message: Optional[str]
    """质量检查失败原因"""
    
    # === 人工确认 ===
    human_approval_required: bool
    """是否需要人工确认"""
    
    human_approved: Optional[bool]
    """人工确认结果（None 表示等待确认）"""
    
    # === 状态标记 ===
    status: Literal["running", "waiting_human", "completed", "failed"]
    """执行状态"""
    
    error_message: Optional[str]
    """错误信息"""
    
    # === 内部上下文（节点间传递） ===
    _context: Optional[dict]
    """上下文信息（由 ContextBuilder 生成，供其他节点使用）"""
    
    _tool_call_counts: dict[str, int]
    """工具调用计数，用于检测重复调用"""
