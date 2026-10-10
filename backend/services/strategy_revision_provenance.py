from __future__ import annotations

"""Strategy Revision Approval Provenance validator (Task 2/4 Phase B).

ponytail: read-only, exact PK, ApprovalCard contract, Phase A canonical joins.
"""
from dataclasses import dataclass

from backend.db.research import ResearchDB
from backend.db.strategy import StrategyDB
from contracts.approval_card import ApprovalCard
from contracts.strategy import StrategyDraft


def _validate_template_governance(draft: StrategyDraft) -> ProvenanceValidationResult:
    p = draft.provenance
    if p is None:
        return ProvenanceValidationResult(False, "strategy_revision_provenance_unavailable", "provenance missing")
    if (p.template_id, p.template_version, p.template_hash) != (draft.strategy_template_id, draft.strategy_template_version, draft.strategy_template_hash):
        return ProvenanceValidationResult(False, "template_governance_binding_mismatch", "draft/template governance identity mismatch")
    from backend.services.strategy_template_library import (
        _governance_map,
        _review_evidence_sha256,
        convert_to_frozen_contract,
        get_template_by_id,
    )
    from backend.services.strategy_config_validator import StrategyConfigValidator
    import json
    template = get_template_by_id(p.template_id)
    if template is None:
        return ProvenanceValidationResult(False, "template_governance_unavailable", "template not found")
    frozen = convert_to_frozen_contract(template, created_at=draft.created_at)

    if frozen.governance_status != "approved":
        return ProvenanceValidationResult(False, "template_governance_binding_mismatch", "template is not approved")

    if p.review_evidence_sha256 != frozen.review_evidence_sha256:
        return ProvenanceValidationResult(False, "template_governance_evidence_mismatch", "review evidence hash mismatch")
    owner_authorization = _governance_map().get(p.template_id, {}).get("owner_authorization")
    if not owner_authorization:
        return ProvenanceValidationResult(False, "template_governance_binding_mismatch", "owner authorization unavailable")

    exact_fields = (
        (p.template_id, frozen.template_id),
        (p.template_version, frozen.version),
        (p.template_hash, frozen.template_hash),
        (p.data_requirements_hash, frozen.data_requirements_hash),
        (p.review_evidence_path, frozen.review_evidence_path),
        (p.reviewer_id, frozen.reviewer_id),
        (p.reviewer_kind, owner_authorization.get("reviewer_kind")),
        (p.review_decision, owner_authorization.get("review_decision")),
        (p.reviewed_at, frozen.reviewed_at),
        (p.review_due_date, frozen.review_due_date),
        (p.authorized_by, frozen.authorized_by),
        (p.authorized_at, frozen.authorized_at),
    )
    if any(actual != expected for actual, expected in exact_fields):
        return ProvenanceValidationResult(False, "template_governance_binding_mismatch", "approved frozen template binding mismatch")
    if p.owner_authorization_hash != frozen.owner_authorization_hash:
        return ProvenanceValidationResult(False, "template_governance_authorization_mismatch", "owner authorization hash mismatch")

    if _review_evidence_sha256(p.review_evidence_path) != p.review_evidence_sha256:
        return ProvenanceValidationResult(False, "template_governance_evidence_mismatch", "review evidence hash mismatch")

    try:
        config = json.loads(draft.strategy_config_json)
    except json.JSONDecodeError as exc:
        return ProvenanceValidationResult(False, "template_governance_config_invalid", str(exc))
    validation = StrategyConfigValidator().validate(config, template)
    if validation.status != "pass":
        return ProvenanceValidationResult(False, "template_governance_config_invalid", str(validation.errors))
    return ProvenanceValidationResult(True)


@dataclass(frozen=True)
class ProvenanceValidationResult:
    is_valid: bool
    reason_code: str | None = None
    detail: str | None = None


def validate_strategy_revision_provenance(
    strategy_db: StrategyDB,
    research_db: ResearchDB,
    strategy_revision_id: str,
) -> ProvenanceValidationResult:
    """Validate StrategyDraft approval provenance (read-only).
    
    ponytail: exact PK, Phase A joins, fail loud on corrupt data.
    """
    # 1. Draft by exact PK
    draft = strategy_db.get_strategy_draft(strategy_revision_id)
    if not draft:
        return ProvenanceValidationResult(
            False, "strategy_revision_provenance_unavailable",
            f"Draft {strategy_revision_id} not found"
        )
    
    if draft.provenance is not None and draft.provenance.kind == "approved_template_governance":
        return _validate_template_governance(draft)

    # 2. Source IDs required + non-empty
    card_id = draft.source_approval_card_id
    confirmed_id = draft.source_confirmed_candidate_id
    if not card_id or not card_id.strip() or not confirmed_id or not confirmed_id.strip():
        return ProvenanceValidationResult(
            False, "strategy_revision_provenance_unavailable",
            "source_approval_card_id or source_confirmed_candidate_id missing/empty"
        )
    
    # 3. Confirmed candidate
    confirmed = research_db.get_confirmed_candidate(confirmed_id)
    if not confirmed:
        return ProvenanceValidationResult(
            False, "source_confirmed_candidate_unavailable",
            f"ConfirmedCandidate {confirmed_id} not found"
        )
    
    # 4. Approval card + parse with contract
    cursor = research_db.conn.cursor()
    cursor.execute(
        "SELECT session_id, card_data FROM agent_approval_cards WHERE approval_card_id = ?",
        (card_id,)
    )
    card_row = cursor.fetchone()
    if not card_row:
        return ProvenanceValidationResult(
            False, "source_approval_card_unavailable",
            f"Approval card {card_id} not found"
        )
    
    session_id = card_row["session_id"]
    # ponytail: ApprovalCard contract parse (fail loud on corrupt/invalid)
    card = ApprovalCard.model_validate_json(card_row["card_data"])
    
    # 5. Cross-binding: card/confirmed IDs
    if confirmed.approval_card_id != card_id:
        return ProvenanceValidationResult(
            False, "approval_candidate_binding_mismatch",
            f"confirmed.approval_card_id {confirmed.approval_card_id} != {card_id}"
        )
    
    if confirmed.confirmed_id != confirmed_id:
        return ProvenanceValidationResult(
            False, "approval_candidate_binding_mismatch",
            "confirmed_id mismatch"
        )
    
    # 6. Theme consistency
    if confirmed.theme_id != draft.theme_id:
        return ProvenanceValidationResult(
            False, "approval_candidate_binding_mismatch",
            f"theme_id mismatch: confirmed={confirmed.theme_id} draft={draft.theme_id}"
        )
    
    # 7. Card decision
    if card.decision != "continue":
        return ProvenanceValidationResult(
            False, "approval_candidate_binding_mismatch",
            f"Card decision {card.decision} != continue"
        )
    
    # 8. Phase A canonical join: workflow_id == session_id
    if card.workflow_id != session_id:
        return ProvenanceValidationResult(
            False, "approval_candidate_binding_mismatch",
            f"workflow_id {card.workflow_id} != session_id {session_id}"
        )
    
    # 9. Artifact ref
    cursor.execute(
        """SELECT 1 FROM agent_artifact_refs 
           WHERE session_id = ? AND artifact_type = 'research_case' AND artifact_id = ?""",
        (session_id, draft.theme_id)
    )
    if not cursor.fetchone():
        return ProvenanceValidationResult(
            False, "approval_candidate_binding_mismatch",
            f"No research_case artifact for theme {draft.theme_id} in session {session_id}"
        )
    
    # 10. Theme in card.artifact_ids
    if draft.theme_id not in card.artifact_ids:
        return ProvenanceValidationResult(
            False, "approval_candidate_binding_mismatch",
            f"theme {draft.theme_id} not in card.artifact_ids"
        )
    
    # 11. Original candidate
    candidate = research_db.get_candidate(confirmed.candidate_id)
    if not candidate:
        return ProvenanceValidationResult(
            False, "approval_candidate_binding_mismatch",
            f"Original candidate {confirmed.candidate_id} not found"
        )
    
    if candidate.theme_id != confirmed.theme_id or candidate.symbol != confirmed.symbol:
        return ProvenanceValidationResult(
            False, "approval_candidate_binding_mismatch",
            "Candidate theme/symbol mismatch"
        )
    
    # 12. Evidence binding
    if not confirmed.primary_evidence_snapshot_id:
        return ProvenanceValidationResult(
            False, "approval_candidate_binding_mismatch",
            "primary_evidence_snapshot_id missing"
        )
    
    if draft.hypothesis_source_snapshot_id != confirmed.primary_evidence_snapshot_id:
        return ProvenanceValidationResult(
            False, "approval_candidate_binding_mismatch",
            f"hypothesis_source {draft.hypothesis_source_snapshot_id} != primary {confirmed.primary_evidence_snapshot_id}"
        )
    
    if confirmed.primary_evidence_snapshot_id not in confirmed.evidence_snapshot_ids:
        return ProvenanceValidationResult(
            False, "approval_candidate_binding_mismatch",
            "primary not in evidence_snapshot_ids"
        )
    
    # 13. Evidence snapshot
    snap = research_db.get_evidence_snapshot(confirmed.primary_evidence_snapshot_id)
    if not snap:
        return ProvenanceValidationResult(
            False, "approval_candidate_binding_mismatch",
            f"Evidence snapshot {confirmed.primary_evidence_snapshot_id} not found"
        )
    
    if snap.get("candidate_id") != confirmed.candidate_id or snap.get("symbol") != confirmed.symbol:
        return ProvenanceValidationResult(
            False, "approval_candidate_binding_mismatch",
            "Evidence snapshot candidate/symbol mismatch"
        )
    
    return ProvenanceValidationResult(True)
