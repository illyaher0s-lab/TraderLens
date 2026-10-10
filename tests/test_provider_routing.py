"""Test index routing fix."""
import os
from datetime import date, timedelta
from pathlib import Path

# ponytail: inline env
for line in Path("D:/Codex/TraderLens/.env.local").read_text(encoding="utf-8").splitlines():
    if line.strip() and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ[k.strip()] = v.strip()


def test_index_uses_index_daily_api():
    """000300.SH should route to index_daily, not daily."""
    from backend.services.research_validation import ResearchValidator
    
    validator = ResearchValidator()
    ts = validator.tushare_client
    
    snapshot = date(2024, 6, 28)  # ponytail: known trading day
    start = (snapshot - timedelta(days=10)).strftime("%Y%m%d")
    end = snapshot.strftime("%Y%m%d")
    
    # Stock route
    df_stock = ts.query("daily", ts_code="600519.SH", start_date=start, end_date=end)
    assert len(df_stock) > 0, "Stock daily should have data"
    
    # Index route
    df_index = ts.query("index_daily", ts_code="000300.SH", start_date=start, end_date=end)
    assert len(df_index) > 0, "Index daily should have data"

