"""Small independent one-symbol reference for the frozen Gate001 lifecycle.

This module intentionally does not call strategy_core signal, fill, fee, lot,
dividend-ledger, or metric helpers. It supports the one Gate001 ETF and its
single open buy/exit cycle; it is not a general backtest engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP
from collections.abc import Mapping, Sequence


CENT = Decimal("0.01")
TICK = Decimal("0.001")
LOT = 100
LIMIT_RATE = Decimal("0.10")
YEAR_DAYS = Decimal("365")


@dataclass(frozen=True)
class ReferenceRun:
    mode: str
    entry_signal_dates: tuple[date, ...]
    exit_signal_dates: tuple[date, ...]
    trades: tuple[dict[str, object], ...]
    daily_values: tuple[dict[str, object], ...]
    daily_open_cycle_pnl: tuple[dict[str, object], ...]
    completed_trade_profits: tuple[Decimal, ...]
    open_trade_profit: Decimal | None
    max_open_trade_floating_loss: Decimal
    open_trade_count: int
    open_quantity: int
    dividend_entitlement: Decimal
    pending_dividend_entitlement: Decimal
    terminal_cash: Decimal
    terminal_market_value: Decimal
    terminal_receivable: Decimal
    terminal_nav: Decimal
    interest_income: Decimal
    pending_at_end: int
    rejected: tuple[dict[str, object], ...]
    pending_limit_up_attempts: int


def run_one_symbol_reference(
    *,
    rows: Sequence[Mapping[str, object]],
    raw_dividend_events: Sequence[Mapping[str, object]],
    market_dates: Sequence[date],
    evaluation_dates: Sequence[date],
    anchor_date: date,
    symbol: str,
    strategy_name: str,
    strategy_version: str,
    initial_cash: Decimal | str | float,
    commission_rate: Decimal | str | float,
    minimum_commission: Decimal | str | float,
    stamp_duty_rate: Decimal | str | float,
    transfer_fee_rate: Decimal | str | float,
    slippage_rate: Decimal | str | float,
    cash_yield_annual_rate: Decimal | str | float,
    mode: str = "strategy",
    opening_capacity_rate: Decimal | str | float = Decimal("0.10"),
) -> ReferenceRun:
    """Independently run the fixed MA250/TP10 profile on one ETF data series."""
    if mode not in {"strategy", "buy_hold", "cash"}:
        raise ValueError("reference mode must be strategy, buy_hold, or cash")
    ordered_rows = sorted(rows, key=lambda row: _as_date(row["date"]))
    by_date = {_as_date(row["date"]): row for row in ordered_rows}
    if len(by_date) != len(ordered_rows):
        raise ValueError("reference market rows contain duplicate dates")
    full_dates = tuple(market_dates)
    eval_dates = tuple(evaluation_dates)
    if not eval_dates or tuple(sorted(set(eval_dates))) != eval_dates:
        raise ValueError("reference evaluation dates must be nonempty, unique, and ascending")
    if any(day not in by_date for day in eval_dates):
        raise ValueError("reference evaluation date is missing its market row")
    if any(left not in full_dates for left in eval_dates):
        raise ValueError("reference evaluation dates are absent from the date-only calendar")

    dividends = _normalize_dividends(raw_dividend_events)
    entry_dates = (
        _adjusted_ma250_downcross_dates(ordered_rows, anchor_date, set(eval_dates))
        if mode == "strategy"
        else ()
    )
    cash = _money(_decimal(initial_cash, "initial_cash"))
    annual_rate = _decimal(cash_yield_annual_rate, "cash_yield_annual_rate")
    fees = {
        "commission_rate": _decimal(commission_rate, "commission_rate"),
        "minimum_commission": _decimal(minimum_commission, "minimum_commission"),
        "stamp_duty_rate": _decimal(stamp_duty_rate, "stamp_duty_rate"),
        "transfer_fee_rate": _decimal(transfer_fee_rate, "transfer_fee_rate"),
        "slippage_rate": _decimal(slippage_rate, "slippage_rate"),
        "opening_capacity_rate": _decimal(opening_capacity_rate, "opening_capacity_rate"),
    }
    if annual_rate < 0 or any(value < 0 for value in fees.values()):
        raise ValueError("reference rates must be nonnegative")

    position: dict[str, object] | None = None
    pending: dict[str, object] | None = None
    receivables: dict[tuple[str, date], Decimal] = {}
    entitlements: dict[tuple[str, date], dict[str, object]] = {}
    completed_cycles: list[dict[str, object]] = []
    trade_rows: list[dict[str, object]] = []
    daily: list[dict[str, object]] = []
    daily_open_cycle_pnl: list[dict[str, object]] = []
    entry_signal_dates: list[date] = []
    exit_signal_dates: list[date] = []
    rejected: list[dict[str, object]] = []
    interest_income = Decimal("0.00")
    dividend_entitlement = Decimal("0.00")
    previous_eod_cash: Decimal | None = None
    previous_eod_date: date | None = None
    pending_limit_up_attempts = 0
    date_index = {day: index for index, day in enumerate(full_dates)}

    for trade_date in eval_dates:
        row = by_date[trade_date]

        # Prior EOD available cash is sampled before any current-open settlement.
        if previous_eod_cash is not None:
            if previous_eod_date is None:
                raise ValueError("reference prior cash has no evaluation date")
            elapsed = (trade_date - previous_eod_date).days
            if elapsed <= 0:
                raise ValueError("reference evaluation dates must increase")
            earned = _money(previous_eod_cash * annual_rate * Decimal(elapsed) / YEAR_DAYS)
            cash = _money(cash + earned)
            interest_income += earned

        if position is not None and _as_date(position["unlock_date"]) <= trade_date:
            position["sellable_quantity"] = int(position["quantity"])

        # Weekend/holiday pay dates settle at the first later session open.
        for event in dividends:
            if event["pay_date"] < trade_date:
                amount = receivables.pop(event["key"], None)
                if amount is not None:
                    cash = _money(cash + amount)

        if pending is not None and _as_date(pending["intended_date"]) <= trade_date:
            fill = _attempt_fill(
                pending=pending,
                trade_date=trade_date,
                row=row,
                rows_by_date=by_date,
                market_dates=full_dates,
                date_index=date_index,
                cash=cash,
                position=position,
                fees=fees,
            )
            if fill["kind"] == "blocked":
                if fill["reason"] == "limit_up":
                    pending_limit_up_attempts += 1
            elif fill["kind"] == "rejected":
                rejected.append({
                    "date": trade_date.isoformat(),
                    "reason": fill["reason"],
                    "order_id": pending["order_id"],
                })
                pending = None
            else:
                cash = Decimal(fill["cash"])
                trade_rows.append(fill["trade"])
                if pending["direction"] == "sell":
                    if position is None:
                        raise ValueError("reference sell fill has no active cycle")
                    position["sell_cash_flow"] = Decimal(fill["trade"]["net_cash_flow"])
                    position["sell_trade"] = fill["trade"]
                    completed_cycles.append(position)
                    position = None
                else:
                    position = fill["position"]
                pending = None

        if mode == "strategy" and trade_date in entry_dates:
            entry_signal_dates.append(trade_date)
        elif mode == "buy_hold" and trade_date == eval_dates[0]:
            entry_signal_dates.append(trade_date)

        take_profit = (
            mode == "strategy"
            and position is not None
            and Decimal(str(row["close"]))
            >= Decimal(str(position["avg_cost"])) * Decimal("1.10")
        )
        if take_profit:
            exit_signal_dates.append(trade_date)

        next_date = _next_date(full_dates, date_index, trade_date)
        if next_date is not None and next_date <= eval_dates[-1] and pending is None:
            if take_profit and position is not None:
                intended_quantity = int(position["quantity"])
                if int(position["sellable_quantity"]) < intended_quantity:
                    unlock_date = _as_date(position["unlock_date"])
                    if unlock_date <= next_date:
                        intended_quantity = int(position["quantity"])
                    else:
                        intended_quantity = int(position["sellable_quantity"])
                if intended_quantity > 0:
                    signal_type = "exit"
                    signal_date = trade_date
                    pending = _new_intent(
                        strategy_name,
                        strategy_version,
                        symbol,
                        signal_date,
                        signal_type,
                        next_date,
                        "sell",
                        intended_quantity,
                    )
            elif (
                mode != "cash"
                and position is None
                and trade_date in entry_signal_dates
                and (pending is None or pending["direction"] != "buy")
            ):
                signal_type = "entry"
                pending = _new_intent(
                    strategy_name,
                    strategy_version,
                    symbol,
                    trade_date,
                    signal_type,
                    next_date,
                    "buy",
                    LOT,
                )

        # Corporate-action entitlement is captured at EOD after this date's fills.
        for event in dividends:
            if event["record_date"] == trade_date:
                quantity = int(position["quantity"]) if position is not None else 0
                amount = _money(event["div_cash"] * Decimal(quantity))
                entitlements[event["key"]] = {
                    "quantity": quantity,
                    "amount": amount,
                    "cycle": position,
                }
        for event in dividends:
            if event["ex_date"] == trade_date:
                entitlement = entitlements.get(event["key"], {})
                quantity = int(entitlement.get("quantity", 0))
                amount = Decimal(entitlement.get("amount", Decimal("0.00")))
                receivables[event["key"]] = amount
                dividend_entitlement += amount
                cycle = entitlement.get("cycle")
                if cycle is not None and quantity > 0:
                    cycle["dividend_income"] = _money(
                        Decimal(cycle["dividend_income"]) + amount
                    )
                    sell_trade = cycle.get("sell_trade")
                    if sell_trade is not None:
                        sell_trade["cycle_profit"] = _money(
                            Decimal(cycle["buy_cash_flow"])
                            + Decimal(cycle["dividend_income"])
                            + Decimal(cycle["sell_cash_flow"])
                        )
        for event in dividends:
            if event["pay_date"] == trade_date:
                amount = receivables.pop(event["key"], None)
                if amount is not None:
                    cash = _money(cash + amount)

        quantity = int(position["quantity"]) if position is not None else 0
        market_value = _money(Decimal(quantity) * Decimal(str(row["close"])))
        receivable = _money(sum(receivables.values(), Decimal("0.00")))
        nav = _money(cash + market_value + receivable)
        daily.append({
            "date": trade_date,
            "cash": cash,
            "market_value": market_value,
            "receivable": receivable,
            "total_value": nav,
            "quantity": quantity,
        })
        if position is not None:
            cycle_profit = _money(
                Decimal(position["buy_cash_flow"])
                + Decimal(position["dividend_income"])
                + market_value
            )
            buy_date = _as_date(position["buy_date"])
            daily_open_cycle_pnl.append({
                "date": trade_date,
                "buy_date": buy_date,
                "quantity": quantity,
                "cycle_profit": cycle_profit,
                "holding_sessions": sum(
                    1 for day in eval_dates if buy_date <= day <= trade_date
                ),
            })
        previous_eod_cash = cash
        previous_eod_date = trade_date

    if pending is not None:
        rejected.append({
            "date": eval_dates[-1].isoformat(),
            "reason": "canceled_at_research_end",
            "order_id": pending["order_id"],
        })

    last = daily[-1]
    end_date = eval_dates[-1]
    pending_dividend_entitlement = _money(sum(
        (
            Decimal(entitlement["amount"])
            for event in dividends
            if event["ex_date"] > end_date
            and (entitlement := entitlements.get(event["key"])) is not None
        ),
        Decimal("0.00"),
    ))
    open_profit = None
    if position is not None:
        open_profit = (
            Decimal(position["buy_cash_flow"])
            + Decimal(position["dividend_income"])
            + Decimal(last["market_value"])
        )
    max_floating_loss = _money(max(
        (max(Decimal("0.00"), -Decimal(item["cycle_profit"])) for item in daily_open_cycle_pnl),
        default=Decimal("0.00"),
    ))
    return ReferenceRun(
        mode=mode,
        entry_signal_dates=tuple(entry_signal_dates),
        exit_signal_dates=tuple(exit_signal_dates),
        trades=tuple(trade_rows),
        daily_values=tuple(daily),
        daily_open_cycle_pnl=tuple(daily_open_cycle_pnl),
        completed_trade_profits=tuple(
            _money(
                Decimal(cycle["buy_cash_flow"])
                + Decimal(cycle["dividend_income"])
                + Decimal(cycle["sell_cash_flow"])
            )
            for cycle in completed_cycles
        ),
        open_trade_profit=open_profit,
        max_open_trade_floating_loss=max_floating_loss,
        open_trade_count=int(position is not None),
        open_quantity=int(position["quantity"]) if position is not None else 0,
        dividend_entitlement=_money(dividend_entitlement),
        pending_dividend_entitlement=pending_dividend_entitlement,
        terminal_cash=Decimal(last["cash"]),
        terminal_market_value=Decimal(last["market_value"]),
        terminal_receivable=Decimal(last["receivable"]),
        terminal_nav=Decimal(last["total_value"]),
        interest_income=_money(interest_income),
        pending_at_end=int(pending is not None),
        rejected=tuple(rejected),
        pending_limit_up_attempts=pending_limit_up_attempts,
    )


def reconcile_engine_result(engine_result, reference: ReferenceRun) -> dict[str, object]:
    """Compare actual engine trades and EOD account states to the independent run."""
    errors: list[str] = []
    if engine_result.entry_signal_count != len(reference.entry_signal_dates):
        errors.append("entry_signal_count")
    if engine_result.exit_signal_count != len(reference.exit_signal_dates):
        errors.append("exit_signal_count")
    if len(engine_result.trades) != len(reference.trades):
        errors.append("trade_count")
    else:
        for index, (actual, expected) in enumerate(zip(engine_result.trades, reference.trades, strict=True)):
            if actual.direction != expected["direction"]:
                errors.append(f"trade_{index}_direction")
            if actual.trade_date != expected["trade_date"]:
                errors.append(f"trade_{index}_date")
            if actual.quantity != expected["quantity"]:
                errors.append(f"trade_{index}_quantity")
            if Decimal(str(actual.price)) != Decimal(expected["price"]):
                errors.append(f"trade_{index}_price")
            if Decimal(str(actual.net_cash_flow)) != Decimal(expected["net_cash_flow"]):
                errors.append(f"trade_{index}_cash_flow")
            if Decimal(str(actual.total_fee)) != Decimal(expected["total_fee"]):
                errors.append(f"trade_{index}_fees")
            order_signal_date, order_type, intended = _signal_fields_from_order_id(actual.order_id)
            if order_signal_date != expected["signal_date"]:
                errors.append(f"trade_{index}_signal_date")
            if order_type != expected["signal_type"]:
                errors.append(f"trade_{index}_signal_type")
            if intended != expected["intended_date"]:
                errors.append(f"trade_{index}_intended_date")

    expected_dates = [item["date"] for item in reference.daily_values]
    actual_daily = list(engine_result.daily_portfolio_values)
    actual_dates = [item.date for item in actual_daily]
    if expected_dates and actual_dates == [expected_dates[0], *expected_dates]:
        actual_daily = actual_daily[1:]
    elif actual_dates != expected_dates:
        errors.append("daily_value_sequence")

    engine_eod: dict[date, object] = {}
    for item in actual_daily:
        if item.date in engine_eod:
            errors.append(f"duplicate_eod_{item.date}")
        engine_eod[item.date] = item
    if set(engine_eod) != {item["date"] for item in reference.daily_values}:
        errors.append("daily_value_dates")
    for expected in reference.daily_values:
        actual = engine_eod.get(expected["date"])
        if actual is None:
            continue
        for field in ("cash", "market_value", "total_value"):
            if Decimal(str(getattr(actual, field))) != Decimal(expected[field]):
                errors.append(f"daily_{expected['date']}_{field}")
        actual_receivable = (
            Decimal(str(actual.total_value))
            - Decimal(str(actual.cash))
            - Decimal(str(actual.market_value))
        )
        if actual_receivable != Decimal(expected["receivable"]):
            errors.append(f"daily_{expected['date']}_receivable")

    if Decimal(str(engine_result.final_capital)) != reference.terminal_nav:
        errors.append("terminal_nav")
    cancelled = sum(
        1 for order in engine_result.rejected_orders
        if order.rejection_reason and "canceled_at_research_end" in order.rejection_reason
    )
    if cancelled != reference.pending_at_end:
        errors.append("pending_order_cancellation")
    return {
        "status": "failed" if errors else "passed",
        "errors": errors,
        "engine_trade_count": len(engine_result.trades),
        "reference_trade_count": len(reference.trades),
        "engine_terminal_nav_cny": Decimal(str(engine_result.final_capital)),
        "reference_terminal_nav_cny": reference.terminal_nav,
        "terminal_nav_cny": reference.terminal_nav,
        "trade_economic_profit_cny": (
            sum(reference.completed_trade_profits, Decimal("0.00"))
            + (reference.open_trade_profit or Decimal("0.00"))
        ),
    }


def _adjusted_ma250_downcross_dates(
    rows: Sequence[Mapping[str, object]],
    anchor_date: date,
    evaluation_date_set: set[date],
) -> tuple[date, ...]:
    by_date = {_as_date(row["date"]): row for row in rows}
    if anchor_date not in by_date:
        raise ValueError(f"reference missing adjusted-price anchor {anchor_date}")
    anchor_factor = _decimal(by_date[anchor_date]["adj_factor"], "anchor adj_factor")
    if anchor_factor <= 0:
        raise ValueError("reference adjustment anchor must be positive")
    adjusted = [
        Decimal(str(row["close"]))
        * _decimal(row["adj_factor"], "adj_factor")
        / anchor_factor
        for row in rows
    ]
    result: list[date] = []
    for index in range(250, len(rows)):
        current_date = _as_date(rows[index]["date"])
        if current_date not in evaluation_date_set:
            continue
        previous_ma = sum(adjusted[index - 250:index], Decimal("0")) / Decimal(250)
        current_ma = sum(adjusted[index - 249:index + 1], Decimal("0")) / Decimal(250)
        if adjusted[index - 1] > previous_ma and adjusted[index] < current_ma:
            result.append(current_date)
    return tuple(result)


def _attempt_fill(*, pending, trade_date, row, rows_by_date, market_dates, date_index, cash, position, fees):
    direction = pending["direction"]
    opened = _decimal(row["open"], "open")
    pre_close = _decimal(row["pre_close"], "pre_close")
    if opened <= 0 or pre_close <= 0:
        return {"kind": "rejected", "reason": "invalid_open"}
    lower = (pre_close * (Decimal("1") - LIMIT_RATE)).quantize(TICK, rounding=ROUND_HALF_UP)
    upper = (pre_close * (Decimal("1") + LIMIT_RATE)).quantize(TICK, rounding=ROUND_HALF_UP)
    if direction == "buy" and opened >= upper:
        return {"kind": "blocked", "reason": "limit_up"}
    if direction == "sell" and opened <= lower:
        return {"kind": "blocked", "reason": "limit_down"}

    rate = fees["slippage_rate"]
    if direction == "buy":
        execution_price = (opened * (Decimal("1") + rate)).quantize(TICK, rounding=ROUND_CEILING)
        if execution_price > upper:
            return {"kind": "blocked", "reason": "execution_price_outside_price_limit"}
    else:
        execution_price = (opened * (Decimal("1") - rate)).quantize(TICK, rounding=ROUND_FLOOR)
        if execution_price < lower:
            return {"kind": "blocked", "reason": "execution_price_outside_price_limit"}

    index = date_index[trade_date]
    if index == 0:
        return {"kind": "rejected", "reason": "missing_previous_session_volume"}
    previous_date = market_dates[index - 1]
    previous_row = rows_by_date.get(previous_date)
    if previous_row is None:
        return {"kind": "rejected", "reason": "missing_previous_session_volume"}
    capacity_lots = (
        Decimal(str(previous_row["volume"]))
        * fees["opening_capacity_rate"]
        / Decimal(LOT)
    ).to_integral_value(rounding=ROUND_FLOOR)
    capacity = int(capacity_lots) * LOT

    if direction == "buy":
        quantity = _max_affordable_quantity(
            cash, execution_price, fees["commission_rate"], fees["minimum_commission"]
        )
        if quantity <= 0:
            return {"kind": "rejected", "reason": "insufficient_capital"}
        if quantity > capacity:
            return {"kind": "blocked", "reason": "liquidity_shortfall"}
        gross, commission, stamp, transfer, total_fee, flow = _cash_flow(
            direction, quantity, execution_price, fees
        )
        next_session = _next_date(market_dates, date_index, trade_date)
        if next_session is None:
            return {"kind": "rejected", "reason": "no_t1_unlock_date"}
        if position is not None:
            raise ValueError("reference profile forbids pyramiding")
        new_cash = _money(cash + flow)
        new_position = {
            "quantity": quantity,
            "sellable_quantity": 0,
            "unlock_date": next_session,
            "avg_cost": execution_price,
            "buy_cash_flow": flow,
            "dividend_income": Decimal("0.00"),
            "buy_date": trade_date,
        }
    else:
        if position is None:
            return {"kind": "rejected", "reason": "no_position"}
        quantity = int(pending["quantity"])
        if int(position["sellable_quantity"]) < quantity:
            return {"kind": "rejected", "reason": "insufficient_position"}
        if quantity != int(position["quantity"]):
            raise ValueError("reference profile only supports full-position exits")
        if quantity > capacity:
            return {"kind": "blocked", "reason": "liquidity_shortfall"}
        gross, commission, stamp, transfer, total_fee, flow = _cash_flow(
            direction, quantity, execution_price, fees
        )
        new_cash = _money(cash + flow)
        new_position = None

    trade = {
        "order_id": pending["order_id"],
        "signal_date": pending["signal_date"],
        "signal_type": pending["signal_type"],
        "intended_date": pending["intended_date"],
        "direction": direction,
        "trade_date": trade_date,
        "quantity": quantity,
        "price": execution_price,
        "gross_amount": gross,
        "commission": commission,
        "stamp_duty": stamp,
        "transfer_fee": transfer,
        "total_fee": total_fee,
        "net_cash_flow": flow,
        "cycle_profit": (
            Decimal(position["buy_cash_flow"])
            + Decimal(position["dividend_income"])
            + flow
            if direction == "sell"
            else Decimal("0.00")
        ),
    }
    return {"kind": "filled", "cash": new_cash, "position": new_position, "trade": trade}


def _new_intent(strategy_name, strategy_version, symbol, signal_date, signal_type, intended_date, direction, quantity):
    signal_id = (
        f"{strategy_name}:{strategy_version}:{symbol}:{signal_date}:"
        f"{signal_type}"
    )
    return {
        "order_id": f"order:{signal_id}:{intended_date}",
        "signal_date": signal_date,
        "signal_type": signal_type,
        "intended_date": intended_date,
        "direction": direction,
        "quantity": quantity,
    }


def _normalize_dividends(events: Sequence[Mapping[str, object]]) -> tuple[dict[str, object], ...]:
    normalized: dict[tuple[str, date], dict[str, object]] = {}
    for raw in events:
        symbol = raw.get("ts_code")
        if not isinstance(symbol, str) or not symbol:
            raise ValueError("reference dividend event has no symbol")
        ann = _as_date(raw.get("ann_date"))
        record = _as_date(raw.get("record_date"))
        ex = _as_date(raw.get("ex_date"))
        pay = _as_date(raw.get("pay_date"))
        amount = _decimal(raw.get("div_cash"), "div_cash")
        if not ann <= record <= ex <= pay or amount <= 0:
            raise ValueError("reference dividend event has invalid dates or amount")
        key = (symbol, ann)
        details = (record, ex, pay, amount, raw.get("verified_unit"))
        previous = normalized.get(key)
        if previous is not None:
            prior_details = (
                previous["record_date"], previous["ex_date"], previous["pay_date"],
                previous["div_cash"], previous["verified_unit"],
            )
            if prior_details != details:
                raise ValueError(f"reference conflicting dividend event: {symbol} {ann}")
            continue
        normalized[key] = {
            "key": key,
            "symbol": symbol,
            "ann_date": ann,
            "record_date": record,
            "ex_date": ex,
            "pay_date": pay,
            "div_cash": amount,
            "verified_unit": raw.get("verified_unit"),
        }
    return tuple(normalized[key] for key in sorted(normalized))


def _max_affordable_quantity(cash: Decimal, price: Decimal, rate: Decimal, minimum: Decimal) -> int:
    if cash <= minimum or price <= 0:
        return 0
    high = int(cash / (price * LOT)) + 1
    low = 0
    while low < high:
        middle = (low + high + 1) // 2
        _, _, _, _, _, flow = _cash_flow(
            "buy",
            middle * LOT,
            price,
            {
                "commission_rate": rate,
                "minimum_commission": minimum,
                "stamp_duty_rate": Decimal("0"),
                "transfer_fee_rate": Decimal("0"),
            },
        )
        if -flow <= cash:
            low = middle
        else:
            high = middle - 1
    return low * LOT


def _cash_flow(direction, quantity, price, fees):
    gross_raw = Decimal(quantity) * price
    gross = _money(gross_raw)
    commission = _money(max(gross_raw * fees["commission_rate"], fees["minimum_commission"]))
    stamp = (
        _money(gross_raw * fees["stamp_duty_rate"])
        if direction == "sell"
        else Decimal("0.00")
    )
    transfer = (
        _money(gross_raw * fees["transfer_fee_rate"])
        if fees["transfer_fee_rate"] > 0
        else Decimal("0.00")
    )
    total_fee = commission + stamp + transfer
    flow = -(gross + total_fee) if direction == "buy" else gross - total_fee
    return gross, commission, stamp, transfer, total_fee, flow


def _next_date(market_dates, date_index, current_date):
    index = date_index[current_date]
    if index + 1 >= len(market_dates):
        return None
    return market_dates[index + 1]


def _signal_fields_from_order_id(order_id: str) -> tuple[date, str, date]:
    if not order_id.startswith("order:"):
        raise ValueError(f"unexpected Gate001 order id: {order_id}")
    signal_id, intended = order_id[len("order:"):].rsplit(":", 1)
    parts = signal_id.split(":")
    if len(parts) != 5 or parts[4] not in {"entry", "exit"}:
        raise ValueError(f"unexpected Gate001 signal id in order: {order_id}")
    return date.fromisoformat(parts[3]), parts[4], date.fromisoformat(intended)


def _decimal(value: object, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except Exception as exc:
        raise ValueError(f"reference {field} must be numeric") from exc
    if not result.is_finite():
        raise ValueError(f"reference {field} must be finite")
    return result


def _as_date(value: object) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    raise ValueError(f"reference date is invalid: {value!r}")


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)
