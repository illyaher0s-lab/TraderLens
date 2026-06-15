"""观察池管理页面

Tab 2: 显示和管理所有加入观察池的股票
"""

import streamlit as st
from datetime import datetime
import json
import os

# 观察池数据文件
WATCHLIST_FILE = os.path.expanduser("~/.hermes/traderlens/watchlist.json")


def render():
    """渲染观察池管理页面"""
    
    st.markdown("## 📈 观察池")
    st.markdown("管理所有加入观察池的股票")
    
    # 加载观察池数据
    watchlist = load_watchlist()
    
    # 顶部操作栏
    col1, col2, col3 = st.columns([1, 1, 8])
    
    with col1:
        if st.button("🔄 刷新", use_container_width=True):
            st.rerun()
    
    with col2:
        if st.button("🗑️ 清空", use_container_width=True):
            if st.session_state.get("confirm_clear"):
                clear_watchlist()
                st.session_state.confirm_clear = False
                st.success("观察池已清空")
                st.rerun()
            else:
                st.session_state.confirm_clear = True
                st.warning("再次点击确认清空")
    
    st.markdown("---")
    
    # 显示统计信息
    if watchlist:
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("总数", len(watchlist))
        
        with col2:
            active_count = sum(1 for item in watchlist if item.get("status") == "active")
            st.metric("活跃", active_count)
        
        with col3:
            removed_count = sum(1 for item in watchlist if item.get("status") == "removed")
            st.metric("已移除", removed_count)
    
    st.markdown("---")
    
    # 显示观察池列表
    if not watchlist:
        st.info("观察池为空，还没有加入任何股票")
        return
    
    # 过滤器
    filter_status = st.selectbox(
        "状态筛选",
        options=["all", "active", "removed"],
        format_func=lambda x: {"all": "全部", "active": "活跃", "removed": "已移除"}[x],
        key="filter_status"
    )
    
    # 过滤数据
    filtered_list = watchlist
    if filter_status != "all":
        filtered_list = [item for item in watchlist if item.get("status") == filter_status]
    
    # 显示列表
    st.markdown(f"### 观察池列表 ({len(filtered_list)} 条)")
    
    for i, item in enumerate(filtered_list):
        render_watchlist_item(item, i)


def render_watchlist_item(item: dict, index: int):
    """渲染单个观察池项目"""
    
    with st.expander(
        f"**{item['stock_code']}** - {item.get('stock_name', 'N/A')} "
        f"({'✅ 活跃' if item.get('status') == 'active' else '❌ 已移除'})",
        expanded=False
    ):
        # 基本信息
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown(f"**股票代码**: `{item['stock_code']}`")
            st.markdown(f"**股票名称**: {item.get('stock_name', 'N/A')}")
        
        with col2:
            st.markdown(f"**策略类型**: `{item.get('strategy_profile', 'N/A')}`")
            st.markdown(f"**加入时间**: {item.get('added_at', 'N/A')}")
        
        with col3:
            st.markdown(f"**状态**: {item.get('status', 'N/A')}")
            if item.get("removed_at"):
                st.markdown(f"**移除时间**: {item.get('removed_at')}")
        
        # 加入理由
        if item.get("reason"):
            st.markdown("**加入理由**:")
            st.info(item["reason"])
        
        # 分析摘要
        if item.get("analysis_summary"):
            st.markdown("**分析摘要**:")
            with st.container():
                summary = item["analysis_summary"]
                
                if summary.get("market"):
                    st.markdown(f"- 📈 市场: {summary['market']}")
                
                if summary.get("technicals"):
                    st.markdown(f"- 📊 技术: {summary['technicals']}")
                
                if summary.get("fundamentals"):
                    st.markdown(f"- 💰 基本面: {summary['fundamentals']}")
        
        # 交易计划
        if item.get("trade_plan"):
            st.markdown("**交易计划**:")
            plan = item["trade_plan"]
            
            col_plan1, col_plan2, col_plan3 = st.columns(3)
            
            with col_plan1:
                st.metric("建议操作", plan.get("action", "N/A"))
            
            with col_plan2:
                entry = plan.get("entry_price")
                if entry:
                    st.metric("入场价格", f"¥{entry:.2f}")
            
            with col_plan3:
                stop_loss = plan.get("stop_loss")
                if stop_loss:
                    st.metric("止损价格", f"¥{stop_loss:.2f}")
        
        # 操作按钮
        st.markdown("---")
        col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 8])
        
        with col_btn1:
            if item.get("status") == "active":
                if st.button("🗑️ 移除", key=f"remove_{index}", use_container_width=True):
                    remove_from_watchlist(item["stock_code"])
                    st.success(f"已移除 {item['stock_code']}")
                    st.rerun()
        
        with col_btn2:
            if item.get("status") == "removed":
                if st.button("♻️ 恢复", key=f"restore_{index}", use_container_width=True):
                    restore_to_watchlist(item["stock_code"])
                    st.success(f"已恢复 {item['stock_code']}")
                    st.rerun()


def load_watchlist() -> list:
    """加载观察池数据"""
    
    if not os.path.exists(WATCHLIST_FILE):
        return []
    
    try:
        with open(WATCHLIST_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get("items", [])
    except Exception as e:
        st.error(f"加载观察池失败: {e}")
        return []


def save_watchlist(items: list):
    """保存观察池数据"""
    
    # 确保目录存在
    os.makedirs(os.path.dirname(WATCHLIST_FILE), exist_ok=True)
    
    data = {
        "items": items,
        "last_updated": datetime.now().isoformat()
    }
    
    try:
        with open(WATCHLIST_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        st.error(f"保存观察池失败: {e}")


def add_to_watchlist(stock_code: str, stock_name: str, reason: str, 
                     strategy_profile: str, analysis_summary: dict = None,
                     trade_plan: dict = None):
    """添加到观察池"""
    
    items = load_watchlist()
    
    # 检查是否已存在
    existing = next((item for item in items if item["stock_code"] == stock_code), None)
    
    if existing:
        # 更新现有项
        existing["status"] = "active"
        existing["reason"] = reason
        existing["strategy_profile"] = strategy_profile
        existing["analysis_summary"] = analysis_summary
        existing["trade_plan"] = trade_plan
        existing["updated_at"] = datetime.now().isoformat()
        existing["removed_at"] = None
    else:
        # 添加新项
        new_item = {
            "stock_code": stock_code,
            "stock_name": stock_name,
            "reason": reason,
            "strategy_profile": strategy_profile,
            "analysis_summary": analysis_summary,
            "trade_plan": trade_plan,
            "status": "active",
            "added_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "removed_at": None
        }
        items.append(new_item)
    
    save_watchlist(items)


def remove_from_watchlist(stock_code: str):
    """从观察池移除（软删除）"""
    
    items = load_watchlist()
    
    for item in items:
        if item["stock_code"] == stock_code:
            item["status"] = "removed"
            item["removed_at"] = datetime.now().isoformat()
            break
    
    save_watchlist(items)


def restore_to_watchlist(stock_code: str):
    """恢复到观察池"""
    
    items = load_watchlist()
    
    for item in items:
        if item["stock_code"] == stock_code:
            item["status"] = "active"
            item["removed_at"] = None
            item["updated_at"] = datetime.now().isoformat()
            break
    
    save_watchlist(items)


def clear_watchlist():
    """清空观察池"""
    save_watchlist([])
