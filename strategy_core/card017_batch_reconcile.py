"""Independent financial and metric reconciliation for the Card017 four-path batch."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, localcontext


CENT = Decimal("0.01")
TICK = Decimal("0.001")
RATIO_QUANTUM = Decimal("0.0000000001")
COMMISSION_RATE = Decimal("0.0003")
MIN_COMMISSION = Decimal("5.00")
INITIAL_CASH = Decimal("5000.00")
EXPECTED_PATH_IDS = {
    "candidate-base",
    "candidate-stress",
    "buy_and_hold-base",
    "buy_and_hold-stress",
}


class ReconciliationError(ValueError):
    """Raised when any batch ledger field differs from an independent recomputation."""


def _d(value: object, label: str) -> Decimal:
    try:
        value = Decimal(str(value))
    except Exception as exc:
        raise ReconciliationError(f"{label}: invalid decimal") from exc
    if not value.is_finite():
        raise ReconciliationError(f"{label}: non-finite decimal")
    return value


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _ratio(value: Decimal) -> Decimal:
    return value.quantize(RATIO_QUANTUM, rounding=ROUND_HALF_UP)


def _date(value: object, label: str) -> date:
    if isinstance(value, datetime):
        raise ReconciliationError(f"{label}: datetime is not an accounting date")
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (ValueError, TypeError):
        raise ReconciliationError(f"{label}: invalid date") from None


def _require(path_id: str, field: str, actual: object, expected: object) -> None:
    if actual != expected:
        raise ReconciliationError(
            f"{path_id} {field} mismatch: expected {expected!r}, got {actual!r}"
        )


def _parse_events(events) -> list[dict[str, object]]:
    parsed = []
    seen = set()
    for index, raw in enumerate(events):
        symbol = raw.get("ts_code")
        ann = _date(raw.get("ann_date"), f"event[{index}].ann_date")
        record = _date(raw.get("record_date"), f"event[{index}].record_date")
        ex = _date(raw.get("ex_date"), f"event[{index}].ex_date")
        pay = _date(raw.get("pay_date"), f"event[{index}].pay_date")
        cash = _d(raw.get("div_cash"), f"event[{index}].div_cash")
        if symbol != "510880.SH" or not ann <= record <= ex <= pay or cash <= 0:
            raise ReconciliationError(f"event[{index}] is invalid for Card017")
        source_ref = raw.get("source_ref")
        if not isinstance(source_ref, str) or not source_ref.strip():
            raise ReconciliationError(f"event[{index}] has no source reference")
        key = (symbol, ann)
        if key in seen:
            raise ReconciliationError(f"duplicate raw dividend key: {key}")
        seen.add(key)
        parsed.append({
            "event_id": f"{symbol}:{ann.isoformat()}",
            "record_date": record,
            "ex_date": ex,
            "pay_date": pay,
            "div_cash": cash,
        })
    return parsed


def _execution_price(direction: str, raw_open: Decimal, slip: Decimal) -> Decimal:
    amount = raw_open * (Decimal(1) + slip if direction == "buy" else Decimal(1) - slip)
    return amount.quantize(TICK, rounding=ROUND_CEILING if direction == "buy" else ROUND_FLOOR)


def _commission(gross_raw: Decimal) -> Decimal:
    return max(gross_raw * COMMISSION_RATE, MIN_COMMISSION).quantize(CENT, rounding=ROUND_HALF_UP)


def _independent_exit_cost(data_source, symbol: str, day: date, quantity: int, slip: Decimal) -> Decimal:
    if quantity == 0:
        return Decimal("0.00")
    bar = data_source.get_daily_bar(symbol, day)
    close = _d(bar.close, f"{day} raw close")
    price = _execution_price("sell", close, slip)
    gross_raw = price * quantity
    fee = _commission(gross_raw)
    adverse_loss = (close - price) * quantity
    return _money(adverse_loss + fee)


def _independent_drawdowns(curve: list[dict[str, object]]) -> tuple[dict[str, object], dict[str, object]]:
    high_water = _d(curve[0]["nav"], "drawdown opening NAV")
    high_date = curve[0]["date"]
    high_index = 0
    worst_cash = Decimal(0)
    worst_rate = Decimal(0)
    cash_peak = cash_trough = None
    rate_peak = rate_trough = None

    for position, row in enumerate(curve):
        nav = _d(row["nav"], "drawdown NAV")
        if nav > high_water:
            high_water = nav
            high_date = row["date"]
            high_index = position
        loss = high_water - nav
        fraction = loss / high_water
        if loss > worst_cash:
            worst_cash = loss
            cash_peak = (high_index, high_date, high_water)
            cash_trough = (position, row["date"])
        if fraction > worst_rate:
            worst_rate = fraction
            rate_peak = (high_index, high_date, high_water)
            rate_trough = (position, row["date"])

    def finish(peak, trough, amount: Decimal | None = None, rate: Decimal | None = None):
        if peak is None or trough is None:
            return ({"amount": Decimal("0.00"), "peak_date": None, "trough_date": None,
                     "recovery_date": None, "underwater_trading_days": 0} if amount is not None else
                    {"ratio": Decimal("0E-10"), "peak_date": None, "trough_date": None,
                     "recovery_date": None, "underwater_trading_days": 0})
        trough_index, trough_date = trough
        peak_index, peak_date, peak_nav = peak
        recovery = next(
            ((idx, row["date"]) for idx, row in enumerate(curve[trough_index + 1:], start=trough_index + 1)
             if _d(row["nav"], "recovery NAV") >= peak_nav),
            None,
        )
        last_index = len(curve) - 1 if recovery is None else recovery[0]
        payload = {
            "peak_date": peak_date,
            "trough_date": trough_date,
            "recovery_date": None if recovery is None else recovery[1],
            "underwater_trading_days": max(0, last_index - trough_index),
        }
        if amount is not None:
            payload["amount"] = _money(amount)
        else:
            payload["ratio"] = _ratio(rate)
        return payload

    return finish(cash_peak, cash_trough, amount=worst_cash), finish(rate_peak, rate_trough, rate=worst_rate)


def _independent_metrics(
    *,
    data_source,
    symbol: str,
    curve_raw: list[dict[str, object]],
    exposure_rows: list[dict[str, object]],
    attempts: list[dict[str, object]],
    period_start: date,
    period_end: date,
    exit_day: date,
    scale: Decimal,
    include_start_date_attempts: bool,
) -> dict[str, object]:
    initial_actual = _d(curve_raw[0]["nav"], "window starting NAV")
    ending_actual = _d(curve_raw[-1]["nav"], "window ending NAV")
    cost_actual = _independent_exit_cost(
        data_source, symbol, exit_day, int(curve_raw[-1].get("quantity", 0)),
        _d(attempts[0]["path_slippage_rate"], "slippage rate") if attempts else Decimal("0.0005"),
    )
    curve = [{**row, "nav": _money(_d(row["nav"], "NAV") * scale)} for row in curve_raw]
    comparison_start = _money(initial_actual * scale)
    comparison_end = _money(ending_actual * scale)
    cost_comparison = _money(cost_actual * scale)
    actual_exit_value = _money(ending_actual - cost_actual)
    comparison_exit_value = _money(comparison_end - cost_comparison)
    elapsed = (period_end - period_start).days
    if elapsed <= 0 or len(curve) < 2:
        raise ReconciliationError("metric window has invalid dates or fewer than two risk points")
    values = [_d(row["nav"], "risk NAV") for row in curve]
    if any(value <= 0 for value in values):
        raise ReconciliationError("metric window NAV must stay positive")
    with localcontext() as context:
        context.prec = 28
        annual = (comparison_exit_value / comparison_start) ** (Decimal(365) / Decimal(elapsed)) - Decimal(1)
        returns = []
        for index in range(1, len(values)):
            returns.append(values[index] / values[index - 1] - Decimal(1))
        average_return = sum(returns, Decimal(0)) / Decimal(len(returns))
        variance = sum(((ret - average_return) ** 2 for ret in returns), Decimal(0)) / Decimal(len(returns))
        deviation = variance.sqrt()
        sharpe = average_return / deviation * Decimal(252).sqrt() if deviation else Decimal(0)

    drawdown_cash, drawdown_rate = _independent_drawdowns(curve)
    if not exposure_rows:
        raise ReconciliationError("metric window has no EOD exposure rows")
    exposure = sum(
        (_d(row["position_value"], "position value") / _d(row["nav"], "exposure NAV") for row in exposure_rows),
        Decimal(0),
    ) / Decimal(len(exposure_rows))
    cash_ratio = sum(
        (_d(row["cash"], "cash") / _d(row["nav"], "cash ratio NAV") for row in exposure_rows),
        Decimal(0),
    ) / Decimal(len(exposure_rows))
    scoped_attempts = [
        row for row in attempts
        if (period_start <= row["attempt_date"] if include_start_date_attempts else period_start < row["attempt_date"])
        and row["attempt_date"] <= period_end
    ]
    actual_fees = sum((_d(row["commission"], "commission") for row in scoped_attempts), Decimal(0))
    actual_slippage = sum((_d(row["slippage_cost"], "slippage") for row in scoped_attempts), Decimal(0))
    start_actual = comparison_start / scale
    return {
        "start_date": period_start,
        "end_date": period_end,
        "elapsed_natural_days": elapsed,
        "start_nav_comparison": comparison_start,
        "start_nav_actual": _money(start_actual),
        "ending_nav_actual": _money(ending_actual),
        "ending_nav_comparison": comparison_end,
        "estimated_exit_cost_actual": cost_actual,
        "estimated_exit_cost_comparison": cost_comparison,
        "estimated_exit_value_actual": actual_exit_value,
        "estimated_exit_value_comparison": comparison_exit_value,
        "net_gain_actual": _money(actual_exit_value - start_actual),
        "net_gain_comparison": _money(comparison_exit_value - comparison_start),
        "cagr": _ratio(annual),
        "sharpe": _ratio(sharpe),
        "max_drawdown_amount": drawdown_cash,
        "max_drawdown_ratio": drawdown_rate,
        "average_exposure": _ratio(exposure),
        "average_cash_ratio": _ratio(cash_ratio),
        "commission_total_actual": _money(actual_fees),
        "commission_total_comparison": _money(actual_fees * scale),
        "slippage_cost_total_actual": _money(actual_slippage),
        "slippage_cost_total_comparison": _money(actual_slippage * scale),
        "trade_count": sum(row["status"] == "filled" for row in scoped_attempts),
        "blocked_attempt_count": sum(row["status"] != "filled" for row in scoped_attempts),
        "scale": _ratio(scale),
    }


def _rebuild_path(path: dict[str, object], data_source, calendar, raw_events: list[dict[str, object]]) -> dict[str, object]:
    path_id = str(path.get("path_id"))
    symbol = path.get("symbol")
    if symbol != "510880.SH":
        raise ReconciliationError(f"{path_id} symbol is outside Card017 scope")
    start = _date(path.get("start_date"), f"{path_id} start_date")
    end = _date(path.get("end_date"), f"{path_id} end_date")
    slip = _d(path.get("slippage_rate"), f"{path_id} slippage_rate")
    if slip not in {Decimal("0.0005"), Decimal("0.001")}:
        raise ReconciliationError(f"{path_id} has an unsupported slippage scenario")
    initial_cash = _d(path.get("initial_cash"), f"{path_id} initial_cash")
    if initial_cash != INITIAL_CASH:
        raise ReconciliationError(f"{path_id} initial cash is not 5,000.00 CNY")
    all_dates = calendar.all_trading_dates()
    if start not in all_dates or end not in all_dates:
        raise ReconciliationError(f"{path_id} window boundaries are not trading sessions")
    sessions = all_dates[all_dates.index(start): all_dates.index(end) + 1]
    rows_by_date = {_date(row["date"], f"{path_id} snapshot date"): row for row in path["daily_snapshots"]}
    if list(rows_by_date) != sessions:
        raise ReconciliationError(f"{path_id} daily snapshots do not cover the exact trading window")

    cash = initial_cash
    positions: list[dict[str, object]] = []
    entitlements: dict[str, int] = {}
    receivables: dict[str, Decimal] = {}
    settled: set[str] = set()
    event_ids = [str(event["event_id"]) for event in raw_events]
    attempts_by_day: dict[date, list[dict[str, object]]] = {}
    seen_children = set()
    intent_rows = path["intents"]
    intents_by_id = {str(intent["intent_id"]): intent for intent in intent_rows}
    if len(intents_by_id) != len(intent_rows):
        raise ReconciliationError(f"{path_id} has duplicate intent IDs")
    for intent_id, intent in intents_by_id.items():
        direction = intent.get("direction")
        signal_date = _date(intent.get("signal_date"), f"{path_id} intent signal_date")
        created_date = _date(intent.get("created_date"), f"{path_id} intent created_date")
        if direction not in {"buy", "sell"} or created_date != signal_date:
            raise ReconciliationError(f"{path_id} intent has invalid direction or signal date: {intent_id}")
        if intent.get("signal_id") != intent_id:
            raise ReconciliationError(f"{path_id} intent signal ID is not bound to its intent: {intent_id}")
        if intent.get("status") not in {"filled", "cancelled"}:
            raise ReconciliationError(f"{path_id} intent was left in a nonterminal state: {intent_id}")

    attempt_counts: dict[str, int] = {}
    last_attempt_by_intent: dict[str, dict[str, object]] = {}
    last_attempt_day = None
    for row in path["attempts"]:
        day = _date(row["attempt_date"], f"{path_id} attempt_date")
        if last_attempt_day is not None and day < last_attempt_day:
            raise ReconciliationError(f"{path_id} attempts are not in chronological order")
        last_attempt_day = day
        child = str(row["child_order_id"])
        if child in seen_children:
            raise ReconciliationError(f"{path_id} duplicate child order ID {child}")
        seen_children.add(child)
        intent_id = str(row["intent_id"])
        if intent_id not in intents_by_id:
            raise ReconciliationError(f"{path_id} attempt is not linked to an intent")
        intent = intents_by_id[intent_id]
        if row.get("path_id") != path_id or row.get("symbol") != symbol:
            raise ReconciliationError(f"{path_id} attempt identity does not match its ledger")
        if row.get("direction") != intent.get("direction"):
            raise ReconciliationError(f"{path_id} attempt intent direction mismatch for {intent_id}")
        if row.get("signal_id") != intent.get("signal_id") or row.get("order_reason") != intent.get("source"):
            raise ReconciliationError(f"{path_id} attempt signal or reason is detached from its intent")
        if row.get("strategy_version") != "card017-month-end-ma250-v1" or row.get("audit_id") != child:
            raise ReconciliationError(f"{path_id} attempt lacks its frozen strategy/audit binding")
        signal_date = _date(row["signal_date"], f"{path_id} signal_date")
        if signal_date != _date(intent["signal_date"], f"{path_id} intent signal_date"):
            raise ReconciliationError(f"{path_id} attempt signal date is detached from its intent")
        if day <= signal_date or day not in sessions:
            raise ReconciliationError(f"{path_id} attempt date is not after its signal and inside the window")
        attempt_counts[intent_id] = attempt_counts.get(intent_id, 0) + 1
        expected_child = f"{intent_id}:child:{day.isoformat()}:{attempt_counts[intent_id]:03d}"
        _require(path_id, f"{day}.child_order_id", child, expected_child)
        last_attempt_by_intent[intent_id] = row
        attempts_by_day.setdefault(day, []).append(row)

    cancellations_by_intent = {}
    for cancellation in path["cancellations"]:
        intent_id = str(cancellation.get("intent_id"))
        if intent_id not in intents_by_id or intent_id in cancellations_by_intent:
            raise ReconciliationError(f"{path_id} cancellation is not uniquely linked to an intent")
        cancellations_by_intent[intent_id] = cancellation
    for intent_id, intent in intents_by_id.items():
        _require(path_id, f"{intent_id}.attempt_count", int(intent.get("attempt_count", -1)), attempt_counts.get(intent_id, 0))
        if intent["status"] == "cancelled":
            cancellation = cancellations_by_intent.get(intent_id)
            if cancellation is None:
                raise ReconciliationError(f"{path_id} cancelled intent has no cancellation record: {intent_id}")
            cancel_date = _date(cancellation.get("date"), f"{path_id} cancellation date")
            if cancel_date != _date(intent.get("cancel_date"), f"{path_id} intent cancel_date"):
                raise ReconciliationError(f"{path_id} cancellation date mismatch for {intent_id}")
            if cancellation.get("reason") != intent.get("cancel_reason"):
                raise ReconciliationError(f"{path_id} cancellation reason mismatch for {intent_id}")
            if intent_id in last_attempt_by_intent and last_attempt_by_intent[intent_id]["attempt_date"] > cancel_date:
                raise ReconciliationError(f"{path_id} has an attempt after intent cancellation: {intent_id}")
        else:
            if intent_id in cancellations_by_intent:
                raise ReconciliationError(f"{path_id} completed intent also has a cancellation: {intent_id}")
            last_attempt = last_attempt_by_intent.get(intent_id)
            if last_attempt is None or last_attempt.get("status") != "filled":
                raise ReconciliationError(f"{path_id} completed intent has no final fill: {intent_id}")

    initial_point = path.get("initial_point", {})
    _require(path_id, "initial_point.nav", initial_point.get("nav"), INITIAL_CASH)
    _require(path_id, "initial_point.cash", initial_point.get("cash"), INITIAL_CASH)
    _require(path_id, "initial_point.quantity", initial_point.get("quantity"), 0)

    for day in sessions:
        if len(attempts_by_day.get(day, [])) > 1:
            raise ReconciliationError(f"{path_id} has multiple child attempts on {day}")
        for event in raw_events:
            if event["pay_date"] < day and event["event_id"] not in settled and event["event_id"] in receivables:
                cash = _money(cash + receivables.pop(event["event_id"]))
                settled.add(event["event_id"])
        for lot in positions:
            if lot["unlock_date"] <= day:
                lot["sellable"] = True
        snapshot = rows_by_date[day]
        _require(path_id, f"{day}.cash_before_open", _d(snapshot["cash_before_open"], "cash_before_open"), cash)
        bar = data_source.get_daily_bar(symbol, day)
        status = data_source.get_daily_status(symbol, day)
        previous_date = calendar.previous_trading_day(day)
        previous_volume = data_source.get_daily_bar(symbol, previous_date).volume
        capacity = (int(previous_volume) // 1000) * 100

        for attempt in attempts_by_day.get(day, []):
            direction = str(attempt["direction"])
            if direction not in {"buy", "sell"}:
                raise ReconciliationError(f"{path_id} has unknown direction on {day}")
            quantity = int(attempt["actual_quantity"])
            requested = int(attempt["requested_quantity"])
            if requested <= 0 or requested % 100:
                raise ReconciliationError(f"{path_id} requested quantity is not a positive board-lot multiple")
            raw_open = _d(bar.open, f"{day} open")
            _require(path_id, f"{day}.raw_open", _d(attempt["raw_open"], "ledger raw open"), raw_open)
            _require(path_id, f"{day}.capacity", int(attempt["capacity_quantity"]), capacity)
            current_quantity = sum(int(lot["quantity"]) for lot in positions)
            current_sellable = sum(int(lot["quantity"]) for lot in positions if lot["sellable"])
            expected_requested = (
                max(capacity, 100)
                if direction == "buy"
                else min(current_quantity, capacity, current_sellable)
                if current_quantity and capacity and current_sellable
                else 100
            )
            _require(path_id, f"{day}.requested_quantity", requested, expected_requested)
            _require(path_id, f"{day}.raw_close", _d(attempt["raw_close"], "ledger raw close"), _d(bar.close, "raw close"))

            if attempt["status"] == "filled":
                if attempt.get("rejection_reason") is not None:
                    raise ReconciliationError(f"{path_id} filled attempt has a rejection reason on {day}")
                if status.is_suspended or (direction == "buy" and status.is_limit_up) or (
                    direction == "sell" and status.is_limit_down
                ):
                    raise ReconciliationError(f"{path_id} filled during a blocked market state on {day}")
                if quantity <= 0 or quantity % 100 or quantity > requested or quantity > capacity:
                    raise ReconciliationError(f"{path_id} filled quantity violates lot or capacity on {day}")
                if direction == "sell" and quantity > current_sellable:
                    raise ReconciliationError(f"{path_id} sell violates T+1 at {day}")
                execution_price = _execution_price(direction, raw_open, slip)
                _require(path_id, f"{day}.execution_price", _d(attempt["execution_price"], "execution price"), execution_price)
                lower, upper = data_source.get_daily_price_limits(symbol, day)
                if not _d(lower, "lower price limit") <= execution_price <= _d(upper, "upper price limit"):
                    raise ReconciliationError(f"{path_id} execution price crosses a daily limit on {day}")
                if direction == "buy":
                    try:
                        calendar.next_trading_day(day)
                    except ValueError:
                        raise ReconciliationError(f"{path_id} buy has no verified T+1 unlock date on {day}") from None
                gross_raw = execution_price * quantity
                gross = _money(gross_raw)
                fee = _commission(gross_raw)
                adverse = _money((execution_price - raw_open) * quantity if direction == "buy" else (raw_open - execution_price) * quantity)
                _require(path_id, f"{day}.gross", _d(attempt["gross"], "gross"), gross)
                _require(path_id, f"{day}.commission", _d(attempt["commission"], "commission"), fee)
                _require(path_id, f"{day}.stamp_duty", _d(attempt["stamp_duty"], "stamp duty"), Decimal("0.00"))
                _require(path_id, f"{day}.transfer_fee", _d(attempt["transfer_fee"], "transfer fee"), Decimal("0.00"))
                _require(path_id, f"{day}.slippage_cost", _d(attempt["slippage_cost"], "slippage"), adverse)
                if direction == "buy":
                    debit = gross + fee
                    if debit > cash:
                        raise ReconciliationError(f"{path_id} buy overdraws cash on {day}")
                    cash = _money(cash - debit)
                    positions.append({
                        "quantity": quantity,
                        "buy_date": day,
                        "unlock_date": calendar.next_trading_day(day),
                        "sellable": False,
                    })
                else:
                    remaining = quantity
                    for lot in positions:
                        if not lot["sellable"]:
                            continue
                        used = min(remaining, int(lot["quantity"]))
                        lot["quantity"] = int(lot["quantity"]) - used
                        remaining -= used
                        if remaining == 0:
                            break
                    if remaining:
                        raise ReconciliationError(f"{path_id} sell could not be assigned to T+1 sellable lots on {day}")
                    positions = [lot for lot in positions if int(lot["quantity"]) > 0]
                    cash = _money(cash + gross - fee)
            else:
                if attempt["status"] != "rejected" or not attempt.get("rejection_reason"):
                    raise ReconciliationError(f"{path_id} rejected attempt lacks a reason on {day}")
                if quantity != 0:
                    raise ReconciliationError(f"{path_id} rejected attempt carries a fill quantity on {day}")
                for name in ("gross", "commission", "stamp_duty", "transfer_fee", "slippage_cost"):
                    _require(path_id, f"{day}.{name}", _d(attempt[name], name), Decimal("0.00"))

            current_quantity = sum(int(lot["quantity"]) for lot in positions)
            current_sellable = sum(int(lot["quantity"]) for lot in positions if lot["sellable"])
            _require(path_id, f"{day}.cash_after", _d(attempt["cash_after"], "cash_after"), cash)
            _require(path_id, f"{day}.position_quantity_after", int(attempt["position_quantity_after"]), current_quantity)
            _require(path_id, f"{day}.sellable_quantity_after", int(attempt["sellable_quantity_after"]), current_sellable)

        for event in raw_events:
            if event["record_date"] == day:
                entitlements[event["event_id"]] = sum(int(lot["quantity"]) for lot in positions)
        for event in raw_events:
            if event["ex_date"] == day:
                amount = _money(event["div_cash"] * entitlements.get(event["event_id"], 0))
                receivables[event["event_id"]] = amount
        for event in raw_events:
            if event["pay_date"] == day and event["event_id"] in receivables and event["event_id"] not in settled:
                cash = _money(cash + receivables.pop(event["event_id"]))
                settled.add(event["event_id"])

        quantity = sum(int(lot["quantity"]) for lot in positions)
        sellable = sum(int(lot["quantity"]) for lot in positions if lot["sellable"])
        position_value = _money(_d(bar.close, f"{day} close") * quantity)
        receivable_total = _money(sum(receivables.values(), Decimal(0)))
        nav = _money(cash + position_value + receivable_total)
        _require(path_id, f"{day}.cash", _d(snapshot["cash"], "daily cash"), cash)
        _require(path_id, f"{day}.position_value", _d(snapshot["position_value"], "daily position value"), position_value)
        _require(path_id, f"{day}.quantity", int(snapshot["quantity"]), quantity)
        _require(path_id, f"{day}.sellable_quantity", int(snapshot["sellable_quantity"]), sellable)
        _require(path_id, f"{day}.receivable", _d(snapshot["receivable"], "daily receivable"), receivable_total)
        _require(path_id, f"{day}.nav", _d(snapshot["nav"], "daily nav"), nav)

    final_day = sessions[-1]
    final_row = rows_by_date[final_day]
    end_quantity = sum(int(lot["quantity"]) for lot in positions)
    end_sellable = sum(int(lot["quantity"]) for lot in positions if lot["sellable"])
    _require(path_id, "ending_cash", _d(path["ending_cash"], "ending cash"), cash)
    _require(path_id, "ending_quantity", int(path["ending_quantity"]), end_quantity)
    _require(path_id, "ending_sellable_quantity", int(path["ending_sellable_quantity"]), end_sellable)
    _require(path_id, "ending_receivable", _d(path["ending_receivable"], "ending receivable"), _money(sum(receivables.values(), Decimal(0))))
    _require(path_id, "ending_nav", _d(path["ending_nav"], "ending nav"), _d(final_row["nav"], "final snapshot nav"))

    expected_metrics = _build_independent_windows(path, data_source, calendar)
    reported = path.get("metrics", {})
    if set(reported) != set(expected_metrics):
        raise ReconciliationError(f"{path_id} metric windows mismatch: expected {sorted(expected_metrics)}, got {sorted(reported)}")
    for window, expected in expected_metrics.items():
        actual = reported[window]
        if set(actual) != set(expected):
            raise ReconciliationError(f"{path_id} {window} metric fields mismatch")
        for key, value in expected.items():
            _require(path_id, f"{window}.{key}", actual[key], value)

    return {
        "status": "RECONCILED",
        "path_id": path_id,
        "checked_attempts": len(path["attempts"]),
        "checked_daily_snapshots": len(path["daily_snapshots"]),
        "ending_cash": cash,
        "ending_quantity": end_quantity,
        "ending_receivable": _money(sum(receivables.values(), Decimal(0))),
        "ending_nav": _d(final_row["nav"], "final NAV"),
        "metrics_verified": sorted(expected_metrics),
    }


def _build_independent_windows(path: dict[str, object], data_source, calendar) -> dict[str, dict[str, object]]:
    daily = list(path["daily_snapshots"])
    if not daily:
        return {}
    by_date = {row["date"]: row for row in daily}
    all_days = calendar.all_trading_dates()
    start = path["start_date"]
    end = path["end_date"]
    attempts = [{**row, "path_slippage_rate": path["slippage_rate"]} for row in path["attempts"]]
    slip = _d(path["slippage_rate"], "scenario slip")
    symbol = str(path["symbol"])
    windows = {}

    def append(name, actual_curve, exposure_rows, period_start, period_end, scale, include_start=True):
        curve = [{"date": row["date"], "nav": _d(row["nav"], "NAV"), "quantity": int(row.get("quantity", 0))} for row in actual_curve]
        # _independent_metrics receives the actual scale separately and independently values the exit at raw close.
        local_attempts = [dict(row, path_slippage_rate=slip) for row in attempts]
        expected = _independent_metrics(
            data_source=data_source,
            symbol=symbol,
            curve_raw=curve,
            exposure_rows=exposure_rows,
            attempts=local_attempts,
            period_start=period_start,
            period_end=period_end,
            exit_day=period_end,
            scale=scale,
            include_start_date_attempts=include_start,
        )
        windows[name] = expected

    initial = {"date": start, "nav": INITIAL_CASH, "quantity": 0}
    if end > start:
        append("full", [initial] + [row for row in daily], daily, start, end, Decimal(1))

    last_2019 = max((day for day in all_days if day.year == 2019), default=None)
    if last_2019 is not None and last_2019 in by_date and last_2019 > start:
        append("2018-2019", [initial] + [by_date[row["date"]] for row in daily if row["date"] <= last_2019],
               [row for row in daily if row["date"] <= last_2019], start, last_2019, Decimal(1))

    last_2020 = max((day for day in all_days if day.year == 2020), default=None)
    last_2019_data = last_2019
    first_2020 = min((day for day in all_days if day.year == 2020), default=None)
    if last_2020 is not None and last_2020 in by_date and last_2019_data is not None and first_2020 is not None:
        prior_nav = _d(by_date[last_2019_data]["nav"], "2019 end NAV")
        if prior_nav <= 0:
            raise ReconciliationError("2019 end NAV must be positive")
        factor = INITIAL_CASH / prior_nav
        starting = {"date": last_2019_data, "nav": prior_nav, "quantity": int(by_date[last_2019_data]["quantity"])}
        segment = [row for row in daily if first_2020 <= row["date"] <= last_2020]
        append("2020", [starting] + segment, segment, last_2019_data, last_2020, factor, include_start=False)
    return windows


def reconcile_batch(path_ledgers, data_source, calendar, *, events=()) -> dict[str, object]:
    """Recompute all four path ledgers from raw bars, statuses, and dividend events."""
    paths = list(path_ledgers)
    ids = [str(path.get("path_id")) for path in paths]
    if len(ids) != 4 or len(set(ids)) != 4 or set(ids) != EXPECTED_PATH_IDS:
        raise ReconciliationError("batch must contain four unique paths")
    raw_events = _parse_events(events)
    results = {}
    for path in paths:
        results[str(path["path_id"])] = _rebuild_path(path, data_source, calendar, raw_events)
    return {
        "status": "RECONCILED",
        "path_results": results,
        "checked_path_count": len(results),
        "dividend_event_count": len(raw_events),
    }

