"""Independent verifier for the v3 historical suspension evidence successor."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.publish_v3_historical_suspension_evidence import (
    CALENDAR_DATES_SHA256,
    CALENDAR_ID,
    CALENDAR_MANIFEST_SHA256,
    DATA_REQUIREMENTS_HASH,
    DIAGNOSTICS_SHA256,
    PROVIDER_PROBE_SHA256,
    ROOT,
    SCOPE_ID,
    SCOPE_MANIFEST_SHA256,
    TEMPLATE_HASH,
    TEMPLATE_ID,
    TEMPLATE_VERSION,
    canonical,
    sha_bytes,
    sha_file,
)
from scripts.v3_liquidity_source_adapter import SOURCE_ADAPTER_CONTRACT_HASH, SOURCE_ADAPTER_ID


def _sidecar(path: Path) -> None:
    sidecar = path.with_name(path.name + ".sha256")
    if not sidecar.exists() or sidecar.read_text(encoding="utf-8").split()[0] != sha_file(path):
        raise ValueError("suspension evidence sidecar mismatch")


def _diagnostic_keys(diagnostics: dict) -> dict[tuple[str, str], set[str]]:
    result: dict[tuple[str, str], set[str]] = {}
    for fault in diagnostics["faults"]:
        for missing in fault["missing_source_dates"]:
            if missing["classification"] == "D":
                result.setdefault((fault["symbol"], missing["missing_date"]), set()).add(fault["execution_date"])
    return result


def verify_evidence(artifact_dir: Path, *, diagnostics_path: Path, provider_probe_path: Path, scope_dir: Path) -> dict:
    artifact_dir = Path(artifact_dir); manifest_path = artifact_dir / "manifest.json"; _sidecar(manifest_path)
    raw = manifest_path.read_bytes(); manifest = json.loads(raw.decode("utf-8"))
    artifact_id = manifest.get("artifact_id")
    payload = {key: value for key, value in manifest.items() if key != "artifact_id"}
    if not artifact_id or sha_bytes(canonical(payload))[:16] != artifact_id:
        raise ValueError("suspension evidence artifact ID mismatch")
    if manifest.get("schema_version") != "v3_historical_suspension_evidence.v1" or manifest.get("status") != "published" or manifest.get("frozen") is not True:
        raise ValueError("suspension evidence publication state mismatch")
    if manifest.get("authorization_scope") != "acbc49159d989a46 historical_liquidity_coverage_only":
        raise ValueError("suspension evidence authorization scope mismatch")
    if manifest.get("not_authorized_for_current_d_b3_b6_oos_gate_promotion_signal") is not True:
        raise ValueError("suspension evidence downstream authorization disclosure missing")
    if manifest.get("template") != {"template_id": TEMPLATE_ID, "version": TEMPLATE_VERSION, "template_hash": TEMPLATE_HASH, "data_requirements_hash": DATA_REQUIREMENTS_HASH}:
        raise ValueError("suspension evidence template binding mismatch")
    if manifest.get("scope") != {"artifact_id": SCOPE_ID, "manifest_sha256": SCOPE_MANIFEST_SHA256, "repo_relative_path": Path(scope_dir).relative_to(ROOT).as_posix()}:
        raise ValueError("suspension evidence scope binding mismatch")
    if manifest.get("calendar") != {"artifact_id": CALENDAR_ID, "common_open_dates_sha256": CALENDAR_DATES_SHA256, "manifest_sha256": CALENDAR_MANIFEST_SHA256, "cutoff": "20260710"}:
        raise ValueError("suspension evidence calendar binding mismatch")
    if sha_file(diagnostics_path) != DIAGNOSTICS_SHA256:
        raise ValueError("diagnostics hash mismatch")
    if sha_file(provider_probe_path) != PROVIDER_PROBE_SHA256:
        raise ValueError("provider probe hash mismatch")
    if manifest.get("lineage", {}).get("diagnostics", {}).get("sha256") != DIAGNOSTICS_SHA256:
        raise ValueError("diagnostics lineage mismatch")
    if manifest.get("lineage", {}).get("provider_probe", {}).get("sha256") != PROVIDER_PROBE_SHA256:
        raise ValueError("provider probe lineage mismatch")
    if manifest.get("source_adapter", {}).get("id") != SOURCE_ADAPTER_ID or manifest.get("source_adapter", {}).get("contract_sha256") != SOURCE_ADAPTER_CONTRACT_HASH:
        raise ValueError("source adapter contract binding mismatch")
    diagnostics = json.loads(Path(diagnostics_path).read_text(encoding="utf-8"))
    probe = json.loads(Path(provider_probe_path).read_text(encoding="utf-8"))
    expected = _diagnostic_keys(diagnostics)
    provider = {(item["symbol"], item["missing_date"]): item for item in probe["d_evidence"]}
    entries = {(item["symbol"], item["missing_date"]): item for item in manifest.get("entries", [])}
    if len(expected) != 58 or set(expected) != set(provider) or set(expected) != set(entries):
        raise ValueError("suspension evidence exact entry set mismatch")
    for key, entry in entries.items():
        if entry["execution_dates"] != sorted(expected[key]) or entry["qualified"] is not True or entry["provider_daily_absent"] is not True:
            raise ValueError(f"execution binding mismatch: {key}")
        source = entry["formal_source_partitions"]
        for item in source.values():
            path = ROOT / item["repo_relative_path"]
            if not path.exists() or sha_file(path) != item["sha256"]:
                raise ValueError(f"formal source hash mismatch: {key}")
        observed = provider[key]
        same_day_s = [row for row in observed.get("same_day_events", []) if row.get("trade_date") == key[1] and row.get("suspend_type") in ("S", "P")]
        if entry["evidence_kind"] == "exact_S_or_P":
            if not same_day_s or entry["exact_suspend_rows"] != same_day_s:
                raise ValueError(f"exact suspension evidence mismatch: {key}")
        elif entry["evidence_kind"] == "active_S_to_later_R_interval":
            if not observed.get("interval_covered") or not observed.get("previous_s") or not observed.get("next_r"):
                raise ValueError(f"interval evidence mismatch: {key}")
        else:
            raise ValueError(f"unsupported evidence kind: {key}")
    stats = manifest.get("stats", {})
    if stats.get("entry_count") != 58 or stats.get("provider_daily_absent_count") != 58 or stats.get("data_fault_count") != 0:
        raise ValueError("suspension evidence stats mismatch")
    return {"status": "verified", "artifact_id": artifact_id, "entry_count": 58, "exact_same_day_s_count": stats.get("exact_same_day_s_or_p_count", 0), "active_interval_count": stats.get("active_s_to_later_r_interval_count", 0)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact_dir", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify_evidence(args.artifact_dir, diagnostics_path=ROOT / "docs/verification/v3_historical_coverage_fault_diagnostics.json", provider_probe_path=ROOT / "docs/verification/v3_historical_liquidity_provider_probe.json", scope_dir=ROOT / "data/pit/historical_scope_freezes/acbc49159d989a46"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
