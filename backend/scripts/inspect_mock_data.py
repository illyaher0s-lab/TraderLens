"""Inspect mock data v2.1 characteristics"""
from pathlib import Path
import pyarrow.parquet as pq

fixture_path = Path("tests/fixed_fixture")
data_path = fixture_path / "data"

# Sample 3 stocks from different types
samples = [
    ("000001.SZ", "trend_up"),
    ("002475.SZ", "trend_down"),
    ("600000.SH", "mean_reversion"),
    ("601888.SH", "volatile_breakout"),
]

for symbol, stype in samples:
    print(f"\n{symbol} ({stype}):")
    
    # Read bars
    table = pq.read_table(data_path / f"{symbol}_daily.parquet")
    df = table.to_pandas()
    
    # Calculate some stats
    first_close = df.iloc[0]["close"]
    last_close = df.iloc[-1]["close"]
    total_return = (last_close - first_close) / first_close
    
    # High/low
    max_price = df["close"].max()
    min_price = df["close"].min()
    
    # Calculate 5-day high for breakthrough detection
    high_5d = df["high"].rolling(5).max()
    breakthrough_days = (df["close"] >= high_5d.shift(1)).sum()
    
    # Calculate MA20
    ma20 = df["close"].rolling(20).mean()
    above_ma20_days = (df["close"] > ma20).sum()
    
    print(f"  Close: {first_close:.2f} -> {last_close:.2f} ({total_return*100:.1f}%)")
    print(f"  Range: {min_price:.2f} - {max_price:.2f}")
    print(f"  Days where close >= 5d high: {breakthrough_days}")
    print(f"  Days where close > MA20: {above_ma20_days} / {len(df)}")
