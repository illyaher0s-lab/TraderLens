"""Vercel 设计系统 - 完整 CSS 实现

基于 popular-web-designs skill 的 Vercel 规范
修复原 app.py 中的问题：
1. 多层 shadow-as-border
2. 完整字体层级
3. Streamlit 特定覆盖
4. 间距系统
5. Focus 状态
"""

def get_vercel_css() -> str:
    """返回完整的 Vercel 设计系统 CSS"""
    return """
    <style>
    /* ============================================
       Vercel Design System - 完整实现
       ============================================ */
    
    /* 字体导入 */
    @import url('https://fonts.googleapis.com/css2?family=Geist:wght@300;400;500;600&family=Geist+Mono:wght@400;500&display=swap');
    
    /* ============================================
       1. CSS 变量定义（Design Tokens）
       ============================================ */
    :root {
        /* 主色 */
        --vercel-black: #171717;
        --vercel-white: #ffffff;
        --vercel-true-black: #000000;
        
        /* 灰度 */
        --vercel-gray-900: #171717;
        --vercel-gray-600: #4d4d4d;
        --vercel-gray-500: #666666;
        --vercel-gray-400: #808080;
        --vercel-gray-100: #ebebeb;
        --vercel-gray-50: #fafafa;
        
        /* 工作流颜色 */
        --ship-red: #ff5b4f;
        --preview-pink: #de1d8d;
        --develop-blue: #0a72ef;
        
        /* 交互色 */
        --link-blue: #0072f5;
        --focus-blue: hsla(212, 100%, 48%, 1);
        --focus-ring: rgba(147, 197, 253, 0.5);
        
        /* Badge */
        --badge-blue-bg: #ebf5ff;
        --badge-blue-text: #0068d6;
        
        /* 间距系统（8px 基准） */
        --space-1: 1px;
        --space-2: 2px;
        --space-4: 4px;
        --space-6: 6px;
        --space-8: 8px;
        --space-10: 10px;
        --space-12: 12px;
        --space-16: 16px;
        --space-24: 24px;
        --space-32: 32px;
        --space-40: 40px;
        --space-48: 48px;
        
        /* Shadow-as-border（Vercel 核心技术） */
        --shadow-border: rgba(0, 0, 0, 0.08) 0px 0px 0px 1px;
        --shadow-border-light: rgb(235, 235, 235) 0px 0px 0px 1px;
        --shadow-elevation: rgba(0, 0, 0, 0.04) 0px 2px 2px;
        --shadow-depth: rgba(0, 0, 0, 0.04) 0px 8px 8px -8px;
        --shadow-inner-glow: var(--vercel-gray-50) 0px 0px 0px 1px inset;
        
        /* 组合 shadow */
        --shadow-card: var(--shadow-border), var(--shadow-elevation), var(--shadow-inner-glow);
        --shadow-card-full: var(--shadow-border), var(--shadow-elevation), var(--shadow-depth), var(--shadow-inner-glow);
        
        /* 圆角 */
        --radius-2: 2px;
        --radius-4: 4px;
        --radius-6: 6px;
        --radius-8: 8px;
        --radius-12: 12px;
        --radius-pill: 9999px;
    }
    
    /* ============================================
       2. 全局重置 - Streamlit 覆盖
       ============================================ */
    
    /* 移除 Streamlit 默认 UI 元素 */
    #MainMenu {visibility: hidden !important;}
    footer {visibility: hidden !important;}
    header {visibility: hidden !important;}
    .stDeployButton {display: none !important;}
    
    /* 全局字体 */
    html, body, [class*="css"], [class*="st"] {
        font-family: 'Geist', system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif !important;
        -webkit-font-smoothing: antialiased;
        -moz-osx-font-smoothing: grayscale;
    }
    
    /* 主容器 */
    .main {
        background-color: var(--vercel-white) !important;
        padding: 0 !important;
    }
    
    .block-container {
        padding-top: var(--space-32) !important;
        padding-bottom: var(--space-48) !important;
        max-width: 1200px !important;
    }
    
    /* ============================================
       3. 字体层级系统（Vercel Typography）
       ============================================ */
    
    /* Display Hero - 48px */
    h1, .display-hero {
        font-family: 'Geist', sans-serif !important;
        font-size: 48px !important;
        font-weight: 600 !important;
        line-height: 1.17 !important;
        letter-spacing: -2.4px !important;
        color: var(--vercel-black) !important;
        margin-top: 0 !important;
        margin-bottom: var(--space-16) !important;
    }
    
    /* Section Heading - 40px */
    .section-heading {
        font-family: 'Geist', sans-serif !important;
        font-size: 40px !important;
        font-weight: 600 !important;
        line-height: 1.20 !important;
        letter-spacing: -2.4px !important;
        color: var(--vercel-black) !important;
        margin-top: var(--space-32) !important;
        margin-bottom: var(--space-16) !important;
    }
    
    /* Sub-heading Large - 32px */
    h2, .sub-heading-large {
        font-family: 'Geist', sans-serif !important;
        font-size: 32px !important;
        font-weight: 600 !important;
        line-height: 1.25 !important;
        letter-spacing: -1.28px !important;
        color: var(--vercel-black) !important;
        margin-top: var(--space-32) !important;
        margin-bottom: var(--space-16) !important;
    }
    
    /* Card Title - 24px */
    h3, .card-title {
        font-family: 'Geist', sans-serif !important;
        font-size: 24px !important;
        font-weight: 600 !important;
        line-height: 1.33 !important;
        letter-spacing: -0.96px !important;
        color: var(--vercel-black) !important;
        margin-top: var(--space-24) !important;
        margin-bottom: var(--space-12) !important;
    }
    
    /* Body Large - 20px */
    .body-large {
        font-family: 'Geist', sans-serif !important;
        font-size: 20px !important;
        font-weight: 400 !important;
        line-height: 1.80 !important;
        color: var(--vercel-gray-600) !important;
    }
    
    /* Body - 18px */
    .body {
        font-family: 'Geist', sans-serif !important;
        font-size: 18px !important;
        font-weight: 400 !important;
        line-height: 1.56 !important;
        color: var(--vercel-gray-600) !important;
    }
    
    /* Body Small - 16px (默认) */
    p, .stMarkdown, .body-small {
        font-family: 'Geist', sans-serif !important;
        font-size: 16px !important;
        font-weight: 400 !important;
        line-height: 1.50 !important;
        color: var(--vercel-gray-600) !important;
    }
    
    /* Body Medium - 16px 加粗 */
    .body-medium {
        font-family: 'Geist', sans-serif !important;
        font-size: 16px !important;
        font-weight: 500 !important;
        line-height: 1.50 !important;
        color: var(--vercel-black) !important;
    }
    
    /* Button/Link Text - 14px */
    .button-text, .link-text {
        font-family: 'Geist', sans-serif !important;
        font-size: 14px !important;
        font-weight: 500 !important;
        line-height: 1.43 !important;
        color: var(--vercel-black) !important;
    }
    
    /* Caption - 12px */
    .caption {
        font-family: 'Geist', sans-serif !important;
        font-size: 12px !important;
        font-weight: 400 !important;
        line-height: 1.33 !important;
        color: var(--vercel-gray-500) !important;
    }
    
    /* Mono - 代码/技术标签 */
    code, pre, .mono {
        font-family: 'Geist Mono', ui-monospace, monospace !important;
        font-size: 13px !important;
        font-weight: 400 !important;
        background-color: var(--vercel-gray-50) !important;
        padding: 2px 6px !important;
        border-radius: var(--radius-4) !important;
        color: var(--vercel-black) !important;
    }
    
    /* ============================================
       4. 按钮样式（Primary + Secondary + Ghost）
       ============================================ */
    
    /* 基础按钮样式 */
    .stButton > button {
        font-family: 'Geist', sans-serif !important;
        font-size: 14px !important;
        font-weight: 500 !important;
        border: none !important;
        border-radius: var(--radius-6) !important;
        padding: 8px 16px !important;
        cursor: pointer !important;
        transition: all 0.2s ease !important;
        line-height: 1.43 !important;
    }
    
    /* Primary Button (黑底白字) */
    .stButton > button[data-testid="baseButton-primary"],
    .stButton > button:not([kind]) {
        background-color: var(--vercel-black) !important;
        color: var(--vercel-white) !important;
    }
    
    .stButton > button[data-testid="baseButton-primary"]:hover,
    .stButton > button:not([kind]):hover {
        background-color: var(--vercel-true-black) !important;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15) !important;
    }
    
    /* Secondary Button (白底黑字 shadow-border) */
    .stButton > button[data-testid="baseButton-secondary"] {
        background-color: var(--vercel-white) !important;
        color: var(--vercel-black) !important;
        box-shadow: var(--shadow-border) !important;
    }
    
    .stButton > button[data-testid="baseButton-secondary"]:hover {
        background-color: var(--vercel-gray-50) !important;
        box-shadow: var(--shadow-border), var(--shadow-elevation) !important;
    }
    
    /* Focus 状态 - 蓝色外圈 */
    .stButton > button:focus,
    .stButton > button:focus-visible {
        outline: 2px solid var(--focus-blue) !important;
        outline-offset: 2px !important;
        box-shadow: 0 0 0 4px var(--focus-ring) !important;
    }
    
    /* ============================================
       5. 输入框样式（Input + Select + Textarea）
       ============================================ */
    
    .stTextInput > div > div > input,
    .stSelectbox > div > div > select,
    .stTextArea > div > div > textarea,
    .stNumberInput > div > div > input {
        font-family: 'Geist', sans-serif !important;
        font-size: 14px !important;
        font-weight: 400 !important;
        color: var(--vercel-black) !important;
        background-color: var(--vercel-white) !important;
        border: none !important;
        border-radius: var(--radius-6) !important;
        box-shadow: var(--shadow-border) !important;
        padding: 8px 12px !important;
        transition: box-shadow 0.2s ease !important;
    }
    
    /* Placeholder */
    .stTextInput > div > div > input::placeholder,
    .stTextArea > div > div > textarea::placeholder {
        color: var(--vercel-gray-400) !important;
    }
    
    /* Focus 状态 */
    .stTextInput > div > div > input:focus,
    .stSelectbox > div > div > select:focus,
    .stTextArea > div > div > textarea:focus,
    .stNumberInput > div > div > input:focus {
        box-shadow: var(--shadow-border), 0 0 0 2px var(--focus-blue) !important;
        outline: none !important;
    }
    
    /* Label */
    .stTextInput > label,
    .stSelectbox > label,
    .stTextArea > label,
    .stNumberInput > label {
        font-family: 'Geist', sans-serif !important;
        font-size: 14px !important;
        font-weight: 500 !important;
        color: var(--vercel-black) !important;
        margin-bottom: var(--space-8) !important;
    }
    
    /* ============================================
       6. 卡片样式（Shadow-as-border 多层叠加）
       ============================================ */
    
    .card, .stContainer {
        background-color: var(--vercel-white) !important;
        border: none !important;
        border-radius: var(--radius-8) !important;
        box-shadow: var(--shadow-card) !important;
        padding: var(--space-24) !important;
        margin-bottom: var(--space-16) !important;
        transition: box-shadow 0.2s ease !important;
    }
    
    .card:hover {
        box-shadow: var(--shadow-card-full) !important;
    }
    
    /* Featured Card - 增强阴影 */
    .card-featured {
        box-shadow: var(--shadow-card-full) !important;
    }
    
    /* ============================================
       7. Tab 导航样式
       ============================================ */
    
    .stTabs [data-baseweb="tab-list"] {
        gap: var(--space-8) !important;
        background-color: var(--vercel-white) !important;
        border-bottom: 1px solid var(--vercel-gray-100) !important;
        padding-bottom: 0 !important;
    }
    
    .stTabs [data-baseweb="tab"] {
        font-family: 'Geist', sans-serif !important;
        font-size: 14px !important;
        font-weight: 500 !important;
        color: var(--vercel-gray-600) !important;
        background-color: transparent !important;
        border: none !important;
        border-radius: var(--radius-6) var(--radius-6) 0 0 !important;
        padding: var(--space-8) var(--space-16) !important;
        transition: all 0.2s ease !important;
    }
    
    .stTabs [data-baseweb="tab"]:hover {
        color: var(--vercel-black) !important;
        background-color: var(--vercel-gray-50) !important;
    }
    
    .stTabs [data-baseweb="tab"][aria-selected="true"] {
        color: var(--vercel-black) !important;
        font-weight: 600 !important;
        background-color: var(--vercel-gray-50) !important;
    }
    
    /* Tab Panel */
    .stTabs [data-baseweb="tab-panel"] {
        padding-top: var(--space-24) !important;
    }
    
    /* ============================================
       8. Badge / Pill 样式
       ============================================ */
    
    .badge, .pill {
        display: inline-block;
        font-family: 'Geist', sans-serif !important;
        font-size: 12px !important;
        font-weight: 500 !important;
        padding: 4px 10px !important;
        border-radius: var(--radius-pill) !important;
        background-color: var(--badge-blue-bg) !important;
        color: var(--badge-blue-text) !important;
        margin: 4px !important;
    }
    
    /* 工作流 Badge */
    .badge-ship {
        background-color: rgba(255, 91, 79, 0.1) !important;
        color: var(--ship-red) !important;
    }
    
    .badge-preview {
        background-color: rgba(222, 29, 141, 0.1) !important;
        color: var(--preview-pink) !important;
    }
    
    .badge-develop {
        background-color: rgba(10, 114, 239, 0.1) !important;
        color: var(--develop-blue) !important;
    }
    
    /* ============================================
       9. 消息框样式（Success / Error / Warning / Info）
       ============================================ */
    
    .stSuccess, .stError, .stWarning, .stInfo {
        font-family: 'Geist', sans-serif !important;
        font-size: 14px !important;
        font-weight: 400 !important;
        border-radius: var(--radius-6) !important;
        padding: 12px 16px !important;
        border: none !important;
        box-shadow: var(--shadow-border) !important;
    }
    
    /* ============================================
       10. 表格样式
       ============================================ */
    
    .stDataFrame, .stTable {
        font-family: 'Geist', sans-serif !important;
        font-size: 14px !important;
    }
    
    .stDataFrame table {
        border-collapse: separate !important;
        border-spacing: 0 !important;
        border: none !important;
        box-shadow: var(--shadow-border) !important;
        border-radius: var(--radius-8) !important;
        overflow: hidden !important;
    }
    
    .stDataFrame th {
        font-family: 'Geist', sans-serif !important;
        font-size: 12px !important;
        font-weight: 600 !important;
        text-transform: uppercase !important;
        letter-spacing: 0.5px !important;
        color: var(--vercel-gray-600) !important;
        background-color: var(--vercel-gray-50) !important;
        padding: 12px 16px !important;
        border-bottom: 1px solid var(--vercel-gray-100) !important;
    }
    
    .stDataFrame td {
        font-family: 'Geist', sans-serif !important;
        font-size: 14px !important;
        font-weight: 400 !important;
        color: var(--vercel-black) !important;
        padding: 12px 16px !important;
        border-bottom: 1px solid var(--vercel-gray-100) !important;
    }
    
    .stDataFrame tr:last-child td {
        border-bottom: none !important;
    }
    
    .stDataFrame tr:hover {
        background-color: var(--vercel-gray-50) !important;
    }
    
    /* ============================================
       11. 加载状态
       ============================================ */
    
    .stSpinner > div {
        border-color: var(--vercel-black) transparent transparent transparent !important;
    }
    
    /* ============================================
       12. 链接样式
       ============================================ */
    
    a {
        color: var(--link-blue) !important;
        text-decoration: underline !important;
        transition: color 0.2s ease !important;
    }
    
    a:hover {
        color: var(--develop-blue) !important;
    }
    
    /* ============================================
       13. 响应式调整
       ============================================ */
    
    @media (max-width: 768px) {
        h1, .display-hero {
            font-size: 32px !important;
            letter-spacing: -1.6px !important;
        }
        
        h2, .sub-heading-large {
            font-size: 24px !important;
            letter-spacing: -0.96px !important;
        }
        
        h3, .card-title {
            font-size: 20px !important;
            letter-spacing: -0.6px !important;
        }
        
        .block-container {
            padding-top: var(--space-16) !important;
            padding-bottom: var(--space-24) !important;
        }
    }
    
    /* ============================================
       14. Utility Classes
       ============================================ */
    
    /* 间距工具类 */
    .mt-8 { margin-top: var(--space-8) !important; }
    .mt-16 { margin-top: var(--space-16) !important; }
    .mt-24 { margin-top: var(--space-24) !important; }
    .mt-32 { margin-top: var(--space-32) !important; }
    
    .mb-8 { margin-bottom: var(--space-8) !important; }
    .mb-16 { margin-bottom: var(--space-16) !important; }
    .mb-24 { margin-bottom: var(--space-24) !important; }
    .mb-32 { margin-bottom: var(--space-32) !important; }
    
    .p-16 { padding: var(--space-16) !important; }
    .p-24 { padding: var(--space-24) !important; }
    .p-32 { padding: var(--space-32) !important; }
    
    /* 颜色工具类 */
    .text-black { color: var(--vercel-black) !important; }
    .text-gray-600 { color: var(--vercel-gray-600) !important; }
    .text-gray-400 { color: var(--vercel-gray-400) !important; }
    
    .bg-white { background-color: var(--vercel-white) !important; }
    .bg-gray-50 { background-color: var(--vercel-gray-50) !important; }
    
    /* Shadow 工具类 */
    .shadow-border { box-shadow: var(--shadow-border) !important; }
    .shadow-card { box-shadow: var(--shadow-card) !important; }
    .shadow-card-full { box-shadow: var(--shadow-card-full) !important; }
    
    </style>
    """
