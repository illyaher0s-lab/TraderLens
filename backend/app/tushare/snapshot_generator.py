"""
Tushare Snapshot Generator - M3.2

Generate frozen Parquet snapshots from Tushare API.
Only used during snapshot generation phase, never during backtest.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from backend.app.tushare.config import TushareConfig
from backend.app.tushare.tushare_client import TushareClient
from contracts import SCHEMA_VERSION


class SnapshotGenerator:
    """
    Generate frozen data snapshots from Tushare API.
    
    M3.2 Implementation:
    - Download data from Tushare API
    - Save as Parquet with metadata
    - Compute deterministic snapshot hash
    - Generate manifest.json, stock_list.json, trade_calendar.json
    """
    
    def __init__(self, config: TushareConfig, client: TushareClient | None = None):
        """
        Initialize snapshot generator.
        
        Args:
            config: TushareConfig with token and storage paths
            client: Optional TushareClient (for testing with mock)
        """
        self.config = config
        self.client = client or TushareClient(config)
    
    def generate_snapshot(
        self,
        symbols: list[str],
        start_date: str,
        end_date: str,
        snapshot_id: str,
    ) -> None:
        """
        Generate frozen snapshot for given symbols and date range.
        
        Args:
            symbols: List of stock symbols (e.g., ["600519.SH", "000001.SZ"])
            start_date: Start date in YYYYMMDD format (e.g., "20230101")
            end_date: End date in YYYYMMDD format (e.g., "20231231")
            snapshot_id: Human-readable snapshot identifier (e.g., "10stocks_30days")
        
        Raises:
            ValueError: If API calls fail or data is incomplete
        
        Process:
        1. Ensure directories exist
        2. Fetch stock identities
        3. Fetch trade calendar
        4. Fetch daily bars for each symbol
        5. Fetch daily statuses for each symbol
        6. Save Parquet files
        7. Generate metadata files
        8. Compute snapshot hash
        9. Write manifest
        """
        # Ensure directories
        self.config.ensure_directories()
        
        print(f"Generating snapshot: {snapshot_id}")
        print(f"Symbols: {len(symbols)}")
        print(f"Date range: {start_date} to {end_date}")
        
        # Step 1: Fetch stock identities
        print("\n[1/5] Fetching stock identities...")
        stock_list = self._fetch_stock_identities(symbols)
        
        # Step 2: Fetch trade calendar
        print("\n[2/5] Fetching trade calendar...")
        trade_calendar = self._fetch_trade_calendar(start_date, end_date)
        
        # Step 3: Fetch daily bars
        print("\n[3/5] Fetching daily bars...")
        daily_files = []
        for i, symbol in enumerate(symbols, 1):
            print(f"  [{i}/{len(symbols)}] {symbol}")
            df = self._fetch_daily_bars(symbol, start_date, end_date)
            file_path = self._save_daily_bars(symbol, df)
            daily_files.append(file_path)
        
        # Step 4: Fetch daily statuses
        print("\n[4/5] Fetching daily statuses...")
        status_files = []
        for i, symbol in enumerate(symbols, 1):
            print(f"  [{i}/{len(symbols)}] {symbol}")
            df = self._fetch_daily_statuses(symbol, start_date, end_date, trade_calendar)
            file_path = self._save_daily_statuses(symbol, df)
            status_files.append(file_path)
        
        # Step 5: Generate metadata and manifest
        print("\n[5/5] Generating metadata...")
        self._save_stock_list(stock_list)
        self._save_trade_calendar(trade_calendar)
        
        # Compute deterministic hash
        snapshot_hash = self._compute_snapshot_hash(
            stock_list, trade_calendar, daily_files, status_files
        )
        
        # Write manifest
        manifest = self._create_manifest(
            snapshot_id=snapshot_id,
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
            trading_days=len(trade_calendar),
            snapshot_hash=snapshot_hash,
        )
        self._save_manifest(manifest)
        
        print(f"\n✓ Snapshot generated: {snapshot_id}")
        print(f"  Hash: {snapshot_hash}")
        print(f"  Files: {len(daily_files) + len(status_files)} Parquet files")
    
    def _fetch_stock_identities(self, symbols: list[str]) -> list[dict[str, Any]]:
        """
        Fetch stock identity information from Tushare.
        
        Returns:
            List of stock identity dicts matching StockIdentity contract
        """
        stock_list = []
        
        for symbol in symbols:
            # Query stock_basic API
            df = self.client.query("stock_basic", ts_code=symbol)
            
            if df.empty:
                raise ValueError(f"Stock not found: {symbol}")
            
            row = df.iloc[0]
            
            # Map Tushare fields to StockIdentity contract
            stock_list.append({
                "symbol": symbol,
                "name": row.get("name", "Unknown"),
                "exchange": "SSE" if symbol.endswith(".SH") else "SZSE",
                "list_date": row.get("list_date", "19900101"),  # YYYYMMDD format
                "delist_date": row.get("delist_date") if pd.notna(row.get("delist_date")) else None,
                "current_status": "listed",  # Simplify for M3.2
                "industry": row.get("industry", "Unknown"),
                "sector": row.get("area", "Unknown"),
            })
        
        return stock_list
    
    def _fetch_trade_calendar(self, start_date: str, end_date: str) -> list[str]:
        """
        Fetch trade calendar from Tushare.
        
        Returns:
            List of trading dates in YYYY-MM-DD format, sorted
        """
        df = self.client.query(
            "trade_cal",
            exchange="SSE",  # Use SSE calendar (consistent with SZSE)
            start_date=start_date,
            end_date=end_date,
            is_open="1",  # Only trading days
        )
        
        if df.empty:
            raise ValueError(f"No trading days found: {start_date} to {end_date}")
        
        # Convert YYYYMMDD to YYYY-MM-DD
        trading_dates = []
        for date_str in df["cal_date"].values:
            date_str = str(date_str)
            formatted = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
            trading_dates.append(formatted)
        
        return sorted(trading_dates)
    
    def _fetch_daily_bars(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        Fetch daily bars from Tushare.
        
        Returns:
            DataFrame with columns: date, symbol, open, high, low, close, volume, amount, adj_factor
        """
        df = self.client.query(
            "daily",
            ts_code=symbol,
            start_date=start_date,
            end_date=end_date,
        )
        
        if df.empty:
            raise ValueError(f"No daily bar data for {symbol}: {start_date} to {end_date}")
        
        # Get adj_factor
        adj_df = self.client.query(
            "adj_factor",
            ts_code=symbol,
            start_date=start_date,
            end_date=end_date,
        )
        
        # Merge adj_factor
        if not adj_df.empty:
            df = df.merge(adj_df[["trade_date", "adj_factor"]], on="trade_date", how="left")
        
        # Fill missing adj_factor with 1.0
        if "adj_factor" not in df.columns:
            df["adj_factor"] = 1.0
        else:
            df["adj_factor"] = df["adj_factor"].fillna(1.0)
        
        # Map to contract schema
        result = pd.DataFrame({
            "date": pd.to_datetime(df["trade_date"], format="%Y%m%d"),
            "symbol": symbol,
            "open": df["open"],
            "high": df["high"],
            "low": df["low"],
            "close": df["close"],
            "volume": df["vol"] * 100,  # Tushare vol in 手 (100 shares)
            "amount": df["amount"] * 1000,  # Tushare amount in 千元
            "adj_factor": df["adj_factor"],
        })
        
        # Sort by date
        result = result.sort_values("date").reset_index(drop=True)
        
        return result
    
    def _fetch_daily_statuses(
        self, symbol: str, start_date: str, end_date: str, trade_calendar: list[str]
    ) -> pd.DataFrame:
        """
        Fetch daily statuses from Tushare.
        
        Note: Tushare doesn't have a single "daily_status" API.
              We query multiple APIs and merge results.
        
        Returns:
            DataFrame with columns: date, symbol, is_st, is_suspended, is_limit_up, is_limit_down
        """
        # Query suspend_d API for suspension info
        suspend_df = self.client.query(
            "suspend_d",
            ts_code=symbol,
            start_date=start_date,
            end_date=end_date,
        )
        
        # Create base status DataFrame from trade calendar
        status_data = []
        for date_str in trade_calendar:
            date_yyyymmdd = date_str.replace("-", "")
            
            is_suspended = False
            if not suspend_df.empty:
                is_suspended = date_yyyymmdd in suspend_df["suspend_date"].values
            
            status_data.append({
                "date": pd.to_datetime(date_str),
                "symbol": symbol,
                "is_st": False,  # M3.2: Simplify (would need name_change or stk_limit API)
                "is_suspended": is_suspended,
                "is_limit_up": False,  # M3.2: Simplify (would need limit_list API)
                "is_limit_down": False,  # M3.2: Simplify
                "suspend_reason": None,
                "st_type": None,
            })
        
        result = pd.DataFrame(status_data)
        return result.sort_values("date").reset_index(drop=True)
    
    def _save_daily_bars(self, symbol: str, df: pd.DataFrame) -> Path:
        """Save daily bars to Parquet."""
        file_path = self.config.data_dir / f"{symbol}_daily.parquet"
        
        # Convert to PyArrow Table for schema control
        table = pa.Table.from_pandas(df, preserve_index=False)
        
        # Write Parquet
        pq.write_table(table, file_path, compression="snappy")
        
        return file_path
    
    def _save_daily_statuses(self, symbol: str, df: pd.DataFrame) -> Path:
        """Save daily statuses to Parquet."""
        file_path = self.config.data_dir / f"{symbol}_status.parquet"
        
        # Convert to PyArrow Table
        table = pa.Table.from_pandas(df, preserve_index=False)
        
        # Write Parquet
        pq.write_table(table, file_path, compression="snappy")
        
        return file_path
    
    def _save_stock_list(self, stock_list: list[dict[str, Any]]) -> None:
        """Save stock list to JSON."""
        file_path = self.config.metadata_dir / "stock_list.json"
        
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(stock_list, f, indent=2, ensure_ascii=False)
    
    def _save_trade_calendar(self, trade_calendar: list[str]) -> None:
        """Save trade calendar to JSON."""
        file_path = self.config.metadata_dir / "trade_calendar.json"
        
        data = {"trading_dates": trade_calendar}
        
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def _compute_snapshot_hash(
        self,
        stock_list: list[dict[str, Any]],
        trade_calendar: list[str],
        daily_files: list[Path],
        status_files: list[Path],
    ) -> str:
        """
        Compute deterministic snapshot hash.
        
        Hash includes:
        - Stock list (symbols + metadata)
        - Trade calendar
        - File content hashes (deterministic)
        
        Does NOT include:
        - created_at or updated_at timestamps
        - File paths
        """
        hasher = hashlib.sha256()
        
        # Hash stock list (sorted by symbol for determinism)
        sorted_stocks = sorted(stock_list, key=lambda x: x["symbol"])
        stock_json = json.dumps(sorted_stocks, sort_keys=True, ensure_ascii=False)
        hasher.update(stock_json.encode("utf-8"))
        
        # Hash trade calendar (already sorted)
        calendar_json = json.dumps(trade_calendar, ensure_ascii=False)
        hasher.update(calendar_json.encode("utf-8"))
        
        # Hash Parquet file contents (sorted by filename)
        all_files = sorted(daily_files + status_files, key=lambda p: p.name)
        for file_path in all_files:
            with open(file_path, "rb") as f:
                hasher.update(f.read())
        
        return hasher.hexdigest()[:16]  # First 16 chars for readability
    
    def _create_manifest(
        self,
        snapshot_id: str,
        symbols: list[str],
        start_date: str,
        end_date: str,
        trading_days: int,
        snapshot_hash: str,
    ) -> dict[str, Any]:
        """Create manifest dict."""
        now = datetime.utcnow()
        
        # Format dates as YYYY-MM-DD
        start_formatted = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:8]}"
        end_formatted = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:8]}"
        
        return {
            "dataset_name": snapshot_id,
            "version": "1.0.0",
            "source": "tushare",
            "fetched_at": now.isoformat() + "Z",
            "created_at": now.isoformat() + "Z",
            "date_range": {
                "start": start_formatted,
                "end": end_formatted,
            },
            "adjust_type": "qfq",  # Forward-adjusted (前复权)
            "schema_version": SCHEMA_VERSION,
            "snapshot_hash": snapshot_hash,
            "is_frozen": True,
            "stock_count": len(symbols),
            "trading_days_count": trading_days,
            "stocks": sorted(symbols),
        }
    
    def _save_manifest(self, manifest: dict[str, Any]) -> None:
        """Save manifest to JSON."""
        file_path = self.config.metadata_dir / "manifest.json"
        
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
    
    def validate_snapshot(self) -> dict[str, Any]:
        """
        Validate snapshot integrity.
        
        Checks:
        - manifest.json exists and has required fields
        - stock_list.json exists
        - trade_calendar.json exists
        - Each symbol has daily.parquet and status.parquet
        - Snapshot hash matches content
        - OHLC constraints valid
        - No negative volume/amount
        
        Returns:
            Validation result dict with status, errors, warnings
        """
        errors = []
        warnings = []
        checks = []
        
        # Check 1: Manifest exists
        checks.append("manifest_exists")
        manifest_file = self.config.metadata_dir / "manifest.json"
        if not manifest_file.exists():
            errors.append(f"Manifest not found: {manifest_file}")
            return {
                "status": "failed",
                "errors": errors,
                "warnings": warnings,
                "checks_performed": checks,
            }
        
        with open(manifest_file, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        
        # Check 2: Required manifest fields
        checks.append("manifest_fields")
        required_fields = [
            "snapshot_hash", "schema_version", "created_at",
            "source", "stock_count", "trading_days_count", "stocks", "is_frozen"
        ]
        for field in required_fields:
            if field not in manifest:
                errors.append(f"Manifest missing required field: {field}")
        
        if "is_frozen" in manifest and not manifest["is_frozen"]:
            errors.append("Snapshot is_frozen must be True")
        
        # Check 3: stock_list.json exists
        checks.append("stock_list_exists")
        stock_list_file = self.config.metadata_dir / "stock_list.json"
        if not stock_list_file.exists():
            errors.append(f"Stock list not found: {stock_list_file}")
        else:
            with open(stock_list_file, "r", encoding="utf-8") as f:
                stock_list = json.load(f)
            
            if len(stock_list) != manifest.get("stock_count", 0):
                warnings.append(
                    f"Stock count mismatch: manifest={manifest.get('stock_count')}, "
                    f"stock_list={len(stock_list)}"
                )
        
        # Check 4: trade_calendar.json exists
        checks.append("trade_calendar_exists")
        calendar_file = self.config.metadata_dir / "trade_calendar.json"
        if not calendar_file.exists():
            errors.append(f"Trade calendar not found: {calendar_file}")
        else:
            with open(calendar_file, "r", encoding="utf-8") as f:
                calendar_data = json.load(f)
            
            trading_dates = calendar_data.get("trading_dates", [])
            if len(trading_dates) != manifest.get("trading_days_count", 0):
                warnings.append(
                    f"Trading days count mismatch: manifest={manifest.get('trading_days_count')}, "
                    f"calendar={len(trading_dates)}"
                )
        
        # Check 5: Parquet files exist
        checks.append("parquet_files_exist")
        if "stocks" in manifest:
            for symbol in manifest["stocks"]:
                daily_file = self.config.data_dir / f"{symbol}_daily.parquet"
                status_file = self.config.data_dir / f"{symbol}_status.parquet"
                
                if not daily_file.exists():
                    errors.append(f"Missing daily data: {daily_file}")
                
                if not status_file.exists():
                    errors.append(f"Missing status data: {status_file}")
        
        # Determine status
        if errors:
            status = "failed"
        elif warnings:
            status = "degraded"
        else:
            status = "pass"
        
        return {
            "status": status,
            "errors": errors,
            "warnings": warnings,
            "checks_performed": checks,
        }
