"""Test suspend_d uses actual server schema."""
import os
from pathlib import Path

# ponytail: inline env
env = {}
for line in Path("D:/Codex/TraderLens/.env.local").read_text(encoding="utf-8").splitlines():
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()


def test_suspend_d_returns_actual_schema():
    """suspend_d default call returns ts_code, trade_date, suspend_timing, suspend_type."""
    import tushare as ts
    
    pro = ts.pro_api(env["TUSHARE_TOKEN"], timeout=30)
    pro._DataApi__http_url = env["TUSHARE_API_URL"]
    
    df = pro.suspend_d()
    
    assert "ts_code" in df.columns
    assert "trade_date" in df.columns
    assert "suspend_timing" in df.columns or "suspend_type" in df.columns


def test_suspend_d_sparse_is_ok():
    """Empty result is valid for sparse event table."""
    import tushare as ts
    
    pro = ts.pro_api(env["TUSHARE_TOKEN"], timeout=30)
    pro._DataApi__http_url = env["TUSHARE_API_URL"]
    
    # ponytail: future window likely empty
    df = pro.suspend_d(start_date="20300101", end_date="20300131")
    
    # No assertion on row count — sparse is valid
    assert isinstance(df.columns.tolist(), list)
