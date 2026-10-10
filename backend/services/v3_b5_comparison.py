"""V3-only theoretical fractional benchmark/control comparison producer.

This module deliberately has no order, fill, lot-size, or generic benchmark
abstraction.  It consumes the already verified v3 PIT inputs and produces two
non-executable comparison indices.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Iterable


ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "v3_b5_comparison.v1"
SCHEMA_KIND = "theoretical_fractional_comparison_index"
IS_START = date(2025, 6, 27)
IS_END = date(2026, 3, 19)
OOS_START = date(2026, 3, 20)
INITIAL_NAV = 1.0
BASE_COST_BPS = 8.0431006062
STRESS_COST_BPS = 20.8425059905
BASE_COST_ID = "991f167678ebb2e9"
BASE_COST_MANIFEST_SHA = "b89d701a6d5fc3cc36757f37823f6dfe29c61d704a6dd360ed321a373aff2564"
OBSERVATION_ID = "f28096063549c23f"
OBSERVATION_MANIFEST_SHA = "32dbd944992c71ce39bad5d856a3ec07529852fbb8e2022f72287d23bc38632c"
OBSERVATION_SHA = "55373c7e7c189663241f48d37b35505f99284d20c7eb07d85b7dec8a0208f842"
INVENTORY_ID = "2fe8321a5f644b9b"
INVENTORY_MANIFEST_SHA = "e23b94ac7294003a9b28db28f270bf2f19eaff40da9a03507adda87aad219a2c"
CALENDAR_DATE_SET_SHA = "62b6880c9acc381d273ceee40c900a486c3f83488600c042c43ce1d8f9cbb194"


class ComparisonError(ValueError):
    """A comparison input or arithmetic contract violation."""


def canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _finite(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _date_value(value: date | str) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ComparisonError(f"invalid ISO date: {value!r}") from exc


def build_weekly_schedule(common_dates: Iterable[date], start: date, end: date) -> list[dict[str, str]]:
    dates = sorted(set(common_dates))
    selected = [day for day in dates if start <= day <= end]
    if not selected:
        raise ComparisonError("comparison has no IS common dates")
    result: list[dict[str, str]] = []
    previous_week: tuple[int, int] | None = None
    for execution_day in selected:
        week = execution_day.isocalendar()[:2]
        if week == previous_week:
            continue
        prior = [day for day in dates if day < execution_day]
        if not prior:
            raise ComparisonError(f"no completed common as_of before {execution_day}")
        result.append({
            "formation_date": execution_day.isoformat(),
            "as_of_date": prior[-1].isoformat(),
            "execution_date": execution_day.isoformat(),
        })
        previous_week = week
    return result


def _validate_member(member: dict[str, Any]) -> tuple[str, str, str]:
    symbol = member.get("symbol", member.get("ts_code"))
    code = member.get("l1_code")
    name = member.get("l1_name")
    if not isinstance(symbol, str) or not symbol.endswith((".SH", ".SZ")):
        raise ComparisonError(f"non-SH/SZ or invalid comparison symbol: {symbol!r}")
    if not isinstance(code, str) or not code or not isinstance(name, str) or not name:
        raise ComparisonError(f"missing active SW2021 industry for {symbol}")
    return symbol, code, name


def industry_weights(members: Iterable[dict[str, Any]]) -> dict[str, float]:
    grouped: dict[str, list[str]] = {}
    names: dict[str, str] = {}
    seen: dict[str, str] = {}
    for member in members:
        symbol, code, name = _validate_member(member)
        if symbol in seen and seen[symbol] != code:
            raise ComparisonError(f"ambiguous active L1 code: {symbol}")
        if symbol in seen:
            continue
        seen[symbol] = code
        names[code] = name
        grouped.setdefault(code, []).append(symbol)
    if not grouped:
        raise ComparisonError("empty benchmark eligible universe")
    industry_weight = 1.0 / len(grouped)
    weights: dict[str, float] = {}
    for code in sorted(grouped):
        member_weight = industry_weight / len(grouped[code])
        for symbol in sorted(grouped[code]):
            weights[symbol] = member_weight
    if not math.isclose(sum(weights.values()), 1.0, rel_tol=0.0, abs_tol=1e-12):
        raise ComparisonError("benchmark target weights do not sum to one")
    return weights


def control_weights(members: Iterable[dict[str, Any]]) -> dict[str, float]:
    symbols = sorted({_validate_member(member)[0] for member in members})
    if not symbols:
        raise ComparisonError("empty control eligible universe")
    weight = 1.0 / len(symbols)
    result = {symbol: weight for symbol in symbols}
    if not math.isclose(sum(result.values()), 1.0, rel_tol=0.0, abs_tol=1e-12):
        raise ComparisonError("control target weights do not sum to one")
    return result


@dataclass(frozen=True)
class RebalanceResult:
    positions: dict[str, float]
    cash: float
    turnover: float
    base_cost: float
    stress_cost: float
    executed_weights: dict[str, float]
    blocked_entries: int
    blocked_exits: int


def rebalance_fractional(
    *,
    positions: dict[str, float],
    cash: float,
    target_weights: dict[str, float],
    execution_prices: dict[str, float],
    tradable: dict[str, bool],
    nav: float,
) -> RebalanceResult:
    if not _finite(cash) or cash < 0 or not _finite(nav) or nav <= 0:
        raise ComparisonError("invalid pre-trade NAV/cash")
    if any(not _finite(weight) or weight < 0 for weight in target_weights.values()):
        raise ComparisonError("invalid target weight")
    if not math.isclose(sum(target_weights.values()), 1.0, rel_tol=0.0, abs_tol=1e-12):
        raise ComparisonError("target weights must sum to one")
    current = {symbol: float(units) for symbol, units in positions.items()}
    for symbol, units in current.items():
        if not _finite(units) or units < 0 or not _finite(execution_prices.get(symbol)) or execution_prices[symbol] <= 0:
            raise ComparisonError(f"invalid existing position price/units: {symbol}")
    pretrade_positions_value = sum(units * execution_prices[symbol] for symbol, units in current.items())
    if not math.isclose(cash + pretrade_positions_value, nav, rel_tol=0.0, abs_tol=1e-12):
        raise ComparisonError("pre-trade NAV/cash mismatch")
    cash_after = float(cash)
    sell_proceeds = 0.0
    blocked_entries = 0
    blocked_exits = 0

    # Sell/release every position that is executable at the open before adding targets.
    for symbol in list(current):
        desired = target_weights.get(symbol, 0.0)
        if desired > 0 and tradable.get(symbol, False):
            proceeds = current[symbol] * execution_prices[symbol]
            sell_proceeds += proceeds
            cash_after += proceeds
            del current[symbol]
        elif desired <= 0:
            if tradable.get(symbol, False):
                proceeds = current[symbol] * execution_prices[symbol]
                sell_proceeds += proceeds
                cash_after += proceeds
                del current[symbol]
            else:
                blocked_exits += 1

    # Scale every executable target by one cash cap; blocked targets keep cash.
    desired_buys: dict[str, float] = {}
    for symbol in sorted(target_weights):
        weight = target_weights[symbol]
        if symbol in current:
            continue  # blocked existing position is carried without reallocation
        if not tradable.get(symbol, False):
            blocked_entries += 1
            continue
        price = execution_prices.get(symbol)
        if not _finite(price) or price <= 0:
            raise ComparisonError(f"missing/invalid executable open: {symbol}")
        desired_buys[symbol] = max(nav * weight, 0.0)
    desired_buy_total = sum(desired_buys.values())
    common_scale = 0.0 if desired_buy_total == 0.0 else min(1.0, max(0.0, cash_after) / desired_buy_total)
    actual_buy_total = 0.0
    for symbol in sorted(desired_buys):
        allocated = desired_buys[symbol] * common_scale
        if allocated == 0.0:
            continue
        current[symbol] = allocated / execution_prices[symbol]
        actual_buy_total += allocated
    cash_after -= actual_buy_total
    if cash_after < 0.0:
        if cash_after >= -1e-12:
            cash_after = 0.0
        else:
            raise ComparisonError("cash allocation exceeds available cash")
    executed_weights = {
        symbol: units * execution_prices[symbol] / nav
        for symbol, units in current.items()
    }
    turnover = (sell_proceeds + actual_buy_total) / nav
    base_cost = turnover * BASE_COST_BPS / 10000.0
    stress_cost = turnover * STRESS_COST_BPS / 10000.0
    return RebalanceResult(
        positions=current,
        cash=cash_after,
        turnover=turnover,
        base_cost=base_cost,
        stress_cost=stress_cost,
        executed_weights=executed_weights,
        blocked_entries=blocked_entries,
        blocked_exits=blocked_exits,
    )


def validate_daily_rows(rows: list[dict[str, Any]], expected_dates: Iterable[date]) -> None:
    dates = [_date_value(day) for day in expected_dates]
    if len(rows) != len(dates):
        raise ComparisonError("daily row count mismatch")
    seen: set[date] = set()
    previous_nav: float | None = None
    for row, expected in zip(rows, dates):
        actual = _date_value(row.get("date"))
        if actual != expected or actual in seen:
            raise ComparisonError("daily dates are not ordered and gap-free")
        seen.add(actual)
        for key in ("gross_nav", "base_net_nav", "stress_net_nav", "daily_return"):
            if not _finite(row.get(key)) or float(row[key]) <= 0 and key != "daily_return":
                raise ComparisonError(f"invalid daily field: {key}")
        expected_return = 0.0 if previous_nav is None else float(row["base_net_nav"]) / previous_nav - 1.0
        if not math.isclose(float(row["daily_return"]), expected_return, rel_tol=0.0, abs_tol=1e-12):
            raise ComparisonError(f"daily return arithmetic mismatch: {actual}")
        previous_nav = float(row["base_net_nav"])


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def calculate_metrics(
    strategy_returns: list[float],
    comparator_returns: list[float],
    strategy_nav: list[float],
    comparator_nav: list[float],
) -> dict[str, float]:
    if len(strategy_returns) != len(comparator_returns) or len(strategy_returns) < 2:
        raise ComparisonError("insufficient comparison return sample")
    if len(strategy_nav) != len(comparator_nav) or len(strategy_nav) != len(strategy_returns):
        raise ComparisonError("comparison NAV/date length mismatch")
    if any(not _finite(value) for value in strategy_returns + comparator_returns + strategy_nav + comparator_nav):
        raise ComparisonError("non-finite comparison metric input")
    comparator_mean = _mean(comparator_returns)
    strategy_mean = _mean(strategy_returns)
    cov = sum((a - strategy_mean) * (b - comparator_mean) for a, b in zip(strategy_returns, comparator_returns))
    var = sum((b - comparator_mean) ** 2 for b in comparator_returns)
    strategy_var = sum((a - strategy_mean) ** 2 for a in strategy_returns)
    if var <= 0 or strategy_var <= 0:
        raise ComparisonError("comparison return variance is zero")
    beta = cov / var
    correlation = cov / math.sqrt(strategy_var * var)
    strategy_cum = strategy_nav[-1] / strategy_nav[0] - 1.0
    comparator_cum = comparator_nav[-1] / comparator_nav[0] - 1.0
    return {
        "strategy_cumulative_return": strategy_cum,
        "comparator_cumulative_return": comparator_cum,
        "relative_return": strategy_cum - comparator_cum,
        "beta": beta,
        "correlation": correlation,
    }


def _monthly_key(day: str) -> str:
    return day[:7]


def build_concentration_audit(rows: list[dict[str, Any]]) -> dict[str, Any]:
    symbol_totals: dict[str, float] = {}
    month_totals: dict[str, float] = {}
    for row in rows:
        for symbol, value in row.get("position_values_by_symbol", {}).items():
            if not _finite(value) or value < 0:
                raise ComparisonError("invalid position value in concentration audit")
            symbol_totals[symbol] = symbol_totals.get(symbol, 0.0) + float(value)
            month = _monthly_key(row["date"])
            month_totals[month] = month_totals.get(month, 0.0) + float(value)
    symbol_total = sum(symbol_totals.values())
    month_total = sum(month_totals.values())
    if symbol_total <= 0 or month_total <= 0:
        raise ComparisonError("empty concentration audit")
    return {
        "symbol_marked_value_contribution": {key: value / symbol_total for key, value in sorted(symbol_totals.items())},
        "month_marked_value_contribution": {key: value / month_total for key, value in sorted(month_totals.items())},
    }


class _FormalComparisonSource:
    """One-process bounded cache around the formal adapter."""

    def __init__(
        self,
        adapter: Any,
        industry_index: dict[str, list[dict[str, Any]]],
        lifecycle: dict[str, tuple[str, str | None]] | None = None,
        coverage_unavailable: set[tuple[str, str]] | dict[tuple[str, str], dict[str, Any]] | None = None,
    ):
        self.adapter = adapter
        self.industry_index = industry_index
        self.lifecycle = lifecycle
        self.coverage_unavailable = coverage_unavailable or set()
        self._eligible_cache: dict[tuple[date, date], list[dict[str, Any]]] = {}
        self._last_prices: dict[str, float] = {}
        self.operation_counts: dict[str, int] = {}
        self.status_counts: dict[str, int] = {}

    def _count(self, name: str) -> None:
        self.operation_counts[name] = self.operation_counts.get(name, 0) + 1

    def _coverage_row(self, symbol: str, day: date) -> dict[str, Any] | None:
        if not isinstance(self.coverage_unavailable, dict):
            return None
        row = self.coverage_unavailable.get((day.strftime("%Y%m%d"), symbol))
        return row if isinstance(row, dict) else None

    def _p2_prior_mark(self, symbol: str, day: date, *, held: bool) -> float:
        row = self._coverage_row(symbol, day)
        if row is None:
            raise ComparisonError(f"unavailable mark has no exact coverage row: {symbol}/{day}")
        if not held:
            raise ComparisonError(f"unavailable mark requires existing held position: {symbol}/{day}")
        expected_key = (day.strftime("%Y%m%d"), symbol)
        if (row.get("execution_date"), row.get("symbol")) != expected_key:
            raise ComparisonError(f"unavailable mark coverage key mismatch: {symbol}/{day}")
        if row.get("status") != "unavailable" or row.get("reason") != "required_history_missing":
            raise ComparisonError(f"unavailable mark coverage admission mismatch: {symbol}/{day}")
        missing_fields = row.get("missing_fields")
        if not isinstance(missing_fields, list) or "daily.close" not in missing_fields:
            raise ComparisonError(f"unavailable mark missing_fields mismatch: {symbol}/{day}")
        try:
            as_of = date.fromisoformat(str(row.get("as_of_date")))
        except (TypeError, ValueError) as exc:
            raise ComparisonError(f"unavailable mark as_of_date invalid: {symbol}/{day}") from exc
        if as_of >= day:
            raise ComparisonError(f"unavailable mark as_of_date is not prior: {symbol}/{day}")
        if self.lifecycle is None or symbol not in self.lifecycle:
            raise ComparisonError(f"unavailable mark lifecycle missing: {symbol}/{day}")
        list_date, delist_date = self.lifecycle[symbol]
        day_key = day.strftime("%Y%m%d")
        if list_date > day_key or (delist_date is not None and day_key >= delist_date):
            raise ComparisonError(f"unavailable mark lifecycle is not active: {symbol}/{day}")
        if not self.adapter.is_eligible(symbol, day):
            raise ComparisonError(f"unavailable mark lifecycle is not active: {symbol}/{day}")
        previous = self._last_prices.get(symbol)
        if previous is None or not _finite(previous) or previous <= 0:
            raise ComparisonError(f"unavailable mark has no prior valid mark: {symbol}/{day}")
        return float(previous)

    def members_for(self, as_of: date, execution: date) -> list[dict[str, Any]]:
        key = (as_of, execution)
        if key in self._eligible_cache:
            return self._eligible_cache[key]
        members: list[dict[str, Any]] = []
        for symbol in self.adapter.symbols_as_of(as_of):
            if not symbol.endswith((".SH", ".SZ")):
                continue
            if self.lifecycle is not None:
                lifecycle_dates = self.lifecycle.get(symbol)
                if lifecycle_dates is None:
                    continue
                list_date, delist_date = lifecycle_dates
                as_of_key = as_of.strftime("%Y%m%d")
                if list_date > as_of_key or (delist_date is not None and as_of_key >= delist_date):
                    continue
            if (execution.strftime("%Y%m%d"), symbol) in self.coverage_unavailable:
                self.status_counts["coverage_unavailable"] = self.status_counts.get("coverage_unavailable", 0) + 1
                continue
            try:
                if not self.adapter.is_eligible(symbol, as_of):
                    continue
                active = [row for row in self.industry_index.get(symbol, []) if row["in_date"] <= as_of and (row["out_date"] is None or as_of <= row["out_date"])]
                codes = {(row["l1_code"], row["l1_name"]) for row in active}
                if len(codes) != 1:
                    raise ComparisonError(f"missing/ambiguous active L1: {symbol}/{as_of}")
                status = self.adapter.get_status(symbol, execution)
                if status.is_st or status.is_suspended:
                    self.status_counts["st_or_suspended_excluded"] = self.status_counts.get("st_or_suspended_excluded", 0) + 1
                    continue
                liquidity = self.adapter.derive_liquidity(symbol, execution)
                if liquidity.get("status") == "data_fault":
                    raise ComparisonError(f"liquidity data fault: {symbol}/{execution}")
                if liquidity.get("status") != "qualified":
                    self.status_counts[str(liquidity.get("status"))] = self.status_counts.get(str(liquidity.get("status")), 0) + 1
                    continue
                code, name = next(iter(codes))
                members.append({"symbol": symbol, "l1_code": code, "l1_name": name})
            except (FileNotFoundError, KeyError, TypeError, ValueError) as exc:
                raise ComparisonError(f"formal eligibility fault: {symbol}/{execution}: {exc}") from exc
        if not members:
            raise ComparisonError(f"empty eligible universe: {execution}")
        self._eligible_cache[key] = sorted(members, key=lambda row: row["symbol"])
        return self._eligible_cache[key]

    def execution(self, symbol: str, day: date, *, held: bool = False) -> tuple[float | None, bool, str]:
        coverage_row = self._coverage_row(symbol, day)
        try:
            status = self.adapter.get_status(symbol, day)
        except (FileNotFoundError, KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, KeyError) and coverage_row is not None:
                previous = self._p2_prior_mark(symbol, day, held=held)
                return previous, False, "unavailable_mark_carry_locked"
            raise ComparisonError(f"execution status fault: {symbol}/{day}: {exc}") from exc
        try:
            bar = self.adapter.get_bar(symbol, day)
        except (FileNotFoundError, KeyError, TypeError, ValueError) as exc:
            if status.is_suspended:
                return None, False, "suspended"
            if coverage_row is not None:
                previous = self._p2_prior_mark(symbol, day, held=held)
                return previous, False, "unavailable_mark_carry_locked"
            raise ComparisonError(f"non-suspended missing execution open: {symbol}/{day}: {exc}") from exc
        if status.is_suspended:
            raise ComparisonError(f"formal suspension conflicts with execution daily row: {symbol}/{day}")
        if status.is_st or status.is_limit_up:
            return None, False, "not_buyable"
        if status.is_limit_down:
            return None, False, "not_sellable"
        return float(bar.open), True, "tradable"

    def mark(self, symbol: str, day: date) -> tuple[float, str]:
        coverage_row = self._coverage_row(symbol, day)
        status_observed = False
        try:
            status = self.adapter.get_status(symbol, day)
            status_observed = True
            try:
                bar = self.adapter.get_bar(symbol, day)
            except (FileNotFoundError, KeyError, TypeError, ValueError) as bar_exc:
                if status.is_suspended:
                    previous = self._last_prices.get(symbol)
                    if previous is None:
                        raise ComparisonError(f"suspended position has no prior mark: {symbol}/{day}") from bar_exc
                    return previous, "suspended_carry"
                if coverage_row is not None:
                    previous = self._p2_prior_mark(symbol, day, held=True)
                    self.status_counts["unavailable_mark_carry"] = self.status_counts.get("unavailable_mark_carry", 0) + 1
                    return previous, "unavailable_mark_carry"
                raise
            if status.is_suspended:
                raise ComparisonError(f"formal suspension conflicts with daily mark: {symbol}/{day}")
            price = float(bar.close)
            if not _finite(price) or price <= 0:
                raise ComparisonError(f"invalid close: {symbol}/{day}")
            self._last_prices[symbol] = price
            return price, "close"
        except ComparisonError:
            raise
        except (FileNotFoundError, KeyError, TypeError, ValueError) as exc:
            if coverage_row is not None:
                if not isinstance(exc, KeyError):
                    raise ComparisonError(f"formal status/bar fault: {symbol}/{day}") from exc
                if status_observed:
                    previous = self._p2_prior_mark(symbol, day, held=True)
                    self.status_counts["unavailable_mark_carry"] = self.status_counts.get("unavailable_mark_carry", 0) + 1
                    return previous, "unavailable_mark_carry"
                previous = self._p2_prior_mark(symbol, day, held=True)
                try:
                    self.adapter.get_bar(symbol, day)
                except KeyError:
                    self.status_counts["unavailable_mark_carry"] = self.status_counts.get("unavailable_mark_carry", 0) + 1
                    return previous, "unavailable_mark_carry"
                except (FileNotFoundError, TypeError, ValueError) as bar_exc:
                    raise ComparisonError(f"unavailable mark daily evidence fault: {symbol}/{day}") from bar_exc
                raise ComparisonError(f"coverage unavailable conflicts with formal daily mark: {symbol}/{day}") from exc
            # The existing force-liquidation contract uses last valid close minus
            # the system 5% penalty; no synthetic price is created here.
            if not self.adapter.is_eligible(symbol, day):
                previous = self._last_prices.get(symbol)
                if previous is None:
                    raise ComparisonError(f"delisted position has no reliable mark: {symbol}/{day}") from exc
                self._last_prices.pop(symbol, None)
                return previous * 0.95, "force_liquidation_last_tradable_with_penalty"
            raise ComparisonError(f"non-suspended missing mark: {symbol}/{day}: {exc}") from exc

    def audit(self) -> dict[str, Any]:
        adapter_audit = self.adapter.audit() if hasattr(self.adapter, "audit") else {}
        return {"operation_counts": dict(sorted(self.operation_counts.items())), "status_counts": dict(sorted(self.status_counts.items())), "read_audit": adapter_audit}


def run_fractional_index(
    *,
    kind: str,
    source: _FormalComparisonSource,
    dates: tuple[date, ...],
    schedule: list[dict[str, str]],
    strategy_observations: list[dict[str, Any]],
    cost_binding: dict[str, str] | None = None,
    observation_binding: dict[str, str] | None = None,
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    if kind not in {"benchmark", "control"}:
        raise ComparisonError(f"unknown comparison kind: {kind}")
    cost_binding = cost_binding or {"artifact_id": BASE_COST_ID, "manifest_sha256": BASE_COST_MANIFEST_SHA}
    observation_binding = observation_binding or {"artifact_id": OBSERVATION_ID, "manifest_sha256": OBSERVATION_MANIFEST_SHA, "observations_sha256": OBSERVATION_SHA}
    schedule_by_day = {date.fromisoformat(item["execution_date"]): item for item in schedule}
    started_at = perf_counter()
    total_rebalances = sum(day in schedule_by_day for day in dates)
    completed_rebalances = 0
    positions: dict[str, float] = {}
    cash = INITIAL_NAV
    base_cost_total = 0.0
    stress_cost_total = 0.0
    rows: list[dict[str, Any]] = []
    rebalances: list[dict[str, Any]] = []
    previous_base_nav: float | None = None
    strategy_by_date = {row["date"]: row for row in strategy_observations}
    if [row["date"] for row in strategy_observations] != [day.isoformat() for day in dates]:
        raise ComparisonError("strategy observation dates do not exactly match comparison IS")

    for day in dates:
        if day in schedule_by_day:
            item = schedule_by_day[day]
            members = source.members_for(date.fromisoformat(item["as_of_date"]), day)
            targets = industry_weights(members) if kind == "benchmark" else control_weights(members)
            execution_prices: dict[str, float] = {}
            tradable: dict[str, bool] = {}
            reasons: dict[str, str] = {}
            for symbol in sorted(set(positions) | set(targets)):
                price, can_trade, reason = source.execution(symbol, day, held=symbol in positions)
                if price is None:
                    price = source._last_prices.get(symbol)
                if price is not None:
                    execution_prices[symbol] = price
                tradable[symbol] = can_trade
                reasons[symbol] = reason
            pre_values = {symbol: units * execution_prices[symbol] for symbol, units in positions.items() if symbol in execution_prices}
            pre_nav = cash + sum(pre_values.values())
            if pre_nav <= 0 or not _finite(pre_nav):
                raise ComparisonError(f"invalid pre-trade NAV: {day}")
            rebalance = rebalance_fractional(
                positions=positions,
                cash=cash,
                target_weights=targets,
                execution_prices=execution_prices,
                tradable=tradable,
                nav=pre_nav,
            )
            positions = rebalance.positions
            cash = rebalance.cash
            base_cost_total += rebalance.base_cost
            stress_cost_total += rebalance.stress_cost
            rebalances.append({
                **item,
                "target_weights": {symbol: targets[symbol] for symbol in sorted(targets)},
                "executed_weights": {symbol: rebalance.executed_weights[symbol] for symbol in sorted(rebalance.executed_weights)},
                "turnover": rebalance.turnover,
                "base_cost": rebalance.base_cost,
                "stress_cost": rebalance.stress_cost,
                "blocked_entries": rebalance.blocked_entries,
                "blocked_exits": rebalance.blocked_exits,
                "status_reasons": reasons,
                "eligible_count": len(members),
                "industry_count": len({member["l1_code"] for member in members}),
            })
            completed_rebalances += 1
            if progress is not None:
                progress({
                    "kind": kind,
                    "phase": "rebalance_completed",
                    "completed_rebalances": completed_rebalances,
                    "total_rebalances": total_rebalances,
                    "execution_date": day.isoformat(),
                    "elapsed_seconds": max(perf_counter() - started_at, 0.0),
                })

        position_values: dict[str, float] = {}
        mark_reasons: dict[str, str] = {}
        for symbol in list(positions):
            price, reason = source.mark(symbol, day)
            mark_reasons[symbol] = reason
            if reason == "force_liquidation_last_tradable_with_penalty":
                cash += positions[symbol] * price
                del positions[symbol]
                continue
            position_values[symbol] = positions[symbol] * price
        gross_nav = cash + sum(position_values.values())
        base_net_nav = gross_nav - base_cost_total
        stress_net_nav = gross_nav - stress_cost_total
        if not _finite(gross_nav) or not _finite(base_net_nav) or not _finite(stress_net_nav) or min(gross_nav, base_net_nav, stress_net_nav) <= 0:
            raise ComparisonError(f"invalid NAV at {day}")
        daily_return = 0.0 if previous_base_nav is None else base_net_nav / previous_base_nav - 1.0
        previous_base_nav = base_net_nav
        rows.append({
            "date": day.isoformat(),
            "gross_nav": gross_nav,
            "base_net_nav": base_net_nav,
            "stress_net_nav": stress_net_nav,
            "daily_return": daily_return,
            "cash": cash,
            "base_cash": cash - base_cost_total,
            "stress_cash": cash - stress_cost_total,
            "positions_value": sum(position_values.values()),
            "position_values_by_symbol": {symbol: position_values[symbol] for symbol in sorted(position_values)},
            "weights_by_symbol": {symbol: position_values[symbol] / gross_nav for symbol in sorted(position_values)},
            "mark_reasons": mark_reasons,
            "eligible_count": rebalances[-1]["eligible_count"] if rebalances and rebalances[-1]["execution_date"] <= day.isoformat() else None,
            "unavailable_count": sum(1 for reason in mark_reasons.values() if reason in {"suspended_carry", "unavailable_mark_carry"}),
        })
    validate_daily_rows(rows, dates)
    strategy_returns = [float(row["daily_return"]) for row in strategy_observations]
    strategy_nav = [float(row["portfolio_value"]) / float(strategy_observations[0]["portfolio_value"]) for row in strategy_observations]
    comparator_returns = [float(row["daily_return"]) for row in rows]
    comparator_nav = [float(row["base_net_nav"]) for row in rows]
    metrics = calculate_metrics(strategy_returns, comparator_returns, strategy_nav, comparator_nav)
    metrics["stress_cumulative_return"] = rows[-1]["stress_net_nav"] / rows[0]["stress_net_nav"] - 1.0
    metrics["gross_cumulative_return"] = rows[-1]["gross_nav"] / rows[0]["gross_nav"] - 1.0
    return {
        "schema_kind": SCHEMA_KIND,
        "comparison_kind": kind,
        "initial_nav": INITIAL_NAV,
        "is_range": {"start": dates[0].isoformat(), "end": dates[-1].isoformat(), "count": len(dates), "oos_start": OOS_START.isoformat()},
        "weekly_schedule": schedule,
        "daily_rows": rows,
        "rebalances": rebalances,
        "metrics": metrics,
        "concentration_audit": build_concentration_audit(rows),
        "availability_mark_carry_event_count": sum(
            1 for row in rows for reason in row.get("mark_reasons", {}).values() if reason == "unavailable_mark_carry"
        ),
        "cost": {"base_bps": BASE_COST_BPS, "stress_bps": STRESS_COST_BPS, "base_total": base_cost_total, "stress_total": stress_cost_total, "artifact_id": cost_binding["artifact_id"], "artifact_manifest_sha256": cost_binding["manifest_sha256"]},
        "source_audit": source.audit(),
        "strategy_observation": dict(observation_binding),
        "non_executable": True,
        "algorithm": "v3_b5_theoretical_fractional_comparison_v1",
    }


class ReadBoundAdapter:
    """Read-only date guard for the comparison producer."""

    def __init__(self, raw: Any, allowed_end: date = IS_END):
        self._raw = raw
        self._allowed_end = allowed_end
        self._max_requested_date: date | None = None
        self._operation_counts: dict[str, int] = {}

    def _record(self, operation: str, day: date) -> None:
        if not isinstance(day, date) or day >= OOS_START or day > self._allowed_end:
            raise ComparisonError(f"comparison attempted future/OOS read: {operation}/{day}")
        self._operation_counts[operation] = self._operation_counts.get(operation, 0) + 1
        if self._max_requested_date is None or day > self._max_requested_date:
            self._max_requested_date = day

    def symbols_as_of(self, day: date):
        self._record("membership", day)
        return self._raw.symbols_as_of(day)

    def common_trading_dates(self, start: date, end: date):
        self._record("calendar", end)
        return self._raw.common_trading_dates(start, end)

    def is_eligible(self, symbol: str, day: date):
        self._record("lifecycle", day)
        return self._raw.is_eligible(symbol, day)

    def derive_liquidity(self, symbol: str, day: date):
        self._record("liquidity", day)
        return self._raw.derive_liquidity(symbol, day)

    def get_status(self, symbol: str, day: date):
        self._record("status", day)
        return self._raw.get_status(symbol, day)

    def get_bar(self, symbol: str, day: date):
        self._record("bar", day)
        return self._raw.get_bar(symbol, day)

    def audit(self) -> dict[str, Any]:
        return {
            "allowed_end": self._allowed_end.isoformat(),
            "oos_start": OOS_START.isoformat(),
            "max_requested_date": self._max_requested_date.isoformat() if self._max_requested_date else None,
            "oos_read_count": 0,
            "operation_counts": dict(sorted(self._operation_counts.items())),
        }
