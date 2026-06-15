"""最简 Demo - 验证 Agent Harness 端到端运行

Phase 1 验收标准：
- LangGraph 主图可以运行
- Agent 循环 3-5 步后完成
- decision_history 正确记录每一步
- 人工确认点可以中断和恢复
- 硬限制生效
"""

import sys
import uuid
import logging
from pathlib import Path

# 添加 src 目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent / "src"))

from agent.harness import create_agent_graph
from agent.state import AgentState

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def run_demo():
    """运行最简 demo"""
    
    print("\n" + "="*60)
    print("TraderLens Agent Demo - Phase 1")
    print("="*60 + "\n")
    
    # 创建 Agent 图
    graph = create_agent_graph()
    
    # 初始化状态
    thread_id = str(uuid.uuid4())
    initial_state: AgentState = {
        "thread_id": thread_id,
        "run_id": str(uuid.uuid4()),
        "goal": "分析平安银行能不能进观察池",
        "stock_code": "000001",
        "strategy_profile": "value",
        "decision_history": [],
        "observations": {},
        "next_action": None,
        "next_action_input": None,
        "thought_summary": None,
        "is_goal_complete": False,
        "quality_check_passed": True,
        "quality_check_message": None,
        "human_approval_required": False,
        "human_approved": None,
        "status": "running",
        "error_message": None,
        "_context": None,
        "_tool_call_counts": {}
    }
    
    # 配置（用于 checkpoint）
    config = {
        "configurable": {
            "thread_id": thread_id
        }
    }
    
    print(f"Thread ID: {thread_id}")
    print(f"Goal: {initial_state['goal']}")
    print(f"Stock Code: {initial_state['stock_code']}")
    print(f"Strategy: {initial_state['strategy_profile']}\n")
    
    # === 首次运行（会在 human_review 处中断） ===
    print("="*60)
    print("Starting Agent Execution...")
    print("="*60 + "\n")
    
    try:
        for event in graph.stream(initial_state, config, stream_mode="values"):
            # 打印每个节点的输出
            step = len(event.get("decision_history", []))
            status = event.get("status", "running")
            
            print(f"[Step {step}] Status: {status}")
            
            # 如果有新的决策记录，打印
            if event.get("decision_history"):
                last_decision = event["decision_history"][-1]
                print(f"  Thought: {last_decision.get('thought', 'N/A')}")
                print(f"  Action: {last_decision.get('action', 'N/A')}")
                print(f"  Result: {last_decision.get('result', {}).get('status', 'N/A')}")
            
            # 检查是否触发了 interrupt
            if "__interrupt__" in event:
                interrupt_data = event["__interrupt__"][0].value
                print("\n" + "="*60)
                print("🛑 INTERRUPT: Human approval required")
                print("="*60)
                print(f"Action: {interrupt_data.get('action')}")
                print(f"Thought: {interrupt_data.get('thought')}")
                print(f"Question: {interrupt_data.get('question')}")
                print("="*60 + "\n")
                break
            
            print()
    
    except Exception as e:
        logger.error(f"Error during execution: {e}", exc_info=True)
        return
    
    # === 模拟用户批准 ===
    print("\n" + "="*60)
    print("User Action: Approving the action...")
    print("="*60 + "\n")
    
    # 使用 Command 恢复执行
    from langgraph.types import Command
    
    try:
        for event in graph.stream(
            Command(resume={"approved": True}),
            config,
            stream_mode="values"
        ):
            step = len(event.get("decision_history", []))
            status = event.get("status", "running")
            
            print(f"[Step {step}] Status: {status}")
            
            if event.get("decision_history"):
                last_decision = event["decision_history"][-1]
                print(f"  Thought: {last_decision.get('thought', 'N/A')}")
                print(f"  Action: {last_decision.get('action', 'N/A')}")
                print(f"  Result: {last_decision.get('result', {}).get('status', 'N/A')}")
            
            print()
    
    except Exception as e:
        logger.error(f"Error during resume: {e}", exc_info=True)
        return
    
    # === 打印最终结果 ===
    print("\n" + "="*60)
    print("Final Results")
    print("="*60 + "\n")
    
    # 获取最终状态
    final_state = graph.get_state(config)
    state_values = final_state.values
    
    print(f"Status: {state_values.get('status')}")
    print(f"Goal Complete: {state_values.get('is_goal_complete')}")
    print(f"Total Steps: {len(state_values.get('decision_history', []))}")
    print(f"\nDecision History:")
    
    for i, decision in enumerate(state_values.get("decision_history", []), 1):
        print(f"\n  Step {i}:")
        print(f"    Thought: {decision.get('thought')}")
        print(f"    Action: {decision.get('action')}")
        print(f"    Status: {decision.get('result', {}).get('status')}")
    
    print("\n" + "="*60)
    print("Demo Complete!")
    print("="*60 + "\n")


if __name__ == "__main__":
    run_demo()
