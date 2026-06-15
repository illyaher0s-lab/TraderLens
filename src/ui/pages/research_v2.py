"""投研分析页面 v2 - 支持异步 Agent 和人工确认

Tab 1: Goal-driven ReAct Agent 投研分析界面
"""

import streamlit as st
from datetime import datetime
import sys
import os
import threading
import time

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from src.agent.harness import create_agent_graph
from src.agent.state import AgentState


def render():
    """渲染投研分析页面"""
    
    st.markdown("## 🔍 AI 投研分析")
    st.markdown("输入投资目标，Agent 将自主调用工具完成分析")
    
    # 初始化 session state
    if "agent_running" not in st.session_state:
        st.session_state.agent_running = False
    if "agent_thread" not in st.session_state:
        st.session_state.agent_thread = None
    if "current_state" not in st.session_state:
        st.session_state.current_state = None
    if "interrupt_data" not in st.session_state:
        st.session_state.interrupt_data = None
    if "graph" not in st.session_state:
        st.session_state.graph = None
    if "config" not in st.session_state:
        st.session_state.config = None
    
    # 输入区域
    with st.container():
        col1, col2 = st.columns([3, 1])
        
        with col1:
            goal = st.text_area(
                "投资目标",
                placeholder="例如：分析平安银行能不能进观察池",
                height=100,
                key="goal_input",
                disabled=st.session_state.agent_running
            )
        
        with col2:
            stock_code = st.text_input(
                "股票代码",
                placeholder="000001",
                key="stock_code_input",
                disabled=st.session_state.agent_running
            )
            
            strategy_profile = st.selectbox(
                "策略类型",
                options=["trend", "growth", "value"],
                format_func=lambda x: {
                    "trend": "趋势策略",
                    "growth": "成长策略", 
                    "value": "价值策略"
                }[x],
                key="strategy_profile_input",
                disabled=st.session_state.agent_running
            )
    
    # 启动/停止按钮
    col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 8])
    
    with col_btn1:
        if not st.session_state.agent_running:
            start_button = st.button(
                "🚀 启动分析",
                type="primary",
                use_container_width=True,
                disabled=not goal or not stock_code
            )
        else:
            start_button = False
            st.button(
                "⏸️ 运行中...",
                type="primary",
                use_container_width=True,
                disabled=True
            )
    
    with col_btn2:
        if st.button("🗑️ 清空", use_container_width=True, disabled=st.session_state.agent_running):
            st.session_state.clear()
            st.rerun()
    
    # 分割线
    st.markdown("---")
    
    # 启动 Agent
    if start_button:
        start_agent_analysis(goal, stock_code, strategy_profile)
        st.rerun()
    
    # 显示人工确认界面
    if st.session_state.interrupt_data:
        display_human_review()
    
    # 显示实时进度
    if st.session_state.agent_running:
        display_progress()
    
    # 显示最终结果（如果有）
    if st.session_state.current_state and not st.session_state.agent_running:
        display_analysis_result(st.session_state.current_state)


def start_agent_analysis(goal: str, stock_code: str, strategy_profile: str):
    """启动 Agent 分析（异步）"""
    
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
        "_tool_call_counts": {}
    }
    
    # 设置环境变量（Mock 模式）
    os.environ["TRADERLENS_DATA_MODE"] = "mock"
    
    # 创建图和配置
    graph = create_agent_graph()
    config = {
        "configurable": {
            "thread_id": initial_state["thread_id"]
        }
    }
    
    # 保存到 session state
    st.session_state.graph = graph
    st.session_state.config = config
    st.session_state.current_state = initial_state
    st.session_state.agent_running = True
    
    # 启动后台线程运行 Agent
    thread = threading.Thread(target=run_agent_async, args=(graph, initial_state, config))
    thread.daemon = True
    thread.start()
    
    st.session_state.agent_thread = thread


def run_agent_async(graph, initial_state, config):
    """异步运行 Agent"""
    try:
        # 使用 stream 模式，逐步处理
        for event in graph.stream(initial_state, config, stream_mode="values"):
            # 更新当前状态
            st.session_state.current_state = event
            
            # 检查是否有 interrupt
            # （实际上 interrupt 会抛出 GraphInterrupt 异常）
            time.sleep(0.1)  # 避免过快更新
        
        # 执行完成
        st.session_state.agent_running = False
    
    except Exception as e:
        # 检查是否是 interrupt
        if "interrupt" in str(type(e)).lower():
            # 这是人工确认中断，提取 interrupt 数据
            st.session_state.interrupt_data = getattr(e, 'interrupts', [{}])[0] if hasattr(e, 'interrupts') else {}
            # Agent 仍在运行，等待用户确认
        else:
            # 其他错误
            st.session_state.agent_running = False
            st.session_state.current_state = {
                **st.session_state.current_state,
                "status": "failed",
                "error_message": str(e)
            }


def display_human_review():
    """显示人工确认界面"""
    interrupt_data = st.session_state.interrupt_data
    
    st.markdown("### 🤚 人工确认")
    
    # 显示待确认的操作
    st.info(f"**步骤 {interrupt_data.get('step', 'N/A')}**: Agent 请求执行 `{interrupt_data.get('action', 'unknown')}`")
    
    # 显示思考过程
    if interrupt_data.get("thought"):
        st.markdown(f"**💭 思考**: {interrupt_data['thought']}")
    
    # 显示操作参数
    if interrupt_data.get("action_input"):
        with st.expander("查看操作参数"):
            st.json(interrupt_data["action_input"])
    
    # 确认按钮
    col1, col2, col3 = st.columns([1, 1, 8])
    
    with col1:
        if st.button("✅ 批准", type="primary", use_container_width=True):
            resume_agent(approved=True)
            st.rerun()
    
    with col2:
        if st.button("❌ 拒绝", use_container_width=True):
            resume_agent(approved=False)
            st.rerun()


def resume_agent(approved: bool):
    """恢复 Agent 执行"""
    # 使用 LangGraph 的 Command API 恢复执行
    # 这里需要调用 graph.invoke() 或 graph.stream() 并传入 resume 参数
    
    # 简化版本：重新创建线程继续执行
    graph = st.session_state.graph
    config = st.session_state.config
    current_state = st.session_state.current_state
    
    # 更新 state 的 human_approved
    current_state["human_approved"] = approved
    current_state["human_approval_required"] = False
    
    # 清除 interrupt 数据
    st.session_state.interrupt_data = None
    
    # 继续执行
    thread = threading.Thread(target=run_agent_async, args=(graph, current_state, config))
    thread.daemon = True
    thread.start()
    
    st.session_state.agent_thread = thread


def display_progress():
    """显示实时进度"""
    st.markdown("### 🤖 Agent 运行中...")
    
    current_state = st.session_state.current_state
    
    if not current_state:
        st.spinner("正在初始化...")
        return
    
    # 显示当前步数
    step_count = len(current_state.get("decision_history", []))
    st.progress(min(step_count / 10, 1.0), text=f"已执行 {step_count} 步")
    
    # 显示最新决策
    if current_state.get("decision_history"):
        latest = current_state["decision_history"][-1]
        st.markdown(f"**最新步骤**: {latest.get('action', 'N/A')}")
        st.markdown(f"**思考**: {latest.get('thought', 'N/A')}")


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
        st.markdown(f"**执行步数**: `{len(state['decision_history'])} 步`")
    
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
                
                # Signals
                if result.get("signals"):
                    signals_html = " ".join([
                        f'<span class="badge">{signal}</span>' 
                        for signal in result["signals"]
                    ])
                    st.markdown(f"**🏷️ 信号**: {signals_html}", unsafe_allow_html=True)
                
                # Result details (collapsible)
                if result.get("result"):
                    with st.expander("查看详细结果"):
                        st.json(result["result"])
    
    # 最终观察结果
    st.markdown("---")
    st.markdown("### 🎯 最终分析")
    
    observations = state.get("observations", {})
    
    if not observations:
        st.warning("无观察结果")
        return
    
    # 市场环境
    if "market_regime_tool" in observations:
        market = observations["market_regime_tool"]
        st.markdown("#### 📈 市场环境")
        st.markdown(market.get("summary", "N/A"))
    
    # 技术面
    if "technicals_tool" in observations:
        tech = observations["technicals_tool"]
        st.markdown("#### 📊 技术面分析")
        st.markdown(tech.get("summary", "N/A"))
    
    # 板块强度
    if "sector_strength_tool" in observations:
        sector = observations["sector_strength_tool"]
        st.markdown("#### 🏢 板块强度")
        st.markdown(sector.get("summary", "N/A"))
    
    # 基本面
    if "analyze_stock_fundamentals" in observations:
        fund = observations["analyze_stock_fundamentals"]
        st.markdown("#### 💰 基本面分析")
        st.markdown(fund.get("summary", "N/A"))
    
    # 回测结果
    if "backtest_tool" in observations:
        backtest = observations["backtest_tool"]
        st.markdown("#### 🔄 回测结果")
        st.markdown(backtest.get("summary", "N/A"))
    
    # 交易计划
    if "trade_plan_tool" in observations:
        plan = observations["trade_plan_tool"]
        st.markdown("#### 📋 交易计划")
        st.markdown(plan.get("summary", "N/A"))
        
        # 详细计划
        if plan.get("result"):
            plan_detail = plan["result"]
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("建议操作", plan_detail.get("action", "N/A"))
            
            with col2:
                entry_price = plan_detail.get("entry_price")
                if entry_price:
                    st.metric("入场价格", f"¥{entry_price:.2f}")
            
            with col3:
                stop_loss = plan_detail.get("stop_loss")
                if stop_loss:
                    st.metric("止损价格", f"¥{stop_loss:.2f}")
    
    # 观察池
    if "watchlist_tool" in observations:
        watchlist = observations["watchlist_tool"]
        st.markdown("#### ⭐ 观察池")
        
        if watchlist.get("status") == "success":
            st.success(watchlist.get("summary", "已加入观察池"))
        else:
            st.warning(watchlist.get("summary", "未加入观察池"))
