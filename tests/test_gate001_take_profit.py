from datetime import date
from pathlib import Path

import pytest

from contracts.stable import DailyBar, FrozenLot, StrategyConfig
from strategy_core.orders import generate_orders
from strategy_core.portfolio import Position
from strategy_core.position_sizer import PositionSizer
from strategy_core.signals import generate_exit_signals
from strategy_core.dsl_parser import parse_strategy_config
from strategy_core.validator import validate_strategy_config


SYMBOL = "510880.SH"
SIGNAL_DATE = date(2025, 1, 2)
NEXT_DATE = date(2025, 1, 3)


class SyntheticExitSource:
    def __init__(self, closes):
        self.bars = [
            DailyBar(
                date=day,
                symbol=SYMBOL,
                open=close,
                high=close,
                low=close,
                close=close,
                volume=100_000,
                amount=close * 100_000,
                adj_factor=1.0,
            )
            for day, close in closes
        ]

    def get_daily_bars(self, symbol):
        if symbol != SYMBOL:
            raise KeyError(symbol)
        return list(self.bars)

    def get_price(self, symbol, target_date):
        return next(bar.close for bar in self.bars if bar.date == target_date)


def take_profit_rule(threshold=0.10):
    return {"type": "take_profit_pct", "threshold": threshold}


def make_config(*, exit_rules=None, entry_rules=None):
    config_path = Path(__file__).parent / "golden_cases" / "strategy_config.yaml"
    values = parse_strategy_config(config_path).model_dump(mode="python")
    values["universe"]["symbols"] = [SYMBOL]
    values["entry_conditions"] = {
        "logic": "AND",
        "rules": list(entry_rules or []),
    }
    values["exit_conditions"] = {
        "logic": "OR",
        "rules": list(exit_rules or []),
    }
    return StrategyConfig.model_validate(values)


def position(*, avg_cost=10.01, sellable_quantity=100):
    frozen_lots = []
    if sellable_quantity == 0:
        frozen_lots = [FrozenLot(quantity=100, unlock_date=NEXT_DATE)]
    return Position(
        symbol=SYMBOL,
        quantity=100,
        sellable_quantity=sellable_quantity,
        frozen_lots=frozen_lots,
        avg_cost=avg_cost,
        last_price=avg_cost,
        oldest_buy_date=SIGNAL_DATE,
    )


def test_validator_accepts_only_the_fixed_ten_percent_exit_rule():
    config = make_config(exit_rules=[take_profit_rule()])
    assert validate_strategy_config(config) is config

    for threshold in (0.099, 0.101, True, float("nan")):
        invalid = make_config(exit_rules=[take_profit_rule(threshold)])
        with pytest.raises(ValueError, match="fixed at 10%"):
            validate_strategy_config(invalid)


def test_validator_rejects_take_profit_as_entry_or_with_extra_parameters():
    entry_rule = take_profit_rule()
    config = make_config(entry_rules=[entry_rule])
    with pytest.raises(ValueError, match="exit-only"):
        validate_strategy_config(config)

    extra_parameter = take_profit_rule()
    extra_parameter["price_field"] = "close"
    config = make_config(exit_rules=[extra_parameter])
    with pytest.raises(ValueError, match="only supports type and threshold"):
        validate_strategy_config(config)


def test_take_profit_triggers_at_decimal_threshold_equality():
    config = make_config(exit_rules=[take_profit_rule()])
    source = SyntheticExitSource([(SIGNAL_DATE, 11.011)])

    signals = generate_exit_signals(
        config, source, SIGNAL_DATE, {SYMBOL: position(avg_cost=10.01)}
    )

    assert len(signals) == 1
    assert signals[0].signal_date == SIGNAL_DATE
    assert signals[0].triggered_rules == ["take_profit:10.0%"]


def test_take_profit_does_not_trigger_one_tick_below_threshold():
    config = make_config(exit_rules=[take_profit_rule()])
    source = SyntheticExitSource([(SIGNAL_DATE, 11.010)])

    signals = generate_exit_signals(
        config, source, SIGNAL_DATE, {SYMBOL: position(avg_cost=10.01)}
    )

    assert signals == []


@pytest.mark.parametrize(
    ("close", "should_trigger"),
    [(11.007, False), (11.008, True)],
)
def test_take_profit_uses_actual_slipped_fill_price_without_adding_commission_or_dividend(
    close,
    should_trigger,
):
    config = make_config(exit_rules=[take_profit_rule()])
    source = SyntheticExitSource([(SIGNAL_DATE, close)])
    filled_position = position(avg_cost=10.007)
    # These are portfolio cash-flow items, not part of Position.avg_cost or the trigger.
    filled_position.commission_paid = 5.0
    filled_position.dividend_receivable_per_share = 0.10

    signals = generate_exit_signals(
        config, source, SIGNAL_DATE, {SYMBOL: filled_position}
    )

    assert bool(signals) is should_trigger


def test_take_profit_uses_only_current_close_and_requires_a_position():
    config = make_config(exit_rules=[take_profit_rule()])
    source = SyntheticExitSource(
        [(SIGNAL_DATE, 11.010), (NEXT_DATE, 20.0)]
    )

    assert generate_exit_signals(
        config, source, SIGNAL_DATE, {SYMBOL: position(avg_cost=10.01)}
    ) == []
    assert generate_exit_signals(config, source, SIGNAL_DATE, {}) == []


def test_take_profit_does_not_signal_for_a_zero_quantity_position():
    config = make_config(exit_rules=[take_profit_rule()])
    source = SyntheticExitSource([(SIGNAL_DATE, 11.011)])
    empty_position = Position(
        symbol=SYMBOL,
        quantity=0,
        sellable_quantity=0,
        avg_cost=10.01,
        last_price=11.011,
        oldest_buy_date=SIGNAL_DATE,
    )

    assert generate_exit_signals(
        config, source, SIGNAL_DATE, {SYMBOL: empty_position}
    ) == []


def test_take_profit_signal_is_generated_when_signal_day_shares_are_t1_frozen():
    config = make_config(exit_rules=[take_profit_rule()])
    source = SyntheticExitSource([(SIGNAL_DATE, 11.011)])
    frozen_position = position(avg_cost=10.01, sellable_quantity=0)
    signals = generate_exit_signals(
        config, source, SIGNAL_DATE, {SYMBOL: frozen_position}
    )

    assert len(signals) == 1
    assert signals[0].signal_date == SIGNAL_DATE


def test_take_profit_order_intent_uses_next_trading_day():
    config = make_config(exit_rules=[take_profit_rule()])
    source = SyntheticExitSource([(SIGNAL_DATE, 11.011), (NEXT_DATE, 11.2)])
    sellable_position = position(avg_cost=10.01)
    signals = generate_exit_signals(
        config, source, SIGNAL_DATE, {SYMBOL: sellable_position}
    )
    order_result = generate_orders(
        signals,
        intended_execution_date=NEXT_DATE,
        price_provider=source,
        sizer=PositionSizer(position_ratio=0.2),
        available_capital=0.0,
        current_positions={SYMBOL: sellable_position},
    )

    assert len(order_result.valid_orders) == 1
    assert order_result.valid_orders[0].signal_date == SIGNAL_DATE
    assert order_result.valid_orders[0].intended_execution_date == NEXT_DATE
    assert order_result.valid_orders[0].direction == "sell"


def test_existing_stop_loss_exit_rule_behavior_is_unchanged():
    config = make_config(exit_rules=[{"type": "stop_loss_pct", "threshold": -0.08}])
    source = SyntheticExitSource([(SIGNAL_DATE, 9.19)])

    signals = generate_exit_signals(
        config, source, SIGNAL_DATE, {SYMBOL: position(avg_cost=10.0)}
    )

    assert len(signals) == 1
    assert signals[0].triggered_rules == ["stop_loss:-8.0%"]
