"""B2 Strategy Template Library - Hard-coded strategy templates with fixed parameters."""
from __future__ import annotations

import hashlib
import json
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
            "strategy_config_payload": self.strategy_config_payload,
            "forbidden_fields": self.forbidden_fields,
            "forbidden_evidence_terms": self.forbidden_evidence_terms,
            "default_cost_model": self.default_cost_model,
            "default_fill_model": self.default_fill_model,
            "default_risk_rules": self.default_risk_rules,
        }
        payload = json.dumps(canonical, sort_keys=True).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()[:32]


# Hard-coded templates with conservative fixed parameters
_TEMPLATES = (
    StrategyTemplate(
        template_id="theme_momentum_breakout_v1",
        version="v1",
        hypothesis_types=("theme_momentum", "bottleneck_breakout"),
        core_entry_rule_id="breakout_entry",
        supported_universe_rule_types=("sector_plus_tags",),
        sample_split_rule_ids=("fixed_ratio_70_30",),
        benchmark_rule_id="theme_then_industry_then_equal_weight",
        strategy_config_payload={
            "entry": {
                "relative_strength_rank_pct_max": 10,
                "breakout_lookback_days": 60,
                "volume_multiple_vs_20d": 1.5,
            },
            "exit": {
                "max_holding_days": 10,
                "close_below_ma_days": 20,
                "stop_loss_pct": 8,
            },
            "risk": {
                "market_regime_allowed": ["green", "yellow"],
                "reject_market_regime": ["red"],
                "min_avg_amount_20d": 50000000,
            },
            "rebalance": {
                "frequency": "daily",
                "max_positions": 5,
            },
        },
        forbidden_fields=("status", "hash", "oos_start", "oos_end", "gate_verdict"),
        forbidden_evidence_terms=("announcement", "disclosure", "report"),
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
    ),
    StrategyTemplate(
        template_id="trend_pullback_watch_v1",
        version="v1",
        hypothesis_types=("trend_pullback", "strong_trend_retest"),
        core_entry_rule_id="trend_pullback_entry",
        supported_universe_rule_types=("sector_plus_tags",),
        sample_split_rule_ids=("fixed_ratio_70_30",),
        benchmark_rule_id="theme_then_industry_then_equal_weight",
        strategy_config_payload={
            "entry": {
                "trend_ma_days": 60,
                "pullback_ma_days": 20,
                "rebound_confirm_days": 2,
            },
            "exit": {
                "max_holding_days": 12,
                "close_below_ma_days": 20,
                "stop_loss_pct": 7,
            },
            "risk": {
                "min_avg_amount_20d": 50000000,
                "reject_market_regime": ["red"],
            },
            "rebalance": {
                "frequency": "daily",
                "max_positions": 5,
            },
        },
        forbidden_fields=("status", "hash", "oos_start", "oos_end", "gate_verdict"),
        forbidden_evidence_terms=("announcement", "disclosure", "report"),
    ),
)

_TEMPLATE_INDEX = {t.template_id: t for t in _TEMPLATES}


class StrategyTemplateLibrary:
    """Immutable library of hard-coded strategy templates."""
    
    def list_templates(self) -> tuple[StrategyTemplate, ...]:
        """Return all registered templates."""
        return _TEMPLATES
    
    def get_template(self, template_id: str) -> StrategyTemplate:
        """Get template by ID. Raises KeyError if unknown."""
        return _TEMPLATE_INDEX[template_id]
    
    def to_b1_definition(self, template_id: str) -> StrategyTemplateDefinition:
        """Convert template to B1 StrategyTemplateDefinition contract."""
        template = self.get_template(template_id)
        return StrategyTemplateDefinition(
            template_id=template.template_id,
            version=template.version,
            template_hash=template.template_hash,
            hypothesis_types=template.hypothesis_types,
            core_entry_rule_id=template.core_entry_rule_id,
            supported_universe_rule_types=template.supported_universe_rule_types,
            sample_split_rule_ids=template.sample_split_rule_ids,
            benchmark_rule_id=template.benchmark_rule_id,
            created_at=datetime.now(),
            frozen=True,
        )
