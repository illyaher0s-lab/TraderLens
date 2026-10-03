"""Bounded, candidate-only market-regime replay for the registered windows."""
from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "backend/config/market_regime_thresholds.yaml"
FORMAL_ROOT = ROOT / "data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal"
INDEX_SOURCE_ROOT = ROOT / "data/pit/market_regime_index_sources"
QUALIFICATION_ROOT = ROOT / "data/pit/market_regime_qualifications"
INDEX_FIELDS = ("ts_code", "trade_date", "close", "pre_close")
REQUIRED_RULES = (
    "extreme_breadth_selloff",
    "structural_breakdown_1d",
    "structural_breakdown_5d",
    "liquidity_exhaustion",
)
REQUIRED_PIT_INPUTS = (
    "trade_cal",
    "daily",
    "index_daily",
    "stock_basic",
    "namechange",
    "suspend_d",
)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha_file(path: Path) -> str:
    return _sha_bytes(path.read_bytes())


def _day(value: object) -> str:
    return str(value).replace("-", "")[:8]


def _finite(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _repo_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(resolved)


def _sidecar(path: Path) -> None:
    sidecar = path.with_name(path.name + ".sha256")
    if not sidecar.exists() or sidecar.read_text(encoding="utf-8").split()[0] != _sha_file(path):
        raise ValueError(f"source artifact sidecar mismatch: {path}")


def _write_sidecar(path: Path) -> None:
    path.with_name(path.name + ".sha256").write_text(
        f"{_sha_file(path)}  {path.name}\n", encoding="utf-8"
    )


def _normalize_index_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for raw in rows:
        if raw.get("ts_code") != "000300.SH":
            raise ValueError("index source contains a non-000300.SH row")
        day = _day(raw.get("trade_date"))
        close = raw.get("close")
        pre_close = raw.get("pre_close")
        if len(day) != 8 or not (_finite(close) and float(close) > 0 and _finite(pre_close) and float(pre_close) > 0):
            raise ValueError(f"invalid index source row: {raw}")
        normalized.append(
            {"ts_code": "000300.SH", "trade_date": day, "close": float(close), "pre_close": float(pre_close)}
        )
    normalized.sort(key=lambda row: row["trade_date"])
    days = [row["trade_date"] for row in normalized]
    if not normalized or len(days) != len(set(days)):
        raise ValueError("index source must have unique non-empty dates")
    return normalized


def publish_index_source(
    rows: list[dict[str, Any]],
    requests: list[dict[str, str]],
    output_root: Path = INDEX_SOURCE_ROOT,
    retrieved_at: str | None = None,
) -> dict[str, Any]:
    """Persist exactly the bounded 000300.SH provider rows with deterministic identity."""
    normalized = _normalize_index_rows(rows)
    dates = [row["trade_date"] for row in normalized]
    payload = {
        "schema_version": "market_regime_index_source.v1",
        "provider": "tushare",
        "api": "index_daily",
        "ts_code": "000300.SH",
        "requests": sorted(requests, key=lambda request: (request["start_date"], request["end_date"])),
        "fields": list(INDEX_FIELDS),
        "row_count": len(normalized),
        "date_set": dates,
        "date_set_sha256": _sha_bytes(_canonical(dates)),
        "rows_sha256": _sha_bytes(_canonical(normalized)),
        "not_authorized_for_b3_b6_oos_gate_promotion_signal": True,
    }
    artifact_id = _sha_bytes(_canonical(payload))[:16]
    target = Path(output_root) / artifact_id
    if target.exists():
        if not target.is_dir():
            raise ValueError(f"source artifact write-once conflict: {target}")
        verified = verify_index_source(target)
        if verified["artifact_id"] != artifact_id:
            raise ValueError(f"source artifact write-once conflict: {target}")
        return {"status": "already_published", "artifact_id": artifact_id, "path": str(target)}

    target.mkdir(parents=True, exist_ok=False)
    parquet_path = target / "index_daily_000300.parquet"
    table = pa.Table.from_pylist(normalized, schema=pa.schema([
        pa.field("ts_code", pa.string()),
        pa.field("trade_date", pa.string()),
        pa.field("close", pa.float64()),
        pa.field("pre_close", pa.float64()),
    ]))
    pq.write_table(table, parquet_path, compression="snappy")
    manifest = {
        **payload,
        "artifact_id": artifact_id,
        "retrieved_at": retrieved_at or datetime.now(timezone.utc).isoformat(),
        "file": {
            "path": parquet_path.name,
            "sha256": _sha_file(parquet_path),
            "byte_size": parquet_path.stat().st_size,
        },
    }
    manifest_path = target / "manifest.json"
    manifest_path.write_bytes(_canonical(manifest))
    _write_sidecar(parquet_path)
    _write_sidecar(manifest_path)
    return {"status": "published", "artifact_id": artifact_id, "path": str(target)}


def verify_index_source(source_dir: Path) -> dict[str, Any]:
    source_dir = Path(source_dir)
    manifest_path = source_dir / "manifest.json"
    parquet_path = source_dir / "index_daily_000300.parquet"
    if not manifest_path.exists() or not parquet_path.exists():
        raise ValueError(f"source artifact incomplete: {source_dir}")
    _sidecar(manifest_path)
    _sidecar(parquet_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload = {key: manifest[key] for key in (
        "schema_version", "provider", "api", "ts_code", "requests", "fields", "row_count",
        "date_set", "date_set_sha256", "rows_sha256", "not_authorized_for_b3_b6_oos_gate_promotion_signal",
    )}
    artifact_id = _sha_bytes(_canonical(payload))[:16]
    if manifest.get("schema_version") != "market_regime_index_source.v1" or manifest.get("artifact_id") != artifact_id:
        raise ValueError("source artifact identity mismatch")
    if manifest.get("file", {}).get("sha256") != _sha_file(parquet_path):
        raise ValueError("source artifact file hash mismatch")
    rows = _normalize_index_rows(pq.read_table(parquet_path).to_pylist())
    if len(rows) != manifest["row_count"] or [row["trade_date"] for row in rows] != manifest["date_set"]:
        raise ValueError("source artifact row/date binding mismatch")
    if _sha_bytes(_canonical(rows)) != manifest["rows_sha256"]:
        raise ValueError("source artifact row hash mismatch")
    return {"status": "verified", "artifact_id": artifact_id, "path": str(source_dir), "row_count": len(rows)}


def _load_config(config_path: Path) -> tuple[dict[str, Any], str]:
    config = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    version = str(config.get("version"))
    if version not in {"1.1", "1.2"} or config.get("validation_status") != "candidate":
        raise ValueError("market-regime config must be candidate version 1.1 or 1.2")
    if version == "1.2":
        minimum = config.get("stress_window_block_day_min")
        if isinstance(minimum, bool) or not isinstance(minimum, int) or minimum < 1:
            raise ValueError("market-regime v1.2 stress_window_block_day_min must be an integer >= 1")
    rules = config.get("candidate_rules", {})
    if set(rules) != set(REQUIRED_RULES) or len(rules) != len(REQUIRED_RULES):
        raise ValueError("market-regime rule set mismatch")
    if tuple(config.get("required_pit_inputs", REQUIRED_PIT_INPUTS)) != REQUIRED_PIT_INPUTS:
        raise ValueError("market-regime required PIT input set mismatch")
    for window in config.get("stress_windows", []):
        if _day(window["start"]) < "20160101" or _day(window["end"]) < "20160101":
            raise ValueError("market-regime window precedes 2016-01-01")
    normal = config["normal_window"]
    if _day(normal["start"]) < "20160101" or _day(normal["end"]) < "20160101":
        raise ValueError("normal window precedes 2016-01-01")
    semantic = {key: config[key] for key in (
        "version", "candidate_rules", "stress_windows", "normal_window", "zero_gap_rule",
        "stress_window_block_day_min", "normal_window_block_ratio_max", "required_pit_inputs",
    ) if key in config}
    return config, _sha_bytes(_canonical(semantic))


def _calendar_days(formal_root: Path) -> list[str]:
    path = Path(formal_root) / "trade_cal" / "part.parquet"
    rows = pq.read_table(path, columns=["cal_date", "is_open"]).to_pylist()
    days = sorted({_day(row["cal_date"]) for row in rows if int(row["is_open"]) == 1})
    if not days:
        raise ValueError("formal trade calendar has no open days")
    return days


def _window_days(calendar: list[str], start: str, end: str) -> list[str]:
    days = [day for day in calendar if _day(start) <= day <= _day(end)]
    if not days:
        raise ValueError(f"registered window has no formal trading days: {start}..{end}")
    return days


def _prior_days(calendar: list[str], day: str, count: int) -> list[str]:
    index = calendar.index(day)
    if index < count:
        raise ValueError(f"insufficient calendar warm-up before {day}")
    return calendar[index - count:index]


def _read_rows(path: Path, columns: list[str]) -> list[dict[str, Any]]:
    if not path.exists():
        raise ValueError(f"missing formal source partition: {_repo_path(path)}")
    return pq.read_table(path, columns=columns).to_pylist()


def _lifecycle(formal_root: Path) -> dict[str, tuple[str, str | None]]:
    table: dict[str, tuple[str, str | None]] = {}
    for status in ("L", "D", "P"):
        for row in _read_rows(Path(formal_root) / "stock_basic" / f"list_status={status}" / "part.parquet", ["ts_code", "list_date", "delist_date"]):
            symbol = row.get("ts_code")
            if not symbol:
                continue
            value = (_day(row["list_date"]), _day(row["delist_date"]) if row.get("delist_date") else None)
            if symbol in table and table[symbol] != value:
                raise ValueError(f"duplicate lifecycle conflict: {symbol}")
            table[symbol] = value
    return table


def resolve_market_regime_gap(
    symbol: str,
    day: str,
    daily_row: dict | None,
    evidence: dict | None,
    suspend_rows: list[dict] | None = None,
) -> dict[str, str]:
    """Apply market-regime-only evidence without masking a formal daily row."""
    if daily_row is not None:
        if evidence is not None:
            raise ValueError(f"market-regime evidence conflicts with daily row: {symbol}/{day}")
        return {"status": "daily"}
    if any(row.get("suspend_type") in ("S", "P") for row in (suspend_rows or [])):
        return {"status": "non_tradable"}
    if evidence is not None and evidence.get("qualified") is True:
        return {"status": "non_tradable"}
    raise ValueError(f"daily row missing without authorized evidence: {symbol}/{day}")


def load_market_regime_evidence(evidence_dir: Path) -> tuple[str, str, dict[tuple[str, str], dict]]:
    evidence_dir = Path(evidence_dir)
    manifest_path = evidence_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") == "market_regime_v12_suspension_evidence.v1":
        from scripts.publish_market_regime_v12_suspension_evidence import verify_v12_evidence

        verified = verify_v12_evidence(evidence_dir)
    elif manifest.get("schema_version") == "market_regime_suspension_evidence_successor.v1":
        from scripts.verify_market_regime_suspension_evidence_successor import verify_successor

        verified = verify_successor(evidence_dir)
    else:
        from scripts.verify_market_regime_suspension_evidence import verify_evidence

        verified = verify_evidence(evidence_dir)
    entries = {
        (entry["symbol"], entry.get("missing_date", entry.get("date"))): entry
        for entry in manifest["entries"]
    }
    if len(entries) != manifest["stats"]["entry_count"]:
        raise ValueError("market-regime evidence entry identity mismatch")
    return verified["artifact_id"], _sha_file(manifest_path), entries


def _day_data(
    formal_root: Path,
    day: str,
    lifecycle: dict[str, tuple[str, str | None]],
    market_regime_evidence: dict[tuple[str, str], dict] | None = None,
) -> tuple[dict[str, dict], dict[str, Any]]:
    daily = _read_rows(Path(formal_root) / "daily" / f"trade_date={day}" / "part.parquet", ["ts_code", "trade_date", "pct_chg", "amount"])
    st = _read_rows(Path(formal_root) / "stock_st" / f"trade_date={day}" / "part.parquet", ["ts_code", "trade_date", "type"])
    suspend = _read_rows(Path(formal_root) / "suspend_d" / f"trade_date={day}" / "part.parquet", ["ts_code", "trade_date", "suspend_type"])
    if any(_day(row.get("trade_date")) != day for row in (*daily, *st, *suspend) if row.get("trade_date") is not None):
        raise ValueError(f"formal source date mismatch: {day}")
    st_codes = {row["ts_code"] for row in st if row.get("ts_code")}
    suspended_codes = {row["ts_code"] for row in suspend if row.get("ts_code")}
    active = {
        symbol for symbol, (listed, delisted) in lifecycle.items()
        if listed <= day and (delisted is None or day < delisted)
    }
    by_symbol: dict[str, dict] = {}
    gaps = []
    for row in daily:
        symbol = row.get("ts_code")
        if symbol in by_symbol:
            raise ValueError(f"duplicate daily row: {day}/{symbol}")
        by_symbol[symbol] = row
    eligible = sorted(active - st_codes)
    non_tradable = set()
    for symbol in eligible:
        resolution = resolve_market_regime_gap(
            symbol,
            day,
            by_symbol.get(symbol),
            (market_regime_evidence or {}).get((symbol, day)),
            [row for row in suspend if row.get("ts_code") == symbol],
        )
        if resolution["status"] == "non_tradable":
            non_tradable.add(symbol)
    eligible = sorted(set(eligible) - non_tradable)
    for symbol in eligible:
        row = by_symbol.get(symbol)
        if row is None or not _finite(row.get("pct_chg")) or not _finite(row.get("amount")) or float(row["amount"]) < 0:
            gaps.append({"date": day, "symbol": symbol, "reason": "daily pct_chg/amount missing or invalid"})
    return by_symbol, {
        "day": day,
        "active_count": len(active),
        "st_count": len(st_codes),
        "suspended_count": len(suspended_codes),
        "eligible_count": len(eligible),
        "eligible": eligible,
        "gaps": gaps,
    }


def _index_rows(source_dir: Path) -> dict[str, dict]:
    verify_market_regime_index_source(source_dir)
    return {row["trade_date"]: row for row in _normalize_index_rows(pq.read_table(Path(source_dir) / "index_daily_000300.parquet").to_pylist())}


def verify_market_regime_index_source(source_dir: Path) -> dict[str, Any]:
    manifest = json.loads((Path(source_dir) / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema_version") == "market_regime_index_source_successor.v1":
        from scripts.market_regime_index_source_successor import verify_successor

        return verify_successor(Path(source_dir))
    return verify_index_source(Path(source_dir))


def run_bounded_replay(
    config_path: Path = CONFIG_PATH,
    formal_root: Path = FORMAL_ROOT,
    index_source_dir: Path | None = None,
    market_regime_evidence_dir: Path | None = None,
) -> dict[str, Any]:
    config, semantic_hash = _load_config(Path(config_path))
    formal_root = Path(formal_root)
    if index_source_dir is None:
        raise ValueError("000300.SH index source artifact is required")
    index_source_dir = Path(index_source_dir)
    index_manifest = json.loads((index_source_dir / "manifest.json").read_text(encoding="utf-8"))
    index_verified = verify_market_regime_index_source(index_source_dir)
    calendar = _calendar_days(formal_root)
    lifecycle = _lifecycle(formal_root)
    windows = [{"id": window["id"], "start": _day(window["start"]), "end": _day(window["end"])} for window in config["stress_windows"]]
    normal = {"id": "normal", "start": _day(config["normal_window"]["start"]), "end": _day(config["normal_window"]["end"])}
    all_windows = windows + [normal]
    window_days = {window["id"]: _window_days(calendar, window["start"], window["end"]) for window in all_windows}
    daily_dates = set(day for days in window_days.values() for day in days)
    for day in sorted(daily_dates):
        daily_dates.update(_prior_days(calendar, day, 30))
    index_dates = set(day for days in window_days.values() for day in days)
    for day in sorted(index_dates):
        index_dates.update(_prior_days(calendar, day, 4))
    index = _index_rows(index_source_dir)
    missing_index = sorted(index_dates - set(index))
    if missing_index:
        raise ValueError(f"000300 source missing required dates: {missing_index[:5]}")
    evidence_identity = None
    evidence_entries = None
    if market_regime_evidence_dir is not None:
        evidence_identity = load_market_regime_evidence(Path(market_regime_evidence_dir))
        evidence_entries = evidence_identity[2]
    day_rows: dict[str, tuple[dict[str, dict], dict[str, Any]]] = {}
    source_inventory: list[dict[str, Any]] = []
    for day in sorted(daily_dates):
        day_rows[day] = _day_data(formal_root, day, lifecycle, evidence_entries)
        for interface in ("daily", "stock_st", "suspend_d"):
            path = formal_root / interface / f"trade_date={day}" / "part.parquet"
            source_inventory.append({"interface": interface, "path": _repo_path(path), "sha256": _sha_file(path)})
    for status in ("L", "D", "P"):
        path = formal_root / "stock_basic" / f"list_status={status}" / "part.parquet"
        source_inventory.append({"interface": "stock_basic", "path": _repo_path(path), "sha256": _sha_file(path)})
    cal_path = formal_root / "trade_cal" / "part.parquet"
    source_inventory.append({"interface": "trade_cal", "path": _repo_path(cal_path), "sha256": _sha_file(cal_path)})
    source_manifest = {
        "schema_version": "market_regime_source_manifest.v1",
        "config_path": _repo_path(Path(config_path)),
        "config_sha256": _sha_file(Path(config_path)),
        "config_semantic_hash": semantic_hash,
        "index_source": {
            "artifact_id": index_verified["artifact_id"],
            "manifest_path": _repo_path(index_source_dir / "manifest.json"),
            "manifest_sha256": _sha_file(index_source_dir / "manifest.json"),
        },
        "market_regime_evidence": {
            "artifact_id": evidence_identity[0],
            "manifest_path": _repo_path(Path(market_regime_evidence_dir) / "manifest.json"),
            "manifest_sha256": evidence_identity[1],
        } if evidence_identity else None,
        "formal_root": _repo_path(formal_root),
        "source_inventory": sorted(source_inventory, key=lambda entry: (entry["interface"], entry["path"])),
        "daily_dates": sorted(daily_dates),
        "index_dates": sorted(index_dates),
        "not_authorized_for_b3_b6_oos_gate_promotion_signal": True,
    }
    source_manifest["source_manifest_sha256"] = _sha_bytes(
        _canonical({key: value for key, value in source_manifest.items() if key != "source_manifest_sha256"})
    )

    daily_replay: dict[str, list[dict[str, Any]]] = {}
    for window in all_windows:
        records = []
        for day in window_days[window["id"]]:
            rows, meta = day_rows[day]
            eligible = meta["eligible"]
            breadth = sum(float(rows[symbol]["pct_chg"]) <= -5.0 for symbol in eligible) / len(eligible) if eligible else 0.0
            current_index = index[day]
            prior_index = index[_prior_days(calendar, day, 4)[0]]
            daily_return = float(current_index["close"]) / float(current_index["pre_close"]) - 1.0
            five_day_return = float(current_index["close"]) / float(prior_index["close"]) - 1.0
            prior_30 = _prior_days(calendar, day, 30)
            total_amount = sum(float(rows[symbol]["amount"]) for symbol in eligible)
            prior_amounts = [sum(float(day_rows[prior][0][symbol]["amount"]) for symbol in day_rows[prior][1]["eligible"]) for prior in prior_30]
            amount_ratio = total_amount / (sum(prior_amounts) / len(prior_amounts)) if prior_amounts and sum(prior_amounts) else None
            triggers = {
                "extreme_breadth_selloff": breadth > float(config["candidate_rules"]["extreme_breadth_selloff"]["threshold_gt"]),
                "structural_breakdown_1d": daily_return <= float(config["candidate_rules"]["structural_breakdown_1d"]["threshold_lte"]),
                "structural_breakdown_5d": five_day_return <= float(config["candidate_rules"]["structural_breakdown_5d"]["threshold_lte"]),
                "liquidity_exhaustion": amount_ratio is not None and amount_ratio < float(config["candidate_rules"]["liquidity_exhaustion"]["threshold_lt"]),
            }
            records.append({
                "trade_date": day,
                "eligible_count": meta["eligible_count"],
                "breadth_down_5pct_ratio": breadth,
                "index_daily_return": daily_return,
                "index_5d_compounded_return": five_day_return,
                "all_a_amount_vs_30d_mean": amount_ratio,
                "triggers": triggers,
                "block_new_entry": any(triggers.values()),
                "gap_count": len(meta["gaps"]),
            })
        daily_replay[window["id"]] = records
    normal_records = daily_replay["normal"]
    normal_block_count = sum(record["block_new_entry"] for record in normal_records)
    normal_ratio = normal_block_count / len(normal_records) if normal_records else 0.0
    zero_gap = all(record["gap_count"] == 0 for records in daily_replay.values() for record in records)
    stress_minimum = int(config.get("stress_window_block_day_min", 0))
    stress_windows_qualified = all(
        sum(record["block_new_entry"] for record in daily_replay[window["id"]]) >= stress_minimum
        for window in windows
    )
    result = {
        "schema_version": "market_regime_bounded_replay.v1",
        "status": "valid" if zero_gap and normal_ratio <= float(config["normal_window_block_ratio_max"]) and stress_windows_qualified else "not_qualified",
        "config_semantic_hash": semantic_hash,
        "source_manifest": source_manifest,
        "zero_gap": zero_gap,
        "zero_gap_gaps": [gap for day in sorted(day_rows) for gap in day_rows[day][1]["gaps"] if day in daily_dates],
        "windows": {
            window_id: {
                "start": records[0]["trade_date"],
                "end": records[-1]["trade_date"],
                "trading_day_count": len(records),
                "blocked_day_count": sum(record["block_new_entry"] for record in records),
                "normal_block_ratio": normal_ratio if window_id == "normal" else None,
                "rule_trigger_counts": {
                    rule: sum(record["triggers"][rule] for record in records) for rule in REQUIRED_RULES
                },
                "daily": records,
            }
            for window_id, records in daily_replay.items()
        },
        "stress_window_block_day_min": stress_minimum,
        "normal_window_block_ratio_max": float(config["normal_window_block_ratio_max"]),
        "not_authorized_for_b3_b6_oos_gate_promotion_signal": True,
    }
    result["validation_semantic_hash"] = _sha_bytes(_canonical({key: value for key, value in result.items() if key != "validation_semantic_hash"}))
    return result


def publish_bounded_qualification(result: dict[str, Any], output_root: Path = QUALIFICATION_ROOT) -> dict[str, Any]:
    if result.get("status") != "valid":
        if any(
            window_id != "normal" and window.get("blocked_day_count", 0) < int(result.get("stress_window_block_day_min", 0))
            for window_id, window in result.get("windows", {}).items()
        ):
            raise ValueError("market-regime stress-window minimum acceptance failed")
        raise ValueError("market-regime replay is not qualified")
    payload = {
        "schema_version": "market_regime_bounded_qualification.v1",
        "status": "validated_candidate",
        "config_semantic_hash": result["config_semantic_hash"],
        "source_manifest_sha256": result["source_manifest"]["source_manifest_sha256"],
        "validation_semantic_hash": result["validation_semantic_hash"],
        "zero_gap": result["zero_gap"],
        "windows": result["windows"],
        "stress_window_block_day_min": result["stress_window_block_day_min"],
        "normal_window_block_ratio_max": result["normal_window_block_ratio_max"],
        "not_authorized_for_b3_b6_oos_gate_promotion_signal": True,
    }
    artifact_id = _sha_bytes(_canonical(payload))[:16]
    target = Path(output_root) / artifact_id
    if target.exists():
        if not target.is_dir():
            raise ValueError(f"market-regime qualification write-once conflict: {target}")
        verified = verify_bounded_qualification(target)
        if verified["artifact_id"] != artifact_id:
            raise ValueError(f"market-regime qualification write-once conflict: {target}")
        return {"status": "already_published", "artifact_id": artifact_id, "path": str(target)}
    target.mkdir(parents=True, exist_ok=False)
    source_manifest_path = target / "source_manifest.json"
    report_path = target / "validation_report.json"
    manifest_path = target / "manifest.json"
    source_manifest_path.write_bytes(_canonical(result["source_manifest"]))
    report_path.write_bytes(_canonical(result))
    manifest = {**payload, "artifact_id": artifact_id, "source_manifest_path": source_manifest_path.name, "validation_report_path": report_path.name}
    manifest_path.write_bytes(_canonical(manifest))
    for path in (source_manifest_path, report_path, manifest_path):
        _write_sidecar(path)
    return {"status": "published", "artifact_id": artifact_id, "path": str(target)}


def verify_bounded_qualification(qualification_dir: Path) -> dict[str, Any]:
    qualification_dir = Path(qualification_dir)
    manifest_path = qualification_dir / "manifest.json"
    source_path = qualification_dir / "source_manifest.json"
    report_path = qualification_dir / "validation_report.json"
    for path in (manifest_path, source_path, report_path):
        if not path.exists():
            raise ValueError(f"market-regime qualification incomplete: {qualification_dir}")
        _sidecar(path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source = json.loads(source_path.read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if source.get("source_manifest_sha256") != _sha_bytes(_canonical({key: value for key, value in source.items() if key != "source_manifest_sha256"})):
        raise ValueError("market-regime source manifest hash mismatch")
    payload = {key: manifest[key] for key in (
        "schema_version", "status", "config_semantic_hash", "source_manifest_sha256", "validation_semantic_hash",
        "zero_gap", "windows", "stress_window_block_day_min", "normal_window_block_ratio_max",
        "not_authorized_for_b3_b6_oos_gate_promotion_signal",
    )}
    artifact_id = _sha_bytes(_canonical(payload))[:16]
    if manifest.get("artifact_id") != artifact_id:
        raise ValueError("market-regime qualification identity mismatch")
    if manifest.get("source_manifest_path") != source_path.name or manifest.get("validation_report_path") != report_path.name:
        raise ValueError("market-regime qualification path binding mismatch")
    if report.get("validation_semantic_hash") != manifest.get("validation_semantic_hash") or report.get("source_manifest", {}).get("source_manifest_sha256") != manifest.get("source_manifest_sha256"):
        raise ValueError("market-regime report binding mismatch")
    if report.get("status") != "valid" or manifest.get("status") != "validated_candidate":
        raise ValueError("market-regime qualification status mismatch")
    if not report.get("zero_gap"):
        raise ValueError("market-regime zero-gap validation failed")
    normal = report["windows"]["normal"]
    if normal["normal_block_ratio"] > float(report["normal_window_block_ratio_max"]):
        raise ValueError("market-regime normal-window ratio failed")
    stress_minimum = int(report.get("stress_window_block_day_min", 0))
    if any(
        window_id != "normal" and window.get("blocked_day_count", 0) < stress_minimum
        for window_id, window in report["windows"].items()
    ):
        raise ValueError("market-regime stress-window minimum acceptance failed")
    return {"status": "verified", "artifact_id": artifact_id, "path": str(qualification_dir)}


def _load_env_local() -> None:
    env_path = ROOT / ".env.local"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key, value)


def fetch_and_publish_index_source(output_root: Path = INDEX_SOURCE_ROOT) -> dict[str, Any]:
    """Make the two bounded provider calls required by the registered windows."""
    _load_env_local()
    from backend.app.tushare.config import TushareConfig
    from backend.app.tushare.tushare_client import TushareClient

    config = TushareConfig.from_env()
    config.retry_attempts = 1
    client = TushareClient(config)
    requests = [
        {"api": "index_daily", "ts_code": "000300.SH", "start_date": "20170828", "end_date": "20171130"},
        {"api": "index_daily", "ts_code": "000300.SH", "start_date": "20200303", "end_date": "20200323"},
    ]
    rows: list[dict[str, Any]] = []
    for request in requests:
        frame = client.query(
            "index_daily",
            fields="ts_code,trade_date,close,pre_close",
            ts_code=request["ts_code"],
            start_date=request["start_date"],
            end_date=request["end_date"],
        )
        rows.extend(frame.to_dict("records"))
    result = publish_index_source(rows, requests, output_root, datetime.now(timezone.utc).isoformat())
    result["api_call_count"] = len(requests)
    result["requests"] = requests
    result["row_count"] = len(_normalize_index_rows(rows))
    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--fetch-index-source", action="store_true")
    parser.add_argument("--index-source", type=Path)
    parser.add_argument("--market-regime-evidence", type=Path)
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    if args.fetch_index_source:
        print(json.dumps(fetch_and_publish_index_source(), sort_keys=True))
    else:
        source = args.index_source
        if source is None:
            raise SystemExit("--index-source is required for replay")
        result = run_bounded_replay(index_source_dir=source, market_regime_evidence_dir=args.market_regime_evidence)
        if args.publish:
            print(json.dumps(publish_bounded_qualification(result), sort_keys=True))
        else:
            print(json.dumps({"status": result["status"], "zero_gap": result["zero_gap"], "validation_semantic_hash": result["validation_semantic_hash"]}, sort_keys=True))
