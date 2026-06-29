"""
V1 Capital Context

Defines capital profile, position sizing, and live-trading capability.
Uses fixed V1 conservative defaults. No technical parameter choices.
No LLM, no recommendations, no execution logic.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, field_validator, model_validator


class CapitalProfile(BaseModel, frozen=True, extra="forbid"):
    """Capital profile for risk management."""

    profile_id: str
    total_capital: float
    cash_available: float
    max_risk_budget: float
    capital_unit: str
    created_at: datetime
    source: str
    confirmed_by_user: bool

    @field_validator("total_capital")
    @classmethod
    def total_capital_must_be_positive(cls, v: float) -> float:
        """total_capital must be > 0."""
        if v <= 0:
            raise ValueError("total_capital must be > 0")
        return v

    @field_validator("max_risk_budget")
    @classmethod
    def max_risk_budget_must_be_positive(cls, v: float) -> float:
        """max_risk_budget must be > 0."""
        if v <= 0:
            raise ValueError("max_risk_budget must be > 0")
        return v

    @model_validator(mode="after")
    def validate_cash_and_risk_limits(self):
        """Validate cash and risk do not exceed total capital."""
        if self.cash_available < 0:
            raise ValueError("cash_available must be >= 0")
        if self.cash_available > self.total_capital:
            raise ValueError("cash_available cannot exceed total_capital")
        if self.max_risk_budget > self.total_capital:
            raise ValueError("max_risk_budget cannot exceed total_capital")
        return self


class PositionSizingPlan(BaseModel, frozen=True, extra="forbid"):
    """Position sizing plan with deterministic V1 conservative rules."""

    plan_id: str
    profile_id: str
    max_single_position_capital: float
    max_total_live_capital: float
    max_position_count: int
    risk_cap_per_trade: float
    created_at: datetime
    basis: str

    @field_validator("max_single_position_capital", "max_total_live_capital", "risk_cap_per_trade")
    @classmethod
    def capital_limits_must_be_positive(cls, v: float) -> float:
        """All capital limits must be > 0."""
        if v <= 0:
            raise ValueError("Capital limits must be > 0")
        return v

    @field_validator("max_position_count")
    @classmethod
    def position_count_must_be_positive(cls, v: int) -> int:
        """max_position_count must be > 0."""
        if v <= 0:
            raise ValueError("max_position_count must be > 0")
        return v

    @model_validator(mode="after")
    def validate_single_does_not_exceed_total(self):
        """max_single_position_capital must be <= max_total_live_capital."""
        if self.max_single_position_capital > self.max_total_live_capital:
            raise ValueError(
                "max_single_position_capital cannot exceed max_total_live_capital"
            )
        return self


class CapitalContext(BaseModel, frozen=True, extra="forbid"):
    """Complete capital context with live-trading capability assessment."""

    profile: CapitalProfile
    position_sizing_plan: PositionSizingPlan
    is_live_capable: bool
    blocking_reason: Optional[str] = None
