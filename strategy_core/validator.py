from __future__ import annotations

from decimal import Decimal, InvalidOperation

from contracts.stable import StrategyConfig


SUPPORTED_RULE_TYPES = {
    "breakthrough",
    "volume_surge",
    "ma_condition",
    "adjusted_ma_cross_down",
    "relative_strength",
    "market_regime",
    "time_exit",
    "ma_breakdown",
    "stop_loss",
    "take_profit_pct",
}

UNSUPPORTED_V1_RULE_TYPES = {
    "pe_ratio",
    "pb_ratio",
    "roe",
    "revenue_growth",
    "announcement_keyword",
    "earnings_event",
    "order_contract",
}


def validate_strategy_config(config: StrategyConfig) -> StrategyConfig:
    if config.universe.type == "static_list" and not config.universe.symbols:
        raise ValueError("static_list universe must include at least one symbol")

    _validate_rule_group("entry", config.entry_conditions)
    _validate_rule_group("exit", config.exit_conditions)
    return config


def _validate_rule_group(group_name: str, group: RuleGroup) -> None:
    for rule in group.rules:
        rule_type = rule.get("type")
        if not isinstance(rule_type, str) or not rule_type:
            raise ValueError(f"{group_name} rule must include a non-empty type")
        if rule_type in UNSUPPORTED_V1_RULE_TYPES:
            raise ValueError(f"{rule_type} is not supported in V1 strategy signals")
        if rule_type not in SUPPORTED_RULE_TYPES:
            raise ValueError(f"unsupported {group_name} rule type: {rule_type}")
        if rule_type == "adjusted_ma_cross_down":
            if group_name != "entry":
                raise ValueError("adjusted_ma_cross_down is entry-only")
            if set(rule) - {"type", "ma_period"}:
                raise ValueError("adjusted_ma_cross_down only supports type and ma_period")
            period = rule.get("ma_period")
            if isinstance(period, bool) or not isinstance(period, int) or period != 250:
                raise ValueError("adjusted_ma_cross_down ma_period is fixed at 250")
        if rule_type == "take_profit_pct":
            if group_name != "exit":
                raise ValueError("take_profit_pct is exit-only")
            if set(rule) != {"type", "threshold"}:
                raise ValueError("take_profit_pct only supports type and threshold")
            try:
                threshold = Decimal(str(rule.get("threshold")))
            except (InvalidOperation, TypeError, ValueError):
                raise ValueError("take_profit_pct threshold is fixed at 10%") from None
            if not threshold.is_finite() or threshold != Decimal("0.10"):
                raise ValueError("take_profit_pct threshold is fixed at 10%")
