from __future__ import annotations

from contracts.stable import BacktestMetrics, DailyPortfolioValue, Trade
from strategy_core.lot_matching import LotMatcher


def calculate_metrics(
    trades: list[Trade],
    daily_values: list[DailyPortfolioValue],
    initial_capital: float,
    risk_free_rate: float = 0.03,
) -> BacktestMetrics:
    """
    Calculate performance metrics from backtest result.
    
    Metrics:
    - Total return, max drawdown, Sharpe ratio
    - Trade counts
    - Round-trip based: closed_lot_win_rate, profit_factor (requires FIFO lot matching)
    
    Trades must be sorted by (trade_date, trade_id) before calling this function
    to ensure deterministic FIFO matching.
    """
    if not daily_values:
        return BacktestMetrics(
            total_return=0.0,
            max_drawdown=0.0,
            sharpe_ratio=0.0,
            total_trades=len(trades),
            filled_orders=len(trades),
            completed_round_trips=0,
        )
    
    final_value = daily_values[-1].total_value
    total_return = (final_value - initial_capital) / initial_capital
    
    # Maximum drawdown
    max_drawdown = _calculate_max_drawdown(daily_values)
    
    # Sharpe ratio
    sharpe_ratio = _calculate_sharpe_ratio(daily_values, risk_free_rate)
    
    # Trade counts
    total_trades = len(trades)
    filled_orders = len(trades)  # All trades in this list are filled
    
    # Round-trip metrics (FIFO lot matching)
    # Sort trades to ensure deterministic matching
    sorted_trades = sorted(trades, key=lambda t: (t.trade_date, t.trade_id))
    
    matcher = LotMatcher()
    for trade in sorted_trades:
        matcher.process_trade(trade)
    
    round_trips = matcher.completed_round_trips
    completed_round_trips = len(round_trips)
    unmatched_sells = matcher.unmatched_sells_count
    
    if completed_round_trips > 0:
        winning_trips = [rt for rt in round_trips if rt.realized_pnl > 0]
        losing_trips = [rt for rt in round_trips if rt.realized_pnl <= 0]
        
        closed_lot_win_rate = len(winning_trips) / completed_round_trips
        
        total_profit = sum(rt.realized_pnl for rt in winning_trips)
        total_loss = abs(sum(rt.realized_pnl for rt in losing_trips))
        
        profit_factor = total_profit / total_loss if total_loss > 0 else float('inf')
        
        avg_win = total_profit / len(winning_trips) if winning_trips else 0.0
        avg_loss = total_loss / len(losing_trips) if losing_trips else 0.0
    else:
        closed_lot_win_rate = 0.0
        profit_factor = 0.0
        avg_win = 0.0
        avg_loss = 0.0
    
    return BacktestMetrics(
        total_return=total_return,
        max_drawdown=max_drawdown,
        sharpe_ratio=sharpe_ratio,
        total_trades=total_trades,
        filled_orders=filled_orders,
        completed_round_trips=completed_round_trips,
        closed_lot_win_rate=closed_lot_win_rate,
        profit_factor=profit_factor,
        avg_win=avg_win,
        avg_loss=avg_loss,
        unmatched_sells=unmatched_sells,
    )


def _calculate_max_drawdown(daily_values: list[DailyPortfolioValue]) -> float:
    """
    Calculate maximum drawdown from daily portfolio values.
    
    Returns negative value (e.g., -0.15 = -15% drawdown).
    """
    peak = daily_values[0].total_value
    max_dd = 0.0
    
    for value in daily_values:
        if value.total_value > peak:
            peak = value.total_value
        dd = (value.total_value - peak) / peak
        if dd < max_dd:
            max_dd = dd
    
    return max_dd


def _calculate_sharpe_ratio(
    daily_values: list[DailyPortfolioValue],
    risk_free_rate: float,
) -> float:
    """
    Calculate annualized Sharpe ratio.
    
    Formula: (mean_daily_return - daily_risk_free_rate) / std_daily_return * sqrt(252)
    """
    if len(daily_values) < 2:
        return 0.0
    
    # Calculate daily returns
    returns = []
    for i in range(1, len(daily_values)):
        prev_value = daily_values[i-1].total_value
        curr_value = daily_values[i].total_value
        if prev_value > 0:
            r = (curr_value - prev_value) / prev_value
            returns.append(r)
    
    if not returns:
        return 0.0
    
    # Mean and std of daily returns
    mean_return = sum(returns) / len(returns)
    variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
    std_return = variance ** 0.5
    
    if std_return == 0:
        return 0.0
    
    # Annualize (assuming ~252 trading days per year)
    daily_rf = risk_free_rate / 252
    sharpe = (mean_return - daily_rf) / std_return * (252 ** 0.5)
    
    return sharpe
