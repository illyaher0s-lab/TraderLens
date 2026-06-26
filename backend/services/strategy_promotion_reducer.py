from __future__ import annotations

import hashlib
from datetime import datetime

from backend.db.strategy import StrategyDB
from contracts.strategy import (
    HumanConfirmationConsumption,
    StrategyLifecycleState,
    StrategyPromotionRecord,
)


def _stable_id(prefix: str, *parts: str) -> str:
    payload = "|".join(parts).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(payload).hexdigest()[:24]}"


class StrategyPromotionReducer:
    def __init__(self, db: StrategyDB):
        self.db = db

    def promote_to_prototype_passed(
        self,
        strategy_revision_id: str,
        gate_result_id: str,
        human_confirmation_id: str,
        promoted_by: str,
    ) -> StrategyPromotionRecord:
        existing = self.db._get_promotion_by_strategy(strategy_revision_id)
        if existing is not None:
            if (
                existing.gate_result_id == gate_result_id
                and existing.human_confirmation_id == human_confirmation_id
            ):
                return existing
            raise ValueError("strategy already promoted by a different gate")

        draft = self.db.get_strategy_draft(strategy_revision_id)
        if draft is None:
            raise ValueError("strategy draft not found")

        current_state = self.db.get_latest_lifecycle_state(strategy_revision_id)
        if current_state is None or current_state.state != "draft":
            raise ValueError("strategy lifecycle state must be draft")

        gate = self.db.get_gate_result(gate_result_id)
        if gate is None:
            raise ValueError("gate result not found")
        if gate.strategy_revision_id != strategy_revision_id:
            raise ValueError("gate result belongs to another strategy")
        if gate.verdict != "candidate_for_prototype_passed":
            raise ValueError(
                "gate verdict must be candidate_for_prototype_passed"
            )

        report = self.db.get_backtest_report(gate.report_id)
        if report is None:
            raise ValueError("backtest report not found")
        if report.integrity_status != "valid":
            raise ValueError("backtest report integrity is invalid")

        protocol = self.db.get_protocol_snapshot(gate.protocol_snapshot_id)
        if protocol is None:
            raise ValueError("research protocol snapshot not found")

        expected_hashes = (
            protocol.strategy_config_hash,
            protocol.data_snapshot_hash,
            protocol.gate_criteria_hash,
        )
        if (
            gate.strategy_config_hash,
            gate.data_snapshot_hash,
            gate.gate_criteria_hash,
        ) != expected_hashes:
            raise ValueError("gate/protocol hash mismatch")
        if (
            report.strategy_config_hash,
            report.data_snapshot_hash,
            report.gate_criteria_hash,
        ) != expected_hashes:
            raise ValueError("report/protocol hash mismatch")

        confirmation = self.db.get_human_confirmation(human_confirmation_id)
        if confirmation is None:
            raise ValueError("human confirmation not found")
        if confirmation.decision != "approve":
            raise ValueError("human confirmation must approve promotion")
        if confirmation.strategy_revision_id != strategy_revision_id:
            raise ValueError("human confirmation belongs to another strategy")
        if confirmation.gate_result_id != gate_result_id:
            raise ValueError("human confirmation belongs to another gate")
        if self.db._confirmation_is_consumed(human_confirmation_id):
            raise ValueError("human confirmation already consumed")

        now = datetime.now()
        promotion_id = _stable_id(
            "promotion",
            strategy_revision_id,
            gate_result_id,
            human_confirmation_id,
        )
        promotion = StrategyPromotionRecord(
            promotion_id=promotion_id,
            strategy_revision_id=strategy_revision_id,
            gate_result_id=gate_result_id,
            report_id=report.report_id,
            protocol_snapshot_id=protocol.protocol_snapshot_id,
            human_confirmation_id=human_confirmation_id,
            previous_state="draft",
            new_state="prototype_passed",
            promoted_by=promoted_by,
            promoted_at=now,
            frozen=True,
        )
        consumption = HumanConfirmationConsumption(
            consumption_id=_stable_id(
                "confirmation_consumption",
                human_confirmation_id,
                promotion_id,
            ),
            human_confirmation_id=human_confirmation_id,
            strategy_revision_id=strategy_revision_id,
            gate_result_id=gate_result_id,
            promotion_id=promotion_id,
            consumed_at=now,
            consumed_by=promoted_by,
            frozen=True,
        )
        lifecycle_state = StrategyLifecycleState(
            lifecycle_state_id=_stable_id(
                "lifecycle",
                strategy_revision_id,
                "2",
                promotion_id,
            ),
            strategy_revision_id=strategy_revision_id,
            state_version=2,
            state="prototype_passed",
            source_record_id=promotion_id,
            recorded_at=now,
            recorded_by=promoted_by,
            frozen=True,
        )
        self.db._commit_validated_promotion(
            promotion,
            consumption,
            lifecycle_state,
        )
        return promotion
