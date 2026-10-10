"""
Observation Pool API

Provides list and detail endpoints for observation positions.
"""

from fastapi import APIRouter, HTTPException
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.db.live_trade import LiveTradeDB
from contracts.live_trade import (
    ObservationPosition,
    DailyObservationSignal,
    PositionLifecycleState,
    DailySignalType,
    TradeType,
)
from contracts.market_data_fault import MarketDataFaultState


router = APIRouter()
_position_market_monitor = None


class PositionMarketCheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(pattern=r"^[A-Za-z0-9-]{16,64}$")


class VoidExecutionLogRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=160)

    @field_validator("reason")
    @classmethod
    def require_nonblank_reason(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("作废原因必填。")
        return value


def get_live_trade_db() -> LiveTradeDB:
    """Get LiveTradeDB instance with canonical path."""
    from backend.config.runtime_paths import get_live_trade_db_path
    return LiveTradeDB(get_live_trade_db_path())


def get_position_market_monitor():
    global _position_market_monitor
    if _position_market_monitor is None:
        from backend.services.position_market_monitor import PositionMarketMonitor

        _position_market_monitor = PositionMarketMonitor()
    return _position_market_monitor


@router.post("/api/observations/market-check")
def check_position_market(request: PositionMarketCheckRequest):
    """Refresh once for this browser session, then return close-only monitor state."""
    db = get_live_trade_db()
    positions = db.list_open_positions()
    position_logs = [(position, db.get_log(position.source_log_id)) for position in positions]
    return get_position_market_monitor().check_positions(
        position_logs,
        session_id=request.session_id,
    )


@router.get("/api/observations")
def list_observations(status: Optional[str] = None):
    """
    List observation positions.
    
    Query params:
    - status: 'open' | 'closed' | None (all)
    
    Returns list of positions with latest daily signal.
    """
    db = get_live_trade_db()
    
    if status == "open":
        positions = db.list_open_positions()
    elif status == "closed":
        all_positions = db.list_all_positions()
        positions = [p for p in all_positions if p.lifecycle_state == PositionLifecycleState.closed]
    else:
        positions = db.list_all_positions()
    
    # Attach latest daily signal to each position
    result = []
    from zoneinfo import ZoneInfo

    today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    for pos in positions:
        latest_signal = db.get_latest_daily_signal(pos.position_id)
        source_log = db.get_log(pos.source_log_id)
        
        position_dict = {
            "position_id": pos.position_id,
            "symbol": pos.symbol,
            "name": pos.name,
            "entry_price": pos.entry_price,
            "quantity": pos.quantity,
            "entry_thesis": pos.entry_thesis,
            "lifecycle_state": pos.lifecycle_state.value,
            "opened_at": pos.opened_at.isoformat(),
            "execution_date": source_log.execution_date.isoformat() if source_log and source_log.execution_date else None,
            "recorded_at": source_log.confirmed_at.isoformat() if source_log else pos.opened_at.isoformat(),
            "closed_at": pos.closed_at.isoformat() if pos.closed_at else None,
            "template_id": pos.template_id,
            "record_source": pos.record_source,
            "trade_type": pos.trade_type.value,
            "plan_linked": bool(pos.action_plan_id),
            "security_type": source_log.security_type if source_log else "unknown",
            "quantity_unit": source_log.quantity_unit if source_log else "unknown",
            "sellable_quantity": db.get_sellable_quantity(
                symbol=pos.symbol,
                trade_type=pos.trade_type,
                record_source=pos.record_source,
                execution_date=today,
            ) if pos.record_source == "autonomous_manual" and pos.trade_type in {TradeType.actual, TradeType.simulated} else 0,
            "latest_signal": None,
        }
        
        if latest_signal:
            position_dict["latest_signal"] = {
                "signal_type": latest_signal.signal_type.value if latest_signal.signal_type else None,
                "as_of_date": latest_signal.as_of_date.isoformat(),
                "market_data_state": latest_signal.market_data_state.value,
                "plain_explanation": latest_signal.plain_explanation,
                "triggered_invalidations": [t.value for t in latest_signal.triggered_invalidations],
            }
        
        result.append(position_dict)
    
    from backend.services.discipline_review import DisciplineReviewService

    review_service = DisciplineReviewService()
    execution_logs = []
    for row in db.list_execution_logs():
        log = db.get_log(row["log_id"])
        fee_calculation = review_service.calculate_order_fee(log) if log else None
        execution_logs.append({
            "log_id": row["log_id"],
            "execution_date": row["execution_date"],
            "recorded_at": row["confirmed_at"],
            "confirmed_action": row["confirmed_action"],
            "confirmed_price": row["confirmed_price"],
            "confirmed_quantity": row["confirmed_quantity"],
            "confirmed_fees": row["confirmed_fees"],
            "fee_calculation": (
                fee_calculation.model_dump(mode="json") if fee_calculation else None
            ),
            "symbol": row["symbol"],
            "name": row["name"],
            "record_source": row["record_source"],
            "trade_type": row["trade_type"],
            "plan_linked": bool(row["action_plan_id"]),
            "trade_amount": row["confirmed_trade_amount"],
            "security_type": row["security_type"],
            "quantity_unit": row["quantity_unit"],
            "trade_source": row["trade_source"],
            "reason": row["reason"],
            "sell_reason": row["sell_reason"],
            "exit_plan_target_price": row["exit_plan_target_price"],
            "exit_plan_stop_price": row["exit_plan_stop_price"],
            "exit_plan_conditions": row["exit_plan_conditions"],
            "exit_plan_entered_at": row["exit_plan_entered_at"],
            "exit_plan_is_retrospective": bool(row["exit_plan_is_retrospective"])
            if row["exit_plan_is_retrospective"] is not None else None,
            "voided": bool(row["voided_at"]),
            "voided_at": row["voided_at"],
            "void_reason": row["void_reason"],
        })

    discipline_reviews = []
    for review in db.list_discipline_reviews():
        buy_log = db.get_log(review.buy_log_id) if review.buy_log_id else None
        sell_log = db.get_log(review.sell_log_id) if review.sell_log_id else None
        buy_log_ids = review.buy_log_ids or ([review.buy_log_id] if review.buy_log_id else [])
        linked_buys = [db.get_log(log_id) for log_id in buy_log_ids]
        if (sell_log and sell_log.voided_at) or any(log and log.voided_at for log in linked_buys):
            continue
        if (
            sell_log
            and sell_log.record_source == "autonomous_manual"
            and sell_log.trade_type == review.trade_type
            and review.trade_type != TradeType.unknown
        ):
            same_day_event_order_note = None
            ledger_logs = db.list_manual_position_logs(
                symbol=sell_log.symbol,
                trade_type=sell_log.trade_type,
                record_source="autonomous_manual",
                execution_date=sell_log.execution_date,
            ) if sell_log.symbol and sell_log.execution_date else []
            pnl = review_service.calculate_manual_position_pnl(
                review.position_id or "",
                ledger_logs,
                sell_log,
            )
            summary = review_service._deterministic_summary(
                review.trade_type, pnl, review.holding_days, review.plan_comparison
            )
            if len(buy_log_ids) > 1:
                summary += f" 成本按{len(buy_log_ids)}笔有效买入加权计算。"
            same_day_actions = {
                item.confirmed_action for item in ledger_logs
                if item.execution_date == sell_log.execution_date
            }
            if {"buy", "sell"}.issubset(same_day_actions):
                same_day_event_order_note = (
                    "同日买卖成本按系统录入时间先后计算；录入时间相同时按记录编号排序。"
                    "这反映录入顺序，不能核实实际成交先后。"
                )
            review = review.model_copy(update={"pnl_record": pnl, "deterministic_summary": summary})
            review_payload = review.model_dump(mode="json")
            review_payload["same_day_event_order_note"] = same_day_event_order_note
        else:
            review_payload = review.model_dump(mode="json")
            review_payload["same_day_event_order_note"] = None
        discipline_reviews.append(review_payload)

    return {
        "positions": result,
        "execution_logs": execution_logs,
        "discipline_reviews": discipline_reviews,
        "total": len(result),
    }


@router.post("/api/observations/execution-logs/{log_id}/void")
def void_execution_log(log_id: str, request: VoidExecutionLogRequest):
    """Append a reasoned void state and rebuild the affected position projection."""
    from zoneinfo import ZoneInfo

    db = get_live_trade_db()
    try:
        return db.void_execution_log(
            log_id,
            request.reason,
            datetime.now(ZoneInfo("Asia/Shanghai")),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="成交记录不存在。") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/api/observations/{position_id}")
def get_observation_detail(position_id: str):
    """
    Get observation position detail with full signal history.
    """
    db = get_live_trade_db()
    
    position = db.get_position(position_id)
    if not position:
        raise HTTPException(status_code=404, detail="Position not found")
    
    # Get all daily signals for this position
    signals = db.list_daily_signals(position_id)
    source_log = db.get_log(position.source_log_id)
    
    return {
        "position": {
            "position_id": position.position_id,
            "symbol": position.symbol,
            "name": position.name,
            "entry_price": position.entry_price,
            "quantity": position.quantity,
            "entry_thesis": position.entry_thesis,
            "lifecycle_state": position.lifecycle_state.value,
            "opened_at": position.opened_at.isoformat(),
            "execution_date": source_log.execution_date.isoformat() if source_log and source_log.execution_date else None,
            "recorded_at": source_log.confirmed_at.isoformat() if source_log else position.opened_at.isoformat(),
            "closed_at": position.closed_at.isoformat() if position.closed_at else None,
            "template_id": position.template_id,
            "template_version": position.template_version,
            "source_log_id": position.source_log_id,
            "record_source": position.record_source,
            "trade_type": position.trade_type.value,
            "plan_linked": bool(position.action_plan_id),
            "security_type": source_log.security_type if source_log else "unknown",
            "quantity_unit": source_log.quantity_unit if source_log else "unknown",
            "execution_card_id": position.execution_card_id,
            "signal_id": position.signal_id,
            "action_plan_id": position.action_plan_id,
            "capital_context_id": position.capital_context_id,
        },
        "daily_signals": [
            {
                "signal_record_id": sig.signal_record_id,
                "signal_type": sig.signal_type.value if sig.signal_type else None,
                "as_of_date": sig.as_of_date.isoformat(),
                "market_data_state": sig.market_data_state.value,
                "plain_explanation": sig.plain_explanation,
                "triggered_invalidations": [t.value for t in sig.triggered_invalidations],
                "explanation_source": sig.explanation_source.value,
            }
            for sig in signals
        ],
    }
