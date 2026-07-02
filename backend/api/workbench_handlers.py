"""
Workbench message handlers - single responsibility per workflow kind.

Each handler receives route_decision and pipeline artifacts, returns agent_reply and artifact_ids.
Handlers do NOT read session.workflow_kind for business logic - only route_decision.workflow_kind.
"""

import uuid
from datetime import datetime
from typing import Tuple

from backend.db.agent_workbench import ArtifactRef, attach_artifact_ref


class HandlerResult:
    """Handler return value."""
    def __init__(
        self,
        agent_reply: str,
        artifact_ids: list[str],
        next_required_user_action: str | None = None,
    ):
        self.agent_reply = agent_reply
        self.artifact_ids = artifact_ids
        self.next_required_user_action = next_required_user_action


def handle_friend_stock(
    db_conn,
    conversation_id: str,
    user_message: str,
    stock_identity,
    route_decision,
    now: datetime,
) -> HandlerResult:
    """
    Handle friend_stock workflow.
    
    MUST NOT handle execution_feedback or position_followup - those have dedicated handlers.
    """
    from backend.services.friend_stock_flow import FriendStockFlowService
    
    artifact_ids = []
    
    if stock_identity.status != "verified":
        # Stock not verified - cannot create flow
        agent_reply = f"无法识别股票信息。{route_decision.reason}"
        return HandlerResult(
            agent_reply=agent_reply,
            artifact_ids=artifact_ids,
            next_required_user_action="provide_stock_code_or_name",
        )
    
    # Record workflow action started
    action_started_artifact = ArtifactRef(
        artifact_ref_id=f"artref_{uuid.uuid4().hex[:12]}",
        session_id=conversation_id,
        artifact_id=f"action_started_{uuid.uuid4().hex[:8]}",
        artifact_type="workflow_action_started",
        created_at=now,
    )
    attach_artifact_ref(db_conn, action_started_artifact)
    
    # Create friend_stock_flow record
    flow_service = FriendStockFlowService(
        db_conn=db_conn,
        serenity_runner=None,  # Stub mode
    )
    
    flow_entry = flow_service.create_flow(
        ticker=stock_identity.ticker,
        company_name=stock_identity.company_name,
        source_channel="workbench",
        raw_source_text=user_message,
    )
    
    flow_id = flow_entry["flow_id"]
    
    # Create flow artifact
    flow_artifact = ArtifactRef(
        artifact_ref_id=f"artref_{uuid.uuid4().hex[:12]}",
        session_id=conversation_id,
        artifact_id=flow_id,
        artifact_type="friend_stock_flow",
        created_at=now,
    )
    attach_artifact_ref(db_conn, flow_artifact)
    artifact_ids.append(flow_id)
    
    # Record workflow action completed
    action_completed_artifact = ArtifactRef(
        artifact_ref_id=f"artref_{uuid.uuid4().hex[:12]}",
        session_id=conversation_id,
        artifact_id=f"action_completed_{uuid.uuid4().hex[:8]}",
        artifact_type="workflow_action_completed",
        created_at=now,
    )
    attach_artifact_ref(db_conn, action_completed_artifact)
    
    agent_reply = f"已识别 {stock_identity.company_name} ({stock_identity.ticker})，已创建调研记录。{flow_id}"
    
    return HandlerResult(
        agent_reply=agent_reply,
        artifact_ids=artifact_ids,
        next_required_user_action=None,
    )


def handle_strategy_idea(
    db_conn,
    conversation_id: str,
    user_message: str,
    route_decision,
    now: datetime,
) -> HandlerResult:
    """Handle strategy_idea workflow."""
    from backend.services.strategy_idea_flow import StrategyIdeaFlowService
    
    artifact_ids = []
    
    # Record workflow action started
    action_started_artifact = ArtifactRef(
        artifact_ref_id=f"artref_{uuid.uuid4().hex[:12]}",
        session_id=conversation_id,
        artifact_id=f"action_started_{uuid.uuid4().hex[:8]}",
        artifact_type="workflow_action_started",
        created_at=now,
    )
    attach_artifact_ref(db_conn, action_started_artifact)
    
    flow_service = StrategyIdeaFlowService()
    
    try:
        # Create strategy idea (defaults to untrusted)
        idea = flow_service.create_idea(
            raw_source_text=user_message,
            source_channel="workbench",
        )
        
        # Create strategy_idea artifact
        idea_artifact = ArtifactRef(
            artifact_ref_id=f"artref_{uuid.uuid4().hex[:12]}",
            session_id=conversation_id,
            artifact_id=idea.idea_id,
            artifact_type="strategy_idea",
            created_at=now,
        )
        attach_artifact_ref(db_conn, idea_artifact)
        artifact_ids.append(idea.idea_id)
        
        # Try to extract and map to template
        extraction_result = flow_service.extract_idea_details(user_message)
        
        if extraction_result:
            # Create extraction artifact
            extraction_artifact = ArtifactRef(
                artifact_ref_id=f"artref_{uuid.uuid4().hex[:12]}",
                session_id=conversation_id,
                artifact_id=f"{idea.idea_id}_extraction",
                artifact_type="strategy_idea_extraction",
                created_at=now,
            )
            attach_artifact_ref(db_conn, extraction_artifact)
            artifact_ids.append(f"{idea.idea_id}_extraction")
            
            mapping_result = flow_service.map_to_template(extraction_result)
            
            if mapping_result and mapping_result.get("template_key"):
                agent_reply = f"已识别策略想法并映射到模板 {mapping_result['template_key']}。想法记录：{idea.idea_id}"
            else:
                # Extraction succeeded but no template match -> rejected
                rejected_entry = flow_service.reject_idea(
                    idea_id=idea.idea_id,
                    reason="no_template_match",
                )
                
                rejection_artifact = ArtifactRef(
                    artifact_ref_id=f"artref_{uuid.uuid4().hex[:12]}",
                    session_id=conversation_id,
                    artifact_id=rejected_entry["idea_id"] + "_rejected",
                    artifact_type="strategy_idea_rejected",
                    created_at=now,
                )
                attach_artifact_ref(db_conn, rejection_artifact)
                artifact_ids.append(rejected_entry["idea_id"] + "_rejected")
                
                # Record workflow action completed (rejected)
                action_completed_artifact = ArtifactRef(
                    artifact_ref_id=f"artref_{uuid.uuid4().hex[:12]}",
                    session_id=conversation_id,
                    artifact_id=f"action_completed_{uuid.uuid4().hex[:8]}",
                    artifact_type="workflow_action_completed",
                    created_at=now,
                )
                attach_artifact_ref(db_conn, action_completed_artifact)
                
                agent_reply = f"策略想法已记录但无法匹配现有模板，已标记为待审核。想法记录：{idea.idea_id}"
        else:
            # Extraction failed
            agent_reply = f"策略想法已记录，但提取详情失败。想法记录：{idea.idea_id}"
        
        # Record workflow action completed (if not already done in rejection)
        if "rejected" not in agent_reply:
            action_completed_artifact = ArtifactRef(
                artifact_ref_id=f"artref_{uuid.uuid4().hex[:12]}",
                session_id=conversation_id,
                artifact_id=f"action_completed_{uuid.uuid4().hex[:8]}",
                artifact_type="workflow_action_completed",
                created_at=now,
            )
            attach_artifact_ref(db_conn, action_completed_artifact)
        
    except Exception as e:
        # Record workflow action failed
        action_failed_artifact = ArtifactRef(
            artifact_ref_id=f"artref_{uuid.uuid4().hex[:12]}",
            session_id=conversation_id,
            artifact_id=f"action_failed_{uuid.uuid4().hex[:8]}",
            artifact_type="workflow_action_failed",
            created_at=now,
        )
        attach_artifact_ref(db_conn, action_failed_artifact)
        
        agent_reply = f"策略想法处理失败：{str(e)}"
    
    return HandlerResult(
        agent_reply=agent_reply,
        artifact_ids=artifact_ids,
        next_required_user_action=None,
    )


def handle_execution_feedback(
    db_conn,
    conversation_id: str,
    user_message: str,
    stock_identity,
    route_decision,
    now: datetime,
) -> HandlerResult:
    """
    Handle execution_feedback workflow.
    
    User reports "已买入100股成交价12.34" - need to verify against pending approval or position.
    Without context, must clarify which stock.
    """
    artifact_ids = []
    
    # TODO: Check for pending approvals or recent research
    # For now, since we have no approval/position context, always clarify
    
    if stock_identity.status != "verified":
        # No stock identity - must clarify
        agent_reply = "我没有建议你买入任何股票。请告诉我这是哪只股票的交易？（提供股票代码或公司名）"
        
        # Create clarification artifact
        clarify_artifact = ArtifactRef(
            artifact_ref_id=f"artref_{uuid.uuid4().hex[:12]}",
            session_id=conversation_id,
            artifact_id=f"clarify_{uuid.uuid4().hex[:8]}",
            artifact_type="execution_feedback_clarification",
            created_at=now,
        )
        attach_artifact_ref(db_conn, clarify_artifact)
        artifact_ids.append(clarify_artifact.artifact_id)
        
        return HandlerResult(
            agent_reply=agent_reply,
            artifact_ids=artifact_ids,
            next_required_user_action="clarify_stock_for_execution",
        )
    
    # Stock verified - check for pending approval or position
    # TODO: Query approval/position DB
    
    # Placeholder: create execution log
    execution_log_id = f"exec_log_{uuid.uuid4().hex[:8]}"
    
    exec_log_artifact = ArtifactRef(
        artifact_ref_id=f"artref_{uuid.uuid4().hex[:12]}",
        session_id=conversation_id,
        artifact_id=execution_log_id,
        artifact_type="execution_log",
        created_at=now,
    )
    attach_artifact_ref(db_conn, exec_log_artifact)
    artifact_ids.append(execution_log_id)
    
    agent_reply = f"已记录 {stock_identity.company_name} ({stock_identity.ticker}) 的执行反馈。执行记录：{execution_log_id}"
    
    return HandlerResult(
        agent_reply=agent_reply,
        artifact_ids=artifact_ids,
        next_required_user_action=None,
    )


def handle_position_followup(
    db_conn,
    conversation_id: str,
    user_message: str,
    stock_identity,
    route_decision,
    now: datetime,
) -> HandlerResult:
    """
    Handle position_followup workflow.
    
    User asks "今天要不要继续拿" - need to check open positions.
    Without position context, must clarify which stock.
    """
    artifact_ids = []
    
    # TODO: Check for open positions
    # For now, since we have no position context, always clarify
    
    if stock_identity.status != "verified":
        # No stock identity - must clarify
        agent_reply = "我没有找到你的持仓记录。请告诉我是哪只股票？"
        
        # Create clarification artifact
        clarify_artifact = ArtifactRef(
            artifact_ref_id=f"artref_{uuid.uuid4().hex[:12]}",
            session_id=conversation_id,
            artifact_id=f"clarify_{uuid.uuid4().hex[:8]}",
            artifact_type="position_followup_clarification",
            created_at=now,
        )
        attach_artifact_ref(db_conn, clarify_artifact)
        artifact_ids.append(clarify_artifact.artifact_id)
        
        return HandlerResult(
            agent_reply=agent_reply,
            artifact_ids=artifact_ids,
            next_required_user_action="clarify_stock_for_followup",
        )
    
    # Stock verified - check for open position
    # TODO: Query position DB
    open_position_id = None  # Placeholder
    
    if not open_position_id:
        agent_reply = f"我没有找到 {stock_identity.company_name} ({stock_identity.ticker}) 的持仓记录。"
        
        clarify_artifact = ArtifactRef(
            artifact_ref_id=f"artref_{uuid.uuid4().hex[:12]}",
            session_id=conversation_id,
            artifact_id=f"clarify_{uuid.uuid4().hex[:8]}",
            artifact_type="position_not_found",
            created_at=now,
        )
        attach_artifact_ref(db_conn, clarify_artifact)
        artifact_ids.append(clarify_artifact.artifact_id)
        
        return HandlerResult(
            agent_reply=agent_reply,
            artifact_ids=artifact_ids,
            next_required_user_action="provide_position_details",
        )
    
    # Position found - provide followup advice
    followup_id = f"followup_{uuid.uuid4().hex[:8]}"
    
    followup_artifact = ArtifactRef(
        artifact_ref_id=f"artref_{uuid.uuid4().hex[:12]}",
        session_id=conversation_id,
        artifact_id=followup_id,
        artifact_type="position_followup_advice",
        created_at=now,
    )
    attach_artifact_ref(db_conn, followup_artifact)
    artifact_ids.append(followup_id)
    
    agent_reply = f"已找到 {stock_identity.company_name} ({stock_identity.ticker}) 的持仓。持仓建议：{followup_id}"
    
    return HandlerResult(
        agent_reply=agent_reply,
        artifact_ids=artifact_ids,
        next_required_user_action=None,
    )


def handle_theme_research_deferred(
    db_conn,
    conversation_id: str,
    user_message: str,
    route_decision,
    now: datetime,
) -> HandlerResult:
    """
    Handle theme_research workflow (deferred).
    
    Theme research is not yet implemented - return "暂未开放" message.
    """
    artifact_ids = []
    
    # Create deferred artifact
    deferred_artifact = ArtifactRef(
        artifact_ref_id=f"artref_{uuid.uuid4().hex[:12]}",
        session_id=conversation_id,
        artifact_id=f"deferred_{uuid.uuid4().hex[:8]}",
        artifact_type="theme_research_deferred",
        created_at=now,
    )
    attach_artifact_ref(db_conn, deferred_artifact)
    artifact_ids.append(deferred_artifact.artifact_id)
    
    agent_reply = "主题研究功能暂未开放，敬请期待。"
    
    return HandlerResult(
        agent_reply=agent_reply,
        artifact_ids=artifact_ids,
        next_required_user_action=None,
    )


def handle_clarification(
    db_conn,
    conversation_id: str,
    user_message: str,
    route_decision,
    now: datetime,
) -> HandlerResult:
    """
    Handle clarification / unknown workflow.
    
    Router could not determine intent or needs more information.
    """
    artifact_ids = []
    
    # Create clarification artifact
    clarify_artifact = ArtifactRef(
        artifact_ref_id=f"artref_{uuid.uuid4().hex[:12]}",
        session_id=conversation_id,
        artifact_id=f"clarify_{uuid.uuid4().hex[:8]}",
        artifact_type="clarification_needed",
        created_at=now,
    )
    attach_artifact_ref(db_conn, clarify_artifact)
    artifact_ids.append(clarify_artifact.artifact_id)
    
    agent_reply = f"{route_decision.reason}\n\n你好，我可以帮你：\n1. 分析朋友推荐的股票（提供股票代码或公司名）\n2. 验证策略/交易想法的技术细节\n\n请问你想了解什么？"
    
    return HandlerResult(
        agent_reply=agent_reply,
        artifact_ids=artifact_ids,
        next_required_user_action="provide_clear_intent",
    )
