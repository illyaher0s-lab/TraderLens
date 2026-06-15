"""Executor 节点

执行工具调用（Phase 2A: 真实工具 + mock）。
"""

import logging
from datetime import datetime
from src.agent.state import AgentState

logger = logging.getLogger(__name__)


def tool_executor(state: AgentState) -> AgentState:
    """工具执行器
    
    Phase 2A: 调用真实工具（market_regime_tool, technicals_tool, trade_plan_tool）
    其他工具仍使用 mock 数据
    
    Args:
        state: 当前 Agent 状态
        
    Returns:
        更新后的状态（observations, decision_history, _tool_call_counts）
    """
    next_action = state.get("next_action")
    next_action_input = state.get("next_action_input")
    
    logger.info(f"ToolExecutor: executing {next_action} with input {next_action_input}")
    
    # 如果是完成信号，直接返回
    if next_action == "complete":
        logger.info("ToolExecutor: Goal marked as complete")
        return {**state, "is_goal_complete": True, "status": "completed"}
    
    # === Phase 2A: 调用真实工具或 mock ===
    tool_result = _execute_tool(next_action, next_action_input, state)
    
    # 更新 observations（保存完整工具返回，包含 status/summary/signals/data_refs）
    observations = state["observations"].copy()
    observations[next_action] = tool_result
    
    # 更新 tool_call_counts
    tool_call_counts = state.get("_tool_call_counts", {}).copy()
    tool_call_counts[next_action] = tool_call_counts.get(next_action, 0) + 1
    
    # 记录到 decision_history
    decision_history = state["decision_history"].copy()
    decision_history.append({
        "step": len(decision_history) + 1,
        "thought": state.get("thought_summary", ""),
        "action": next_action,
        "action_input": next_action_input,
        "result": tool_result,
        "timestamp": datetime.now().isoformat()
    })
    
    logger.info(f"ToolExecutor: {next_action} returned status={tool_result['status']}")
    
    return {
        **state,
        "observations": observations,
        "decision_history": decision_history,
        "_tool_call_counts": tool_call_counts,
        # 清空下一步行动（等待 Reasoner 重新决策）
        "next_action": None,
        "next_action_input": None,
        "thought_summary": None
    }


def _execute_tool(tool_name: str, tool_input: dict, state: AgentState) -> dict:
    """执行工具（Phase 2A: 真实工具 + mock）
    
    Args:
        tool_name: 工具名称
        tool_input: 工具输入
        state: 当前状态（用于传递 observations）
        
    Returns:
        统一格式的工具返回
    """
    # === Phase 2A: 真实工具 ===
    if tool_name == "market_regime_tool":
        from src.tools.market_regime_tool import market_regime_tool
        return market_regime_tool(
            index_code=tool_input.get("index_code", "000001")
        )
    
    elif tool_name == "technicals_tool":
        from src.tools.technicals_tool import technicals_tool
        return technicals_tool(
            stock_code=tool_input["stock_code"],
            strategy_profile=tool_input.get("strategy_profile", "trend")
        )
    
    elif tool_name == "trade_plan_tool":
        from src.tools.trade_plan_tool import trade_plan_tool
        observations = state["observations"]
        
        # 从完整工具返回中提取 result
        market_regime = observations.get("market_regime_tool", {}).get("result", {})
        technicals = observations.get("technicals_tool", {}).get("result", {})
        
        return trade_plan_tool(
            stock_code=tool_input["stock_code"],
            market_regime=market_regime,
            technicals=technicals,
            strategy_profile=tool_input.get("strategy_profile", "trend")
        )
    
    elif tool_name == "watchlist_tool":
        from src.tools.watchlist_tool import add_to_watchlist
        observations = state["observations"]
        
        # 从完整工具返回中提取 result
        trade_plan = observations.get("trade_plan_tool", {}).get("result", {})
        
        return add_to_watchlist(
            stock_code=tool_input["stock_code"],
            trade_plan=trade_plan,
            strategy_profile=tool_input.get("strategy_profile", "trend"),
            stock_name=tool_input.get("stock_name"),
            source_run_id=state.get("run_id")
        )
    
    elif tool_name == "sector_strength_tool":
        from src.tools.sector_strength_tool import sector_strength_tool
        return sector_strength_tool(
            stock_code=tool_input["stock_code"]
        )
    
    elif tool_name == "analyze_stock_fundamentals":
        from src.tools.fundamentals_tool import analyze_stock_fundamentals
        return analyze_stock_fundamentals(
            stock_code=tool_input["stock_code"],
            strategy_profile=tool_input.get("strategy_profile", "trend"),
            include_industry_context=tool_input.get("include_industry_context", True)
        )
    
    elif tool_name == "search_research_memory":
        from src.tools.research_memory_tool import search_research_memory
        return search_research_memory(
            query=tool_input.get("query", ""),
            limit=tool_input.get("limit", 5)
        )
    
    # === Phase 2A: 仍使用 mock 的工具 ===
    else:
        return _get_mock_result(tool_name, tool_input)


def _get_mock_result(tool_name: str, tool_input: dict) -> dict:
    """生成 mock 工具返回（Phase 2A: 其他工具仍使用）
    
    Args:
        tool_name: 工具名称
        tool_input: 工具输入
        
    Returns:
        统一格式的工具返回
    """
    # 统一返回格式（Phase 2A 更新）
    base_result = {
        "tool": tool_name,
        "status": "success",
        "result": {},
        "summary": f"{tool_name} 执行成功（mock）",
        "signals": [],
        "data_refs": {},
        "error": None,
        "created_at": datetime.now().isoformat()
    }
    
    # 根据工具类型返回不同的 mock 数据
    if tool_name == "backtest_tool":
        # 调用真实的回测工具
        from src.tools.backtest_tool import backtest_tool
        return backtest_tool(
            stock_code=tool_input.get("stock_code"),
            strategy_profile=tool_input.get("strategy_profile", "trend"),
            period=tool_input.get("period", "1y")
        )
    
    elif tool_name == "watchlist_tool":
        base_result["result"] = {
            "added": True,
            "watchlist_id": "default",
            "stock_code": tool_input.get("stock_code", "000001")
        }
        base_result["summary"] = f"已加入观察池: {tool_input.get('stock_code', '000001')}"
        base_result["signals"] = ["added_to_watchlist"]
    
    else:
        base_result["status"] = "error"
        base_result["summary"] = f"未知工具: {tool_name}"
        base_result["error"] = f"Unknown tool: {tool_name}"
    
    return base_result
