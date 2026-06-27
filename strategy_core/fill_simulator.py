from __future__ import annotations

from datetime import date

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
    Quantity may be reduced if capital is insufficient; order rejected if cannot afford one lot.
    
    Rejection reasons:
    - no data available
    - suspended
    - limit_up (buy) / limit_down (sell)
    - insufficient_capital (buy, after reducing quantity and costs)
    - no_position (sell)
    - insufficient_position (sell)
    """
    try:
        status = data_source.get_daily_status(order.symbol, execution_date)
        bar = data_source.get_daily_bar(order.symbol, execution_date)
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
    # Delegate to direction-specific fill logic
    if order.direction == "buy":
        return _simulate_buy_fill(
            order, execution_date, bar, status, portfolio,
            commission_rate, min_commission, stamp_duty_rate, transfer_fee_rate,
            slippage_rate, max_participation_rate, calendar
        )
    elif order.direction == "sell":
        return _simulate_sell_fill(
            order, execution_date, bar, status, portfolio,
            commission_rate, min_commission, stamp_duty_rate, transfer_fee_rate,
            slippage_rate, max_participation_rate
        )
    else:
        raise ValueError(f"unknown direction: {order.direction}")


def _simulate_buy_fill(order, execution_date, bar, status, portfolio,
                       commission_rate, min_commission, stamp_duty_rate, transfer_fee_rate,
                       slippage_rate, max_participation_rate, calendar):
    """Simulate buy order fill with transaction costs, T+1 freeze, slippage, and liquidity."""
    # Limit up check
    if status.is_limit_up:
        return order.model_copy(update={
            "status": "rejected",
            "rejection_reason": "limit_up",
        })
    
    # Liquidity check
    max_allowed_quantity = int(bar.volume * max_participation_rate / 100) * 100
    if order.quantity > max_allowed_quantity:
        return order.model_copy(update={
            "status": "rejected",
            "rejection_reason": "liquidity_shortfall",
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
    execution_price = base_price * (1 + slippage_rate)
    
    # Calculate costs for planned quantity
    gross, commission, stamp_duty, transfer_fee, total_fee, net_cash_flow = calculate_transaction_costs(
        "buy", order.quantity, execution_price,
        commission_rate, min_commission, stamp_duty_rate, transfer_fee_rate
    )
    total_cash_required = -net_cash_flow  # net_cash_flow is negative for buy
    
    # Capital check with costs
    if total_cash_required > portfolio.cash:
        # Calculate affordable quantity considering costs
        affordable_quantity = calculate_affordable_quantity(
            portfolio.cash, execution_price,
            commission_rate, min_commission, lot_size=100
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
            commission_rate, min_commission, stamp_duty_rate, transfer_fee_rate
        )
        total_cash_required = -net_cash_flow  # Update total_cash_required with new quantity
    else:
        actual_quantity = order.quantity
    
    # Final sanity check: ensure we have enough cash
    if total_cash_required > portfolio.cash:
        # This should not happen if calculate_affordable_quantity works correctly
        return order.model_copy(update={
            "status": "rejected",
            "rejection_reason": "insufficient_capital_after_recalc",
        })
    
    # Update portfolio
    portfolio.cash -= total_cash_required
    
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


def _simulate_sell_fill(order, execution_date, bar, status, portfolio,
                        commission_rate, min_commission, stamp_duty_rate, transfer_fee_rate,
                        slippage_rate, max_participation_rate):
    """Simulate sell order fill with transaction costs, slippage, and liquidity."""
    # Limit down check
    if status.is_limit_down:
        return order.model_copy(update={
            "status": "rejected",
            "rejection_reason": "limit_down",
        })
    
    # Liquidity check
    max_allowed_quantity = int(bar.volume * max_participation_rate / 100) * 100
    if order.quantity > max_allowed_quantity:
        return order.model_copy(update={
            "status": "rejected",
            "rejection_reason": "liquidity_shortfall",
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
    execution_price = base_price * (1 - slippage_rate)
    
    # Calculate costs
    gross, commission, stamp_duty, transfer_fee, total_fee, net_cash_flow = calculate_transaction_costs(
        "sell", order.quantity, execution_price,
        commission_rate, min_commission, stamp_duty_rate, transfer_fee_rate
    )
    
    # Add net proceeds to cash
    portfolio.cash += net_cash_flow  # net_cash_flow is positive for sell
    
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
