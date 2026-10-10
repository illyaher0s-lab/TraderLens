from uuid import uuid4
import sqlite3
import json
from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient

from backend.api.research import create_research_app
from backend.config import runtime_paths
from backend.db.live_trade import LiveTradeDB
from backend.db.research import ResearchDB
from backend.api.observations import router as observations_router
from contracts.live_trade import ObservationPosition, PositionLifecycleState, TradeType


class FailableSecurityFixture(dict):
    fail_lookup = False

    def items(self):
        if self.fail_lookup:
            raise RuntimeError("security identity source unavailable")
        return super().items()


class FixedSseTradeCalendar:
    def trade_calendar_rows_between(self, start_date, end_date):
        from datetime import timedelta

        return [
            {"cal_date": (start_date + timedelta(days=offset)).strftime("%Y%m%d"),
             "is_open": int((start_date + timedelta(days=offset)).weekday() < 5)}
            for offset in range((end_date - start_date).days + 1)
        ]


@pytest.fixture
def trade_app(tmp_path, monkeypatch):
    ledger_path = tmp_path / "live_trade.db"
    monkeypatch.setattr(runtime_paths, "get_live_trade_db_path", lambda: str(ledger_path))
    security_fixture = FailableSecurityFixture({
        "600000.SH": {
            "ticker": "600000.SH",
            "company_name": "浦发银行",
            "exchange": "SSE",
            "list_status": "L",
            "security_type": "stock",
            "quantity_unit": "share",
        },
        "510880.SH": {
            "ticker": "510880.SH",
            "company_name": "上证红利ETF",
            "exchange": "SSE",
            "security_type": "fund",
            "quantity_unit": "fund_share",
        },
        "159001.SZ": {
            "ticker": "159001.SZ",
            "company_name": "测试用未核交易规则基金",
            "exchange": "SZSE",
            "list_status": "L",
            "security_type": "fund",
            "quantity_unit": "fund_share",
        },
    })
    app = create_research_app(
        db=ResearchDB(":memory:"),
        conversation_mode="deterministic",
        serenity_execution_mode="stub",
        stock_resolver_fixture=security_fixture,
    )
    app.include_router(observations_router)
    app.state.manual_security_identity_fixture = security_fixture
    monkeypatch.setattr(
        "backend.api.observations.get_position_market_monitor",
        lambda: FixedSseTradeCalendar(),
    )
    return app, ledger_path


def manual_request(
    action: str,
    operation_id: str | None = None,
    *,
    fees=None,
    trade_type: str = "simulated",
    execution_date: str | None = None,
    symbol: str = "600000",
    position_id: str | None = None,
    price: str | None = None,
    quantity: int = 100,
):
    request = {
        "symbol": symbol,
        "action": action,
        "trade_type": trade_type,
        "price": price or ("10.00" if action == "buy" else "12.00"),
        "quantity": quantity,
        "execution_date": execution_date or ("2026-09-10" if action == "buy" else "2026-09-11"),
        "operation_id": operation_id or str(uuid4()),
        "confirmed_already_executed": True,
        "trade_source": "self_research",
        "reason": "按原计划记录成交",
    }
    if position_id is not None:
        request["position_id"] = position_id
    if action == "sell":
        request["sell_reason"] = "target"
    if fees is not None:
        request["fees"] = fees
    return request


def post_manual(client, request):
    return client.post("/api/agent/workbench/execution-feedback", json=request)


def insert_legacy_manual_sell(ledger, buy_response, *, quantity, execution_date, log_id):
    buy = ledger.get_log(buy_response["log_id"])
    with sqlite3.connect(ledger.db_path) as conn:
        conn.execute(
            """
            INSERT INTO execution_observation_logs (
                log_id, confirmed_action, confirmed_execution_status, confirmed_price,
                confirmed_quantity, confirmed_by_user, broker_verified, confirmed_at,
                execution_date, symbol, name, record_source, trade_type, operation_id,
                operation_fingerprint, confirmed_trade_amount, security_type,
                quantity_unit, sell_reason
            ) VALUES (?, 'sell', 'executed_full', 3.443, ?, 1, 0, ?, ?, ?, ?,
                      'autonomous_manual', ?, ?, ?, ?, ?, ?, 'target')
            """,
            (
                log_id, quantity, buy.confirmed_at.isoformat(), execution_date,
                buy.symbol, buy.name, buy.trade_type.value, f"legacy-{log_id}",
                f"fingerprint-{log_id}", str(3.443 * quantity), buy.security_type,
                buy.quantity_unit,
            ),
        )


def test_manual_trade_requires_explicit_confirmation_and_operation_id(trade_app):
    app, ledger_path = trade_app
    client = TestClient(app)
    response = post_manual(client, {
        "feedback": "已买入 100 股，成交价 10.00",
        "symbol": "600000.SH",
    })
    assert response.status_code == 422
    assert LiveTradeDB(ledger_path).list_all_positions() == []


def test_manual_trade_requires_explicit_trade_type(trade_app):
    app, ledger_path = trade_app
    client = TestClient(app)
    request = manual_request("buy")
    request.pop("trade_type")

    response = post_manual(client, request)

    assert response.status_code == 422
    assert LiveTradeDB(ledger_path).list_all_positions() == []


def test_trade_type_persists_through_log_position_observation_and_review(trade_app):
    app, ledger_path = trade_app
    client = TestClient(app)
    request = manual_request("buy", trade_type="actual")

    bought = post_manual(client, request)
    assert bought.status_code == 200, bought.text
    ledger = LiveTradeDB(ledger_path)
    log = ledger.get_log(bought.json()["log_id"])
    position = ledger.get_position(bought.json()["position_id"])
    assert log.trade_type.value == "actual"
    assert position.trade_type.value == "actual"

    listed = client.get("/api/observations?status=open").json()
    assert listed["positions"][0]["trade_type"] == "actual"
    assert listed["execution_logs"][0]["trade_type"] == "actual"

    sold = post_manual(client, manual_request(
        "sell", trade_type="actual", execution_date="2026-09-11",
        position_id=bought.json()["position_id"],
    ))
    assert sold.status_code == 200, sold.text
    assert sold.json()["discipline_review_id"]
    review = ledger.get_discipline_review(sold.json()["discipline_review_id"])
    assert review.trade_type.value == "actual"
    assert review.pnl_record.trade_type.value == "actual"
    assert review.execution_rule_status == "actual_recorded"


def test_reused_operation_id_with_different_trade_type_conflicts(trade_app):
    app, _ = trade_app
    client = TestClient(app)
    request = manual_request("buy", trade_type="simulated")

    first = post_manual(client, request)
    changed_type = dict(request, trade_type="actual")

    assert first.status_code == 200, first.text
    assert post_manual(client, changed_type).status_code == 409


def test_sell_matches_only_the_selected_trade_type(trade_app):
    app, ledger_path = trade_app
    client = TestClient(app)
    actual_buy = post_manual(client, manual_request("buy", trade_type="actual"))
    simulated_buy = post_manual(client, manual_request("buy", trade_type="simulated"))
    assert actual_buy.status_code == 200, actual_buy.text
    assert simulated_buy.status_code == 200, simulated_buy.text

    mismatched_actual_sell = post_manual(client, manual_request(
        "sell", trade_type="actual", position_id=simulated_buy.json()["position_id"],
    ))
    assert mismatched_actual_sell.status_code == 400

    simulated_sell = post_manual(client, manual_request(
        "sell", trade_type="simulated", position_id=simulated_buy.json()["position_id"],
    ))
    assert simulated_sell.status_code == 200, simulated_sell.text
    assert simulated_sell.json()["execution_rule_status"] == "verified"
    ledger = LiveTradeDB(ledger_path)
    actual_position = ledger.get_position(actual_buy.json()["position_id"])
    simulated_position = ledger.get_position(simulated_buy.json()["position_id"])
    assert actual_position.lifecycle_state.value == "open"
    assert simulated_position.lifecycle_state.value == "closed"
    review = ledger.get_discipline_review(simulated_sell.json()["discipline_review_id"])
    assert review.trade_type.value == "simulated"
    assert review.pnl_record.trade_type.value == "simulated"


def test_partial_simulated_sells_keep_one_durable_review_per_sale(trade_app):
    app, ledger_path = trade_app
    client = TestClient(app)
    ledger = LiveTradeDB(ledger_path)
    buy = post_manual(client, manual_request("buy", fees=4.0, trade_type="simulated"))
    assert buy.status_code == 200, buy.text

    first_sell = manual_request(
        "sell", fees=1.0, trade_type="simulated", execution_date="2026-09-11",
        position_id=buy.json()["position_id"], quantity=50,
    )
    first = post_manual(client, first_sell)
    second_sell = manual_request(
        "sell", fees=1.0, trade_type="simulated", execution_date="2026-09-14",
        position_id=buy.json()["position_id"], quantity=50,
    )
    second = post_manual(client, second_sell)

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["realized_pnl"] == 97.0
    assert second.json()["realized_pnl"] == 97.0
    reopened = LiveTradeDB(ledger_path)
    reviews = reopened.list_discipline_reviews()
    assert len(reviews) == 2
    assert {review.sell_log_id for review in reviews} == {first.json()["log_id"], second.json()["log_id"]}
    assert all(review.position_id == buy.json()["position_id"] for review in reviews)
    assert all(review.execution_rule_status == "verified" for review in reviews)
    assert all(review.dividend_status == "unverified" for review in reviews)
    assert {review.holding_days for review in reviews} == {1, 4}
    assert all(review.plan_comparison["message"] == "无事前计划，无法判断纪律" for review in reviews)
    assert reopened.get_position(buy.json()["position_id"]).lifecycle_state.value == "closed"
    assert len(client.get("/api/observations?status=all").json()["discipline_reviews"]) == 2


def test_simulated_stock_same_day_sell_is_rejected_without_writes(trade_app):
    app, ledger_path = trade_app
    client = TestClient(app)
    ledger = LiveTradeDB(ledger_path)
    buy = post_manual(client, manual_request("buy", trade_type="simulated"))
    assert buy.status_code == 200, buy.text

    sell_request = manual_request(
        "sell", trade_type="simulated", execution_date="2026-09-10",
        position_id=buy.json()["position_id"],
    )
    sell_operation_id = sell_request["operation_id"]

    rejected = post_manual(client, sell_request)

    assert rejected.status_code == 400
    assert "T+1" in rejected.json()["detail"]
    position = ledger.get_position(buy.json()["position_id"])
    assert position.lifecycle_state.value == "open"
    assert position.quantity == 100
    with ledger._get_conn() as conn:
        assert conn.execute("SELECT COUNT(*) FROM execution_observation_logs").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM discipline_reviews").fetchone()[0] == 0
    assert ledger.get_manual_operation(sell_operation_id) is None


def test_simulated_stock_sell_on_non_trading_day_is_rejected_without_writes(trade_app):
    app, ledger_path = trade_app
    client = TestClient(app)
    ledger = LiveTradeDB(ledger_path)
    buy = post_manual(client, manual_request("buy", trade_type="simulated"))
    assert buy.status_code == 200, buy.text

    sold = post_manual(client, manual_request(
        "sell", trade_type="simulated", execution_date="2026-09-12",
        position_id=buy.json()["position_id"],
    ))

    assert sold.status_code == 400
    assert "未保存记录" in sold.json()["detail"]
    assert ledger.get_position(buy.json()["position_id"]).lifecycle_state.value == "open"
    assert len(ledger.list_execution_logs()) == 1
    assert ledger.list_discipline_reviews() == []


def test_simulated_510880_stock_etf_same_day_sell_is_rejected(trade_app):
    app, ledger_path = trade_app
    client = TestClient(app)
    ledger = LiveTradeDB(ledger_path)
    buy = post_manual(client, manual_request("buy", symbol="510880", trade_type="simulated"))
    assert buy.status_code == 200, buy.text

    rejected = post_manual(
        client,
        manual_request("sell", symbol="510880", trade_type="simulated", execution_date="2026-09-10", position_id=buy.json()["position_id"]),
    )

    assert rejected.status_code == 400
    assert "T+1" in rejected.json()["detail"]
    assert ledger.get_position(buy.json()["position_id"]).lifecycle_state.value == "open"
    with ledger._get_conn() as conn:
        assert conn.execute("SELECT COUNT(*) FROM execution_observation_logs").fetchone()[0] == 1


def test_simulated_other_fund_rule_stays_unverified_and_preserves_sell_fact(trade_app):
    app, ledger_path = trade_app
    client = TestClient(app)
    ledger = LiveTradeDB(ledger_path)
    buy = post_manual(client, manual_request("buy", symbol="159001", trade_type="simulated"))
    assert buy.status_code == 200, buy.text

    sold = post_manual(
        client,
        manual_request("sell", symbol="159001", trade_type="simulated", execution_date="2026-09-11", position_id=buy.json()["position_id"]),
    )

    assert sold.status_code == 400
    assert "未保存记录" in sold.json()["detail"]
    assert ledger.get_position(buy.json()["position_id"]).lifecycle_state.value == "open"
    assert len(ledger.list_execution_logs()) == 1
    assert ledger.list_discipline_reviews() == []


def test_manual_oversell_is_rejected_atomically(trade_app):
    app, ledger_path = trade_app
    client = TestClient(app)
    ledger = LiveTradeDB(ledger_path)
    buy = post_manual(client, manual_request("buy", trade_type="simulated"))
    assert buy.status_code == 200, buy.text

    sell_request = manual_request(
        "sell", trade_type="simulated", execution_date="2026-09-11"
    )
    sell_request["position_id"] = buy.json()["position_id"]
    sell_request["quantity"] = 101
    operation_id = sell_request["operation_id"]

    rejected = post_manual(client, sell_request)

    assert rejected.status_code == 400
    assert "可卖" in rejected.json()["detail"]
    assert len(ledger.list_execution_logs()) == 1
    assert ledger.get_position(buy.json()["position_id"]).quantity == 100
    assert ledger.list_discipline_reviews() == []
    assert ledger.get_manual_operation(operation_id) is None


def test_manual_ledger_writer_rechecks_sellable_quantity_inside_transaction(trade_app):
    app, ledger_path = trade_app
    client = TestClient(app)
    ledger = LiveTradeDB(ledger_path)
    buy = post_manual(client, manual_request("buy", trade_type="simulated"))
    assert buy.status_code == 200, buy.text
    buy_log = ledger.get_log(buy.json()["log_id"])
    invalid_sell = buy_log.model_copy(update={
        "log_id": "log_direct_oversell",
        "confirmed_action": "sell",
        "confirmed_quantity": 101,
        "confirmed_price": 12.0,
        "confirmed_trade_amount": "1212.00",
        "execution_date": date(2026, 9, 11),
        "operation_id": "direct-oversell-operation",
        "operation_fingerprint": "direct-oversell-fingerprint",
        "sell_reason": "target",
    })

    with pytest.raises(ValueError, match="可卖数量"):
        ledger.save_manual_operation(
            invalid_sell,
            {"status": "success"},
            close_position_id=buy.json()["position_id"],
        )

    assert len(ledger.list_execution_logs()) == 1
    assert ledger.get_position(buy.json()["position_id"]).quantity == 100
    assert ledger.get_manual_operation("direct-oversell-operation") is None


def test_voiding_legacy_oversell_restores_position_and_is_idempotent(trade_app):
    app, ledger_path = trade_app
    client = TestClient(app)
    ledger = LiveTradeDB(ledger_path)
    buy_request = manual_request(
        "buy", symbol="510880", trade_type="simulated",
        execution_date="2026-09-30", price="3.409", quantity=500,
    )
    buy = post_manual(client, buy_request)
    assert buy.status_code == 200, buy.text
    insert_legacy_manual_sell(
        ledger, buy.json(), quantity=1000, execution_date="2026-10-01",
        log_id="log_legacy_oversell",
    )

    voided = client.post(
        "/api/observations/execution-logs/log_legacy_oversell/void",
        json={"reason": "历史卖出超过当时持仓"},
    )

    assert voided.status_code == 200, voided.text
    original = ledger.get_log("log_legacy_oversell")
    assert original.confirmed_action == "sell"
    assert original.confirmed_quantity == 1000
    assert original.void_reason == "历史卖出超过当时持仓"
    assert original.voided_at is not None
    position = ledger.get_position(buy.json()["position_id"])
    assert position.lifecycle_state.value == "open"
    assert position.quantity == 500
    listed_log = next(
        row for row in client.get("/api/observations?status=all").json()["execution_logs"]
        if row["log_id"] == "log_legacy_oversell"
    )
    assert listed_log["voided"] is True
    assert listed_log["void_reason"] == "历史卖出超过当时持仓"

    retried = client.post(
        "/api/observations/execution-logs/log_legacy_oversell/void",
        json={"reason": "历史卖出超过当时持仓"},
    )
    assert retried.status_code == 200
    assert retried.json()["status"] == "already_voided"
    with ledger._get_conn() as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM execution_observation_logs WHERE log_id = 'log_legacy_oversell'"
        ).fetchone()[0] == 1


def test_void_requires_reason_and_requires_dependent_sell_first(trade_app):
    app, ledger_path = trade_app
    client = TestClient(app)
    ledger = LiveTradeDB(ledger_path)
    buy = post_manual(client, manual_request(
        "buy", symbol="510880", trade_type="simulated",
        execution_date="2026-09-30", quantity=100,
    ))
    assert buy.status_code == 200, buy.text
    sell = post_manual(client, manual_request(
        "sell", symbol="510880", trade_type="simulated",
        execution_date="2026-10-01", position_id=buy.json()["position_id"],
        quantity=50,
    ))
    assert sell.status_code == 200, sell.text

    missing_reason = client.post(
        f"/api/observations/execution-logs/{buy.json()['log_id']}/void",
        json={"reason": "   "},
    )
    assert missing_reason.status_code == 422
    blocked = client.post(
        f"/api/observations/execution-logs/{buy.json()['log_id']}/void",
        json={"reason": "更正买入记录"},
    )
    assert blocked.status_code == 409
    assert "先作废依赖的卖出" in blocked.json()["detail"]
    assert ledger.get_log(buy.json()["log_id"]).voided_at is None

    void_sell = client.post(
        f"/api/observations/execution-logs/{sell.json()['log_id']}/void",
        json={"reason": "卖出测试录错"},
    )
    assert void_sell.status_code == 200, void_sell.text
    assert client.get("/api/observations?status=all").json()["discipline_reviews"] == []
    restored = ledger.get_position(buy.json()["position_id"])
    assert restored.quantity == 100
    assert restored.lifecycle_state.value == "open"

    void_buy = client.post(
        f"/api/observations/execution-logs/{buy.json()['log_id']}/void",
        json={"reason": "测试买入录错"},
    )
    assert void_buy.status_code == 200, void_buy.text
    closed = ledger.get_position(buy.json()["position_id"])
    assert closed.lifecycle_state.value == "closed"
    assert ledger.get_sellable_quantity(
        symbol="510880.SH", trade_type=TradeType.simulated,
        record_source="autonomous_manual", execution_date=date(2026, 10, 2),
    ) == 0


def test_moving_average_keeps_total_and_sellable_quantity_separate(trade_app):
    app, ledger_path = trade_app
    client = TestClient(app)
    ledger = LiveTradeDB(ledger_path)
    first = post_manual(
        client,
        manual_request("buy", execution_date="2026-09-09", price="10.00", symbol="510880"),
    )
    second_request = manual_request(
        "buy", execution_date="2026-09-10", price="20.00", symbol="510880"
    )
    second_request["reason"] = "第二笔买入采用不同理由"
    second = post_manual(client, second_request)
    assert first.status_code == second.status_code == 200

    today_sell = manual_request(
        "sell",
        symbol="510880",
        execution_date="2026-09-10",
        position_id=first.json()["position_id"],
        price="30.00",
        quantity=50,
    )
    sold = post_manual(client, today_sell)

    assert sold.status_code == 200, sold.text
    assert sold.json()["gross_pnl_amount"] == 750.0
    assert sold.json()["pnl_fee_calculation"]["amount"] == 7.5
    assert sold.json()["realized_pnl"] == 742.5
    after_first_sale = ledger.get_position(first.json()["position_id"])
    assert after_first_sale.quantity == 150
    assert after_first_sale.entry_price == 15.0
    assert ledger.get_sellable_quantity(
        symbol="510880.SH",
        trade_type=TradeType.simulated,
        record_source="autonomous_manual",
        execution_date=date(2026, 9, 10),
    ) == 50
    later_sell = manual_request(
        "sell",
        symbol="510880",
        execution_date="2026-09-11",
        position_id=first.json()["position_id"],
        price="30.00",
        quantity=50,
    )
    later_sale = post_manual(client, later_sell)
    assert later_sale.status_code == 200, later_sale.text
    assert later_sale.json()["gross_pnl_amount"] == 750.0
    assert later_sale.json()["pnl_fee_calculation"]["amount"] == 7.5
    assert later_sale.json()["realized_pnl"] == 742.5
    later_review = ledger.get_discipline_review(later_sale.json()["discipline_review_id"])
    assert later_review.buy_log_id is None
    assert later_review.buy_log_ids == [first.json()["log_id"], second.json()["log_id"]]
    assert later_review.plan_comparison["message"] == "多笔买入来源或理由不一致，无法按单一计划判断纪律"
    positions = ledger.list_open_positions()
    assert len(positions) == 1
    assert positions[0].position_id == first.json()["position_id"]
    assert positions[0].quantity == 100
    assert positions[0].entry_price == 15.0
    assert ledger.get_sellable_quantity(
        symbol="510880.SH",
        trade_type=TradeType.simulated,
        record_source="autonomous_manual",
        execution_date=date(2026, 9, 10),
    ) == 50
    assert ledger.get_sellable_quantity(
        symbol="510880.SH",
        trade_type=TradeType.simulated,
        record_source="autonomous_manual",
        execution_date=date(2026, 9, 11),
    ) == 100


def test_voiding_earlier_sale_reprices_later_review_and_blocks_buy_void(trade_app):
    app, ledger_path = trade_app
    client = TestClient(app)
    ledger = LiveTradeDB(ledger_path)
    first = post_manual(client, manual_request(
        "buy", symbol="510880", execution_date="2026-09-08", price="10", quantity=100,
    ))
    first_sale = post_manual(client, manual_request(
        "sell", symbol="510880", execution_date="2026-09-09", position_id=first.json()["position_id"],
        price="30", quantity=50,
    ))
    second = post_manual(client, manual_request(
        "buy", symbol="510880", execution_date="2026-09-10", price="20", quantity=100,
    ))
    second_sale = post_manual(client, manual_request(
        "sell", symbol="510880", execution_date="2026-09-11", position_id=first.json()["position_id"],
        price="30", quantity=50,
    ))
    assert first.status_code == first_sale.status_code == second.status_code == second_sale.status_code == 200
    assert second_sale.json()["gross_pnl_amount"] == pytest.approx(666.67)

    blocked_buy_void = client.post(
        f"/api/observations/execution-logs/{second.json()['log_id']}/void",
        json={"reason": "更正第二笔买入"},
    )
    assert blocked_buy_void.status_code == 409
    assert "成本计算" in blocked_buy_void.json()["detail"]
    assert ledger.get_log(second.json()["log_id"]).voided_at is None

    void_first_sale = client.post(
        f"/api/observations/execution-logs/{first_sale.json()['log_id']}/void",
        json={"reason": "更正历史卖出记录"},
    )
    assert void_first_sale.status_code == 200, void_first_sale.text
    refreshed = client.get("/api/observations?status=all").json()
    later_review = next(
        row for row in refreshed["discipline_reviews"]
        if row["sell_log_id"] == second_sale.json()["log_id"]
    )
    assert later_review["pnl_record"]["gross_pnl_amount"] == pytest.approx(750.0)
    assert ledger.get_position(first.json()["position_id"]).entry_price == 15.0


def test_same_day_sale_before_later_buy_keeps_the_recorded_cost_order(trade_app):
    app, ledger_path = trade_app
    client = TestClient(app)
    ledger = LiveTradeDB(ledger_path)
    first = post_manual(client, manual_request(
        "buy", symbol="510880", execution_date="2026-09-08", price="10", quantity=100,
    ))
    sale = post_manual(client, manual_request(
        "sell", symbol="510880", execution_date="2026-09-09", position_id=first.json()["position_id"],
        price="30", quantity=50,
    ))
    later_buy = post_manual(client, manual_request(
        "buy", symbol="510880", execution_date="2026-09-09", price="20", quantity=100,
    ))
    assert first.status_code == sale.status_code == later_buy.status_code == 200
    assert sale.json()["gross_pnl_amount"] == pytest.approx(1000.0)

    refreshed = client.get("/api/observations?status=all").json()
    review = next(row for row in refreshed["discipline_reviews"] if row["sell_log_id"] == sale.json()["log_id"])
    assert review["pnl_record"]["gross_pnl_amount"] == pytest.approx(1000.0)
    assert "不能核实实际成交先后" in review["same_day_event_order_note"]

    void_later_buy = client.post(
        f"/api/observations/execution-logs/{later_buy.json()['log_id']}/void",
        json={"reason": "同日后录入的买入不属于先前卖出成本"},
    )
    assert void_later_buy.status_code == 200, void_later_buy.text
    position = ledger.get_position(first.json()["position_id"])
    assert position.quantity == 50
    assert position.entry_price == pytest.approx(10.0)


def test_unknown_trade_type_history_is_visible_voidable_and_not_sellable(trade_app):
    app, ledger_path = trade_app
    client = TestClient(app)
    ledger = LiveTradeDB(ledger_path)
    with sqlite3.connect(ledger.db_path) as conn:
        conn.execute(
            """
            INSERT INTO execution_observation_logs (
                log_id, confirmed_action, confirmed_execution_status, confirmed_price,
                confirmed_quantity, confirmed_by_user, broker_verified, confirmed_at,
                execution_date, symbol, name, record_source, trade_type, operation_id,
                operation_fingerprint, confirmed_trade_amount, security_type, quantity_unit
            ) VALUES (?, 'buy', 'executed_full', 10, 100, 1, 0, ?, ?, ?, ?,
                      'autonomous_manual', 'unknown', ?, ?, '1000', 'unknown', 'unknown')
            """,
            ("log_unknown_legacy", "2026-09-10T09:00:00", "2026-09-10", "123456", "历史类型未确认",
             "unknown-op", "unknown-fingerprint"),
        )
    ledger.save_position(ObservationPosition(
        position_id="pos_unknown_legacy",
        source_log_id="log_unknown_legacy",
        symbol="123456",
        name="历史类型未确认",
        entry_price=10,
        quantity=100,
        template_id="manual_unlinked",
        template_version="v1",
        entry_thesis="历史记录",
        lifecycle_state=PositionLifecycleState.open,
        opened_at=datetime(2026, 9, 10, 9, 0),
        closed_at=None,
        record_source="autonomous_manual",
        trade_type=TradeType.unknown,
    ))

    response = client.get("/api/observations?status=open")
    assert response.status_code == 200, response.text
    assert response.json()["positions"][0]["trade_type"] == "unknown"
    assert response.json()["positions"][0]["sellable_quantity"] == 0
    assert any(row["log_id"] == "log_unknown_legacy" for row in response.json()["execution_logs"])
    assert ledger.get_sellable_quantity(
        symbol="123456", trade_type=TradeType.unknown,
        record_source="autonomous_manual", execution_date=date(2026, 9, 11),
    ) == 0

    voided = client.post(
        "/api/observations/execution-logs/log_unknown_legacy/void",
        json={"reason": "历史类型无法确认"},
    )
    assert voided.status_code == 200, voided.text
    listed = client.get("/api/observations?status=all").json()
    unknown_row = next(row for row in listed["execution_logs"] if row["log_id"] == "log_unknown_legacy")
    assert unknown_row["voided"] is True
    assert unknown_row["void_reason"] == "历史类型无法确认"
    assert listed["positions"][0]["sellable_quantity"] == 0


def test_unmatched_and_oversell_events_are_rejected_without_writes(trade_app):
    app, ledger_path = trade_app
    client = TestClient(app)
    unmatched = post_manual(client, manual_request("sell", trade_type="actual"))
    assert unmatched.status_code == 422

    ledger = LiveTradeDB(ledger_path)
    assert ledger.list_execution_logs() == []
    assert ledger.list_discipline_reviews() == []

    buy = post_manual(client, manual_request("buy", trade_type="actual"))
    oversell = manual_request(
        "sell", trade_type="actual", execution_date="2026-09-11",
        position_id=buy.json()["position_id"], quantity=150,
    )
    sold = post_manual(client, oversell)

    assert sold.status_code == 400
    assert "补录遗漏的买入记录" in sold.json()["detail"]
    assert len(ledger.list_execution_logs()) == 1
    assert ledger.list_discipline_reviews() == []
    assert LiveTradeDB(ledger_path).get_position(buy.json()["position_id"]).quantity == 100


def test_market_check_route_passes_only_open_typed_positions_to_monitor(trade_app, monkeypatch):
    app, _ = trade_app
    client = TestClient(app)
    bought = post_manual(client, manual_request("buy", trade_type="simulated"))
    assert bought.status_code == 200, bought.text

    class RecordingMonitor:
        calls = []

        def check_positions(self, positions, *, session_id):
            self.calls.append((positions, session_id))
            return {"session_id": session_id, "items": []}

    monitor = RecordingMonitor()
    monkeypatch.setattr(
        "backend.api.observations.get_position_market_monitor",
        lambda: monitor,
    )

    response = client.post(
        "/api/observations/market-check",
        json={"session_id": "browser-session-012345"},
    )

    assert response.status_code == 200, response.text
    assert response.json() == {"session_id": "browser-session-012345", "items": []}
    assert len(monitor.calls) == 1
    paired = monitor.calls[0][0]
    assert len(paired) == 1
    assert paired[0][0].trade_type.value == "simulated"
    assert paired[0][1].trade_type.value == "simulated"


def test_manual_trade_uses_single_sessionless_action_without_workbench_session(trade_app):
    app, ledger_path = trade_app
    client = TestClient(app)
    request = manual_request("buy")

    first = post_manual(client, request)
    retry = post_manual(client, request)

    assert first.status_code == 200, first.text
    assert retry.status_code == 200, retry.text
    assert retry.json() == first.json()
    assert first.json()["record_source"] == "autonomous_manual"
    assert first.json()["plan_linked"] is False
    assert first.json()["fees"] is None
    assert first.json()["execution_date"] == request["execution_date"]
    assert "conversation_id" not in first.json()
    assert "session_id" not in first.json()

    ledger = LiveTradeDB(ledger_path)
    positions = ledger.list_open_positions()
    assert len(positions) == 1
    assert positions[0].execution_card_id is None
    assert positions[0].signal_id is None
    assert positions[0].action_plan_id is None
    with ledger._get_conn() as conn:
        assert conn.execute("SELECT COUNT(*) FROM execution_observation_logs").fetchone()[0] == 1
    assert app.state.db.conn.execute("SELECT COUNT(*) FROM agent_sessions").fetchone()[0] == 0
    assert app.state.db.conn.execute("SELECT COUNT(*) FROM agent_messages").fetchone()[0] == 0


def test_manual_trade_requires_confirmation(trade_app):
    app, ledger_path = trade_app
    client = TestClient(app)
    request = manual_request("buy")
    request["confirmed_already_executed"] = False

    response = post_manual(client, request)

    assert response.status_code == 400
    assert LiveTradeDB(ledger_path).list_all_positions() == []


def test_manual_trade_rejects_ledger_overrides(trade_app):
    app, ledger_path = trade_app
    client = TestClient(app)
    request = manual_request("buy")
    request["ledger_path"] = str(ledger_path.parent / "override.db")

    response = post_manual(client, request)

    assert response.status_code == 422
    assert LiveTradeDB(ledger_path).list_all_positions() == []
    assert not (ledger_path.parent / "override.db").exists()


def test_manual_trade_write_is_available_only_on_the_sessionless_card002_route(trade_app):
    app, ledger_path = trade_app
    client = TestClient(app)
    request = manual_request("buy")

    assert client.post("/api/manual/execution-feedback", json=request).status_code == 404
    assert client.post(
        "/api/agent/workbench/conv_card002/execution-feedback", json=request
    ).status_code == 404
    assert LiveTradeDB(ledger_path).list_all_positions() == []

    response = post_manual(client, request)
    assert response.status_code == 200, response.text


def test_manual_trade_requires_an_explicit_execution_date(trade_app):
    app, ledger_path = trade_app
    client = TestClient(app)
    request = manual_request("buy")
    request.pop("execution_date")

    response = post_manual(client, request)

    assert response.status_code == 422
    assert LiveTradeDB(ledger_path).list_all_positions() == []


def test_manual_buy_is_idempotent_and_uses_canonical_unlinked_ledger(trade_app):
    app, ledger_path = trade_app
    client = TestClient(app)
    request = manual_request("buy")

    first = post_manual(client, request)
    retry = post_manual(client, request)

    assert first.status_code == 200, first.text
    assert retry.status_code == 200, retry.text
    assert retry.json() == first.json()
    assert first.json()["record_source"] == "autonomous_manual"
    assert first.json()["plan_linked"] is False
    assert first.json()["fees"] is None
    assert first.json()["execution_date"] == request["execution_date"]
    assert first.json()["realized_pnl"] is None
    assert any("T+1" in warning for warning in first.json()["warnings"])

    separate_trade = post_manual(client, manual_request("buy"))
    assert separate_trade.status_code == 200, separate_trade.text
    assert separate_trade.json()["log_id"] != first.json()["log_id"]
    conflicting_retry = dict(request)
    conflicting_retry["price"] = "11.00"
    assert post_manual(client, conflicting_retry).status_code == 409
    date_conflict = dict(request)
    date_conflict["execution_date"] = "2026-09-11"
    assert post_manual(client, date_conflict).status_code == 409

    reopened_db = LiveTradeDB(ledger_path)
    positions = reopened_db.list_open_positions()
    assert len(positions) == 2
    assert positions[0].execution_card_id is None
    assert positions[0].signal_id is None
    assert positions[0].action_plan_id is None
    assert positions[0].capital_context_id is None
    with reopened_db._get_conn() as conn:
        assert conn.execute("SELECT COUNT(*) FROM execution_observation_logs").fetchone()[0] == 2
        row = conn.execute(
            "SELECT operation_id, confirmed_fees, record_source, execution_date FROM execution_observation_logs"
            " WHERE operation_id = ?",
            (request["operation_id"],),
        ).fetchone()
    assert row["operation_id"] == request["operation_id"]
    assert row["confirmed_fees"] is None
    assert row["record_source"] == "autonomous_manual"
    assert row["execution_date"] == request["execution_date"]
    observation_payload = client.get("/api/observations?status=open").json()
    observations = observation_payload["positions"]
    assert len(observations) == 2
    assert all(item["record_source"] == "autonomous_manual" for item in observations)
    assert all(item["plan_linked"] is False for item in observations)
    assert observation_payload["execution_logs"][0]["execution_date"] == request["execution_date"]


def test_legacy_unmatched_sell_is_readable_in_existing_observation_list(trade_app):
    app, ledger_path = trade_app
    client = TestClient(app)
    LiveTradeDB(ledger_path)
    with sqlite3.connect(ledger_path) as conn:
        conn.execute(
            """
            INSERT INTO execution_observation_logs (
                log_id, confirmed_action, confirmed_execution_status, confirmed_price,
                confirmed_quantity, reason, confirmed_by_user, broker_verified, confirmed_at,
                execution_date, confirmed_fees, symbol, name, record_source, trade_type,
                operation_id, operation_fingerprint, confirmed_trade_amount,
                security_type, quantity_unit, sell_reason
            ) VALUES (?, 'sell', 'executed_full', 12, 100, '历史孤立卖出', 1, 0, ?, ?,
                      2.5, '600000.SH', '浦发银行', 'autonomous_manual', 'actual',
                      'legacy-unmatched-operation', 'legacy-unmatched-fingerprint',
                      '1200', 'stock', 'share', 'target')
            """,
            ("log_legacy_unmatched_sell", "2026-09-11T10:00:00", "2026-09-11"),
        )

    listed = client.get("/api/observations?status=all")
    assert listed.status_code == 200, listed.text
    payload = listed.json()
    assert payload["positions"] == []
    assert len(payload["execution_logs"]) == 1
    log = payload["execution_logs"][0]
    assert log["execution_date"] == "2026-09-11"
    assert log["recorded_at"] and log["recorded_at"] != log["execution_date"]
    assert log["confirmed_action"] == "sell"
    assert log["confirmed_price"] == 12.0
    assert log["confirmed_quantity"] == 100
    assert log["confirmed_fees"] == 2.5
    assert log["record_source"] == "autonomous_manual"
    assert log["plan_linked"] is False


def test_manual_sell_keeps_actual_blank_fees_unknown_and_explicit_zero_is_numeric(trade_app):
    app, ledger_path = trade_app
    client = TestClient(app)
    db = LiveTradeDB(ledger_path)

    unknown_buy = post_manual(client, manual_request("buy", trade_type="actual"))
    unknown_sell = post_manual(client, manual_request(
        "sell", trade_type="actual", position_id=unknown_buy.json()["position_id"],
    ))
    assert unknown_buy.status_code == 200, unknown_buy.text
    assert unknown_sell.status_code == 200, unknown_sell.text
    assert unknown_sell.json()["fees"] is None
    assert unknown_sell.json()["realized_pnl"] is None
    assert unknown_sell.json()["pnl_fee_calculation"]["source"] == "unknown"
    review = db.get_discipline_review(unknown_sell.json()["discipline_review_id"])
    assert review.pnl_record.pnl_amount is None
    assert review.pnl_record.fees is None
    assert "fees" in review.pnl_record.missing_fields
    assert review.pnl_record.gross_pnl_amount == 200.0
    assert review.pnl_record.gross_pnl_pct == 0.2
    assert "毛盈亏 +¥200.00（+20.00%）" in review.deterministic_summary
    assert review.ai_review_status == "unavailable"
    assert unknown_sell.json()["gross_pnl_amount"] == 200.0
    assert unknown_sell.json()["gross_pnl_pct"] == 0.2
    assert review.plan_adherence.followed_plan is None
    assert review.input_completeness["action_plan"] == "missing"
    assert review.holding_days == 1
    assert review.dividend_status == "unverified"
    assert review.plan_comparison["message"] == "无事前计划，无法判断纪律"


def test_observation_get_projects_gross_for_legacy_manual_review_without_writing(trade_app):
    app, ledger_path = trade_app
    client = TestClient(app)

    bought = post_manual(client, manual_request("buy", fees=None))
    sold = post_manual(client, manual_request(
        "sell", fees=None, position_id=bought.json()["position_id"],
    ))
    assert bought.status_code == 200, bought.text
    assert sold.status_code == 200, sold.text

    review_id = sold.json()["discipline_review_id"]
    with sqlite3.connect(ledger_path) as conn:
        row = conn.execute(
            "SELECT review_json FROM discipline_reviews WHERE review_id = ?", (review_id,)
        ).fetchone()
        legacy_review = json.loads(row[0])
        legacy_review.pop("deterministic_summary", None)
        legacy_review.pop("ai_review_status", None)
        legacy_review.pop("ai_review_text", None)
        legacy_review["pnl_record"].pop("gross_pnl_amount", None)
        legacy_review["pnl_record"].pop("gross_pnl_pct", None)
        conn.execute(
            "UPDATE discipline_reviews SET review_json = ? WHERE review_id = ?",
            (json.dumps(legacy_review), review_id),
        )
        conn.commit()
        before = conn.execute(
            "SELECT review_json FROM discipline_reviews WHERE review_id = ?", (review_id,)
        ).fetchone()[0]

    listed = client.get("/api/observations?status=all")
    assert listed.status_code == 200, listed.text
    projected = next(
        item for item in listed.json()["discipline_reviews"] if item["review_id"] == review_id
    )
    assert projected["pnl_record"]["gross_pnl_amount"] == 200.0
    assert projected["pnl_record"]["gross_pnl_pct"] == 0.2
    assert "毛盈亏 +¥200.00（+20.00%）" in projected["deterministic_summary"]

    with sqlite3.connect(ledger_path) as conn:
        after = conn.execute(
            "SELECT review_json FROM discipline_reviews WHERE review_id = ?", (review_id,)
        ).fetchone()[0]
    assert after == before


def test_explicit_zero_fees_are_not_treated_as_unknown(trade_app):
    app, ledger_path = trade_app
    client = TestClient(app)
    explicit_zero_buy = post_manual(client, manual_request("buy", fees=0, trade_type="actual"))
    explicit_zero_sell = post_manual(client, manual_request(
        "sell", fees=0, trade_type="actual", position_id=explicit_zero_buy.json()["position_id"],
    ))
    assert explicit_zero_buy.status_code == 200, explicit_zero_buy.text
    assert explicit_zero_sell.status_code == 200, explicit_zero_sell.text
    assert explicit_zero_sell.json()["fees"] == 0
    assert explicit_zero_sell.json()["realized_pnl"] == 200
    assert LiveTradeDB(ledger_path).get_discipline_review(
        explicit_zero_sell.json()["discipline_review_id"]
    ).pnl_record.fees == 0


def test_simulated_fund_blank_fees_estimate_but_remain_unconfirmed(trade_app):
    app, ledger_path = trade_app
    client = TestClient(app)
    db = LiveTradeDB(ledger_path)
    buy_request = manual_request(
        "buy", symbol="510880", trade_type="simulated", execution_date="2026-09-30"
    )
    buy_request.update({"price": "3.368", "quantity": 1000})
    sell_request = manual_request(
        "sell", symbol="510880", trade_type="simulated", execution_date="2026-10-08"
    )
    sell_request.update({"price": "3.416", "quantity": 1000})

    buy_response = post_manual(client, buy_request)
    assert buy_response.status_code == 200, buy_response.text
    sell_request["position_id"] = buy_response.json()["position_id"]
    sell_response = post_manual(client, sell_request)

    assert sell_response.status_code == 200, sell_response.text
    assert buy_response.json()["fees"] is None
    assert buy_response.json()["fee_calculation"]["source"] == "simulated_estimate"
    assert buy_response.json()["fee_calculation"]["amount"] == 5.0
    assert sell_response.json()["fees"] is None
    assert sell_response.json()["fee_calculation"]["amount"] == 5.0
    assert sell_response.json()["pnl_fee_calculation"]["source"] == "simulated_estimate"
    assert sell_response.json()["pnl_fee_calculation"]["amount"] == 10.0
    assert sell_response.json()["pnl_fee_calculation"]["stamp_duty"] == 0.0
    assert sell_response.json()["gross_pnl_amount"] == 48.0
    assert sell_response.json()["realized_pnl"] == 38.0
    assert sell_response.json()["pnl_source"] == "calculated_with_fee_estimate"
    review = db.get_discipline_review(sell_response.json()["discipline_review_id"])
    assert review.pnl_record.fee_calculation.source == "simulated_estimate"
    assert review.pnl_record.fees == 10.0
    assert review.pnl_record.pnl_amount == 38.0
    logs = {row["log_id"]: row for row in db.list_execution_logs()}
    assert logs[buy_response.json()["log_id"]]["confirmed_fees"] is None
    assert logs[sell_response.json()["log_id"]]["confirmed_fees"] is None

    listed = client.get("/api/observations?status=all")
    assert listed.status_code == 200, listed.text
    projected_logs = {row["log_id"]: row for row in listed.json()["execution_logs"]}
    assert projected_logs[buy_response.json()["log_id"]]["fee_calculation"]["source"] == "simulated_estimate"
    assert projected_logs[buy_response.json()["log_id"]]["confirmed_fees"] is None


def test_discipline_review_migration_preserves_existing_rows(tmp_path):
    ledger_path = tmp_path / "legacy_reviews.db"
    legacy_json = '{"review_id":"review_legacy","sell_log_id":"log_legacy"}'
    with sqlite3.connect(ledger_path) as conn:
        conn.execute(
            "CREATE TABLE discipline_reviews ("
            "review_id TEXT PRIMARY KEY, position_id TEXT NOT NULL, execution_card_id TEXT, "
            "signal_id TEXT, review_json TEXT NOT NULL, created_at TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO discipline_reviews VALUES (?, ?, ?, ?, ?, ?)",
            ("review_legacy", "pos_legacy", None, None, legacy_json, "2026-01-02T03:04:05"),
        )

    LiveTradeDB(ledger_path)

    with sqlite3.connect(ledger_path) as conn:
        columns = {row[1]: row for row in conn.execute("PRAGMA table_info(discipline_reviews)")}
        row = conn.execute("SELECT * FROM discipline_reviews WHERE review_id = ?", ("review_legacy",)).fetchone()
    assert columns["position_id"][3] == 0
    assert "sell_log_id" in columns
    assert row[0:4] == ("review_legacy", "pos_legacy", None, None)
    assert row[4] == legacy_json
    assert row[5] == "2026-01-02T03:04:05"
    assert row[6] == "log_legacy"


def test_security_identity_lookup_distinguishes_fund_from_stock(trade_app):
    app, _ = trade_app
    client = TestClient(app)

    fund = client.get("/api/agent/workbench/security-identity/510880")
    stock = client.get("/api/agent/workbench/security-identity/600000")

    assert fund.status_code == 200
    assert fund.json() == {
        "status": "verified",
        "symbol": "510880.SH",
        "name": "上证红利ETF",
        "security_type": "fund",
        "quantity_unit": "fund_share",
        "data_source": "deterministic_fixture",
    }
    assert stock.json()["security_type"] == "stock"
    assert stock.json()["quantity_unit"] == "share"


def test_structured_execution_uses_decimal_amount_and_persists_personal_retrospective_plan(trade_app):
    app, ledger_path = trade_app
    client = TestClient(app)
    request = manual_request("buy")
    request.update({
        "price": "3.215",
        "quantity": 2000,
        "fees": None,
        "exit_plan_target_price": "3.600",
        "exit_plan_stop_price": "3.000",
        "exit_plan_conditions": "跌破支撑后重新评估",
    })

    response = post_manual(client, request)

    assert response.status_code == 200, response.text
    assert response.json()["trade_amount"] == "6430.000"
    log = LiveTradeDB(ledger_path).get_log(response.json()["log_id"])
    assert log.confirmed_price == 3.215
    assert log.confirmed_quantity == 2000
    assert log.confirmed_trade_amount == "6430.000"
    assert log.confirmed_fees is None
    assert log.trade_source == "self_research"
    assert log.exit_plan_target_price == 3.6
    assert log.exit_plan_stop_price == 3.0
    assert log.exit_plan_conditions == "跌破支撑后重新评估"
    assert log.exit_plan_entered_at is not None
    assert log.exit_plan_is_retrospective is True
    assert log.action_plan_id is None

    listed = client.get("/api/observations?status=open").json()["execution_logs"][0]
    assert listed["trade_amount"] == "6430.000"
    assert listed["quantity_unit"] == "share"
    assert listed["exit_plan_is_retrospective"] is True


def test_buy_saves_core_facts_when_all_optional_fields_are_blank(trade_app):
    app, ledger_path = trade_app
    client = TestClient(app)
    request = manual_request("buy")
    request.pop("trade_source")
    request.pop("reason")

    response = post_manual(client, request)

    assert response.status_code == 200, response.text
    ledger = LiveTradeDB(ledger_path)
    log = ledger.get_log(response.json()["log_id"])
    assert log.reason is None
    assert log.trade_source is None
    assert log.confirmed_fees is None
    assert log.action_plan_id is None
    assert log.exit_plan_entered_at is None
    listed = client.get("/api/observations?status=open").json()["execution_logs"][0]
    assert listed["reason"] is None
    assert listed["trade_source"] is None
    assert listed["confirmed_fees"] is None
    assert listed["plan_linked"] is False


def test_unverified_security_name_is_unknown_without_rejecting_completed_trade(trade_app):
    app, ledger_path = trade_app
    client = TestClient(app)
    request = manual_request("buy")
    request["symbol"] = "123456"

    identity = client.get("/api/agent/workbench/security-identity/123456")
    response = post_manual(client, request)

    assert identity.status_code == 200
    assert identity.json()["status"] == "unknown"
    assert identity.json()["name"] is None
    assert identity.json()["security_type"] == "unknown"
    assert response.status_code == 200, response.text
    log = LiveTradeDB(ledger_path).get_log(response.json()["log_id"])
    assert log.symbol == "123456.SZ"
    assert log.name == "名称未知"
    assert log.quantity_unit == "unknown"


def test_stock_buy_anomalous_quantity_requires_ack_but_odd_lot_sell_is_recorded(trade_app):
    app, ledger_path = trade_app
    client = TestClient(app)
    buy = manual_request("buy")
    buy["quantity"] = 150

    unacknowledged = post_manual(client, buy)
    assert unacknowledged.status_code == 400
    assert "100" in unacknowledged.json()["detail"]
    assert LiveTradeDB(ledger_path).list_execution_logs() == []

    buy["confirm_quantity_anomaly"] = True
    accepted_buy = post_manual(client, buy)
    assert accepted_buy.status_code == 200, accepted_buy.text
    assert any("100" in warning for warning in accepted_buy.json()["warnings"])

    sell = manual_request("sell", position_id=accepted_buy.json()["position_id"])
    sell["quantity"] = 50
    accepted_sell = post_manual(client, sell)
    assert accepted_sell.status_code == 200, accepted_sell.text
    assert accepted_sell.json()["action"] == "sell"


def test_structured_fields_are_part_of_idempotency_fingerprint(trade_app):
    app, _ = trade_app
    client = TestClient(app)
    request = manual_request("buy")
    request["exit_plan_target_price"] = "12.00"

    first = post_manual(client, request)
    changed_plan = dict(request)
    changed_plan["exit_plan_target_price"] = "13.00"
    changed_source = dict(request)
    changed_source["trade_source"] = "friend"

    assert first.status_code == 200, first.text
    assert post_manual(client, changed_plan).status_code == 409
    assert post_manual(client, changed_source).status_code == 409


def test_idempotent_retry_returns_original_identity_when_lookup_later_fails(trade_app):
    app, _ = trade_app
    client = TestClient(app)
    request = manual_request("buy")
    first = post_manual(client, request)
    assert first.status_code == 200, first.text
    assert first.json()["security_identity_status"] == "verified"

    app.state.manual_security_cache.clear()
    app.state.manual_security_identity_fixture.fail_lookup = True
    retry = post_manual(client, request)

    assert retry.status_code == 200, retry.text
    assert retry.json() == first.json()
    logs = client.get("/api/observations?status=open").json()["execution_logs"]
    assert len(logs) == 1
    assert logs[0]["name"] == "浦发银行"
    assert logs[0]["security_type"] == "stock"


def test_daily_signal_reports_unavailable_without_synthetic_quote(trade_app):
    app, ledger_path = trade_app
    client = TestClient(app)
    buy = post_manual(client, manual_request("buy"))
    assert buy.status_code == 200, buy.text

    response = client.post("/api/agent/workbench/conv_card002/daily-signal")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "market_data_unavailable"
    assert response.json()["signals"] == []
    with LiveTradeDB(ledger_path)._get_conn() as conn:
        assert conn.execute("SELECT COUNT(*) FROM daily_observation_signals").fetchone()[0] == 0


@pytest.mark.parametrize("existing_session", [False, True])
def test_workbench_trade_intent_does_not_write_business_ledger(trade_app, existing_session):
    app, ledger_path = trade_app
    client = TestClient(app)
    conversation_id = None
    if existing_session:
        initial = client.post("/api/agent/workbench/message", json={"message": "你好"})
        assert initial.status_code == 200, initial.text
        conversation_id = initial.json()["conversation_id"]

    request = {"message": "我已经买入浦发银行 100 股，成交价 10 元"}
    if conversation_id:
        request["conversation_id"] = conversation_id
    response = client.post("/api/agent/workbench/message", json=request)

    assert response.status_code == 200, response.text
    assert "暂不支持，请在页面记录" in response.json()["agent_reply"]
    assert LiveTradeDB(ledger_path).list_all_positions() == []
    with LiveTradeDB(ledger_path)._get_conn() as conn:
        assert conn.execute("SELECT COUNT(*) FROM execution_observation_logs").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM discipline_reviews").fetchone()[0] == 0


def test_legacy_ledger_migration_preserves_existing_rows_and_unlinks_new_manual_refs(tmp_path):
    ledger_path = tmp_path / "legacy-live-trade.db"
    conn = sqlite3.connect(ledger_path)
    conn.executescript("""
        CREATE TABLE execution_observation_logs (
            log_id TEXT PRIMARY KEY, draft_id TEXT NOT NULL, execution_card_id TEXT NOT NULL,
            signal_id TEXT NOT NULL, action_plan_id TEXT NOT NULL, capital_context_id TEXT NOT NULL,
            market_snapshot_id TEXT NOT NULL, confirmed_action TEXT NOT NULL,
            confirmed_execution_status TEXT NOT NULL, confirmed_price REAL, confirmed_quantity INTEGER,
            reason TEXT, confirmed_by_user INTEGER NOT NULL, broker_verified INTEGER NOT NULL,
            confirmed_at TEXT NOT NULL
        );
        CREATE TABLE observation_positions (
            position_id TEXT PRIMARY KEY, source_log_id TEXT NOT NULL, execution_card_id TEXT NOT NULL,
            signal_id TEXT NOT NULL, action_plan_id TEXT NOT NULL, capital_context_id TEXT NOT NULL,
            symbol TEXT NOT NULL, name TEXT NOT NULL, entry_price REAL NOT NULL, quantity INTEGER NOT NULL,
            template_id TEXT NOT NULL, template_version TEXT NOT NULL, entry_thesis TEXT NOT NULL,
            lifecycle_state TEXT NOT NULL, opened_at TEXT NOT NULL, closed_at TEXT
        );
        CREATE TABLE discipline_reviews (
            review_id TEXT PRIMARY KEY, position_id TEXT NOT NULL, execution_card_id TEXT NOT NULL,
            signal_id TEXT NOT NULL, review_json TEXT NOT NULL, created_at TEXT NOT NULL
        );
        INSERT INTO execution_observation_logs VALUES (
            'old-log', 'old-draft', 'old-card', 'old-signal', 'old-plan', 'old-capital', 'old-snapshot',
            'buy', 'executed_full', 10.0, 100, NULL, 1, 0, '2026-01-01T00:00:00'
        );
        INSERT INTO observation_positions VALUES (
            'old-position', 'old-log', 'old-card', 'old-signal', 'old-plan', 'old-capital',
            '600000.SH', '浦发银行', 10.0, 100, 'legacy-template', 'v1', 'legacy thesis',
            'open', '2026-01-01T00:00:00', NULL
        );
        INSERT INTO discipline_reviews VALUES (
            'old-review', 'old-position', 'old-card', 'old-signal', '{"preserved":true}', '2026-01-02T00:00:00'
        );
    """)
    conn.commit()
    conn.close()

    LiveTradeDB(ledger_path)
    db = LiveTradeDB(ledger_path)
    with db._get_conn() as migrated:
        assert migrated.execute("SELECT COUNT(*) FROM execution_observation_logs").fetchone()[0] == 1
        assert migrated.execute("SELECT action_plan_id FROM execution_observation_logs").fetchone()[0] == "old-plan"
        assert migrated.execute("SELECT execution_date FROM execution_observation_logs").fetchone()[0] is None
        assert tuple(migrated.execute("SELECT security_type, quantity_unit FROM execution_observation_logs").fetchone()) == ("unknown", "unknown")
        assert tuple(migrated.execute("SELECT trade_source, exit_plan_is_retrospective FROM execution_observation_logs").fetchone()) == (None, None)
        assert migrated.execute("SELECT COUNT(*) FROM observation_positions").fetchone()[0] == 1
        assert migrated.execute("SELECT review_json FROM discipline_reviews").fetchone()[0] == '{"preserved":true}'
        assert migrated.execute(
            "SELECT record_source FROM observation_positions WHERE position_id='old-position'"
        ).fetchone()[0] == "strategy_plan"
        assert {row[1]: row[3] for row in migrated.execute(
            "PRAGMA table_info(execution_observation_logs)"
        )}["action_plan_id"] == 0
        assert migrated.execute(
            "SELECT trade_type FROM execution_observation_logs WHERE log_id='old-log'"
        ).fetchone()[0] == "unknown"
        assert migrated.execute(
            "SELECT trade_type FROM observation_positions WHERE position_id='old-position'"
        ).fetchone()[0] == "unknown"


def test_trade_type_migration_preserves_existing_structured_execution_fields(tmp_path):
    ledger_path = tmp_path / "structured-legacy-live-trade.db"
    conn = sqlite3.connect(ledger_path)
    conn.executescript("""
        CREATE TABLE execution_observation_logs (
            log_id TEXT PRIMARY KEY, draft_id TEXT, execution_card_id TEXT, signal_id TEXT,
            action_plan_id TEXT, capital_context_id TEXT, market_snapshot_id TEXT,
            confirmed_action TEXT NOT NULL, confirmed_execution_status TEXT NOT NULL,
            confirmed_price REAL, confirmed_quantity INTEGER, reason TEXT,
            confirmed_by_user INTEGER NOT NULL, broker_verified INTEGER NOT NULL,
            confirmed_at TEXT NOT NULL, execution_date TEXT, confirmed_fees REAL,
            symbol TEXT, name TEXT, record_source TEXT, operation_id TEXT,
            operation_fingerprint TEXT, operation_response TEXT, confirmed_trade_amount TEXT,
            security_type TEXT, quantity_unit TEXT, trade_source TEXT, sell_reason TEXT,
            exit_plan_target_price REAL, exit_plan_stop_price REAL, exit_plan_conditions TEXT,
            exit_plan_entered_at TEXT, exit_plan_is_retrospective INTEGER
        );
        INSERT INTO execution_observation_logs VALUES (
            'structured-log', NULL, NULL, NULL, NULL, NULL, NULL,
            'buy', 'executed_full', 3.409, 500, 'manual', 1, 0,
            '2026-10-08T10:07:00', '2026-10-08', NULL, '510880.SH', '上证红利ETF',
            'autonomous_manual', 'op-1', 'old-fingerprint', '{"old":true}', '1704.500',
            'fund', 'fund_share', 'self_research', NULL, 3.8, 3.2, 'plan',
            '2026-10-08T10:07:00', 1
        );
    """)
    conn.commit()
    conn.close()

    db = LiveTradeDB(ledger_path)
    with db._get_conn() as migrated:
        row = migrated.execute(
            "SELECT trade_type, confirmed_trade_amount, security_type, quantity_unit, "
            "trade_source, exit_plan_target_price, operation_fingerprint, operation_response "
            "FROM execution_observation_logs WHERE log_id='structured-log'"
        ).fetchone()
        assert tuple(row) == (
            "unknown", "1704.500", "fund", "fund_share", "self_research", 3.8,
            "old-fingerprint", '{"old":true}',
        )
