"""Daily close monitoring for explicitly typed open positions."""

from __future__ import annotations

import json
import math
import re
import threading
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from contracts.live_trade import ExecutionObservationLog, ObservationPosition, TradeType


SHANGHAI = ZoneInfo("Asia/Shanghai")


class PositionMarketMonitor:
    """Fetch, cache, and label close-only data for current explicitly typed positions."""

    def __init__(self, cache_root: Path | None = None, client_factory=None):
        if cache_root is None:
            from backend.config.runtime_paths import PROJECT_ROOT

            cache_root = PROJECT_ROOT / "data" / "cache" / "daily_bars"
        self.cache_root = Path(cache_root)
        self.client_factory = client_factory or self._create_client
        self._client = None
        self._lock = threading.RLock()

    @staticmethod
    def _create_client():
        from backend.app.tushare.config import TushareConfig
        from backend.app.tushare.tushare_client import TushareClient

        config = TushareConfig.from_env()
        # One page-session action must make at most one provider attempt per call.
        config.retry_attempts = 1
        return TushareClient(config)

    def _get_client(self):
        if self._client is None:
            self._client = self.client_factory()
        return self._client

    @staticmethod
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

    @staticmethod
    def _parse_date(value: Any) -> date:
        text = str(value)
        if len(text) == 8 and text.isdigit():
            return date(int(text[:4]), int(text[4:6]), int(text[6:8]))
        return date.fromisoformat(text[:10])

    @classmethod
    def expected_trade_date(cls, now: datetime, calendar_rows: Any) -> date:
        """Return the latest completed SSE date under the 15:00 Shanghai cutoff."""
        today = now.date()
        rows = cls._records(calendar_rows)
        opens: set[date] = set()
        today_open: bool | None = None
        for row in rows:
            try:
                cal_date = cls._parse_date(row["cal_date"])
                is_open = str(row["is_open"]).strip() in {"1", "1.0", "True", "true"}
            except (KeyError, TypeError, ValueError):
                continue
            if is_open:
                opens.add(cal_date)
            if cal_date == today:
                today_open = is_open
        if today_open is None:
            raise ValueError("SSE calendar does not cover today")
        if not today_open or now.timetz().replace(tzinfo=None) < time(15, 0):
            previous = [day for day in opens if day < today]
            if not previous:
                raise ValueError("SSE calendar has no previous open date")
            return max(previous)
        return today

    def _calendar_rows(self, now: datetime) -> list[dict]:
        today = now.date()
        path = self.cache_root / "sse_trade_calendar.json"
        cached = self._read_json(path)
        if cached and cached.get("as_of_date") == today.isoformat() and cached.get("rows"):
            return cached["rows"]

        start = today - timedelta(days=90)
        result = self._get_client().query(
            "trade_cal",
            exchange="SSE",
            start_date=start.strftime("%Y%m%d"),
            end_date=today.strftime("%Y%m%d"),
            fields="cal_date,is_open",
        )
        rows = self._records(result)
        self._write_json(path, {"as_of_date": today.isoformat(), "rows": rows})
        return rows

    def trade_calendar_rows_between(self, start_date: date, end_date: date) -> list[dict]:
        """Return complete SSE calendar coverage for an inclusive date range."""
        if start_date > end_date:
            raise ValueError("SSE calendar range starts after it ends")

        requested_dates = [
            start_date + timedelta(days=offset)
            for offset in range((end_date - start_date).days + 1)
        ]

        def covered_rows(rows: Any) -> list[dict] | None:
            by_date: dict[date, bool] = {}
            for row in self._records(rows):
                try:
                    cal_date = self._parse_date(row["cal_date"])
                    raw_open = str(row["is_open"]).strip()
                except (KeyError, TypeError, ValueError):
                    continue
                if raw_open in {"1", "1.0", "True", "true"}:
                    by_date[cal_date] = True
                elif raw_open in {"0", "0.0", "False", "false"}:
                    by_date[cal_date] = False

            if any(day not in by_date for day in requested_dates):
                return None
            return [
                {"cal_date": day.strftime("%Y%m%d"), "is_open": int(by_date[day])}
                for day in requested_dates
            ]

        with self._lock:
            cache = self._read_json(self.cache_root / "sse_trade_calendar.json") or {}
            cached_rows = covered_rows(cache.get("rows", []))
            if cached_rows is not None:
                return cached_rows

            result = self._get_client().query(
                "trade_cal",
                exchange="SSE",
                start_date=start_date.strftime("%Y%m%d"),
                end_date=end_date.strftime("%Y%m%d"),
                fields="cal_date,is_open",
            )
            queried_rows = covered_rows(result)
            if queried_rows is None:
                raise ValueError("SSE calendar does not cover the requested date range")
            return queried_rows

    def _position_path(self, symbol: str) -> Path:
        safe_symbol = re.sub(r"[^A-Za-z0-9._-]", "_", symbol)
        return self.cache_root / f"{safe_symbol}.json"

    @staticmethod
    def _read_json(path: Path) -> dict | None:
        try:
            with path.open("r", encoding="utf-8") as stream:
                value = json.load(stream)
            return value if isinstance(value, dict) else None
        except (OSError, json.JSONDecodeError):
            return None

    def _write_json(self, path: Path, value: dict) -> None:
        self.cache_root.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        with temp.open("w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True)
            stream.flush()
        temp.replace(path)

    def check_positions(
        self,
        positions: list[tuple[ObservationPosition, ExecutionObservationLog | None]],
        *,
        session_id: str,
        now: datetime | None = None,
    ) -> dict:
        """Check each unique eligible symbol once and return per-position close state."""
        now = now or datetime.now(SHANGHAI)
        if now.tzinfo is None:
            now = now.replace(tzinfo=SHANGHAI)
        checked_at = now.isoformat()

        with self._lock:
            symbols: dict[str, list[tuple[ObservationPosition, ExecutionObservationLog | None]]] = {}
            for position, source_log in positions:
                symbols.setdefault(position.symbol, []).append((position, source_log))

            caches = {symbol: self._read_json(self._position_path(symbol)) or {} for symbol in symbols}
            pending = [
                symbol for symbol, entries in symbols.items()
                if not caches[symbol].get("last_check", {}).get("session_id") == session_id
                and any(position.trade_type in {TradeType.actual, TradeType.simulated} for position, _ in entries)
            ]

            expected_date: date | None = None
            calendar_error = False
            if pending:
                try:
                    expected_date = self.expected_trade_date(now, self._calendar_rows(now))
                except Exception:
                    calendar_error = True

            for symbol in pending:
                cache = caches[symbol]
                entries = symbols[symbol]
                typed_entries = [
                    (position, source_log)
                    for position, source_log in entries
                    if position.trade_type in {TradeType.actual, TradeType.simulated}
                ]
                supported_entries = [
                    (position, source_log)
                    for position, source_log in typed_entries
                    if source_log and source_log.security_type in {"stock", "fund"}
                ]
                kinds = {source_log.security_type for _, source_log in supported_entries}
                last_success = cache.get("last_success")
                status = "stale"
                message = "行情未更新；显示上次成功收盘价" if last_success else "行情暂不可用"

                if calendar_error or expected_date is None:
                    message = "交易日历暂不可用"
                elif len(kinds) != 1:
                    status = "unavailable"
                    message = "证券类型未知，无法选择对应日线接口"
                elif last_success and self._parse_date(last_success["trade_date"]) >= expected_date:
                    status = "ok"
                    message = "收盘行情已更新"
                else:
                    security_type = next(iter(kinds))
                    api_name = "fund_daily" if security_type == "fund" else "daily"
                    try:
                        rows = self._records(self._get_client().query(
                            api_name,
                            ts_code=symbol,
                            start_date=expected_date.strftime("%Y%m%d"),
                            end_date=expected_date.strftime("%Y%m%d"),
                            fields="ts_code,trade_date,close",
                        ))
                        valid_rows = []
                        for row in rows:
                            if row.get("ts_code") != symbol:
                                continue
                            try:
                                trade_date = self._parse_date(row["trade_date"])
                                close = float(row["close"])
                            except (KeyError, TypeError, ValueError):
                                continue
                            if trade_date <= expected_date and math.isfinite(close) and close > 0:
                                valid_rows.append((trade_date, close))
                        if valid_rows:
                            trade_date, close = max(valid_rows, key=lambda item: item[0])
                            if not last_success or trade_date >= self._parse_date(last_success["trade_date"]):
                                last_success = {
                                    "trade_date": trade_date.isoformat(),
                                    "close": close,
                                    "fetched_at": checked_at,
                                    "source": "Tushare-compatible",
                                    "api": api_name,
                                    "symbol": symbol,
                                }
                        if last_success and self._parse_date(last_success["trade_date"]) >= expected_date:
                            status = "ok"
                            message = "收盘行情已更新"
                    except Exception:
                        # Keep the last successful close and suppress same-session retries.
                        pass

                cache["last_success"] = last_success
                cache["last_check"] = {
                    "session_id": session_id,
                    "expected_trade_date": expected_date.isoformat() if expected_date else None,
                    "checked_at": checked_at,
                    "status": status,
                    "message": message,
                }
                self._write_json(self._position_path(symbol), cache)
                caches[symbol] = cache

            items = []
            for position, source_log in positions:
                cache = caches.get(position.symbol, {})
                check = cache.get("last_check", {})
                last_success = cache.get("last_success")
                items.append(self._position_view(position, source_log, check, last_success))

            return {"session_id": session_id, "items": items}

    def _position_view(
        self,
        position: ObservationPosition,
        source_log: ExecutionObservationLog | None,
        check: dict,
        last_success: dict | None,
    ) -> dict:
        if position.trade_type == TradeType.unknown:
            return {
                "position_id": position.position_id,
                "symbol": position.symbol,
                "trade_type": "unknown",
                "status": "unavailable",
                "message": "历史记录的交易类型未确认，暂不监控行情",
                "expected_trade_date": None,
                "trade_date": None,
                "close": None,
                "fetched_at": None,
                "source": None,
                "api": None,
                "unrealized_pnl": None,
                "unrealized_pnl_state": "unknown_before_entry",
                "target_price": None,
                "stop_price": None,
                "distance_to_target_pct": None,
                "distance_to_stop_pct": None,
                "alerts": [],
            }
        if not source_log or source_log.security_type not in {"stock", "fund"}:
            return {
                "position_id": position.position_id,
                "symbol": position.symbol,
                "trade_type": position.trade_type.value,
                "status": "unavailable",
                "message": "证券类型未知，无法选择对应日线接口",
                "expected_trade_date": check.get("expected_trade_date"),
                "trade_date": None,
                "close": None,
                "fetched_at": None,
                "source": None,
                "api": None,
                "unrealized_pnl": None,
                "unrealized_pnl_state": "unknown_before_entry",
                "target_price": None,
                "stop_price": None,
                "distance_to_target_pct": None,
                "distance_to_stop_pct": None,
                "alerts": [],
            }
        close = last_success.get("close") if last_success else None
        trade_date = last_success.get("trade_date") if last_success else None
        entry_date = source_log.execution_date if source_log else None
        post_entry_close = bool(entry_date and trade_date and self._parse_date(trade_date) >= entry_date)
        pnl = round((float(close) - position.entry_price) * position.quantity, 2) if close is not None and post_entry_close else None
        target = source_log.exit_plan_target_price if source_log else None
        stop = source_log.exit_plan_stop_price if source_log else None
        can_alert = check.get("status") == "ok" and post_entry_close and close is not None
        alerts: list[str] = []
        if can_alert and target is not None and float(close) >= target:
            alerts.append("target_reached")
        if can_alert and stop is not None and float(close) <= stop:
            alerts.append("stop_reached")
        return {
            "position_id": position.position_id,
            "symbol": position.symbol,
            "trade_type": position.trade_type.value,
            "status": check.get("status", "unavailable"),
            "message": check.get("message", "尚未检查行情"),
            "expected_trade_date": check.get("expected_trade_date"),
            "trade_date": trade_date,
            "close": close,
            "fetched_at": last_success.get("fetched_at") if last_success else None,
            "source": last_success.get("source") if last_success else None,
            "api": last_success.get("api") if last_success else None,
            "unrealized_pnl": pnl,
            "unrealized_pnl_state": "known_gross" if pnl is not None else "unknown_before_entry",
            "target_price": target,
            "stop_price": stop,
            "distance_to_target_pct": round((target - close) / close * 100, 2)
            if post_entry_close and target is not None and close else None,
            "distance_to_stop_pct": round((close - stop) / close * 100, 2)
            if post_entry_close and stop is not None and close else None,
            "alerts": alerts,
        }
