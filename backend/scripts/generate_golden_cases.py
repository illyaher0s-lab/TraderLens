from __future__ import annotations

from datetime import date
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


STOCKS = {
    "000001.SZ": {"base": 10.0, "limit_up": False, "limit_down": False, "suspended": False},
    "600000.SH": {"base": 8.0, "limit_up": False, "limit_down": False, "suspended": True},
    "000002.SZ": {"base": 12.0, "limit_up": False, "limit_down": True, "suspended": False},
    "600519.SH": {"base": 1600.0, "limit_up": True, "limit_down": False, "suspended": False},
    "300750.SZ": {"base": 180.0, "limit_up": False, "limit_down": False, "suspended": False},
}


def _require_pyarrow():
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "pyarrow is required to generate Golden Case Parquet snapshots"
        ) from exc
    return pa, pq


def _daily_rows(symbol: str, base: float) -> list[dict[str, object]]:
    return [
        {
            "date": date(2024, 1, 2),
            "symbol": symbol,
            "open": base,
            "high": round(base * 1.02, 2),
            "low": round(base * 0.99, 2),
            "close": round(base * 1.01, 2),
            "volume": 1000000,
            "amount": base * 1000000,
            "adj_factor": 1.0,
        },
        {
            "date": date(2024, 1, 3),
            "symbol": symbol,
            "open": round(base * 1.01, 2),
            "high": round(base * 1.05, 2),
            "low": round(base * 1.00, 2),
            "close": round(base * 1.03, 2),
            "volume": 1200000,
            "amount": base * 1200000,
            "adj_factor": 1.0,
        },
        {
            "date": date(2025, 1, 2),
            "symbol": symbol,
            "open": round(base * 1.04, 2),
            "high": round(base * 1.06, 2),
            "low": round(base * 1.01, 2),
            "close": round(base * 1.02, 2),
            "volume": 900000,
            "amount": base * 900000,
            "adj_factor": 1.0,
        },
    ]


def _status_rows(symbol: str, flags: dict[str, object]) -> list[dict[str, object]]:
    return [
        {
            "date": date(2024, 1, 2),
            "symbol": symbol,
            "is_st": False,
            "is_suspended": False,
            "is_limit_up": False,
            "is_limit_down": False,
            "suspend_reason": None,
            "st_type": None,
        },
        {
            "date": date(2024, 1, 3),
            "symbol": symbol,
            "is_st": False,
            "is_suspended": bool(flags["suspended"]),
            "is_limit_up": bool(flags["limit_up"]),
            "is_limit_down": bool(flags["limit_down"]),
            "suspend_reason": "golden_case_suspension" if flags["suspended"] else None,
            "st_type": None,
        },
        {
            "date": date(2025, 1, 2),
            "symbol": symbol,
            "is_st": False,
            "is_suspended": False,
            "is_limit_up": False,
            "is_limit_down": False,
            "suspend_reason": None,
            "st_type": None,
        },
    ]


def generate(root: Path) -> None:
    pa, pq = _require_pyarrow()
    out = root / "data_snapshot"
    out.mkdir(parents=True, exist_ok=True)

    for symbol, flags in STOCKS.items():
        pq.write_table(
            pa.Table.from_pylist(_daily_rows(symbol, float(flags["base"]))),
            out / f"{symbol}_daily.parquet",
            compression="snappy",
        )
        pq.write_table(
            pa.Table.from_pylist(_status_rows(symbol, flags)),
            out / f"{symbol}_status.parquet",
            compression="snappy",
        )


if __name__ == "__main__":
    generate(Path("tests") / "golden_cases")
    print("Generated Golden Case Parquet snapshots")
