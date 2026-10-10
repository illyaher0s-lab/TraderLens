from __future__ import annotations

from datetime import datetime

from backend.db.agent_workbench import (
    attach_approval_card,
    attach_artifact_ref,
    create_session,
    init_agent_workbench_db,
)
from contracts.agent_workbench import (
    AgentSession,
    ArtifactRef,
    WorkflowKind,
    WorkflowState,
)
from contracts.approval_card import ApprovalCard


def attach_continued_approval(
    db,
    theme_id: str,
    *,
    session_id: str | None = None,
    approval_card_id: str | None = None,
    card_artifact_ids: list[str] | None = None,
    artifact_theme_ids: list[str] | None = None,
) -> str:
    """Create a real persisted Approval Card provenance chain for tests."""
    init_agent_workbench_db(db.conn)
    session_id = session_id or f"session_{theme_id}"
    approval_card_id = approval_card_id or f"card_{theme_id}"
    now = datetime.now()

    create_session(
        db.conn,
        AgentSession(
            session_id=session_id,
            workflow_kind=WorkflowKind.FRIEND_STOCK,
            workflow_state=WorkflowState.WAITING_FOR_APPROVAL,
            title=f"Approval for {theme_id}",
            created_at=now,
            updated_at=now,
        ),
    )
    for index, artifact_theme_id in enumerate(artifact_theme_ids or [theme_id]):
        attach_artifact_ref(
            db.conn,
            ArtifactRef(
                artifact_ref_id=f"ref_{session_id}_{index}",
                session_id=session_id,
                artifact_id=artifact_theme_id,
                artifact_type="research_case",
                created_at=now,
            ),
        )
    attach_approval_card(
        db.conn,
        session_id,
        ApprovalCard(
            approval_card_id=approval_card_id,
            workflow_id=session_id,
            stage="research_confirmation",
            title=f"Continue {theme_id}",
            plain_language_summary=f"Continue research for {theme_id}",
            allowed_decisions=["continue"],
            artifact_ids=card_artifact_ids or [theme_id],
            created_at=now,
            decision="continue",
            decided_at=now,
            decided_by="user",
        ),
    )
    return approval_card_id
