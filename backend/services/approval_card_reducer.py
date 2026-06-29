"""
Approval Card Reducer

Deterministic state transitions for approval cards.

Hard rules:
- No external API calls
- No database calls
- No random/time except values passed explicitly
- Reject unknown decisions
- Reject technical-decision labels
- Require at least one artifact_id
"""

import hashlib
from datetime import datetime, timezone

from contracts.approval_card import ApprovalCard, ALLOWED_DECISIONS


def create_approval_card(
    workflow_id: str,
    stage: str,
    title: str,
    plain_language_summary: str,
    allowed_decisions: list[str],
    artifact_ids: list[str],
    created_at: datetime | None = None,
    blocked_technical_decisions: list[str] | None = None,
) -> ApprovalCard:
    """
    Create a new approval card.

    Args:
        workflow_id: Workflow session ID
        stage: Workflow stage
        title: Card title
        plain_language_summary: Plain-language summary
        allowed_decisions: Allowed decisions for this card
        artifact_ids: Backing artifact IDs
        created_at: Creation timestamp (defaults to UTC now)
        blocked_technical_decisions: Technical decisions blocked for this card

    Returns:
        ApprovalCard with deterministic approval_card_id

    Raises:
        ValueError: If artifact_ids is empty or decisions are invalid
    """
    # Require at least one artifact_id
    if not artifact_ids or len(artifact_ids) == 0:
        raise ValueError("Approval card requires at least one artifact_id")

    # Validate all allowed_decisions are in ALLOWED_DECISIONS
    for decision in allowed_decisions:
        if decision not in ALLOWED_DECISIONS:
            raise ValueError(
                f"Unknown decision: {decision}. "
                f"Allowed decisions: {', '.join(sorted(ALLOWED_DECISIONS))}"
            )

    # Default created_at
    if created_at is None:
        created_at = datetime.now(timezone.utc)

    # Generate deterministic approval_card_id
    components = [
        workflow_id,
        stage,
        "|".join(sorted(artifact_ids)),
        created_at.isoformat(),
    ]
    hash_input = "|".join(components)
    hash_digest = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()
    approval_card_id = f"approval_{hash_digest[:16]}"

    # Default blocked_technical_decisions
    if blocked_technical_decisions is None:
        blocked_technical_decisions = [
            "candidate_pool_technical_quality",
            "strategy_parameters",
            "oos_windows",
            "thresholds",
            "stop_loss",
            "liquidity_rules",
            "manual_execution_fields",
        ]

    return ApprovalCard(
        approval_card_id=approval_card_id,
        workflow_id=workflow_id,
        stage=stage,
        title=title,
        plain_language_summary=plain_language_summary,
        allowed_decisions=allowed_decisions,
        blocked_technical_decisions=blocked_technical_decisions,
        artifact_ids=artifact_ids,
        created_at=created_at,
        decided_at=None,
        decision=None,
        decided_by=None,
    )


def validate_decision(
    allowed_decisions: list[str],
    blocked_technical_decisions: list[str],
    proposed_decision: str,
) -> None:
    """
    Validate a proposed decision.

    Args:
        allowed_decisions: Allowed decisions for this card
        blocked_technical_decisions: Blocked technical decisions
        proposed_decision: Proposed decision to validate

    Raises:
        ValueError: If decision is not allowed or is a blocked technical decision
    """
    # Check if decision is a blocked technical decision (check first)
    if proposed_decision in blocked_technical_decisions:
        raise ValueError(
            f"Decision '{proposed_decision}' is a blocked technical decision. "
            f"User cannot approve technical decisions."
        )

    # Check if decision is in allowed_decisions
    if proposed_decision not in allowed_decisions:
        raise ValueError(
            f"Decision '{proposed_decision}' is not allowed for this card. "
            f"Allowed decisions: {', '.join(allowed_decisions)}"
        )


def apply_decision(
    card: ApprovalCard,
    decision: str,
    decided_by: str,
    decided_at: datetime | None = None,
) -> ApprovalCard:
    """
    Apply user decision to approval card.

    Args:
        card: Original approval card
        decision: User's decision
        decided_by: User who made decision
        decided_at: Decision timestamp (defaults to UTC now)

    Returns:
        Updated approval card with decision applied

    Raises:
        ValueError: If decision is not allowed
    """
    # Validate decision
    validate_decision(
        allowed_decisions=card.allowed_decisions,
        blocked_technical_decisions=card.blocked_technical_decisions,
        proposed_decision=decision,
    )

    # Default decided_at
    if decided_at is None:
        decided_at = datetime.now(timezone.utc)

    # Return updated card
    return card.model_copy(
        update={
            "decision": decision,
            "decided_by": decided_by,
            "decided_at": decided_at,
        }
    )
