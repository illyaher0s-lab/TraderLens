"""投研分析页面 - 真实 Agent 集成

Phase 3C-1: 接入真实 Agent Harness
"""

import streamlit as st
from datetime import datetime
import sys
import os
import logging

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from src.agent.harness import run_agent
from src.agent.state import AgentState
from src.ui.pages.watchlist import add_to_watchlist

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def render():
    """渲染投研分析页面"""
    
    st.markdown("## 🔍 AI 投研分析")
    st.markdown("输入投资目标，Agent 将自主调用工具完成分析")
    
    # 初始化 session state
    if "agent_state" not in st.session_state:
        st.session_state.agent_state = "idle"  # idle / running / completed / error
    if "analysis_result" not in st.session_state:
        st.session_state.analysis_result = None
    
    # 根据状态渲染不同界面
    if st.session_state.agent_state == "idle":
        render_input_form()
    
    elif st.session_state.agent_state == "running":
        render_running_status()
    
    elif st.session_state.agent_state in ["completed", "error"]:
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
            start_agent_analysis(goal, stock_code, strategy_profile)
            st.rerun()


def render_running_status():
    """渲染运行状态"""
    st.markdown("### 🤖 Agent 运行中...")
    st.info("Agent 正在分析，请稍候...")
    
    # 自动刷新（每 2 秒检查一次）
    import time
    time.sleep(2)
    st.rerun()


def render_results():
    """渲染分析结果"""
    
    result = st.session_state.analysis_result
    
    # 顶部按钮
    col1, col2 = st.columns([1, 9])
    with col1:
        if st.button("🔄 新分析", use_container_width=True):
            st.session_state.agent_state = "idle"
            st.session_state.analysis_result = None
            st.rerun()
    
    st.markdown("---")
    
    # 显示结果
    if result:
        display_analysis_result(result)


def start_agent_analysis(goal: str, stock_code: str, strategy_profile: str):
    """启动 Agent 分析（真实版本）"""
    
    logger.info(f"Starting Agent analysis: goal={goal}, stock_code={stock_code}, strategy={strategy_profile}")
    
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
        "human_approved": True,  # 默认批准（Phase 3C-1 先不处理 interrupt）
        "human_approval_required": False,
        "quality_check_passed": True
    }
    
    # 设置环境变量（Mock 模式 + 自动批准）
    os.environ["TRADERLENS_DATA_MODE"] = "mock"
    os.environ["TRADERLENS_AUTO_APPROVE"] = "1"  # Phase 3C-1: 自动批准所有操作
    
    # 更新状态为 running
    st.session_state.agent_state = "running"
    
    try:
        # 调用真实 Agent
        logger.info("Calling run_agent()...")
        final_state = run_agent(initial_state)
        
        logger.info(f"Agent completed: status={final_state.get('status')}")
        
        # 保存结果
        st.session_state.analysis_result = final_state
        st.session_state.agent_state = "completed" if final_state.get("status") != "failed" else "error"
        
        # 如果成功加入观察池，同步到 watchlist
        if "watchlist_tool" in final_state.get("observations", {}):
            watchlist_result = final_state["observations"]["watchlist_tool"]
            
            if watchlist_result.get("status") == "success":
                # 提取分析摘要
                analysis_summary = {
                    "market": final_state.get("observations", {}).get("market_regime_tool", {}).get("summary", "N/A"),
                    "technicals": final_state.get("observations", {}).get("technicals_tool", {}).get("summary", "N/A"),
                    "fundamentals": final_state.get("observations", {}).get("analyze_stock_fundamentals", {}).get("summary", "N/A")
                }
                
                # 提取交易计划
                trade_plan = None
                if "trade_plan_tool" in final_state.get("observations", {}):
                    plan_result = final_state["observations"]["trade_plan_tool"].get("result", {})
                    trade_plan = {
                        "action": plan_result.get("action"),
                        "entry_price": plan_result.get("entry_price"),
                        "stop_loss": plan_result.get("stop_loss"),
                        "take_profit": plan_result.get("take_profit"),
                        "position_size": plan_result.get("position_size")
                    }
                
                # 添加到观察池
                add_to_watchlist(
                    stock_code=stock_code,
                    stock_name=watchlist_result.get("result", {}).get("stock_name", stock_code),
                    reason=watchlist_result.get("result", {}).get("reason", "Agent 分析建议"),
                    strategy_profile=strategy_profile,
                    analysis_summary=analysis_summary,
                    trade_plan=trade_plan
                )
                
                logger.info(f"Added {stock_code} to watchlist")
    
    except Exception as e:
        logger.error(f"Agent execution failed: {e}", exc_info=True)
        
        # 保存错误状态
        st.session_state.analysis_result = {
            "status": "failed",
            "error_message": str(e),
            "decision_history": [],
            "observations": {}
        }
        st.session_state.agent_state = "error"


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
    
    # 错误信息
    if state.get("error_message"):
        st.error(f"错误: {state['error_message']}")
    
    # 决策链
    st.markdown("---")
    st.markdown("### 🔗 决策链")
    
    decision_history = state.get("decision_history", [])
    
    if not decision_history:
        st.warning("无决策记录")
    else:
        for i, decision in enumerate(decision_history, 1):
            with st.expander(f"步骤 {i}: {decision.get('action', 'N/A')}", expanded=(i == len(decision_history))):
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
    observations = state.get("observations", {})
    
    if observations:
        st.markdown("---")
        st.markdown("### 🎯 最终分析")
        
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
