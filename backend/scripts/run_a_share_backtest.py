#!/usr/bin/env python3
"""Run A-Share Backtest with Tushare Data - M3.4"""
import argparse, sys
from pathlib import Path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.app.tushare.config import TushareConfig
from backend.app.tushare.tushare_data_source import TushareDataSource
from strategy_core.backtest_engine import run_backtest
from strategy_core.trading_calendar import TradingCalendar
from strategy_core.dsl_parser import parse_strategy_config
from backend.scripts.export_backtest_result import export_metrics, export_trades, export_round_trips, export_equity_curve

def main():
    parser = argparse.ArgumentParser(description="Run A-share backtest")
    parser.add_argument("--snapshot-dir", required=True)
    parser.add_argument("--strategy", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--initial-capital", type=float, default=100000.0)
    args = parser.parse_args()
    
    snapshot_dir = Path(args.snapshot_dir)
    strategy_path = Path(args.strategy)
    output_dir = Path(args.output)
    
    if not snapshot_dir.exists():
        print(f"Error: Snapshot not found: {snapshot_dir}")
        sys.exit(1)
    if not strategy_path.exists():
        print(f"Error: Strategy not found: {strategy_path}")
        sys.exit(1)
    
    print("Loading TushareDataSource...")
    config = TushareConfig(token="", snapshot_root=snapshot_dir)
    data_source = TushareDataSource(config)
    metadata = data_source.get_metadata()
    print(f"Loaded: {metadata.symbol_count} symbols, {metadata.trading_days} days")
    
    print("Loading strategy...")
    strategy_config = parse_strategy_config(strategy_path)
    calendar = TradingCalendar(data_source)
    
    print("Running backtest...")
    result = run_backtest(strategy_config, data_source, calendar, initial_capital=args.initial_capital)
    print(f"Complete: {len(result.trades)} trades, return {result.total_return:.2%}")
    
    print(f"Exporting to {output_dir}...")
    output_dir.mkdir(parents=True, exist_ok=True)
    result_dict = result.model_dump(mode='json')
    export_metrics(result_dict, output_dir / "metrics.json")
    export_trades(result_dict, output_dir / "trades.csv")
    export_round_trips(result_dict, output_dir / "round_trips.csv")
    export_equity_curve(result_dict, output_dir / "equity_curve.csv")
    print("Done!")

if __name__ == "__main__":
    main()
