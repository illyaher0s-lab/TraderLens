"""
Live Execution Feedback Handler

Implements handle_execution_feedback for Workbench.
User reports "已买入100股成交价12.34", system creates execution_observation_log and observation_position.
"""

import json
import uuid
from datetime import datetime

from backend.db.agent_workbench import ArtifactRef, attach_artifact_ref
from backend.db.live_trade import LiveTradeDB
from contracts.live_trade import (
    ExecutionObservationLog,
    ObservationPosition,
    PositionLifecycleState,
)


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
    
    User reports "已买入100股成交价12.34" - create execution log and observation position.
    Requires stock identity from context or explicit mention.
    """
    artifact_ids = []
    
    # Verify stock identity
    if stock_identity.status != "verified":
        agent_reply = "我没有找到你提到的股票。请告诉我这是哪只股票？（提供股票代码或公司名）"
        
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
    
    # Parse execution details from user message
    # TODO: Use LLM or regex to extract price, quantity, action
    # For now, use simple parsing
    import re
    
    price_match = re.search(r'成交价[：:]*\s*(\d+\.?\d*)', user_message)
    quantity_match = re.search(r'(\d+)\s*股', user_message)
    
    if not price_match or not quantity_match:
        agent_reply = "请提供完整的交易信息：买入数量（多少股）和成交价格（多少元）。"
        
        clarify_artifact = ArtifactRef(
            artifact_ref_id=f"artref_{uuid.uuid4().hex[:12]}",
            session_id=conversation_id,
            artifact_id=f"clarify_{uuid.uuid4().hex[:8]}",
            artifact_type="execution_feedback_incomplete",
            created_at=now,
        )
        attach_artifact_ref(db_conn, clarify_artifact)
        artifact_ids.append(clarify_artifact.artifact_id)
        
        return HandlerResult(
            agent_reply=agent_reply,
            artifact_ids=artifact_ids,
            next_required_user_action="provide_execution_details",
        )
    
    confirmed_price = float(price_match.group(1))
    confirmed_quantity = int(quantity_match.group(1))
    
    # Create execution_observation_log
    from backend.config.runtime_paths import get_live_trade_db_path
    live_db = LiveTradeDB(get_live_trade_db_path())
    
    log_id = f"log_{uuid.uuid4().hex[:12]}"
    execution_card_id = f"card_{uuid.uuid4().hex[:12]}"
    signal_id = f"sig_{uuid.uuid4().hex[:12]}"
    action_plan_id = f"plan_{uuid.uuid4().hex[:12]}"
    capital_context_id = f"ctx_{uuid.uuid4().hex[:12]}"
    market_snapshot_id = f"snap_{uuid.uuid4().hex[:12]}"
    
    log = ExecutionObservationLog(
        log_id=log_id,
        draft_id=f"draft_{uuid.uuid4().hex[:12]}",
        execution_card_id=execution_card_id,
        signal_id=signal_id,
        action_plan_id=action_plan_id,
        capital_context_id=capital_context_id,
        market_snapshot_id=market_snapshot_id,
        confirmed_action="buy",
        confirmed_execution_status="filled",
        confirmed_price=confirmed_price,
        confirmed_quantity=confirmed_quantity,
        reason=f"用户反馈：{user_message}",
        confirmed_by_user=True,
        broker_verified=False,
        confirmed_at=now,
    )
    
    live_db.save_log(log)
    
    # Create observation_position
    position_id = f"pos_{uuid.uuid4().hex[:12]}"
    
    position = ObservationPosition(
        position_id=position_id,
        source_log_id=log_id,
        execution_card_id=execution_card_id,
        signal_id=signal_id,
        action_plan_id=action_plan_id,
        capital_context_id=capital_context_id,
        symbol=stock_identity.ticker,
        name=stock_identity.company_name,
        entry_price=confirmed_price,
        quantity=confirmed_quantity,
        template_id="template_execution_feedback_v1",
        template_version="v1",
        entry_thesis=f"用户自主买入：{user_message}",
        lifecycle_state=PositionLifecycleState.open,
        opened_at=now,
        closed_at=None,
    )
    
    live_db.save_position(position)
    
    # Create artifacts for timeline
    log_artifact = ArtifactRef(
        artifact_ref_id=f"artref_{uuid.uuid4().hex[:12]}",
        session_id=conversation_id,
        artifact_id=log_id,
        artifact_type="execution_observation_log",
        created_at=now,
    )
    attach_artifact_ref(db_conn, log_artifact, content={"log_id": log_id, "position_id": position_id})
    artifact_ids.append(log_id)
    
    position_artifact = ArtifactRef(
        artifact_ref_id=f"artref_{uuid.uuid4().hex[:12]}",
        session_id=conversation_id,
        artifact_id=position_id,
        artifact_type="observation_position",
        created_at=now,
    )
    attach_artifact_ref(db_conn, position_artifact, content={"position_id": position_id})
    artifact_ids.append(position_id)
    
    action_completed_artifact = ArtifactRef(
        artifact_ref_id=f"artref_{uuid.uuid4().hex[:12]}",
        session_id=conversation_id,
        artifact_id=f"action_completed_{uuid.uuid4().hex[:8]}",
        artifact_type="workflow_action_completed",
        created_at=now,
    )
    attach_artifact_ref(db_conn, action_completed_artifact)
    artifact_ids.append(action_completed_artifact.artifact_id)
    
    agent_reply = (
        f"已记录买入：\\n"
        f"股票：{stock_identity.company_name} ({stock_identity.ticker})\\n"
        f"数量：{confirmed_quantity} 股\\n"
        f"成交价：¥{confirmed_price:.2f}\\n\\n"
        f"持仓已进入观察池，你可以在 /observations 查看。"
    )
    
    return HandlerResult(
        agent_reply=agent_reply,
        artifact_ids=artifact_ids,
    )
