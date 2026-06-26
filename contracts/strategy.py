from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class FrozenStrategyContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _require_non_empty(value: str, field_name: str) -> str:
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")
    return value


class StrategyTemplateDefinition(FrozenStrategyContract):
    template_id: str
    version: str
    template_hash: str
    hypothesis_types: tuple[str, ...]
    core_entry_rule_id: str
    supported_universe_rule_types: tuple[
        Literal["sector_plus_tags", "point_in_time_membership"], ...
    ]
    sample_split_rule_ids: tuple[str, ...]
    benchmark_rule_id: str
    created_at: datetime
    frozen: Literal[True] = True


class BacktestUniverseSpec(FrozenStrategyContract):
    universe_spec_id: str
    universe_rule_type: Literal["sector_plus_tags", "point_in_time_membership"]
    sector: str | None = None
    chain_layer_tags: tuple[str, ...] = ()
    membership_source: str
    membership_effective_from: date
    membership_effective_to: date
    snapshot_date: date
    include_delisted: Literal[True] = True
    membership_snapshot_ids: tuple[str, ...]
    quality_status: Literal["ok", "degraded", "insufficient"]
    gaps: tuple[str, ...] = ()
    frozen: Literal[True] = True

    @model_validator(mode="after")
    def validate_membership_window(self) -> "BacktestUniverseSpec":
        if self.membership_effective_from > self.membership_effective_to:
            raise ValueError("membership_effective_from cannot exceed membership_effective_to")
        if not self.membership_snapshot_ids and self.quality_status != "insufficient":
            raise ValueError("membership_snapshot_ids required unless quality is insufficient")
        return self


class ForwardWatchlistSnapshot(FrozenStrategyContract):
    watchlist_snapshot_id: str
    theme_id: str
    confirmed_candidate_ids: tuple[str, ...]
    symbols: tuple[str, ...]
    snapshot_date: date
    created_at: datetime
    forward_only: Literal[True] = True
    frozen: Literal[True] = True


class StrategyDraft(FrozenStrategyContract):
    strategy_revision_id: str
    theme_id: str
    hypothesis_id: str
    strategy_template_id: str
    strategy_template_version: str
    strategy_template_hash: str
    hypothesis_source_snapshot_id: str
    backtest_universe_spec_id: str
    strategy_config_json: str
    sample_split_rule_id: str
    created_at: datetime
    frozen: Literal[True] = True

    @field_validator("strategy_revision_id")
    @classmethod
    def revision_id_must_be_non_empty(cls, value: str) -> str:
        return _require_non_empty(value, "strategy_revision_id")


class StrategyLifecycleState(FrozenStrategyContract):
    lifecycle_state_id: str
    strategy_revision_id: str
    state_version: int = Field(ge=1)
    state: Literal["draft", "prototype_passed"]
    source_record_id: str
    recorded_at: datetime
    recorded_by: str
    frozen: Literal[True] = True


class ResearchProtocolSnapshot(FrozenStrategyContract):
    protocol_snapshot_id: str
    theme_id: str
    hypothesis_source_snapshot_id: str
    strategy_revision_id: str
    sample_split_rule_id: str
    oos_window_rule_id: str
    oos_window_rule_params_json: str
    oos_window_start: date
    oos_window_end: date
    shared_oos_window_id: str
    backtest_universe_spec_id: str
    data_snapshot_id: str
    kill_criteria_snapshot_id: str
    prototype_gate_thresholds_json: str
    strategy_config_hash: str
    data_snapshot_hash: str
    gate_criteria_hash: str
    frozen_at: datetime
    frozen_by: str
    frozen: Literal[True] = True

    @model_validator(mode="after")
    def validate_protocol(self) -> "ResearchProtocolSnapshot":
        for name in (
            "strategy_config_hash",
            "data_snapshot_hash",
            "gate_criteria_hash",
        ):
            _require_non_empty(getattr(self, name), name)
        if self.oos_window_start > self.oos_window_end:
            raise ValueError("oos_window_start cannot exceed oos_window_end")
        return self


class OOSEvaluationLedger(FrozenStrategyContract):
    ledger_snapshot_id: str
    theme_id: str
    hypothesis_source_snapshot_id: str
    ledger_version: int = Field(ge=1)
    oos_evaluation_count: int = Field(ge=0, le=3)
    oos_budget_limit: Literal[3] = 3
    next_oos_draw_index: int = Field(ge=1, le=3)
    budget_status: Literal["available", "reserved", "oos_budget_exhausted"]
    completed_evaluation_ids: tuple[str, ...] = ()
    active_reservation_ids: tuple[str, ...] = ()
    report_ids: tuple[str, ...] = ()
    recorded_at: datetime
    frozen: Literal[True] = True


class ImmutableBacktestReport(FrozenStrategyContract):
    report_id: str
    theme_id: str
    strategy_revision_id: str
    protocol_snapshot_id: str
    strategy_config_hash: str
    data_snapshot_hash: str
    gate_criteria_hash: str
    evaluation_mode: Literal[
        "in_sample", "out_of_sample", "prototype_sanity_check_only"
    ]
    oos_draw_index: int | None = Field(default=None, ge=1, le=3)
    shared_oos_window_id: str | None = None
    multiple_comparison_flag: bool = False
    report_payload_json: str
    integrity_status: Literal["valid", "invalid"]
    generated_at: datetime
    report_hash: str
    frozen: Literal[True] = True


class PrototypeGateResultV2(FrozenStrategyContract):
    gate_result_id: str
    report_id: str
    strategy_revision_id: str
    protocol_snapshot_id: str
    verdict: Literal[
        "rejected",
        "needs_review",
        "candidate_for_prototype_passed",
    ]
    checks_json: str
    blocking_issues: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    strategy_config_hash: str
    data_snapshot_hash: str
    gate_criteria_hash: str
    oos_draw_index: int | None = Field(default=None, ge=1, le=3)
    shared_oos_window_id: str | None = None
    multiple_comparison_flag: bool = False
    generated_at: datetime
    gate_result_hash: str
    frozen: Literal[True] = True


class HumanPromotionConfirmation(FrozenStrategyContract):
    human_confirmation_id: str
    strategy_revision_id: str
    gate_result_id: str
    decision: Literal["approve", "reject"]
    confirmed_by: str
    confirmed_at: datetime
    frozen: Literal[True] = True


class HumanConfirmationConsumption(FrozenStrategyContract):
    consumption_id: str
    human_confirmation_id: str
    strategy_revision_id: str
    gate_result_id: str
    promotion_id: str
    consumed_at: datetime
    consumed_by: str
    frozen: Literal[True] = True


class StrategyPromotionRecord(FrozenStrategyContract):
    promotion_id: str
    strategy_revision_id: str
    gate_result_id: str
    report_id: str
    protocol_snapshot_id: str
    human_confirmation_id: str
    previous_state: Literal["draft"]
    new_state: Literal["prototype_passed"]
    promoted_by: str
    promoted_at: datetime
    frozen: Literal[True] = True


def admit_formal_backtest_universe(
    universe: BacktestUniverseSpec,
) -> BacktestUniverseSpec:
    if not isinstance(universe, BacktestUniverseSpec):
        raise TypeError("formal backtest requires BacktestUniverseSpec")
    return universe
