"""Lineage binding and metadata-only write-once bundle for v3 B5."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from backend.services.v3_b5_source_inventory import (
    ROOT,
    verify_source_inventory,
)
from backend.services.v3_b5_types import (
    RESULT_TYPES,
    canonical_json,
    sha256_bytes,
    validate_result_payload,
)


SCHEMA = "v3_b5_bundle.v1"
SOURCE_INVENTORY_ID = "2fe8321a5f644b9b"
SOURCE_INVENTORY_MANIFEST_SHA256 = "e23b94ac7294003a9b28db28f270bf2f19eaff40da9a03507adda87aad219a2c"
TEMPLATE = {
    "template_id": "relative_strength_rotation_shsz_sw2021_v3",
    "template_version": "v3_shsz_sw2021_pit_12m_liquidity20d",
    "template_hash": "f7c0fd8123f62f37118cb947e1735861374435f8707e01b06d788a8ec4df39c1",
    "data_requirements_hash": "ef2ab5b1dafe4349f305b52733a7dcb018a2961464dfbc6542a10e34805d041d",
}
REVISION_ID = "6440ffc03a742f4d4632078481cf3abf171eafb1a24f2bc69bc6f352d1b19ebc"
PROTOCOL_ID = "8770c56c5a69ef128442c0f593f9e4b081a6b13c69744b27171b27cc8c8b7bbe"
SUPPLEMENT_ID = "185a6b8f03915dca"
SUPPLEMENT_MANIFEST_SHA256 = "df51e7a9efae3b6e915d8cac8210b431e07f3992fe83fb183e499e512bc9c895"
FORMAL_SNAPSHOT_ID = "v3ds_d73256081de82e8a"
FORMAL_SNAPSHOT_MANIFEST_SHA256 = "57067e15e6ad1a92b23b42b48173b6cf1af2e7e23f3357320288fb7e109c2680"
FORMAL_SNAPSHOT_SEMANTIC_HASH = "d73256081de82e8a764ea2394d613af820fd1b82e773c48156ca2463a452c80e"
B4_ID = "cfa75e8b2a72bc76"
B4_MANIFEST_SHA256 = "b7db7cd296987ebd85ad199df16841a3a5d8a105892350e5a0bd091e4b5b6f89"
B4_EVENT_SHA256 = "8a8b5955ea6620c97e93914cdfdecd7006967bad0a297affb87a09af064d9a74"
MEMBERSHIP_ID = "pims_traderlens_v2_shsz_sw2021_pit_005"
MEMBERSHIP_MANIFEST_SHA256 = "32f58adbca49fb89dfeb54ceeb4ac9b27b6a26c55e0c9cfeae7a8fcaf3683f10"
MEMBERSHIP_RECORDS_SHA256 = "2e8c922de9f198ab18a6b38743a01f4343fbf52b876da84026389d3ffd11eec0"
CALENDAR_ID = "shsz_common_trade_calendar_v1"
CALENDAR_MANIFEST_SHA256 = "ae019cf45072d8274f915837a03d1824c02a69159df473512dbce2e925586785"
CALENDAR_DATE_SET_SHA256 = "62b6880c9acc381d273ceee40c900a486c3f83488600c042c43ce1d8f9cbb194"
SCOPE_ID = "acbc49159d989a46"
SCOPE_MANIFEST_SHA256 = "cef48909b7b7bb05bc952a19ff8e50702540b427c58fd21eb1670afcaf675c67"
GATE_ENVELOPE_HASH = "94da0dda30af75d663a7d28deb0a15d64a4e068586a1295f3b4f52203a8c4738"
IS_RANGE = {"start": "2025-06-27", "end": "2026-03-19"}
PAYLOAD_FILES = {
    "base_transaction_cost": "base_transaction_cost.json",
    "stress_transaction_cost": "stress_transaction_cost.json",
    "benchmark_comparison": "benchmark_comparison.json",
    "same_universe_control_comparison": "same_universe_control.json",
}
_COST_LINEAGE_EXTRAS = frozenset({"daily_observation_hash", "ledger_observation"})
_COMPARISON_LINEAGE_EXTRAS = frozenset(
    {
        "comparison_contract",
        "cost_artifact",
        "historical_coverage",
        "ledger_observation",
        "lifecycle_successor",
        "missing_mark_diagnostic",
    }
)


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _read(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _bound_manifest(repo_root: Path, relative: str, expected_id: str, id_field: str, expected_sha: str) -> dict:
    path = Path(repo_root) / relative / "manifest.json"
    sidecar = path.with_name(path.name + ".sha256")
    if not path.exists() or not sidecar.exists():
        raise ValueError(f"missing bound artifact: {relative}")
    actual_sha = _sha(path)
    if actual_sha != expected_sha or sidecar.read_text(encoding="utf-8").split()[0] != actual_sha:
        raise ValueError(f"bound artifact hash mismatch: {relative}")
    manifest = _read(path)
    if manifest.get(id_field) != expected_id:
        raise ValueError(f"bound artifact identity mismatch: {relative}")
    return manifest


def build_lineage(repo_root: Path = ROOT, *, source_inventory_dir: Path | None = None) -> dict[str, Any]:
    repo_root = Path(repo_root).resolve()
    source_inventory_dir = Path(source_inventory_dir) if source_inventory_dir is not None else repo_root / "data/pit/v3_b5_source_inventories" / SOURCE_INVENTORY_ID
    source_verified = verify_source_inventory(repo_root, source_inventory_dir)
    if source_verified.get("status") != "verified" or source_verified.get("artifact_id") != SOURCE_INVENTORY_ID or source_verified.get("manifest_sha256") != SOURCE_INVENTORY_MANIFEST_SHA256:
        raise ValueError("source_inventory is not the verified v3 B5 successor")

    supplement = _bound_manifest(repo_root, "data/pit/v3_execution_semantics_supplements/" + SUPPLEMENT_ID, SUPPLEMENT_ID, "supplement_id", SUPPLEMENT_MANIFEST_SHA256)
    snapshot = _bound_manifest(repo_root, "data/pit/v3_formal_data_snapshot_manifests/" + FORMAL_SNAPSHOT_ID, FORMAL_SNAPSHOT_ID, "snapshot_id", FORMAL_SNAPSHOT_MANIFEST_SHA256)
    _bound_manifest(repo_root, "data/pit/v3_b4_is_results/" + B4_ID, B4_ID, "artifact_id", B4_MANIFEST_SHA256)
    membership = _bound_manifest(repo_root, "data/pit/pit_membership_snapshots/" + MEMBERSHIP_ID, MEMBERSHIP_ID, "snapshot_id", MEMBERSHIP_MANIFEST_SHA256)
    membership_records = repo_root / "data/pit/pit_membership_snapshots" / MEMBERSHIP_ID / "records.parquet"
    if not membership_records.exists() or _sha(membership_records) != MEMBERSHIP_RECORDS_SHA256:
        raise ValueError("membership records hash mismatch")
    if membership.get("records_parquet_sha256") != MEMBERSHIP_RECORDS_SHA256:
        raise ValueError("membership manifest records binding mismatch")
    _bound_manifest(repo_root, "data/pit/shsz_common_trade_calendars/" + CALENDAR_ID, CALENDAR_ID, "artifact_id", CALENDAR_MANIFEST_SHA256)
    _bound_manifest(repo_root, "data/pit/historical_scope_freezes/" + SCOPE_ID, SCOPE_ID, "artifact_id", SCOPE_MANIFEST_SHA256)
    event_path = repo_root / "data/pit/v3_b4_is_results" / B4_ID / "event_result.json"
    event_sidecar = event_path.with_name(event_path.name + ".sha256")
    if not event_path.exists() or not event_sidecar.exists() or _sha(event_path) != B4_EVENT_SHA256 or event_sidecar.read_text(encoding="utf-8").split()[0] != B4_EVENT_SHA256:
        raise ValueError("B4 event result hash mismatch")

    return {
        "template": dict(TEMPLATE),
        "strategy_revision_id": REVISION_ID,
        "protocol_snapshot_id": PROTOCOL_ID,
        "execution_supplement": {"id": SUPPLEMENT_ID, "manifest_sha256": SUPPLEMENT_MANIFEST_SHA256},
        "formal_snapshot": {
            "id": FORMAL_SNAPSHOT_ID,
            "semantic_hash": snapshot.get("semantic_hash"),
            "manifest_sha256": FORMAL_SNAPSHOT_MANIFEST_SHA256,
        },
        "b4": {"artifact_id": B4_ID, "manifest_sha256": B4_MANIFEST_SHA256, "event_sha256": B4_EVENT_SHA256},
        "source_inventory": {"artifact_id": SOURCE_INVENTORY_ID, "manifest_sha256": SOURCE_INVENTORY_MANIFEST_SHA256},
        "membership": {"id": MEMBERSHIP_ID, "manifest_sha256": MEMBERSHIP_MANIFEST_SHA256, "records_sha256": MEMBERSHIP_RECORDS_SHA256},
        "calendar": {"id": CALENDAR_ID, "manifest_sha256": CALENDAR_MANIFEST_SHA256, "date_set_sha256": CALENDAR_DATE_SET_SHA256},
        "scope": {"id": SCOPE_ID, "manifest_sha256": SCOPE_MANIFEST_SHA256},
        "gate_criteria_envelope_hash": GATE_ENVELOPE_HASH,
        "is_range": dict(IS_RANGE),
    }


def _bundle_core(lineage: dict[str, Any], refs: dict[str, dict[str, str]]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA,
        "status": "verified",
        "authorization_scope": "v3_b5_contract_fixture_only",
        "not_authorized_for_b6_oos_gate_promotion_signal": True,
        "lineage": lineage,
        "results": refs,
    }


def _not_authorized(reasons: list[str]) -> dict[str, Any]:
    return {"status": "not_authorized", "not_authorized_for_b6_oos_gate_promotion_signal": True, "missing_or_invalid": sorted(set(reasons))}


def _expected_files(core: dict[str, Any], payloads: dict[str, dict[str, Any]]) -> dict[str, bytes]:
    bundle_id = sha256_bytes(canonical_json(core))[:16]
    manifest = {**core, "bundle_id": bundle_id}
    files = {"manifest.json": canonical_json(manifest)}
    for result_type, payload in payloads.items():
        files[PAYLOAD_FILES[result_type]] = canonical_json(payload)
    for name, raw in list(files.items()):
        files[name + ".sha256"] = f"{sha256_bytes(raw)}  {name}\n".encode("utf-8")
    return files


def _write_once(target: Path, files: dict[str, bytes]) -> str:
    if target.exists():
        if not target.is_dir() or {path.name for path in target.iterdir()} != set(files):
            raise ValueError("v3 B5 bundle write-once conflict")
        for name, expected in files.items():
            path = target / name
            if not path.is_file() or path.read_bytes() != expected:
                raise ValueError("v3 B5 bundle write-once conflict")
        return "already_published"
    output_root = target.parent
    output_root.mkdir(parents=True, exist_ok=True)
    staging_prefix = f".{target.name}.staging-"
    staging = Path(tempfile.mkdtemp(prefix=staging_prefix, dir=output_root))
    for name, raw in files.items():
        path = staging / name
        with tempfile.NamedTemporaryFile(dir=staging, prefix=name + ".", suffix=".tmp", delete=False) as handle:
            temp = Path(handle.name)
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    os.replace(staging, target)
    return "published"


def _validated_payloads(
    results: dict[str, dict[str, Any]], lineage: dict[str, Any]
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    payloads: dict[str, dict[str, Any]] = {}
    reasons: list[str] = []
    for result_type in RESULT_TYPES:
        if result_type not in results:
            reasons.append(result_type)
            continue
        try:
            payloads[result_type] = _validate_payload_for_bundle(results[result_type], result_type, lineage)
        except (TypeError, ValueError, KeyError) as error:
            reasons.extend((result_type, f"{result_type}: {error}"))
    return payloads, reasons


def _validate_payload_for_bundle(
    payload: dict[str, Any], result_type: str, lineage: dict[str, Any]
) -> dict[str, Any]:
    allowed_extras = (
        _COST_LINEAGE_EXTRAS
        if result_type in {"base_transaction_cost", "stress_transaction_cost"}
        else _COMPARISON_LINEAGE_EXTRAS
    )
    payload_lineage = payload.get("lineage")
    if not isinstance(payload_lineage, dict):
        raise ValueError("result lineage must be an object")
    if any(payload_lineage.get(key) != value for key, value in lineage.items()):
        raise ValueError("result lineage base binding mismatch")
    unexpected = set(payload_lineage) - set(lineage) - allowed_extras
    if unexpected:
        raise ValueError(f"unsupported result lineage fields: {sorted(unexpected)}")
    return validate_result_payload(payload, result_type, payload_lineage)


def publish_b5_bundle(
    repo_root: Path,
    results: dict[str, dict[str, Any]],
    output_root: Path,
    *,
    source_inventory_dir: Path | None = None,
) -> dict[str, Any]:
    try:
        lineage = build_lineage(repo_root, source_inventory_dir=source_inventory_dir)
    except (OSError, TypeError, ValueError, KeyError) as error:
        return _not_authorized([f"source_inventory: {error}"])
    payloads, reasons = _validated_payloads(results, lineage)
    if reasons:
        return _not_authorized(reasons)
    refs = {
        result_type: {
            "payload_id": payload["payload_id"],
            "canonical_payload_sha256": payload["canonical_payload_sha256"],
            "path": PAYLOAD_FILES[result_type],
        }
        for result_type, payload in payloads.items()
    }
    core = _bundle_core(lineage, refs)
    bundle_id = sha256_bytes(canonical_json(core))[:16]
    files = _expected_files(core, payloads)
    status = _write_once(Path(output_root) / bundle_id, files)
    return {"status": status, "bundle_id": bundle_id, "path": str(Path(output_root) / bundle_id), "not_authorized_for_b6_oos_gate_promotion_signal": True}


def verify_b5_bundle(
    repo_root: Path,
    bundle_dir: Path,
    *,
    source_inventory_dir: Path | None = None,
) -> dict[str, Any]:
    try:
        bundle_dir = Path(bundle_dir)
        expected_names = {
            "manifest.json",
            "manifest.json.sha256",
            *PAYLOAD_FILES.values(),
            *(f"{name}.sha256" for name in PAYLOAD_FILES.values()),
        }
        if not bundle_dir.is_dir() or {path.name for path in bundle_dir.iterdir()} != expected_names:
            return {"status": "invalid", "reason": "bundle file set mismatch"}
        manifest_path = bundle_dir / "manifest.json"
        sidecar_path = bundle_dir / "manifest.json.sha256"
        if not manifest_path.exists() or not sidecar_path.exists():
            return {"status": "invalid", "reason": "bundle manifest or sidecar missing"}
        actual_manifest_sha = _sha(manifest_path)
        expected_manifest_sidecar = f"{actual_manifest_sha}  manifest.json\n".encode("utf-8")
        if sidecar_path.read_bytes() != expected_manifest_sidecar:
            return {"status": "invalid", "reason": "bundle manifest sidecar mismatch"}
        manifest = _read(manifest_path)
        if manifest.get("schema_version") != SCHEMA or manifest.get("status") != "verified":
            return {"status": "invalid", "reason": "bundle schema or status mismatch"}
        lineage = build_lineage(repo_root, source_inventory_dir=source_inventory_dir)
        if manifest.get("lineage") != lineage:
            return {"status": "invalid", "reason": "bundle lineage mismatch"}
        refs = manifest.get("results")
        if not isinstance(refs, dict) or set(refs) != set(RESULT_TYPES):
            return {"status": "invalid", "reason": "bundle result references mismatch"}
        payloads: dict[str, dict[str, Any]] = {}
        for result_type in RESULT_TYPES:
            ref = refs[result_type]
            if not ref or ref.get("path") != PAYLOAD_FILES[result_type]:
                return {"status": "invalid", "reason": f"missing result reference: {result_type}"}
            path = bundle_dir / ref["path"]
            sidecar = path.with_name(path.name + ".sha256")
            if not path.exists() or not sidecar.exists():
                return {"status": "invalid", "reason": f"missing result file: {result_type}"}
            raw = path.read_bytes()
            actual = sha256_bytes(raw)
            expected_sidecar = f"{actual}  {path.name}\n".encode("utf-8")
            if sidecar.read_bytes() != expected_sidecar:
                return {"status": "invalid", "reason": f"result sidecar mismatch: {result_type}"}
            payload = json.loads(raw.decode("utf-8"))
            payloads[result_type] = _validate_payload_for_bundle(payload, result_type, lineage)
            if ref.get("payload_id") != payload["payload_id"] or ref.get("canonical_payload_sha256") != payload["canonical_payload_sha256"]:
                return {"status": "invalid", "reason": f"result reference mismatch: {result_type}"}
        core = _bundle_core(lineage, refs)
        expected_id = sha256_bytes(canonical_json(core))[:16]
        expected_manifest = {**core, "bundle_id": expected_id}
        if manifest != expected_manifest or bundle_dir.name != expected_id:
            return {"status": "invalid", "reason": "bundle identity mismatch"}
        return {
            "status": "verified",
            "bundle_id": expected_id,
            "manifest_sha256": actual_manifest_sha,
            "result_count": len(payloads),
            "not_authorized_for_b6_oos_gate_promotion_signal": True,
        }
    except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError) as error:
        return {"status": "invalid", "reason": str(error)}
