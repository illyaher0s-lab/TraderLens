"""
Mock Data Generation v2.1 - Deterministic Volatility Patterns + Controlled Breakouts

Generate realistic mock market data with 4 stock types:
- trend_up: Upward trending stocks
- trend_down: Downward trending stocks  
- mean_reversion: Oscillating around mean
- volatile_breakout: Periodic volatility spikes
"""
import numpy as np
import pandas as pd
from datetime import datetime
import sys


def create_mock_data_v2(symbols, trading_dates, data_path, metadata_path, benchmarks_path):
    """Create mock data v2.1 with deterministic volatility patterns and controlled breakouts."""
    import json
    import pyarrow as pa
    import pyarrow.parquet as pq

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    
    print("\n⚠️  Creating MOCK data (not real market data)")
    print("   Mock version: 2.1 - deterministic volatility patterns + controlled breakouts")
    print("   This is for testing the backtest engine only.")
    print()
    
    # Seed for deterministic generation
    SEED = 42
    np.random.seed(SEED)
    
    # Assign stock types (4 categories)
    stock_types = {
        "trend_up": symbols[:5],
        "trend_down": symbols[5:10],
        "mean_reversion": symbols[10:15],
        "volatile_breakout": symbols[15:20],
    }
    
    print(f"  Stock type distribution:")
    for stype, syms in stock_types.items():
        print(f"    {stype}: {len(syms)} stocks")
    print()
    
    for i, symbol in enumerate(symbols):
        print(f"  Creating mock data for {symbol}...")
        
        # Determine stock type
        if symbol in stock_types["trend_up"]:
            bars, statuses = generate_trend_up_stock(symbol, trading_dates, SEED + i)
        elif symbol in stock_types["trend_down"]:
            bars, statuses = generate_trend_down_stock(symbol, trading_dates, SEED + i)
        elif symbol in stock_types["mean_reversion"]:
            bars, statuses = generate_mean_reversion_stock(symbol, trading_dates, SEED + i)
        else:  # volatile_breakout
            bars, statuses = generate_volatile_breakout_stock(symbol, trading_dates, SEED + i)
        
        bars, statuses = inject_controlled_breakthroughs(bars, statuses)

        # Save daily bars
        table = pa.Table.from_pandas(bars, preserve_index=False)
        pq.write_table(table, data_path / f"{symbol}_daily.parquet")
        
        # Save daily status
        status_table = pa.Table.from_pandas(statuses, preserve_index=False)
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
            
            # Benchmark: slow trend up with moderate volatility
            base_value = benchmark.get("base_value", 1000.0)
            df_benchmark = generate_benchmark_index(code, trading_dates, base_value, SEED)
            
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
    manifest["mock_version"] = "2.1"
    manifest["mock_seed"] = SEED
    manifest["mock_generation_model"] = "deterministic_volatility_patterns_with_controlled_breakouts"
    manifest["result_usage"] = "toolchain_validation_only"
    manifest["warnings"] = [
        "MOCK DATA v2.1 - Deterministic volatility patterns with controlled breakouts for testing.",
        "Not real market data. For backtest engine validation only.",
        "Do not use for strategy performance evaluation."
    ]

    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    
    print(f"\n✓ Mock fixture created (v2.1)")
    print(f"  - {len(symbols)} stocks (4 types)")
    print(f"  - {len(trading_dates)} trading days (mock)")
    if benchmark_list_file.exists():
        print(f"  - {len(benchmarks)} benchmarks")
    print("  - Mock version: 2.1")
    print(f"  - Seed: {SEED} (deterministic)")


def inject_controlled_breakthroughs(bars: pd.DataFrame, statuses: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Inject sparse deterministic breakout days for toolchain validation.

    Signal rules use an inclusive high_Nd window. Selected days therefore close
    exactly at the day high while exceeding prior highs. Volume is lifted on the
    same dates so price+volume breakout strategies have deterministic coverage.
    """
    bars = bars.copy()
    statuses = statuses.copy()
    breakout_indices = [40, 90, 150, 230, 320, 410]

    for index in breakout_indices:
        if index >= len(bars):
            continue

        lookback_start = max(0, index - 30)
        prior_high = bars.loc[lookback_start:index - 1, "high"].max()
        breakout_close = max(float(prior_high) * 1.02, float(bars.at[index, "close"]) * 1.01)
        breakout_open = breakout_close * 0.985
        breakout_low = min(float(bars.at[index, "low"]), breakout_open * 0.99)

        volume_start = max(0, index - 20)
        prior_volume = bars.loc[volume_start:index - 1, "volume"]
        average_volume = float(prior_volume.mean()) if not prior_volume.empty else float(bars.at[index, "volume"])
        breakout_volume = max(int(bars.at[index, "volume"]), int(average_volume * 8))

        bars.at[index, "open"] = breakout_open
        bars.at[index, "high"] = breakout_close
        bars.at[index, "low"] = breakout_low
        bars.at[index, "close"] = breakout_close
        bars.at[index, "volume"] = breakout_volume
        bars.at[index, "amount"] = breakout_volume * breakout_close * 0.8

        statuses.at[index, "is_suspended"] = False
        statuses.at[index, "is_limit_up"] = False
        statuses.at[index, "is_limit_down"] = False

    return bars, statuses


def generate_trend_up_stock(symbol, trading_dates, seed):
    """Generate trend-up stock with moderate upward trend."""
    np.random.seed(seed)
    n = len(trading_dates)
    
    base_price = 10.0
    trend = np.linspace(0, 0.25, n)
    noise = np.random.normal(0, 0.015, n).cumsum()
    
    close_prices = base_price * (1 + trend + noise * 0.3)
    close_prices = np.maximum(close_prices, 1.0)
    
    bars = generate_ohlc_from_close(symbol, trading_dates, close_prices, seed)
    statuses = generate_statuses(symbol, trading_dates, seed, suspended_days=1, limit_up_days=2, limit_down_days=1)
    
    return bars, statuses


def generate_trend_down_stock(symbol, trading_dates, seed):
    """Generate trend-down stock for stop-loss testing."""
    np.random.seed(seed)
    n = len(trading_dates)
    
    base_price = 15.0
    trend = np.linspace(0, -0.20, n)
    noise = np.random.normal(0, 0.012, n).cumsum()
    
    close_prices = base_price * (1 + trend + noise * 0.3)
    close_prices = np.maximum(close_prices, 2.0)
    
    bars = generate_ohlc_from_close(symbol, trading_dates, close_prices, seed)
    statuses = generate_statuses(symbol, trading_dates, seed, suspended_days=0, limit_up_days=1, limit_down_days=3)
    
    return bars, statuses


def generate_mean_reversion_stock(symbol, trading_dates, seed):
    """Generate mean-reverting stock with oscillation around mean."""
    np.random.seed(seed)
    n = len(trading_dates)
    
    base_price = 12.0
    t = np.linspace(0, 4 * np.pi, n)
    oscillation = 0.08 * np.sin(t) + 0.04 * np.sin(2 * t)
    noise = np.random.normal(0, 0.01, n).cumsum()
    
    close_prices = base_price * (1 + oscillation + noise * 0.2)
    close_prices = np.maximum(close_prices, 5.0)
    
    bars = generate_ohlc_from_close(symbol, trading_dates, close_prices, seed)
    statuses = generate_statuses(symbol, trading_dates, seed, suspended_days=2, limit_up_days=2, limit_down_days=2)
    
    return bars, statuses


def generate_volatile_breakout_stock(symbol, trading_dates, seed):
    """Generate volatile stock with periodic breakouts."""
    np.random.seed(seed)
    n = len(trading_dates)
    
    base_price = 8.0
    trend = np.linspace(0, 0.15, n)
    
    breakouts = np.zeros(n)
    spike_intervals = [60, 75, 65, 80, 55, 70, 85]
    current_pos = 0
    for interval in spike_intervals:
        current_pos += interval
        if current_pos >= n:
            break
        spike_len = 7
        spike_height = 0.20
        for j in range(min(spike_len, n - current_pos)):
            breakouts[current_pos + j] = spike_height * (1 - j / spike_len)
    
    noise = np.random.normal(0, 0.02, n).cumsum()
    close_prices = base_price * (1 + trend + breakouts + noise * 0.4)
    close_prices = np.maximum(close_prices, 3.0)
    
    bars = generate_ohlc_from_close(symbol, trading_dates, close_prices, seed)
    statuses = generate_statuses(symbol, trading_dates, seed, suspended_days=1, limit_up_days=3, limit_down_days=1)
    
    return bars, statuses


def generate_ohlc_from_close(symbol, trading_dates, close_prices, seed):
    """Generate OHLC bars from close prices with realistic intraday volatility."""
    np.random.seed(seed + 1000)
    n = len(close_prices)
    
    daily_range = np.random.uniform(0.01, 0.03, n)
    
    open_prices = close_prices * (1 + np.random.uniform(-0.01, 0.01, n))
    high_prices = np.maximum(open_prices, close_prices) * (1 + daily_range)
    low_prices = np.minimum(open_prices, close_prices) * (1 - daily_range)
    
    high_prices = np.maximum(high_prices, np.maximum(open_prices, close_prices))
    low_prices = np.minimum(low_prices, np.minimum(open_prices, close_prices))
    
    price_change = np.abs(np.diff(np.concatenate([[close_prices[0]], close_prices])))
    base_volume = 1000000
    volume = base_volume * (1 + price_change * 50 + np.random.uniform(0.5, 2.0, n))
    
    surge_count = int(n * 0.05)
    surge_days = np.random.choice(n, size=surge_count, replace=False)
    volume[surge_days] *= np.random.uniform(1.5, 3.0, len(surge_days))
    
    amount = volume * close_prices * 0.8
    
    return pd.DataFrame({
        "date": trading_dates,
        "symbol": [symbol] * n,
        "open": open_prices,
        "high": high_prices,
        "low": low_prices,
        "close": close_prices,
        "volume": volume.astype(int),
        "amount": amount,
        "adj_factor": [1.0] * n,
    })


def generate_statuses(symbol, trading_dates, seed,
                     suspended_days=1, limit_up_days=2, limit_down_days=1):
    """Generate daily status with sparse special events."""
    np.random.seed(seed + 2000)
    n = len(trading_dates)
    
    is_suspended = [False] * n
    is_limit_up = [False] * n
    is_limit_down = [False] * n
    is_st = [False] * n
    
    if suspended_days > 0:
        suspended_indices = np.random.choice(n, size=min(suspended_days, n), replace=False)
        for idx in suspended_indices:
            is_suspended[idx] = True
    
    if limit_up_days > 0:
        limit_up_indices = np.random.choice(n, size=min(limit_up_days, n), replace=False)
        for idx in limit_up_indices:
            is_limit_up[idx] = True
    
    if limit_down_days > 0:
        limit_down_indices = np.random.choice(n, size=min(limit_down_days, n), replace=False)
        for idx in limit_down_indices:
            is_limit_down[idx] = True
    
    return pd.DataFrame({
        "date": trading_dates,
        "symbol": [symbol] * n,
        "is_st": is_st,
        "is_suspended": is_suspended,
        "is_limit_up": is_limit_up,
        "is_limit_down": is_limit_down,
    })


def generate_benchmark_index(code, trading_dates, base_value, seed):
    """Generate benchmark index with slow upward trend and moderate volatility."""
    np.random.seed(seed + 5000)
    n = len(trading_dates)
    
    trend = np.linspace(0, 0.10, n)
    noise = np.random.normal(0, 0.008, n).cumsum()
    
    close_values = base_value * (1 + trend + noise * 0.3)
    
    daily_range = np.random.uniform(0.005, 0.015, n)
    open_values = close_values * (1 + np.random.uniform(-0.005, 0.005, n))
    high_values = np.maximum(open_values, close_values) * (1 + daily_range)
    low_values = np.minimum(open_values, close_values) * (1 - daily_range)
    
    volume = np.random.uniform(1e9, 3e9, n)
    amount = volume * close_values * 0.5
    
    return pd.DataFrame({
        "date": trading_dates,
        "code": [code] * n,
        "open": open_values,
        "high": high_values,
        "low": low_values,
        "close": close_values,
        "volume": volume.astype(int),
        "amount": amount,
    })

