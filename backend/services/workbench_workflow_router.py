"""
Workbench Workflow Router - Deterministic routing decision

Task 20A: Final workflow routing based on prescan + intent + stock identity.

Rules:
- Stock identity verified -> friend_stock (priority)
- Stock entity + "买入/卖出" -> friend_stock (not strategy_idea)
- Strategy rule shape + no verified stock -> strategy_idea
- LLM intent is advisory, not final decision
- Routing is deterministic based on available evidence
"""

from typing import Literal
from pydantic import BaseModel
from backend.services.workbench_prescan import WorkbenchPreScan
from backend.services.workbench_intent_extractor import WorkbenchIntentExtraction
from backend.services.stock_identity_resolver import StockIdentityResolution


class WorkbenchRouteDecision(BaseModel):
    """Final workflow routing decision."""
    workflow_kind: Literal[
        "friend_stock",
        "theme_research",
        "strategy_idea",
        "execution_feedback",
        "position_followup",
        "review_request",
        "unknown"
    ]
    workflow_state: str
    route_reason: str
    next_required_user_action: str
    allowed_to_start_workflow: bool


class WorkbenchWorkflowRouter:
    """
    Deterministic workflow router.
    
    Makes final routing decision based on:
    - PreScan results (fast patterns)
    - Intent extraction (LLM semantic understanding)
    - Stock identity resolution (Tushare verification)
    """
    
    def route(
        self,
        prescan: WorkbenchPreScan,
        intent_extraction: WorkbenchIntentExtraction,
        stock_identity: StockIdentityResolution,
        open_positions: list = None,
    ) -> WorkbenchRouteDecision:
        """
        Make final workflow routing decision.
        
        Routing rules (priority order):
        1. Execution feedback detected -> execution_feedback
        2. Stock identity verified -> friend_stock
        3. Stock entity + research language -> friend_stock
        4. Stock ambiguous/not_found/data_fault -> clarification/stopped
        5. Strategy rule shape -> strategy_idea
        6. Unknown -> clarification
        
        Args:
            prescan: PreScan result
            intent_extraction: Intent extraction result
            stock_identity: Stock identity resolution result
            
        Returns:
            WorkbenchRouteDecision with final routing
        """
        # Rule 1: Execution feedback detected -> execution_feedback (highest priority)
        if prescan.detected_execution_action:
            return WorkbenchRouteDecision(
                workflow_kind="execution_feedback",
                workflow_state="created",
                route_reason="检测到执行反馈",
                next_required_user_action="confirm_execution_details",
                allowed_to_start_workflow=True,
            )
        
        # Rule 2: Stock identity verified -> friend_stock
        if stock_identity.status == "verified":
            return WorkbenchRouteDecision(
                workflow_kind="friend_stock",
                workflow_state="created",
                route_reason=f"股票身份已确认：{stock_identity.company_name} ({stock_identity.ticker})",
                next_required_user_action="wait_for_research",
                allowed_to_start_workflow=True,
            )
        
        # Rule 3: Stock identity issues
        if stock_identity.status == "ambiguous":
            return WorkbenchRouteDecision(
                workflow_kind="friend_stock",
                workflow_state="waiting_for_clarification",
                route_reason=f"找到多个匹配：{len(stock_identity.candidates)} 个候选",
                next_required_user_action="clarify_company",
                allowed_to_start_workflow=False,
            )
        
        if stock_identity.status == "not_found":
            return WorkbenchRouteDecision(
                workflow_kind="unknown",
                workflow_state="stopped",
                route_reason=f"无法识别股票：{stock_identity.fault_reason}",
                next_required_user_action="provide_valid_stock",
                allowed_to_start_workflow=False,
            )
        
        if stock_identity.status == "data_fault":
            return WorkbenchRouteDecision(
                workflow_kind="unknown",
                workflow_state="stopped",
                route_reason=f"数据源故障：{stock_identity.fault_reason}",
                next_required_user_action="retry_later",
                allowed_to_start_workflow=False,
            )
        
        if stock_identity.status == "unsupported_exchange":
            return WorkbenchRouteDecision(
                workflow_kind="unknown",
                workflow_state="stopped",
                route_reason=stock_identity.fault_reason,
                next_required_user_action="provide_supported_exchange",
                allowed_to_start_workflow=False,
            )
        
        # Rule 4: Position followup
        if intent_extraction.primary_intent == "position_followup":
            # Check if user has open positions
            if not open_positions or len(open_positions) == 0:
                # No open positions - cannot follow up
                return WorkbenchRouteDecision(
                    workflow_kind="unknown",
                    workflow_state="created",
                    route_reason="检测到持仓跟进请求，但当前无持仓",
                    next_required_user_action="clarify_intent_or_provide_context",
                    allowed_to_start_workflow=False,
                )
            return WorkbenchRouteDecision(
                workflow_kind="position_followup",
                workflow_state="created",
                route_reason="检测到持仓跟进请求",
                next_required_user_action="provide_context_or_clarify",
                allowed_to_start_workflow=True,
            )
        
        # Rule 5: Strategy rule shape -> strategy_idea
        # Important: Only route to strategy_idea if has clear strategy rule shape
        # NOT if just has "买入/卖出" with stock context
        if prescan.has_strategy_rule_shape and not prescan.has_stock_research_language:
            return WorkbenchRouteDecision(
                workflow_kind="strategy_idea",
                workflow_state="created",
                route_reason="检测到策略规则结构",
                next_required_user_action="wait_for_extraction",
                allowed_to_start_workflow=True,
            )
        
        # Rule 6: Stock research intent but no stock entity -> clarification
        if intent_extraction.primary_intent == "stock_research":
            if stock_identity.status == "not_applicable":
                # No stock code or company name extracted
                return WorkbenchRouteDecision(
                    workflow_kind="unknown",
                    workflow_state="created",
                    route_reason="理解为股票研究请求，但缺少公司名或代码（需要 session context 或用户明确）",
                    next_required_user_action="provide_stock_code_or_name",
                    allowed_to_start_workflow=False,
                )
        
        # Rule 7: Unknown intent -> clarification
        return WorkbenchRouteDecision(
            workflow_kind="unknown",
            workflow_state="created",
            route_reason="无法判断用户意图",
            next_required_user_action="clarify_intent",
            allowed_to_start_workflow=False,
        )
