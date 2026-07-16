"""B2 Strategy Template Library - Hard-coded strategy templates with fixed parameters."""
from __future__ import annotations

import hashlib
import json
import types
from datetime import date, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from contracts.strategy import StrategyTemplateDefinition, SourceRuleMapping


_V2_TEMPLATE_ID = "relative_strength_rotation_shsz_sw2021_v1"
_V2_SUCCESSOR_MANIFEST = Path(
    "data/pit/qualification_successors/e5100669ed247769/manifest.json"
)
_V2_COVERAGE_MANIFEST = Path(
    "data/pit/coverage_packages/695245b51005e50b/coverage_manifest.json"
)


def _load_v2_requirements_hash(template: "StrategyTemplate") -> str:
    """Read and cross-check the existing V1 successor and coverage bindings.

    Only for V1 template (relative_strength_rotation_shsz_sw2021_v1).
    V2 candidate uses get_template_data_requirements_hash() instead.
    """
    root = Path(__file__).resolve().parents[2]
    successor = json.loads((root / _V2_SUCCESSOR_MANIFEST).read_text(encoding="utf-8"))
    coverage = json.loads((root / _V2_COVERAGE_MANIFEST).read_text(encoding="utf-8"))
    requirements_hash = successor["predecessor_data_requirements_hash"]

    if (
        successor["template_id"] != template.template_id
        or successor["template_version"] != template.version
        or successor["template_hash"] != template.frozen_template_hash
        or coverage["input_template_hash"] != template.frozen_template_hash
        or coverage["input_data_requirements_hash"] != requirements_hash
    ):
        raise ValueError("V1 template governance bindings do not match successor and coverage manifests")
    return requirements_hash


def get_template_data_requirements(template: "StrategyTemplate") -> dict:
    """Pure function: canonical data requirements for template (not bound to V1 artifacts).

    Returns structured data requirements including:
    - Template identification (id, version, hash)
    - Data sources (daily.close, adj_factor.adj_factor)
    - Temporal semantics (lookback_trading_days, minimum_history_trading_days)
    - Universe constraints (SW2021 PIT membership, SH/SZ calendar)
    - Ranking semantics (cross-sectional, confirm_days)
    - Unavailability rules (missing endpoints = unavailable)
    """
    config = template.strategy_config_payload

    requirements = {
        "template_id": template.template_id,
        "template_version": template.version,
        "template_hash": template.frozen_template_hash,
        "hypothesis_family_id": config.get("hypothesis_family_id"),
        "decision_timing": {
            "as_of_semantics": config.get("as_of_semantics"),
            "execution_day": config.get("execution_day"),
        },
        "data_sources": {
            "daily_close": "daily.close",
            "adj_factor": "adj_factor.adj_factor",
            "adjusted_close_formula": config.get("adjusted_close_formula"),
            "comment": "Both endpoints from same PIT snapshot, neither later than as_of_date",
        },
        "temporal_requirements": {
            "lookback_trading_days": config.get("lookback_trading_days", 0),
            "minimum_history_trading_days": config.get("minimum_history_trading_days", 0),
            "s_definition": config.get("s_definition"),
            "comment": "252 trading days = non-calendar-month lookback; no shortening for new stocks",
        },
        "calendar": {
            "type": "sh_sz_common_trading_days",
            "comment": "SH and SZ common open trading days only",
        },
        "universe": {
            "type": "point_in_time_membership",
            "source": "SW2021",
            "scope": config.get("market_scope", []),
            "ranking_universe": config.get("ranking_universe"),
            "comment": "Formal SW2021 PIT membership at as_of_date",
        },
        "momentum_calculation": {
            "formula": config.get("momentum_formula"),
            "s_definition": config.get("s_definition"),
            "adjusted_close": config.get("adjusted_close_formula"),
            "endpoint_unavailable": config.get("endpoint_unavailable"),
        },
        "ranking": {
            "universe": config.get("ranking_universe"),
            "direction": "descending_return",
            "tie_break": config.get("tie_break"),
            "top_count_formula": config.get("top_count_formula"),
        },
    }

    # Add confirmation if entry.confirm_days exists
    if "entry" in config and "confirm_days" in config["entry"]:
        requirements["confirmation"] = {
            "confirm_days": config["entry"]["confirm_days"],
            "semantic": config.get("confirm_semantics"),
        }

    return requirements


def get_template_data_requirements_hash(template: "StrategyTemplate") -> str:
    """Pure function: deterministic SHA-256 hash of canonical data requirements.

    Does NOT read V1 successor/coverage manifests. Independent of artifact bindings.
    """
    requirements = get_template_data_requirements(template)
    canonical_json = json.dumps(requirements, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


_OWNER_AUTHORIZATION_FIELDS = (
    "template_id",
    "version",
    "template_hash",
    "data_requirements_hash",
    "review_evidence_path",
    "review_evidence_sha256",
    "reviewer_id",
    "reviewer_kind",
    "review_decision",
    "reviewed_at",
    "authorized_by",
    "authorized_at",
    "review_due_date",
)


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _review_evidence_sha256(relative_path: str) -> str | None:
    """Hash a readable review file only when it stays under the repository root."""
    path = Path(relative_path)
    root = _repository_root().resolve()
    if path.is_absolute():
        return None
    candidate = (root / path).resolve()
    try:
        candidate.relative_to(root)
        return hashlib.sha256(candidate.read_bytes()).hexdigest()
    except (OSError, ValueError):
        return None


def _owner_authorization_hash(authorization: dict) -> str | None:
    """Return the deterministic hash of a complete owner authorization record."""
    if any(authorization.get(field) in (None, "") for field in _OWNER_AUTHORIZATION_FIELDS):
        return None
    payload = {
        field: (
            authorization[field].isoformat()
            if isinstance(authorization[field], (date, datetime))
            else authorization[field]
        )
        for field in _OWNER_AUTHORIZATION_FIELDS
    }
    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def _governance_evidence_hash(
    template: "StrategyTemplate",
    governance: dict,
    data_requirements_hash: str | None,
    effective_status: str | None = None,
    owner_authorization_hash: str | None = None,
) -> str:
    """Hash stable governance evidence, excluding runtime and review timestamps."""
    payload = {
        "template_id": template.template_id,
        "version": template.version,
        "template_hash": template.frozen_template_hash,
        "governance_status": effective_status or governance["status"],
        "source_citation": governance["citation"],
        "source_retrieval_date": (
            governance["retrieval"].isoformat() if governance["retrieval"] else None
        ),
        "source_rule_mappings": [
            mapping.model_dump(mode="json")
            if hasattr(mapping, "model_dump")
            else mapping
            for mapping in governance.get("source_rule_mappings", ())
        ],
        "market_scope_difference": governance.get("market_scope_difference"),
        "data_requirements_hash": data_requirements_hash,
        "owner_authorization_hash": owner_authorization_hash,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()


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
        template_id="relative_strength_rotation_vendor_industry_v1",
        version="v1_vendor_industry",
        hypothesis_types=("relative_strength", "theme_rotation"),
        core_entry_rule_id="relative_strength_entry",
        supported_universe_rule_types=("sector_plus_tags",),
        sample_split_rule_ids=("fixed_ratio_70_30",),
        benchmark_rule_id="theme_then_industry_then_equal_weight",
        strategy_config_payload={
            "entry": {"relative_strength_rank_pct_max": 15, "confirm_days": 3},
            "exit": {"rank_exit_pct_min": 40, "max_holding_days": 15, "stop_loss_pct": 8},
            "risk": {"market_regime_allowed": ["green", "yellow"], "min_avg_amount_20d": 50000000},
            "rebalance": {"frequency": "weekly", "max_positions": 5},
        },
        forbidden_fields=("status", "hash", "oos_start", "oos_end", "gate_verdict"),
        forbidden_evidence_terms=("announcement", "disclosure", "report"),
        market_fit="A-share relative strength, vendor industry control group",
        forbidden_market=("limit_up", "st_stock", "delisting_risk"),
        entry_rules="Top 15% relative strength confirmed over 3 days",
        exit_rules="Exit when rank drops below 40% or max 15 days or 8% stop-loss",
        risk_rules="Green/yellow market regime, min 50M avg daily volume",
        position_sizing_rules="Equal weight across max 5 positions, weekly rebalance",
        validation_gate_profile="standard",
    ),
    StrategyTemplate(
        template_id="relative_strength_rotation_sw2021_pit_v1",
        version="v1_sw2021_pit",
        hypothesis_types=("relative_strength", "theme_rotation"),
        core_entry_rule_id="relative_strength_entry",
        supported_universe_rule_types=("point_in_time_membership",),
        sample_split_rule_ids=("fixed_ratio_70_30",),
        benchmark_rule_id="theme_then_industry_then_equal_weight",
        strategy_config_payload={
            "entry": {"relative_strength_rank_pct_max": 15, "confirm_days": 3},
            "exit": {"rank_exit_pct_min": 40, "max_holding_days": 15, "stop_loss_pct": 8},
            "risk": {"market_regime_allowed": ["green", "yellow"], "min_avg_amount_20d": 50000000},
            "rebalance": {"frequency": "weekly", "max_positions": 5},
        },
        forbidden_fields=("status", "hash", "oos_start", "oos_end", "gate_verdict"),
        forbidden_evidence_terms=("announcement", "disclosure", "report"),
        market_fit="A-share relative strength, SW2021 PIT industry control group",
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
    StrategyTemplate(
        template_id="relative_strength_rotation_shsz_sw2021_v1",
        version="v1_shsz_sw2021_pit",
        hypothesis_types=("relative_strength", "theme_rotation"),
        core_entry_rule_id="relative_strength_entry",
        supported_universe_rule_types=("point_in_time_membership",),
        sample_split_rule_ids=("fixed_ratio_70_30",),
        benchmark_rule_id="theme_then_industry_then_equal_weight",
        strategy_config_payload={
            "entry": {"relative_strength_rank_pct_max": 15, "confirm_days": 3},
            "exit": {"rank_exit_pct_min": 40, "max_holding_days": 15, "stop_loss_pct": 8},
            "risk": {"market_regime_allowed": ["green", "yellow"], "min_avg_amount_20d": 50000000},
            "rebalance": {"frequency": "weekly", "max_positions": 5},
            "market_scope": ["SH", "SZ"],
            "minimum_history_trading_days": 0,
        },
        forbidden_fields=("status", "hash", "oos_start", "oos_end", "gate_verdict"),
        forbidden_evidence_terms=("announcement", "disclosure", "report"),
        market_fit="SH/SZ A-share relative strength, SW2021 PIT industry control group. V2 scope reduction: BSE deferred",
        forbidden_market=("limit_up", "st_stock", "delisting_risk"),
        entry_rules="Top 15% relative strength confirmed over 3 days",
        exit_rules="Exit when rank drops below 40% or max 15 days or 8% stop-loss",
        risk_rules="Green/yellow market regime, min 50M avg daily volume",
        position_sizing_rules="Equal weight across max 5 positions, weekly rebalance",
        validation_gate_profile="standard",
    ),
    StrategyTemplate(
        template_id="relative_strength_rotation_shsz_sw2021_v2",
        version="v2_shsz_sw2021_pit_12m",
        hypothesis_types=("relative_strength", "theme_rotation"),
        core_entry_rule_id="relative_strength_entry",
        supported_universe_rule_types=("point_in_time_membership",),
        sample_split_rule_ids=("fixed_ratio_70_30",),
        benchmark_rule_id="theme_then_industry_then_equal_weight",
        strategy_config_payload={
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
        },
        forbidden_fields=("status", "hash", "oos_start", "oos_end", "gate_verdict"),
        forbidden_evidence_terms=("announcement", "disclosure", "report"),
        market_fit="SW2021 PIT membership universe",
        forbidden_market=("limit_up", "st_stock", "delisting_risk"),
        entry_rules="Top 15% relative strength confirmed over 3 days (implementation constraint)",
        exit_rules="Exit when rank drops below 40% or max 15 days or 8% stop-loss (implementation constraint)",
        risk_rules="Green/yellow market regime, min 50M avg daily volume (implementation constraint)",
        position_sizing_rules="Equal weight across max 5 positions, weekly rebalance (implementation constraint)",
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
    """List only approved templates (exclude candidate/retired)."""
    approved = []
    for template in APPROVED_TEMPLATES:
        frozen = convert_to_frozen_contract(template, created_at=datetime.now())
        if frozen.governance_status == "approved":
            approved.append(template)
    return tuple(approved)


def _governance_map() -> dict:
    """Return the sole template-governance and owner-authorization source."""
    return {
        "theme_momentum_breakout_v1": {
            "status": "candidate",
            "citation": "10.1111/0022-1082.00146",
            "retrieval": date(2026, 7, 10),
        },
        "volume_breakout_followthrough_v1": {
            "status": "candidate",
            "citation": "10.1111/0022-1082.00280",
            "retrieval": date(2026, 7, 10),
        },
        "trend_pullback_watch_v1": {
            "status": "retired",
            "citation": None,
            "retrieval": None,
        },
        "relative_strength_rotation_shsz_sw2021_v1": {
            "status": "candidate",
            "citation": "10.1111/j.1540-6261.1993.tb04702.x",
            "retrieval": date(2026, 7, 10),
            "source_rule_mappings": (),
            "market_scope_difference": (
                "J&T's market, sample, costs, shorting, and holding horizon do not equal "
                "TraderLens's SH/SZ A-share, SW2021 PIT, long-only implementation; it is "
                "a hypothesis source, not evidence of expected A-share returns."
            ),
        },
        "relative_strength_rotation_shsz_sw2021_v2": {
            "status": "approved",
            "citation": "10.1111/j.1540-6261.1993.tb04702.x",
            "retrieval": date(2026, 7, 10),
            "source_rule_mappings": (
                # ponytail: 2 source claims from AI review L167-L176
                SourceRuleMapping(
                    source_claim_id="relative_strength_direction",
                    source_locator="p.65, p.73",
                    frozen_rule_id="entry.relative_strength_rank_pct_max",
                    mapping_kind="source_claim",
                    rationale="Core hypothesis: relative strength momentum direction",
                ),
                SourceRuleMapping(
                    source_claim_id="equal_weight",
                    source_locator="p.73",
                    frozen_rule_id="rebalance.max_positions",
                    mapping_kind="source_claim",
                    rationale="Paper equal-weights winners",
                ),
            ),
            "market_scope_difference": (
                "J&T 1993 supports relative strength directional hypothesis only. "
                "All parameters (15%, 3 days, 40%, 15 days, 8%, 50M volume, 5 positions, weekly), "
                "252-day lookback, market scope (SH/SZ, SW2021, T+1, limits, ST), and risk controls "
                "are implementation constraints. Paper: 90-365 day holding, ~300 stocks/portfolio; "
                "Template: 15-day max, 5 positions (5-20x shorter, 60x more concentrated). "
                "No generalization claim to A-shares."
            ),
            # ponytail: Task 1-E owner authorization (single source of truth)
            "owner_authorization": {
                "template_id": "relative_strength_rotation_shsz_sw2021_v2",
                "version": "v2_shsz_sw2021_pit_12m",
                "template_hash": "867a47eeece1c0d208c591f35b5ca31d663ccda183c8721eef803483921238b6",
                "data_requirements_hash": "1910d7a598b1008fb5ba6ee69833e174b5a9949f31a998e2fced436950d8df04",
                "review_evidence_path": "docs/verification/TASK1_V2_AI_TECHNICAL_REVIEW.md",
                "review_evidence_sha256": "ab4391a42ade48c2319dc15bec6799a0280fbbe4ae75dc49bd1a51f403935194",
                "reviewer_id": "ai_reviewer_openai_codex_gpt5",
                "reviewer_kind": "ai_technical_reviewer",
                "review_decision": "approved",
                "reviewed_at": date(2026, 7, 15),
                "review_due_date": date(2027, 7, 15),
                "authorized_by": "illya",
                "authorized_at": datetime(2026, 7, 16, 10, 30, 0),
            },
        },
    }


def convert_to_frozen_contract(
    template: StrategyTemplate,
    created_at: datetime,
) -> StrategyTemplateDefinition:
    """Convert StrategyTemplate to frozen B-module contract with V2 governance."""
    governance_map = _governance_map()
    gov = governance_map.get(template.template_id, {"status": "candidate", "citation": None, "retrieval": None})

    # ponytail: three-way routing for data requirements hash
    if template.template_id == _V2_TEMPLATE_ID:
        data_requirements_hash = _load_v2_requirements_hash(template)
    elif template.template_id == "relative_strength_rotation_shsz_sw2021_v2":
        data_requirements_hash = get_template_data_requirements_hash(template)
    else:
        data_requirements_hash = None  # old templates keep original behavior
    # B1: governance_status always starts from governance_map
    governance_status = gov["status"]
    reviewer_id = None
    reviewed_at = None
    review_due_date = None
    review_evidence_path = None
    review_evidence_sha256 = None
    authorized_by = None
    authorized_at = None
    owner_authorization_hash = None

    # B6: owner_authorization exact-match path
    owner_auth = gov.get("owner_authorization")
    if owner_auth:
        actual_review_sha256 = _review_evidence_sha256(
            owner_auth.get("review_evidence_path", "")
        )
        owner_authorization_hash = _owner_authorization_hash(owner_auth)
        exact_match = (
            owner_auth.get("template_id") == template.template_id
            and owner_auth.get("version") == template.version
            and owner_auth.get("template_hash") == template.frozen_template_hash
            and owner_auth.get("data_requirements_hash") == data_requirements_hash
            and actual_review_sha256 == owner_auth.get("review_evidence_sha256")
            and owner_auth.get("reviewer_id") == "ai_reviewer_openai_codex_gpt5"
            and owner_auth.get("reviewer_kind") == "ai_technical_reviewer"
            and owner_auth.get("review_decision") == "approved"
            and isinstance(owner_auth.get("reviewed_at"), date)
            and isinstance(owner_auth.get("authorized_at"), datetime)
            and isinstance(owner_auth.get("review_due_date"), date)
            and owner_auth["review_due_date"] > owner_auth["reviewed_at"]
            and bool(owner_auth.get("authorized_by"))
            and owner_authorization_hash is not None
        )
        if exact_match:
            governance_status = "approved"
            reviewer_id = owner_auth["reviewer_id"]
            reviewed_at = datetime.combine(owner_auth["reviewed_at"], datetime.min.time())
            review_due_date = owner_auth["review_due_date"]
            review_evidence_path = owner_auth["review_evidence_path"]
            review_evidence_sha256 = owner_auth["review_evidence_sha256"]
            authorized_by = owner_auth["authorized_by"]
            authorized_at = owner_auth["authorized_at"]
        else:
            # exact_match failed: downgrade to candidate regardless of gov["status"]
            governance_status = "candidate"

    return StrategyTemplateDefinition(
        template_id=template.template_id,
        version=template.version,
        template_hash=template.frozen_template_hash,
        hypothesis_types=template.hypothesis_types,
        core_entry_rule_id=template.core_entry_rule_id,
        supported_universe_rule_types=template.supported_universe_rule_types,
        sample_split_rule_ids=template.sample_split_rule_ids,
        benchmark_rule_id=template.benchmark_rule_id,
        created_at=created_at,
        governance_status=governance_status,
        source_citation=gov["citation"],
        source_retrieval_date=gov["retrieval"],
        source_rule_mappings=gov.get("source_rule_mappings", ()),
        market_scope_difference=gov.get("market_scope_difference"),
        data_requirements_hash=data_requirements_hash,
        governance_evidence_hash=_governance_evidence_hash(
            template,
            gov,
            data_requirements_hash,
            governance_status,
            owner_authorization_hash if governance_status == "approved" else None,
        ),
        reviewer_id=reviewer_id,
        reviewed_at=reviewed_at,
        review_due_date=review_due_date,
        review_evidence_path=review_evidence_path,
        review_evidence_sha256=review_evidence_sha256,
        owner_authorization_hash=(
            owner_authorization_hash if governance_status == "approved" else None
        ),
        authorized_by=authorized_by,
        authorized_at=authorized_at,
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
