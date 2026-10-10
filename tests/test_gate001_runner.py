from datetime import date, timedelta
from decimal import Decimal
import json
from pathlib import Path

import pytest

from scripts import run_gate001_once as gate_runner
from scripts.gate001_reference import run_one_symbol_reference


def test_formal_mode_stops_before_loading_research_data_when_lock_is_false(tmp_path, monkeypatch):
    def unexpected_load(_protocol):
        raise AssertionError("formal data must not load while the result lock is false")

    monkeypatch.setattr(gate_runner, "_load_formal_inputs", unexpected_load)
    ledger_path = tmp_path / "trials.jsonl"

    report = gate_runner.run_gate001_once(
        mode="formal",
        trial_ledger_path=ledger_path,
    )

    assert report["status"] == "formal_run_blocked"
    assert report["formal_performance_result_allowed"] is False
    assert report["data_loaded"] is False
    assert report["metrics"] is None
    assert any("formal_performance_result_allowed=false" in item for item in report["blockers"])
    assert not ledger_path.exists()


def test_synthetic_entry_block_fill_dividend_tp_sell_and_terminal_nav_reconcile():
    report = gate_runner.run_synthetic_preflight()

    assert report["status"] == "synthetic_verified"
    assert report["formal_performance_result_allowed"] is False
    assert report["entry_signal_count"] == 1
    assert report["exit_signal_count"] == 1
    assert report["pending_limit_up_attempts"] == 1
    assert [item["direction"] for item in report["trades"]] == ["buy", "sell"]
    assert report["trades"][0]["trade_date"] == report["dates"][2]
    assert report["trades"][1]["trade_date"] == report["dates"][3]
    assert report["dividend_entitlement_cny"] == report["trades"][0]["quantity"] * 0.10
    assert report["open_trade_count"] == 0
    assert report["terminal_market_value_cny"] == 0.0
    assert report["terminal_receivable_cny"] == 0.0
    assert report["reference"]["status"] == "passed"
    assert report["reference"]["trade_economic_profit_cny"] > 0
    expected_cycle_profit = (
        sum(item["net_cash_flow"] for item in report["trades"])
        + report["dividend_entitlement_cny"]
    )
    assert report["reference"]["trade_economic_profit_cny"] == pytest.approx(
        expected_cycle_profit
    )
    assert report["reference"]["terminal_nav_cny"] == report["terminal_cash_cny"]


def test_synthetic_connection_runs_all_nine_paths_and_uses_verified_summary_fields():
    report = gate_runner.run_synthetic_preflight()

    assert set(report["scenario_results"]) == {"primary", "double_cost", "cash_yield_3pct"}
    for scenario in report["scenario_results"].values():
        assert set(scenario) == {"strategy", "buy_hold", "cash"}
        for portfolio in scenario.values():
            metrics = portfolio["metrics"]
            assert metrics["sharpe_risk_free_rate"] == 0.0
            assert metrics["mdd_loss_fraction"] >= 0.0
            assert metrics["calmar"] is None or isinstance(metrics["calmar"], float)
            assert "drawdown_duration_trading_days" in metrics
            assert "mean_exposure_fraction" in metrics
            assert "mean_capital_occupancy_fraction" in metrics
            assert "worst_completed_trade_pnl_cny" in metrics
            assert "best_winner_share" in metrics
            assert "independent_entry_calendar_years" in metrics
    for scenario in report["scenario_results"].values():
        assert scenario["strategy"]["reconciliation"]["status"] == "passed"
        assert scenario["buy_hold"]["reconciliation"]["status"] == "passed"
        assert [trade["direction"] for trade in scenario["buy_hold"]["trades"]] == ["buy"]
        assert scenario["buy_hold"]["trades"][0]["trade_date"] == report["dates"][2]
        assert scenario["cash"]["trades"] == []
    assert report["scenario_results"]["primary"]["cash"]["terminal_nav_cny"] == 100_000.0
    assert report["scenario_results"]["double_cost"]["cash"]["terminal_nav_cny"] == 100_000.0
    assert report["scenario_results"]["cash_yield_3pct"]["cash"]["terminal_nav_cny"] > 100_000.0


def test_synthetic_terminal_boundary_keeps_open_position_receivable_and_no_future_bar():
    boundary = gate_runner.run_synthetic_terminal_boundary()

    assert boundary["open_trade_count"] == 1
    assert boundary["open_quantity"] > 0
    assert boundary["terminal_receivable_cny"] > 0.0
    assert boundary["terminal_cash_cny"] < boundary["terminal_nav_cny"]
    assert boundary["pending_dividend_entitlement_cny"] == 0.0
    assert boundary["max_floating_loss_cny"] > 0.0
    assert boundary["t1_unlock_date"] == "2021-01-04"
    assert boundary["bar_rows_end"] == "2020-12-31"
    assert boundary["post_window_bar_requests"] == []


def test_synthetic_one_shot_trial_is_two_phase_and_not_market_research(tmp_path):
    ledger = tmp_path / "trials.jsonl"
    report = gate_runner.run_gate001_once(mode="synthetic", trial_ledger_path=ledger)

    records = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
    assert [record["phase"] for record in records] == ["start", "end"]
    assert records[0]["trial_id"] == records[1]["trial_id"]
    assert records[0]["attempt_class"] == "synthetic_validation"
    assert records[0]["market_sample"] is False
    assert records[0]["counts_as_new_research"] is False
    assert records[0]["new_research_count"] == 0
    assert records[0]["technical_rerun_count"] == 0
    assert records[0]["synthetic_validation_count"] == 1
    assert records[1]["status"] == "synthetic_verified"
    assert report["trial"]["trial_id"] == records[0]["trial_id"]


def test_formal_failure_is_appended_after_start_with_same_trial_id(tmp_path):
    ledger = tmp_path / "trials.jsonl"
    protocol = gate_runner.load_protocol()

    def fail_after_start(_protocol):
        started = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
        assert len(started) == 1
        assert started[0]["phase"] == "start"
        raise RuntimeError("synthetic injected failure")

    report = gate_runner._run_formal_trial(
        protocol,
        trial_ledger_path=ledger,
        attempt_class="technical_rerun",
        trial_id="synthetic-failure-001",
        input_loader=fail_after_start,
    )

    records = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
    assert [record["phase"] for record in records] == ["start", "end"]
    assert records[0]["trial_id"] == records[1]["trial_id"] == "synthetic-failure-001"
    assert records[1]["status"] == "failed"
    assert records[1]["failure_type"] == "RuntimeError"
    assert report["status"] == "formal_run_failed"
    assert report["formal_performance_result_allowed"] is False


def test_protocol_records_accepted_execution_proxy_and_closed_calculation_gate_only():
    protocol = gate_runner.load_protocol()

    assert protocol["formal_performance_result_allowed"] is False
    execution_gate = protocol["account_and_execution"]["execution_fact_gates"]
    assert execution_gate["status"] == "accepted_with_research_proxy_limitations"
    assert execution_gate["accepted_source_years"] == [2004, 2006, 2012]
    assert "first actually executable daily open" in execution_gate["research_proxy"]
    assert protocol["gate"]["calculation_contract_gate"]["status"] == "closed"


def test_formal_guard_requires_explicit_gate_states_and_matching_evidence():
    protocol = gate_runner.load_protocol()
    protocol["formal_performance_result_allowed"] = True
    protocol["formal_run_authorization"] = {
        "status": "authorized",
        "instruction_reference": "synthetic-test-only",
    }
    assert gate_runner._formal_blockers(protocol) == []

    no_run_authorization = json.loads(json.dumps(protocol))
    no_run_authorization["formal_run_authorization"]["status"] = "not_authorized"
    assert any("formal_run_authorization" in item for item in gate_runner._formal_blockers(no_run_authorization))

    unknown_status = json.loads(json.dumps(protocol))
    unknown_status["account_and_execution"]["execution_fact_gates"]["status"] = "pending_review"
    assert any("execution_fact_gates=" in item for item in gate_runner._formal_blockers(unknown_status))

    unsupported_closed_status = json.loads(json.dumps(protocol))
    unsupported_closed_status["account_and_execution"]["execution_fact_gates"]["status"] = "closed"
    assert any("execution_fact_gates=" in item for item in gate_runner._formal_blockers(unsupported_closed_status))

    missing_execution_evidence = json.loads(json.dumps(protocol))
    del missing_execution_evidence["account_and_execution"]["execution_fact_gates"]["accepted_source_years"]
    assert any("execution_fact_gates_evidence" in item for item in gate_runner._formal_blockers(missing_execution_evidence))

    missing_calculation_evidence = json.loads(json.dumps(protocol))
    missing_calculation_evidence["gate"]["calculation_contract_gate"]["closure_evidence"] = []
    assert any("calculation_contract_gate_evidence" in item for item in gate_runner._formal_blockers(missing_calculation_evidence))


def test_reference_keeps_pre_ex_entitlement_pending_at_research_cutoff():
    dates = []
    current = date(2009, 1, 5)
    while len(dates) < 253:
        if current.weekday() < 5:
            dates.append(current)
        current += timedelta(days=1)

    closes = [9.0] + [10.0] * 248 + [11.0, 9.0, 9.0]
    rows = []
    for index, (day, close) in enumerate(zip(dates[:252], closes[:252], strict=True)):
        opening = 9.5 if index == 251 else close
        rows.append({
            "date": day,
            "open": opening,
            "high": max(opening, close),
            "low": min(opening, close),
            "close": close,
            "pre_close": closes[index - 1] if index else close,
            "volume": 1_000_000,
            "adj_factor": 1.0,
        })

    result = run_one_symbol_reference(
        rows=rows,
        raw_dividend_events=[{
            "ts_code": "510880.SH",
            "ann_date": dates[250].isoformat(),
            "record_date": dates[251].isoformat(),
            "ex_date": dates[252].isoformat(),
            "pay_date": dates[252].isoformat(),
            "div_cash": "0.10",
            "verified_unit": "CNY per fund unit",
        }],
        market_dates=dates[:253],
        evaluation_dates=dates[250:252],
        anchor_date=dates[0],
        symbol="510880.SH",
        strategy_name="Dividend_MA250_TP10_V1",
        strategy_version="V1",
        initial_cash=Decimal("100000.00"),
        commission_rate=Decimal("0.0003"),
        minimum_commission=Decimal("5.00"),
        stamp_duty_rate=Decimal("0"),
        transfer_fee_rate=Decimal("0"),
        slippage_rate=Decimal("0"),
        cash_yield_annual_rate=Decimal("0"),
    )

    assert result.open_trade_count == 1
    assert result.dividend_entitlement == Decimal("0.00")
    assert result.terminal_receivable == Decimal("0.00")
    assert result.pending_dividend_entitlement == Decimal(result.open_quantity) * Decimal("0.10")


def test_formal_profile_uses_frozen_cost_scenarios_and_all_gate_execution_flags():
    protocol = gate_runner.load_protocol()
    profiles = gate_runner.scenario_profiles(protocol)

    assert set(profiles) == {"primary", "double_cost", "cash_yield_3pct"}
    assert profiles["primary"]["commission_rate"] == 0.0003
    assert profiles["primary"]["minimum_commission"] == 5.0
    assert profiles["primary"]["slippage_rate"] == 0.0005
    assert profiles["primary"]["cash_yield_annual_rate"] == 0.0
    assert profiles["double_cost"]["commission_rate"] == 0.0006
    assert profiles["double_cost"]["minimum_commission"] == 10.0
    assert profiles["double_cost"]["slippage_rate"] == 0.001
    assert profiles["cash_yield_3pct"]["cash_yield_annual_rate"] == 0.03
    assert gate_runner.GATE_EXECUTION_FLAGS == {
        "cash_target_buy": True,
        "retry_temporarily_blocked_orders": True,
        "opening_capacity_mode": True,
        "round_to_cents": True,
        "execution_price_mode": True,
        "next_day_exit_intent_mode": True,
    }


def test_date_only_calendar_supplies_terminal_t1_unlock_without_post_window_bars():
    source = gate_runner.make_terminal_calendar_fixture()
    calendar = gate_runner.Gate001EvaluationCalendar(
        source.calendar,
        evaluation_end=date(2020, 12, 31),
        date_only_next_session=date(2021, 1, 4),
    )

    assert calendar.all_trading_dates() == [date(2020, 12, 30), date(2020, 12, 31)]
    assert calendar.next_trading_day(date(2020, 12, 31)) == date(2021, 1, 4)
    assert calendar.previous_trading_day(date(2021, 1, 4)) == date(2020, 12, 31)
    position = gate_runner.make_terminal_frozen_position(calendar)
    assert position.frozen_lots[0].unlock_date == date(2021, 1, 4)
    assert source.post_window_bar_requests == []


def test_gate_verdict_is_deterministic_and_invalidity_precedes_economics():
    protocol = gate_runner.load_protocol()
    good = {
        "validity_errors": [],
        "completed_round_trips": 8,
        "entry_calendar_years": 5,
        "best_winner_share": 0.25,
        "scenarios_pass": True,
    }
    assert gate_runner.classify_verdict(good, protocol) == "worth_continuing"
    assert gate_runner.classify_verdict(
        {**good, "validity_errors": ["reference_mismatch"]}, protocol
    ) == "invalid_test"
    assert gate_runner.classify_verdict(
        {**good, "completed_round_trips": 7}, protocol
    ) == "insufficient_evidence"
    assert gate_runner.classify_verdict(
        {**good, "best_winner_share": 0.51}, protocol
    ) == "insufficient_evidence"
    assert gate_runner.classify_verdict(
        {**good, "scenarios_pass": False}, protocol
    ) == "reject"


def test_trial_ledger_only_appends_and_preserves_previous_records(tmp_path):
    ledger = tmp_path / "trials.jsonl"
    first = {"trial_id": "first", "kind": "formal"}
    second = {"trial_id": "second", "kind": "technical_rerun"}

    gate_runner.append_trial_record(ledger, first)
    original_bytes = ledger.read_bytes()
    gate_runner.append_trial_record(ledger, second)

    lines = ledger.read_text(encoding="utf-8").splitlines()
    assert ledger.read_bytes().startswith(original_bytes)
    assert [json.loads(line) for line in lines] == [first, second]


@pytest.mark.parametrize("mode", ["formal", "synthetic"])
def test_one_shot_output_marks_non_formal_modes(mode):
    report = gate_runner.run_gate001_once(mode=mode)

    assert report["mode"] == mode
    assert report["formal_performance_result_allowed"] is False
