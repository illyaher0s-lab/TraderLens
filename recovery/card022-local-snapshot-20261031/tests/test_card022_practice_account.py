import sqlite3
from datetime import date, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from backend.api.observations import router as observations_router
from backend.api.research import create_research_app
from backend.config import runtime_paths
from backend.db.live_trade import LiveTradeDB
from backend.db.research import ResearchDB
from backend.services.card022_practice_account import (
    Card022PracticeAccountStore,
    PracticeAccountConflictError,
    PRACTICE_ACCOUNT_ID,
    STARTING_CASH_CENTS,
)


def _last_weekday(day=None):
    day = day or date.today()
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


class WeekdayCalendar:
    def trade_calendar_rows_between(self, start_date, end_date):
        return [
            {
                "cal_date": (start_date + timedelta(days=offset)).strftime("%Y%m%d"),
                "is_open": int((start_date + timedelta(days=offset)).weekday() < 5),
            }
            for offset in range((end_date - start_date).days + 1)
        ]


def test_practice_account_initialization_is_idempotent_and_never_resets_cash(tmp_path):
    store = Card022PracticeAccountStore(tmp_path / "practice_trade.db")

    initialized = store.initialize()
    assert initialized["status"] == "initialized"
    assert initialized["account_id"] == PRACTICE_ACCOUNT_ID
    assert initialized["cash_cents"] == STARTING_CASH_CENTS
    assert initialized["revision"] == 0

    existing = store.initialize()
    assert existing["status"] == "existing"
    assert existing["cash_cents"] == STARTING_CASH_CENTS
    assert existing["revision"] == 0


def test_practice_account_initialization_preserves_existing_database_conflict(tmp_path):
    path = tmp_path / "practice_trade.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE existing_user_data (value TEXT NOT NULL)")
        conn.execute("INSERT INTO existing_user_data VALUES ('preserve-me')")

    store = Card022PracticeAccountStore(path)
    with pytest.raises(PracticeAccountConflictError):
        store.initialize()

    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT value FROM existing_user_data").fetchone()[0] == "preserve-me"
        assert conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = 'card022_practice_accounts'"
        ).fetchone()[0] == 0


def _practice_app(tmp_path, monkeypatch, *, initialize=True):
    practice_path = tmp_path / "practice_trade.db"
    actual_path = tmp_path / "live_trade.db"
    monkeypatch.setattr(runtime_paths, "get_practice_trade_db_path", lambda: str(practice_path))
    monkeypatch.setattr(runtime_paths, "get_live_trade_db_path", lambda: str(actual_path))
    monkeypatch.setattr("backend.api.observations.get_position_market_monitor", lambda: WeekdayCalendar())
    resolver = {
        "510880.SH": {
            "ticker": "510880.SH",
            "company_name": "上证红利ETF",
            "exchange": "SSE",
            "list_status": "L",
            "security_type": "fund",
            "quantity_unit": "fund_share",
        }
    }
    app = create_research_app(
        db=ResearchDB(":memory:"),
        conversation_mode="deterministic",
        serenity_execution_mode="stub",
        stock_resolver_fixture=resolver,
    )
    app.include_router(observations_router)
    store = Card022PracticeAccountStore(practice_path)
    if initialize:
        store.initialize(initialized_at=datetime.now(ZoneInfo("Asia/Shanghai")) - timedelta(days=30))
    return TestClient(app), store, practice_path, actual_path


def _saved_practice_observation(store, *, action="buy", quantity=200, suggested_date=None):
    result = {
        "snapshot_id": "card021_test_snapshot",
        "snapshot_mode": "live_observation",
        "selected_account_mode": "simulated_practice",
        "account_mode": "simulated_practice",
        "account_revision": store.get_status()["revision"],
        "account_data_status": "simulated_practice_account_available",
        "action_decision": action,
        "suggested_quantity_shares": quantity,
        "suggested_action_date": (suggested_date or _last_weekday()).isoformat(),
        "target_valid_until": (date.today() + timedelta(days=30)).isoformat(),
    }
    return store.record_observation(result)["practice_observation_id"]


def _practice_trade_request(
    observation_id,
    *,
    operation_id=None,
    action="buy",
    quantity=100,
    origin="strategy_linked",
    revision=0,
    execution_date=None,
):
    request = {
        "symbol": "510880",
        "action": action,
        "trade_type": "simulated",
        "practice_account_id": PRACTICE_ACCOUNT_ID,
        "practice_execution_origin": origin,
        "practice_account_revision": revision,
        "price": "3.40",
        "quantity": quantity,
        "execution_date": (execution_date or _last_weekday()).isoformat(),
        "operation_id": operation_id or str(uuid4()),
        "confirmed_already_executed": True,
        "trade_source": "self_research",
        "reason": "按已保存观察登记模拟成交",
    }
    if observation_id is not None:
        request["practice_observation_id"] = observation_id
    if action == "sell":
        request["position_id"] = "practice-position"
        request["sell_reason"] = "target"
    return request


def test_confirmed_practice_fill_is_bound_to_saved_observation_and_updates_cash_once(tmp_path, monkeypatch):
    client, store, practice_path, actual_path = _practice_app(tmp_path, monkeypatch)
    observation_id = _saved_practice_observation(store)
    request = _practice_trade_request(observation_id)

    response = client.post("/api/agent/workbench/execution-feedback", json=request)

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["practice_account"]["cash_cents"] == 465_500
    assert result["practice_account"]["revision"] == 1
    assert result["practice_observation_id"] == observation_id
    assert LiveTradeDB(practice_path, read_only=True).list_open_positions()[0].quantity == 100
    assert not actual_path.exists()
    listed = client.get(f"/api/observations?practice_account_id={PRACTICE_ACCOUNT_ID}").json()
    assert listed["execution_logs"][0]["practice_observation_id"] == observation_id
    assert listed["practice_account"]["revision"] == 1

    retry = client.post("/api/agent/workbench/execution-feedback", json=request)
    assert retry.status_code == 200
    assert retry.json() == result
    assert Card022PracticeAccountStore(practice_path).get_status()["revision"] == 1

    voided = client.post(
        f"/api/observations/execution-logs/{result['log_id']}/void?practice_account_id={PRACTICE_ACCOUNT_ID}",
        json={"reason": "测试撤销这笔模拟成交"},
    )
    assert voided.status_code == 200, voided.text
    reopened = client.get(f"/api/observations?practice_account_id={PRACTICE_ACCOUNT_ID}").json()
    assert reopened["practice_account"]["cash_cents"] == STARTING_CASH_CENTS
    assert reopened["practice_account"]["revision"] == 2
    assert reopened["execution_logs"][0]["voided"] is True
    assert reopened["practice_cash_events"][0]["event_type"] == "void"
    assert Card022PracticeAccountStore(practice_path).get_status()["revision"] == 2
    assert not actual_path.exists()


def test_practice_fill_rejects_stale_observation_and_second_same_day_fill(tmp_path, monkeypatch):
    client, store, practice_path, _actual_path = _practice_app(tmp_path, monkeypatch)
    first_observation_id = _saved_practice_observation(store)
    first = client.post(
        "/api/agent/workbench/execution-feedback",
        json=_practice_trade_request(first_observation_id),
    )
    assert first.status_code == 200, first.text

    stale = client.post(
        "/api/agent/workbench/execution-feedback",
        json=_practice_trade_request(first_observation_id),
    )
    assert stale.status_code == 409
    assert Card022PracticeAccountStore(practice_path).get_status()["revision"] == 1

    fresh_observation_id = _saved_practice_observation(store)
    same_day = client.post(
        "/api/agent/workbench/execution-feedback",
        json=_practice_trade_request(fresh_observation_id),
    )
    assert same_day.status_code == 409
    assert Card022PracticeAccountStore(practice_path).get_status()["revision"] == 1
    assert len(LiveTradeDB(practice_path, read_only=True).list_open_positions()) == 1


def test_practice_fill_requires_observation_direction_and_lot_limit(tmp_path, monkeypatch):
    client, store, practice_path, _actual_path = _practice_app(tmp_path, monkeypatch)
    observation_id = _saved_practice_observation(store, action="sell", quantity=100)

    wrong_direction = client.post(
        "/api/agent/workbench/execution-feedback",
        json=_practice_trade_request(observation_id, action="buy"),
    )
    too_many_shares = client.post(
        "/api/agent/workbench/execution-feedback",
        json=_practice_trade_request(observation_id, action="sell", quantity=200),
    )

    assert wrong_direction.status_code == 409
    assert too_many_shares.status_code == 409
    assert Card022PracticeAccountStore(practice_path).get_status()["revision"] == 0


def test_autonomous_practice_sell_is_labeled_and_not_gated_by_strategy_direction(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "backend.api.observations.get_position_market_monitor",
        lambda: WeekdayCalendar(),
    )
    client, store, practice_path, _actual_path = _practice_app(tmp_path, monkeypatch)
    sell_date = _last_weekday()
    buy_date = sell_date - timedelta(days=1)
    while buy_date.weekday() >= 5:
        buy_date -= timedelta(days=1)

    buy_observation = _saved_practice_observation(store, suggested_date=buy_date)
    buy = client.post(
        "/api/agent/workbench/execution-feedback",
        json=_practice_trade_request(buy_observation, execution_date=buy_date),
    )
    assert buy.status_code == 200, buy.text

    autonomous_sell = _practice_trade_request(
        None,
        action="sell",
        origin="autonomous_practice",
        revision=1,
        execution_date=sell_date,
    )
    autonomous_sell["position_id"] = buy.json()["position_id"]
    autonomous_sell["price"] = "3.50"
    sold = client.post("/api/agent/workbench/execution-feedback", json=autonomous_sell)

    assert sold.status_code == 200, sold.text
    assert sold.json()["practice_execution_origin"] == "autonomous_practice"
    assert sold.json()["practice_observation_id"] is None
    assert sold.json()["discipline_review_id"]
    assert any("自主模拟成交记录" in warning for warning in sold.json()["warnings"])
    listed = client.get(f"/api/observations?practice_account_id={PRACTICE_ACCOUNT_ID}").json()
    sell_log = next(log for log in listed["execution_logs"] if log["confirmed_action"] == "sell")
    assert sell_log["practice_execution_origin"] == "autonomous_practice"
    assert sell_log["practice_observation_id"] is None
    assert listed["practice_account"]["cash_cents"] == STARTING_CASH_CENTS
    assert listed["positions"][0]["lifecycle_state"] == "closed"
    assert any(review["sell_log_id"] == sold.json()["log_id"] for review in listed["discipline_reviews"])


def test_practice_account_status_detects_cash_journal_mismatch(tmp_path):
    path = tmp_path / "practice_trade.db"
    store = Card022PracticeAccountStore(path)
    store.initialize()
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE card022_practice_accounts SET cash_cents = cash_cents - 100 WHERE account_id = ?",
            (PRACTICE_ACCOUNT_ID,),
        )

    with pytest.raises(PracticeAccountConflictError, match="余额与流水版本不符"):
        store.get_status()


def test_practice_cash_events_are_append_only(tmp_path):
    path = tmp_path / "practice_trade.db"
    Card022PracticeAccountStore(path).initialize()

    with sqlite3.connect(path) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(
                "UPDATE card022_practice_cash_events SET cash_delta_cents = 0 WHERE revision = 0"
            )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("DELETE FROM card022_practice_cash_events WHERE revision = 0")


def test_new_practice_account_stays_separate_from_legacy_simulated_records(tmp_path, monkeypatch):
    client, _store, practice_path, actual_path = _practice_app(tmp_path, monkeypatch, initialize=False)
    legacy_trade = {
        "symbol": "510880",
        "action": "buy",
        "trade_type": "simulated",
        "price": "3.40",
        "quantity": 100,
        "execution_date": _last_weekday().isoformat(),
        "operation_id": str(uuid4()),
        "confirmed_already_executed": True,
        "trade_source": "self_research",
        "reason": "原模拟账本历史记录",
    }
    legacy_response = client.post(
        "/api/agent/workbench/execution-feedback",
        json=legacy_trade,
    )
    assert legacy_response.status_code == 200, legacy_response.text
    actual_db = LiveTradeDB(actual_path, read_only=True)
    legacy_before = [(p.position_id, p.quantity) for p in actual_db.list_open_positions()]
    actual_bytes_before = actual_path.read_bytes()

    initialized = client.post("/api/research/card021/practice-account/initialize")
    assert initialized.status_code == 200, initialized.text
    assert initialized.json()["status"] == "initialized"
    assert initialized.json()["cash_cents"] == STARTING_CASH_CENTS
    assert initialized.json()["revision"] == 0
    assert actual_path.read_bytes() == actual_bytes_before

    legacy_view = client.get("/api/observations").json()
    assert legacy_view["positions"][0]["trade_type"] == "simulated"
    assert legacy_view["positions"][0]["position_id"] == legacy_response.json()["position_id"]
    assert legacy_view["execution_logs"][0]["trade_type"] == "simulated"

    practice_view = client.get(f"/api/observations?practice_account_id={PRACTICE_ACCOUNT_ID}").json()
    assert practice_view["positions"] == []
    assert practice_view["execution_logs"] == []
    assert practice_view["practice_account"]["cash_cents"] == STARTING_CASH_CENTS
    assert practice_view["practice_account"]["revision"] == 0
    practice_snapshot = Card022PracticeAccountStore(practice_path).account_snapshot(
        as_of_date=date.today(),
        signal_date=date.today(),
    )
    assert practice_snapshot["actual_shares"] == 0
    assert actual_path.read_bytes() == actual_bytes_before

    reopened_store = Card022PracticeAccountStore(practice_path)
    assert reopened_store.get_status()["cash_cents"] == STARTING_CASH_CENTS
    assert LiveTradeDB(practice_path, read_only=True).list_open_positions() == []
    assert [(p.position_id, p.quantity) for p in actual_db.list_open_positions()] == legacy_before
