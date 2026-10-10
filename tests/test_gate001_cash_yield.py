from datetime import date, timedelta
from decimal import Decimal
import inspect
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from contracts.stable import DailyBar, DailyStatus, Signal, StrategyConfig
from strategy_core import backtest_engine, signals as signal_module
from strategy_core.dsl_parser import parse_strategy_config
from strategy_core.trading_calendar import TradingCalendar


SYMBOL = "510880.SH"
DATES = [date(2025, 1, 2), date(2025, 1, 3), date(2025, 1, 6), date(2025, 1, 7)]


class SyntheticCashSource:
    def __init__(self, dates=DATES, open_price_by_date=None):
        self.dates = list(dates)
        open_price_by_date = open_price_by_date or {}
        self.bars = {
            day: DailyBar(
                date=day,
                symbol=SYMBOL,
                open=open_price_by_date.get(day, 10.0),
                high=12.0,
                low=9.0,
                close=10.0,
                volume=1_000_000,
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

    def symbols(self):
        return [SYMBOL]

    def get_daily_bars(self, symbol):
        self._require_symbol(symbol)
        return [self.bars[day] for day in self.dates]

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


def make_config(dates=DATES, *, full_position=False):
    path = Path(__file__).parent / "golden_cases" / "strategy_config.yaml"
    values = parse_strategy_config(path).model_dump(mode="python")
    values["universe"]["symbols"] = [SYMBOL]
    values["risk_filters"]["max_position_per_stock"] = 1.0 if full_position else 0.2
    values["risk_filters"]["max_total_position"] = 1.0 if full_position else 0.8
    values["fill_model"]["stamp_tax"] = 0.0
    values["backtest_config"]["start_date"] = dates[0]
    values["backtest_config"]["end_date"] = dates[-1]
    values["backtest_config"]["sample_split"] = {
        "in_sample_end": dates[1],
        "out_of_sample_start": dates[2],
    }
    return StrategyConfig.model_validate(values)


def make_event(dates=DATES, *, record_date=None, ex_date=None, pay_date=None, div_cash="10.00"):
    record_date = record_date or dates[-1] + timedelta(days=1)
    ex_date = ex_date or record_date + timedelta(days=1)
    pay_date = pay_date or ex_date + timedelta(days=1)
    return {
        "ts_code": SYMBOL,
        "ann_date": dates[0].isoformat(),
        "record_date": record_date.isoformat(),
        "ex_date": ex_date.isoformat(),
        "pay_date": pay_date.isoformat(),
        "div_cash": div_cash,
        "source_ref": "synthetic://gate001/cash-yield-test",
    }


def make_entry_signal(trade_date):
    return Signal(
        signal_id=f"cash-yield-entry:{trade_date}",
        strategy_id="gate001-cash-yield-test",
        strategy_version="test-v1",
        symbol=SYMBOL,
        signal_date=trade_date,
        signal_type="entry",
        triggered_rules=["synthetic-entry"],
        audit_id=f"cash-yield-entry:{trade_date}",
    )


def run_with_signals(config, source, calendar, entry_dates=(), **kwargs):
    def entries(_config, _source, trade_date, _universe):
        return [make_entry_signal(trade_date)] if trade_date in entry_dates else []

    with (
        patch.object(backtest_engine, "generate_signals", side_effect=entries),
        patch.object(signal_module, "generate_exit_signals", return_value=[]),
    ):
        return backtest_engine.run_backtest(config, source, calendar, **kwargs)


def cash_at(result, target_date):
    matches = [
        item.cash for item in result.daily_portfolio_values
        if item.date == target_date
    ]
    return matches[-1]


def value_at(result, target_date):
    matches = [
        item for item in result.daily_portfolio_values
        if item.date == target_date
    ]
    return matches[-1]


def test_cash_yield_is_keyword_only_zero_by_default_and_protocol_keeps_lock_closed():
    parameter = inspect.signature(backtest_engine.run_backtest).parameters[
        "cash_yield_annual_rate"
    ]
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert parameter.default == 0.0

    protocol_path = (
        Path(__file__).parents[1]
        / "data"
        / "alpha_gate_001"
        / "GATE001_PROTOCOL_V1_20261005_a94b1e3f6d6a46af87894e0269777a32.json"
    )
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    assert protocol["formal_performance_result_allowed"] is False
    assert protocol["cash_return"]["primary_annual_rate"] == "0"
    assert protocol["cash_return"]["stress_annual_rate"] == "0.03"
    assert "first common evaluation date" in protocol["cash_return"]["stress_accrual"]
    assert "previous evaluation date's end-of-day available cash" in protocol["cash_return"]["stress_accrual"]


def test_cash_yield_skips_preheat_and_uses_one_or_three_calendar_days():
    source = SyntheticCashSource()
    calendar = TradingCalendar(source)
    config = make_config()
    result = run_with_signals(
        config,
        source,
        calendar,
        initial_capital=100_000.0,
        dividend_events=[make_event()],
        round_to_cents=True,
        cash_yield_annual_rate=0.03,
    )

    assert Decimal(str(cash_at(result, DATES[0]))) == Decimal("100000.00")
    assert Decimal(str(cash_at(result, DATES[1]))) == Decimal("100008.22")
    assert Decimal(str(cash_at(result, DATES[2]))) == Decimal("100032.88")


def test_zero_rate_preserves_legacy_no_ledger_backtest_output():
    source = SyntheticCashSource()
    calendar = TradingCalendar(source)
    config = make_config()
    with (
        patch.object(backtest_engine, "generate_signals", return_value=[]),
        patch.object(signal_module, "generate_exit_signals", return_value=[]),
    ):
        default_result = backtest_engine.run_backtest(
            config, source, calendar, initial_capital=100_000.0
        )
        zero_rate_result = backtest_engine.run_backtest(
            config,
            source,
            calendar,
            initial_capital=100_000.0,
            cash_yield_annual_rate=0.0,
        )

    assert default_result.model_dump() == zero_rate_result.model_dump()


def test_each_interest_interval_rounds_to_cents_half_up():
    source = SyntheticCashSource()
    calendar = TradingCalendar(source)
    result = run_with_signals(
        make_config(),
        source,
        calendar,
        initial_capital=1_000.0,
        dividend_events=[make_event()],
        round_to_cents=True,
        cash_yield_annual_rate=0.001825,
    )

    # One day earns exactly half a cent; the following three-day interval is rounded separately.
    assert Decimal(str(cash_at(result, DATES[1]))) == Decimal("1000.01")
    assert Decimal(str(cash_at(result, DATES[2]))) == Decimal("1000.03")


@pytest.mark.parametrize("pay_date", [date(2025, 1, 4), date(2025, 1, 6)])
def test_dividend_receivable_does_not_earn_interest_before_open_or_eod_payment(pay_date):
    source = SyntheticCashSource()
    calendar = TradingCalendar(source)
    config = make_config()
    event = make_event(
        record_date=DATES[1],
        ex_date=DATES[1],
        pay_date=pay_date,
        div_cash="10.00",
    )
    result = run_with_signals(
        config,
        source,
        calendar,
        entry_dates={DATES[0]},
        initial_capital=100_000.0,
        dividend_events=[event],
        round_to_cents=True,
        cash_yield_annual_rate=0.03,
    )

    previous_eod_cash = Decimal(str(cash_at(result, DATES[1])))
    current_eod_cash = Decimal(str(cash_at(result, DATES[2])))
    previous_eod_value = value_at(result, DATES[1])
    expected_interest = (
        previous_eod_cash * Decimal("0.03") * Decimal("3") / Decimal("365")
    ).quantize(Decimal("0.01"), rounding="ROUND_HALF_UP")
    dividend_payment = Decimal("20000.00")

    assert result.trades[0].quantity == 2_000
    assert Decimal(str(previous_eod_value.total_value)) == (
        previous_eod_cash
        + Decimal(str(previous_eod_value.market_value))
        + dividend_payment
    )
    assert current_eod_cash - previous_eod_cash - dividend_payment == expected_interest


@pytest.mark.parametrize("rate", [-0.01, float("nan"), float("inf")])
def test_cash_yield_rejects_negative_or_nonfinite_rates(rate):
    source = SyntheticCashSource()
    calendar = TradingCalendar(source)

    with pytest.raises(ValueError, match="cash_yield_annual_rate must be finite and nonnegative"):
        run_with_signals(
            make_config(),
            source,
            calendar,
            cash_yield_annual_rate=rate,
        )


def test_interest_changes_cash_target_buy_budget_and_nonzero_rate_requires_deferred_path():
    source = SyntheticCashSource(open_price_by_date={DATES[1]: 9.9975})
    calendar = TradingCalendar(source)
    config = make_config(full_position=True)
    event = make_event()

    baseline = run_with_signals(
        config,
        source,
        calendar,
        entry_dates={DATES[0]},
        initial_capital=100_000.0,
        dividend_events=[event],
        cash_target_buy=True,
        round_to_cents=True,
        cash_yield_annual_rate=0.0,
    )
    stress = run_with_signals(
        config,
        source,
        calendar,
        entry_dates={DATES[0]},
        initial_capital=100_000.0,
        dividend_events=[event],
        cash_target_buy=True,
        round_to_cents=True,
        cash_yield_annual_rate=0.03,
    )

    assert baseline.trades[0].quantity == 9_900
    assert stress.trades[0].quantity == 10_000
    assert stress.trades[0].quantity > baseline.trades[0].quantity

    with pytest.raises(ValueError, match="cash yield requires deferred next-session orders"):
        run_with_signals(
            config,
            source,
            calendar,
            initial_capital=100_000.0,
            cash_yield_annual_rate=0.03,
        )

    retry_path = run_with_signals(
        config,
        source,
        calendar,
        initial_capital=100_000.0,
        retry_temporarily_blocked_orders=True,
        round_to_cents=True,
        cash_yield_annual_rate=0.03,
    )
    assert Decimal(str(cash_at(retry_path, DATES[1]))) == Decimal("100008.22")
