import hashlib
import json
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

SERVICE_ROOT = Path(__file__).parents[1] / "backend" / "services"
sys.path.insert(0, str(SERVICE_ROOT))

from daily_market_scout import DailyMarketScout  # noqa: E402


FORMAL_REL = Path("data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal")
CURRENT_REL = Path("data/current_market_snapshots")


def _write_verified(path, frame):
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False, engine="pyarrow")
    path.with_suffix(path.suffix + ".sha256").write_text(hashlib.sha256(path.read_bytes()).hexdigest(), encoding="ascii")


def _calendar_frame(exchange, dates):
    return pd.DataFrame({"exchange": exchange, "cal_date": dates, "is_open": [1] * len(dates)})


def _market_frame(symbols, day, day_index, kind, limit_symbol=None):
    rows = []
    for index, symbol in enumerate(symbols):
        base = 10.0 + index
        close = base * (1.0 + day_index * 0.002)
        if symbol == limit_symbol:
            close = 20.0
        if kind == "daily":
            rows.append({
                "ts_code": symbol,
                "trade_date": day,
                "open": close,
                "high": close * 1.01,
                "low": close * 0.99,
                "close": close,
                "pre_close": close,
                "change": 0.0,
                "pct_chg": 0.0,
                "vol": 100.0 + index,
                "amount": 1000.0 + index,
            })
        elif kind == "adj_factor":
            rows.append({"ts_code": symbol, "trade_date": day, "adj_factor": 1.0})
        elif kind == "stk_limit":
            up = close if symbol == limit_symbol else close * 1.1
            rows.append({"trade_date": day, "ts_code": symbol, "up_limit": up, "down_limit": close * 0.9})
    return pd.DataFrame(rows)


def build_fixture(tmp_path, valid_count=4, *, tamper_manifest=False, gaps=None, partial=False):
    repo = Path(tmp_path)
    formal = repo / FORMAL_REL
    current = repo / CURRENT_REL
    formal_dates = [(date(2026, 5, 11) + timedelta(days=i)).strftime("%Y%m%d") for i in range(61)]
    current_dates = ["20260711", "20260712"]
    all_dates = formal_dates + current_dates
    valid = [f"0000{10 + i:02d}.SZ" for i in range(valid_count)]
    special = ["000001.SZ", "000002.SZ", "000003.SZ", "000004.SZ", "000006.SZ", "000007.SZ"]
    daily_symbols = special + valid
    formal_symbols = ["000001.SZ", "000002.SZ", "000003.SZ", "000004.SZ"] + valid

    b3 = repo / "data/pit/b3_execution_input_packages/b3eip_traderlens_v2_shsz_pit_001/inputs/trade_cal/part.parquet"
    szse = repo / "data/pit/shsz_common_trade_calendars/shsz_common_trade_calendar_v1/szse_trade_cal.parquet"
    _write_verified(b3, _calendar_frame("SSE", formal_dates))
    _write_verified(szse, _calendar_frame("SZSE", all_dates))

    stock_columns = ["ts_code", "symbol", "name", "market", "exchange", "list_status", "list_date", "delist_date"]
    stock_rows = []
    for symbol in ["000001.SZ", "000002.SZ", "000003.SZ", "000004.SZ"] + valid:
        stock_rows.append({"ts_code": symbol, "symbol": symbol[:6], "name": symbol, "market": "主板", "exchange": "SZSE", "list_status": "L", "list_date": "20200101", "delist_date": None})
    stock_rows.append({"ts_code": "000006.SZ", "symbol": "000006", "name": "late", "market": "主板", "exchange": "SZSE", "list_status": "L", "list_date": "20260713", "delist_date": None})
    stock_rows.append({"ts_code": "000007.SZ", "symbol": "000007", "name": "short", "market": "主板", "exchange": "SZSE", "list_status": "L", "list_date": "20260710", "delist_date": None})
    stock_frame = pd.DataFrame(stock_rows, columns=stock_columns)
    _write_verified(formal / "stock_basic/list_status=L/part.parquet", stock_frame)
    _write_verified(formal / "stock_basic/list_status=D/part.parquet", pd.DataFrame(columns=stock_columns))
    _write_verified(formal / "stock_basic/list_status=P/part.parquet", pd.DataFrame(columns=stock_columns))

    for day_index, day in enumerate(formal_dates):
        _write_verified(formal / f"daily/trade_date={day}/part.parquet", _market_frame(formal_symbols, day, day_index, "daily", "000002.SZ"))
        _write_verified(formal / f"adj_factor/trade_date={day}/part.parquet", _market_frame(formal_symbols, day, day_index, "adj_factor"))
        _write_verified(formal / f"suspend_d/trade_date={day}/part.parquet", pd.DataFrame(columns=["ts_code", "trade_date", "suspend_timing", "suspend_type"]))
        _write_verified(formal / f"stk_limit/trade_date={day}/part.parquet", _market_frame(formal_symbols, day, day_index, "stk_limit", "000002.SZ"))

    manifest_files = []
    for day_index, day in enumerate(current_dates, start=len(formal_dates)):
        for dataset in ("daily", "adj_factor", "suspend_d", "stk_limit"):
            frame = _market_frame(daily_symbols, day, day_index, dataset, "000002.SZ") if dataset != "suspend_d" else pd.DataFrame([{"ts_code": "000004.SZ", "trade_date": day, "suspend_timing": "09:30", "suspend_type": "停牌"}] if day == "20260712" else [], columns=["ts_code", "trade_date", "suspend_timing", "suspend_type"])
            path = current / dataset / f"trade_date={day}" / "part.parquet"
            _write_verified(path, frame)
            manifest_files.append(path)
    stock_st = pd.DataFrame([{"ts_code": "000003.SZ", "name": "ST Test", "trade_date": "20260712", "type": "ST", "type_name": "ST"}], columns=["ts_code", "name", "trade_date", "type", "type_name"])
    stock_st_path = current / "as_of_date=2026-07-12/state/stock_st.parquet"
    _write_verified(stock_st_path, stock_st)
    manifest_files.append(stock_st_path)

    manifest = {
        "schema_version": "current_incremental_snapshot_v1",
        "snapshot_type": "operational_current_market",
        "as_of_date": "2026-07-12",
        "quality_status": "ok",
        "gaps": gaps or [],
        "common_trading_dates": current_dates,
        "files": [
            {"path": path.relative_to(repo).as_posix(), "size": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            for path in manifest_files
        ],
    }
    manifest_path = current / "as_of_date=2026-07-12/manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    if tamper_manifest:
        manifest["files"][0]["sha256"] = "0" * 64
        manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    if partial:
        (current / "daily/trade_date=20260712/part.parquet.partial").write_bytes(b"partial")
    return repo


def test_cross_boundary_scan_filters_and_contract():
    result = DailyMarketScout(build_fixture(Path(tempfile.mkdtemp(prefix="scout_fixture_")))).scan()
    assert result["status"] == "ok"
    assert result["as_of_date"] == "2026-07-12"
    assert result["candidate_is_signal"] is False
    assert result["industry_breadth_status"] == "unknown"
    assert result["candidate_count"] > 0
    symbols = {item["symbol"] for item in result["candidates"]}
    assert "000003.SZ" not in symbols
    assert "000004.SZ" not in symbols
    assert "000006.SZ" not in symbols
    assert "000005.SZ" not in symbols
    limit = next(item for item in result["candidates"] if item["symbol"] == "000002.SZ")
    assert limit["status"] == "watch"
    assert "limit_reached" in limit["soft_risks"]
    assert set(limit["features"]) == {"medium_relative_strength", "short_trend", "liquidity", "volatility"}


def test_fixed_rank_tie_break_and_maximum_twenty():
    result = DailyMarketScout(build_fixture(Path(tempfile.mkdtemp(prefix="scout_fixture_")), valid_count=30)).scan()
    assert result["status"] == "ok"
    assert result["candidate_count"] == 20
    ordered = [item["symbol"] for item in result["candidates"]]
    assert ordered == sorted(ordered, key=lambda symbol: (-next(item["score"] for item in result["candidates"] if item["symbol"] == symbol), symbol))
    assert all(0.0 <= item["score"] <= 1.0 for item in result["candidates"])


def test_insufficient_history_is_local_exclusion():
    result = DailyMarketScout(build_fixture(Path(tempfile.mkdtemp(prefix="scout_fixture_")))).scan()
    assert result["status"] == "ok"
    assert "000007.SZ" not in {item["symbol"] for item in result["candidates"]}
    assert result["excluded_counts"].get("insufficient_history", 0) >= 1


def test_duplicate_suspend_records_mean_suspended_once_not_global_data_failure():
    repo = build_fixture(Path(tempfile.mkdtemp(prefix="scout_fixture_")))
    path = repo / FORMAL_REL / "suspend_d/trade_date=20260601/part.parquet"
    _write_verified(path, pd.DataFrame([
        {"ts_code": "000010.SZ", "trade_date": "20260601", "suspend_timing": "09:30", "suspend_type": "盘中停牌"},
        {"ts_code": "000010.SZ", "trade_date": "20260601", "suspend_timing": "10:30", "suspend_type": "继续停牌"},
    ]))
    result = DailyMarketScout(repo).scan()
    assert result["status"] == "ok"
    assert "000010.SZ" in {item["symbol"] for item in result["candidates"]}


def test_scan_preserves_parity_without_rowwise_dataframe_iteration(monkeypatch):
    repo = build_fixture(Path(tempfile.mkdtemp(prefix="scout_fixture_")))

    def forbidden_iterrows(_frame):
        raise AssertionError("row-wise dataframe iteration is outside the scan budget")

    monkeypatch.setattr(pd.DataFrame, "iterrows", forbidden_iterrows)
    result = DailyMarketScout(repo).scan()
    assert result["status"] == "ok"
    assert result["candidate_count"] == 6
    assert {item["symbol"] for item in result["candidates"]} == {
        "000001.SZ",
        "000002.SZ",
        "000010.SZ",
        "000011.SZ",
        "000012.SZ",
        "000013.SZ",
    }


def test_manifest_hash_gap_and_partial_errors_are_global_hard_blocks():
    for kwargs in ({"tamper_manifest": True}, {"gaps": ["20260712"]}, {"partial": True}):
        result = DailyMarketScout(build_fixture(Path(tempfile.mkdtemp(prefix="scout_fixture_")), **kwargs)).scan()
        assert result["status"] == "hard_block"
        assert result["reason"].startswith("hard_block:data_")
        assert result["candidate_count"] == 0


def test_scanner_has_no_signal_action_or_backtest_dependency():
    source = (SERVICE_ROOT / "daily_market_scout.py").read_text(encoding="utf-8")
    for forbidden in ("BacktestUniverse", "Signal", "Action", "write_text", "to_parquet"):
        assert forbidden not in source
