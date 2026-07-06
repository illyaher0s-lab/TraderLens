"""
Workbench Intent Extractor - LLM semantic understanding

Task 20A: LLM extracts user intent from natural language.

Rules:
- LLM can understand semantics
- LLM can extract company names
- LLM can extract stock code candidates
- LLM can extract strategy text
- LLM cannot confirm stock existence
- LLM cannot make final routing decision
"""

from typing import Literal, Optional
from pydantic import BaseModel, Field
from backend.services.workbench_prescan import WorkbenchPreScan


class WorkbenchIntentExtraction(BaseModel):
    """LLM intent extraction result."""
    primary_intent: Literal[
        "stock_research",
        "theme_research",
        "strategy_idea",
        "execution_feedback",
        "position_followup",
        "review_request",
        "add_to_observation",
        "unknown"
    ]
    intent_candidates: list[str] = Field(default_factory=list)
    extracted_company_name: Optional[str] = None
    extracted_stock_code: Optional[str] = None
    extracted_strategy_text: Optional[str] = None
    confidence: Literal["high", "medium", "low"]
    ambiguity_reason: Optional[str] = None
    extraction_source: Literal["llm", "deterministic_fixture"]


class LLMIntentExtractor:
    """
    Extract user intent using LLM semantic understanding.
    
    Production mode: uses real LLMClient
    Deterministic mode: uses fake extractor
    """
    
    def __init__(self, llm_client=None, mode: str = "deterministic"):
        """
        Args:
            llm_client: LLMClient for production extraction
            mode: "real" or "deterministic"
        """
        self.llm_client = llm_client
        self.mode = mode
    
    def extract_intent(
        self,
        user_message: str,
        prescan: WorkbenchPreScan,
    ) -> WorkbenchIntentExtraction:
        """
        Extract user intent from natural language.
        
        Args:
            user_message: Raw user input
            prescan: PreScan result for context
            
        Returns:
            WorkbenchIntentExtraction with semantic understanding
        """
        if self.mode == "real" and self.llm_client:
            return self._extract_with_llm(user_message, prescan)
        else:
            return self._extract_deterministic(user_message, prescan)
    
    def _extract_with_llm(
        self,
        user_message: str,
        prescan: WorkbenchPreScan,
    ) -> WorkbenchIntentExtraction:
        """Production path: use real LLM."""
        # Build prompt with prescan context
        system_prompt = """你是 TraderLens 意图理解助手。

你的任务是理解用户的自然语言输入，提取意图和关键信息。

可能的意图类型：
- stock_research: 用户想研究某只股票（公司推荐、值得买吗、帮我看看）
- theme_research: 用户想研究某个主题/行业（产业链、赛道）
- strategy_idea: 用户想验证交易策略（抖音策略、买入卖出规则）
- execution_feedback: 用户报告交易执行（已买入、已卖出）
- position_followup: 用户询问持仓（我的持仓、今天信号）
- review_request: 用户想要复盘（回顾、总结）
- unknown: 无法判断意图

你需要提取：
- primary_intent: 主要意图
- intent_candidates: 可能的意图列表（如果模糊）
- extracted_company_name: 公司名（如果提到）
- extracted_stock_code: 股票代码候选（如果提到）
- extracted_strategy_text: 策略描述（如果是策略）
- confidence: high/medium/low
- ambiguity_reason: 如果模糊，说明原因

注意：
- 你只提取信息，不确认股票是否存在
- 你不做最终路由决定
- 如果用户提到"买入某公司"，这是 stock_research，不是 strategy_idea
- 只有明确的规则（时间+条件）才是 strategy_idea

请以 JSON 格式返回结果。"""

        user_prompt = f"""用户输入：{user_message}

PreScan 结果：
- detected_stock_code: {prescan.detected_stock_code}
- has_strategy_rule_shape: {prescan.has_strategy_rule_shape}
- has_stock_research_language: {prescan.has_stock_research_language}
- is_plain_greeting: {prescan.is_plain_greeting}

请分析并返回 JSON 格式的意图提取结果。"""

        try:
            response = self.llm_client.complete(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"}
            )
            
            # Parse JSON response
            import json
            result_dict = json.loads(response)
            
            # Validate with Pydantic
            extraction = WorkbenchIntentExtraction(
                extraction_source="llm",
                **result_dict
            )
            return extraction
            
        except Exception as e:
            # LLM extraction failed, retry once
            try:
                response = self.llm_client.complete(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    response_format={"type": "json_object"}
                )
                result_dict = json.loads(response)
                extraction = WorkbenchIntentExtraction(
                    extraction_source="llm",
                    **result_dict
                )
                return extraction
            except Exception as retry_error:
                # Both attempts failed, fall back to deterministic
                return self._extract_deterministic(user_message, prescan)
    
    def _extract_deterministic(
        self,
        user_message: str,
        prescan: WorkbenchPreScan,
    ) -> WorkbenchIntentExtraction:
        """Deterministic fallback for testing."""
        import re
        
        # Plain greeting
        if prescan.is_plain_greeting:
            return WorkbenchIntentExtraction(
                primary_intent="unknown",
                intent_candidates=["unknown"],
                confidence="high",
                extraction_source="deterministic_fixture",
            )
        
        # Add to observation (highest priority after greeting)
        if prescan.detected_add_to_observation:
            return WorkbenchIntentExtraction(
                primary_intent="add_to_observation",
                intent_candidates=["add_to_observation"],
                confidence="high",
                extraction_source="deterministic_fixture",
            )
        
        # Execution feedback
        if prescan.detected_execution_action:
            # Extract company name and stock code from message
            import re
            
            # Extract stock code from prescan
            extracted_stock_code = prescan.detected_stock_code
            
            # Extract company name
            # Remove detected stock code from message first
            message_no_code = user_message
            if prescan.detected_stock_code:
                message_no_code = re.sub(r'\d{6}(\.(SH|SZ|BJ))?', '', user_message)
            
            # Remove noise words and punctuation
            noise_words = ['已买入', '已卖出', '买入', '卖出', '成交价', '股', '元', '昨天', '今天']
            cleaned_message = message_no_code
            for noise in noise_words:
                cleaned_message = cleaned_message.replace(noise, ' ')
            
            cleaned_message = re.sub(r'[，。、；：？！（）\s\d]+', ' ', cleaned_message)
            cleaned_message = cleaned_message.strip()
            
            # Extract Chinese company name
            company_pattern = r'[\u4e00-\u9fa5]{2,12}'
            company_matches = re.findall(company_pattern, cleaned_message)
            
            extracted_company = None
            if company_matches:
                company_matches.sort(key=len, reverse=True)
                extracted_company = company_matches[0].strip()
            
            return WorkbenchIntentExtraction(
                primary_intent="execution_feedback",
                intent_candidates=["execution_feedback"],
                extracted_company_name=extracted_company,
                extracted_stock_code=extracted_stock_code,
                confidence="high",
                extraction_source="deterministic_fixture",
            )
        
        # Strategy idea - must have strategy rule shape
        if prescan.has_strategy_rule_shape:
            return WorkbenchIntentExtraction(
                primary_intent="strategy_idea",
                intent_candidates=["strategy_idea"],
                extracted_strategy_text=user_message,
                confidence="high",
                extraction_source="deterministic_fixture",
            )
        
        # Position followup - check for specific patterns
        position_followup_patterns = [
            r'今天.*继续.*拿',
            r'持仓.*信号',
            r'我的.*持仓',
            r'.*要不要.*继续',
            r'.*卖不卖',
        ]
        for pattern in position_followup_patterns:
            if re.search(pattern, user_message):
                return WorkbenchIntentExtraction(
                    primary_intent="position_followup",
                    intent_candidates=["position_followup"],
                    confidence="medium",
                    ambiguity_reason="需要 session context 才能确认持仓",
                    extraction_source="deterministic_fixture",
                )
        
        # Stock research - has stock code or stock research language
        if prescan.detected_stock_code or prescan.has_stock_research_language:
            # Extract company name from message
            import re
            
            # Remove detected stock code from message first
            message_no_code = user_message
            if prescan.detected_stock_code:
                message_no_code = re.sub(r'\d{6}(\.(SH|SZ|BJ))?', '', user_message)
            
            # Remove noise words first
            noise_words = [
                '帮我看一下', '是否值得买入', '朋友推荐了', '朋友推荐', '代码', '查一下',
                '值不值得关注', '帮我查', '看看', '分析', '研究', '怎么样',
                '如何', '好不好', '能不能买', '能不能做', '可以买吗', '适不适合', '适合',
                '值得', '买入', '是否', '一下', '帮我', '可以', '可以吗',
                '看一下', '查一下', '我朋友', '帮我看', '看'
            ]
            
            cleaned_message = message_no_code
            for noise in noise_words:
                cleaned_message = cleaned_message.replace(noise, ' ')
            
            # Remove punctuation and extra spaces
            cleaned_message = re.sub(r'[，。、；：？！（）\s]+', ' ', cleaned_message)
            cleaned_message = cleaned_message.strip()
            
            # Extract Chinese company name from cleaned message
            company_pattern = r'[\u4e00-\u9fa5]{2,12}'
            company_matches = re.findall(company_pattern, cleaned_message)
            
            # Pick longest match as company name
            extracted_company = None
            if company_matches:
                # Sort by length descending
                company_matches.sort(key=len, reverse=True)
                extracted_company = company_matches[0].strip()
            
            return WorkbenchIntentExtraction(
                primary_intent="stock_research",
                intent_candidates=["stock_research"],
                extracted_company_name=extracted_company,
                extracted_stock_code=prescan.detected_stock_code,
                confidence="high" if prescan.detected_stock_code else "medium",
                extraction_source="deterministic_fixture",
            )
        
        # Unknown
        return WorkbenchIntentExtraction(
            primary_intent="unknown",
            intent_candidates=["unknown"],
            confidence="low",
            ambiguity_reason="无法判断用户意图，缺少明确的股票、策略或执行反馈信号",
            extraction_source="deterministic_fixture",
        )
