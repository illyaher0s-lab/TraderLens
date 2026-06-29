"""B2 Strategy Template Library - Hard-coded strategy templates with fixed parameters."""
from __future__ import annotations

import hashlib
import json
import types
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from contracts.strategy import StrategyTemplateDefinition


class StrategyTemplate(BaseModel):
    """Immutable strategy template with fixed parameters."""
    
    model_config = ConfigDict(frozen=True, extra="forbid")
    
    template_id: str
    version: str
    hypothesis_types: tuple[str, ...]
    core_entry_rule_id: str
    supported_universe_rule_types: tuple[
        Literal["sector_plus_tags", "point_in_time_membership"], ...
    ]
    sample_split_rule_ids: tuple[str, ...]
    benchmark_rule_id: str
    strategy_config_payload: dict
    forbidden_fields: tuple[str, ...] = ()
    forbidden_evidence_terms: tuple[str, ...] = ()
    default_cost_model: str = "base"
    default_fill_model: str = "market_open"
    default_risk_rules: dict = {}
    
    # V1 PRD fields
    market_fit: str = ""
    forbidden_market: tuple[str, ...] = ()
    entry_rules: str = ""
    exit_rules: str = ""
    risk_rules: str = ""
    position_sizing_rules: str = ""
    validation_gate_profile: str = ""
    
    def model_post_init(self, __context):
        """Deep-freeze nested dicts to ensure immutability."""
        # Convert strategy_config_payload to immutable nested structure
        object.__setattr__(self, 'strategy_config_payload', self._make_immutable(self.strategy_config_payload))
        object.__setattr__(self, 'default_risk_rules', self._make_immutable(self.default_risk_rules))
    
    @staticmethod
    def _make_immutable(obj):
        """Recursively convert dicts/lists to immutable equivalents."""
        if isinstance(obj, dict):
            return types.MappingProxyType({k: StrategyTemplate._make_immutable(v) for k, v in obj.items()})
        elif isinstance(obj, list):
            return tuple(StrategyTemplate._make_immutable(item) for item in obj)
        return obj
    
    @property
    def template_hash(self) -> str:
        """Compute stable hash from semantic content only."""
        canonical = {
            "template_id": self.template_id,
            "version": self.version,
            "hypothesis_types": self.hypothesis_types,
            "core_entry_rule_id": self.core_entry_rule_id,
            "supported_universe_rule_types": self.supported_universe_rule_types,
            "sample_split_rule_ids": self.sample_split_rule_ids,
            "benchmark_rule_id": self.benchmark_rule_id,
            "strategy_config_payload": self._serialize_for_hash(self.strategy_config_payload),
            "forbidden_fields": self.forbidden_fields,
            "forbidden_evidence_terms": self.forbidden_evidence_terms,
            "default_cost_model": self.default_cost_model,
            "default_fill_model": self.default_fill_model,
            "default_risk_rules": self._serialize_for_hash(self.default_risk_rules),
        }
        payload = json.dumps(canonical, sort_keys=True).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()[:32]
    
    @property
    def frozen_template_hash(self) -> str:
        """V1 semantic hash covering all rules and config."""
        canonical = {
            "template_id": self.template_id,
            "version": self.version,
            "entry_rules": self.entry_rules,
            "exit_rules": self.exit_rules,
            "risk_rules": self.risk_rules,
            "position_sizing_rules": self.position_sizing_rules,
            "validation_gate_profile": self.validation_gate_profile,
            "strategy_config_payload": self._serialize_for_hash(self.strategy_config_payload),
            "market_fit": self.market_fit,
            "forbidden_market": self.forbidden_market,
        }
        payload = json.dumps(canonical, sort_keys=True).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()
    
    @staticmethod
    def _serialize_for_hash(obj):
        """Convert immutable proxy objects back to serializable form."""
        if isinstance(obj, types.MappingProxyType):
            return {k: StrategyTemplate._serialize_for_hash(v) for k, v in obj.items()}
        elif isinstance(obj, tuple):
            return [StrategyTemplate._serialize_for_hash(item) for item in obj]
        return obj


# Hard-coded templates with conservative fixed parameters
_TEMPLATES = (
    StrategyTemplate(
        template_id="theme_momentum_breakout_v1",
        version="v1",
        hypothesis_types=("momentum", "macd_crossover"),
        core_entry_rule_id="macd_crossover_entry",
        supported_universe_rule_types=("sector_plus_tags",),
        sample_split_rule_ids=("fixed_ratio_70_30",),
        benchmark_rule_id="theme_then_industry_then_equal_weight",
        strategy_config_payload={
            "entry": {
                "macd_fast": 12,
                "macd_slow": 26,
                "macd_signal": 9,
                "confirm_days": 2,
            },
            "exit": {
                "max_holding_days": 15,
                "stop_loss_pct": 8,
            },
            "risk": {
                "market_regime_allowed": ["green", "yellow"],
                "min_avg_amount_20d": 50000000,
            },
            "rebalance": {
                "frequency": "daily",
                "max_positions": 5,
            },
        },
        forbidden_fields=("status", "hash", "oos_start", "oos_end", "gate_verdict"),
        forbidden_evidence_terms=("announcement", "disclosure", "report"),
        # V1 PRD fields
        market_fit="A-share momentum with MACD confirmation",
        forbidden_market=("limit_up", "st_stock", "delisting_risk"),
        entry_rules="MACD golden cross confirmed by 2-day price strength",
        exit_rules="Max 15 days hold or 8% stop-loss",
        risk_rules="Green/yellow market regime, min 50M avg daily volume",
        position_sizing_rules="Equal weight across max 5 positions, daily rebalance",
        validation_gate_profile="standard",
    ),
    StrategyTemplate(
        template_id="relative_strength_rotation_v1",
        version="v1",
        hypothesis_types=("relative_strength", "theme_rotation"),
        core_entry_rule_id="relative_strength_entry",
        supported_universe_rule_types=("sector_plus_tags",),
        sample_split_rule_ids=("fixed_ratio_70_30",),
        benchmark_rule_id="theme_then_industry_then_equal_weight",
        strategy_config_payload={
            "entry": {
                "relative_strength_rank_pct_max": 15,
                "confirm_days": 3,
            },
            "exit": {
                "rank_exit_pct_min": 40,
                "max_holding_days": 15,
                "stop_loss_pct": 8,
            },
            "risk": {
                "market_regime_allowed": ["green", "yellow"],
                "min_avg_amount_20d": 50000000,
            },
            "rebalance": {
                "frequency": "weekly",
                "max_positions": 5,
            },
        },
        forbidden_fields=("status", "hash", "oos_start", "oos_end", "gate_verdict"),
        forbidden_evidence_terms=("announcement", "disclosure", "report"),
        # V1 PRD fields
        market_fit="A-share relative strength rotation",
        forbidden_market=("limit_up", "st_stock", "delisting_risk"),
        entry_rules="Top 15% relative strength confirmed over 3 days",
        exit_rules="Exit when rank drops below 40% or max 15 days or 8% stop-loss",
        risk_rules="Green/yellow market regime, min 50M avg daily volume",
        position_sizing_rules="Equal weight across max 5 positions, weekly rebalance",
        validation_gate_profile="standard",
    ),
    StrategyTemplate(
        template_id="volume_breakout_followthrough_v1",
        version="v1",
        hypothesis_types=("volume_breakout", "followthrough"),
        core_entry_rule_id="volume_breakout_entry",
        supported_universe_rule_types=("sector_plus_tags",),
        sample_split_rule_ids=("fixed_ratio_70_30",),
        benchmark_rule_id="theme_then_industry_then_equal_weight",
        strategy_config_payload={
            "entry": {
                "breakout_lookback_days": 40,
                "volume_multiple_vs_20d": 2.0,
                "followthrough_days": 2,
            },
            "exit": {
                "max_holding_days": 8,
                "close_below_ma_days": 10,
                "stop_loss_pct": 7,
            },
            "risk": {
                "min_avg_amount_20d": 80000000,
                "reject_limit_up_entry": True,
            },
            "rebalance": {
                "frequency": "daily",
                "max_positions": 4,
            },
        },
        forbidden_fields=("status", "hash", "oos_start", "oos_end", "gate_verdict"),
        forbidden_evidence_terms=("announcement", "disclosure", "report"),
        # V1 PRD fields
        market_fit="A-share volume breakout with price confirmation",
        forbidden_market=("limit_up_entry", "st_stock", "delisting_risk"),
        entry_rules="40-day breakout with 2x volume, 2-day followthrough confirmation",
        exit_rules="Exit if close below 10-day MA or max 8 days or 7% stop-loss",
        risk_rules="Min 80M avg daily volume, reject limit-up entry",
        position_sizing_rules="Equal weight across max 4 positions, daily rebalance",
        validation_gate_profile="standard",
    ),
    StrategyTemplate(
        template_id="trend_pullback_watch_v1",
        version="v1",
        hypothesis_types=("trend", "pullback"),
        core_entry_rule_id="pullback_entry",
        supported_universe_rule_types=("sector_plus_tags",),
        sample_split_rule_ids=("fixed_ratio_70_30",),
        benchmark_rule_id="theme_then_industry_then_equal_weight",
        strategy_config_payload={
            "entry": {
                "trend_ma_days": 50,
                "pullback_pct": 5,
                "confirm_days": 2,
            },
            "exit": {
                "max_holding_days": 12,
                "stop_loss_pct": 6,
            },
            "risk": {
                "market_regime_allowed": ["green"],
                "min_avg_amount_20d": 60000000,
            },
            "rebalance": {
                "frequency": "daily",
                "max_positions": 4,
            },
        },
        forbidden_fields=("status", "hash", "oos_start", "oos_end", "gate_verdict"),
        forbidden_evidence_terms=("announcement", "disclosure", "report"),
        # V1 PRD fields
        market_fit="A-share trend pullback entry",
        forbidden_market=("limit_up", "st_stock", "delisting_risk"),
        entry_rules="5% pullback from 50-day MA trend, 2-day confirmation",
        exit_rules="Max 12 days hold or 6% stop-loss",
        risk_rules="Green market regime only, min 60M avg daily volume",
        position_sizing_rules="Equal weight across max 4 positions, daily rebalance",
        validation_gate_profile="standard",
    ),
)

APPROVED_TEMPLATES = _TEMPLATES


def get_template_by_id(template_id: str) -> StrategyTemplate | None:
    """Get approved template by ID. Returns None if not found."""
    for template in APPROVED_TEMPLATES:
        if template.template_id == template_id:
            return template
    return None


def list_approved_templates() -> tuple[StrategyTemplate, ...]:
    """List all approved templates."""
    return APPROVED_TEMPLATES


def convert_to_frozen_contract(template: StrategyTemplate, created_at: datetime) -> StrategyTemplateDefinition:
    """Convert StrategyTemplate to frozen B-module contract."""
    return StrategyTemplateDefinition(
        template_id=template.template_id,
        version=template.version,
        template_hash=template.frozen_template_hash,  # Use V1 semantic hash
        hypothesis_types=template.hypothesis_types,
        core_entry_rule_id=template.core_entry_rule_id,
        supported_universe_rule_types=template.supported_universe_rule_types,
        sample_split_rule_ids=template.sample_split_rule_ids,
        benchmark_rule_id=template.benchmark_rule_id,
        created_at=created_at,
    )


# B2 backward compatibility wrapper
class StrategyTemplateLibrary:
    """Backward compatibility wrapper for B2 tests."""
    
    def list_templates(self) -> tuple[StrategyTemplate, ...]:
        """List all approved templates."""
        return APPROVED_TEMPLATES
    
    def get_template(self, template_id: str) -> StrategyTemplate:
        """Get template by ID. Raises KeyError if not found."""
        template = get_template_by_id(template_id)
        if template is None:
            raise KeyError(f"Template not found: {template_id}")
        return template
    
    def to_b1_definition(self, template_id: str) -> StrategyTemplateDefinition:
        """Convert template to frozen B1 definition."""
        template = self.get_template(template_id)
        return convert_to_frozen_contract(template, datetime.now())
