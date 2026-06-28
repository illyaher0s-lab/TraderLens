"""B6 final vertical flow orchestration."""
from __future__ import annotations

from datetime import datetime

from contracts.strategy import StrategyDraft, ResearchProtocolSnapshot
from backend.services.b3_protocol_types import (
    DataSnapshotManifest,
    PointInTimeMembershipSnapshot,
)
from backend.services.b5_oos_types import B6ValidationRunResult
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
    ):
        self.oos_controller = oos_controller or OOSEvaluationController()
        self.report_builder = report_builder or BacktestReportBuilder()
        self.gate = gate or PrototypeGateV2()
        self.explanation_builder = explanation_builder or GateExplanationBuilder()
        self.strategy_db = strategy_db
        self.promotion_reducer = promotion_reducer

    def run_minimal_validation(
        self,
        *,
        strategy_draft: StrategyDraft | None,
        protocol: ResearchProtocolSnapshot | None,
        manifest: DataSnapshotManifest | None,
        universe: PointInTimeMembershipSnapshot | None,
        b4_qualification: dict | None,
        b4_event_result,
        human_decision: str | None,
        **unexpected_user_parameters,
    ) -> B6ValidationRunResult:
        """
        Run minimal B6 validation flow.

        Args:
            strategy_draft: StrategyDraft (required)
            protocol: ResearchProtocolSnapshot (required)
            manifest: DataSnapshotManifest (required)
            universe: PointInTimeMembershipSnapshot (required)
            b4_qualification: B4 formal qualification (required)
            b4_event_result: B4 event backtest result (required)
            human_decision: "approve" or "reject" or None

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

        # Validate human_decision
        if human_decision not in (None, "approve", "reject"):
            raise ValueError("human_decision must be None, 'approve', or 'reject'")

        # Step 1: Validate B3/B4 prerequisites
        self.oos_controller.validate_b3_b4_prerequisites(
            protocol=protocol,
            manifest=manifest,
            universe=universe,
            b4_result=b4_qualification,
        )

        # Step 2: Build report
        report = self.report_builder.build_report(
            report_id=f"report_{strategy_draft.strategy_revision_id}",
            strategy_revision_id=strategy_draft.strategy_revision_id,
            protocol_snapshot_id=protocol.protocol_snapshot_id,
            strategy_config_hash=protocol.strategy_config_hash,
            data_snapshot_hash=protocol.data_snapshot_hash,
            gate_criteria_hash=protocol.gate_criteria_hash,
            oos_draw_index=1,
            shared_oos_window_id=protocol.shared_oos_window_id,
            b4_result=b4_event_result,
            adjustment_mode="qfq",
            adjustment_snapshot_fingerprint=manifest.adjustment_factor_fingerprint,
        )

        # Step 3: Evaluate Gate
        gate_result = self.gate.evaluate(report, protocol.gate_criteria_hash)

        # Step 4: Build explanation
        explanation = self.explanation_builder.build_explanation(report.report_id, gate_result)

        # Step 5: Determine final state based on Gate + human decision
        promotion_id = None
        final_state = gate_result.verdict

        # Only attempt promotion if DB and reducer available
        if (
            self.strategy_db is not None
            and self.promotion_reducer is not None
            and gate_result.verdict == "candidate_for_prototype_passed"
            and human_decision == "approve"
        ):
            # Store artifacts in DB
            self.strategy_db.store_backtest_report(report)
            self.strategy_db.store_gate_result(gate_result)

            # Store human confirmation
            confirmation = HumanPromotionConfirmation(
                human_confirmation_id=f"confirmation_{strategy_draft.strategy_revision_id}",
                strategy_revision_id=strategy_draft.strategy_revision_id,
                gate_result_id=gate_result.gate_result_id,
                decision="approve",
                confirmed_by="test_user",
                confirmed_at=datetime.now(),
            )
            self.strategy_db.store_human_confirmation(confirmation)

            # Promote via reducer. Reducer failures must remain loud.
            promotion = self.promotion_reducer.promote_to_prototype_passed(
                strategy_revision_id=strategy_draft.strategy_revision_id,
                gate_result_id=gate_result.gate_result_id,
                human_confirmation_id=confirmation.human_confirmation_id,
                promoted_by="test_user",
            )
            promotion_id = promotion.promotion_id
            final_state = "prototype_passed"

        return B6ValidationRunResult(
            run_id=f"b6_{strategy_draft.strategy_revision_id}",
            strategy_revision_id=strategy_draft.strategy_revision_id,
            protocol_snapshot_id=protocol.protocol_snapshot_id,
            report_id=report.report_id,
            gate_result_id=gate_result.gate_result_id,
            explanation_id=explanation.explanation_id,
            promotion_id=promotion_id,
            final_state=final_state,
            status="completed",
            blocking_reason=None,
            created_at=datetime.now(),
        )
