from __future__ import annotations

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


def run_backtest(
    strategy_config: StrategyConfig,
    data_source: GoldenCaseDataSource,
    calendar: TradingCalendar,
    initial_capital: float = 100000.0,
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
    - min_commission: 5.0 RMB
    - stamp_duty_rate: 0.001 (千一)
    - transfer_fee_rate: 0.0 (not implemented)
    
    Returns:
        BacktestResult with trades (including cost breakdown), daily values, rejected orders, and warnings
    """
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
    
    universe = build_universe(strategy_config, data_source)
    sizer = PositionSizer(position_ratio=0.2)
    
    # Read fee rates from fill_model or use defaults
    fill_model = strategy_config.fill_model
    commission_rate = fill_model.commission if fill_model.commission > 0 else 0.0003
    stamp_duty_rate = fill_model.stamp_tax if fill_model.stamp_tax > 0 else 0.001
    min_commission = 5.0  # Default minimum commission
    transfer_fee_rate = 0.0  # Not implemented in MVP
    
    trading_dates = [
        trading_date
        for trading_date in calendar.all_trading_dates()
        if strategy_config.backtest_config.start_date
        <= trading_date
        <= strategy_config.backtest_config.end_date
    ]
    if not trading_dates:
        raise ValueError("no trading dates within configured backtest range")
    
    # Record initial portfolio value
    daily_values.append(DailyPortfolioValue(
        date=trading_dates[0],
        cash=portfolio.cash,
        market_value=0.0,
        total_value=portfolio.cash,
    ))
    
    for i, trade_date in enumerate(trading_dates):
        # Unlock frozen lots at start of trading day
        portfolio.unlock_frozen_lots(trade_date)
        
        # Generate entry signals for this trading day
        entry_signals = generate_signals(strategy_config, data_source, trade_date, universe)
        entry_signal_count += len(entry_signals)
        
        # Generate exit signals for current positions
        from strategy_core.signals import generate_exit_signals
        exit_signals = generate_exit_signals(strategy_config, data_source, trade_date, portfolio.positions)
        exit_signal_count += len(exit_signals)
        for signal in exit_signals:
            exit_triggered_rules.update(signal.triggered_rules)
        
        # Combine entry and exit signals
        signals = entry_signals + exit_signals
        
        if signals:
            try:
                next_date = calendar.next_trading_day(trade_date)
            except ValueError:
                # Last trading day, cannot execute orders
                break
            if next_date > strategy_config.backtest_config.end_date:
                break
            
            # Generate order intents (planned quantity based on signal_date close)
            order_result = generate_orders(
                signals,
                intended_execution_date=next_date,
                price_provider=data_source,
                sizer=sizer,
                available_capital=portfolio.available_capital(),
                current_positions=portfolio.positions,
            )
            
            # Collect generation events
            all_generation_events.extend(order_result.events)
            
            # Count T+1 events
            for event in order_result.events:
                if event.event_type == "t1_frozen":
                    t1_blocked_exit_count += 1
                elif event.event_type == "partial_exit_due_to_t1_freeze":
                    partial_exit_due_to_t1_count += 1
            
            # Simulate fill on next_date (verify capital with execution open price + costs)
            for order in order_result.valid_orders:
                if order.direction == "buy":
                    buy_order_count += 1
                elif order.direction == "sell":
                    sell_order_count += 1

                filled_order = simulate_fill(
                    order, next_date, data_source, portfolio,
                    commission_rate=commission_rate,
                    min_commission=min_commission,
                    stamp_duty_rate=stamp_duty_rate,
                    transfer_fee_rate=transfer_fee_rate,
                    calendar=calendar,
                )
                
                if filled_order.status == "filled":
                    filled_orders.append(filled_order)
                    
                    # Calculate transaction costs for trade record
                    gross, commission, stamp_duty, transfer_fee, total_fee, net_cash_flow = calculate_transaction_costs(
                        filled_order.direction,
                        filled_order.actual_quantity,
                        filled_order.actual_price,
                        commission_rate,
                        min_commission,
                        stamp_duty_rate,
                        transfer_fee_rate,
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
                        cost=net_cash_flow,  # Backward compatibility
                    ))
                else:
                    rejected_orders.append(filled_order)
        
        # Update position prices with current day close
        if portfolio.positions:
            prices = {symbol: data_source.get_price(symbol, trade_date) for symbol in portfolio.positions}
            portfolio.update_position_prices(prices)
        
        # Record daily portfolio value
        daily_values.append(DailyPortfolioValue(
            date=trade_date,
            cash=portfolio.cash,
            market_value=portfolio.market_value(),
            total_value=portfolio.total_value(),
        ))
    
    final_capital = portfolio.total_value()
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
    
    return BacktestResult(
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
