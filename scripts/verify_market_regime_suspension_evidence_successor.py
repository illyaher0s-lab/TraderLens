"""Independent verifier for the 141-entry market-regime evidence successor."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pyarrow.parquet as pq

from scripts.verify_market_regime_suspension_evidence import verify_evidence as verify_predecessor
from scripts.publish_market_regime_suspension_evidence_successor import (
    DEFAULT_DIAGNOSTICS,
    DEFAULT_PREDECESSOR,
    DEFAULT_PROVIDER_PROBE,
    DIAGNOSTICS_SHA256,
    PREDECESSOR_ID,
    PREDECESSOR_SHA256,
    ROOT,
    AUTHORIZATION_SCOPE,
    canonical,
    sha_bytes,
    sha_file,
)


def _sidecar(path: Path) -> None:
    sidecar = path.with_name(path.name + ".sha256")
    if not sidecar.exists() or sidecar.read_text(encoding="utf-8").split()[0] != sha_file(path):
        raise ValueError(f"market-regime successor sidecar mismatch: {path}")


def _row_hash(row: dict) -> str:
    return sha_bytes(canonical({key: row.get(key) for key in ("ts_code", "trade_date", "suspend_type", "suspend_timing")}))


def _event_source(missing_source: dict, event: dict) -> dict:
    missing_path = ROOT / missing_source["repo_relative_path"]
    partition = missing_path.parent.parent / f"trade_date={event['trade_date']}" / "part.parquet"
    rows = pq.read_table(partition, columns=["ts_code", "trade_date", "suspend_type", "suspend_timing"]).to_pylist()
    selected = [row for row in rows if row.get("ts_code") == event["ts_code"] and str(row.get("trade_date")).replace("-", "")[:8] == event["trade_date"] and row.get("suspend_type") == event["suspend_type"]]
    if len(selected) != 1:
        raise ValueError(f"formal event source mismatch: {event}")
    row = {key: selected[0].get(key) for key in ("ts_code", "trade_date", "suspend_type", "suspend_timing")}
    if _row_hash(row) != event["canonical_sha256"]:
        raise ValueError(f"formal event row hash mismatch: {event}")
    return {"row": row, "partition": {"repo_relative_path": partition.relative_to(ROOT).as_posix(), "sha256": sha_file(partition)}}


def verify_successor(artifact_dir: Path, *, diagnostics_path: Path = DEFAULT_DIAGNOSTICS, predecessor_dir: Path = DEFAULT_PREDECESSOR) -> dict:
    artifact_dir = Path(artifact_dir); manifest_path = artifact_dir / "manifest.json"; _sidecar(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifact_id = manifest.get("artifact_id")
    payload = {key: value for key, value in manifest.items() if key != "artifact_id"}
    if not artifact_id or sha_bytes(canonical(payload))[:16] != artifact_id:
        raise ValueError("market-regime successor artifact ID mismatch")
    if manifest.get("schema_version") != "market_regime_suspension_evidence_successor.v1" or manifest.get("status") != "published" or manifest.get("frozen") is not True:
        raise ValueError("market-regime successor publication state mismatch")
    if manifest.get("authorization_scope") != AUTHORIZATION_SCOPE or manifest.get("not_authorized_for_b4_b6_oos_gate_promotion_signal") is not True:
        raise ValueError("market-regime successor authorization mismatch")
    if sha_file(diagnostics_path) != DIAGNOSTICS_SHA256:
        raise ValueError("market-regime successor diagnostics hash mismatch")
    pred_manifest = Path(predecessor_dir) / "manifest.json"
    if sha_file(pred_manifest) != PREDECESSOR_SHA256:
        raise ValueError("market-regime successor predecessor hash mismatch")
    pred_result = verify_predecessor(predecessor_dir, diagnostics_path=diagnostics_path, provider_probe_path=DEFAULT_PROVIDER_PROBE)
    if pred_result["artifact_id"] != PREDECESSOR_ID or pred_result["entry_count"] != 135:
        raise ValueError("market-regime successor predecessor verification mismatch")
    if manifest.get("lineage", {}).get("predecessor", {}).get("artifact_id") != PREDECESSOR_ID or manifest.get("lineage", {}).get("predecessor", {}).get("manifest_sha256") != PREDECESSOR_SHA256:
        raise ValueError("market-regime successor predecessor lineage mismatch")
    diagnostics = json.loads(Path(diagnostics_path).read_text(encoding="utf-8"))
    expected = {(g["symbol"], g["date"]): g for g in diagnostics["gaps"] if g["gap_kind"] == "daily_missing"}
    actual = {(entry["symbol"], entry["missing_date"]): entry for entry in manifest.get("entries", [])}
    pred_manifest_data = json.loads(pred_manifest.read_text(encoding="utf-8"))
    pred_entries = {(entry["symbol"], entry["missing_date"]): entry for entry in pred_manifest_data["entries"]}
    if len(expected) != 141 or set(actual) != set(expected) or len(pred_entries) != 135 or not set(pred_entries).issubset(set(expected)):
        raise ValueError("market-regime successor exact 141 entry set mismatch")
    formal_count = 0
    provider_count = 0
    for key, gap in expected.items():
        entry = actual[key]
        if key in pred_entries:
            expected_entry = {**pred_entries[key], "evidence_origin": "predecessor_provider_bounded"}
            if entry != expected_entry:
                raise ValueError(f"market-regime successor predecessor entry mismatch: {key}")
            provider_count += 1
            continue
        if gap["classification"] != "formal_suspend_evidence":
            raise ValueError(f"market-regime successor unauthorized entry origin: {key}")
        previous = gap["formal_interval"]["previous_S_or_P"]; later = gap["formal_interval"]["next_R"]
        if not previous or not later or previous["suspend_type"] not in ("S", "P") or later["suspend_type"] != "R" or not previous["trade_date"] <= key[1] < later["trade_date"]:
            raise ValueError(f"market-regime successor formal interval mismatch: {key}")
        source = gap["source_partitions"]
        for item in source.values():
            path = ROOT / item["repo_relative_path"]
            if not path.exists() or sha_file(path) != item["sha256"]:
                raise ValueError(f"market-regime successor gap source mismatch: {key}")
        expected_entry = {
            "symbol": key[0], "missing_date": key[1], "window_membership": gap["window_membership"], "registered_window_date": gap["registered_window_date"],
            "list_date": gap["lifecycle"]["list_date"], "delist_date": gap["lifecycle"]["delist_date"], "qualified": True,
            "evidence_kind": "formal_active_S_to_later_R_interval", "evidence_origin": "diagnostics_formal_interval", "formal_daily_absent": True,
            "formal_suspend_absent": True, "provider_daily_not_requested": True, "request": None, "provider_response_sha256": None,
            "previous_s": previous, "later_r": later, "boundary": {"kind": "formal_later_R", "date": later["trade_date"]},
            "formal_source_partitions": source, "formal_event_sources": {"previous_s": _event_source(source["suspend_d"], previous), "later_r": _event_source(source["suspend_d"], later)},
        }
        if entry != expected_entry:
            raise ValueError(f"market-regime successor formal entry mismatch: {key}")
        formal_count += 1
    stats = manifest.get("stats", {})
    if stats != {"entry_count": 141, "provider_bounded_count": 135, "formal_interval_count": 6, "data_fault_count": 0, "formal_daily_absent_count": 141, "formal_suspend_absent_count": 141} or provider_count != 135 or formal_count != 6:
        raise ValueError("market-regime successor arithmetic mismatch")
    return {"status": "verified", "artifact_id": artifact_id, "path": str(artifact_dir), "entry_count": 141, "provider_bounded_count": 135, "formal_interval_count": 6}


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("artifact_dir", type=Path); args = parser.parse_args()
    print(json.dumps(verify_successor(args.artifact_dir), sort_keys=True)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
