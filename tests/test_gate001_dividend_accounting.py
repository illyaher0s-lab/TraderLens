from datetime import date, timedelta
from decimal import Decimal

import pytest

from contracts.stable import DailyBar, DailyStatus, Signal, StrategyConfig
from strategy_core.backtest_engine import run_backtest
from strategy_core.dividend_ledger import DividendLedger
from strategy_core.gate001_dividend_adapter import (
    _verify_sha256,
    load_gate001_dividend_snapshot,
)
from strategy_core.portfolio import Position, PortfolioState
from strategy_core.trading_calendar import TradingCalendar


SYMBOL = "600000.SH"


def event(**updates):
    value = {
        "ts_code": SYMBOL,
        "ann_date": "2025-01-01",
        "record_date": "2025-01-02",
        "ex_date": "2025-01-03",
        "pay_date": "2025-01-05",
        "div_cash": "0.005",
        "source_ref": "synthetic://dividend/plan-1",
    }
    value.update(updates)
    return value


def test_ledger_deduplicates_and_keeps_all_source_refs():
    ledger = DividendLedger([
        event(),
        event(source_ref="synthetic://second-copy"),
    ])

    assert len(ledger.events) == 1
    assert ledger.events[0].source_refs == (
        "synthetic://dividend/plan-1",
        "synthetic://second-copy",
    )


@pytest.mark.parametrize(
    "events",
    [
        [event(), event(div_cash="0.006", source_ref="synthetic://conflict")],
        [event(), event(record_date="2025-01-04", source_ref="synthetic://date-conflict")],
        [event(record_date=None)],
        [event(div_cash="NaN")],
        [event(div_cash="-0.01")],
    ],
)
def test_ledger_rejects_conflicting_or_invalid_events(events):
    with pytest.raises(ValueError):
        DividendLedger(events)


def test_record_date_entitlement_survives_later_sale_and_rounds_half_up():
    ledger = DividendLedger([event()])
    portfolio = PortfolioState(cash=Decimal("10.00"))
    portfolio.positions[SYMBOL] = Position(
        symbol=SYMBOL,
        quantity=1,
        sellable_quantity=1,
        avg_cost=1.0,
        last_price=1.0,
    )

    ledger.process_eod(date(2025, 1, 2), portfolio)
    del portfolio.positions[SYMBOL]
    ledger.process_eod(date(2025, 1, 3), portfolio)

    assert portfolio.cash == 10.0
    assert ledger.total_receivable() == Decimal("0.01")
    assert ledger.total_value(portfolio) == Decimal("10.01")

    ledger.settle_due_at_open(date(2025, 1, 6), portfolio)

    assert Decimal(str(portfolio.cash)) == Decimal("10.01")
    assert ledger.total_receivable() == Decimal("0.00")


def test_shares_bought_after_record_date_do_not_receive_dividend():
    ledger = DividendLedger([event(div_cash="1.00")])
    portfolio = PortfolioState(cash=0.0)

    ledger.process_eod(date(2025, 1, 2), portfolio)
    portfolio.positions[SYMBOL] = Position(
        symbol=SYMBOL,
        quantity=100,
        sellable_quantity=100,
        avg_cost=10.0,
        last_price=10.0,
    )
    ledger.process_eod(date(2025, 1, 3), portfolio)

    assert ledger.total_receivable() == Decimal("0.00")


class SyntheticSource:
    def __init__(self, dates, symbol=SYMBOL):
        self.symbol = symbol
        self.bars = {
            d: DailyBar(
                date=d,
                symbol=self.symbol,
                open=11.0 if d == dates[3] else 10.0,
                high=12.0,
                low=9.0,
                close=9.5 if d == dates[2] else 10.0,
                volume=1_000_000,
                amount=10_000_000.0,
                adj_factor=1.0,
            )
            for d in dates
        }
        self.statuses = {
            d: DailyStatus(
                date=d,
                symbol=self.symbol,
                is_st=False,
                is_suspended=False,
                is_limit_up=False,
                is_limit_down=False,
            )
            for d in dates
        }

    def symbols(self):
        return [self.symbol]

    def get_daily_bars(self, symbol):
        return list(self.bars.values())

    def get_daily_bar(self, symbol, target_date):
        return self.bars[target_date]

    def get_daily_status(self, symbol, target_date):
        return self.statuses[target_date]

    def get_price(self, symbol, target_date):
        return self.bars[target_date].close


def config_for(dates, symbol=SYMBOL):
    return StrategyConfig.model_validate(
        {
            "strategy_name": "synthetic-dividend-test",
            "version": "test",
            "status": "draft",
            "hypothesis_source_snapshot": {
                "source_type": "user",
                "source_run_id": "synthetic",
                "generated_at": "2025-01-01T00:00:00",
                "data_range_used_for_generation": {
                    "start": dates[0].isoformat(),
                    "end": dates[-1].isoformat(),
                },
            },
            "universe": {"type": "static_list", "symbols": [symbol]},
            "entry_conditions": {"logic": "AND", "rules": []},
            "exit_conditions": {"logic": "OR", "rules": []},
            "risk_filters": {
                "max_position_per_stock": 0.2,
                "max_total_position": 0.8,
                "restrict_limit_up_buy": True,
                "restrict_limit_down_sell": True,
                "restrict_suspended": True,
                "min_liquidity_for_trade": 0,
            },
            "rebalance": {"frequency": "daily", "check_time": "close"},
            "fill_model": {
                "signal_to_execution": "T+1",
                "execution_price": "open",
                "commission": 0.0003,
                "stamp_tax": 0.001,
                "slippage": 0.0,
                "lot_size": 100,
                "lot_rounding": "floor",
                "handling": {
                    "limit_up_buy": "skip",
                    "limit_down_sell": "skip",
                    "suspended": "skip",
                },
            },
            "backtest_config": {
                "initial_capital": 100000,
                "start_date": dates[0].isoformat(),
                "end_date": dates[3].isoformat(),
                "sample_split": {
                    "in_sample_end": dates[1].isoformat(),
                    "out_of_sample_start": dates[2].isoformat(),
                },
                "benchmark": {"type": "index", "code": "SYNTH", "name": "Synthetic"},
                "data_source": "synthetic_test_only",
                "include_delisted": "none",
            },
            "audit": {
                "created_at": "2025-01-01T00:00:00",
                "created_by": "test",
                "last_modified_at": "2025-01-01T00:00:00",
                "config_hash": "synthetic",
            },
        }
    )


def test_run_backtest_processes_dividends_in_the_trading_loop(monkeypatch):
    from strategy_core import backtest_engine

    dates = [date(2025, 1, 2) + timedelta(days=i) for i in range(5)]
    source = SyntheticSource(dates)
    calendar = TradingCalendar(source)
    config = config_for(dates)
    signal_dates = set(dates[:4])

    def synthetic_signals(config, data_source, trade_date, universe):
        if trade_date not in signal_dates:
            return []
        return [
            Signal(
                signal_id=f"synthetic:{trade_date}",
                strategy_id=config.strategy_name,
                strategy_version=config.version,
                symbol=SYMBOL,
                signal_date=trade_date,
                signal_type="entry",
                triggered_rules=["synthetic-entry"],
                audit_id=f"synthetic:{trade_date}",
            )
        ]

    original_simulate_fill = backtest_engine.simulate_fill
    cash_at_fill = {}
    cash_after_fill = {}

    def capture_fill(order, execution_date, data_source, portfolio, **kwargs):
        cash_at_fill[execution_date] = portfolio.cash
        filled = original_simulate_fill(
            order, execution_date, data_source, portfolio, **kwargs
        )
        cash_after_fill[execution_date] = portfolio.cash
        return filled

    monkeypatch.setattr(backtest_engine, "generate_signals", synthetic_signals)
    monkeypatch.setattr(backtest_engine, "simulate_fill", capture_fill)

    result = run_backtest(
        config,
        source,
        calendar,
        initial_capital=100000.0,
        dividend_events=[
            event(
                ann_date=dates[0].isoformat(),
                record_date=dates[1].isoformat(),
                ex_date=dates[2].isoformat(),
                pay_date=dates[2].isoformat(),
                div_cash="0.50",
            )
        ],
    )

    daily_by_date = {v.date: v for v in result.daily_portfolio_values}
    dividend_credit = Decimal("0.50") * Decimal("2000")

    assert cash_after_fill[dates[2]] - cash_at_fill[dates[2]] < 0
    assert Decimal(str(daily_by_date[dates[2]].cash)) == (
        Decimal(str(cash_after_fill[dates[2]])) + dividend_credit
    )
    assert cash_at_fill[dates[2]] == cash_after_fill[dates[1]]
    assert cash_at_fill[dates[3]] == daily_by_date[dates[2]].cash
    assert daily_by_date[dates[2]].market_value == pytest.approx(3500 * 9.5)
    assert any("synthetic://dividend/plan-1" in w for w in result.warnings)

    no_events_by_default = run_backtest(config, source, calendar, initial_capital=100000.0)
    no_events_explicit = run_backtest(
        config, source, calendar, initial_capital=100000.0, dividend_events=[]
    )
    assert no_events_by_default.model_dump() == no_events_explicit.model_dump()

    unpaid_result = run_backtest(
        config,
        source,
        calendar,
        initial_capital=100000.0,
        dividend_events=[
            event(
                ann_date=dates[0].isoformat(),
                record_date=dates[1].isoformat(),
                ex_date=dates[2].isoformat(),
                pay_date="2025-01-20",
                div_cash="0.50",
            )
        ],
    )
    last_day = next(
        value for value in reversed(unpaid_result.daily_portfolio_values)
        if value.date == dates[3]
    )
    assert last_day.total_value - last_day.cash - last_day.market_value == pytest.approx(1000.0)
    assert unpaid_result.final_capital == pytest.approx(last_day.total_value)


def test_gate001_snapshot_maps_20_raw_rows_to_13_ledger_events_and_keeps_provenance():
    snapshot = load_gate001_dividend_snapshot()
    ledger = DividendLedger(snapshot.events)

    assert snapshot.snapshot_id == "fund_div_announcements_20261005T004106Z"
    assert snapshot.ann_date_window == (date(2009, 1, 1), date(2020, 12, 31))
    assert snapshot.target_raw_rows == 20
    assert len(snapshot.events) == 20
    assert len(ledger.events) == 13
    assert snapshot.duplicate_rows == 7
    assert len(snapshot.raw_file_hashes) == 13
    assert all(len(event.source_refs) >= 1 for event in ledger.events)
    assert sum(len(event.source_refs) for event in ledger.events) == 20
    assert all("manifest_sha256=" in ref and "sha256=" in ref and "row=" in ref
               for event in ledger.events for ref in event.source_refs)

    events_by_announcement = {event.ann_date: event for event in ledger.events}
    event_2019 = events_by_announcement[date(2019, 1, 10)]
    assert event_2019.div_cash == Decimal("0.098")
    assert (event_2019.record_date, event_2019.ex_date, event_2019.pay_date) == (
        date(2019, 1, 15), date(2019, 1, 16), date(2019, 1, 21)
    )
    event_2020 = events_by_announcement[date(2020, 1, 13)]
    assert event_2020.div_cash == Decimal("0.144")
    assert (event_2020.record_date, event_2020.ex_date, event_2020.pay_date) == (
        date(2020, 1, 16), date(2020, 1, 17), date(2020, 1, 22)
    )
    assert snapshot.official_spotcheck_dates == (
        date(2019, 1, 10), date(2020, 1, 13)
    )
    assert "do not establish full-history completeness" in snapshot.evidence_gap.lower()


def test_gate001_snapshot_conflicting_raw_economic_key_is_rejected():
    events = list(load_gate001_dividend_snapshot().events)
    duplicate_indices = [
        index for index, event in enumerate(events)
        if event["ann_date"] == "2019-01-10"
    ]
    assert len(duplicate_indices) == 2
    conflicting = dict(events[duplicate_indices[1]])
    conflicting["div_cash"] = "0.099"
    events[duplicate_indices[1]] = conflicting

    with pytest.raises(ValueError, match="conflicting dividend event"):
        DividendLedger(events)


def test_gate001_snapshot_loader_rejects_a_bad_hash(tmp_path):
    raw_path = tmp_path / "raw.json"
    raw_path.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        _verify_sha256(raw_path, "0" * 64, "synthetic raw row")


def test_real_gate001_dividend_events_flow_through_ordinary_loop_with_synthetic_account(monkeypatch):
    """Real dividend event + synthetic prices/account; this is not a historical backtest."""
    from strategy_core import backtest_engine

    snapshot = load_gate001_dividend_snapshot()
    symbol = "510880.SH"
    dates = [date(2019, 1, 14) + timedelta(days=i) for i in range(4)]
    source = SyntheticSource(dates, symbol=symbol)
    calendar = TradingCalendar(source)
    config = config_for(dates, symbol=symbol)

    def synthetic_signals(config, data_source, trade_date, universe):
        if trade_date != dates[0]:
            return []
        return [Signal(
            signal_id="synthetic:record-date-entry",
            strategy_id=config.strategy_name,
            strategy_version=config.version,
            symbol=symbol,
            signal_date=trade_date,
            signal_type="entry",
            triggered_rules=["synthetic-entry"],
            audit_id="synthetic:record-date-entry",
        )]

    monkeypatch.setattr(backtest_engine, "generate_signals", synthetic_signals)
    result = run_backtest(
        config,
        source,
        calendar,
        initial_capital=100000.0,
        dividend_events=list(snapshot.events),
    )

    ex_day = next(value for value in result.daily_portfolio_values if value.date == date(2019, 1, 16))
    assert ex_day.cash == pytest.approx(79994.0)
    assert ex_day.market_value == pytest.approx(2000 * 9.5)
    assert ex_day.total_value == pytest.approx(ex_day.cash + ex_day.market_value + 196.0)
    assert result.final_capital == pytest.approx(result.daily_portfolio_values[-1].total_value)
    assert any("20190110.json" in warning for warning in result.warnings)
