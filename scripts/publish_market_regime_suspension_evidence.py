"""Publish bounded market-regime-only non-tradable evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIAGNOSTICS = ROOT / "docs/verification/market_regime_v11_daily_gap_diagnostics.json"
DEFAULT_PROVIDER_PROBE = ROOT / "docs/verification/market_regime_v11_provider_event_probes/111c4d5fcd8bd5a6/manifest.json"
DEFAULT_OUTPUT_ROOT = ROOT / "data/pit/market_regime_suspension_evidence"
DIAGNOSTICS_SHA256 = "ed471314faf6005061c2709d674a350f158e355ba38056606fda24222bffcc87"
PROVIDER_PROBE_ID = "111c4d5fcd8bd5a6"
PROVIDER_PROBE_SHA256 = "301c2dea1f91ba701fde1f5ac06c384aa28abc5bb94371e2a85f90caec56a896"
AUTHORIZATION_SCOPE = "market_regime_v1.1_bounded_windows_only"


def canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha_file(path: Path) -> str:
    return sha_bytes(Path(path).read_bytes())


def _read(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _sidecar(path: Path) -> None:
    sidecar = path.with_name(path.name + ".sha256")
    if not sidecar.exists() or sidecar.read_text(encoding="utf-8").split()[0] != sha_file(path):
        raise ValueError(f"market-regime evidence sidecar mismatch: {path}")


def _repo_path(path: Path) -> str:
    return Path(path).resolve().relative_to(ROOT.resolve()).as_posix()


def _gap_entries(diagnostics: dict) -> dict[tuple[str, str], dict]:
    gaps = [entry for entry in diagnostics["gaps"] if entry["classification"] == "no_suspend_evidence"]
    entries = {(entry["symbol"], entry["date"]): entry for entry in gaps}
    if len(gaps) != 135 or len(entries) != 135 or len({entry["symbol"] for entry in gaps}) != 7:
        raise ValueError("market-regime evidence requires the exact 135-gap set")
    return entries


def _load_inputs(diagnostics_path: Path, provider_probe_path: Path) -> tuple[dict, dict, dict[tuple[str, str], dict], dict[tuple[str, str], dict]]:
    if sha_file(diagnostics_path) != DIAGNOSTICS_SHA256:
        raise ValueError("market-regime diagnostics hash mismatch")
    _sidecar(provider_probe_path)
    if sha_file(provider_probe_path) != PROVIDER_PROBE_SHA256:
        raise ValueError("market-regime provider probe hash mismatch")
    diagnostics = _read(diagnostics_path)
    probe = _read(provider_probe_path)
    if diagnostics.get("header", {}).get("schema_version") != "market_regime_v11_daily_gap_diagnostics.v1":
        raise ValueError("market-regime diagnostics schema mismatch")
    if diagnostics.get("header", {}).get("not_authorized_for_b4_b6_oos_gate_promotion_signal") is not True:
        raise ValueError("market-regime diagnostics authorization disclosure missing")
    if probe.get("schema_version") != "market_regime_v11_provider_event_probe.v1" or probe.get("status") != "candidate_provider_probe":
        raise ValueError("market-regime provider probe schema/status mismatch")
    if probe.get("artifact_id") != PROVIDER_PROBE_ID or probe.get("diagnostics", {}).get("sha256") != DIAGNOSTICS_SHA256:
        raise ValueError("market-regime provider probe identity/diagnostics binding mismatch")
    gaps = _gap_entries(diagnostics)
    qualifications = {(item["symbol"], item["gap_date"]): item for item in probe.get("gap_qualifications", [])}
    if set(gaps) != set(qualifications) or len(qualifications) != 135:
        raise ValueError("market-regime provider qualification set mismatch")
    responses = {item["symbol"]: item for item in probe.get("responses", [])}
    if set(responses) != {key[0] for key in gaps} or len(responses) != 7:
        raise ValueError("market-regime provider response symbol set mismatch")
    return diagnostics, probe, gaps, qualifications


def _validate_response(response: dict) -> None:
    rows = response["rows"]
    if response["row_count"] != len(rows) or response["canonical_response_bytes_sha256"] != sha_bytes(canonical(rows)):
        raise ValueError(f"market-regime provider response hash mismatch: {response['symbol']}")
    if len(response["row_hashes"]) != len(rows) or response["row_hashes"] != [sha_bytes(canonical(row)) for row in rows]:
        raise ValueError(f"market-regime provider row hash mismatch: {response['symbol']}")
    request = response["request"]
    for row in rows:
        if row["ts_code"] != response["symbol"] or row["suspend_type"] not in ("S", "R", "P"):
            raise ValueError(f"market-regime provider event mismatch: {response['symbol']}")
        if not request["start_date"] <= row["trade_date"] <= request["end_date"]:
            raise ValueError(f"market-regime provider request coverage mismatch: {response['symbol']}")


def _derive_entries(diagnostics: dict, probe: dict, gaps: dict[tuple[str, str], dict], qualifications: dict[tuple[str, str], dict]) -> tuple[list[dict], dict]:
    responses = {item["symbol"]: item for item in probe["responses"]}
    entries = []
    for key in sorted(gaps):
        gap = gaps[key]
        q = qualifications[key]
        response = responses[key[0]]
        _validate_response(response)
        if gap["daily_row"] is not None or gap["suspend_d_rows"]:
            raise ValueError(f"market-regime formal source conflict: {key}")
        request = response["request"]
        delist = gap["lifecycle"]["delist_date"]
        rows = response["rows"]
        starts = [row for row in rows if row["trade_date"] <= key[1] and row["suspend_type"] in ("S", "P")]
        later_r = [row for row in rows if row["trade_date"] > key[1] and row["suspend_type"] == "R"]
        previous = starts[-1] if starts else None
        if previous is None or later_r or request["end_date"] != delist or not key[1] < delist:
            raise ValueError(f"market-regime open interval qualification mismatch: {key}")
        for source in gap["source_partitions"].values():
            path = ROOT / source["repo_relative_path"]
            if not path.exists() or sha_file(path) != source["sha256"]:
                raise ValueError(f"market-regime formal source hash mismatch: {key}")
        expected = {
            "symbol": key[0], "missing_date": key[1], "window_membership": gap["window_membership"],
            "registered_window_date": gap["registered_window_date"], "list_date": gap["lifecycle"]["list_date"],
            "delist_date": delist, "qualified": True, "evidence_kind": "bounded_open_until_lifecycle_delist",
            "formal_daily_absent": True, "formal_suspend_absent": True, "provider_daily_not_requested": True,
            "request": request, "provider_response_sha256": response["canonical_response_bytes_sha256"],
            "previous_s": previous, "later_r": None, "boundary": {"kind": "lifecycle_delist_date", "date": delist},
            "formal_source_partitions": gap["source_partitions"],
        }
        if q.get("qualified") is not True or q.get("evidence_kind") != expected["evidence_kind"]:
            raise ValueError(f"market-regime provider qualification mismatch: {key}")
        entries.append(expected)
    stats = {
        "entry_count": len(entries), "unique_symbol_count": len({entry["symbol"] for entry in entries}),
        "bounded_open_until_lifecycle_delist_count": len(entries), "data_fault_count": 0,
        "formal_daily_absent_count": sum(entry["formal_daily_absent"] for entry in entries),
        "formal_suspend_absent_count": sum(entry["formal_suspend_absent"] for entry in entries),
    }
    if stats["entry_count"] != 135 or stats["unique_symbol_count"] != 7:
        raise ValueError("market-regime evidence stats mismatch")
    return entries, stats


def publish_evidence(*, diagnostics_path: Path = DEFAULT_DIAGNOSTICS, provider_probe_path: Path = DEFAULT_PROVIDER_PROBE, output_root: Path = DEFAULT_OUTPUT_ROOT) -> dict:
    diagnostics_path = Path(diagnostics_path); provider_probe_path = Path(provider_probe_path); output_root = Path(output_root)
    diagnostics, probe, gaps, qualifications = _load_inputs(diagnostics_path, provider_probe_path)
    entries, stats = _derive_entries(diagnostics, probe, gaps, qualifications)
    header = diagnostics["header"]
    payload = {
        "schema_version": "market_regime_suspension_evidence.v1", "status": "published", "frozen": True,
        "authorization_scope": AUTHORIZATION_SCOPE,
        "not_authorized_for_b4_b6_oos_gate_promotion_signal": True,
        "scope": {"artifact_id": header["scope"]["artifact_id"], "manifest_sha256": header["scope"]["manifest_sha256"]},
        "config": {"path": header["config"]["path"], "sha256": header["config"]["sha256"], "semantic_hash": header["config"]["semantic_hash"]},
        "index_source": header["index_source"],
        "lineage": {
            "diagnostics": {"path": _repo_path(diagnostics_path), "sha256": DIAGNOSTICS_SHA256},
            "provider_probe": {"path": _repo_path(provider_probe_path), "artifact_id": PROVIDER_PROBE_ID, "sha256": PROVIDER_PROBE_SHA256},
        },
        "semantics": {
            "daily_precedence": "formal_daily_absent_required",
            "event_start_types": ["S", "P"], "event_end_type": "R",
            "open_interval_boundary": "formal_lifecycle_delist_date",
            "authorization": "market-regime-source-evidence-only",
        },
        "stats": stats, "entries": entries,
    }
    artifact_id = sha_bytes(canonical(payload))[:16]
    target = output_root / artifact_id
    raw = canonical({**payload, "artifact_id": artifact_id})
    if target.exists():
        manifest = target / "manifest.json"
        if not manifest.exists() or manifest.read_bytes() != raw:
            raise ValueError("market-regime evidence write-once conflict")
        _sidecar(manifest)
        return {"status": "already_published", "artifact_id": artifact_id, "path": str(target), "stats": stats}
    target.mkdir(parents=True, exist_ok=False)
    manifest = target / "manifest.json"
    temp = target / "manifest.json.tmp"
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
    print(json.dumps(publish_evidence(output_root=args.output_root), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
