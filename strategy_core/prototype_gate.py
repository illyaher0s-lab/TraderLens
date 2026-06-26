from __future__ import annotations

from datetime import date

from contracts.stable import (
    PrototypeGateConfig,
    PrototypeGateResult,
    BacktestMetrics,
    DailyPortfolioValue,
    Trade,
)
from strategy_core.metrics import calculate_metrics


def evaluate_prototype_gate(
    trades: list[Trade],
    daily_values: list[DailyPortfolioValue],
    initial_capital: float,
    gate_config: PrototypeGateConfig,
    sample_split_date: date | None = None,
) -> PrototypeGateResult:
    """
    Evaluate prototype gate based on backtest metrics.
    
    Returns:
        PrototypeGateResult with status, failed/warning checks, and recommendation.
        
    Important: This is a recommendation only. Does NOT modify strategy.status.
    Status transitions must go through human_required_sync.
    
    Status values:
    - not_evaluated: gate disabled
    - passed: all checks passed
    - needs_review: warnings present or insufficient OOS sample
    - failed: critical checks failed
    
    Recommendation values:
    - reject: failed critical checks
    - review: passed but with warnings
    - candidate_for_prototype_passed: all checks passed
    """
    # Calculate full-period metrics
    metrics_full = calculate_metrics(trades, daily_values, initial_capital)
    
    # If gate disabled, return not_evaluated
    if not gate_config.enabled:
        return PrototypeGateResult(
            status="not_evaluated",
            failed_checks=[],
            warning_checks=[],
            recommendation="review",
            metrics_full=metrics_full,
        )
    
    # Split IS/OOS if sample_split_date provided
    metrics_is = None
    metrics_oos = None
    oos_split_date = None
    oos_start_value = None
    oos_end_value = None
    
    if sample_split_date:
        is_daily = [v for v in daily_values if v.date <= sample_split_date]
        oos_daily = [v for v in daily_values if v.date > sample_split_date]
        is_trades = [t for t in trades if t.trade_date <= sample_split_date]
        oos_trades = [t for t in trades if t.trade_date > sample_split_date]
        
        if is_daily:
            metrics_is = calculate_metrics(is_trades, is_daily, initial_capital)
        
        if oos_daily:
            # OOS starts with capital from end of IS period
            oos_start_capital = is_daily[-1].total_value if is_daily else initial_capital
            metrics_oos = calculate_metrics(oos_trades, oos_daily, oos_start_capital)
            oos_split_date = sample_split_date
            oos_start_value = oos_start_capital
            oos_end_value = oos_daily[-1].total_value
    
    # Evaluate checks
    failed_checks = []
    warning_checks = []
    
    # Full-period checks
    if gate_config.min_total_return is not None:
        if metrics_full.total_return < gate_config.min_total_return:
            failed_checks.append(
                f"total_return {metrics_full.total_return:.2%} < min {gate_config.min_total_return:.2%}"
            )
    
    if gate_config.max_drawdown is not None:
        if metrics_full.max_drawdown < gate_config.max_drawdown:
            failed_checks.append(
                f"max_drawdown {metrics_full.max_drawdown:.2%} worse than threshold {gate_config.max_drawdown:.2%}"
            )
    
    if gate_config.min_sharpe_ratio is not None:
        if metrics_full.sharpe_ratio < gate_config.min_sharpe_ratio:
            failed_checks.append(
                f"sharpe_ratio {metrics_full.sharpe_ratio:.2f} < min {gate_config.min_sharpe_ratio:.2f}"
            )
    
    if gate_config.min_trades is not None:
        if metrics_full.filled_orders < gate_config.min_trades:
            failed_checks.append(
                f"filled_orders {metrics_full.filled_orders} < min {gate_config.min_trades}"
            )
    
    # Round-trip checks
    if gate_config.min_completed_round_trips is not None:
        if metrics_full.completed_round_trips < gate_config.min_completed_round_trips:
            failed_checks.append(
                f"completed_round_trips {metrics_full.completed_round_trips} < min {gate_config.min_completed_round_trips}"
            )
    
    if gate_config.min_closed_lot_win_rate is not None:
        if metrics_full.closed_lot_win_rate < gate_config.min_closed_lot_win_rate:
            failed_checks.append(
                f"closed_lot_win_rate {metrics_full.closed_lot_win_rate:.2%} < min {gate_config.min_closed_lot_win_rate:.2%}"
            )
    
    if gate_config.min_profit_factor is not None:
        if metrics_full.profit_factor < gate_config.min_profit_factor:
            failed_checks.append(
                f"profit_factor {metrics_full.profit_factor:.2f} < min {gate_config.min_profit_factor:.2f}"
            )
    
    # Warn on unmatched sells
    if metrics_full.unmatched_sells > 0:
        warning_checks.append(
            f"unmatched_sells: {metrics_full.unmatched_sells} sell trades without matching buy lots"
        )
    
    # OOS-specific checks
    if metrics_oos:
        if gate_config.min_oos_return is not None:
            if metrics_oos.total_return < gate_config.min_oos_return:
                failed_checks.append(
                    f"oos_return {metrics_oos.total_return:.2%} < min {gate_config.min_oos_return:.2%}"
                )
        
        if gate_config.max_oos_drawdown is not None:
            if metrics_oos.max_drawdown < gate_config.max_oos_drawdown:
                failed_checks.append(
                    f"oos_drawdown {metrics_oos.max_drawdown:.2%} worse than threshold {gate_config.max_oos_drawdown:.2%}"
                )
        
        if gate_config.min_oos_trades is not None:
            if metrics_oos.filled_orders < gate_config.min_oos_trades:
                warning_checks.append(
                    f"oos_trades {metrics_oos.filled_orders} < min {gate_config.min_oos_trades} (insufficient_sample)"
                )
    elif sample_split_date:
        # OOS period exists but no trades
        warning_checks.append("OOS period has no data (insufficient_sample)")
    
    # Determine status and recommendation
    if failed_checks:
        status = "failed"
        recommendation = "reject"
    elif warning_checks:
        status = "needs_review"
        recommendation = "review"
    else:
        status = "passed"
        recommendation = "candidate_for_prototype_passed"
    
    return PrototypeGateResult(
        status=status,
        failed_checks=failed_checks,
        warning_checks=warning_checks,
        recommendation=recommendation,
        metrics_full=metrics_full,
        metrics_is=metrics_is,
        metrics_oos=metrics_oos,
        oos_split_date=oos_split_date,
        oos_start_value=oos_start_value,
        oos_end_value=oos_end_value,
    )
