from __future__ import annotations

from datetime import date
import re
from typing import Protocol

from contracts.stable import DailyBar, Signal, StrategyConfig


class BarDataSource(Protocol):
    def get_daily_bars(self, symbol: str) -> list[DailyBar]:
        ...


def generate_signals(
    config: StrategyConfig,
    data_source: BarDataSource,
    trade_date: date,
    universe: list[str],
) -> list[Signal]:
    """
    Generate entry signals based on entry_conditions.
    
    Exit signals are generated separately by generate_exit_signals().
    """
    if config.entry_conditions.logic != "AND":
        raise NotImplementedError("only AND entry_conditions are implemented")

    rules = config.entry_conditions.rules
    if not rules:
        return []

    signals: list[Signal] = []
    for symbol in universe:
        triggered_rules: list[str] = []
        for rule in rules:
            rule_type = rule.get("type")
            if rule_type == "breakthrough":
                matched = _evaluate_breakthrough(rule, data_source.get_daily_bars(symbol), trade_date)
            elif rule_type == "volume_surge":
                matched = _evaluate_volume_surge(rule, data_source.get_daily_bars(symbol), trade_date)
            elif rule_type == "ma_condition":
                matched = _evaluate_ma_condition(rule, data_source.get_daily_bars(symbol), trade_date)
            else:
                raise NotImplementedError(f"signal rule is not implemented: {rule.get('type')}")

            if matched:
                triggered_rules.append(_rule_label(rule))

        if len(triggered_rules) == len(rules):
            signals.append(
                Signal(
                    signal_id=f"{config.strategy_name}:{config.version}:{symbol}:{trade_date}:entry",
                    strategy_id=config.strategy_name,
                    strategy_version=config.version,
                    symbol=symbol,
                    signal_date=trade_date,
                    signal_type="entry",
                    triggered_rules=triggered_rules,
                    audit_id=f"signal:{config.audit.config_hash}:{symbol}:{trade_date}",
                )
            )
    return signals


def generate_exit_signals(
    config: StrategyConfig,
    data_source: BarDataSource,
    trade_date: date,
    current_positions: dict[str, any],  # symbol -> Position
) -> list[Signal]:
    """
    Generate exit signals for current positions based on exit_conditions.
    
    Exit conditions use OR logic: any rule triggers → exit.
    """
    if config.exit_conditions.logic != "OR":
        raise NotImplementedError("only OR exit_conditions are implemented")
    
    rules = config.exit_conditions.rules
    if not rules:
        return []
    
    signals: list[Signal] = []
    
    for symbol, position in current_positions.items():
        triggered_rules: list[str] = []
        
        for rule in rules:
            rule_type = rule.get("type")
            bars = data_source.get_daily_bars(symbol)
            
            if rule_type == "ma_condition":
                matched = _evaluate_ma_condition_exit(rule, bars, trade_date)
            elif rule_type == "breakthrough":
                matched = _evaluate_breakthrough_exit(rule, bars, trade_date)
            elif rule_type == "holding_days":
                matched = _evaluate_holding_days_exit(rule, position, trade_date)
            elif rule_type == "stop_loss_pct":
                matched = _evaluate_stop_loss_pct_exit(rule, bars, trade_date, position)
            else:
                raise NotImplementedError(f"exit rule is not implemented: {rule.get('type')}")
            
            if matched:
                triggered_rules.append(_rule_label_exit(rule, position))
        
        # OR logic: any rule triggers → exit
        if triggered_rules:
            signals.append(
                Signal(
                    signal_id=f"{config.strategy_name}:{config.version}:{symbol}:{trade_date}:exit",
                    strategy_id=config.strategy_name,
                    strategy_version=config.version,
                    symbol=symbol,
                    signal_date=trade_date,
                    signal_type="exit",
                    triggered_rules=triggered_rules,
                    audit_id=f"signal:{config.audit.config_hash}:{symbol}:{trade_date}",
                )
            )
    
    return signals


def _evaluate_breakthrough(rule: dict, bars: list[DailyBar], trade_date: date) -> bool:
    if rule.get("field") != "close":
        raise NotImplementedError("breakthrough only supports field=close")
    if rule.get("operator") != ">=":
        raise NotImplementedError("breakthrough only supports operator=>=")

    window = _parse_high_window(rule.get("benchmark"))
    history = [bar for bar in bars if bar.date <= trade_date]
    history.sort(key=lambda bar: bar.date)
    if not history:
        return False

    current = history[-1]
    recent = history[-window:]
    benchmark_high = max(bar.high for bar in recent)
    return current.close >= benchmark_high


def _parse_high_window(benchmark: object) -> int:
    if not isinstance(benchmark, str):
        raise ValueError("breakthrough benchmark must be high_Nd")
    match = re.fullmatch(r"high_(\d+)d", benchmark)
    if match is None:
        raise NotImplementedError(f"breakthrough benchmark is not implemented: {benchmark}")
    window = int(match.group(1))
    if window <= 0:
        raise ValueError("breakthrough benchmark window must be positive")
    return window


def _evaluate_volume_surge(rule: dict, bars: list[DailyBar], trade_date: date) -> bool:
    if rule.get("field") != "volume":
        raise NotImplementedError("volume_surge only supports field=volume")
    if rule.get("operator") != ">=":
        raise NotImplementedError("volume_surge only supports operator=>=")

    window = _parse_ma_volume_window(rule.get("benchmark"))
    multiplier = rule.get("multiplier")
    if not isinstance(multiplier, (int, float)) or multiplier <= 0:
        raise ValueError("volume_surge multiplier must be a positive number")

    history = [bar for bar in bars if bar.date <= trade_date]
    history.sort(key=lambda bar: bar.date)
    if not history:
        return False

    current = history[-1]
    recent = history[-window:]
    average_volume = sum(bar.volume for bar in recent) / len(recent)
    return current.volume >= average_volume * float(multiplier)


def _parse_ma_volume_window(benchmark: object) -> int:
    if not isinstance(benchmark, str):
        raise ValueError("volume_surge benchmark must be ma_volume_Nd")
    match = re.fullmatch(r"ma_volume_(\d+)d", benchmark)
    if match is None:
        raise NotImplementedError(f"volume_surge benchmark is not implemented: {benchmark}")
    window = int(match.group(1))
    if window <= 0:
        raise ValueError("volume_surge benchmark window must be positive")
    return window


def _evaluate_ma_condition(rule: dict, bars: list[DailyBar], trade_date: date) -> bool:
    if rule.get("field") != "close":
        raise NotImplementedError("ma_condition only supports field=close")
    if rule.get("operator") != ">":
        raise NotImplementedError("ma_condition only supports operator=>")

    period = rule.get("ma_period")
    if not isinstance(period, int) or period <= 0:
        raise ValueError("ma_condition ma_period must be a positive integer")

    history = [bar for bar in bars if bar.date <= trade_date]
    history.sort(key=lambda bar: bar.date)
    if not history:
        return False

    current = history[-1]
    recent = history[-period:]
    moving_average = sum(bar.close for bar in recent) / len(recent)
    return current.close > moving_average


def _rule_label(rule: dict) -> str:
    if rule.get("type") == "volume_surge":
        return (
            f"volume_surge:{rule.get('field')}{rule.get('operator')}"
            f"{rule.get('benchmark')}*{rule.get('multiplier')}"
        )
    if rule.get("type") == "ma_condition":
        return f"ma_condition:{rule.get('field')}{rule.get('operator')}ma_{rule.get('ma_period')}"
    return f"breakthrough:{rule.get('field')}{rule.get('operator')}{rule.get('benchmark')}"


def _rule_label_exit(rule: dict, position: any) -> str:
    """Generate label for exit rule with actual values."""
    rule_type = rule.get("type")
    
    if rule_type == "ma_condition":
        return f"ma_condition:{rule.get('field')}{rule.get('operator')}ma_{rule.get('ma_period')}"
    elif rule_type == "breakthrough":
        direction = rule.get("direction", "breakdown")
        return f"breakthrough:{direction}:{rule.get('field')}{rule.get('operator')}{rule.get('benchmark')}"
    elif rule_type == "holding_days":
        return f"holding_days >= {rule.get('max_holding_days')}"
    elif rule_type == "stop_loss_pct":
        threshold = rule.get("threshold")
        return f"stop_loss:{threshold*100:.1f}%"
    
    return f"{rule_type}:triggered"


def _evaluate_ma_condition_exit(rule: dict, bars: list[DailyBar], trade_date: date) -> bool:
    """Evaluate MA condition for exit (e.g., close < MA)."""
    if rule.get("field") != "close":
        raise NotImplementedError("ma_condition exit only supports field=close")
    
    operator = rule.get("operator")
    if operator not in ["<", ">"]:
        raise NotImplementedError(f"ma_condition exit only supports operator < or >, got {operator}")
    
    period = rule.get("ma_period")
    if not isinstance(period, int) or period <= 0:
        raise ValueError("ma_condition ma_period must be a positive integer")
    
    history = [bar for bar in bars if bar.date <= trade_date]
    history.sort(key=lambda bar: bar.date)
    if len(history) < period:
        return False
    
    current = history[-1]
    recent = history[-period:]
    moving_average = sum(bar.close for bar in recent) / len(recent)
    
    if operator == "<":
        return current.close < moving_average
    else:  # operator == ">"
        return current.close > moving_average


def _evaluate_breakthrough_exit(rule: dict, bars: list[DailyBar], trade_date: date) -> bool:
    """
    Evaluate breakthrough exit (breakdown below N-day low).
    
    Direction: "breakdown" (跌破低点)
    Benchmark: low_Nd (过去 N 日最低点，不包含当日)
    Operator: "<" (收盘价 < 基准)
    """
    direction = rule.get("direction")
    if direction != "breakdown":
        raise NotImplementedError(f"breakthrough exit only supports direction=breakdown, got {direction}")
    
    if rule.get("field") != "close":
        raise NotImplementedError("breakthrough exit only supports field=close")
    
    operator = rule.get("operator")
    if operator != "<":
        raise NotImplementedError(f"breakthrough exit only supports operator <, got {operator}")
    
    benchmark = rule.get("benchmark")
    if not isinstance(benchmark, str) or not benchmark.startswith("low_"):
        raise NotImplementedError(f"breakthrough exit benchmark must be low_Nd, got {benchmark}")
    
    window = _parse_low_window(benchmark)
    
    history = [bar for bar in bars if bar.date < trade_date]  # Exclude current day
    history.sort(key=lambda bar: bar.date)
    
    if len(history) < window:
        return False  # Not enough data
    
    recent = history[-window:]
    benchmark_low = min(bar.low for bar in recent)
    
    # Get current day bar
    current_bars = [bar for bar in bars if bar.date == trade_date]
    if not current_bars:
        return False
    
    current = current_bars[0]
    return current.close < benchmark_low


def _parse_low_window(benchmark: str) -> int:
    """Parse low_Nd benchmark and return window size."""
    match = re.fullmatch(r"low_(\d+)d", benchmark)
    if match is None:
        raise NotImplementedError(f"breakthrough exit benchmark must be low_Nd, got {benchmark}")
    window = int(match.group(1))
    if window <= 0:
        raise ValueError("breakthrough exit benchmark window must be positive")
    return window


def _evaluate_holding_days_exit(rule: dict, position: any, trade_date: date) -> bool:
    """
    Evaluate holding days exit.
    
    Holding days is calculated from the oldest frozen lot's unlock_date - 1 (buy date under T+1).
    """
    max_holding_days = rule.get("max_holding_days")
    if not isinstance(max_holding_days, int) or max_holding_days <= 0:
        raise ValueError("holding_days max_holding_days must be a positive integer")
    
    buy_date = getattr(position, "oldest_buy_date", None)
    if buy_date is None:
        if not hasattr(position, "frozen_lots") or not position.frozen_lots:
            return False
        from datetime import timedelta
        oldest_unlock_date = min(lot.unlock_date for lot in position.frozen_lots)
        buy_date = oldest_unlock_date - timedelta(days=1)

    holding_days = (trade_date - buy_date).days
    
    return holding_days >= max_holding_days


def _evaluate_stop_loss_pct_exit(rule: dict, bars: list[DailyBar], trade_date: date, position: any) -> bool:
    """
    Evaluate stop loss percentage exit.
    
    Loss is calculated from position.avg_cost to current close price.
    """
    threshold = rule.get("threshold")
    if not isinstance(threshold, (int, float)) or threshold >= 0:
        raise ValueError("stop_loss_pct threshold must be negative (e.g., -0.08 for -8%)")
    
    price_field = rule.get("price_field", "close")
    if price_field != "close":
        raise NotImplementedError("stop_loss_pct only supports price_field=close")
    
    # Get current bar
    current_bars = [bar for bar in bars if bar.date == trade_date]
    if not current_bars:
        return False
    
    current = current_bars[0]
    
    # Calculate return from avg_cost
    if not hasattr(position, "avg_cost") or position.avg_cost <= 0:
        return False
    
    return_pct = (current.close - position.avg_cost) / position.avg_cost
    
    return return_pct <= threshold
