from datetime import date, timedelta
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
from collections import Counter

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from backend.services.formal_pit_partition_adapter import FormalPITPartitionAdapter
from backend.services.v3_b5_comparison import ComparisonError, _FormalComparisonSource


SNAPSHOT_ID = "pims_traderlens_v2_shsz_sw2021_pit_005"
FORMAL_REL = Path("data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal")
REPO_ROOT = Path(
    os.environ.get("TRADERLENS_SOURCE_ROOT", Path(__file__).parents[1])
).resolve()


def _fixture_adapter(root: Path, *, calendar_artifact_dir: Path | None = None) -> FormalPITPartitionAdapter:
    formal_root = root / FORMAL_REL
    return FormalPITPartitionAdapter.for_test_fixture(
        root,
        formal_input_root=formal_root,
        stock_basic_root=formal_root / "stock_basic",
        calendar_artifact_dir=calendar_artifact_dir,
    )


def _write_table(path: Path, rows: list[dict], schema: pa.Schema | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pylist(rows, schema=schema)
    pq.write_table(table, path)


def _write_partition(formal: Path, interface: str, day: date, rows: list[dict], schema: pa.Schema | None = None) -> None:
    _write_table(formal / interface / f"trade_date={day:%Y%m%d}" / "part.parquet", rows, schema)


def _build_fixture(tmp_path: Path) -> Path:
    formal = tmp_path / FORMAL_REL
    days = [date(2024, 1, 1) + timedelta(days=i) for i in range(5)]
    calendar_rows = [
        {"exchange": exchange, "cal_date": f"{day:%Y%m%d}", "is_open": 1}
        for day in days
        for exchange in ("SSE", "SZSE")
    ]
    _write_table(formal / "trade_cal" / "part.parquet", calendar_rows)

    stock_schema = pa.schema([
        pa.field("ts_code", pa.string()),
        pa.field("list_date", pa.string()),
        pa.field("delist_date", pa.string()),
    ])
    _write_table(
        formal / "stock_basic/list_status=L/part.parquet",
        [
            {"ts_code": "000001.SZ", "list_date": "20240101", "delist_date": None},
            {"ts_code": "000002.SZ", "list_date": "20240101", "delist_date": None},
        ],
        stock_schema,
    )
    for status in ("D", "P"):
        _write_table(formal / f"stock_basic/list_status={status}/part.parquet", [], stock_schema)

    membership_dir = tmp_path / "data/pit/pit_membership_snapshots" / SNAPSHOT_ID
    membership_rows = [
        {"symbol": "000001.SZ", "effective_from": date(2024, 1, 1), "effective_to": date(2024, 1, 3), "source": "fixture", "snapshot_id": SNAPSHOT_ID},
        {"symbol": "000002.SZ", "effective_from": date(2024, 1, 3), "effective_to": None, "source": "fixture", "snapshot_id": SNAPSHOT_ID},
    ]
    records_path = membership_dir / "records.parquet"
    _write_table(records_path, membership_rows)
    records_sha = sha256(records_path.read_bytes()).hexdigest()
    manifest = {"snapshot_id": SNAPSHOT_ID, "records_parquet_sha256": records_sha, "frozen": True}
    _write_table  # keep the fixture's writer visible at the data boundary
    membership_dir.mkdir(parents=True, exist_ok=True)
    (membership_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (membership_dir / "records.parquet.sha256").write_text(f"{records_sha}  records.parquet\n", encoding="utf-8")
    manifest_sha = sha256((membership_dir / "manifest.json").read_bytes()).hexdigest()
    (membership_dir / "manifest.json.sha256").write_text(f"{manifest_sha}  manifest.json\n", encoding="utf-8")

    daily_schema = pa.schema([
        pa.field("ts_code", pa.string()), pa.field("trade_date", pa.string()),
        pa.field("open", pa.float64()), pa.field("high", pa.float64()),
        pa.field("low", pa.float64()), pa.field("close", pa.float64()),
        pa.field("amount", pa.float64()), pa.field("vol", pa.float64()),
    ])
    adj_schema = pa.schema([pa.field("ts_code", pa.string()), pa.field("adj_factor", pa.float64())])
    suspend_schema = pa.schema([
        pa.field("ts_code", pa.string()), pa.field("trade_date", pa.string()), pa.field("suspend_type", pa.string())
    ])
    st_schema = pa.schema([
        pa.field("ts_code", pa.string()), pa.field("trade_date", pa.string()), pa.field("type_name", pa.string()), pa.field("name", pa.string())
    ])
    limit_schema = pa.schema([
        pa.field("ts_code", pa.string()), pa.field("up_limit", pa.float64()), pa.field("down_limit", pa.float64())
    ])
    for index, day in enumerate(days):
        daily = [
            {"ts_code": symbol, "trade_date": f"{day:%Y%m%d}", "open": 10.0 + index, "high": 11.0 + index, "low": 9.0 + index, "close": 10.5 + index, "amount": 100000.0, "vol": 10000.0}
            for symbol in ("000001.SZ", "000002.SZ")
        ]
        _write_partition(formal, "daily", day, daily, daily_schema)
        _write_partition(formal, "adj_factor", day, [{"ts_code": symbol, "adj_factor": 1.0} for symbol in ("000001.SZ", "000002.SZ")], adj_schema)
        _write_partition(formal, "suspend_d", day, [], suspend_schema)
        _write_partition(formal, "stock_st", day, [], st_schema)
        _write_partition(formal, "stk_limit", day, [{"ts_code": symbol, "up_limit": 100.0, "down_limit": 0.1} for symbol in ("000001.SZ", "000002.SZ")], limit_schema)
    calendar_source = REPO_ROOT / "data/pit/shsz_common_trade_calendars/shsz_common_trade_calendar_v1"
    shutil.copytree(calendar_source, tmp_path / "data/pit/shsz_common_trade_calendars/shsz_common_trade_calendar_v1")
    return tmp_path


SUSPEND_SCHEMA = pa.schema([
    pa.field("ts_code", pa.string()),
    pa.field("trade_date", pa.string()),
    pa.field("suspend_timing", pa.string()),
    pa.field("suspend_type", pa.string()),
])


def _rewrite_suspend(root: Path, day: date, rows: list[dict]) -> None:
    _write_partition(root / "data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal", "suspend_d", day, rows, SUSPEND_SCHEMA)


def _remove_daily_symbol(root: Path, day: date, symbol: str) -> None:
    path = root / FORMAL_REL / f"daily/trade_date={day:%Y%m%d}/part.parquet"
    schema = pq.read_schema(path)
    rows = [row for row in pq.read_table(path).to_pylist() if row["ts_code"] != symbol]
    pq.write_table(pa.Table.from_pylist(rows, schema=schema), path)


def _rewrite_daily_symbol(root: Path, day: date, symbol: str, **updates: float) -> None:
    path = root / FORMAL_REL / f"daily/trade_date={day:%Y%m%d}/part.parquet"
    schema = pq.read_schema(path)
    rows = pq.read_table(path).to_pylist()
    for row in rows:
        if row["ts_code"] == symbol:
            row.update(updates)
    pq.write_table(pa.Table.from_pylist(rows, schema=schema), path)


def _comparison_source(root: Path, coverage: dict | None = None) -> _FormalComparisonSource:
    return _FormalComparisonSource(
        _fixture_adapter(root),
        {},
        lifecycle={"000001.SZ": ("20240101", None)},
        coverage_unavailable=coverage or {},
    )


def _qualified_coverage(day: date) -> dict:
    return {
        (day.strftime("%Y%m%d"), "000001.SZ"): {
            "execution_date": day.strftime("%Y%m%d"),
            "as_of_date": "20240102",
            "symbol": "000001.SZ",
            "status": "unavailable",
            "reason": "required_history_missing",
            "missing_fields": ["daily.close"],
        }
    }


def test_v3_adapter_reads_pit_membership_and_common_bars(tmp_path: Path) -> None:
    adapter = _fixture_adapter(_build_fixture(tmp_path))

    assert adapter.symbols_as_of(date(2024, 1, 2)) == ("000001.SZ",)
    assert adapter.symbols_as_of(date(2024, 1, 3)) == ("000002.SZ",)
    assert adapter.symbols_as_of(date(2024, 1, 4)) == ("000002.SZ",)
    assert adapter.common_trading_dates(date(2024, 1, 2), date(2024, 1, 4)) == (
        date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)
    )

    bars = adapter.get_daily_bars("000001.SZ", date(2024, 1, 3), 2)
    assert [bar.date for bar in bars] == [date(2024, 1, 2), date(2024, 1, 3)]
    assert adapter.get_bar("000001.SZ", date(2024, 1, 3)).close == bars[-1].close
    status = adapter.get_status("000001.SZ", date(2024, 1, 3))
    assert status.is_suspended is False


def test_v3_adapter_missing_required_partition_fails_loud(tmp_path: Path) -> None:
    root = _build_fixture(tmp_path)
    adapter = _fixture_adapter(root)
    (root / FORMAL_REL / "daily/trade_date=20240103/part.parquet").unlink()
    with pytest.raises(FileNotFoundError, match="daily.*20240103"):
        adapter.get_bar("000001.SZ", date(2024, 1, 3))


def test_v3_production_adapter_uses_verified_common_calendar() -> None:
    adapter = FormalPITPartitionAdapter(REPO_ROOT)

    dates = adapter.common_trading_dates(date(2025, 6, 27), date(2026, 3, 19))

    assert len(adapter.get_trading_dates()) == 2554
    assert len(dates) == 176
    assert dates[0] == date(2025, 6, 27)
    assert dates[-1] == date(2026, 3, 19)


def test_v3_explicit_calendar_tamper_is_rejected(tmp_path: Path) -> None:
    root = _build_fixture(tmp_path)
    calendar_dir = root / "data/pit/shsz_common_trade_calendars/shsz_common_trade_calendar_v1"
    (calendar_dir / "szse_trade_cal.parquet").write_bytes(
        (calendar_dir / "szse_trade_cal.parquet").read_bytes() + b"tamper"
    )

    with pytest.raises(ValueError, match="calendar"):
        _fixture_adapter(root, calendar_artifact_dir=calendar_dir)


def test_v3_explicit_missing_calendar_fails_without_formal_fallback(tmp_path: Path) -> None:
    root = _build_fixture(tmp_path)

    with pytest.raises((FileNotFoundError, ValueError), match="calendar"):
        _fixture_adapter(root, calendar_artifact_dir=tmp_path / "missing-calendar")


def test_formal_suspension_without_daily_returns_status_but_never_a_bar() -> None:
    adapter = FormalPITPartitionAdapter(REPO_ROOT)
    suspended_day = date(2025, 7, 31)

    status = adapter.get_status("688585.SH", suspended_day)

    assert status.is_suspended is True
    assert status.suspend_reason == "S"
    with pytest.raises(KeyError, match="688585.SH"):
        adapter.get_bar("688585.SH", suspended_day)


def test_r_plus_daily_is_resume_not_suspended_and_bar_is_usable() -> None:
    adapter = FormalPITPartitionAdapter(REPO_ROOT)

    status = adapter.get_status("300478.SZ", date(2025, 7, 2))
    bar = adapter.get_bar("300478.SZ", date(2025, 7, 2))

    assert status.is_suspended is False
    assert status.suspend_reason == "R"
    assert bar.open == 16.18
    assert bar.close == 14.98


@pytest.mark.parametrize(
    ("symbol", "day"),
    (("600930.SH", date(2025, 7, 16)), ("603056.SH", date(2026, 1, 9))),
)
def test_s_plus_nonempty_timing_and_daily_is_tradable_without_parsing(symbol: str, day: date) -> None:
    adapter = FormalPITPartitionAdapter(REPO_ROOT)

    status = adapter.get_status(symbol, day)
    bar = adapter.get_bar(symbol, day)

    assert status.is_suspended is False
    assert status.suspend_reason == "S"
    assert bar.open > 0
    assert bar.close > 0


@pytest.mark.parametrize("timing", (None, ""))
def test_s_or_p_missing_timing_with_daily_remains_suspended(tmp_path: Path, timing: str | None) -> None:
    root = _build_fixture(tmp_path)
    day = date(2024, 1, 3)
    _rewrite_suspend(root, day, [{
        "ts_code": "000001.SZ", "trade_date": f"{day:%Y%m%d}",
        "suspend_timing": timing, "suspend_type": "S",
    }])

    status = _fixture_adapter(root).get_status("000001.SZ", day)

    assert status.is_suspended is True
    assert status.suspend_reason == "S"


def test_p_plus_nonempty_timing_and_daily_is_tradable(tmp_path: Path) -> None:
    root = _build_fixture(tmp_path)
    day = date(2024, 1, 3)
    _rewrite_suspend(root, day, [{
        "ts_code": "000001.SZ", "trade_date": f"{day:%Y%m%d}",
        "suspend_timing": "13:00-13:10", "suspend_type": "P",
    }])

    adapter = _fixture_adapter(root)
    status = adapter.get_status("000001.SZ", day)

    assert status.is_suspended is False
    assert status.suspend_reason == "P"
    assert adapter.get_bar("000001.SZ", day).close == 12.5


@pytest.mark.parametrize("row_order", (("R", "S"), ("S", "R")))
def test_s_and_r_without_daily_is_deterministically_suspended(tmp_path: Path, row_order: tuple[str, str]) -> None:
    root = _build_fixture(tmp_path / "fixture")
    day = date(2024, 1, 3)
    _remove_daily_symbol(root, day, "000001.SZ")
    _rewrite_suspend(root, day, [{
        "ts_code": "000001.SZ", "trade_date": f"{day:%Y%m%d}",
        "suspend_timing": None, "suspend_type": suspend_type,
    } for suspend_type in row_order])

    status = _fixture_adapter(root).get_status("000001.SZ", day)

    assert status.is_suspended is True
    assert status.suspend_reason == "S"


def test_r_only_without_daily_is_missing_not_suspension_carry(tmp_path: Path) -> None:
    root = _build_fixture(tmp_path)
    day = date(2024, 1, 3)
    _remove_daily_symbol(root, day, "000001.SZ")
    _rewrite_suspend(root, day, [{
        "ts_code": "000001.SZ", "trade_date": f"{day:%Y%m%d}",
        "suspend_timing": None, "suspend_type": "R",
    }])

    with pytest.raises(ValueError, match="Formal status fault.*R-only"):
        _fixture_adapter(root).get_status("000001.SZ", day)


def test_invalid_daily_open_cannot_be_tradable_through_comparison_execution(tmp_path: Path) -> None:
    root = _build_fixture(tmp_path)
    day = date(2024, 1, 3)
    _rewrite_daily_symbol(root, day, "000001.SZ", open=float("nan"))
    _rewrite_suspend(root, day, [{
        "ts_code": "000001.SZ", "trade_date": f"{day:%Y%m%d}",
        "suspend_timing": None, "suspend_type": "R",
    }])

    with pytest.raises(ComparisonError, match="invalid|missing|execution"):
        _comparison_source(root).execution("000001.SZ", day)


@pytest.mark.parametrize(
    ("field", "value"),
    (("open", float("nan")), ("high", float("inf")), ("low", 0.0),
     ("close", -1.0), ("amount", 0.0), ("vol", 0.0)),
)
def test_invalid_daily_source_fields_fail_loud_in_execution_and_mark(
    tmp_path: Path, field: str, value: float
) -> None:
    root = _build_fixture(tmp_path)
    day = date(2024, 1, 3)
    _rewrite_daily_symbol(root, day, "000001.SZ", **{field: value})
    _rewrite_suspend(root, day, [{
        "ts_code": "000001.SZ", "trade_date": f"{day:%Y%m%d}",
        "suspend_timing": None, "suspend_type": "R",
    }])

    source = _comparison_source(root)
    with pytest.raises(ComparisonError, match="invalid|missing|execution|mark"):
        source.execution("000001.SZ", day)
    with pytest.raises(ComparisonError, match="invalid|missing|execution|mark"):
        source.mark("000001.SZ", day)


@pytest.mark.parametrize("field", ("amount", "vol"))
def test_non_positive_daily_amount_or_volume_cannot_be_tradable_through_comparison(
    tmp_path: Path, field: str
) -> None:
    root = _build_fixture(tmp_path)
    day = date(2024, 1, 3)
    _rewrite_daily_symbol(root, day, "000001.SZ", **{field: 0.0})
    _rewrite_suspend(root, day, [{
        "ts_code": "000001.SZ", "trade_date": f"{day:%Y%m%d}",
        "suspend_timing": None, "suspend_type": "R",
    }])

    with pytest.raises(ComparisonError, match="invalid|missing|execution"):
        _comparison_source(root).execution("000001.SZ", day)


def test_unknown_suspend_type_with_daily_is_not_formal_suspension(tmp_path: Path) -> None:
    root = _build_fixture(tmp_path)
    day = date(2024, 1, 3)
    _rewrite_suspend(root, day, [{
        "ts_code": "000001.SZ", "trade_date": f"{day:%Y%m%d}",
        "suspend_timing": None, "suspend_type": "X",
    }])

    with pytest.raises(ComparisonError, match="status|unknown|unsupported"):
        _comparison_source(root).execution("000001.SZ", day)


def test_unknown_suspend_type_without_daily_is_not_suspension_carry(tmp_path: Path) -> None:
    root = _build_fixture(tmp_path)
    day = date(2024, 1, 3)
    _remove_daily_symbol(root, day, "000001.SZ")
    _rewrite_suspend(root, day, [{
        "ts_code": "000001.SZ", "trade_date": f"{day:%Y%m%d}",
        "suspend_timing": None, "suspend_type": "X",
    }])

    with pytest.raises(ComparisonError, match="status|unknown|unsupported"):
        _comparison_source(root).execution("000001.SZ", day, held=True)


def test_r_only_without_daily_cannot_enter_p2_mark_carry(tmp_path: Path) -> None:
    root = _build_fixture(tmp_path)
    day = date(2024, 1, 3)
    _remove_daily_symbol(root, day, "000001.SZ")
    _rewrite_suspend(root, day, [{
        "ts_code": "000001.SZ", "trade_date": f"{day:%Y%m%d}",
        "suspend_timing": None, "suspend_type": "R",
    }])
    source = _comparison_source(root, _qualified_coverage(day))
    source.mark("000001.SZ", date(2024, 1, 2))

    with pytest.raises(ComparisonError, match="status|missing|suspension"):
        source.mark("000001.SZ", day)
    with pytest.raises(ComparisonError, match="status|missing|suspension"):
        source.execution("000001.SZ", day, held=True)


def test_r_only_without_daily_cannot_enter_p2_execution_carry(tmp_path: Path) -> None:
    root = _build_fixture(tmp_path)
    day = date(2024, 1, 3)
    _remove_daily_symbol(root, day, "000001.SZ")
    _rewrite_suspend(root, day, [{
        "ts_code": "000001.SZ", "trade_date": f"{day:%Y%m%d}",
        "suspend_timing": None, "suspend_type": "R",
    }])
    source = _comparison_source(root, _qualified_coverage(day))
    source.mark("000001.SZ", date(2024, 1, 2))

    with pytest.raises(ComparisonError, match="status|missing|suspension"):
        source.execution("000001.SZ", day, held=True)


def test_plain_missing_daily_with_qualified_coverage_remains_p2(tmp_path: Path) -> None:
    root = _build_fixture(tmp_path)
    day = date(2024, 1, 3)
    _remove_daily_symbol(root, day, "000001.SZ")
    source = _comparison_source(root, _qualified_coverage(day))
    source.mark("000001.SZ", date(2024, 1, 2))

    assert source.mark("000001.SZ", day) == (11.5, "unavailable_mark_carry")
    assert source.execution("000001.SZ", day, held=True) == (
        11.5, False, "unavailable_mark_carry_locked"
    )


def test_suspension_without_daily_keeps_p1_over_qualified_coverage(tmp_path: Path) -> None:
    root = _build_fixture(tmp_path)
    day = date(2024, 1, 3)
    _remove_daily_symbol(root, day, "000001.SZ")
    _rewrite_suspend(root, day, [{
        "ts_code": "000001.SZ", "trade_date": f"{day:%Y%m%d}",
        "suspend_timing": None, "suspend_type": "S",
    }])
    source = _comparison_source(root, _qualified_coverage(day))
    source.mark("000001.SZ", date(2024, 1, 2))

    assert source.mark("000001.SZ", day) == (11.5, "suspended_carry")
    assert source.execution("000001.SZ", day, held=True) == (
        None, False, "suspended"
    )


def test_missing_daily_without_suspension_evidence_still_fails_loud(tmp_path: Path) -> None:
    root = _build_fixture(tmp_path)
    day = date(2024, 1, 3)
    daily_path = root / FORMAL_REL / "daily/trade_date=20240103/part.parquet"
    rows = [row for row in pq.read_table(daily_path).to_pylist() if row["ts_code"] == "000001.SZ"]
    pq.write_table(pa.Table.from_pylist(rows, schema=pq.read_schema(daily_path)), daily_path)
    adapter = _fixture_adapter(root)

    with pytest.raises(KeyError, match="000002.SZ"):
        adapter.get_status("000002.SZ", day)


def test_partition_reads_are_shared_across_symbols_for_one_date(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _build_fixture(tmp_path)
    reads: list[str] = []
    original_parquet_file = pq.ParquetFile

    def counted_parquet_file(path, *args, **kwargs):
        parquet_file = original_parquet_file(path, *args, **kwargs)
        original_read = parquet_file.read

        def counted_read(*read_args, **read_kwargs):
            reads.append(str(path))
            return original_read(*read_args, **read_kwargs)

        parquet_file.read = counted_read
        return parquet_file

    monkeypatch.setattr(pq, "ParquetFile", counted_parquet_file)
    adapter = _fixture_adapter(root)
    adapter.get_bar("000001.SZ", date(2024, 1, 3))
    adapter.get_bar("000002.SZ", date(2024, 1, 3))

    counts = Counter(reads)
    assert counts[str(root / FORMAL_REL / "daily/trade_date=20240103/part.parquet")] == 1
    assert counts[str(root / FORMAL_REL / "adj_factor/trade_date=20240103/part.parquet")] == 1


def test_derived_liquidity_reuses_per_day_result_without_reentering_builder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _build_fixture(tmp_path)
    adapter = _fixture_adapter(root)
    calls = 0

    def counted(day):
        nonlocal calls
        calls += 1
        result = {
            "000001.SZ": ("qualified", 100_000_000.0),
            "000002.SZ": ("qualified", 100_000_000.0),
        }
        adapter._liquidity_cache[day] = result
        return result

    monkeypatch.setattr(adapter, "_prepare_liquidity", counted)
    adapter._stock_basic["000001.SZ"] = (date(2023, 1, 1), None)
    adapter._stock_basic["000002.SZ"] = (date(2023, 1, 1), None)
    adapter._common_trading_dates = tuple(date(2023, 12, 1) + timedelta(days=index) for index in range(40))
    day = date(2024, 1, 3)
    assert adapter.derive_liquidity("000001.SZ", day)["status"] == "qualified"
    assert adapter.derive_liquidity("000002.SZ", day)["status"] == "qualified"
    assert calls == 1


def test_batch_endpoint_reads_four_exact_partitions_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _build_fixture(tmp_path)
    reads: list[str] = []
    original_parquet_file = pq.ParquetFile

    def counted_parquet_file(path, *args, **kwargs):
        parquet_file = original_parquet_file(path, *args, **kwargs)
        original_read = parquet_file.read

        def counted_read(*read_args, **read_kwargs):
            reads.append(str(path))
            return original_read(*read_args, **read_kwargs)

        parquet_file.read = counted_read
        return parquet_file

    monkeypatch.setattr(pq, "ParquetFile", counted_parquet_file)
    adapter = _fixture_adapter(root)
    endpoints = adapter.get_adjusted_momentum_endpoints(
        ("000001.SZ", "000002.SZ"), date(2024, 1, 2), date(2024, 1, 4)
    )

    assert set(endpoints) == {"000001.SZ", "000002.SZ"}
    assert all(pair[0].date == date(2024, 1, 2) and pair[1].date == date(2024, 1, 4) for pair in endpoints.values())
    counts = Counter(reads)
    expected = (
        root / FORMAL_REL / "daily/trade_date=20240102/part.parquet",
        root / FORMAL_REL / "adj_factor/trade_date=20240102/part.parquet",
        root / FORMAL_REL / "daily/trade_date=20240104/part.parquet",
        root / FORMAL_REL / "adj_factor/trade_date=20240104/part.parquet",
    )
    assert all(counts[str(path)] == 1 for path in expected)
    assert sum(counts[str(path)] for path in expected) == 4


def test_formal_runtime_hashes_each_partition_against_b3_input_index(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.services.v3_b5_bundle import resolve_formal_input_bindings

    bindings = resolve_formal_input_bindings(REPO_ROOT)
    adapter = FormalPITPartitionAdapter(REPO_ROOT, formal_input_binding=bindings)
    day = date(2026, 3, 20)
    formal_root_rel = bindings["b3_execution_input"]["formal_input_root_repo_relative"]

    for interface in ("daily", "adj_factor"):
        expected_rel = f"{formal_root_rel}/{interface}/trade_date={day:%Y%m%d}/part.parquet"
        expected_path = REPO_ROOT / Path(*expected_rel.split("/"))
        rows = adapter._read_partition(interface, day)
        assert isinstance(rows, dict)
        assert adapter._indexed_input_partition_sha256[expected_rel] == sha256(expected_path.read_bytes()).hexdigest()

    monkeypatch.setattr(adapter, "_sha256_bytes", lambda _raw: "0" * 64)
    with pytest.raises(ValueError, match="B3 indexed partition hash mismatch"):
        adapter._read_partition("daily", date(2026, 3, 23))
