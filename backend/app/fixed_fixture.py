"""
Fixed Fixture Data Source

Load 20-stock fixed snapshot for deterministic backtesting.
NOT a production data source. NOT real-time.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Optional

import pyarrow.parquet as pq

from backend.app.contracts import DailyBar, DailyStatus, StockIdentity
from strategy_core.data_source_metadata import DataSourceMetadata, validate_metadata
from contracts import SCHEMA_VERSION


class FixedFixtureDataSource:
    """
    Load 20-stock fixed fixture for reproducible testing.
    
    Data structure:
    - tests/fixed_fixture/metadata/manifest.json
    - tests/fixed_fixture/metadata/stock_list.json
    - tests/fixed_fixture/metadata/trade_calendar.json
    - tests/fixed_fixture/data/{symbol}_daily.parquet
    - tests/fixed_fixture/data/{symbol}_status.parquet
    """
    
    def __init__(self, fixture_path: Optional[Path] = None):
        """
        Args:
            fixture_path: Path to fixed_fixture directory. Defaults to tests/fixed_fixture.
        """
        if fixture_path is None:
            # Default: tests/fixed_fixture relative to this file
            fixture_path = Path(__file__).parent.parent.parent / "tests" / "fixed_fixture"
        
        self.fixture_path = fixture_path
        self.metadata_path = fixture_path / "metadata"
        self.data_path = fixture_path / "data"
        
        # Load manifest
        manifest_file = self.metadata_path / "manifest.json"
        if not manifest_file.exists():
            raise FileNotFoundError(
                f"Manifest not found: {manifest_file}\n"
                "Run backend/scripts/generate_fixed_fixture.py to create fixture."
            )
        
        with open(manifest_file, "r", encoding="utf-8") as f:
            self.manifest = json.load(f)
        
        # Load stock list
        stock_list_file = self.metadata_path / "stock_list.json"
        if not stock_list_file.exists():
            raise FileNotFoundError(f"Stock list not found: {stock_list_file}")
        
        with open(stock_list_file, "r", encoding="utf-8") as f:
            stock_list_data = json.load(f)
            self._stock_identities = {
                item["symbol"]: StockIdentity(**item) for item in stock_list_data
            }
        
        # Cache for loaded data
        self._daily_bars_cache: dict[str, list[DailyBar]] = {}
        self._daily_statuses_cache: dict[str, list[DailyStatus]] = {}
    
    def symbols(self) -> list[str]:
        """Return list of 20 stock symbols."""
        return list(self._stock_identities.keys())
    
    def get_stock_identity(self, symbol: str) -> StockIdentity:
        """Get stock identity info."""
        if symbol not in self._stock_identities:
            raise ValueError(f"Unknown symbol: {symbol}. Available: {self.symbols()}")
        return self._stock_identities[symbol]
    
    def get_daily_bars(self, symbol: str) -> list[DailyBar]:
        """Load daily bars for a symbol."""
        if symbol in self._daily_bars_cache:
            return self._daily_bars_cache[symbol]
        
        if symbol not in self._stock_identities:
            raise ValueError(f"Unknown symbol: {symbol}. Available: {self.symbols()}")
        
        parquet_file = self.data_path / f"{symbol}_daily.parquet"
        if not parquet_file.exists():
            raise FileNotFoundError(
                f"Daily bar data not found: {parquet_file}\n"
                f"Run backend/scripts/generate_fixed_fixture.py to create data for {symbol}."
            )
        
        table = pq.read_table(parquet_file)
        df = table.to_pandas()
        
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
        
        self._daily_bars_cache[symbol] = bars
        return bars
    
    def get_daily_statuses(self, symbol: str) -> list[DailyStatus]:
        """Load daily status for a symbol."""
        if symbol in self._daily_statuses_cache:
            return self._daily_statuses_cache[symbol]
        
        if symbol not in self._stock_identities:
            raise ValueError(f"Unknown symbol: {symbol}. Available: {self.symbols()}")
        
        parquet_file = self.data_path / f"{symbol}_status.parquet"
        if not parquet_file.exists():
            raise FileNotFoundError(
                f"Daily status data not found: {parquet_file}\n"
                f"Run backend/scripts/generate_fixed_fixture.py to create data for {symbol}."
            )
        
        table = pq.read_table(parquet_file)
        df = table.to_pandas()
        
        statuses = []
        for _, row in df.iterrows():
            statuses.append(DailyStatus(
                date=row["date"].date() if hasattr(row["date"], "date") else row["date"],
                symbol=row["symbol"],
                is_st=bool(row["is_st"]),
                is_suspended=bool(row["is_suspended"]),
                is_limit_up=bool(row["is_limit_up"]),
                is_limit_down=bool(row["is_limit_down"]),
            ))
        
        self._daily_statuses_cache[symbol] = statuses
        return statuses
    
    def get_daily_bar(self, symbol: str, date: date) -> DailyBar:
        """Get single bar for a symbol on a specific date."""
        bars = self.get_daily_bars(symbol)
        for bar in bars:
            if bar.date == date:
                return bar
        raise ValueError(f"No data for {symbol} on {date}")
    
    def get_daily_status(self, symbol: str, date: date) -> DailyStatus:
        """Get single status for a symbol on a specific date."""
        statuses = self.get_daily_statuses(symbol)
        for status in statuses:
            if status.date == date:
                return status
        raise ValueError(f"No status data for {symbol} on {date}")
    
    def get_price(self, symbol: str, date: date) -> float:
        """
        PriceProvider protocol implementation.
        Returns closing price for a symbol on a date.
        """
        bar = self.get_daily_bar(symbol, date)
        return bar.close
    
    def get_manifest(self) -> dict:
        """Return manifest metadata."""
        return self.manifest.copy()
    
    def get_metadata(self) -> DataSourceMetadata:
        """
        Return data source metadata for validation and versioning.
        
        M2 Requirement: All data sources must implement this method.
        
        Raises:
            ValueError: If manifest is missing required fields.
        """
        import hashlib
        from datetime import datetime
        
        # Validate manifest has required fields
        if "schema_version" not in self.manifest:
            raise ValueError(
                f"Manifest missing 'schema_version' field. "
                f"Run backend/scripts/generate_fixed_fixture.py to regenerate with schema version."
            )
        
        if "snapshot_hash" not in self.manifest:
            raise ValueError(
                f"Manifest missing 'snapshot_hash' field. "
                f"Run backend/scripts/generate_fixed_fixture.py to regenerate."
            )
        
        if "created_at" not in self.manifest:
            raise ValueError(
                f"Manifest missing 'created_at' field. "
                f"Run backend/scripts/generate_fixed_fixture.py to regenerate."
            )
        
        # Extract metadata from manifest
        manifest_created_at = self.manifest["created_at"]
        if isinstance(manifest_created_at, str):
            created_at = datetime.fromisoformat(manifest_created_at)
        else:
            created_at = manifest_created_at
        
        # Get trading calendar for date range
        trade_calendar_file = self.metadata_path / "trade_calendar.json"
        with open(trade_calendar_file, "r", encoding="utf-8") as f:
            trade_calendar = json.load(f)
        
        trading_dates = trade_calendar["trading_dates"]
        
        metadata = DataSourceMetadata(
            source_id=f"fixed_fixture_{len(self.symbols())}_stocks",
            source_type="fixed_fixture",
            schema_version=self.manifest["schema_version"],
            snapshot_id=self.manifest.get("mock_version", "mock_v2.1"),
            snapshot_hash=self.manifest["snapshot_hash"],
            created_at=created_at,
            data_mode="fixed_fixture",
            is_frozen=True,  # Fixed fixture is immutable
            symbol_count=len(self.symbols()),
            trading_days=len(trading_dates),
            date_range_start=trading_dates[0],
            date_range_end=trading_dates[-1],
        )
        
        # Validate metadata
        validate_metadata(metadata)
        
        return metadata
    
    def validate(self) -> "DataSourceValidationResult":
        """
        Validate data integrity.
        
        M2 Requirement: All data sources must provide validation capability.
        """
        from strategy_core.data_source_protocol import DataSourceValidationResult
        from datetime import datetime
        
        errors = []
        warnings = []
        checks = []
        
        # Check 1: Schema version
        checks.append("schema_version")
        try:
            metadata = self.get_metadata()
            # Validation already done in get_metadata()
        except Exception as e:
            errors.append(f"Metadata validation failed: {e}")
        
        # Check 2: Trading calendar
        checks.append("trading_calendar")
        try:
            trade_calendar_file = self.metadata_path / "trade_calendar.json"
            with open(trade_calendar_file, "r", encoding="utf-8") as f:
                trade_calendar = json.load(f)
            
            trading_dates = trade_calendar["trading_dates"]
            if not trading_dates:
                errors.append("Trading calendar is empty")
            elif trading_dates != sorted(trading_dates):
                errors.append("Trading dates are not sorted")
        except Exception as e:
            errors.append(f"Trading calendar check failed: {e}")
        
        # Check 3: Symbol coverage (basic check)
        checks.append("symbol_coverage")
        try:
            symbols = self.symbols()
            if not symbols:
                errors.append("No symbols available")
        except Exception as e:
            errors.append(f"Symbol coverage check failed: {e}")
        
        # Determine status
        if errors:
            status = "failed"
        elif warnings:
            status = "degraded"
        else:
            status = "pass"
        
        return DataSourceValidationResult(
            status=status,
            source_id=self.get_metadata().source_id if not errors else "unknown",
            checked_at=datetime.now(),
            errors=errors,
            warnings=warnings,
            checks_performed=checks,
        )
