from dataclasses import dataclass, field
from datetime import date, timedelta
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from contracts.stable import DailyBar, DailyStatus
from strategy_core.v3_relative_strength_executor import (
    V3RelativeStrengthExecutionSpec,
    _CursorBoundV3DataSource,
    _V3Calendar,
    _entry_symbols,
    _exit_symbols,
    _mark_position_prices,
    _rank_snapshot,
    adjusted_momentum,
    execution_schedule,
    rank_candidates,
    run_v3_relative_strength_backtest,
)
from backend.services.backtest_time_cursor import BacktestTimeCursor, FutureDataAccessError


REVISION_ID = "6440ffc03a742f4d4632078481cf3abf171eafb1a24f2bc69bc6f352d1b19ebc"
REPO_ROOT = Path(__file__).parent.parent


@dataclass
class FakeV3Data:
    dates: tuple[date, ...]
    bars: dict[str, dict[date, DailyBar]]
    blocked_dates: set[date]
    suspended_symbols: set[str] = field(default_factory=set)

    def symbols_as_of(self, as_of: date) -> tuple[str, ...]:
        return tuple(sorted(self.bars))

    def common_trading_dates(self, start: date, end: date) -> tuple[date, ...]:
        return tuple(day for day in self.dates if start <= day <= end)

    def get_daily_bars(self, symbol: str, end: date, n: int) -> tuple[DailyBar, ...]:
        dates = [day for day in self.dates if day <= end]
        if len(dates) < n:
            raise ValueError("insufficient bars")
        return tuple(self.bars[symbol][day] for day in dates[-n:])

    def get_bar(self, symbol: str, day: date) -> DailyBar:
        return self.bars[symbol][day]

    def get_daily_bar(self, symbol: str, day: date) -> DailyBar:
        return self.get_bar(symbol, day)

    def get_status(self, symbol: str, day: date) -> DailyStatus:
        return DailyStatus(
            date=day, symbol=symbol, is_st=False, is_suspended=symbol in self.suspended_symbols,
            is_limit_up=False, is_limit_down=False,
        )

    def get_daily_status(self, symbol: str, day: date) -> DailyStatus:
        return self.get_status(symbol, day)

    def derive_liquidity(self, symbol: str, execution_day: date) -> dict[str, object]:
        return {"status": "qualified", "average_amount_yuan": 60_000_000.0}

    def market_regime_blocked(self, as_of: date) -> bool:
        return as_of in self.blocked_dates


def _data(symbols: tuple[str, ...] = ("000001.SZ", "000002.SZ", "000003.SZ")) -> FakeV3Data:
    start = date(2024, 1, 1)
    dates = tuple(start + timedelta(days=i) for i in range(280))
    bars = {}
    for index, symbol in enumerate(symbols):
        by_day = {}
        for day_index, day in enumerate(dates):
            close = 100.0 + day_index * (index + 1)
            by_day[day] = DailyBar(
                date=day, symbol=symbol, open=close, high=close + 1,
                low=close - 1, close=close, volume=1_000_000,
                amount=100_000.0, adj_factor=1.0,
            )
        bars[symbol] = by_day
    return FakeV3Data(dates=dates, bars=bars, blocked_dates=set())


def test_execution_spec_is_frozen_and_schedule_uses_previous_common_day() -> None:
    data = _data()
    start = date(2024, 9, 1)
    schedule = execution_schedule(data.dates, start, date(2024, 9, 15))
    assert schedule
    assert all(execution > as_of for execution, as_of in schedule)
    assert schedule[0][1] in data.dates
    assert all(execution.isocalendar()[:2] != previous.isocalendar()[:2] for (execution, _), (previous, _) in zip(schedule[1:], schedule))
    spec = V3RelativeStrengthExecutionSpec(
        strategy_revision_id=REVISION_ID,
        protocol_snapshot_id="6f7cbdcdeb26f8cdd2611a5450dbab3ff22544b6a66ec8539f5cab9151329111",
        data_snapshot_hash="snapshot-hash",
        supplement_id="supplement-id",
        backtest_start=start,
        backtest_end=date(2024, 9, 15),
    )
    with pytest.raises(Exception):
        spec.backtest_start = date(2024, 9, 2)


def test_adjusted_momentum_and_rank_tie_break_are_deterministic() -> None:
    data = _data(("000002.SZ", "000001.SZ"))
    as_of = data.dates[-1]
    assert adjusted_momentum(data, "000001.SZ", as_of) == pytest.approx(
        data.bars["000001.SZ"][as_of].close / data.bars["000001.SZ"][data.dates[-253]].close - 1
    )
    ranked = rank_candidates({"000002.SZ": 0.1, "000001.SZ": 0.1, "000003.SZ": 0.05})
    assert ranked == [("000001.SZ", 0.1, 1), ("000002.SZ", 0.1, 2), ("000003.SZ", 0.05, 3)]


def test_adjusted_momentum_reads_only_the_two_frozen_endpoints() -> None:
    data = _data(("000001.SZ",))
    as_of = data.dates[-1]

    class EndpointProbe:
        def __init__(self, source):
            self.source = source
            self.bar_calls = []

        def common_trading_dates(self, start, end):
            return self.source.common_trading_dates(start, end)

        def get_bar(self, symbol, day):
            self.bar_calls.append((symbol, day))
            return self.source.get_bar(symbol, day)

        def get_daily_bars(self, symbol, end, n):
            raise AssertionError("momentum must not read a bulk bar window")

    probe = EndpointProbe(data)
    value = adjusted_momentum(probe, "000001.SZ", as_of)

    assert probe.bar_calls == [("000001.SZ", data.dates[-253]), ("000001.SZ", as_of)]
    assert value == pytest.approx(
        data.bars["000001.SZ"][as_of].close / data.bars["000001.SZ"][data.dates[-253]].close - 1
    )


def test_rank_snapshot_computes_common_endpoints_once_for_all_symbols() -> None:
    symbols = tuple(f"{index:06d}.SZ" for index in range(1, 13))
    data = _data(symbols)

    class CountingSource:
        def __init__(self, source):
            self.source = source
            self.common_calls = 0
            self.bar_calls = []

        def symbols_as_of(self, as_of):
            return self.source.symbols_as_of(as_of)

        def common_trading_dates(self, start, end):
            self.common_calls += 1
            return self.source.common_trading_dates(start, end)

        def get_bar(self, symbol, day):
            self.bar_calls.append((symbol, day))
            return self.source.get_bar(symbol, day)

    probe = CountingSource(data)
    as_of = data.dates[-1]
    ranked = _rank_snapshot(probe, as_of)

    assert len(ranked) == len(symbols)
    assert probe.common_calls == 1
    assert len(probe.bar_calls) == 2 * len(symbols)
    assert all(day in (data.dates[-253], as_of) for _, day in probe.bar_calls)


def test_rank_snapshot_batch_endpoints_match_legacy_values_and_exclude_missing() -> None:
    symbols = ("000001.SZ", "000002.SZ", "000003.SZ")
    data = _data(symbols)
    as_of = data.dates[-1]
    expected_values = {
        symbol: adjusted_momentum(data, symbol, as_of)
        for symbol in symbols[:2]
    }

    class BatchSource:
        def __init__(self, source):
            self.source = source
            self.common_calls = 0
            self.batch_calls = 0

        def symbols_as_of(self, day):
            return self.source.symbols_as_of(day)

        def common_trading_dates(self, start, end):
            self.common_calls += 1
            return self.source.common_trading_dates(start, end)

        def get_adjusted_momentum_endpoints(self, requested_symbols, start_day, end_day):
            self.batch_calls += 1
            return {
                symbol: (self.source.bars[symbol][start_day], self.source.bars[symbol][end_day])
                for symbol in requested_symbols[:2]
            }

        def get_bar(self, symbol, day):
            raise AssertionError("batch rank path must not call per-symbol get_bar")

    source = BatchSource(data)
    ranked = _rank_snapshot(source, as_of)

    assert ranked == rank_candidates(expected_values)
    assert source.common_calls == 1
    assert source.batch_calls == 1


def test_rank_snapshot_reuses_one_as_of_result() -> None:
    source = _data()

    class CountingSource:
        def __init__(self, source):
            self.source = source
            self.symbol_calls = 0

        def symbols_as_of(self, as_of):
            self.symbol_calls += 1
            return self.source.symbols_as_of(as_of)

        def common_trading_dates(self, start, end):
            return self.source.common_trading_dates(start, end)

        def get_bar(self, symbol, day):
            return self.source.get_bar(symbol, day)

    probe = CountingSource(source)
    as_of = source.dates[-1]
    first = _rank_snapshot(probe, as_of)
    second = _rank_snapshot(probe, as_of)

    assert first == second
    assert probe.symbol_calls == 1


def test_rank_snapshot_cache_is_bounded() -> None:
    data = _data()
    for as_of in data.dates[-9:]:
        _rank_snapshot(data, as_of)

    assert len(data._v3_rank_snapshot_cache) <= 8


def test_empty_portfolio_does_not_trigger_marketwide_exit_rank() -> None:
    class NoRankSource:
        def symbols_as_of(self, as_of):
            raise AssertionError("empty portfolio must not rank the market")

    from strategy_core.portfolio import PortfolioState

    assert _exit_symbols(NoRankSource(), PortfolioState(cash=100000.0), date(2024, 1, 2)) == set()


def test_v3_core_binds_revision_and_blocks_new_entry_on_market_regime() -> None:
    data = _data()
    start = data.dates[-10]
    end = data.dates[-2]
    data.blocked_dates.add(data.dates[-6])
    spec = V3RelativeStrengthExecutionSpec(
        strategy_revision_id=REVISION_ID,
        protocol_snapshot_id="6f7cbdcdeb26f8cdd2611a5450dbab3ff22544b6a66ec8539f5cab9151329111",
        data_snapshot_hash="snapshot-hash",
        supplement_id="supplement-id",
        backtest_start=start,
        backtest_end=end,
    )
    result = run_v3_relative_strength_backtest(spec, data)
    assert result.strategy_revision_id == REVISION_ID
    assert result.protocol_snapshot_id == spec.protocol_snapshot_id
    assert result.future_violations == ()
    assert all(fill.fill_date <= end for fill in result.fills)


def test_observation_sink_receives_one_frozen_snapshot_per_trading_day() -> None:
    data = _data()
    start = data.dates[-10]
    end = data.dates[-2]
    spec = V3RelativeStrengthExecutionSpec(
        strategy_revision_id=REVISION_ID,
        protocol_snapshot_id="proto",
        data_snapshot_hash="snapshot",
        supplement_id="supplement",
        backtest_start=start,
        backtest_end=end,
    )
    snapshots = []

    result = run_v3_relative_strength_backtest(
        spec, data, observation_sink=snapshots.append
    )

    assert result.backtest_start == start
    assert [snapshot.date for snapshot in snapshots] == list(data.dates[-10:-1])
    assert len(snapshots) == len(data.dates[-10:-1])
    assert all(snapshot.positions == tuple(snapshot.positions) for snapshot in snapshots)


def test_observation_sink_snapshot_is_immutable_and_default_result_is_equivalent() -> None:
    data = _data()
    start = data.dates[-10]
    end = data.dates[-2]
    spec = V3RelativeStrengthExecutionSpec(
        strategy_revision_id=REVISION_ID,
        protocol_snapshot_id="proto",
        data_snapshot_hash="snapshot",
        supplement_id="supplement",
        backtest_start=start,
        backtest_end=end,
    )
    baseline = run_v3_relative_strength_backtest(spec, data)
    seen = []

    def observe(snapshot):
        seen.append(snapshot)
        with pytest.raises((AttributeError, TypeError)):
            snapshot.cash = 0.0

    observed = run_v3_relative_strength_backtest(spec, data, observation_sink=observe)

    assert seen
    assert observed == baseline


def test_observation_sink_exception_is_fail_loud() -> None:
    data = _data()
    spec = V3RelativeStrengthExecutionSpec(
        strategy_revision_id=REVISION_ID,
        protocol_snapshot_id="proto",
        data_snapshot_hash="snapshot",
        supplement_id="supplement",
        backtest_start=data.dates[-10],
        backtest_end=data.dates[-2],
    )

    def fail(_snapshot):
        raise RuntimeError("observation sink failed")

    with pytest.raises(RuntimeError, match="observation sink failed"):
        run_v3_relative_strength_backtest(spec, data, observation_sink=fail)


def test_entry_selection_applies_top15_liquidity_and_max_five() -> None:
    symbols = tuple(f"{index:06d}.SZ" for index in range(1, 41))
    data = _data(symbols)
    as_of = data.dates[-2]
    selected = _entry_symbols(data, as_of, data.dates[-1], set())
    assert len(selected) == 6  # ceil(0.15 * 40), before portfolio slot limiting
    assert selected == sorted(selected, key=lambda symbol: -int(symbol[:6]))

    small = _data()
    small.suspended_symbols.add("000003.SZ")
    assert "000003.SZ" not in _entry_symbols(small, as_of, data.dates[-1], set())

    spec = V3RelativeStrengthExecutionSpec(
        strategy_revision_id=REVISION_ID,
        protocol_snapshot_id="proto",
        data_snapshot_hash="snapshot",
        supplement_id="supplement",
        backtest_start=data.dates[-10],
        backtest_end=data.dates[-2],
    )
    result = run_v3_relative_strength_backtest(spec, data)
    assert len(result.final_portfolio.positions) <= 5


def test_stop_loss_and_holding_period_are_common_session_rules() -> None:
    data = _data()
    calendar = _V3Calendar(data.dates)
    from strategy_core.portfolio import PortfolioState

    portfolio = PortfolioState(cash=100000.0)
    buy_day = data.dates[-20]
    portfolio.add_position("000001.SZ", 100, 100.0, buy_day, calendar)
    as_of = data.dates[-1]
    current = data.bars["000001.SZ"][as_of]
    data.bars["000001.SZ"][as_of] = current.model_copy(update={"close": 90.0, "open": 90.0, "high": 91.0, "low": 89.0})
    assert "000001.SZ" in _exit_symbols(data, portfolio, as_of)


def test_suspended_position_keeps_last_price_without_reading_missing_bar() -> None:
    data = _data(("000001.SZ",))
    suspended_day = data.dates[-1]
    data.suspended_symbols.add("000001.SZ")
    calendar = _V3Calendar(data.dates)
    from strategy_core.portfolio import PortfolioState

    portfolio = PortfolioState(cash=100000.0)
    portfolio.add_position("000001.SZ", 100, 100.0, data.dates[-20], calendar)
    portfolio.positions["000001.SZ"].last_price = 123.0

    class MissingSuspendedBar:
        def get_status(self, symbol, day):
            return data.get_status(symbol, day)

        def get_bar(self, symbol, day):
            raise KeyError(f"missing suspended bar {symbol}/{day}")

    _mark_position_prices(MissingSuspendedBar(), portfolio, suspended_day)

    assert portfolio.positions["000001.SZ"].last_price == 123.0


def test_suspended_exit_keeps_holding_exit_pending_without_stop_bar() -> None:
    data = _data(("000001.SZ",))
    suspended_day = data.dates[-1]
    data.suspended_symbols.add("000001.SZ")
    calendar = _V3Calendar(data.dates)
    from strategy_core.portfolio import PortfolioState

    portfolio = PortfolioState(cash=100000.0)
    portfolio.add_position("000001.SZ", 100, 100.0, data.dates[-20], calendar)

    class MissingSuspendedBar:
        def symbols_as_of(self, as_of):
            return data.symbols_as_of(as_of)

        def common_trading_dates(self, start, end):
            return data.common_trading_dates(start, end)

        def get_bar(self, symbol, day):
            if day == suspended_day:
                raise KeyError(f"missing suspended bar {symbol}/{day}")
            return data.get_bar(symbol, day)

        def get_status(self, symbol, day):
            return data.get_status(symbol, day)

    assert "000001.SZ" in _exit_symbols(MissingSuspendedBar(), portfolio, suspended_day)


def test_market_regime_block_does_not_create_entry_intents() -> None:
    data = _data()
    data.blocked_dates.update(data.dates[-12:-1])
    spec = V3RelativeStrengthExecutionSpec(
        strategy_revision_id=REVISION_ID,
        protocol_snapshot_id="proto",
        data_snapshot_hash="snapshot",
        supplement_id="supplement",
        backtest_start=data.dates[-10],
        backtest_end=data.dates[-2],
    )
    result = run_v3_relative_strength_backtest(spec, data)
    assert all(intent.intent != "buy" for intent in result.order_intents)


def test_v3_data_reads_use_existing_future_cursor_guard() -> None:
    data = _data()
    as_of = data.dates[-2]
    cursor = BacktestTimeCursor(
        cursor_id="v3-signal-test",
        current_date=as_of,
        evaluation_mode="signal_phase",
    )
    view = _CursorBoundV3DataSource(data, cursor)
    with pytest.raises(FutureDataAccessError):
        view.get_bar("000001.SZ", data.dates[-1])
    with pytest.raises(FutureDataAccessError):
        view.get_daily_bars("000001.SZ", data.dates[-1], 1)


def test_v3_batch_endpoint_reads_guard_both_frozen_dates() -> None:
    data = _data()
    as_of = data.dates[-2]
    cursor = BacktestTimeCursor(
        cursor_id="v3-batch-test",
        current_date=as_of,
        evaluation_mode="signal_phase",
    )
    view = _CursorBoundV3DataSource(data, cursor)
    with pytest.raises(FutureDataAccessError):
        view.get_adjusted_momentum_endpoints(
            ("000001.SZ",), data.dates[-253], data.dates[-1]
        )
    with pytest.raises(FutureDataAccessError):
        view.get_adjusted_momentum_endpoints(
            ("000001.SZ",), data.dates[-1], as_of
        )


def test_multi_exit_order_sequence_is_stable_across_hash_seeds() -> None:
    """Real V3 runs must not expose set iteration order in execution output."""
    script = r'''
import json
from datetime import date

from tests.test_v3_relative_strength_executor import _data
from strategy_core.v3_relative_strength_executor import (
    V3RelativeStrengthExecutionSpec,
    run_v3_relative_strength_backtest,
)

data = _data(tuple(f"{index:06d}.SZ" for index in range(1, 9)))
for symbol, by_day in data.bars.items():
    for day, bar in tuple(by_day.items()):
        by_day[day] = bar.model_copy(update={
            "open": bar.open / 100.0,
            "high": bar.high / 100.0,
            "low": bar.low / 100.0,
            "close": bar.close / 100.0,
        })
start = data.dates[-24]
end = data.dates[-1]
spec = V3RelativeStrengthExecutionSpec(
    strategy_revision_id="6440ffc03a742f4d4632078481cf3abf171eafb1a24f2bc69bc6f352d1b19ebc",
    protocol_snapshot_id="hash-seed-protocol",
    data_snapshot_hash="hash-seed-data",
    supplement_id="hash-seed-supplement",
    backtest_start=start,
    backtest_end=end,
)
observations = []
result = run_v3_relative_strength_backtest(spec, data, observation_sink=observations.append)

def model(value):
    return value.model_dump(mode="json")

def observation(value):
    return {
        "date": value.date.isoformat(),
        "cash": value.cash,
        "portfolio_value": value.portfolio_value,
        "positions": value.positions,
    }

intents = [model(item) for item in result.order_intents]
fills = [model(item) for item in result.fills]
rejects = [model(item) for item in result.rejected_orders]
business = {
    "intents": sorted(
        [
            {
                "symbol": item["symbol"],
                "signal_date": item["signal_date"],
                "intent": item["intent"],
                "quantity": item["quantity"],
            }
            for item in intents
        ],
        key=lambda item: (item["symbol"], item["signal_date"], item["intent"], item["quantity"]),
    ),
    "fills": sorted(
        [
            {
                "symbol": item["symbol"],
                "fill_date": item["fill_date"],
                "fill_price": item["fill_price"],
                "fill_quantity": item["fill_quantity"],
                "execution_mode": item["execution_mode"],
            }
            for item in fills
        ],
        key=lambda item: (item["symbol"], item["fill_date"], item["fill_price"], item["fill_quantity"], item["execution_mode"]),
    ),
    "rejects": sorted(
        [
            {
                "symbol": item["symbol"],
                "intended_date": item["intended_date"],
                "rejection_reason": item["rejection_reason"],
            }
            for item in rejects
        ],
        key=lambda item: (item["symbol"], item["intended_date"], item["rejection_reason"]),
    ),
    "final_positions": result.final_portfolio.positions,
}
canonical = {
    "intents": intents,
    "fills": fills,
    "rejects": rejects,
    "final_portfolio": model(result.final_portfolio),
    "observations": [observation(item) for item in observations],
}
if sum(item["intent"] == "sell" for item in intents) < 2:
    raise AssertionError(f"fixture did not create a multi-exit run: {canonical}")
print(json.dumps({"business": business, "canonical": canonical}, sort_keys=True, separators=(",", ":")))
'''

    payloads = []
    for seed in ("1", "2"):
        environment = os.environ.copy()
        environment["PYTHONHASHSEED"] = seed
        completed = subprocess.run(
            [sys.executable, "-c", script],
            cwd=str(REPO_ROOT),
            env=environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        assert completed.returncode == 0, completed.stderr
        payloads.append(json.loads(completed.stdout))

    assert payloads[0]["business"] == payloads[1]["business"]
    assert payloads[0]["canonical"] == payloads[1]["canonical"]


def test_pending_exit_carry_and_new_exit_are_consumed_symbol_sorted() -> None:
    """A carried exit must not retain dict insertion order ahead of a new exit."""
    symbols = tuple(f"{index:06d}.SZ" for index in range(1, 9))

    class ScenarioData(FakeV3Data):
        def get_status(self, symbol, day):
            status = super().get_status(symbol, day)
            if (symbol, day) in getattr(self, "status_overrides", set()):
                return status.model_copy(update={"is_suspended": True})
            return status

    base = _data(symbols)
    for symbol, by_day in base.bars.items():
        for day, bar in tuple(by_day.items()):
            by_day[day] = bar.model_copy(update={
                "open": bar.open / 100.0,
                "high": bar.high / 100.0,
                "low": bar.low / 100.0,
                "close": bar.close / 100.0,
            })
    data = ScenarioData(
        dates=base.dates,
        bars=base.bars,
        blocked_dates=set(base.blocked_dates),
        suspended_symbols=set(base.suspended_symbols),
    )
    schedule = execution_schedule(data.dates, data.dates[-24], data.dates[-1])
    assert len(schedule) >= 3
    first_execution, _ = schedule[0]
    carry_execution, carry_as_of = schedule[1]
    merge_execution, merge_as_of = schedule[2]
    carry_symbol = symbols[-1]
    new_symbol = symbols[-2]

    for day, symbol in ((carry_as_of, carry_symbol), (merge_as_of, carry_symbol), (merge_as_of, new_symbol)):
        current = data.bars[symbol][day]
        data.bars[symbol][day] = current.model_copy(update={
            "open": 0.1,
            "high": 0.1,
            "low": 0.1,
            "close": 0.1,
        })
    data.blocked_dates.update({carry_as_of, merge_as_of})
    data.status_overrides = {
        (carry_symbol, day)
        for day in data.dates
        if carry_execution <= day < merge_execution
    }

    result = run_v3_relative_strength_backtest(
        V3RelativeStrengthExecutionSpec(
            strategy_revision_id=REVISION_ID,
            protocol_snapshot_id="carry-merge-protocol",
            data_snapshot_hash="carry-merge-data",
            supplement_id="carry-merge-supplement",
            backtest_start=data.dates[-24],
            backtest_end=data.dates[-1],
        ),
        data,
    )

    first_buys = {
        item.symbol
        for item in result.order_intents
        if item.intent == "buy" and item.order_id.endswith(f":buy:{first_execution}")
    }
    assert first_buys == {carry_symbol, new_symbol}
    assert any(
        item.symbol == carry_symbol
        and item.intended_date == carry_execution
        and item.rejection_reason == "suspended"
        for item in result.rejected_orders
    )

    merge_sells = [
        item.symbol
        for item in result.order_intents
        if item.intent == "sell" and item.order_id.endswith(f":sell:{merge_execution}")
    ]
    assert sorted(merge_sells) == sorted({carry_symbol, new_symbol}), {
        "merge_sells": merge_sells,
        "intents": [item.model_dump(mode="json") for item in result.order_intents],
        "fills": [item.model_dump(mode="json") for item in result.fills],
        "rejected": [item.model_dump(mode="json") for item in result.rejected_orders],
    }
    assert merge_sells == sorted(merge_sells)
