from __future__ import annotations

from datetime import date, timedelta
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import yaml

from scripts.diagnose_market_regime_v12_daily_gaps import (
    _validate_resolution_arithmetic,
    diagnose,
)


def _write(path: Path, rows: list[dict], schema: pa.Schema | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows, schema=schema), path)


def _empty_schema(*fields: tuple[str, pa.DataType]) -> pa.Schema:
    return pa.schema([pa.field(name, dtype) for name, dtype in fields])


def _fixture(root: Path, config_path: Path) -> None:
    days = []
    current = date(2017, 7, 21)
    while current <= date(2017, 9, 1):
        if current.weekday() < 5:
            days.append(current.strftime("%Y%m%d"))
        current += timedelta(days=1)
    _write(root / "trade_cal" / "part.parquet", [{"cal_date": day, "is_open": 1} for day in days])
    lifecycle_schema = _empty_schema(
        ("ts_code", pa.string()), ("list_date", pa.string()), ("delist_date", pa.string())
    )
    lifecycle = [{"ts_code": "000001.SZ", "list_date": "20100101", "delist_date": None}]
    _write(root / "stock_basic" / "list_status=L" / "part.parquet", lifecycle)
    _write(root / "stock_basic" / "list_status=D" / "part.parquet", [], lifecycle_schema)
    _write(root / "stock_basic" / "list_status=P" / "part.parquet", [], lifecycle_schema)
    daily_schema = _empty_schema(
        ("ts_code", pa.string()), ("trade_date", pa.string()), ("pct_chg", pa.float64()), ("amount", pa.float64())
    )
    st_schema = _empty_schema(("ts_code", pa.string()), ("trade_date", pa.string()), ("type", pa.string()))
    suspend_schema = _empty_schema(
        ("ts_code", pa.string()), ("trade_date", pa.string()), ("suspend_type", pa.string()), ("suspend_timing", pa.string())
    )
    for day in days:
        _write(root / "daily" / f"trade_date={day}" / "part.parquet", [], daily_schema)
        _write(root / "stock_st" / f"trade_date={day}" / "part.parquet", [], st_schema)
        _write(
            root / "suspend_d" / f"trade_date={day}" / "part.parquet",
            [{"ts_code": "000001.SZ", "trade_date": day, "suspend_type": "S", "suspend_timing": None}],
            suspend_schema,
        )
    config_path.write_text(
        yaml.safe_dump(
            {
                "version": "1.2",
                "validation_status": "candidate",
                "candidate_rules": {
                    "extreme_breadth_selloff": {"threshold_gt": 0.80},
                    "structural_breakdown_1d": {"threshold_lte": -0.05},
                    "structural_breakdown_5d": {"threshold_lte": -0.10},
                    "liquidity_exhaustion": {"threshold_lt": 0.30},
                },
                "stress_windows": [{"id": "B", "start": "2017-09-01", "end": "2017-09-01"}],
                "normal_window": {"start": "2017-09-01", "end": "2017-09-01"},
                "zero_gap_rule": True,
                "stress_window_block_day_min": 1,
                "normal_window_block_ratio_max": 0.05,
                "required_pit_inputs": ["trade_cal", "daily", "index_daily", "stock_basic", "namechange", "suspend_d"],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def test_real_diagnose_caller_excludes_formal_suspension_without_duplicate_error(tmp_path: Path) -> None:
    formal = tmp_path / "formal"
    config = tmp_path / "config.yaml"
    _fixture(formal, config)
    result = diagnose(config_path=config, formal_root=formal, output_path=tmp_path / "diagnostic.json")
    payload = json.loads((tmp_path / "diagnostic.json").read_text(encoding="utf-8"))
    assert result["gap_count"] == 0
    assert payload["resolution_counts"]["resolved_formal_suspension"] > 0
    assert payload["scan_stats"]["new_unresolved_count"] == 0


def test_true_duplicate_identity_is_still_rejected() -> None:
    duplicate = [{"symbol": "000001.SZ", "date": "20200203"}, {"symbol": "000001.SZ", "date": "20200203"}]
    with pytest.raises(ValueError, match="duplicate gap identity"):
        _validate_resolution_arithmetic(duplicate, raw_missing_daily_count=2, resolution_counts={"resolved_formal_suspension": 0, "existing_qualified_evidence": 0, "new_unresolved": 2})
