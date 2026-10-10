from datetime import date
from pathlib import Path
import inspect
import unittest
from unittest.mock import patch

from contracts.stable import DailyBar, DailyStatus, Signal, StrategyConfig
from strategy_core import backtest_engine, signals as signal_module
from strategy_core.trading_calendar import TradingCalendar


class SyntheticRetrySource:
    symbol = "600000.SH"

    def __init__(self, dates, price_by_date=None):
        self.dates = list(dates)
        price_by_date = price_by_date or {}
        self.bars = {
            day: DailyBar(
                date=day,
                symbol=self.symbol,
                open=price_by_date.get(day, 10.0),
                high=price_by_date.get(day, 10.0),
                low=price_by_date.get(day, 10.0),
                close=price_by_date.get(day, 10.0),
                volume=1_000_000,
                amount=10_000_000.0,
                adj_factor=1.0,
            )
            for day in self.dates
        }
        self.statuses = {
            day: DailyStatus(
                date=day,
                symbol=self.symbol,
                is_st=False,
                is_suspended=False,
                is_limit_up=False,
                is_limit_down=False,
            )
            for day in self.dates
        }

    def symbols(self):
        return [self.symbol]

    def get_daily_bars(self, symbol):
        self._assert_symbol(symbol)
        return list(self.bars.values())

    def get_daily_bar(self, symbol, target_date):
        self._assert_symbol(symbol)
        return self.bars[target_date]

    def get_daily_status(self, symbol, target_date):
        self._assert_symbol(symbol)
        return self.statuses[target_date]

    def get_price(self, symbol, target_date):
        return self.get_daily_bar(symbol, target_date).close

    @classmethod
    def _assert_symbol(cls, symbol):
        if symbol != cls.symbol:
            raise KeyError(symbol)


def make_config(source):
    from strategy_core.dsl_parser import parse_strategy_config

    path = Path(__file__).parent / "golden_cases" / "strategy_config.yaml"
    values = parse_strategy_config(path).model_dump(mode="python")
    values["universe"]["symbols"] = [source.symbol]
    values["risk_filters"]["max_position_per_stock"] = 1.0
    values["risk_filters"]["max_total_position"] = 1.0
    values["backtest_config"]["start_date"] = source.dates[0]
    values["backtest_config"]["end_date"] = source.dates[-1]
    values["backtest_config"]["sample_split"] = {
        "in_sample_end": source.dates[0],
        "out_of_sample_start": source.dates[1],
    }
    return StrategyConfig.model_validate(values)


def make_signal(config, signal_date, direction="entry", variant=0):
    signal_key = f"synthetic-{direction}:{signal_date}"
    if variant:
        signal_key = f"{signal_key}:{variant}"
    return Signal(
        signal_id=signal_key,
        strategy_id=config.strategy_name,
        strategy_version=config.version,
        symbol=SyntheticRetrySource.symbol,
        signal_date=signal_date,
        signal_type=direction,
        triggered_rules=[f"synthetic-{direction}"],
        audit_id=signal_key,
    )


class TestGate001PendingOrderRetries(unittest.TestCase):
    def setUp(self):
        self.dates = [
            date(2025, 1, 2),
            date(2025, 1, 3),
            date(2025, 1, 6),
            date(2025, 1, 7),
            date(2025, 1, 8),
        ]
        self.source = SyntheticRetrySource(self.dates)
        self.calendar = TradingCalendar(self.source)
        self.config = make_config(self.source)

    def _run_with_signals(self, entries, exits=None, initial_capital=100_000.0, **kwargs):
        exits = exits or {}

        def entry_provider(config, _source, day, _universe):
            matching_dates = [entry_day for entry_day in entries if entry_day == day]
            return [
                make_signal(config, day, "entry", variant=index)
                for index, _entry_day in enumerate(matching_dates)
            ]

        def exit_provider(config, _source, day, _positions):
            return [make_signal(config, day, "exit")] if day in exits else []

        with patch.object(backtest_engine, "generate_signals", side_effect=entry_provider), \
             patch.object(signal_module, "generate_exit_signals", side_effect=exit_provider):
            return backtest_engine.run_backtest(
                self.config,
                self.source,
                self.calendar,
                initial_capital=initial_capital,
                **kwargs,
            )

    def test_retry_flag_is_keyword_only_and_off_by_default(self):
        parameter = inspect.signature(backtest_engine.run_backtest).parameters.get(
            "retry_temporarily_blocked_orders"
        )
        self.assertIsNotNone(parameter)
        self.assertEqual(parameter.kind, inspect.Parameter.KEYWORD_ONLY)
        self.assertIs(parameter.default, False)

    def test_buy_retries_only_temporary_blocks_and_preserves_original_intent(self):
        self.source.statuses[self.dates[1]] = self.source.statuses[self.dates[1]].model_copy(
            update={"is_limit_up": True}
        )
        self.source.statuses[self.dates[2]] = self.source.statuses[self.dates[2]].model_copy(
            update={"is_suspended": True}
        )
        retry_price = 10.123
        self.source.bars[self.dates[3]] = self.source.bars[self.dates[3]].model_copy(
            update={"open": retry_price, "high": retry_price, "low": retry_price,
                    "close": retry_price, "amount": retry_price * 1_000_000}
        )

        result = self._run_with_signals(
            {self.dates[0]},
            retry_temporarily_blocked_orders=True,
            cash_target_buy=True,
        )

        self.assertEqual(len(result.trades), 1)
        trade = result.trades[0]
        self.assertEqual(trade.direction, "buy")
        self.assertEqual(trade.trade_date, self.dates[3])
        self.assertEqual(trade.price, retry_price)
        self.assertEqual(trade.order_id, f"order:synthetic-entry:{self.dates[0]}:{self.dates[1]}")
        self.assertEqual(trade.quantity, 9_800)
        retry_audits = [warning for warning in result.warnings if "pending_order_retry" in warning]
        self.assertEqual(len(retry_audits), 2)
        self.assertIn(str(self.dates[1]), retry_audits[0])
        self.assertIn("limit_up", retry_audits[0])
        self.assertIn(str(self.dates[2]), retry_audits[1])
        self.assertIn("suspended", retry_audits[1])
        self.assertEqual(result.buy_order_count, 1)
        self.assertEqual(result.buy_fill_count, 1)
        for blocked_day in self.dates[1:3]:
            daily_value = next(
                value for value in result.daily_portfolio_values
                if value.date == blocked_day
            )
            self.assertEqual(daily_value.cash, 100_000.0)
        fill_day_value = next(
            value for value in result.daily_portfolio_values
            if value.date == self.dates[3]
        )
        self.assertAlmostEqual(fill_day_value.cash, 100_000.0 + trade.net_cash_flow)

    def test_sell_retry_waits_for_t1_unlock_and_suppresses_duplicate_exit_intents(self):
        self.source.statuses[self.dates[3]] = self.source.statuses[self.dates[3]].model_copy(
            update={"is_limit_down": True}
        )

        result = self._run_with_signals(
            {self.dates[0]},
            exits={self.dates[2], self.dates[3]},
            retry_temporarily_blocked_orders=True,
        )

        self.assertEqual([trade.direction for trade in result.trades], ["buy", "sell"])
        buy, sell = result.trades
        self.assertEqual(buy.trade_date, self.dates[1])
        self.assertEqual(sell.trade_date, self.dates[4])
        self.assertEqual(sell.order_id, f"order:synthetic-exit:{self.dates[2]}:{self.dates[3]}")
        self.assertEqual(result.sell_order_count, 1)
        self.assertEqual(result.sell_fill_count, 1)
        self.assertTrue(any(str(self.dates[3]) in warning and "limit_down" in warning
                            for warning in result.warnings if "pending_order_retry" in warning))

    def test_pending_buy_does_not_create_duplicate_entry_while_blocked(self):
        self.source.statuses[self.dates[1]] = self.source.statuses[self.dates[1]].model_copy(
            update={"is_limit_up": True}
        )

        result = self._run_with_signals(
            {self.dates[0], self.dates[1]},
            retry_temporarily_blocked_orders=True,
        )

        self.assertEqual(len(result.trades), 1)
        self.assertEqual(result.trades[0].trade_date, self.dates[2])
        self.assertEqual(result.trades[0].order_id, f"order:synthetic-entry:{self.dates[0]}:{self.dates[1]}")
        self.assertEqual(result.buy_order_count, 1)

    def test_multiple_same_day_entry_signals_create_one_pending_buy(self):
        result = self._run_with_signals(
            [self.dates[0], self.dates[0]],
            retry_temporarily_blocked_orders=True,
        )

        self.assertEqual(len(result.trades), 1)
        self.assertEqual(result.buy_order_count, 1)
        self.assertTrue(any("pending_order_duplicate_suppressed" in warning
                            for warning in result.warnings))

    def test_non_temporary_rejection_is_not_retried(self):
        cheap_close = 0.2
        self.source.bars[self.dates[0]] = self.source.bars[self.dates[0]].model_copy(
            update={"open": cheap_close, "high": cheap_close, "low": cheap_close,
                    "close": cheap_close, "amount": 200_000.0}
        )
        expensive_open = 2.0
        self.source.bars[self.dates[1]] = self.source.bars[self.dates[1]].model_copy(
            update={"open": expensive_open, "high": expensive_open, "low": expensive_open,
                    "close": expensive_open, "amount": 2_000_000.0}
        )

        result = self._run_with_signals(
            {self.dates[0]},
            retry_temporarily_blocked_orders=True,
            initial_capital=100.0,
        )

        self.assertEqual(result.trades, [])
        self.assertEqual(len(result.rejected_orders), 1)
        self.assertEqual(result.rejected_orders[0].rejection_reason, "insufficient_capital")
        self.assertFalse(any("pending_order_retry" in warning for warning in result.warnings))

    def test_final_temporary_block_is_canceled_with_attempt_audit(self):
        self.config.backtest_config.end_date = self.dates[1]
        self.source.statuses[self.dates[1]] = self.source.statuses[self.dates[1]].model_copy(
            update={"is_limit_up": True}
        )

        result = self._run_with_signals(
            {self.dates[0]},
            retry_temporarily_blocked_orders=True,
        )

        self.assertEqual(result.trades, [])
        self.assertEqual(len(result.rejected_orders), 1)
        rejected = result.rejected_orders[0]
        self.assertEqual(rejected.rejection_reason,
                         "canceled_at_research_end_after_1_blocked_attempts")
        self.assertEqual(rejected.signal_date, self.dates[0])
        self.assertEqual(rejected.intended_execution_date, self.dates[1])
        self.assertTrue(any("pending_order_retry" in warning and "limit_up" in warning
                            for warning in result.warnings))

    def test_retry_mode_records_the_final_research_session_even_when_it_has_signals(self):
        self.config.backtest_config.end_date = self.dates[1]
        self.source.statuses[self.dates[1]] = self.source.statuses[self.dates[1]].model_copy(
            update={"is_limit_up": True}
        )

        result = self._run_with_signals(
            {self.dates[0]},
            exits={self.dates[1]},
            retry_temporarily_blocked_orders=True,
        )

        self.assertEqual(result.daily_portfolio_values[-1].date, self.dates[1])

    def test_default_mode_still_rejects_after_one_attempt(self):
        self.source.statuses[self.dates[1]] = self.source.statuses[self.dates[1]].model_copy(
            update={"is_limit_up": True}
        )

        result = self._run_with_signals({self.dates[0]})

        self.assertEqual(result.trades, [])
        self.assertEqual(len(result.rejected_orders), 1)
        self.assertEqual(result.rejected_orders[0].rejection_reason, "limit_up")
        self.assertFalse(any("pending_order_retry" in warning for warning in result.warnings))


if __name__ == "__main__":
    unittest.main()
