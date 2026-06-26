from __future__ import annotations


def calculate_transaction_costs(
    direction: str,
    quantity: int,
    price: float,
    commission_rate: float = 0.0003,
    min_commission: float = 5.0,
    stamp_duty_rate: float = 0.001,
    transfer_fee_rate: float = 0.0,
) -> tuple[float, float, float, float, float, float]:
    """
    Calculate transaction costs for A-share trading.
    
    Parameters:
    - direction: "buy" or "sell"
    - quantity: number of shares
    - price: execution price per share
    - commission_rate: commission rate (default 0.0003, 万三)
    - min_commission: minimum commission per trade (default 5.0 RMB)
    - stamp_duty_rate: stamp duty rate for sell only (default 0.001, 千一)
    - transfer_fee_rate: transfer fee rate (default 0.0, not implemented in MVP)
    
    Returns:
    - (gross_amount, commission, stamp_duty, transfer_fee, total_fee, net_cash_flow)
    
    Rules:
    - Commission: both buy and sell, with minimum threshold
    - Stamp duty: sell only, no minimum
    - Transfer fee: both directions if enabled (default 0)
    - net_cash_flow: negative for buy, positive for sell
    
    Examples:
    >>> calculate_transaction_costs("buy", 1000, 10.0)
    (10000.0, 5.0, 0.0, 0.0, 5.0, -10005.0)
    
    >>> calculate_transaction_costs("sell", 1000, 12.0)
    (12000.0, 5.0, 12.0, 0.0, 17.0, 11983.0)
    """
    gross_amount = quantity * price
    
    # Commission (both directions, with minimum threshold)
    commission = max(gross_amount * commission_rate, min_commission)
    
    # Stamp duty (sell only, no minimum)
    stamp_duty = gross_amount * stamp_duty_rate if direction == "sell" else 0.0
    
    # Transfer fee (both directions if enabled)
    transfer_fee = gross_amount * transfer_fee_rate if transfer_fee_rate > 0 else 0.0
    
    # Total fee
    total_fee = commission + stamp_duty + transfer_fee
    
    # Net cash flow
    if direction == "buy":
        net_cash_flow = -(gross_amount + total_fee)
    else:  # sell
        net_cash_flow = gross_amount - total_fee
    
    return gross_amount, commission, stamp_duty, transfer_fee, total_fee, net_cash_flow


def calculate_total_cash_required(
    quantity: int,
    price: float,
    commission_rate: float = 0.0003,
    min_commission: float = 5.0,
) -> float:
    """
    Calculate total cash required for a buy order including commission.
    
    Parameters:
    - quantity: number of shares
    - price: execution price per share
    - commission_rate: commission rate
    - min_commission: minimum commission
    
    Returns:
    - total_cash_required: gross_amount + commission
    """
    gross_amount = quantity * price
    commission = max(gross_amount * commission_rate, min_commission)
    return gross_amount + commission


def calculate_affordable_quantity(
    available_cash: float,
    price: float,
    commission_rate: float = 0.0003,
    min_commission: float = 5.0,
    lot_size: int = 100,
) -> int:
    """
    Calculate affordable quantity given available cash and transaction costs.
    
    Parameters:
    - available_cash: available capital
    - price: execution price per share
    - commission_rate: commission rate
    - min_commission: minimum commission
    - lot_size: lot size (default 100 for A-shares)
    
    Returns:
    - affordable_quantity: rounded down to lot_size multiples
    
    Algorithm:
    1. Check if cash can afford minimum commission
    2. Estimate max quantity assuming commission = amount * rate
    3. Verify actual commission and adjust if needed
    """
    # Cannot afford minimum commission
    if available_cash <= min_commission:
        return 0
    
    # Estimate max affordable quantity (assuming commission > min_commission)
    # cash = price * qty + max(price * qty * rate, min_commission)
    # If price * qty * rate > min_commission:
    #   cash = price * qty * (1 + rate)
    #   qty = cash / (price * (1 + rate))
    estimated_quantity = int((available_cash / (price * (1 + commission_rate))) / lot_size) * lot_size
    
    if estimated_quantity <= 0:
        return 0
    
    # Verify actual cost
    total_required = calculate_total_cash_required(estimated_quantity, price, commission_rate, min_commission)
    
    if total_required <= available_cash:
        return estimated_quantity
    
    # If estimate is too high, reduce by one lot and verify again
    reduced_quantity = estimated_quantity - lot_size
    if reduced_quantity <= 0:
        return 0
    
    total_required = calculate_total_cash_required(reduced_quantity, price, commission_rate, min_commission)
    if total_required <= available_cash:
        return reduced_quantity
    
    # Still too high, return 0
    return 0
