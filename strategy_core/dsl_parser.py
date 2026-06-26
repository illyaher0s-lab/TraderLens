from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from contracts.stable import StrategyConfig


def parse_strategy_config(path: str | Path, validate_semantics: bool = False) -> StrategyConfig:
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)

    if not isinstance(raw, dict):
        raise ValueError(f"strategy config must be a YAML mapping: {config_path}")

    return parse_strategy_config_dict(raw, validate_semantics=validate_semantics)


def parse_strategy_config_dict(raw: dict[str, Any], validate_semantics: bool = False) -> StrategyConfig:
    config = StrategyConfig.model_validate(raw)
    if validate_semantics:
        from .validator import validate_strategy_config

        validate_strategy_config(config)
    return config
