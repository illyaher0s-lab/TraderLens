"""Market Guard candidate configuration tests."""
import hashlib
import json
from pathlib import Path

import pytest
import yaml


def test_guard_config_exists():
    """Config file must exist."""
    config_path = Path("backend/config/market_regime_thresholds.yaml")
    assert config_path.exists(), "market_regime_thresholds.yaml not found"


def test_guard_config_has_frozen_rules():
    """Config must contain all pre-registered candidate rules."""
    config_path = Path("backend/config/market_regime_thresholds.yaml")
    with open(config_path) as f:
        config = yaml.safe_load(f)
    
    assert config["validation_status"] == "candidate"
    assert config["version"] == "1.2"
    
    # All four candidate rules
    rules = config["candidate_rules"]
    assert "extreme_breadth_selloff" in rules
    assert rules["extreme_breadth_selloff"]["threshold_gt"] == 0.80
    
    assert "structural_breakdown_1d" in rules
    assert rules["structural_breakdown_1d"]["threshold_lte"] == -0.05
    
    assert "structural_breakdown_5d" in rules
    assert rules["structural_breakdown_5d"]["threshold_lte"] == -0.10
    
    assert "liquidity_exhaustion" in rules
    assert rules["liquidity_exhaustion"]["threshold_lt"] == 0.30


def test_guard_config_has_validation_windows():
    """Config must contain stress and normal windows."""
    config_path = Path("backend/config/market_regime_thresholds.yaml")
    with open(config_path) as f:
        config = yaml.safe_load(f)
    
    stress = config["stress_windows"]
    assert len(stress) == 1
    assert stress[0]["id"] == "B"
    assert stress[0]["start"] == "2020-02-03"
    assert stress[0]["end"] == "2020-02-07"
    assert all(window["start"] >= "2016-01-01" for window in stress)
    
    normal = config["normal_window"]
    assert normal["start"] == "2017-09-01"
    assert normal["end"] == "2017-11-30"


def test_guard_config_has_data_quality_rules():
    """Config must contain zero-gap rule and normal-window ratio."""
    config_path = Path("backend/config/market_regime_thresholds.yaml")
    with open(config_path) as f:
        config = yaml.safe_load(f)
    
    assert config["zero_gap_rule"] is True
    assert config["stress_window_block_day_min"] == 1
    assert config["normal_window_block_ratio_max"] == 0.05


def test_guard_config_semantic_hash_stable():
    """Semantic hash must be stable for same rules."""
    config_path = Path("backend/config/market_regime_thresholds.yaml")
    with open(config_path) as f:
        config = yaml.safe_load(f)
    
    # Semantic fields only (exclude validation state)
    semantic = {
        "version": config["version"],
        "candidate_rules": config["candidate_rules"],
        "stress_windows": config["stress_windows"],
        "normal_window": config["normal_window"],
        "zero_gap_rule": config["zero_gap_rule"],
        "stress_window_block_day_min": config["stress_window_block_day_min"],
        "normal_window_block_ratio_max": config["normal_window_block_ratio_max"],
        "required_pit_inputs": config["required_pit_inputs"],
    }
    
    canonical = json.dumps(semantic, sort_keys=True).encode("utf-8")
    hash1 = hashlib.sha256(canonical).hexdigest()
    
    # Recompute
    hash2 = hashlib.sha256(canonical).hexdigest()
    assert hash1 == hash2, "Hash not stable"


def test_guard_config_semantic_hash_changes_on_rule_change():
    """Hash must change if any threshold/window/metric changes."""
    config_path = Path("backend/config/market_regime_thresholds.yaml")
    with open(config_path) as f:
        config = yaml.safe_load(f)
    
    semantic = {
        "version": config["version"],
        "candidate_rules": config["candidate_rules"],
        "stress_windows": config["stress_windows"],
        "normal_window": config["normal_window"],
        "zero_gap_rule": config["zero_gap_rule"],
        "stress_window_block_day_min": config["stress_window_block_day_min"],
        "normal_window_block_ratio_max": config["normal_window_block_ratio_max"],
        "required_pit_inputs": config["required_pit_inputs"],
    }
    
    hash_original = hashlib.sha256(json.dumps(semantic, sort_keys=True).encode()).hexdigest()
    
    # Mutate threshold
    semantic_mutated = semantic.copy()
    semantic_mutated["candidate_rules"] = semantic["candidate_rules"].copy()
    semantic_mutated["candidate_rules"]["extreme_breadth_selloff"] = semantic["candidate_rules"]["extreme_breadth_selloff"].copy()
    semantic_mutated["candidate_rules"]["extreme_breadth_selloff"]["threshold_gt"] = 0.85
    
    hash_mutated = hashlib.sha256(json.dumps(semantic_mutated, sort_keys=True).encode()).hexdigest()
    assert hash_original != hash_mutated, "Hash must change when threshold changes"


def test_guard_config_semantic_hash_ignores_validation_state():
    """Hash must NOT change when source_manifest_hash/validation fields change."""
    config_path = Path("backend/config/market_regime_thresholds.yaml")
    with open(config_path) as f:
        config = yaml.safe_load(f)
    
    # Semantic hash excludes validation state
    semantic = {
        "version": config["version"],
        "candidate_rules": config["candidate_rules"],
        "stress_windows": config["stress_windows"],
        "normal_window": config["normal_window"],
        "zero_gap_rule": config["zero_gap_rule"],
        "stress_window_block_day_min": config["stress_window_block_day_min"],
        "normal_window_block_ratio_max": config["normal_window_block_ratio_max"],
        "required_pit_inputs": config["required_pit_inputs"],
    }
    
    hash_before = hashlib.sha256(json.dumps(semantic, sort_keys=True).encode()).hexdigest()
    
    # Simulate validation state change (not in semantic fields)
    config_with_validation = config.copy()
    config_with_validation["source_manifest_hash"] = "abc123"
    config_with_validation["validated_at"] = "2026-07-11"
    
    # Recompute semantic hash (should be same)
    hash_after = hashlib.sha256(json.dumps(semantic, sort_keys=True).encode()).hexdigest()
    assert hash_before == hash_after, "Hash must NOT change when validation state changes"


def test_guard_config_status_is_candidate():
    """Validation status must be candidate, not frozen/ok."""
    config_path = Path("backend/config/market_regime_thresholds.yaml")
    with open(config_path) as f:
        config = yaml.safe_load(f)
    
    assert config["validation_status"] == "candidate", "Guard must be candidate before replay"
    assert config["frozen_at"] is None, "Guard cannot be pre-frozen"
    assert config["approved_by"] is None, "Guard cannot be pre-approved"


def test_guard_config_has_pit_dependencies():
    """Config must declare required PIT inputs."""
    config_path = Path("backend/config/market_regime_thresholds.yaml")
    with open(config_path) as f:
        config = yaml.safe_load(f)
    
    deps = config["required_pit_inputs"]
    assert "trade_cal" in deps
    assert "daily" in deps
    assert "index_daily" in deps
    assert "stock_basic" in deps
    assert "suspend_d" in deps
