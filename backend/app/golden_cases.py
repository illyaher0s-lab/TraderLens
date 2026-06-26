from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .contracts import DailyBar, DailyStatus
from strategy_core.data_source_metadata import DataSourceMetadata, validate_metadata
from contracts import SCHEMA_VERSION


@dataclass(frozen=True)
class GoldenCaseSnapshot:
    daily_bars: list[DailyBar]
    daily_statuses: list[DailyStatus]


class GoldenCaseDataSource:
    def __init__(self, root: str | Path):
        self._snapshots = load_golden_case_snapshots(root)
        self._bar_index: dict[tuple[str, date], DailyBar] = {}
        self._status_index: dict[tuple[str, date], DailyStatus] = {}
        for symbol, snapshot in self._snapshots.items():
            bar_dates = [bar.date for bar in snapshot.daily_bars]
            status_dates = [status.date for status in snapshot.daily_statuses]
            if bar_dates != status_dates:
                raise ValueError(f"daily bars and statuses are not date-aligned for {symbol}")
            for bar in snapshot.daily_bars:
                self._bar_index[(symbol, bar.date)] = bar
            for status in snapshot.daily_statuses:
                self._status_index[(symbol, status.date)] = status

    def symbols(self) -> list[str]:
        return sorted(self._snapshots)

    def get_daily_bars(self, symbol: str) -> list[DailyBar]:
        return list(self._snapshot(symbol).daily_bars)

    def get_daily_statuses(self, symbol: str) -> list[DailyStatus]:
        return list(self._snapshot(symbol).daily_statuses)

    def get_daily_bar(self, symbol: str, target_date: date) -> DailyBar:
        return self._get(self._bar_index, symbol, target_date)

    def get_daily_status(self, symbol: str, target_date: date) -> DailyStatus:
        return self._get(self._status_index, symbol, target_date)

    def get_price(self, symbol: str, target_date: date) -> float:
        """Return closing price for the given symbol and date (PriceProvider interface)."""
        bar = self.get_daily_bar(symbol, target_date)
        return bar.close

    def _snapshot(self, symbol: str) -> GoldenCaseSnapshot:
        try:
            return self._snapshots[symbol]
        except KeyError as exc:
            raise KeyError(f"unknown Golden Case symbol: {symbol}") from exc

    @staticmethod
    def _get(index: dict[tuple[str, date], Any], symbol: str, target_date: date) -> Any:
        try:
            return index[(symbol, target_date)]
        except KeyError as exc:
            raise KeyError(f"no Golden Case row for {symbol} on {target_date}") from exc
    
    def get_metadata(self) -> DataSourceMetadata:
        """
        Return data source metadata for validation and versioning.
        
        M2 Requirement: All data sources must implement this method.
        """
        # Collect all dates from all symbols
        all_dates = set()
        for snapshot in self._snapshots.values():
            for bar in snapshot.daily_bars:
                all_dates.add(bar.date)
        
        if not all_dates:
            raise ValueError("Golden Case has no data")
        
        sorted_dates = sorted(all_dates)
        
        metadata = DataSourceMetadata(
            source_id="golden_case_5_stocks",
            source_type="golden_case",
            schema_version=SCHEMA_VERSION,
            snapshot_id="golden_case_v1",
            snapshot_hash="golden_case_5_stocks_deterministic",  # Fixed deterministic hash
            created_at=datetime(2026, 1, 1, 0, 0, 0),  # Fixed deterministic timestamp
            data_mode="golden_case",
            is_frozen=True,  # Golden case is immutable
            symbol_count=len(self._snapshots),
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
        checks = ["schema_version", "symbol_coverage"]
        
        # Check metadata
        try:
            metadata = self.get_metadata()
        except Exception as e:
            errors.append(f"Metadata validation failed: {e}")
        
        # Check symbols
        try:
            if not self._snapshots:
                errors.append("No symbols available")
        except Exception as e:
            errors.append(f"Symbol check failed: {e}")
        
        # Determine status
        if errors:
            status = "failed"
        elif warnings:
            status = "degraded"
        else:
            status = "pass"
        
        return DataSourceValidationResult(
            status=status,
            source_id=self.get_metadata().source_id if not errors else "golden_case",
            checked_at=datetime.now(),
            errors=errors,
            warnings=warnings,
            checks_performed=checks,
        )


def _require_pyarrow() -> Any:
    try:
        import pyarrow.parquet as pq
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "pyarrow is required to read Golden Case Parquet snapshots. "
            "Install project dependencies before running this validation."
        ) from exc
    return pq


def _table_rows(parquet_path: Path) -> list[dict[str, Any]]:
    pq = _require_pyarrow()
    table = pq.read_table(parquet_path)
    return table.to_pylist()


def load_golden_case_snapshots(root: str | Path) -> dict[str, GoldenCaseSnapshot]:
    root_path = Path(root)
    snapshot_dir = root_path / "data_snapshot"
    if not snapshot_dir.exists():
        raise FileNotFoundError(f"Golden Case data snapshot directory not found: {snapshot_dir}")

    symbols = sorted(
        path.name.removesuffix("_daily.parquet")
        for path in snapshot_dir.glob("*_daily.parquet")
    )
    if not symbols:
        raise FileNotFoundError(f"No Golden Case daily Parquet snapshots found in: {snapshot_dir}")

    snapshots: dict[str, GoldenCaseSnapshot] = {}
    for symbol in symbols:
        daily_path = snapshot_dir / f"{symbol}_daily.parquet"
        status_path = snapshot_dir / f"{symbol}_status.parquet"
        if not status_path.exists():
            raise FileNotFoundError(f"Missing status snapshot for {symbol}: {status_path}")

        snapshots[symbol] = GoldenCaseSnapshot(
            daily_bars=[DailyBar.model_validate(row) for row in _table_rows(daily_path)],
            daily_statuses=[DailyStatus.model_validate(row) for row in _table_rows(status_path)],
        )
    return snapshots
