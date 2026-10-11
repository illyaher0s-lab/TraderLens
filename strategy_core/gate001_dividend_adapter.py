from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from strategy_core.dividend_ledger import DividendLedger


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_ID = "fund_div_announcements_20261005T004106Z"
MANIFEST_PATH = (
    PROJECT_ROOT
    / "data"
    / "alpha_gate_001"
    / SNAPSHOT_ID
    / "manifest.json"
)
EXPECTED_MANIFEST_SHA256 = "AFC16B529242C160E311FC23C002B1EA4B4DBA22D9493AF6458AE2ECDF8CEE68"
TARGET_SYMBOL = "510880.SH"
ANN_DATE_WINDOW = (date(2009, 1, 1), date(2020, 12, 31))
DIV_CASH_FIELD_UNIT = "每股派息(元)"
VERIFIED_UNIT = "CNY per fund unit"


@dataclass(frozen=True)
class Gate001DividendSnapshot:
    """Verified file snapshot plus raw event rows ready for DividendLedger."""

    snapshot_id: str
    manifest_sha256: str
    ann_date_window: tuple[date, date]
    raw_file_hashes: tuple[tuple[str, str], ...]
    target_raw_rows: int
    duplicate_rows: int
    events: tuple[dict[str, object], ...]
    official_spotcheck_dates: tuple[date, ...]
    evidence_gap: str


def _verify_sha256(path: Path, expected_sha256: str, label: str) -> str:
    actual = hashlib.sha256(path.read_bytes()).hexdigest().upper()
    if actual != expected_sha256.strip().upper():
        raise ValueError(f"{label} SHA-256 mismatch: {path}")
    return actual


def _parse_raw_date(value: object, field_name: str, raw_path: Path, row_index: int) -> date:
    if not isinstance(value, str) or len(value) != 8 or not value.isdigit():
        raise ValueError(
            f"{raw_path} row {row_index}: {field_name} must be YYYYMMDD"
        )
    try:
        return date(int(value[:4]), int(value[4:6]), int(value[6:8]))
    except ValueError as exc:
        raise ValueError(
            f"{raw_path} row {row_index}: invalid {field_name}={value}"
        ) from exc


def load_gate001_dividend_snapshot() -> Gate001DividendSnapshot:
    """Read only the pinned 2009–2020 Gate001 fund-dividend raw snapshot.

    Returned rows preserve one source reference per raw line. The regular
    ``DividendLedger`` performs economic-event deduplication and is used here
    as a preflight too; callers pass ``snapshot.events`` to ``run_backtest``.
    """
    manifest_hash = _verify_sha256(
        MANIFEST_PATH, EXPECTED_MANIFEST_SHA256, "Gate001 dividend manifest"
    )
    try:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("Gate001 dividend manifest is unreadable") from exc

    if manifest.get("schema") != "alpha_gate_001_fund_div_raw.v1":
        raise ValueError("unexpected Gate001 dividend manifest schema")
    if manifest.get("snapshot_id") != SNAPSHOT_ID or manifest.get("status") != "raw_unverified":
        raise ValueError("Gate001 dividend snapshot identity or status mismatch")
    scope = manifest.get("scope", {})
    if (
        scope.get("ts_code") != TARGET_SYMBOL
        or scope.get("ann_date_min") != "20090101"
        or scope.get("ann_date_max") != "20201231"
    ):
        raise ValueError("Gate001 dividend snapshot scope mismatch")

    field_units = manifest.get("documented_field_units", {})
    if field_units.get("div_cash") != DIV_CASH_FIELD_UNIT:
        raise ValueError("Gate001 div_cash unit is missing or unverified")

    requests = manifest.get("requests")
    if not isinstance(requests, dict) or not requests:
        raise ValueError("Gate001 dividend manifest has no raw-file inventory")

    events: list[dict[str, object]] = []
    raw_file_hashes: list[tuple[str, str]] = []
    target_keys: dict[tuple[str, date], tuple[date, date, date, Decimal, str]] = {}
    expected_target_rows = 0
    start_date, end_date = ANN_DATE_WINDOW

    for request_ann_date, record in sorted(requests.items()):
        if record.get("status") != "raw" or record.get("sent") is not True:
            raise ValueError(f"raw request {request_ann_date} is not a saved response")
        relative_path = record.get("file")
        expected_raw_hash = record.get("sha256")
        if not isinstance(relative_path, str) or not isinstance(expected_raw_hash, str):
            raise ValueError(f"raw request {request_ann_date} is missing file/hash metadata")
        raw_path = (PROJECT_ROOT / relative_path).resolve()
        expected_parent = (MANIFEST_PATH.parent / "raw").resolve()
        if raw_path.parent != expected_parent:
            raise ValueError(f"raw path escapes the pinned Gate001 snapshot: {relative_path}")
        raw_hash = _verify_sha256(raw_path, expected_raw_hash, "Gate001 dividend raw file")
        raw_file_hashes.append((relative_path, raw_hash))

        try:
            rows = json.loads(raw_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"raw response is unreadable: {relative_path}") from exc
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            raise ValueError(f"raw response must be a list of objects: {relative_path}")

        expected_target_rows += int(record.get("target_rows_saved", 0))
        for row_index, row in enumerate(rows):
            if row.get("ts_code") != TARGET_SYMBOL:
                continue
            ann_date = _parse_raw_date(row.get("ann_date"), "ann_date", raw_path, row_index)
            if not start_date <= ann_date <= end_date:
                continue
            if row.get("verified_unit", VERIFIED_UNIT) != VERIFIED_UNIT:
                raise ValueError(f"{raw_path} row {row_index}: verified unit conflict")

            record_date = _parse_raw_date(row.get("record_date"), "record_date", raw_path, row_index)
            ex_date = _parse_raw_date(row.get("ex_date"), "ex_date", raw_path, row_index)
            pay_date = _parse_raw_date(row.get("pay_date"), "pay_date", raw_path, row_index)
            try:
                div_cash = Decimal(str(row.get("div_cash")))
            except (InvalidOperation, ValueError):
                raise ValueError(f"{raw_path} row {row_index}: invalid div_cash") from None
            if not div_cash.is_finite() or div_cash <= 0:
                raise ValueError(f"{raw_path} row {row_index}: invalid div_cash")
            if not ann_date <= record_date <= ex_date <= pay_date:
                raise ValueError(f"{raw_path} row {row_index}: dividend date order conflict")
            if _parse_raw_date(request_ann_date, "request ann_date", raw_path, row_index) != ann_date:
                raise ValueError(f"{raw_path} row {row_index}: request/event announcement mismatch")

            key = (TARGET_SYMBOL, ann_date)
            details = (record_date, ex_date, pay_date, div_cash, VERIFIED_UNIT)
            if key in target_keys and target_keys[key] != details:
                raise ValueError(f"conflicting Gate001 dividend event for {key}")
            target_keys[key] = details

            # div_cash is already CNY per fund unit; preserve it without /10 conversion.
            source_ref = (
                f"{SNAPSHOT_ID}|manifest_sha256={manifest_hash.lower()}|"
                f"raw={relative_path}|raw_sha256={raw_hash.lower()}|row={row_index}"
            )
            events.append({
                "ts_code": TARGET_SYMBOL,
                "ann_date": ann_date.isoformat(),
                "record_date": record_date.isoformat(),
                "ex_date": ex_date.isoformat(),
                "pay_date": pay_date.isoformat(),
                "div_cash": format(div_cash, "f"),
                "verified_unit": VERIFIED_UNIT,
                "source_ref": source_ref,
            })

    if len(events) != expected_target_rows:
        raise ValueError(
            f"Gate001 target-row count mismatch: read {len(events)}, manifest declares {expected_target_rows}"
        )
    declared_ann_dates = {
        _parse_raw_date(value, "declared ann_date", MANIFEST_PATH, 0)
        for value in scope.get("unique_announcement_dates_from_prior_probe", [])
    }
    if set(key[1] for key in target_keys) != declared_ann_dates:
        raise ValueError("Gate001 economic-event keys do not match the manifest scope")

    normalized = DividendLedger(events).events
    if len(normalized) != len(declared_ann_dates):
        raise ValueError("Gate001 dividend ledger normalization count mismatch")

    return Gate001DividendSnapshot(
        snapshot_id=SNAPSHOT_ID,
        manifest_sha256=manifest_hash.lower(),
        ann_date_window=ANN_DATE_WINDOW,
        raw_file_hashes=tuple(raw_file_hashes),
        target_raw_rows=len(events),
        duplicate_rows=len(events) - len(normalized),
        events=tuple(events),
        official_spotcheck_dates=(date(2019, 1, 10), date(2020, 1, 13)),
        evidence_gap=(
            "The raw snapshot is marked raw_unverified; official announcement checks cover only "
            "2019-01-10 and 2020-01-13. They do not establish full-history completeness or "
            "independently verify every historical event."
        ),
    )
