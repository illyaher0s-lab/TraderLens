"""Build an operational, current-only incremental market-data snapshot.

This module deliberately has no formal PIT or backtest-universe dependency.
The injected provider makes the test boundary deterministic; the CLI is the
only place that wires the existing Tushare client.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd


CURRENT_NAMESPACE = Path("data/current_market_snapshots")
DATE_DATASETS = ("daily", "adj_factor", "suspend_d", "stk_limit")
REQUIRED_DATE_DATASETS = ("daily", "adj_factor", "stk_limit")
SHANGHAI = ZoneInfo("Asia/Shanghai")
CLOSE_TIME = time(15, 0)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _date_text(value: date) -> str:
    return value.strftime("%Y%m%d")


def _parse_date(value: Any) -> date:
    try:
        return datetime.strptime(str(value), "%Y%m%d").date()
    except (TypeError, ValueError) as exc:
        raise ValueError("data_fault: invalid date") from exc


def _query(provider: Any, api_name: str, **params: Any) -> pd.DataFrame:
    try:
        frame = provider.query(api_name, **params)
    except Exception as exc:
        raise ValueError(f"data_fault: {api_name} query failed: {exc}") from exc
    if frame is None or not isinstance(frame, pd.DataFrame):
        raise ValueError(f"data_fault: {api_name} response is not a DataFrame")
    return frame.copy()


def _load_env_local(repo_root: Path) -> None:
    env_file = Path(repo_root) / ".env.local"
    if not env_file.exists():
        return
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = (part.strip() for part in line.split("=", 1))
        if key not in {"TUSHARE_TOKEN", "TUSHARE_API_URL"}:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key, value)


def _open_dates(frame: pd.DataFrame, exchange: str, cutoff: date) -> set[date]:
    required = {"exchange", "cal_date", "is_open"}
    if set(frame.columns) < required:
        raise ValueError(f"data_fault: {exchange} calendar schema")
    if frame["cal_date"].duplicated().any():
        raise ValueError(f"data_fault: {exchange} calendar duplicate date")
    values: set[date] = set()
    for row in frame.itertuples(index=False):
        if row.exchange != exchange or type(row.is_open) is not int or row.is_open not in (0, 1):
            raise ValueError(f"data_fault: {exchange} calendar value")
        day = _parse_date(row.cal_date)
        if row.is_open == 1 and day <= cutoff:
            values.add(day)
    return values


def _cutoff(now: datetime) -> date:
    if now.tzinfo is not None:
        now = now.astimezone(SHANGHAI)
    return now.date() if now.time() >= CLOSE_TIME else now.date() - timedelta(days=1)


def common_trading_dates(provider: Any, now: datetime) -> list[date]:
    """Return completed SSE/SZSE common open dates in order."""
    cutoff = _cutoff(now)
    params = {"start_date": "20160101", "end_date": _date_text(cutoff)}
    sse = _open_dates(_query(provider, "trade_cal", exchange="SSE", **params), "SSE", cutoff)
    szse = _open_dates(_query(provider, "trade_cal", exchange="SZSE", **params), "SZSE", cutoff)
    common = sorted(sse & szse)
    if not common:
        raise ValueError("data_stale: no completed common trading date")
    return common


def select_latest_common_date(provider: Any, now: datetime) -> date:
    """Return the latest completed SSE/SZSE common open date."""
    return common_trading_dates(provider, now)[-1]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _relative(repo_root: Path, path: Path) -> str:
    return path.relative_to(repo_root).as_posix()


class CurrentIncrementalSnapshotBuilder:
    """Build only current operational data; never writes formal PIT paths."""

    def __init__(self, repo_root: Path, provider: Any, *, history_end: date, now: datetime):
        self.repo_root = Path(repo_root).resolve()
        self.provider = provider
        self.history_end = history_end
        self.now = now
        self.current_root = self.repo_root / CURRENT_NAMESPACE
        self.common_dates = common_trading_dates(provider, now)
        self.as_of_date = self.common_dates[-1]

    def _partition_path(self, dataset: str, trade_date: str) -> Path:
        return self.current_root / dataset / f"trade_date={trade_date}" / "part.parquet"

    def _record(self, path: Path, dataset: str, params: dict[str, Any]) -> dict[str, Any]:
        return {
            "dataset": dataset,
            "trade_date": params.get("trade_date"),
            "path": _relative(self.repo_root, path),
            "row_count": int(len(pd.read_parquet(path, engine="pyarrow"))),
            "size": path.stat().st_size,
            "sha256": _sha256(path),
            "source_params": params,
        }

    def _existing_partition(self, path: Path) -> bool:
        sidecar = path.with_suffix(".parquet.sha256")
        if not path.exists() and not sidecar.exists():
            return False
        if not path.exists() or not sidecar.exists() or sidecar.read_text(encoding="ascii").strip() != _sha256(path):
            raise ValueError(f"data_fault: partition hash conflict: {path}")
        return True

    def _write_partition(self, path: Path, frame: pd.DataFrame) -> None:
        if self._existing_partition(path):
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_suffix(".parquet.partial")
        frame.to_parquet(partial, index=False, engine="pyarrow")
        partial.replace(path)
        sidecar_partial = path.with_suffix(".parquet.sha256.partial")
        sidecar_partial.write_text(_sha256(path), encoding="ascii")
        sidecar_partial.replace(path.with_suffix(".parquet.sha256"))

    def _validate_date_frame(self, dataset: str, frame: pd.DataFrame, day: str) -> None:
        if "trade_date" not in frame.columns:
            raise ValueError(f"data_fault: {dataset} schema")
        if not frame.empty and set(frame["trade_date"].map(str)) != {day}:
            raise ValueError(f"data_stale: {dataset} date mismatch")
        if dataset in REQUIRED_DATE_DATASETS and frame.empty:
            raise ValueError(f"data_stale: {dataset} empty for {day}")

    def _write_state(self, snapshot_dir: Path, dataset: str, frame: pd.DataFrame, params: dict[str, Any]) -> dict[str, Any]:
        path = snapshot_dir / "state" / f"{dataset}.parquet"
        if self._existing_partition(path):
            return self._record(path, dataset, params)
        self._write_partition(path, frame)
        return self._record(path, dataset, params)

    def build(self) -> dict[str, Any]:
        if self.current_root.resolve() == self.repo_root / "data" / "pit":
            raise ValueError("data_fault: current namespace is formal PIT")
        snapshot_dir = self.current_root / f"as_of_date={self.as_of_date.isoformat()}"
        manifest_path = snapshot_dir / "manifest.json"
        if manifest_path.exists():
            raise ValueError("data_fault: current snapshot already exists")

        common_dates = [day for day in self.common_dates if day > self.history_end]
        missing_dates: list[str] = []
        records: list[dict[str, Any]] = []
        frames_to_write: list[tuple[Path, pd.DataFrame]] = []
        for day in common_dates:
            day_text = _date_text(day)
            missing = False
            for dataset in DATE_DATASETS:
                path = self._partition_path(dataset, day_text)
                if self._existing_partition(path):
                    records.append(self._record(path, dataset, {"resume": "exact", "trade_date": day_text}))
                else:
                    missing = True
                    frame = _query(self.provider, dataset, trade_date=day_text)
                    self._validate_date_frame(dataset, frame, day_text)
                    frames_to_write.append((path, frame))
            if missing:
                missing_dates.append(day_text)

        st_params = {"trade_date": _date_text(self.as_of_date)}
        stock_st = _query(self.provider, "stock_st", **st_params)
        self._validate_date_frame("stock_st", stock_st, st_params["trade_date"])

        snapshot_dir.mkdir(parents=True, exist_ok=True)
        for path, frame in frames_to_write:
            self._write_partition(path, frame)
            records.append(self._record(path, path.parts[-3], {"trade_date": path.parts[-2].split("=", 1)[1]}))
        records.append(self._write_state(snapshot_dir, "stock_st", stock_st, st_params))
        records.sort(key=lambda item: item["path"])
        manifest = {
            "schema_version": "current_incremental_snapshot_v1",
            "snapshot_type": "operational_current_market",
            "as_of_date": self.as_of_date.isoformat(),
            "source": {
                "provider": "tushare",
                "timezone": "Asia/Shanghai",
                "close_time": "15:00:00",
                "history_end": self.history_end.isoformat(),
                "apis": ["trade_cal", "daily", "adj_factor", "suspend_d", "stk_limit", "stock_st"],
            },
            "common_trading_dates": [_date_text(day) for day in common_dates],
            "missing_common_dates": missing_dates,
            "files": records,
            "gaps": [],
            "quality_status": "ok",
        }
        manifest_partial = manifest_path.with_suffix(".json.partial")
        manifest_partial.write_text(json.dumps(manifest, sort_keys=True, ensure_ascii=False, indent=2), encoding="utf-8")
        manifest_partial.replace(manifest_path)
        return {"as_of_date": self.as_of_date.isoformat(), "manifest_path": _relative(self.repo_root, manifest_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--history-end", default="20260710")
    parser.add_argument("--now", default=None, help="Asia/Shanghai ISO datetime; defaults to current time")
    args = parser.parse_args()
    _load_env_local(args.repo_root)
    from backend.app.tushare.config import TushareConfig
    from backend.app.tushare.tushare_client import TushareClient

    config = TushareConfig.from_env()
    config.retry_attempts = 2
    config.request_timeout_seconds = 8.0
    provider = TushareClient(config)
    now = datetime.fromisoformat(args.now) if args.now else datetime.now(SHANGHAI)
    result = CurrentIncrementalSnapshotBuilder(
        args.repo_root, provider, history_end=datetime.strptime(args.history_end, "%Y%m%d").date(), now=now
    ).build()
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
