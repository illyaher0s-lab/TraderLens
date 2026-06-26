"""
Tushare Data Source - M3.1

Real A-share data integration via Tushare API.
Snapshot generation and frozen data loading only.
"""

from backend.app.tushare.config import TushareConfig
from backend.app.tushare.tushare_data_source import TushareDataSource

__all__ = [
    "TushareConfig",
    "TushareDataSource",
]
