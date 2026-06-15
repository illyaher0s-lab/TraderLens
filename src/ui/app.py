"""TraderLens UI - 主入口

基于 Vercel 设计系统的投研分析界面
"""

import streamlit as st
from src.ui.vercel_design_system import get_vercel_css

# 页面配置
st.set_page_config(
    page_title="TraderLens - AI 投研分析",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 加载完整的 Vercel 设计系统 CSS
st.markdown(get_vercel_css(), unsafe_allow_html=True)

# 导航栏
def render_header():
    """渲染顶部导航"""
    col1, col2, col3 = st.columns([2, 6, 2])
    
    with col1:
        st.markdown("# 📊 TraderLens")
    
    with col3:
        if st.button("文档", key="docs_btn"):
            st.info("文档功能开发中...")

render_header()

# Tab 导航
tab1, tab2, tab3, tab4, tab5, tab_design = st.tabs([
    "🔍 投研分析",
    "📈 观察池",
    "📊 回测历史",
    "🎯 策略管理",
    "⚙️ 设置",
    "🎨 设计系统"
])

# Tab 1: 投研分析（主功能）
with tab1:
    from src.ui.pages import research_real
    research_real.render()

# Tab 2-5: 占位页面
with tab2:
    from src.ui.pages import watchlist
    watchlist.render()

with tab3:
    st.markdown("## 📊 回测历史")
    st.info("功能开发中...")

with tab4:
    st.markdown("## 🎯 策略管理")
    st.info("功能开发中...")

with tab5:
    st.markdown("## ⚙️ 设置")
    st.info("功能开发中...")

with tab_design:
    from src.ui.pages import design_system_test
    design_system_test.render()
