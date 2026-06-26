"""
Benchmark Data Source

Loads benchmark index data (e.g., CSI 500, CSI 300) for backtest comparison.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import pyarrow.parquet as pq
from pydantic import BaseModel

from backend.app.contracts import DailyBar
from strategy_core.data_source_metadata import DataSourceMetadata, validate_metadata
from contracts import SCHEMA_VERSION

class BenchmarkBar(BaseModel):
    """Benchmark daily bar data."""
    date: date
    code: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    amount: float


class BenchmarkIdentity(BaseModel):
    """Benchmark identity information."""
    code: str
    name: str
    name_en: str
    exchange: str
    index_type: str
    base_date: str
    base_value: float
    description: str = ""


class BenchmarkDataSource:
    """
    Load benchmark (index) data from fixed fixture.
    
    Benchmarks are stored in tests/fixed_fixture/benchmarks/:
    - benchmark_list.json: metadata for all benchmarks
    - {code}_daily.parquet: daily bar data for each benchmark
    """
    
    def __init__(self, benchmarks_path: Optional[Path] = None):
        """
        Args:
            benchmarks_path: Path to benchmarks directory. Defaults to tests/fixed_fixture/benchmarks.
        """
        if benchmarks_path is None:
            # Default: tests/fixed_fixture/benchmarks relative to this file
            benchmarks_path = Path(__file__).parent.parent.parent / "tests" / "fixed_fixture" / "benchmarks"
        
        self.benchmarks_path = benchmarks_path
        
        # Load benchmark list
        benchmark_list_file = self.benchmarks_path / "benchmark_list.json"
        if not benchmark_list_file.exists():
            raise FileNotFoundError(
                f"benchmark_list.json not found: {benchmark_list_file}\n"
                "Run backend/scripts/generate_fixed_fixture.py to create benchmark data."
            )
        
        with open(benchmark_list_file, "r", encoding="utf-8") as f:
            benchmark_list_data = json.load(f)
            self._benchmark_identities = {
                item["code"]: BenchmarkIdentity(**item) for item in benchmark_list_data
            }
        
        # Cache for loaded data
        self._bars_cache: dict[str, list[BenchmarkBar]] = {}
    
    def codes(self) -> list[str]:
        """Return list of available benchmark codes."""
        return list(self._benchmark_identities.keys())
    
    def get_benchmark_identity(self, code: str) -> BenchmarkIdentity:
        """Get benchmark identity info."""
        if code not in self._benchmark_identities:
            raise ValueError(f"Unknown benchmark code: {code}. Available: {self.codes()}")
        return self._benchmark_identities[code]
    
    def get_daily_bars(self, code: str) -> list[BenchmarkBar]:
        """Load daily bars for a benchmark."""
        if code in self._bars_cache:
            return self._bars_cache[code]
        
        if code not in self._benchmark_identities:
            raise ValueError(f"Unknown benchmark code: {code}. Available: {self.codes()}")
        
        parquet_file = self.benchmarks_path / f"{code}_daily.parquet"
        if not parquet_file.exists():
            raise FileNotFoundError(
                f"Benchmark data not found: {parquet_file}\n"
                f"Run backend/scripts/generate_fixed_fixture.py to create data for {code}."
            )
        
        table = pq.read_table(parquet_file)
        df = table.to_pandas()
        
        bars = []
        for _, row in df.iterrows():
            bars.append(BenchmarkBar(
                date=row["date"].date() if hasattr(row["date"], "date") else row["date"],
                code=row["code"],
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=int(row["volume"]),
                amount=float(row["amount"]),
            ))
        
        self._bars_cache[code] = bars
        return bars
    
    def get_daily_bar(self, code: str, date: date) -> BenchmarkBar:
        """Get single bar for a benchmark on a specific date."""
        bars = self.get_daily_bars(code)
        for bar in bars:
            if bar.date == date:
                return bar
        raise ValueError(f"No data for {code} on {date}")
    
    def get_close_price(self, code: str, date: date) -> float:
        """Get closing price for a benchmark on a date."""
        bar = self.get_daily_bar(code, date)
        return bar.close
    
    def calculate_return(self, code: str, start_date: date, end_date: date) -> float:
        """
        Calculate benchmark return between two dates.
        
        Returns:
            Total return as decimal (e.g., 0.15 for 15% gain)
        """
        start_bar = self.get_daily_bar(code, start_date)
        end_bar = self.get_daily_bar(code, end_date)
        
        return (end_bar.close - start_bar.close) / start_bar.close
    
    def get_metadata(self) -> DataSourceMetadata:
        """
        Return data source metadata for validation and versioning.
        
        M2 Requirement: All data sources must implement this method.
        """
        # Collect all dates from all benchmarks
        all_dates = set()
        for code in self.codes():
            bars = self.get_daily_bars(code)
            for bar in bars:
                all_dates.add(bar.date)
        
        if not all_dates:
            raise ValueError("Benchmark has no data")
        
        sorted_dates = sorted(all_dates)
        
        # Use fixed deterministic values for benchmark fixture
        metadata = DataSourceMetadata(
            source_id=f"benchmark_fixture_{len(self.codes())}_indexes",
            source_type="benchmark_fixture",
            schema_version=SCHEMA_VERSION,
            snapshot_id="benchmark_mock_v2.1",
            snapshot_hash="benchmark_fixture_deterministic",  # Fixed deterministic hash
            created_at=datetime(2026, 6, 22, 15, 21, 10),  # Match fixed_fixture created_at
            data_mode="fixed_fixture",
            is_frozen=True,  # Benchmark fixture is immutable
            symbol_count=len(self.codes()),
            trading_days=len(sorted_dates),
            date_range_start=sorted_dates[0].isoformat(),
            date_range_end=sorted_dates[-1].isoformat(),
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
        
        errors = []
        warnings = []
        checks = ["schema_version", "benchmark_coverage"]
        
        # Check metadata
        try:
            metadata = self.get_metadata()
        except Exception as e:
            errors.append(f"Metadata validation failed: {e}")
        
        # Check benchmarks
        try:
            if not self._benchmark_identities:
                errors.append("No benchmarks available")
        except Exception as e:
            errors.append(f"Benchmark check failed: {e}")
        
        # Determine status
        if errors:
            status = "failed"
        elif warnings:
            status = "degraded"
        else:
            status = "pass"
        
        return DataSourceValidationResult(
            status=status,
            source_id=self.get_metadata().source_id if not errors else "benchmark",
            checked_at=datetime.now(),
            errors=errors,
            warnings=warnings,
            checks_performed=checks,
        )
