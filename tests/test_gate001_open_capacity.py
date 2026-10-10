from datetime import date
import inspect
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from contracts.stable import DailyBar, DailyStatus, Order, StrategyConfig
from strategy_core import backtest_engine, signals as signal_module
from strategy_core.fill_simulator import simulate_fill
from strategy_core.portfolio import Position, PortfolioState
from strategy_core.transaction_costs import calculate_transaction_costs
from strategy_core.trading_calendar import TradingCalendar


SYMBOL = "510880.SH"
DATES = [date(2025, 1, 2), date(2025, 1, 3), date(2025, 1, 6), date(2025, 1, 7)]
PROTOCOL_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "alpha_gate_001"
    / "GATE001_PROTOCOL_V1_20261005_a94b1e3f6d6a46af87894e0269777a32.json"
)


class SyntheticCapacitySource:
    def __init__(self, dates=DATES, volumes=None):
        self.dates = list(dates)
        volumes = volumes or {}
        self.bars = {
            day: DailyBar(
                date=day,
                symbol=SYMBOL,
                open=10.0,
                high=10.5,
                low=9.5,
                close=10.0,
                volume=volumes.get(day, 1_000_000),
                amount=10_000_000.0,
                adj_factor=1.0,
            )
            for day in self.dates
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
            for day in self.dates
        }
        self.bar_overrides = {}

    def symbols(self):
        return [SYMBOL]

    def get_daily_bars(self, symbol):
        self._require_symbol(symbol)
        return [self.bars[day] for day in self.dates]

    def get_daily_statuses(self, symbol):
        self._require_symbol(symbol)
        return [self.statuses[day] for day in self.dates]

    def get_daily_bar(self, symbol, target_date):
        self._require_symbol(symbol)
        if target_date in self.bar_overrides:
            return self.bar_overrides[target_date]
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


def make_order(direction="buy", quantity=100, execution_date=DATES[1], signal_date=DATES[0]):
    return Order(
        order_id=f"capacity:{direction}:{execution_date}:{quantity}",
        signal_id=f"capacity-signal:{signal_date}",
        signal_date=signal_date,
        intended_execution_date=execution_date,
        symbol=SYMBOL,
        direction=direction,
        quantity=quantity,
        reason="synthetic-capacity-test",
        strategy_version="test",
        audit_id=f"capacity-audit:{signal_date}",
    )


def make_config(source):
    from strategy_core.dsl_parser import parse_strategy_config

    path = Path(__file__).parent / "golden_cases" / "strategy_config.yaml"
    values = parse_strategy_config(path).model_dump(mode="python")
    values["universe"]["symbols"] = [SYMBOL]
    values["risk_filters"]["max_position_per_stock"] = 1.0
    values["risk_filters"]["max_total_position"] = 1.0
    values["backtest_config"]["start_date"] = source.dates[0]
    values["backtest_config"]["end_date"] = source.dates[-1]
    values["backtest_config"]["sample_split"] = {
        "in_sample_end": source.dates[0],
        "out_of_sample_start": source.dates[1],
    }
    return StrategyConfig.model_validate(values)


def entry_signal(config, signal_date):
    from contracts.stable import Signal

    return Signal(
        signal_id=f"capacity-entry:{signal_date}",
        strategy_id=config.strategy_name,
        strategy_version=config.version,
        symbol=SYMBOL,
        signal_date=signal_date,
        signal_type="entry",
        triggered_rules=["capacity-entry"],
        audit_id=f"capacity-entry:{signal_date}",
    )


def test_opening_capacity_mode_is_explicit_and_default_off():
    fill_parameter = inspect.signature(simulate_fill).parameters.get("opening_capacity_mode")
    backtest_parameter = inspect.signature(backtest_engine.run_backtest).parameters.get(
        "opening_capacity_mode"
    )
    assert fill_parameter is not None
    assert fill_parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert fill_parameter.default is False
    assert backtest_parameter is not None
    assert backtest_parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert backtest_parameter.default is False


def test_buy_capacity_uses_previous_session_volume_and_floors_to_whole_lots():
    source = SyntheticCapacitySource(volumes={DATES[0]: 1999, DATES[1]: 0})
    calendar = TradingCalendar(source)

    blocked = simulate_fill(
        make_order(quantity=200), DATES[1], source, PortfolioState(cash=100_000),
        calendar=calendar, opening_capacity_mode=True,
    )
    assert blocked.status == "rejected"
    assert blocked.rejection_reason == "liquidity_shortfall"

    source.bars[DATES[0]] = source.bars[DATES[0]].model_copy(update={"volume": 2000})
    filled = simulate_fill(
        make_order(quantity=200), DATES[1], source, PortfolioState(cash=100_000),
        calendar=calendar, opening_capacity_mode=True,
    )
    assert filled.status == "filled"
    assert filled.actual_quantity == 200


def test_execution_day_volume_does_not_change_buy_capacity_but_default_mode_still_uses_it():
    source = SyntheticCapacitySource(volumes={DATES[0]: 2000, DATES[1]: 0})
    calendar = TradingCalendar(source)

    observed_open_fill = simulate_fill(
        make_order(quantity=200), DATES[1], source, PortfolioState(cash=100_000),
        calendar=calendar, opening_capacity_mode=True,
    )
    assert observed_open_fill.status == "filled"
    assert observed_open_fill.actual_quantity == 200

    legacy = simulate_fill(
        make_order(quantity=200), DATES[1], source, PortfolioState(cash=100_000),
        calendar=calendar,
    )
    assert legacy.status == "rejected"
    assert legacy.rejection_reason == "liquidity_shortfall"


def test_sell_capacity_uses_previous_session_volume_without_mutating_on_shortfall():
    source = SyntheticCapacitySource(volumes={DATES[0]: 1999, DATES[1]: 1_000_000})
    calendar = TradingCalendar(source)
    portfolio = PortfolioState(cash=500.0)
    portfolio.positions[SYMBOL] = Position(
        symbol=SYMBOL,
        quantity=200,
        sellable_quantity=200,
        avg_cost=10.0,
        last_price=10.0,
    )

    blocked = simulate_fill(
        make_order(direction="sell", quantity=200), DATES[1], source, portfolio,
        calendar=calendar, opening_capacity_mode=True,
    )
    assert blocked.status == "rejected"
    assert blocked.rejection_reason == "liquidity_shortfall"
    assert portfolio.positions[SYMBOL].quantity == 200
    assert portfolio.cash == 500.0

    source.bars[DATES[0]] = source.bars[DATES[0]].model_copy(update={"volume": 2000})
    filled = simulate_fill(
        make_order(direction="sell", quantity=200), DATES[1], source, portfolio,
        calendar=calendar, opening_capacity_mode=True,
    )
    assert filled.status == "filled"
    assert filled.actual_quantity == 200
    assert SYMBOL not in portfolio.positions


def test_sell_quantity_is_independent_of_execution_day_volume():
    fills = []
    for execution_volume in (0, 5_000_000):
        source = SyntheticCapacitySource(
            volumes={DATES[0]: 2000, DATES[1]: execution_volume}
        )
        calendar = TradingCalendar(source)
        portfolio = PortfolioState(cash=500.0)
        portfolio.positions[SYMBOL] = Position(
            symbol=SYMBOL,
            quantity=200,
            sellable_quantity=200,
            avg_cost=10.0,
            last_price=10.0,
        )
        fills.append(simulate_fill(
            make_order(direction="sell", quantity=200), DATES[1], source, portfolio,
            calendar=calendar, opening_capacity_mode=True,
        ))

    assert [fill.status for fill in fills] == ["filled", "filled"]
    assert [fill.actual_quantity for fill in fills] == [200, 200]


def test_zero_prior_volume_is_an_explicit_retryable_zero_capacity_block():
    source = SyntheticCapacitySource(volumes={DATES[0]: 0})
    calendar = TradingCalendar(source)

    result = simulate_fill(
        make_order(quantity=100), DATES[1], source, PortfolioState(cash=100_000),
        calendar=calendar, opening_capacity_mode=True,
    )

    assert result.status == "rejected"
    assert result.rejection_reason == "liquidity_shortfall_zero_previous_session_capacity"


def test_missing_or_invalid_previous_session_volume_fails_loud():
    first_day_source = SyntheticCapacitySource(dates=DATES[1:])
    first_day_calendar = TradingCalendar(first_day_source)
    with pytest.raises(ValueError, match="no trading day before"):
        simulate_fill(
            make_order(quantity=100, execution_date=DATES[1], signal_date=date(2025, 1, 1)),
            DATES[1], first_day_source, PortfolioState(cash=100_000),
            calendar=first_day_calendar, opening_capacity_mode=True,
        )

    source = SyntheticCapacitySource()
    source.bar_overrides[DATES[0]] = SimpleNamespace(
        date=DATES[0], symbol=SYMBOL, volume=-1
    )
    with pytest.raises(ValueError, match="previous session volume"):
        simulate_fill(
            make_order(quantity=100), DATES[1], source, PortfolioState(cash=100_000),
            calendar=TradingCalendar(source), opening_capacity_mode=True,
        )


def test_cash_target_buy_waits_as_a_whole_order_then_fills_once(monkeypatch):
    source = SyntheticCapacitySource(volumes={DATES[0]: 0, DATES[1]: 200_000})
    calendar = TradingCalendar(source)
    config = make_config(source)

    def entries(current_config, _source, current_date, _universe):
        return [entry_signal(current_config, current_date)] if current_date == DATES[0] else []

    monkeypatch.setattr(backtest_engine, "generate_signals", entries)
    monkeypatch.setattr(signal_module, "generate_exit_signals", lambda *_args: [])
    result = backtest_engine.run_backtest(
        config,
        source,
        calendar,
        initial_capital=100_000.0,
        cash_target_buy=True,
        opening_capacity_mode=True,
    )

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.direction == "buy"
    assert trade.trade_date == DATES[2]
    assert trade.quantity == 9900
    assert trade.order_id == f"order:capacity-entry:{DATES[0]}:{DATES[1]}"
    assert result.buy_order_count == result.buy_fill_count == 1
    assert result.rejected_orders == []
    assert any("opening capacity mode" in warning.lower() for warning in result.warnings)
    retry_warnings = [warning for warning in result.warnings if "pending_order_retry" in warning]
    assert len(retry_warnings) == 1
    assert "liquidity_shortfall_zero_previous_session_capacity" in retry_warnings[0]
    assert next(value for value in result.daily_portfolio_values if value.date == DATES[1]).cash == 100_000.0
    fill_day_cash = next(value for value in result.daily_portfolio_values if value.date == DATES[2]).cash
    assert fill_day_cash == pytest.approx(100_000.0 + trade.net_cash_flow)


def test_cash_target_quantity_above_positive_capacity_waits_without_partial_debit():
    source = SyntheticCapacitySource(volumes={DATES[0]: 50_000, DATES[1]: 200_000})
    calendar = TradingCalendar(source)
    portfolio = PortfolioState(cash=100_000.0)
    order = make_order(quantity=100)

    blocked = simulate_fill(
        order, DATES[1], source, portfolio,
        calendar=calendar, cash_target_buy=True, opening_capacity_mode=True,
    )
    assert blocked.status == "rejected"
    assert blocked.rejection_reason == "liquidity_shortfall"
    assert portfolio.cash == 100_000.0
    assert portfolio.positions == {}

    filled = simulate_fill(
        order, DATES[2], source, portfolio,
        calendar=calendar, cash_target_buy=True, opening_capacity_mode=True,
    )
    assert filled.status == "filled"
    assert filled.actual_quantity == 9900
    *_, net_cash_flow = calculate_transaction_costs(
        "buy", filled.actual_quantity, filled.actual_price,
        0.0003, 5.0, 0.001, 0.0,
    )
    assert portfolio.cash == pytest.approx(100_000.0 + net_cash_flow)


def test_protocol_records_prior_volume_capacity_and_limitation():
    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    policy = protocol["account_and_execution"]["opening_capacity_policy"]

    assert policy["enabled_by_default"] is False
    assert policy["capacity_input"] == "previous_trading_session_daily_volume_shares"
    assert policy["participation_rate"] == "0.10"
    assert policy["lot_size_shares"] == 100
    assert policy["rounding"] == "floor_to_whole_100_share_lots"
    assert "entire original order pending" in policy["capacity_overflow"]
    assert "fail_loud" in policy["missing_previous_session_or_invalid_volume"]
    assert "must_not_affect" in policy["execution_date_volume"]
    assert "queue" in policy["limitations"].lower()
    assert protocol["formal_performance_result_allowed"] is False
