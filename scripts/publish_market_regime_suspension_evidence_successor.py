"""Publish the 141-entry market-regime evidence successor."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

import pyarrow.parquet as pq

from scripts.verify_market_regime_suspension_evidence import verify_evidence as verify_predecessor
from scripts.publish_market_regime_suspension_evidence import (
    DEFAULT_DIAGNOSTICS,
    DEFAULT_OUTPUT_ROOT,
    DEFAULT_PROVIDER_PROBE,
    DIAGNOSTICS_SHA256,
    ROOT,
    AUTHORIZATION_SCOPE,
    canonical,
    sha_bytes,
    sha_file,
)

PREDECESSOR_ID = "6a74758b672b90b7"
PREDECESSOR_SHA256 = "fc288a29236f351c05f52cdcea9764bf6000d63047d7357d6abe305cc7148cef"
DEFAULT_PREDECESSOR = ROOT / "data/pit/market_regime_suspension_evidence" / PREDECESSOR_ID


def _read(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _sidecar(path: Path) -> None:
    sidecar = path.with_name(path.name + ".sha256")
    if not sidecar.exists() or sidecar.read_text(encoding="utf-8").split()[0] != sha_file(path):
        raise ValueError(f"market-regime successor sidecar mismatch: {path}")


def _row_hash(row: dict) -> str:
    return sha_bytes(canonical({key: row.get(key) for key in ("ts_code", "trade_date", "suspend_type", "suspend_timing")}))


def _event_source(missing_source: dict, event: dict) -> dict:
    missing_path = ROOT / missing_source["repo_relative_path"]
    partition = missing_path.parent.parent / f"trade_date={event['trade_date']}" / "part.parquet"
    if not partition.exists():
        raise ValueError(f"formal event partition missing: {partition}")
    rows = pq.read_table(partition, columns=["ts_code", "trade_date", "suspend_type", "suspend_timing"]).to_pylist()
    selected = [row for row in rows if row.get("ts_code") == event["ts_code"] and str(row.get("trade_date")).replace("-", "")[:8] == event["trade_date"] and row.get("suspend_type") == event["suspend_type"]]
    if len(selected) != 1:
        raise ValueError(f"formal event row mismatch: {event}")
    row = {key: selected[0].get(key) for key in ("ts_code", "trade_date", "suspend_type", "suspend_timing")}
    if _row_hash(row) != event["canonical_sha256"]:
        raise ValueError(f"formal event row hash mismatch: {event}")
    return {"row": row, "partition": {"repo_relative_path": partition.relative_to(ROOT).as_posix(), "sha256": sha_file(partition)}}


def _load_inputs(diagnostics_path: Path, predecessor_dir: Path) -> tuple[dict, dict, dict, list[dict]]:
    if sha_file(diagnostics_path) != DIAGNOSTICS_SHA256:
        raise ValueError("market-regime successor diagnostics hash mismatch")
    predecessor_manifest = predecessor_dir / "manifest.json"
    if sha_file(predecessor_manifest) != PREDECESSOR_SHA256:
        raise ValueError("market-regime predecessor manifest hash mismatch")
    verified = verify_predecessor(predecessor_dir, diagnostics_path=diagnostics_path, provider_probe_path=DEFAULT_PROVIDER_PROBE)
    if verified["artifact_id"] != PREDECESSOR_ID or verified["entry_count"] != 135:
        raise ValueError("market-regime predecessor verification mismatch")
    diagnostics = _read(diagnostics_path)
    predecessor = _read(predecessor_manifest)
    formal = [entry for entry in diagnostics["gaps"] if entry["classification"] == "formal_suspend_evidence"]
    if len(formal) != 6 or len({(entry["symbol"], entry["date"]) for entry in formal}) != 6:
        raise ValueError("market-regime formal interval set mismatch")
    return diagnostics, predecessor, {"artifact_id": PREDECESSOR_ID, "manifest_sha256": PREDECESSOR_SHA256}, formal


def _formal_entries(diagnostics: dict, formal: list[dict]) -> list[dict]:
    entries = []
    for gap in sorted(formal, key=lambda item: (item["date"], item["symbol"])):
        previous = gap["formal_interval"]["previous_S_or_P"]
        later = gap["formal_interval"]["next_R"]
        if not previous or not later or previous["suspend_type"] not in ("S", "P") or later["suspend_type"] != "R" or not previous["trade_date"] <= gap["date"] < later["trade_date"]:
            raise ValueError(f"formal interval boundary mismatch: {gap['symbol']}/{gap['date']}")
        source = gap["source_partitions"]
        for item in source.values():
            path = ROOT / item["repo_relative_path"]
            if not path.exists() or sha_file(path) != item["sha256"]:
                raise ValueError(f"formal gap source hash mismatch: {gap['symbol']}/{gap['date']}")
        event_sources = {
            "previous_s": _event_source(source["suspend_d"], previous),
            "later_r": _event_source(source["suspend_d"], later),
        }
        entries.append({
            "symbol": gap["symbol"], "missing_date": gap["date"], "window_membership": gap["window_membership"],
            "registered_window_date": gap["registered_window_date"], "list_date": gap["lifecycle"]["list_date"],
            "delist_date": gap["lifecycle"]["delist_date"], "qualified": True,
            "evidence_kind": "formal_active_S_to_later_R_interval", "evidence_origin": "diagnostics_formal_interval",
            "formal_daily_absent": True, "formal_suspend_absent": True, "provider_daily_not_requested": True,
            "request": None, "provider_response_sha256": None, "previous_s": previous, "later_r": later,
            "boundary": {"kind": "formal_later_R", "date": later["trade_date"]},
            "formal_source_partitions": source, "formal_event_sources": event_sources,
        })
    return entries


def publish_successor(*, diagnostics_path: Path = DEFAULT_DIAGNOSTICS, predecessor_dir: Path = DEFAULT_PREDECESSOR, output_root: Path = DEFAULT_OUTPUT_ROOT) -> dict:
    diagnostics_path = Path(diagnostics_path); predecessor_dir = Path(predecessor_dir); output_root = Path(output_root)
    diagnostics, predecessor, predecessor_identity, formal = _load_inputs(diagnostics_path, predecessor_dir)
    formal_entries = _formal_entries(diagnostics, formal)
    provider_entries = [{**entry, "evidence_origin": "predecessor_provider_bounded"} for entry in predecessor["entries"]]
    entries = sorted(provider_entries + formal_entries, key=lambda item: (item["missing_date"], item["symbol"]))
    keys = {(entry["symbol"], entry["missing_date"]) for entry in entries}
    expected_keys = {(entry["symbol"], entry["date"]) for entry in diagnostics["gaps"] if entry["gap_kind"] == "daily_missing"}
    if len(entries) != 141 or keys != expected_keys:
        raise ValueError("market-regime successor exact 141 entry set mismatch")
    header = diagnostics["header"]
    stats = {"entry_count": 141, "provider_bounded_count": 135, "formal_interval_count": 6, "data_fault_count": 0, "formal_daily_absent_count": 141, "formal_suspend_absent_count": 141}
    payload = {
        "schema_version": "market_regime_suspension_evidence_successor.v1", "status": "published", "frozen": True,
        "authorization_scope": AUTHORIZATION_SCOPE, "not_authorized_for_b4_b6_oos_gate_promotion_signal": True,
        "scope": {"artifact_id": header["scope"]["artifact_id"], "manifest_sha256": header["scope"]["manifest_sha256"]},
        "config": {"path": header["config"]["path"], "sha256": header["config"]["sha256"], "semantic_hash": header["config"]["semantic_hash"]},
        "index_source": header["index_source"],
        "lineage": {"predecessor": {"artifact_id": predecessor_identity["artifact_id"], "path": (predecessor_dir.relative_to(ROOT)).as_posix(), "manifest_sha256": predecessor_identity["manifest_sha256"]}, "diagnostics": {"path": diagnostics_path.relative_to(ROOT).as_posix(), "sha256": DIAGNOSTICS_SHA256}},
        "semantics": {"provider_entries": "predecessor verified provider bounded open intervals", "formal_entries": "diagnostics verified previous S/P to later R, S<=gap<R", "daily_precedence": "valid daily row cannot be masked by evidence", "authorization": "market-regime-source-evidence-only"},
        "stats": stats, "entries": entries,
    }
    artifact_id = sha_bytes(canonical(payload))[:16]
    target = output_root / artifact_id
    raw = canonical({**payload, "artifact_id": artifact_id})
    if target.exists():
        manifest = target / "manifest.json"
        if not manifest.exists() or manifest.read_bytes() != raw:
            raise ValueError("market-regime successor write-once conflict")
        _sidecar(manifest)
        return {"status": "already_published", "artifact_id": artifact_id, "path": str(target), "stats": stats}
    target.mkdir(parents=True, exist_ok=False)
    manifest = target / "manifest.json"; temp = target / "manifest.json.tmp"
    try:
        with open(temp, "wb") as handle:
            handle.write(raw); handle.flush(); os.fsync(handle.fileno())
        os.replace(temp, manifest)
        (target / "manifest.json.sha256").write_text(f"{sha_file(manifest)}  manifest.json\n", encoding="utf-8")
    finally:
        if temp.exists(): temp.unlink()
    return {"status": "published", "artifact_id": artifact_id, "path": str(target), "stats": stats}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args()
    print(json.dumps(publish_successor(output_root=args.output_root), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
