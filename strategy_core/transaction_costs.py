from __future__ import annotations

from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP


CENT = Decimal("0.01")


def _to_cents(amount: Decimal) -> Decimal:
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


def calculate_transaction_costs(
    direction: str,
    quantity: int,
    price: float,
    commission_rate: float = 0.0003,
    min_commission: float = 5.0,
    stamp_duty_rate: float = 0.001,
    transfer_fee_rate: float = 0.0,
    *,
    round_to_cents: bool = False,
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
    - round_to_cents: opt in to Decimal HALF_UP cent settlement; the default preserves legacy precision
    
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
    if round_to_cents:
        gross_raw = Decimal(quantity) * Decimal(str(price))
        gross_amount = _to_cents(gross_raw)
        commission_rate_decimal = Decimal(str(commission_rate))
        min_commission_decimal = Decimal(str(min_commission))
        commission = _to_cents(max(gross_raw * commission_rate_decimal, min_commission_decimal))
        stamp_duty = (
            _to_cents(gross_raw * Decimal(str(stamp_duty_rate)))
            if direction == "sell"
            else Decimal("0.00")
        )
        transfer_fee_rate_decimal = Decimal(str(transfer_fee_rate))
        transfer_fee = (
            _to_cents(gross_raw * transfer_fee_rate_decimal)
            if transfer_fee_rate_decimal > 0
            else Decimal("0.00")
        )
        total_fee = commission + stamp_duty + transfer_fee
        if direction == "buy":
            net_cash_flow = -(gross_amount + total_fee)
        else:
            net_cash_flow = gross_amount - total_fee

        return (
            float(gross_amount),
            float(commission),
            float(stamp_duty),
            float(transfer_fee),
            float(total_fee),
            float(net_cash_flow),
        )

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
    *,
    round_to_cents: bool = False,
) -> float:
    """
    Calculate total cash required for a buy order including commission.
    
    Parameters:
    - quantity: number of shares
    - price: execution price per share
    - commission_rate: commission rate
    - min_commission: minimum commission
    - round_to_cents: opt in to HALF_UP cent settlement for the buy debit
    
    Returns:
    - total_cash_required: gross_amount + commission
    """
    if round_to_cents:
        *_, net_cash_flow = calculate_transaction_costs(
            "buy",
            quantity,
            price,
            commission_rate,
            min_commission,
            stamp_duty_rate=0.0,
            transfer_fee_rate=0.0,
            round_to_cents=True,
        )
        return -net_cash_flow

    gross_amount = quantity * price
    commission = max(gross_amount * commission_rate, min_commission)
    return gross_amount + commission


def calculate_affordable_quantity(
    available_cash: float,
    price: float,
    commission_rate: float = 0.0003,
    min_commission: float = 5.0,
    lot_size: int = 100,
    *,
    round_to_cents: bool = False,
) -> int:
    """
    Calculate affordable quantity given available cash and transaction costs.
    
    Parameters:
    - available_cash: available capital
    - price: execution price per share
    - commission_rate: commission rate
    - min_commission: minimum commission
    - lot_size: lot size (default 100 for A-shares)
    - round_to_cents: opt in to HALF_UP cent settlement for affordability checks
    
    Returns:
    - affordable_quantity: rounded down to lot_size multiples
    
    With cent settlement enabled, affordability is found by binary searching whole lots
    against the same cent-rounded buy debit used by calculate_total_cash_required.
    The default retains the legacy estimate and adjustment algorithm.
    """
    if round_to_cents:
        available_cash_decimal = Decimal(str(available_cash))
        min_commission_decimal = Decimal(str(min_commission))
        if available_cash_decimal <= min_commission_decimal:
            return 0

        price_decimal = Decimal(str(price))
        lot_size_decimal = Decimal(lot_size)
        high = int(
            (available_cash_decimal / (price_decimal * lot_size_decimal)).to_integral_value(
                rounding=ROUND_FLOOR
            )
        ) + 1
        low = 0
        while low < high:
            middle = (low + high + 1) // 2
            quantity = middle * lot_size
            required = Decimal(str(calculate_total_cash_required(
                quantity,
                price,
                commission_rate,
                min_commission,
                round_to_cents=True,
            )))
            if required <= available_cash_decimal:
                low = middle
            else:
                high = middle - 1
        return low * lot_size

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
