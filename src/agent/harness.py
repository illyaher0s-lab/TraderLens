"""Agent Harness - LangGraph 主图

将 5 个节点连接成循环图，实现 Goal-driven ReAct Agent。
"""

import logging
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from src.agent.state import AgentState
from src.agent.context_builder import context_builder
from src.agent.reasoner import agent_reasoner
from src.agent.quality_gate import quality_gate
from src.agent.executor import tool_executor
from src.agent.human_review import human_review

logger = logging.getLogger(__name__)


def create_agent_graph():
    """创建 LangGraph Agent 图
    
    节点流程：
    START → ContextBuilder → AgentReasoner → QualityGate → HumanReview → ToolExecutor → (loop back or END)
    
    Returns:
        编译后的 LangGraph
    """
    # 创建 StateGraph
    workflow = StateGraph(AgentState)
    
    # 添加节点
    workflow.add_node("context_builder", context_builder)
    workflow.add_node("agent_reasoner", agent_reasoner)
    workflow.add_node("quality_gate", quality_gate)
    workflow.add_node("human_review", human_review)
    workflow.add_node("tool_executor", tool_executor)
    
    # === 添加边 ===
    
    # 入口：START → context_builder
    workflow.set_entry_point("context_builder")
    
    # context_builder → agent_reasoner
    workflow.add_edge("context_builder", "agent_reasoner")
    
    # agent_reasoner → quality_gate
    workflow.add_edge("agent_reasoner", "quality_gate")
    
    # quality_gate → 条件边
    workflow.add_conditional_edges(
        "quality_gate",
        _should_continue_after_quality_gate,
        {
            "human_review": "human_review",
            "end": END
        }
    )
    
    # human_review → 条件边
    workflow.add_conditional_edges(
        "human_review",
        _should_continue_after_human_review,
        {
            "tool_executor": "tool_executor",
            "end": END
        }
    )
    
    # tool_executor → 条件边（循环或结束）
    workflow.add_conditional_edges(
        "tool_executor",
        _should_continue_after_execution,
        {
            "context_builder": "context_builder",  # 循环回去
            "end": END
        }
    )
    
    # 编译图（必须启用 checkpointer 才能使用 interrupt）
    checkpointer = MemorySaver()
    graph = workflow.compile(checkpointer=checkpointer)
    
    logger.info("Agent graph compiled successfully")
    
    return graph


def _should_continue_after_quality_gate(state: AgentState) -> str:
    """QualityGate 之后的路由逻辑
    
    如果质量检查失败 → END
    否则 → human_review
    """
    if not state.get("quality_check_passed", False):
        logger.info("Quality check failed, ending")
        return "end"
    
    return "human_review"


def _should_continue_after_human_review(state: AgentState) -> str:
    """HumanReview 之后的路由逻辑
    
    如果用户拒绝 → END
    否则 → tool_executor
    """
    if not state.get("human_approved", True):
        logger.info("Human rejected, ending")
        return "end"
    
    return "tool_executor"


def _should_continue_after_execution(state: AgentState) -> str:
    """ToolExecutor 之后的路由逻辑
    
    如果目标完成 → END
    如果执行失败 → END
    否则 → context_builder（循环）
    """
    if state.get("is_goal_complete", False):
        logger.info("Goal complete, ending")
        return "end"
    
    if state.get("status") == "failed":
        logger.info("Execution failed, ending")
        return "end"
    
    logger.info("Continuing to next step")
    return "context_builder"


def run_agent(initial_state: AgentState) -> AgentState:
    """运行 Agent 直到完成
    
    Args:
        initial_state: 初始 AgentState
    
    Returns:
        最终 AgentState
    """
    logger.info(f"Starting agent run: {initial_state.get('run_id')}")
    
    # 创建图
    graph = create_agent_graph()
    
    # 配置
    config = {
        "configurable": {
            "thread_id": initial_state.get("thread_id", "default")
        }
    }
    
    # 运行图（同步模式）
    final_state = initial_state
    try:
        for chunk in graph.stream(initial_state, config):
            # chunk 可能是 dict 或 tuple
            if isinstance(chunk, dict):
                # dict 格式: {node_name: state}
                for node_name, node_output in chunk.items():
                    final_state = node_output
                    logger.debug(f"Node '{node_name}' completed")
            elif isinstance(chunk, tuple) and len(chunk) == 2:
                # tuple 格式: (node_name, state)
                node_name, node_output = chunk
                # 如果 node_output 是 dict，才更新 final_state
                if isinstance(node_output, dict):
                    final_state = node_output
                    logger.debug(f"Node '{node_name}' completed")
                else:
                    logger.debug(f"Skipping non-dict output from '{node_name}'")
            else:
                # 其他格式，如果是 dict 就使用
                if isinstance(chunk, dict):
                    final_state = chunk
                logger.debug(f"Chunk type: {type(chunk)}")
        
        # 确保 final_state 是 dict
        if isinstance(final_state, dict):
            logger.info(f"Agent run completed: {final_state.get('status')}")
        else:
            logger.warning(f"Agent run completed with unexpected type: {type(final_state)}")
            # 如果不是 dict，返回初始状态加错误信息
            final_state = {
                **initial_state,
                "status": "failed",
                "error_message": f"Unexpected final state type: {type(final_state)}"
            }
        
    except Exception as e:
        logger.error(f"Agent execution failed: {e}", exc_info=True)
        # 返回错误状态
        final_state = {
            **initial_state,
            "status": "failed",
            "error_message": str(e)
        }
    
    return final_state
