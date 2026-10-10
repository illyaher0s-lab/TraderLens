"""Read-only v1.2 market-regime daily-gap diagnostic."""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.market_regime_bounded_replay import (
    CONFIG_PATH,
    FORMAL_ROOT,
    _calendar_days,
    _day,
    _load_config,
    _lifecycle,
    _prior_days,
    _read_rows,
    _repo_path,
    resolve_market_regime_gap,
    _sha_bytes,
    _sha_file,
    _window_days,
)
from scripts.market_regime_index_source_successor import verify_successor as verify_index_successor

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "docs/verification/market_regime_v12_daily_gap_diagnostics.json"
INDEX_SOURCE = ROOT / "data/pit/market_regime_index_sources/b1208520d9b0c0b0"
EVIDENCE_SOURCE = ROOT / "data/pit/market_regime_suspension_evidence/bf378df5053744c0"
EVIDENCE_MANIFEST_SHA256 = "70b9e46d53346d2372369c3c5a66500710c3a634a86ddb3d3828ec998b5f4c32"
V11_DIAGNOSTICS_SHA256 = "ed471314faf6005061c2709d674a350f158e355ba38056606fda24222bffcc87"


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sidecar(path: Path) -> None:
    sidecar = path.with_name(path.name + ".sha256")
    if not sidecar.exists() or sidecar.read_text(encoding="utf-8").split()[0] != _sha_file(path):
        raise ValueError(f"diagnostic source sidecar mismatch: {path}")


def _partition_metadata(formal_root: Path, day: str) -> dict[str, dict[str, str]]:
    metadata: dict[str, dict[str, str]] = {}
    for interface in ("daily", "stock_st", "suspend_d"):
        path = Path(formal_root) / interface / f"trade_date={day}" / "part.parquet"
        if not path.exists():
            raise ValueError(f"missing diagnostic partition: {path}")
        metadata[interface] = {"repo_relative_path": _repo_path(path), "sha256": _sha_file(path)}
    return metadata


def _classify_missing_gap(
    symbol: str,
    day: str,
    suspend_rows: list[dict[str, Any]],
    evidence: dict[str, Any] | None,
) -> str:
    try:
        resolution = resolve_market_regime_gap(symbol, day, None, evidence, suspend_rows)
    except ValueError:
        return "new_unresolved"
    if any(row.get("suspend_type") in ("S", "P") for row in suspend_rows):
        return "resolved_formal_suspension"
    if resolution["status"] == "non_tradable" and evidence is not None and evidence.get("qualified") is True:
        return "existing_qualified_evidence"
    return "new_unresolved"


def _validate_resolution_arithmetic(
    classified_gaps: list[dict[str, Any]],
    *,
    raw_missing_daily_count: int,
    resolution_counts: dict[str, int],
) -> None:
    keys = {(gap["symbol"], gap["date"]) for gap in classified_gaps}
    if len(keys) != len(classified_gaps):
        raise ValueError("v1.2 diagnostic duplicate gap identity")
    resolved_count = resolution_counts["resolved_formal_suspension"]
    if len(classified_gaps) + resolved_count != raw_missing_daily_count:
        raise ValueError("v1.2 diagnostic resolution arithmetic mismatch")
    if sum(resolution_counts.values()) != raw_missing_daily_count:
        raise ValueError("v1.2 diagnostic resolution count arithmetic mismatch")


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    raw = _canonical(payload)
    try:
        with open(temp, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def diagnose(
    *,
    config_path: Path = CONFIG_PATH,
    formal_root: Path = FORMAL_ROOT,
    index_source: Path = INDEX_SOURCE,
    evidence_source: Path = EVIDENCE_SOURCE,
    output_path: Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    config, semantic_hash = _load_config(Path(config_path))
    if config.get("version") != "1.2":
        raise ValueError("v1.2 diagnostics requires config version 1.2")
    index_verified = verify_index_successor(Path(index_source))
    evidence_manifest_path = Path(evidence_source) / "manifest.json"
    _sidecar(evidence_manifest_path)
    evidence_hash = _sha_file(evidence_manifest_path)
    if evidence_hash != EVIDENCE_MANIFEST_SHA256:
        raise ValueError("v1.2 diagnostic evidence successor hash mismatch")
    evidence_manifest = json.loads(evidence_manifest_path.read_text(encoding="utf-8"))
    evidence_id = evidence_manifest.get("artifact_id")
    if evidence_id != "bf378df5053744c0" or evidence_manifest.get("stats", {}).get("entry_count") != 141:
        raise ValueError("v1.2 diagnostic evidence successor identity mismatch")
    evidence_entries = {(entry["symbol"], entry["missing_date"]): entry for entry in evidence_manifest["entries"]}
    if _sha_file(ROOT / "docs/verification/market_regime_v11_daily_gap_diagnostics.json") != V11_DIAGNOSTICS_SHA256:
        raise ValueError("v1.1 diagnostic immutable binding mismatch")
    calendar = _calendar_days(Path(formal_root))
    lifecycle = _lifecycle(Path(formal_root))
    windows = [
        {"id": window["id"], "start": _day(window["start"]), "end": _day(window["end"])}
        for window in config["stress_windows"]
    ]
    windows.append({"id": "normal", "start": _day(config["normal_window"]["start"]), "end": _day(config["normal_window"]["end"])})
    window_days = {window["id"]: _window_days(calendar, window["start"], window["end"]) for window in windows}
    scan_dates = set()
    for days in window_days.values():
        scan_dates.update(days)
        for day in days:
            scan_dates.update(_prior_days(calendar, day, 30))
    gaps: list[dict[str, Any]] = []
    existing_evidence_gaps: list[dict[str, Any]] = []
    raw_missing_daily_count = 0
    resolution_counts = {
        "resolved_formal_suspension": 0,
        "existing_qualified_evidence": 0,
        "new_unresolved": 0,
    }
    source_inventory: list[dict[str, str]] = []
    for day in sorted(scan_dates):
        daily_path = Path(formal_root) / "daily" / f"trade_date={day}" / "part.parquet"
        st_path = Path(formal_root) / "stock_st" / f"trade_date={day}" / "part.parquet"
        suspend_path = Path(formal_root) / "suspend_d" / f"trade_date={day}" / "part.parquet"
        daily = _read_rows(daily_path, ["ts_code", "trade_date", "pct_chg", "amount"])
        st = _read_rows(st_path, ["ts_code", "trade_date", "type"])
        suspend = _read_rows(suspend_path, ["ts_code", "trade_date", "suspend_type", "suspend_timing"])
        partition_metadata = _partition_metadata(Path(formal_root), day)
        for interface, metadata in partition_metadata.items():
            source_inventory.append({"interface": interface, "path": metadata["repo_relative_path"], "sha256": metadata["sha256"]})
        daily_by_symbol = {row.get("ts_code"): row for row in daily if row.get("ts_code")}
        st_by_symbol = {row.get("ts_code"): row for row in st if row.get("ts_code")}
        suspend_by_symbol: dict[str, list[dict[str, Any]]] = {}
        for row in suspend:
            if row.get("ts_code"):
                suspend_by_symbol.setdefault(row["ts_code"], []).append(row)
        active = {symbol for symbol, (listed, delisted) in lifecycle.items() if listed <= day and (delisted is None or day < delisted)}
        eligible = sorted(active - set(st_by_symbol))
        window_membership = [window_id for window_id, days in window_days.items() if day in days]
        if not window_membership:
            window_membership = ["liquidity_warmup"]
        for symbol in eligible:
            if symbol in daily_by_symbol:
                continue
            raw_missing_daily_count += 1
            evidence = evidence_entries.get((symbol, day))
            same_day = suspend_by_symbol.get(symbol, [])
            classification = _classify_missing_gap(symbol, day, same_day, evidence)
            resolution_counts[classification] += 1
            list_date, delist_date = lifecycle[symbol]
            gap = {
                "symbol": symbol,
                "date": day,
                "gap_kind": "daily_missing",
                "classification": classification,
                "registered_window_date": day in {item for days in window_days.values() for item in days},
                "window_membership": window_membership,
                "lifecycle": {"active": True, "list_date": list_date, "delist_date": delist_date},
                "daily_row": None,
                "stock_st_row": st_by_symbol.get(symbol),
                "suspend_d_rows": same_day,
                "source_partitions": partition_metadata,
                "existing_exact_corrective_evidence": {"artifact_id": evidence_id, "manifest_sha256": evidence_hash, "entry": evidence} if evidence is not None else None,
            }
            if classification == "existing_qualified_evidence":
                existing_evidence_gaps.append(gap)
            elif classification == "new_unresolved":
                gaps.append(gap)
    classified_gaps = existing_evidence_gaps + gaps
    _validate_resolution_arithmetic(
        classified_gaps,
        raw_missing_daily_count=raw_missing_daily_count,
        resolution_counts=resolution_counts,
    )
    expected_existing = len(existing_evidence_gaps)
    header = {
        "schema_version": "market_regime_v12_daily_gap_diagnostics.v1",
        "status": "diagnostic_only",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config": {"path": _repo_path(Path(config_path)), "sha256": _sha_file(Path(config_path)), "semantic_hash": semantic_hash, "version": config["version"], "validation_status": config["validation_status"]},
        "formal_root": _repo_path(Path(formal_root)),
        "index_source": {"artifact_id": index_verified["artifact_id"], "manifest_path": _repo_path(Path(index_source) / "manifest.json"), "manifest_sha256": _sha_file(Path(index_source) / "manifest.json"), "rows": index_verified["row_count"]},
        "existing_evidence": {"artifact_id": evidence_id, "manifest_path": _repo_path(Path(evidence_source) / "manifest.json"), "manifest_sha256": evidence_hash, "v1_1_diagnostics_sha256": V11_DIAGNOSTICS_SHA256},
        "not_authorized_for_b4_b6_oos_gate_promotion_signal": True,
    }
    payload = {
        "header": header,
        "windows": windows,
        "window_date_counts": {window_id: len(days) for window_id, days in window_days.items()},
        "registered_execution_date_count": sum(len(days) for days in window_days.values()),
        "scan_date_count": len(scan_dates),
        "scan_date_min": min(scan_dates),
        "scan_date_max": max(scan_dates),
        "scan_scope_semantics": "registered v1.2 windows plus exact 30 prior common open-day liquidity warm-up dates",
        "classification_counts": resolution_counts,
        "resolution_counts": resolution_counts,
        "scan_stats": {
            "raw_missing_daily_count": raw_missing_daily_count,
            "resolved_formal_suspension_count": resolution_counts["resolved_formal_suspension"],
            "existing_exact_evidence_count": expected_existing,
            "new_unresolved_count": len(gaps),
            "eligible_daily_missing_count": len(gaps),
            "unique_symbols": len({gap["symbol"] for gap in gaps}),
            "unique_dates": len({gap["date"] for gap in gaps}),
        },
        "source_inventory": sorted(source_inventory, key=lambda entry: (entry["interface"], entry["path"])),
        "existing_evidence_gaps": sorted(existing_evidence_gaps, key=lambda gap: (gap["date"], gap["symbol"])),
        "gaps": sorted(gaps, key=lambda gap: (gap["date"], gap["symbol"])),
        "self_check": {"canonical_json": True, "source_hashes_checked": True, "exact_gap_identity_checked": True, "not_authorized": True},
    }
    _atomic_write(Path(output_path), payload)
    written = json.loads(Path(output_path).read_text(encoding="utf-8"))
    if (
        _canonical(written) != _canonical(payload)
        or len(written["gaps"]) != resolution_counts["new_unresolved"]
        or len(written["existing_evidence_gaps"]) != resolution_counts["existing_qualified_evidence"]
        or sum(written["resolution_counts"].values()) != written["scan_stats"]["raw_missing_daily_count"]
    ):
        raise ValueError("v1.2 diagnostic post-write self-check failed")
    for item in written["source_inventory"]:
        if _sha_file(ROOT / item["path"]) != item["sha256"]:
            raise ValueError(f"v1.2 diagnostic source hash self-check failed: {item['path']}")
    return {"status": "written", "path": str(output_path), "gap_count": len(gaps), "classification_counts": resolution_counts}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    print(json.dumps(diagnose(output_path=args.output), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
