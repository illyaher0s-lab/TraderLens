"""Dedicated execution core for the approved v3 relative-strength strategy."""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Callable

from contracts.stable import DailyBar, Order
from backend.services.b4_protocol_types import (
    DailyPortfolioSnapshot,
    EventBacktestResult,
    FillRecord,
    OrderIntentRecord,
    RejectedOrderRecord,
)
from backend.services.backtest_time_cursor import BacktestTimeCursor, FutureDataAccessError
from strategy_core.fill_simulator import simulate_fill
from strategy_core.portfolio import PortfolioState
from strategy_core.position_sizer import PositionSizer


STRATEGY_REVISION_ID = "6440ffc03a742f4d4632078481cf3abf171eafb1a24f2bc69bc6f352d1b19ebc"
RANK_SNAPSHOT_CACHE_MAX_ENTRIES = 8


@dataclass(frozen=True)
class V3RelativeStrengthExecutionSpec:
    strategy_revision_id: str
    protocol_snapshot_id: str
    data_snapshot_hash: str
    supplement_id: str
    backtest_start: date
    backtest_end: date
    initial_capital: float = 100000.0


@dataclass(frozen=True)
class V3DailyPortfolioObservation:
    """Immutable end-of-day value view for the v3-only observation seam."""

    date: date
    cash: float
    portfolio_value: float
    # (symbol, quantity, last_price); primitives only, so no mutable Position leaks.
    positions: tuple[tuple[str, int, float], ...]


class _V3Calendar:
    def __init__(self, dates: tuple[date, ...]):
        self._dates = tuple(sorted(set(dates)))
        self._index = {day: index for index, day in enumerate(self._dates)}
        if not self._dates:
            raise ValueError("v3 execution requires a non-empty common trading calendar")

    def all_trading_dates(self) -> list[date]:
        return list(self._dates)

    def next_trading_day(self, current_date: date) -> date:
        try:
            index = self._index[current_date]
        except KeyError as exc:
            raise ValueError(f"not a common trading day: {current_date}") from exc
        if index + 1 >= len(self._dates):
            raise ValueError(f"no common trading day after {current_date}")
        return self._dates[index + 1]


class _CursorBoundV3DataSource:
    """Bind v3's small data contract to the existing B4 time cursor."""

    def __init__(self, raw_data_source: Any, cursor: BacktestTimeCursor):
        self._raw = raw_data_source
        self._cursor = cursor

    def _allow(self, symbol: str, requested_date: date, data_type: str) -> None:
        allowed, violation = self._cursor.request_read(
            symbol=symbol,
            requested_date=requested_date,
            data_type=data_type,
            source="v3_relative_strength_executor",
        )
        if not allowed:
            raise FutureDataAccessError(violation)

    def symbols_as_of(self, as_of: date) -> tuple[str, ...]:
        self._allow("*", as_of, "membership")
        return tuple(self._raw.symbols_as_of(as_of))

    def common_trading_dates(self, start: date, end: date) -> tuple[date, ...]:
        self._allow("*", end, "calendar")
        return tuple(self._raw.common_trading_dates(start, end))

    def get_daily_bars(self, symbol: str, end: date, n: int) -> tuple[DailyBar, ...]:
        self._allow(symbol, end, "bar")
        bars = tuple(self._raw.get_daily_bars(symbol, end, n))
        for bar in bars:
            self._allow(symbol, bar.date, "bar")
        return bars

    def get_bar(self, symbol: str, day: date) -> DailyBar:
        self._allow(symbol, day, "bar")
        return self._raw.get_bar(symbol, day)

    def get_adjusted_momentum_endpoints(
        self,
        symbols: tuple[str, ...] | list[str],
        start_day: date,
        end_day: date,
    ) -> dict[str, tuple[DailyBar, DailyBar]] | None:
        self._allow("*", start_day, "bar")
        self._allow("*", end_day, "bar")
        reader = getattr(self._raw, "get_adjusted_momentum_endpoints", None)
        if reader is None:
            return None
        return reader(tuple(symbols), start_day, end_day)

    def get_daily_bar(self, symbol: str, day: date) -> DailyBar:
        return self.get_bar(symbol, day)

    def get_status(self, symbol: str, day: date):
        self._allow(symbol, day, "daily_status")
        return self._raw.get_status(symbol, day)

    def get_daily_status(self, symbol: str, day: date):
        return self.get_status(symbol, day)

    def derive_liquidity(self, symbol: str, execution_day: date) -> dict[str, object]:
        prior_dates = tuple(
            day
            for day in self._raw.common_trading_dates(date(1900, 1, 1), execution_day)
            if day < execution_day
        )
        if prior_dates:
            self._allow(symbol, prior_dates[-1], "liquidity")
        return self._raw.derive_liquidity(symbol, execution_day)

    def market_regime_blocked(self, as_of: date) -> bool:
        self._allow("*", as_of, "market_regime")
        checker = getattr(self._raw, "market_regime_blocked", None)
        return bool(checker(as_of)) if checker is not None else False


def execution_schedule(
    common_dates: tuple[date, ...] | list[date],
    start: date,
    end: date,
) -> tuple[tuple[date, date], ...]:
    """Return weekly execution dates with their immediately prior common as-of dates."""
    dates = tuple(sorted(set(common_dates)))
    if start > end:
        raise ValueError("backtest start cannot be after end")
    selected = [day for day in dates if start <= day <= end]
    schedule: list[tuple[date, date]] = []
    for index, execution_day in enumerate(selected):
        previous = [day for day in dates if day < execution_day]
        if not previous:
            raise ValueError(f"no completed common day before {execution_day}")
        if index == 0 or execution_day.isocalendar()[:2] != selected[index - 1].isocalendar()[:2]:
            schedule.append((execution_day, previous[-1]))
    return tuple(schedule)


def adjusted_momentum(data_source: Any, symbol: str, as_of: date) -> float:
    """Compute the frozen 252-common-day adjusted-close return."""
    common_dates = tuple(data_source.common_trading_dates(date(1900, 1, 1), as_of))
    if len(common_dates) < 253 or common_dates[-1] > as_of:
        raise ValueError(f"v3 momentum endpoint unavailable or future-dated: {symbol}/{as_of}")
    return _adjusted_momentum_from_endpoints(data_source, symbol, common_dates[-253], as_of)


def _adjusted_momentum_from_endpoints(
    data_source: Any,
    symbol: str,
    start_day: date,
    end_day: date,
) -> float:
    start = data_source.get_bar(symbol, start_day)
    end = data_source.get_bar(symbol, end_day)
    return _adjusted_momentum_from_bars(symbol, start, end, start_day, end_day)


def _adjusted_momentum_from_bars(
    symbol: str,
    start: DailyBar,
    end: DailyBar,
    start_day: date,
    end_day: date,
) -> float:
    if start.date != start_day or end.date > end_day:
        raise ValueError(f"v3 momentum endpoint unavailable or future-dated: {symbol}/{end_day}")
    start_value = float(start.close) * float(start.adj_factor)
    end_value = float(end.close) * float(end.adj_factor)
    if not math.isfinite(start_value) or not math.isfinite(end_value) or start_value <= 0:
        raise ValueError(f"invalid v3 momentum endpoint: {symbol}/{end_day}")
    return end_value / start_value - 1.0


def rank_candidates(values: dict[str, float]) -> list[tuple[str, float, int]]:
    """Rank descending return with deterministic symbol-ascending ties."""
    ordered = sorted(values.items(), key=lambda item: (-item[1], item[0]))
    return [(symbol, value, rank) for rank, (symbol, value) in enumerate(ordered, start=1)]


def _rank_snapshot(data_source: Any, as_of: date) -> list[tuple[str, float, int]]:
    cache = getattr(data_source, "_v3_rank_snapshot_cache", None)
    if cache is None:
        cache = {}
        setattr(data_source, "_v3_rank_snapshot_cache", cache)
    if as_of in cache:
        return cache[as_of]
    common_dates = tuple(data_source.common_trading_dates(date(1900, 1, 1), as_of))
    if len(common_dates) < 253 or common_dates[-1] > as_of:
        raise ValueError(f"v3 momentum endpoint unavailable or future-dated: {as_of}")
    start_day = common_dates[-253]
    symbols = tuple(data_source.symbols_as_of(as_of))
    batch_reader = getattr(data_source, "get_adjusted_momentum_endpoints", None)
    values: dict[str, float] = {}
    if batch_reader is not None:
        try:
            endpoint_map = batch_reader(symbols, start_day, as_of)
        except (FileNotFoundError, KeyError, ValueError, TypeError):
            endpoint_map = {}
        if endpoint_map is not None:
            for symbol in symbols:
                try:
                    start_bar, end_bar = endpoint_map[symbol]
                    values[symbol] = _adjusted_momentum_from_bars(
                        symbol, start_bar, end_bar, start_day, as_of
                    )
                except (FileNotFoundError, KeyError, ValueError, TypeError):
                    continue
        else:
            batch_reader = None
    if batch_reader is None:
        for symbol in symbols:
            try:
                values[symbol] = _adjusted_momentum_from_endpoints(data_source, symbol, start_day, as_of)
            except (FileNotFoundError, KeyError, ValueError, TypeError):
                continue
    ranked = rank_candidates(values)
    if len(cache) >= RANK_SNAPSHOT_CACHE_MAX_ENTRIES:
        cache.pop(next(iter(cache)))
    cache[as_of] = ranked
    return ranked


def _market_regime_blocked(data_source: Any, as_of: date) -> bool:
    checker = getattr(data_source, "market_regime_blocked", None)
    return bool(checker(as_of)) if checker is not None else False


def _holding_sessions(data_source: Any, bought: date, as_of: date) -> int:
    dates = data_source.common_trading_dates(date(1900, 1, 1), as_of)
    return sum(bought <= day <= as_of for day in dates)


def _mark_position_prices(data_source: Any, portfolio: PortfolioState, as_of: date) -> None:
    """Mark only with a formal bar; retain the last price on an exact suspension."""
    for symbol in list(portfolio.positions):
        status = data_source.get_status(symbol, as_of)
        if status.is_suspended:
            continue
        portfolio.positions[symbol].last_price = data_source.get_bar(symbol, as_of).close


def _exit_symbols(data_source: Any, portfolio: PortfolioState, as_of: date) -> set[str]:
    if not portfolio.positions:
        return set()
    ranked = _rank_snapshot(data_source, as_of)
    rank_by_symbol = {symbol: (value, rank) for symbol, value, rank in ranked}
    exit_symbols: set[str] = set()
    top_40_cutoff = math.ceil(0.40 * len(ranked)) if ranked else 0
    for symbol, position in portfolio.positions.items():
        item = rank_by_symbol.get(symbol)
        rank_exit = item is not None and item[1] > top_40_cutoff
        holding_exit = position.oldest_buy_date is not None and _holding_sessions(
            data_source, position.oldest_buy_date, as_of
        ) >= 15
        status = data_source.get_status(symbol, as_of)
        stop_exit = False
        if not status.is_suspended:
            bar = data_source.get_bar(symbol, as_of)
            stop_exit = float(bar.close) <= float(position.avg_cost) * 0.92
        if rank_exit or holding_exit or stop_exit:
            exit_symbols.add(symbol)
    return exit_symbols


def _entry_symbols(data_source: Any, as_of: date, execution_day: date, occupied: set[str]) -> list[str]:
    if _market_regime_blocked(data_source, as_of):
        return []
    ranked = _rank_snapshot(data_source, as_of)
    top_count = math.ceil(0.15 * len(ranked)) if ranked else 0
    ranks_by_symbol = {symbol: (value, rank) for symbol, value, rank in ranked}
    confirmation_dates = data_source.common_trading_dates(date(1900, 1, 1), as_of)[-3:]
    if len(confirmation_dates) != 3:
        return []
    result: list[tuple[float, str]] = []
    for symbol, value, rank in ranked:
        if rank > top_count or symbol in occupied:
            continue
        try:
            status = data_source.get_status(symbol, as_of)
        except (FileNotFoundError, KeyError, ValueError, TypeError):
            continue
        if status.is_st or status.is_suspended:
            continue
        if any(
            next((item[2] for item in _rank_snapshot(data_source, confirm) if item[0] == symbol), top_count + 1)
            > top_count
            for confirm in confirmation_dates
        ):
            continue
        liquidity = data_source.derive_liquidity(symbol, execution_day)
        if liquidity.get("status") != "qualified":
            continue
        result.append((value, symbol))
    return [symbol for _, symbol in sorted(result, key=lambda item: (-item[0], item[1]))]


def _make_order(
    symbol: str,
    direction: str,
    signal_date: date,
    execution_day: date,
    quantity: int,
    reason: str,
    sequence: int,
) -> Order:
    return Order(
        order_id=f"v3-order:{sequence}:{symbol}:{direction}:{execution_day}",
        signal_id=f"v3-signal:{sequence}:{symbol}:{direction}",
        signal_date=signal_date,
        intended_execution_date=execution_day,
        symbol=symbol,
        direction=direction,
        quantity=quantity,
        reason=reason,
        strategy_version=STRATEGY_REVISION_ID,
        generated_by="v3_relative_strength_executor",
        audit_id=f"v3-audit:{sequence}",
    )


def run_v3_relative_strength_backtest(
    spec: V3RelativeStrengthExecutionSpec,
    data_source: Any,
    observation_sink: Callable[[V3DailyPortfolioObservation], object] | None = None,
) -> EventBacktestResult:
    """Run only the frozen v3 relative-strength execution loop."""
    if spec.strategy_revision_id != STRATEGY_REVISION_ID:
        raise ValueError("v3 strategy revision mismatch")
    if spec.backtest_start > spec.backtest_end or spec.initial_capital <= 0:
        raise ValueError("invalid v3 backtest range or initial capital")
    all_dates = tuple(data_source.common_trading_dates(date(1900, 1, 1), spec.backtest_end))
    calendar = _V3Calendar(all_dates)
    schedule = dict(execution_schedule(all_dates, spec.backtest_start, spec.backtest_end))
    trading_dates = tuple(day for day in all_dates if spec.backtest_start <= day <= spec.backtest_end)
    if not trading_dates:
        raise ValueError("v3 backtest range has no common trading days")

    portfolio = PortfolioState(cash=spec.initial_capital)
    sizer = PositionSizer(position_ratio=0.20, lot_size=100)
    order_intents: list[OrderIntentRecord] = []
    fills: list[FillRecord] = []
    rejected: list[RejectedOrderRecord] = []
    pending_exits: dict[str, tuple[date, str]] = {}
    sequence = 0

    for day in trading_dates:
        execution_cursor = BacktestTimeCursor(
            cursor_id=f"v3-execution:{day}",
            current_date=day - timedelta(days=1),
            evaluation_mode="execution_phase",
        )
        execution_data = _CursorBoundV3DataSource(data_source, execution_cursor)
        portfolio.unlock_frozen_lots(day)

        as_of = all_dates[all_dates.index(day) - 1] if all_dates.index(day) > 0 else None
        if as_of is not None:
            signal_cursor = BacktestTimeCursor(
                cursor_id=f"v3-signal:{as_of}",
                current_date=as_of,
                evaluation_mode="signal_phase",
            )
            signal_data = _CursorBoundV3DataSource(data_source, signal_cursor)
            _mark_position_prices(signal_data, portfolio, as_of)
            for symbol in sorted(_exit_symbols(signal_data, portfolio, as_of)):
                pending_exits.setdefault(symbol, (as_of, "rank_or_holding_or_stop"))
        else:
            signal_data = None

        orders: list[tuple[Order, bool]] = []
        for symbol, (signal_date, reason) in sorted(pending_exits.items()):
            if symbol not in portfolio.positions:
                pending_exits.pop(symbol, None)
                continue
            position = portfolio.positions[symbol]
            if position.sellable_quantity > 0:
                sequence += 1
                orders.append((_make_order(symbol, "sell", signal_date, day, position.sellable_quantity, reason, sequence), True))

        if day in schedule:
            signal_date = schedule[day]
            if signal_data is None or signal_date != as_of:
                signal_cursor = BacktestTimeCursor(
                    cursor_id=f"v3-signal:{signal_date}",
                    current_date=signal_date,
                    evaluation_mode="signal_phase",
                )
                signal_data = _CursorBoundV3DataSource(data_source, signal_cursor)
            entry_symbols = _entry_symbols(signal_data, signal_date, day, set(portfolio.positions) | set(pending_exits))
            slots = max(0, 5 - len(portfolio.positions) - len(pending_exits))
            for symbol in entry_symbols[:slots]:
                decision_bar = signal_data.get_bar(symbol, signal_date)
                quantity = sizer.calculate_quantity(decision_bar.close, portfolio.total_value())
                if quantity <= 0:
                    continue
                sequence += 1
                orders.append((_make_order(symbol, "buy", signal_date, day, quantity, "top15_confirmed", sequence), False))

        for order, is_exit in orders:
            order_intents.append(OrderIntentRecord(
                order_id=order.order_id, symbol=order.symbol, signal_date=order.signal_date,
                intent=order.direction, quantity=order.quantity,
            ))
            filled = simulate_fill(
                order, day, execution_data, portfolio,
                commission_rate=0.0003, min_commission=5.0,
                stamp_duty_rate=0.001, transfer_fee_rate=0.0,
                slippage_rate=0.0, max_participation_rate=0.10,
                calendar=calendar,
            )
            if filled.status == "filled":
                fills.append(FillRecord(
                    fill_id=f"fill:{filled.order_id}", order_id=filled.order_id,
                    symbol=filled.symbol, fill_date=filled.actual_execution_date,
                    fill_price=filled.actual_price, fill_quantity=filled.actual_quantity,
                    execution_mode="simulated",
                ))
                if is_exit:
                    pending_exits.pop(order.symbol, None)
            else:
                rejected.append(RejectedOrderRecord(
                    order_id=filled.order_id, symbol=filled.symbol,
                    intended_date=filled.intended_execution_date,
                    rejection_reason=filled.rejection_reason or "rejected",
                ))
                if not is_exit:
                    # Entries expire after their scheduled execution day.
                    continue
                pending_exits[order.symbol] = (order.signal_date, order.reason)

        _mark_position_prices(execution_data, portfolio, day)
        if observation_sink is not None:
            observation_sink(
                V3DailyPortfolioObservation(
                    date=day,
                    cash=float(portfolio.cash),
                    portfolio_value=float(portfolio.total_value()),
                    positions=tuple(
                        sorted(
                            (
                                symbol,
                                int(position.quantity),
                                float(position.last_price),
                            )
                            for symbol, position in portfolio.positions.items()
                        )
                    ),
                )
            )

    final_day = trading_dates[-1]
    final_cursor = BacktestTimeCursor(
        cursor_id=f"v3-final:{final_day}",
        current_date=final_day,
        evaluation_mode="signal_phase",
    )
    final_data = _CursorBoundV3DataSource(data_source, final_cursor)
    _mark_position_prices(final_data, portfolio, final_day)
    final = DailyPortfolioSnapshot(
        snapshot_id=f"v3-final:{spec.protocol_snapshot_id}:{final_day}",
        snapshot_date=final_day,
        cash=portfolio.cash,
        positions=tuple(sorted((symbol, position.quantity) for symbol, position in portfolio.positions.items())),
        portfolio_value=portfolio.total_value(),
    )
    return EventBacktestResult(
        result_id=f"v3-result:{spec.protocol_snapshot_id}:{spec.backtest_start}:{spec.backtest_end}",
        strategy_revision_id=spec.strategy_revision_id,
        protocol_snapshot_id=spec.protocol_snapshot_id,
        evaluation_mode="formal_backtest",
        backtest_start=trading_dates[0],
        backtest_end=final_day,
        order_intents=tuple(order_intents), fills=tuple(fills),
        rejected_orders=tuple(rejected), future_violations=(),
        final_portfolio=final, frozen_at=date.today(),
    )
