"""投研分析页面

Tab 1: Goal-driven ReAct Agent 投研分析界面
"""

import streamlit as st
from datetime import datetime
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from src.agent.harness import run_agent
from src.agent.state import AgentState


def render():
    """渲染投研分析页面"""
    
    st.markdown("## 🔍 AI 投研分析")
    st.markdown("输入投资目标，Agent 将自主调用工具完成分析")
    
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
    col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 8])
    
    with col_btn1:
        start_button = st.button(
            "🚀 启动分析",
            type="primary",
            use_container_width=True,
            disabled=not goal or not stock_code
        )
    
    with col_btn2:
        if st.button("🗑️ 清空", use_container_width=True):
            st.session_state.clear()
            st.rerun()
    
    # 分割线
    st.markdown("---")
    
    # 启动 Agent
    if start_button:
        run_agent_analysis(goal, stock_code, strategy_profile)
    
    # 显示历史分析结果（如果有）
    if "analysis_result" in st.session_state:
        display_analysis_result(st.session_state.analysis_result)


def run_agent_analysis(goal: str, stock_code: str, strategy_profile: str):
    """运行 Agent 分析"""
    
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
    
    # 显示状态
    st.markdown("### 🤖 Agent 运行中...")
    
    # 创建占位符
    status_placeholder = st.empty()
    decision_placeholder = st.empty()
    
    # 运行 Agent（同步模式）
    try:
        with st.spinner("Agent 正在分析..."):
            # 设置环境变量（Mock 模式）
            os.environ["TRADERLENS_DATA_MODE"] = "mock"
            
            # 运行 Agent
            final_state = run_agent(initial_state)
            
            # 保存到 session state
            st.session_state.analysis_result = final_state
            
            # 显示完成状态
            status_placeholder.success(f"✅ 分析完成！共执行 {len(final_state['decision_history'])} 步")
            
            # 重新渲染以显示结果
            st.rerun()
    
    except Exception as e:
        status_placeholder.error(f"❌ 分析失败: {str(e)}")
        st.exception(e)


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
