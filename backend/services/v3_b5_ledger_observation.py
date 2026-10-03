"""Deterministic v3 B5 observations rebuilt from the verified B4 fill ledger."""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from backend.services.b4_protocol_types import DailyPortfolioSnapshot, EventBacktestResult
from strategy_core.portfolio import PortfolioState
from strategy_core.transaction_costs import calculate_transaction_costs
from strategy_core.v3_relative_strength_executor import _V3Calendar


IS_START = date(2025, 6, 27)
IS_END = date(2026, 3, 19)
OOS_START = date(2026, 3, 20)
OBSERVATION_SCHEMA = "v3_b5_ledger_observations.v1"


class LedgerObservationError(ValueError):
    """A ledger or observation violates the frozen v3 accounting contract."""


@dataclass(frozen=True)
class LedgerReplay:
    observations: tuple[dict[str, object], ...]
    portfolio: PortfolioState
    consumed_fill_ids: tuple[str, ...]
    cost_ledger: tuple[dict[str, object], ...]
    operation_counts: dict[str, int]
    derived_position_details: dict[str, dict[str, object]]


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def _finite(value: object) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(float(value))


def _raise(message: str) -> None:
    raise LedgerObservationError(message)


def _validate_event(event: EventBacktestResult, expected_dates: tuple[date, ...]) -> dict[str, Any]:
    if not expected_dates or tuple(sorted(set(expected_dates))) != expected_dates:
        _raise("expected common dates must be non-empty, sorted and unique")
    if event.backtest_start != expected_dates[0] or event.backtest_end != expected_dates[-1]:
        _raise("event IS range does not match expected common dates")
    if event.future_violations:
        _raise("event contains future violations")
    intents = {item.order_id: item for item in event.order_intents}
    if len(intents) != len(event.order_intents):
        _raise("duplicate order intent identity")
    fill_ids = [item.fill_id for item in event.fills]
    if len(set(fill_ids)) != len(fill_ids):
        _raise("duplicate fill identity")
    if fill_ids != list(dict.fromkeys(fill_ids)):
        _raise("fill identity order is not deterministic")
    fill_dates = [item.fill_date for item in event.fills]
    if fill_dates != sorted(fill_dates):
        _raise("fill ledger is not ordered by fill_date")
    expected_set = set(expected_dates)
    for fill in event.fills:
        if fill.fill_date not in expected_set:
            _raise(f"fill outside expected IS: {fill.fill_id}")
        intent = intents.get(fill.order_id)
        if intent is None:
            _raise(f"fill order intent missing: {fill.order_id}")
        if intent.symbol != fill.symbol or intent.intent not in ("buy", "sell") or intent.quantity < fill.fill_quantity:
            _raise(f"fill/order intent mismatch: {fill.fill_id}")
        if not _finite(fill.fill_price) or fill.fill_price <= 0 or fill.fill_quantity <= 0:
            _raise(f"invalid fill value: {fill.fill_id}")
    return intents


def _mark_positions(data_source: Any, portfolio: PortfolioState, day: date, operation_counts: dict[str, int]) -> dict[str, int]:
    marks = {"status": 0, "bar": 0, "suspended_carry_forward": 0, "non_suspended_bar": 0}
    for symbol in list(portfolio.positions):
        try:
            status = data_source.get_status(symbol, day)
        except Exception as exc:  # preserve the source exception as a contract failure
            raise LedgerObservationError(f"status read failed: {symbol}/{day}") from exc
        marks["status"] += 1
        if not hasattr(status, "is_suspended"):
            _raise(f"status missing suspension field: {symbol}/{day}")
        if status.is_suspended:
            marks["suspended_carry_forward"] += 1
            continue
        try:
            bar = data_source.get_bar(symbol, day)
        except Exception as exc:
            raise LedgerObservationError(f"non-suspended daily bar missing: {symbol}/{day}") from exc
        if getattr(bar, "date", None) != day or not _finite(getattr(bar, "close", None)) or float(bar.close) <= 0:
            _raise(f"invalid daily mark: {symbol}/{day}")
        portfolio.positions[symbol].last_price = float(bar.close)
        marks["bar"] += 1
        marks["non_suspended_bar"] += 1
    return marks


def _make_observation(portfolio: PortfolioState, day: date, previous_value: float | None) -> tuple[dict[str, object], float]:
    values = {
        symbol: float(position.quantity) * float(position.last_price)
        for symbol, position in sorted(portfolio.positions.items())
    }
    positions_value = sum(values.values())
    portfolio_value = float(portfolio.cash) + positions_value
    if not _finite(portfolio.cash) or portfolio.cash < 0 or not _finite(portfolio_value):
        _raise(f"invalid portfolio accounting on {day}")
    if previous_value is None:
        daily_return = 0.0
    else:
        if previous_value == 0:
            _raise(f"zero previous portfolio value on {day}")
        daily_return = portfolio_value / previous_value - 1.0
    row = {
        "date": day.isoformat(),
        "cash": float(portfolio.cash),
        "portfolio_value": portfolio_value,
        "gross_exposure": positions_value,
        "net_exposure": positions_value,
        "positions_value": positions_value,
        "daily_return": daily_return,
        "position_values_by_symbol": values,
    }
    if sum(values.values()) != row["positions_value"] or row["cash"] + row["positions_value"] != row["portfolio_value"]:
        _raise(f"portfolio arithmetic mismatch on {day}")
    return row, portfolio_value


def replay_ledger(
    event: EventBacktestResult,
    data_source: Any,
    expected_dates: Iterable[date],
    *,
    initial_capital: float,
    allowed_end: date = IS_END,
) -> LedgerReplay:
    """Replay only immutable fills and formal EOD marks; never generate trades."""
    dates = tuple(expected_dates)
    if not _finite(initial_capital) or initial_capital <= 0:
        _raise("initial capital must be a positive finite value")
    if dates[-1] > allowed_end or dates[-1] >= OOS_START:
        _raise("expected dates cross the OOS boundary")
    intents = _validate_event(event, dates)
    calendar = _V3Calendar(dates)
    portfolio = PortfolioState(cash=float(initial_capital))
    fills_by_date: dict[date, list[Any]] = {day: [] for day in dates}
    for fill in event.fills:
        fills_by_date[fill.fill_date].append(fill)
    consumed: list[str] = []
    costs: list[dict[str, object]] = []
    observations: list[dict[str, object]] = []
    operation_counts = {
        "rank_snapshot": 0, "entry_symbols": 0, "exit_symbols": 0,
        "confirmation": 0, "derive_liquidity": 0, "market_regime": 0,
        "entry_generation": 0, "exit_generation": 0,
    }
    marks_total = {"status": 0, "bar": 0, "suspended_carry_forward": 0, "non_suspended_bar": 0}
    previous_value: float | None = None
    for day in dates:
        portfolio.unlock_frozen_lots(day)
        for fill in fills_by_date[day]:
            direction = intents[fill.order_id].intent
            gross, commission, stamp, transfer, total_fee, net_cash_flow = calculate_transaction_costs(
                direction, fill.fill_quantity, fill.fill_price,
                commission_rate=0.0003, min_commission=5.0,
                stamp_duty_rate=0.001, transfer_fee_rate=0.0,
            )
            portfolio.cash += net_cash_flow
            if direction == "buy":
                try:
                    portfolio.add_position(fill.symbol, fill.fill_quantity, fill.fill_price, day, calendar)
                except Exception as exc:
                    raise LedgerObservationError(f"buy ledger application failed: {fill.fill_id}") from exc
            else:
                try:
                    portfolio.reduce_position(fill.symbol, fill.fill_quantity)
                except Exception as exc:
                    raise LedgerObservationError(f"sell ledger application failed: {fill.fill_id}") from exc
            portfolio.validate_invariants()
            consumed.append(fill.fill_id)
            costs.append({
                "fill_id": fill.fill_id, "order_id": fill.order_id,
                "symbol": fill.symbol, "date": day.isoformat(), "direction": direction,
                "quantity": fill.fill_quantity, "price": fill.fill_price,
                "gross_amount": gross, "commission": commission,
                "stamp_duty": stamp, "transfer_fee": transfer,
                "total_fee": total_fee, "net_cash_flow": net_cash_flow,
            })
        marks = _mark_positions(data_source, portfolio, day, operation_counts)
        for key, value in marks.items():
            marks_total[key] += value
        row, previous_value = _make_observation(portfolio, day, previous_value)
        observations.append(row)
    if tuple(consumed) != tuple(fill.fill_id for fill in event.fills):
        _raise("not every fill was consumed exactly once")
    derived = {
        symbol: {
            "quantity": position.quantity,
            "avg_cost": float(position.avg_cost),
            "last_price": float(position.last_price),
            "sellable_quantity": position.sellable_quantity,
            "predecessor_expected_available": False,
        }
        for symbol, position in sorted(portfolio.positions.items())
    }
    operation_counts.update(marks_total)
    return LedgerReplay(tuple(observations), portfolio, tuple(consumed), tuple(costs), operation_counts, derived)


def validate_observation_rows(
    rows: list[dict[str, object]] | tuple[dict[str, object], ...],
    expected_dates: Iterable[date],
    *,
    allowed_end: date = IS_END,
) -> None:
    expected = tuple(expected_dates)
    if len(rows) != len(expected):
        _raise("observation date count mismatch")
    seen: list[date] = []
    previous: float | None = None
    fields = {"date", "cash", "portfolio_value", "gross_exposure", "net_exposure", "positions_value", "daily_return", "position_values_by_symbol"}
    for row, expected_day in zip(rows, expected):
        if set(row) != fields:
            _raise("observation schema mismatch")
        try:
            day = date.fromisoformat(str(row["date"]))
        except (TypeError, ValueError) as exc:
            raise LedgerObservationError("invalid observation date") from exc
        if day != expected_day or day > allowed_end or day >= OOS_START or day in seen:
            _raise("observation date order/gap/future mismatch")
        seen.append(day)
        for key in ("cash", "portfolio_value", "gross_exposure", "net_exposure", "positions_value", "daily_return"):
            if not _finite(row[key]):
                _raise(f"non-finite observation field: {key}")
        values = row["position_values_by_symbol"]
        if not isinstance(values, dict) or any(not isinstance(symbol, str) or not _finite(value) or float(value) < 0 for symbol, value in values.items()):
            _raise("invalid position values")
        if sum(values.values()) != row["positions_value"] or row["cash"] + row["positions_value"] != row["portfolio_value"]:
            _raise("observation arithmetic mismatch")
        if row["gross_exposure"] != row["positions_value"] or row["net_exposure"] != row["positions_value"]:
            _raise("observation exposure mismatch")
        expected_return = 0.0 if previous is None else row["portfolio_value"] / previous - 1.0
        if row["daily_return"] != expected_return:
            _raise("observation return mismatch")
        previous = float(row["portfolio_value"])


def authoritative_final_match(
    portfolio: PortfolioState | None,
    expected: DailyPortfolioSnapshot,
) -> dict[str, object]:
    derived_unavailable = {
        "comparable": False,
        "reason": "20960 DailyPortfolioSnapshot has no predecessor expected field",
    }
    if portfolio is None:
        return {"all_equal": False, "average_cost": derived_unavailable, "last_price": derived_unavailable}
    actual_positions = tuple(sorted((symbol, position.quantity) for symbol, position in portfolio.positions.items()))
    comparisons = {
        "cash": {"actual": portfolio.cash, "expected": expected.cash, "equal": portfolio.cash == expected.cash},
        "positions_symbol_quantity": {"actual": actual_positions, "expected": tuple(sorted(expected.positions)), "equal": actual_positions == tuple(sorted(expected.positions))},
        "portfolio_value": {"actual": portfolio.total_value(), "expected": expected.portfolio_value, "equal": portfolio.total_value() == expected.portfolio_value},
        "snapshot_date": {"actual": expected.snapshot_date.isoformat(), "expected": expected.snapshot_date.isoformat(), "equal": True},
        "average_cost": derived_unavailable,
        "last_price": derived_unavailable,
    }
    comparisons["all_equal"] = all(comparisons[key]["equal"] for key in ("cash", "positions_symbol_quantity", "portfolio_value", "snapshot_date"))
    return comparisons
