"""Fixed, deterministic Card020 510880 volatility-budget validation runner."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_CEILING, ROUND_DOWN, ROUND_FLOOR, ROUND_HALF_UP, localcontext
from pathlib import Path
from statistics import stdev
from typing import Any

from contracts.stable import Order
from strategy_core.dividend_ledger import DividendLedger
from strategy_core.fill_simulator import simulate_fill
from strategy_core.portfolio import PortfolioState
from strategy_core.trading_calendar import TradingCalendar
from strategy_core.transaction_costs import calculate_affordable_quantity, calculate_transaction_costs


STRATEGY_ID = "510880-vol-budget-v1"
SYMBOL = "510880.SH"
PROTOCOL_SHA256 = "969903D59F949DA0024448128404266C0059EA1A7BEF901B6496045BFDDE8D9D"
INITIAL_CASH = Decimal("5000.00")
STATIC_BUDGET = Decimal("2500.00")
START_DATE = date(2018, 1, 2)
END_DATE = date(2020, 12, 31)
PREHEAT_START = date(2016, 12, 23)
PREHEAT_END = date(2017, 12, 31)
WINDOW = 60
VOL_TARGET = Decimal("0.10")
COMMISSION_RATE = Decimal("0.0003")
MIN_COMMISSION = Decimal("5.00")
COMMISSION_LIMIT = Decimal("0.005")
SLIPPAGE = {"base": Decimal("0.0005"), "stress": Decimal("0.001")}
CENT = Decimal("0.01")
TICK = Decimal("0.001")
Q10 = Decimal("0.0000000001")
SQRT_252 = Decimal(252).sqrt()
EXPECTED_PATHS = (
    ("candidate-base", "candidate", "base"),
    ("candidate-stress", "candidate", "stress"),
    ("buy_and_hold-base", "buy_and_hold", "base"),
    ("buy_and_hold-stress", "buy_and_hold", "stress"),
    ("static_half-base", "static_half", "base"),
    ("static_half-stress", "static_half", "stress"),
)


class Card020RunError(ValueError):
    pass


def _d(value: object, label: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except Exception:
        raise Card020RunError(f"invalid {label}") from None
    if not parsed.is_finite():
        raise Card020RunError(f"non-finite {label}")
    return parsed


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _shown(value: Decimal | None) -> str | None:
    return None if value is None else format(value.quantize(Q10, rounding=ROUND_HALF_UP), "f")


def _month_end(dates: list[date], index: int) -> bool:
    if index + 1 >= len(dates):
        return True
    current, following = dates[index], dates[index + 1]
    return (current.year, current.month) != (following.year, following.month)


def _adjusted_price(market, day: date) -> Decimal:
    bar = market.get_daily_bar(SYMBOL, day)
    close = _d(bar.close, f"{day} raw close")
    factor = _d(bar.adj_factor, f"{day} adjustment factor")
    if close <= 0 or factor <= 0:
        raise Card020RunError(f"invalid price data on {day}")
    return close * factor


def _signal_volatility(market, dates: list[date], signal_date: date) -> tuple[Decimal, list[date]]:
    observations = [day for day in dates if PREHEAT_START <= day <= signal_date]
    if len(observations) < WINDOW + 1:
        raise Card020RunError(f"missing 61 adjusted closes through {signal_date}")
    selected = observations[-(WINDOW + 1):]
    prices = [_adjusted_price(market, day) for day in selected]
    returns = [prices[index] / prices[index - 1] - Decimal(1) for index in range(1, len(prices))]
    if len(returns) != WINDOW:
        raise Card020RunError(f"incomplete 60-return window through {signal_date}")
    with localcontext() as context:
        context.prec = 28
        mean = sum(returns, Decimal(0)) / Decimal(len(returns))
        variance = sum(((value - mean) ** 2 for value in returns), Decimal(0)) / Decimal(len(returns) - 1)
        annualized = variance.sqrt() * SQRT_252
    if not annualized.is_finite() or annualized < 0:
        raise Card020RunError(f"invalid realized signal volatility through {signal_date}")
    return annualized, selected


def _target_weight(volatility: Decimal) -> Decimal:
    if volatility == 0:
        return Decimal(1)
    return min(Decimal(1), VOL_TARGET / volatility)


def _target_shares(weight: Decimal, nav: Decimal, raw_close: Decimal) -> int:
    if nav < 0 or raw_close <= 0:
        raise Card020RunError("invalid NAV or close for target share calculation")
    lots = (weight * nav / (Decimal(100) * raw_close)).to_integral_value(rounding=ROUND_DOWN)
    return int(lots) * 100


def _opening_capacity(market, calendar, execution_date: date) -> int:
    prior = calendar.previous_trading_day(execution_date)
    bar = market.get_daily_bar(SYMBOL, prior)
    if bar.date != prior or bar.symbol != SYMBOL:
        raise Card020RunError(f"previous-session bar identity mismatch on {prior}")
    volume = bar.volume
    if isinstance(volume, bool) or not isinstance(volume, int) or volume < 0:
        raise Card020RunError(f"invalid prior-session volume on {prior}")
    lots = (Decimal(volume) * Decimal("0.10") / Decimal(100)).to_integral_value(rounding=ROUND_DOWN)
    return int(lots) * 100


def _execution_price(raw_open: Decimal, direction: str, slip: Decimal) -> Decimal:
    adjusted = raw_open * (Decimal(1) + slip if direction == "buy" else Decimal(1) - slip)
    return adjusted.quantize(TICK, rounding=ROUND_CEILING if direction == "buy" else ROUND_FLOOR)


def _nav(portfolio: PortfolioState, receivable: Decimal, raw_close: Decimal) -> Decimal:
    quantity = portfolio.positions.get(SYMBOL).quantity if SYMBOL in portfolio.positions else 0
    return _money(Decimal(str(portfolio.cash)) + Decimal(quantity) * raw_close + receivable)


def _new_intent(path_id: str, *, source_date: date, target_shares: int, current_shares: int,
                intent_type: str, risk_change: bool, sequence: int) -> dict | None:
    delta = target_shares - current_shares
    if delta == 0:
        return None
    return {
        "intent_id": f"{path_id}:intent:{sequence:04d}",
        "source_target_date": source_date.isoformat(),
        "target_shares": target_shares,
        "direction": "buy" if delta > 0 else "sell",
        "remaining_quantity": abs(delta),
        "intent_type": intent_type,
        "dynamic_risk_change": bool(risk_change),
        "status": "open",
        "attempts": 0,
    }


def _risk_candidate_has_filled_rebalance(trades: list[dict]) -> bool:
    """Initial build retries never qualify as post-build dynamic adjustment."""
    return any(
        trade.get("intent_type") == "monthly_rebalance"
        and trade.get("actual_quantity", 0) > 0
        and trade.get("source_target_date") > PREHEAT_END.isoformat()
        for trade in trades
    )


def _window_activity(path: dict, start: date, end: date) -> dict:
    trades = [
        trade for trade in path["trades"]
        if start <= date.fromisoformat(trade["execution_date"]) <= end
    ]
    events = path["dividend_summary"]["events"]
    window_events = []
    for event in events:
        ex_date = date.fromisoformat(event["ex_date"])
        paid_date = date.fromisoformat(event["paid_date"]) if event["paid_date"] else None
        paid_by_end = paid_date is not None and paid_date <= end
        receivable_at_end = (
            _d(event["entitlement_amount_cny"], "window receivable")
            if ex_date <= end and not paid_by_end else Decimal(0)
        )
        if (
            (start <= ex_date <= end)
            or (paid_date is not None and start <= paid_date <= end)
            or receivable_at_end > 0
        ):
            window_events.append({
                **event,
                "paid_amount_cny": event["paid_amount_cny"] if paid_by_end else "0.00",
                "paid_date": paid_date.isoformat() if paid_by_end else None,
                "receivable_at_window_end_cny": format(_money(receivable_at_end), "f"),
            })
    end_snapshot = next(
        (row for row in reversed(path["daily_snapshots"]) if date.fromisoformat(row["date"]) <= end),
        None,
    )
    if end_snapshot is None:
        raise Card020RunError("window end snapshot is missing for activity summary")
    return {
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "trade_count": len(trades),
        "commission_total_cny": format(_money(sum(
            (_d(trade["commission_cny"], "window commission") for trade in trades), Decimal(0),
        )), "f"),
        "slippage_cost_total_cny": format(_money(sum(
            (_d(trade["slippage_cost_cny"], "window slippage") for trade in trades), Decimal(0),
        )), "f"),
        "dividend_entitlement_total_cny": format(_money(sum(
            (_d(event["entitlement_amount_cny"], "window dividend entitlement")
             for event in events if start <= date.fromisoformat(event["ex_date"]) <= end), Decimal(0),
        )), "f"),
        "dividend_paid_total_cny": format(_money(sum(
            (_d(event["paid_amount_cny"], "window dividend payment")
             for event in events if event["paid_date"] and start <= date.fromisoformat(event["paid_date"]) <= end), Decimal(0),
        )), "f"),
        "dividend_receivable_end_cny": end_snapshot["dividend_receivable_cny"],
        "dividend_events": window_events,
        "signal_volatility_observations": [
            {
                "signal_date": decision["signal_date"],
                "window_start": decision.get("window_start"),
                "window_end": decision.get("window_end"),
                "signal_volatility": decision.get("signal_volatility"),
                "target_weight": decision.get("target_weight"),
                "target_shares": decision.get("target_shares"),
            }
            for decision in path["decisions"]
            if path["account_type"] == "candidate"
            and (decision["intent_type"] == "initial_build" or start <= date.fromisoformat(decision["signal_date"]) <= end)
        ],
    }


def _commission_ratio_exceeds(quantity: int, execution_price: Decimal) -> bool:
    gross = Decimal(quantity) * execution_price
    if gross <= 0:
        return True
    commission = max(gross * COMMISSION_RATE, MIN_COMMISSION)
    return commission / gross > COMMISSION_LIMIT


def _audit_execution_price(raw_open: Decimal, direction: str, slip: Decimal) -> Decimal:
    """Independent copy of the frozen adverse-price arithmetic for reconciliation."""
    factor = Decimal(1) + slip if direction == "buy" else Decimal(1) - slip
    unrounded = raw_open * factor
    if direction == "buy":
        return (unrounded / TICK).to_integral_value(rounding=ROUND_CEILING) * TICK
    return (unrounded / TICK).to_integral_value(rounding=ROUND_FLOOR) * TICK


def _audit_capacity(market, trading_dates: list[date], execution_date: date) -> int:
    try:
        index = trading_dates.index(execution_date)
    except ValueError:
        raise Card020RunError("audit execution date is not in calendar") from None
    if index == 0:
        raise Card020RunError("audit has no previous trading session")
    prior = trading_dates[index - 1]
    previous_bar = market.get_daily_bar(SYMBOL, prior)
    if previous_bar.date != prior or previous_bar.symbol != SYMBOL:
        raise Card020RunError("audit prior bar identity mismatch")
    volume = previous_bar.volume
    if isinstance(volume, bool) or not isinstance(volume, int) or volume < 0:
        raise Card020RunError("audit prior volume is invalid")
    capacity = (Decimal(volume) / Decimal(1000)).to_integral_value(rounding=ROUND_FLOOR) * Decimal(100)
    return int(capacity)


def _audit_affordable_quantity(cash: Decimal, price: Decimal) -> int:
    """Independent whole-lot affordability search, separate from trade-cost helpers."""
    low, high = 0, int(cash / (price * Decimal(100))) + 1
    while low < high:
        middle = (low + high + 1) // 2
        quantity = middle * 100
        gross = (Decimal(quantity) * price).quantize(CENT, rounding=ROUND_HALF_UP)
        commission = max(
            (Decimal(quantity) * price * COMMISSION_RATE).quantize(CENT, rounding=ROUND_HALF_UP),
            MIN_COMMISSION,
        )
        if gross + commission <= cash:
            low = middle
        else:
            high = middle - 1
    return low * 100


def _simulate_path(
    *, path_id: str, account_type: str, cost_name: str, market, calendar,
    dates: list[date], dividend_events: list[dict],
) -> dict:
    slip = SLIPPAGE[cost_name]
    portfolio = PortfolioState(cash=float(INITIAL_CASH))
    ledger = DividendLedger(dividend_events)
    ledger.validate_for_backtest(START_DATE, END_DATE, dates)
    dividend_rows = {
        event.event_id: {
            "event_id": event.event_id,
            "ann_date": event.ann_date.isoformat(),
            "record_date": event.record_date.isoformat(),
            "ex_date": event.ex_date.isoformat(),
            "pay_date": event.pay_date.isoformat(),
            "div_cash_cny_per_share": format(event.div_cash, "f"),
            "source_refs": list(event.source_refs),
            "entitled_quantity": 0,
            "entitlement_amount_cny": "0.00",
            "paid_amount_cny": "0.00",
            "paid_date": None,
        }
        for event in ledger.events
    }
    dividend_receivables: dict[str, Decimal] = {}
    trade_rows: list[dict] = []
    attempt_rows: list[dict] = []
    decision_rows: list[dict] = []
    snapshots: list[dict] = []
    intent: dict | None = None
    intent_sequence = 0
    order_sequence = 0
    previous_target_weight: Decimal | None = None
    initial_target_date: date | None = None
    fill_days: set[date] = set()
    comparator_pending = account_type in {"buy_and_hold", "static_half"}
    comparator_source_date = calendar.previous_trading_day(START_DATE) if comparator_pending else None
    comparator_budget = INITIAL_CASH if account_type == "buy_and_hold" else STATIC_BUDGET

    if account_type == "candidate":
        preheat_dates = [day for day in dates if day <= PREHEAT_END]
        if not preheat_dates:
            raise Card020RunError("2017 year-end preheat date is missing")
        initial_target_date = preheat_dates[-1]
        volatility, window_dates = _signal_volatility(market, dates, initial_target_date)
        weight = _target_weight(volatility)
        raw_close = _d(market.get_daily_bar(SYMBOL, initial_target_date).close, "preheat raw close")
        nav = INITIAL_CASH
        target = _target_shares(weight, nav, raw_close)
        intent_sequence += 1
        intent = _new_intent(
            path_id, source_date=initial_target_date, target_shares=target,
            current_shares=0, intent_type="initial_build", risk_change=False,
            sequence=intent_sequence,
        )
        previous_target_weight = weight
        decision_rows.append({
            "signal_date": initial_target_date.isoformat(),
            "intent_type": "initial_build",
            "signal_volatility": _shown(volatility),
            "target_weight": _shown(weight),
            "target_shares": target,
            "window_start": window_dates[0].isoformat(),
            "window_end": window_dates[-1].isoformat(),
            "execution_status": "pending",
        })

    validation_dates = [day for day in dates if START_DATE <= day <= END_DATE]
    if not validation_dates or validation_dates[0] != START_DATE or validation_dates[-1] != END_DATE:
        raise Card020RunError("fixed validation window is not fully covered")

    for day in validation_dates:
        portfolio.unlock_frozen_lots(day)
        ledger.settle_due_at_open(day, portfolio)
        for event_id, amount in list(dividend_receivables.items()):
            if date.fromisoformat(dividend_rows[event_id]["pay_date"]) < day:
                row = dividend_rows[event_id]
                row["paid_amount_cny"] = format(amount, "f")
                row["paid_date"] = day.isoformat()
                del dividend_receivables[event_id]
        bar = market.get_daily_bar(SYMBOL, day)
        raw_open = _d(bar.open, f"{day} raw open")
        if raw_open <= 0:
            raise Card020RunError(f"nonpositive opening price on {day}")

        # The two simple comparators make one independent opening order and hold.
        if account_type in {"buy_and_hold", "static_half"} and comparator_pending:
            capacity = _opening_capacity(market, calendar, day)
            execution_price = _execution_price(raw_open, "buy", slip)
            affordable = calculate_affordable_quantity(
                float(comparator_budget), float(execution_price), float(COMMISSION_RATE),
                float(MIN_COMMISSION), lot_size=100, round_to_cents=True,
            )
            if capacity == 0 or affordable > capacity:
                attempt_rows.append({
                    "date": day.isoformat(), "intent_type": "initial_build",
                    "status": "deferred", "reason": "opening_capacity_shortfall",
                    "requested_quantity": affordable, "daily_capacity": capacity,
                })
            elif affordable:
                quantity = affordable
                if _commission_ratio_exceeds(quantity, execution_price):
                    attempt_rows.append({
                        "date": day.isoformat(), "intent_type": "initial_build",
                        "status": "cancelled", "reason": "commission_ratio_over_0.5_percent",
                    })
                    comparator_pending = False
                else:
                    order_sequence += 1
                    order = _order(path_id, order_sequence, day, comparator_source_date, quantity, "buy", "initial comparator build")
                    filled = simulate_fill(
                        order, day, market, portfolio,
                        commission_rate=float(COMMISSION_RATE), min_commission=float(MIN_COMMISSION),
                        stamp_duty_rate=0.0, transfer_fee_rate=0.0, slippage_rate=float(slip),
                        max_participation_rate=0.10, calendar=calendar,
                        opening_capacity_mode=True, round_to_cents=True, execution_price_mode=True,
                    )
                    attempt_rows.append({"date": day.isoformat(), "intent_type": "initial_build", "status": filled.status,
                                         "reason": filled.rejection_reason, "requested_quantity": quantity})
                    if filled.status == "filled":
                        trade_rows.append(_trade_row(
                            path_id, filled, day, raw_open, account_type, "initial_build", False,
                            comparator_source_date.isoformat(), intent_sequence=0,
                        ))
                        fill_days.add(day)
                        comparator_pending = False
            else:
                attempt_rows.append({
                    "date": day.isoformat(), "intent_type": "initial_build", "status": "deferred",
                    "reason": "cash_cannot_afford_one_lot", "requested_quantity": 0,
                })

        elif account_type == "candidate" and intent is not None and intent["status"] == "open":
            capacity = _opening_capacity(market, calendar, day)
            position = portfolio.positions.get(SYMBOL)
            held = position.quantity if position else 0
            remaining_to_target = abs(int(intent["target_shares"]) - held)
            if remaining_to_target == 0:
                intent["status"] = "filled"
            else:
                direction = intent["direction"]
                if direction == "buy":
                    execution_price = _execution_price(raw_open, direction, slip)
                    affordable = calculate_affordable_quantity(
                        float(portfolio.cash), float(execution_price), float(COMMISSION_RATE),
                        float(MIN_COMMISSION), lot_size=100, round_to_cents=True,
                    )
                    quantity = min(remaining_to_target, capacity, affordable)
                else:
                    execution_price = _execution_price(raw_open, direction, slip)
                    sellable = position.sellable_quantity if position else 0
                    quantity = min(remaining_to_target, capacity, sellable)
                if quantity <= 0:
                    reason = "capacity_zero" if capacity == 0 else "cash_or_t_plus_one"
                    attempt_rows.append({
                        "date": day.isoformat(), "intent_id": intent["intent_id"],
                        "source_target_date": intent["source_target_date"],
                        "intent_type": intent["intent_type"], "status": "deferred", "reason": reason,
                        "remaining_quantity": remaining_to_target,
                    })
                    intent["attempts"] += 1
                elif _commission_ratio_exceeds(quantity, execution_price):
                    intent["status"] = "cancelled"
                    attempt_rows.append({
                        "date": day.isoformat(), "intent_id": intent["intent_id"],
                        "source_target_date": intent["source_target_date"],
                        "intent_type": intent["intent_type"], "status": "cancelled",
                        "reason": "commission_ratio_over_0.5_percent",
                        "remaining_quantity": remaining_to_target,
                    })
                else:
                    order_sequence += 1
                    order = _order(path_id, order_sequence, day, date.fromisoformat(intent["source_target_date"]),
                                   quantity, direction, intent["intent_type"])
                    filled = simulate_fill(
                        order, day, market, portfolio,
                        commission_rate=float(COMMISSION_RATE), min_commission=float(MIN_COMMISSION),
                        stamp_duty_rate=0.0, transfer_fee_rate=0.0, slippage_rate=float(slip),
                        max_participation_rate=0.10, calendar=calendar,
                        opening_capacity_mode=True, round_to_cents=True, execution_price_mode=True,
                    )
                    attempt_rows.append({
                        "date": day.isoformat(), "intent_id": intent["intent_id"],
                        "source_target_date": intent["source_target_date"],
                        "intent_type": intent["intent_type"], "status": filled.status,
                        "reason": filled.rejection_reason, "requested_quantity": quantity,
                        "remaining_before": remaining_to_target,
                    })
                    if filled.status == "filled":
                        trade = _trade_row(
                            path_id, filled, day, raw_open, account_type,
                            intent["intent_type"], intent["dynamic_risk_change"],
                            intent["source_target_date"], intent_sequence=intent_sequence,
                        )
                        trade_rows.append(trade)
                        fill_days.add(day)
                        held_after = portfolio.positions.get(SYMBOL).quantity if SYMBOL in portfolio.positions else 0
                        remaining_after = abs(int(intent["target_shares"]) - held_after)
                        intent["remaining_quantity"] = remaining_after
                        if remaining_after == 0:
                            intent["status"] = "filled"
                    intent["attempts"] += 1

        # EOD updates: raw close, dividend rights/receivables, then book NAV.
        close = _d(bar.close, f"{day} raw close")
        if SYMBOL in portfolio.positions:
            portfolio.positions[SYMBOL].last_price = float(close)
        ledger.process_eod(day, portfolio)
        for event in ledger.events:
            row = dividend_rows[event.event_id]
            if event.record_date == day:
                position = portfolio.positions.get(SYMBOL)
                row["entitled_quantity"] = position.quantity if position is not None else 0
            if event.ex_date == day:
                amount = _money(event.div_cash * Decimal(row["entitled_quantity"]))
                row["entitlement_amount_cny"] = format(amount, "f")
                dividend_receivables[event.event_id] = amount
            if event.pay_date == day and event.event_id in dividend_receivables:
                amount = dividend_receivables.pop(event.event_id)
                row["paid_amount_cny"] = format(amount, "f")
                row["paid_date"] = day.isoformat()
        receivable = ledger.total_receivable()
        observed_receivable = sum(dividend_receivables.values(), Decimal(0))
        if observed_receivable != receivable:
            raise Card020RunError(f"dividend event trace disagrees with authoritative ledger on {day}")
        current_nav = _nav(portfolio, receivable, close)
        quantity = portfolio.positions.get(SYMBOL).quantity if SYMBOL in portfolio.positions else 0
        snapshots.append({
            "date": day.isoformat(),
            "cash_cny": format(_money(Decimal(str(portfolio.cash))), "f"),
            "quantity": quantity,
            "raw_close_cny": format(close, "f"),
            "dividend_receivable_cny": format(receivable, "f"),
            "book_nav_cny": format(current_nav, "f"),
        })

        # Month-end targets are formed after that day's open fills and close accounting.
        date_index = dates.index(day)
        if account_type == "candidate" and _month_end(dates, date_index):
            volatility, window_dates = _signal_volatility(market, dates, day)
            weight = _target_weight(volatility)
            target = _target_shares(weight, current_nav, close)
            held = quantity
            risk_change = previous_target_weight is not None and weight != previous_target_weight
            if intent is not None and intent["status"] == "open":
                intent["status"] = "cancelled"
                attempt_rows.append({
                    "date": day.isoformat(), "intent_id": intent["intent_id"],
                    "intent_type": intent["intent_type"], "status": "cancelled",
                    "reason": "superseded_by_new_month_end_target",
                    "remaining_quantity": intent["remaining_quantity"],
                })
            intent_sequence += 1
            intent = _new_intent(
                path_id, source_date=day, target_shares=target, current_shares=held,
                intent_type="monthly_rebalance", risk_change=risk_change,
                sequence=intent_sequence,
            )
            decision_rows.append({
                "signal_date": day.isoformat(), "intent_type": "monthly_rebalance",
                "signal_volatility": _shown(volatility), "target_weight": _shown(weight),
                "target_shares": target, "held_shares": held,
                "dynamic_risk_change": risk_change,
                "window_start": window_dates[0].isoformat(),
                "window_end": window_dates[-1].isoformat(),
                "execution_status": "pending" if intent else "no_trade_target",
            })
            previous_target_weight = weight

    if intent is not None and intent["status"] == "open":
        intent["status"] = "cancelled"
        attempt_rows.append({
            "date": END_DATE.isoformat(), "intent_id": intent["intent_id"],
            "intent_type": intent["intent_type"], "status": "cancelled",
            "reason": "validation_window_ended", "remaining_quantity": intent["remaining_quantity"],
        })

    return {
        "path_id": path_id,
        "account_type": account_type,
        "cost_scenario": cost_name,
        "slippage_rate": format(slip, "f"),
        "starting_capital_cny": format(INITIAL_CASH, "f"),
        "trade_count": len(trade_rows),
        "dynamic_risk_fill_count": sum(
            1 for trade in trade_rows
            if trade["intent_type"] == "monthly_rebalance"
            and trade["source_target_date"] > PREHEAT_END.isoformat()
            and trade["actual_quantity"] > 0
        ),
        "has_post_build_dynamic_risk_fill": _risk_candidate_has_filled_rebalance(trade_rows),
        "trades": trade_rows,
        "attempts": attempt_rows,
        "decisions": decision_rows,
        "daily_snapshots": snapshots,
        "ending_nav_cny": snapshots[-1]["book_nav_cny"],
        "commission_total_cny": format(_money(sum((_d(row["commission_cny"], "commission") for row in trade_rows), Decimal(0))), "f"),
        "slippage_cost_total_cny": format(_money(sum((_d(row["slippage_cost_cny"], "slippage") for row in trade_rows), Decimal(0))), "f"),
        "dividend_receivable_cny": snapshots[-1]["dividend_receivable_cny"],
        "dividend_summary": {
            "entitlement_total_cny": format(_money(sum(
                (_d(row["entitlement_amount_cny"], "dividend entitlement") for row in dividend_rows.values()),
                Decimal(0),
            )), "f"),
            "paid_total_cny": format(_money(sum(
                (_d(row["paid_amount_cny"], "paid dividend") for row in dividend_rows.values()),
                Decimal(0),
            )), "f"),
            "ending_receivable_cny": format(_money(observed_receivable), "f"),
            "events": list(dividend_rows.values()),
        },
    }


def _order(path_id: str, sequence: int, day: date, source_date: date, quantity: int,
           direction: str, reason: str) -> Order:
    if source_date >= day:
        raise Card020RunError("order execution date must follow its source target date")
    return Order(
        order_id=f"{path_id}:fill:{sequence:05d}", signal_id=f"{path_id}:target:{source_date.isoformat()}",
        signal_date=source_date, intended_execution_date=day, symbol=SYMBOL,
        direction=direction, quantity=quantity, reason=reason,
        strategy_version=STRATEGY_ID, generated_by="card020_fixed_runner", audit_id=f"{path_id}:{sequence:05d}",
    )


def _trade_row(path_id: str, filled: Order, day: date, raw_open: Decimal, account_type: str,
               intent_type: str, dynamic_risk_change: bool, source_target_date: str,
               *, intent_sequence: int) -> dict:
    if filled.status != "filled" or filled.actual_quantity is None or filled.actual_price is None:
        raise Card020RunError("fill simulator returned an incomplete fill")
    quantity = int(filled.actual_quantity)
    price = _d(filled.actual_price, "fill price")
    gross, commission, stamp, transfer, total_fee, net = calculate_transaction_costs(
        filled.direction, quantity, float(price), float(COMMISSION_RATE), float(MIN_COMMISSION),
        stamp_duty_rate=0.0, transfer_fee_rate=0.0, round_to_cents=True,
    )
    slip_cost = abs(price - raw_open) * quantity
    return {
        "trade_id": filled.order_id,
        "path_id": path_id,
        "account_type": account_type,
        "intent_id": f"{path_id}:intent:{intent_sequence:04d}" if intent_sequence else f"{path_id}:initial",
        "intent_type": intent_type,
        "dynamic_risk_change": bool(dynamic_risk_change),
        "source_target_date": source_target_date,
        "execution_date": day.isoformat(),
        "direction": filled.direction,
        "actual_quantity": quantity,
        "raw_open_cny": format(raw_open, "f"),
        "execution_price_cny": format(price, "f"),
        "gross_cny": format(_money(_d(gross, "gross")), "f"),
        "commission_cny": format(_money(_d(commission, "commission")), "f"),
        "stamp_duty_cny": format(_money(_d(stamp, "stamp duty")), "f"),
        "transfer_fee_cny": format(_money(_d(transfer, "transfer fee")), "f"),
        "total_fee_cny": format(_money(_d(total_fee, "total fee")), "f"),
        "net_cash_flow_cny": format(_money(_d(net, "cash flow")), "f"),
        "slippage_cost_cny": format(_money(slip_cost), "f"),
    }


def _drawdown(curve: list[tuple[str | None, Decimal]], *, amount_mode: bool) -> dict:
    peak_value = curve[0][1]
    peak_index = 0
    worst = Decimal(0)
    worst_peak_index = 0
    worst_trough_index = 0
    for index, (_day, value) in enumerate(curve):
        if value > peak_value:
            peak_value, peak_index = value, index
        drawdown = peak_value - value if amount_mode else (peak_value - value) / peak_value
        if drawdown > worst:
            worst = drawdown
            worst_peak_index = peak_index
            worst_trough_index = index
    peak_date = curve[worst_peak_index][0]
    trough_date = curve[worst_trough_index][0]
    recovery_index = next(
        (index for index in range(worst_trough_index + 1, len(curve)) if curve[index][1] >= curve[worst_peak_index][1]),
        None,
    )
    return {
        "value": worst,
        "peak_date": peak_date,
        "trough_date": trough_date,
        "recovery_date": curve[recovery_index][0] if recovery_index is not None else None,
        "underwater_trading_days": (
            recovery_index - worst_trough_index if recovery_index is not None
            else len(curve) - 1 - worst_trough_index
        ),
    }


def _curve_metrics(
    snapshots: list[dict], *, start_date: date, end_date: date,
    actual_start_nav: Decimal, evaluation_scale: Decimal, baseline_date: date,
) -> dict:
    selected = [row for row in snapshots if start_date <= date.fromisoformat(row["date"]) <= end_date]
    if not selected:
        raise Card020RunError(f"no daily NAV rows in {start_date} through {end_date}")
    actual_values = [_d(row["book_nav_cny"], "book NAV") for row in selected]
    if len(actual_values) != (end_date - start_date).days + 1:
        # Trading sessions are sparse by design; coverage is confirmed by the input calendar.
        pass
    eval_start = actual_start_nav * evaluation_scale
    curve = [(baseline_date.isoformat(), eval_start)] + [
        (row["date"], _d(row["book_nav_cny"], "book NAV") * evaluation_scale)
        for row in selected
    ]
    eval_values = [value for _, value in curve]
    daily_returns = [eval_values[i] / eval_values[i - 1] - Decimal(1) for i in range(1, len(eval_values))]
    if len(daily_returns) >= 2:
        mean = sum(daily_returns, Decimal(0)) / Decimal(len(daily_returns))
        variance = sum(((value - mean) ** 2 for value in daily_returns), Decimal(0)) / Decimal(len(daily_returns) - 1)
        realized_vol = variance.sqrt() * SQRT_252
    else:
        realized_vol = None
    end_actual = actual_values[-1]
    end_eval = curve[-1][1]
    drawdown_amount_eval = _drawdown(curve, amount_mode=True)
    drawdown_ratio_eval = _drawdown(curve, amount_mode=False)
    actual_curve = [(baseline_date.isoformat(), actual_start_nav)] + [(row["date"], _d(row["book_nav_cny"], "book NAV")) for row in selected]
    drawdown_amount_actual = _drawdown(actual_curve, amount_mode=True)
    drawdown_ratio_actual = _drawdown(actual_curve, amount_mode=False)
    elapsed_days = (end_date - baseline_date).days
    annualized = None
    if eval_start > 0 and end_eval > 0 and elapsed_days > 0:
        with localcontext() as context:
            context.prec = 28
            annualized = ((end_eval / eval_start).ln() * (Decimal(365) / Decimal(elapsed_days))).exp() - Decimal(1)
    average_exposure = sum(
        (Decimal(str(row["quantity"])) * _d(row["raw_close_cny"], "raw close") / _d(row["book_nav_cny"], "NAV") for row in selected),
        Decimal(0),
    ) / Decimal(len(selected))
    average_cash = sum(
        (_d(row["cash_cny"], "cash") / _d(row["book_nav_cny"], "NAV") for row in selected),
        Decimal(0),
    ) / Decimal(len(selected))
    return {
        "start_date": start_date.isoformat(), "end_date": end_date.isoformat(),
        "start_nav_actual_cny": format(_money(actual_start_nav), "f"),
        "end_nav_actual_cny": format(_money(end_actual), "f"),
        "evaluation_scale": _shown(evaluation_scale),
        "evaluation_initial_nav_cny": format(eval_start, "f"),
        "evaluation_end_nav_cny": format(end_eval, "f"),
        "net_gain_actual_cny": format(_money(end_actual - actual_start_nav), "f"),
        "evaluation_net_gain_cny": _shown(end_eval - eval_start),
        "return_ratio": _shown(end_eval / eval_start - Decimal(1)) if eval_start else None,
        "annualized_return": _shown(annualized),
        "realized_volatility": _shown(realized_vol),
        "max_drawdown_amount_evaluation_cny": _shown(drawdown_amount_eval["value"]),
        "max_drawdown_ratio": _shown(drawdown_ratio_eval["value"]),
        "drawdown_amount_peak_date": drawdown_amount_eval["peak_date"],
        "drawdown_amount_trough_date": drawdown_amount_eval["trough_date"],
        "drawdown_amount_recovery_date": drawdown_amount_eval["recovery_date"],
        "drawdown_amount_underwater_trading_days": drawdown_amount_eval["underwater_trading_days"],
        "drawdown_ratio_peak_date": drawdown_ratio_eval["peak_date"],
        "drawdown_ratio_trough_date": drawdown_ratio_eval["trough_date"],
        "drawdown_ratio_recovery_date": drawdown_ratio_eval["recovery_date"],
        "drawdown_ratio_underwater_trading_days": drawdown_ratio_eval["underwater_trading_days"],
        "max_drawdown_amount_actual_cny": _shown(drawdown_amount_actual["value"]),
        "max_drawdown_ratio_actual": _shown(drawdown_ratio_actual["value"]),
        "average_exposure_ratio": _shown(average_exposure),
        "average_cash_ratio": _shown(average_cash),
        "trading_days": len(selected),
        "decision_values": {
            "evaluation_initial_nav_cny": format(eval_start, "f"),
            "evaluation_end_nav_cny": format(end_eval, "f"),
            "max_drawdown_amount_evaluation_cny": format(drawdown_amount_eval["value"], "f"),
            "max_drawdown_ratio": format(drawdown_ratio_eval["value"], "f"),
        },
    }


def _dominates(comparator: dict, candidate: dict) -> bool:
    comparator_values = comparator["decision_values"]
    candidate_values = candidate["decision_values"]
    comp_terminal = _d(comparator_values["evaluation_end_nav_cny"], "comparator terminal value")
    candidate_terminal = _d(candidate_values["evaluation_end_nav_cny"], "candidate terminal value")
    comp_amount = _d(comparator_values["max_drawdown_amount_evaluation_cny"], "comparator drawdown amount")
    candidate_amount = _d(candidate_values["max_drawdown_amount_evaluation_cny"], "candidate drawdown amount")
    comp_ratio = _d(comparator_values["max_drawdown_ratio"], "comparator drawdown ratio")
    candidate_ratio = _d(candidate_values["max_drawdown_ratio"], "candidate drawdown ratio")
    value = comp_terminal >= candidate_terminal
    amount = comp_amount <= candidate_amount
    ratio = comp_ratio <= candidate_ratio
    strict = (
        comp_terminal > candidate_terminal or comp_amount < candidate_amount or comp_ratio < candidate_ratio
    )
    return value and amount and ratio and strict


def _classify(paths: dict[str, dict], critical_source_gaps: list[str], reconciled: bool) -> tuple[str, list[str]]:
    reasons: list[str] = list(critical_source_gaps)
    if not reconciled:
        reasons.append("至少一条路径未通过独立账本核对。")
    if reasons:
        return "D", reasons

    candidate = [paths[f"candidate-{cost}"] for cost in ("base", "stress")]
    dynamic_fill = any(item["has_post_build_dynamic_risk_fill"] for item in candidate)
    if not dynamic_fill:
        return "C", ["初始建仓以外，没有实际成交形成动态风险调整。"]
    stable_dominators = []
    for comparator in ("buy_and_hold", "static_half"):
        if all(
            _dominates(paths[f"{comparator}-{cost}"]["metrics"]["full"], paths[f"candidate-{cost}"]["metrics"]["full"])
            for cost in ("base", "stress")
        ):
            stable_dominators.append(comparator)
    if stable_dominators:
        return "C", [f"同一简单对照在基础与压力成本下均支配候选：{stable_dominators[0]}。"]

    full_ok = True
    for cost in ("base", "stress"):
        if not _dominates(paths[f"candidate-{cost}"]["metrics"]["full"], paths[f"buy_and_hold-{cost}"]["metrics"]["full"]):
            full_ok = False
    if full_ok:
        segment_ok = True
        for window in ("2018-2019", "2020"):
            for cost in ("base", "stress"):
                if _dominates(paths[f"buy_and_hold-{cost}"]["metrics"][window], paths[f"candidate-{cost}"]["metrics"][window]):
                    segment_ok = False
        if segment_ok:
            return "A", ["全期条件成立，买入持有未在任一规定分段成本情景中支配候选。"]
    return "B", ["结果未命中 D、C 或全部 A 条件；需查看全期、分段与成本取舍。"]


def _reconcile_path(path: dict, market, calendar, dividend_events: list[dict]) -> dict:
    snapshots = path["daily_snapshots"]
    trades_by_day: dict[str, list[dict]] = {}
    for trade in path["trades"]:
        trades_by_day.setdefault(trade["execution_date"], []).append(trade)
    if any(len(items) > 1 for items in trades_by_day.values()):
        return {"status": "failed", "reason": "multiple_fills_in_one_day"}

    cash = INITIAL_CASH
    shares = 0
    sellable = 0
    frozen: list[tuple[int, date]] = []
    receivable_by_event: dict[str, Decimal] = {}
    entitled: dict[str, int] = {}
    event_by_id = {}
    for raw in dividend_events:
        event_id = f"{raw['ts_code']}:{date.fromisoformat(raw['ann_date']).isoformat()}"
        row = {
            "event_id": event_id,
            "ann_date": date.fromisoformat(raw["ann_date"]).isoformat(),
            "record_date": date.fromisoformat(raw["record_date"]),
            "ex_date": date.fromisoformat(raw["ex_date"]),
            "pay_date": date.fromisoformat(raw["pay_date"]),
            "div_cash": _d(raw["div_cash"], "dividend per share"),
            "source_refs": [raw["source_ref"]],
        }
        existing = event_by_id.get(event_id)
        if existing is not None:
            if any(existing[key] != row[key] for key in ("record_date", "ex_date", "pay_date", "div_cash")):
                return {"status": "failed", "reason": "conflicting_dividend_event"}
            if row["source_refs"][0] not in existing["source_refs"]:
                existing["source_refs"].extend(row["source_refs"])
        else:
            event_by_id[event_id] = row
    event_rows = [event_by_id[event_id] for event_id in sorted(event_by_id)]
    scenario = path["cost_scenario"]
    slip = SLIPPAGE[scenario]
    trading_dates = calendar.all_trading_dates()
    trade_index = 0
    replayed_snapshots: list[dict] = []
    for snapshot in snapshots:
        day = date.fromisoformat(snapshot["date"])
        newly_sellable = sum(quantity for quantity, unlock in frozen if unlock <= day)
        sellable += newly_sellable
        frozen = [(quantity, unlock) for quantity, unlock in frozen if unlock > day]
        for event in event_rows:
            if event["pay_date"] < day and event["event_id"] in receivable_by_event:
                amount = receivable_by_event.pop(event["event_id"])
                cash = _money(cash + amount)
                event["paid_amount_cny"] = amount
                event["paid_date"] = day
        bar = market.get_daily_bar(SYMBOL, day)
        prev_capacity = _audit_capacity(market, trading_dates, day)
        for trade in trades_by_day.get(day.isoformat(), []):
            quantity = int(trade["actual_quantity"])
            direction = trade["direction"]
            raw_open = _d(bar.open, "reconciled raw open")
            expected_price = _audit_execution_price(raw_open, direction, slip)
            actual_price = _d(trade["execution_price_cny"], "reconciled execution price")
            source_date = date.fromisoformat(trade["source_target_date"])
            try:
                source_index = trading_dates.index(source_date)
                execution_index = trading_dates.index(day)
            except ValueError:
                return {"status": "failed", "reason": "source_or_execution_date_missing"}
            status = market.get_daily_status(SYMBOL, day)
            limits = market.get_daily_price_limits(SYMBOL, day)
            lower_limit, upper_limit = (_d(limits[0], "lower price limit"), _d(limits[1], "upper price limit"))
            blocked_by_market = (
                status.is_suspended
                or (direction == "buy" and status.is_limit_up)
                or (direction == "sell" and status.is_limit_down)
            )
            if (
                blocked_by_market or source_index >= execution_index
                or expected_price != actual_price or quantity > prev_capacity or quantity % 100
                or actual_price % TICK != 0 or actual_price < lower_limit or actual_price > upper_limit
            ):
                return {"status": "failed", "reason": "execution_legality_or_price_mismatch"}
            gross = _money(Decimal(quantity) * actual_price)
            commission = _money(max(Decimal(quantity) * actual_price * COMMISSION_RATE, MIN_COMMISSION))
            expected_net = -gross - commission if direction == "buy" else gross - commission
            expected_slippage = _money(abs(actual_price - raw_open) * quantity)
            if commission / gross > COMMISSION_LIMIT:
                return {"status": "failed", "reason": "commission_filter_mismatch"}
            if (
                _d(trade["gross_cny"], "reported gross") != gross
                or _d(trade["commission_cny"], "reported commission") != commission
                or _d(trade["total_fee_cny"], "reported fee") != commission
                or _d(trade["net_cash_flow_cny"], "reported net cash flow") != expected_net
                or _d(trade["slippage_cost_cny"], "reported slippage") != expected_slippage
            ):
                return {"status": "failed", "reason": "trade_cost_replay_mismatch"}
            if direction == "buy":
                if quantity > _audit_affordable_quantity(cash, actual_price):
                    return {"status": "failed", "reason": "buy_exceeds_available_cash"}
                cash = _money(cash - gross - commission)
                shares += quantity
                frozen.append((quantity, calendar.next_trading_day(day)))
            else:
                if quantity > sellable:
                    return {"status": "failed", "reason": "sell_violates_t_plus_one"}
                cash = _money(cash + gross - commission)
                shares -= quantity
                sellable -= quantity
            trade_index += 1
        for event in event_rows:
            if event["record_date"] == day:
                entitled[event["event_id"]] = shares
                event["entitled_quantity"] = shares
        for event in event_rows:
            if event["ex_date"] == day:
                amount = _money(event["div_cash"] * entitled.get(event["event_id"], 0))
                receivable_by_event[event["event_id"]] = amount
                event["entitlement_amount_cny"] = amount
        for event in event_rows:
            if event["pay_date"] == day and event["event_id"] in receivable_by_event:
                amount = receivable_by_event.pop(event["event_id"])
                cash = _money(cash + amount)
                event["paid_amount_cny"] = amount
                event["paid_date"] = day
        receivable = sum(receivable_by_event.values(), Decimal(0))
        close = _d(bar.close, "reconciled close")
        nav = _money(cash + Decimal(shares) * close + receivable)
        if (
            _money(cash) != _d(snapshot["cash_cny"], "reported cash")
            or shares != snapshot["quantity"]
            or receivable != _d(snapshot["dividend_receivable_cny"], "reported receivable")
            or nav != _d(snapshot["book_nav_cny"], "reported book NAV")
        ):
            return {"status": "failed", "reason": "daily_ledger_replay_mismatch", "date": day.isoformat()}
        if shares < 0 or sellable < 0 or shares != sellable + sum(quantity for quantity, _ in frozen) or cash < 0:
            return {"status": "failed", "reason": "independent_position_or_cash_invariant_failed", "date": day.isoformat()}
        replayed_snapshots.append({
            "date": day.isoformat(), "cash_cny": format(cash, "f"),
            "quantity": shares, "raw_close_cny": format(close, "f"),
            "dividend_receivable_cny": format(receivable, "f"),
            "book_nav_cny": format(nav, "f"),
        })

    expected_dividend_summary = {
        "entitlement_total_cny": format(_money(sum(
            (event.get("entitlement_amount_cny", Decimal(0)) for event in event_rows), Decimal(0),
        )), "f"),
        "paid_total_cny": format(_money(sum(
            (event.get("paid_amount_cny", Decimal(0)) for event in event_rows), Decimal(0),
        )), "f"),
        "ending_receivable_cny": format(_money(sum(receivable_by_event.values(), Decimal(0))), "f"),
        "events": [
            {
                "event_id": event["event_id"],
                "ann_date": event["ann_date"],
                "record_date": event["record_date"].isoformat(),
                "ex_date": event["ex_date"].isoformat(),
                "pay_date": event["pay_date"].isoformat(),
                "div_cash_cny_per_share": format(event["div_cash"], "f"),
                "source_refs": event["source_refs"],
                "entitled_quantity": event.get("entitled_quantity", 0),
                "entitlement_amount_cny": format(_money(event.get("entitlement_amount_cny", Decimal(0))), "f"),
                "paid_amount_cny": format(_money(event.get("paid_amount_cny", Decimal(0))), "f"),
                "paid_date": event["paid_date"].isoformat() if event.get("paid_date") else None,
            }
            for event in event_rows
        ],
    }
    if path.get("dividend_summary") != expected_dividend_summary:
        return {"status": "failed", "reason": "independent_dividend_event_trace_mismatch"}

    # Independently recompute window returns, realized volatility, drawdowns,
    # and average exposure from the replayed ledger, without using the runner metrics.
    window_specs = (
        ("full", START_DATE, END_DATE),
        ("2018-2019", START_DATE, date(2019, 12, 31)),
        ("2020", date(2020, 1, 2), END_DATE),
    )
    checked_fields = (
        "end_nav_actual_cny", "evaluation_end_nav_cny", "net_gain_actual_cny",
        "evaluation_net_gain_cny", "return_ratio", "annualized_return",
        "realized_volatility", "max_drawdown_amount_evaluation_cny",
        "max_drawdown_ratio", "drawdown_amount_peak_date", "drawdown_amount_trough_date",
        "drawdown_amount_recovery_date", "drawdown_ratio_peak_date",
        "drawdown_ratio_trough_date", "drawdown_ratio_recovery_date",
        "max_drawdown_amount_actual_cny", "max_drawdown_ratio_actual",
        "average_exposure_ratio", "average_cash_ratio",
        "drawdown_amount_underwater_trading_days", "drawdown_ratio_underwater_trading_days",
    )
    for window_name, start, end in window_specs:
        selected = [row for row in replayed_snapshots if start <= date.fromisoformat(row["date"]) <= end]
        if not selected:
            return {"status": "failed", "reason": "independent_metric_window_missing"}
        window_trades = [
            trade for trade in path["trades"]
            if start <= date.fromisoformat(trade["execution_date"]) <= end
        ]
        window_dividend_events = []
        for event in event_rows:
            paid_date = event.get("paid_date")
            paid_by_end = paid_date is not None and paid_date <= end
            receivable_at_end = (
                event.get("entitlement_amount_cny", Decimal(0))
                if event["ex_date"] <= end and not paid_by_end else Decimal(0)
            )
            if (
                start <= event["ex_date"] <= end
                or (paid_date is not None and start <= paid_date <= end)
                or receivable_at_end > 0
            ):
                window_dividend_events.append({
                    "event": event,
                    "paid_by_end": paid_by_end,
                    "receivable_at_end": receivable_at_end,
                })
        audit_activity = {
            "window_start": start.isoformat(),
            "window_end": end.isoformat(),
            "trade_count": len(window_trades),
            "commission_total_cny": format(_money(sum(
                (_money(max(
                    Decimal(int(trade["actual_quantity"]))
                    * _d(trade["execution_price_cny"], "activity price") * COMMISSION_RATE,
                    MIN_COMMISSION,
                )) for trade in window_trades), Decimal(0),
            )), "f"),
            "slippage_cost_total_cny": format(_money(sum(
                (_money(abs(
                    _d(market.get_daily_bar(SYMBOL, date.fromisoformat(trade["execution_date"])).open, "activity raw open")
                    - _d(trade["execution_price_cny"], "activity execution price")
                ) * Decimal(int(trade["actual_quantity"]))) for trade in window_trades), Decimal(0),
            )), "f"),
            "dividend_entitlement_total_cny": format(_money(sum(
                (event.get("entitlement_amount_cny", Decimal(0)) for event in event_rows
                 if start <= event["ex_date"] <= end), Decimal(0),
            )), "f"),
            "dividend_paid_total_cny": format(_money(sum(
                (event.get("paid_amount_cny", Decimal(0)) for event in event_rows
                 if event.get("paid_date") is not None and start <= event["paid_date"] <= end), Decimal(0),
            )), "f"),
            "dividend_receivable_end_cny": format(
                _money(_d(selected[-1]["dividend_receivable_cny"], "window-end receivable")), "f",
            ),
            "dividend_events": [
                {
                    "event_id": item["event"]["event_id"],
                    "ann_date": item["event"]["ann_date"],
                    "record_date": item["event"]["record_date"].isoformat(),
                    "ex_date": item["event"]["ex_date"].isoformat(),
                    "pay_date": item["event"]["pay_date"].isoformat(),
                    "div_cash_cny_per_share": format(item["event"]["div_cash"], "f"),
                    "source_refs": item["event"]["source_refs"],
                    "entitled_quantity": item["event"].get("entitled_quantity", 0),
                    "entitlement_amount_cny": format(_money(item["event"].get("entitlement_amount_cny", Decimal(0))), "f"),
                    "paid_amount_cny": format(_money(item["event"].get("paid_amount_cny", Decimal(0))), "f") if item["paid_by_end"] else "0.00",
                    "paid_date": item["event"]["paid_date"].isoformat() if item["paid_by_end"] else None,
                    "receivable_at_window_end_cny": format(_money(item["receivable_at_end"]), "f"),
                }
                for item in window_dividend_events
            ],
            "signal_volatility_observations": [
                {
                    "signal_date": decision["signal_date"],
                    "window_start": decision.get("window_start"),
                    "window_end": decision.get("window_end"),
                    "signal_volatility": decision.get("signal_volatility"),
                    "target_weight": decision.get("target_weight"),
                    "target_shares": decision.get("target_shares"),
                }
                for decision in path["decisions"]
                if path["account_type"] == "candidate"
                and (decision["intent_type"] == "initial_build" or start <= date.fromisoformat(decision["signal_date"]) <= end)
            ],
        }
        reported_activity = path.get("window_activity", {}).get(window_name, {})
        if audit_activity != reported_activity:
            return {
                "status": "failed", "reason": "independent_window_activity_replay_mismatch",
                "window": window_name,
                "mismatched_fields": [
                    key for key in audit_activity
                    if audit_activity.get(key) != reported_activity.get(key)
                ],
                "reported_values": {
                    key: {"replayed": audit_activity.get(key), "reported": reported_activity.get(key)}
                    for key in audit_activity
                    if audit_activity.get(key) != reported_activity.get(key)
                },
            }
        if window_name == "2020":
            prior = next((row for row in replayed_snapshots if row["date"] == "2019-12-31"), None)
            if prior is None:
                return {"status": "failed", "reason": "independent_2020_baseline_missing"}
            actual_start = _d(prior["book_nav_cny"], "independent 2019 NAV")
            scale = INITIAL_CASH / actual_start
            baseline_date = date(2019, 12, 31)
        else:
            actual_start = INITIAL_CASH
            scale = Decimal(1)
            baseline_date = start
        eval_start = actual_start * scale
        actual_values = [_d(row["book_nav_cny"], "independent NAV") for row in selected]
        eval_curve = [eval_start] + [value * scale for value in actual_values]
        eval_end = eval_curve[-1]
        actual_end = actual_values[-1]
        returns = [eval_curve[index] / eval_curve[index - 1] - Decimal(1) for index in range(1, len(eval_curve))]
        if len(returns) >= 2:
            mean_return = sum(returns, Decimal(0)) / Decimal(len(returns))
            variance = sum(((value - mean_return) ** 2 for value in returns), Decimal(0)) / Decimal(len(returns) - 1)
            audit_vol = variance.sqrt() * SQRT_252
        else:
            audit_vol = None

        def audit_drawdown(values: list[Decimal], ratio: bool) -> tuple[Decimal, int, int, int | None, int]:
            current_peak = values[0]
            peak_at = 0
            worst = Decimal(0)
            worst_peak = 0
            worst_trough = 0
            for index, value in enumerate(values):
                if value > current_peak:
                    current_peak, peak_at = value, index
                drawdown = (current_peak - value) / current_peak if ratio else current_peak - value
                if drawdown > worst:
                    worst, worst_peak, worst_trough = drawdown, peak_at, index
            recovery_at = next(
                (index for index in range(worst_trough + 1, len(values)) if values[index] >= values[worst_peak]),
                None,
            )
            underwater = recovery_at - worst_trough if recovery_at is not None else len(values) - 1 - worst_trough
            return worst, worst_peak, worst_trough, recovery_at, underwater

        amount_dd = audit_drawdown(eval_curve, False)
        ratio_dd = audit_drawdown(eval_curve, True)
        actual_curve = [actual_start] + actual_values
        actual_amount_dd = audit_drawdown(actual_curve, False)
        actual_ratio_dd = audit_drawdown(actual_curve, True)
        annualized = None
        if eval_start > 0 and eval_end > 0:
            with localcontext() as context:
                context.prec = 28
                elapsed_days = (end - baseline_date).days
                annualized = ((eval_end / eval_start).ln() * (Decimal(365) / Decimal(elapsed_days))).exp() - Decimal(1)
        average_exposure = sum((
            Decimal(row["quantity"]) * _d(row["raw_close_cny"], "independent close")
            / _d(row["book_nav_cny"], "independent NAV") for row in selected
        ), Decimal(0)) / Decimal(len(selected))
        average_cash = sum((
            _d(row["cash_cny"], "independent cash") / _d(row["book_nav_cny"], "independent NAV")
            for row in selected
        ), Decimal(0)) / Decimal(len(selected))
        date_for = lambda index: baseline_date.isoformat() if index == 0 else selected[index - 1]["date"]
        audit = {
            "end_nav_actual_cny": format(_money(actual_end), "f"),
            "evaluation_end_nav_cny": format(eval_end, "f"),
            "net_gain_actual_cny": format(_money(actual_end - actual_start), "f"),
            "evaluation_net_gain_cny": _shown(eval_end - eval_start),
            "return_ratio": _shown(eval_end / eval_start - Decimal(1)),
            "annualized_return": _shown(annualized),
            "realized_volatility": _shown(audit_vol),
            "max_drawdown_amount_evaluation_cny": _shown(amount_dd[0]),
            "max_drawdown_ratio": _shown(ratio_dd[0]),
            "drawdown_amount_peak_date": date_for(amount_dd[1]),
            "drawdown_amount_trough_date": date_for(amount_dd[2]),
            "drawdown_amount_recovery_date": date_for(amount_dd[3]) if amount_dd[3] is not None else None,
            "drawdown_ratio_peak_date": date_for(ratio_dd[1]),
            "drawdown_ratio_trough_date": date_for(ratio_dd[2]),
            "drawdown_ratio_recovery_date": date_for(ratio_dd[3]) if ratio_dd[3] is not None else None,
            "drawdown_amount_underwater_trading_days": amount_dd[4],
            "drawdown_ratio_underwater_trading_days": ratio_dd[4],
            "max_drawdown_amount_actual_cny": _shown(actual_amount_dd[0]),
            "max_drawdown_ratio_actual": _shown(actual_ratio_dd[0]),
            "average_exposure_ratio": _shown(average_exposure),
            "average_cash_ratio": _shown(average_cash),
        }
        expected = path["metrics"][window_name]
        if any(audit[field] != expected[field] for field in checked_fields):
            return {"status": "failed", "reason": "independent_metric_replay_mismatch", "window": window_name}
        decision_values = {
            "evaluation_initial_nav_cny": format(eval_start, "f"),
            "evaluation_end_nav_cny": format(eval_end, "f"),
            "max_drawdown_amount_evaluation_cny": format(amount_dd[0], "f"),
            "max_drawdown_ratio": format(ratio_dd[0], "f"),
        }
        if decision_values != expected["decision_values"]:
            return {"status": "failed", "reason": "independent_unrounded_decision_values_mismatch", "window": window_name}
    return {
        "status": "passed", "replayed_trades": trade_index,
        "replayed_sessions": len(snapshots), "independent_metric_windows": [item[0] for item in window_specs],
        "independent_metric_fields_checked": list(checked_fields),
        "independent_activity_windows_checked": [item[0] for item in window_specs],
    }


def _json_sha256(payload: dict) -> str:
    stable = {key: value for key, value in payload.items() if key not in {"result_sha256", "generated_at_utc"}}
    raw = json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest().upper()


def _load_fixed_inputs() -> tuple[Any, TradingCalendar, list[dict], dict]:
    from backend.services.card020_preflight import prepare_card020_inputs

    prepared = prepare_card020_inputs()
    return prepared["market"], prepared["calendar"], prepared["dividend_events"], prepared["data_provenance"]


def run_card020_validation(frozen: dict, *, market=None, calendar=None,
                           dividend_events: list[dict] | None = None,
                           data_provenance: dict | None = None) -> dict:
    """Execute six fixed account/cost paths only for an already page-frozen strategy."""
    if frozen.get("strategy_id") != STRATEGY_ID or frozen.get("protocol_sha256") != PROTOCOL_SHA256:
        raise Card020RunError("frozen strategy identity or protocol hash mismatch")
    if market is None or calendar is None or dividend_events is None:
        market, calendar, dividend_events, data_provenance = _load_fixed_inputs()
    if data_provenance is None:
        data_provenance = {"market": {"source_status": "test_input"}, "dividends": {"source_status": "test_input"}}
    dates = calendar.all_trading_dates()
    if START_DATE not in dates or END_DATE not in dates:
        raise Card020RunError("fixed 2018-2020 window endpoints are absent")
    if not any(day <= PREHEAT_END for day in dates):
        raise Card020RunError("preheat sessions are absent")
    paths: dict[str, dict] = {}
    for path_id, account_type, cost_name in EXPECTED_PATHS:
        path = _simulate_path(
            path_id=path_id, account_type=account_type, cost_name=cost_name,
            market=market, calendar=calendar, dates=dates, dividend_events=dividend_events,
        )
        paths[path_id] = path

    last_2019 = next((row for row in paths["candidate-base"]["daily_snapshots"] if row["date"] == "2019-12-31"), None)
    if last_2019 is None:
        raise Card020RunError("2019 year-end account NAV is missing")
    windows = {
        "full": (START_DATE, END_DATE),
        "2018-2019": (START_DATE, date(2019, 12, 31)),
        "2020": (date(2020, 1, 2), END_DATE),
    }
    for path in paths.values():
        snapshots = path["daily_snapshots"]
        for name, (start, end) in windows.items():
            if name == "full" or name == "2018-2019":
                actual_start = INITIAL_CASH
                scale = Decimal(1)
                baseline_date = start
            else:
                prior = next((row for row in snapshots if row["date"] == "2019-12-31"), None)
                if prior is None:
                    raise Card020RunError("2020 segment opening NAV is missing")
                actual_start = _d(prior["book_nav_cny"], "2019 year-end NAV")
                if actual_start <= 0:
                    raise Card020RunError("2020 segment opening NAV is nonpositive")
                scale = INITIAL_CASH / actual_start
                baseline_date = date(2019, 12, 31)
            path.setdefault("metrics", {})[name] = _curve_metrics(
                snapshots, start_date=start, end_date=end,
                actual_start_nav=actual_start, evaluation_scale=scale, baseline_date=baseline_date,
            )
            path.setdefault("window_activity", {})[name] = _window_activity(path, start, end)

    reconcile = {path_id: _reconcile_path(path, market, calendar, dividend_events) for path_id, path in paths.items()}
    reconciliation_passed = all(item["status"] == "passed" for item in reconcile.values())
    critical_source_gaps = data_provenance.get("critical_source_gaps", [])
    if not isinstance(critical_source_gaps, list):
        critical_source_gaps = ["来源准入记录格式无效。"]
    category, reasons = _classify(paths, critical_source_gaps, reconciliation_passed)

    public_paths = {}
    for path_id, path in paths.items():
        public_paths[path_id] = {
            key: value for key, value in path.items()
            if key not in {"trades", "attempts", "decisions"}
        }
        public_paths[path_id]["trades"] = path["trades"]
        public_paths[path_id]["attempts"] = path["attempts"]
        public_paths[path_id]["decisions"] = path["decisions"]

    payload = {
        "strategy_id": STRATEGY_ID,
        "protocol_revision": 3,
        "protocol_sha256": PROTOCOL_SHA256,
        "freeze_id": frozen["freeze_id"],
        "freeze_sha256": frozen["freeze_sha256"],
        "preflight_id": frozen.get("preflight_id"),
        "input_inventory_sha256": frozen.get("input_inventory_sha256"),
        "execution_bundle_sha256": frozen.get("execution_bundle_sha256"),
        "run_status": "completed",
        "evaluation_status": "blocked_D" if category == "D" else "evaluated",
        "evaluation_category": category,
        "category_reasons": reasons,
        "acceptance_status": "not_qualified",
        "formal_trade_qualification": False,
        "evidence_level": "low" if category == "D" or data_provenance.get("data_limitations") else "medium",
        "period_start_date": START_DATE.isoformat(),
        "period_end_date": END_DATE.isoformat(),
        "starting_capital_cny": format(INITIAL_CASH, "f"),
        "path_ids": [item[0] for item in EXPECTED_PATHS],
        "paths": public_paths,
        "data_provenance": data_provenance,
        "reconciliation_status": "passed" if reconciliation_passed else "failed",
        "reconciliation": reconcile,
        "historical_reuse": True,
        "not_out_of_sample": True,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest().upper(),
    }
    payload["result_sha256"] = _json_sha256(payload)
    return payload
