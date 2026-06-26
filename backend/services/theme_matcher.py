"""
Deterministic theme relevance matcher.

计算来源与主题的匹配关系，不涉及 LLM。
规则：
- 关键词来自主题名称或用户背景
- 排除过短、停用词和通用词
- 匹配目标：来源的 title、summary 或行业字段
- 归一化：大小写、空格、中英文标点
"""

import re


# 中文通用词（不能证明主题相关）
CHINESE_GENERIC_TERMS = {
    "业务", "公司", "企业", "行业", "发展", "市场", "产品", "服务",
    "管理", "经营", "运营", "战略", "合作", "投资", "项目", "技术",
    "系统", "平台", "方案", "模式", "体系", "建设", "创新", "研发",
    "生产", "销售", "客户", "用户", "品牌", "价值", "能力", "水平",
}

# 英文通用词（不能证明主题相关）
ENGLISH_GENERIC_TERMS = {
    "business", "company", "enterprise", "industry", "development", "market",
    "product", "service", "management", "operation", "strategy", "cooperation",
    "investment", "project", "technology", "system", "platform", "solution",
    "model", "construction", "innovation", "production", "sales", "customer",
    "user", "brand", "value", "capability", "level",
}


def normalize_text(text: str) -> str:
    """归一化文本：小写、去空格、统一标点。"""
    text = text.lower()
    # 统一中英文标点
    text = text.replace("，", ",").replace("。", ".").replace("！", "!").replace("？", "?")
    text = text.replace("：", ":").replace("；", ";").replace("（", "(").replace("）", ")")
    # 去除多余空格
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def extract_keywords(theme_name: str, theme_background: str = "") -> list[str]:
    """
    从主题名称和背景提取有效关键词。
    
    规则：
    - 长度 >= 2（中文）或 >= 3（英文）
    - 排除通用词
    - 归一化
    """
    text = f"{theme_name} {theme_background}"
    text = normalize_text(text)
    
    keywords = []
    
    # 中文分词（简单按空格和标点分割）
    # TODO: 可以使用 jieba 分词提升准确度
    tokens = re.split(r'[\s,，.。!！?？:：;；()（）]+', text)
    
    for token in tokens:
        token = token.strip()
        if not token:
            continue
        
        # 长度检查
        is_chinese = bool(re.search(r'[\u4e00-\u9fff]', token))
        if is_chinese and len(token) < 2:
            continue
        if not is_chinese and len(token) < 3:
            continue
        
        # 通用词检查
        if token in CHINESE_GENERIC_TERMS or token in ENGLISH_GENERIC_TERMS:
            continue
        
        keywords.append(token)
    
    # 去重保持顺序
    seen = set()
    result = []
    for kw in keywords:
        if kw not in seen:
            seen.add(kw)
            result.append(kw)
    
    return result


def match_theme_to_source(
    keywords: list[str],
    source_title: str,
    source_summary: str,
    source_industry: str = "",
) -> tuple[list[str], str | None]:
    """
    确定性匹配：检查关键词是否出现在来源内容中。
    
    Returns:
        (matched_keywords, relevance_basis)
        
    relevance_basis 可能值：
        - "title_match": 关键词匹配标题
        - "summary_match": 关键词匹配摘要
        - "industry_match": 关键词匹配行业字段
        - None: 无匹配
    """
    if not keywords:
        return [], None
    
    # 归一化来源内容
    title_norm = normalize_text(source_title)
    summary_norm = normalize_text(source_summary)
    industry_norm = normalize_text(source_industry)
    
    matched = []
    basis = None
    
    for kw in keywords:
        kw_norm = normalize_text(kw)
        
        # 检查标题匹配
        if kw_norm in title_norm:
            if kw not in matched:
                matched.append(kw)
            if basis is None:
                basis = "title_match"
        
        # 检查摘要匹配
        elif kw_norm in summary_norm:
            if kw not in matched:
                matched.append(kw)
            if basis is None:
                basis = "summary_match"
        
        # 检查行业匹配
        elif source_industry and kw_norm in industry_norm:
            if kw not in matched:
                matched.append(kw)
            if basis is None:
                basis = "industry_match"
    
    return matched, basis
