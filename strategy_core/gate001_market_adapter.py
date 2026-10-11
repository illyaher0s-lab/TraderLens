from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from contracts import SCHEMA_VERSION
from contracts.stable import DailyBar, DailyStatus
from strategy_core.data_source_metadata import DataSourceMetadata, validate_metadata
from strategy_core.data_source_protocol import DataSourceValidationResult


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_ID = "snapshot_20261005T002537Z"
SNAPSHOT_DIR = PROJECT_ROOT / "data" / "alpha_gate_001" / SNAPSHOT_ID
MANIFEST_PATH = SNAPSHOT_DIR / "manifest.json"
EXPECTED_MANIFEST_SHA256 = "C434E25E79736FD58F77A37F5B6D47A0465BAFD85DC08D06F6D6482C9EAEF9F4"
TARGET_SYMBOL = "510880.SH"
EXPECTED_STATUS = "downloaded_unverified_for_research_use"
EXPECTED_SCHEMA = "alpha_gate_001_raw_data_snapshot.v1"
EXPECTED_DAILY_ROWS = 2918
PRICE_TICK = Decimal("0.001")
PRICE_LIMIT_RATE = Decimal("0.10")
VOLUME_MULTIPLIER = Decimal("100")
AMOUNT_MULTIPLIER = Decimal("1000")


EXPECTED_REQUESTS: dict[str, tuple[str, dict[str, str]]] = {
    "fund_adj_2009_2014": (
        "fund_adj",
        {"ts_code": TARGET_SYMBOL, "start_date": "20090101", "end_date": "20141231"},
    ),
    "fund_adj_2015_2020": (
        "fund_adj",
        {"ts_code": TARGET_SYMBOL, "start_date": "20150101", "end_date": "20201231"},
    ),
    "fund_daily_2009_2014": (
        "fund_daily",
        {"ts_code": TARGET_SYMBOL, "start_date": "20090101", "end_date": "20141231"},
    ),
    "fund_daily_2015_2020": (
        "fund_daily",
        {"ts_code": TARGET_SYMBOL, "start_date": "20150101", "end_date": "20201231"},
    ),
    "trade_cal_2009_2014": (
        "trade_cal",
        {"exchange": "SSE", "is_open": "1", "start_date": "20090101", "end_date": "20141231"},
    ),
    "trade_cal_2015_2020": (
        "trade_cal",
        {"exchange": "SSE", "is_open": "1", "start_date": "20150101", "end_date": "20201231"},
    ),
}


def _verify_sha256(path: Path, expected_sha256: str, label: str) -> str:
    actual = hashlib.sha256(path.read_bytes()).hexdigest().upper()
    if actual != expected_sha256.strip().upper():
        raise ValueError(f"{label} SHA-256 mismatch: {path}")
    return actual


def _parse_raw_date(value: object, field_name: str, raw_path: Path, row_index: int) -> date:
    if not isinstance(value, str) or len(value) != 8 or not value.isdigit():
        raise ValueError(f"{raw_path} row {row_index}: {field_name} must be YYYYMMDD")
    try:
        return date(int(value[:4]), int(value[4:6]), int(value[6:8]))
    except ValueError as exc:
        raise ValueError(
            f"{raw_path} row {row_index}: invalid {field_name}={value}"
        ) from exc


def _decimal_value(value: object, field_name: str, raw_path: Path, row_index: int) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"{raw_path} row {row_index}: invalid {field_name}") from None
    if not parsed.is_finite():
        raise ValueError(f"{raw_path} row {row_index}: invalid {field_name}")
    return parsed


def _require_price_tick(value: Decimal, field_name: str, raw_path: Path, row_index: int) -> None:
    if value <= 0:
        raise ValueError(f"{raw_path} row {row_index}: {field_name} must be positive")
    if value % PRICE_TICK != 0:
        raise ValueError(f"{raw_path} row {row_index}: {field_name} is not on the 0.001 tick")


def _derive_price_limits(pre_close: Decimal) -> tuple[Decimal, Decimal]:
    """Return lower and upper research bands from the known previous close."""
    if not pre_close.is_finite() or pre_close <= 0:
        raise ValueError("pre_close must be finite and positive to derive price limits")
    if pre_close % PRICE_TICK != 0:
        raise ValueError("pre_close must use the 0.001 tick to derive price limits")
    upper_limit = (pre_close * (Decimal("1") + PRICE_LIMIT_RATE)).quantize(
        PRICE_TICK, rounding=ROUND_HALF_UP
    )
    lower_limit = (pre_close * (Decimal("1") - PRICE_LIMIT_RATE)).quantize(
        PRICE_TICK, rounding=ROUND_HALF_UP
    )
    return lower_limit, upper_limit


def _derive_open_status(
    symbol: str,
    trade_date: date,
    open_price: Decimal,
    pre_close: Decimal,
) -> DailyStatus:
    """Derive opening eligibility from observed open and prior close only.

    This is a research model for the pinned Gate001 snapshot, not an exchange
    status feed or a claim that an order would receive queue priority.
    """
    if not open_price.is_finite() or open_price <= 0:
        raise ValueError(f"{symbol} {trade_date}: open must be finite and positive")
    if not pre_close.is_finite() or pre_close <= 0:
        raise ValueError(f"{symbol} {trade_date}: pre_close must be finite and positive")
    if open_price % PRICE_TICK != 0 or pre_close % PRICE_TICK != 0:
        raise ValueError(f"{symbol} {trade_date}: open and pre_close must use the 0.001 tick")

    lower_limit, upper_limit = _derive_price_limits(pre_close)
    return DailyStatus(
        date=trade_date,
        symbol=symbol,
        is_st=False,
        # A valid positive opening print is evidence the fund traded at open.
        is_suspended=False,
        is_limit_up=open_price >= upper_limit,
        is_limit_down=open_price <= lower_limit,
    )


def _parse_daily_row(
    row: dict[str, Any],
    adj_factor: Decimal,
    raw_path: Path,
    row_index: int,
) -> tuple[DailyBar, DailyStatus]:
    required_fields = (
        "ts_code", "trade_date", "open", "high", "low", "close", "pre_close", "vol", "amount"
    )
    for field_name in required_fields:
        if field_name not in row or row[field_name] is None:
            raise ValueError(f"{raw_path} row {row_index}: missing {field_name}")
    if row["ts_code"] != TARGET_SYMBOL:
        raise ValueError(f"{raw_path} row {row_index}: unexpected symbol {row['ts_code']}")

    trade_date = _parse_raw_date(row["trade_date"], "trade_date", raw_path, row_index)
    prices = {
        field_name: _decimal_value(row[field_name], field_name, raw_path, row_index)
        for field_name in ("open", "high", "low", "close", "pre_close")
    }
    for field_name, price in prices.items():
        _require_price_tick(price, field_name, raw_path, row_index)
    if prices["low"] > prices["high"]:
        raise ValueError(f"{raw_path} row {row_index}: low exceeds high")
    if not prices["low"] <= prices["open"] <= prices["high"]:
        raise ValueError(f"{raw_path} row {row_index}: open is outside low/high")
    if not prices["low"] <= prices["close"] <= prices["high"]:
        raise ValueError(f"{raw_path} row {row_index}: close is outside low/high")

    raw_volume = _decimal_value(row["vol"], "vol", raw_path, row_index)
    raw_amount = _decimal_value(row["amount"], "amount", raw_path, row_index)
    if raw_volume <= 0:
        raise ValueError(f"{raw_path} row {row_index}: vol must be positive")
    if raw_amount <= 0:
        raise ValueError(f"{raw_path} row {row_index}: amount must be positive")
    converted_volume = raw_volume * VOLUME_MULTIPLIER
    if converted_volume != converted_volume.to_integral_value():
        raise ValueError(f"{raw_path} row {row_index}: vol does not convert to whole shares")
    if not adj_factor.is_finite() or adj_factor <= 0:
        raise ValueError(f"{raw_path} row {row_index}: adj_factor must be finite and positive")

    bar = DailyBar(
        date=trade_date,
        symbol=TARGET_SYMBOL,
        open=float(prices["open"]),
        high=float(prices["high"]),
        low=float(prices["low"]),
        close=float(prices["close"]),
        volume=int(converted_volume),
        amount=float(raw_amount * AMOUNT_MULTIPLIER),
        adj_factor=float(adj_factor),
    )
    status = _derive_open_status(
        TARGET_SYMBOL, trade_date, prices["open"], prices["pre_close"]
    )
    return bar, status


def _read_raw_rows(path: Path, expected_rows: int, expected_sha256: str, label: str) -> list[dict[str, Any]]:
    _verify_sha256(path, expected_sha256, label)
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is unreadable: {path}") from exc
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError(f"{label} must be a JSON array of objects: {path}")
    if len(rows) != expected_rows:
        raise ValueError(f"{label} row count mismatch: {len(rows)} != {expected_rows}")
    return rows


class Gate001MarketDataSource:
    """Read the pinned Gate001 ETF snapshot as a research-only data source.

    The adapter does not call a provider. Opening limit status is derived from
    ``open`` and ``pre_close`` using the accepted 10%/0.001 research rule;
    source authentication, queue priority, and intraday halts are unavailable.
    """

    def __init__(self) -> None:
        self.manifest_sha256 = _verify_sha256(
            MANIFEST_PATH, EXPECTED_MANIFEST_SHA256, "Gate001 market manifest"
        ).lower()
        try:
            manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("Gate001 market manifest is unreadable") from exc
        self.manifest = manifest
        self._validate_manifest_identity(manifest)

        daily_rows: dict[date, tuple[dict[str, Any], Path, int]] = {}
        factor_rows: dict[date, Decimal] = {}
        open_calendar_dates: set[date] = set()
        raw_file_hashes: list[tuple[str, str]] = []
        requests = manifest["requests"]
        raw_root = (SNAPSHOT_DIR / "raw").resolve()

        for request_id, (expected_api, expected_params) in EXPECTED_REQUESTS.items():
            record = requests[request_id]
            if record.get("status") != "success" or record.get("sent") is not True:
                raise ValueError(f"Gate001 request {request_id} is not a saved success")
            if record.get("api") != expected_api or record.get("params") != expected_params:
                raise ValueError(f"Gate001 request {request_id} does not match pinned scope")
            quality = record.get("quality")
            if not isinstance(quality, dict):
                raise ValueError(f"Gate001 request {request_id} is missing quality metadata")
            relative_path = quality.get("file")
            expected_raw_hash = quality.get("sha256")
            expected_rows = quality.get("rows")
            if not isinstance(relative_path, str) or not isinstance(expected_raw_hash, str):
                raise ValueError(f"Gate001 request {request_id} is missing file/hash metadata")
            if not isinstance(expected_rows, int) or expected_rows <= 0:
                raise ValueError(f"Gate001 request {request_id} has invalid row count")
            raw_path = (PROJECT_ROOT / relative_path).resolve()
            if raw_path.parent != raw_root:
                raise ValueError(f"Gate001 raw path escapes the pinned snapshot: {relative_path}")
            rows = _read_raw_rows(raw_path, expected_rows, expected_raw_hash, request_id)
            raw_file_hashes.append((relative_path, expected_raw_hash.lower()))

            for row_index, row in enumerate(rows):
                if expected_api == "fund_daily":
                    if row.get("ts_code") != TARGET_SYMBOL:
                        raise ValueError(f"{raw_path} row {row_index}: unexpected symbol")
                    trade_date = _parse_raw_date(row.get("trade_date"), "trade_date", raw_path, row_index)
                    if trade_date in daily_rows:
                        raise ValueError(f"{raw_path} row {row_index}: duplicate daily row for {trade_date}")
                    daily_rows[trade_date] = (row, raw_path, row_index)
                elif expected_api == "fund_adj":
                    if row.get("ts_code") != TARGET_SYMBOL:
                        raise ValueError(f"{raw_path} row {row_index}: unexpected factor symbol")
                    trade_date = _parse_raw_date(row.get("trade_date"), "trade_date", raw_path, row_index)
                    if trade_date in factor_rows:
                        raise ValueError(f"{raw_path} row {row_index}: duplicate factor row for {trade_date}")
                    factor = _decimal_value(row.get("adj_factor"), "adj_factor", raw_path, row_index)
                    if factor <= 0:
                        raise ValueError(f"{raw_path} row {row_index}: adj_factor must be positive")
                    factor_rows[trade_date] = factor
                else:
                    if row.get("exchange") != "SSE" or row.get("is_open") not in (1, "1"):
                        raise ValueError(f"{raw_path} row {row_index}: calendar row is not SSE-open")
                    trade_date = _parse_raw_date(row.get("cal_date"), "cal_date", raw_path, row_index)
                    if trade_date in open_calendar_dates:
                        raise ValueError(f"{raw_path} row {row_index}: duplicate open calendar date {trade_date}")
                    open_calendar_dates.add(trade_date)

        if len(daily_rows) != EXPECTED_DAILY_ROWS:
            raise ValueError(f"Gate001 daily row count mismatch: {len(daily_rows)} != {EXPECTED_DAILY_ROWS}")
        if set(daily_rows) != set(factor_rows):
            raise ValueError("Gate001 daily bars and adjustment factors are not date-aligned")
        if set(daily_rows) != open_calendar_dates:
            raise ValueError("Gate001 daily bars and SSE open calendar are not date-aligned")

        self._dates = sorted(daily_rows)
        if self._dates[0] != date(2009, 1, 5) or self._dates[-1] != date(2020, 12, 31):
            raise ValueError("Gate001 daily date range does not match the pinned 2009–2020 scope")
        self._bars: list[DailyBar] = []
        self._statuses: list[DailyStatus] = []
        self._bar_index: dict[date, DailyBar] = {}
        self._status_index: dict[date, DailyStatus] = {}
        self._price_limit_index: dict[date, tuple[Decimal, Decimal]] = {}
        for trade_date in self._dates:
            daily_row, raw_path, row_index = daily_rows[trade_date]
            bar, status = _parse_daily_row(
                daily_row, factor_rows[trade_date], raw_path, row_index
            )
            pre_close = _decimal_value(
                daily_row["pre_close"], "pre_close", raw_path, row_index
            )
            self._bars.append(bar)
            self._statuses.append(status)
            self._bar_index[trade_date] = bar
            self._status_index[trade_date] = status
            self._price_limit_index[trade_date] = _derive_price_limits(pre_close)
        self.raw_file_hashes = tuple(sorted(raw_file_hashes))

    @staticmethod
    def _validate_manifest_identity(manifest: dict[str, Any]) -> None:
        if manifest.get("schema") != EXPECTED_SCHEMA:
            raise ValueError("unexpected Gate001 market manifest schema")
        if manifest.get("snapshot_id") != SNAPSHOT_ID or manifest.get("status") != EXPECTED_STATUS:
            raise ValueError("Gate001 market snapshot identity or status mismatch")
        scope = manifest.get("scope", {})
        if (
            scope.get("symbol") != TARGET_SYMBOL
            or scope.get("calendar_mode") != "SSE open dates only (is_open=1)"
            or scope.get("preheat_start") != "20090101"
            or scope.get("research_start") != "20100101"
            or scope.get("research_end") != "20201231"
        ):
            raise ValueError("Gate001 market snapshot scope mismatch")
        requests = manifest.get("requests")
        if not isinstance(requests, dict) or set(requests) != set(EXPECTED_REQUESTS):
            raise ValueError("Gate001 market manifest request inventory mismatch")
        created_at = manifest.get("created_at_utc")
        if not isinstance(created_at, str):
            raise ValueError("Gate001 market manifest is missing created_at_utc")
        try:
            datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("Gate001 market manifest has invalid created_at_utc") from exc

    def symbols(self) -> list[str]:
        return [TARGET_SYMBOL]

    def get_daily_bars(self, symbol: str) -> list[DailyBar]:
        self._require_target(symbol)
        return list(self._bars)

    def get_daily_statuses(self, symbol: str) -> list[DailyStatus]:
        self._require_target(symbol)
        return list(self._statuses)

    def get_daily_bar(self, symbol: str, target_date: date) -> DailyBar:
        self._require_target(symbol)
        try:
            return self._bar_index[target_date]
        except KeyError as exc:
            raise KeyError(f"no Gate001 daily bar for {symbol} on {target_date}") from exc

    def get_daily_status(self, symbol: str, target_date: date) -> DailyStatus:
        self._require_target(symbol)
        try:
            return self._status_index[target_date]
        except KeyError as exc:
            raise KeyError(f"no Gate001 daily status for {symbol} on {target_date}") from exc

    def get_daily_price_limits(
        self,
        symbol: str,
        target_date: date,
    ) -> tuple[Decimal, Decimal]:
        """Return lower and upper bands derived from this date's raw pre_close."""
        self._require_target(symbol)
        try:
            return self._price_limit_index[target_date]
        except KeyError as exc:
            raise KeyError(f"no Gate001 daily price limits for {symbol} on {target_date}") from exc

    def get_price(self, symbol: str, target_date: date) -> float:
        return self.get_daily_bar(symbol, target_date).close

    def get_metadata(self) -> DataSourceMetadata:
        created_at = datetime.fromisoformat(
            self.manifest["created_at_utc"].replace("Z", "+00:00")
        )
        metadata = DataSourceMetadata(
            source_id=f"gate001_{SNAPSHOT_ID}_{TARGET_SYMBOL}",
            # DataSourceMetadata only admits these legacy source_type values;
            # TushareDataSource uses this same frozen-snapshot convention.
            source_type="fixed_fixture",
            schema_version=SCHEMA_VERSION,
            snapshot_id=SNAPSHOT_ID,
            snapshot_hash=self.manifest_sha256,
            created_at=created_at,
            data_mode="real_data",
            is_frozen=True,
            symbol_count=1,
            trading_days=len(self._dates),
            date_range_start=self._dates[0].isoformat(),
            date_range_end=self._dates[-1].isoformat(),
        )
        validate_metadata(metadata)
        return metadata

    def validate(self) -> DataSourceValidationResult:
        return DataSourceValidationResult(
            status="degraded",
            source_id=self.get_metadata().source_id,
            checked_at=datetime.now(),
            errors=[],
            warnings=[
                "Snapshot status is downloaded_unverified_for_research_use; internal file hashes do not authenticate provider origin or establish full-history completeness.",
                "DailyStatus opening eligibility is derived from positive open and pre_close with 10% bands rounded half-up to 0.001; it is not exchange-certified and does not model queue priority or intraday partial suspensions.",
                "Volume uses the documented-provider expectation vol × 100 shares and amount × 1000 CNY; the raw manifest does not declare units, so this remains an explicit unit assumption.",
            ],
            checks_performed=[
                "pinned_manifest_sha256",
                "raw_file_sha256",
                "manifest_scope",
                "daily_factor_calendar_alignment",
                "bar_price_and_volume_fields",
                "derived_opening_status",
            ],
        )

    @staticmethod
    def _require_target(symbol: str) -> None:
        if symbol != TARGET_SYMBOL:
            raise KeyError(f"Gate001 market snapshot only contains {TARGET_SYMBOL}: {symbol}")
