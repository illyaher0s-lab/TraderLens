"""V3 candidate template focused tests - liquidity contract freeze."""
import hashlib
import json

from backend.services.strategy_template_library import (
    get_template_by_id,
    get_template_data_requirements,
    get_template_data_requirements_hash,
    convert_to_frozen_contract,
    list_approved_templates,
    StrategyTemplate,
)
from datetime import datetime


def test_v3_exact_identity():
    """V3 has exact template_id and version."""
    t = get_template_by_id("relative_strength_rotation_shsz_sw2021_v3")
    assert t is not None
    assert t.template_id == "relative_strength_rotation_shsz_sw2021_v3"
    assert t.version == "v3_shsz_sw2021_pit_12m_liquidity20d"
    assert t.strategy_config_payload["hypothesis_family_id"] == "relative_strength_rotation_shsz_sw2021"


def test_v3_liquidity_contract_complete():
    """V3 strategy_config_payload has complete liquidity dict."""
    t = get_template_by_id("relative_strength_rotation_shsz_sw2021_v3")
    liq = t.strategy_config_payload["liquidity"]
    assert liq["algorithm_id"] == "avg_amount_20d_shsz_common_v1"
    assert liq["threshold_yuan"] == 50000000
    assert liq["window_trading_days"] == 20
    assert liq["window_definition"] == "20_completed_sh_sz_common_trading_days_before_execution_day"
    assert liq["execution_day_excluded"] is True
    assert liq["source_field"] == "daily.amount"
    assert liq["source_unit"] == "thousand_yuan"
    assert liq["yuan_multiplier"] == 1000
    assert liq["minimum_history_trading_days"] == 20
    assert liq["insufficient_history"] == "unavailable_ineligible"
    assert liq["suspension_evidence_source"] == "suspend_d"
    assert liq["suspended_day_amount_yuan"] == 0
    assert liq["other_missing"] == "data_fault"
    assert liq["partial_mean_allowed"] is False
    assert liq["window_extension_allowed"] is False


def test_v3_liquidity_in_data_requirements():
    """V3 data_requirements includes liquidity payload."""
    t = get_template_by_id("relative_strength_rotation_shsz_sw2021_v3")
    req = get_template_data_requirements(t)
    assert "liquidity" in req
    liq = req["liquidity"]
    assert liq["algorithm_id"] == "avg_amount_20d_shsz_common_v1"
    assert liq["threshold_yuan"] == 50000000
    assert liq["window_trading_days"] == 20


def test_v3_liquidity_algorithm_hash():
    """V3 liquidity has deterministic algorithm hash."""
    t = get_template_by_id("relative_strength_rotation_shsz_sw2021_v3")
    liq = t.strategy_config_payload["liquidity"]
    
    # ponytail: compact JSON sorted keys
    algo_payload = {k: v for k, v in liq.items() if k != "threshold_yuan"}
    canonical = json.dumps(algo_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    
    req = get_template_data_requirements(t)
    assert req["liquidity"]["algorithm_hash"] == expected


def test_v3_data_requirements_hash_deterministic():
    """V3 data_requirements_hash is deterministic."""
    t = get_template_by_id("relative_strength_rotation_shsz_sw2021_v3")
    h1 = get_template_data_requirements_hash(t)
    h2 = get_template_data_requirements_hash(t)
    assert h1 == h2
    assert len(h1) == 64  # SHA-256


def test_v3_template_hash_deterministic():
    """V3 frozen_template_hash is deterministic."""
    t = get_template_by_id("relative_strength_rotation_shsz_sw2021_v3")
    h1 = t.frozen_template_hash
    h2 = t.frozen_template_hash
    assert h1 == h2
    assert len(h1) == 64


def test_v3_approved_status():
    """V3 is approved after Task 4 owner authorization."""
    t = get_template_by_id("relative_strength_rotation_shsz_sw2021_v3")
    frozen = convert_to_frozen_contract(t, created_at=datetime.now())
    assert frozen.governance_status == "approved"
    assert frozen.reviewer_id == "ai_reviewer_openai_codex_gpt5"
    assert frozen.authorized_by == "illya"


def test_v3_owner_authorized_for_task4():
    """Task 4 authorization binds the exact reviewed V3 content."""
    t = get_template_by_id("relative_strength_rotation_shsz_sw2021_v3")
    frozen = convert_to_frozen_contract(t, created_at=datetime(2026, 8, 4))
    assert frozen.governance_status == "approved"
    assert frozen.authorized_by == "illya"
    assert frozen.reviewer_id == "ai_reviewer_openai_codex_gpt5"
    assert frozen.review_evidence_path == "docs/verification/TASK4_V3_AI_TECHNICAL_REVIEW.md"


def test_v3_in_approved_list():
    """V3 is included after exact owner authorization."""
    approved = list_approved_templates()
    ids = [t.template_id for t in approved]
    assert "relative_strength_rotation_shsz_sw2021_v3" in ids


def test_v3_shares_hypothesis_family():
    """V3 shares hypothesis_family_id with V2."""
    v2 = get_template_by_id("relative_strength_rotation_shsz_sw2021_v2")
    v3 = get_template_by_id("relative_strength_rotation_shsz_sw2021_v3")
    assert v2.strategy_config_payload["hypothesis_family_id"] == v3.strategy_config_payload["hypothesis_family_id"]


def test_v2_immutable():
    """V2 template hash and data requirements hash unchanged."""
    v2 = get_template_by_id("relative_strength_rotation_shsz_sw2021_v2")
    assert v2.frozen_template_hash == "867a47eeece1c0d208c591f35b5ca31d663ccda183c8721eef803483921238b6"
    assert get_template_data_requirements_hash(v2) == "1910d7a598b1008fb5ba6ee69833e174b5a9949f31a998e2fced436950d8df04"


def test_v2_still_approved():
    """V2 remains approved."""
    v2 = get_template_by_id("relative_strength_rotation_shsz_sw2021_v2")
    frozen = convert_to_frozen_contract(v2, created_at=datetime.now())
    assert frozen.governance_status == "approved"
    assert frozen.authorized_by == "illya"


def test_v2_no_liquidity_backfill():
    """V2 strategy_config_payload has no liquidity key."""
    v2 = get_template_by_id("relative_strength_rotation_shsz_sw2021_v2")
    assert "liquidity" not in v2.strategy_config_payload


def test_v3_algorithm_hash_stable_under_threshold_change():
    """V3 algorithm hash unchanged when only threshold_yuan changes."""
    t = get_template_by_id("relative_strength_rotation_shsz_sw2021_v3")
    req1 = get_template_data_requirements(t)
    algo_hash1 = req1["liquidity"]["algorithm_hash"]
    
    # ponytail: modify threshold, recompute
    modified = dict(t.strategy_config_payload["liquidity"])
    modified["threshold_yuan"] = 100000000
    algo_payload = {k: v for k, v in modified.items() if k != "threshold_yuan"}
    algo_hash2 = hashlib.sha256(
        json.dumps(algo_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()
    
    assert algo_hash1 == algo_hash2


def test_v3_algorithm_hash_changes_on_window_semantic_change():
    """V3 algorithm hash changes when window semantics change."""
    t = get_template_by_id("relative_strength_rotation_shsz_sw2021_v3")
    req1 = get_template_data_requirements(t)
    algo_hash1 = req1["liquidity"]["algorithm_hash"]
    
    # ponytail: modify window semantic
    modified = dict(t.strategy_config_payload["liquidity"])
    modified["window_trading_days"] = 30
    algo_payload = {k: v for k, v in modified.items() if k != "threshold_yuan"}
    algo_hash2 = hashlib.sha256(
        json.dumps(algo_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()
    
    assert algo_hash1 != algo_hash2


def test_v3_data_requirements_hash_changes_on_threshold_change():
    """V3 data_requirements_hash changes when threshold_yuan changes."""
    import backend.services.strategy_template_library as lib
    from backend.services.strategy_template_library import StrategyTemplate
    
    t = get_template_by_id("relative_strength_rotation_shsz_sw2021_v3")
    h1 = get_template_data_requirements_hash(t)
    
    # ponytail: shallow copy config, change threshold
    modified_config = dict(t.strategy_config_payload)
    modified_liq = dict(modified_config["liquidity"])
    modified_liq["threshold_yuan"] = 100000000
    modified_config["liquidity"] = modified_liq
    
    # ponytail: create modified template
    t2 = StrategyTemplate(
        template_id=t.template_id,
        version=t.version,
        hypothesis_types=t.hypothesis_types,
        core_entry_rule_id=t.core_entry_rule_id,
        supported_universe_rule_types=t.supported_universe_rule_types,
        sample_split_rule_ids=t.sample_split_rule_ids,
        benchmark_rule_id=t.benchmark_rule_id,
        strategy_config_payload=modified_config,
        forbidden_fields=t.forbidden_fields,
        forbidden_evidence_terms=t.forbidden_evidence_terms,
        market_fit=t.market_fit,
        forbidden_market=t.forbidden_market,
        entry_rules=t.entry_rules,
        exit_rules=t.exit_rules,
        risk_rules=t.risk_rules,
        position_sizing_rules=t.position_sizing_rules,
        validation_gate_profile=t.validation_gate_profile,
    )
    h2 = get_template_data_requirements_hash(t2)
    
    assert h1 != h2
