from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import date as Date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from contracts.stable import BacktestResult, DailyPortfolioValue, Trade, StrategyConfig
from backend.app.golden_cases import GoldenCaseDataSource
from strategy_core.trading_calendar import TradingCalendar
from strategy_core.portfolio import PortfolioState
from strategy_core.universe_builder import build_universe
from strategy_core.signals import generate_signals
from strategy_core.orders import generate_orders
from strategy_core.position_sizer import PositionSizer
from strategy_core.fill_simulator import simulate_fill
from strategy_core.transaction_costs import calculate_transaction_costs
from strategy_core.prototype_gate import evaluate_prototype_gate
from backend.services.backtest_time_cursor import BacktestTimeCursor, FutureDataAccessError
from backend.services.b4_protocol_types import (
    OrderIntentRecord,
    FillRecord,
    RejectedOrderRecord,
    EventBacktestResult,
    DailyPortfolioSnapshot,
    FutureDataViolation,
)
from strategy_core.cursor_bound_data_view import CursorBoundDataView
from strategy_core.dividend_ledger import DividendLedger


CURRENCY_CENT = Decimal("0.01")


def _currency_float(value: Decimal | float) -> float:
    return float(Decimal(str(value)).quantize(CURRENCY_CENT, rounding=ROUND_HALF_UP))


def run_backtest(
    strategy_config: StrategyConfig,
    data_source: GoldenCaseDataSource,
    calendar: TradingCalendar,
    initial_capital: float = 100000.0,
    dividend_events: list[Mapping[str, object]] | None = None,
    *,
    cash_target_buy: bool = False,
    retry_temporarily_blocked_orders: bool = False,
    opening_capacity_mode: bool = False,
    round_to_cents: bool = False,
    minimum_commission: float = 5.0,
    execution_price_mode: bool = False,
    next_day_exit_intent_mode: bool = False,
    cash_yield_annual_rate: float = 0.0,
) -> BacktestResult:
    """
    Run event-loop backtest with A-share constraints and transaction costs.
    
    Workflow per trading day:
    1. Generate signals based on strategy rules
    2. Generate order intents (planned quantity based on signal_date close)
    3. Simulate fill on next trading day (verify capital with execution_date open + costs)
    4. Update positions and cash
    5. Record daily portfolio value
    
    Transaction costs are read from strategy_config.fill_model or use defaults:
    - commission_rate: 0.0003 (万三)
    - minimum_commission: 5.0 RMB (finite, nonnegative; overridable for a protocol stress case)
    - stamp_duty_rate: 0.001 (千一)
    - transfer_fee_rate: 0.0 (not implemented)
    - round_to_cents: false by default; when enabled, cash and EOD currency values settle to cents
    - execution_price_mode: false by default; when enabled, FillModel.slippage is rounded adversely
      to the 0.001 price tick and checked against date-specific price limits
    - next_day_exit_intent_mode: false by default; when enabled, exit intents include frozen lots
      that unlock by the next trading session's planned execution date
    - cash_yield_annual_rate: 0.0 by default; when positive, accrue ACT/365 interest on prior
      evaluation-date EOD available cash before current-session events, rounded to cents
    
    Returns:
        BacktestResult with trades (including cost breakdown), daily values, rejected orders, and warnings
    """
    try:
        minimum_commission = float(minimum_commission)
    except (TypeError, ValueError, OverflowError):
        raise ValueError("minimum_commission must be finite and nonnegative") from None
    if not math.isfinite(minimum_commission) or minimum_commission < 0:
        raise ValueError("minimum_commission must be finite and nonnegative")

    try:
        cash_yield_rate = Decimal(str(cash_yield_annual_rate))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("cash_yield_annual_rate must be finite and nonnegative") from None
    if not cash_yield_rate.is_finite() or cash_yield_rate < 0:
        raise ValueError("cash_yield_annual_rate must be finite and nonnegative")

    if round_to_cents:
        initial_capital = _currency_float(initial_capital)
    portfolio = PortfolioState(cash=initial_capital)
    filled_orders = []
    rejected_orders = []
    trades = []
    daily_values = []
    all_generation_events = []
    entry_signal_count = 0
    exit_signal_count = 0
    buy_order_count = 0
    sell_order_count = 0
    exit_triggered_rules: set[str] = set()
    t1_blocked_exit_count = 0
    partial_exit_due_to_t1_count = 0
    pending_retry_warnings = []
    counted_order_ids: set[str] = set()
    blocked_attempt_counts: dict[str, int] = {}
    retry_mode_enabled = retry_temporarily_blocked_orders or opening_capacity_mode
    
    universe = build_universe(strategy_config, data_source)
    if cash_target_buy:
        if strategy_config.risk_filters.max_position_per_stock < 1.0:
            raise ValueError(
                "cash_target_buy requires risk_filters.max_position_per_stock=1.0"
            )
        if strategy_config.risk_filters.max_total_position < 1.0:
            raise ValueError(
                "cash_target_buy requires risk_filters.max_total_position=1.0"
            )
    sizer = PositionSizer(position_ratio=0.2)
    
    # Read fee rates from fill_model or use defaults
    fill_model = strategy_config.fill_model
    commission_rate = fill_model.commission if fill_model.commission > 0 else 0.0003
    stamp_duty_rate = fill_model.stamp_tax
    min_commission = minimum_commission
    transfer_fee_rate = 0.0  # Not implemented in MVP
    slippage_rate = fill_model.slippage if execution_price_mode else 0.0
    if execution_price_mode:
        try:
            slippage_decimal = Decimal(str(slippage_rate))
        except (InvalidOperation, TypeError, ValueError):
            raise ValueError("execution price mode slippage must be finite and in [0, 1)") from None
        if not slippage_decimal.is_finite() or slippage_decimal < 0 or slippage_decimal >= 1:
            raise ValueError("execution price mode slippage must be finite and in [0, 1)")
    
    trading_dates = [
        trading_date
        for trading_date in calendar.all_trading_dates()
        if strategy_config.backtest_config.start_date
        <= trading_date
        <= strategy_config.backtest_config.end_date
    ]
    if not trading_dates:
        raise ValueError("no trading dates within configured backtest range")

    dividend_ledger = DividendLedger(dividend_events) if dividend_events else None
    if dividend_ledger is not None:
        dividend_ledger.validate_for_backtest(
            strategy_config.backtest_config.start_date,
            strategy_config.backtest_config.end_date,
            trading_dates,
        )
    if cash_yield_rate > 0 and dividend_ledger is None and not retry_mode_enabled:
        raise ValueError(
            "cash yield requires deferred next-session orders via dividend_events "
            "or a pending-order retry mode"
        )

    pending_orders = []
    pending_retries = []
    previous_eod_available_cash: Decimal | None = None
    previous_evaluation_date: Date | None = None

    def is_temporary_fill_block(order, rejection_reason):
        if rejection_reason == "suspended":
            return True
        if order.direction == "buy" and rejection_reason == "limit_up":
            return True
        if order.direction == "sell" and rejection_reason == "limit_down":
            return True
        if rejection_reason == "execution_price_outside_price_limit":
            return True
        if opening_capacity_mode and rejection_reason in {
            "liquidity_shortfall",
            "liquidity_shortfall_zero_previous_session_capacity",
        }:
            return True
        return False

    def execute_order_batch(orders, execution_date, *, retry_temporary_blocks=False):
        nonlocal buy_order_count, sell_order_count
        retry_orders = []
        for order in orders:
            if order.order_id not in counted_order_ids:
                counted_order_ids.add(order.order_id)
                if order.direction == "buy":
                    buy_order_count += 1
                elif order.direction == "sell":
                    sell_order_count += 1

            filled_order = simulate_fill(
                order, execution_date, data_source, portfolio,
                commission_rate=commission_rate,
                min_commission=min_commission,
                stamp_duty_rate=stamp_duty_rate,
                transfer_fee_rate=transfer_fee_rate,
                max_participation_rate=0.10,
                calendar=calendar,
                cash_target_buy=cash_target_buy,
                opening_capacity_mode=opening_capacity_mode,
                round_to_cents=round_to_cents,
                slippage_rate=slippage_rate,
                execution_price_mode=execution_price_mode,
            )

            if filled_order.status == "filled":
                filled_orders.append(filled_order)

                gross, commission, stamp_duty, transfer_fee, total_fee, net_cash_flow = calculate_transaction_costs(
                    filled_order.direction,
                    filled_order.actual_quantity,
                    filled_order.actual_price,
                    commission_rate,
                    min_commission,
                    stamp_duty_rate,
                    transfer_fee_rate,
                    round_to_cents=round_to_cents,
                )

                trades.append(Trade(
                    trade_id=f"trade:{filled_order.order_id}",
                    order_id=filled_order.order_id,
                    symbol=filled_order.symbol,
                    direction=filled_order.direction,
                    quantity=filled_order.actual_quantity,
                    price=filled_order.actual_price,
                    trade_date=filled_order.actual_execution_date,
                    gross_amount=gross,
                    commission=commission,
                    stamp_duty=stamp_duty,
                    transfer_fee=transfer_fee,
                    total_fee=total_fee,
                    net_cash_flow=net_cash_flow,
                    cost=net_cash_flow,
                ))
            else:
                if retry_temporary_blocks and is_temporary_fill_block(
                    order, filled_order.rejection_reason
                ):
                    blocked_attempt_count = blocked_attempt_counts.get(order.order_id, 0) + 1
                    blocked_attempt_counts[order.order_id] = blocked_attempt_count
                    pending_retry_warnings.append(
                        "pending_order_retry "
                        f"order_id={order.order_id} signal_date={order.signal_date} "
                        f"intended_execution_date={order.intended_execution_date} "
                        f"attempted_date={execution_date} "
                        f"rejection_reason={filled_order.rejection_reason} "
                        f"blocked_attempt={blocked_attempt_count}"
                    )
                    retry_orders.append(order)
                else:
                    rejected_orders.append(filled_order)
        return retry_orders
    
    # Record initial portfolio value
    daily_values.append(DailyPortfolioValue(
        date=trading_dates[0],
        cash=portfolio.cash,
        market_value=0.0,
        total_value=portfolio.cash,
    ))
    
    for i, trade_date in enumerate(trading_dates):
        if cash_yield_rate > 0 and previous_eod_available_cash is not None:
            if previous_evaluation_date is None:
                raise ValueError("cash yield prior cash is missing its evaluation date")
            elapsed_calendar_days = (trade_date - previous_evaluation_date).days
            if elapsed_calendar_days <= 0:
                raise ValueError("cash yield evaluation dates must be strictly increasing")
            interval_interest = (
                previous_eod_available_cash
                * cash_yield_rate
                * Decimal(elapsed_calendar_days)
                / Decimal("365")
            ).quantize(CURRENCY_CENT, rounding=ROUND_HALF_UP)
            portfolio.cash = float(previous_eod_available_cash + interval_interest)

        # Unlock frozen lots at start of trading day
        portfolio.unlock_frozen_lots(trade_date)

        if dividend_ledger is not None:
            # Weekend/holiday pay dates settle before the first later session opens.
            dividend_ledger.settle_due_at_open(trade_date, portfolio)

        if retry_mode_enabled:
            pending_retries = execute_order_batch(
                pending_retries,
                trade_date,
                retry_temporary_blocks=True,
            )
        elif dividend_ledger is not None:
            due_orders = [
                order for order in pending_orders
                if order.intended_execution_date == trade_date
            ]
            pending_orders = [
                order for order in pending_orders
                if order.intended_execution_date != trade_date
            ]
            execute_order_batch(due_orders, trade_date)
        
        # Generate entry signals for this trading day
        entry_signals = generate_signals(strategy_config, data_source, trade_date, universe)
        entry_signal_count += len(entry_signals)

        if retry_mode_enabled:
            pending_buy_symbols = {
                order.symbol for order in pending_retries if order.direction == "buy"
            }
            blocked_buy_symbols = pending_buy_symbols | set(portfolio.positions)
            filtered_entries = []
            for signal in entry_signals:
                if signal.symbol in blocked_buy_symbols:
                    pending_retry_warnings.append(
                        "pending_order_duplicate_suppressed "
                        f"direction=buy symbol={signal.symbol} signal_date={trade_date}"
                    )
                else:
                    filtered_entries.append(signal)
                    blocked_buy_symbols.add(signal.symbol)
            entry_signals = filtered_entries
        
        # Generate exit signals for current positions
        from strategy_core.signals import generate_exit_signals
        exit_signals = generate_exit_signals(strategy_config, data_source, trade_date, portfolio.positions)
        exit_signal_count += len(exit_signals)
        for signal in exit_signals:
            exit_triggered_rules.update(signal.triggered_rules)

        if retry_mode_enabled:
            pending_sell_symbols = {
                order.symbol for order in pending_retries if order.direction == "sell"
            }
            seen_exit_symbols = set(pending_sell_symbols)
            filtered_exits = []
            for signal in exit_signals:
                if signal.symbol in seen_exit_symbols:
                    pending_retry_warnings.append(
                        "pending_order_duplicate_suppressed "
                        f"direction=sell symbol={signal.symbol} signal_date={trade_date}"
                    )
                else:
                    filtered_exits.append(signal)
                    seen_exit_symbols.add(signal.symbol)
            exit_signals = filtered_exits
        
        # Combine entry and exit signals
        signals = entry_signals + exit_signals
        
        if signals:
            try:
                next_date = calendar.next_trading_day(trade_date)
            except ValueError:
                # Last trading day, cannot execute orders
                if dividend_ledger is None and not retry_mode_enabled:
                    break
                next_date = None

            if next_date is not None:
                if next_date > strategy_config.backtest_config.end_date:
                    if dividend_ledger is None and not retry_mode_enabled:
                        break
                else:
                    # Generate order intents using the existing sizing and T+1 path.
                    order_result = generate_orders(
                        signals,
                        intended_execution_date=next_date,
                        price_provider=data_source,
                        sizer=sizer,
                        available_capital=portfolio.available_capital(),
                        current_positions=portfolio.positions,
                        cash_target_buy=cash_target_buy,
                        next_day_exit_intent_mode=next_day_exit_intent_mode,
                    )

                    all_generation_events.extend(order_result.events)
                    for event in order_result.events:
                        if event.event_type == "t1_frozen":
                            t1_blocked_exit_count += 1
                        elif event.event_type == "partial_exit_due_to_t1_freeze":
                            partial_exit_due_to_t1_count += 1

                    if retry_mode_enabled:
                        pending_retries.extend(order_result.valid_orders)
                    elif dividend_ledger is None:
                        execute_order_batch(order_result.valid_orders, next_date)
                    else:
                        pending_orders.extend(order_result.valid_orders)
        
        # Update position prices with current day close
        if portfolio.positions:
            prices = {symbol: data_source.get_price(symbol, trade_date) for symbol in portfolio.positions}
            portfolio.update_position_prices(prices)

        if dividend_ledger is not None:
            dividend_ledger.process_eod(trade_date, portfolio)
        
        # Record daily portfolio value
        if round_to_cents:
            portfolio.cash = _currency_float(portfolio.cash)
            market_value = _currency_float(portfolio.market_value())
            total_value_amount = (
                dividend_ledger.total_value(portfolio)
                if dividend_ledger is not None
                else Decimal(str(portfolio.cash)) + Decimal(str(portfolio.market_value()))
            )
            total_value = _currency_float(total_value_amount)
        else:
            market_value = portfolio.market_value()
            total_value = (
                float(dividend_ledger.total_value(portfolio))
                if dividend_ledger is not None
                else portfolio.total_value()
            )
        if cash_yield_rate > 0:
            previous_eod_available_cash = Decimal(str(portfolio.cash))
            previous_evaluation_date = trade_date
        daily_values.append(DailyPortfolioValue(
            date=trade_date,
            cash=portfolio.cash,
            market_value=market_value,
            total_value=total_value,
        ))
    
    if retry_mode_enabled:
        for order in pending_retries:
            blocked_attempt_count = blocked_attempt_counts[order.order_id]
            rejected_orders.append(order.model_copy(update={
                "status": "rejected",
                "rejection_reason": (
                    "canceled_at_research_end_after_"
                    f"{blocked_attempt_count}_blocked_attempts"
                ),
            }))
            pending_retry_warnings.append(
                "pending_order_canceled_at_research_end "
                f"order_id={order.order_id} blocked_attempts={blocked_attempt_count}"
            )

    if round_to_cents:
        final_capital_amount = (
            dividend_ledger.total_value(portfolio)
            if dividend_ledger is not None
            else Decimal(str(portfolio.cash)) + Decimal(str(portfolio.market_value()))
        )
        final_capital = _currency_float(final_capital_amount)
    else:
        final_capital = (
            float(dividend_ledger.total_value(portfolio))
            if dividend_ledger is not None
            else portfolio.total_value()
        )
    buy_fill_count = sum(1 for order in filled_orders if order.direction == "buy")
    sell_fill_count = sum(1 for order in filled_orders if order.direction == "sell")
    exit_rejected_count = sum(1 for order in rejected_orders if order.direction == "sell")
    
    # Calculate round-trips (for audit trail)
    from strategy_core.lot_matching import LotMatcher
    sorted_trades = sorted(trades, key=lambda t: (t.trade_date, t.trade_id))
    matcher = LotMatcher()
    for trade in sorted_trades:
        matcher.process_trade(trade)
    round_trips = matcher.completed_round_trips
    
    # Evaluate prototype gate
    sample_split_date = strategy_config.backtest_config.sample_split.in_sample_end if strategy_config.backtest_config.sample_split else None
    gate_result = evaluate_prototype_gate(
        trades=trades,
        daily_values=daily_values,
        initial_capital=initial_capital,
        gate_config=strategy_config.prototype_gate,
        sample_split_date=sample_split_date,
    )
    
    result = BacktestResult(
        strategy_id=strategy_config.strategy_name,
        strategy_version=strategy_config.version,
        initial_capital=initial_capital,
        final_capital=final_capital,
        total_return=(final_capital - initial_capital) / initial_capital,
        trades=trades,
        daily_portfolio_values=daily_values,
        rejected_orders=rejected_orders,
        round_trips=round_trips,
        prototype_gate_result=gate_result,
        order_generation_events=all_generation_events,
        entry_signal_count=entry_signal_count,
        exit_signal_count=exit_signal_count,
        buy_order_count=buy_order_count,
        sell_order_count=sell_order_count,
        buy_fill_count=buy_fill_count,
        sell_fill_count=sell_fill_count,
        exit_rejected_count=exit_rejected_count,
        completed_round_trips=len(round_trips),
        exit_triggered_rules=sorted(exit_triggered_rules),
        t1_blocked_exit_count=t1_blocked_exit_count,
        partial_exit_due_to_t1_count=partial_exit_due_to_t1_count,
    )
    if dividend_ledger is not None:
        result.warnings.extend(dividend_ledger.provenance_lines())
    if cash_yield_rate > 0:
        result.warnings.append(
            "Cash yield applied to previous evaluation-date EOD available cash at "
            f"{format(cash_yield_rate, 'f')} ACT/365; each interval rounds half up to cents; "
            "receivables are excluded."
        )
    if cash_target_buy:
        result.warnings.append(
            "Cash-target buys are sized at fill; Order.quantity is a placeholder and "
            "Trade.quantity records the actual filled quantity."
        )
    if opening_capacity_mode:
        result.warnings.append(
            "Opening capacity mode uses previous-session known volume at 10% participation, "
            "floors to 100-share lots, and does not establish actual opening-auction queue priority "
            "or guarantee execution."
        )
    result.warnings.extend(pending_retry_warnings)
    return result


def run_event_backtest(
    strategy_config: StrategyConfig,
    data_source: GoldenCaseDataSource,
    calendar: TradingCalendar,
    protocol_snapshot_id: str,
    data_snapshot_hash: str,
    initial_capital: float = 100000.0,
    supplement_path=None,
    verified_supplement=None,
    observation_sink=None,
) -> EventBacktestResult:
    """
    Run event-driven backtest with T-day signal semantics and strict time cursor.
    
    Event loop per trading day T:
    1. Create signal_phase cursor (allowed_read_until = T)
    2. Build point-in-time universe as of T
    3. Generate signals using data <= T
    4. After T close: create order intents
    5. Record order intents with signal_date = T
    6. Move to T+1: create execution_phase cursor
    7. Process pending orders using T+1 data
    8. Record fills
    9. Record read trace
    
    Args:
        strategy_config: Strategy configuration
        data_source: Data source for bars/status
        calendar: Trading calendar
        protocol_snapshot_id: B3 protocol snapshot ID (required)
        data_snapshot_hash: B3 data snapshot hash (required)
        initial_capital: Initial capital
    
    Returns:
        EventBacktestResult with order intents, fills, violations, and read trace
    
    Raises:
        ValueError: If protocol_snapshot_id or data_snapshot_hash missing
    """
    from strategy_core.v3_relative_strength_executor import (
        V3RelativeStrengthExecutionSpec,
        run_v3_relative_strength_backtest,
    )

    if isinstance(strategy_config, V3RelativeStrengthExecutionSpec):
        if (supplement_path is None) == (verified_supplement is None):
            raise ValueError(
                "v3 execution requires exactly one of supplement_path or verified_supplement"
            )
        if supplement_path is not None:
            from scripts.verify_v3_execution_semantics import verify_v3_execution_semantics

            supplement = verify_v3_execution_semantics(supplement_path)
        else:
            if not isinstance(verified_supplement, Mapping):
                raise TypeError("v3 frozen verified supplement must be a mapping")
            expected_fields = {
                "status",
                "supplement_id",
                "manifest_sha256",
                "strategy_revision_id",
                "protocol_snapshot_id",
                "data_snapshot_hash",
            }
            if set(verified_supplement) != expected_fields:
                raise ValueError("v3 frozen verified supplement contract mismatch")
            supplement = dict(verified_supplement)
        if supplement.get("status") != "verified":
            raise ValueError(f"v3 execution supplement invalid: {supplement.get('reason', 'unknown')}")
        if supplement.get("supplement_id") != strategy_config.supplement_id:
            raise ValueError("v3 execution supplement identity mismatch")
        if supplement.get("strategy_revision_id") != strategy_config.strategy_revision_id:
            raise ValueError("v3 strategy revision mismatch")
        if supplement.get("protocol_snapshot_id") != strategy_config.protocol_snapshot_id:
            raise ValueError("v3 supplement protocol binding mismatch")
        if supplement.get("data_snapshot_hash") != strategy_config.data_snapshot_hash:
            raise ValueError("v3 supplement data snapshot binding mismatch")
        if protocol_snapshot_id != strategy_config.protocol_snapshot_id:
            raise ValueError("v3 protocol snapshot mismatch")
        if data_snapshot_hash != strategy_config.data_snapshot_hash:
            raise ValueError("v3 data snapshot hash mismatch")
        if initial_capital != strategy_config.initial_capital:
            raise ValueError("v3 initial capital mismatch")
        return run_v3_relative_strength_backtest(
            strategy_config, data_source, observation_sink=observation_sink
        )

    # Validate B3 protocol snapshot and data snapshot hash
    if not protocol_snapshot_id or protocol_snapshot_id.strip() == "":
        raise ValueError("protocol_snapshot_id is required for event backtest")
    
    if not data_snapshot_hash or data_snapshot_hash.strip() == "":
        raise ValueError("data_snapshot_hash is required for event backtest")
    
    # Initialize
    portfolio = PortfolioState(cash=initial_capital)
    order_intents: list[OrderIntentRecord] = []
    fills: list[FillRecord] = []
    rejected_orders = []
    all_read_trace: list[str] = []
    future_violations: list[FutureDataViolation] = []
    
    universe = build_universe(strategy_config, data_source)
    sizer = PositionSizer(position_ratio=0.2)
    
    trading_dates = [
        trading_date
        for trading_date in calendar.all_trading_dates()
        if strategy_config.backtest_config.start_date
        <= trading_date
        <= strategy_config.backtest_config.end_date
    ]
    
    if not trading_dates:
        raise ValueError("no trading dates within configured backtest range")
    
    for i, trade_date in enumerate(trading_dates):
        # === PHASE 1: Signal Phase (T日) ===
        # Create signal phase cursor: can only read <= T
        signal_cursor = BacktestTimeCursor(
            cursor_id=f"signal_{trade_date}",
            current_date=trade_date,
            evaluation_mode="signal_phase",
        )
        
        # Create cursor-bound data view for signal phase
        signal_data_view = CursorBoundDataView(data_source, signal_cursor)
        
        # Unlock frozen lots at start of trading day
        portfolio.unlock_frozen_lots(trade_date)
        
        # Generate entry signals using cursor-bound data view
        # Any attempt to read T+1 will raise FutureDataAccessError
        try:
            entry_signals = generate_signals(strategy_config, signal_data_view, trade_date, universe)
        except FutureDataAccessError as e:
            # Record violation and skip this day
            future_violations.append(e.violation)
            entry_signals = []
        
        # Generate exit signals for current positions
        from strategy_core.signals import generate_exit_signals
        try:
            exit_signals = generate_exit_signals(strategy_config, signal_data_view, trade_date, portfolio.positions)
        except FutureDataAccessError as e:
            future_violations.append(e.violation)
            exit_signals = []
        
        # Combine signals
        signals = entry_signals + exit_signals
        
        # Record signal phase read trace
        signal_state = signal_cursor.get_state()
        all_read_trace.extend(signal_state.read_trace)
        
        # === PHASE 2: Order Creation (after T close) ===
        if signals:
            try:
                next_date = calendar.next_trading_day(trade_date)
            except ValueError:
                # Last trading day, cannot execute orders
                break
            if next_date > strategy_config.backtest_config.end_date:
                break
            
            # Create order intents (planned quantity based on signal_date close)
            # Use signal_data_view for price reads (still within signal phase time bounds)
            order_result = generate_orders(
                signals,
                intended_execution_date=next_date,
                price_provider=signal_data_view,
                sizer=sizer,
                available_capital=portfolio.available_capital(),
                current_positions=portfolio.positions,
            )
            
            # Record order intents with signal_date
            for order in order_result.valid_orders:
                intent = OrderIntentRecord(
                    order_id=order.order_id,
                    symbol=order.symbol,
                    signal_date=trade_date,  # T
                    intent=order.direction,  # "buy" or "sell"
                    quantity=order.quantity,  # Order has 'quantity', not 'planned_quantity'
                )
                order_intents.append(intent)
            
            # === PHASE 3: Execution Phase (T+1) ===
            # Create execution phase cursor: can read T+1 for execution
            exec_cursor = BacktestTimeCursor(
                cursor_id=f"exec_{trade_date}",
                current_date=trade_date,
                evaluation_mode="execution_phase",
            )
            
            # Create cursor-bound data view for execution phase
            exec_data_view = CursorBoundDataView(data_source, exec_cursor)
            
            # Simulate fill on next_date using T+1 execution data
            # Task 6: A-share base cost model
            for order in order_result.valid_orders:
                try:
                    filled_order = simulate_fill(
                        order, next_date, exec_data_view, portfolio,
                        commission_rate=0.0003,  # Task 6: A-share commission (万三)
                        min_commission=5.0,      # Task 6: min commission
                        stamp_duty_rate=0.001,   # Task 6: stamp duty (千一)
                        transfer_fee_rate=0.0,
                        slippage_rate=0.0,       # Task 6: slippage (default 0)
                        max_participation_rate=0.10,  # Task 6: liquidity constraint (10%)
                        calendar=calendar,
                    )
                    
                    if filled_order.status == "filled":
                        # Record fill
                        fill = FillRecord(
                            fill_id=f"fill:{filled_order.order_id}",
                            order_id=filled_order.order_id,
                            symbol=filled_order.symbol,
                            fill_date=filled_order.actual_execution_date,
                            fill_price=filled_order.actual_price,
                            fill_quantity=filled_order.actual_quantity,
                            execution_mode="simulated",
                        )
                        fills.append(fill)
                    else:
                        # Record rejection
                        rejected_record = RejectedOrderRecord(
                            order_id=filled_order.order_id,
                            symbol=filled_order.symbol,
                            intended_date=filled_order.intended_execution_date,
                            rejection_reason=filled_order.rejection_reason,
                        )
                        rejected_orders.append(rejected_record)
                except FutureDataAccessError as e:
                    # Execution tried to read beyond T+1
                    future_violations.append(e.violation)
            
            # Record execution phase read trace
            exec_state = exec_cursor.get_state()
            all_read_trace.extend(exec_state.read_trace)
        
        # Update position prices with current day close (use signal_data_view for T)
        if portfolio.positions:
            try:
                prices = {symbol: signal_data_view.get_price(symbol, trade_date) for symbol in portfolio.positions}
                portfolio.update_position_prices(prices)
            except FutureDataAccessError as e:
                # Should not happen (reading T from T cursor), but record if it does
                future_violations.append(e.violation)
    
    # Create final portfolio snapshot
    final_portfolio = DailyPortfolioSnapshot(
        snapshot_id=f"final_{trading_dates[-1]}",
        snapshot_date=trading_dates[-1],
        cash=portfolio.cash,
        positions=tuple((symbol, pos.quantity) for symbol, pos in portfolio.positions.items()),
        portfolio_value=portfolio.total_value(),
    )
    
    # Return EventBacktestResult
    return EventBacktestResult(
        result_id=f"result_{protocol_snapshot_id}_{strategy_config.strategy_name}",
        strategy_revision_id=strategy_config.strategy_name,
        protocol_snapshot_id=protocol_snapshot_id,
        evaluation_mode="formal_backtest",
        backtest_start=trading_dates[0],
        backtest_end=trading_dates[-1],
        order_intents=tuple(order_intents),
        fills=tuple(fills),
        rejected_orders=tuple(rejected_orders),  # Task 6: return rejected orders
        future_violations=tuple(future_violations),
        final_portfolio=final_portfolio,
        frozen_at=Date.today(),
    )
