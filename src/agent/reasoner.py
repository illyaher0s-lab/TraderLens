"""AgentReasoner 节点

LLM 推理下一步行动（Phase 1 使用硬编码决策，Phase 2-3 接入 LLM）。
"""

import logging
from src.agent.state import AgentState

logger = logging.getLogger(__name__)


def agent_reasoner(state: AgentState) -> AgentState:
    """Agent 推理器
    
    Phase 1: 硬编码决策路径（验证循环逻辑）
    Phase 2-3: 接入 LLM（让 LLM 根据上下文决定下一步）
    
    决策逻辑（Phase 1 硬编码）：
    1. 如果没有市场环境 → market_regime_tool
    2. 如果没有基本面 → fundamentals_tool
    3. 如果没有技术面 → technicals_tool
    4. 如果都有了 → trade_plan_tool
    5. 如果有交易计划 → watchlist_tool
    6. 如果加入观察池 → complete
    
    Args:
        state: 当前 Agent 状态
        
    Returns:
        更新后的状态（next_action, next_action_input, thought_summary, is_goal_complete）
    """
    logger.info(f"AgentReasoner: goal={state['goal']}, step={len(state['decision_history'])}")
    
    observations = state["observations"]
    stock_code = state.get("stock_code", "000001")  # 默认平安银行
    strategy_profile = state["strategy_profile"]
    
    # === Phase 1: 硬编码决策路径 ===
    
    # 1. 检查市场环境
    if "market_regime_tool" not in observations:
        logger.info("AgentReasoner: No market regime → call market_regime_tool")
        return {
            **state,
            "next_action": "market_regime_tool",
            "next_action_input": {},
            "thought_summary": "需要先了解当前市场环境",
            "is_goal_complete": False
        }
    
    # 2. 检查基本面
    if "fundamentals_tool" not in observations:
        logger.info("AgentReasoner: No fundamentals → call fundamentals_tool")
        return {
            **state,
            "next_action": "fundamentals_tool",
            "next_action_input": {
                "stock_code": stock_code,
                "strategy_profile": strategy_profile
            },
            "thought_summary": f"市场环境已确认，现在分析 {stock_code} 的基本面",
            "is_goal_complete": False
        }
    
    # 3. 检查技术面
    if "technicals_tool" not in observations:
        logger.info("AgentReasoner: No technicals → call technicals_tool")
        return {
            **state,
            "next_action": "technicals_tool",
            "next_action_input": {
                "stock_code": stock_code,
                "strategy_profile": strategy_profile
            },
            "thought_summary": f"基本面已确认，现在分析 {stock_code} 的技术面",
            "is_goal_complete": False
        }
    
    # 4. 生成交易计划
    if "trade_plan_tool" not in observations:
        logger.info("AgentReasoner: No trade plan → call trade_plan_tool")
        return {
            **state,
            "next_action": "trade_plan_tool",
            "next_action_input": {
                "stock_code": stock_code,
                "fundamentals": observations["fundamentals_tool"],
                "technicals": observations["technicals_tool"],
                "strategy_profile": strategy_profile
            },
            "thought_summary": "基本面和技术面都已分析完成，现在生成交易计划",
            "is_goal_complete": False
        }
    
    # 5. 加入观察池
    if "watchlist_tool" not in observations:
        logger.info("AgentReasoner: No watchlist → call watchlist_tool")
        return {
            **state,
            "next_action": "watchlist_tool",
            "next_action_input": {
                "stock_code": stock_code,
                "trade_plan": observations["trade_plan_tool"]
            },
            "thought_summary": "交易计划已生成，准备加入观察池",
            "is_goal_complete": False,
            "human_approval_required": True  # 触发人工确认
        }
    
    # 6. 完成
    logger.info("AgentReasoner: All steps complete → goal complete")
    return {
        **state,
        "next_action": "complete",
        "next_action_input": {},
        "thought_summary": "投研分析完成，股票已加入观察池",
        "is_goal_complete": True
    }
