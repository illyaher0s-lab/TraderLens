from datetime import date, datetime, timedelta

from contracts.live_trade import (
    ExecutionObservationLog,
    ObservationPosition,
    PositionLifecycleState,
    TradeType,
)
from backend.services.position_market_monitor import PositionMarketMonitor


class FakeTushareClient:
    def __init__(self, bars_by_api):
        self.calls = []
        self.bars_by_api = list(bars_by_api)

    def query(self, api_name, **kwargs):
        self.calls.append((api_name, kwargs))
        if api_name == "trade_cal":
            return [
                {"cal_date": "20260930", "is_open": 1},
                {"cal_date": "20261008", "is_open": 1},
                {"cal_date": "20261009", "is_open": 1},
                {"cal_date": "20261010", "is_open": 0},
            ]
        result = self.bars_by_api.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def make_trade(execution_date=date(2026, 10, 8), target=3.8, stop=3.2):
    log = ExecutionObservationLog(
        log_id="log-buy",
        confirmed_action="buy",
        confirmed_execution_status="executed_full",
        confirmed_price=3.409,
        confirmed_quantity=500,
        reason="manual",
        confirmed_by_user=True,
        broker_verified=False,
        confirmed_at=datetime(2026, 10, 8, 10, 7),
        execution_date=execution_date,
        confirmed_fees=None,
        symbol="510880.SH",
        security_type="fund",
        quantity_unit="fund_share",
        trade_type=TradeType.simulated,
        record_source="autonomous_manual",
        operation_id="op-buy",
        operation_fingerprint="fingerprint",
        exit_plan_target_price=target,
        exit_plan_stop_price=stop,
    )
    position = ObservationPosition(
        position_id="pos-buy",
        source_log_id=log.log_id,
        symbol="510880.SH",
        name="上证红利ETF",
        entry_price=3.409,
        quantity=500,
        template_id="manual_unlinked",
        template_version="v1",
        entry_thesis="",
        lifecycle_state=PositionLifecycleState.open,
        opened_at=log.confirmed_at,
        closed_at=None,
        trade_type=TradeType.simulated,
        record_source="autonomous_manual",
    )
    return position, log


def test_session_calendar_uses_exchange_open_dates_and_1500_cutoff(tmp_path):
    client = FakeTushareClient([])
    monitor = PositionMarketMonitor(cache_root=tmp_path, client_factory=lambda: client)

    before_close = monitor.expected_trade_date(
        datetime(2026, 10, 8, 14, 59), client.query("trade_cal")
    )
    at_close = monitor.expected_trade_date(
        datetime(2026, 10, 8, 15, 0), client.query("trade_cal")
    )
    non_trading_day = monitor.expected_trade_date(
        datetime(2026, 10, 10, 11, 0), client.query("trade_cal")
    )

    assert before_close == date(2026, 9, 30)
    assert at_close == date(2026, 10, 8)
    assert non_trading_day == date(2026, 10, 9)


def test_trade_calendar_range_reuses_complete_cache_without_provider_call(tmp_path):
    client = FakeTushareClient([])
    monitor = PositionMarketMonitor(cache_root=tmp_path, client_factory=lambda: client)
    monitor._write_json(
        tmp_path / "sse_trade_calendar.json",
        {
            "as_of_date": "2026-10-08",
            "rows": [
                {"cal_date": "20260910", "is_open": 1},
                {"cal_date": "20260911", "is_open": 1},
            ],
        },
    )

    rows = monitor.trade_calendar_rows_between(date(2026, 9, 10), date(2026, 9, 11))

    assert rows == [
        {"cal_date": "20260910", "is_open": 1},
        {"cal_date": "20260911", "is_open": 1},
    ]
    assert client.calls == []


def test_trade_calendar_range_queries_only_requested_gap_and_keeps_daily_cache(tmp_path):
    class BoundedCalendarClient:
        def __init__(self):
            self.calls = []

        def query(self, api_name, **kwargs):
            self.calls.append((api_name, kwargs))
            start = date(int(kwargs["start_date"][:4]), int(kwargs["start_date"][4:6]), int(kwargs["start_date"][6:8]))
            end = date(int(kwargs["end_date"][:4]), int(kwargs["end_date"][4:6]), int(kwargs["end_date"][6:8]))
            return [
                {"cal_date": (start + timedelta(days=offset)).strftime("%Y%m%d"), "is_open": 1}
                for offset in range((end - start).days + 1)
            ]

    client = BoundedCalendarClient()
    monitor = PositionMarketMonitor(cache_root=tmp_path, client_factory=lambda: client)
    original_cache = {
        "as_of_date": "2026-10-08",
        "rows": [{"cal_date": "20261008", "is_open": 1}],
    }
    monitor._write_json(tmp_path / "sse_trade_calendar.json", original_cache)

    rows = monitor.trade_calendar_rows_between(date(2026, 9, 10), date(2026, 9, 11))

    assert [row["cal_date"] for row in rows] == ["20260910", "20260911"]
    assert len(client.calls) == 1
    assert client.calls[0] == (
        "trade_cal",
        {
            "exchange": "SSE",
            "start_date": "20260910",
            "end_date": "20260911",
            "fields": "cal_date,is_open",
        },
    )
    assert monitor._read_json(tmp_path / "sse_trade_calendar.json") == original_cache


def test_position_monitor_uses_real_close_and_deduplicates_same_page_session(tmp_path):
    client = FakeTushareClient([[{"ts_code": "510880.SH", "trade_date": "20260930", "close": 3.368}]])
    monitor = PositionMarketMonitor(cache_root=tmp_path, client_factory=lambda: client)
    position, log = make_trade()
    now = datetime(2026, 10, 8, 14, 0)

    first = monitor.check_positions([(position, log)], session_id="browser-session-1", now=now)
    second = monitor.check_positions([(position, log)], session_id="browser-session-1", now=now)

    assert len(client.calls) == 2
    assert [call[0] for call in client.calls] == ["trade_cal", "fund_daily"]
    item = first["items"][0]
    assert second == first
    assert item["close"] == 3.368
    assert item["trade_date"] == "2026-09-30"
    assert item["unrealized_pnl"] is None
    assert item["unrealized_pnl_state"] == "unknown_before_entry"
    assert item["alerts"] == []


def test_failed_refresh_preserves_last_close_and_does_not_retry_in_session(tmp_path):
    position, log = make_trade()
    first_client = FakeTushareClient([[{"ts_code": "510880.SH", "trade_date": "20260930", "close": 3.368}]])
    first_monitor = PositionMarketMonitor(cache_root=tmp_path, client_factory=lambda: first_client)
    first_monitor.check_positions(
        [(position, log)], session_id="session-before", now=datetime(2026, 10, 8, 14, 0)
    )

    failing_client = FakeTushareClient([RuntimeError("upstream unavailable")])
    second_monitor = PositionMarketMonitor(cache_root=tmp_path, client_factory=lambda: failing_client)
    result = second_monitor.check_positions(
        [(position, log)], session_id="session-after", now=datetime(2026, 10, 8, 15, 30)
    )
    repeated = second_monitor.check_positions(
        [(position, log)], session_id="session-after", now=datetime(2026, 10, 8, 15, 31)
    )

    item = result["items"][0]
    assert item["status"] == "stale"
    assert item["message"] == "行情未更新；显示上次成功收盘价"
    assert item["close"] == 3.368
    assert item["trade_date"] == "2026-09-30"
    assert item["alerts"] == []
    assert repeated == result
    assert [call[0] for call in failing_client.calls] == ["fund_daily"]


def test_only_fresh_close_can_trigger_personal_target_or_stop_alert(tmp_path):
    client = FakeTushareClient([[{"ts_code": "510880.SH", "trade_date": "20261008", "close": 3.9}]])
    monitor = PositionMarketMonitor(cache_root=tmp_path, client_factory=lambda: client)
    position, log = make_trade(execution_date=date(2026, 10, 7))

    result = monitor.check_positions(
        [(position, log)], session_id="browser-session-2", now=datetime(2026, 10, 8, 15, 30)
    )

    item = result["items"][0]
    assert item["status"] == "ok"
    assert item["unrealized_pnl"] == 245.5
    assert item["target_price"] == 3.8
    assert item["stop_price"] == 3.2
    assert item["alerts"] == ["target_reached"]
    assert item["distance_to_target_pct"] < 0
    assert item["distance_to_stop_pct"] > 0


def test_unknown_legacy_position_does_not_block_simulated_position_same_symbol(tmp_path):
    client = FakeTushareClient([[{"ts_code": "510880.SH", "trade_date": "20260930", "close": 3.368}]])
    monitor = PositionMarketMonitor(cache_root=tmp_path, client_factory=lambda: client)
    simulated_position, simulated_log = make_trade()
    legacy_position = simulated_position.model_copy(
        update={"position_id": "legacy-position", "trade_type": TradeType.unknown}
    )
    legacy_log = simulated_log.model_copy(
        update={"log_id": "legacy-log", "trade_type": TradeType.unknown}
    )

    result = monitor.check_positions(
        [(legacy_position, legacy_log), (simulated_position, simulated_log)],
        session_id="browser-session-legacy",
        now=datetime(2026, 10, 8, 14, 0),
    )

    by_id = {item["position_id"]: item for item in result["items"]}
    assert by_id["legacy-position"]["status"] == "unavailable"
    assert by_id["legacy-position"]["close"] is None
    assert "类型未确认" in by_id["legacy-position"]["message"]
    assert by_id["pos-buy"]["status"] == "ok"
    assert by_id["pos-buy"]["close"] == 3.368
    assert [call[0] for call in client.calls] == ["trade_cal", "fund_daily"]


def test_market_bar_requires_matching_tushare_code(tmp_path):
    client = FakeTushareClient([[
        {"trade_date": "20260930", "close": 3.4},
        {"ts_code": "510881.SH", "trade_date": "20260930", "close": 3.5},
    ]])
    monitor = PositionMarketMonitor(cache_root=tmp_path, client_factory=lambda: client)
    position, log = make_trade()

    result = monitor.check_positions(
        [(position, log)], session_id="browser-session-symbol-check", now=datetime(2026, 10, 8, 14, 0)
    )

    item = result["items"][0]
    assert item["status"] == "stale"
    assert item["close"] is None
    assert item["trade_date"] is None
