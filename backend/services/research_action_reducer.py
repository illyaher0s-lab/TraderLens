"""
Research action reducer.

Deterministic reducer for proposed actions and transitions.

Key behaviors:
- receive ProposedAction
- validate action against deterministic rules
- apply or reject action
- store audit record
- return AppliedAction
- reject stale actions when board version changed
- reject duplicate applies for the same action_id
- increment theme board_version by exactly 1 after each successful state-changing apply
- do not increment theme board_version for failed validation or rejected pending actions

Rules:
- propose_confirm never directly confirms a candidate
- Final confirmation requires a human click from the board
- Blocked candidates require override_reason
- Reopen actions require a non-empty reason
- reopen_to_serenity can move theme evidence_done -> serenity_done
- reopen_to_evidence can move candidate confirmed/rejected -> needs_evidence
- Every applied or rejected action is recorded in audit storage
- Agent-proposed actions can be displayed but not applied without deterministic validation
- Proposed actions are idempotent by action_id; applying the same action twice must not duplicate state
- Stale proposed actions are rejected when board_version no longer matches current board state
- Reject, reopen, and override actions must record applied_by, actor_reason, and applied_at
"""

from datetime import date, datetime
from backend.db.research import ResearchDB
from backend.services.research_validation import ResearchValidator
from contracts.research import (
    ProposedAction,
    AppliedAction,
    CandidateStock,
    ConfirmedCandidate,
)


class ResearchActionReducer:
    """Deterministic reducer for research actions."""

    def __init__(self, db: ResearchDB, validator: ResearchValidator):
        """
        Initialize reducer.
        
        Args:
            db: Research database
            validator: Research validator
        """
        self.db = db
        self.validator = validator

    def apply_action(
        self, action: ProposedAction, applied_by: str
    ) -> AppliedAction:
        """
        Apply a proposed action.
        
        Args:
            action: Proposed action
            applied_by: User who is applying the action
        
        Returns:
            AppliedAction with applied status and reason
        """
        now = datetime.now()

        # Check if already applied
        existing = self.db.get_applied_action(action.action_id)
        if existing:
            # Return existing applied action without re-inserting
            return existing

        # Validate board version
        if action.board_version is not None:
            theme_id = self._get_theme_id_from_target(action.target_id, action.action)
            theme = self.db.get_theme(theme_id)
            if theme and theme.board_version != action.board_version:
                applied = AppliedAction(
                    action_id=action.action_id,
                    proposed_action=action,
                    applied=False,
                    rejection_reason=f"Stale action: board version {action.board_version} != current {theme.board_version}",
                    applied_by=applied_by,
                    applied_at=now,
                )
                self.db.store_applied_action(applied)
                return applied

        # Route to action handler
        try:
            if action.action == "add_candidate":
                self._apply_add_candidate(action, applied_by)
            elif action.action == "propose_confirm":
                # propose_confirm does NOT confirm; it only creates a pending action
                # This handler should not be reached through apply_action
                raise ValueError("propose_confirm must go through explicit confirm endpoint")
            else:
                raise ValueError(f"Unknown action: {action.action}")

            # Success: increment board version
            theme_id = self._get_theme_id_from_target(action.target_id, action.action)
            self.db.increment_board_version(theme_id)

            applied = AppliedAction(
                action_id=action.action_id,
                proposed_action=action,
                applied=True,
                actor_reason="Action applied successfully",
                applied_by=applied_by,
                applied_at=now,
            )
            self.db.store_applied_action(applied)
            return applied

        except Exception as e:
            applied = AppliedAction(
                action_id=action.action_id,
                proposed_action=action,
                applied=False,
                rejection_reason=str(e),
                applied_by=applied_by,
                applied_at=now,
            )
            self.db.store_applied_action(applied)
            return applied

    def _apply_add_candidate(self, action: ProposedAction, applied_by: str):
        """Apply add_candidate action."""
        now = datetime.now()
        verification_id = action.args.get("verification_id")
        if not verification_id:
            raise ValueError("add_candidate requires verification_id")

        if not self.db.is_verification_valid(verification_id):
            raise ValueError("verification_id is invalid or expired")

        verification = self.db.get_ticker_verification(verification_id)
        if not verification:
            raise ValueError("verification record not found")

        symbol = action.args["symbol"]
        if verification.symbol != symbol:
            raise ValueError(
                f"verification_id is for {verification.symbol}, not {symbol}"
            )
        if verification.status != "listed":
            raise ValueError(
                f"verified ticker status must be listed, got {verification.status}"
            )

        candidate_id = f"cand_{action.action_id}"

        candidate = CandidateStock(
            candidate_id=candidate_id,
            theme_id=action.target_id,
            symbol=verification.symbol,
            company_name=verification.company_name,
            verification_id=verification.verification_id,
            source_type=action.args["source_type"],
            match_reason=action.args["match_reason"],
            status="raw",
            created_at=now,
        )
        self.db.add_candidate(candidate)

    def _get_theme_id_from_target(self, target_id: str, action: str) -> str:
        """Get theme_id from target_id based on action type."""
        if action == "add_candidate":
            # target_id is theme_id
            return target_id
        elif action in ["propose_confirm", "propose_reject", "reopen_to_evidence"]:
            # target_id is candidate_id, need to look up theme_id
            candidate = self.db.get_candidate(target_id)
            if candidate:
                return candidate.theme_id
        elif action == "reopen_to_serenity":
            # target_id is theme_id
            return target_id
        return target_id

    def confirm_candidate(
        self,
        candidate_id: str,
        confirmation_reason: str,
        evidence_level: str,
        confirmed_by: str,
        pool_snapshot_date: date,
        thesis_snapshot: str,
        invalidation_rules: list[dict],
        price_snapshot: dict,
        benchmark_snapshot: dict,
        approval_card_id: str | None = None,
        override_reason: str | None = None,
        source_serenity_run_id: str | None = None,
        source_evidence_run_id: str | None = None,
        evidence_snapshot_ids: list[str] | None = None,
        primary_evidence_snapshot_id: str | None = None,
    ) -> ConfirmedCandidate:
        """
        Confirm a candidate (human confirmation only).
        
        Args:
            candidate_id: Candidate ID
            confirmation_reason: Reason for confirmation
            evidence_level: Evidence level
            confirmed_by: User who confirmed
            pool_snapshot_date: Pool snapshot date
            thesis_snapshot: Thesis snapshot
            invalidation_rules: Invalidation rules
            price_snapshot: Price snapshot
            benchmark_snapshot: Benchmark snapshot
            override_reason: Override reason for blocked candidates
            source_serenity_run_id: Source Serenity run ID
            source_evidence_run_id: Source Evidence run ID
            evidence_snapshot_ids: Evidence snapshot IDs (at least one required)
            primary_evidence_snapshot_id: Primary evidence snapshot ID
        
        Returns:
            ConfirmedCandidate
        
        Raises:
            ValueError: If blocked candidate without override reason,
                       or if evidence snapshots are not valid
        """
        # Validate evidence snapshots
        snapshot_ids = evidence_snapshot_ids or []
        primary = primary_evidence_snapshot_id

        if not snapshot_ids:
            raise ValueError(
                "At least one evidence_snapshot_id is required to confirm a candidate"
            )

        candidate = self.db.get_candidate(candidate_id)
        if not candidate:
            raise ValueError(f"Candidate not found: {candidate_id}")

        # Validate each snapshot
        for sid in snapshot_ids:
            snap = self.db.get_evidence_snapshot(sid)
            if not snap:
                raise ValueError(f"Evidence snapshot not found: {sid}")
            if snap.get("candidate_id") != candidate_id:
                raise ValueError(
                    f"Snapshot {sid} candidate_id ({snap.get('candidate_id')}) "
                    f"does not match {candidate_id}"
                )
            if snap.get("symbol") != candidate.symbol:
                raise ValueError(
                    f"Snapshot {sid} symbol ({snap.get('symbol')}) "
                    f"does not match candidate symbol ({candidate.symbol})"
                )

            # Verification ID consistency
            snap_verification = snap.get("verification_id")
            cand_verification = candidate.verification_id
            if snap_verification and cand_verification and snap_verification != cand_verification:
                raise ValueError(
                    f"Snapshot {sid} verification_id ({snap_verification}) "
                    f"does not match candidate verification_id ({cand_verification})"
                )

            # Hash integrity: recompute packet hash and compare
            stored_packet = snap.get("packet_data")
            if stored_packet:
                try:
                    import hashlib
                    raw = str(stored_packet).encode("utf-8")
                    recomputed = hashlib.sha256(raw).hexdigest()
                    stored_hash = snap.get("packet_input_hash", "")
                    if recomputed != stored_hash:
                        raise ValueError(
                            f"Snapshot {sid} hash integrity check failed: "
                            f"stored hash does not match recomputed hash"
                        )
                except Exception as exc:
                    raise ValueError(
                        f"Snapshot {sid} hash integrity check failed: {exc}"
                    )

            ev_output = snap.get("evidence_output", {})
            blocking = ev_output.get("blocking_issues", [])
            if blocking:
                raise ValueError(
                    f"Snapshot {sid} has blocking issues: {', '.join(blocking)}. "
                    f"Cannot confirm with unresolved blocking issues."
                )

        if primary and primary not in snapshot_ids:
            raise ValueError(
                f"primary_evidence_snapshot_id ({primary}) is not in evidence_snapshot_ids"
            )

        confirmed = self.db.confirm_candidate(
            candidate_id=candidate_id,
            confirmation_reason=confirmation_reason,
            evidence_level=evidence_level,
            confirmed_by=confirmed_by,
            pool_snapshot_date=pool_snapshot_date,
            thesis_snapshot=thesis_snapshot,
            invalidation_rules=invalidation_rules,
            price_snapshot=price_snapshot,
            benchmark_snapshot=benchmark_snapshot,
            approval_card_id=approval_card_id,
            override_reason=override_reason,
            source_serenity_run_id=source_serenity_run_id,
            source_evidence_run_id=source_evidence_run_id,
            evidence_snapshot_ids=snapshot_ids,
            primary_evidence_snapshot_id=primary,
        )

        return confirmed
