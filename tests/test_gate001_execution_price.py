from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
import inspect

import pytest

from contracts.stable import DailyBar, DailyStatus, Order, Signal, StrategyConfig
from strategy_core import backtest_engine, gate001_market_adapter
from strategy_core.fill_simulator import simulate_fill
from strategy_core.portfolio import PortfolioState, Position
from strategy_core.trading_calendar import TradingCalendar


SYMBOL = "510880.SH"
DATES = [date(2025, 1, 2), date(2025, 1, 3), date(2025, 1, 6), date(2025, 1, 7)]


class SyntheticExecutionPriceSource:
    def __init__(self, open_prices=None, price_limits=None):
        open_prices = open_prices or {}
        price_limits = price_limits or {}
        self.bars = {}
        self.statuses = {}
        self.price_limits = {}
        for day in DATES:
            opening = float(open_prices.get(day, 10.001))
            lower, upper = price_limits.get(day, (Decimal("9.000"), Decimal("11.000")))
            self.price_limits[day] = (Decimal(str(lower)), Decimal(str(upper)))
            bar = DailyBar(
                date=day,
                symbol=SYMBOL,
                open=opening,
                high=max(opening, 10.1),
                low=min(opening, 9.9),
                close=10.001,
                volume=100_000,
                amount=1_000_000.0,
                adj_factor=1.0,
            )
            self.bars[day] = bar
            self.statuses[day] = DailyStatus(
                date=day,
                symbol=SYMBOL,
                is_st=False,
                is_suspended=False,
                is_limit_up=Decimal(str(opening)) >= self.price_limits[day][1],
                is_limit_down=Decimal(str(opening)) <= self.price_limits[day][0],
            )

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

    def get_daily_price_limits(self, symbol, target_date):
        self._require_symbol(symbol)
        return self.price_limits[target_date]

    def get_price(self, symbol, target_date):
        return self.get_daily_bar(symbol, target_date).close

    @staticmethod
    def _require_symbol(symbol):
        if symbol != SYMBOL:
            raise KeyError(symbol)


def make_order(direction="buy", quantity=100):
    return Order(
        order_id=f"execution-price:{direction}",
        signal_id="execution-price-signal",
        signal_date=DATES[0],
        intended_execution_date=DATES[1],
        symbol=SYMBOL,
        direction=direction,
        quantity=quantity,
        reason="synthetic execution-price test",
        strategy_version="gate001-test-v1",
        audit_id="execution-price-test",
    )


def make_config(source, *, slippage):
    from strategy_core.dsl_parser import parse_strategy_config

    config_path = Path(__file__).parent / "golden_cases" / "strategy_config.yaml"
    values = parse_strategy_config(config_path).model_dump(mode="python")
    values["universe"]["symbols"] = [SYMBOL]
    values["risk_filters"]["max_position_per_stock"] = 1.0
    values["risk_filters"]["max_total_position"] = 1.0
    values["fill_model"]["commission"] = 0.0003
    values["fill_model"]["stamp_tax"] = 0.0
    values["fill_model"]["slippage"] = slippage
    values["backtest_config"]["start_date"] = DATES[0]
    values["backtest_config"]["end_date"] = DATES[-1]
    values["backtest_config"]["sample_split"] = {
        "in_sample_end": DATES[0],
        "out_of_sample_start": DATES[1],
    }
    return StrategyConfig.model_validate(values)


def make_entry_signal(config, signal_date):
    return Signal(
        signal_id=f"execution-price-entry:{signal_date}",
        strategy_id=config.strategy_name,
        strategy_version=config.version,
        symbol=SYMBOL,
        signal_date=signal_date,
        signal_type="entry",
        triggered_rules=["synthetic-entry"],
        audit_id=f"execution-price-entry:{signal_date}",
    )


def test_execution_price_modes_are_keyword_only_and_default_off():
    for function in (simulate_fill, backtest_engine.run_backtest):
        parameter = inspect.signature(function).parameters.get("execution_price_mode")
        assert parameter is not None
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
        assert parameter.default is False


@pytest.mark.parametrize(
    ("slippage", "expected_price"),
    [(0.0005, 10.007), (0.001, 10.012)],
)
def test_buy_price_uses_configured_slippage_and_ceiling_tick(slippage, expected_price):
    source = SyntheticExecutionPriceSource()
    calendar = TradingCalendar(source)
    portfolio = PortfolioState(cash=100_000.0)

    filled = simulate_fill(
        make_order(), DATES[1], source, portfolio,
        slippage_rate=slippage,
        calendar=calendar,
        round_to_cents=True,
        execution_price_mode=True,
    )

    assert filled.status == "filled"
    assert filled.actual_price == expected_price
    assert filled.actual_quantity == 100
    assert portfolio.positions[SYMBOL].avg_cost == expected_price
    assert portfolio.cash == pytest.approx(100_000.0 - expected_price * 100 - 5.0)


def test_sell_price_uses_unfavorable_floor_tick():
    source = SyntheticExecutionPriceSource()
    calendar = TradingCalendar(source)
    portfolio = PortfolioState(
        cash=0.0,
        positions={
            SYMBOL: Position(
                symbol=SYMBOL,
                quantity=100,
                sellable_quantity=100,
                avg_cost=10.0,
                last_price=10.0,
                oldest_buy_date=DATES[0],
            )
        },
    )

    filled = simulate_fill(
        make_order(direction="sell"), DATES[1], source, portfolio,
        slippage_rate=0.0005,
        calendar=calendar,
        round_to_cents=True,
        execution_price_mode=True,
    )

    assert filled.status == "filled"
    assert filled.actual_price == 9.995
    assert SYMBOL not in portfolio.positions
    assert portfolio.cash == pytest.approx(993.50)


@pytest.mark.parametrize(
    ("direction", "opening", "limits"),
    [
        ("buy", 10.999, (Decimal("9.000"), Decimal("11.000"))),
        ("sell", 9.001, (Decimal("9.000"), Decimal("11.000"))),
    ],
)
def test_slipped_price_outside_daily_band_is_rejected_without_mutation(direction, opening, limits):
    source = SyntheticExecutionPriceSource(
        open_prices={DATES[1]: opening},
        price_limits={DATES[1]: limits},
    )
    calendar = TradingCalendar(source)
    positions = {}
    if direction == "sell":
        positions[SYMBOL] = Position(
            symbol=SYMBOL,
            quantity=100,
            sellable_quantity=100,
            avg_cost=10.0,
            last_price=10.0,
            oldest_buy_date=DATES[0],
        )
    portfolio = PortfolioState(cash=100_000.0, positions=positions)
    before_cash = portfolio.cash
    before_quantity = portfolio.positions.get(SYMBOL).quantity if SYMBOL in portfolio.positions else 0

    result = simulate_fill(
        make_order(direction=direction), DATES[1], source, portfolio,
        slippage_rate=0.0005,
        calendar=calendar,
        execution_price_mode=True,
    )

    assert result.status == "rejected"
    assert result.rejection_reason == "execution_price_outside_price_limit"
    assert portfolio.cash == before_cash
    assert (portfolio.positions[SYMBOL].quantity if SYMBOL in portfolio.positions else 0) == before_quantity


def test_execution_price_mode_fails_loudly_without_price_band_source():
    source = SyntheticExecutionPriceSource()
    source.get_daily_price_limits = None

    with pytest.raises(ValueError, match="daily price limits"):
        simulate_fill(
            make_order(), DATES[1], source, PortfolioState(cash=100_000.0),
            calendar=TradingCalendar(source),
            execution_price_mode=True,
        )


@pytest.mark.parametrize(
    ("limits", "message"),
    [
        ((Decimal("12.000"), Decimal("11.000")), "lower price limit exceeds"),
        ((Decimal("8.9995"), Decimal("11.000")), "0.001 tick"),
    ],
)
def test_execution_price_mode_rejects_invalid_price_band_metadata(limits, message):
    source = SyntheticExecutionPriceSource()
    source.price_limits[DATES[1]] = limits

    with pytest.raises(ValueError, match=message):
        simulate_fill(
            make_order(), DATES[1], source, PortfolioState(cash=100_000.0),
            calendar=TradingCalendar(source),
            execution_price_mode=True,
        )


def test_gate001_price_limits_use_preclose_and_half_up_tick():
    derive_limits = getattr(gate001_market_adapter, "_derive_price_limits", None)
    assert callable(derive_limits)
    lower, upper = derive_limits(Decimal("1.005"))
    assert (lower, upper) == (Decimal("0.905"), Decimal("1.106"))

    getter = getattr(gate001_market_adapter.Gate001MarketDataSource, "get_daily_price_limits", None)
    assert callable(getter)
    source = object.__new__(gate001_market_adapter.Gate001MarketDataSource)
    source._price_limit_index = {DATES[0]: (lower, upper)}
    assert getter(source, SYMBOL, DATES[0]) == (lower, upper)


@pytest.mark.parametrize(
    ("slippage", "expected_execution_price"),
    [(0.0005, 10.007), (0.001, 10.012)],
)
def test_backtest_uses_fill_model_slippage_and_retries_band_block_at_same_opening_intent(
    slippage,
    expected_execution_price,
):
    source = SyntheticExecutionPriceSource(
        open_prices={DATES[1]: 10.999, DATES[2]: 10.001},
    )
    calendar = TradingCalendar(source)
    config = make_config(source, slippage=slippage)

    def entries(current_config, _source, trade_date, _universe):
        if trade_date == DATES[0]:
            return [make_entry_signal(current_config, trade_date)]
        return []

    with (
        patch.object(backtest_engine, "generate_signals", side_effect=entries),
        patch("strategy_core.signals.generate_exit_signals", return_value=[]),
    ):
        result = backtest_engine.run_backtest(
            config,
            source,
            calendar,
            initial_capital=100_000.0,
            cash_target_buy=True,
            retry_temporarily_blocked_orders=True,
            round_to_cents=True,
            execution_price_mode=True,
        )

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.trade_date == DATES[2]
    assert trade.price == expected_execution_price
    assert trade.quantity == 9_900
    assert trade.gross_amount == pytest.approx(trade.price * trade.quantity)
    assert trade.total_fee == pytest.approx(trade.commission + trade.stamp_duty + trade.transfer_fee)
    assert trade.net_cash_flow == pytest.approx(-trade.gross_amount - trade.total_fee)
    fill_day_value = next(value for value in result.daily_portfolio_values if value.date == DATES[2])
    assert fill_day_value.cash == pytest.approx(100_000.0 + trade.net_cash_flow)
    assert any("rejection_reason=execution_price_outside_price_limit" in warning for warning in result.warnings)
    assert any("signal_date=2025-01-02" in warning for warning in result.warnings)
    assert not result.rejected_orders


def test_backtest_legacy_default_does_not_apply_configured_slippage():
    source = SyntheticExecutionPriceSource()
    calendar = TradingCalendar(source)
    config = make_config(source, slippage=0.001)

    def entries(current_config, _source, trade_date, _universe):
        if trade_date == DATES[0]:
            return [make_entry_signal(current_config, trade_date)]
        return []

    with (
        patch.object(backtest_engine, "generate_signals", side_effect=entries),
        patch("strategy_core.signals.generate_exit_signals", return_value=[]),
    ):
        result = backtest_engine.run_backtest(
            config,
            source,
            calendar,
            initial_capital=100_000.0,
            cash_target_buy=True,
            round_to_cents=True,
        )

    assert len(result.trades) == 1
    assert result.trades[0].price == 10.001
