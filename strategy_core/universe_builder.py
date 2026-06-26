from __future__ import annotations

from typing import Protocol

from contracts.stable import StrategyConfig


class SymbolDataSource(Protocol):
    def symbols(self) -> list[str]:
        ...


def build_universe(config: StrategyConfig, data_source: SymbolDataSource) -> list[str]:
    if config.universe.type != "static_list":
        raise NotImplementedError(f"{config.universe.type} universe is not implemented")

    available = set(data_source.symbols())
    for symbol in config.universe.symbols:
        if symbol not in available:
            raise ValueError(f"symbol not available in data source: {symbol}")
    return list(config.universe.symbols)
