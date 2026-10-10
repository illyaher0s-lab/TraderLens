"""Publish the bounded v3 suspension evidence successor from local evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from scripts.qualify_v3_liquidity import ALGORITHM
from scripts.v3_liquidity_source_adapter import SOURCE_ADAPTER_CONTRACT, SOURCE_ADAPTER_CONTRACT_HASH, SOURCE_ADAPTER_ID


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DIAGNOSTICS = ROOT / "docs/verification/v3_historical_coverage_fault_diagnostics.json"
DEFAULT_PROVIDER_PROBE = ROOT / "docs/verification/v3_historical_liquidity_provider_probe.json"
DEFAULT_SCOPE_DIR = ROOT / "data/pit/historical_scope_freezes/acbc49159d989a46"
DEFAULT_OUTPUT_ROOT = ROOT / "data/pit/v3_historical_suspension_evidence"
TEMPLATE_ID = "relative_strength_rotation_shsz_sw2021_v3"
TEMPLATE_VERSION = "v3_shsz_sw2021_pit_12m_liquidity20d"
TEMPLATE_HASH = "f7c0fd8123f62f37118cb947e1735861374435f8707e01b06d788a8ec4df39c1"
DATA_REQUIREMENTS_HASH = "ef2ab5b1dafe4349f305b52733a7dcb018a2961464dfbc6542a10e34805d041d"
SCOPE_ID = "acbc49159d989a46"
SCOPE_MANIFEST_SHA256 = "cef48909b7b7bb05bc952a19ff8e50702540b427c58fd21eb1670afcaf675c67"
DIAGNOSTICS_SHA256 = "b0faed72f1af63c9c4f21268fed8c7526710fad02afa40ea32449b2ec085dfd3"
PROVIDER_PROBE_SHA256 = "da581bc3b8ebf2ca00a533dda3e3787b6c1c53ac010f5843b311f5144f044320"
CALENDAR_ID = "shsz_common_trade_calendar_v1"
CALENDAR_DATES_SHA256 = "62b6880c9acc381d273ceee40c900a486c3f83488600c042c43ce1d8f9cbb194"
CALENDAR_MANIFEST_SHA256 = "ae019cf45072d8274f915837a03d1824c02a69159df473512dbce2e925586785"
CUTOFF = "20260710"


def canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha_file(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sidecar(path: Path) -> None:
    sidecar = path.with_name(path.name + ".sha256")
    if not sidecar.exists() or sidecar.read_text(encoding="utf-8").split()[0] != sha_file(path):
        raise ValueError(f"source sidecar mismatch: {path}")


def _row_hash(row: dict, fields: list[str]) -> str:
    return sha_bytes(canonical({field: row.get(field) for field in fields}))


def _diagnostic_entries(diagnostics: dict) -> dict[tuple[str, str], dict]:
    entries: dict[tuple[str, str], dict] = {}
    for fault in diagnostics["faults"]:
        for missing in fault["missing_source_dates"]:
            if missing["classification"] != "D":
                continue
            key = (fault["symbol"], missing["missing_date"])
            entry = entries.setdefault(key, {"symbol": key[0], "missing_date": key[1], "execution_dates": set()})
            entry["execution_dates"].add(fault["execution_date"])
            source_identity = {"daily": missing["daily"], "suspend_d": missing["suspend_d"]}
            if "source" not in entry:
                entry["source"] = missing
            elif {"daily": entry["source"]["daily"], "suspend_d": entry["source"]["suspend_d"]} != source_identity:
                raise ValueError(f"diagnostics source conflict: {key}")
    return entries


def _validate_inputs(diagnostics_path: Path, provider_probe_path: Path, scope_dir: Path) -> tuple[dict, dict, dict]:
    if sha_file(diagnostics_path) != DIAGNOSTICS_SHA256:
        raise ValueError("diagnostics hash mismatch")
    if sha_file(provider_probe_path) != PROVIDER_PROBE_SHA256:
        raise ValueError("provider probe hash mismatch")
    scope_path = scope_dir / "manifest.json"
    _sidecar(scope_path)
    if sha_file(scope_path) != SCOPE_MANIFEST_SHA256:
        raise ValueError("scope manifest hash mismatch")
    diagnostics = _read(diagnostics_path)
    probe = _read(provider_probe_path)
    scope = _read(scope_path)
    if diagnostics.get("schema") != "v3_historical_coverage_diagnostics.v1":
        raise ValueError("diagnostics schema mismatch")
    if probe.get("schema") != "v3_historical_liquidity_provider_probe.v1" or probe.get("status") != "candidate_provider_probe":
        raise ValueError("provider probe schema/status mismatch")
    if probe.get("diagnostics", {}).get("sha256") != DIAGNOSTICS_SHA256:
        raise ValueError("provider probe diagnostics binding mismatch")
    if scope.get("artifact_id") != SCOPE_ID or scope.get("template", {}).get("template_hash") != TEMPLATE_HASH:
        raise ValueError("scope identity mismatch")
    if scope.get("calendar", {}).get("common_open_dates_sha256") != CALENDAR_DATES_SHA256:
        raise ValueError("scope calendar binding mismatch")
    template = diagnostics.get("identity", {}).get("template", {})
    if (template.get("template_id"), template.get("version"), template.get("template_hash"), template.get("data_requirements_hash")) != (TEMPLATE_ID, TEMPLATE_VERSION, TEMPLATE_HASH, DATA_REQUIREMENTS_HASH):
        raise ValueError("diagnostics v3 identity mismatch")
    return diagnostics, probe, scope


def _derive_entries(diagnostics: dict, probe: dict) -> tuple[list[dict], dict]:
    diagnostic_entries = _diagnostic_entries(diagnostics)
    provider_entries = {(row["symbol"], row["missing_date"]): row for row in probe["d_evidence"]}
    if set(diagnostic_entries) != set(provider_entries) or len(diagnostic_entries) != 58:
        raise ValueError("suspension evidence must bind exact 58 D entries")
    entries = []
    source_partitions: dict[str, dict] = {}
    for key in sorted(diagnostic_entries):
        diagnostic = diagnostic_entries[key]
        provider = provider_entries[key]
        source = diagnostic["source"]
        daily = source["daily"]
        suspend = source["suspend_d"]
        for item in (daily, suspend):
            path = ROOT / item["repo_relative_path"]
            if not path.exists() or sha_file(path) != item["sha256"]:
                raise ValueError(f"formal source hash mismatch: {item['repo_relative_path']}")
        if provider.get("provider_daily_row") is not None or provider.get("provider_daily_amount") is not None:
            raise ValueError(f"provider daily is not absent: {key}")
        same_day_s = [row for row in provider.get("same_day_events", []) if row.get("trade_date") == key[1] and row.get("suspend_type") in ("S", "P")]
        if same_day_s:
            evidence_kind = "exact_S_or_P"
        elif provider.get("interval_covered") is True and provider.get("previous_s") and provider.get("next_r"):
            evidence_kind = "active_S_to_later_R_interval"
        else:
            raise ValueError(f"provider evidence does not qualify missing source: {key}")
        for row in provider.get("same_day_events", []) + ([provider["previous_s"]] if provider.get("previous_s") else []) + ([provider["next_r"]] if provider.get("next_r") else []):
            fields = ["ts_code", "trade_date", "suspend_type", "suspend_timing"]
            if row.get("suspend_type") not in ("S", "R") or row.get("canonical_sha256") != _row_hash(row, fields):
                raise ValueError(f"provider row hash/type mismatch: {key}")
        source_partitions.setdefault(key[1], {
            "daily": {"repo_relative_path": daily["repo_relative_path"], "sha256": daily["sha256"]},
            "suspend_d": {"repo_relative_path": suspend["repo_relative_path"], "sha256": suspend["sha256"]},
        })
        entries.append({
            "symbol": key[0],
            "missing_date": key[1],
            "execution_dates": sorted(diagnostic["execution_dates"]),
            "qualified": True,
            "provider_daily_absent": True,
            "evidence_kind": evidence_kind,
            "exact_suspend_rows": same_day_s,
            "previous_s": provider.get("previous_s"),
            "later_r": provider.get("next_r"),
            "open_through_cutoff": provider.get("next_r") is None,
            "formal_source_partitions": {
                "daily": {"repo_relative_path": daily["repo_relative_path"], "sha256": daily["sha256"]},
                "suspend_d": {"repo_relative_path": suspend["repo_relative_path"], "sha256": suspend["sha256"]},
            },
        })
    stats = {
        "entry_count": len(entries),
        "unique_symbol_count": len({entry["symbol"] for entry in entries}),
        "provider_daily_absent_count": sum(entry["provider_daily_absent"] for entry in entries),
        "exact_same_day_s_or_p_count": sum(entry["evidence_kind"] == "exact_S_or_P" for entry in entries),
        "active_s_to_later_r_interval_count": sum(entry["evidence_kind"] == "active_S_to_later_R_interval" for entry in entries),
        "open_through_cutoff_count": sum(entry["open_through_cutoff"] for entry in entries),
        "data_fault_count": 0,
    }
    if stats["entry_count"] != 58 or stats["provider_daily_absent_count"] != 58:
        raise ValueError("suspension evidence arithmetic mismatch")
    return entries, {"stats": stats, "source_partitions": source_partitions}


def publish_evidence(*, diagnostics_path: Path = DEFAULT_DIAGNOSTICS, provider_probe_path: Path = DEFAULT_PROVIDER_PROBE, scope_dir: Path = DEFAULT_SCOPE_DIR, output_root: Path = DEFAULT_OUTPUT_ROOT) -> dict:
    diagnostics_path = Path(diagnostics_path); provider_probe_path = Path(provider_probe_path); scope_dir = Path(scope_dir); output_root = Path(output_root)
    diagnostics, probe, scope = _validate_inputs(diagnostics_path, provider_probe_path, scope_dir)
    entries, derived = _derive_entries(diagnostics, probe)
    diagnostics_repo_path = diagnostics_path.relative_to(ROOT).as_posix()
    probe_repo_path = provider_probe_path.relative_to(ROOT).as_posix()
    scope_repo_path = scope_dir.relative_to(ROOT).as_posix()
    payload = {
        "schema_version": "v3_historical_suspension_evidence.v1",
        "status": "published",
        "frozen": True,
        "authorization_scope": "acbc49159d989a46 historical_liquidity_coverage_only",
        "not_authorized_for_current_d_b3_b6_oos_gate_promotion_signal": True,
        "template": {"template_id": TEMPLATE_ID, "version": TEMPLATE_VERSION, "template_hash": TEMPLATE_HASH, "data_requirements_hash": DATA_REQUIREMENTS_HASH},
        "scope": {"artifact_id": SCOPE_ID, "manifest_sha256": SCOPE_MANIFEST_SHA256, "repo_relative_path": scope_repo_path},
        "calendar": {"artifact_id": CALENDAR_ID, "common_open_dates_sha256": CALENDAR_DATES_SHA256, "manifest_sha256": CALENDAR_MANIFEST_SHA256, "cutoff": CUTOFF},
        "lineage": {
            "diagnostics": {"repo_relative_path": diagnostics_repo_path, "sha256": DIAGNOSTICS_SHA256},
            "provider_probe": {"repo_relative_path": probe_repo_path, "sha256": PROVIDER_PROBE_SHA256},
        },
        "source_adapter": {"id": SOURCE_ADAPTER_ID, "contract": SOURCE_ADAPTER_CONTRACT, "contract_sha256": SOURCE_ADAPTER_CONTRACT_HASH},
        "liquidity_algorithm": {"algorithm_id": ALGORITHM["algorithm_id"], "algorithm_hash": sha_bytes(canonical(ALGORITHM))},
        "formal_source_partitions": derived["source_partitions"],
        "stats": derived["stats"],
        "entries": entries,
        "excluded_legacy_correctives": ["4d4159824570b6f0", "ef7ca72690d426b3"],
    }
    artifact_id = sha_bytes(canonical(payload))[:16]
    target = output_root / artifact_id
    raw = canonical({**payload, "artifact_id": artifact_id})
    if target.exists():
        if not (target / "manifest.json").exists() or (target / "manifest.json").read_bytes() != raw:
            raise ValueError("suspension evidence write-once conflict")
        return {"status": "already_published", "artifact_id": artifact_id, "path": str(target), "stats": derived["stats"]}
    target.mkdir(parents=True, exist_ok=False)
    (target / "manifest.json").write_bytes(raw)
    (target / "manifest.json.sha256").write_text(sha_bytes(raw) + "  manifest.json\n", encoding="utf-8")
    return {"status": "published", "artifact_id": artifact_id, "path": str(target), "stats": derived["stats"]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args()
    print(json.dumps(publish_evidence(output_root=args.output_root), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
