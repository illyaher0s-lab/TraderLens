from datetime import date, datetime
import json
from pathlib import Path

import pytest
from contracts.strategy import StrategyDraft
from contracts.strategy import BacktestUniverseSpec, StrategyLifecycleState
from backend.db.strategy import StrategyDB
from backend.services.strategy_template_library import _owner_authorization_hash


def _draft_kwargs():
    return {
        "strategy_revision_id": "revision_governance_test",
        "theme_id": "template_governance:relative_strength_rotation_shsz_sw2021_v3",
        "hypothesis_id": "template_governance:hypothesis:relative_strength_rotation_shsz_sw2021_v3",
        "strategy_template_id": "relative_strength_rotation_shsz_sw2021_v3",
        "strategy_template_version": "v3_shsz_sw2021_pit_12m_liquidity20d",
        "strategy_template_hash": "f7c0fd8123f62f37118cb947e1735861374435f8707e01b06d788a8ec4df39c1",
        "hypothesis_source_snapshot_id": "template_governance:source:relative_strength_rotation_shsz_sw2021_v3",
        "backtest_universe_spec_id": "universe_governance_test",
        "strategy_config_json": json.dumps({
            "hypothesis_family_id": "relative_strength_rotation_shsz_sw2021",
            "lookback_trading_days": 252,
            "minimum_history_trading_days": 252,
            "as_of_semantics": "latest_complete_sh_sz_common_trading_day",
            "execution_day": "next_executable_after_as_of",
            "adjusted_close_formula": "close * adj_factor",
            "momentum_formula": "adjusted_close(d) / adjusted_close(s) - 1",
            "s_definition": "d_minus_252_common_trading_days",
            "endpoint_unavailable": "either_missing_no_fill_no_fallback_no_window_change",
            "ranking_universe": "formal_sw2021_pit_sh_sz_complete_252d_at_d",
            "tie_break": "return_desc_symbol_asc",
            "top_count_formula": "ceil(0.15 * N)",
            "confirm_semantics": "3_days_independent_pit_and_window",
            "entry": {"relative_strength_rank_pct_max": 15, "confirm_days": 3},
            "exit": {"rank_exit_pct_min": 40, "max_holding_days": 15, "stop_loss_pct": 8},
            "risk": {"market_regime_allowed": ["green", "yellow"], "min_avg_amount_20d": 50000000},
            "rebalance": {"frequency": "weekly", "max_positions": 5},
            "market_scope": ["SH", "SZ"],
            "liquidity": {"algorithm_id": "avg_amount_20d_shsz_common_v1", "threshold_yuan": 50000000, "window_trading_days": 20, "window_definition": "20_completed_sh_sz_common_trading_days_before_execution_day", "execution_day_excluded": True, "source_field": "daily.amount", "source_unit": "thousand_yuan", "yuan_multiplier": 1000, "minimum_history_trading_days": 20, "insufficient_history": "unavailable_ineligible", "suspension_evidence_source": "suspend_d", "suspended_day_amount_yuan": 0, "other_missing": "data_fault", "partial_mean_allowed": False, "window_extension_allowed": False},
        }, sort_keys=True, separators=(",", ":")),
        "sample_split_rule_id": "fixed_ratio_70_30",
        "created_at": datetime(2026, 8, 5),
        "provenance": {
            "kind": "approved_template_governance",
            "template_id": "relative_strength_rotation_shsz_sw2021_v3",
            "template_version": "v3_shsz_sw2021_pit_12m_liquidity20d",
            "template_hash": "f7c0fd8123f62f37118cb947e1735861374435f8707e01b06d788a8ec4df39c1",
            "data_requirements_hash": "ef2ab5b1dafe4349f305b52733a7dcb018a2961464dfbc6542a10e34805d041d",
            "review_evidence_path": "docs/verification/TASK4_V3_AI_TECHNICAL_REVIEW.md",
            "review_evidence_sha256": "9ea7b9f96c326afbbd0de84e5e2183cb7315c29e26d953b4a5c9aa06b7d4ae69",
            "reviewer_id": "ai_reviewer_openai_codex_gpt5",
            "reviewer_kind": "ai_technical_reviewer",
            "review_decision": "approved",
            "reviewed_at": "2026-08-04T00:00:00",
            "review_due_date": "2027-08-04",
            "owner_authorization_hash": "653350938e4bda2a91ee0c3b16bd9c4bf407517d74d6f3da66cb7884cad39349",
            "authorized_by": "illya",
            "authorized_at": "2026-08-04T00:00:00",
        },
    }


def _authorization_payload(provenance):
    return {
        "template_id": provenance.template_id,
        "version": provenance.template_version,
        "template_hash": provenance.template_hash,
        "data_requirements_hash": provenance.data_requirements_hash,
        "review_evidence_path": provenance.review_evidence_path,
        "review_evidence_sha256": provenance.review_evidence_sha256,
        "reviewer_id": provenance.reviewer_id,
        "reviewer_kind": provenance.reviewer_kind,
        "review_decision": provenance.review_decision,
        "reviewed_at": provenance.reviewed_at.date(),
        "authorized_by": provenance.authorized_by,
        "authorized_at": provenance.authorized_at,
        "review_due_date": provenance.review_due_date,
    }


def _store_governance_draft(draft):
    db = StrategyDB(":memory:")
    db.store_backtest_universe(
        BacktestUniverseSpec(
            universe_spec_id=draft.backtest_universe_spec_id,
            universe_rule_type="point_in_time_membership",
            membership_source="B3:05f38a2884dc7e47",
            membership_effective_from=date(1984, 5, 9),
            membership_effective_to=date(2026, 6, 5),
            snapshot_date=date(2026, 7, 17),
            membership_snapshot_ids=("pims_traderlens_v2_shsz_sw2021_pit_005",),
            quality_status="ok",
            gaps=("availability_limited",),
        )
    )
    db.create_strategy_draft(
        draft,
        StrategyLifecycleState(
            lifecycle_state_id="lifecycle_governance_test",
            strategy_revision_id=draft.strategy_revision_id,
            state_version=1,
            state="draft",
            source_record_id="template_governance:source:relative_strength_rotation_shsz_sw2021_v3",
            recorded_at=draft.created_at,
            recorded_by="illya",
        ),
    )
    return db


from backend.services.strategy_revision_provenance import validate_strategy_revision_provenance


def test_approved_template_governance_provenance_is_explicit_and_validatable(tmp_path: Path):
    draft = StrategyDraft(**_draft_kwargs())
    db = StrategyDB(":memory:")
    db.store_backtest_universe(
        BacktestUniverseSpec(
            universe_spec_id=draft.backtest_universe_spec_id,
            universe_rule_type="point_in_time_membership",
            membership_source="B3:05f38a2884dc7e47",
            membership_effective_from=date(2021, 1, 1),
            membership_effective_to=date(2021, 12, 31),
            snapshot_date=date(2021, 1, 5),
            membership_snapshot_ids=("pims_traderlens_v2_shsz_sw2021_pit_005",),
            quality_status="ok",
        )
    )
    db.create_strategy_draft(
        draft,
        StrategyLifecycleState(
            lifecycle_state_id="lifecycle_governance_test",
            strategy_revision_id=draft.strategy_revision_id,
            state_version=1,
            state="draft",
            source_record_id="template_governance:source:relative_strength_rotation_shsz_sw2021_v3",
            recorded_at=draft.created_at,
            recorded_by="illya",
        ),
    )
    result = validate_strategy_revision_provenance(db, None, draft.strategy_revision_id)
    assert result.is_valid, result


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("template_version", "tampered-version"),
        ("review_evidence_path", "./docs/verification/TASK4_V3_AI_TECHNICAL_REVIEW.md"),
        ("reviewer_id", "tampered-reviewer"),
        ("reviewer_kind", "manual-reviewer"),
        ("reviewed_at", datetime(2026, 8, 3)),
        ("authorized_by", "tampered-owner"),
    ),
)
def test_approved_template_governance_rejects_non_authoritative_fields(field, value):
    kwargs = _draft_kwargs()
    draft = StrategyDraft(**kwargs)
    provenance = draft.provenance.model_copy(update={field: value})
    provenance = provenance.model_copy(
        update={"owner_authorization_hash": _owner_authorization_hash(_authorization_payload(provenance))}
    )
    draft_updates = {"provenance": provenance}
    if field == "template_version":
        draft_updates["strategy_template_version"] = value
    draft = draft.model_copy(update=draft_updates)
    db = _store_governance_draft(draft)

    result = validate_strategy_revision_provenance(db, None, draft.strategy_revision_id)

    assert not result.is_valid
    assert result.reason_code == "template_governance_binding_mismatch"


def test_approved_template_governance_rejects_candidate_template():
    from backend.services.strategy_template_library import convert_to_frozen_contract, get_template_by_id

    kwargs = _draft_kwargs()
    candidate = get_template_by_id("relative_strength_rotation_shsz_sw2021_v1")
    frozen_candidate = convert_to_frozen_contract(candidate, datetime(2026, 8, 5))
    draft = StrategyDraft(**kwargs)
    provenance = draft.provenance.model_copy(
        update={
            "template_id": frozen_candidate.template_id,
            "template_version": frozen_candidate.version,
            "template_hash": frozen_candidate.template_hash,
            "data_requirements_hash": "candidate-requirements",
        }
    )
    provenance = provenance.model_copy(
        update={"owner_authorization_hash": _owner_authorization_hash(_authorization_payload(provenance))}
    )
    draft = draft.model_copy(
        update={
            "strategy_template_id": frozen_candidate.template_id,
            "strategy_template_version": frozen_candidate.version,
            "strategy_template_hash": frozen_candidate.template_hash,
            "provenance": provenance,
        }
    )
    db = _store_governance_draft(draft)

    result = validate_strategy_revision_provenance(db, None, draft.strategy_revision_id)

    assert not result.is_valid
    assert result.reason_code == "template_governance_binding_mismatch"


def test_approved_template_governance_rejects_config_mismatch():
    kwargs = _draft_kwargs()
    config = json.loads(kwargs["strategy_config_json"])
    config["entry"]["confirm_days"] = 4
    kwargs["strategy_config_json"] = json.dumps(config, sort_keys=True, separators=(",", ":"))
    draft = StrategyDraft(**kwargs)
    db = _store_governance_draft(draft)

    result = validate_strategy_revision_provenance(db, None, draft.strategy_revision_id)

    assert not result.is_valid
    assert result.reason_code == "template_governance_config_invalid"


@pytest.mark.parametrize(
    ("field", "value", "reason_code"),
    (
        ("template_hash", "tampered-template-hash", "template_governance_binding_mismatch"),
        ("data_requirements_hash", "tampered-requirements-hash", "template_governance_binding_mismatch"),
        ("review_evidence_sha256", "tampered-review-hash", "template_governance_evidence_mismatch"),
        ("owner_authorization_hash", "tampered-owner-hash", "template_governance_authorization_mismatch"),
    ),
)
def test_approved_template_governance_rejects_integrity_mismatches(field, value, reason_code):
    draft = StrategyDraft(**_draft_kwargs())
    provenance = draft.provenance.model_copy(update={field: value})
    if field not in {"review_evidence_sha256", "owner_authorization_hash"}:
        provenance = provenance.model_copy(
            update={"owner_authorization_hash": _owner_authorization_hash(_authorization_payload(provenance))}
        )
    draft_updates = {"provenance": provenance}
    if field == "template_hash":
        draft_updates["strategy_template_hash"] = value
    draft = draft.model_copy(update=draft_updates)
    db = _store_governance_draft(draft)

    result = validate_strategy_revision_provenance(db, None, draft.strategy_revision_id)

    assert not result.is_valid
    assert result.reason_code == reason_code
