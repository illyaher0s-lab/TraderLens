"""
Live Execution Feedback Handler

Implements handle_execution_feedback for Workbench.
User reports "已买入100股成交价12.34" or "已卖出100股成交价13.00".
Buy: creates execution_observation_log and observation_position.
Sell: creates sell log, closes position, generates P&L and discipline review.
"""

import json
import re
import uuid
from datetime import datetime

from backend.db.agent_workbench import ArtifactRef, attach_artifact_ref
from backend.db.live_trade import LiveTradeDB
from contracts.live_trade import (
    DisciplineReview,
    ExecutionObservationLog,
    ExplanationSource,
    ObservationPosition,
    PlanAdherenceResult,
    PnlRecord,
    PnlSource,
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
    
    User reports buy or sell execution.
    Buy: create execution log and observation position.
    Sell: create sell log, close position, generate P&L and review.
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
    price_match = re.search(r'成交价[：:]*\s*(\d+\.?\d*)', user_message)
    quantity_match = re.search(r'(\d+)\s*股', user_message)
    
    if not price_match or not quantity_match:
        agent_reply = "请提供完整的交易信息：数量（多少股）和成交价格（多少元）。"
        
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
    
    # Detect action: buy or sell
    is_sell = re.search(r'已卖出|卖出|sell', user_message, re.IGNORECASE)
    
    from backend.config.runtime_paths import get_live_trade_db_path
    live_db = LiveTradeDB(get_live_trade_db_path())
    
    if is_sell:
        return _handle_sell(
            db_conn,
            conversation_id,
            user_message,
            stock_identity,
            confirmed_price,
            confirmed_quantity,
            live_db,
            now,
        )
    else:
        return _handle_buy(
            db_conn,
            conversation_id,
            user_message,
            stock_identity,
            confirmed_price,
            confirmed_quantity,
            live_db,
            now,
        )


def _handle_buy(
    db_conn,
    conversation_id: str,
    user_message: str,
    stock_identity,
    confirmed_price: float,
    confirmed_quantity: int,
    live_db: LiveTradeDB,
    now: datetime,
) -> HandlerResult:
    """Handle buy execution."""
    artifact_ids = []
    
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
    attach_artifact_ref(db_conn, log_artifact, content=json.dumps({"log_id": log_id, "position_id": position_id}))
    artifact_ids.append(log_id)
    
    position_artifact = ArtifactRef(
        artifact_ref_id=f"artref_{uuid.uuid4().hex[:12]}",
        session_id=conversation_id,
        artifact_id=position_id,
        artifact_type="observation_position",
        created_at=now,
    )
    attach_artifact_ref(db_conn, position_artifact, content=json.dumps({"position_id": position_id}))
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
        f"已记录买入：\n"
        f"股票：{stock_identity.company_name} ({stock_identity.ticker})\n"
        f"数量：{confirmed_quantity} 股\n"
        f"成交价：¥{confirmed_price:.2f}\n\n"
        f"持仓已进入观察池，你可以在 /observations 查看。"
    )
    
    return HandlerResult(
        agent_reply=agent_reply,
        artifact_ids=artifact_ids,
    )


def _handle_sell(
    db_conn,
    conversation_id: str,
    user_message: str,
    stock_identity,
    confirmed_price: float,
    confirmed_quantity: int,
    live_db: LiveTradeDB,
    now: datetime,
) -> HandlerResult:
    """Handle sell execution: create sell log, close position, generate P&L and review."""
    artifact_ids = []
    
    # Find open position for this stock
    open_position = live_db.find_open_position_by_symbol(stock_identity.ticker)
    
    if not open_position:
        agent_reply = f"没有找到 {stock_identity.company_name} ({stock_identity.ticker}) 的持仓记录。"
        return HandlerResult(
            agent_reply=agent_reply,
            artifact_ids=artifact_ids,
        )
    
    # Create sell log (reuse position's evidence chain)
    sell_log_id = f"log_{uuid.uuid4().hex[:12]}"
    
    sell_log = ExecutionObservationLog(
        log_id=sell_log_id,
        draft_id=f"draft_{uuid.uuid4().hex[:12]}",
        execution_card_id=open_position.execution_card_id,
        signal_id=open_position.signal_id,
        action_plan_id=open_position.action_plan_id,
        capital_context_id=open_position.capital_context_id,
        market_snapshot_id=f"snap_{uuid.uuid4().hex[:12]}",
        confirmed_action="sell",
        confirmed_execution_status="filled",
        confirmed_price=confirmed_price,
        confirmed_quantity=confirmed_quantity,
        reason=f"用户反馈：{user_message}",
        confirmed_by_user=True,
        broker_verified=False,
        confirmed_at=now,
    )
    
    live_db.save_log(sell_log)
    
    # Close position
    live_db.close_position(open_position.position_id, now)
    
    # Generate P&L record (deterministic calculation)
    pnl_amount = (confirmed_price - open_position.entry_price) * confirmed_quantity
    pnl_pct = ((confirmed_price - open_position.entry_price) / open_position.entry_price) * 100
    
    pnl_record = PnlRecord(
        pnl_record_id=f"pnl_{uuid.uuid4().hex[:12]}",
        position_id=open_position.position_id,
        buy_price=open_position.entry_price,
        sell_price=confirmed_price,
        quantity=confirmed_quantity,
        fees=None,
        pnl_amount=round(pnl_amount, 2),
        pnl_pct=round(pnl_pct, 2),
        pnl_source=PnlSource.calculated_from_confirmed_details,
        missing_fields=[],
        computed_at=now,
    )
    
    # Generate discipline review (honest: unclassified if no attribution evidence)
    plan_adherence = PlanAdherenceResult(
        followed_plan=None,  # Undetermined: no plan to compare against
        deviations=[],
        adherence_trace={"note": "no_action_plan_available"},
    )
    
    review_id = f"review_{uuid.uuid4().hex[:12]}"
    
    review = DisciplineReview(
        review_id=review_id,
        position_id=open_position.position_id,
        execution_card_id=open_position.execution_card_id,
        signal_id=open_position.signal_id,
        daily_signal_ids=[],
        buy_log_id=open_position.source_log_id,
        sell_log_id=sell_log_id,
        input_completeness={
            "execution_card": "present",
            "buy_log": "present",
            "sell_log": "present",
            "daily_signals": "missing",
            "action_plan": "missing",
        },
        pnl_record=pnl_record,
        plan_adherence=plan_adherence,
        plain_narrative=None,  # No LLM explanation for honest unclassified
        narrative_source=ExplanationSource.none,
        forward_looking_guard_passed=True,
        created_at=now,
    )
    
    live_db.save_discipline_review(review)
    
    # Create artifacts
    sell_log_artifact = ArtifactRef(
        artifact_ref_id=f"artref_{uuid.uuid4().hex[:12]}",
        session_id=conversation_id,
        artifact_id=sell_log_id,
        artifact_type="execution_observation_log",
        created_at=now,
    )
    attach_artifact_ref(db_conn, sell_log_artifact, content=json.dumps({"log_id": sell_log_id, "action": "sell"}))
    artifact_ids.append(sell_log_id)
    
    review_artifact = ArtifactRef(
        artifact_ref_id=f"artref_{uuid.uuid4().hex[:12]}",
        session_id=conversation_id,
        artifact_id=review_id,
        artifact_type="discipline_review",
        created_at=now,
    )
    attach_artifact_ref(db_conn, review_artifact, content=json.dumps({"review_id": review_id, "pnl": pnl_record.model_dump(mode='json')}))
    artifact_ids.append(review_id)
    
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
        f"已记录卖出：\n"
        f"股票：{stock_identity.company_name} ({stock_identity.ticker})\n"
        f"数量：{confirmed_quantity} 股\n"
        f"成交价：¥{confirmed_price:.2f}\n\n"
        f"持仓已平仓，盈亏：¥{pnl_amount:.2f} ({pnl_pct:+.2f}%)\n"
        f"你可以在 /observations?status=closed 查看已平仓记录。"
    )
    
    return HandlerResult(
        agent_reply=agent_reply,
        artifact_ids=artifact_ids,
    )
