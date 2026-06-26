"""
Generate 20-stock fixed fixture from Tushare.

Usage:
    python backend/scripts/generate_fixed_fixture.py

Requirements:
    - tushare package installed
    - TUSHARE_TOKEN environment variable set
"""
import json
import os
from datetime import datetime, date
from pathlib import Path

import pandas as pd
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq


def main():
    fixture_root = Path(__file__).parent.parent.parent / "tests" / "fixed_fixture"
    metadata_path = fixture_root / "metadata"
    data_path = fixture_root / "data"
    benchmarks_path = fixture_root / "benchmarks"
    
    # Ensure directories exist
    metadata_path.mkdir(parents=True, exist_ok=True)
    data_path.mkdir(parents=True, exist_ok=True)
    benchmarks_path.mkdir(parents=True, exist_ok=True)
    
    # Load stock list
    stock_list_file = metadata_path / "stock_list.json"
    if not stock_list_file.exists():
        print(f"Error: {stock_list_file} not found. Create it first.")
        return
    
    with open(stock_list_file, "r", encoding="utf-8") as f:
        stock_list = json.load(f)
    
    symbols = [item["symbol"] for item in stock_list]
    print(f"Loaded {len(symbols)} symbols from stock_list.json")
    
    # Check Tushare availability
    token = os.getenv("TUSHARE_TOKEN")
    if not token:
        print("Error: TUSHARE_TOKEN environment variable not set.")
        print("This script requires Tushare API access to fetch data.")
        print("\nAlternative: Use sample/mock data for testing purposes.")
        print("Creating mock data files...")
        
        # Use v2.1 mock data generator
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from mock_data_generator_v2 import create_mock_data_v2
        
        trading_dates = pd.date_range("2023-01-03", "2024-12-31", freq="B").tolist()[:487]
        create_mock_data_v2(symbols, trading_dates, data_path, metadata_path, benchmarks_path)
        return
    
    try:
        import tushare as ts
    except ImportError:
        print("Error: tushare package not installed.")
        print("Install with: pip install tushare")
        print("\nCreating mock data files for testing...")
        create_mock_data(symbols, data_path, metadata_path)
        return
    
    # Initialize Tushare
    ts.set_token(token)
    pro = ts.pro_api()
    
    # Fetch data
    start_date = "20230101"
    end_date = "20241231"
    
    print(f"\nFetching data from Tushare ({start_date} to {end_date})...")
    
    trading_dates = set()
    
    for i, symbol in enumerate(symbols, 1):
        print(f"[{i}/{len(symbols)}] Fetching {symbol}...")
        
        # Convert symbol format: 000001.SZ -> 000001.SZ (Tushare format)
        ts_code = symbol
        
        try:
            # Fetch daily data (forward-adjusted)
            df_daily = pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
            if df_daily.empty:
                print(f"  Warning: No daily data for {symbol}")
                continue
            
            # Fetch adjustment factor
            df_adj = pro.adj_factor(ts_code=ts_code, start_date=start_date, end_date=end_date)
            df_daily = df_daily.merge(df_adj[["trade_date", "adj_factor"]], on="trade_date", how="left")
            df_daily["adj_factor"].fillna(1.0, inplace=True)
            
            # Fetch daily indicators (for ST, limit up/down)
            df_daily_basic = pro.daily_basic(ts_code=ts_code, start_date=start_date, end_date=end_date, fields="ts_code,trade_date,turnover_rate,volume_ratio,pe,pb")
            
            # Fetch suspend info
            df_suspend = pro.suspend_d(ts_code=ts_code, start_date=start_date, end_date=end_date)
            suspend_dates = set(df_suspend["suspend_date"].tolist()) if not df_suspend.empty else set()
            
            # Prepare daily bars
            df_daily = df_daily.sort_values("trade_date")
            df_daily["date"] = pd.to_datetime(df_daily["trade_date"], format="%Y%m%d")
            df_daily["symbol"] = symbol
            df_daily.rename(columns={"vol": "volume"}, inplace=True)
            
            daily_bars = df_daily[["date", "symbol", "open", "high", "low", "close", "volume", "amount", "adj_factor"]]
            
            # Save daily bars
            table = pa.Table.from_pandas(daily_bars, preserve_index=False)
            pq.write_table(table, data_path / f"{symbol}_daily.parquet")
            
            # Prepare daily status
            df_status = df_daily[["date", "symbol"]].copy()
            df_status["is_st"] = df_status["symbol"].str.contains("ST")  # Simplified ST detection
            df_status["is_suspended"] = df_status["date"].apply(lambda d: d.strftime("%Y%m%d") in suspend_dates)
            
            # Detect limit up/down (simplified: 10% for main board, 20% for ChiNext/STAR)
            pct_change_limit = 0.20 if symbol.startswith("300") or symbol.startswith("688") else 0.10
            df_status["is_limit_up"] = df_daily["pct_chg"] >= (pct_change_limit * 100 - 0.01)
            df_status["is_limit_down"] = df_daily["pct_chg"] <= (-pct_change_limit * 100 + 0.01)
            
            # Save daily status
            status_table = pa.Table.from_pandas(df_status, preserve_index=False)
            pq.write_table(status_table, data_path / f"{symbol}_status.parquet")
            
            # Collect trading dates
            trading_dates.update(df_daily["trade_date"].tolist())
            
            print(f"  ✓ Saved {len(df_daily)} days of data")
            
        except Exception as e:
            print(f"  ✗ Error fetching {symbol}: {e}")
            continue
    
    # Save trade calendar
    trade_calendar = {
        "exchange": "SSE",
        "date_range": {
            "start": "2023-01-01",
            "end": "2024-12-31"
        },
        "trading_dates": sorted([
            datetime.strptime(d, "%Y%m%d").strftime("%Y-%m-%d") for d in trading_dates
        ])
    }
    
    with open(metadata_path / "trade_calendar.json", "w", encoding="utf-8") as f:
        json.dump(trade_calendar, f, indent=2, ensure_ascii=False)
    
    # Update manifest
    manifest_file = metadata_path / "manifest.json"
    with open(manifest_file, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    
    manifest["fetched_at"] = datetime.now().isoformat() + "Z"
    manifest["trading_days_count"] = len(trade_calendar["trading_dates"])
    
    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    
    print(f"\n✓ Fixed fixture generated successfully")
    print(f"  - {len(symbols)} stocks")
    print(f"  - {manifest['trading_days_count']} trading days")
    print(f"  - Date range: {manifest['date_range']['start']} to {manifest['date_range']['end']}")


def create_mock_data(symbols: list[str], data_path: Path, metadata_path: Path, benchmarks_path: Path):
    """Create mock data for testing when Tushare is not available."""
    print("\n⚠️  Creating MOCK data (not real market data)")
    print("   This is for testing the data loader only.")
    print("   Run with TUSHARE_TOKEN to fetch real data.\n")
    
    # Generate mock trading dates (2023-2024, ~487 days)
    trading_dates = pd.date_range("2023-01-03", "2024-12-31", freq="B").tolist()[:487]
    
    for symbol in symbols:
        print(f"  Creating mock data for {symbol}...")
        
        # Mock daily bars
        dates = trading_dates
        n = len(dates)
        
        df_daily = pd.DataFrame({
            "date": dates,
            "symbol": [symbol] * n,
            "open": [10.0 + i * 0.01 for i in range(n)],
            "high": [10.5 + i * 0.01 for i in range(n)],
            "low": [9.5 + i * 0.01 for i in range(n)],
            "close": [10.0 + i * 0.01 for i in range(n)],
            "volume": [1000000 + i * 1000 for i in range(n)],
            "amount": [10000000.0 + i * 10000 for i in range(n)],
            "adj_factor": [1.0] * n,
        })
        
        table = pa.Table.from_pandas(df_daily, preserve_index=False)
        pq.write_table(table, data_path / f"{symbol}_daily.parquet")
        
        # Mock daily status
        df_status = pd.DataFrame({
            "date": dates,
            "symbol": [symbol] * n,
            "is_st": [False] * n,
            "is_suspended": [False] * n,
            "is_limit_up": [False] * n,
            "is_limit_down": [False] * n,
        })
        
        status_table = pa.Table.from_pandas(df_status, preserve_index=False)
        pq.write_table(status_table, data_path / f"{symbol}_status.parquet")
    
    # Create mock benchmark data
    print("\n  Creating mock benchmark data...")
    
    # Load benchmark list
    benchmark_list_file = benchmarks_path / "benchmark_list.json"
    if benchmark_list_file.exists():
        with open(benchmark_list_file, "r", encoding="utf-8") as f:
            benchmarks = json.load(f)
        
        for benchmark in benchmarks:
            code = benchmark["code"]
            print(f"    Creating mock data for {code} ({benchmark['name']})...")
            
            # Mock index values (slowly rising)
            base_value = benchmark.get("base_value", 1000.0)
            df_benchmark = pd.DataFrame({
                "date": trading_dates,
                "code": [code] * len(trading_dates),
                "open": [base_value * (1 + i * 0.0002) for i in range(len(trading_dates))],
                "high": [base_value * (1 + i * 0.0002 + 0.005) for i in range(len(trading_dates))],
                "low": [base_value * (1 + i * 0.0002 - 0.005) for i in range(len(trading_dates))],
                "close": [base_value * (1 + i * 0.0002) for i in range(len(trading_dates))],
                "volume": [1000000000 + i * 1000000 for i in range(len(trading_dates))],
                "amount": [100000000000.0 + i * 10000000 for i in range(len(trading_dates))],
            })
            
            table = pa.Table.from_pandas(df_benchmark, preserve_index=False)
            pq.write_table(table, benchmarks_path / f"{code}_daily.parquet")
    
    # Save trade calendar
    trade_calendar = {
        "exchange": "SSE",
        "date_range": {
            "start": "2023-01-01",
            "end": "2024-12-31"
        },
        "trading_dates": [d.strftime("%Y-%m-%d") for d in trading_dates]
    }
    
    with open(metadata_path / "trade_calendar.json", "w", encoding="utf-8") as f:
        json.dump(trade_calendar, f, indent=2, ensure_ascii=False)
    
    # Update manifest
    manifest_file = metadata_path / "manifest.json"
    with open(manifest_file, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    
    manifest["fetched_at"] = datetime.now().isoformat() + "Z"
    manifest["trading_days_count"] = len(trading_dates)
    manifest["source"] = "mock"
    manifest["warnings"].append("⚠️  MOCK DATA - Not real market data. For testing only.")
    
    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    
    print(f"\n✓ Mock fixture created")
    print(f"  - {len(symbols)} stocks")
    print(f"  - {len(trading_dates)} trading days (mock)")
    if benchmark_list_file.exists():
        print(f"  - {len(benchmarks)} benchmarks")


if __name__ == "__main__":
    main()
