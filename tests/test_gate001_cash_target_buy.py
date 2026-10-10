from datetime import date
from decimal import Decimal
from pathlib import Path
import unittest
from unittest.mock import patch

from contracts.stable import DailyBar, DailyStatus, Order, Signal, StrategyConfig
from strategy_core import backtest_engine, signals as signal_module
from strategy_core.fill_simulator import simulate_fill
from strategy_core.orders import generate_orders
from strategy_core.portfolio import Position, PortfolioState
from strategy_core.position_sizer import PositionSizer
from strategy_core.trading_calendar import TradingCalendar


class SyntheticExecutionSource:
    symbol = "600000.SH"

    def __init__(self):
        self.dates = [date(2025, 1, 2), date(2025, 1, 3), date(2025, 1, 6)]
        self.bars = {
            target_date: DailyBar(
                date=target_date,
                symbol=self.symbol,
                open=2000.0 if target_date == self.dates[0] else 10.123,
                high=2000.0 if target_date == self.dates[0] else 10.123,
                low=2000.0 if target_date == self.dates[0] else 10.123,
                close=2000.0 if target_date == self.dates[0] else 10.123,
                volume=100_000,
                amount=2_000_000.0 if target_date == self.dates[0] else 1_012_300.0,
                adj_factor=1.0,
            )
            for target_date in self.dates
        }
        self.statuses = {
            target_date: DailyStatus(
                date=target_date,
                symbol=self.symbol,
                is_st=False,
                is_suspended=False,
                is_limit_up=False,
                is_limit_down=False,
            )
            for target_date in self.dates
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


def make_config(source, max_position_per_stock=1.0, max_total_position=1.0):
    from strategy_core.dsl_parser import parse_strategy_config

    path = Path(__file__).parent / "golden_cases" / "strategy_config.yaml"
    values = parse_strategy_config(path).model_dump(mode="python")
    values["universe"]["symbols"] = [source.symbol]
    values["risk_filters"]["max_position_per_stock"] = max_position_per_stock
    values["risk_filters"]["max_total_position"] = max_total_position
    values["backtest_config"]["start_date"] = source.dates[0]
    values["backtest_config"]["end_date"] = source.dates[-1]
    values["backtest_config"]["sample_split"] = {
        "in_sample_end": source.dates[0],
        "out_of_sample_start": source.dates[1],
    }
    return StrategyConfig.model_validate(values)


def entry_signal(config, signal_date):
    return Signal(
        signal_id=f"synthetic-entry:{signal_date}",
        strategy_id=config.strategy_name,
        strategy_version=config.version,
        symbol=SyntheticExecutionSource.symbol,
        signal_date=signal_date,
        signal_type="entry",
        triggered_rules=["synthetic-entry"],
        audit_id=f"synthetic-entry:{signal_date}",
    )


class TestGate001CashTargetBuy(unittest.TestCase):
    def setUp(self):
        self.source = SyntheticExecutionSource()
        self.calendar = TradingCalendar(self.source)
        self.config = make_config(self.source)

    def _patch_one_entry(self):
        def entries(config, _source, trade_date, _universe):
            if trade_date == self.source.dates[0]:
                return [entry_signal(config, trade_date)]
            return []

        return (
            patch.object(backtest_engine, "generate_signals", side_effect=entries),
            patch.object(signal_module, "generate_exit_signals", return_value=[]),
        )

    def test_run_backtest_uses_execution_price_and_keeps_default_sizing_unchanged(self):
        entry_patch, exit_patch = self._patch_one_entry()
        with entry_patch, exit_patch:
            ordinary = backtest_engine.run_backtest(
                self.config, self.source, self.calendar, initial_capital=100_000.0
            )
            cash_target = backtest_engine.run_backtest(
                self.config,
                self.source,
                self.calendar,
                initial_capital=100_000.0,
                cash_target_buy=True,
            )

        self.assertEqual(ordinary.trades, [])
        self.assertEqual(ordinary.order_generation_events[0].event_type, "zero_quantity")
        self.assertEqual(len(cash_target.trades), 1)
        trade = cash_target.trades[0]
        self.assertEqual(trade.direction, "buy")
        self.assertEqual(trade.price, 10.123)
        self.assertEqual(trade.quantity, 9800)
        self.assertAlmostEqual(cash_target.daily_portfolio_values[-1].cash, 100_000.0 + trade.net_cash_flow)
        self.assertTrue(any("placeholder" in warning for warning in cash_target.warnings))

    def test_cash_target_preflight_rejects_conflicting_risk_caps(self):
        config = make_config(self.source, max_position_per_stock=0.2, max_total_position=1.0)
        with self.assertRaisesRegex(ValueError, "max_position_per_stock.*1.0"):
            backtest_engine.run_backtest(
                config,
                self.source,
                self.calendar,
                initial_capital=100_000.0,
                cash_target_buy=True,
            )

    def test_cash_target_order_intent_does_not_read_signal_close(self):
        signal = entry_signal(self.config, self.source.dates[0])

        class NoSignalCloseSource:
            def get_price(self, symbol, target_date):
                raise AssertionError("cash-target order generation must not use signal-date close")

        result = generate_orders(
            [signal],
            self.source.dates[1],
            NoSignalCloseSource(),
            PositionSizer(position_ratio=0.2),
            available_capital=100_000.0,
            current_positions={},
            cash_target_buy=True,
        )

        self.assertEqual(len(result.valid_orders), 1)
        order = result.valid_orders[0]
        self.assertEqual(order.quantity, 100)
        self.assertIn("cash-target", order.reason)
        self.assertIn("placeholder", order.reason)

    def test_cash_target_fill_uses_cash_execution_price_and_all_buy_fees(self):
        signal = entry_signal(self.config, self.source.dates[0])
        order = generate_orders(
            [signal],
            self.source.dates[1],
            self.source,
            PositionSizer(position_ratio=0.2),
            available_capital=100_000.0,
            current_positions={},
            cash_target_buy=True,
        ).valid_orders[0]
        portfolio = PortfolioState(cash=100_000.0)
        portfolio.positions["000001.SZ"] = Position(
            symbol="000001.SZ",
            quantity=100_000,
            sellable_quantity=100_000,
            avg_cost=10.0,
            last_price=100.0,
        )

        filled = simulate_fill(
            order,
            self.source.dates[1],
            self.source,
            portfolio,
            commission_rate=0.0003,
            min_commission=5.0,
            transfer_fee_rate=0.001,
            calendar=self.calendar,
            cash_target_buy=True,
        )

        self.assertEqual(filled.status, "filled")
        self.assertEqual(filled.actual_quantity, 9800)
        gross = filled.actual_quantity * filled.actual_price
        commission = max(gross * 0.0003, 5.0)
        transfer_fee = gross * 0.001
        self.assertAlmostEqual(portfolio.cash, 100_000.0 - gross - commission - transfer_fee)
        self.assertGreaterEqual(portfolio.cash, 0.0)
        next_lot_gross = (filled.actual_quantity + 100) * filled.actual_price
        self.assertGreater(next_lot_gross + max(next_lot_gross * 0.0003, 5.0) + next_lot_gross * 0.001, 100_000.0)

    def test_cent_settlement_round_trip_and_dividend_conserve_cash_and_trade_ledger(self):
        execution_price = 167.466
        extra_date = date(2025, 1, 7)
        self.source.dates.append(extra_date)
        self.source.bars[extra_date] = self.source.bars[self.source.dates[-2]].model_copy(
            update={"date": extra_date}
        )
        self.source.statuses[extra_date] = self.source.statuses[self.source.dates[-2]].model_copy(
            update={"date": extra_date}
        )
        self.calendar = TradingCalendar(self.source)
        config_values = self.config.model_dump(mode="python")
        config_values["backtest_config"]["end_date"] = extra_date
        self.config = StrategyConfig.model_validate(config_values)
        for target_date in self.source.dates[1:]:
            self.source.bars[target_date] = self.source.bars[target_date].model_copy(update={
                "open": execution_price,
                "high": execution_price,
                "low": execution_price,
                "close": execution_price,
                "amount": execution_price * 100_000,
            })

        config_values = self.config.model_dump(mode="python")
        config_values["fill_model"]["commission"] = 0.0003
        config_values["fill_model"]["stamp_tax"] = 0.0
        config = StrategyConfig.model_validate(config_values)

        def entries(current_config, _source, trade_date, _universe):
            return [entry_signal(current_config, trade_date)] if trade_date == self.source.dates[0] else []

        def exits(current_config, _source, trade_date, positions):
            if trade_date != self.source.dates[2] or self.source.symbol not in positions:
                return []
            return [Signal(
                signal_id=f"synthetic-exit:{trade_date}",
                strategy_id=current_config.strategy_name,
                strategy_version=current_config.version,
                symbol=self.source.symbol,
                signal_date=trade_date,
                signal_type="exit",
                triggered_rules=["synthetic-exit"],
                audit_id=f"synthetic-exit:{trade_date}",
            )]

        dividend = {
            "ts_code": self.source.symbol,
            "ann_date": "2025-01-01",
            "record_date": "2025-01-03",
            "ex_date": "2025-01-03",
            "pay_date": "2025-01-06",
            "div_cash": "0.005",
            "source_ref": "synthetic://fee-rounding-dividend",
        }
        with patch.object(backtest_engine, "generate_signals", side_effect=entries), \
             patch.object(signal_module, "generate_exit_signals", side_effect=exits):
            result = backtest_engine.run_backtest(
                config,
                self.source,
                self.calendar,
                initial_capital=16_751.62,
                dividend_events=[dividend],
                cash_target_buy=True,
                opening_capacity_mode=True,
                round_to_cents=True,
            )

        self.assertEqual([trade.direction for trade in result.trades], ["buy", "sell"])
        buy_trade, sell_trade = result.trades
        self.assertEqual((buy_trade.quantity, buy_trade.price), (100, execution_price))
        self.assertEqual((buy_trade.gross_amount, buy_trade.commission, buy_trade.total_fee), (16_746.60, 5.02, 5.02))
        self.assertEqual(buy_trade.net_cash_flow, -16_751.62)
        self.assertEqual((sell_trade.gross_amount, sell_trade.commission, sell_trade.total_fee), (16_746.60, 5.02, 5.02))
        self.assertEqual(sell_trade.net_cash_flow, 16_741.58)

        after_buy = next(value for value in result.daily_portfolio_values if value.date == self.source.dates[1])
        self.assertEqual(after_buy.cash, 0.0)
        self.assertEqual(after_buy.market_value, 16_746.60)
        self.assertEqual(after_buy.total_value, 16_747.10)
        dividend_paid_day = next(
            value for value in result.daily_portfolio_values if value.date == self.source.dates[2]
        )
        self.assertEqual(dividend_paid_day.cash, 0.50)
        self.assertEqual(dividend_paid_day.market_value, 16_746.60)
        self.assertEqual(dividend_paid_day.total_value, 16_747.10)
        final_value = result.daily_portfolio_values[-1]
        expected_cash = Decimal("16751.62") + Decimal(str(buy_trade.net_cash_flow))
        expected_cash += Decimal("0.50") + Decimal(str(sell_trade.net_cash_flow))
        self.assertEqual(Decimal(str(final_value.cash)), expected_cash)
        self.assertEqual(Decimal(str(final_value.total_value)), expected_cash)
        self.assertEqual(Decimal(str(result.final_capital)), expected_cash)

    def test_minimum_commission_ten_reaches_cent_rounded_double_cost_fill(self):
        execution_price = 16.658
        for target_date in self.source.dates[1:]:
            self.source.bars[target_date] = self.source.bars[target_date].model_copy(update={
                "open": execution_price,
                "high": execution_price,
                "low": execution_price,
                "close": execution_price,
                "amount": execution_price * 100_000,
            })
        config_values = self.config.model_dump(mode="python")
        config_values["fill_model"]["commission"] = 0.0006
        config_values["fill_model"]["stamp_tax"] = 0.0
        config = StrategyConfig.model_validate(config_values)

        entry_patch, exit_patch = self._patch_one_entry()
        with entry_patch, exit_patch:
            result = backtest_engine.run_backtest(
                config,
                self.source,
                self.calendar,
                initial_capital=16_668.00,
                cash_target_buy=True,
                opening_capacity_mode=True,
                round_to_cents=True,
                minimum_commission=10.0,
            )

        self.assertEqual(len(result.trades), 1)
        trade = result.trades[0]
        self.assertEqual((trade.quantity, trade.gross_amount), (1000, 16_658.0))
        self.assertEqual((trade.commission, trade.total_fee, trade.net_cash_flow), (10.0, 10.0, -16_668.0))
        after_buy = next(value for value in result.daily_portfolio_values if value.date == self.source.dates[1])
        self.assertEqual(after_buy.cash, 0.0)
        self.assertEqual(after_buy.market_value, 16_658.0)
        self.assertEqual(after_buy.total_value, 16_658.0)

    def test_cent_settlement_reduces_planned_buy_to_affordable_whole_lots(self):
        execution_price = 167.466
        target_date = self.source.dates[1]
        self.source.bars[target_date] = self.source.bars[target_date].model_copy(update={
            "open": execution_price,
            "high": execution_price,
            "low": execution_price,
            "close": execution_price,
            "amount": execution_price * 100_000,
        })
        order = Order(
            order_id="cent-affordability-buy",
            signal_id="cent-affordability-buy",
            signal_date=self.source.dates[0],
            intended_execution_date=target_date,
            symbol=self.source.symbol,
            direction="buy",
            quantity=200,
            reason="synthetic-affordability-boundary",
            strategy_version=self.config.version,
            audit_id="cent-affordability-buy",
        )
        portfolio = PortfolioState(cash=16_751.62)

        filled = simulate_fill(
            order,
            target_date,
            self.source,
            portfolio,
            commission_rate=0.0003,
            min_commission=5.0,
            stamp_duty_rate=0.0,
            calendar=self.calendar,
            round_to_cents=True,
        )

        self.assertEqual(filled.status, "filled")
        self.assertEqual(filled.actual_quantity, 100)
        self.assertEqual(portfolio.cash, 0.0)

    def test_minimum_commission_must_be_finite_and_nonnegative(self):
        for value in (-0.01, float("nan"), float("inf")):
            with self.subTest(minimum_commission=value):
                with self.assertRaisesRegex(ValueError, "minimum_commission"):
                    backtest_engine.run_backtest(
                        self.config,
                        self.source,
                        self.calendar,
                        minimum_commission=value,
                    )


if __name__ == "__main__":
    unittest.main()
