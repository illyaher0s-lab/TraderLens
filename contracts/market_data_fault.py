"""
V1 Market Data Fault Boundary

Defines auditable market data quality states and results.
No LLM, no recommendations, no execution logic.
"""

from datetime import date
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, field_validator, model_validator


class MarketDataFaultState(str, Enum):
    """Market data quality states."""

    ok = "ok"
    stale = "stale"
    partial = "partial"
    inconsistent = "inconsistent"
    unavailable = "unavailable"
    source_error = "source_error"
    adapter_unsupported = "adapter_unsupported"


class MarketDataFault(BaseModel, frozen=True, extra="forbid"):
    """Market data fault information."""

    state: MarketDataFaultState
    source: str
    dataset: str
    symbol: str
    as_of: date
    message: Optional[str] = None
    recoverable: bool
    evidence: Optional[dict[str, Any]] = None

    @model_validator(mode="after")
    def validate_non_ok_requires_message_and_evidence(self):
        """Non-ok states must have message and evidence."""
        if self.state != MarketDataFaultState.ok:
            if not self.message or not self.message.strip():
                raise ValueError("Non-ok fault states must have a non-empty message")
            if not self.evidence:
                raise ValueError("Non-ok fault states must have evidence")
        return self

    @model_validator(mode="after")
    def validate_adapter_unsupported_not_recoverable(self):
        """adapter_unsupported must be non-recoverable."""
        if self.state == MarketDataFaultState.adapter_unsupported:
            if self.recoverable:
                raise ValueError("adapter_unsupported faults must have recoverable=False")
        return self


class MarketDataResult(BaseModel, frozen=True, extra="forbid"):
    """Market data result with fault information."""

    symbol: str
    dataset: str
    as_of: date
    data: Optional[dict[str, Any]] = None
    fault: MarketDataFault

    @model_validator(mode="after")
    def validate_data_fault_consistency(self):
        """Non-ok faults cannot have data, ok faults must have data."""
        if self.fault.state != MarketDataFaultState.ok:
            if self.data is not None:
                raise ValueError("Non-ok faults cannot have data")
        else:
            if self.data is None:
                raise ValueError("ok faults must have data")
        return self
