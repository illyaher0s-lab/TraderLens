from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

import pytest

from backend.services.card020_vol_budget import (
    EXPECTED_PATHS,
    PREHEAT_END,
    _curve_metrics,
    _classify,
    _shown,
    _risk_candidate_has_filled_rebalance,
    _reconcile_path,
    run_card020_validation,
)


class FakeBar:
    def __init__(self, day: date, open_price: Decimal, close: Decimal):
        self.date = day
        self.symbol = "510880.SH"
        self.open = float(open_price)
        self.close = float(close)
        self.high = float(max(open_price, close) + Decimal("0.010"))
        self.low = float(min(open_price, close) - Decimal("0.010"))
        self.volume = 2_000_000
        self.amount = float(close * self.volume)
        self.adj_factor = 1.0


class FakeStatus:
    def __init__(self, *, is_suspended=False, is_limit_up=False, is_limit_down=False):
        self.is_suspended = is_suspended
        self.is_limit_up = is_limit_up
        self.is_limit_down = is_limit_down


class FakeMarket:
    def __init__(self, *, block_first_session=False):
        days = []
        current = date(2016, 12, 23)
        end = date(2020, 12, 31)
        while current <= end:
            if current.weekday() < 5:
                days.append(current)
            current += timedelta(days=1)
        price = Decimal("3.500")
        self.bars = {}
        self.statuses = {}
        self.limits = {}
        for index, day in enumerate(days):
            raw_open = price
            step = (Decimal("0.025"), Decimal("-0.021"), Decimal("0.008"), Decimal("-0.006"))[index % 4]
            price = (price * (Decimal(1) + step)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
            if price <= 0:
                price = Decimal("0.100")
            self.bars[day] = FakeBar(day, raw_open, price)
            self.statuses[day] = FakeStatus(
                is_suspended=block_first_session and day == date(2018, 1, 2),
            )
            self.limits[day] = (
                (raw_open * Decimal("0.9")).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP),
                (raw_open * Decimal("1.1")).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP),
            )

    def symbols(self):
        return ["510880.SH"]

    def get_daily_bars(self, symbol):
        assert symbol == "510880.SH"
        return list(self.bars.values())

    def get_daily_bar(self, symbol, day):
        assert symbol == "510880.SH"
        return self.bars[day]

    def get_daily_status(self, symbol, day):
        assert symbol == "510880.SH"
        return self.statuses[day]

    def get_daily_price_limits(self, symbol, day):
        assert symbol == "510880.SH"
        return self.limits[day]


def test_initial_capacity_retries_do_not_count_as_dynamic_risk_rebalancing():
    later_fill_from_initial_target = [{
        "intent_type": "initial_build", "dynamic_risk_change": False,
        "source_target_date": PREHEAT_END.isoformat(), "actual_quantity": 100,
        "execution_date": "2018-02-01",
    }]
    mislabeled_old_target = [{
        "intent_type": "monthly_rebalance", "dynamic_risk_change": True,
        "source_target_date": PREHEAT_END.isoformat(), "actual_quantity": 100,
        "execution_date": "2018-02-01",
    }]
    actual_later_target_fill = [{
        "intent_type": "monthly_rebalance", "dynamic_risk_change": False,
        "source_target_date": "2018-02-28", "actual_quantity": 100,
        "execution_date": "2018-03-01",
    }]

    assert not _risk_candidate_has_filled_rebalance(later_fill_from_initial_target)
    assert not _risk_candidate_has_filled_rebalance(mislabeled_old_target)
    assert _risk_candidate_has_filled_rebalance(actual_later_target_fill)


def _classification_metric(end: str, drawdown_amount: str, drawdown_ratio: str) -> dict:
    return {"decision_values": {
        "evaluation_end_nav_cny": end,
        "max_drawdown_amount_evaluation_cny": drawdown_amount,
        "max_drawdown_ratio": drawdown_ratio,
    }}


def _classification_paths() -> dict:
    paths = {}
    for account in ("candidate", "buy_and_hold", "static_half"):
        for cost in ("base", "stress"):
            if account == "candidate":
                full = _classification_metric("110", "10", "0.1")
                segment = _classification_metric("100", "10", "0.1")
            elif account == "buy_and_hold":
                full = _classification_metric("100", "20", "0.2")
                segment = _classification_metric("90", "20", "0.2")
            else:
                full = _classification_metric("90", "30", "0.3")
                segment = _classification_metric("80", "30", "0.3")
            paths[f"{account}-{cost}"] = {
                "has_post_build_dynamic_risk_fill": True,
                "metrics": {"full": full, "2018-2019": segment, "2020": segment.copy()},
            }
    return paths


@pytest.mark.parametrize(
    ("case", "expected_category"),
    [
        ("D_precedes_other_rules", "D"),
        ("no_post_build_fill", "C"),
        ("same_comparator_dominates_both_costs", "C"),
        ("different_comparators_do_not_combine", "B"),
        ("one_segment_blocks_A", "B"),
        ("all_A_conditions_hold", "A"),
        ("unrounded_decimal_values_drive_classification", "A"),
    ],
)
def test_card020_frozen_category_rules(case, expected_category):
    paths = _classification_paths()
    gaps = []
    reconciled = True
    if case == "D_precedes_other_rules":
        paths["candidate-base"]["has_post_build_dynamic_risk_fill"] = False
        gaps = ["实质数据问题"]
        reconciled = False
    elif case == "no_post_build_fill":
        paths["candidate-base"]["has_post_build_dynamic_risk_fill"] = False
        paths["candidate-stress"]["has_post_build_dynamic_risk_fill"] = False
    elif case == "same_comparator_dominates_both_costs":
        for cost in ("base", "stress"):
            paths[f"buy_and_hold-{cost}"]["metrics"]["full"] = _classification_metric("120", "5", "0.05")
    elif case == "different_comparators_do_not_combine":
        paths["buy_and_hold-base"]["metrics"]["full"] = _classification_metric("120", "5", "0.05")
        paths["static_half-stress"]["metrics"]["full"] = _classification_metric("120", "5", "0.05")
    elif case == "one_segment_blocks_A":
        paths["buy_and_hold-base"]["metrics"]["2018-2019"] = _classification_metric("110", "5", "0.05")
    elif case == "unrounded_decimal_values_drive_classification":
        for cost in ("base", "stress"):
            paths[f"candidate-{cost}"]["metrics"]["full"] = _classification_metric("5000.00000000004", "10", "0.1")
            paths[f"buy_and_hold-{cost}"]["metrics"]["full"] = _classification_metric("5000.00000000003", "10", "0.1")
        assert _shown(Decimal("5000.00000000004")) == _shown(Decimal("5000.00000000003"))

    category, _reasons = _classify(paths, gaps, reconciled)

    assert category == expected_category


def test_2020_act365_uses_continuous_account_baseline_date():
    from datetime import date

    metrics = _curve_metrics(
        [{
            "date": "2020-12-31", "book_nav_cny": "5500.00",
            "cash_cny": "5500.00", "quantity": 0, "raw_close_cny": "3.500",
        }],
        start_date=date(2020, 1, 2), end_date=date(2020, 12, 31),
        actual_start_nav=Decimal("5000.00"), evaluation_scale=Decimal(1),
        baseline_date=date(2019, 12, 31),
    )
    expected = _shown((Decimal("1.1").ln() * Decimal(365) / Decimal(366)).exp() - Decimal(1))

    assert (date(2020, 12, 31) - date(2019, 12, 31)).days == 366
    assert metrics["annualized_return"] == expected


def test_card020_runs_exact_six_paths_and_independently_reconciles_synthetic_history():
    market = FakeMarket(block_first_session=True)
    from strategy_core.trading_calendar import TradingCalendar

    dividends = [
        {
            "ts_code": "510880.SH", "ann_date": "2018-01-15", "record_date": "2018-03-01",
            "ex_date": "2018-03-02", "pay_date": "2018-03-04", "div_cash": "0.05",
            "source_ref": "synthetic settled-dividend fixture",
        },
        {
            "ts_code": "510880.SH", "ann_date": "2019-12-01", "record_date": "2019-12-30",
            "ex_date": "2019-12-31", "pay_date": "2021-01-10", "div_cash": "0.02",
            "source_ref": "synthetic ending-receivable fixture",
        },
    ]
    result = run_card020_validation(
        {
            "strategy_id": "510880-vol-budget-v1",
            "protocol_sha256": "969903D59F949DA0024448128404266C0059EA1A7BEF901B6496045BFDDE8D9D",
            "freeze_id": "freeze-test-001",
            "freeze_sha256": "a" * 64,
        },
        market=market,
        calendar=TradingCalendar(market),
        dividend_events=dividends,
        data_provenance={
            "market": {"source_status": "verified"},
            "dividends": {"source_status": "verified"},
        },
    )

    assert result["path_ids"] == [path_id for path_id, _, _ in EXPECTED_PATHS]
    assert set(result["paths"]) == set(result["path_ids"])
    assert result["reconciliation_status"] == "passed", result["reconciliation"]
    assert all(value["status"] == "passed" for value in result["reconciliation"].values())
    assert all("2020" in result["paths"][path_id]["metrics"] for path_id in result["path_ids"])
    assert all("daily_snapshots" in result["paths"][path_id] for path_id in result["path_ids"])
    assert all(set(result["paths"][path_id]["window_activity"]) == {"full", "2018-2019", "2020"} for path_id in result["path_ids"])
    for path_id in result["path_ids"]:
        path = result["paths"][path_id]
        settled_event = path["dividend_summary"]["events"][0]
        unpaid_event = path["dividend_summary"]["events"][1]
        assert settled_event["entitled_quantity"] > 0
        assert settled_event["entitlement_amount_cny"] == settled_event["paid_amount_cny"]
        assert settled_event["paid_date"] == "2018-03-05"  # Sunday pay date settles at the next session open.
        assert Decimal(unpaid_event["entitlement_amount_cny"]) > 0
        assert unpaid_event["paid_amount_cny"] == "0.00" and unpaid_event["paid_date"] is None
        assert path["dividend_summary"]["ending_receivable_cny"] == unpaid_event["entitlement_amount_cny"]
        window = path["window_activity"]["2018-2019"]
        assert window["dividend_entitlement_total_cny"] == (
            format(Decimal(settled_event["entitlement_amount_cny"]) + Decimal(unpaid_event["entitlement_amount_cny"]), "f")
        )
        assert window["dividend_paid_total_cny"] == settled_event["paid_amount_cny"]
        assert window["dividend_receivable_end_cny"] == unpaid_event["entitlement_amount_cny"]
        assert next(item for item in window["dividend_events"] if item["event_id"] == unpaid_event["event_id"])["paid_amount_cny"] == "0.00"
        assert path["window_activity"]["2020"]["dividend_paid_total_cny"] == "0.00"
        assert path["window_activity"]["2020"]["dividend_receivable_end_cny"] == unpaid_event["entitlement_amount_cny"]
        assert window["trade_count"] > 0
        assert "commission_total_cny" in window and "slippage_cost_total_cny" in window
    tampered = result["paths"]["buy_and_hold-base"]
    tampered["window_activity"]["full"]["commission_total_cny"] = "0.00"
    audit = _reconcile_path(tampered, market, TradingCalendar(market), dividends)
    assert audit["status"] == "failed"
    assert audit["reason"] == "independent_window_activity_replay_mismatch"
    assert result["paths"]["buy_and_hold-base"]["trades"][0]["execution_date"] == "2018-01-03"
    assert result["paths"]["static_half-base"]["trades"][0]["execution_date"] == "2018-01-03"
    assert len(result["result_sha256"]) == 64
