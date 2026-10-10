"""Offline audit of the saved Gate001 capture without running either backtest."""

from __future__ import annotations

import hashlib
import json
import math
import sys
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.gate001_reference import _signal_fields_from_order_id
from strategy_core.gate001_market_adapter import Gate001MarketDataSource


CAPTURE_PATH = ROOT / "docs/verification/GATE001_FORMAL_TECHNICAL_PRIMARY_REPLAY.json"
SIDECAR_PATH = ROOT / "docs/verification/GATE001_FORMAL_TECHNICAL_PRIMARY_REPLAY_NONFINITE.json"
FORMAL_JSON_PATH = ROOT / "docs/verification/GATE001_FORMAL_RESULT.json"
FORMAL_MD_PATH = ROOT / "docs/verification/GATE001_FORMAL_RESULT.md"
LEDGER_PATH = ROOT / "docs/verification/GATE001_TRIALS.jsonl"
PARSER_PATH = ROOT / "scripts/gate001_reference.py"
MARKET_ADAPTER_PATH = ROOT / "strategy_core/gate001_market_adapter.py"
AUDIT_JSON_PATH = ROOT / "docs/verification/GATE001_SAVED_CAPTURE_AUDIT.json"
AUDIT_MD_PATH = ROOT / "docs/verification/GATE001_SAVED_CAPTURE_AUDIT.md"
CENT = Decimal("0.01")


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON numeric constant: {value}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _assert_finite_tree(value: Any, path: str = "$") -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"non-finite JSON number at {path}")
    if isinstance(value, dict):
        for key, child in value.items():
            _assert_finite_tree(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_finite_tree(child, f"{path}[{index}]")


def _load_strict_json(path: Path) -> Any:
    value = json.loads(
        path.read_text(encoding="utf-8"),
        parse_constant=_reject_constant,
        object_pairs_hook=_unique_object,
    )
    _assert_finite_tree(value)
    return value


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _decimal(value: Any, label: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{label} must be numeric") from None
    if not result.is_finite():
        raise ValueError(f"{label} must be finite")
    return result


def _date(value: Any, label: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be an ISO date string")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{label} must be an ISO date string") from None


def canonical_trade_key(row: dict[str, Any]) -> tuple[date, str, int, Decimal]:
    """Return the scale-insensitive economic identity for a saved trade row."""
    direction = row.get("direction")
    if direction not in {"buy", "sell"}:
        raise ValueError("trade direction must be buy or sell")
    quantity = row.get("quantity")
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
        raise ValueError("trade quantity must be a positive integer")
    price = _decimal(row.get("price"), "trade price")
    if price <= 0:
        raise ValueError("trade price must be positive")
    return (_date(row.get("trade_date"), "trade_date"), direction, quantity, price)


def trade_signal_context(
    trade: dict[str, Any],
    persisted_order: dict[str, Any],
    reference_trade: dict[str, Any],
    captured_signals: list[dict[str, Any]],
) -> dict[str, Any]:
    """Link entry signals or derive an exit context from its persisted order."""
    direction = trade["direction"]
    signal_id = persisted_order.get("signal_id")
    if not isinstance(signal_id, str) or not signal_id:
        raise ValueError("filled order is missing signal_id")
    if persisted_order.get("order_id") != trade.get("order_id"):
        raise ValueError("persisted order does not belong to the trade")
    order_signal_date = _date(persisted_order.get("signal_date"), "order signal_date")
    intended_date = _date(
        persisted_order.get("intended_execution_date"), "order intended_execution_date"
    )
    reference_date = _date(reference_trade.get("signal_date"), "reference signal_date")
    reference_intended = _date(reference_trade.get("intended_date"), "reference intended_date")
    expected_type = "entry" if direction == "buy" else "exit"

    if direction == "buy":
        matches = [signal for signal in captured_signals if signal.get("signal_id") == signal_id]
        if len(matches) != 1:
            raise ValueError(f"entry signal {signal_id} does not have exactly one captured object")
        signal = matches[0]
        signal_date = _date(signal.get("signal_date"), "captured signal_date")
        if (
            signal.get("signal_type") != expected_type
            or signal.get("symbol") != trade.get("symbol")
            or persisted_order.get("symbol") != trade.get("symbol")
            or signal_date != order_signal_date
            or reference_date != order_signal_date
            or intended_date != reference_intended
        ):
            raise ValueError(f"entry signal/order/reference context mismatch for {signal_id}")
        return {
            "context_source": "captured_signal",
            "runtime_signal_captured": True,
            "signal_id": signal_id,
            "signal_date": signal_date.isoformat(),
            "signal_type": expected_type,
            "intended_date": intended_date.isoformat(),
        }

    if direction != "sell":
        raise ValueError(f"unsupported trade direction: {direction}")
    if any(signal.get("signal_type") == "exit" for signal in captured_signals):
        raise ValueError("capture unexpectedly contains exit Signal objects")
    if any(signal.get("signal_id") == signal_id for signal in captured_signals):
        raise ValueError(f"exit signal {signal_id} was captured as a runtime Signal object")
    parsed_signal_date, parsed_type, parsed_intended = _signal_fields_from_order_id(
        persisted_order["order_id"]
    )
    if (
        parsed_type != expected_type
        or parsed_signal_date != order_signal_date
        or parsed_intended != intended_date
        or reference_date != parsed_signal_date
        or reference_trade.get("signal_type") != parsed_type
        or reference_intended != parsed_intended
    ):
        raise ValueError(f"derived exit order/reference context mismatch for {signal_id}")
    return {
        "context_source": "derived_from_persisted_order",
        "runtime_signal_captured": False,
        "signal_id": signal_id,
        "signal_date": parsed_signal_date.isoformat(),
        "signal_type": parsed_type,
        "intended_date": parsed_intended.isoformat(),
    }


def _index_trades(rows: list[dict[str, Any]], label: str) -> dict[tuple[date, str, int, Decimal], dict[str, Any]]:
    result = {}
    for row in rows:
        key = canonical_trade_key(row)
        if key in result:
            raise ValueError(f"{label} has a duplicate canonical trade key: {key}")
        result[key] = row
    return result


def _assert_decimal_equal(left: Any, right: Any, label: str) -> Decimal:
    left_value = _decimal(left, f"{label} left")
    right_value = _decimal(right, f"{label} right")
    if left_value != right_value:
        raise ValueError(f"{label} mismatch: {left_value} != {right_value}")
    return left_value


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _ledger_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    starts = [record for record in records if record.get("phase") == "start"]
    return {
        "new_research": sum(record.get("attempt_class") == "new_research" for record in starts),
        "technical_reruns": sum(record.get("attempt_class") == "technical_rerun" for record in starts),
        "synthetic_validations": sum(
            record.get("attempt_class") == "synthetic_validation" for record in starts
        ),
    }


def _json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _markdown_report(audit: dict[str, Any]) -> bytes:
    trade = audit["trade_reconciliation"]
    signal = audit["signal_association"]
    daily = audit["daily_account_reconciliation"]
    costs = audit["cost_and_cashflow_reconciliation"]
    terminal = audit["terminal_account_reconciliation"]
    sidecar = audit["sidecar_hash_audit"]
    metrics = audit["primary_metrics_reconciliation"]
    lines = [
        "# GATE001 Saved Capture Offline Audit",
        "",
        f"- Audit status: `{audit['status']}`",
        f"- Source capture status retained: `{audit['source_capture_status']}`",
        f"- Formal parent: `{audit['formal_parent_trial_id']}`",
        f"- Technical capture: `{audit['technical_trial_id']}`",
        "- Scope: saved artifacts and frozen local bars only; no engine/reference backtest, API call, holdout, or parameter search.",
        "- This audit does not establish strategy qualification or alpha.",
        "",
        "## Trade and signal linkage",
        "",
        f"- Canonical economic trades: {trade['matched_trade_count']}/7 across engine, reference, and original formal result.",
        f"- Persisted filled orders: {trade['matched_filled_order_count']}/7.",
        f"- Entry Signal objects captured: {signal['captured_entry_signal_count']}/4.",
        f"- Exit contexts derived from persisted orders: {signal['derived_exit_context_count']}/3. Runtime exit Signal objects were not captured.",
        f"- Frozen-bar take-profit evidence: {signal['take_profit_checks_passed']}/3 exit dates met the saved 10% condition.",
        "",
        "## Economics and accounts",
        "",
        f"- Cost fields and cash flows reconciled: {costs['trade_count']}/7 trades.",
        f"- Daily accounts: {daily['normalized_engine_rows']} normalized engine rows match {daily['reference_rows']} reference rows.",
        f"- Duplicate initial anchor preserved as evidence: `{daily['duplicate_anchor_date']}`; the first of two identical engine anchors is removed only for comparison.",
        f"- Primary metrics match the original formal result: `{metrics['match']}`.",
        f"- Terminal NAV: CNY {terminal['terminal_nav_cny']}; cash {terminal['cash_cny']}; market value {terminal['market_value_cny']}; receivable {terminal['receivable_cny']}.",
        "",
        "## Input serialization and preserved capture errors",
        "",
        f"- Sidecar actual disk SHA-256: `{sidecar['actual_disk_sha256']}`.",
        f"- Capture-embedded sidecar SHA-256: `{sidecar['embedded_sha256']}`; it matches the LF-normalized bytes, while the on-disk CRLF bytes have a different hash.",
        f"- Existing capture comparison errors remain recorded unchanged: `{', '.join(audit['preserved_capture_comparison_errors'])}`.",
        "- No capture, sidecar, formal result, or historical ledger line was rewritten.",
        "",
        "## Ledger addendum",
        "",
        f"- Appended record: `{audit['ledger_addendum']['trial_id']}` (`audit_addendum`; not a research run or technical rerun).",
        f"- Counts remain new research {audit['ledger_addendum']['counts_after_append']['new_research']}, technical reruns {audit['ledger_addendum']['counts_after_append']['technical_reruns']}, synthetic validations {audit['ledger_addendum']['counts_after_append']['synthetic_validations']}.",
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def run_offline_audit() -> dict[str, Any]:
    if AUDIT_JSON_PATH.exists() or AUDIT_MD_PATH.exists():
        raise FileExistsError("saved-capture audit outputs already exist; refusing to overwrite")

    capture_bytes = CAPTURE_PATH.read_bytes()
    sidecar_bytes = SIDECAR_PATH.read_bytes()
    formal_json_bytes = FORMAL_JSON_PATH.read_bytes()
    formal_md_bytes = FORMAL_MD_PATH.read_bytes()
    ledger_before = LEDGER_PATH.read_bytes()
    capture = _load_strict_json(CAPTURE_PATH)
    sidecar = _load_strict_json(SIDECAR_PATH)
    formal = _load_strict_json(FORMAL_JSON_PATH)
    ledger_records = [
        json.loads(line.decode("utf-8"), parse_constant=_reject_constant, object_pairs_hook=_unique_object)
        for line in ledger_before.splitlines()
    ]
    if ledger_before and not ledger_before.endswith(b"\n"):
        raise ValueError("trial ledger has an incomplete final line")

    ledger_counts_before = _ledger_counts(ledger_records)
    if ledger_counts_before != {
        "new_research": 1,
        "technical_reruns": 4,
        "synthetic_validations": 3,
    }:
        raise ValueError(f"unexpected historical ledger counts: {ledger_counts_before}")
    capture_sha = _sha256_bytes(capture_bytes)
    sidecar_sha = _sha256_bytes(sidecar_bytes)
    formal_json_sha = _sha256_bytes(formal_json_bytes)
    formal_md_sha = _sha256_bytes(formal_md_bytes)
    technical_trial_id = capture["trial_id"]
    formal_parent_trial_id = capture["parent_trial_id"]
    audit_trial_id = f"gate001-capture-audit-{capture_sha[:16].lower()}"
    if any(record.get("trial_id") == audit_trial_id for record in ledger_records):
        raise ValueError(f"ledger already contains audit addendum {audit_trial_id}")

    technical_end = next(
        (
            record
            for record in reversed(ledger_records)
            if record.get("trial_id") == technical_trial_id and record.get("phase") == "end"
        ),
        None,
    )
    if not technical_end:
        raise ValueError("source technical capture is not present in the existing trial ledger")
    if (
        technical_end.get("capture_sha256") != capture_sha
        or technical_end.get("non_finite_sidecar_sha256") != sidecar_sha
        or technical_end.get("status") != "mismatch_stop"
    ):
        raise ValueError("saved capture or sidecar does not match the recorded technical trial")

    if formal.get("trial", {}).get("trial_id") != formal_parent_trial_id:
        raise ValueError("formal result parent identity does not match the saved capture")
    if capture.get("status") != "mismatch_stop":
        raise ValueError("unexpected source capture status")
    if sidecar.get("trial_id") != technical_trial_id or sidecar.get("parent_trial_id") != formal_parent_trial_id:
        raise ValueError("sidecar trial identity mismatch")
    if sidecar.get("fields") != capture.get("non_finite_audit", {}).get("fields"):
        raise ValueError("sidecar mapping does not match the embedded non-finite audit")

    embedded_sidecar_sha = capture["non_finite_audit"]["sidecar_sha256"].upper()
    lf_sidecar_sha = _sha256_bytes(sidecar_bytes.replace(b"\r\n", b"\n"))
    has_crlf = b"\r\n" in sidecar_bytes
    if not has_crlf or lf_sidecar_sha != embedded_sidecar_sha or sidecar_sha == embedded_sidecar_sha:
        raise ValueError("sidecar byte-hash discrepancy does not match the recorded LF/CRLF serialization difference")

    engine_trades = capture["engine_result"]["trades"]
    reference_trades = capture["reference_result"]["trades"]
    formal_trades = formal["scenario_results"]["primary"]["strategy"]["trades"]
    engine_by_key = _index_trades(engine_trades, "engine")
    reference_by_key = _index_trades(reference_trades, "reference")
    formal_by_key = _index_trades(formal_trades, "original formal result")
    if len(engine_by_key) != 7 or set(engine_by_key) != set(reference_by_key) or set(engine_by_key) != set(formal_by_key):
        raise ValueError("canonical trade tuples do not match one-to-one across the three saved results")

    fill_by_order_id: dict[str, dict[str, Any]] = {}
    for fill_attempt in capture["captured_fill_attempts"]:
        filled_order = fill_attempt["order_after_fill"]
        order_id = filled_order.get("order_id")
        if not isinstance(order_id, str) or order_id in fill_by_order_id:
            raise ValueError("filled-order capture has a missing or duplicate order_id")
        fill_by_order_id[order_id] = filled_order

    captured_signals = capture["captured_signals"]
    entry_count = exit_count = 0
    matched_trades = []
    economic_fields = (
        "gross_amount",
        "commission",
        "stamp_duty",
        "transfer_fee",
        "total_fee",
        "net_cash_flow",
    )
    for key, engine_trade in engine_by_key.items():
        reference_trade = reference_by_key[key]
        formal_trade = formal_by_key[key]
        order_id = engine_trade.get("order_id")
        if not order_id or order_id not in fill_by_order_id:
            raise ValueError(f"trade has no persisted filled order: {key}")
        order = fill_by_order_id[order_id]
        if (
            order.get("status") != "filled"
            or order.get("symbol") != engine_trade.get("symbol")
            or order.get("direction") != engine_trade.get("direction")
            or order.get("actual_execution_date") != engine_trade.get("trade_date")
        ):
            raise ValueError(f"persisted fill identity mismatch for {order_id}")
        if order.get("actual_quantity") != engine_trade.get("quantity"):
            raise ValueError(f"persisted fill quantity mismatch for {order_id}")
        _assert_decimal_equal(order.get("actual_price"), engine_trade.get("price"), f"fill price {order_id}")
        _assert_decimal_equal(engine_trade.get("price"), reference_trade.get("price"), f"price {order_id}")
        _assert_decimal_equal(engine_trade.get("quantity"), reference_trade.get("quantity"), f"quantity {order_id}")
        for field in economic_fields:
            _assert_decimal_equal(engine_trade.get(field), reference_trade.get(field), f"{field} {order_id}")
        _assert_decimal_equal(engine_trade.get("net_cash_flow"), formal_trade.get("net_cash_flow"), f"formal cash flow {order_id}")
        _assert_decimal_equal(engine_trade.get("price"), formal_trade.get("price"), f"formal price {order_id}")
        _assert_decimal_equal(engine_trade.get("quantity"), formal_trade.get("quantity"), f"formal quantity {order_id}")

        price = _decimal(engine_trade["price"], f"{order_id} price")
        quantity = Decimal(engine_trade["quantity"])
        gross = _money(price * quantity)
        fees = sum((_decimal(engine_trade[field], f"{order_id} {field}") for field in ("commission", "stamp_duty", "transfer_fee")), Decimal("0"))
        if any(_decimal(engine_trade[field], f"{order_id} {field}") < 0 for field in ("commission", "stamp_duty", "transfer_fee")):
            raise ValueError(f"negative transaction cost for {order_id}")
        if _money(gross) != _money(_decimal(engine_trade["gross_amount"], f"{order_id} gross_amount")):
            raise ValueError(f"gross amount does not equal price times quantity for {order_id}")
        if _money(fees) != _money(_decimal(engine_trade["total_fee"], f"{order_id} total_fee")):
            raise ValueError(f"total fee does not equal its components for {order_id}")
        expected_cash_flow = -(gross + fees) if engine_trade["direction"] == "buy" else gross - fees
        actual_cash_flow = _decimal(engine_trade["net_cash_flow"], f"{order_id} net_cash_flow")
        if _money(expected_cash_flow) != _money(actual_cash_flow):
            raise ValueError(f"cash flow arithmetic mismatch for {order_id}")
        if "cost" in engine_trade:
            _assert_decimal_equal(engine_trade["cost"], engine_trade["net_cash_flow"], f"engine cost {order_id}")

        context = trade_signal_context(engine_trade, order, reference_trade, captured_signals)
        if context["context_source"] == "captured_signal":
            entry_count += 1
        else:
            exit_count += 1
        matched_trades.append(
            {
                "trade_key": {
                    "trade_date": key[0].isoformat(),
                    "direction": key[1],
                    "quantity": key[2],
                    "price": str(key[3]),
                },
                "order_id": order_id,
                "context": context,
                "gross_amount_cny": str(_money(gross)),
                "total_fee_cny": str(_money(fees)),
                "net_cash_flow_cny": str(_money(actual_cash_flow)),
            }
        )
    if len(fill_by_order_id) != 7 or entry_count != 4 or exit_count != 3:
        raise ValueError("expected exactly seven persisted fills, four captured entries, and three derived exits")

    market_source = Gate001MarketDataSource()
    exit_conditions = capture["strategy_config"]["exit_conditions"]
    rules = exit_conditions.get("rules", [])
    if exit_conditions.get("logic") != "OR" or len(rules) != 1 or rules[0].get("type") != "take_profit_pct":
        raise ValueError("saved exit rule does not match the frozen take-profit rule under audit")
    threshold = _decimal(rules[0].get("threshold"), "take-profit threshold")
    if threshold != Decimal("0.10"):
        raise ValueError("saved take-profit threshold differs from the frozen 10% rule")

    open_buy: dict[str, Any] | None = None
    take_profit_checks = []
    for key in sorted(engine_by_key):
        trade = engine_by_key[key]
        if trade["direction"] == "buy":
            if open_buy is not None:
                raise ValueError("trade sequence opened a new buy before closing the prior position")
            open_buy = trade
        else:
            if open_buy is None or int(open_buy["quantity"]) != int(trade["quantity"]):
                raise ValueError("sell trade does not close the preceding buy quantity")
            ref = reference_by_key[key]
            signal_day = _date(ref["signal_date"], "exit signal_date")
            close = _decimal(market_source.get_daily_bar(trade["symbol"], signal_day).close, "frozen signal-day close")
            buy_fill = _decimal(open_buy["price"], "buy fill price")
            required_close = buy_fill * (Decimal("1") + threshold)
            if close < required_close:
                raise ValueError(f"frozen signal-day close fails saved take-profit condition: {signal_day}")
            take_profit_checks.append(
                {
                    "buy_trade_date": open_buy["trade_date"],
                    "buy_fill_price_cny": str(buy_fill),
                    "exit_signal_date": signal_day.isoformat(),
                    "frozen_close_cny": str(close),
                    "threshold": str(threshold),
                    "required_close_cny": str(required_close),
                    "condition_met": True,
                }
            )
            open_buy = None
    if len(take_profit_checks) != 3 or open_buy is None:
        raise ValueError("expected three completed take-profit cycles followed by one open terminal position")

    engine_daily = capture["all_daily_values"]["engine"]
    reference_daily = capture["all_daily_values"]["independent_reference"]
    if len(engine_daily) != len(reference_daily) + 1 or len(engine_daily) < 2:
        raise ValueError("daily arrays do not have the known one-row duplicate initial anchor")
    daily_fields = ("date", "cash", "market_value", "total_value")

    def normalized_daily(row: dict[str, Any]) -> tuple[Any, ...]:
        return (
            _date(row.get("date"), "daily date"),
            *(_decimal(row.get(field), f"daily {field}") for field in daily_fields[1:]),
        )

    engine_anchor_0 = normalized_daily(engine_daily[0])
    engine_anchor_1 = normalized_daily(engine_daily[1])
    reference_anchor = normalized_daily(reference_daily[0])
    if engine_anchor_0 != engine_anchor_1 or engine_anchor_0 != reference_anchor:
        raise ValueError("the first-day duplicate anchor is not an exact repeated matching account row")
    if [normalized_daily(row)[0] for row in engine_daily] != [reference_anchor[0], *[normalized_daily(row)[0] for row in reference_daily]]:
        raise ValueError("daily sequence has a date mismatch beyond the duplicate first anchor")
    engine_normalized = [normalized_daily(row) for row in engine_daily[1:]]
    reference_normalized = [normalized_daily(row) for row in reference_daily]
    if engine_normalized != reference_normalized:
        raise ValueError("normalized daily EOD accounts differ")
    for row in reference_daily:
        receivable = _decimal(row.get("receivable"), "reference daily receivable")
        if _money(_decimal(row["cash"], "reference cash") + _decimal(row["market_value"], "reference market value") + receivable) != _money(_decimal(row["total_value"], "reference total value")):
            raise ValueError(f"reference account components do not sum to total on {row['date']}")

    capture_metrics = capture["primary_metrics"]
    formal_metrics = formal["metrics"]["primary"]["strategy"]["metrics"]
    if capture_metrics != formal_metrics:
        raise ValueError("captured primary metrics differ from original formal metrics")
    terminal = {
        "cash_cny": _decimal(capture["reference_result"]["terminal_cash"], "reference terminal cash"),
        "market_value_cny": _decimal(capture["reference_result"]["terminal_market_value"], "reference terminal market value"),
        "receivable_cny": _decimal(capture["reference_result"]["terminal_receivable"], "reference terminal receivable"),
        "terminal_nav_cny": _decimal(capture["reference_result"]["terminal_nav"], "reference terminal NAV"),
    }
    if _money(terminal["cash_cny"] + terminal["market_value_cny"] + terminal["receivable_cny"]) != _money(terminal["terminal_nav_cny"]):
        raise ValueError("reference terminal account components do not sum to NAV")
    if _money(terminal["terminal_nav_cny"]) != _money(_decimal(formal_metrics["terminal_nav_cny"], "formal terminal NAV")):
        raise ValueError("terminal NAV differs from the original formal metric")
    engine_terminal = engine_daily[-1]
    reference_terminal = reference_daily[-1]
    for field, terminal_key in (
        ("cash", "cash_cny"),
        ("market_value", "market_value_cny"),
        ("total_value", "terminal_nav_cny"),
    ):
        _assert_decimal_equal(engine_terminal[field], terminal[terminal_key], f"engine terminal {field}")
        _assert_decimal_equal(reference_terminal[field], terminal[terminal_key], f"reference terminal {field}")
    if _money(_decimal(capture["engine_result"]["final_capital"], "engine final capital")) != _money(terminal["terminal_nav_cny"]):
        raise ValueError("engine final capital differs from the reconciled terminal NAV")
    for metric_key, terminal_key in (
        ("terminal_cash_cny", "cash_cny"),
        ("terminal_market_value_cny", "market_value_cny"),
        ("terminal_receivable_cny", "receivable_cny"),
        ("terminal_nav_cny", "terminal_nav_cny"),
    ):
        _assert_decimal_equal(terminal[terminal_key], formal_metrics[metric_key], f"formal terminal {metric_key}")

    manifest = market_source.manifest
    market_raw_hashes = []
    for relative_path, expected_hash in market_source.raw_file_hashes:
        raw_path = ROOT / relative_path
        actual_hash = _sha256_file(raw_path)
        if actual_hash.lower() != expected_hash.lower():
            raise ValueError(f"frozen market raw-file hash mismatch: {relative_path}")
        market_raw_hashes.append({"path": relative_path, "sha256": actual_hash})

    now = datetime.now(timezone.utc).isoformat()
    ledger_counts_after = dict(ledger_counts_before)
    audit = {
        "schema": "gate001-saved-capture-offline-audit.v1",
        "status": "supplemental_offline_audit_complete",
        "created_at_utc": now,
        "mainline_step": 4,
        "mainline_step_name": "executable Action Plan",
        "source_capture_status": capture["status"],
        "formal_parent_trial_id": formal_parent_trial_id,
        "technical_trial_id": technical_trial_id,
        "scope": {
            "offline_only": True,
            "engine_or_reference_backtest_run": False,
            "api_calls": False,
            "holdout_access": False,
            "parameter_search": False,
            "alpha_or_qualification_claim": False,
            "source_capture_comparison_errors_preserved": True,
        },
        "input_artifacts": {
            "capture": {"path": str(CAPTURE_PATH.relative_to(ROOT)), "sha256": capture_sha},
            "sidecar": {"path": str(SIDECAR_PATH.relative_to(ROOT)), "sha256": sidecar_sha},
            "original_formal_json": {"path": str(FORMAL_JSON_PATH.relative_to(ROOT)), "sha256": formal_json_sha},
            "original_formal_markdown": {"path": str(FORMAL_MD_PATH.relative_to(ROOT)), "sha256": formal_md_sha},
            "existing_order_id_parser": {"path": str(PARSER_PATH.relative_to(ROOT)), "sha256": _sha256_file(PARSER_PATH)},
            "frozen_market_source": {
                "path": str(MARKET_ADAPTER_PATH.relative_to(ROOT)),
                "sha256": _sha256_file(MARKET_ADAPTER_PATH),
                "snapshot_id": manifest["snapshot_id"],
                "manifest_sha256": market_source.manifest_sha256.upper(),
                "raw_file_hashes": market_raw_hashes,
            },
        },
        "trade_reconciliation": {
            "canonical_key_fields": ["trade_date", "direction", "quantity", "Decimal(price)"],
            "matched_trade_count": len(matched_trades),
            "matched_filled_order_count": len(fill_by_order_id),
            "engine_reference_formal_tuples_match": True,
            "trade_details": matched_trades,
        },
        "cost_and_cashflow_reconciliation": {
            "trade_count": len(matched_trades),
            "gross_cost_fee_and_cashflow_checks_passed": True,
            "fields_compared_engine_reference": list(economic_fields),
            "price_times_quantity_and_fee_component_arithmetic_checked": True,
        },
        "signal_association": {
            "captured_entry_signal_count": entry_count,
            "derived_exit_context_count": exit_count,
            "runtime_exit_signal_objects_captured": False,
            "exit_context_source": "persisted filled order plus existing _signal_fields_from_order_id parser, cross-checked against saved reference context",
            "take_profit_threshold": str(threshold),
            "take_profit_checks_passed": len(take_profit_checks),
            "take_profit_evidence": take_profit_checks,
        },
        "daily_account_reconciliation": {
            "engine_raw_rows": len(engine_daily),
            "reference_rows": len(reference_daily),
            "normalized_engine_rows": len(engine_normalized),
            "normalized_eod_accounts_match": True,
            "date_sequence_match_after_preserving_anchor_evidence": True,
            "duplicate_anchor_date": engine_anchor_0[0].isoformat(),
            "duplicate_anchor_engine_rows": 2,
            "dropped_from_comparison_only": "the first duplicate engine anchor row; both original rows remain untouched",
            "reference_receivable_included_in_account_sum_check": True,
        },
        "primary_metrics_reconciliation": {
            "match": True,
            "captured_metrics_match_original_formal_metrics": True,
            "metric_count": len(capture_metrics),
        },
        "terminal_account_reconciliation": {
            **{key: str(_money(value)) for key, value in terminal.items()},
            "engine_reference_formal_values_match": True,
        },
        "sidecar_hash_audit": {
            "actual_disk_sha256": sidecar_sha,
            "embedded_sha256": embedded_sidecar_sha,
            "lf_normalized_sha256": lf_sidecar_sha,
            "disk_line_endings_contain_crlf": has_crlf,
            "embedded_sha_matches_lf_normalized_bytes": True,
            "difference_explanation": "The capture embeds the SHA-256 of the LF-serialized sidecar text; the saved sidecar has CRLF line endings, so its actual byte hash differs.",
            "original_capture_sidecar_and_formal_files_modified": False,
        },
        "preserved_capture_comparison_errors": list(capture["comparison_errors"]),
        "ledger_addendum": {
            "trial_id": audit_trial_id,
            "phase": "audit_addendum",
            "attempt_class": "offline_technical_audit_addendum",
            "counts_as_new_research": False,
            "counts_as_technical_rerun": False,
            "counts_before_append": ledger_counts_before,
            "counts_after_append": ledger_counts_after,
            "ledger_before_sha256": _sha256_bytes(ledger_before),
        },
    }
    json_bytes = _json_bytes(audit)
    md_bytes = _markdown_report(audit)
    AUDIT_JSON_PATH.write_bytes(json_bytes)
    AUDIT_MD_PATH.write_bytes(md_bytes)
    json_sha = _sha256_bytes(json_bytes)
    md_sha = _sha256_bytes(md_bytes)
    addendum = {
        "trial_id": audit_trial_id,
        "parent_trial_id": formal_parent_trial_id,
        "technical_trial_id": technical_trial_id,
        "phase": "audit_addendum",
        "attempt_class": "offline_technical_audit_addendum",
        "recorded_at_utc": now,
        "status": "supplemental_offline_audit_complete",
        "counts_as_new_research": False,
        "counts_as_technical_rerun": False,
        "new_research_count": ledger_counts_before["new_research"],
        "technical_rerun_count": ledger_counts_before["technical_reruns"],
        "synthetic_validation_count": ledger_counts_before["synthetic_validations"],
        "source_capture_status": capture["status"],
        "source_capture_sha256": capture_sha,
        "source_sidecar_sha256_actual_bytes": sidecar_sha,
        "source_formal_json_sha256": formal_json_sha,
        "audit_outputs": {
            str(AUDIT_JSON_PATH.relative_to(ROOT)): json_sha,
            str(AUDIT_MD_PATH.relative_to(ROOT)): md_sha,
        },
    }
    with LEDGER_PATH.open("ab") as handle:
        handle.write((json.dumps(addendum, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8"))
        handle.flush()

    ledger_after = LEDGER_PATH.read_bytes()
    if not ledger_after.startswith(ledger_before):
        raise ValueError("historical ledger bytes changed while appending the addendum")
    appended_lines = ledger_after[len(ledger_before):].splitlines()
    if len(appended_lines) != 1 or json.loads(appended_lines[0].decode("utf-8")) != addendum:
        raise ValueError("expected exactly one valid audit addendum ledger record")
    counts_after = _ledger_counts(
        [
            json.loads(line.decode("utf-8"), parse_constant=_reject_constant, object_pairs_hook=_unique_object)
            for line in ledger_after.splitlines()
        ]
    )
    if counts_after != ledger_counts_before:
        raise ValueError("audit addendum changed historical research or rerun counts")
    return {
        "audit": audit,
        "audit_json_sha256": json_sha,
        "audit_markdown_sha256": md_sha,
        "ledger_addendum": addendum,
        "ledger_counts_after": counts_after,
    }


if __name__ == "__main__":
    result = run_offline_audit()
    print(json.dumps({
        "status": result["audit"]["status"],
        "audit_json": str(AUDIT_JSON_PATH),
        "audit_json_sha256": result["audit_json_sha256"],
        "audit_markdown": str(AUDIT_MD_PATH),
        "audit_markdown_sha256": result["audit_markdown_sha256"],
        "ledger_addendum_id": result["ledger_addendum"]["trial_id"],
        "ledger_counts": result["ledger_counts_after"],
    }, ensure_ascii=False, allow_nan=False))
