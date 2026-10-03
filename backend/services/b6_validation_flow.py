"""B6 final vertical flow orchestration."""
from __future__ import annotations

from datetime import datetime

from contracts.strategy import StrategyDraft, ResearchProtocolSnapshot
from backend.services.b3_protocol_types import (
    DataSnapshotManifest,
    PointInTimeMembershipSnapshot,
)
from backend.services.b5_oos_types import B6ValidationRunResult
from backend.services.b5_oos_types import B6SameDrawOOSResult
from backend.services.oos_evaluation_controller import OOSEvaluationController
from backend.services.backtest_report_builder import BacktestReportBuilder
from backend.services.prototype_gate_v2 import PrototypeGateV2
from backend.services.gate_explanation_builder import GateExplanationBuilder
from backend.db.strategy import StrategyDB
from backend.services.strategy_promotion_reducer import StrategyPromotionReducer
from contracts.strategy import HumanPromotionConfirmation


class B6ValidationFlow:
    """Thin MVP flow over existing B1-B5 components."""

    def __init__(
        self,
        oos_controller: OOSEvaluationController | None = None,
        report_builder: BacktestReportBuilder | None = None,
        gate: PrototypeGateV2 | None = None,
        explanation_builder: GateExplanationBuilder | None = None,
        strategy_db: StrategyDB | None = None,
        promotion_reducer: StrategyPromotionReducer | None = None,
        oos_budget_ledger=None,  # ponytail: OOSBudgetLedger | None, avoid circular import
    ):
        self.oos_controller = oos_controller or OOSEvaluationController()
        self.report_builder = report_builder or BacktestReportBuilder()
        self.gate = gate or PrototypeGateV2()
        self.explanation_builder = explanation_builder or GateExplanationBuilder()
        self.strategy_db = strategy_db
        self.promotion_reducer = promotion_reducer
        self.oos_budget_ledger = oos_budget_ledger

    def complete_same_draw_validation(
        self,
        *,
        task,
        protocol: ResearchProtocolSnapshot,
        reservation,
        b4_result,
        same_draw_result: B6SameDrawOOSResult,
        b5_bundle: dict,
    ) -> B6ValidationRunResult:
        """Build and persist one already-executed same-draw result."""
        identity = same_draw_result.identity
        if identity.task_id != task.task_id or identity.task_key != task.task_key:
            raise ValueError("same-draw task identity mismatch")
        report = self.report_builder.build_report(
            report_id=f"report_{task.task_id}_{reservation.oos_draw_index}",
            strategy_revision_id=protocol.strategy_revision_id,
            protocol_snapshot_id=protocol.protocol_snapshot_id,
            strategy_config_hash=protocol.strategy_config_hash,
            data_snapshot_hash=protocol.data_snapshot_hash,
            gate_criteria_hash=protocol.gate_criteria_hash,
            oos_draw_index=reservation.oos_draw_index,
            shared_oos_window_id=protocol.shared_oos_window_id,
            b4_result=b4_result,
            adjustment_mode="qfq",
            adjustment_snapshot_fingerprint=b5_bundle["lineage"]["formal_snapshot"]["manifest_sha256"],
            same_draw_result=same_draw_result,
        )
        gate_result = self.gate.evaluate(report, protocol.gate_criteria_hash)
        explanation = self.explanation_builder.build_explanation(
            report_id=report.report_id,
            gate_result=gate_result,
        )
        if explanation.report_id != report.report_id or explanation.gate_result_id != gate_result.gate_result_id:
            raise ValueError("same-draw explanation identity mismatch")
        self.strategy_db.store_b6_terminal_result_tx(
            report=report,
            gate_result=gate_result,
            reservation_id=reservation.reservation_id,
            verdict=gate_result.verdict,
            task_id=task.task_id,
            oos_budget_ledger=self.oos_budget_ledger,
        )
        return B6ValidationRunResult(
            run_id=f"b6_{protocol.strategy_revision_id}",
            strategy_revision_id=protocol.strategy_revision_id,
            protocol_snapshot_id=protocol.protocol_snapshot_id,
            report_id=report.report_id,
            gate_result_id=gate_result.gate_result_id,
            explanation_id=explanation.explanation_id,
            promotion_id=None,
            final_state=gate_result.verdict,
            status="completed",
            blocking_reason=None,
            created_at=datetime.now(),
        )

    def run_minimal_validation(
        self,
        *,
        strategy_draft: StrategyDraft | None,
        protocol: ResearchProtocolSnapshot | None,
        manifest: DataSnapshotManifest | None,
        universe: PointInTimeMembershipSnapshot | None,
        b4_qualification: dict | None,
        b4_event_result,
        task_id: str,  # NEW: from application service
        **unexpected_user_parameters,
    ) -> B6ValidationRunResult:
        """
        Run B6 validation flow (minimal MVP).

        Args:
            strategy_draft: StrategyDraft to validate
            protocol: ResearchProtocolSnapshot (frozen)
            manifest: DataSnapshotManifest
            universe: PointInTimeMembershipSnapshot
            b4_qualification: B4 qualification result
            b4_event_result: EventBacktestResult from B4
            task_id: B6 task ID (deterministic, from application service)

        Returns:
            B6ValidationRunResult with final state

        Raises:
            ValueError: If prerequisites missing or user parameters supplied
        """
        # Reject user-supplied technical parameters
        if unexpected_user_parameters:
            raise ValueError(
                "B6 validation flow does not accept user-supplied technical parameters"
            )

        # Validate prerequisites
        if strategy_draft is None:
            raise ValueError("StrategyDraft is required for B6 validation flow")
        if protocol is None:
            raise ValueError("ResearchProtocolSnapshot is required for B6 validation flow")
        if manifest is None:
            raise ValueError("DataSnapshotManifest is required for B6 validation flow")
        if universe is None:
            raise ValueError("PointInTimeMembershipSnapshot is required for B6 validation flow")
        if b4_qualification is None:
            raise ValueError("B4 formal qualification is required for B6 validation flow")
        if b4_event_result is None:
            raise ValueError("B4 event backtest result is required for B6 validation flow")

        # Validate template governance (first gate)
        from backend.services.strategy_template_library import get_template_by_id, convert_to_frozen_contract

        template = get_template_by_id(strategy_draft.strategy_template_id)
        if template is None:
            return B6ValidationRunResult(
                run_id=f"b6_{strategy_draft.strategy_revision_id}",
                strategy_revision_id=strategy_draft.strategy_revision_id,
                protocol_snapshot_id=protocol.protocol_snapshot_id,
                report_id=None,
                gate_result_id=None,
                explanation_id=None,
                promotion_id=None,
                final_state="draft",
                status="blocked",
                blocking_reason=f"Template {strategy_draft.strategy_template_id} not found in template library",
                created_at=datetime.now(),
            )

        frozen_template = convert_to_frozen_contract(template, created_at=datetime.now())

        if frozen_template.governance_status == "candidate":
            return B6ValidationRunResult(
                run_id=f"b6_{strategy_draft.strategy_revision_id}",
                strategy_revision_id=strategy_draft.strategy_revision_id,
                protocol_snapshot_id=protocol.protocol_snapshot_id,
                report_id=None,
                gate_result_id=None,
                explanation_id=None,
                promotion_id=None,
                final_state="draft",
                status="blocked",
                blocking_reason=f"Template {strategy_draft.strategy_template_id} is candidate; B6/OOS/Gate/Promotion require approved template (per Task 1 section 2.3)",
                created_at=datetime.now(),
            )

        if frozen_template.governance_status == "retired":
            return B6ValidationRunResult(
                run_id=f"b6_{strategy_draft.strategy_revision_id}",
                strategy_revision_id=strategy_draft.strategy_revision_id,
                protocol_snapshot_id=protocol.protocol_snapshot_id,
                report_id=None,
                gate_result_id=None,
                explanation_id=None,
                promotion_id=None,
                final_state="draft",
                status="blocked",
                blocking_reason=f"Template {strategy_draft.strategy_template_id} is retired; cannot enter B6/OOS/Gate/Promotion",
                created_at=datetime.now(),
            )

        # Step 1: Validate B3/B4 prerequisites
        self.oos_controller.validate_b3_b4_prerequisites(
            protocol=protocol,
            manifest=manifest,
            universe=universe,
            b4_result=b4_qualification,
        )

        # Step 2: Task precheck (before reserve)
        task = self.strategy_db.get_b6_task_by_id(task_id)
        if not task:
            return B6ValidationRunResult(
                run_id=f"b6_{strategy_draft.strategy_revision_id}",
                strategy_revision_id=strategy_draft.strategy_revision_id,
                protocol_snapshot_id=protocol.protocol_snapshot_id,
                report_id=None, gate_result_id=None, explanation_id=None,
                promotion_id=None, final_state="draft", status="blocked",
                blocking_reason=f"Task {task_id} not found",
                created_at=datetime.now(),
            )
        if task.strategy_revision_id != strategy_draft.strategy_revision_id or task.protocol_snapshot_id != protocol.protocol_snapshot_id:
            return B6ValidationRunResult(
                run_id=f"b6_{strategy_draft.strategy_revision_id}",
                strategy_revision_id=strategy_draft.strategy_revision_id,
                protocol_snapshot_id=protocol.protocol_snapshot_id,
                report_id=None, gate_result_id=None, explanation_id=None,
                promotion_id=None, final_state="draft", status="blocked",
                blocking_reason=f"Task {task_id} revision/protocol mismatch",
                created_at=datetime.now(),
            )
        if task.status != "running":
            return B6ValidationRunResult(
                run_id=f"b6_{strategy_draft.strategy_revision_id}",
                strategy_revision_id=strategy_draft.strategy_revision_id,
                protocol_snapshot_id=protocol.protocol_snapshot_id,
                report_id=None, gate_result_id=None, explanation_id=None,
                promotion_id=None, final_state="draft", status="blocked",
                blocking_reason=f"Task {task_id} status={task.status}, expected running",
                created_at=datetime.now(),
            )

        # Step 3: Durable budget guard + reserve
        if self.oos_budget_ledger is None:
            return B6ValidationRunResult(
                run_id=f"b6_{strategy_draft.strategy_revision_id}",
                strategy_revision_id=strategy_draft.strategy_revision_id,
                protocol_snapshot_id=protocol.protocol_snapshot_id,
                report_id=None,
                gate_result_id=None,
                explanation_id=None,
                promotion_id=None,
                final_state="draft",
                status="blocked",
                blocking_reason="No durable OOS budget ledger injected; validation infrastructure unavailable",
                created_at=datetime.now(),
            )

        # ponytail: reserve with task binding
        try:
            reservation = self.oos_budget_ledger.reserve_oos_draw(
                theme_id=strategy_draft.theme_id,
                hypothesis_source_snapshot_id=protocol.hypothesis_source_snapshot_id,
                strategy_config_hash=protocol.strategy_config_hash,
                data_snapshot_hash=protocol.data_snapshot_hash,
                gate_criteria_hash=protocol.gate_criteria_hash,
                shared_oos_window_id=protocol.shared_oos_window_id,
                idempotency_key=task.task_key,
                task_key=task.task_key,
                protocol_snapshot_id=protocol.protocol_snapshot_id,
            )
        except ValueError as e:
            # Budget exhausted or guard rejection
            return B6ValidationRunResult(
                run_id=f"b6_{strategy_draft.strategy_revision_id}",
                strategy_revision_id=strategy_draft.strategy_revision_id,
                protocol_snapshot_id=protocol.protocol_snapshot_id,
                report_id=None,
                gate_result_id=None,
                explanation_id=None,
                promotion_id=None,
                final_state="draft",
                status="blocked",
                blocking_reason=f"OOS budget unavailable: {e}",
                created_at=datetime.now(),
            )

        # If reservation is terminal (idempotent retry), replay from persisted metadata
        if reservation.status in ("completed", "failed", "released"):
            meta = self.oos_budget_ledger.get_terminal_metadata(reservation.reservation_id)

            if meta["status"] == "completed":
                if not meta["verdict"] or not meta["report_id"]:
                    raise ValueError(f"Completed reservation {reservation.reservation_id} missing verdict or report_id")
                if meta["verdict"] not in (
                    "rejected",
                    "needs_review",
                    "candidate_for_prototype_passed",
                ):
                    raise ValueError(
                        f"Completed reservation {reservation.reservation_id} has invalid persisted verdict"
                    )
                return B6ValidationRunResult(
                    run_id=f"b6_{strategy_draft.strategy_revision_id}",
                    strategy_revision_id=strategy_draft.strategy_revision_id,
                    protocol_snapshot_id=protocol.protocol_snapshot_id,
                    report_id=meta["report_id"],
                    gate_result_id=None,  # ponytail: not persisted, cannot reconstruct
                    explanation_id=None,
                    promotion_id=None,
                    final_state=meta["verdict"],
                    status="completed",
                    blocking_reason=None,
                    created_at=datetime.now(),
                )
            elif meta["status"] == "failed":
                return B6ValidationRunResult(
                    run_id=f"b6_{strategy_draft.strategy_revision_id}",
                    strategy_revision_id=strategy_draft.strategy_revision_id,
                    protocol_snapshot_id=protocol.protocol_snapshot_id,
                    report_id=None,
                    gate_result_id=None,
                    explanation_id=None,
                    promotion_id=None,
                    final_state="draft",
                    status="failed",
                    blocking_reason=meta["terminal_reason"],
                    created_at=datetime.now(),
                )
            else:  # released
                return B6ValidationRunResult(
                    run_id=f"b6_{strategy_draft.strategy_revision_id}",
                    strategy_revision_id=strategy_draft.strategy_revision_id,
                    protocol_snapshot_id=protocol.protocol_snapshot_id,
                    report_id=None,
                    gate_result_id=None,
                    explanation_id=None,
                    promotion_id=None,
                    final_state="draft",
                    status="blocked",
                    blocking_reason=meta["terminal_reason"],
                    created_at=datetime.now(),
                )

        # Step 4: Start execution
        # Step 4: Start execution
        try:
            self.oos_budget_ledger.start_execution(reservation.reservation_id)
        except Exception as e:
            self.oos_budget_ledger.release_pre_execution(reservation.reservation_id, f"start_failed: {e}")
            raise

        # Step 5: Build report
        try:
            report = self.report_builder.build_report(
                report_id=f"report_{strategy_draft.strategy_revision_id}_{reservation.oos_draw_index}",
                strategy_revision_id=strategy_draft.strategy_revision_id,
                protocol_snapshot_id=protocol.protocol_snapshot_id,
                strategy_config_hash=protocol.strategy_config_hash,
                data_snapshot_hash=protocol.data_snapshot_hash,
                gate_criteria_hash=protocol.gate_criteria_hash,
                oos_draw_index=reservation.oos_draw_index,
                shared_oos_window_id=protocol.shared_oos_window_id,
                b4_result=b4_event_result,
                adjustment_mode="qfq",
                adjustment_snapshot_fingerprint=manifest.adjustment_factor_fingerprint,
            )
        except Exception as e:
            # Post-start failure: write failure terminal then re-raise
            try:
                self.strategy_db.conn.execute("BEGIN IMMEDIATE")
                self.oos_budget_ledger.fail_reservation_within_tx(
                    self.strategy_db.conn, reservation.reservation_id, f"report_build_failed: {e}"
                )
                cursor = self.strategy_db.update_b6_task_status(task_id, "failed", datetime.now(), "report_build_failed", str(e))
                if cursor.rowcount != 1:
                    raise RuntimeError(f"Task {task_id} UPDATE affected {cursor.rowcount} rows")
                self.strategy_db.conn.commit()
            except Exception as inner:
                self.strategy_db.conn.rollback()
                raise RuntimeError(f"Failure terminal also failed: {inner}") from e
            raise

        # Step 6: Evaluate Gate
        try:
            gate_result = self.gate.evaluate(report, protocol.gate_criteria_hash)
        except Exception as e:
            # Gate failed: write failure terminal then re-raise
            try:
                self.strategy_db.conn.execute("BEGIN IMMEDIATE")
                self.oos_budget_ledger.fail_reservation_within_tx(
                    self.strategy_db.conn, reservation.reservation_id, f"gate_failed: {e}"
                )
                cursor = self.strategy_db.update_b6_task_status(task_id, "failed", datetime.now(), "gate_failed", str(e))
                if cursor.rowcount != 1:
                    raise RuntimeError(f"Task {task_id} UPDATE affected {cursor.rowcount} rows")
                self.strategy_db.conn.commit()
            except Exception as inner:
                self.strategy_db.conn.rollback()
                raise RuntimeError(f"Failure terminal also failed: {inner}") from e
            raise

        # Step 7: Build explanation
        try:
            explanation = self.explanation_builder.build_explanation(
                report_id=report.report_id,
                gate_result=gate_result,
            )
        except Exception as e:
            # Explanation failed: write failure terminal then re-raise
            try:
                self.strategy_db.conn.execute("BEGIN IMMEDIATE")
                self.oos_budget_ledger.fail_reservation_within_tx(
                    self.strategy_db.conn, reservation.reservation_id, f"explanation_failed: {e}"
                )
                cursor = self.strategy_db.update_b6_task_status(task_id, "failed", datetime.now(), "explanation_failed", str(e))
                if cursor.rowcount != 1:
                    raise RuntimeError(f"Task {task_id} UPDATE affected {cursor.rowcount} rows")
                self.strategy_db.conn.commit()
            except Exception as inner:
                self.strategy_db.conn.rollback()
                raise RuntimeError(f"Failure terminal also failed: {inner}") from e
            raise

        # Step 8: Terminal transaction (report + Gate + completed ledger + task completed)
        try:
            self.strategy_db.store_b6_terminal_result_tx(
                report=report,
                gate_result=gate_result,
                reservation_id=reservation.reservation_id,
                verdict=gate_result.verdict,
                task_id=task_id,
                oos_budget_ledger=self.oos_budget_ledger,
            )
        except Exception as e:
            # Terminal write failed - write failure terminal then re-raise
            try:
                self.strategy_db.conn.execute("BEGIN IMMEDIATE")
                self.oos_budget_ledger.fail_reservation_within_tx(
                    self.strategy_db.conn, reservation.reservation_id, f"terminal_write_failed: {e}"
                )
                cursor = self.strategy_db.update_b6_task_status(task_id, "failed", datetime.now(), "terminal_write_failed", str(e))
                if cursor.rowcount != 1:
                    raise RuntimeError(f"Task {task_id} UPDATE affected {cursor.rowcount} rows")
                self.strategy_db.conn.commit()
            except Exception as inner:
                self.strategy_db.conn.rollback()
                raise RuntimeError(f"Failure terminal also failed: {inner}") from e
            raise

        # Step 9: Return result (no Promotion in B6)
        return B6ValidationRunResult(
            run_id=f"b6_{strategy_draft.strategy_revision_id}",
            strategy_revision_id=strategy_draft.strategy_revision_id,
            protocol_snapshot_id=protocol.protocol_snapshot_id,
            report_id=report.report_id,
            gate_result_id=gate_result.gate_result_id,
            explanation_id=explanation.explanation_id,
            promotion_id=None,  # No Promotion in B6
            final_state=gate_result.verdict,
            status="completed",
            blocking_reason=None,
            created_at=datetime.now(),
        )
