"""Generate the Gate001 dividend-corrected final-report draft from frozen evidence."""

from __future__ import annotations

import hashlib
import json
import math
import sys
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from strategy_core.dividend_ledger import DividendLedger
from strategy_core.gate001_dividend_adapter import MANIFEST_PATH, load_gate001_dividend_snapshot


CAPTURE_PATH = ROOT / "docs/verification/GATE001_FORMAL_TECHNICAL_PRIMARY_REPLAY.json"
SIDECAR_PATH = ROOT / "docs/verification/GATE001_FORMAL_TECHNICAL_PRIMARY_REPLAY_NONFINITE.json"
FORMAL_JSON_PATH = ROOT / "docs/verification/GATE001_FORMAL_RESULT.json"
FORMAL_MD_PATH = ROOT / "docs/verification/GATE001_FORMAL_RESULT.md"
CAPTURE_AUDIT_PATH = ROOT / "docs/verification/GATE001_SAVED_CAPTURE_AUDIT.json"
CAPTURE_AUDIT_MD_PATH = ROOT / "docs/verification/GATE001_SAVED_CAPTURE_AUDIT.md"
PROTOCOL_PATH = ROOT / "data/alpha_gate_001/GATE001_PROTOCOL_V1_20261005_a94b1e3f6d6a46af87894e0269777a32.json"
TRIALS_PATH = ROOT / "docs/verification/GATE001_TRIALS.jsonl"
DIVIDEND_ADAPTER_PATH = ROOT / "strategy_core/gate001_dividend_adapter.py"
DIVIDEND_LEDGER_PATH = ROOT / "strategy_core/dividend_ledger.py"
OUT_MD = ROOT / "docs/verification/GATE001_FINAL_RESEARCH_REPORT.md"
OUT_JSON = ROOT / "docs/verification/GATE001_DIVIDEND_DISPLAY_AUDIT.json"
CENT = Decimal("0.01")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def _file_sha(path: Path) -> str:
    return _sha(path.read_bytes())


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant: {value}")


def _finite(value: Any, path: str = "$") -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"non-finite JSON number at {path}")
    if isinstance(value, dict):
        for key, item in value.items():
            _finite(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _finite(item, f"{path}[{index}]")


def _load(path: Path) -> Any:
    value = json.loads(
        path.read_text(encoding="utf-8"),
        parse_constant=_reject_constant,
        object_pairs_hook=_unique_object,
    )
    _finite(value)
    return value


def _dec(value: Any, label: str) -> Decimal:
    try:
        number = Decimal(str(value))
    except Exception as exc:
        raise ValueError(f"{label} is not numeric") from exc
    if not number.is_finite():
        raise ValueError(f"{label} is not finite")
    return number


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _iso(value: date | str) -> str:
    return value.isoformat() if isinstance(value, date) else str(value)


def _fmt(value: Decimal | str | int) -> str:
    return f"{_dec(value, 'report amount'):,.2f}"


def _price(value: Decimal | str | int) -> str:
    return f"{_dec(value, 'trade price'):.3f}"


def _trade_key(row: dict[str, Any]) -> tuple[date, str, int, Decimal]:
    return (
        date.fromisoformat(row["trade_date"]),
        row["direction"],
        int(row["quantity"]),
        _dec(row["price"], "trade price"),
    )


def _trial_counts(path: Path) -> dict[str, int]:
    records = [
        json.loads(line, parse_constant=_reject_constant, object_pairs_hook=_unique_object)
        for line in path.read_text(encoding="utf-8").splitlines()
    ]
    starts = [record for record in records if record.get("phase") == "start"]
    return {
        "new_research": sum(row.get("attempt_class") == "new_research" for row in starts),
        "technical_reruns": sum(row.get("attempt_class") == "technical_rerun" for row in starts),
        "synthetic_validations": sum(row.get("attempt_class") == "synthetic_validation" for row in starts),
    }


def build_report() -> tuple[dict[str, Any], str]:
    capture = _load(CAPTURE_PATH)
    formal = _load(FORMAL_JSON_PATH)
    capture_audit = _load(CAPTURE_AUDIT_PATH)
    protocol = _load(PROTOCOL_PATH)
    snapshot = load_gate001_dividend_snapshot()
    dividend_ledger = DividendLedger(snapshot.events)
    normalized = {event.ann_date: event for event in dividend_ledger.events}
    if len(normalized) != len(dividend_ledger.events):
        raise ValueError("normalized dividend events are not unique")

    if capture["status"] != "mismatch_stop" or formal["deterministic_verdict"] != "insufficient_evidence":
        raise ValueError("frozen source status or research verdict changed")
    if formal.get("trial", {}).get("trial_id") != capture["parent_trial_id"]:
        raise ValueError("formal trial and capture parent do not match")
    if capture_audit["input_artifacts"]["capture"]["sha256"] != _file_sha(CAPTURE_PATH):
        raise ValueError("saved-capture audit is not bound to the current capture")
    if capture_audit["input_artifacts"]["original_formal_json"]["sha256"] != _file_sha(FORMAL_JSON_PATH):
        raise ValueError("saved-capture audit is not bound to the original formal result")
    if snapshot.manifest_sha256.upper() != capture["input_source_hashes"]["dividend_manifest_sha256"]:
        raise ValueError("frozen dividend manifest differs from the formal capture")
    capture_raw_hashes = {
        item["path"]: item["sha256"].upper()
        for item in capture["input_source_hashes"]["dividend_raw_file_hashes"]
    }
    snapshot_raw_hashes = {path: digest.upper() for path, digest in snapshot.raw_file_hashes}
    if capture_raw_hashes != snapshot_raw_hashes:
        raise ValueError("frozen dividend raw-file hashes differ from the formal capture")
    if (
        snapshot.target_raw_rows != 20
        or snapshot.duplicate_rows != 7
        or len(snapshot.events) != 20
        or len(dividend_ledger.events) != 13
        or sum(len(event.source_refs) for event in dividend_ledger.events) != 20
    ):
        raise ValueError("frozen dividend normalization is not 20 raw rows to 13 events with 7 duplicates")
    if capture["raw_dividend_event_rows"] != snapshot.target_raw_rows or capture["normalized_dividend_event_count"] != len(normalized):
        raise ValueError("formal capture dividend counts differ from the pinned source normalization")
    if _file_sha(DIVIDEND_ADAPTER_PATH) != capture["input_source_hashes"]["code_sha256"]["dividend_adapter"]:
        raise ValueError("frozen dividend adapter code hash differs from the capture")
    if _file_sha(ROOT / "scripts/gate001_reference.py") != capture["input_source_hashes"]["code_sha256"]["reference"]:
        raise ValueError("frozen reference implementation hash differs from the capture")

    start = date.fromisoformat(capture["market_window"]["evaluation_start"])
    end = date.fromisoformat(capture["market_window"]["evaluation_end"])
    cycles = capture["cycle_dividend_audit"]
    if len(cycles) != 4:
        raise ValueError("expected three closed cycles and one terminal open cycle")
    cycle_by_id = {row["cycle_id"]: row for row in cycles}
    if len(cycle_by_id) != 4:
        raise ValueError("cycle ids are not unique")
    cycle_event_keys: set[date] = set()
    cycle_summaries: list[dict[str, Any]] = []
    event_assignments: dict[date, tuple[dict[str, Any], dict[str, Any]]] = {}

    for cycle in cycles:
        events = cycle["dividend_events"]
        event_total = Decimal("0.00")
        for saved_event in events:
            ann = date.fromisoformat(saved_event["ann_date"])
            if ann in cycle_event_keys or ann not in normalized:
                raise ValueError(f"duplicate or unknown dividend event in cycle audit: {ann}")
            cycle_event_keys.add(ann)
            event = normalized[ann]
            expected_fields = {
                "record_date": event.record_date.isoformat(),
                "ex_date": event.ex_date.isoformat(),
                "pay_date": event.pay_date.isoformat(),
                "div_cash_per_unit_cny": format(event.div_cash, "f"),
            }
            if any(saved_event[field] != value for field, value in expected_fields.items()):
                raise ValueError(f"capture and normalized dividend event differ: {ann}")
            if tuple(saved_event["source_refs"]) != event.source_refs:
                raise ValueError(f"captured event raw-row provenance differs: {ann}")
            if saved_event["raw_row_count"] != len(event.source_refs) or saved_event["duplicate_raw_rows"] != len(event.source_refs) - 1:
                raise ValueError(f"captured duplicate-row count differs: {ann}")
            quantity = int(saved_event["quantity_at_record"])
            if quantity != int(cycle["buy_quantity"]):
                raise ValueError(f"captured dividend quantity differs from cycle holding: {ann}")
            amount = _money(event.div_cash * quantity)
            if amount != _dec(saved_event["dividend_cny"], f"captured dividend {ann}"):
                raise ValueError(f"captured dividend amount differs from frozen unit amount: {ann}")
            event_total += amount
            event_assignments[ann] = (cycle, saved_event)
        if event_total != _dec(cycle["dividend_total_cny"], f"cycle dividend total {cycle['cycle_id']}"):
            raise ValueError(f"cycle dividend total differs from its unique event rows: {cycle['cycle_id']}")

    normalized_events: list[dict[str, Any]] = []
    paid_total = receivable_total = pending_right_total = Decimal("0.00")
    for ann, event in normalized.items():
        active = []
        for cycle in cycles:
            buy_date = date.fromisoformat(cycle["buy_date"])
            sell_date = date.fromisoformat(cycle["sell_date"]) if cycle["sell_date"] else None
            if buy_date <= event.record_date <= end and (sell_date is None or event.record_date < sell_date):
                active.append(cycle)
        if len(active) > 1:
            raise ValueError(f"more than one holding cycle owns dividend record date {ann}")
        cycle = active[0] if active else None
        saved_pair = event_assignments.get(ann)
        if (cycle is None) != (saved_pair is None):
            raise ValueError(f"cycle dividend audit omits or adds ownership for {ann}")
        if cycle is not None and saved_pair[0]["cycle_id"] != cycle["cycle_id"]:
            raise ValueError(f"dividend is attributed to the wrong cycle: {ann}")

        quantity = int(cycle["buy_quantity"]) if cycle else 0
        entitlement = _money(event.div_cash * quantity)
        if not cycle:
            state = "no_position_at_record_date"
        elif event.pay_date <= end:
            state = "paid_to_simulated_cash_by_cutoff"
            paid_total += entitlement
        elif event.ex_date <= end:
            state = "confirmed_receivable_at_cutoff"
            receivable_total += entitlement
        elif event.record_date <= end:
            state = "confirmed_right_pending_ex_date"
            pending_right_total += entitlement
        else:
            state = "after_cutoff_not_counted"
        normalized_events.append({
            "ann_date": ann.isoformat(),
            "record_date": event.record_date.isoformat(),
            "ex_date": event.ex_date.isoformat(),
            "pay_date": event.pay_date.isoformat(),
            "div_cash_cny_per_unit": format(event.div_cash, "f"),
            "source_ref_count": len(event.source_refs),
            "duplicate_raw_rows": len(event.source_refs) - 1,
            "source_refs": list(event.source_refs),
            "ownership": "eligible" if cycle else "not_eligible",
            "cycle_id": cycle["cycle_id"] if cycle else None,
            "quantity_at_record": quantity,
            "entitlement_cny": str(entitlement),
            "settlement_state": state,
        })

    if len(event_assignments) != 9 or len(cycle_event_keys) != 9:
        raise ValueError("expected nine unique held-position dividend events across four cycles")
    if _money(paid_total + receivable_total + pending_right_total) != _dec(capture["reference_result"]["dividend_entitlement"], "reference dividend entitlement"):
        raise ValueError("modeled dividend states do not reconcile to the reference dividend entitlement")
    if _money(receivable_total) != _dec(capture["reference_result"]["terminal_receivable"], "reference terminal receivable"):
        raise ValueError("confirmed dividend receivables differ from the reference account")
    if _money(pending_right_total) != _dec(capture["reference_result"]["pending_dividend_entitlement"], "reference pending dividend entitlement"):
        raise ValueError("pending confirmed dividend rights differ from the reference result")

    completed_pnls = capture["reference_result"]["completed_trade_profits"]
    closed_count = 0
    open_count = 0
    for index, cycle in enumerate(cycles):
        buy_net = _dec(cycle["buy_cash_flow_cny"], "cycle buy net cash flow")
        dividend_total = _dec(cycle["dividend_total_cny"], "cycle dividend total")
        if cycle["sell_date"] is not None:
            closed_count += 1
            sell_net = _dec(cycle["sell_cash_flow_cny"], "cycle sell net cash flow")
            calculated = _money(buy_net + sell_net + dividend_total)
            reference_pnl = _dec(completed_pnls[index], "reference completed-cycle P&L")
            if calculated != _dec(cycle["cycle_economic_pnl_cny"], "captured closed-cycle P&L") or calculated != reference_pnl:
                raise ValueError(f"closed-cycle economics differ: {cycle['cycle_id']}")
            base_leg = {"buy_net_cash_flow_cny": str(_money(buy_net)), "sell_net_cash_flow_cny": str(_money(sell_net))}
            formula = f"{_money(buy_net)} + {_money(sell_net)} + {_money(dividend_total)} = {calculated}"
            terminal_market_value = None
        else:
            open_count += 1
            sell_net = Decimal("0.00")
            terminal_market_value = _dec(capture["reference_result"]["terminal_market_value"], "reference terminal market value")
            calculated = _money(buy_net + terminal_market_value + dividend_total)
            reference_pnl = _dec(capture["reference_result"]["open_trade_profit"], "reference open-cycle P&L")
            if calculated != reference_pnl:
                raise ValueError("open-cycle economics differ from the reference")
            base_leg = {"buy_net_cash_flow_cny": str(_money(buy_net)), "sell_net_cash_flow_cny": None}
            formula = f"{_money(buy_net)} + {_money(terminal_market_value)} + {_money(dividend_total)} = {calculated}"
        owned_events = [event for event in normalized_events if event["cycle_id"] == cycle["cycle_id"]]
        cycle_summaries.append({
            "cycle_id": cycle["cycle_id"],
            "buy_date": cycle["buy_date"],
            "sell_date": cycle["sell_date"],
            "quantity": int(cycle["buy_quantity"]),
            **base_leg,
            "terminal_market_value_cny": str(_money(terminal_market_value)) if terminal_market_value is not None else None,
            "eligible_dividends_cny": str(_money(dividend_total)),
            "dividend_event_count": len(owned_events),
            "dividends_paid_to_simulated_cash_cny": str(sum((_dec(event["entitlement_cny"], "event entitlement") for event in owned_events if event["settlement_state"] == "paid_to_simulated_cash_by_cutoff"), Decimal("0.00"))),
            "confirmed_receivable_at_cutoff_cny": str(sum((_dec(event["entitlement_cny"], "event entitlement") for event in owned_events if event["settlement_state"] == "confirmed_receivable_at_cutoff"), Decimal("0.00"))),
            "confirmed_right_pending_ex_date_cny": str(sum((_dec(event["entitlement_cny"], "event entitlement") for event in owned_events if event["settlement_state"] == "confirmed_right_pending_ex_date"), Decimal("0.00"))),
            "reference_pnl_cny": str(_money(reference_pnl)),
            "equation": formula,
            "equation_verified": True,
        })
    if (closed_count, open_count) != (3, 1):
        raise ValueError("expected three closed cycles and one open terminal cycle")

    trades = capture["engine_result"]["trades"]
    reference_trades = capture["reference_result"]["trades"]
    formal_trades = formal["scenario_results"]["primary"]["strategy"]["trades"]
    saved_trade_details = capture_audit["trade_reconciliation"]["trade_details"]
    if any(len(rows) != 7 for rows in (trades, reference_trades, formal_trades, saved_trade_details)):
        raise ValueError("saved trade evidence does not contain seven rows in every representation")
    formal_by_key = {_trade_key(row): row for row in formal_trades}
    reference_by_order = {row["order_id"]: row for row in reference_trades}
    audit_by_order = {row["order_id"]: row for row in saved_trade_details}
    fill_by_order = {row["order_after_fill"]["order_id"]: row["order_after_fill"] for row in capture["captured_fill_attempts"]}
    if len(formal_by_key) != 7 or len(reference_by_order) != 7 or len(audit_by_order) != 7 or len(fill_by_order) != 7:
        raise ValueError("saved trade/order identifiers are not one-to-one")
    if set(reference_by_order) != set(audit_by_order) or set(fill_by_order) != set(reference_by_order):
        raise ValueError("saved trade rows do not match the persisted fill-order ids")

    trade_rows: list[dict[str, Any]] = []
    for trade in trades:
        key = _trade_key(trade)
        order_id = trade["order_id"]
        if key not in formal_by_key or order_id not in reference_by_order:
            raise ValueError(f"trade is absent from reference or formal result: {order_id}")
        order = fill_by_order[order_id]
        reference = reference_by_order[order_id]
        formal_trade = formal_by_key[key]
        audit_row = audit_by_order[order_id]
        context = audit_row["context"]
        if order["status"] != "filled" or order["actual_execution_date"] != trade["trade_date"] or int(order["actual_quantity"]) != int(trade["quantity"]):
            raise ValueError(f"persisted fill does not match economic trade: {order_id}")
        if _dec(order["actual_price"], "persisted fill price") != _dec(trade["price"], "trade price"):
            raise ValueError(f"persisted fill price differs: {order_id}")
        for peer in (reference, formal_trade):
            if _trade_key(peer) != key or _dec(peer["net_cash_flow"], "net cash flow") != _dec(trade["net_cash_flow"], "net cash flow"):
                raise ValueError(f"saved economic trade differs across result: {order_id}")
        if context["signal_id"] != order["signal_id"]:
            raise ValueError(f"trade signal context differs from persisted order: {order_id}")
        if _money(_dec(trade["price"], "trade price") * int(trade["quantity"])) != _money(_dec(trade["gross_amount"], "gross amount")):
            raise ValueError(f"trade gross amount arithmetic differs: {order_id}")
        commission = _dec(trade["commission"], "commission")
        stamp_duty = _dec(trade["stamp_duty"], "stamp duty")
        transfer_fee = _dec(trade["transfer_fee"], "transfer fee")
        fees = _money(commission + stamp_duty + transfer_fee)
        if fees != _money(_dec(trade["total_fee"], "total fees")):
            raise ValueError(f"trade fee components differ: {order_id}")
        expected_net = -(_dec(trade["gross_amount"], "gross amount") + fees) if trade["direction"] == "buy" else _dec(trade["gross_amount"], "gross amount") - fees
        if _money(expected_net) != _money(_dec(trade["net_cash_flow"], "net cash flow")):
            raise ValueError(f"trade net cash flow differs from gross less fees: {order_id}")
        trade_rows.append({
            "trade_date": trade["trade_date"],
            "direction": trade["direction"],
            "signal_date": context["signal_date"],
            "intended_date": context["intended_date"],
            "signal_source": context["context_source"],
            "runtime_signal_captured": bool(context["runtime_signal_captured"]),
            "signal_id": context["signal_id"],
            "order_id": order_id,
            "quantity": int(trade["quantity"]),
            "fill_price_cny": str(_dec(trade["price"], "trade price")),
            "gross_amount_cny": str(_money(_dec(trade["gross_amount"], "gross amount"))),
            "commission_cny": str(_money(commission)),
            "stamp_duty_cny": str(_money(stamp_duty)),
            "transfer_fee_cny": str(_money(transfer_fee)),
            "total_fee_cny": str(fees),
            "net_cash_flow_cny": str(_money(_dec(trade["net_cash_flow"], "net cash flow"))),
        })
    if sum(row["signal_source"] == "captured_signal" for row in trade_rows) != 4 or sum(row["signal_source"] == "derived_from_persisted_order" for row in trade_rows) != 3:
        raise ValueError("expected four captured entry signals and three derived exit contexts")
    if any(signal.get("signal_type") == "exit" for signal in capture["captured_signals"]):
        raise ValueError("the capture unexpectedly contains runtime exit Signal objects")

    metrics = formal["metrics"]["primary"]["strategy"]["metrics"]
    if capture["primary_metrics"] != metrics or not capture_audit["primary_metrics_reconciliation"]["match"]:
        raise ValueError("primary metrics are not identical to the original formal result")
    minimum = protocol["gate"]["minimum_evidence"]
    entry_years = metrics["independent_entry_calendar_years"]
    terminal = capture["reference_result"]
    terminal_cash = _dec(terminal["terminal_cash"], "terminal cash")
    terminal_market_value = _dec(terminal["terminal_market_value"], "terminal market value")
    terminal_receivable = _dec(terminal["terminal_receivable"], "terminal receivable")
    terminal_nav = _dec(terminal["terminal_nav"], "terminal NAV")
    if _money(terminal_cash + terminal_market_value + terminal_receivable) != _money(terminal_nav):
        raise ValueError("terminal account components do not sum to the terminal NAV")
    closed_pnl = sum((_dec(row["reference_pnl_cny"], "closed-cycle P&L") for row in cycle_summaries if row["sell_date"]), Decimal("0.00"))
    open_pnl = sum((_dec(row["reference_pnl_cny"], "open-cycle P&L") for row in cycle_summaries if row["sell_date"] is None), Decimal("0.00"))
    initial_capital = _dec(capture["engine_result"]["initial_capital"], "initial capital")
    interest = _dec(metrics["cash_interest_income_cny"], "cash interest")
    if _money(initial_capital + closed_pnl + open_pnl + interest) != _money(terminal_nav):
        raise ValueError("initial capital plus cycle economics does not reconcile to terminal NAV")

    counts = _trial_counts(TRIALS_PATH)
    if counts != {"new_research": 1, "technical_reruns": 4, "synthetic_validations": 3}:
        raise ValueError(f"historical research counts changed: {counts}")
    capture_hash = _file_sha(CAPTURE_PATH)
    sidecar_hash = _file_sha(SIDECAR_PATH)
    formal_hash = _file_sha(FORMAL_JSON_PATH)
    ledger_hash = _file_sha(TRIALS_PATH)
    source_hashes = {
        "capture_sha256": capture_hash,
        "sidecar_sha256_actual_bytes": sidecar_hash,
        "formal_json_sha256": formal_hash,
        "formal_markdown_sha256": _file_sha(FORMAL_MD_PATH),
        "saved_capture_audit_json_sha256": _file_sha(CAPTURE_AUDIT_PATH),
        "saved_capture_audit_markdown_sha256": _file_sha(CAPTURE_AUDIT_MD_PATH),
        "protocol_sha256": _file_sha(PROTOCOL_PATH),
        "dividend_manifest_sha256": _file_sha(MANIFEST_PATH),
        "dividend_adapter_sha256": _file_sha(DIVIDEND_ADAPTER_PATH),
        "dividend_ledger_sha256": _file_sha(DIVIDEND_LEDGER_PATH),
        "trial_ledger_before_report_correction_sha256": ledger_hash,
        "dividend_raw_files": [{"path": path, "sha256": digest.upper()} for path, digest in snapshot.raw_file_hashes],
    }
    report_date = date.today().isoformat()
    exposure_disclosure = (
        "此前的独立验收者在研究规则冻结后阅览过 2021–2025 年分红金额及 NAV 增长的搜索结果片段；"
        "未打开 PDF、未调用 API、未下载文件。本次任务没有再次查询这些内容，也不把这些片段作为本报告的数字来源。"
        "因此不能声称所有审阅者均未见过该后续时期信息；任何后续时期的独立 Holdout 主张均需单独说明这次暴露。"
    )
    audit = {
        "schema": "gate001-dividend-display-audit.v1",
        "report_status": "draft_pending_independent_review",
        "report_date": report_date,
        "formal_parent_trial_id": capture["parent_trial_id"],
        "technical_capture_trial_id": capture["trial_id"],
        "source_capture_status_preserved": capture["status"],
        "source_capture_comparison_errors_preserved": list(capture["comparison_errors"]),
        "research_verdict": formal["deterministic_verdict"],
        "research_window": {"start": start.isoformat(), "end": end.isoformat()},
        "claim_boundary": {
            "current_market_assessment": False,
            "actual_investment_return": False,
            "qualified_strategy": False,
            "alpha_claim": False,
            "engine_or_reference_backtest_rerun": False,
            "api_calls_or_downloads": False,
            "holdout_queries_in_this_task": False,
        },
        "source_hashes": source_hashes,
        "dividend_normalization": {
            "snapshot_id": snapshot.snapshot_id,
            "ann_date_window": [snapshot.ann_date_window[0].isoformat(), snapshot.ann_date_window[1].isoformat()],
            "raw_target_rows": snapshot.target_raw_rows,
            "normalized_events": len(dividend_ledger.events),
            "duplicate_raw_rows_removed": snapshot.duplicate_rows,
            "source_reference_count_after_normalization": sum(len(event.source_refs) for event in dividend_ledger.events),
            "div_cash_unit": "CNY per fund unit",
            "official_spotcheck_dates": [day.isoformat() for day in snapshot.official_spotcheck_dates],
            "evidence_gap": snapshot.evidence_gap,
            "event_rows": normalized_events,
        },
        "cycle_reconciliation": {
            "closed_cycles": closed_count,
            "closed_cycle_minimum": int(minimum["independent_completed_round_trips"]),
            "terminal_open_cycles": open_count,
            "cycle_rows": cycle_summaries,
            "eligible_dividend_total_cny": str(_money(paid_total + receivable_total + pending_right_total)),
            "paid_to_simulated_cash_by_cutoff_cny": str(_money(paid_total)),
            "confirmed_receivable_at_cutoff_cny": str(_money(receivable_total)),
            "confirmed_right_pending_ex_date_cny": str(_money(pending_right_total)),
            "outside_frozen_source_window_future_rights": "not quantified or included",
        },
        "trade_legs": {
            "count": len(trade_rows),
            "dividends_in_trade_rows": False,
            "runtime_exit_signal_objects_captured": False,
            "rows": trade_rows,
        },
        "terminal_account": {
            "initial_capital_cny": str(_money(initial_capital)),
            "terminal_cash_cny": str(_money(terminal_cash)),
            "terminal_market_value_cny": str(_money(terminal_market_value)),
            "terminal_receivable_cny": str(_money(terminal_receivable)),
            "terminal_nav_cny": str(_money(terminal_nav)),
        "reference_open_cycle_pnl_cny": str(_money(open_pnl)),
        "closed_cycle_pnl_total_cny": str(_money(closed_pnl)),
        "cash_interest_income_cny": str(_money(interest)),
            "account_components_reconcile": True,
            "initial_capital_plus_cycles_reconciles": True,
        },
        "formal_metrics": {
            "completed_round_trips": int(metrics["completed_round_trips"]),
            "minimum_completed_round_trips": int(minimum["independent_completed_round_trips"]),
            "distinct_entry_years": entry_years,
            "entry_year_count": len(entry_years),
            "minimum_entry_years": int(minimum["distinct_entry_calendar_years"]),
            "cagr_act_365": metrics["cagr_act_365"],
            "mdd_loss_fraction": metrics["mdd_loss_fraction"],
            "calmar": metrics["calmar"],
            "sharpe": metrics["sharpe"],
        },
        "limitations_and_disclosures": {
            "execution_proxy": "T+1 next-open execution with daily-bar inputs, configured slippage and rule-based limit/suspension handling; this is not observed queue-level execution.",
            "dividend_source_status": "raw_unverified; the frozen source adapter reports only the two stated official spot-check dates and does not establish full-history completeness.",
            "holdout_exposure": exposure_disclosure,
            "performance_interpretation": "All performance figures describe only the frozen 2010–2020 historical research window and the saved simulated account; they are not current market conditions or actual investment returns.",
            "review_status": "pending independent review; the original formal JSON/Markdown, capture, sidecar, prior audit files, and historical trial rows remain unchanged.",
        },
        "trial_counts_at_generation": counts,
    }
    markdown = _render_markdown(audit)
    return audit, markdown


def _render_markdown(audit: dict[str, Any]) -> str:
    div = audit["dividend_normalization"]
    cycle_data = audit["cycle_reconciliation"]
    terminal = audit["terminal_account"]
    metrics = audit["formal_metrics"]
    trade_rows = audit["trade_legs"]["rows"]
    lines = [
        "# GATE001 最终研究报告草稿",
        "",
        "> **状态：待独立验收（pending independent review）。** 本稿是分红展示更正草稿；原始正式结果和审计历史保留不变。",
        "",
        "## 研究结论与范围",
        "",
        f"- 已保存正式结论：**{audit['research_verdict']}**。当前正式研究窗为 {audit['research_window']['start']} 至 {audit['research_window']['end']}。",
        "- 标的是 `510880.SH`。第四次技术 capture 的原状态仍是 `mismatch_stop`；此前离线补充审计用于校正经济腿关联，但没有重写原状态或错误列表。",
        f"- 完成闭环 {metrics['completed_round_trips']}/{metrics['minimum_completed_round_trips']}，独立入场年份 {metrics['entry_year_count']}/{metrics['minimum_entry_years']}（{', '.join(str(y) for y in metrics['distinct_entry_years'])}）。未达到最低证据门槛。",
        f"- 历史研究窗指标：CAGR {metrics['cagr_act_365']:.4%}；最大回撤损失幅度 {metrics['mdd_loss_fraction']:.4%}；Calmar {metrics['calmar']:.4f}；Sharpe {metrics['sharpe']:.4f}。这些数值仅复述冻结结果。",
        "- 本稿不评价当前行情、不称实际投资收益、不判定策略合格，也不作 Alpha 结论。期末仍有一笔未平仓持仓；它提供账户估值证据，不计入闭环最低门槛。",
        "",
        "## 七笔订单与信号来源",
        "",
        "每行对应一笔实际保存的成交订单。费用和净现金流按原始成交记录列出；分红只在下方周期表中归属一次，不重复记在买卖两腿。完整订单与信号 ID 保存在配套 JSON。",
        "",
        "| 成交日 / 方向 | 信号日 → 计划成交日 | 信号来源 | 数量 × 成交价 | 毛额 | 佣金 / 印花税 / 过户费 / 总费 | 净现金流 |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for row in trade_rows:
        fees = " / ".join(_fmt(row[key]) for key in ("commission_cny", "stamp_duty_cny", "transfer_fee_cny", "total_fee_cny"))
        source = "实录入场 Signal" if row["signal_source"] == "captured_signal" else "由持久化卖单推导；运行时退出 Signal 未捕获"
        lines.append(
            f"| {row['trade_date']} {row['direction']} | {row['signal_date']} → {row['intended_date']} | {source} | {row['quantity']:,} × {_price(row['fill_price_cny'])} | {_fmt(row['gross_amount_cny'])} | {fees} | {_fmt(row['net_cash_flow_cny'])} |"
        )
    lines += [
        "",
        "## 分红归一化与周期归属",
        "",
        f"冻结分红快照含 {div['raw_target_rows']} 条原始行；现有 `DividendLedger` 按经济事件归一为 {div['normalized_events']} 条，重复原始行 {div['duplicate_raw_rows_removed']} 条。每个分红事件仅归属一个持仓周期，且以 record date 的冻结持仓数量计算。",
        "",
        "以下周期表列的是净成交现金流（已含交易费用）及每个周期分红小计。分红事件明细是小计的拆分，不能与周期小计再次相加。",
        "",
        "| 周期 | 买入 → 卖出 / 期末 | 买入净流 | 卖出净流或期末市值 | 周期分红 | 已入账现金 / 应收 / 待除息权利 | 参考周期损益与核对式 |",
        "|---|---|---:|---:|---:|---|---:|",
    ]
    for row in cycle_data["cycle_rows"]:
        sell_or_value = row["sell_net_cash_flow_cny"] if row["sell_date"] else row["terminal_market_value_cny"]
        payment = " / ".join(_fmt(row[key]) for key in (
            "dividends_paid_to_simulated_cash_cny",
            "confirmed_receivable_at_cutoff_cny",
            "confirmed_right_pending_ex_date_cny",
        ))
        end_label = row["sell_date"] or audit["research_window"]["end"] + " 期末"
        lines.append(
            f"| {row['cycle_id']} | {row['buy_date']} → {end_label} | {_fmt(row['buy_net_cash_flow_cny'])} | {_fmt(sell_or_value)} | {_fmt(row['eligible_dividends_cny'])} | {payment} | {_fmt(row['reference_pnl_cny'])} ({row['equation']}) |"
        )
    lines += [
        "",
        f"- 分红事件合计 ¥{_fmt(cycle_data['eligible_dividend_total_cny'])}：在参考模拟账户中截至研究窗末均已按 pay date 入账；期末已确认应收 ¥{_fmt(cycle_data['confirmed_receivable_at_cutoff_cny'])}，已记录但尚未到 ex date 的权利 ¥{_fmt(cycle_data['confirmed_right_pending_ex_date_cny'])}。冻结数据窗外未来事件不估值、不计入。",
        "- 13 条归一事件中，9 条在 record date 有持仓，4 条当日无持仓。明细见 [分红核对证据 JSON](GATE001_DIVIDEND_DISPLAY_AUDIT.json)，含 record/ex/pay 日期、冻结数量和来源行引用。",
        "",
        "## 期末账户对齐",
        "",
        f"初始资金 ¥{_fmt(terminal['initial_capital_cny'])} + 三个闭环损益合计 ¥{_fmt(terminal['closed_cycle_pnl_total_cny'])} + 期末未平仓周期损益 ¥{_fmt(terminal['reference_open_cycle_pnl_cny'])} + 利息 ¥{_fmt(terminal['cash_interest_income_cny'])} = 期末 NAV ¥{_fmt(terminal['terminal_nav_cny'])}。账户组件：现金 ¥{_fmt(terminal['terminal_cash_cny'])} + 市值 ¥{_fmt(terminal['terminal_market_value_cny'])} + 应收 ¥{_fmt(terminal['terminal_receivable_cny'])}。未将费用再次扣除，也未将分红重复计入买卖腿。",
        "",
        "## 证据边界与披露",
        "",
        f"- 执行是 T+1 次日开盘价的日线代理，含冻结的滑点和规则化涨跌停/停牌处理；没有逐笔队列、真实撮合或实际成交证明。",
        f"- 分红原始快照标记为 `raw_unverified`；历史官方抽查仅覆盖 {', '.join(div['official_spotcheck_dates'])}，不能据此声称完整历史均已独立核实。单位为每基金份额人民币，原归一逻辑未作 `/10` 换算。",
        f"- Holdout 暴露：{audit['limitations_and_disclosures']['holdout_exposure']}",
        "- 原正式 JSON/Markdown、capture、sidecar、前次补充审计和历史账本行均未改写；本稿与配套核对 JSON 仍待独立验收。",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    audit, markdown = build_report()
    OUT_JSON.write_text(json.dumps(audit, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    OUT_MD.write_text(markdown, encoding="utf-8", newline="\n")
    print(json.dumps({
        "status": audit["report_status"],
        "markdown": str(OUT_MD),
        "markdown_sha256": _file_sha(OUT_MD),
        "dividend_audit": str(OUT_JSON),
        "dividend_audit_sha256": _file_sha(OUT_JSON),
        "raw_rows": audit["dividend_normalization"]["raw_target_rows"],
        "normalized_events": audit["dividend_normalization"]["normalized_events"],
        "duplicate_rows": audit["dividend_normalization"]["duplicate_raw_rows_removed"],
        "closed_cycles": audit["cycle_reconciliation"]["closed_cycles"],
        "open_cycles": audit["cycle_reconciliation"]["terminal_open_cycles"],
        "ledger_counts": audit["trial_counts_at_generation"],
    }, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
