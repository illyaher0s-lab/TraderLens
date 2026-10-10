"""Publish and verify the exact v1.2 suspension-evidence successor."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from scripts.market_regime_bounded_replay import ROOT, _canonical, _day, _repo_path, _sha_bytes, _sha_file, _sidecar

DEFAULT_DIAGNOSTICS = ROOT / "docs/verification/market_regime_v12_daily_gap_diagnostics.json"
DEFAULT_PROVIDER_PROBE = ROOT / "docs/verification/market_regime_v11_provider_event_probes/111c4d5fcd8bd5a6"
DEFAULT_PREDECESSOR = ROOT / "data/pit/market_regime_suspension_evidence/bf378df5053744c0"
DEFAULT_FORMAL_ROOT = ROOT / "data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal"
DEFAULT_OUTPUT_ROOT = ROOT / "data/pit/market_regime_suspension_evidence"
DIAGNOSTICS_SHA256 = "1da7e99b1b811c8602b10e82eeb5bdfabc7f640e4b4c412d330a7771450f87f5"
PROVIDER_ID = "111c4d5fcd8bd5a6"
PROVIDER_SHA256 = "301c2dea1f91ba701fde1f5ac06c384aa28abc5bb94371e2a85f90caec56a896"
PREDECESSOR_ID = "bf378df5053744c0"
PREDECESSOR_SHA256 = "70b9e46d53346d2372369c3c5a66500710c3a634a86ddb3d3828ec998b5f4c32"
AUTHORIZATION_SCOPE = "market_regime_v1.2_bounded_windows_only"


def _row_hash(row: dict[str, Any]) -> str:
    return _sha_bytes(_canonical({key: row.get(key) for key in ("ts_code", "trade_date", "suspend_type", "suspend_timing")}))


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _load_inputs(
    diagnostics_path: Path,
    provider_probe_dir: Path,
    predecessor_dir: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    diagnostics_path = Path(diagnostics_path)
    if _sha_file(diagnostics_path) != DIAGNOSTICS_SHA256:
        raise ValueError("v1.2 evidence diagnostics hash mismatch")
    diagnostics = _load_json(diagnostics_path)
    if diagnostics.get("header", {}).get("config", {}).get("version") != "1.2" or diagnostics.get("scan_stats", {}).get("new_unresolved_count") != 82:
        raise ValueError("v1.2 evidence diagnostics identity mismatch")
    provider_manifest_path = Path(provider_probe_dir) / "manifest.json"
    _sidecar(provider_manifest_path)
    if _sha_file(provider_manifest_path) != PROVIDER_SHA256:
        raise ValueError("v1.2 evidence provider probe hash mismatch")
    provider = _load_json(provider_manifest_path)
    if provider.get("artifact_id") != PROVIDER_ID or provider.get("status") != "candidate_provider_probe":
        raise ValueError("v1.2 evidence provider probe identity mismatch")
    predecessor_manifest_path = Path(predecessor_dir) / "manifest.json"
    _sidecar(predecessor_manifest_path)
    if _sha_file(predecessor_manifest_path) != PREDECESSOR_SHA256:
        raise ValueError("v1.2 evidence predecessor hash mismatch")
    predecessor = _load_json(predecessor_manifest_path)
    if predecessor.get("artifact_id") != PREDECESSOR_ID or predecessor.get("stats", {}).get("entry_count") != 141:
        raise ValueError("v1.2 evidence predecessor identity mismatch")
    return diagnostics, provider, predecessor


def _provider_entries(diagnostics: dict[str, Any], provider: dict[str, Any]) -> list[dict[str, Any]]:
    gaps = diagnostics["gaps"]
    responses = {item["symbol"]: item for item in provider["responses"]}
    requests = {item["ts_code"]: item for item in provider["requests"]}
    entries = []
    for gap in gaps:
        symbol = gap["symbol"]
        response = responses.get(symbol)
        request = requests.get(symbol)
        if response is None or request is None:
            continue
        candidates = [row for row in response["rows"] if row.get("suspend_type") in ("S", "P") and _day(row.get("trade_date")) <= gap["date"]]
        if not candidates:
            continue
        previous = max(candidates, key=lambda row: _day(row["trade_date"]))
        if not (_day(request["start_date"]) <= _day(previous["trade_date"]) <= gap["date"] <= _day(request["end_date"])):
            raise ValueError(f"v1.2 provider interval coverage mismatch: {symbol}/{gap['date']}")
        delist = gap["lifecycle"]["delist_date"]
        if delist is None or not gap["date"] < delist or _day(request["end_date"]) < delist:
            raise ValueError(f"v1.2 provider lifecycle boundary mismatch: {symbol}/{gap['date']}")
        entries.append({
            **gap,
            "missing_date": gap["date"],
            "qualified": True,
            "evidence_kind": "bounded_open_until_lifecycle_delist",
            "evidence_origin": "verified_provider_event_stream_reuse",
            "previous_s": previous,
            "later_r": None,
            "boundary": {"kind": "lifecycle_delist_date", "date": delist},
            "provider_request": request,
            "provider_response_sha256": response["canonical_response_bytes_sha256"],
            "provider_rows": response["rows"],
            "provider_row_hashes": response["row_hashes"],
        })
    return entries


def _read_predecessor_event(
    reference: dict[str, Any],
    *,
    expected_symbol: str,
    expected_type: str,
    expected_canonical_sha256: str,
) -> dict[str, Any]:
    partition_ref = reference.get("partition", {})
    relative_path = partition_ref.get("repo_relative_path")
    expected_partition_sha256 = partition_ref.get("sha256")
    if not relative_path or not expected_partition_sha256:
        raise ValueError("v1.2 predecessor formal event reference is incomplete")
    partition = ROOT / relative_path
    if not partition.exists() or _sha_file(partition) != expected_partition_sha256:
        raise ValueError(f"v1.2 predecessor formal event partition hash mismatch: {relative_path}")
    rows = pq.read_table(
        partition,
        columns=["ts_code", "trade_date", "suspend_type", "suspend_timing"],
    ).to_pylist()
    expected_row = {
        key: reference.get("row", {}).get(key)
        for key in ("ts_code", "trade_date", "suspend_type", "suspend_timing")
    }
    matches = [
        raw for raw in rows
        if raw.get("ts_code") == expected_symbol
        and _day(raw.get("trade_date")) == _day(expected_row["trade_date"])
        and raw.get("suspend_type") == expected_type
    ]
    if len(matches) != 1:
        raise ValueError(f"v1.2 predecessor formal event row mismatch: {expected_symbol}/{expected_type}")
    row = {key: matches[0].get(key) for key in expected_row}
    if row != expected_row or _row_hash(row) != expected_canonical_sha256:
        raise ValueError(f"v1.2 predecessor formal event row hash mismatch: {expected_symbol}/{expected_type}")
    return {
        "row": row,
        "partition": {"repo_relative_path": _repo_path(partition), "sha256": _sha_file(partition)},
        "canonical_sha256": _row_hash(row),
    }


def _formal_entries(
    diagnostics: dict[str, Any],
    predecessor: dict[str, Any],
    formal_root: Path,
) -> list[dict[str, Any]]:
    formal_by_symbol = {
        entry["symbol"]: entry
        for entry in predecessor["entries"]
        if entry.get("evidence_kind") == "formal_active_S_to_later_R_interval"
    }
    entries = []
    for gap in diagnostics["gaps"]:
        predecessor_entry = formal_by_symbol.get(gap["symbol"])
        if predecessor_entry is None:
            continue
        sources = predecessor_entry.get("formal_event_sources", {})
        previous_event = _read_predecessor_event(
            sources.get("previous_s", {}),
            expected_symbol=gap["symbol"],
            expected_type="S",
            expected_canonical_sha256=predecessor_entry["previous_s"]["canonical_sha256"],
        )
        later_event = _read_predecessor_event(
            sources.get("later_r", {}),
            expected_symbol=gap["symbol"],
            expected_type="R",
            expected_canonical_sha256=predecessor_entry["later_r"]["canonical_sha256"],
        )
        if not _day(previous_event["row"]["trade_date"]) <= gap["date"] < _day(later_event["row"]["trade_date"]):
            raise ValueError(f"v1.2 formal interval boundary mismatch: {gap['symbol']}/{gap['date']}")
        entries.append({
            **gap,
            "missing_date": gap["date"],
            "qualified": True,
            "evidence_kind": "active_S_to_later_R_interval",
            "evidence_origin": "verified_formal_suspend_interval_reuse",
            "previous_s": previous_event["row"],
            "later_r": later_event["row"],
            "boundary": {"kind": "formal_later_R", "date": later_event["row"]["trade_date"]},
            "formal_event_sources": {"previous_s": previous_event, "later_r": later_event},
        })
    return entries


def _existing_entries(diagnostics: dict[str, Any], predecessor: dict[str, Any]) -> list[dict[str, Any]]:
    predecessor_by_key = {
        (entry["symbol"], entry.get("missing_date", entry.get("date"))): entry
        for entry in predecessor["entries"]
    }
    entries = []
    for gap in diagnostics.get("existing_evidence_gaps", []):
        key = (gap["symbol"], gap["date"])
        entry = predecessor_by_key.get(key)
        expected = gap.get("existing_exact_corrective_evidence", {}).get("entry")
        if entry is None or expected is None or entry != expected:
            raise ValueError(f"v1.2 existing evidence binding mismatch: {gap['symbol']}/{gap['date']}")
        entries.append({**entry, "date": gap["date"], "missing_date": gap["date"]})
    return entries


def _build_entries(
    diagnostics: dict[str, Any],
    provider: dict[str, Any],
    predecessor: dict[str, Any],
    formal_root: Path,
) -> list[dict[str, Any]]:
    all_gaps = diagnostics["gaps"] + diagnostics.get("existing_evidence_gaps", [])
    expected = {(gap["symbol"], gap["date"]) for gap in all_gaps}
    provider_entries = _provider_entries(diagnostics, provider)
    provider_keys = {(entry["symbol"], entry["date"]) for entry in provider_entries}
    remaining = {(gap["symbol"], gap["date"]) for gap in diagnostics["gaps"] if (gap["symbol"], gap["date"]) not in provider_keys}
    formal_candidates = _formal_entries(
        {"gaps": [gap for gap in diagnostics["gaps"] if (gap["symbol"], gap["date"]) in remaining]},
        predecessor,
        formal_root,
    )
    existing_entries = _existing_entries(diagnostics, predecessor)
    entries = sorted(provider_entries + formal_candidates + existing_entries, key=lambda entry: (entry["missing_date"], entry["symbol"]))
    if {(entry["symbol"], entry["missing_date"]) for entry in entries} != expected or len(entries) != 112:
        raise ValueError("v1.2 evidence exact entry set mismatch")
    return entries


def _write_sidecar(path: Path) -> None:
    path.with_name(path.name + ".sha256").write_text(f"{_sha_file(path)}  {path.name}\n", encoding="utf-8")


def publish_v12_evidence(
    *,
    diagnostics_path: Path = DEFAULT_DIAGNOSTICS,
    provider_probe_dir: Path = DEFAULT_PROVIDER_PROBE,
    predecessor_dir: Path = DEFAULT_PREDECESSOR,
    formal_root: Path = DEFAULT_FORMAL_ROOT,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
) -> dict[str, Any]:
    diagnostics, provider, predecessor = _load_inputs(diagnostics_path, provider_probe_dir, predecessor_dir)
    entries = _build_entries(diagnostics, provider, predecessor, Path(formal_root))
    provider_count = sum(entry["evidence_kind"] == "bounded_open_until_lifecycle_delist" for entry in entries)
    formal_count = sum(entry["evidence_kind"] == "active_S_to_later_R_interval" for entry in entries)
    stats = {"entry_count": len(entries), "provider_bounded_count": provider_count, "formal_interval_count": formal_count, "data_fault_count": 0}
    payload = {
        "schema_version": "market_regime_v12_suspension_evidence.v1",
        "status": "published",
        "frozen": True,
        "authorization_scope": AUTHORIZATION_SCOPE,
        "not_authorized_for_b4_b6_oos_gate_promotion_signal": True,
        "config": diagnostics["header"]["config"],
        "index_source": diagnostics["header"]["index_source"],
        "lineage": {
            "diagnostics": {"path": _repo_path(Path(diagnostics_path)), "sha256": DIAGNOSTICS_SHA256},
            "provider_probe": {"artifact_id": PROVIDER_ID, "path": _repo_path(Path(provider_probe_dir) / "manifest.json"), "manifest_sha256": PROVIDER_SHA256},
            "predecessor": {"artifact_id": PREDECESSOR_ID, "path": _repo_path(Path(predecessor_dir) / "manifest.json"), "manifest_sha256": PREDECESSOR_SHA256},
        },
        "semantics": {"daily_precedence": "valid daily row wins; evidence only resolves exact missing daily", "formal_interval": "S/P <= gap < later R", "provider_open": "prior S/P through lifecycle delist with bounded provider request coverage", "predecessor_formal_event_sources": "only explicitly referenced predecessor event partitions are reread"},
        "stats": stats,
        "entries": entries,
    }
    artifact_id = _sha_bytes(_canonical(payload))[:16]
    target = Path(output_root) / artifact_id
    manifest = {**payload, "artifact_id": artifact_id}
    if target.exists():
        manifest_path = target / "manifest.json"
        if not manifest_path.exists() or _load_json(manifest_path) != manifest:
            raise ValueError("v1.2 evidence write-once conflict")
        verify_v12_evidence(target)
        return {"status": "already_published", "artifact_id": artifact_id, "path": str(target), "stats": stats}
    target.mkdir(parents=True, exist_ok=False)
    manifest_path = target / "manifest.json"
    temp = target / "manifest.json.tmp"
    try:
        temp.write_bytes(_canonical(manifest))
        with open(temp, "rb+") as handle:
            handle.flush(); os.fsync(handle.fileno())
        os.replace(temp, manifest_path)
    finally:
        if temp.exists():
            temp.unlink()
    _write_sidecar(manifest_path)
    return {"status": "published", "artifact_id": artifact_id, "path": str(target), "stats": stats}


def verify_v12_evidence(
    artifact_dir: Path,
    *,
    diagnostics_path: Path = DEFAULT_DIAGNOSTICS,
    provider_probe_dir: Path = DEFAULT_PROVIDER_PROBE,
    predecessor_dir: Path = DEFAULT_PREDECESSOR,
    formal_root: Path = DEFAULT_FORMAL_ROOT,
) -> dict[str, Any]:
    artifact_dir = Path(artifact_dir)
    manifest_path = artifact_dir / "manifest.json"
    _sidecar(manifest_path)
    manifest = _load_json(manifest_path)
    artifact_id = manifest.get("artifact_id")
    payload = {key: value for key, value in manifest.items() if key != "artifact_id"}
    if manifest.get("schema_version") != "market_regime_v12_suspension_evidence.v1" or manifest.get("status") != "published" or manifest.get("frozen") is not True:
        raise ValueError("v1.2 evidence publication state mismatch")
    if _sha_bytes(_canonical(payload))[:16] != artifact_id:
        raise ValueError("v1.2 evidence artifact identity mismatch")
    diagnostics, provider, predecessor = _load_inputs(diagnostics_path, provider_probe_dir, predecessor_dir)
    expected_entries = _build_entries(diagnostics, provider, predecessor, Path(formal_root))
    if manifest.get("entries") != expected_entries:
        raise ValueError("v1.2 evidence entry/source binding mismatch")
    expected_stats = {
        "entry_count": len(expected_entries),
        "provider_bounded_count": sum(entry["evidence_kind"] == "bounded_open_until_lifecycle_delist" for entry in expected_entries),
        "formal_interval_count": sum(entry["evidence_kind"] == "active_S_to_later_R_interval" for entry in expected_entries),
        "data_fault_count": 0,
    }
    if manifest.get("stats") != expected_stats:
        raise ValueError("v1.2 evidence arithmetic mismatch")
    return {"status": "verified", "artifact_id": artifact_id, "path": str(artifact_dir), "entry_count": len(expected_entries), "stats": expected_stats}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--verify", type=Path)
    args = parser.parse_args()
    result = verify_v12_evidence(args.verify) if args.verify else publish_v12_evidence(output_root=args.output_root)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
