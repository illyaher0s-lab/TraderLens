"""设计系统验证页

验证 Vercel 设计系统的所有核心组件：
1. Typography（字体层级）
2. Colors（色板）
3. Buttons（按钮状态）
4. Cards（卡片样式）
5. Form Elements（表单）
6. Badges（标签）
7. Table（表格）
"""

import streamlit as st


def render():
    """渲染设计系统验证页"""
    
    st.markdown("# 🎨 设计系统验证页")
    st.markdown('<p class="body-large">验证 Vercel 设计系统的所有核心组件是否正确加载和渲染</p>', unsafe_allow_html=True)
    
    st.markdown("---")
    
    # ============================================
    # 1. Typography（字体层级）
    # ============================================
    st.markdown("## Typography 字体层级")
    st.markdown('<p class="caption">验证字体大小、字重、letter-spacing 是否符合 Vercel 标准</p>', unsafe_allow_html=True)
    
    with st.container():
        st.markdown("""
        <div class="card">
            <h1 style="margin-top: 0;">Display Hero - 48px / -2.4px</h1>
            <div class="section-heading">Section Heading - 40px / -2.4px</div>
            <h2>Sub-heading Large - 32px / -1.28px</h2>
            <h3>Card Title - 24px / -0.96px</h3>
            <p class="body-large">Body Large - 20px / line-height 1.80 (介绍性文本)</p>
            <p class="body">Body - 18px / line-height 1.56 (标准阅读文本)</p>
            <p class="body-small">Body Small - 16px / line-height 1.50 (默认 UI 文本)</p>
            <p class="body-medium">Body Medium - 16px weight 500 (导航/强调)</p>
            <p class="button-text">Button/Link Text - 14px weight 500</p>
            <p class="caption">Caption - 12px (元数据/标签)</p>
            <code class="mono">Geist Mono - 13px (代码/技术标签)</code>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("**验证项：**")
    st.markdown("- ✅ Display Hero 是否明显比其他标题大？")
    st.markdown("- ✅ letter-spacing 是否为负值（标题看起来紧凑）？")
    st.markdown("- ✅ Body Large 行高是否宽松（适合阅读）？")
    st.markdown("- ✅ Geist Mono 是否等宽字体？")
    
    st.markdown("---")
    
    # ============================================
    # 2. Colors（色板）
    # ============================================
    st.markdown("## Colors 色板")
    st.markdown('<p class="caption">验证主色、灰度、工作流颜色是否正确</p>', unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("""
        <div class="card">
            <h3>主色</h3>
            <div style="background: #171717; color: white; padding: 16px; border-radius: 6px; margin: 8px 0;">
                Vercel Black #171717
            </div>
            <div style="background: #ffffff; color: #171717; padding: 16px; border-radius: 6px; margin: 8px 0; box-shadow: var(--shadow-border);">
                Pure White #ffffff
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown("""
        <div class="card">
            <h3>灰度</h3>
            <div style="background: #4d4d4d; color: white; padding: 12px; border-radius: 6px; margin: 4px 0; font-size: 12px;">
                Gray 600 #4d4d4d
            </div>
            <div style="background: #808080; color: white; padding: 12px; border-radius: 6px; margin: 4px 0; font-size: 12px;">
                Gray 400 #808080
            </div>
            <div style="background: #ebebeb; color: #171717; padding: 12px; border-radius: 6px; margin: 4px 0; font-size: 12px;">
                Gray 100 #ebebeb
            </div>
            <div style="background: #fafafa; color: #171717; padding: 12px; border-radius: 6px; margin: 4px 0; font-size: 12px; box-shadow: var(--shadow-border);">
                Gray 50 #fafafa
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown("""
        <div class="card">
            <h3>工作流颜色</h3>
            <div style="background: #ff5b4f; color: white; padding: 12px; border-radius: 6px; margin: 4px 0; font-size: 12px;">
                Ship Red #ff5b4f
            </div>
            <div style="background: #de1d8d; color: white; padding: 12px; border-radius: 6px; margin: 4px 0; font-size: 12px;">
                Preview Pink #de1d8d
            </div>
            <div style="background: #0a72ef; color: white; padding: 12px; border-radius: 6px; margin: 4px 0; font-size: 12px;">
                Develop Blue #0a72ef
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("**验证项：**")
    st.markdown("- ✅ Vercel Black 是否为深灰而非纯黑（#171717 vs #000000）？")
    st.markdown("- ✅ 灰度层级是否清晰可辨？")
    st.markdown("- ✅ 工作流颜色是否鲜艳且有区分度？")
    
    st.markdown("---")
    
    # ============================================
    # 3. Buttons（按钮）
    # ============================================
    st.markdown("## Buttons 按钮")
    st.markdown('<p class="caption">验证按钮样式、hover 状态、focus 外圈</p>', unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("### Primary Button")
        st.button("黑底白字 Primary", key="btn_primary_1", type="primary")
        st.markdown('<p class="caption">背景 #171717 / hover 变 #000000</p>', unsafe_allow_html=True)
    
    with col2:
        st.markdown("### Secondary Button")
        st.button("白底黑字 Shadow-border", key="btn_secondary_1", type="secondary")
        st.markdown('<p class="caption">shadow-as-border 技术</p>', unsafe_allow_html=True)
    
    with col3:
        st.markdown("### Focus 状态")
        st.button("点击测试 Focus", key="btn_focus_1")
        st.markdown('<p class="caption">应有蓝色外圈 (Focus Blue)</p>', unsafe_allow_html=True)
    
    st.markdown("**验证项：**")
    st.markdown("- ✅ Primary 按钮是黑底白字，hover 时变得更黑？")
    st.markdown("- ✅ Secondary 按钮有细边框（shadow-as-border）？")
    st.markdown("- ✅ 点击按钮时出现蓝色 focus 外圈？")
    st.markdown("- ✅ 字体是 Geist 14px weight 500？")
    
    st.markdown("---")
    
    # ============================================
    # 4. Cards（卡片）
    # ============================================
    st.markdown("## Cards 卡片")
    st.markdown('<p class="caption">验证 shadow-as-border 多层叠加效果</p>', unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
        <div class="card">
            <h3 style="margin-top: 0;">标准卡片</h3>
            <p class="body-small">这是一个标准卡片，使用 shadow-as-border + 轻微 elevation + 内发光。</p>
            <p class="caption">box-shadow: border + elevation + inner-glow</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown("""
        <div class="card card-featured">
            <h3 style="margin-top: 0;">Featured 卡片</h3>
            <p class="body-small">这是一个 featured 卡片，增加了 depth 层（8px blur）。</p>
            <p class="caption">box-shadow: border + elevation + depth + inner-glow</p>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("**验证项：**")
    st.markdown("- ✅ 卡片边框是否为细线（1px shadow-border）？")
    st.markdown("- ✅ 卡片是否有轻微的内发光效果（#fafafa inset）？")
    st.markdown("- ✅ Featured 卡片是否比标准卡片阴影更深？")
    st.markdown("- ✅ Hover 卡片时阴影是否加深？")
    
    st.markdown("---")
    
    # ============================================
    # 5. Form Elements（表单）
    # ============================================
    st.markdown("## Form Elements 表单")
    st.markdown('<p class="caption">验证输入框、下拉框、focus 状态</p>', unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.text_input("文本输入框", placeholder="输入文字测试 placeholder 颜色", key="input_test_1")
        st.selectbox("下拉选择框", ["选项 1", "选项 2", "选项 3"], key="select_test_1")
    
    with col2:
        st.number_input("数字输入框", min_value=0, max_value=100, value=50, key="number_test_1")
        st.text_area("文本域", placeholder="多行文本输入", key="textarea_test_1")
    
    st.markdown("**验证项：**")
    st.markdown("- ✅ 输入框边框是 shadow-as-border（非传统 border）？")
    st.markdown("- ✅ Placeholder 颜色是 Gray 400 (#808080)？")
    st.markdown("- ✅ Focus 时出现蓝色外圈（Focus Blue）？")
    st.markdown("- ✅ 字体是 Geist 14px？")
    
    st.markdown("---")
    
    # ============================================
    # 6. Badges（标签）
    # ============================================
    st.markdown("## Badges 标签")
    st.markdown('<p class="caption">验证 pill 样式、工作流颜色</p>', unsafe_allow_html=True)
    
    st.markdown("""
    <div class="card">
        <h3 style="margin-top: 0;">Badge 样式</h3>
        <div style="margin: 16px 0;">
            <span class="badge">默认蓝色 Badge</span>
            <span class="badge-develop">Develop</span>
            <span class="badge-preview">Preview</span>
            <span class="badge-ship">Ship</span>
        </div>
        <p class="caption">所有 badge 应为 9999px 圆角（pill 形状）</p>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("**验证项：**")
    st.markdown("- ✅ Badge 是否为完整的 pill 形状（9999px 圆角）？")
    st.markdown("- ✅ 工作流 badge 颜色是否正确（蓝/粉/红）？")
    st.markdown("- ✅ 字体是 Geist 12px weight 500？")
    
    st.markdown("---")
    
    # ============================================
    # 7. Table（表格）
    # ============================================
    st.markdown("## Table 表格")
    st.markdown('<p class="caption">验证表格样式、hover 状态、表头</p>', unsafe_allow_html=True)
    
    import pandas as pd
    
    df = pd.DataFrame({
        "股票代码": ["000001", "600519", "000858"],
        "股票名称": ["平安银行", "贵州茅台", "五粮液"],
        "当前价格": [12.50, 1850.00, 180.30],
        "涨跌幅": ["+2.3%", "-0.5%", "+1.2%"],
        "状态": ["观察中", "观察中", "观察中"]
    })
    
    st.dataframe(df, use_container_width=True)
    
    st.markdown("**验证项：**")
    st.markdown("- ✅ 表格边框是 shadow-as-border？")
    st.markdown("- ✅ 表头是否为大写、Gray 50 背景、字重 600？")
    st.markdown("- ✅ Hover 行时背景是否变为 Gray 50？")
    st.markdown("- ✅ 字体是 Geist 14px？")
    
    st.markdown("---")
    
    # ============================================
    # 8. Messages（消息框）
    # ============================================
    st.markdown("## Messages 消息框")
    st.markdown('<p class="caption">验证 success/error/warning/info 样式</p>', unsafe_allow_html=True)
    
    st.success("✅ Success - 操作成功")
    st.error("❌ Error - 发生错误")
    st.warning("⚠️ Warning - 警告信息")
    st.info("ℹ️ Info - 提示信息")
    
    st.markdown("**验证项：**")
    st.markdown("- ✅ 消息框是否有 shadow-border？")
    st.markdown("- ✅ 圆角是否为 6px？")
    st.markdown("- ✅ 字体是 Geist 14px？")
    
    st.markdown("---")
    
    # ============================================
    # 9. 最终验证清单
    # ============================================
    st.markdown("## 🎯 最终验证清单")
    st.markdown("### 通过标准")
    
    checklist = {
        "字体加载": "Geist 和 Geist Mono 是否正确加载？",
        "字体层级": "Display (48px) → Sub-heading (32px) → Card Title (24px) 层级清晰？",
        "Letter-spacing": "大标题是否有负值 letter-spacing（看起来紧凑）？",
        "Shadow-as-border": "卡片/按钮/输入框边框是否为 1px shadow 而非传统 border？",
        "多层 shadow": "卡片是否有内发光效果（#fafafa inset）？",
        "按钮样式": "Primary 黑底白字，Secondary 白底黑字带 shadow-border？",
        "Focus 状态": "点击输入框/按钮时是否出现蓝色外圈？",
        "工作流颜色": "Ship (红) / Preview (粉) / Develop (蓝) 是否正确？",
        "间距系统": "元素之间间距是否舒适（不拥挤也不松散）？",
        "响应式": "缩小窗口时字体大小是否适配？"
    }
    
    for item, description in checklist.items():
        st.markdown(f"- [ ] **{item}**: {description}")
    
    st.markdown("---")
    st.markdown('<p class="caption" style="text-align: center;">如果所有验证项通过，设计系统正常工作 ✅<br>如果有验证项失败，需要修复全局 CSS ❌</p>', unsafe_allow_html=True)
