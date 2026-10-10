"""Publish the metadata-only formal v3 data snapshot."""
from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

from backend.services.b3_protocol_types import DataSnapshotManifest
from scripts.publish_v3_historical_scope import verify_scope
from scripts.verify_v3_historical_coverage import verify_coverage
from scripts.verify_v3_historical_suspension_evidence import verify_evidence


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = {
    "template_id": "relative_strength_rotation_shsz_sw2021_v3",
    "template_version": "v3_shsz_sw2021_pit_12m_liquidity20d",
    "template_hash": "f7c0fd8123f62f37118cb947e1735861374435f8707e01b06d788a8ec4df39c1",
    "data_requirements_hash": "ef2ab5b1dafe4349f305b52733a7dcb018a2961464dfbc6542a10e34805d041d",
}
SCOPE_DIR = ROOT / "data/pit/historical_scope_freezes/acbc49159d989a46"
COVERAGE_DIR = ROOT / "data/pit/v3_historical_coverage_packages/1e79d26460c0c109"
EVIDENCE_DIR = ROOT / "data/pit/v3_historical_suspension_evidence/4871f6ba56b40e93"
B3_MANIFEST = ROOT / "data/pit/b3_execution_input_packages/05f38a2884dc7e47/manifest.json"
LIFECYCLE_MANIFEST = ROOT / "data/pit/qualification_successors/49b09326f35936c6/manifest.json"
MEMBERSHIP_DIR = ROOT / "data/pit/pit_membership_snapshots/pims_traderlens_v2_shsz_sw2021_pit_005"
DEFAULT_OUTPUT_ROOT = ROOT / "data/pit/v3_formal_data_snapshot_manifests"
DIAGNOSTICS = ROOT / "docs/verification/v3_historical_coverage_fault_diagnostics.json"
PROVIDER_PROBE = ROOT / "docs/verification/v3_historical_liquidity_provider_probe.json"


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha(path: Path) -> str:
    return _sha_bytes(path.read_bytes())


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sidecar_hash(path: Path) -> str:
    sidecar = path.with_name(path.name + ".sha256")
    if not sidecar.exists():
        raise ValueError(f"sidecar missing: {sidecar}")
    value = sidecar.read_text(encoding="utf-8").split()[0]
    actual = _sha(path)
    if value != actual:
        raise ValueError(f"sidecar mismatch: {path}")
    return actual


def _manifest_binding(path: Path, *, artifact_id: str | None = None) -> tuple[dict, str]:
    manifest = _read(path)
    manifest_hash = _sidecar_hash(path)
    observed_id = manifest.get("artifact_id", manifest.get("successor_id", manifest.get("snapshot_id")))
    if artifact_id is not None and observed_id != artifact_id:
        raise ValueError(f"artifact identity mismatch: {path}")
    return manifest, manifest_hash


def _load_inputs(
    *,
    coverage_dir: Path,
    scope_dir: Path,
    evidence_dir: Path,
    b3_manifest_path: Path,
    lifecycle_manifest_path: Path,
    membership_dir: Path,
) -> dict:
    scope_dir = Path(scope_dir).resolve()
    coverage_dir = Path(coverage_dir).resolve()
    evidence_dir = Path(evidence_dir).resolve()
    b3_manifest_path = Path(b3_manifest_path).resolve()
    lifecycle_manifest_path = Path(lifecycle_manifest_path).resolve()
    membership_dir = Path(membership_dir).resolve()

    coverage_candidate = _read(coverage_dir / "manifest.json")
    if coverage_candidate.get("coverage", {}).get("data_fault_count") != 0:
        raise ValueError("v3 formal snapshot rejects data_fault")
    scope = verify_scope(scope_dir)
    scope_manifest_path = scope_dir / "manifest.json"
    scope_hash = _sidecar_hash(scope_manifest_path)
    coverage_result = verify_coverage(coverage_dir, scope_dir=scope_dir)
    coverage_path = coverage_dir / "manifest.json"
    coverage = _read(coverage_path)
    coverage_hash = _sidecar_hash(coverage_path)
    evidence_result = verify_evidence(
        evidence_dir,
        diagnostics_path=DIAGNOSTICS,
        provider_probe_path=PROVIDER_PROBE,
        scope_dir=scope_dir,
    )
    evidence_path = evidence_dir / "manifest.json"
    evidence = _read(evidence_path)
    evidence_hash = _sidecar_hash(evidence_path)
    if coverage_result.get("status") != "valid" or evidence_result.get("status") != "verified":
        raise ValueError("bound coverage/evidence verifier did not pass")
    if coverage.get("template") != TEMPLATE:
        raise ValueError("v3 template identity mismatch")
    if coverage.get("coverage", {}).get("data_fault_count") != 0:
        raise ValueError("v3 formal snapshot rejects data_fault")
    if coverage.get("scope_freeze", {}).get("artifact_id") != "acbc49159d989a46":
        raise ValueError("scope identity mismatch")
    if evidence.get("artifact_id") != "4871f6ba56b40e93":
        raise ValueError("suspension evidence identity mismatch")

    b3, b3_hash = _manifest_binding(b3_manifest_path, artifact_id="05f38a2884dc7e47")
    if b3.get("template") != {
        "template_id": TEMPLATE["template_id"],
        "template_version": TEMPLATE["template_version"],
        "template_hash": TEMPLATE["template_hash"],
        "data_requirements_hash": TEMPLATE["data_requirements_hash"],
    }:
        raise ValueError("B3 template identity mismatch")
    lifecycle, lifecycle_hash = _manifest_binding(lifecycle_manifest_path, artifact_id="49b09326f35936c6")
    membership_path = membership_dir / "manifest.json"
    membership, membership_hash = _manifest_binding(membership_path, artifact_id="pims_traderlens_v2_shsz_sw2021_pit_005")
    membership_records_hash = _sidecar_hash(membership_dir / "records.parquet")
    if membership.get("records_parquet_sha256") != membership_records_hash:
        raise ValueError("membership records hash mismatch")

    lineage = coverage["lineage"]
    if lineage["b3_execution_input_successor"]["manifest_sha256"] != b3_hash:
        raise ValueError("coverage/B3 manifest binding mismatch")
    if lineage["lifecycle_successor"]["manifest_sha256"] != lifecycle_hash:
        raise ValueError("coverage/lifecycle manifest binding mismatch")
    if lineage["membership_snapshot"]["manifest_sha256"] != membership_hash:
        raise ValueError("coverage/membership manifest binding mismatch")
    if lineage["suspension_evidence"]["manifest_sha256"] != evidence_hash:
        raise ValueError("coverage/suspension evidence binding mismatch")

    files = {}
    for key, filename in {
        "coverage_by_code": "coverage_by_code.parquet",
        "coverage_by_date": "coverage_by_date.parquet",
        "unavailable": "unavailable_security_dates.parquet",
    }.items():
        path = coverage_dir / filename
        actual = _sha(path)
        if actual != coverage["files"][key]["sha256"]:
            raise ValueError(f"coverage file hash mismatch: {filename}")
        files[key] = {"path": filename, **coverage["files"][key]}

    source_inventory = {
        key: {
            "content_hash": value["content_hash"],
            "entry_count": value["entry_count"],
        }
        for key, value in coverage["sources"].items()
        if key in ("daily", "adj_factor", "suspend_d")
    }
    source_inventory["formal_input_root"] = coverage["sources"]["formal_input_root"]
    return {
        "scope": scope,
        "scope_hash": scope_hash,
        "coverage": coverage,
        "coverage_hash": coverage_hash,
        "evidence": evidence,
        "evidence_hash": evidence_hash,
        "b3": b3,
        "b3_hash": b3_hash,
        "lifecycle": lifecycle,
        "lifecycle_hash": lifecycle_hash,
        "membership": membership,
        "membership_hash": membership_hash,
        "membership_records_hash": membership_records_hash,
        "files": files,
        "source_inventory": source_inventory,
    }


def _build_payload(inputs: dict) -> tuple[dict, str]:
    coverage = inputs["coverage"]
    template = coverage["template"]
    semantic = {
        "template": template,
        "scope": {
            "artifact_id": coverage["scope_freeze"]["artifact_id"],
            "manifest_sha256": inputs["scope_hash"],
            "execution_scope": coverage["execution_scope"],
            "source_scope": coverage["source_scope"],
        },
        "coverage": {
            "artifact_id": coverage["artifact_id"],
            "manifest_sha256": inputs["coverage_hash"],
            "files": inputs["files"],
            "stats": coverage["coverage"],
            "algorithm_hash": coverage["liquidity_algorithm"]["algorithm_hash"],
        },
        "calendar": coverage["calendar"],
        "membership": {
            "snapshot_id": inputs["membership"]["snapshot_id"],
            "manifest_sha256": inputs["membership_hash"],
            "records_sha256": inputs["membership_records_hash"],
        },
        "lifecycle": {
            "successor_id": inputs["lifecycle"]["successor_id"],
            "manifest_sha256": inputs["lifecycle_hash"],
        },
        "suspension_evidence": {
            "artifact_id": inputs["evidence"]["artifact_id"],
            "manifest_sha256": inputs["evidence_hash"],
            "source_adapter": coverage["source_adapter"],
        },
        "source_adapter": coverage["source_adapter"],
        "source_inventory": inputs["source_inventory"],
        "b3_execution_input": {
            "artifact_id": inputs["b3"]["artifact_id"],
            "manifest_sha256": inputs["b3_hash"],
            "authorization_scope": inputs["b3"]["authorization_scope"],
        },
        "execution_scope": coverage["execution_scope"],
        "source_scope": coverage["source_scope"],
        "market_data_start": "2024-06-07",
        "market_data_end": "2026-07-10",
        "execution_coverage_start": "2025-06-27",
        "execution_coverage_end": "2026-07-10",
        "quality_status": "ok",
        "availability_status": "availability_bounded",
        "authorization_scope": "b6_coverage_bound",
    }
    semantic_hash = _sha_bytes(_canonical(semantic))
    snapshot_id = f"v3ds_{semantic_hash[:16]}"
    model = DataSnapshotManifest(
        snapshot_id=snapshot_id,
        provider="traderlens_v3_pit",
        retrieval_date=None,
        retrieval_date_status="unknown",
        market_data_start=date(2024, 6, 7),
        market_data_end=date(2026, 7, 10),
        universe_snapshot_ids=(inputs["membership"]["snapshot_id"],),
        semantic_hash=semantic_hash,
        quality_status="ok",
        gaps=("availability_bounded",),
        frozen=True,
        schema_version="v3_formal_data_snapshot.v1",
        availability_status="availability_bounded",
        authorization_scope="b6_coverage_bound",
        v3_qualification=semantic,
        coverage_start=date(2025, 6, 27),
        coverage_end=date(2026, 7, 10),
        source_manifest_hashes=tuple(sorted((key, value["content_hash"]) for key, value in inputs["source_inventory"].items() if isinstance(value, dict) and "content_hash" in value)),
        not_authorized_for_b6_oos_gate_promotion_signal=False,
    )
    base = model.model_dump(mode="json")
    base["manifest_content_hash"] = ""
    content_hash = _sha_bytes(_canonical(base))
    base["manifest_content_hash"] = content_hash
    return base, snapshot_id


def publish_formal_snapshot(
    *,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    coverage_dir: Path = COVERAGE_DIR,
    scope_dir: Path = SCOPE_DIR,
    evidence_dir: Path = EVIDENCE_DIR,
    b3_manifest_path: Path = B3_MANIFEST,
    lifecycle_manifest_path: Path = LIFECYCLE_MANIFEST,
    membership_dir: Path = MEMBERSHIP_DIR,
) -> dict:
    inputs = _load_inputs(
        coverage_dir=coverage_dir,
        scope_dir=scope_dir,
        evidence_dir=evidence_dir,
        b3_manifest_path=b3_manifest_path,
        lifecycle_manifest_path=lifecycle_manifest_path,
        membership_dir=membership_dir,
    )
    payload, snapshot_id = _build_payload(inputs)
    target = Path(output_root) / snapshot_id
    manifest_path = target / "manifest.json"
    sidecar_path = target / "manifest.json.sha256"
    raw = _canonical(payload)
    if target.exists():
        if not manifest_path.exists() or not sidecar_path.exists():
            raise ValueError("formal snapshot write-once conflict: incomplete existing artifact")
        if manifest_path.read_bytes() != raw or sidecar_path.read_text(encoding="utf-8").split()[0] != _sha_bytes(raw):
            raise ValueError("formal snapshot write-once conflict: content differs")
        return {"status": "already_published", "snapshot_id": snapshot_id, "path": str(target), "semantic_hash": payload["semantic_hash"], "manifest_sha256": _sha_bytes(raw)}
    target.mkdir(parents=True, exist_ok=False)
    manifest_path.write_bytes(raw)
    sidecar_path.write_text(_sha_bytes(raw) + "  manifest.json\n", encoding="utf-8")
    return {"status": "published", "snapshot_id": snapshot_id, "path": str(target), "semantic_hash": payload["semantic_hash"], "manifest_sha256": _sha_bytes(raw)}


if __name__ == "__main__":
    print(json.dumps(publish_formal_snapshot(), sort_keys=True))
