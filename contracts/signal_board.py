"""
Signal Board Data Models

Defines PlannedSignal entity for next-day trading signals.
Signal Board is a display layer: shows strategy_core results, doesn't generate signals.

Design Principles:
- Immutable after creation (only review_status can change)
- Always linked to snapshot_hash (reproducibility)
- Always linked to strategy_version (auditability)
- No "approved_for_execution" status (M4 doesn't execute trades)
"""

from datetime import date, datetime
from typing import Literal
from pydantic import BaseModel, Field


class PlannedSignal(BaseModel):
    """
    A planned trading signal for next trading day.
    
    Generated from strategy_core, displayed in Signal Board,
    reviewed by human, never auto-executed in M4.
    
    Attributes:
        signal_id: Unique identifier (UUID)
        strategy_id: Strategy that generated this signal
        strategy_version: Version of strategy (for reproducibility)
        snapshot_hash: Hash of frozen snapshot used (links to exact data)
        signal_date: When signal was generated (EOD after close)
        intended_execution_date: Next trading day (T+1)
        
        symbol: Stock symbol (e.g., "600519.SH")
        direction: Buy or sell
        quantity: Number of shares (None if signal only, no sizing yet)
        trigger_reason: Human-readable explanation of which rule fired
        
        review_status: Human review state (pending/reviewed/ignored/approved_for_watch)
        reviewed_at: Timestamp of human review (if any)
        reviewed_by: Username who reviewed (if any)
        rejection_reason: Why signal was ignored (if any)
        
        current_price: Close price on signal_date (for context)
        position_before: Existing position quantity (if any)
        
        created_at: Timestamp of signal generation
        metadata: Strategy params, risk filters, etc. (JSON dict)
    
    Status Flow:
        pending → reviewed → ignored
                         → approved_for_watch
    
    Immutability:
        - All fields except review_status, reviewed_at, reviewed_by, rejection_reason
          are immutable after creation.
        - No backwards transitions (cannot go back to pending).
    
    Audit Trail:
        - snapshot_hash: reproducibility (can replay exact data)
        - strategy_version: auditability (which strategy version generated this)
        - trigger_reason: explainability (why this signal fired)
        - reviewed_at/by: accountability (who made the decision)
    """
    
    signal_id: str = Field(
        ...,
        description="Deterministic hash: sha256(strategy_id + strategy_version + snapshot_hash + signal_date + intended_execution_date + symbol + direction + trigger_reason). Prevents duplicates, enables upsert."
    )
    
    strategy_id: str = Field(
        ...,
        description="Strategy identifier (e.g., 'momentum_v2')"
    )
    
    strategy_version: str = Field(
        ...,
        description="Strategy version string (e.g., 'v2.1.0'). Links to exact strategy config used."
    )
    
    snapshot_hash: str = Field(
        ...,
        description="Hash of frozen snapshot used. Links to exact data for reproducibility."
    )
    
    signal_date: date = Field(
        ...,
        description="Date when signal was generated (EOD after market close)"
    )
    
    intended_execution_date: date = Field(
        ...,
        description="Next trading day (T+1). When this signal should be acted upon."
    )
    
    symbol: str = Field(
        ...,
        description="Stock symbol (e.g., '600519.SH')"
    )
    
    direction: Literal["buy", "sell"] = Field(
        ...,
        description="Trading direction: buy or sell (data layer only)"
    )
    
    planned_action: Literal["enter", "exit"] = Field(
        ...,
        description="UI display: enter (入场) or exit (离场). Mapped from direction. Avoids regulatory implications of '买入/卖出建议'."
    )
    
    quantity: int | None = Field(
        None,
        description="Number of shares. None if signal only (no position sizing yet)."
    )
    
    trigger_reason: str = Field(
        ...,
        description="Human-readable explanation of which entry/exit rule fired (e.g., 'Price broke above 5-day high')"
    )
    
    review_status: Literal["pending", "ignored", "watching", "expired"] = Field(
        "pending",
        description="Human review state. pending=待人工看, ignored=人工决定不跟, watching=人工决定加入观察, expired=信号过期未处理. No 'reviewed' status (看过但没决定 has no execution value)."
    )
    
    reviewed_at: datetime | None = Field(
        None,
        description="Timestamp when user reviewed this signal (if any)"
    )
    
    reviewed_by: str | None = Field(
        None,
        description="Username who reviewed this signal (if any)"
    )
    
    rejection_reason: str | None = Field(
        None,
        description="Why signal was ignored (if review_status is 'ignored')"
    )
    
    current_price: float | None = Field(
        None,
        description="Close price on signal_date (for context)"
    )
    
    position_before: int | None = Field(
        None,
        description="Existing position quantity before this signal (if any)"
    )
    
    created_at: datetime = Field(
        ...,
        description="Timestamp of signal generation (immutable)"
    )
    
    metadata: dict = Field(
        default_factory=dict,
        description="Strategy params, risk filters, evidence checks, etc. (JSON dict)"
    )
    
    # Evidence light_check fields (M4.1)
    risk_flags: list[str] = Field(
        default_factory=list,
        description="Risk flags from evidence light_check: ['ST', 'suspended', 'limit_up', 'limit_down', 'low_liquidity']. Empty list = no risks detected."
    )
    
    evidence_status: Literal["clean", "warning", "blocked"] = Field(
        "clean",
        description="Evidence check status. clean=no risks, warning=some risks but tradeable, blocked=untradeable (suspended/limit)."
    )
    
    evidence_checked_at: datetime | None = Field(
        None,
        description="Timestamp when evidence light_check was performed (if any)"
    )
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "signal_id": "a1b2c3d4e5f6...",  # sha256 hash
                    "strategy_id": "momentum_v2",
                    "strategy_version": "v2.1.0",
                    "snapshot_hash": "a1b2c3d4e5f6",
                    "signal_date": "2023-12-29",
                    "intended_execution_date": "2024-01-02",
                    "symbol": "600519.SH",
                    "direction": "buy",
                    "planned_action": "enter",
                    "quantity": 100,
                    "trigger_reason": "Price broke above 5-day high (¥1850.00) with volume surge (2.5x avg)",
                    "review_status": "pending",
                    "reviewed_at": None,
                    "reviewed_by": None,
                    "rejection_reason": None,
                    "current_price": 1855.00,
                    "position_before": 0,
                    "created_at": "2023-12-29T16:30:00Z",
                    "metadata": {
                        "strategy_params": {
                            "lookback_period": 5,
                            "volume_threshold": 2.0
                        },
                        "risk_filters": {
                            "max_position_size": 10000,
                            "max_concentration": 0.1
                        }
                    }
                }
            ]
        }
    }


class SignalReviewRequest(BaseModel):
    """
    Request to update review status of a signal.
    
    Used by POST /api/signals/{signal_id}/review endpoint.
    """
    
    review_status: Literal["ignored", "watching", "expired"] = Field(
        ...,
        description="New review status. Cannot set back to 'pending'. ignored=不跟, watching=观察, expired=过期."
    )
    
    reviewed_by: str = Field(
        ...,
        description="Username who is reviewing this signal"
    )
    
    rejection_reason: str | None = Field(
        None,
        description="Why signal was ignored (required if review_status is 'ignored')"
    )


class SignalBatchReviewRequest(BaseModel):
    """
    Request to batch-update review status of multiple signals.
    
    Used by POST /api/signals/batch-review endpoint.
    """
    
    signal_ids: list[str] = Field(
        ...,
        description="List of signal IDs to review"
    )
    
    review_status: Literal["ignored", "watching", "expired"] = Field(
        ...,
        description="New review status for all selected signals"
    )
    
    reviewed_by: str = Field(
        ...,
        description="Username who is reviewing these signals"
    )
    
    rejection_reason: str | None = Field(
        None,
        description="Why signals were ignored (applied to all if review_status is 'ignored')"
    )


class SignalSummary(BaseModel):
    """
    Summary statistics for signals on a given date.
    
    Used by GET /api/signals/summary endpoint.
    """
    
    signal_date: date = Field(
        ...,
        description="Date when signals were generated"
    )
    
    total_count: int = Field(
        ...,
        description="Total number of signals"
    )
    
    by_status: dict[str, int] = Field(
        default_factory=dict,
        description="Count by review_status (e.g., {'pending': 10, 'reviewed': 5})"
    )
    
    by_direction: dict[str, int] = Field(
        default_factory=dict,
        description="Count by direction (e.g., {'buy': 8, 'sell': 7})"
    )
    
    pending_count: int = Field(
        ...,
        description="Count of signals with review_status='pending'"
    )
