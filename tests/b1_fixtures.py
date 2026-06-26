from datetime import date, datetime

from contracts.strategy import (
    BacktestUniverseSpec,
    ForwardWatchlistSnapshot,
    HumanPromotionConfirmation,
    ImmutableBacktestReport,
    OOSEvaluationLedger,
    PrototypeGateResultV2,
    ResearchProtocolSnapshot,
    StrategyDraft,
    StrategyLifecycleState,
    StrategyTemplateDefinition,
)


NOW = datetime(2026, 6, 26, 9, 0, 0)


def make_template_definition() -> StrategyTemplateDefinition:
    return StrategyTemplateDefinition(
        template_id="theme_momentum_breakout_v1",
        version="v1",
        template_hash="template_hash_001",
        hypothesis_types=("theme_momentum",),
        core_entry_rule_id="breakout_entry",
        supported_universe_rule_types=("sector_plus_tags",),
        sample_split_rule_ids=("fixed_ratio_70_30",),
        benchmark_rule_id="theme_then_industry_then_equal_weight",
        created_at=NOW,
        frozen=True,
    )


def make_backtest_universe() -> BacktestUniverseSpec:
    return BacktestUniverseSpec(
        universe_spec_id="universe_001",
        universe_rule_type="sector_plus_tags",
        sector="electrical_equipment",
        chain_layer_tags=("battery",),
        membership_source="tushare_point_in_time",
        membership_effective_from=date(2020, 1, 1),
        membership_effective_to=date(2025, 12, 31),
        snapshot_date=date(2025, 12, 31),
        include_delisted=True,
        membership_snapshot_ids=("membership_001",),
        quality_status="ok",
        gaps=(),
        frozen=True,
    )


def make_forward_watchlist() -> ForwardWatchlistSnapshot:
    return ForwardWatchlistSnapshot(
        watchlist_snapshot_id="watchlist_001",
        theme_id="theme_001",
        confirmed_candidate_ids=("confirmed_001",),
        symbols=("300750.SZ",),
        snapshot_date=date(2026, 6, 25),
        created_at=NOW,
        forward_only=True,
        frozen=True,
    )


def make_strategy_draft() -> StrategyDraft:
    return StrategyDraft(
        strategy_revision_id="strategy_revision_001",
        theme_id="theme_001",
        hypothesis_id="hypothesis_001",
        strategy_template_id="theme_momentum_breakout_v1",
        strategy_template_version="v1",
        strategy_template_hash="template_hash_001",
        hypothesis_source_snapshot_id="hypothesis_snapshot_001",
        backtest_universe_spec_id="universe_001",
        strategy_config_json='{"entry":"breakout","exit":"time_exit"}',
        sample_split_rule_id="fixed_ratio_70_30",
        created_at=NOW,
        frozen=True,
    )


def make_lifecycle_state(
    state: str = "draft",
    state_version: int = 1,
    source_record_id: str = "strategy_revision_001",
) -> StrategyLifecycleState:
    return StrategyLifecycleState(
        lifecycle_state_id=f"lifecycle_{state_version}",
        strategy_revision_id="strategy_revision_001",
        state_version=state_version,
        state=state,
        source_record_id=source_record_id,
        recorded_at=NOW,
        recorded_by="system",
        frozen=True,
    )


def make_protocol_snapshot() -> ResearchProtocolSnapshot:
    return ResearchProtocolSnapshot(
        protocol_snapshot_id="protocol_001",
        theme_id="theme_001",
        hypothesis_source_snapshot_id="hypothesis_snapshot_001",
        strategy_revision_id="strategy_revision_001",
        sample_split_rule_id="fixed_ratio_70_30",
        oos_window_rule_id="latest_252_trading_days",
        oos_window_rule_params_json='{"length":252}',
        oos_window_start=date(2025, 1, 2),
        oos_window_end=date(2025, 12, 31),
        shared_oos_window_id="oos_window_001",
        backtest_universe_spec_id="universe_001",
        data_snapshot_id="data_snapshot_001",
        kill_criteria_snapshot_id="kill_snapshot_001",
        prototype_gate_thresholds_json='{"min_oos_trades":20}',
        strategy_config_hash="strategy_hash_001",
        data_snapshot_hash="data_hash_001",
        gate_criteria_hash="gate_hash_001",
        frozen_at=NOW,
        frozen_by="system",
        frozen=True,
    )


def make_ledger() -> OOSEvaluationLedger:
    return OOSEvaluationLedger(
        ledger_snapshot_id="ledger_001",
        theme_id="theme_001",
        hypothesis_source_snapshot_id="hypothesis_snapshot_001",
        ledger_version=1,
        oos_evaluation_count=0,
        oos_budget_limit=3,
        next_oos_draw_index=1,
        budget_status="available",
        completed_evaluation_ids=(),
        active_reservation_ids=(),
        report_ids=(),
        recorded_at=NOW,
        frozen=True,
    )


def make_report() -> ImmutableBacktestReport:
    return ImmutableBacktestReport(
        report_id="report_001",
        theme_id="theme_001",
        strategy_revision_id="strategy_revision_001",
        protocol_snapshot_id="protocol_001",
        strategy_config_hash="strategy_hash_001",
        data_snapshot_hash="data_hash_001",
        gate_criteria_hash="gate_hash_001",
        evaluation_mode="out_of_sample",
        oos_draw_index=1,
        shared_oos_window_id="oos_window_001",
        multiple_comparison_flag=False,
        report_payload_json='{"data_quality_status":"ok"}',
        integrity_status="valid",
        generated_at=NOW,
        report_hash="report_hash_001",
        frozen=True,
    )


def make_gate_result(
    verdict: str = "candidate_for_prototype_passed",
) -> PrototypeGateResultV2:
    return PrototypeGateResultV2(
        gate_result_id="gate_001",
        report_id="report_001",
        strategy_revision_id="strategy_revision_001",
        protocol_snapshot_id="protocol_001",
        verdict=verdict,
        checks_json='{"all_checks":"pass"}',
        blocking_issues=(),
        warnings=(),
        strategy_config_hash="strategy_hash_001",
        data_snapshot_hash="data_hash_001",
        gate_criteria_hash="gate_hash_001",
        oos_draw_index=1,
        shared_oos_window_id="oos_window_001",
        multiple_comparison_flag=False,
        generated_at=NOW,
        gate_result_hash="gate_result_hash_001",
        frozen=True,
    )


def make_confirmation() -> HumanPromotionConfirmation:
    return HumanPromotionConfirmation(
        human_confirmation_id="human_confirmation_001",
        strategy_revision_id="strategy_revision_001",
        gate_result_id="gate_001",
        decision="approve",
        confirmed_by="owner_001",
        confirmed_at=NOW,
        frozen=True,
    )
