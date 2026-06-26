from __future__ import annotations

from datetime import date

from contracts.stable import Order
from backend.app.golden_cases import GoldenCaseDataSource
from strategy_core.portfolio import Position, PortfolioState
from strategy_core.transaction_costs import (
    calculate_transaction_costs,
    calculate_affordable_quantity,
)


def simulate_fill(
    order: Order,
    execution_date: date,
    data_source: GoldenCaseDataSource,
    portfolio: PortfolioState,
    commission_rate: float = 0.0003,
    min_commission: float = 5.0,
    stamp_duty_rate: float = 0.001,
    transfer_fee_rate: float = 0.0,
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
    
    if order.direction == "buy":
        return _simulate_buy_fill(
            order, execution_date, bar, status, portfolio,
            commission_rate, min_commission, stamp_duty_rate, transfer_fee_rate, calendar
        )
    elif order.direction == "sell":
        return _simulate_sell_fill(
            order, execution_date, bar, status, portfolio,
            commission_rate, min_commission, stamp_duty_rate, transfer_fee_rate
        )
    else:
        raise ValueError(f"unknown direction: {order.direction}")


def _simulate_buy_fill(order, execution_date, bar, status, portfolio,
                       commission_rate, min_commission, stamp_duty_rate, transfer_fee_rate, calendar):
    """Simulate buy order fill with transaction costs and T+1 freeze."""
    # Limit up check
    if status.is_limit_up:
        return order.model_copy(update={
            "status": "rejected",
            "rejection_reason": "limit_up",
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
    
    execution_price = bar.open
    
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
                        commission_rate, min_commission, stamp_duty_rate, transfer_fee_rate):
    """Simulate sell order fill with transaction costs."""
    # Limit down check
    if status.is_limit_down:
        return order.model_copy(update={
            "status": "rejected",
            "rejection_reason": "limit_down",
        })
    
    # Position check
    if order.symbol not in portfolio.positions:
        return order.model_copy(update={
            "status": "rejected",
            "rejection_reason": "no_position",
        })
    
    pos = portfolio.positions[order.symbol]
    
    # Check total quantity first (insufficient_position takes precedence over T+1)
    if order.quantity > pos.quantity:
        return order.model_copy(update={
            "status": "rejected",
            "rejection_reason": "insufficient_position",
        })
    
    # T+1 check: can only sell sellable_quantity
    if order.quantity > pos.sellable_quantity:
        return order.model_copy(update={
            "status": "rejected",
            "rejection_reason": (
                f"t1_violation: only {pos.sellable_quantity} sellable "
                f"(total {pos.quantity}, frozen {pos.quantity - pos.sellable_quantity})"
            ),
        })
    
    execution_price = bar.open
    
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
