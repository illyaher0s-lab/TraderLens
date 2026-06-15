"""投研分析页面 v2 - 支持人工确认

通过 session state 实现人工确认流程，避免 LangGraph interrupt 的复杂性
"""

import streamlit as st
from datetime import datetime
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from src.agent.state import AgentState
from src.agent.config import MUST_REVIEW_TOOLS


def render():
    """渲染投研分析页面"""
    
    st.markdown("## 🔍 AI 投研分析")
    st.markdown("输入投资目标，Agent 将自主调用工具完成分析")
    
    # 初始化 session state
    if "analysis_state" not in st.session_state:
        st.session_state.analysis_state = "idle"  # idle / running / waiting_approval / completed
    if "pending_action" not in st.session_state:
        st.session_state.pending_action = None
    if "current_state" not in st.session_state:
        st.session_state.current_state = None
    
    # 根据状态渲染不同界面
    if st.session_state.analysis_state == "idle":
        render_input_form()
    
    elif st.session_state.analysis_state == "waiting_approval":
        render_approval_dialog()
    
    elif st.session_state.analysis_state == "completed":
        render_results()


def render_input_form():
    """渲染输入表单"""
    
    # 输入区域
    with st.container():
        col1, col2 = st.columns([3, 1])
        
        with col1:
            goal = st.text_area(
                "投资目标",
                placeholder="例如：分析平安银行能不能进观察池",
                height=100,
                key="goal_input"
            )
        
        with col2:
            stock_code = st.text_input(
                "股票代码",
                placeholder="000001",
                key="stock_code_input"
            )
            
            strategy_profile = st.selectbox(
                "策略类型",
                options=["trend", "growth", "value"],
                format_func=lambda x: {
                    "trend": "趋势策略",
                    "growth": "成长策略", 
                    "value": "价值策略"
                }[x],
                key="strategy_profile_input"
            )
    
    # 启动按钮
    col_btn1, col_btn2 = st.columns([1, 9])
    
    with col_btn1:
        if st.button(
            "🚀 启动分析",
            type="primary",
            use_container_width=True,
            disabled=not goal or not stock_code
        ):
            start_analysis(goal, stock_code, strategy_profile)
            st.rerun()


def render_approval_dialog():
    """渲染人工确认对话框"""
    
    pending = st.session_state.pending_action
    current = st.session_state.current_state
    
    st.markdown("### 🤚 人工确认")
    
    # 显示当前进度
    step_count = len(current.get("decision_history", []))
    st.info(f"**步骤 {step_count + 1}**: Agent 请求执行 `{pending['action']}`")
    
    # 显示思考过程
    if pending.get("thought"):
        st.markdown(f"**💭 思考**: {pending['thought']}")
    
    # 显示操作参数
    if pending.get("action_input"):
        with st.expander("查看操作参数", expanded=True):
            st.json(pending["action_input"])
    
    # 显示已完成的步骤
    if current.get("decision_history"):
        with st.expander(f"查看已完成的 {step_count} 步"):
            for i, decision in enumerate(current["decision_history"], 1):
                st.markdown(f"**{i}. {decision.get('action', 'N/A')}** - {decision.get('thought', '')[:50]}...")
    
    # 确认按钮
    col1, col2, col3 = st.columns([1, 1, 8])
    
    with col1:
        if st.button("✅ 批准", type="primary", use_container_width=True, key="approve_btn"):
            approve_action(approved=True)
            st.rerun()
    
    with col2:
        if st.button("❌ 拒绝", use_container_width=True, key="reject_btn"):
            approve_action(approved=False)
            st.rerun()
    
    with col3:
        if st.button("🗑️ 取消分析", use_container_width=True, key="cancel_btn"):
            st.session_state.analysis_state = "idle"
            st.session_state.current_state = None
            st.session_state.pending_action = None
            st.rerun()


def render_results():
    """渲染分析结果"""
    
    state = st.session_state.current_state
    
    # 顶部按钮
    col1, col2 = st.columns([1, 9])
    with col1:
        if st.button("🔄 新分析", use_container_width=True):
            st.session_state.analysis_state = "idle"
            st.session_state.current_state = None
            st.rerun()
    
    st.markdown("---")
    
    # 显示结果
    display_analysis_result(state)


def start_analysis(goal: str, stock_code: str, strategy_profile: str):
    """启动分析（简化版：直接执行到需要确认的步骤）"""
    
    # 创建初始 state
    initial_state: AgentState = {
        "thread_id": f"streamlit_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "run_id": f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "goal": goal,
        "stock_code": stock_code,
        "strategy_profile": strategy_profile,
        "observations": {},
        "decision_history": [],
        "next_action": None,
        "next_action_input": None,
        "is_goal_complete": False,
        "status": "running",
        "thought_summary": None,
        "_tool_call_counts": {},
        "human_approved": True,  # 默认批准
        "human_approval_required": False
    }
    
    # 设置环境变量（Mock 模式）
    os.environ["TRADERLENS_DATA_MODE"] = "mock"
    
    # 保存 state
    st.session_state.current_state = initial_state
    st.session_state.analysis_state = "running"
    
    # 执行一步（模拟 - 实际应该调用 Agent）
    # 这里我们先模拟一个需要确认的操作
    simulate_next_step()


def simulate_next_step():
    """模拟执行下一步（临时实现，用于测试 UI）"""
    
    current = st.session_state.current_state
    step_count = len(current.get("decision_history", []))
    
    # 模拟决策
    if step_count == 0:
        # 第一步：市场评估（不需要确认）
        execute_action("market_regime_tool", {"index": "000001"})
        simulate_next_step()  # 继续下一步
    
    elif step_count == 1:
        # 第二步：技术分析（不需要确认）
        execute_action("technicals_tool", {"stock_code": current["stock_code"]})
        simulate_next_step()
    
    elif step_count == 2:
        # 第三步：加入观察池（需要确认）
        request_approval(
            action="watchlist_tool",
            action_input={"stock_code": current["stock_code"], "reason": "技术面良好"},
            thought="基于前两步分析，建议加入观察池"
        )
    
    else:
        # 完成
        st.session_state.analysis_state = "completed"


def request_approval(action: str, action_input: dict, thought: str):
    """请求人工确认"""
    
    st.session_state.pending_action = {
        "action": action,
        "action_input": action_input,
        "thought": thought
    }
    
    st.session_state.analysis_state = "waiting_approval"


def approve_action(approved: bool):
    """批准/拒绝操作"""
    
    pending = st.session_state.pending_action
    current = st.session_state.current_state
    
    if approved:
        # 执行操作
        execute_action(pending["action"], pending["action_input"])
        
        # 清除 pending
        st.session_state.pending_action = None
        st.session_state.analysis_state = "running"
        
        # 继续下一步
        simulate_next_step()
    
    else:
        # 拒绝 - 记录并结束
        decision = {
            "step": len(current["decision_history"]) + 1,
            "action": pending["action"],
            "thought": pending["thought"],
            "action_input": pending["action_input"],
            "result": {
                "status": "rejected",
                "summary": "用户拒绝了该操作"
            }
        }
        
        current["decision_history"].append(decision)
        current["status"] = "failed"
        current["error_message"] = "用户拒绝了操作"
        
        st.session_state.pending_action = None
        st.session_state.analysis_state = "completed"


def execute_action(action: str, action_input: dict):
    """执行工具（模拟）"""
    
    current = st.session_state.current_state
    
    # 模拟工具执行
    result = {
        "tool": action,
        "status": "success",
        "result": {"data": "mock_data"},
        "summary": f"{action} 执行成功",
        "signals": ["测试信号"],
        "created_at": datetime.now().isoformat()
    }
    
    # 记录到 decision_history
    decision = {
        "step": len(current["decision_history"]) + 1,
        "action": action,
        "thought": f"执行 {action}",
        "action_input": action_input,
        "result": result
    }
    
    current["decision_history"].append(decision)
    
    # 保存到 observations
    current["observations"][action] = result


def display_analysis_result(state: AgentState):
    """显示分析结果"""
    
    st.markdown("### 📊 分析结果")
    
    # 基本信息
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown(f"**股票代码**: `{state.get('stock_code', 'N/A')}`")
    
    with col2:
        st.markdown(f"**策略类型**: `{state.get('strategy_profile', 'N/A')}`")
    
    with col3:
        status = state.get("status", "unknown")
        status_emoji = "✅" if status == "completed" else "❌" if status == "failed" else "⏸️"
        st.markdown(f"**状态**: {status_emoji} `{status}`")
    
    # 决策链
    st.markdown("---")
    st.markdown("### 🔗 决策链")
    
    for i, decision in enumerate(state["decision_history"], 1):
        with st.expander(f"步骤 {i}: {decision.get('action', 'N/A')}", expanded=(i == len(state["decision_history"]))):
            # Thought
            if decision.get("thought"):
                st.markdown(f"**💭 思考**: {decision['thought']}")
            
            # Action
            st.markdown(f"**🔧 工具**: `{decision['action']}`")
            
            # Action Input
            if decision.get("action_input"):
                with st.container():
                    st.markdown("**📥 输入参数**:")
                    st.json(decision["action_input"])
            
            # Result
            if decision.get("result"):
                result = decision["result"]
                
                # Status badge
                status = result.get("status", "unknown")
                status_emoji = "✅" if status == "success" else "❌"
                st.markdown(f"**{status_emoji} 状态**: `{status}`")
                
                # Summary
                if result.get("summary"):
                    st.markdown(f"**📝 摘要**: {result['summary']}")
    
    # 最终观察结果
    observations = state.get("observations", {})
    
    if observations:
        st.markdown("---")
        st.markdown("### 🎯 工具输出")
        
        for tool_name, tool_result in observations.items():
            st.markdown(f"#### {tool_name}")
            st.markdown(tool_result.get("summary", "N/A"))
