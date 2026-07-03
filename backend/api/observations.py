"""
Observation Pool API

Provides list and detail endpoints for observation positions.
"""

from fastapi import APIRouter, HTTPException
from typing import Optional
from datetime import datetime

from backend.db.live_trade import LiveTradeDB
from contracts.live_trade import (
    ObservationPosition,
    DailyObservationSignal,
    PositionLifecycleState,
    DailySignalType,
)
from contracts.market_data_fault import MarketDataFaultState


router = APIRouter()


def get_live_trade_db() -> LiveTradeDB:
    """Get LiveTradeDB instance with canonical path."""
    from backend.config.runtime_paths import get_live_trade_db_path
    return LiveTradeDB(get_live_trade_db_path())


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
    for pos in positions:
        latest_signal = db.get_latest_daily_signal(pos.position_id)
        
        position_dict = {
            "position_id": pos.position_id,
            "symbol": pos.symbol,
            "name": pos.name,
            "entry_price": pos.entry_price,
            "quantity": pos.quantity,
            "entry_thesis": pos.entry_thesis,
            "lifecycle_state": pos.lifecycle_state.value,
            "opened_at": pos.opened_at.isoformat(),
            "closed_at": pos.closed_at.isoformat() if pos.closed_at else None,
            "template_id": pos.template_id,
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
    
    return {"positions": result, "total": len(result)}


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
            "closed_at": position.closed_at.isoformat() if position.closed_at else None,
            "template_id": position.template_id,
            "template_version": position.template_version,
            "source_log_id": position.source_log_id,
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
