"""
Tushare Data Source - M3.3

Load frozen Tushare snapshots for backtest execution.
Implements DataSource Protocol (8 methods).

Design:
- Reads frozen Parquet snapshots only (no live API calls)
- Lazy loads Parquet files with caching
- Fail-loud on missing data (KeyError for missing symbol/date)
- Returns is_frozen=True in metadata
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pyarrow.parquet as pq

from backend.app.tushare.config import TushareConfig
from contracts import SCHEMA_VERSION
from contracts.stable import DailyBar, DailyStatus, StockIdentity
from strategy_core.data_source_metadata import DataSourceMetadata, validate_metadata
from strategy_core.data_source_protocol import DataSourceValidationResult


class TushareDataSource:
    """
    Load frozen Tushare snapshots for backtest.
    
    M3.3 Implementation:
    - Implements DataSource Protocol (8 methods)
    - Reads Parquet snapshots only (no live API calls)
    - Fail-loud on missing data
    - Returns is_frozen=True in metadata
    """
    
    def __init__(self, config: TushareConfig):
        """
        Initialize Tushare data source.
        
        Args:
            config: TushareConfig with snapshot paths
        
        Raises:
            FileNotFoundError: If snapshot metadata not found
        
        Note: Does NOT call Tushare API. Reads frozen snapshots only.
        """
        self.config = config
        
        # Verify snapshot exists
        if not config.metadata_dir.exists():
            raise FileNotFoundError(
                f"Tushare snapshot metadata not found: {config.metadata_dir}\n"
                "Run backend/scripts/generate_tushare_snapshot.py to create frozen snapshot first."
            )
        
        # Load manifest
        manifest_file = config.metadata_dir / "manifest.json"
        if not manifest_file.exists():
            raise FileNotFoundError(
                f"Manifest not found: {manifest_file}\n"
                "Run backend/scripts/generate_tushare_snapshot.py to create snapshot."
            )
        
        with open(manifest_file, "r", encoding="utf-8") as f:
            self.manifest = json.load(f)
        
        # Load stock list
        stock_list_file = config.metadata_dir / "stock_list.json"
        if not stock_list_file.exists():
            raise FileNotFoundError(f"Stock list not found: {stock_list_file}")
        
        with open(stock_list_file, "r", encoding="utf-8") as f:
            stock_list_data = json.load(f)
            # Map: symbol -> StockIdentity
            self._stock_identity_map = {
                item["symbol"]: self._parse_stock_identity(item)
                for item in stock_list_data
            }
        
        # Load trade calendar
        calendar_file = config.metadata_dir / "trade_calendar.json"
        if not calendar_file.exists():
            raise FileNotFoundError(f"Trade calendar not found: {calendar_file}")
        
        with open(calendar_file, "r", encoding="utf-8") as f:
            calendar_data = json.load(f)
            self._trading_dates = calendar_data["trading_dates"]
        
        # Cache for loaded Parquet data
        self._daily_bars_cache: dict[str, list[DailyBar]] = {}
        self._daily_statuses_cache: dict[str, list[DailyStatus]] = {}
    
    @staticmethod
    def _parse_stock_identity(item: dict) -> StockIdentity:
        """Parse stock identity from JSON."""
        # Parse list_date
        list_date_str = item.get("list_date", "19900101")
        if isinstance(list_date_str, str) and len(list_date_str) == 8:
            list_date = date(
                int(list_date_str[:4]),
                int(list_date_str[4:6]),
                int(list_date_str[6:8])
            )
        else:
            list_date = date(1990, 1, 1)
        
        # Parse delist_date
        delist_date_str = item.get("delist_date")
        delist_date = None
        if delist_date_str and isinstance(delist_date_str, str) and len(delist_date_str) == 8:
            delist_date = date(
                int(delist_date_str[:4]),
                int(delist_date_str[4:6]),
                int(delist_date_str[6:8])
            )
        
        return StockIdentity(
            symbol=item["symbol"],
            name=item["name"],
            exchange=item["exchange"],
            list_date=list_date,
            delist_date=delist_date,
            current_status=item["current_status"],
            industry=item["industry"],
            sector=item["sector"],
        )
    
    def symbols(self) -> list[str]:
        """
        Return list of available symbols.
        
        Returns:
            List of stock symbols (e.g., ["600519.SH", "000001.SZ"])
        """
        return list(self._stock_identity_map.keys())
    
    def get_daily_bars(self, symbol: str) -> list[DailyBar]:
        """
        Return all daily bars for a symbol.
        
        Args:
            symbol: Stock symbol (e.g., "600519.SH")
        
        Returns:
            List of DailyBar sorted by date
        
        Raises:
            KeyError: If symbol not found (fail-loud, M2 policy)
        """
        # Check cache
        if symbol in self._daily_bars_cache:
            return self._daily_bars_cache[symbol]
        
        # Verify symbol exists
        if symbol not in self._stock_identity_map:
            raise KeyError(
                f"Symbol not found: {symbol}. "
                f"Available symbols: {self.symbols()}"
            )
        
        # Load Parquet
        parquet_file = self.config.data_dir / f"{symbol}_daily.parquet"
        if not parquet_file.exists():
            raise FileNotFoundError(
                f"Daily bar data not found: {parquet_file}\n"
                f"Snapshot may be incomplete. Run validation."
            )
        
        table = pq.read_table(parquet_file)
        df = table.to_pandas()
        
        # Convert to DailyBar contracts
        bars = []
        for _, row in df.iterrows():
            bars.append(DailyBar(
                date=row["date"].date() if hasattr(row["date"], "date") else row["date"],
                symbol=row["symbol"],
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=int(row["volume"]),
                amount=float(row["amount"]),
                adj_factor=float(row["adj_factor"]),
            ))
        
        # Cache and return
        self._daily_bars_cache[symbol] = bars
        return bars
    
    def get_daily_statuses(self, symbol: str) -> list[DailyStatus]:
        """
        Return all daily statuses for a symbol.
        
        Args:
            symbol: Stock symbol
        
        Returns:
            List of DailyStatus sorted by date
        
        Raises:
            KeyError: If symbol not found (fail-loud)
        """
        # Check cache
        if symbol in self._daily_statuses_cache:
            return self._daily_statuses_cache[symbol]
        
        # Verify symbol exists
        if symbol not in self._stock_identity_map:
            raise KeyError(
                f"Symbol not found: {symbol}. "
                f"Available symbols: {self.symbols()}"
            )
        
        # Load Parquet
        parquet_file = self.config.data_dir / f"{symbol}_status.parquet"
        if not parquet_file.exists():
            raise FileNotFoundError(
                f"Daily status data not found: {parquet_file}\n"
                f"Snapshot may be incomplete. Run validation."
            )
        
        table = pq.read_table(parquet_file)
        df = table.to_pandas()
        
        # Convert to DailyStatus contracts
        statuses = []
        for _, row in df.iterrows():
            statuses.append(DailyStatus(
                date=row["date"].date() if hasattr(row["date"], "date") else row["date"],
                symbol=row["symbol"],
                is_st=bool(row["is_st"]),
                is_suspended=bool(row["is_suspended"]),
                is_limit_up=bool(row["is_limit_up"]),
                is_limit_down=bool(row["is_limit_down"]),
                suspend_reason=row.get("suspend_reason"),
                st_type=row.get("st_type"),
            ))
        
        # Cache and return
        self._daily_statuses_cache[symbol] = statuses
        return statuses
    
    def get_daily_bar(self, symbol: str, date: date) -> DailyBar:
        """
        Return single bar for symbol on date.
        
        Args:
            symbol: Stock symbol
            date: Trading date
        
        Returns:
            DailyBar for that symbol and date
        
        Raises:
            KeyError: If symbol/date not found (fail-loud)
        """
        bars = self.get_daily_bars(symbol)
        
        for bar in bars:
            if bar.date == date:
                return bar
        
        raise KeyError(
            f"No daily bar data for {symbol} on {date}. "
            f"Available dates: {min(b.date for b in bars)} to {max(b.date for b in bars)}"
        )
    
    def get_daily_status(self, symbol: str, date: date) -> DailyStatus:
        """
        Return single status for symbol on date.
        
        Args:
            symbol: Stock symbol
            date: Trading date
        
        Returns:
            DailyStatus for that symbol and date
        
        Raises:
            KeyError: If symbol/date not found (fail-loud)
        """
        statuses = self.get_daily_statuses(symbol)
        
        for status in statuses:
            if status.date == date:
                return status
        
        raise KeyError(
            f"No daily status data for {symbol} on {date}. "
            f"Available dates: {min(s.date for s in statuses)} to {max(s.date for s in statuses)}"
        )
    
    def get_price(self, symbol: str, date: date) -> float:
        """
        PriceProvider protocol: get close price for symbol on date.
        
        Args:
            symbol: Stock symbol
            date: Trading date
        
        Returns:
            Closing price (float)
        
        Raises:
            KeyError: If symbol/date not found (fail-loud)
        """
        bar = self.get_daily_bar(symbol, date)
        return bar.close
    
    def get_metadata(self) -> DataSourceMetadata:
        """
        Return data source metadata including schema version.
        
        M2 Requirement: All data sources MUST implement this.
        
        Returns:
            DataSourceMetadata with schema_version, snapshot info, etc.
        
        Raises:
            ValueError: If required metadata fields are missing.
        """
        # Validate manifest has required fields
        required_fields = [
            "schema_version", "snapshot_hash", "created_at",
            "stock_count", "trading_days_count"
        ]
        
        for field in required_fields:
            if field not in self.manifest:
                raise ValueError(
                    f"Manifest missing required field: {field}. "
                    f"Snapshot may be corrupted. Run validation."
                )
        
        # Parse created_at
        manifest_created_at = self.manifest["created_at"]
        if isinstance(manifest_created_at, str):
            created_at = datetime.fromisoformat(manifest_created_at.replace("Z", "+00:00"))
        else:
            created_at = manifest_created_at
        
        # Extract date range
        date_range = self.manifest.get("date_range", {})
        date_range_start = date_range.get("start", self._trading_dates[0])
        date_range_end = date_range.get("end", self._trading_dates[-1])
        
        metadata = DataSourceMetadata(
            source_id=f"tushare_{self.manifest.get('dataset_name', 'unknown')}",
            source_type="fixed_fixture",  # Use existing literal (M3.2 simplification)
            schema_version=self.manifest["schema_version"],
            snapshot_id=self.manifest.get("dataset_name", "unknown"),
            snapshot_hash=self.manifest["snapshot_hash"],
            created_at=created_at,
            data_mode="real_data",
            is_frozen=True,  # Tushare snapshots are immutable
            symbol_count=self.manifest["stock_count"],
            trading_days=self.manifest["trading_days_count"],
            date_range_start=date_range_start,
            date_range_end=date_range_end,
        )
        
        # Validate metadata
        validate_metadata(metadata)
        
        return metadata
    
    def validate(self) -> DataSourceValidationResult:
        """
        Validate data integrity.
        
        M2 Requirement: All data sources must provide validation capability.
        
        Returns:
            DataSourceValidationResult with status and issues found.
        """
        from backend.app.tushare.snapshot_generator import SnapshotGenerator
        
        # Reuse M3.2 validation logic
        generator = SnapshotGenerator(self.config, client=None)  # No client needed for validation
        validation_result = generator.validate_snapshot()
        
        # Convert to DataSourceValidationResult
        return DataSourceValidationResult(
            status=validation_result["status"],
            source_id=self.get_metadata().source_id,
            checked_at=datetime.now(),
            errors=validation_result["errors"],
            warnings=validation_result["warnings"],
            checks_performed=validation_result["checks_performed"],
        )
