"""HumanReview 节点

人工确认节点，使用 LangGraph 的 interrupt 机制。
"""

import logging
from langgraph.types import interrupt
from src.agent.state import AgentState
from src.agent.config import MUST_REVIEW_TOOLS

logger = logging.getLogger(__name__)


def human_review(state: AgentState) -> AgentState:
    """人工确认节点
    
    当满足以下条件时触发人工确认：
    1. next_action 在 MUST_REVIEW_TOOLS 中
    2. human_approval_required 为 True
    
    使用 LangGraph 的 interrupt() 函数暂停执行，等待用户输入。
    
    Phase 3C-1: 如果设置了 TRADERLENS_AUTO_APPROVE=1，自动批准所有操作（用于测试）
    
    Args:
        state: 当前 Agent 状态
        
    Returns:
        更新后的状态（human_approved）
    """
    import os
    
    next_action = state.get("next_action")
    
    logger.info(f"HumanReview: checking if approval needed for {next_action}")
    
    # 检查是否需要人工确认
    needs_approval = (
        state.get("human_approval_required", False) or
        next_action in MUST_REVIEW_TOOLS
    )
    
    if not needs_approval:
        logger.info("HumanReview: No approval needed, skipping")
        return {**state, "human_approved": True, "human_approval_required": False}
    
    # Phase 3C-1: 自动批准模式（用于测试和开发）
    auto_approve = os.environ.get("TRADERLENS_AUTO_APPROVE") == "1"
    
    if auto_approve:
        logger.info(f"HumanReview: AUTO-APPROVE mode enabled, approving {next_action}")
        
        # 记录自动批准到 decision_history
        new_decision = {
            "step": len(state["decision_history"]) + 1,
            "action": f"human_review_{next_action}",
            "thought": f"自动批准 {next_action}（测试模式）",
            "action_input": {},
            "result": {
                "tool": "human_review",
                "status": "success",
                "summary": "自动批准",
                "created_at": ""
            }
        }
        
        decision_history = state["decision_history"] + [new_decision]
        
        return {
            **state,
            "decision_history": decision_history,
            "human_approved": True,
            "human_approval_required": False
        }
    
    # === 触发 interrupt ===
    logger.info(f"HumanReview: Requesting approval for {next_action}")
    
    # 准备展示给用户的信息
    interrupt_data = {
        "action": next_action,
        "action_input": state.get("next_action_input"),
        "thought": state.get("thought_summary"),
        "step": len(state["decision_history"]) + 1,
        "question": f"是否批准执行 {next_action}？"
    }
    
    # 调用 interrupt() - 会暂停图的执行
    # 返回值是用户通过 Command(resume=...) 传入的值
    approval = interrupt(interrupt_data)
    
    logger.info(f"HumanReview: User response = {approval}")
    
    # 解析用户输入
    if isinstance(approval, dict):
        approved = approval.get("approved", False)
    elif isinstance(approval, bool):
        approved = approval
    elif isinstance(approval, str):
        # 简单字符串解析
        approved = approval.lower() in ["yes", "y", "true", "approve", "批准", "同意"]
    else:
        approved = False
    
    logger.info(f"HumanReview: Approval = {approved}")
    
    # 记录人工审批结果到 decision_history
    new_decision = {
        "step": len(state["decision_history"]) + 1,
        "action": f"human_review_{next_action}",
        "thought": f"用户{'批准' if approved else '拒绝'}了 {next_action}",
        "action_input": {},
        "result": {
            "tool": "human_review",
            "status": "success" if approved else "error",
            "summary": "批准" if approved else "拒绝",
            "created_at": ""
        }
    }
    
    decision_history = state["decision_history"] + [new_decision]
    
    return {
        **state,
        "decision_history": decision_history,
        "human_approved": approved,
        "human_approval_required": False,
        "status": "running" if approved else "failed",
        "error_message": None if approved else "用户拒绝了操作"
    }
