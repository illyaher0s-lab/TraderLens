"""Debug PreScan and Intent Extractor"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.services.workbench_prescan import prescan_message
from backend.services.workbench_intent_extractor import LLMIntentExtractor

test_cases = [
    "帮我看宏昌电子是否值得买入",
    "帮我看603002",
    "朋友推荐了宏昌电子",
    "买入宏昌电子可以吗",
    "刷到策略下午两点半买第二天卖",
    "已买入100股成交价12.34",
    "今天要不要继续拿",
    "帮我看看",
    "你好",
]

extractor = LLMIntentExtractor(mode="deterministic")

for msg in test_cases:
    print(f"输入: {msg}")
    prescan = prescan_message(msg)
    print(f"  PreScan:")
    print(f"    detected_stock_code: {prescan.detected_stock_code}")
    print(f"    has_strategy_rule_shape: {prescan.has_strategy_rule_shape}")
    print(f"    has_stock_research_language: {prescan.has_stock_research_language}")
    print(f"    detected_execution_action: {prescan.detected_execution_action}")
    print(f"    is_plain_greeting: {prescan.is_plain_greeting}")
    
    intent = extractor.extract_intent(msg, prescan)
    print(f"  Intent:")
    print(f"    primary_intent: {intent.primary_intent}")
    print(f"    extracted_company_name: {intent.extracted_company_name}")
    print(f"    extracted_stock_code: {intent.extracted_stock_code}")
    print()
