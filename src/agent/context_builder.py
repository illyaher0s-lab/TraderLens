"""ContextBuilder 节点

整理上下文信息，为后续节点提供清晰的状态摘要。
"""

import logging
from src.agent.state import AgentState

logger = logging.getLogger(__name__)


def context_builder(state: AgentState) -> AgentState:
    """整理上下文
    
    提取关键信息，生成结构化上下文供其他节点使用。
    
    Args:
        state: 当前 Agent 状态
        
    Returns:
        更新后的状态（包含 _context 字段）
    """
    logger.info(f"ContextBuilder: thread_id={state['thread_id']}, step={len(state['decision_history'])}")
    
    # 提取已完成的步骤
    completed_steps = len(state["decision_history"])
    
    # 提取已有观察结果
    available_observations = list(state["observations"].keys())
    
    # 提取已调用工具的计数
    tool_call_counts = state.get("_tool_call_counts", {})
    
    # 生成上下文
    context = {
        "goal": state["goal"],
        "stock_code": state.get("stock_code"),
        "strategy_profile": state["strategy_profile"],
        "completed_steps": completed_steps,
        "available_observations": available_observations,
        "tool_call_counts": tool_call_counts,
        "is_goal_complete": state.get("is_goal_complete", False)
    }
    
    logger.debug(f"ContextBuilder: context={context}")
    
    # 返回 partial update
    return {**state, "_context": context}
