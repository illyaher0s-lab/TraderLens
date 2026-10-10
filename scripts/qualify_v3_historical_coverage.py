"""Bounded v3 historical availability and liquidity coverage qualification."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict, deque
from datetime import date
from io import BytesIO
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from scripts.publish_v3_historical_scope import (
    DATA_REQUIREMENTS_HASH,
    DEFAULT_CALENDAR_DIR,
    TEMPLATE_HASH,
    TEMPLATE_ID,
    TEMPLATE_VERSION,
    _canonical,
    _sha256_bytes,
    _sha256_file,
    verify_scope,
)
from scripts.publish_v3_historical_suspension_evidence import DEFAULT_DIAGNOSTICS, DEFAULT_PROVIDER_PROBE
from scripts.v3_liquidity_source_adapter import SOURCE_ADAPTER_CONTRACT_HASH, SOURCE_ADAPTER_ID, resolve_source_amount
from scripts.verify_v3_historical_suspension_evidence import verify_evidence


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SCOPE_DIR = ROOT / "data/pit/historical_scope_freezes/acbc49159d989a46"
DEFAULT_INPUT_ROOT = ROOT / "data/pit/b3_execution_input_packages/b3eip_traderlens_v2_shsz_pit_001/inputs"
DEFAULT_FORMAL_ROOT = ROOT / "data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal"
DEFAULT_MEMBERSHIP_DIR = ROOT / "data/pit/pit_membership_snapshots/pims_traderlens_v2_shsz_sw2021_pit_005"
DEFAULT_LIFECYCLE_MANIFEST = ROOT / "data/pit/qualification_successors/49b09326f35936c6/manifest.json"
DEFAULT_B3_SUCCESSOR_MANIFEST = ROOT / "data/pit/b3_execution_input_packages/05f38a2884dc7e47/manifest.json"
DEFAULT_LIQUIDITY_SUCCESSOR_MANIFEST = ROOT / "data/pit/liquidity_qualification_successors/7c05ece4d3f01086/manifest.json"
DEFAULT_OUTPUT_ROOT = ROOT / "data/pit/v3_historical_coverage_packages"
V3_MEMBERSHIP_ID = "pims_traderlens_v2_shsz_sw2021_pit_005"
LIFECYCLE_ID = "49b09326f35936c6"
B3_SUCCESSOR_ID = "05f38a2884dc7e47"
LIQUIDITY_SUCCESSOR_ID = "7c05ece4d3f01086"


def _default_suspension_evidence_manifest() -> Path:
    root = ROOT / "data/pit/v3_historical_suspension_evidence"
    manifests = sorted(root.glob("*/manifest.json")) if root.exists() else []
    if len(manifests) != 1:
        raise ValueError("suspension evidence binding is missing or ambiguous")
    return manifests[0]


def _load_suspension_evidence(manifest_path: Path | None, scope_dir: Path) -> tuple[dict, dict[tuple[str, str, str], dict], dict]:
    manifest_path = Path(manifest_path) if manifest_path is not None else _default_suspension_evidence_manifest()
    verification = verify_evidence(manifest_path.parent, diagnostics_path=DEFAULT_DIAGNOSTICS, provider_probe_path=DEFAULT_PROVIDER_PROBE, scope_dir=scope_dir)
    manifest = _read_json(manifest_path)
    lookup = {
        (entry["symbol"], entry["missing_date"], execution): entry
        for entry in manifest["entries"]
        for execution in entry["execution_dates"]
    }
    try:
        repo_path = manifest_path.relative_to(ROOT).as_posix()
    except ValueError:
        repo_path = str(manifest_path)
    binding = {
        "artifact_id": verification["artifact_id"],
        "manifest_sha256": _sha256_file(manifest_path),
        "repo_relative_path": repo_path,
        "source_adapter_id": manifest["source_adapter"]["id"],
        "source_adapter_contract_sha256": manifest["source_adapter"]["contract_sha256"],
    }
    return manifest, lookup, binding


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sidecar_hash(path: Path) -> str:
    parts = path.read_text(encoding="utf-8").strip().split()
    if not parts or len(parts[0]) != 64:
        raise ValueError(f"invalid sidecar: {path}")
    return parts[0]


def _check_sidecar(path: Path) -> None:
    sidecar = path.with_name(path.name + ".sha256")
    if not sidecar.exists() or _sidecar_hash(sidecar) != _sha256_file(path):
        raise ValueError(f"sidecar mismatch: {path}")


def _day(value: object) -> str:
    if isinstance(value, date):
        return value.strftime("%Y%m%d")
    return str(value).replace("-", "")[:8]


def _finite(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _partition(root: Path, day: str, columns: list[str], interface: str, read_counts: Counter) -> list[dict]:
    path = root / f"trade_date={day}" / "part.parquet"
    if not path.exists():
        raise ValueError(f"data_fault: missing {interface} partition {day}")
    key = f"{interface}:{day}"
    read_counts[key] += 1
    rows = pq.read_table(path, columns=columns).to_pylist()
    if any(_day(row.get("trade_date")) != day for row in rows if "trade_date" in row):
        raise ValueError(f"data_fault: {interface} date mismatch {day}")
    return rows


def _unique_map(rows: list[dict], key: str, interface: str, day: str) -> dict[str, dict]:
    result = {}
    for row in rows:
        symbol = row.get(key)
        if not symbol or symbol in result:
            raise ValueError(f"data_fault: duplicate or empty {interface} symbol {day}")
        result[symbol] = row
    return result


def _inventory(root: Path, dates: list[str]) -> dict:
    entries = []
    for day in dates:
        path = root / f"trade_date={day}" / "part.parquet"
        if not path.exists():
            raise ValueError(f"missing source partition for inventory: {root.name} {day}")
        entries.append({"path": path.relative_to(root).as_posix(), "sha256": _sha256_file(path), "byte_size": path.stat().st_size})
    return {"entry_count": len(entries), "content_hash": _sha256_bytes(_canonical(entries)), "entries": entries}


def _load_lifecycle(stock_basic_root: Path, lifecycle_manifest_path: Path) -> tuple[dict[str, tuple[str, str | None]], dict]:
    lifecycle_manifest = _read_json(lifecycle_manifest_path)
    _check_sidecar(lifecycle_manifest_path)
    if lifecycle_manifest.get("schema_version") != "bounded_vendor_lifecycle_successor.v1":
        raise ValueError("lifecycle successor schema mismatch")
    if lifecycle_manifest.get("qualification_status") != "bounded_qualified_vendor_lifecycle":
        raise ValueError("lifecycle successor status mismatch")
    if lifecycle_manifest.get("successor_id", LIFECYCLE_ID) != LIFECYCLE_ID:
        raise ValueError("lifecycle successor identity mismatch")
    result: dict[str, tuple[str, str | None]] = {}
    for status in ("L", "D", "P"):
        path = stock_basic_root / f"list_status={status}" / "part.parquet"
        rows = pq.read_table(path, columns=["ts_code", "list_date", "delist_date"]).to_pylist()
        for row in rows:
            symbol = row["ts_code"]
            if symbol in result:
                raise ValueError(f"data_fault: duplicate lifecycle {symbol}")
            result[symbol] = (_day(row["list_date"]), _day(row["delist_date"]) if row.get("delist_date") else None)
    for row in lifecycle_manifest["codes"]:
        symbol = row["ts_code"]
        supplied = (_day(row["list_date"]), _day(row["delist_date"]) if row.get("delist_date") else None)
        if symbol in result and result[symbol] != supplied:
            raise ValueError(f"lifecycle source conflict: {symbol}")
        result[symbol] = supplied
    return result, {
        "manifest_sha256": _sha256_file(lifecycle_manifest_path),
        "manifest_repo_relative_path": lifecycle_manifest_path.relative_to(ROOT).as_posix(),
        "stock_basic_root": stock_basic_root.relative_to(ROOT).as_posix(),
        "stock_basic_files": [
            {"path": path.relative_to(stock_basic_root).as_posix(), "sha256": _sha256_file(path)}
            for path in sorted(stock_basic_root.glob("list_status=*/part.parquet"))
        ],
    }


def _load_membership(membership_dir: Path) -> tuple[dict[str, list[tuple[str, str | None]]], dict]:
    manifest_path = membership_dir / "manifest.json"
    records_path = membership_dir / "records.parquet"
    _check_sidecar(manifest_path)
    _check_sidecar(records_path)
    manifest = _read_json(manifest_path)
    if manifest.get("snapshot_id") != V3_MEMBERSHIP_ID:
        raise ValueError("membership snapshot identity mismatch")
    if manifest.get("records_parquet_sha256") != _sha256_file(records_path):
        raise ValueError("membership records binding mismatch")
    intervals: dict[str, list[tuple[str, str | None]]] = defaultdict(list)
    for row in pq.read_table(records_path, columns=["symbol", "effective_from", "effective_to", "snapshot_id"]).to_pylist():
        if row.get("snapshot_id") != V3_MEMBERSHIP_ID:
            raise ValueError("membership record snapshot mismatch")
        intervals[row["symbol"]].append((_day(row["effective_from"]), _day(row["effective_to"]) if row.get("effective_to") else None))
    return intervals, {
        "snapshot_id": V3_MEMBERSHIP_ID,
        "manifest_sha256": _sha256_file(manifest_path),
        "manifest_repo_relative_path": manifest_path.relative_to(ROOT).as_posix(),
        "records_sha256": _sha256_file(records_path),
        "records_repo_relative_path": records_path.relative_to(ROOT).as_posix(),
    }


def _active(intervals: dict[str, list[tuple[str, str | None]]], lifecycle: dict[str, tuple[str, str | None]], day: str) -> list[str]:
    out = []
    for symbol, ranges in intervals.items():
        if not symbol.endswith((".SH", ".SZ")):
            continue
        if symbol not in lifecycle:
            raise ValueError(f"data_fault: membership symbol missing lifecycle {symbol}")
        list_date, delist_date = lifecycle[symbol]
        if list_date > day or (delist_date is not None and day >= delist_date):
            continue
        if any(start <= day and (end is None or day <= end) for start, end in ranges):
            out.append(symbol)
    return sorted(out)


def _parquet_bytes(rows: list[dict], columns: list[str]) -> bytes:
    if rows:
        table = pa.Table.from_pylist(rows)
    else:
        table = pa.table({column: pa.array([], type=pa.string()) for column in columns})
    buffer = BytesIO()
    pq.write_table(table, buffer, compression="snappy")
    return buffer.getvalue()


def scan_coverage(
    *,
    scope_dir: Path = DEFAULT_SCOPE_DIR,
    execution_dates: list[str] | None = None,
    calendar_dir: Path = DEFAULT_CALENDAR_DIR,
    input_root: Path = DEFAULT_INPUT_ROOT,
    formal_root: Path = DEFAULT_FORMAL_ROOT,
    membership_dir: Path = DEFAULT_MEMBERSHIP_DIR,
    lifecycle_manifest_path: Path = DEFAULT_LIFECYCLE_MANIFEST,
    b3_successor_manifest_path: Path = DEFAULT_B3_SUCCESSOR_MANIFEST,
    liquidity_successor_manifest_path: Path = DEFAULT_LIQUIDITY_SUCCESSOR_MANIFEST,
    suspension_evidence_manifest_path: Path | None = None,
) -> dict:
    verify_scope(scope_dir, calendar_dir=calendar_dir)
    _, suspension_evidence, suspension_evidence_binding = _load_suspension_evidence(suspension_evidence_manifest_path, Path(scope_dir))
    scope = _read_json(Path(scope_dir) / "manifest.json")
    all_execution_dates = list(scope["execution"]["dates"])
    selected = list(execution_dates or all_execution_dates)
    if any(day not in all_execution_dates for day in selected) or selected != all_execution_dates[: len(selected)]:
        raise ValueError("execution subset must be an ordered prefix of the frozen scope")
    selected_asofs = scope["execution"]["as_of_dates"][: len(selected)]
    source_dates = list(scope["source"]["dates"])
    source_end = selected_asofs[-1] if selected_asofs else source_dates[-1]
    source_dates = [day for day in source_dates if day <= source_end or day in selected]
    if not selected:
        raise ValueError("empty execution scope")

    b3_manifest = _read_json(b3_successor_manifest_path)
    _check_sidecar(b3_successor_manifest_path)
    if b3_manifest.get("artifact_id") != B3_SUCCESSOR_ID or b3_manifest.get("authorization_scope") != "b3_execution_input_binding_only":
        raise ValueError("B3 successor binding mismatch")
    liquidity_manifest = _read_json(liquidity_successor_manifest_path)
    _check_sidecar(liquidity_successor_manifest_path)
    if (
        liquidity_manifest.get("artifact_id") != LIQUIDITY_SUCCESSOR_ID
        or liquidity_manifest.get("schema_version") != "v3_liquidity_qualification_successor.v1"
        or liquidity_manifest.get("scope", {}).get("start") != "20260710"
        or liquidity_manifest.get("scope", {}).get("end") != "20260710"
    ):
        raise ValueError("current-D-only liquidity artifact cannot be used as historical qualification")
    lifecycle, lifecycle_binding = _load_lifecycle(formal_root / "stock_basic", lifecycle_manifest_path)
    membership_intervals, membership_binding = _load_membership(membership_dir)
    read_counts: Counter = Counter()
    daily_history: deque[tuple[str, set[str], set[str]]] = deque()
    daily_valid_counts: Counter = Counter()
    adj_valid_counts: Counter = Counter()
    liquidity_window: deque[tuple[str, dict[str, dict], dict[str, list[dict]]]] = deque()
    expected_by_execution = {
        execution: _active(membership_intervals, lifecycle, asof)
        for execution, asof in zip(selected, selected_asofs)
    }
    asof_to_execution = {asof: execution for execution, asof in zip(selected, selected_asofs)}
    history_results: dict[str, dict[str, tuple[str, str | None, list[str]]]] = {}
    liquidity_faults: defaultdict[str, set[str]] = defaultdict(set)
    liquidity_ineligible: defaultdict[str, set[str]] = defaultdict(set)
    liquidity_results: dict[str, dict[str, bool]] = defaultdict(dict)

    for day in source_dates:
        if day in {selected[0], *selected[1:]}:
            execution = day
            expected = expected_by_execution[day]
            if len(liquidity_window) != 20:
                raise ValueError(f"data_fault: liquidity warm-up is not 20 days before {day}")
            for symbol in expected:
                if sum(1 for prior_day, _, _ in liquidity_window if prior_day >= lifecycle[symbol][0]) < 20:
                    liquidity_ineligible[day].add(symbol)
                    continue
                liquidity_fault = False
                amount_values = []
                for prior_day, daily_map, suspend_map in liquidity_window:
                    decision = resolve_source_amount(
                        daily_row=daily_map.get(symbol),
                        suspend_rows=suspend_map.get(symbol, []),
                        interval_evidence=suspension_evidence.get((symbol, prior_day, execution)),
                    )
                    if decision["status"] == "data_fault":
                        liquidity_fault = True
                        break
                    amount_values.append(decision["amount_yuan"])
                if liquidity_fault:
                    liquidity_faults[day].add(symbol)
                else:
                    liquidity_results[day][symbol] = (sum(amount_values) / 20.0) >= 50_000_000

        daily_rows = _unique_map(_partition(input_root / "daily", day, ["ts_code", "trade_date", "close", "amount"], "daily", read_counts), "ts_code", "daily", day)
        adj_rows = _unique_map(_partition(input_root / "adj_factor", day, ["ts_code", "trade_date", "adj_factor"], "adj_factor", read_counts), "ts_code", "adj_factor", day)
        suspend_rows = _partition(input_root / "suspend_d", day, ["ts_code", "trade_date", "suspend_type"], "suspend_d", read_counts)
        suspend_map: dict[str, list[dict]] = defaultdict(list)
        for row in suspend_rows:
            suspend_map[row["ts_code"]].append(row)
        daily_valid = {symbol for symbol, row in daily_rows.items() if _finite(row.get("close"))}
        adj_valid = {symbol for symbol, row in adj_rows.items() if _finite(row.get("adj_factor"))}
        daily_history.append((day, daily_valid, adj_valid))
        for symbol in daily_valid:
            daily_valid_counts[symbol] += 1
        for symbol in adj_valid:
            adj_valid_counts[symbol] += 1
        if len(daily_history) > 253:
            _, old_daily, old_adj = daily_history.popleft()
            for symbol in old_daily:
                daily_valid_counts[symbol] -= 1
            for symbol in old_adj:
                adj_valid_counts[symbol] -= 1

        if day in asof_to_execution:
            execution = asof_to_execution[day]
            expected = expected_by_execution[execution]
            history_start = scope["source"]["dates"][scope["source"]["dates"].index(day) - 252]
            results = {}
            for symbol in expected:
                missing = []
                list_date = lifecycle[symbol][0]
                if list_date > history_start:
                    status = "unavailable_ineligible"
                    reason = "insufficient_history"
                else:
                    if daily_valid_counts[symbol] < 253:
                        missing.append("daily.close")
                    if adj_valid_counts[symbol] < 253:
                        missing.append("adj_factor.adj_factor")
                    status = "unavailable" if missing else "complete"
                    reason = "required_history_missing" if missing else None
                results[symbol] = (status, reason, missing)
            history_results[execution] = results

        liquidity_window.append((day, daily_rows, dict(suspend_map)))
        if len(liquidity_window) > 20:
            liquidity_window.popleft()

    coverage_rows: list[dict] = []
    unavailable_rows: list[dict] = []
    by_code: defaultdict[str, Counter] = defaultdict(Counter)
    field_missing_counts: Counter = Counter()
    first_data_fault = None
    for execution, asof in zip(selected, selected_asofs):
        expected = expected_by_execution[execution]
        complete = unavailable = data_fault = 0
        for symbol in expected:
            status, reason, missing = history_results[execution][symbol]
            if symbol in liquidity_faults[execution]:
                status = "data_fault"
                reason = "daily.amount missing outside suspension"
                data_fault += 1
                first_data_fault = first_data_fault or {"symbol": symbol, "execution_date": execution, "reason": reason}
                unavailable_rows.append({"execution_date": execution, "as_of_date": asof, "symbol": symbol, "status": status, "reason": reason, "missing_fields": ["daily.amount"]})
            else:
                if symbol in liquidity_ineligible[execution]:
                    status = "unavailable_ineligible"
                    reason = "insufficient_liquidity_history"
                if status == "complete":
                    complete += 1
                else:
                    unavailable += 1
                    for field in missing:
                        field_missing_counts[field] += 1
                    unavailable_rows.append({"execution_date": execution, "as_of_date": asof, "symbol": symbol, "status": status, "reason": reason, "missing_fields": missing})
            by_code[symbol][status] += 1
        coverage_rows.append({"execution_date": execution, "as_of_date": asof, "expected_codes": len(expected), "complete_codes": complete, "unavailable_codes": unavailable, "data_fault_codes": data_fault})
    stats = {
        "expected_stock_days": sum(row["expected_codes"] for row in coverage_rows),
        "complete_stock_days": sum(row["complete_codes"] for row in coverage_rows),
        "unavailable_stock_days": sum(row["unavailable_codes"] for row in coverage_rows),
        "data_fault_count": sum(row["data_fault_codes"] for row in coverage_rows),
        "first_data_fault": first_data_fault,
        "field_missing_counts": dict(sorted(field_missing_counts.items())),
    }
    for row in coverage_rows:
        liquidity = liquidity_results[row["execution_date"]]
        expected = expected_by_execution[row["execution_date"]]
        row["liquidity_valid_codes"] = len(liquidity)
        row["liquidity_threshold_pass_codes"] = sum(1 for symbol in expected if liquidity.get(symbol) is True)
        row["liquidity_threshold_fail_codes"] = sum(1 for symbol in expected if liquidity.get(symbol) is False)
    if stats["expected_stock_days"] != stats["complete_stock_days"] + stats["unavailable_stock_days"] + stats["data_fault_count"]:
        raise ValueError("coverage arithmetic mismatch")
    return {
        "execution_count": len(selected),
        "scope": scope,
        "stats": stats,
        "coverage_rows": coverage_rows,
        "unavailable_rows": unavailable_rows,
        "by_code": [{"symbol": symbol, **dict(counts)} for symbol, counts in sorted(by_code.items())],
        "partition_read_counts": dict(read_counts),
        "source_dates": source_dates,
        "lifecycle_binding": lifecycle_binding,
        "membership_binding": membership_binding,
        "suspension_evidence_binding": suspension_evidence_binding,
        "b3_manifest_sha256": _sha256_file(b3_successor_manifest_path),
        "b3_manifest_repo_relative_path": b3_successor_manifest_path.relative_to(ROOT).as_posix(),
        "liquidity_lineage": {
            "artifact_id": LIQUIDITY_SUCCESSOR_ID,
            "manifest_sha256": _sha256_file(liquidity_successor_manifest_path),
            "manifest_repo_relative_path": liquidity_successor_manifest_path.relative_to(ROOT).as_posix(),
            "usage": "algorithm_and_correction_evidence_only; historical values recomputed from source partitions",
        },
    }


def publish_coverage(
    *,
    scope_dir: Path = DEFAULT_SCOPE_DIR,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    calendar_dir: Path = DEFAULT_CALENDAR_DIR,
    input_root: Path = DEFAULT_INPUT_ROOT,
    formal_root: Path = DEFAULT_FORMAL_ROOT,
    membership_dir: Path = DEFAULT_MEMBERSHIP_DIR,
    lifecycle_manifest_path: Path = DEFAULT_LIFECYCLE_MANIFEST,
    b3_successor_manifest_path: Path = DEFAULT_B3_SUCCESSOR_MANIFEST,
    liquidity_successor_manifest_path: Path = DEFAULT_LIQUIDITY_SUCCESSOR_MANIFEST,
    suspension_evidence_manifest_path: Path | None = None,
) -> dict:
    result = scan_coverage(
        scope_dir=scope_dir,
        calendar_dir=calendar_dir,
        input_root=input_root,
        formal_root=formal_root,
        membership_dir=membership_dir,
        lifecycle_manifest_path=lifecycle_manifest_path,
        b3_successor_manifest_path=b3_successor_manifest_path,
        liquidity_successor_manifest_path=liquidity_successor_manifest_path,
        suspension_evidence_manifest_path=suspension_evidence_manifest_path,
    )
    stats = result["stats"]
    if stats["data_fault_count"] != 0:
        raise ValueError(f"data_fault: {stats['first_data_fault']}")
    if stats["expected_stock_days"] != stats["complete_stock_days"] + stats["unavailable_stock_days"]:
        raise ValueError("coverage arithmetic mismatch")
    scope = result["scope"]
    coverage_by_date = _parquet_bytes(result["coverage_rows"], ["execution_date", "as_of_date", "expected_codes", "complete_codes", "unavailable_codes", "data_fault_codes", "liquidity_valid_codes", "liquidity_threshold_pass_codes", "liquidity_threshold_fail_codes"])
    coverage_by_code = _parquet_bytes(result["by_code"], ["symbol", "complete", "unavailable", "unavailable_ineligible"])
    unavailable = _parquet_bytes(result["unavailable_rows"], ["execution_date", "as_of_date", "symbol", "status", "reason", "missing_fields"])
    files = {
        "coverage_by_date": {"sha256": _sha256_bytes(coverage_by_date), "byte_size": len(coverage_by_date)},
        "coverage_by_code": {"sha256": _sha256_bytes(coverage_by_code), "byte_size": len(coverage_by_code)},
        "unavailable": {"sha256": _sha256_bytes(unavailable), "byte_size": len(unavailable)},
    }
    payload = {
        "schema_version": "v3_historical_coverage.v1",
        "status": "published",
        "frozen": True,
        "template": {"template_id": TEMPLATE_ID, "template_version": TEMPLATE_VERSION, "template_hash": TEMPLATE_HASH, "data_requirements_hash": DATA_REQUIREMENTS_HASH},
        "scope_freeze": {"artifact_id": scope["artifact_id"], "manifest_sha256": _sha256_file(Path(scope_dir) / "manifest.json"), "path": Path(scope_dir).relative_to(ROOT).as_posix()},
        "lineage": {
            "b3_execution_input_successor": {"artifact_id": B3_SUCCESSOR_ID, "manifest_sha256": result["b3_manifest_sha256"], "path": result["b3_manifest_repo_relative_path"], "authorization_scope": "b3_execution_input_binding_only"},
            "liquidity_successor_lineage": result["liquidity_lineage"],
            "lifecycle_successor": {"artifact_id": LIFECYCLE_ID, **result["lifecycle_binding"]},
            "membership_snapshot": result["membership_binding"],
            "suspension_evidence": result["suspension_evidence_binding"],
        },
        "calendar": scope["calendar"],
        "execution_scope": {"count": scope["execution"]["count"], "start": scope["execution"]["start"], "end": scope["execution"]["end"], "ordered_date_set_sha256": scope["execution"]["ordered_date_set_sha256"], "as_of_ordered_dates_sha256": _sha256_bytes(_canonical(scope["execution"]["as_of_dates"]))},
        "source_scope": {"count": scope["source"]["count"], "start": scope["source"]["start"], "end": scope["source"]["end"], "ordered_date_set_sha256": scope["source"]["ordered_date_set_sha256"]},
        "liquidity_algorithm": {
            "algorithm_id": "avg_amount_20d_shsz_common_v1",
            "window_trading_days": 20,
            "execution_day_excluded": True,
            "source_field": "daily.amount",
            "source_unit": "thousand_yuan",
            "yuan_multiplier": 1000,
            "threshold_yuan": 50000000,
            "minimum_history_trading_days": 20,
            "suspension_evidence_source": "suspend_d",
            "suspended_day_amount_yuan": 0,
            "partial_mean_allowed": False,
            "window_extension_allowed": False,
            "insufficient_history": "unavailable_ineligible",
            "other_missing": "data_fault",
            "algorithm_hash": _sha256_bytes(_canonical({"algorithm_id": "avg_amount_20d_shsz_common_v1", "window_trading_days": 20, "execution_day_excluded": True, "source_field": "daily.amount", "source_unit": "thousand_yuan", "yuan_multiplier": 1000, "threshold_yuan": 50000000, "minimum_history_trading_days": 20, "suspension_evidence_source": "suspend_d", "suspended_day_amount_yuan": 0, "partial_mean_allowed": False, "window_extension_allowed": False, "insufficient_history": "unavailable_ineligible", "other_missing": "data_fault"})),
        },
        "source_adapter": {"id": SOURCE_ADAPTER_ID, "contract_sha256": SOURCE_ADAPTER_CONTRACT_HASH},
        "sources": {
            "daily": _inventory(input_root / "daily", result["source_dates"]),
            "adj_factor": _inventory(input_root / "adj_factor", result["source_dates"]),
            "suspend_d": _inventory(input_root / "suspend_d", result["source_dates"]),
            "formal_input_root": input_root.relative_to(ROOT).as_posix(),
        },
        "files": files,
        "coverage": {**stats, "structural_validation": "passed", "structural_errors": []},
        "not_authorized_for_b6_oos_gate_promotion_signal": False,
    }
    artifact_id = _sha256_bytes(_canonical(payload))[:16]
    target = Path(output_root) / artifact_id
    output_bytes = {
        "coverage_by_date.parquet": coverage_by_date,
        "coverage_by_code.parquet": coverage_by_code,
        "unavailable_security_dates.parquet": unavailable,
    }
    raw = _canonical({**payload, "artifact_id": artifact_id})
    if target.exists():
        paths = [target / "manifest.json", target / "manifest.json.sha256"] + [target / name for name in output_bytes]
        if not all(path.exists() for path in paths):
            raise ValueError("coverage write-once conflict: incomplete existing artifact")
        if (target / "manifest.json").read_bytes() != raw:
            raise ValueError("coverage write-once conflict: manifest differs")
        for name, value in output_bytes.items():
            if (target / name).read_bytes() != value:
                raise ValueError(f"coverage write-once conflict: {name} differs")
        return {"status": "already_published", "artifact_id": artifact_id, "path": str(target), "stats": stats}
    target.mkdir(parents=True, exist_ok=False)
    (target / "manifest.json").write_bytes(raw)
    (target / "manifest.json.sha256").write_text(_sha256_bytes(raw) + "  manifest.json\n", encoding="utf-8")
    for name, value in output_bytes.items():
        (target / name).write_bytes(value)
        (target / f"{name}.sha256").write_text(_sha256_bytes(value) + f"  {name}\n", encoding="utf-8")
    return {"status": "published", "artifact_id": artifact_id, "path": str(target), "stats": stats}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope-dir", type=Path, default=DEFAULT_SCOPE_DIR)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args()
    result = publish_coverage(scope_dir=args.scope_dir, output_root=args.output_root)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
