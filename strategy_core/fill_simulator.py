from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_DOWN, ROUND_FLOOR, ROUND_HALF_UP

from contracts.stable import Order
from backend.app.golden_cases import GoldenCaseDataSource
from strategy_core.portfolio import Position, PortfolioState
from strategy_core.transaction_costs import (
    calculate_transaction_costs,
    calculate_affordable_quantity,
)


# Task 9: System baseline delisting penalty (5%)
# This is the minimum penalty applied to delisted/long-suspended positions
# Runtime cannot lower this value
DELISTING_PENALTY_PCT = 0.05
CURRENCY_CENT = Decimal("0.01")
PRICE_TICK = Decimal("0.001")


def _apply_cash_flow(
    portfolio: PortfolioState,
    net_cash_flow: float,
    *,
    round_to_cents: bool,
) -> None:
    if round_to_cents:
        cash = Decimal(str(portfolio.cash)) + Decimal(str(net_cash_flow))
        portfolio.cash = float(cash.quantize(CURRENCY_CENT, rounding=ROUND_HALF_UP))
    else:
        portfolio.cash += net_cash_flow


def _gate_execution_price(
    order: Order,
    execution_date: date,
    data_source,
    open_price: object,
    slippage_rate: float,
) -> tuple[Decimal, Decimal, Decimal]:
    get_limits = getattr(data_source, "get_daily_price_limits", None)
    if not callable(get_limits):
        raise ValueError(
            "execution price mode requires daily price limits from the data source"
        )
    try:
        limits = get_limits(order.symbol, execution_date)
    except KeyError:
        raise ValueError(
            f"execution price mode has no daily price limits for {order.symbol} on {execution_date}"
        ) from None
    if not isinstance(limits, (tuple, list)) or len(limits) != 2:
        raise ValueError("execution price mode daily price limits must be (lower, upper)")

    try:
        lower_limit = Decimal(str(limits[0]))
        upper_limit = Decimal(str(limits[1]))
        base_price = Decimal(str(open_price))
        rate = Decimal(str(slippage_rate))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("execution price mode received invalid price, band, or slippage") from None
    if any(not value.is_finite() or value <= 0 for value in (lower_limit, upper_limit, base_price)):
        raise ValueError("execution price mode prices and bands must be finite and positive")
    if lower_limit > upper_limit:
        raise ValueError("execution price mode lower price limit exceeds upper price limit")
    if any(value % PRICE_TICK != 0 for value in (lower_limit, upper_limit, base_price)):
        raise ValueError("execution price mode prices and bands must use the 0.001 tick")
    if not rate.is_finite() or rate < 0 or rate >= 1:
        raise ValueError("execution price mode slippage must be finite and in [0, 1)")

    if order.direction == "buy":
        adjusted = base_price * (Decimal("1") + rate)
        execution_price = adjusted.quantize(PRICE_TICK, rounding=ROUND_CEILING)
    else:
        adjusted = base_price * (Decimal("1") - rate)
        execution_price = adjusted.quantize(PRICE_TICK, rounding=ROUND_FLOOR)
    if not execution_price.is_finite() or execution_price <= 0:
        raise ValueError("execution price mode produced a nonpositive execution price")
    return execution_price, lower_limit, upper_limit


def simulate_fill(
    order: Order,
    execution_date: date,
    data_source: GoldenCaseDataSource,
    portfolio: PortfolioState,
    commission_rate: float = 0.0003,
    min_commission: float = 5.0,
    stamp_duty_rate: float = 0.001,
    transfer_fee_rate: float = 0.0,
    slippage_rate: float = 0.0,  # Task 6: slippage rate
    max_participation_rate: float = 0.10,  # Task 6: liquidity constraint (10%)
    calendar=None,  # TradingCalendar, required for T+1 freeze tracking
    *,
    cash_target_buy: bool = False,
    opening_capacity_mode: bool = False,
    round_to_cents: bool = False,
    execution_price_mode: bool = False,
) -> Order:
    """
    Simulate order fill on execution date with A-share constraints, transaction costs, and T+1 freeze logic.
    
    Returns updated Order with status filled/rejected.
    
    Fill logic:
    - Buy: fills at open price if not suspended/limit_up and capital sufficient (including costs)
    - Sell: fills at open price if not suspended/limit_down and position sufficient (T+1 check: only sellable_quantity)
    - Sell: fills at open price if not limit_down and position sufficient
    
    Transaction costs:
    - Commission: both buy/sell, with minimum threshold
    - Stamp duty: sell only
    - Transfer fee: optional (default 0)
    
    Capital verification uses actual execution_date open price plus transaction costs.
    With opening_capacity_mode enabled, the participation cap uses only the
    previous trading session's known volume and rounds down to 100-share lots.
    Quantity may be reduced if capital is insufficient; order rejected if cannot afford one lot.
    With round_to_cents enabled, cost calculations and cash mutations use cent-settled amounts.
    
    Rejection reasons:
    - no data available
    - suspended
    - limit_up (buy) / limit_down (sell)
    - insufficient_capital (buy, after reducing quantity and costs)
    - no_position (sell)
    - insufficient_position (sell)
    """
    previous_session_volume = None
    if opening_capacity_mode:
        previous_session_volume = _previous_session_volume(
            order.symbol, execution_date, data_source, calendar
        )

    try:
        status = data_source.get_daily_status(order.symbol, execution_date)
    except KeyError:
        return order.model_copy(update={
            "status": "rejected",
            "rejection_reason": f"no data available for {order.symbol} on {execution_date}",
        })
    
    # Suspended check
    if status.is_suspended:
        return order.model_copy(update={
            "status": "rejected",
            "rejection_reason": "suspended",
        })
    try:
        bar = data_source.get_daily_bar(order.symbol, execution_date)
    except KeyError:
        return order.model_copy(update={
            "status": "rejected",
            "rejection_reason": f"no data available for {order.symbol} on {execution_date}",
        })
    capacity_volume = previous_session_volume if opening_capacity_mode else bar.volume
    max_allowed_quantity = _max_participation_quantity(
        capacity_volume,
        max_participation_rate,
        strict=opening_capacity_mode,
    )
    capacity_rejection_reason = (
        "liquidity_shortfall_zero_previous_session_capacity"
        if opening_capacity_mode and max_allowed_quantity == 0
        else "liquidity_shortfall"
    )
    # Delegate to direction-specific fill logic
    if order.direction == "buy":
        return _simulate_buy_fill(
            order, execution_date, bar, status, portfolio,
            commission_rate, min_commission, stamp_duty_rate, transfer_fee_rate,
            slippage_rate, max_allowed_quantity, capacity_rejection_reason,
            calendar, cash_target_buy, round_to_cents, execution_price_mode,
            data_source,
        )
    elif order.direction == "sell":
        return _simulate_sell_fill(
            order, execution_date, bar, status, portfolio,
            commission_rate, min_commission, stamp_duty_rate, transfer_fee_rate,
            slippage_rate, max_allowed_quantity, capacity_rejection_reason,
            round_to_cents, execution_price_mode, data_source,
        )
    else:
        raise ValueError(f"unknown direction: {order.direction}")


def _previous_session_volume(symbol, execution_date, data_source, calendar) -> int:
    if calendar is None:
        raise ValueError("Trading calendar is required for opening capacity")
    try:
        previous_date = calendar.previous_trading_day(execution_date)
    except ValueError as exc:
        raise ValueError(
            f"opening capacity cannot determine previous trading session for {execution_date}: {exc}"
        ) from exc
    try:
        previous_bar = data_source.get_daily_bar(symbol, previous_date)
    except KeyError as exc:
        raise ValueError(
            f"opening capacity previous session bar is missing for {symbol} on {previous_date}"
        ) from exc

    if getattr(previous_bar, "date", None) != previous_date:
        raise ValueError(
            f"opening capacity previous session bar date mismatch for {symbol} on {previous_date}"
        )
    if getattr(previous_bar, "symbol", None) != symbol:
        raise ValueError(
            f"opening capacity previous session bar symbol mismatch for {symbol} on {previous_date}"
        )
    volume = getattr(previous_bar, "volume", None)
    if isinstance(volume, bool) or not isinstance(volume, int) or volume < 0:
        raise ValueError(
            f"opening capacity previous session volume is invalid for {symbol} on {previous_date}"
        )
    return volume


def _max_participation_quantity(volume, participation_rate, *, strict=False) -> int:
    if strict:
        try:
            rate = Decimal(str(participation_rate))
        except (InvalidOperation, ValueError, TypeError):
            raise ValueError("opening capacity participation rate is invalid") from None
        if not rate.is_finite() or rate < 0 or rate > 1:
            raise ValueError("opening capacity participation rate must be between 0 and 1")
        capacity_lots = (Decimal(volume) * rate / Decimal("100")).to_integral_value(
            rounding=ROUND_DOWN
        )
        return int(capacity_lots) * 100
    return int(volume * participation_rate / 100) * 100


def _simulate_buy_fill(order, execution_date, bar, status, portfolio,
                       commission_rate, min_commission, stamp_duty_rate, transfer_fee_rate,
                       slippage_rate, max_allowed_quantity, capacity_rejection_reason,
                       calendar, cash_target_buy=False, round_to_cents=False,
                       execution_price_mode=False, data_source=None):
    """Simulate buy order fill with transaction costs, T+1 freeze, slippage, and liquidity."""
    # Limit up check
    if status.is_limit_up:
        return order.model_copy(update={
            "status": "rejected",
            "rejection_reason": "limit_up",
        })
    
    # Liquidity check
    if not cash_target_buy and order.quantity > max_allowed_quantity:
        return order.model_copy(update={
            "status": "rejected",
            "rejection_reason": capacity_rejection_reason,
        })

    if calendar is None:
        raise ValueError("Trading calendar is required for T+1 freeze tracking in buy operations")
    try:
        calendar.next_trading_day(execution_date)
    except ValueError:
        return order.model_copy(update={
            "status": "rejected",
            "rejection_reason": "no_t1_unlock_date",
        })
    
    # Base execution price + slippage (buy pays more)
    base_price = bar.open
    if execution_price_mode:
        execution_price_decimal, _lower_limit, upper_limit = _gate_execution_price(
            order, execution_date, data_source, base_price, slippage_rate
        )
        if execution_price_decimal > upper_limit:
            return order.model_copy(update={
                "status": "rejected",
                "rejection_reason": "execution_price_outside_price_limit",
            })
        execution_price = float(execution_price_decimal)
    else:
        execution_price = base_price * (1 + slippage_rate)

    if cash_target_buy:
        actual_quantity = _max_cash_target_quantity(
            portfolio.cash,
            execution_price,
            commission_rate,
            min_commission,
            stamp_duty_rate,
            transfer_fee_rate,
            round_to_cents=round_to_cents,
        )
        if actual_quantity == 0:
            return order.model_copy(update={
                "status": "rejected",
                "rejection_reason": "insufficient_capital",
            })
        if actual_quantity > max_allowed_quantity:
            return order.model_copy(update={
                "status": "rejected",
                "rejection_reason": capacity_rejection_reason,
            })
    else:
        actual_quantity = order.quantity
    
    # Calculate costs for the planned quantity or the execution-time cash target.
    gross, commission, stamp_duty, transfer_fee, total_fee, net_cash_flow = calculate_transaction_costs(
        "buy", actual_quantity, execution_price,
        commission_rate, min_commission, stamp_duty_rate, transfer_fee_rate,
        round_to_cents=round_to_cents,
    )
    total_cash_required = -net_cash_flow  # net_cash_flow is negative for buy
    
    # Capital check with costs
    if total_cash_required > portfolio.cash and not cash_target_buy:
        # Calculate affordable quantity considering costs
        affordable_quantity = calculate_affordable_quantity(
            portfolio.cash, execution_price,
            commission_rate, min_commission, lot_size=100,
            round_to_cents=round_to_cents,
        )
        
        if affordable_quantity == 0:
            return order.model_copy(update={
                "status": "rejected",
                "rejection_reason": "insufficient_capital",
            })
        
        # Recalculate costs with reduced quantity
        actual_quantity = affordable_quantity
        gross, commission, stamp_duty, transfer_fee, total_fee, net_cash_flow = calculate_transaction_costs(
            "buy", actual_quantity, execution_price,
            commission_rate, min_commission, stamp_duty_rate, transfer_fee_rate,
            round_to_cents=round_to_cents,
        )
        total_cash_required = -net_cash_flow  # Update total_cash_required with new quantity
    elif total_cash_required > portfolio.cash:
        return order.model_copy(update={
            "status": "rejected",
            "rejection_reason": "insufficient_capital_after_recalc",
        })
    
    # Final sanity check: ensure we have enough cash
    if total_cash_required > portfolio.cash:
        # This should not happen if calculate_affordable_quantity works correctly
        return order.model_copy(update={
            "status": "rejected",
            "rejection_reason": "insufficient_capital_after_recalc",
        })
    
    # Update portfolio
    _apply_cash_flow(portfolio, net_cash_flow, round_to_cents=round_to_cents)
    
    # Validate portfolio invariants after cash deduction
    portfolio.validate_invariants()
    
    # Add position with T+1 freeze
    if order.symbol in portfolio.positions:
        # Update existing position via add_position (handles T+1)
        portfolio.add_position(
            symbol=order.symbol,
            quantity=actual_quantity,
            price=execution_price,
            buy_date=execution_date,
            calendar=calendar,
        )
        # Update last_price separately
        portfolio.positions[order.symbol].last_price = bar.close
    else:
        # New position
        portfolio.add_position(
            symbol=order.symbol,
            quantity=actual_quantity,
            price=execution_price,
            buy_date=execution_date,
            calendar=calendar,
        )
        portfolio.positions[order.symbol].last_price = bar.close
    
    return order.model_copy(update={
        "status": "filled",
        "actual_execution_date": execution_date,
        "actual_price": execution_price,
        "actual_quantity": actual_quantity,
    })


def _max_cash_target_quantity(
    available_cash,
    execution_price,
    commission_rate,
    min_commission,
    stamp_duty_rate,
    transfer_fee_rate,
    lot_size=100,
    *,
    round_to_cents=False,
):
    """Return the greatest whole-lot buy quantity covered by cash and all fees."""
    if available_cash <= 0 or execution_price <= 0:
        return 0

    high = int(available_cash / (execution_price * lot_size)) + 1
    low = 0
    while low < high:
        middle = (low + high + 1) // 2
        quantity = middle * lot_size
        *_, net_cash_flow = calculate_transaction_costs(
            "buy",
            quantity,
            execution_price,
            commission_rate,
            min_commission,
            stamp_duty_rate,
            transfer_fee_rate,
            round_to_cents=round_to_cents,
        )
        affordable = (
            Decimal(str(-net_cash_flow)) <= Decimal(str(available_cash))
            if round_to_cents
            else -net_cash_flow <= available_cash
        )
        if affordable:
            low = middle
        else:
            high = middle - 1
    return low * lot_size


def _simulate_sell_fill(order, execution_date, bar, status, portfolio,
                        commission_rate, min_commission, stamp_duty_rate, transfer_fee_rate,
                        slippage_rate, max_allowed_quantity, capacity_rejection_reason,
                        round_to_cents=False, execution_price_mode=False,
                        data_source=None):
    """Simulate sell order fill with transaction costs, slippage, and liquidity."""
    # Limit down check
    if status.is_limit_down:
        return order.model_copy(update={
            "status": "rejected",
            "rejection_reason": "limit_down",
        })
    
    # Liquidity check
    if order.quantity > max_allowed_quantity:
        return order.model_copy(update={
            "status": "rejected",
            "rejection_reason": capacity_rejection_reason,
        })
    
    # Position check
    if order.symbol not in portfolio.positions:
        return order.model_copy(update={
            "status": "rejected",
            "rejection_reason": "no_position",
        })
    
    position = portfolio.positions[order.symbol]
    
    # T+1 check: only sellable_quantity available
    if position.sellable_quantity < order.quantity:
        return order.model_copy(update={
            "status": "rejected",
            "rejection_reason": "insufficient_position",
        })
    
    # Base execution price - slippage (sell gets less)
    base_price = bar.open
    if execution_price_mode:
        execution_price_decimal, lower_limit, _upper_limit = _gate_execution_price(
            order, execution_date, data_source, base_price, slippage_rate
        )
        if execution_price_decimal < lower_limit:
            return order.model_copy(update={
                "status": "rejected",
                "rejection_reason": "execution_price_outside_price_limit",
            })
        execution_price = float(execution_price_decimal)
    else:
        execution_price = base_price * (1 - slippage_rate)
    
    # Calculate costs
    gross, commission, stamp_duty, transfer_fee, total_fee, net_cash_flow = calculate_transaction_costs(
        "sell", order.quantity, execution_price,
        commission_rate, min_commission, stamp_duty_rate, transfer_fee_rate,
        round_to_cents=round_to_cents,
    )
    
    # Add net proceeds to cash
    _apply_cash_flow(portfolio, net_cash_flow, round_to_cents=round_to_cents)
    
    # Reduce position (uses sellable_quantity)
    portfolio.reduce_position(order.symbol, order.quantity)
    
    # Update last_price if position still exists
    if order.symbol in portfolio.positions:
        portfolio.positions[order.symbol].last_price = bar.close
    
    return order.model_copy(update={
        "status": "filled",
        "actual_execution_date": execution_date,
        "actual_price": execution_price,
        "actual_quantity": order.quantity,
    })


def try_force_liquidation(
    symbol: str,
    position: Position,
    last_tradable_bar,  # DailyBar | None
    reason: str,
    runtime_penalty_pct: float | None = None,
) -> dict:
    """
    Force liquidation for delisted or long-suspended stock.
    
    Task 9: Delisting and long suspension liquidation policy.
    
    Policy:
    1. If last_tradable_bar available: use last tradable close with system baseline penalty
    2. If no reliable exit price: mark result as insufficient
    3. System baseline penalty (DELISTING_PENALTY_PCT) is fixed, cannot be lowered at runtime
    
    Args:
        symbol: Stock symbol
        position: Position to liquidate
        last_tradable_bar: Last tradable bar before delisting/suspension (None if unavailable)
        reason: "delisted" or "long_suspension"
        runtime_penalty_pct: Optional runtime penalty override (must be >= baseline, or raises ValueError)
    
    Returns:
        dict with liquidation record:
        - status: "liquidated" or "insufficient"
        - symbol, reason, quantity
        - exit_price, exit_price_source
        - penalty_pct (always >= DELISTING_PENALTY_PCT)
        - impact_on_value
        - insufficient_reason (if status=insufficient)
    
    Raises:
        ValueError: If runtime_penalty_pct < DELISTING_PENALTY_PCT (cannot lower baseline)
    """
    # Validate reason
    if reason not in ("delisted", "long_suspension"):
        raise ValueError(f"Invalid liquidation reason: {reason}")
    
    # Determine penalty: runtime override must not lower baseline
    if runtime_penalty_pct is not None:
        if runtime_penalty_pct < DELISTING_PENALTY_PCT:
            raise ValueError(
                f"Runtime penalty ({runtime_penalty_pct}) cannot be lower than "
                f"system baseline ({DELISTING_PENALTY_PCT})"
            )
        penalty_pct = runtime_penalty_pct
    else:
        penalty_pct = DELISTING_PENALTY_PCT
    
    # No reliable exit price → insufficient
    if last_tradable_bar is None:
        return {
            "status": "insufficient",
            "symbol": symbol,
            "reason": reason,
            "quantity": position.quantity,
            "exit_price": None,
            "exit_price_source": "none",
            "penalty_pct": penalty_pct,
            "impact_on_value": 0.0,
            "insufficient_reason": "no_reliable_exit_price",
        }
    
    # Use last tradable close with penalty
    base_price = last_tradable_bar.close
    exit_price = base_price * (1 - penalty_pct)
    impact_on_value = position.quantity * exit_price
    
    return {
        "status": "liquidated",
        "symbol": symbol,
        "reason": reason,
        "quantity": position.quantity,
        "exit_price": exit_price,
        "exit_price_source": "last_tradable_with_penalty",
        "penalty_pct": penalty_pct,
        "impact_on_value": impact_on_value,
        "base_price": base_price,
        "last_tradable_date": last_tradable_bar.date,
    }


def apply_force_liquidation(
    portfolio: PortfolioState,
    liquidation: dict,
) -> None:
    """
    Apply forced liquidation to portfolio.
    
    Task 9: Portfolio application of delisting/long suspension liquidation.
    
    Updates:
    - Removes position from portfolio
    - Adds liquidation proceeds to cash (with penalty applied)
    
    Args:
        portfolio: Portfolio state to update (mutated)
        liquidation: Liquidation record from try_force_liquidation()
    
    Raises:
        ValueError: If liquidation status is insufficient or position doesn't exist
    """
    if liquidation["status"] != "liquidated":
        raise ValueError(
            f"Cannot apply {liquidation['status']} liquidation. "
            f"Reason: {liquidation.get('insufficient_reason', 'unknown')}"
        )
    
    symbol = liquidation["symbol"]
    
    if symbol not in portfolio.positions:
        raise ValueError(f"Position {symbol} not found in portfolio")
    
    position = portfolio.positions[symbol]
    
    # Verify quantity matches
    if position.quantity != liquidation["quantity"]:
        raise ValueError(
            f"Position quantity mismatch: portfolio has {position.quantity}, "
            f"liquidation expects {liquidation['quantity']}"
        )
    
    # Add liquidation proceeds to cash (exit_price × quantity, penalty already applied)
    liquidation_proceeds = liquidation["impact_on_value"]
    portfolio.cash += liquidation_proceeds
    
    # Remove position entirely (forced liquidation closes all)
    del portfolio.positions[symbol]
    
    # Validate portfolio invariants
    portfolio.validate_invariants()
