from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import yaml

from scripts.market_regime_bounded_replay import (
    publish_index_source,
    publish_bounded_qualification,
    resolve_market_regime_gap,
    run_bounded_replay,
    verify_index_source,
)
from scripts.verify_market_regime_bounded import verify_bounded_qualification_independently


def _write(path: Path, rows: list[dict], schema: pa.Schema | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pylist(rows, schema=schema)
    pq.write_table(table, path)


def _empty_schema(*fields: tuple[str, pa.DataType]) -> pa.Schema:
    return pa.schema([pa.field(name, dtype) for name, dtype in fields])


def _formal_fixture(root: Path) -> list[str]:
    dates = []
    current = date(2017, 7, 20)
    while current <= date(2017, 9, 4):
        if current.weekday() < 5:
            dates.append(current.strftime("%Y%m%d"))
        current += timedelta(days=1)
    _write(
        root / "trade_cal" / "part.parquet",
        [{"cal_date": d, "is_open": 1} for d in dates],
    )
    lifecycle = [
        {"ts_code": "000001.SZ", "list_date": "19910403", "delist_date": None},
        {"ts_code": "600000.SH", "list_date": "19991110", "delist_date": None},
    ]
    _write(root / "stock_basic" / "list_status=L" / "part.parquet", lifecycle)
    _write(
        root / "stock_basic" / "list_status=D" / "part.parquet",
        [],
        _empty_schema(
            ("ts_code", pa.string()), ("list_date", pa.string()), ("delist_date", pa.string())
        ),
    )
    _write(
        root / "stock_basic" / "list_status=P" / "part.parquet",
        [],
        _empty_schema(
            ("ts_code", pa.string()), ("list_date", pa.string()), ("delist_date", pa.string())
        ),
    )
    empty_st = _empty_schema(
        ("ts_code", pa.string()), ("trade_date", pa.string()), ("type", pa.string())
    )
    empty_suspend = _empty_schema(
        ("ts_code", pa.string()), ("trade_date", pa.string()), ("suspend_type", pa.string())
    )
    for d in dates:
        rows = [
            {
                "ts_code": "000001.SZ",
                "trade_date": d,
                "pct_chg": 0.0,
                "amount": 100.0,
            },
            {
                "ts_code": "600000.SH",
                "trade_date": d,
                "pct_chg": 0.0,
                "amount": 100.0,
            },
        ]
        _write(root / "daily" / f"trade_date={d}" / "part.parquet", rows)
        _write(root / "stock_st" / f"trade_date={d}" / "part.parquet", [], empty_st)
        _write(root / "suspend_d" / f"trade_date={d}" / "part.parquet", [], empty_suspend)
    return dates


def _config(path: Path) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "version": "1.1",
                "validation_status": "candidate",
                "candidate_rules": {
                    "extreme_breadth_selloff": {
                        "metric": "proportion_daily_pct_chg_lte_minus5",
                        "threshold_gt": 0.80,
                    },
                    "structural_breakdown_1d": {
                        "metric": "index_000300_SH_daily_return",
                        "threshold_lte": -0.05,
                    },
                    "structural_breakdown_5d": {
                        "metric": "index_000300_SH_5d_compounded_return",
                        "threshold_lte": -0.10,
                    },
                    "liquidity_exhaustion": {
                        "metric": "all_a_share_amount_vs_30d_mean",
                        "threshold_lt": 0.30,
                    },
                },
                "stress_windows": [{"id": "B", "start": "20170901", "end": "20170904"}],
                "normal_window": {"start": "20170901", "end": "20170904"},
                "zero_gap_rule": True,
                "normal_window_block_ratio_max": 0.05,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def test_index_source_write_once_and_tamper_is_rejected(tmp_path: Path) -> None:
    rows = [
        {"ts_code": "000300.SH", "trade_date": "20170828", "close": 100.0, "pre_close": 99.0},
        {"ts_code": "000300.SH", "trade_date": "20170901", "close": 100.0, "pre_close": 100.0},
    ]
    requests = [{"api": "index_daily", "ts_code": "000300.SH", "start_date": "20170828", "end_date": "20170901"}]
    first = publish_index_source(rows, requests, tmp_path / "sources")
    assert first["status"] == "published"
    assert verify_index_source(Path(first["path"]))["status"] == "verified"
    second = publish_index_source(rows, requests, tmp_path / "sources")
    assert second["status"] == "already_published"
    parquet = Path(first["path"]) / "index_daily_000300.parquet"
    parquet.write_bytes(parquet.read_bytes() + b"tamper")
    with pytest.raises(ValueError, match="source artifact"):
        verify_index_source(Path(first["path"]))


def test_bounded_replay_consumes_exact_windows_and_enforces_zero_gap(tmp_path: Path) -> None:
    formal = tmp_path / "formal"
    dates = _formal_fixture(formal)
    index_rows = []
    close = 100.0
    for d in dates:
        index_rows.append(
            {
                "ts_code": "000300.SH",
                "trade_date": d,
                "close": close,
                "pre_close": close,
            }
        )
    source = publish_index_source(
        index_rows,
        [{"api": "index_daily", "ts_code": "000300.SH", "start_date": dates[0], "end_date": dates[-1]}],
        tmp_path / "sources",
    )
    config = tmp_path / "market_regime.yaml"
    _config(config)
    result = run_bounded_replay(config, formal, Path(source["path"]))
    assert result["status"] == "valid"
    assert result["zero_gap"] is True
    assert result["windows"]["B"]["trading_day_count"] == 2
    assert result["windows"]["B"]["blocked_day_count"] == 0
    assert result["windows"]["normal"]["normal_block_ratio"] == 0.0


def test_v12_replay_rejects_stress_window_without_trigger(tmp_path: Path) -> None:
    formal = tmp_path / "formal"
    dates = _formal_fixture(formal)
    source = publish_index_source(
        [{"ts_code": "000300.SH", "trade_date": day, "close": 100.0, "pre_close": 100.0} for day in dates],
        [{"api": "index_daily", "ts_code": "000300.SH", "start_date": dates[0], "end_date": dates[-1]}],
        tmp_path / "sources",
    )
    config = tmp_path / "market_regime_v12.yaml"
    _config(config)
    payload = yaml.safe_load(config.read_text(encoding="utf-8"))
    payload["version"] = "1.2"
    payload["stress_window_block_day_min"] = 1
    config.write_text(yaml.safe_dump(payload, sort_keys=True), encoding="utf-8")

    result = run_bounded_replay(config, formal, Path(source["path"]))

    assert result["windows"]["B"]["blocked_day_count"] == 0
    assert result["status"] == "not_qualified"
    with pytest.raises(ValueError, match="stress-window minimum"):
        publish_bounded_qualification(result, tmp_path / "qualifications")


def test_independent_verifier_recomputes_source_and_rejects_report_tamper(tmp_path: Path) -> None:
    formal = tmp_path / "formal"
    dates = _formal_fixture(formal)
    source = publish_index_source(
        [{"ts_code": "000300.SH", "trade_date": day, "close": 100.0, "pre_close": 100.0} for day in dates],
        [{"api": "index_daily", "ts_code": "000300.SH", "start_date": dates[0], "end_date": dates[-1]}],
        tmp_path / "sources",
    )
    config = tmp_path / "market_regime.yaml"
    _config(config)
    result = run_bounded_replay(config, formal, Path(source["path"]))
    qualification = publish_bounded_qualification(result, tmp_path / "qualifications")
    assert verify_bounded_qualification_independently(Path(qualification["path"]))["status"] == "verified"
    report_path = Path(qualification["path"]) / "validation_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["windows"]["B"]["blocked_day_count"] = 1
    report_path.write_text(json.dumps(report, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    report_path.with_name(report_path.name + ".sha256").write_text(
        f"{__import__('hashlib').sha256(report_path.read_bytes()).hexdigest()}  {report_path.name}\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="validation semantic hash mismatch"):
        verify_bounded_qualification_independently(Path(qualification["path"]))


def test_market_regime_evidence_is_exact_missing_only_and_daily_precedes_it() -> None:
    assert resolve_market_regime_gap("000001.SZ", "20200309", {"amount": 1.0}, None)["status"] == "daily"
    assert resolve_market_regime_gap("000001.SZ", "20200309", {"amount": 1.0}, None, [{"suspend_type": "R"}])["status"] == "daily"
    assert resolve_market_regime_gap("000001.SZ", "20200309", None, None, [{"suspend_type": "S"}])["status"] == "non_tradable"
    with pytest.raises(ValueError, match="conflicts with daily"):
        resolve_market_regime_gap("000001.SZ", "20200309", {"amount": 1.0}, {"qualified": True})
    assert resolve_market_regime_gap("000001.SZ", "20200309", None, {"qualified": True})["status"] == "non_tradable"
    with pytest.raises(ValueError, match="missing without authorized evidence"):
        resolve_market_regime_gap("000001.SZ", "20200309", None, None)


def test_independent_qualification_verifier_consumes_successor_evidence() -> None:
    qualification = Path("data/pit/market_regime_qualifications/44c9c152bb17e970")
    assert verify_bounded_qualification_independently(qualification)["status"] == "verified"
