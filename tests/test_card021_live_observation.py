from datetime import date, datetime, time, timedelta
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from backend.api import card020 as card020_api
from backend.api import observations as observations_api
from backend.api.card021 import create_card021_router
from backend.api.research import create_research_app
from backend.db.live_trade import LiveTradeDB
from backend.db.research import ResearchDB
from backend.services.card021_store import Card021SnapshotStore
from backend.services.card020_vol_budget import _target_shares


SHANGHAI = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 10, 29, 17, 30, tzinfo=SHANGHAI)


class FakeMarketClient:
    def __init__(self, *, missing_adjustment_date: str | None = None,
                 dividend_ex_date: str = "20260515", apply_dividend_factor: bool = True,
                 dividend_rows: list[dict] | None = None,
                 unreported_adjustment_date: str | None = None,
                 as_of: date = NOW.date()):
        start = as_of - timedelta(days=180)
        days = [start + timedelta(days=offset) for offset in range(243)]
        self.open_dates = [day for day in days if day.weekday() < 5 and day <= as_of]
        self.calls = []
        daily_rows = [
            {
                "ts_code": "510880.SH",
                "trade_date": day.strftime("%Y%m%d"),
                "close": 3.0 + index / 10000,
                "vol": 50000.0,
            }
            for index, day in enumerate(self.open_dates)
        ]
        event_day = date.fromisoformat(f"{dividend_ex_date[:4]}-{dividend_ex_date[4:6]}-{dividend_ex_date[6:8]}")
        factor = 1.0
        adjustment_rows = []
        for index, day in enumerate(self.open_dates):
            if day == event_day and apply_dividend_factor and index > 0:
                previous_close = daily_rows[index - 1]["close"]
                factor *= previous_close / (previous_close - 0.01)
            if day.strftime("%Y%m%d") == unreported_adjustment_date:
                factor *= 1.01
            if day.strftime("%Y%m%d") != missing_adjustment_date:
                adjustment_rows.append({
                    "ts_code": "510880.SH",
                    "trade_date": day.strftime("%Y%m%d"),
                    "adj_factor": factor,
                })
        self.rows = {
            "trade_cal": [
                {"cal_date": day.strftime("%Y%m%d"), "is_open": 1 if day.weekday() < 5 else 0}
                for day in days
            ],
            "fund_daily": daily_rows,
            "fund_adj": adjustment_rows,
            "fund_div": dividend_rows if dividend_rows is not None else [
                {
                    "ts_code": "510880.SH",
                    "ann_date": "20260501",
                    "imp_anndate": "20260501",
                    "ex_date": dividend_ex_date,
                    "pay_date": "20260520",
                    "div_proc": "实施",
                    "div_cash": 0.01,
                }
            ],
        }

    def query(self, api_name, fields=None, *, single_attempt=False, **kwargs):
        self.calls.append((api_name, fields, single_attempt, kwargs))
        return self.rows[api_name]


def _router_app(client_provider, account_provider=None, snapshot_store=None):
    app = FastAPI()
    app.include_router(create_card021_router(
        client_provider,
        account_provider=account_provider,
        now_provider=lambda: NOW,
        snapshot_store=snapshot_store,
    ))
    return TestClient(app)


def test_live_observation_reuses_frozen_card020_math_and_blocks_without_account_nav():
    market = FakeMarketClient()
    account_dates = []

    def account_provider(signal_date, latest_data_date):
        account_dates.append((signal_date, latest_data_date))
        return {
            "status": "user_confirmed_position",
            "record_source": "autonomous_manual",
            "confirmed_by_user": True,
            "broker_verified": False,
            "actual_shares": 600,
            "sellable_shares": 500,
            "account_cash_at_signal_cny": None,
            "dividend_receivable_at_signal_cny": None,
        }

    response = _router_app(lambda: market, account_provider).get("/api/research/card021/510880/live-observation")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "available"
    assert payload["strategy_id"] == "510880-vol-budget-v1"
    assert payload["symbol"] == "510880.SH"
    assert payload["protocol_sha256"] == "969903D59F949DA0024448128404266C0059EA1A7BEF901B6496045BFDDE8D9D"
    assert payload["protocol_verified"] is True
    assert payload["valid_adjusted_close_count"] == 61
    assert payload["signal_date"] == "2026-09-30"
    assert payload["model_account_cash_cny"] == "5000.00"
    assert payload["model_reference_shares"] > 0
    assert payload["model_reference_shares"] % 100 == 0
    assert 0 < float(payload["target_weight_percentage"]) <= 100
    assert payload["actual_shares"] == 600
    assert payload["sellable_shares_as_of_latest_market_data"] == 500
    assert payload["actual_delta_shares"] is None
    assert payload["execution_gate"] == "blocked_missing_account_nav_or_cash"
    assert payload["action_decision"] == "not_decidable"
    assert account_dates == [(date(2026, 9, 30), date(2026, 10, 29))]
    assert payload["first_attempt_status"] == "past"
    assert payload["target_validity_status"] == "active_until_next_month_end"
    assert payload["target_valid_until"] == "2026-10-30"
    assert payload["retry_policy_status"] == "conditional_unresolved_remainder_not_tracked"
    assert payload["next_possible_attempt_date"] == "2026-10-30"
    assert {call[0] for call in market.calls} == {"trade_cal", "fund_daily", "fund_adj", "fund_div"}
    assert all(call[2] is True for call in market.calls)
    assert payload["provider_responses_received"] == ["trade_cal", "fund_daily", "fund_adj", "fund_div"]
    assert payload["dividend_source"]["coverage"] == "verified_signal_window_factor_changes"


def test_client_initialization_failure_returns_safe_unavailable_result_without_provider_queries():
    def unavailable_client():
        raise ValueError("sensitive provider configuration detail")

    response = _router_app(unavailable_client).get("/api/research/card021/510880/live-observation")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "unavailable"
    assert payload["failure_code"] == "market_client_unavailable"
    assert payload["protocol_sha256"] == "969903D59F949DA0024448128404266C0059EA1A7BEF901B6496045BFDDE8D9D"
    assert payload["protocol_verified"] is True
    assert payload["provider_call_attempted"] is False
    assert payload["provider_responses_received"] == []
    assert "sensitive provider configuration detail" not in response.text
    assert "token" not in response.text.lower()


def test_incomplete_adjustment_window_does_not_emit_a_signal():
    market = FakeMarketClient(missing_adjustment_date="20260930")

    response = _router_app(lambda: market).get("/api/research/card021/510880/live-observation")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "unavailable"
    assert payload["failure_code"] == "adjusted_close_window_incomplete"
    assert payload.get("target_weight") is None
    assert payload.get("model_reference_shares") is None


def test_market_query_failure_reports_endpoint_and_exception_type_without_raw_error():
    market = FakeMarketClient()
    original_query = market.query

    def fail_adjustments(api_name, fields=None, *, single_attempt=False, **kwargs):
        if api_name == "fund_adj":
            raise ValueError("Authorization: Bearer sensitive-value")
        return original_query(api_name, fields, single_attempt=single_attempt, **kwargs)

    market.query = fail_adjustments
    response = _router_app(lambda: market).get("/api/research/card021/510880/live-observation")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "unavailable"
    assert payload["failure_code"] == "market_source_query_failed"
    assert payload["failed_endpoint"] == "fund_adj"
    assert payload["error_type"] == "ValueError"
    assert payload["provider_responses_received"] == ["trade_cal", "fund_daily"]
    assert "sensitive-value" not in response.text


def test_protocol_hash_mismatch_blocks_all_card021_provider_calls(monkeypatch):
    market_calls = []
    account_calls = []

    def broken_protocol():
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="protocol mismatch")

    monkeypatch.setattr(card020_api, "_read_protocol", broken_protocol)

    def market_provider():
        market_calls.append(True)
        return FakeMarketClient()

    def account_provider(*_dates):
        account_calls.append(True)
        return {"status": "unverified"}

    response = _router_app(market_provider, account_provider).get(
        "/api/research/card021/510880/live-observation",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "unavailable"
    assert payload["failure_code"] == "frozen_protocol_unavailable"
    assert payload["protocol_verified"] is False
    assert payload["protocol_sha256"] == "969903D59F949DA0024448128404266C0059EA1A7BEF901B6496045BFDDE8D9D"
    assert payload["provider_call_attempted"] is False
    assert market_calls == []
    assert account_calls == []


def test_query_after_open_does_not_offer_already_passed_open_as_next_attempt():
    now = datetime.combine(date(2026, 10, 29), time(10, 0), tzinfo=SHANGHAI)
    market = FakeMarketClient()
    app = FastAPI()
    app.include_router(create_card021_router(lambda: market, now_provider=lambda: now))

    payload = TestClient(app).get("/api/research/card021/510880/live-observation").json()

    assert payload["latest_market_data_date"] == "2026-10-28"
    assert payload["next_possible_attempt_date"] == "2026-10-30"
    assert payload["market_constraints"]["volume_capacity_shares_for_next_possible_attempt"] is None
    assert payload["market_constraints"]["volume_capacity_status"] == "previous_session_not_yet_complete"


def test_first_attempt_status_changes_after_open_on_first_attempt_date():
    now = datetime.combine(date(2026, 10, 1), time(10, 0), tzinfo=SHANGHAI)
    market = FakeMarketClient(as_of=now.date())
    app = FastAPI()
    app.include_router(create_card021_router(lambda: market, now_provider=lambda: now))

    payload = TestClient(app).get("/api/research/card021/510880/live-observation").json()

    assert payload["signal_date"] == "2026-09-30"
    assert payload["earliest_attempt_after_signal_date"] == "2026-10-01"
    assert payload["first_attempt_status"] == "past"
    assert payload["retry_policy_status"] == "conditional_unresolved_remainder_not_tracked"


def test_unverified_account_provenance_does_not_expose_actual_quantity():
    market = FakeMarketClient()
    account = {
        "status": "user_confirmed_position",
        "record_source": "autonomous_manual",
        "confirmed_by_user": True,
        "broker_verified": True,
        "actual_shares": 1000,
        "sellable_shares": 1000,
    }

    payload = _router_app(lambda: market, lambda _signal, _latest: account).get(
        "/api/research/card021/510880/live-observation",
    ).json()

    assert payload["status"] == "available"
    assert payload["account_data_status"] == "provenance_unverified"
    assert payload["actual_shares"] is None
    assert payload["actual_delta_shares"] is None
    assert payload["action_decision"] == "not_decidable"


def test_research_app_reuses_the_validator_market_client():
    market = FakeMarketClient()

    class Validator:
        @property
        def tushare_client(self):
            return market

    app = create_research_app(
        db=ResearchDB(":memory:"),
        validator=Validator(),
        card021_account_provider=lambda _signal_date, _latest_date: {"status": "unverified"},
    )
    response = TestClient(app).get("/api/research/card021/510880/live-observation")

    assert response.status_code == 200
    assert response.json()["status"] == "available"
    assert len(market.calls) == 4


def test_default_account_provider_reuses_existing_user_confirmed_actual_records(monkeypatch):
    from contracts.live_trade import TradeType

    market = FakeMarketClient()
    log = SimpleNamespace(
        confirmed_by_user=True,
        broker_verified=False,
        record_source="autonomous_manual",
        trade_type=TradeType.actual,
        security_type="fund",
        quantity_unit="fund_share",
        confirmed_execution_status="executed_full",
        execution_date=date(2026, 9, 20),
    )

    class IsolatedLiveTradeDB:
        def __init__(self):
            self.log_query = None
            self.quantity_dates = []
            self.sellable_query = None

        def list_manual_position_logs(self, **kwargs):
            self.log_query = kwargs
            return [log]

        def get_position_quantity(self, **kwargs):
            self.quantity_dates.append(kwargs["execution_date"])
            return 200 if kwargs["execution_date"] == date(2026, 9, 30) else 600

        def get_sellable_quantity(self, **kwargs):
            self.sellable_query = kwargs
            return 500

    isolated_db = IsolatedLiveTradeDB()
    requested_read_only = []

    def get_isolated_live_trade_db(*, read_only=False):
        requested_read_only.append(read_only)
        return isolated_db

    monkeypatch.setattr(observations_api, "get_live_trade_db", get_isolated_live_trade_db)

    class Validator:
        @property
        def tushare_client(self):
            return market

    app = create_research_app(db=ResearchDB(":memory:"), validator=Validator())
    payload = TestClient(app).get("/api/research/card021/510880/live-observation").json()

    assert payload["status"] == "available"
    assert payload["actual_shares"] == 600
    assert payload["sellable_shares_as_of_latest_market_data"] == 500
    assert payload["actual_delta_shares"] is None
    assert payload["execution_gate"] == "blocked_missing_account_nav_or_cash"
    assert payload["account_source"] == "user_confirmed_autonomous_manual_records_unverified_by_broker"
    latest_date = date.fromisoformat(payload["latest_market_data_date"])
    signal_date = date.fromisoformat(payload["signal_date"])
    assert isolated_db.log_query == {
        "symbol": "510880.SH",
        "trade_type": TradeType.actual,
        "record_source": "autonomous_manual",
        "execution_date": latest_date,
    }
    assert isolated_db.quantity_dates == [latest_date, signal_date]
    assert isolated_db.sellable_query == {
        "symbol": "510880.SH",
        "trade_type": TradeType.actual,
        "record_source": "autonomous_manual",
        "execution_date": latest_date,
    }
    assert requested_read_only == [True]


def test_read_only_live_trade_db_does_not_create_missing_ledger(tmp_path):
    path = tmp_path / "missing" / "live_trade.db"
    db = LiveTradeDB(path, read_only=True)

    with pytest.raises(sqlite3.OperationalError):
        with db._get_conn():
            pass

    assert not path.exists()
    assert not path.parent.exists()


def test_read_only_live_trade_db_rejects_writes(tmp_path):
    path = tmp_path / "live_trade.db"
    LiveTradeDB(path)
    db = LiveTradeDB(path, read_only=True)

    with db._get_conn() as conn:
        assert conn.execute("SELECT COUNT(*) FROM execution_observation_logs").fetchone()[0] == 0
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            conn.execute("CREATE TABLE must_not_be_created (id INTEGER)")

    with sqlite3.connect(path) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='must_not_be_created'",
        ).fetchone()[0] == 0


def test_empty_dividend_source_blocks_signal():
    market = FakeMarketClient(dividend_rows=[])

    response = _router_app(lambda: market).get("/api/research/card021/510880/live-observation")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "unavailable"
    assert payload["failure_code"] == "dividend_source_empty"
    assert payload.get("target_weight") is None


def test_dividend_factor_mismatch_blocks_signal():
    market = FakeMarketClient(dividend_ex_date="20260915", apply_dividend_factor=False)

    response = _router_app(lambda: market).get("/api/research/card021/510880/live-observation")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "unavailable"
    assert payload["failure_code"] == "dividend_adjustment_mismatch"
    assert payload.get("target_weight") is None


def test_dividend_factor_mismatch_on_first_signal_window_day_blocks_signal():
    market = FakeMarketClient()
    signal_date = date(2026, 9, 30)
    window_start = [day for day in market.open_dates if day <= signal_date][-61]
    ex_date = window_start.strftime("%Y%m%d")
    market = FakeMarketClient(dividend_ex_date=ex_date, apply_dividend_factor=False)

    payload = _router_app(lambda: market).get(
        "/api/research/card021/510880/live-observation",
    ).json()

    assert payload["status"] == "unavailable"
    assert payload["failure_code"] == "dividend_adjustment_mismatch"
    assert payload.get("target_weight") is None


def test_adjustment_factor_change_without_dividend_event_blocks_signal():
    market = FakeMarketClient(unreported_adjustment_date="20260915")

    response = _router_app(lambda: market).get("/api/research/card021/510880/live-observation")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "unavailable"
    assert payload["failure_code"] == "dividend_source_uncovered_adjustment"
    assert payload.get("target_weight") is None


def test_confirmed_isolated_account_snapshot_computes_frozen_share_delta():
    from backend.services.card020_vol_budget import _target_shares, _target_weight

    market = FakeMarketClient()
    account = {
        "status": "user_confirmed_position",
        "record_source": "autonomous_manual",
        "confirmed_by_user": True,
        "broker_verified": False,
        "actual_shares": 400,
        "sellable_shares": 300,
        "shares_at_signal": 200,
        "account_cash_at_signal_cny": "4000.00",
        "dividend_receivable_at_signal_cny": "0.00",
    }
    response = _router_app(lambda: market, lambda _signal_date, _latest_date: account).get(
        "/api/research/card021/510880/live-observation",
    )

    payload = response.json()
    signal_close = next(row["close"] for row in market.rows["fund_daily"] if row["trade_date"] == "20260930")
    expected_target = _target_shares(
        _target_weight(Decimal(payload["signal_volatility"])),
        Decimal("4000.00") + Decimal("200") * Decimal(str(signal_close)),
        Decimal(str(signal_close)),
    )
    assert payload["status"] == "available"
    assert payload["account_target_shares"] == expected_target
    assert payload["actual_shares"] == 400
    assert payload["actual_delta_shares"] == expected_target - 400


def test_next_completed_month_end_supersedes_previous_target():
    from datetime import time

    now = datetime.combine(date(2026, 10, 30), time(17, 30), tzinfo=SHANGHAI)
    market = FakeMarketClient(as_of=now.date())
    app = FastAPI()
    app.include_router(create_card021_router(lambda: market, now_provider=lambda: now))

    response = TestClient(app).get("/api/research/card021/510880/live-observation")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "available"
    assert payload["signal_date"] == "2026-10-30"
    assert payload["supersedes_signal_date"] == "2026-09-30"
    assert payload["first_attempt_status"] == "not_started"
    assert payload["target_validity_status"] == "active_until_next_month_end"


def test_reported_signal_price_and_target_weight_floor_to_800_model_shares():
    target_weight = Decimal("58.9172130881") / Decimal("100")

    shares = _target_shares(target_weight, Decimal("5000.00"), Decimal("3.368"))

    assert shares == 800
    assert shares * Decimal("3.368") == Decimal("2694.400")
    assert Decimal("900") * Decimal("3.368") > target_weight * Decimal("5000.00")


def test_market_snapshot_is_append_only_account_free_and_read_without_live_queries():
    market = FakeMarketClient()
    account_calls = []
    db = ResearchDB(":memory:")
    store = Card021SnapshotStore(db.conn)

    def account_provider(*dates):
        account_calls.append(dates)
        return {
            "status": "user_confirmed_position",
            "record_source": "autonomous_manual",
            "confirmed_by_user": True,
            "broker_verified": False,
            "actual_shares": 600,
            "sellable_shares": 500,
        }

    client = _router_app(lambda: market, account_provider, store)
    live = client.get("/api/research/card021/510880/live-observation")

    assert live.status_code == 200
    payload = live.json()
    assert payload["status"] == "available"
    assert payload["snapshot_id"].startswith("card021_")
    assert payload["market_input_sha256"]
    assert payload["market_result_sha256"]
    assert payload["implementation_sha256"]
    assert payload["protocol_sha256"] == "969903D59F949DA0024448128404266C0059EA1A7BEF901B6496045BFDDE8D9D"
    assert payload["judgment_at"] == NOW.isoformat(timespec="microseconds")
    assert payload["received_at"]
    assert len(payload["sources"]) == 4
    for source in payload["sources"]:
        assert source["request_started_at"]
        assert source["received_at"]
        assert source["row_count"] > 0
        assert datetime.fromisoformat(source["request_started_at"]) <= datetime.fromisoformat(source["received_at"])
        assert source["retrieved_at"] == source["received_at"]

    stored = store.get_snapshot(payload["snapshot_id"])
    assert len(stored["market_inputs"]["signal_window"]) == 61
    assert stored["market_inputs"]["signal_window"][-1]["trade_date"] == "20260930"
    serialized = json.dumps(stored, ensure_ascii=False, sort_keys=True)
    for forbidden in (
        "actual_shares",
        "sellable_shares",
        "account_target_shares",
        "actual_delta_shares",
        "account_cash_at_signal_cny",
        "dividend_receivable_at_signal_cny",
        "account_source",
    ):
        assert forbidden not in serialized

    market_call_count = len(market.calls)
    account_call_count = len(account_calls)
    saved = client.get(f"/api/research/card021/510880/snapshots/{payload['snapshot_id']}")

    assert saved.status_code == 200
    saved_payload = saved.json()
    assert saved_payload["snapshot_mode"] == "saved_market_snapshot"
    assert saved_payload["snapshot_historical"] is True
    assert saved_payload["snapshot_id"] == payload["snapshot_id"]
    assert saved_payload["signal_date"] == payload["signal_date"]
    assert saved_payload["model_reference_shares"] == payload["model_reference_shares"]
    assert saved_payload["account_data_status"] == "not_saved_or_read"
    assert "actual_shares" not in saved_payload
    assert len(market.calls) == market_call_count
    assert len(account_calls) == account_call_count == 1


def test_incomplete_provider_result_is_saved_as_unavailable_and_never_falls_back_to_old_snapshot():
    market = FakeMarketClient(missing_adjustment_date="20260930")
    account_calls = []
    db = ResearchDB(":memory:")
    store = Card021SnapshotStore(db.conn)
    client = _router_app(
        lambda: market,
        lambda *_dates: account_calls.append(True),
        store,
    )

    live = client.get("/api/research/card021/510880/live-observation").json()
    call_count = len(market.calls)
    saved = client.get(f"/api/research/card021/510880/snapshots/{live['snapshot_id']}")

    assert live["status"] == "unavailable"
    assert live["failure_code"] == "adjusted_close_window_incomplete"
    assert live["snapshot_id"]
    assert saved.status_code == 200
    assert saved.json()["status"] == "unavailable"
    assert saved.json()["failure_code"] == "adjusted_close_window_incomplete"
    assert saved.json().get("target_weight") is None
    assert len(market.calls) == call_count == 4
    assert account_calls == []


def test_concurrent_card021_observations_write_distinct_snapshots():
    market = FakeMarketClient()
    db = ResearchDB(":memory:")
    store = Card021SnapshotStore(db.conn)
    app = FastAPI()
    app.include_router(create_card021_router(
        lambda: market,
        now_provider=lambda: NOW,
        snapshot_store=store,
    ))

    def query_once():
        with TestClient(app) as client:
            response = client.get("/api/research/card021/510880/live-observation")
            assert response.status_code == 200
            return response.json()["snapshot_id"]

    with ThreadPoolExecutor(max_workers=4) as pool:
        snapshot_ids = list(pool.map(lambda _index: query_once(), range(4)))

    assert len(set(snapshot_ids)) == 4
    assert all(store.get_snapshot(snapshot_id) is not None for snapshot_id in snapshot_ids)
    assert db.conn.execute("SELECT COUNT(*) FROM card021_market_snapshots").fetchone()[0] == 4


def test_saved_market_snapshot_survives_reopening_research_db_without_live_reads(tmp_path):
    db_path = tmp_path / "research.db"
    market = FakeMarketClient()
    first_db = ResearchDB(str(db_path))
    first_store = Card021SnapshotStore(first_db.conn)
    with _router_app(lambda: market, snapshot_store=first_store) as first_client:
        live = first_client.get("/api/research/card021/510880/live-observation").json()
    first_db.close()

    reopened_db = ResearchDB(str(db_path))
    reopened_store = Card021SnapshotStore(reopened_db.conn)
    unexpected_calls = []

    def unexpected_live_read():
        unexpected_calls.append("market")
        raise AssertionError("saved snapshot lookup must not query the market provider")

    def unexpected_account_read(*_dates):
        unexpected_calls.append("account")
        raise AssertionError("saved snapshot lookup must not query account data")

    with _router_app(
        unexpected_live_read,
        unexpected_account_read,
        reopened_store,
    ) as reopened_client:
        saved = reopened_client.get(f"/api/research/card021/510880/snapshots/{live['snapshot_id']}")

    assert saved.status_code == 200
    assert saved.json()["snapshot_id"] == live["snapshot_id"]
    assert saved.json()["snapshot_sha256"] == live["snapshot_sha256"]
    assert saved.json()["market_input_sha256"] == live["market_input_sha256"]
    assert unexpected_calls == []
    reopened_db.close()
