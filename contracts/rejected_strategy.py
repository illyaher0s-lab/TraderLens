"""
Rejected Strategy Registry Contracts

All rejected, blocked, and needs-review strategies preserved append-only.
Prevents survivorship bias.
"""

from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field, field_validator


class RejectedStrategyStatus(str, Enum):
    """Status of rejected strategy."""
    REJECTED = "rejected"
    BLOCKED = "blocked"
    NEEDS_REVIEW = "needs_review"


class DataQualityStatus(str, Enum):
    """Data quality status."""
    OK = "ok"
    PARTIAL = "partial"
    STALE = "stale"
    INCONSISTENT = "inconsistent"
    UNAVAILABLE = "unavailable"
    SOURCE_ERROR = "source_error"
    ADAPTER_UNSUPPORTED = "adapter_unsupported"


class RejectedStrategyRecord(BaseModel):
    """
    Rejected strategy record.
    
    Append-only. No live execution or P&L fields.
    """
    
    registry_id: str = Field(..., description="Unique registry ID")
    strategy_revision_id: str = Field(..., description="Strategy revision ID")
    template_id: str = Field(..., description="Template ID")
    template_version: str = Field(..., description="Template version")
    status: RejectedStrategyStatus = Field(..., description="Rejection status")
    failed_gate: str = Field(..., description="Which gate failed")
    rejection_reason: str = Field(..., description="Why rejected")
    data_quality_status: DataQualityStatus = Field(..., description="Data quality")
    market_context_snapshot: dict = Field(default_factory=dict, description="Market context at rejection time")
    cost_stress_result_id: str | None = Field(None, description="Cost stress result ID if available")
    future_retest_allowed: bool = Field(False, description="Can retest in future")
    retest_eligibility_reason: str = Field("", description="Why retest allowed/not")
    artifact_ids: list[str] = Field(..., description="Evidence artifact IDs")
    created_at: datetime = Field(..., description="When rejected")
    actor: str = Field(..., description="Who/what rejected (user/system/gate)")
    
    @field_validator("artifact_ids")
    @classmethod
    def validate_artifact_ids(cls, v):
        """artifact_ids must be non-empty."""
        if not v or len(v) == 0:
            raise ValueError("artifact_ids must be non-empty")
        return v
    
    @field_validator("rejection_reason")
    @classmethod
    def validate_rejection_reason(cls, v):
        """rejection_reason must be non-empty."""
        if not v or not v.strip():
            raise ValueError("rejection_reason must be non-empty")
        return v
    
    @field_validator("failed_gate")
    @classmethod
    def validate_failed_gate(cls, v, info):
        """failed_gate must be non-empty for rejected and blocked."""
        status = info.data.get("status")
        if status in (RejectedStrategyStatus.REJECTED, RejectedStrategyStatus.BLOCKED):
            if not v or not v.strip():
                raise ValueError("failed_gate must be non-empty for rejected/blocked status")
        return v
    
    @field_validator("retest_eligibility_reason")
    @classmethod
    def validate_retest_eligibility_reason(cls, v, info):
        """If future_retest_allowed=True, retest_eligibility_reason must be non-empty."""
        future_retest_allowed = info.data.get("future_retest_allowed")
        if future_retest_allowed and (not v or not v.strip()):
            raise ValueError("retest_eligibility_reason must be non-empty when future_retest_allowed=True")
        return v
