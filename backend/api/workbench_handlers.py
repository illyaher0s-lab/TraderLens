"""
Workbench message handlers - single responsibility per workflow kind.

Each handler receives route_decision and pipeline artifacts, returns agent_reply and artifact_ids.
Handlers do NOT read session.workflow_kind for business logic - only route_decision.workflow_kind.
"""

import json
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
    validator,
    serenity_runner,
    market_data_provider,
) -> HandlerResult:
    """
    Handle friend_stock workflow.

    MUST NOT handle execution_feedback or position_followup - those have dedicated handlers.
    """
    from backend.services.friend_stock_flow import FriendStockFlowService
    
    artifact_ids = []
    
    if stock_identity.status != "verified":
        # Stock not verified - cannot create flow
        agent_reply = f"无法识别股票信息。{route_decision.route_reason}"
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
    
    # Check if serenity_runner is configured
    # If not configured, status = waiting (not fake researching)
    if serenity_runner is None:
        flow_status = "waiting"
        agent_reply_suffix = "研究服务未配置，已记录为待研究。"
    else:
        # Check if it's a stub runner
        from backend.services.serenity_stub import SerenityStubRunner
        if isinstance(serenity_runner, SerenityStubRunner):
            flow_status = "waiting"
            agent_reply_suffix = "当前为测试模式，已记录为待研究。"
        else:
            # Real runner available - can start research
            # For now, still mark as waiting until we implement job dispatch
            flow_status = "waiting"
            agent_reply_suffix = "已创建研究记录，等待研究服务启动。"
    
    # Create friend_stock_flow record directly in DB
    # Service is used for complex orchestration (verify_ticker, run_industry_research, etc.)
    # For workbench, we only need to record the flow entry
    from backend.db.research import ResearchDB
    
    flow_id = f"flow_{uuid.uuid4().hex[:12]}"
    
    # Get ResearchDB instance from connection
    # The connection is db.conn, we need the ResearchDB instance
    # We'll directly insert via SQL for now (workbench creates simple flow records)
    import sqlite3
    from datetime import datetime as dt
    now_iso = dt.now().isoformat()
    
    cursor = db_conn.cursor()
    cursor.execute("""
        INSERT INTO friend_stock_flows
        (flow_id, raw_company_input, raw_code_input, source_note,
         ticker_verification_result, research_output, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        flow_id,
        stock_identity.company_name,
        stock_identity.ticker,
        f"workbench: {user_message}",
        None,  # No ticker verification needed (already verified by stock_identity)
        None,  # No research output yet
        flow_status,  # waiting (not fake researching)
        now_iso,
        now_iso,
    ))
    db_conn.commit()
    
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
    
    agent_reply = f"已识别 {stock_identity.company_name} ({stock_identity.ticker})。{agent_reply_suffix} 研究ID: {flow_id}"
    
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
    strategy_flow_service=None,  # New: for test injection
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
    
    if strategy_flow_service is None:
        flow_service = StrategyIdeaFlowService()
    else:
        flow_service = strategy_flow_service
    
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
        
        extraction_result = flow_service.extract_claims(idea)
        extraction_content = json.dumps({
            "extraction_id": extraction_result.extraction_id,
            "idea_id": extraction_result.idea_id,
            "claimed_entry": extraction_result.claimed_entry,
            "claimed_exit": extraction_result.claimed_exit,
            "claimed_edge": extraction_result.claimed_edge,
            "extraction_source": extraction_result.extraction_source,
        })
        extraction_artifact = ArtifactRef(
            artifact_ref_id=f"artref_{uuid.uuid4().hex[:12]}",
            session_id=conversation_id,
            artifact_id=extraction_result.extraction_id,
            artifact_type="strategy_idea_extraction",
            created_at=now,
        )
        attach_artifact_ref(db_conn, extraction_artifact, content=extraction_content)
        artifact_ids.append(extraction_result.extraction_id)

        mapping_result = flow_service.map_to_template(
            idea=idea,
            matched_template_id=None,
            template_version=None,
            mapping_reason="当前系统暂无已批准模板库。",
        )
        mapping_content = json.dumps({
            "mapping_id": mapping_result.mapping_id,
            "idea_id": mapping_result.idea_id,
            "path_type": mapping_result.path_type,
            "matched_template_id": mapping_result.matched_template_id,
            "template_version": mapping_result.template_version,
            "mapping_reason": mapping_result.mapping_reason,
            "live_eligible": mapping_result.live_eligible,
        })
        mapping_artifact = ArtifactRef(
            artifact_ref_id=f"artref_{uuid.uuid4().hex[:12]}",
            session_id=conversation_id,
            artifact_id=mapping_result.mapping_id,
            artifact_type="strategy_template_mapping",
            created_at=now,
        )
        attach_artifact_ref(db_conn, mapping_artifact, content=mapping_content)
        artifact_ids.append(mapping_result.mapping_id)

        rejected_entry = flow_service.reject_idea(
            idea=idea,
            reason="no_approved_template",
        )
        rejection_artifact_id = f"{rejected_entry['idea_id']}_rejected"
        # Convert datetime to ISO string for JSON serialization
        rejection_content_dict = rejected_entry.copy()
        if 'rejected_at' in rejection_content_dict and hasattr(rejection_content_dict['rejected_at'], 'isoformat'):
            rejection_content_dict['rejected_at'] = rejection_content_dict['rejected_at'].isoformat()
        rejection_content = json.dumps(rejection_content_dict)
        rejection_artifact = ArtifactRef(
            artifact_ref_id=f"artref_{uuid.uuid4().hex[:12]}",
            session_id=conversation_id,
            artifact_id=rejection_artifact_id,
            artifact_type="strategy_idea_rejected",
            created_at=now,
        )
        attach_artifact_ref(db_conn, rejection_artifact, content=rejection_content)
        artifact_ids.append(rejection_artifact_id)

        action_completed_artifact = ArtifactRef(
            artifact_ref_id=f"artref_{uuid.uuid4().hex[:12]}",
            session_id=conversation_id,
            artifact_id=f"action_completed_{uuid.uuid4().hex[:8]}",
            artifact_type="workflow_action_completed",
            created_at=now,
        )
        attach_artifact_ref(db_conn, action_completed_artifact)

        agent_reply = (
            "已提取策略想法：\n"
            f"入场条件：{extraction_result.claimed_entry}\n"
            f"出场条件：{extraction_result.claimed_exit}\n"
            "当前系统暂无已批准模板库。策略想法已记录，但不可用于实盘交易。\n"
            "该策略想法已记录到拒绝注册表，不会生成交易信号。"
        )
        
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


def handle_position_followup(
    db_conn,
    conversation_id: str,
    user_message: str,
    stock_identity,
    route_decision,
    now: datetime,
    open_positions: list | None = None,
) -> HandlerResult:
    """
    Handle position_followup workflow.
    
    User asks "今天要不要继续拿" - need to check open positions.
    Without position context, must clarify which stock.
    """
    artifact_ids = []
    
    open_positions = open_positions or []
    
    if stock_identity.status != "verified" and not open_positions:
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
    
    # Stock verified or a single open position is available from session context.
    open_position = None
    if stock_identity.status == "verified":
        for position in open_positions:
            if position.get("symbol") == stock_identity.ticker:
                open_position = position
                break
    elif len(open_positions) == 1:
        open_position = open_positions[0]

    open_position_id = open_position.get("position_id") if open_position else None

    if not open_position_id:
        if stock_identity.status == "verified":
            agent_reply = f"我没有找到 {stock_identity.company_name} ({stock_identity.ticker}) 的持仓记录。"
        else:
            agent_reply = "我找到了多个或不明确的持仓上下文，请告诉我是哪只股票。"
        
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
    
    symbol = open_position.get("symbol", stock_identity.ticker if stock_identity.status == "verified" else "")
    name = open_position.get("name", stock_identity.company_name if stock_identity.status == "verified" else "")
    agent_reply = f"已找到 {name} ({symbol}) 的持仓 {open_position_id}。持仓跟进记录：{followup_id}"
    
    return HandlerResult(
        agent_reply=agent_reply,
        artifact_ids=[open_position_id] + artifact_ids,
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
    
    agent_reply = f"{route_decision.route_reason}\n\n你好，我可以帮你：\n1. 分析朋友推荐的股票（提供股票代码或公司名）\n2. 验证策略/交易想法的技术细节\n\n请问你想了解什么？"
    
    return HandlerResult(
        agent_reply=agent_reply,
        artifact_ids=artifact_ids,
        next_required_user_action="provide_clear_intent",
    )


def handle_add_to_observation(
    db_conn,
    conversation_id: str,
    user_message: str,
    claimed_stock: dict | None,
    route_decision,
    now: datetime,
) -> HandlerResult:
    """
    Handle add_to_observation workflow.
    
    User inputs "加入观察" after friend_stock research.
    Requires claimed_stock from session context.
    Creates observation_position with lifecycle_state=open.
    """
    from backend.db.live_trade import LiveTradeDB
    from contracts.live_trade import ObservationPosition, PositionLifecycleState
    from pathlib import Path
    
    artifact_ids = []
    
    # Check if we have claimed_stock from session context
    if not claimed_stock or not claimed_stock.get("ticker"):
        # No stock context - must clarify
        agent_reply = "我需要知道是哪只股票。请先告诉我股票代码或公司名。"
        
        clarify_artifact = ArtifactRef(
            artifact_ref_id=f"artref_{uuid.uuid4().hex[:12]}",
            session_id=conversation_id,
            artifact_id=f"clarify_{uuid.uuid4().hex[:8]}",
            artifact_type="add_to_observation_clarification",
            created_at=now,
        )
        attach_artifact_ref(db_conn, clarify_artifact)
        artifact_ids.append(clarify_artifact.artifact_id)
        
        return HandlerResult(
            agent_reply=agent_reply,
            artifact_ids=artifact_ids,
            next_required_user_action="provide_stock_for_observation",
        )
    
    # Extract stock info from claimed_stock
    ticker = claimed_stock.get("ticker")
    company_name = claimed_stock.get("company_name", ticker)
    original_context = claimed_stock.get("original_context", "")  # May contain run_id
    
    # Create observation position
    position_id = f"pos_{uuid.uuid4().hex[:12]}"
    
    # Build entry_thesis from user message, claimed stock, and original context
    if original_context:
        entry_thesis = f"用户请求加入观察池：{company_name}（{ticker}）。原始上下文：{original_context}。当前输入：{user_message}"
    else:
        entry_thesis = f"用户请求加入观察池：{company_name}（{ticker}）。原始输入：{user_message}"
    
    # Friend stock observation has no real execution chain - use sentinel values
    # These are NOT fake execution records, they mark "no execution chain" explicitly
    execution_card_id = "friend_stock_no_exec_card"
    signal_id = "friend_stock_no_signal"
    action_plan_id = "friend_stock_no_plan"
    capital_context_id = "friend_stock_no_capital"
    
    # Create position record with sentinel values (not fake execution data)
    position = ObservationPosition(
        position_id=position_id,
        source_log_id="friend_stock_observation",  # Explicit marker: not from execution log
        execution_card_id=execution_card_id,
        signal_id=signal_id,
        action_plan_id=action_plan_id,
        capital_context_id=capital_context_id,
        symbol=ticker,
        name=company_name,
        entry_price=0.01,  # Sentinel price (observation-only, no real entry)
        quantity=1,  # Sentinel quantity (observation-only, no real position)
        template_id="",
        template_version="",
        entry_thesis=entry_thesis,
        lifecycle_state=PositionLifecycleState.open,
        opened_at=now,
        closed_at=None,
    )
    
    # Save to live_trade.db
    live_trade_db_path = Path("data/live_trade.db")
    live_trade_db = LiveTradeDB(live_trade_db_path)
    live_trade_db.save_position(position)
    
    # Create position artifact
    position_artifact = ArtifactRef(
        artifact_ref_id=f"artref_{uuid.uuid4().hex[:12]}",
        session_id=conversation_id,
        artifact_id=position_id,
        artifact_type="observation_position",
        created_at=now,
    )
    attach_artifact_ref(db_conn, position_artifact)
    artifact_ids.append(position_id)
    
    agent_reply = f"已将 {company_name}（{ticker}）加入观察池。观察位置ID：{position_id}"
    
    return HandlerResult(
        agent_reply=agent_reply,
        artifact_ids=artifact_ids,
        next_required_user_action=None,
    )
