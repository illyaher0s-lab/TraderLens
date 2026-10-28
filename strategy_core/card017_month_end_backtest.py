"""Narrow research runner for Card017's 510880 month-end MA250 hypothesis."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, localcontext

from contracts.stable import Order
from strategy_core.dividend_ledger import DividendLedger
from strategy_core.fill_simulator import simulate_fill
from strategy_core.portfolio import PortfolioState
from strategy_core.transaction_costs import calculate_affordable_quantity, calculate_transaction_costs


SYMBOL = "510880.SH"
INITIAL_CASH = Decimal("5000.00")
ANCHOR_DATE = date(2009, 1, 5)
MA_SESSIONS = 250
COMMISSION_RATE = Decimal("0.0003")
MIN_COMMISSION = Decimal("5.00")
PRICE_TICK = Decimal("0.001")
CENT = Decimal("0.01")
RATIO_QUANTUM = Decimal("0.0000000001")
EXPECTED_PATH_IDS = frozenset({
    "candidate-base",
    "candidate-stress",
    "buy_and_hold-base",
    "buy_and_hold-stress",
})


def _decimal(value: object, label: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except Exception as exc:
        raise ValueError(f"{label} must be a finite decimal") from exc
    if not result.is_finite():
        raise ValueError(f"{label} must be a finite decimal")
    return result


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _month_end(calendar, target_date: date) -> bool:
    dates = calendar.all_trading_dates()
    try:
        index = dates.index(target_date)
    except ValueError:
        raise ValueError(f"not a trading date: {target_date}") from None
    if index + 1 == len(dates):
        return True
    next_date = dates[index + 1]
    return (next_date.year, next_date.month) != (target_date.year, target_date.month)


def evaluate_month_end_signal(
    data_source,
    calendar,
    observation_date: date,
    *,
    symbol: str = SYMBOL,
    anchor_date: date = ANCHOR_DATE,
) -> dict[str, object]:
    """Calculate one causal 250-trading-session adjusted-close state."""
    if not _month_end(calendar, observation_date):
        raise ValueError(f"{observation_date} is not the month's last trading session")
    if anchor_date > observation_date:
        raise ValueError("adjustment anchor is after the observation date")

    sessions = [day for day in calendar.all_trading_dates() if day <= observation_date]
    if len(sessions) < MA_SESSIONS:
        raise ValueError(f"MA250 requires 250 trading sessions; found {len(sessions)}")
    lookback_dates = sessions[-MA_SESSIONS:]
    if len(set(lookback_dates)) != MA_SESSIONS:
        raise ValueError("MA250 lookback contains duplicate trading dates")

    anchor = data_source.get_daily_bar(symbol, anchor_date)
    anchor_factor = _decimal(anchor.adj_factor, "anchor adjustment factor")
    if anchor_factor <= 0:
        raise ValueError("anchor adjustment factor must be positive")

    adjusted_closes: list[Decimal] = []
    for day in lookback_dates:
        if day > observation_date:
            raise ValueError("MA250 attempted to read a future session")
        bar = data_source.get_daily_bar(symbol, day)
        if bar.date != day or bar.symbol != symbol:
            raise ValueError(f"market bar identity mismatch on {day}")
        close = _decimal(bar.close, f"{day} close")
        factor = _decimal(bar.adj_factor, f"{day} adjustment factor")
        if close <= 0 or factor <= 0:
            raise ValueError(f"invalid close or adjustment factor on {day}")
        adjusted_closes.append(close * factor / anchor_factor)

    current_close = adjusted_closes[-1]
    with localcontext() as context:
        context.prec = 28
        average = sum(adjusted_closes, Decimal(0)) / Decimal(MA_SESSIONS)
    state = "above" if current_close > average else "below" if current_close < average else "equal"
    return {
        "observation_date": observation_date,
        "symbol": symbol,
        "lookback_dates": tuple(lookback_dates),
        "adjusted_close": current_close,
        "sma250": average,
        "state": state,
    }


def _adjusted_execution_price(direction: str, raw_price: Decimal, slippage: Decimal) -> Decimal:
    rate = slippage
    adjusted = raw_price * (Decimal(1) + rate if direction == "buy" else Decimal(1) - rate)
    return adjusted.quantize(
        PRICE_TICK,
        rounding=ROUND_CEILING if direction == "buy" else ROUND_FLOOR,
    )


def _capacity_quantity(data_source, calendar, symbol: str, execution_date: date) -> int:
    previous_date = calendar.previous_trading_day(execution_date)
    previous_bar = data_source.get_daily_bar(symbol, previous_date)
    if previous_bar.date != previous_date or previous_bar.symbol != symbol:
        raise ValueError(f"previous-session bar identity mismatch on {previous_date}")
    volume = previous_bar.volume
    if isinstance(volume, bool) or not isinstance(volume, int) or volume < 0:
        raise ValueError(f"invalid previous-session volume on {previous_date}")
    return (volume // 1000) * 100


def _make_intent(
    *, path_id: str, direction: str, signal_date: date, created_date: date, source: str, sequence: int
) -> dict[str, object]:
    intent_id = f"{path_id}:intent:{sequence:04d}"
    return {
        "intent_id": intent_id,
        "signal_id": intent_id,
        "signal_date": signal_date,
        "created_date": created_date,
        "direction": direction,
        "source": source,
        "status": "open",
        "attempt_count": 0,
    }


def _cancel_intent(intent: dict[str, object], cancellations: list[dict[str, object]], day: date, reason: str) -> None:
    intent["status"] = "cancelled"
    intent["cancel_date"] = day
    intent["cancel_reason"] = reason
    cancellations.append({
        "intent_id": intent["intent_id"],
        "date": day,
        "reason": reason,
    })


def _apply_month_end_target(
    signal: dict[str, object],
    *,
    day: date,
    position_quantity: int,
    current_intent: dict[str, object] | None,
    intents: list[dict[str, object]],
    cancellations: list[dict[str, object]],
    path_id: str,
    sequence: int,
) -> tuple[dict[str, object] | None, int]:
    state = signal["state"]
    if state == "equal":
        return current_intent, sequence

    wanted = "buy" if state == "above" else "sell"
    should_trade = (wanted == "buy" and position_quantity == 0) or (
        wanted == "sell" and position_quantity > 0
    )
    if current_intent is not None and current_intent["status"] == "open":
        if current_intent["direction"] == wanted and (
            (wanted == "buy" and state == "above") or (wanted == "sell" and position_quantity > 0)
        ):
            return current_intent, sequence
        _cancel_intent(current_intent, cancellations, day, "opposite_month_end_target")
        current_intent = None
    if not should_trade:
        return None, sequence

    sequence += 1
    intent = _make_intent(
        path_id=path_id,
        direction=wanted,
        signal_date=day,
        created_date=day,
        source="month_end_ma250",
        sequence=sequence,
    )
    intents.append(intent)
    return intent, sequence


def _attempt_order(
    *,
    data_source,
    calendar,
    portfolio: PortfolioState,
    intent: dict[str, object],
    execution_date: date,
    path_id: str,
    slippage_rate: Decimal,
    source_sequence: int,
) -> tuple[dict[str, object], bool]:
    direction = str(intent["direction"])
    symbol = SYMBOL
    capacity = _capacity_quantity(data_source, calendar, symbol, execution_date)
    position = portfolio.positions.get(symbol)
    if direction == "buy":
        requested_quantity = max(capacity, 100)
    else:
        sellable = position.sellable_quantity if position is not None else 0
        requested_quantity = min(position.quantity, capacity, sellable) if position and sellable and capacity else 100

    attempt_number = int(intent["attempt_count"]) + 1
    child_id = f"{intent['intent_id']}:child:{execution_date.isoformat()}:{attempt_number:03d}"
    intent["attempt_count"] = attempt_number
    order = Order(
        order_id=child_id,
        signal_id=str(intent["signal_id"]),
        signal_date=intent["signal_date"],
        intended_execution_date=execution_date,
        symbol=symbol,
        direction=direction,
        quantity=requested_quantity,
        reason=str(intent["source"]),
        strategy_version="card017-month-end-ma250-v1",
        audit_id=child_id,
    )
    result = simulate_fill(
        order,
        execution_date,
        data_source,
        portfolio,
        commission_rate=float(COMMISSION_RATE),
        min_commission=float(MIN_COMMISSION),
        stamp_duty_rate=0.0,
        transfer_fee_rate=0.0,
        slippage_rate=float(slippage_rate),
        max_participation_rate=0.10,
        calendar=calendar,
        opening_capacity_mode=True,
        round_to_cents=True,
        execution_price_mode=True,
    )

    raw_bar = data_source.get_daily_bar(symbol, execution_date)
    raw_open = _decimal(raw_bar.open, f"{execution_date} open")
    raw_close = _decimal(raw_bar.close, f"{execution_date} close")
    execution_price = (
        _decimal(result.actual_price, "execution price") if result.status == "filled" else None
    )
    actual_quantity = result.actual_quantity or 0
    commission = Decimal("0.00")
    gross = Decimal("0.00")
    slippage_cost = Decimal("0.00")
    if result.status == "filled":
        gross_float, commission_float, _stamp, _transfer, _total, _net = calculate_transaction_costs(
            direction,
            actual_quantity,
            float(execution_price),
            float(COMMISSION_RATE),
            float(MIN_COMMISSION),
            0.0,
            0.0,
            round_to_cents=True,
        )
        gross = _money(_decimal(gross_float, "fill gross"))
        commission = _money(_decimal(commission_float, "commission"))
        slippage_cost = _money(abs(execution_price - raw_open) * actual_quantity)

    position_after = portfolio.positions.get(symbol)
    row = {
        "path_id": path_id,
        "intent_id": intent["intent_id"],
        "signal_id": order.signal_id,
        "child_order_id": child_id,
        "audit_id": order.audit_id,
        "symbol": order.symbol,
        "order_reason": order.reason,
        "strategy_version": order.strategy_version,
        "signal_date": intent["signal_date"],
        "attempt_date": execution_date,
        "direction": direction,
        "requested_quantity": requested_quantity,
        "status": result.status,
        "rejection_reason": result.rejection_reason,
        "raw_open": raw_open,
        "execution_price": execution_price,
        "raw_close": raw_close,
        "actual_quantity": actual_quantity,
        "gross": gross,
        "commission": commission,
        "stamp_duty": Decimal("0.00"),
        "transfer_fee": Decimal("0.00"),
        "slippage_cost": slippage_cost,
        "capacity_quantity": capacity,
        "cash_after": _money(_decimal(portfolio.cash, "cash")),
        "position_quantity_after": position_after.quantity if position_after else 0,
        "sellable_quantity_after": position_after.sellable_quantity if position_after else 0,
    }

    max_affordable = 0
    if direction == "buy" and execution_price is not None:
        max_affordable = calculate_affordable_quantity(
            float(Decimal(str(row["cash_after"])) + gross + commission),
            float(execution_price),
            float(COMMISSION_RATE),
            float(MIN_COMMISSION),
            round_to_cents=True,
        )
    if direction == "buy":
        finished = result.status == "filled" and actual_quantity >= max_affordable and capacity >= requested_quantity
        # A rejection is retryable; later price or capacity can make a board lot executable.
    else:
        finished = result.status == "filled" and (position_after is None)
    return row, finished


def run_path(
    data_source,
    calendar,
    *,
    account_kind: str,
    start_date: date,
    end_date: date,
    events=(),
    slippage_rate: Decimal = Decimal("0.0005"),
    anchor_date: date = ANCHOR_DATE,
    initial_cash: Decimal = INITIAL_CASH,
    symbol: str = SYMBOL,
) -> dict[str, object]:
    """Run one isolated candidate or buy-and-hold research account."""
    if account_kind not in {"candidate", "buy_and_hold"}:
        raise ValueError("account_kind must be candidate or buy_and_hold")
    if symbol != SYMBOL:
        raise ValueError("Card017 supports only 510880.SH")
    slip = _decimal(slippage_rate, "slippage rate")
    if slip not in {Decimal("0.0005"), Decimal("0.001")}:
        raise ValueError("Card017 slippage must be 0.0005 or 0.001")
    cash = _money(_decimal(initial_cash, "initial cash"))
    if cash <= 0:
        raise ValueError("initial cash must be positive")

    all_dates = calendar.all_trading_dates()
    if start_date not in all_dates or end_date not in all_dates or end_date < start_date:
        raise ValueError("window boundaries must be ordered trading dates")
    start_index, end_index = all_dates.index(start_date), all_dates.index(end_date)
    window_dates = all_dates[start_index : end_index + 1]
    if not window_dates or window_dates[0] != start_date or window_dates[-1] != end_date:
        raise ValueError("window trading dates are incomplete")

    path_id = f"{account_kind}-{'base' if slip == Decimal('0.0005') else 'stress'}"
    portfolio = PortfolioState(cash=float(cash))
    dividend_ledger = DividendLedger(events)
    dividend_ledger.validate_for_backtest(start_date, end_date, window_dates)
    intents: list[dict[str, object]] = []
    attempts: list[dict[str, object]] = []
    cancellations: list[dict[str, object]] = []
    daily_snapshots: list[dict[str, object]] = []
    current_intent: dict[str, object] | None = None
    sequence = 0
    first_signal_date = calendar.previous_trading_day(start_date)

    if account_kind == "buy_and_hold":
        sequence += 1
        current_intent = _make_intent(
            path_id=path_id,
            direction="buy",
            signal_date=first_signal_date,
            created_date=first_signal_date,
            source="buy_and_hold_initial",
            sequence=sequence,
        )
        intents.append(current_intent)
    else:
        initial_signal = evaluate_month_end_signal(
            data_source, calendar, first_signal_date, symbol=symbol, anchor_date=anchor_date
        )
        if initial_signal["state"] == "above":
            sequence += 1
            current_intent = _make_intent(
                path_id=path_id,
                direction="buy",
                signal_date=first_signal_date,
                created_date=first_signal_date,
                source="month_end_ma250_initial",
                sequence=sequence,
            )
            intents.append(current_intent)

    initial_point = {
        "date": start_date,
        "nav": cash,
        "cash": cash,
        "position_value": Decimal("0.00"),
        "receivable": Decimal("0.00"),
        "quantity": 0,
        "sellable_quantity": 0,
        "is_initial_point": True,
    }
    for day in window_dates:
        portfolio.unlock_frozen_lots(day)
        dividend_ledger.settle_due_at_open(day, portfolio)
        cash_before_open = _money(_decimal(portfolio.cash, "cash before open"))
        if current_intent is not None and current_intent["status"] == "open":
            row, finished = _attempt_order(
                data_source=data_source,
                calendar=calendar,
                portfolio=portfolio,
                intent=current_intent,
                execution_date=day,
                path_id=path_id,
                slippage_rate=slip,
                source_sequence=sequence,
            )
            attempts.append(row)
            if finished:
                current_intent["status"] = "filled"
                current_intent["complete_date"] = day
                current_intent = None

        close_bar = data_source.get_daily_bar(symbol, day)
        portfolio.update_position_prices({symbol: close_bar.close})
        dividend_ledger.process_eod(day, portfolio)
        position = portfolio.positions.get(symbol)
        quantity = position.quantity if position else 0
        sellable = position.sellable_quantity if position else 0
        position_value = _money(_decimal(close_bar.close, f"{day} close") * quantity)
        receivable = dividend_ledger.total_receivable().quantize(CENT, rounding=ROUND_HALF_UP)
        cash_eod = _money(_decimal(portfolio.cash, "cash"))
        nav = _money(cash_eod + position_value + receivable)
        daily_snapshots.append({
            "date": day,
            "cash_before_open": cash_before_open,
            "cash": cash_eod,
            "position_value": position_value,
            "quantity": quantity,
            "sellable_quantity": sellable,
            "receivable": receivable,
            "nav": nav,
            "is_initial_point": False,
        })

        if account_kind == "candidate" and _month_end(calendar, day):
            signal = evaluate_month_end_signal(
                data_source, calendar, day, symbol=symbol, anchor_date=anchor_date
            )
            current_intent, sequence = _apply_month_end_target(
                signal,
                day=day,
                position_quantity=quantity,
                current_intent=current_intent,
                intents=intents,
                cancellations=cancellations,
                path_id=path_id,
                sequence=sequence,
            )

    if current_intent is not None and current_intent["status"] == "open":
        _cancel_intent(current_intent, cancellations, end_date, "window_end")

    result = {
        "path_id": path_id,
        "account_kind": account_kind,
        "slippage_rate": slip,
        "symbol": symbol,
        "start_date": start_date,
        "end_date": end_date,
        "initial_cash": cash,
        "initial_point": initial_point,
        "intents": intents,
        "attempts": attempts,
        "cancellations": cancellations,
        "daily_snapshots": daily_snapshots,
        "dividend_events": [event.__dict__.copy() for event in dividend_ledger.events],
        "dividend_provenance": dividend_ledger.provenance_lines(),
        "ending_cash": _money(_decimal(portfolio.cash, "ending cash")),
        "ending_quantity": portfolio.positions.get(symbol).quantity if symbol in portfolio.positions else 0,
        "ending_sellable_quantity": portfolio.positions.get(symbol).sellable_quantity if symbol in portfolio.positions else 0,
        "ending_receivable": dividend_ledger.total_receivable().quantize(CENT, rounding=ROUND_HALF_UP),
        "ending_nav": daily_snapshots[-1]["nav"],
        "metrics": {},
    }
    build_performance_windows(data_source, result, calendar)
    return result


def calculate_window_metrics(
    curve: list[dict[str, object]],
    exposure_rows: list[dict[str, object]],
    *,
    start_date: date,
    end_date: date,
    ending_nav: Decimal,
    exit_cost: Decimal,
    attempt_rows: list[dict[str, object]],
    scale: Decimal = Decimal(1),
    ending_nav_actual: Decimal | None = None,
    exit_cost_actual: Decimal | None = None,
    include_start_date_attempts: bool = True,
) -> dict[str, object]:
    """Calculate fixed Card017 metrics from a prepared dated curve."""
    if len(curve) < 2 or curve[0]["date"] != start_date or curve[-1]["date"] != end_date:
        raise ValueError("window risk curve is missing a boundary or EOD point")
    values = [Decimal(str(row["nav"])) for row in curve]
    if any(value <= 0 for value in values):
        raise ValueError("NAV must be positive for Card017 metrics")
    elapsed_days = (end_date - start_date).days
    if elapsed_days <= 0:
        raise ValueError("window must span at least one natural day")
    final_after_exit = _money(ending_nav - exit_cost)
    actual_nav = ending_nav if ending_nav_actual is None else ending_nav_actual
    actual_exit_cost = exit_cost if exit_cost_actual is None else exit_cost_actual
    actual_after_exit = _money(actual_nav - actual_exit_cost)
    actual_start_nav = values[0] / scale
    if final_after_exit < 0:
        raise ValueError("estimated exit value cannot be negative")

    with localcontext() as context:
        context.prec = 28
        cagr = (final_after_exit / values[0]) ** (Decimal(365) / Decimal(elapsed_days)) - Decimal(1)
        returns = [values[index] / values[index - 1] - Decimal(1) for index in range(1, len(values))]
        mean = sum(returns, Decimal(0)) / Decimal(len(returns))
        variance = sum(((value - mean) ** 2 for value in returns), Decimal(0)) / Decimal(len(returns))
        std = variance.sqrt()
        sharpe = (mean / std * Decimal(252).sqrt()) if std else Decimal(0)

    amount_dd, ratio_dd = _drawdowns(curve)
    if not exposure_rows:
        raise ValueError("window has no trading-day EOD exposure observations")
    exposures = [Decimal(str(row["position_value"])) / Decimal(str(row["nav"])) for row in exposure_rows]
    cash_ratios = [Decimal(str(row["cash"])) / Decimal(str(row["nav"])) for row in exposure_rows]
    selected = [
        row for row in attempt_rows
        if (start_date <= row["attempt_date"] if include_start_date_attempts else start_date < row["attempt_date"])
        and row["attempt_date"] <= end_date
    ]
    commissions = sum((Decimal(str(row["commission"])) for row in selected), Decimal(0))
    slippage = sum((Decimal(str(row["slippage_cost"])) for row in selected), Decimal(0))
    trade_count = sum(row["status"] == "filled" for row in selected)
    blocked_count = sum(row["status"] != "filled" for row in selected)

    return {
        "start_date": start_date,
        "end_date": end_date,
        "elapsed_natural_days": elapsed_days,
        "start_nav_comparison": _money(values[0]),
        "start_nav_actual": _money(actual_start_nav),
        "ending_nav_actual": _money(actual_nav),
        "ending_nav_comparison": _money(ending_nav),
        "estimated_exit_cost_actual": _money(actual_exit_cost),
        "estimated_exit_cost_comparison": _money(exit_cost),
        "estimated_exit_value_actual": actual_after_exit,
        "estimated_exit_value_comparison": final_after_exit,
        "net_gain_actual": _money(actual_after_exit - actual_start_nav),
        "net_gain_comparison": _money(final_after_exit - values[0]),
        "cagr": _ratio(cagr),
        "sharpe": _ratio(sharpe),
        "max_drawdown_amount": amount_dd,
        "max_drawdown_ratio": ratio_dd,
        "average_exposure": _ratio(sum(exposures, Decimal(0)) / Decimal(len(exposures))),
        "average_cash_ratio": _ratio(sum(cash_ratios, Decimal(0)) / Decimal(len(cash_ratios))),
        "commission_total_actual": _money(commissions),
        "commission_total_comparison": _money(commissions * scale),
        "slippage_cost_total_actual": _money(slippage),
        "slippage_cost_total_comparison": _money(slippage * scale),
        "trade_count": trade_count,
        "blocked_attempt_count": blocked_count,
        "scale": _ratio(scale),
    }


def _ratio(value: Decimal) -> Decimal:
    return value.quantize(RATIO_QUANTUM, rounding=ROUND_HALF_UP)


def _drawdowns(curve: list[dict[str, object]]) -> tuple[dict[str, object], dict[str, object]]:
    peak_value = Decimal(str(curve[0]["nav"]))
    peak_date = curve[0]["date"]
    peak_index = 0
    amount_max = Decimal(0)
    ratio_max = Decimal(0)
    amount_peak: tuple[int, date, Decimal] | None = None
    amount_trough: tuple[int, date] | None = None
    ratio_peak: tuple[int, date, Decimal] | None = None
    ratio_trough: tuple[int, date] | None = None
    for index, row in enumerate(curve):
        day = row["date"]
        value = Decimal(str(row["nav"]))
        if value > peak_value:
            peak_value, peak_date = value, day
            peak_index = index
        amount = peak_value - value
        ratio = amount / peak_value
        if amount > amount_max:
            amount_max = amount
            amount_peak = (peak_index, peak_date, peak_value)
            amount_trough = (index, day)
        if ratio > ratio_max:
            ratio_max = ratio
            ratio_peak = (peak_index, peak_date, peak_value)
            ratio_trough = (index, day)

    def dates(
        peak: tuple[int, date, Decimal] | None,
        trough: tuple[int, date] | None,
    ) -> dict[str, object]:
        if peak is None or trough is None:
            return {"peak_date": None, "trough_date": None, "recovery_date": None, "underwater_trading_days": 0}
        _peak_index, peak_day, peak_nav = peak
        trough_index, trough_day = trough
        recovery = next(
            (
                (index, row["date"])
                for index, row in enumerate(curve[trough_index + 1 :], start=trough_index + 1)
                if Decimal(str(row["nav"])) >= peak_nav
            ),
            None,
        )
        recovery_index = len(curve) - 1 if recovery is None else recovery[0]
        return {
            "peak_date": peak_day,
            "trough_date": trough_day,
            "recovery_date": recovery[1] if recovery is not None else None,
            "underwater_trading_days": max(0, recovery_index - trough_index),
        }

    amount_dates = dates(amount_peak, amount_trough)
    ratio_dates = dates(ratio_peak, ratio_trough)
    return (
        {"amount": _money(amount_max), **amount_dates},
        {"ratio": _ratio(ratio_max), **ratio_dates},
    )


def _exit_cost(data_source, symbol: str, target_date: date, quantity: int, slip: Decimal) -> Decimal:
    if quantity == 0:
        return Decimal("0.00")
    bar = data_source.get_daily_bar(symbol, target_date)
    raw_close = _decimal(bar.close, f"{target_date} close")
    execution_price = _adjusted_execution_price("sell", raw_close, slip)
    gross = execution_price * quantity
    commission = max(gross * COMMISSION_RATE, MIN_COMMISSION).quantize(CENT, rounding=ROUND_HALF_UP)
    lost_to_slippage = (raw_close - execution_price) * quantity
    return _money(lost_to_slippage + commission)


def build_performance_windows(data_source, result: dict[str, object], calendar=None) -> dict[str, dict[str, object]]:
    """Attach full, 2018-2019, and normalized 2020 research windows when present."""
    daily = list(result["daily_snapshots"])
    if not daily:
        return {}
    start_date = result["start_date"]
    slip = Decimal(str(result["slippage_rate"]))
    symbol = str(result["symbol"])
    by_date = {row["date"]: row for row in daily}
    windows: dict[str, dict[str, object]] = {}
    end_all = daily[-1]["date"]
    calendar_dates = calendar.all_trading_dates() if calendar is not None else [row["date"] for row in daily]

    def add_window(
        name: str,
        window_start: date,
        window_end: date,
        curve: list[dict[str, object]],
        exposures: list[dict[str, object]],
        scale: Decimal,
        include_start_date_attempts: bool = True,
    ) -> None:
        final = by_date[window_end]
        raw_exit_cost = _exit_cost(data_source, symbol, window_end, int(final["quantity"]), slip)
        exit_cost = _money(raw_exit_cost * scale)
        ending_nav = _money(Decimal(str(final["nav"])) * scale)
        scaled_curve = [dict(row, nav=_money(Decimal(str(row["nav"])) * scale)) for row in curve]
        windows[name] = calculate_window_metrics(
            scaled_curve,
            exposures,
            start_date=window_start,
            end_date=window_end,
            ending_nav=ending_nav,
            exit_cost=exit_cost,
            attempt_rows=list(result["attempts"]),
            scale=scale,
            ending_nav_actual=Decimal(str(final["nav"])),
            exit_cost_actual=raw_exit_cost,
            include_start_date_attempts=include_start_date_attempts,
        )

    initial = dict(result["initial_point"])
    if start_date in by_date and end_all > start_date:
        curve = [initial] + [row for row in daily if row["date"] <= end_all]
        add_window("full", start_date, end_all, curve, daily, Decimal(1))

    research_end = date(2019, 12, 31)
    expected_research_end = max((day for day in calendar_dates if day <= research_end), default=None)
    research_dates = [day for day in by_date if day <= research_end]
    if expected_research_end in by_date and research_dates and research_dates[-1] == expected_research_end and expected_research_end > start_date:
        end = expected_research_end
        curve = [initial] + [by_date[day] for day in research_dates]
        add_window("2018-2019", start_date, end, curve, [by_date[day] for day in research_dates], Decimal(1))

    first_2020 = min((day for day in calendar_dates if day.year == 2020), default=None)
    prior_2019 = max((day for day in calendar_dates if day.year == 2019), default=None)
    last_2020 = max((day for day in calendar_dates if day.year == 2020), default=None)
    if (
        first_2020 is not None
        and prior_2019 is not None
        and last_2020 is not None
        and first_2020 in by_date
        and prior_2019 in by_date
        and last_2020 in by_date
    ):
        base_nav = Decimal(str(by_date[prior_2019]["nav"]))
        if base_nav <= 0:
            raise ValueError("2019 year-end NAV must be positive to normalize 2020")
        scale = INITIAL_CASH / base_nav
        start_point = {"date": prior_2019, "nav": base_nav, "is_initial_point": True}
        rows = [by_date[day] for day in calendar_dates if first_2020 <= day <= last_2020 and day in by_date]
        curve = [start_point] + rows
        add_window("2020", prior_2019, last_2020, curve, rows, scale, include_start_date_attempts=False)
    result["metrics"] = windows
    return windows

