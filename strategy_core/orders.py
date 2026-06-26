from __future__ import annotations

from datetime import date

from contracts.stable import Order, OrderGenerationEvent, OrderGenerationResult, Signal
from strategy_core.position_sizer import PositionSizer
from strategy_core.price_provider import PriceProvider
from strategy_core.portfolio import Position


def generate_orders(
    signals: list[Signal],
    intended_execution_date: date,
    price_provider: PriceProvider,
    sizer: PositionSizer,
    available_capital: float,
    current_positions: dict[str, Position],
) -> OrderGenerationResult:
    """
    Convert signals into order intents with T+1 pre-check.

    Parameters:
    - signals: signal list
    - intended_execution_date: planned execution date (must be after signal_date)
    - price_provider: price query interface (uses signal_date close price for entry sizing)
    - sizer: position sizing tool (for entry only)
    - available_capital: current available capital (for entry only)
    - current_positions: current portfolio positions (for exit only)

    Returns:
    - OrderGenerationResult with valid_orders and events

    Behavior:
    - entry signal: use sizer to calculate quantity; only generate order if quantity > 0
    - exit signal: check T+1 constraint; generate order for sellable_quantity only
    - hold signal: no order generated
    - conflict: same symbol has both entry and exit on same day → exit wins, entry rejected
    - no position for exit: create event with type="no_position_to_exit"
    - T+1 fully frozen: create event with type="t1_frozen", no order generated
    - T+1 partially frozen: create order for sellable_quantity + event with type="partial_exit_due_to_t1_freeze"
    """
    valid_orders: list[Order] = []
    events: list[OrderGenerationEvent] = []

    # Group signals by symbol to detect conflicts
    signals_by_symbol: dict[str, list[Signal]] = {}
    for signal in signals:
        if signal.symbol not in signals_by_symbol:
            signals_by_symbol[signal.symbol] = []
        signals_by_symbol[signal.symbol].append(signal)

    for symbol, symbol_signals in signals_by_symbol.items():
        # Check for entry + exit conflict on same symbol
        has_entry = any(s.signal_type == "entry" for s in symbol_signals)
        has_exit = any(s.signal_type == "exit" for s in symbol_signals)

        if has_entry and has_exit:
            # Conflict: exit wins, entry rejected
            for signal in symbol_signals:
                if signal.signal_type == "entry":
                    # Record conflict event
                    events.append(OrderGenerationEvent(
                        event_type="signal_conflict",
                        symbol=signal.symbol,
                        signal_id=signal.signal_id,
                        intended_execution_date=intended_execution_date,
                        reason="entry_exit_conflict_on_same_day",
                    ))
                elif signal.signal_type == "exit":
                    # Process exit normally
                    _process_exit_signal(
                        signal, intended_execution_date, current_positions, valid_orders, events
                    )
            continue

        # No conflict, process signals normally
        for signal in symbol_signals:
            if signal.signal_type == "hold":
                continue
            elif signal.signal_type == "exit":
                _process_exit_signal(
                    signal, intended_execution_date, current_positions, valid_orders, events
                )
            elif signal.signal_type == "entry":
                _process_entry_signal(
                    signal,
                    intended_execution_date,
                    price_provider,
                    sizer,
                    available_capital,
                    valid_orders,
                    events,
                )

    return OrderGenerationResult(valid_orders=valid_orders, events=events)


def _process_exit_signal(
    signal: Signal,
    intended_execution_date: date,
    current_positions: dict[str, Position],
    valid_orders: list[Order],
    events: list[OrderGenerationEvent],
) -> None:
    """Process exit signal with T+1 pre-check."""
    if signal.symbol not in current_positions:
        # No position to exit, create event
        events.append(OrderGenerationEvent(
            event_type="no_position_to_exit",
            symbol=signal.symbol,
            signal_id=signal.signal_id,
            intended_execution_date=intended_execution_date,
            reason="no_position_to_exit",
            requested_quantity=None,
            generated_quantity=0,
            sellable_quantity=0,
            total_quantity=0,
        ))
        return

    position = current_positions[signal.symbol]
    requested_quantity = position.quantity

    # T+1 pre-check
    if position.sellable_quantity == 0:
        # Fully frozen, no order generated
        events.append(OrderGenerationEvent(
            event_type="t1_frozen",
            symbol=signal.symbol,
            signal_id=signal.signal_id,
            intended_execution_date=intended_execution_date,
            reason=f"t1_frozen: all {position.quantity} shares frozen",
            requested_quantity=requested_quantity,
            generated_quantity=0,
            sellable_quantity=0,
            total_quantity=position.quantity,
        ))
        return

    if position.sellable_quantity < position.quantity:
        # Partially frozen, generate order for sellable_quantity
        events.append(OrderGenerationEvent(
            event_type="partial_exit_due_to_t1_freeze",
            symbol=signal.symbol,
            signal_id=signal.signal_id,
            intended_execution_date=intended_execution_date,
            reason=(
                f"partial_exit: requested {requested_quantity}, "
                f"only {position.sellable_quantity} sellable "
                f"(frozen {position.quantity - position.sellable_quantity})"
            ),
            requested_quantity=requested_quantity,
            generated_quantity=position.sellable_quantity,
            sellable_quantity=position.sellable_quantity,
            total_quantity=position.quantity,
        ))

    # Generate order for sellable_quantity (full or partial)
    valid_orders.append(Order(
        order_id=f"order:{signal.signal_id}:{intended_execution_date}",
        signal_id=signal.signal_id,
        signal_date=signal.signal_date,
        intended_execution_date=intended_execution_date,
        symbol=signal.symbol,
        direction="sell",
        quantity=position.sellable_quantity,
        reason=";".join(signal.triggered_rules),
        strategy_version=signal.strategy_version,
        audit_id=f"order:{signal.audit_id}:{intended_execution_date}",
    ))


def _process_entry_signal(
    signal: Signal,
    intended_execution_date: date,
    price_provider: PriceProvider,
    sizer: PositionSizer,
    available_capital: float,
    valid_orders: list[Order],
    events: list[OrderGenerationEvent],
) -> None:
    """Process entry signal: calculate quantity via sizer."""
    price = price_provider.get_price(signal.symbol, signal.signal_date)
    quantity = sizer.calculate_quantity(price, available_capital)

    if quantity == 0:
        # Insufficient capital, record event
        events.append(OrderGenerationEvent(
            event_type="zero_quantity",
            symbol=signal.symbol,
            signal_id=signal.signal_id,
            intended_execution_date=intended_execution_date,
            reason="insufficient_capital_for_one_lot",
        ))
        return

    valid_orders.append(Order(
        order_id=f"order:{signal.signal_id}:{intended_execution_date}",
        signal_id=signal.signal_id,
        signal_date=signal.signal_date,
        intended_execution_date=intended_execution_date,
        symbol=signal.symbol,
        direction="buy",
        quantity=quantity,
        reason=";".join(signal.triggered_rules),
        strategy_version=signal.strategy_version,
        audit_id=f"order:{signal.audit_id}:{intended_execution_date}",
    ))
