"""Read-only live observation for the frozen Card020 510880 strategy."""

from __future__ import annotations

import hashlib
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable
from zoneinfo import ZoneInfo

from backend.services import card020_vol_budget
from backend.services.card020_vol_budget import (
    INITIAL_CASH,
    SYMBOL,
    _shown,
    _signal_volatility,
    _target_shares,
    _target_weight,
)


SHANGHAI = ZoneInfo("Asia/Shanghai")
_MARKET_CLOSE_DATA_CUTOFF = time(17, 0)
_MARKET_OPEN = time(9, 30)
_CALENDAR_LOOKBACK_DAYS = 180
_CALENDAR_LOOKAHEAD_DAYS = 62
_COMMISSION_RATE = Decimal("0.0003")
_MIN_COMMISSION = Decimal("5.00")
_COMMISSION_RATIO_LIMIT = Decimal("0.005")


class _ObservationFailure(Exception):
    def __init__(self, code: str, message: str, *, endpoint: str | None = None,
                 error_type: str | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.endpoint = endpoint
        self.error_type = error_type


def _records(value: Any) -> list[dict]:
    if value is None:
        return []
    if hasattr(value, "empty") and value.empty:
        return []
    if hasattr(value, "to_dict"):
        try:
            return value.to_dict("records")
        except TypeError:
            pass
    if isinstance(value, dict):
        return [value]
    return [dict(row) for row in value]


def _parse_date(value: Any) -> date:
    text = str(value).strip()
    if len(text) == 8 and text.isdigit():
        return date(int(text[:4]), int(text[4:6]), int(text[6:8]))
    return date.fromisoformat(text[:10])


def _decimal(value: Any, label: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise _ObservationFailure("market_rows_invalid", f"{label} 格式无效。") from None
    if not result.is_finite():
        raise _ObservationFailure("market_rows_invalid", f"{label} 不是有限数值。")
    return result


def _retrieved_at(now: datetime) -> str:
    return now.isoformat(timespec="microseconds")


_SOURCE_ROW_FIELDS = {
    "trade_cal": ("cal_date", "is_open"),
    "fund_daily": ("ts_code", "trade_date", "open", "close", "vol"),
    "fund_adj": ("ts_code", "trade_date", "adj_factor"),
    "fund_div": (
        "ts_code", "ann_date", "imp_anndate", "ex_date", "pay_date", "div_proc", "div_cash",
    ),
}


def _captured_row(endpoint: str, row: dict) -> dict:
    fields = _SOURCE_ROW_FIELDS[endpoint]
    return {
        key: None if row.get(key) is None else str(row.get(key))
        for key in fields
        if key in row
    }


def _timestamp_now() -> str:
    return datetime.now(SHANGHAI).isoformat(timespec="microseconds")


def _finish_observation(result: dict, market_inputs: dict, source_receipts: list[dict], judgment_at: str) -> dict:
    received_at = _timestamp_now()
    result["judgment_at"] = judgment_at
    result["received_at"] = received_at
    result["retrieved_at"] = received_at
    result["_card021_capture"] = {
        "market_inputs": market_inputs,
        "source_receipts": source_receipts,
        "judgment_at": judgment_at,
        "received_at": received_at,
    }
    return result


def card021_implementation_fingerprint() -> str:
    """Fingerprint Card021 calculation and the fixed Card020 math it calls."""
    sources = (
        ("card021_live_observation.py", Path(__file__)),
        ("card020_vol_budget.py", Path(card020_vol_budget.__file__)),
    )
    manifest = "\n".join(
        f"{name}:{hashlib.sha256(path.read_bytes()).hexdigest().upper()}"
        for name, path in sources
    )
    return hashlib.sha256(manifest.encode("utf-8")).hexdigest().upper()


def snapshot_market_inputs(capture: dict, result: dict) -> dict:
    """Keep the signal window and only the market rows needed by its checks."""
    raw = capture.get("market_inputs", {}) if isinstance(capture, dict) else {}
    if result.get("status") != "available":
        return {
            "trade_cal": raw.get("trade_cal", []),
            "fund_daily": raw.get("fund_daily", []),
            "fund_adj": raw.get("fund_adj", []),
            "signal_window": [],
            "anchor_market_rows": [],
            "fund_div": raw.get("fund_div", []),
        }

    window_start = result["signal_window_start"]
    window_end = result["signal_window_end"]
    daily_by_date = {row.get("trade_date"): row for row in raw.get("fund_daily", [])}
    factors_by_date = {row.get("trade_date"): row for row in raw.get("fund_adj", [])}
    open_dates = sorted({
        str(row["cal_date"])
        for row in raw.get("trade_cal", [])
        if str(row.get("is_open", "")).strip() in {"1", "1.0", "True", "true"}
    })
    window_dates = [
        day for day in open_dates
        if window_start.replace("-", "") <= day <= window_end.replace("-", "")
    ]
    if len(window_dates) != 61 or window_dates[-1] != window_end.replace("-", ""):
        raise ValueError("Card021 captured calendar does not match the 61-day result window")
    signal_window = []
    for day in window_dates:
        daily = daily_by_date.get(day)
        factor = factors_by_date.get(day)
        if daily is None or factor is None or "close" not in daily or "adj_factor" not in factor:
            raise ValueError("Card021 captured market rows do not cover the result window")
        signal_window.append({"trade_date": day, "close": daily["close"], "adj_factor": factor["adj_factor"]})

    first_window_index = open_dates.index(window_dates[0])
    anchor_dates = {result["latest_market_data_date"].replace("-", "")}
    if first_window_index > 0:
        anchor_dates.add(open_dates[first_window_index - 1])
    anchors = []
    for day in sorted(anchor_dates - set(window_dates)):
        daily = daily_by_date.get(day)
        factor = factors_by_date.get(day)
        if daily is None or factor is None:
            raise ValueError("Card021 captured market rows do not cover a required market anchor")
        anchors.append({
            "trade_date": day,
            "close": daily.get("close"),
            "vol": daily.get("vol"),
            "adj_factor": factor.get("adj_factor"),
        })

    return {
        "trade_cal": raw.get("trade_cal", []),
        "signal_window": signal_window,
        "anchor_market_rows": anchors,
        "fund_div": raw.get("fund_div", []),
    }


def _unavailable(code: str, message: str, now: datetime, *, provider_call_attempted: bool,
                 endpoint: str | None = None, error_type: str | None = None,
                 sources: list[dict] | None = None,
                 completed_endpoints: list[str] | None = None) -> dict:
    result = {
        "status": "unavailable",
        "failure_code": code,
        "failure_message": message,
        "strategy_id": "510880-vol-budget-v1",
        "protocol_revision": 3,
        "symbol": SYMBOL,
        "evidence_level": "数据不足",
        "provider_call_attempted": provider_call_attempted,
        "provider_responses_received": completed_endpoints or [],
        "retrieved_at": _retrieved_at(now),
        "source_origin_authenticated": False,
        "sources": sources or [],
        "target_weight": None,
        "model_reference_shares": None,
        "actual_shares": None,
        "actual_delta_shares": None,
        "action_decision": "not_decidable",
    }
    if endpoint:
        result["failed_endpoint"] = endpoint
    if error_type:
        result["error_type"] = error_type
    return result


def _client_rows(client, endpoint: str, fields: str | None, params: dict,
                 attempted: list[str], completed: list[str], market_inputs: dict,
                 source_receipts: list[dict]) -> list[dict]:
    attempted.append(endpoint)
    receipt = {
        "endpoint": endpoint,
        "query_fields": fields,
        "query_params": params,
        "request_started_at": _timestamp_now(),
    }
    try:
        response = client.query(
            endpoint,
            fields=fields,
            single_attempt=True,
            **params,
        )
    except Exception as exc:
        receipt.update({
            "received_at": _timestamp_now(),
            "response_status": "error",
            "error_type": type(exc).__name__,
        })
        source_receipts.append(receipt)
        raise _ObservationFailure(
            "market_source_query_failed",
            "行情来源请求失败，未生成目标。",
            endpoint=endpoint,
            error_type=type(exc).__name__,
        ) from None
    receipt["received_at"] = _timestamp_now()
    try:
        rows = _records(response)
        market_inputs[endpoint] = [_captured_row(endpoint, row) for row in rows]
    except Exception as exc:
        receipt.update({"response_status": "invalid_response", "error_type": type(exc).__name__})
        source_receipts.append(receipt)
        raise _ObservationFailure(
            "market_source_query_failed",
            "行情来源请求失败，未生成目标。",
            endpoint=endpoint,
            error_type=type(exc).__name__,
        ) from None
    receipt.update({"row_count": len(rows), "response_status": "received"})
    source_receipts.append(receipt)
    completed.append(endpoint)
    return rows


def _source_summaries(source_receipts: list[dict]) -> list[dict]:
    return [
        {
            "source": "configured_tushare_client",
            "endpoint": receipt["endpoint"],
            "request_started_at": receipt["request_started_at"],
            "received_at": receipt["received_at"],
            "retrieved_at": receipt["received_at"],
            **({"row_count": receipt["row_count"]} if "row_count" in receipt else {}),
            "response_status": receipt["response_status"],
            **({"error_type": receipt["error_type"]} if "error_type" in receipt else {}),
            "provider_origin_authenticated": False,
        }
        for receipt in source_receipts
    ]


def _calendar_index(rows: list[dict], start: date, end: date) -> dict[date, bool]:
    indexed: dict[date, bool] = {}
    for row in rows:
        try:
            day = _parse_date(row["cal_date"])
            raw_open = str(row["is_open"]).strip()
        except (KeyError, TypeError, ValueError):
            continue
        if raw_open in {"1", "1.0", "True", "true"}:
            is_open = True
        elif raw_open in {"0", "0.0", "False", "false"}:
            is_open = False
        else:
            continue
        if day in indexed and indexed[day] != is_open:
            raise _ObservationFailure("sse_calendar_conflict", "SSE 交易日历存在冲突。")
        indexed[day] = is_open

    expected = start
    while expected <= end:
        if expected not in indexed:
            raise _ObservationFailure("sse_calendar_incomplete", "SSE 交易日历未覆盖所需日期。")
        expected += timedelta(days=1)
    return indexed


def _symbol_rows(rows: list[dict], endpoint: str) -> dict[date, dict]:
    indexed: dict[date, dict] = {}
    for row in rows:
        if row.get("ts_code") != SYMBOL:
            raise _ObservationFailure("market_symbol_mismatch", "行情来源返回了不同证券代码。", endpoint=endpoint)
        try:
            day = _parse_date(row["trade_date"])
        except (KeyError, TypeError, ValueError):
            raise _ObservationFailure("market_rows_invalid", "行情日期无效。", endpoint=endpoint) from None
        if day in indexed:
            raise _ObservationFailure("market_rows_duplicate", "行情来源返回重复交易日。", endpoint=endpoint)
        indexed[day] = row
    return indexed


def _validate_dividend_coverage(
    rows: list[dict],
    *,
    signal_date: date,
    window_start: date,
    open_dates: list[date],
    daily: dict[date, dict],
    factors: dict[date, dict],
) -> dict:
    if not rows:
        raise _ObservationFailure("dividend_source_empty", "基金分红接口未返回可核实记录。", endpoint="fund_div")

    implemented_before_signal = 0
    window_events: dict[date, Decimal] = {}
    reported_dates: list[date] = []
    for row in rows:
        if row.get("ts_code") != SYMBOL:
            raise _ObservationFailure("market_symbol_mismatch", "分红来源返回了不同证券代码。", endpoint="fund_div")
        procedure = str(row.get("div_proc") or "").strip()
        ex_date_value = row.get("ex_date")
        if not ex_date_value:
            if procedure == "实施":
                raise _ObservationFailure("dividend_source_incomplete", "已实施分红记录缺少除息日。", endpoint="fund_div")
            continue
        try:
            ex_date = _parse_date(ex_date_value)
        except (TypeError, ValueError):
            raise _ObservationFailure("dividend_source_incomplete", "分红来源的除息日无效。", endpoint="fund_div") from None
        if ex_date <= signal_date:
            reported_dates.append(ex_date)
        if window_start <= ex_date <= signal_date and procedure != "实施":
            raise _ObservationFailure("dividend_source_incomplete", "信号窗口内的分红尚未核实为已实施。", endpoint="fund_div")
        if procedure != "实施":
            continue
        if ex_date <= signal_date:
            implemented_before_signal += 1
        if not (window_start <= ex_date <= signal_date):
            continue
        try:
            announcement = _parse_date(row.get("ann_date"))
            implementation_announcement = _parse_date(row.get("imp_anndate"))
        except (TypeError, ValueError):
            raise _ObservationFailure("dividend_source_incomplete", "信号窗口内分红缺少可核实公告日期。", endpoint="fund_div") from None
        if announcement > signal_date or implementation_announcement > signal_date:
            raise _ObservationFailure("dividend_lookahead", "信号窗口内分红公告晚于信号日。", endpoint="fund_div")
        cash = _decimal(row.get("div_cash"), "每份现金分红")
        if cash < 0 or ex_date not in open_dates:
            raise _ObservationFailure("dividend_source_incomplete", "分红金额或除息交易日无效。", endpoint="fund_div")
        if ex_date in window_events:
            raise _ObservationFailure("dividend_source_duplicate", "信号窗口内分红事件重复。", endpoint="fund_div")
        window_events[ex_date] = cash

    if implemented_before_signal == 0:
        raise _ObservationFailure("dividend_source_no_implemented_history", "分红来源没有信号日前已实施记录。", endpoint="fund_div")

    matched = 0
    window_dates = [day for day in open_dates if window_start <= day <= signal_date]
    open_before = {day: open_dates[index - 1] for index, day in enumerate(open_dates) if index > 0}
    for ex_date in window_dates:
        previous_date = open_before.get(ex_date)
        if (
            previous_date is None
            or previous_date not in daily
            or ex_date not in daily
            or previous_date not in factors
            or ex_date not in factors
        ):
            raise _ObservationFailure("dividend_adjustment_window_incomplete", "除息日前后行情或复权因子不完整。", endpoint="fund_adj")
        previous_factor = _decimal(factors[previous_date].get("adj_factor"), "前一交易日复权因子")
        ex_factor = _decimal(factors[ex_date].get("adj_factor"), "当日复权因子")
        if previous_factor <= 0 or ex_factor <= 0:
            raise _ObservationFailure("dividend_adjustment_mismatch", "复权因子无法安全核对。", endpoint="fund_adj")
        actual_ratio = ex_factor / previous_factor
        cash = window_events.get(ex_date)
        if cash is None:
            if abs(actual_ratio - Decimal(1)) > Decimal("0.00000001"):
                raise _ObservationFailure(
                    "dividend_source_uncovered_adjustment",
                    "信号窗口复权因子发生变化，但分红来源没有对应的已实施事件。",
                    endpoint="fund_div",
                )
            continue
        previous_close = _decimal(daily[previous_date].get("close"), "除息日前收盘价")
        if previous_close <= cash:
            raise _ObservationFailure("dividend_adjustment_mismatch", "分红金额与复权因子无法安全核对。", endpoint="fund_adj")
        expected_ratio = previous_close / (previous_close - cash)
        relative_error = abs(actual_ratio - expected_ratio) / expected_ratio
        if relative_error > Decimal("0.00001"):
            raise _ObservationFailure("dividend_adjustment_mismatch", "信号窗口分红金额与复权因子口径不一致。", endpoint="fund_adj")
        matched += 1

    return {
        "row_count": len(rows),
        "implemented_history_event_count": implemented_before_signal,
        "matched_signal_window_event_count": matched,
        "latest_reported_ex_date": max(reported_dates).isoformat() if reported_dates else None,
        "coverage": "verified_signal_window_factor_changes",
        "used_in_signal_math": False,
    }


def _account_snapshot(account_provider, signal_date: date, latest_data_date: date,
                      raw_signal_close: Decimal, weight: Decimal) -> dict:
    base = {
        "account_snapshot_status": "not_provided",
        "account_source": None,
        "actual_shares": None,
        "sellable_shares_as_of_latest_market_data": None,
        "account_target_shares": None,
        "actual_delta_shares": None,
        "account_cash_at_signal_cny": None,
        "dividend_receivable_at_signal_cny": None,
    }
    if account_provider is None:
        return base
    try:
        snapshot = account_provider(signal_date, latest_data_date)
    except Exception as exc:
        return {**base, "account_snapshot_status": "unavailable", "account_error_type": type(exc).__name__}
    if not isinstance(snapshot, dict):
        return {**base, "account_snapshot_status": "invalid"}

    status = snapshot.get("status")
    if status != "user_confirmed_position":
        return {**base, "account_snapshot_status": status if isinstance(status, str) else "unverified"}
    if (
        snapshot.get("record_source") != "autonomous_manual"
        or snapshot.get("confirmed_by_user") is not True
        or snapshot.get("broker_verified") is not False
    ):
        return {**base, "account_snapshot_status": "provenance_unverified"}

    actual_shares = snapshot.get("actual_shares")
    sellable_shares = snapshot.get("sellable_shares")
    if (
        type(actual_shares) is not int or actual_shares < 0
        or type(sellable_shares) is not int or not 0 <= sellable_shares <= actual_shares
    ):
        return {**base, "account_snapshot_status": "quantity_invalid"}

    result = {
        **base,
        "account_snapshot_status": "position_confirmed_nav_missing",
        "account_source": "user_confirmed_autonomous_manual_records_unverified_by_broker",
        "actual_shares": actual_shares,
        "sellable_shares_as_of_latest_market_data": sellable_shares,
    }
    shares_at_signal = snapshot.get("shares_at_signal")
    cash_at_signal = snapshot.get("account_cash_at_signal_cny")
    receivable_at_signal = snapshot.get("dividend_receivable_at_signal_cny")
    if type(shares_at_signal) is not int or shares_at_signal < 0 or cash_at_signal is None or receivable_at_signal is None:
        return result
    try:
        cash = _decimal(cash_at_signal, "信号日账户可用现金")
        receivable = _decimal(receivable_at_signal, "信号日分红应收")
    except _ObservationFailure:
        return {**result, "account_snapshot_status": "account_nav_invalid"}
    if cash < 0 or receivable < 0:
        return {**result, "account_snapshot_status": "account_nav_invalid"}
    nav = cash + Decimal(shares_at_signal) * raw_signal_close + receivable
    if not nav.is_finite() or nav < 0:
        return {**result, "account_snapshot_status": "account_nav_invalid"}
    target_shares = _target_shares(weight, nav, raw_signal_close)
    return {
        **result,
        "account_snapshot_status": "user_confirmed_nav_available",
        "account_target_shares": target_shares,
        "actual_delta_shares": target_shares - actual_shares,
        "account_cash_at_signal_cny": format(cash, ".2f"),
        "dividend_receivable_at_signal_cny": format(receivable, ".2f"),
    }


class _Card020MarketWindow:
    def __init__(self, closes: dict[date, Decimal], factors: dict[date, Decimal]):
        self._closes = closes
        self._factors = factors

    def get_daily_bar(self, symbol: str, day: date):
        if symbol != SYMBOL or day not in self._closes or day not in self._factors:
            raise _ObservationFailure("adjusted_close_window_incomplete", "61 个有效复权收盘价不完整。")
        return SimpleNamespace(close=self._closes[day], adj_factor=self._factors[day])


def get_card021_live_observation(
    client_provider: Callable[[], Any],
    *,
    account_provider: Callable[[date, date], dict] | None = None,
    now: datetime | None = None,
) -> dict:
    """Query fresh read-only sources and apply Card020's frozen target math."""
    now = now or datetime.now(SHANGHAI)
    if now.tzinfo is None:
        now = now.replace(tzinfo=SHANGHAI)
    judgment_at = _retrieved_at(now)
    market_inputs: dict[str, list[dict]] = {}
    source_receipts: list[dict] = []

    try:
        client = client_provider()
    except Exception as exc:
        return _finish_observation(
            _unavailable(
                "market_client_unavailable",
                "市场数据客户端未完成初始化；尚未请求行情数据。",
                now,
                provider_call_attempted=False,
                error_type=type(exc).__name__,
            ),
            market_inputs,
            source_receipts,
            judgment_at,
        )

    start = now.date() - timedelta(days=_CALENDAR_LOOKBACK_DAYS)
    calendar_end = now.date() + timedelta(days=_CALENDAR_LOOKAHEAD_DAYS)
    attempted: list[str] = []
    completed: list[str] = []
    try:
        calendar_rows = _client_rows(
            client,
            "trade_cal",
            "cal_date,is_open",
            {
                "exchange": "SSE",
                "start_date": start.strftime("%Y%m%d"),
                "end_date": calendar_end.strftime("%Y%m%d"),
            },
            attempted,
            completed,
            market_inputs,
            source_receipts,
        )
        calendar = _calendar_index(calendar_rows, start, calendar_end)
        open_dates = sorted(day for day, is_open in calendar.items() if is_open)
        today_open = calendar.get(now.date())
        if today_open is None:
            raise _ObservationFailure("sse_calendar_incomplete", "SSE 交易日历未覆盖今天。")
        if today_open and now.timetz().replace(tzinfo=None) >= _MARKET_CLOSE_DATA_CUTOFF:
            latest_complete = now.date()
        else:
            previous = [day for day in open_dates if day < now.date()]
            if not previous:
                raise _ObservationFailure("sse_calendar_incomplete", "SSE 交易日历缺少最近已完成交易日。")
            latest_complete = previous[-1]

        daily_rows = _client_rows(
            client,
            "fund_daily",
            "ts_code,trade_date,open,close,vol",
            {
                "ts_code": SYMBOL,
                "start_date": start.strftime("%Y%m%d"),
                "end_date": latest_complete.strftime("%Y%m%d"),
            },
            attempted,
            completed,
            market_inputs,
            source_receipts,
        )
        adjustment_rows = _client_rows(
            client,
            "fund_adj",
            "ts_code,trade_date,adj_factor",
            {
                "ts_code": SYMBOL,
                "start_date": start.strftime("%Y%m%d"),
                "end_date": latest_complete.strftime("%Y%m%d"),
            },
            attempted,
            completed,
            market_inputs,
            source_receipts,
        )
        dividend_rows = _client_rows(
            client,
            "fund_div",
            None,
            {"ts_code": SYMBOL},
            attempted,
            completed,
            market_inputs,
            source_receipts,
        )

        daily = _symbol_rows(daily_rows, "fund_daily")
        factors = _symbol_rows(adjustment_rows, "fund_adj")
        if latest_complete not in daily or latest_complete not in factors:
            raise _ObservationFailure(
                "latest_market_data_missing",
                "最新已完成交易日的行情或复权因子尚未齐备。",
            )

        month_last_open: dict[tuple[int, int], date] = {}
        for day in open_dates:
            key = (day.year, day.month)
            month_last_open[key] = max(day, month_last_open.get(key, day))
        completed_month_ends = [
            day for day in month_last_open.values()
            if day <= latest_complete
        ]
        if not completed_month_ends:
            raise _ObservationFailure("month_end_signal_unavailable", "没有可用的已完成月末信号日。")
        signal_date = max(completed_month_ends)
        window_dates = [day for day in open_dates if day <= signal_date][-61:]
        if len(window_dates) != 61 or window_dates[-1] != signal_date:
            raise _ObservationFailure("adjusted_close_window_incomplete", "月末信号日缺少完整 61 个交易日窗口。")

        closes: dict[date, Decimal] = {}
        factor_values: dict[date, Decimal] = {}
        for day in window_dates:
            if day not in daily or day not in factors:
                raise _ObservationFailure("adjusted_close_window_incomplete", "61 个有效复权收盘价不完整。")
            close = _decimal(daily[day].get("close"), "原始收盘价")
            factor = _decimal(factors[day].get("adj_factor"), "复权因子")
            if close <= 0 or factor <= 0:
                raise _ObservationFailure("market_rows_invalid", "原始收盘价或复权因子必须为正数。")
            closes[day] = close
            factor_values[day] = factor

        volatility, used_dates = _signal_volatility(
            _Card020MarketWindow(closes, factor_values),
            window_dates,
            signal_date,
        )
        weight = _target_weight(volatility)
        raw_signal_close = closes[signal_date]
        model_reference_shares = _target_shares(weight, INITIAL_CASH, raw_signal_close)

        dividend_summary = _validate_dividend_coverage(
            dividend_rows,
            signal_date=signal_date,
            window_start=window_dates[0],
            open_dates=open_dates,
            daily=daily,
            factors=factors,
        )

        next_signal_attempt = next((day for day in open_dates if day > signal_date), None)
        if today_open and now.timetz().replace(tzinfo=None) < _MARKET_OPEN:
            next_possible_attempt = now.date()
        else:
            next_possible_attempt = next((day for day in open_dates if day > now.date()), None)
        target_valid_until = next((day for day in sorted(month_last_open.values()) if day > signal_date), None)
        if next_signal_attempt is None or next_possible_attempt is None or target_valid_until is None:
            raise _ObservationFailure("sse_calendar_incomplete", "SSE 交易日历未覆盖下一次可尝试交易日。")
        previous_signal_date = max((day for day in completed_month_ends if day < signal_date), default=None)
        first_attempt_has_passed = (
            next_signal_attempt < now.date()
            or (
                next_signal_attempt == now.date()
                and bool(today_open)
                and now.timetz().replace(tzinfo=None) >= _MARKET_OPEN
            )
        )
        first_attempt_status = "past" if first_attempt_has_passed else "not_started"
        target_is_valid = next_possible_attempt <= target_valid_until
        target_validity_status = "active_until_next_month_end" if target_is_valid else "expired"
        retry_policy_status = (
            "not_eligible_expired"
            if not target_is_valid
            else "conditional_unresolved_remainder_not_tracked"
            if first_attempt_status == "past"
            else "first_attempt_not_started"
        )

        latest_volume_hands: int | None = None
        raw_volume = daily[latest_complete].get("vol")
        if raw_volume is not None:
            volume_hands = _decimal(raw_volume, "前一交易日成交量（手）")
            if volume_hands < 0:
                raise _ObservationFailure("market_rows_invalid", "前一交易日成交量不能为负。")
            latest_volume_hands = int(volume_hands)
        volume_capacity_shares = None
        attempt_index = open_dates.index(next_possible_attempt)
        previous_session_for_attempt = open_dates[attempt_index - 1] if attempt_index > 0 else None
        volume_capacity_status = (
            "previous_session_not_yet_complete"
            if previous_session_for_attempt != latest_complete
            else "previous_session_volume_missing"
            if latest_volume_hands is None
            else "verified"
        )
        if volume_capacity_status == "verified":
            capacity_lots = (Decimal(latest_volume_hands) * Decimal("0.10")).to_integral_value(rounding=ROUND_DOWN)
            volume_capacity_shares = int(capacity_lots) * 100

        account = _account_snapshot(
            account_provider,
            signal_date,
            latest_complete,
            raw_signal_close,
            weight,
        )
        if not target_is_valid:
            account["account_target_shares"] = None
            account["actual_delta_shares"] = None
        execution_gate = (
            "blocked_target_expired"
            if not target_is_valid
            else "blocked_missing_account_nav_or_cash"
            if account["account_target_shares"] is None
            else "blocked_attempt_date_constraints_not_checked"
        )

        result = {
            "status": "available",
            "strategy_id": "510880-vol-budget-v1",
            "protocol_revision": 3,
            "symbol": SYMBOL,
            "evidence_level": "低",
            "signal_date": signal_date.isoformat(),
            "supersedes_signal_date": previous_signal_date.isoformat() if previous_signal_date else None,
            "latest_market_data_date": latest_complete.isoformat(),
            "retrieved_at": _retrieved_at(now),
            "signal_window_start": used_dates[0].isoformat(),
            "signal_window_end": used_dates[-1].isoformat(),
            "valid_adjusted_close_count": len(used_dates),
            "signal_volatility": _shown(volatility),
            "target_weight": _shown(weight),
            "target_weight_percentage": _shown(weight * Decimal(100)),
            "target_price_raw_cny": _shown(raw_signal_close),
            "model_account_cash_cny": format(INITIAL_CASH, ".2f"),
            "model_reference_shares": model_reference_shares,
            "actual_shares": account["actual_shares"],
            "sellable_shares_as_of_latest_market_data": account["sellable_shares_as_of_latest_market_data"],
            "account_target_shares": account["account_target_shares"],
            "actual_delta_shares": account["actual_delta_shares"],
            "account_data_status": account["account_snapshot_status"],
            "account_source": account["account_source"],
            "account_cash_at_signal_cny": account["account_cash_at_signal_cny"],
            "dividend_receivable_at_signal_cny": account["dividend_receivable_at_signal_cny"],
            "execution_gate": execution_gate,
            "action_decision": "not_decidable",
            "research_rationale": (
                "已按固定修订3规则计算月末目标；本页只显示既有用户确认成交记录，不能核实券商持仓。"
                "现金与分红应收未从账户路径取得，无法计算真实账户目标或执行判断；仅研究参考。"
            ),
            "earliest_attempt_after_signal_date": next_signal_attempt.isoformat(),
            "first_attempt_status": first_attempt_status,
            "next_possible_attempt_date": next_possible_attempt.isoformat(),
            "target_valid_until": target_valid_until.isoformat(),
            "target_validity_status": target_validity_status,
            "retry_policy_status": retry_policy_status,
            "retry_rule": "协议只允许在本月目标有效期内，对尚未完成且合规的剩余差额逐交易日重试；本页不跟踪剩余委托状态。",
            "adjustment_source_status": "61个信号窗口交易日均有复权因子；最新已完成交易日也有因子。",
            "dividend_source": {
                "endpoint": "fund_div",
                "query_status": "queried",
                **dividend_summary,
            },
            "market_constraints": {
                "orders_submitted": False,
                "account_cash_cny": None,
                "actual_shares": account["actual_shares"],
                "sellable_shares": account["sellable_shares_as_of_latest_market_data"],
                "execution_gate": execution_gate,
                "account_affordability": "not_computed_without_account_cash",
                "round_lot_shares": 100,
                "t_plus_one": "当日买入份额不能当日卖出。",
                "max_daily_volume_fraction": "0.10",
                "previous_session_volume_hands": latest_volume_hands if volume_capacity_status == "verified" else None,
                "volume_capacity_shares_for_next_possible_attempt": volume_capacity_shares,
                "volume_capacity_source_date": previous_session_for_attempt.isoformat() if volume_capacity_status == "verified" else None,
                "volume_capacity_status": volume_capacity_status,
                "commission_rate": format(_COMMISSION_RATE, "f"),
                "minimum_commission_cny": format(_MIN_COMMISSION, ".2f"),
                "commission_ratio_limit": format(_COMMISSION_RATIO_LIMIT, "f"),
                "minimum_order_value_for_commission_filter_cny": format(
                    _MIN_COMMISSION / _COMMISSION_RATIO_LIMIT, ".2f",
                ),
                "other_fees": "not_independently_verified",
                "suspension_and_price_limits": "must_be_checked_on_the_attempt_date",
                "execution_price": "must_use_attempt_date_open; unavailable before that session",
            },
            "source_freshness": {
                "market_data_as_of": latest_complete.isoformat(),
                "calendar_coverage_through": calendar_end.isoformat(),
                "origin_authenticated": False,
                "dividend_coverage": dividend_summary["coverage"],
            },
            "source_origin_authenticated": False,
            "provider_call_attempted": True,
            "provider_responses_received": completed,
            "sources": _source_summaries(source_receipts),
        }
        return _finish_observation(result, market_inputs, source_receipts, judgment_at)
    except _ObservationFailure as exc:
        return _finish_observation(
            _unavailable(
                exc.code,
                exc.message,
                now,
                provider_call_attempted=bool(attempted),
                endpoint=exc.endpoint,
                error_type=exc.error_type,
                sources=_source_summaries(source_receipts),
                completed_endpoints=completed,
            ),
            market_inputs,
            source_receipts,
            judgment_at,
        )
    except Exception as exc:
        return _finish_observation(
            _unavailable(
                "observation_calculation_failed",
                "行情输入无法安全核验，未生成目标。",
                now,
                provider_call_attempted=bool(attempted),
                error_type=type(exc).__name__,
                sources=_source_summaries(source_receipts),
                completed_endpoints=completed,
            ),
            market_inputs,
            source_receipts,
            judgment_at,
        )
