"""QualityGate 节点

6 个安全检查，确保 Agent 不会进入异常状态。
"""

import logging
from src.agent.state import AgentState
from src.agent.config import MAX_STEPS, MAX_TOOL_CALLS_PER_TOOL, AVAILABLE_TOOLS, MUST_REVIEW_TOOLS

logger = logging.getLogger(__name__)


def quality_gate(state: AgentState) -> AgentState:
    """质量门控
    
    执行 6 个安全检查：
    1. 最大步数限制
    2. 工具重复调用检测
    3. 无效工具检测
    4. 必要参数缺失检测
    5. 状态一致性检查
    6. 循环检测（连续两步相同 action）
    
    Args:
        state: 当前 Agent 状态
        
    Returns:
        更新后的状态（quality_check_passed, quality_check_message）
    """
    logger.info(f"QualityGate: step={len(state['decision_history'])}, next_action={state.get('next_action')}")
    
    # 如果目标已完成，跳过检查
    if state.get("is_goal_complete"):
        logger.info("QualityGate: Goal complete, skipping checks")
        return {**state, "quality_check_passed": True}
    
    # === 检查 1: 最大步数限制 ===
    if len(state["decision_history"]) >= MAX_STEPS:
        logger.warning(f"QualityGate: Max steps reached ({MAX_STEPS})")
        return {
            **state,
            "quality_check_passed": False,
            "quality_check_message": f"已达到最大步数限制 ({MAX_STEPS} 步)",
            "status": "failed"
        }
    
    next_action = state.get("next_action")
    
    # 如果没有 next_action，说明是初始状态或已完成
    if not next_action:
        return {**state, "quality_check_passed": True}
    
    # === 检查 2: 工具重复调用检测 ===
    tool_call_counts = state.get("_tool_call_counts", {})
    if next_action in tool_call_counts:
        if tool_call_counts[next_action] >= MAX_TOOL_CALLS_PER_TOOL:
            logger.warning(f"QualityGate: Tool {next_action} called too many times ({tool_call_counts[next_action]})")
            return {
                **state,
                "quality_check_passed": False,
                "quality_check_message": f"工具 {next_action} 已调用 {tool_call_counts[next_action]} 次，超过限制",
                "status": "failed"
            }
    
    # === 检查 3: 无效工具检测 ===
    if next_action not in AVAILABLE_TOOLS and next_action != "complete":
        logger.warning(f"QualityGate: Invalid tool {next_action}")
        return {
            **state,
            "quality_check_passed": False,
            "quality_check_message": f"无效工具: {next_action}",
            "status": "failed"
        }
    
    # === 检查 4: 必要参数缺失检测 ===
    next_action_input = state.get("next_action_input")
    # 注意：空字典 {} 是合法的输入（某些工具不需要参数）
    if next_action != "complete" and next_action_input is None:
        logger.warning(f"QualityGate: Missing action_input for {next_action}")
        return {
            **state,
            "quality_check_passed": False,
            "quality_check_message": f"工具 {next_action} 缺少输入参数",
            "status": "failed"
        }
    
    # === 检查 5: 状态一致性检查 ===
    if state.get("status") == "failed":
        logger.warning("QualityGate: State already marked as failed")
        return {
            **state,
            "quality_check_passed": False,
            "quality_check_message": "状态已标记为失败"
        }
    
    # === 检查 6: 循环检测（连续两步相同 action） ===
    decision_history = state["decision_history"]
    if len(decision_history) >= 2:
        last_action = decision_history[-1]["action"]
        second_last_action = decision_history[-2]["action"]
        if last_action == second_last_action == next_action:
            logger.warning(f"QualityGate: Loop detected - same action 3 times: {next_action}")
            return {
                **state,
                "quality_check_passed": False,
                "quality_check_message": f"检测到循环：连续 3 次调用 {next_action}",
                "status": "failed"
            }
    
    # === 检查 7: 人工确认拦截 ===
    if next_action in MUST_REVIEW_TOOLS:
        logger.info(f"QualityGate: Tool {next_action} requires human approval, setting status=waiting_human")
        return {
            **state,
            "quality_check_passed": True,
            "status": "waiting_human",
            "quality_check_message": f"工具 {next_action} 需要人工确认"
        }
    
    # 所有检查通过
    logger.info("QualityGate: All checks passed")
    return {**state, "quality_check_passed": True, "quality_check_message": None}
