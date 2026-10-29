from datetime import datetime
import logging
from zoneinfo import ZoneInfo

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.card021 import create_card021_router
from backend.db.research import ResearchDB
from backend.services.card021_store import Card021SnapshotStore


NOW = datetime(2026, 10, 29, 17, 30, tzinfo=ZoneInfo("Asia/Shanghai"))


class EmptyMarketClient:
    def query(self, *_args, **_kwargs):
        return []


def test_snapshot_save_failure_logs_only_stage_and_exception_type(caplog):
    db = ResearchDB(":memory:")
    store = Card021SnapshotStore(db.conn)
    db.conn.executescript(
        """
        CREATE TRIGGER fail_card021_snapshot_insert
        BEFORE INSERT ON card021_market_snapshots
        BEGIN
            SELECT RAISE(ABORT, 'synthetic-secret-marker');
        END;
        """
    )
    app = FastAPI()
    app.include_router(
        create_card021_router(
            lambda: EmptyMarketClient(),
            account_provider=lambda *_dates: {"status": "unverified"},
            now_provider=lambda: NOW,
            snapshot_store=store,
        )
    )
    caplog.set_level(logging.ERROR, logger="backend.api.card021")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/research/card021/510880/live-observation")

    assert response.status_code == 503
    assert response.json() == {
        "detail": "无法保存可核对的行情快照，本次观察不展示为可用。"
    }
    records = [record for record in caplog.records if record.name == "backend.api.card021"]
    assert len(records) == 1
    record = records[0]
    assert record.getMessage() == (
        "Card021 snapshot save failed; stage=record_snapshot exception_type=IntegrityError"
    )
    assert record.exc_info is None
    assert record.stack_info is None
    assert "synthetic-secret-marker" not in caplog.text
    assert db.conn.execute("SELECT COUNT(*) FROM card021_market_snapshots").fetchone()[0] == 0
    db.conn.close()


def test_successful_snapshot_save_does_not_emit_failure_log(caplog):
    db = ResearchDB(":memory:")
    store = Card021SnapshotStore(db.conn)
    app = FastAPI()
    app.include_router(
        create_card021_router(
            lambda: EmptyMarketClient(),
            account_provider=lambda *_dates: {"status": "unverified"},
            now_provider=lambda: NOW,
            snapshot_store=store,
        )
    )
    caplog.set_level(logging.ERROR, logger="backend.api.card021")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/research/card021/510880/live-observation")

    assert response.status_code == 200
    assert response.json().get("snapshot_id")
    assert db.conn.execute("SELECT COUNT(*) FROM card021_market_snapshots").fetchone()[0] == 1
    assert [record for record in caplog.records if record.name == "backend.api.card021"] == []
    db.conn.close()



def test_snapshot_persists_reverse_order_tushare_calendar(caplog):
    from datetime import timedelta
    import numpy as np
    import pandas as pd

    days = [NOW.date() - timedelta(days=180) + timedelta(days=i) for i in range(243)]
    open_dates = [day for day in days if day.weekday() < 5 and day <= NOW.date()]
    calendar_rows = [
        {"cal_date": day.strftime("%Y%m%d"), "is_open": int(day.weekday() < 5)}
        for day in days
    ]
    calendar_rows.reverse()

    frames = {
        "trade_cal": pd.DataFrame(calendar_rows),
        "fund_daily": pd.DataFrame([
            {
                "ts_code": "510880.SH",
                "trade_date": day.strftime("%Y%m%d"),
                "close": 3.0 + index / 10000,
                "vol": np.int64(50000),
            }
            for index, day in enumerate(open_dates)
        ]),
        "fund_adj": pd.DataFrame([
            {
                "ts_code": "510880.SH",
                "trade_date": day.strftime("%Y%m%d"),
                "adj_factor": np.float64(1.0),
            }
            for day in open_dates
        ]),
        "fund_div": pd.DataFrame([{
            "ts_code": "510880.SH",
            "ann_date": "20260501",
            "imp_anndate": pd.NA,
            "ex_date": "20260515",
            "div_proc": "\u5b9e\u65bd",
            "div_cash": np.float64(0.01),
        }]),
    }
    frames["fund_daily"]["open"] = np.nan

    class DataFrameMarketClient:
        def __init__(self):
            self.calls = []

        def query(self, api_name, **_kwargs):
            self.calls.append(api_name)
            return frames[api_name]

    market = DataFrameMarketClient()
    db = ResearchDB(":memory:")
    store = Card021SnapshotStore(db.conn)
    app = FastAPI()
    app.include_router(
        create_card021_router(
            lambda: market,
            account_provider=lambda *_dates: {"status": "unverified"},
            now_provider=lambda: NOW,
            snapshot_store=store,
        )
    )
    caplog.set_level(logging.ERROR, logger="backend.api.card021")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/research/card021/510880/live-observation")
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "available"
        assert payload["snapshot_id"]
        saved = client.get(
            f"/api/research/card021/510880/snapshots/{payload['snapshot_id']}"
        )

    assert saved.status_code == 200
    stored = store.get_snapshot(payload["snapshot_id"])
    assert stored is not None
    dates = [row["trade_date"] for row in stored["market_inputs"]["signal_window"]]
    assert dates == sorted(dates)
    assert dates[-1] == "20260930"
    assert market.calls == ["trade_cal", "fund_daily", "fund_adj", "fund_div"]
    assert [record for record in caplog.records if record.name == "backend.api.card021"] == []
    db.conn.close()


def test_expired_month_end_target_does_not_expose_account_share_delta():
    from datetime import date, timedelta

    now = datetime(2026, 12, 31, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    start = now.date() - timedelta(days=180)
    calendar_end = now.date() + timedelta(days=62)
    days = [start + timedelta(days=offset) for offset in range((calendar_end - start).days + 1)]
    open_dates = [
        day for day in days
        if day.weekday() < 5 and day != date(2027, 1, 1)
    ]
    completed_dates = [day for day in open_dates if day < now.date()]
    daily_rows = []
    adjustment_rows = []
    factor = 1.0
    dividend_ex_date = date(2026, 5, 15)
    for index, day in enumerate(completed_dates):
        close = 3.0 + index / 10000
        if day == dividend_ex_date and index > 0:
            factor *= daily_rows[-1]["close"] / (daily_rows[-1]["close"] - 0.01)
        daily_rows.append({
            "ts_code": "510880.SH",
            "trade_date": day.strftime("%Y%m%d"),
            "open": close,
            "close": close,
            "vol": 50000,
        })
        adjustment_rows.append({
            "ts_code": "510880.SH",
            "trade_date": day.strftime("%Y%m%d"),
            "adj_factor": factor,
        })

    frames = {
        "trade_cal": [
            {"cal_date": day.strftime("%Y%m%d"), "is_open": int(day in open_dates)}
            for day in days
        ],
        "fund_daily": daily_rows,
        "fund_adj": adjustment_rows,
        "fund_div": [{
            "ts_code": "510880.SH",
            "ann_date": "20260501",
            "imp_anndate": "20260501",
            "ex_date": "20260515",
            "pay_date": "20260520",
            "div_proc": "实施",
            "div_cash": 0.01,
        }],
    }

    class FakeMarketClient:
        def query(self, api_name, **_kwargs):
            return frames[api_name]

    account = {
        "status": "user_confirmed_position",
        "record_source": "autonomous_manual",
        "confirmed_by_user": True,
        "broker_verified": False,
        "actual_shares": 600,
        "sellable_shares": 500,
        "shares_at_signal": 600,
        "account_cash_at_signal_cny": "4000.00",
        "dividend_receivable_at_signal_cny": "0.00",
    }
    db = ResearchDB(":memory:")
    store = Card021SnapshotStore(db.conn)
    app = FastAPI()
    app.include_router(
        create_card021_router(
            lambda: FakeMarketClient(),
            account_provider=lambda *_dates: account,
            now_provider=lambda: now,
            snapshot_store=store,
        )
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/research/card021/510880/live-observation")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "available"
    assert payload["signal_date"] == "2026-11-30"
    assert payload["target_valid_until"] == "2026-12-31"
    assert payload["next_possible_attempt_date"] > payload["target_valid_until"]
    assert payload["target_validity_status"] == "expired"
    assert payload["retry_policy_status"] == "not_eligible_expired"
    assert payload["execution_gate"] == "blocked_target_expired"
    assert payload["action_decision"] == "not_decidable"
    assert payload["actual_shares"] == 600
    assert payload["sellable_shares_as_of_latest_market_data"] == 500
    assert payload["account_target_shares"] is None
    assert payload["actual_delta_shares"] is None
    db.conn.close()
