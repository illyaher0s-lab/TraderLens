"""
Agent Workbench Contracts

Conversation-driven workflow timeline contracts for V1.

Stores:
- Session (workflow_kind, workflow_state)
- Messages (user/agent/system)
- Artifact references (not raw content)
- Approval cards (result-level only)
"""

from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field, field_validator


class WorkflowKind(str, Enum):
    """Workflow kind for V1."""

    FRIEND_STOCK = "friend_stock"
    STRATEGY_IDEA = "strategy_idea"


class WorkflowState(str, Enum):
    """Workflow state."""

    CREATED = "created"
    RESEARCHING = "researching"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    VALIDATING = "validating"
    LIVE_EXECUTION_PENDING = "live_execution_pending"
    OBSERVING = "observing"
    REVIEWING = "reviewing"
    COMPLETED = "completed"
    STOPPED = "stopped"


class AgentSession(BaseModel):
    """
    Agent conversation session.

    Tracks one workflow timeline (friend_stock or strategy_idea).
    """

    session_id: str = Field(
        ...,
        description="Unique session identifier",
    )

    workflow_kind: WorkflowKind = Field(
        ...,
        description="Workflow kind: friend_stock or strategy_idea",
    )

    workflow_state: WorkflowState = Field(
        ...,
        description="Current workflow state",
    )

    title: str = Field(
        ...,
        description="Session title",
    )

    created_at: datetime = Field(
        ...,
        description="When session was created",
    )

    updated_at: datetime = Field(
        ...,
        description="When session was last updated",
    )


class AgentMessage(BaseModel):
    """
    Agent conversation message.

    Allowed roles: user, agent, system.
    """

    message_id: str = Field(
        ...,
        description="Unique message identifier",
    )

    session_id: str = Field(
        ...,
        description="Session this message belongs to",
    )

    role: str = Field(
        ...,
        description="Message role: user, agent, or system",
    )

    content: str = Field(
        ...,
        description="Message content",
    )

    created_at: datetime = Field(
        ...,
        description="When message was created",
    )

    @field_validator("role")
    @classmethod
    def validate_role(cls, v):
        """Only user, agent, system roles are allowed."""
        allowed_roles = {"user", "agent", "system"}

        if v not in allowed_roles:
            raise ValueError(
                f"Invalid role: {v}. "
                f"Allowed roles: {', '.join(sorted(allowed_roles))}"
            )

        return v


class ArtifactRef(BaseModel):
    """
    Artifact reference.

    Stores reference to research report, validation report, etc.
    Does NOT store raw report content.
    """

    artifact_ref_id: str = Field(
        ...,
        description="Unique artifact reference identifier",
    )

    session_id: str = Field(
        ...,
        description="Session this artifact belongs to",
    )

    artifact_id: str = Field(
        ...,
        description="Artifact identifier (research_report_001, validation_report_001, etc.)",
    )

    artifact_type: str = Field(
        ...,
        description="Artifact type (research_report, validation_report, execution_record, etc.)",
    )

    created_at: datetime = Field(
        ...,
        description="When artifact was attached",
    )
