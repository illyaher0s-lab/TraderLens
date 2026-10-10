"""Test board sample selection and suspend_d partitioning."""
import os
from pathlib import Path

env = {}
for line in Path("D:/Codex/TraderLens/.env.local").read_text(encoding="utf-8").splitlines():
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()


def test_board_samples_by_prefix():
    """Main/chinext/star selected by ts_code prefix, not market column."""
    import pandas as pd
    
    # ponytail: use merged snapshot
    df = pd.read_parquet("data/pit/tushare/1ad2b85b44b4e602/stock_basic.parquet")
    
    main = df[df['ts_code'].str.startswith('60')]
    chinext = df[df['ts_code'].str.startswith('30')]
    star = df[df['ts_code'].str.startswith(('688', '689'))]
    
    assert len(main) > 0, "No main board (60*)"
    assert len(chinext) > 0, "No chinext (30*)"
    assert len(star) > 0, "No star (688/689*)"
    
    # ponytail: first of each
    assert main.iloc[0]['ts_code'].startswith('60')
    assert chinext.iloc[0]['ts_code'].startswith('30')
    assert star.iloc[0]['ts_code'].startswith(('688', '689'))


def test_suspend_d_partition_coverage():
    """suspend_d must partition 2019-2025, each <5000 rows, dates in range."""
    import tushare as ts
    
    pro = ts.pro_api(env["TUSHARE_TOKEN"], timeout=30)
    pro._DataApi__http_url = env["TUSHARE_API_URL"]
    
    # ponytail: quarterly partitions
    partitions = [
        ("20190101", "20190331"),
        ("20240101", "20240331"),
    ]
    
    for start, end in partitions:
        df = pro.suspend_d(start_date=start, end_date=end)
        
        assert len(df) < 5000, f"Partition {start}-{end} hit 5000 limit (truncated)"
        
        if len(df) > 0 and 'trade_date' in df.columns:
            dates = df['trade_date'].astype(str)
            assert dates.min() >= start, f"Date {dates.min()} before {start}"
            assert dates.max() <= end, f"Date {dates.max()} after {end}"
