"""
Workbench PreScan - Deterministic fast pattern detection

Task 20A: Quick structural extraction before LLM intent understanding.

Rules:
- No LLM calls
- No final routing decision
- Only detect obvious patterns
"""

import re
from typing import Literal, NamedTuple


class WorkbenchPreScan(NamedTuple):
    """Fast deterministic pattern detection result."""
    detected_stock_code: str | None
    detected_execution_action: Literal["buy", "sell"] | None
    has_strategy_rule_shape: bool
    has_stock_research_language: bool
    has_market_scan_language: bool
    is_plain_greeting: bool
    detected_add_to_observation: bool


def prescan_message(user_message: str) -> WorkbenchPreScan:
    """
    Fast deterministic pattern scan.
    
    Detects:
    - A-share stock codes (bare or with suffix)
    - Execution feedback patterns
    - Strategy rule shape
    - Stock research language
    - Plain greetings
    
    Args:
        user_message: Raw user input
        
    Returns:
        WorkbenchPreScan with detected patterns
    """
    # Detect stock code
    detected_stock_code = None
    
    # Try to find stock code with suffix first
    code_with_suffix = re.search(r'(\d{6})\.(SH|SZ|BJ|sh|sz|bj)', user_message)
    if code_with_suffix:
        code = code_with_suffix.group(1)
        exchange = code_with_suffix.group(2).upper()
        detected_stock_code = f"{code}.{exchange}"
    else:
        # Try to find bare 6-digit code
        bare_code = re.search(r'(?:^|[^\d])(\d{6})(?:[^\d]|$)', user_message)
        if bare_code:
            code = bare_code.group(1)
            # Infer exchange from code prefix
            if code.startswith(('600', '601', '603', '605', '688')):
                detected_stock_code = f"{code}.SH"
            elif code.startswith(('000', '001', '002', '003', '300', '301')):
                detected_stock_code = f"{code}.SZ"
            elif code.startswith(('430', '8', '9')):
                detected_stock_code = f"{code}.BJ"
            else:
                # Unknown prefix, mark as potential SH
                detected_stock_code = f"{code}.SH"
    
    # Detect execution feedback pattern
    detected_execution_action = None
    if re.search(r'(?:已买入|已经买入|买入了|买了|买进).*股.*成交价', user_message):
        detected_execution_action = "buy"
    elif re.search(r'(?:已卖出|已经卖出|卖出了|卖了).*股.*成交价', user_message):
        detected_execution_action = "sell"
    
    # Detect strategy rule shape
    # Look for time + action + time/condition patterns
    has_strategy_rule_shape = False
    strategy_patterns = [
        r'(上午|下午|早上|晚上|两点半|三点|收盘|开盘).*买.*卖',
        r'(抖音|视频|策略|规则|刷到).*买.*卖',
        r'买.*(第二天|明天|收盘|次日).*卖',
        r'(入场|买入).*(出场|卖出|止盈|止损)',
    ]
    for pattern in strategy_patterns:
        if re.search(pattern, user_message):
            has_strategy_rule_shape = True
            break
    
    # Detect stock research language
    has_stock_research_language = False
    stock_research_patterns = [
        r'帮我看',
        r'帮我查',
        r'值得买',
        r'适合买',
        r'能不能买',
        r'可以买吗',
        r'是否值得',
        r'朋友推荐',
        r'买入.*可以',
        r'买入.*吗',
    ]
    for pattern in stock_research_patterns:
        if re.search(pattern, user_message):
            has_stock_research_language = True
            break
    
    # Also consider stock research if message contains Chinese company name pattern
    # without strategy rule shape
    if not has_stock_research_language and not has_strategy_rule_shape:
        # Check if message is mostly a Chinese company name (2-12 chars)
        chinese_only = re.sub(r'[^\u4e00-\u9fa5]', '', user_message)
        if 2 <= len(chinese_only) <= 12:
            has_stock_research_language = True

    market_scan_patterns = [r'选股', r'市场', r'行情', r'关注什么', r'今天关注', r'昨天市场']
    has_market_scan_language = any(re.search(pattern, user_message) for pattern in market_scan_patterns)
    
    # Detect plain greeting
    is_plain_greeting = False
    greeting_patterns = [
        r'^你好$',
        r'^hi$',
        r'^hello$',
        r'^您好$',
    ]
    for pattern in greeting_patterns:
        if re.search(pattern, user_message.strip(), re.IGNORECASE):
            is_plain_greeting = True
            break
    
    # Detect add to observation
    detected_add_to_observation = False
    add_to_observation_patterns = [
        r'加入观察',
        r'放入观察',
        r'加入观察池',
        r'放入观察池',
        r'加观察',
    ]
    for pattern in add_to_observation_patterns:
        if re.search(pattern, user_message):
            detected_add_to_observation = True
            break
    
    return WorkbenchPreScan(
        detected_stock_code=detected_stock_code,
        detected_execution_action=detected_execution_action,
        has_strategy_rule_shape=has_strategy_rule_shape,
        has_stock_research_language=has_stock_research_language,
        has_market_scan_language=has_market_scan_language,
        is_plain_greeting=is_plain_greeting,
        detected_add_to_observation=detected_add_to_observation,
    )
