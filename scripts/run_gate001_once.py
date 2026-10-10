"""Guarded one-shot entry and synthetic Gate001 lifecycle preflight."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from contracts.stable import DailyBar, DailyStatus, FrozenLot, Signal, StrategyConfig
from scripts.gate001_reference import reconcile_engine_result, run_one_symbol_reference
from strategy_core.backtest_engine import run_backtest
from strategy_core.dsl_parser import parse_strategy_config
from strategy_core.metrics import calculate_cagr, calculate_metrics
from strategy_core.portfolio import Position
from strategy_core.trading_calendar import TradingCalendar
from strategy_core.validator import validate_strategy_config


PROTOCOL_PATH = (
    PROJECT_ROOT
    / "data"
    / "alpha_gate_001"
    / "GATE001_PROTOCOL_V1_20261005_a94b1e3f6d6a46af87894e0269777a32.json"
)
CONFIG_PATH = PROJECT_ROOT / "tests" / "golden_cases" / "strategy_config.yaml"
SYMBOL = "510880.SH"
STRATEGY_NAME = "Dividend_MA250_TP10_V1"
STRATEGY_VERSION = "V1"
ANCHOR_DATE = date(2009, 1, 5)
TRIAL_LEDGER_PATH = PROJECT_ROOT / "docs" / "verification" / "GATE001_TRIALS.jsonl"
GATE_EXECUTION_FLAGS = {
    "cash_target_buy": True,
    "retry_temporarily_blocked_orders": True,
    "opening_capacity_mode": True,
    "round_to_cents": True,
    "execution_price_mode": True,
    "next_day_exit_intent_mode": True,
}


def load_protocol() -> dict[str, Any]:
    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    if protocol.get("protocol_id") != "Gate001" or protocol.get("version") != "1":
        raise ValueError("unexpected Gate001 protocol identity")
    return protocol


def scenario_profiles(protocol: dict[str, Any]) -> dict[str, dict[str, float]]:
    costs = protocol["cost_model"]
    primary = {
        "commission_rate": float(Decimal(costs["commission_rate_each_side"])),
        "minimum_commission": float(Decimal(costs["minimum_commission_cny_each_order"])),
        "stamp_duty_rate": float(Decimal(costs["stamp_duty_rate"])),
        "transfer_fee_rate": float(Decimal(costs["transfer_fee_rate"])),
        "slippage_rate": float(Decimal(costs["slippage_rate_each_side"])),
        "cash_yield_annual_rate": float(Decimal(protocol["cash_return"]["primary_annual_rate"])),
    }
    stress_costs = costs["double_cost_stress"]
    double_cost = {
        **primary,
        "commission_rate": float(Decimal(stress_costs["commission_rate_each_side"])),
        "minimum_commission": float(Decimal(stress_costs["minimum_commission_cny_each_order"])),
        "stamp_duty_rate": float(Decimal(stress_costs["stamp_duty_rate"])),
        "transfer_fee_rate": float(Decimal(stress_costs["transfer_fee_rate"])),
        "slippage_rate": float(Decimal(stress_costs["slippage_rate_each_side"])),
    }
    return {
        "primary": primary,
        "double_cost": double_cost,
        "cash_yield_3pct": {
            **primary,
            "cash_yield_annual_rate": float(Decimal(protocol["cash_return"]["stress_annual_rate"])),
        },
    }


def classify_verdict(evidence: dict[str, Any], protocol: dict[str, Any]) -> str:
    if evidence.get("validity_errors"):
        return "invalid_test"
    minimum = protocol["gate"]["minimum_evidence"]
    if (
        int(evidence.get("completed_round_trips", 0))
        < int(minimum["independent_completed_round_trips"])
        or int(evidence.get("entry_calendar_years", 0))
        < int(minimum["distinct_entry_calendar_years"])
    ):
        return "insufficient_evidence"
    concentration_limit = Decimal("0.50")
    if Decimal(str(evidence.get("best_winner_share", 0))) > concentration_limit:
        return "insufficient_evidence"
    return "worth_continuing" if evidence.get("scenarios_pass") is True else "reject"


class Gate001EvaluationCalendar:
    """Research-window dates plus one date-only T+1 unlock date."""

    def __init__(
        self,
        source_calendar: TradingCalendar,
        *,
        evaluation_end: date,
        date_only_next_session: date | None,
    ) -> None:
        self._dates = [
            day for day in source_calendar.all_trading_dates()
            if day <= evaluation_end
        ]
        if not self._dates or self._dates[-1] != evaluation_end:
            raise ValueError("evaluation end must be present in the market calendar")
        if date_only_next_session is not None and date_only_next_session <= evaluation_end:
            raise ValueError("date-only T+1 session must be after evaluation end")
        self.evaluation_end = evaluation_end
        self.date_only_next_session = date_only_next_session
        self._indices = {day: index for index, day in enumerate(self._dates)}

    def all_trading_dates(self) -> list[date]:
        return list(self._dates)

    def is_trading_day(self, target_date: date) -> bool:
        return target_date in self._indices

    def next_trading_day(self, current_date: date) -> date:
        index = self._indices.get(current_date)
        if index is None:
            raise ValueError(f"not a research trading date: {current_date}")
        if index + 1 < len(self._dates):
            return self._dates[index + 1]
        if current_date == self.evaluation_end and self.date_only_next_session is not None:
            return self.date_only_next_session
        raise ValueError(f"no known next trading date after {current_date}")

    def previous_trading_day(self, current_date: date) -> date:
        if current_date == self.date_only_next_session:
            return self.evaluation_end
        index = self._indices.get(current_date)
        if index is None:
            raise ValueError(f"not a known trading date: {current_date}")
        if index == 0:
            raise ValueError(f"no previous trading date before {current_date}")
        return self._dates[index - 1]


class _SyntheticSource:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.bars: dict[date, DailyBar] = {}
        self.statuses: dict[date, DailyStatus] = {}
        self.price_limits: dict[date, tuple[Decimal, Decimal]] = {}
        self.post_window_bar_requests: list[date] = []
        for row in rows:
            day = row["date"]
            opening = Decimal(str(row["open"]))
            prior_close = Decimal(str(row["pre_close"]))
            lower = (prior_close * Decimal("0.90")).quantize(
                Decimal("0.001"), rounding=ROUND_HALF_UP
            )
            upper = (prior_close * Decimal("1.10")).quantize(
                Decimal("0.001"), rounding=ROUND_HALF_UP
            )
            self.price_limits[day] = (lower, upper)
            self.bars[day] = DailyBar(
                date=day,
                symbol=SYMBOL,
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=int(row["volume"]),
                amount=float(row["amount"]),
                adj_factor=float(row["adj_factor"]),
            )
            self.statuses[day] = DailyStatus(
                date=day,
                symbol=SYMBOL,
                is_st=False,
                is_suspended=False,
                is_limit_up=opening >= upper,
                is_limit_down=opening <= lower,
            )

    def symbols(self) -> list[str]:
        return [SYMBOL]

    def get_daily_bars(self, symbol: str) -> list[DailyBar]:
        self._require_symbol(symbol)
        return list(self.bars.values())

    def get_daily_bar(self, symbol: str, target_date: date) -> DailyBar:
        self._require_symbol(symbol)
        try:
            return self.bars[target_date]
        except KeyError:
            if target_date > max(self.bars):
                self.post_window_bar_requests.append(target_date)
            raise

    def get_daily_status(self, symbol: str, target_date: date) -> DailyStatus:
        self._require_symbol(symbol)
        return self.statuses[target_date]

    def get_daily_price_limits(
        self,
        symbol: str,
        target_date: date,
    ) -> tuple[Decimal, Decimal]:
        self._require_symbol(symbol)
        return self.price_limits[target_date]

    def get_price(self, symbol: str, target_date: date) -> float:
        return self.get_daily_bar(symbol, target_date).close

    @staticmethod
    def _require_symbol(symbol: str) -> None:
        if symbol != SYMBOL:
            raise KeyError(symbol)


def make_terminal_calendar_fixture() -> _SyntheticSource:
    days = [date(2020, 12, 30), date(2020, 12, 31)]
    rows = []
    for day, close in zip(days, (10.0, 10.1), strict=True):
        rows.append({
            "date": day,
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "pre_close": close,
            "volume": 100_000,
            "amount": close * 100_000,
            "adj_factor": 1.0,
        })
    source = _SyntheticSource(rows)
    source.calendar = TradingCalendar(source)
    return source


def make_terminal_frozen_position(calendar: Gate001EvaluationCalendar) -> Position:
    unlock_date = calendar.next_trading_day(calendar.evaluation_end)
    return Position(
        symbol=SYMBOL,
        quantity=100,
        sellable_quantity=0,
        frozen_lots=[FrozenLot(quantity=100, unlock_date=unlock_date)],
        avg_cost=10.0,
        last_price=10.0,
        oldest_buy_date=calendar.evaluation_end,
    )


def run_synthetic_terminal_boundary() -> dict[str, Any]:
    """Exercise a terminal open cycle, ex-date receivable, and date-only T+1."""
    market_dates = _weekdays(date(2020, 1, 15), 252)
    anchor_date = date(2009, 1, 5)
    anchor_row = {
        "date": anchor_date,
        "open": 10.0,
        "high": 10.0,
        "low": 10.0,
        "close": 10.0,
        "pre_close": 10.0,
        "volume": 1_000_000,
        "amount": 10_000_000.0,
        "adj_factor": 1.0,
    }
    rows = []
    for index, day in enumerate(market_dates):
        close = 10.0
        if index == 249:
            close = 10.1
        elif index == 250:
            close = 9.0
        elif index == 251:
            close = 8.5
        opening = 9.0 if index == 251 else close
        previous_close = rows[-1]["close"] if rows else close
        rows.append({
            "date": day,
            "open": opening,
            "high": max(opening, close),
            "low": min(opening, close),
            "close": close,
            "pre_close": previous_close,
            "volume": 1_000_000,
            "amount": close * 1_000_000,
            "adj_factor": 1.0,
        })
    rows.insert(0, anchor_row)
    evaluation_dates = market_dates[-2:]
    date_only_next_session = date(2021, 1, 4)
    market_dates_with_unlock = [anchor_date, *market_dates, date_only_next_session]
    dividend_event = {
        "ts_code": SYMBOL,
        "ann_date": evaluation_dates[0].isoformat(),
        "record_date": evaluation_dates[-1].isoformat(),
        "ex_date": evaluation_dates[-1].isoformat(),
        "pay_date": date_only_next_session.isoformat(),
        "div_cash": "0.10",
        "verified_unit": "CNY per fund unit",
        "source_ref": "synthetic://gate001/terminal-open-receivable",
    }
    source = _SyntheticSource(rows)
    base_calendar = TradingCalendar(source)
    calendar = Gate001EvaluationCalendar(
        base_calendar,
        evaluation_end=evaluation_dates[-1],
        date_only_next_session=date_only_next_session,
    )
    config = _synthetic_strategy_config(evaluation_dates)
    result = run_backtest(
        config,
        source,
        calendar,
        initial_capital=100_000.0,
        dividend_events=[dividend_event],
        minimum_commission=5.0,
        **GATE_EXECUTION_FLAGS,
    )
    reference = run_one_symbol_reference(
        rows=rows,
        raw_dividend_events=[dividend_event],
        market_dates=market_dates_with_unlock,
        evaluation_dates=evaluation_dates,
        anchor_date=anchor_date,
        symbol=SYMBOL,
        strategy_name=STRATEGY_NAME,
        strategy_version=STRATEGY_VERSION,
        initial_cash="100000.00",
        commission_rate="0.0003",
        minimum_commission="5.00",
        stamp_duty_rate="0",
        transfer_fee_rate="0",
        slippage_rate="0.0005",
        cash_yield_annual_rate="0",
        opening_capacity_rate="0.10",
    )
    reconciliation = reconcile_engine_result(result, reference)
    open_rows = list(reference.daily_open_cycle_pnl)
    return {
        "status": "passed" if reconciliation["status"] == "passed" else "failed",
        "reconciliation": _json_safe(reconciliation),
        "open_trade_count": reference.open_trade_count,
        "open_quantity": reference.open_quantity,
        "terminal_cash_cny": float(reference.terminal_cash),
        "terminal_receivable_cny": float(reference.terminal_receivable),
        "pending_dividend_entitlement_cny": float(reference.pending_dividend_entitlement),
        "terminal_nav_cny": float(reference.terminal_nav),
        "max_floating_loss_cny": float(reference.max_open_trade_floating_loss),
        "terminal_open_trade_pnl_cny": (
            float(reference.open_trade_profit) if reference.open_trade_profit is not None else None
        ),
        "terminal_holding_sessions": open_rows[-1]["holding_sessions"] if open_rows else 0,
        "t1_unlock_date": date_only_next_session.isoformat(),
        "post_window_bar_requests": source.post_window_bar_requests,
        "bar_rows_end": max(source.bars).isoformat(),
    }


def _scenario_strategy_config(
    evaluation_dates: list[date],
    profile: dict[str, float],
    *,
    mode: str,
) -> StrategyConfig:
    config = _synthetic_strategy_config(evaluation_dates)
    values = config.model_dump(mode="python")
    values["fill_model"]["commission"] = profile["commission_rate"]
    values["fill_model"]["stamp_tax"] = profile["stamp_duty_rate"]
    values["fill_model"]["slippage"] = profile["slippage_rate"]
    if mode in {"buy_hold", "cash"}:
        values["exit_conditions"] = {"logic": "OR", "rules": []}
    return StrategyConfig.model_validate(values)


def _run_engine_path(
    *,
    config: StrategyConfig,
    source: Any,
    calendar: Any,
    dividend_events: list[dict[str, Any]],
    profile: dict[str, float],
    mode: str,
) -> Any:
    if mode == "strategy":
        return run_backtest(
            config,
            source,
            calendar,
            initial_capital=100_000.0,
            dividend_events=dividend_events,
            minimum_commission=profile["minimum_commission"],
            **GATE_EXECUTION_FLAGS,
            cash_yield_annual_rate=profile["cash_yield_annual_rate"],
        )

    original_module = sys.modules["strategy_core.backtest_engine"]

    def benchmark_or_cash_signals(strategy_config, _source, trade_date, universe):
        if mode == "cash" or trade_date != strategy_config.backtest_config.start_date:
            return []
        return [Signal(
            signal_id=(f"{strategy_config.strategy_name}:{strategy_config.version}:"
                       f"{SYMBOL}:{trade_date}:entry"),
            strategy_id=strategy_config.strategy_name,
            strategy_version=strategy_config.version,
            symbol=SYMBOL,
            signal_date=trade_date,
            signal_type="entry",
            triggered_rules=["buy_hold_first_common_close"],
            audit_id=f"signal:{strategy_config.audit.config_hash}:{SYMBOL}:{trade_date}",
        )]

    with patch.object(original_module, "generate_signals", benchmark_or_cash_signals):
        return run_backtest(
            config,
            source,
            calendar,
            initial_capital=100_000.0,
            dividend_events=dividend_events,
            minimum_commission=profile["minimum_commission"],
            **GATE_EXECUTION_FLAGS,
            cash_yield_annual_rate=profile["cash_yield_annual_rate"],
        )


def _summarize_path(result: Any, reference: Any, start_date: date, end_date: date) -> dict[str, Any]:
    metrics = calculate_metrics(
        result.trades,
        result.daily_portfolio_values,
        result.initial_capital,
        risk_free_rate=0.0,
    )
    eod_by_date = {item["date"]: item for item in reference.daily_values}
    eod_values = [eod_by_date[day] for day in sorted(eod_by_date)]
    navs = [Decimal(item["total_value"]) for item in eod_values]
    peak = Decimal("0")
    current_duration = 0
    max_duration = 0
    drawdown_start: date | None = None
    max_drawdown_calendar_days = 0
    peak_date: date | None = None
    for item, nav in zip(eod_values, navs, strict=True):
        if nav >= peak:
            if drawdown_start is not None and peak_date is not None:
                max_drawdown_calendar_days = max(
                    max_drawdown_calendar_days,
                    (item["date"] - peak_date).days,
                )
            peak = nav
            peak_date = item["date"]
            current_duration = 0
            drawdown_start = None
        else:
            if drawdown_start is None:
                drawdown_start = item["date"]
            current_duration += 1
            max_duration = max(max_duration, current_duration)
    if drawdown_start is not None and peak_date is not None:
        max_drawdown_calendar_days = max(
            max_drawdown_calendar_days,
            (end_date - peak_date).days,
        )

    completed = list(reference.completed_trade_profits)
    winners = [profit for profit in completed if profit > 0]
    winner_total = sum(winners, Decimal("0.00"))
    best_winner_share = (
        float(max(winners) / winner_total) if winner_total > 0 else 0.0
    )
    buy_fill_years = sorted({
        trade["trade_date"].year
        for trade in reference.trades
        if trade["direction"] == "buy"
    })
    mean_exposure = sum(
        float(Decimal(item["market_value"]) / Decimal(item["total_value"]))
        if Decimal(item["total_value"]) > 0 else 0.0
        for item in eod_values
    ) / len(eod_values)
    mean_occupancy = sum(
        float(Decimal(item["market_value"]) / Decimal("100000.00"))
        for item in eod_values
    ) / len(eod_values)
    cagr = calculate_cagr(
        result.initial_capital,
        result.final_capital,
        start_date,
        end_date,
    )
    mdd = abs(float(metrics.max_drawdown))
    return {
        "cagr_act_365": cagr,
        "mdd_loss_fraction": mdd,
        "calmar": cagr / mdd if mdd > 0 else None,
        "sharpe": float(metrics.sharpe_ratio),
        "sharpe_risk_free_rate": 0.0,
        "drawdown_duration_trading_days": max_duration,
        "drawdown_duration_calendar_days": max_drawdown_calendar_days,
        "mean_exposure_fraction": mean_exposure,
        "mean_capital_occupancy_fraction": mean_occupancy,
        "completed_round_trips": len(completed),
        "completed_trade_pnl_cny": [float(value) for value in completed],
        "worst_completed_trade_pnl_cny": float(min(completed)) if completed else None,
        "best_winner_share": best_winner_share,
        "independent_entry_calendar_years": buy_fill_years,
        "open_trade_count": reference.open_trade_count,
        "open_quantity": reference.open_quantity,
        "terminal_open_trade_pnl_cny": (
            float(reference.open_trade_profit) if reference.open_trade_profit is not None else None
        ),
        "max_floating_loss_cny": float(reference.max_open_trade_floating_loss),
        "terminal_holding_sessions": (
            reference.daily_open_cycle_pnl[-1]["holding_sessions"]
            if reference.daily_open_cycle_pnl else 0
        ),
        "unfilled_terminal_orders": reference.pending_at_end,
        "historical_rejected_orders": len(reference.rejected),
        "cash_interest_income_cny": float(reference.interest_income),
        "terminal_cash_cny": float(reference.terminal_cash),
        "terminal_market_value_cny": float(reference.terminal_market_value),
        "terminal_receivable_cny": float(reference.terminal_receivable),
        "terminal_nav_cny": float(reference.terminal_nav),
    }


def _evaluate_nine_paths(inputs: dict[str, Any], protocol: dict[str, Any]) -> dict[str, Any]:
    source = inputs["market_source"]
    evaluation_dates: list[date] = inputs["evaluation_dates"]
    market_dates: list[date] = inputs["market_dates"]
    rows: list[dict[str, Any]] = inputs["rows"]
    dividends: list[dict[str, Any]] = inputs["dividend_events"]
    date_only_next = inputs.get("date_only_next_session")
    profiles = scenario_profiles(protocol)
    scenario_results: dict[str, Any] = {}
    validity_errors: list[str] = []
    for scenario_name, profile in profiles.items():
        scenario_results[scenario_name] = {}
        for mode in ("strategy", "buy_hold", "cash"):
            config = _scenario_strategy_config(evaluation_dates, profile, mode=mode)
            calendar = Gate001EvaluationCalendar(
                TradingCalendar(source),
                evaluation_end=evaluation_dates[-1],
                date_only_next_session=date_only_next,
            )
            engine_result = _run_engine_path(
                config=config,
                source=source,
                calendar=calendar,
                dividend_events=dividends,
                profile=profile,
                mode=mode,
            )
            reference = run_one_symbol_reference(
                rows=rows,
                raw_dividend_events=dividends,
                market_dates=market_dates,
                evaluation_dates=evaluation_dates,
                anchor_date=ANCHOR_DATE,
                symbol=SYMBOL,
                strategy_name=STRATEGY_NAME if mode == "strategy" else f"Gate001_{mode}",
                strategy_version=STRATEGY_VERSION,
                initial_cash="100000.00",
                commission_rate=profile["commission_rate"],
                minimum_commission=profile["minimum_commission"],
                stamp_duty_rate=profile["stamp_duty_rate"],
                transfer_fee_rate=profile["transfer_fee_rate"],
                slippage_rate=profile["slippage_rate"],
                cash_yield_annual_rate=profile["cash_yield_annual_rate"],
                mode=mode,
                opening_capacity_rate="0.10",
            )
            reconciliation = reconcile_engine_result(engine_result, reference)
            if reconciliation["status"] != "passed":
                validity_errors.extend(
                    f"{scenario_name}.{mode}:{error}"
                    for error in reconciliation["errors"]
                )
            scenario_results[scenario_name][mode] = {
                "metrics": _summarize_path(
                    engine_result, reference, evaluation_dates[0], evaluation_dates[-1]
                ),
                "terminal_nav_cny": float(reference.terminal_nav),
                "terminal_cash_cny": float(reference.terminal_cash),
                "terminal_market_value_cny": float(reference.terminal_market_value),
                "terminal_receivable_cny": float(reference.terminal_receivable),
                "reconciliation": _json_safe(reconciliation),
                "trades": [
                    {
                        "direction": trade.direction,
                        "trade_date": trade.trade_date.isoformat(),
                        "quantity": trade.quantity,
                        "price": trade.price,
                        "net_cash_flow": trade.net_cash_flow,
                    }
                    for trade in engine_result.trades
                ],
                "entry_signal_count": engine_result.entry_signal_count,
                "exit_signal_count": engine_result.exit_signal_count,
            }
    economics_by_scenario = {
        key: _scenario_economics(paths)
        for key, paths in scenario_results.items()
    }
    all_scenarios_pass = all(item["passed"] for item in economics_by_scenario.values())
    total_completed = len(
        scenario_results["primary"]["strategy"]["metrics"]["completed_trade_pnl_cny"]
    )
    years = scenario_results["primary"]["strategy"]["metrics"]["independent_entry_calendar_years"]
    concentration = scenario_results["primary"]["strategy"]["metrics"]["best_winner_share"]
    evidence = {
        "validity_errors": validity_errors,
        "completed_round_trips": total_completed,
        "entry_calendar_years": len(years),
        "best_winner_share": concentration,
        "scenarios_pass": all_scenarios_pass,
    }
    return {
        "scenario_results": scenario_results,
        "scenario_economics": economics_by_scenario,
        "validity_errors": validity_errors,
        "deterministic_verdict": classify_verdict(evidence, protocol),
        "scenario_thresholds_pass": all_scenarios_pass,
    }


def _scenario_economics(paths: dict[str, Any]) -> dict[str, Any]:
    strategy = paths["strategy"]["metrics"]
    buy_hold = paths["buy_hold"]["metrics"]
    cash = paths["cash"]["metrics"]
    cagr = strategy["cagr_act_365"]
    mdd = strategy["mdd_loss_fraction"]
    bh_cagr = buy_hold["cagr_act_365"]
    bh_mdd = buy_hold["mdd_loss_fraction"]
    cash_cagr = cash["cagr_act_365"]
    rule_a = cagr >= bh_cagr + 0.01 and mdd <= bh_mdd + 0.02
    rule_b = cagr >= bh_cagr - 0.005 and mdd <= bh_mdd - 0.05
    beats_cash = cagr >= cash_cagr + 0.01
    return {
        "strategy_cagr_at_least_cash_plus_1pp": beats_cash,
        "buy_hold_rule_a": rule_a,
        "buy_hold_rule_b": rule_b,
        "passed": beats_cash and (rule_a or rule_b),
    }


def run_synthetic_preflight() -> dict[str, Any]:
    rows, market_dates, evaluation_dates, dividend_event = _synthetic_rows_and_event()
    source = _SyntheticSource(rows)
    calendar = TradingCalendar(source)
    config = _synthetic_strategy_config(evaluation_dates)
    validate_strategy_config(config)
    result = run_backtest(
        config,
        source,
        calendar,
        initial_capital=100_000.0,
        dividend_events=[dividend_event],
        minimum_commission=5.0,
        **GATE_EXECUTION_FLAGS,
        cash_yield_annual_rate=0.0,
    )
    reference = run_one_symbol_reference(
        rows=rows,
        raw_dividend_events=[dividend_event],
        market_dates=market_dates,
        evaluation_dates=evaluation_dates,
        anchor_date=ANCHOR_DATE,
        symbol=SYMBOL,
        strategy_name=STRATEGY_NAME,
        strategy_version=STRATEGY_VERSION,
        initial_cash="100000.00",
        commission_rate="0.0003",
        minimum_commission="5.00",
        stamp_duty_rate="0",
        transfer_fee_rate="0",
        slippage_rate="0.0005",
        cash_yield_annual_rate="0",
        opening_capacity_rate="0.10",
    )
    reconciliation = reconcile_engine_result(result, reference)
    date_only_next = _next_weekday(evaluation_dates[-1])
    scenario_inputs = {
        "market_source": source,
        "rows": rows,
        "market_dates": [*market_dates, date_only_next],
        # The first synthetic bar is the initial-NAV anchor; the next close is
        # the first common evaluation close used by the scenario matrix.
        "evaluation_dates": evaluation_dates[1:],
        "dividend_events": [dividend_event],
        "date_only_next_session": date_only_next,
    }
    matrix = _evaluate_nine_paths(scenario_inputs, load_protocol())
    boundary = run_synthetic_terminal_boundary()
    matrix_valid = not matrix["validity_errors"] and boundary["status"] == "passed"
    trade_rows = [
        {
            "direction": trade.direction,
            "trade_date": trade.trade_date.isoformat(),
            "quantity": trade.quantity,
            "price": trade.price,
            "net_cash_flow": trade.net_cash_flow,
            "total_fee": trade.total_fee,
        }
        for trade in result.trades
    ]
    return {
        "mode": "synthetic",
        "status": (
            "synthetic_verified"
            if reconciliation["status"] == "passed" and matrix_valid
            else "synthetic_failed"
        ),
        "formal_performance_result_allowed": False,
        "data_classification": "synthetic_test_only",
        "data_loaded": False,
        "dates": [day.isoformat() for day in evaluation_dates],
        "entry_signal_count": result.entry_signal_count,
        "exit_signal_count": result.exit_signal_count,
        "pending_limit_up_attempts": reference.pending_limit_up_attempts,
        "trades": trade_rows,
        "dividend_entitlement_cny": float(reference.dividend_entitlement),
        "pending_dividend_entitlement_cny": float(reference.pending_dividend_entitlement),
        "open_trade_count": reference.open_trade_count,
        "open_quantity": reference.open_quantity,
        "terminal_cash_cny": float(reference.terminal_cash),
        "terminal_market_value_cny": float(reference.terminal_market_value),
        "terminal_receivable_cny": float(reference.terminal_receivable),
        "terminal_nav_cny": float(reference.terminal_nav),
        "reference": _json_safe(reconciliation),
        "scenario_results": matrix["scenario_results"],
        "scenario_economics": matrix["scenario_economics"],
        "scenario_thresholds_pass": matrix["scenario_thresholds_pass"],
        "deterministic_verdict": "not_applicable_synthetic_validation",
        "scenario_validity_errors": matrix["validity_errors"],
        "terminal_boundary": boundary,
        "warnings": [
            "Synthetic rows exercise all nine calculation paths; no historical strategy result or verdict was produced.",
            "Price-limit and volume inputs are explicit test fixtures, not exchange evidence.",
        ],
    }


def run_gate001_once(
    *,
    mode: str,
    trial_ledger_path: Path | str | None = None,
    attempt_class: str = "new_research",
) -> dict[str, Any]:
    if mode == "synthetic":
        if trial_ledger_path is None:
            return run_synthetic_preflight()
        return _run_logged_synthetic(Path(trial_ledger_path))
    if mode != "formal":
        raise ValueError("mode must be formal or synthetic")

    protocol = load_protocol()
    blockers = _formal_blockers(protocol)
    if blockers:
        return {
            "mode": "formal",
            "status": "formal_run_blocked",
            "formal_performance_result_allowed": False,
            "data_loaded": False,
            "metrics": None,
            "trial_ledger_written": False,
            "blockers": blockers,
        }

    return _run_formal_trial(
        protocol,
        trial_ledger_path=trial_ledger_path or TRIAL_LEDGER_PATH,
        attempt_class=attempt_class,
        input_loader=_load_formal_inputs,
    )


def append_trial_record(path: Path | str, record: dict[str, Any]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        previous = destination.read_bytes()
        if previous and not previous.endswith(b"\n"):
            raise ValueError("trial ledger has an incomplete final line")
        for line_number, line in enumerate(previous.splitlines(), start=1):
            try:
                json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"trial ledger line {line_number} is invalid JSON") from exc
    with destination.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(_json_safe(record), ensure_ascii=False, allow_nan=False))
        handle.write("\n")


def _read_trial_records(path: Path | str) -> list[dict[str, Any]]:
    destination = Path(path)
    if not destination.exists():
        return []
    data = destination.read_bytes()
    if data and not data.endswith(b"\n"):
        raise ValueError("trial ledger has an incomplete final line")
    records = []
    for line_number, line in enumerate(data.splitlines(), start=1):
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"trial ledger line {line_number} is invalid JSON") from exc
        if not isinstance(record, dict):
            raise ValueError(f"trial ledger line {line_number} is not an object")
        records.append(record)
    return records


def _trial_start_record(
    protocol: dict[str, Any],
    *,
    ledger_path: Path,
    attempt_class: str,
    trial_id: str,
    market_sample: bool,
) -> dict[str, Any]:
    if attempt_class not in {"new_research", "technical_rerun", "synthetic_validation"}:
        raise ValueError("invalid Gate001 trial attempt class")
    records = _read_trial_records(ledger_path)
    starts = [record for record in records if record.get("phase") == "start"]
    counts = {
        "new_research_count": sum(record.get("attempt_class") == "new_research" for record in starts),
        "technical_rerun_count": sum(record.get("attempt_class") == "technical_rerun" for record in starts),
        "synthetic_validation_count": sum(
            record.get("attempt_class") == "synthetic_validation" for record in starts
        ),
    }
    counts_key = {
        "new_research": "new_research_count",
        "technical_rerun": "technical_rerun_count",
        "synthetic_validation": "synthetic_validation_count",
    }[attempt_class]
    counts[counts_key] += 1
    now = datetime.now(timezone.utc)
    protocol_bytes = PROTOCOL_PATH.read_bytes()
    data_contract = protocol["data_contract"]
    return {
        "trial_id": trial_id,
        "phase": "start",
        "attempt_class": attempt_class,
        "started_at_utc": now.isoformat(),
        "started_at_local": now.astimezone(ZoneInfo("Asia/Shanghai")).isoformat(),
        "protocol_id": protocol["protocol_id"],
        "protocol_version": protocol["version"],
        "protocol_sha256": hashlib.sha256(protocol_bytes).hexdigest().upper(),
        "formal_run_authorization": protocol.get("formal_run_authorization", {}),
        "evaluation_window": protocol["evaluation_window"]["common_evaluation_start"]
        + ".."
        + protocol["evaluation_window"]["common_evaluation_end"],
        "cutoff_date": protocol["evaluation_window"]["common_evaluation_end"],
        "market_snapshot_id": data_contract["market_snapshot"]["snapshot_id"],
        "market_manifest_sha256": data_contract["market_snapshot"]["manifest_sha256"],
        "dividend_snapshot_id": data_contract["dividend_provider"]["snapshot_id"],
        "dividend_manifest_sha256": data_contract["dividend_provider"]["manifest_sha256"],
        "market_sample": market_sample,
        "counts_as_new_research": attempt_class == "new_research",
        **counts,
    }


def _run_logged_synthetic(ledger_path: Path) -> dict[str, Any]:
    protocol = load_protocol()
    trial_id = f"synthetic-{uuid4().hex}"
    start = _trial_start_record(
        protocol,
        ledger_path=ledger_path,
        attempt_class="synthetic_validation",
        trial_id=trial_id,
        market_sample=False,
    )
    append_trial_record(ledger_path, start)
    try:
        report = run_synthetic_preflight()
        end = {
            "trial_id": trial_id,
            "phase": "end",
            "attempt_class": "synthetic_validation",
            "ended_at_utc": datetime.now(timezone.utc).isoformat(),
            "status": report["status"],
            "market_sample": False,
            "counts_as_new_research": False,
        }
    except Exception as exc:
        end = {
            "trial_id": trial_id,
            "phase": "end",
            "attempt_class": "synthetic_validation",
            "ended_at_utc": datetime.now(timezone.utc).isoformat(),
            "status": "failed",
            "failure_type": type(exc).__name__,
            "failure_message": str(exc),
            "market_sample": False,
            "counts_as_new_research": False,
        }
        append_trial_record(ledger_path, end)
        raise
    append_trial_record(ledger_path, end)
    report["trial"] = {"trial_id": trial_id, **{key: start[key] for key in (
        "attempt_class", "market_sample", "counts_as_new_research", "new_research_count",
        "technical_rerun_count", "synthetic_validation_count",
    )}}
    return report


def _run_formal_trial(
    protocol: dict[str, Any],
    *,
    trial_ledger_path: Path | str,
    attempt_class: str,
    trial_id: str | None = None,
    input_loader=None,
) -> dict[str, Any]:
    ledger_path = Path(trial_ledger_path)
    current_trial_id = trial_id or f"gate001-{uuid4().hex}"
    start = _trial_start_record(
        protocol,
        ledger_path=ledger_path,
        attempt_class=attempt_class,
        trial_id=current_trial_id,
        market_sample=True,
    )
    append_trial_record(ledger_path, start)
    try:
        inputs = (input_loader or _load_formal_inputs)(protocol)
        result = _evaluate_nine_paths(inputs, protocol)
        report = {
            "mode": "formal",
            "status": "formal_run_complete",
            "formal_performance_result_allowed": protocol.get("formal_performance_result_allowed") is True,
            "data_loaded": True,
            "metrics": result["scenario_results"],
            **result,
        }
        end = {
            "trial_id": current_trial_id,
            "phase": "end",
            "attempt_class": attempt_class,
            "ended_at_utc": datetime.now(timezone.utc).isoformat(),
            "status": report["status"],
            "deterministic_verdict": result["deterministic_verdict"],
            "validity_errors": result["validity_errors"],
        }
    except Exception as exc:
        report = {
            "mode": "formal",
            "status": "formal_run_failed",
            "formal_performance_result_allowed": False,
            "data_loaded": "inputs" in locals(),
            "metrics": None,
            "failure_type": type(exc).__name__,
            "failure_message": str(exc),
        }
        end = {
            "trial_id": current_trial_id,
            "phase": "end",
            "attempt_class": attempt_class,
            "ended_at_utc": datetime.now(timezone.utc).isoformat(),
            "status": "failed",
            "failure_type": type(exc).__name__,
            "failure_message": str(exc),
        }
    append_trial_record(ledger_path, end)
    report["trial"] = {"trial_id": current_trial_id, **{key: start[key] for key in (
        "attempt_class", "market_sample", "counts_as_new_research", "new_research_count",
        "technical_rerun_count", "synthetic_validation_count",
    )}}
    report["trial_ledger_written"] = True
    return report


def _formal_blockers(protocol: dict[str, Any]) -> list[str]:
    blockers = []
    if protocol.get("formal_performance_result_allowed") is not True:
        blockers.append("formal_performance_result_allowed=false")
    authorization = protocol.get("formal_run_authorization", {})
    if (
        authorization.get("status") != "authorized"
        or not authorization.get("instruction_reference")
    ):
        blockers.append("formal_run_authorization=missing_separate_controller_instruction")
    execution_gate = protocol["account_and_execution"]["execution_fact_gates"]
    execution_status = execution_gate.get("status")
    if execution_status != "accepted_with_research_proxy_limitations":
        blockers.append(f"execution_fact_gates={execution_gate.get('status')}")
    else:
        accepted_execution_evidence = (
            execution_gate.get("accepted_source_years") == [2004, 2006, 2012]
            and "first actually executable daily open" in str(execution_gate.get("research_proxy", ""))
            and bool(execution_gate.get("acceptance_basis"))
            and bool(execution_gate.get("accepted_limitations"))
        )
        if not accepted_execution_evidence:
            blockers.append("execution_fact_gates_evidence=missing_or_mismatched")
    calculation_gate = protocol["gate"]["calculation_contract_gate"]
    if calculation_gate.get("status") != "closed":
        blockers.append(f"calculation_contract_gate={calculation_gate.get('status')}")
    else:
        evidence = calculation_gate.get("closure_evidence")
        evidence_text = " ".join(evidence) if isinstance(evidence, list) else ""
        if (
            "scripts/run_gate001_once.py" not in evidence_text
            or "calculate_cagr" not in evidence_text
            or "risk_free_rate=0.0" not in evidence_text
            or "tests/test_gate001_runner.py" not in evidence_text
            or "synthetic nine-path" not in evidence_text
        ):
            blockers.append("calculation_contract_gate_evidence=missing_or_mismatched")
    return blockers


def _load_formal_inputs(protocol: dict[str, Any]) -> dict[str, Any]:
    """Lazy historical readers; called only after all formal locks close."""
    import hashlib as hash_module
    import json as json_module
    from strategy_core.gate001_dividend_adapter import load_gate001_dividend_snapshot
    import strategy_core.gate001_market_adapter as market_adapter
    from strategy_core.gate001_market_adapter import Gate001MarketDataSource

    source = Gate001MarketDataSource()
    dividend_snapshot = load_gate001_dividend_snapshot()
    raw_pre_close: dict[date, float] = {}
    manifest = source.manifest
    expected_hashes = dict(source.raw_file_hashes)
    for request_id in ("fund_daily_2009_2014", "fund_daily_2015_2020"):
        record = manifest["requests"][request_id]
        relative_path = record["quality"]["file"]
        raw_path = (PROJECT_ROOT / relative_path).resolve()
        if raw_path.parent != (market_adapter.SNAPSHOT_DIR / "raw").resolve():
            raise ValueError("Gate001 raw daily path escaped the pinned snapshot")
        actual_hash = hash_module.sha256(raw_path.read_bytes()).hexdigest().lower()
        if actual_hash != expected_hashes.get(relative_path, "").lower():
            raise ValueError(f"Gate001 raw daily SHA-256 mismatch: {relative_path}")
        raw_rows = json_module.loads(raw_path.read_text(encoding="utf-8"))
        for raw in raw_rows:
            raw_pre_close[date.fromisoformat(
                f"{raw['trade_date'][:4]}-{raw['trade_date'][4:6]}-{raw['trade_date'][6:8]}"
            )] = float(raw["pre_close"])
    rows = []
    for bar in source.get_daily_bars(SYMBOL):
        rows.append({
            "date": bar.date,
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "pre_close": raw_pre_close[bar.date],
            "volume": bar.volume,
            "amount": bar.amount,
            "adj_factor": bar.adj_factor,
        })
    calendar = TradingCalendar(source)
    start = date.fromisoformat(protocol["evaluation_window"]["common_evaluation_start"])
    end = date.fromisoformat(protocol["evaluation_window"]["common_evaluation_end"])
    evaluation_dates = [day for day in calendar.all_trading_dates() if start <= day <= end]
    if not evaluation_dates or evaluation_dates[0] != start or evaluation_dates[-1] != end:
        raise ValueError("Gate001 evaluation window is not present in the pinned market calendar")
    return {
        "protocol": protocol,
        "market_source": source,
        "dividend_snapshot": dividend_snapshot,
        "rows": rows,
        "market_dates": [*calendar.all_trading_dates(), date(2021, 1, 4)],
        "evaluation_dates": evaluation_dates,
        "dividend_events": list(dividend_snapshot.events),
        "date_only_next_session": date(2021, 1, 4),
    }


def _synthetic_rows_and_event() -> tuple[list[dict[str, Any]], list[date], list[date], dict[str, Any]]:
    market_dates = _weekdays(ANCHOR_DATE, 254)
    evaluation_dates = market_dates[250:]
    closes = [9.0] + [10.0] * 248 + [11.0, 9.0]
    rows = []
    for index, day in enumerate(market_dates):
        if index < len(closes):
            opening = closes[index]
            closing = closes[index]
        else:
            opening = 10.0
            closing = 10.0
        if index == 251:
            opening = closing = 9.9
        elif index == 252:
            opening, closing = 10.0, 11.1
        elif index == 253:
            opening, closing = 11.0, 10.9
        previous_close = closes[index - 1] if index > 0 and index < len(closes) else (
            rows[index - 1]["close"] if index > 0 else closing
        )
        rows.append({
            "date": day,
            "open": opening,
            "high": max(opening, closing),
            "low": min(opening, closing),
            "close": closing,
            "pre_close": previous_close,
            "volume": 1_000_000,
            "amount": closing * 1_000_000,
            "adj_factor": 1.0,
        })
    dividend_event = {
        "ts_code": SYMBOL,
        "ann_date": market_dates[250].isoformat(),
        "record_date": market_dates[252].isoformat(),
        "ex_date": market_dates[253].isoformat(),
        "pay_date": market_dates[253].isoformat(),
        "div_cash": "0.10",
        "verified_unit": "CNY per fund unit",
        "source_ref": "synthetic://gate001/record-ex-pay-cycle",
    }
    return rows, market_dates, evaluation_dates, dividend_event


def _synthetic_strategy_config(dates: list[date]) -> StrategyConfig:
    values = parse_strategy_config(CONFIG_PATH).model_dump(mode="python")
    values["strategy_name"] = STRATEGY_NAME
    values["version"] = STRATEGY_VERSION
    values["status"] = "draft"
    values["universe"]["symbols"] = [SYMBOL]
    values["entry_conditions"] = {
        "logic": "AND",
        "rules": [{"type": "adjusted_ma_cross_down", "ma_period": 250}],
    }
    values["exit_conditions"] = {
        "logic": "OR",
        "rules": [{"type": "take_profit_pct", "threshold": 0.10}],
    }
    values["risk_filters"]["max_position_per_stock"] = 1.0
    values["risk_filters"]["max_total_position"] = 1.0
    values["risk_filters"]["min_liquidity_for_trade"] = 0.0
    values["fill_model"]["commission"] = 0.0003
    values["fill_model"]["stamp_tax"] = 0.0
    values["fill_model"]["slippage"] = 0.0005
    values["backtest_config"].update({
        "initial_capital": 100_000.0,
        "start_date": dates[0],
        "end_date": dates[-1],
        "sample_split": {
            "in_sample_end": dates[0],
            "out_of_sample_start": dates[-1],
        },
    })
    values["prototype_gate"]["enabled"] = False
    return StrategyConfig.model_validate(values)


def _weekdays(start: date, count: int) -> list[date]:
    result = []
    current = start
    while len(result) < count:
        if current.weekday() < 5:
            result.append(current)
        current += timedelta(days=1)
    return result


def _next_weekday(value: date) -> date:
    candidate = value + timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return candidate


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_json_safe(report), ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _write_markdown_report(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Gate001 research connection preflight",
        "",
        f"- Status: `{report['status']}`",
        f"- Data classification: `{report.get('data_classification', 'formal_snapshot')}`",
        f"- Formal performance result allowed: `{str(report.get('formal_performance_result_allowed', False)).lower()}`",
        f"- Deterministic verdict: `{report.get('deterministic_verdict', 'not_applicable')}`",
        "",
        (
            "This report validates the nine-path runner and reference reconciliation. Synthetic inputs are not market evidence."
            if report.get("mode") == "synthetic"
            else "Formal study output from the pinned research snapshot; see the JSON report for complete metrics and evidence gaps."
        ),
        "",
        "| Scenario | Strategy | Buy and hold | Cash |",
        "|---|---:|---:|---:|",
    ]
    for scenario_name, paths in report.get("scenario_results", {}).items():
        status_cells = [
            paths[name]["reconciliation"]["status"]
            for name in ("strategy", "buy_hold", "cash")
        ]
        lines.append(f"| {scenario_name} | {status_cells[0]} | {status_cells[1]} | {status_cells[2]} |")
    if report.get("scenario_validity_errors"):
        lines.extend(["", "Validity errors:", *[f"- `{item}`" for item in report["scenario_validity_errors"]]])
    boundary = report.get("terminal_boundary")
    if boundary:
        lines.extend([
            "",
            f"Terminal boundary fixture reconciliation: `{boundary['status']}`; open positions: {boundary['open_trade_count']}; receivable: CNY {boundary['terminal_receivable_cny']:.2f}.",
        ])
    if report.get("mode") == "synthetic":
        lines.append("No historical strategy performance result was produced by this synthetic preflight.")
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the guarded one-shot Gate001 entry")
    parser.add_argument("--mode", choices=("formal", "synthetic"), required=True)
    parser.add_argument("--report-path", type=Path)
    parser.add_argument("--markdown-report-path", type=Path)
    parser.add_argument("--trial-ledger-path", type=Path)
    parser.add_argument(
        "--attempt-class",
        choices=("new_research", "technical_rerun"),
        default="new_research",
    )
    args = parser.parse_args(argv)
    trial_ledger_path = args.trial_ledger_path
    if args.mode == "synthetic" and trial_ledger_path is None:
        trial_ledger_path = TRIAL_LEDGER_PATH
    report = run_gate001_once(
        mode=args.mode,
        trial_ledger_path=trial_ledger_path,
        attempt_class=args.attempt_class,
    )
    if args.report_path is not None:
        _write_report(args.report_path, report)
    elif args.mode == "synthetic":
        default_report = PROJECT_ROOT / "docs" / "verification" / "GATE001_FORMAL_CONNECTION.json"
        _write_report(default_report, report)
    elif report.get("status") == "formal_run_complete" and report.get("formal_performance_result_allowed") is True:
        default_report = PROJECT_ROOT / "docs" / "verification" / "GATE001_FORMAL_RESULT.json"
        _write_report(default_report, report)
    if args.markdown_report_path is not None:
        _write_markdown_report(args.markdown_report_path, report)
    elif args.mode == "synthetic":
        default_markdown = PROJECT_ROOT / "docs" / "verification" / "GATE001_FORMAL_CONNECTION.md"
        _write_markdown_report(default_markdown, report)
    elif report.get("status") == "formal_run_complete" and report.get("formal_performance_result_allowed") is True:
        default_markdown = PROJECT_ROOT / "docs" / "verification" / "GATE001_FORMAL_RESULT.md"
        _write_markdown_report(default_markdown, report)
    print(json.dumps(_json_safe(report), ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if report["status"] in {"synthetic_verified", "formal_run_blocked"} else 1


if __name__ == "__main__":
    sys.exit(main())
