"""B4 Protocol Types - Event-driven backtest contracts with strict time cursor."""
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class BacktestCursorState(BaseModel):
    """
    Immutable backtest time cursor state.
    
    Tracks current evaluation date and allowed read window.
    """
    
    model_config = ConfigDict(frozen=True, extra="forbid")
    
    cursor_id: str = Field(min_length=1)
    current_date: date
    allowed_read_until: date  # Inclusive max date strategy can read
    evaluation_mode: Literal["signal_phase", "execution_phase"]
    read_trace: tuple[str, ...]  # Audit trail of data accesses


class BacktestReadRequest(BaseModel):
    """Read request from strategy logic."""
    
    model_config = ConfigDict(frozen=True, extra="forbid")
    
    symbol: str = Field(min_length=1)
    requested_date: date
    data_type: Literal["bar", "daily_status", "financial", "membership", "adjustment_factor"]
    source: str = Field(min_length=1)


class FutureDataViolation(BaseModel):
    """Record of attempted future data access (blocking failure)."""
    
    model_config = ConfigDict(frozen=True, extra="forbid")
    
    requested_date: date
    allowed_max_date: date
    source: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    evaluation_mode: Literal["signal_phase", "execution_phase"]


class RejectedOrderRecord(BaseModel):
    """Order rejected by engine (e.g., insufficient data, halted symbol)."""
    
    model_config = ConfigDict(frozen=True, extra="forbid")
    
    order_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    intended_date: date
    rejection_reason: str = Field(min_length=1)


class OrderIntentRecord(BaseModel):
    """Order intent before execution (what strategy wants to do)."""
    
    model_config = ConfigDict(frozen=True, extra="forbid")
    
    order_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    signal_date: date
    intent: Literal["buy", "sell", "hold"]
    quantity: int = Field(ge=0)


class FillRecord(BaseModel):
    """Actual fill record after execution."""
    
    model_config = ConfigDict(frozen=True, extra="forbid")
    
    fill_id: str = Field(min_length=1)
    order_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    fill_date: date
    fill_price: float = Field(gt=0)
    fill_quantity: int = Field(gt=0)
    execution_mode: Literal["simulated", "paper", "live"]


class DailyPortfolioSnapshot(BaseModel):
    """Daily portfolio state snapshot (for audit, not for user recommendation)."""
    
    model_config = ConfigDict(frozen=True, extra="forbid")
    
    snapshot_id: str = Field(min_length=1)
    snapshot_date: date
    cash: float = Field(ge=0)
    positions: tuple[tuple[str, int], ...]  # (symbol, quantity)
    portfolio_value: float = Field(ge=0)


class EventBacktestResult(BaseModel):
    """
    Immutable backtest result (no Gate verdict, no promotion, no user recommendation).
    
    Records what happened during backtest for audit.
    """
    
    model_config = ConfigDict(frozen=True, extra="forbid")
    
    result_id: str = Field(min_length=1)
    strategy_revision_id: str = Field(min_length=1)
    protocol_snapshot_id: str = Field(min_length=1)
    evaluation_mode: Literal["canary_qualification", "formal_backtest"]
    backtest_start: date
    backtest_end: date
    order_intents: tuple[OrderIntentRecord, ...]
    fills: tuple[FillRecord, ...]
    rejected_orders: tuple[RejectedOrderRecord, ...]
    future_violations: tuple[FutureDataViolation, ...]
    final_portfolio: DailyPortfolioSnapshot
    frozen_at: date


class CanaryCaseResult(BaseModel):
    """
    Result of single Canary case (must be deterministic block).
    
    Correct result: blocked by future guard.
    Wrong result: completed normally (qualification failed).
    """
    
    model_config = ConfigDict(frozen=True, extra="forbid")
    
    case_id: str = Field(min_length=1)
    case_name: str = Field(min_length=1)
    attempted_violation: Literal[
        "future_bar",
        "future_status",
        "future_financial_ann_date",
        "future_membership",
        "full_sample_normalization",
        "future_adjustment_factor",
    ]
    outcome: Literal["blocked", "completed"]  # "blocked" is correct
    violation_count: int = Field(ge=0)
    violations: tuple[FutureDataViolation, ...]


class BacktestEngineQualificationResult(BaseModel):
    """
    Qualification result: all Canary cases must be blocked.
    
    No Gate verdict, no promotion, frozen result.
    """
    
    model_config = ConfigDict(frozen=True, extra="forbid")
    
    qualification_id: str = Field(min_length=1)
    protocol_snapshot_id: str = Field(min_length=1)
    canary_cases: tuple[CanaryCaseResult, ...]
    qualification_status: Literal["pass", "fail"]  # pass = all blocked
    qualified_at: date
    frozen: Literal[True] = True
