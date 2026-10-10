"""Independent verifier for market-regime bounded non-tradable evidence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.publish_market_regime_suspension_evidence import (
    AUTHORIZATION_SCOPE,
    DEFAULT_DIAGNOSTICS,
    DEFAULT_PROVIDER_PROBE,
    DIAGNOSTICS_SHA256,
    PROVIDER_PROBE_ID,
    PROVIDER_PROBE_SHA256,
    ROOT,
    canonical,
    sha_bytes,
    sha_file,
)


def _sidecar(path: Path) -> None:
    sidecar = path.with_name(path.name + ".sha256")
    if not sidecar.exists() or sidecar.read_text(encoding="utf-8").split()[0] != sha_file(path):
        raise ValueError(f"market-regime evidence sidecar mismatch: {path}")


def _read(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def verify_evidence(artifact_dir: Path, *, diagnostics_path: Path = DEFAULT_DIAGNOSTICS, provider_probe_path: Path = DEFAULT_PROVIDER_PROBE) -> dict:
    artifact_dir = Path(artifact_dir)
    manifest_path = artifact_dir / "manifest.json"
    _sidecar(manifest_path)
    manifest = _read(manifest_path)
    artifact_id = manifest.get("artifact_id")
    payload = {key: value for key, value in manifest.items() if key != "artifact_id"}
    if not artifact_id or sha_bytes(canonical(payload))[:16] != artifact_id:
        raise ValueError("market-regime evidence artifact ID mismatch")
    if manifest.get("schema_version") != "market_regime_suspension_evidence.v1" or manifest.get("status") != "published" or manifest.get("frozen") is not True:
        raise ValueError("market-regime evidence publication state mismatch")
    if manifest.get("authorization_scope") != AUTHORIZATION_SCOPE or manifest.get("not_authorized_for_b4_b6_oos_gate_promotion_signal") is not True:
        raise ValueError("market-regime evidence authorization disclosure mismatch")
    if sha_file(diagnostics_path) != DIAGNOSTICS_SHA256 or sha_file(provider_probe_path) != PROVIDER_PROBE_SHA256:
        raise ValueError("market-regime evidence lineage input hash mismatch")
    diagnostics = _read(diagnostics_path)
    probe = _read(provider_probe_path)
    if manifest.get("lineage", {}).get("diagnostics", {}).get("sha256") != DIAGNOSTICS_SHA256:
        raise ValueError("market-regime diagnostics lineage mismatch")
    if manifest.get("lineage", {}).get("provider_probe", {}).get("artifact_id") != PROVIDER_PROBE_ID or manifest.get("lineage", {}).get("provider_probe", {}).get("sha256") != PROVIDER_PROBE_SHA256:
        raise ValueError("market-regime provider lineage mismatch")
    expected = {(g["symbol"], g["date"]): g for g in diagnostics["gaps"] if g["classification"] == "no_suspend_evidence"}
    provider = {(q["symbol"], q["gap_date"]): q for q in probe["gap_qualifications"]}
    responses = {response["symbol"]: response for response in probe["responses"]}
    actual = {(entry["symbol"], entry["missing_date"]): entry for entry in manifest.get("entries", [])}
    if len(expected) != 135 or set(expected) != set(provider) or set(expected) != set(actual):
        raise ValueError("market-regime evidence exact entry set mismatch")
    for key, gap in expected.items():
        entry = actual[key]
        q = provider[key]
        response = responses[key[0]]
        rows = response["rows"]
        if response["canonical_response_bytes_sha256"] != sha_bytes(canonical(rows)) or response["row_hashes"] != [sha_bytes(canonical(row)) for row in rows]:
            raise ValueError(f"market-regime provider response hash mismatch: {key}")
        if any(row["ts_code"] != key[0] or row["suspend_type"] not in ("S", "R", "P") for row in rows):
            raise ValueError(f"market-regime provider event type mismatch: {key}")
        request = response["request"]
        delist = gap["lifecycle"]["delist_date"]
        if request["end_date"] != delist or not request["start_date"] <= key[1] < delist:
            raise ValueError(f"market-regime request boundary mismatch: {key}")
        starts = [row for row in rows if row["trade_date"] <= key[1] and row["suspend_type"] in ("S", "P")]
        later_r = [row for row in rows if row["trade_date"] > key[1] and row["suspend_type"] == "R"]
        if not starts or later_r:
            raise ValueError(f"market-regime lifecycle interval not qualified: {key}")
        for source in gap["source_partitions"].values():
            path = ROOT / source["repo_relative_path"]
            if not path.exists() or sha_file(path) != source["sha256"]:
                raise ValueError(f"market-regime formal source hash mismatch: {key}")
        expected_fields = {
            "symbol": key[0], "missing_date": key[1], "window_membership": gap["window_membership"],
            "registered_window_date": gap["registered_window_date"], "list_date": gap["lifecycle"]["list_date"],
            "delist_date": delist, "qualified": True, "evidence_kind": "bounded_open_until_lifecycle_delist",
            "formal_daily_absent": True, "formal_suspend_absent": True, "provider_daily_not_requested": True,
            "request": request, "provider_response_sha256": response["canonical_response_bytes_sha256"],
            "previous_s": starts[-1], "later_r": None, "boundary": {"kind": "lifecycle_delist_date", "date": delist},
            "formal_source_partitions": gap["source_partitions"],
        }
        if entry != expected_fields or q.get("qualified") is not True:
            raise ValueError(f"market-regime evidence entry mismatch: {key}")
    stats = manifest.get("stats", {})
    if stats != {"entry_count": 135, "unique_symbol_count": 7, "bounded_open_until_lifecycle_delist_count": 135, "data_fault_count": 0, "formal_daily_absent_count": 135, "formal_suspend_absent_count": 135}:
        raise ValueError("market-regime evidence stats mismatch")
    return {"status": "verified", "artifact_id": artifact_id, "path": str(artifact_dir), "entry_count": 135, "bounded_open_until_lifecycle_delist_count": 135}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact_dir", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify_evidence(args.artifact_dir), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
