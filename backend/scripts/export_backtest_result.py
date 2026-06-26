"""
Export Backtest Result to CSV/JSON/PNG files

Usage:
    python backend/scripts/export_backtest_result.py <result_json_path> <output_dir>
    
Example:
    python backend/scripts/export_backtest_result.py backtest_result.json ./output
"""
import json
import csv
import sys
from pathlib import Path
from datetime import date

# Use Agg backend for headless operation
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates


def export_backtest_result(result_json_path: str, output_dir: str):
    """
    Export BacktestResult to multiple files for analysis.
    
    Outputs:
    - metrics.json: key performance metrics
    - trades.csv: all trades with cost breakdown
    - round_trips.csv: matched buy-sell pairs with PnL
    - equity_curve.csv: daily portfolio values
    - order_generation_events.csv: T+1 audit events (if any)
    """
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    result_path = Path(result_json_path)
    output_path = Path(output_dir)
    
    if not result_path.exists():
        print(f"Error: {result_json_path} not found")
        sys.exit(1)
    
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Load result
    with open(result_path, "r", encoding="utf-8") as f:
        result = json.load(f)
    
    print(f"Loading backtest result: {result['strategy_id']} v{result['strategy_version']}")
    print(f"  Initial capital: {result['initial_capital']:,.2f}")
    print(f"  Final capital: {result['final_capital']:,.2f}")
    print(f"  Total return: {result['total_return']*100:.2f}%")
    print(f"  Trades: {len(result['trades'])}")
    print(f"  Round trips: {len(result['round_trips'])}")
    
    # Export metrics.json
    export_metrics(result, output_path / "metrics.json")
    print(f"✓ Exported metrics.json")
    
    # Export trades.csv
    export_trades(result, output_path / "trades.csv")
    print(f"✓ Exported trades.csv ({len(result['trades'])} trades)")
    
    # Export round_trips.csv
    export_round_trips(result, output_path / "round_trips.csv")
    print(f"✓ Exported round_trips.csv ({len(result['round_trips'])} round trips)")
    
    # Export equity_curve.csv
    export_equity_curve(result, output_path / "equity_curve.csv")
    print(f"✓ Exported equity_curve.csv ({len(result['daily_portfolio_values'])} days)")
    
    # Export order_generation_events.csv (if any)
    if result.get("order_generation_events"):
        export_order_generation_events(result, output_path / "order_generation_events.csv")
        print(f"✓ Exported order_generation_events.csv ({len(result['order_generation_events'])} events)")
    
    # Export equity_curve.png
    try:
        export_equity_curve_png(result, output_path / "equity_curve.png")
        print(f"✓ Exported equity_curve.png")
    except Exception as e:
        print(f"⚠ Failed to export equity_curve.png: {e}")
    
    # Export drawdown_curve.png
    try:
        export_drawdown_curve_png(result, output_path / "drawdown_curve.png")
        print(f"✓ Exported drawdown_curve.png")
    except Exception as e:
        print(f"⚠ Failed to export drawdown_curve.png: {e}")
    
    print(f"\n✓ All artifacts exported to {output_path.absolute()}")


def export_metrics(result: dict, output_path: Path):
    """Export key metrics to JSON with schema version."""
    from contracts import SCHEMA_VERSION
    
    trades = result["trades"]
    round_trips = result["round_trips"]
    
    # Calculate win rate
    winning_trips = [rt for rt in round_trips if rt["realized_pnl"] > 0]
    losing_trips = [rt for rt in round_trips if rt["realized_pnl"] < 0]
    win_rate = len(winning_trips) / len(round_trips) if round_trips else 0
    
    # Calculate profit factor
    total_profit = sum(rt["realized_pnl"] for rt in winning_trips)
    total_loss = abs(sum(rt["realized_pnl"] for rt in losing_trips))
    profit_factor = total_profit / total_loss if total_loss > 0 else float('inf')
    
    # Calculate average holding days
    avg_holding_days = sum(rt["holding_days"] for rt in round_trips) / len(round_trips) if round_trips else 0
    
    # Calculate max drawdown (simplified: from peak to trough in equity curve)
    daily_values = result["daily_portfolio_values"]
    peak = result["initial_capital"]
    max_drawdown = 0.0
    
    for dv in daily_values:
        total = dv["total_value"]
        if total > peak:
            peak = total
        drawdown = (total - peak) / peak
        if drawdown < max_drawdown:
            max_drawdown = drawdown
    
    metrics = {
        # Schema metadata (M2)
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "metrics",
        
        # Strategy identification
        "strategy_id": result["strategy_id"],
        "strategy_version": result["strategy_version"],
        
        # Capital and returns
        "initial_capital": result["initial_capital"],
        "final_capital": result["final_capital"],
        "total_return": result["total_return"],
        "total_return_pct": result["total_return"] * 100,
        "max_drawdown": max_drawdown,
        "max_drawdown_pct": max_drawdown * 100,
        
        # Trade counts
        "total_trades": len(trades),
        "buy_trades": len([t for t in trades if t["direction"] == "buy"]),
        "sell_trades": len([t for t in trades if t["direction"] == "sell"]),
        
        # Round trip metrics
        "total_round_trips": len(round_trips),
        "winning_trips": len(winning_trips),
        "losing_trips": len(losing_trips),
        "win_rate": win_rate,
        "profit_factor": profit_factor if profit_factor != float('inf') else None,
        "avg_holding_days": avg_holding_days,
        
        # Transaction costs
        "total_commission": sum(t["commission"] for t in trades),
        "total_stamp_duty": sum(t["stamp_duty"] for t in trades),
        "total_fees": sum(t["total_fee"] for t in trades),
        
        # T+1 diagnostics
        "t1_blocked_exit_count": result.get("t1_blocked_exit_count", 0),
        "partial_exit_due_to_t1_count": result.get("partial_exit_due_to_t1_count", 0),
        
        # Rejected orders
        "rejected_orders": len(result.get("rejected_orders", [])),
    }
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2, ensure_ascii=False)


def export_trades(result: dict, output_path: Path):
    """Export trades to CSV."""
    trades = result["trades"]
    
    if not trades:
        # Create empty CSV with headers
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "trade_id", "order_id", "symbol", "direction", "quantity", "price",
                "trade_date", "gross_amount", "commission", "stamp_duty", "transfer_fee",
                "total_fee", "net_cash_flow"
            ])
        return
    
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "trade_id", "order_id", "symbol", "direction", "quantity", "price",
            "trade_date", "gross_amount", "commission", "stamp_duty", "transfer_fee",
            "total_fee", "net_cash_flow"
        ])
        writer.writeheader()
        
        for trade in trades:
            writer.writerow({
                "trade_id": trade["trade_id"],
                "order_id": trade["order_id"],
                "symbol": trade["symbol"],
                "direction": trade["direction"],
                "quantity": trade["quantity"],
                "price": f"{trade['price']:.2f}",
                "trade_date": trade["trade_date"],
                "gross_amount": f"{trade['gross_amount']:.2f}",
                "commission": f"{trade['commission']:.2f}",
                "stamp_duty": f"{trade['stamp_duty']:.2f}",
                "transfer_fee": f"{trade['transfer_fee']:.2f}",
                "total_fee": f"{trade['total_fee']:.2f}",
                "net_cash_flow": f"{trade['net_cash_flow']:.2f}",
            })


def export_round_trips(result: dict, output_path: Path):
    """Export round trips to CSV."""
    round_trips = result["round_trips"]
    
    if not round_trips:
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "symbol", "buy_date", "sell_date", "holding_days", "quantity",
                "buy_price", "sell_price", "buy_cost", "sell_proceeds",
                "realized_pnl", "return_pct"
            ])
        return
    
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "symbol", "buy_date", "sell_date", "holding_days", "quantity",
            "buy_price", "sell_price", "buy_cost", "sell_proceeds",
            "realized_pnl", "return_pct"
        ])
        writer.writeheader()
        
        for rt in round_trips:
            return_pct = (rt["realized_pnl"] / rt["buy_cost"] * 100) if rt["buy_cost"] > 0 else 0
            writer.writerow({
                "symbol": rt["symbol"],
                "buy_date": rt["buy_date"],
                "sell_date": rt["sell_date"],
                "holding_days": rt["holding_days"],
                "quantity": rt["matched_quantity"],
                "buy_price": f"{rt['buy_price']:.2f}",
                "sell_price": f"{rt['sell_price']:.2f}",
                "buy_cost": f"{rt['buy_cost']:.2f}",
                "sell_proceeds": f"{rt['sell_proceeds']:.2f}",
                "realized_pnl": f"{rt['realized_pnl']:.2f}",
                "return_pct": f"{return_pct:.2f}",
            })


def export_equity_curve(result: dict, output_path: Path):
    """Export equity curve to CSV."""
    daily_values = result["daily_portfolio_values"]
    
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "date", "cash", "market_value", "total_value", "return_from_start_pct"
        ])
        writer.writeheader()
        
        initial_capital = result["initial_capital"]
        
        for dv in daily_values:
            return_pct = ((dv["total_value"] - initial_capital) / initial_capital * 100)
            writer.writerow({
                "date": dv["date"],
                "cash": f"{dv['cash']:.2f}",
                "market_value": f"{dv['market_value']:.2f}",
                "total_value": f"{dv['total_value']:.2f}",
                "return_from_start_pct": f"{return_pct:.2f}",
            })


def export_order_generation_events(result: dict, output_path: Path):
    """Export order generation events (T+1 audit) to CSV."""
    events = result["order_generation_events"]
    
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "event_type", "symbol", "signal_id", "intended_execution_date",
            "reason", "requested_quantity", "generated_quantity",
            "sellable_quantity", "total_quantity"
        ])
        writer.writeheader()
        
        for event in events:
            writer.writerow({
                "event_type": event["event_type"],
                "symbol": event["symbol"],
                "signal_id": event.get("signal_id", ""),
                "intended_execution_date": event["intended_execution_date"],
                "reason": event["reason"],
                "requested_quantity": event.get("requested_quantity", ""),
                "generated_quantity": event.get("generated_quantity", ""),
                "sellable_quantity": event.get("sellable_quantity", ""),
                "total_quantity": event.get("total_quantity", ""),
            })


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python export_backtest_result.py <result_json_path> <output_dir>")
        print("\nExample:")
        print("  python backend/scripts/export_backtest_result.py backtest_result.json ./output")
        sys.exit(1)
    
    result_json_path = sys.argv[1]
    output_dir = sys.argv[2]
    
    export_backtest_result(result_json_path, output_dir)


def export_equity_curve_png(result: dict, output_path: Path):
    """Export equity curve as PNG chart."""
    daily_values = result["daily_portfolio_values"]
    
    if not daily_values:
        raise ValueError("No daily portfolio values to plot")
    
    # Extract dates and total values
    from datetime import datetime
    dates = [datetime.strptime(dv["date"], "%Y-%m-%d").date() for dv in daily_values]
    total_values = [dv["total_value"] for dv in daily_values]
    
    if not dates or not total_values:
        raise ValueError("Empty dates or values")
    
    # Create figure
    fig, ax = plt.subplots(figsize=(12, 6))
    
    # Plot equity curve
    ax.plot(dates, total_values, linewidth=1.5, color="#2E86AB", label="Strategy")
    
    # Format
    ax.set_title(
        f"{result['strategy_id']} - Equity Curve\n"
        f"{dates[0]} to {dates[-1]}",
        fontsize=14,
        fontweight="bold"
    )
    ax.set_xlabel("Date", fontsize=12)
    ax.set_ylabel("Total Value (RMB)", fontsize=12)
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper left")
    
    # Format x-axis dates
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    plt.xticks(rotation=45)
    
    # Add initial capital reference line
    initial_capital = result["initial_capital"]
    ax.axhline(y=initial_capital, color="gray", linestyle="--", alpha=0.5, label="Initial Capital")
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()


def export_drawdown_curve_png(result: dict, output_path: Path):
    """Export drawdown curve as PNG chart."""
    daily_values = result["daily_portfolio_values"]
    
    if not daily_values:
        raise ValueError("No daily portfolio values to plot")
    
    # Extract dates and total values
    from datetime import datetime
    dates = [datetime.strptime(dv["date"], "%Y-%m-%d").date() for dv in daily_values]
    total_values = [dv["total_value"] for dv in daily_values]
    
    if not dates or not total_values:
        raise ValueError("Empty dates or values")
    
    # Calculate drawdown
    cumulative_max = []
    current_max = total_values[0]
    for value in total_values:
        if value > current_max:
            current_max = value
        cumulative_max.append(current_max)
    
    drawdown_pct = [(value / cum_max - 1) * 100 for value, cum_max in zip(total_values, cumulative_max)]
    max_drawdown = min(drawdown_pct)
    
    # Create figure
    fig, ax = plt.subplots(figsize=(12, 6))
    
    # Plot drawdown curve
    ax.fill_between(dates, drawdown_pct, 0, color="#A23B72", alpha=0.3)
    ax.plot(dates, drawdown_pct, linewidth=1.5, color="#A23B72")
    
    # Format
    ax.set_title(
        f"{result['strategy_id']} - Drawdown Curve\n"
        f"Max Drawdown: {max_drawdown:.2f}%",
        fontsize=14,
        fontweight="bold"
    )
    ax.set_xlabel("Date", fontsize=12)
    ax.set_ylabel("Drawdown (%)", fontsize=12)
    ax.grid(True, alpha=0.3)
    
    # Format x-axis dates
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    plt.xticks(rotation=45)
    
    # Ensure y-axis shows negative values clearly
    ax.axhline(y=0, color="gray", linestyle="-", alpha=0.5)
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()
