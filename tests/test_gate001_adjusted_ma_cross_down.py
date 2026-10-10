from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
import unittest

import yaml

from backend.services.backtest_time_cursor import BacktestTimeCursor, FutureDataAccessError
from contracts.stable import DailyBar
from strategy_core.cursor_bound_data_view import CursorBoundDataView
from strategy_core.dsl_parser import parse_strategy_config_dict
from strategy_core.signals import generate_signals
from strategy_core.validator import validate_strategy_config


SYMBOL = "510880.SH"
ANCHOR_DATE = date(2009, 1, 5)
RULE = {"type": "adjusted_ma_cross_down", "ma_period": 250}


class MemoryBarSource:
    def __init__(self, bars):
        self._bars = bars

    def get_daily_bars(self, symbol):
        return list(self._bars if symbol == SYMBOL else [])


def make_dates(count, start=ANCHOR_DATE):
    dates = []
    current = start
    while len(dates) < count:
        if current.weekday() < 5:
            dates.append(current)
        current += timedelta(days=1)
    return dates


def make_bars(adjusted_closes, dates, factors=None, anchor_factor=2.0):
    if factors is None:
        factors = [anchor_factor] * len(adjusted_closes)
    bars = []
    for day, adjusted_close, factor in zip(dates, adjusted_closes, factors, strict=True):
        raw_close = float(Decimal(str(adjusted_close)) * Decimal(str(anchor_factor)) / Decimal(str(factor)))
        bars.append(DailyBar(
            date=day,
            symbol=SYMBOL,
            open=raw_close,
            high=raw_close,
            low=raw_close,
            close=raw_close,
            volume=1000,
            amount=raw_close * 1000,
            adj_factor=factor,
        ))
    return bars


def make_config(entry_rules, exit_rules=None):
    path = Path(__file__).parent / "golden_cases" / "strategy_config.yaml"
    with path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    raw["universe"]["symbols"] = [SYMBOL]
    raw["entry_conditions"]["rules"] = entry_rules
    raw["exit_conditions"]["rules"] = exit_rules or []
    return parse_strategy_config_dict(raw)


def downcross_bars(dates, *, with_future=False):
    adjusted = [9.0] + [10.0] * 248 + [11.0, 9.0]
    factors = [2.0] * len(adjusted)
    factors[-1] = 1.5
    bars = make_bars(adjusted, dates[:251], factors)
    if with_future:
        future_date = dates[251]
        bars.extend(make_bars([0.1], [future_date], [2.0]))
    return bars


class TestGate001AdjustedMACrossDown(unittest.TestCase):
    def test_adjusted_downcross_uses_full_251_trading_bar_windows_and_anchor_factor(self):
        dates = make_dates(252)
        trade_date = dates[250]
        config = make_config([RULE])
        validate_strategy_config(config)
        source = MemoryBarSource(downcross_bars(dates, with_future=True))

        signals = generate_signals(config, source, trade_date, [SYMBOL])

        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].signal_date, trade_date)
        self.assertEqual(signals[0].triggered_rules, ["adjusted_ma_cross_down:close<ma_250"])

    def test_equality_on_either_side_of_cross_does_not_trigger(self):
        dates = make_dates(251)
        config = make_config([RULE])
        cases = {
            "previous_close_equals_previous_ma": [10.0] * 250 + [9.0],
            "current_close_equals_current_ma": [9.0] + [10.0] * 250,
        }

        for case_name, adjusted in cases.items():
            with self.subTest(case=case_name):
                source = MemoryBarSource(make_bars(adjusted, dates))
                self.assertEqual(generate_signals(config, source, dates[-1], [SYMBOL]), [])

    def test_history_shorter_than_251_bars_does_not_shrink_the_ma_window(self):
        dates = make_dates(250)
        config = make_config([RULE])
        source = MemoryBarSource(make_bars([9.0] + [10.0] * 248 + [9.0], dates))

        self.assertEqual(generate_signals(config, source, dates[-1], [SYMBOL]), [])

    def test_missing_adjustment_anchor_fails_loudly(self):
        dates = make_dates(251, start=ANCHOR_DATE + timedelta(days=1))
        config = make_config([RULE])
        source = MemoryBarSource(downcross_bars(dates))

        with self.assertRaisesRegex(ValueError, "2009-01-05 adjustment anchor"):
            generate_signals(config, source, dates[-1], [SYMBOL])

    def test_cursor_path_uses_actual_dates_and_reads_no_future_bar_values(self):
        dates = make_dates(252)
        trade_date = dates[250]
        config = make_config([RULE])
        raw_source = MemoryBarSource(downcross_bars(dates, with_future=True))
        cursor = BacktestTimeCursor(
            cursor_id="adjusted-ma-test",
            current_date=trade_date,
            evaluation_mode="signal_phase",
        )
        data_view = CursorBoundDataView(raw_source, cursor)

        signals = generate_signals(config, data_view, trade_date, [SYMBOL])

        self.assertEqual(len(signals), 1)
        read_dates = [
            date.fromisoformat(trace.split(":")[2])
            for trace in cursor.read_trace
            if trace.startswith(("bar:", "bar_dates:"))
        ]
        self.assertTrue(read_dates)
        self.assertLessEqual(max(read_dates), trade_date)
        self.assertTrue(any(trace.startswith(f"bar_dates:{SYMBOL}:{trade_date}") for trace in cursor.read_trace))
        with self.assertRaises(FutureDataAccessError):
            data_view.get_bar_dates_until(SYMBOL, dates[251])

    def test_cursor_path_without_trading_date_getter_fails_loudly(self):
        class IncompleteCursorSource:
            def get_bar(self, _symbol, _day):
                return None

        config = make_config([RULE])

        with self.assertRaisesRegex(NotImplementedError, "cursor trading-date lookup"):
            generate_signals(config, IncompleteCursorSource(), ANCHOR_DATE, [SYMBOL])

    def test_validator_freezes_ma_period_and_restricts_rule_to_entry(self):
        invalid_period = make_config([{"type": RULE["type"], "ma_period": 249}])
        exit_only = make_config([], exit_rules=[RULE])
        extra_parameter = make_config([dict(RULE, operator="<")])

        with self.assertRaisesRegex(ValueError, "fixed at 250"):
            validate_strategy_config(invalid_period)
        with self.assertRaisesRegex(ValueError, "entry-only"):
            validate_strategy_config(exit_only)
        with self.assertRaisesRegex(ValueError, "only supports type and ma_period"):
            validate_strategy_config(extra_parameter)


if __name__ == "__main__":
    unittest.main()
