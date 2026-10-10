from datetime import date
from pathlib import Path
from unittest.mock import patch
import inspect

from contracts.stable import DailyBar, DailyStatus, FrozenLot, Signal, StrategyConfig
from strategy_core import backtest_engine, signals as signal_module
from strategy_core.dsl_parser import parse_strategy_config
from strategy_core.fill_simulator import simulate_fill
from strategy_core.orders import generate_orders
from strategy_core.portfolio import Position, PortfolioState
from strategy_core.position_sizer import PositionSizer
from strategy_core.trading_calendar import TradingCalendar


SYMBOL = "510880.SH"
DATES = [date(2025, 1, 2), date(2025, 1, 3), date(2025, 1, 6)]


class SyntheticOrderSource:
    def __init__(self):
        self.bars = {
            day: DailyBar(
                date=day,
                symbol=SYMBOL,
                open=10.0,
                high=10.1,
                low=9.9,
                close=10.0,
                volume=100_000,
                amount=1_000_000.0,
                adj_factor=1.0,
            )
            for day in DATES
        }
        self.statuses = {
            day: DailyStatus(
                date=day,
                symbol=SYMBOL,
                is_st=False,
                is_suspended=False,
                is_limit_up=False,
                is_limit_down=False,
            )
            for day in DATES
        }

    def symbols(self):
        return [SYMBOL]

    def get_daily_bars(self, symbol):
        self._require_symbol(symbol)
        return [self.bars[day] for day in DATES]

    def get_daily_bar(self, symbol, target_date):
        self._require_symbol(symbol)
        return self.bars[target_date]

    def get_daily_status(self, symbol, target_date):
        self._require_symbol(symbol)
        return self.statuses[target_date]

    def get_price(self, symbol, target_date):
        return self.get_daily_bar(symbol, target_date).close

    @staticmethod
    def _require_symbol(symbol):
        if symbol != SYMBOL:
            raise KeyError(symbol)


def make_signal(signal_date=DATES[0]):
    return Signal(
        signal_id=f"next-day-exit:{signal_date}",
        strategy_id="gate001-next-day-exit-test",
        strategy_version="test-v1",
        symbol=SYMBOL,
        signal_date=signal_date,
        signal_type="exit",
        triggered_rules=["take_profit:10.0%"],
        audit_id=f"next-day-exit:{signal_date}",
    )


def make_position(quantity, sellable_quantity, frozen_lots, *, avg_cost=10.0):
    return Position(
        symbol=SYMBOL,
        quantity=quantity,
        sellable_quantity=sellable_quantity,
        frozen_lots=frozen_lots,
        avg_cost=avg_cost,
        last_price=10.0,
        oldest_buy_date=DATES[0],
    )


def make_order_result(position, *, enabled, intended_execution_date=DATES[1]):
    source = SyntheticOrderSource()
    return generate_orders(
        [make_signal()],
        intended_execution_date=intended_execution_date,
        price_provider=source,
        sizer=PositionSizer(position_ratio=0.2),
        available_capital=0.0,
        current_positions={SYMBOL: position},
        next_day_exit_intent_mode=enabled,
    )


def test_next_day_exit_intent_mode_is_keyword_only_and_default_off():
    for function in (generate_orders, backtest_engine.run_backtest):
        parameter = inspect.signature(function).parameters.get("next_day_exit_intent_mode")
        assert parameter is not None
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
        assert parameter.default is False


def test_frozen_position_reproduces_legacy_lost_next_day_exit_intent():
    position = make_position(
        100,
        0,
        [FrozenLot(quantity=100, unlock_date=DATES[1])],
    )

    legacy = make_order_result(position, enabled=False)

    assert legacy.valid_orders == []
    assert [event.event_type for event in legacy.events] == ["t1_frozen"]


def test_opt_in_creates_full_order_for_lot_unlocking_on_intended_date():
    position = make_position(
        100,
        0,
        [FrozenLot(quantity=100, unlock_date=DATES[1])],
    )

    result = make_order_result(position, enabled=True)

    assert len(result.valid_orders) == 1
    assert result.valid_orders[0].quantity == 100
    assert result.valid_orders[0].intended_execution_date == DATES[1]
    assert result.events == []


def test_opt_in_partial_order_excludes_lots_unlocking_after_intended_date():
    position = make_position(
        300,
        100,
        [
            FrozenLot(quantity=100, unlock_date=DATES[1]),
            FrozenLot(quantity=100, unlock_date=DATES[2]),
        ],
    )

    result = make_order_result(position, enabled=True)

    assert len(result.valid_orders) == 1
    assert result.valid_orders[0].quantity == 200
    assert len(result.events) == 1
    event = result.events[0]
    assert event.event_type == "partial_exit_due_to_t1_freeze"
    assert event.requested_quantity == 300
    assert event.generated_quantity == 200
    assert event.sellable_quantity == 200
    assert event.total_quantity == 300


def test_mode_off_keeps_existing_sellable_quantity_behavior():
    position = make_position(
        200,
        100,
        [FrozenLot(quantity=100, unlock_date=DATES[1])],
    )

    legacy = make_order_result(position, enabled=False)
    opt_in = make_order_result(position, enabled=True)

    assert legacy.valid_orders[0].quantity == 100
    assert legacy.events[0].sellable_quantity == 100
    assert opt_in.valid_orders[0].quantity == 200
    assert opt_in.events == []


def test_fill_day_t1_guard_rejects_same_day_and_allows_intended_next_day_fill():
    source = SyntheticOrderSource()
    calendar = TradingCalendar(source)
    position = make_position(
        100,
        0,
        [FrozenLot(quantity=100, unlock_date=DATES[1])],
    )
    result = make_order_result(position, enabled=True)
    order = result.valid_orders[0]
    portfolio = PortfolioState(cash=0.0, positions={SYMBOL: position})

    same_day = simulate_fill(order, DATES[0], source, portfolio, calendar=calendar)

    assert same_day.status == "rejected"
    assert same_day.rejection_reason == "insufficient_position"
    assert portfolio.positions[SYMBOL].quantity == 100

    portfolio.unlock_frozen_lots(DATES[1])
    next_day = simulate_fill(order, DATES[1], source, portfolio, calendar=calendar)

    assert next_day.status == "filled"
    assert next_day.actual_execution_date == DATES[1]
    assert SYMBOL not in portfolio.positions


def test_run_backtest_passes_explicit_mode_to_order_generation():
    source = SyntheticOrderSource()
    calendar = TradingCalendar(source)
    config_path = Path(__file__).parent / "golden_cases" / "strategy_config.yaml"
    values = parse_strategy_config(config_path).model_dump(mode="python")
    values["universe"]["symbols"] = [SYMBOL]
    values["backtest_config"]["start_date"] = DATES[0]
    values["backtest_config"]["end_date"] = DATES[1]
    values["backtest_config"]["sample_split"] = {
        "in_sample_end": DATES[0],
        "out_of_sample_start": DATES[1],
    }
    config = StrategyConfig.model_validate(values)

    order_mode_values = []
    original_generate_orders = generate_orders

    def capture_generate_orders(*args, **kwargs):
        order_mode_values.append(kwargs.get("next_day_exit_intent_mode"))
        return original_generate_orders(*args, **kwargs)

    with (
        patch.object(backtest_engine, "generate_signals", return_value=[]),
        patch.object(signal_module, "generate_exit_signals", side_effect=[
            [make_signal(DATES[0])], []
        ]),
        patch.object(backtest_engine, "generate_orders", side_effect=capture_generate_orders),
    ):
        backtest_engine.run_backtest(
            config,
            source,
            calendar,
            next_day_exit_intent_mode=True,
        )

    assert order_mode_values == [True]
