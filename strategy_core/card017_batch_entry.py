"""Narrow, one-shot entry for the frozen Card017 historical batch.

Importing this module and running the read-only preflight do not compute any
historical signal or performance. Historical execution additionally requires
the total controller to mark the external batch state released and the operator
to pass the exact batch ID on the command line.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from strategy_core.card017_batch_reconcile import reconcile_batch
from strategy_core.card017_month_end_backtest import run_path
from strategy_core.dividend_ledger import DividendLedger
from strategy_core.gate001_dividend_adapter import load_gate001_dividend_snapshot
from strategy_core.gate001_market_adapter import Gate001MarketDataSource
from strategy_core.trading_calendar import TradingCalendar


BATCH_ID = "card017-510880-2018-2020-v1-001"
SYMBOL = "510880.SH"
START_DATE = date(2018, 1, 2)
END_DATE = date(2020, 12, 31)
PREHEAT_SIGNAL_DATE = date(2017, 12, 29)
ANCHOR_DATE = date(2009, 1, 5)
READY_STATUS = "ready_for_controller_released_run"
DEFAULT_VALIDATION_DIR = Path(r"D:\TraderLens_validation\card017-20261020")
STATUS_PATH = DEFAULT_VALIDATION_DIR / "batch-001-status.json"
RESULT_PATH = DEFAULT_VALIDATION_DIR / "batch-001-ledger.json"
LOCK_PATH = DEFAULT_VALIDATION_DIR / "batch-001.lock"
PREFLIGHT_PATH = DEFAULT_VALIDATION_DIR / "phase-b-input-preflight-001.json"


@dataclass(frozen=True)
class PathSpec:
    status_name: str
    path_id: str
    account_kind: str
    slippage_rate: str


PATH_SPECS = (
    PathSpec("candidate_base_5bp", "candidate-base", "candidate", "0.0005"),
    PathSpec("candidate_stress_10bp", "candidate-stress", "candidate", "0.001"),
    PathSpec("buy_hold_base_5bp", "buy_and_hold-base", "buy_and_hold", "0.0005"),
    PathSpec("buy_hold_stress_10bp", "buy_and_hold-stress", "buy_and_hold", "0.001"),
)

CODE_PATHS = (
    "strategy_core/__init__.py",
    "strategy_core/card017_batch_entry.py",
    "strategy_core/card017_month_end_backtest.py",
    "strategy_core/card017_batch_reconcile.py",
    "strategy_core/gate001_market_adapter.py",
    "strategy_core/gate001_dividend_adapter.py",
    "strategy_core/dividend_ledger.py",
    "strategy_core/fill_simulator.py",
    "strategy_core/portfolio.py",
    "strategy_core/transaction_costs.py",
    "strategy_core/trading_calendar.py",
    "strategy_core/data_source_metadata.py",
    "strategy_core/data_source_protocol.py",
    "contracts/stable.py",
    "contracts/draft.py",
    "contracts/__init__.py",
    "backend/app/__init__.py",
    "backend/app/contracts.py",
    "backend/app/golden_cases.py",
)


class BatchEntryError(RuntimeError):
    """Raised when the fixed historical batch is not safe to start."""


def validate_run_gate(state: dict[str, Any], *, release_batch_id: str) -> tuple[PathSpec, ...]:
    """Require the exact one-time batch, four named paths, and controller release."""
    if release_batch_id != BATCH_ID:
        raise BatchEntryError("controller release must name the fixed batch ID")
    if state.get("batch_id") != BATCH_ID:
        raise BatchEntryError("batch state has a different batch ID")
    if state.get("status") != READY_STATUS:
        raise BatchEntryError("batch is not marked ready after controller review")
    release = state.get("release")
    if (
        not isinstance(release, dict)
        or release.get("authority") != "total_controller"
        or release.get("approved_batch_id") != BATCH_ID
    ):
        raise BatchEntryError("batch state has no controller release for this batch")
    if state.get("historical_run_count") != 0:
        raise BatchEntryError("historical run count is not zero; refusing any rerun")
    if state.get("historical_execution_started") is not False:
        raise BatchEntryError("historical execution already started; refusing any rerun")
    if state.get("allowed_historical_batch_count") != 1:
        raise BatchEntryError("batch state does not authorize exactly one historical batch")
    expected_names = [spec.status_name for spec in PATH_SPECS]
    if state.get("execution_paths") != expected_names:
        raise BatchEntryError("batch path mapping does not match the four frozen paths")
    return PATH_SPECS


def normalize_window_dividends(events) -> list[dict[str, object]]:
    """Apply the existing DividendLedger economic-key dedupe and retain sources."""
    start_ex_date = START_DATE
    normalized = DividendLedger(events).events
    result = []
    for event in normalized:
        if not start_ex_date <= event.ex_date <= END_DATE:
            continue
        result.append({
            "ts_code": event.symbol,
            "ann_date": event.ann_date.isoformat(),
            "record_date": event.record_date.isoformat(),
            "ex_date": event.ex_date.isoformat(),
            "pay_date": event.pay_date.isoformat(),
            "div_cash": format(event.div_cash, "f"),
            "verified_unit": "CNY per fund unit",
            "source_ref": "\n".join(event.source_refs),
        })
    return result


def _code_fingerprint(project_root: Path) -> dict[str, Any]:
    files = {}
    for relative in CODE_PATHS:
        path = project_root / relative
        if not path.is_file():
            raise BatchEntryError(f"required code file is missing: {relative}")
        files[relative] = hashlib.sha256(path.read_bytes()).hexdigest().upper()
    canonical = "\n".join(f"{path}\0{digest}" for path, digest in sorted(files.items()))
    return {
        "sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest().upper(),
        "files": files,
    }


def _data_fingerprint(market, dividends) -> dict[str, Any]:
    return {
        "market": {
            "snapshot_id": market.manifest["snapshot_id"],
            "manifest_sha256": market.manifest_sha256.upper(),
            "raw_files": dict(sorted((path, digest.upper()) for path, digest in market.raw_file_hashes)),
        },
        "dividends": {
            "snapshot_id": dividends.snapshot_id,
            "manifest_sha256": dividends.manifest_sha256.upper(),
            "raw_files": dict(sorted((path, digest.upper()) for path, digest in dividends.raw_file_hashes)),
        },
    }


def _prepare_inputs() -> tuple[Gate001MarketDataSource, TradingCalendar, list[dict[str, object]], dict[str, Any]]:
    market = Gate001MarketDataSource()
    dividends = load_gate001_dividend_snapshot()
    calendar = TradingCalendar(market)
    trading_dates = calendar.all_trading_dates()
    preheat_dates = [day for day in trading_dates if day <= PREHEAT_SIGNAL_DATE]
    if PREHEAT_SIGNAL_DATE not in trading_dates or len(preheat_dates) < 250:
        raise BatchEntryError("pinned calendar does not cover the initial 250-session signal window")
    if START_DATE not in trading_dates or END_DATE not in trading_dates:
        raise BatchEntryError("pinned calendar does not cover the fixed research window")
    events = normalize_window_dividends(dividends.events)
    if len(events) != 3:
        raise BatchEntryError(f"expected the three pre-mapped window dividend events, got {len(events)}")
    DividendLedger(events).validate_for_backtest(START_DATE, END_DATE, trading_dates)
    metadata = {
        "market": {
            "snapshot_id": market.manifest["snapshot_id"],
            "status": market.manifest["status"],
            "manifest_sha256": market.manifest_sha256.upper(),
            "raw_file_hashes": dict(sorted((path, digest.upper()) for path, digest in market.raw_file_hashes)),
            "bar_count": len(market.get_daily_bars(SYMBOL)),
            "calendar_count": len(trading_dates),
            "first_date": trading_dates[0].isoformat(),
            "last_date": trading_dates[-1].isoformat(),
            "preheat_end_present": PREHEAT_SIGNAL_DATE in trading_dates,
            "preheat_sessions_through_2017_12_29": len(preheat_dates),
            "ma250_coverage": len(preheat_dates) >= 250,
            "research_window_sessions": sum(START_DATE <= day <= END_DATE for day in trading_dates),
            "window_start_present": START_DATE in trading_dates,
            "window_end_present": END_DATE in trading_dates,
        },
        "dividends": {
            "snapshot_id": dividends.snapshot_id,
            "manifest_sha256": dividends.manifest_sha256.upper(),
            "raw_file_hashes": dict(sorted((path, digest.upper()) for path, digest in dividends.raw_file_hashes)),
            "raw_target_rows": dividends.target_raw_rows,
            "duplicate_rows_removed_by_existing_ledger": dividends.duplicate_rows,
            "normalized_event_count": dividends.target_raw_rows - dividends.duplicate_rows,
            "window_events": events,
            "official_spotcheck_dates": [day.isoformat() for day in dividends.official_spotcheck_dates],
            "raw_snapshot_status": "raw_unverified (preserved from the existing adapter)",
            "historical_adapter_note": dividends.evidence_gap,
            "card017_window_coverage": (
                "closed by the pre-existing 2018-2020 official annual-report/original-announcement review; "
                "reused without reopening broader historical coverage"
            ),
        },
        "historical_strategy_metrics_computed": False,
    }
    return market, calendar, events, metadata


def _json_default(value: object) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    raise TypeError(f"cannot serialize {type(value).__name__}")


def _atomic_json_write(path: Path, payload: object, *, refuse_existing: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if refuse_existing and path.exists():
        raise BatchEntryError(f"refusing to replace existing artifact: {path}")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def run_batch_once(*, release_batch_id: str) -> dict[str, Any]:
    """Run only after the batch state records controller release; never retry."""
    project_root = Path(__file__).resolve().parents[1]
    state = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    path_specs = validate_run_gate(state, release_batch_id=release_batch_id)
    if RESULT_PATH.exists() or LOCK_PATH.exists():
        raise BatchEntryError("batch lock or result already exists; refusing another run")

    protocol = state.get("protocol", {})
    protocol_path = project_root / str(protocol.get("path", ""))
    if not protocol_path.is_file():
        raise BatchEntryError("the frozen protocol file is missing")
    protocol_hash = hashlib.sha256(protocol_path.read_bytes()).hexdigest().upper()
    if protocol_hash != str(protocol.get("sha256", "")).upper():
        raise BatchEntryError("frozen protocol hash changed after preflight")

    market, calendar, events, preflight = _prepare_inputs()
    data_hashes = _data_fingerprint(market, load_gate001_dividend_snapshot())
    if state.get("data", {}).get("actual_data_hashes_before_run") != data_hashes:
        raise BatchEntryError("pinned input hashes differ from the saved read-only preflight")
    code_hashes = _code_fingerprint(project_root)
    recorded_code = state.get("code", {})
    if recorded_code.get("sha256_before_run") != code_hashes["sha256"]:
        raise BatchEntryError("running or reconciliation code changed after preflight")
    if recorded_code.get("files") != code_hashes["files"]:
        raise BatchEntryError("one or more code file hashes changed after preflight")

    # O_EXCL is the durable single-writer lock. It is intentionally never removed.
    try:
        lock_fd = os.open(str(LOCK_PATH), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise BatchEntryError("the unique batch lock already exists; refusing another run") from None
    with os.fdopen(lock_fd, "w", encoding="utf-8") as lock_file:
        lock_file.write(json.dumps({"batch_id": BATCH_ID, "pid": os.getpid(), "claimed_at": datetime.now().astimezone().isoformat()}))

    # Re-read and claim after obtaining the exclusive lock. This is persisted
    # before the first strategy signal or historical performance calculation.
    state = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    validate_run_gate(state, release_batch_id=release_batch_id)
    state["status"] = "RUNNING"
    state["historical_execution_started"] = True
    state["historical_run_count"] = 1
    state["run_started_at_local"] = datetime.now().astimezone().isoformat()
    state["run_protocol_sha256"] = protocol_hash
    state["run_input_hashes"] = data_hashes
    state["run_code_hashes"] = code_hashes
    state["path_id_mapping"] = {spec.status_name: spec.path_id for spec in path_specs}
    _atomic_json_write(STATUS_PATH, state)

    paths = []
    phase = "strategy_paths"
    try:
        for spec in path_specs:
            ledger = run_path(
                market,
                calendar,
                account_kind=spec.account_kind,
                start_date=START_DATE,
                end_date=END_DATE,
                events=events,
                slippage_rate=Decimal(spec.slippage_rate),
                anchor_date=ANCHOR_DATE,
            )
            if ledger.get("path_id") != spec.path_id:
                raise BatchEntryError(f"runner path ID does not match frozen mapping for {spec.status_name}")
            paths.append(ledger)
        phase = "independent_reconciliation"
        reconciliation = reconcile_batch(paths, market, calendar, events=events)
        report = {
            "batch_id": BATCH_ID,
            "status": "RECONCILED",
            "protocol_sha256": protocol_hash,
            "input_hashes": data_hashes,
            "code_hashes": code_hashes,
            "preflight": preflight,
            "path_id_mapping": {spec.status_name: spec.path_id for spec in path_specs},
            "path_ledgers": paths,
            "reconciliation": reconciliation,
        }
        _atomic_json_write(RESULT_PATH, report, refuse_existing=True)
        state["status"] = "COMPLETED"
        state["reconciliation"]["status"] = "RECONCILED"
        state["result_path"] = str(RESULT_PATH)
        state["run_finished_at_local"] = datetime.now().astimezone().isoformat()
        _atomic_json_write(STATUS_PATH, state)
        return report
    except Exception as exc:
        abort_report = {
            "batch_id": BATCH_ID,
            "status": "ABORTED",
            "failed_phase": phase,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "protocol_sha256": protocol_hash,
            "input_hashes": data_hashes,
            "code_hashes": code_hashes,
            "preflight": preflight,
            "path_id_mapping": {spec.status_name: spec.path_id for spec in path_specs},
            "partial_path_ledgers": paths,
        }
        _atomic_json_write(RESULT_PATH, abort_report, refuse_existing=True)
        state["status"] = "ABORTED"
        state["reconciliation"]["status"] = "ABORTED" if phase == "independent_reconciliation" else "not_reached"
        state["abort_reason"] = {"phase": phase, "type": type(exc).__name__, "message": str(exc)}
        state["result_path"] = str(RESULT_PATH)
        state["run_finished_at_local"] = datetime.now().astimezone().isoformat()
        _atomic_json_write(STATUS_PATH, state)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight", action="store_true", help="read fixed inputs only; do not calculate signals or performance")
    parser.add_argument("--run-once", action="store_true", help="attempt the one-shot historical batch")
    parser.add_argument("--release-batch-id", default="", help="exact batch ID after total-controller release")
    args = parser.parse_args(argv)
    if args.run_once:
        if not args.release_batch_id:
            parser.error("--run-once requires --release-batch-id")
        run_batch_once(release_batch_id=args.release_batch_id)
        return 0
    if not args.preflight:
        parser.print_help()
        return 0
    _, _, _, preflight = _prepare_inputs()
    _atomic_json_write(PREFLIGHT_PATH, preflight)
    print(json.dumps(preflight, ensure_ascii=False, indent=2, default=_json_default))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
