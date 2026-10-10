"""Publish the exact v3 availability-bounded qualification successor."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.publish_v3_formal_snapshot import (
    B3_MANIFEST,
    COVERAGE_DIR,
    EVIDENCE_DIR,
    LIFECYCLE_MANIFEST,
    MEMBERSHIP_DIR,
    SCOPE_DIR,
    TEMPLATE,
)
from scripts.verify_v3_formal_snapshot import verify_formal_snapshot
from scripts.verify_v3_historical_coverage import verify_coverage
from scripts.verify_v3_historical_suspension_evidence import verify_evidence
from scripts.publish_v3_formal_snapshot import DIAGNOSTICS, PROVIDER_PROBE


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = ROOT / "data/pit/v3_availability_bounded_qualification_successors"


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sidecar_hash(path: Path) -> str:
    sidecar = path.with_name(path.name + ".sha256")
    if not sidecar.exists() or sidecar.read_text(encoding="utf-8").split()[0] != _sha(path):
        raise ValueError(f"sidecar mismatch: {path}")
    return _sha(path)


def _bound_inputs(formal_snapshot_dir: Path, coverage_dir: Path, scope_dir: Path, evidence_dir: Path) -> dict:
    snapshot_result = verify_formal_snapshot(formal_snapshot_dir, coverage_dir=coverage_dir, scope_dir=scope_dir, evidence_dir=evidence_dir)
    coverage_result = verify_coverage(coverage_dir, scope_dir=scope_dir)
    evidence_result = verify_evidence(evidence_dir, diagnostics_path=DIAGNOSTICS, provider_probe_path=PROVIDER_PROBE, scope_dir=scope_dir)
    if snapshot_result.get("status") != "valid" or coverage_result.get("status") != "valid" or evidence_result.get("status") != "verified":
        raise ValueError("v3 bound verifier failed")
    coverage = _read(Path(coverage_dir) / "manifest.json")
    snapshot = _read(Path(formal_snapshot_dir) / "manifest.json")
    evidence = _read(Path(evidence_dir) / "manifest.json")
    scope_manifest = Path(scope_dir) / "manifest.json"
    b3 = _read(B3_MANIFEST)
    lifecycle = _read(LIFECYCLE_MANIFEST)
    membership = _read(MEMBERSHIP_DIR / "manifest.json")
    coverage_hash = _sidecar_hash(Path(coverage_dir) / "manifest.json")
    snapshot_hash = _sidecar_hash(Path(formal_snapshot_dir) / "manifest.json")
    evidence_hash = _sidecar_hash(Path(evidence_dir) / "manifest.json")
    scope_hash = _sidecar_hash(scope_manifest)
    b3_hash = _sidecar_hash(B3_MANIFEST)
    lifecycle_hash = _sidecar_hash(LIFECYCLE_MANIFEST)
    membership_hash = _sidecar_hash(MEMBERSHIP_DIR / "manifest.json")
    membership_records_hash = _sidecar_hash(MEMBERSHIP_DIR / "records.parquet")
    if coverage.get("template") != TEMPLATE or coverage["coverage"]["data_fault_count"] != 0:
        raise ValueError("v3 coverage identity or data_fault mismatch")
    if b3.get("artifact_id") != "05f38a2884dc7e47" or lifecycle.get("successor_id") != "49b09326f35936c6" or membership.get("snapshot_id") != "pims_traderlens_v2_shsz_sw2021_pit_005":
        raise ValueError("v3 lineage identity mismatch")
    if coverage["lineage"]["b3_execution_input_successor"]["manifest_sha256"] != b3_hash:
        raise ValueError("v3 B3 lineage hash mismatch")
    if coverage["lineage"]["lifecycle_successor"]["manifest_sha256"] != lifecycle_hash:
        raise ValueError("v3 lifecycle lineage hash mismatch")
    if coverage["lineage"]["membership_snapshot"]["manifest_sha256"] != membership_hash:
        raise ValueError("v3 membership lineage hash mismatch")
    if coverage["lineage"]["membership_snapshot"]["records_sha256"] != membership_records_hash:
        raise ValueError("v3 membership records hash mismatch")
    if coverage["lineage"]["suspension_evidence"]["manifest_sha256"] != evidence_hash:
        raise ValueError("v3 suspension evidence lineage hash mismatch")
    return {
        "coverage": coverage,
        "coverage_hash": coverage_hash,
        "snapshot": snapshot,
        "snapshot_hash": snapshot_hash,
        "evidence": evidence,
        "evidence_hash": evidence_hash,
        "scope_hash": scope_hash,
        "b3": b3,
        "b3_hash": b3_hash,
        "lifecycle": lifecycle,
        "lifecycle_hash": lifecycle_hash,
        "membership": membership,
        "membership_hash": membership_hash,
        "membership_records_hash": membership_records_hash,
    }


def build_successor(
    *,
    formal_snapshot_dir: Path,
    coverage_dir: Path = COVERAGE_DIR,
    scope_dir: Path = SCOPE_DIR,
    evidence_dir: Path = EVIDENCE_DIR,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
) -> dict:
    inputs = _bound_inputs(Path(formal_snapshot_dir), Path(coverage_dir), Path(scope_dir), Path(evidence_dir))
    coverage = inputs["coverage"]
    payload = {
        "successor_schema_version": "v3_availability_bounded_qualification_successor.v1",
        "status": "availability_bounded_qualified",
        "authorization_scope": "b6_coverage_bound",
        "not_authorized_for_b6_oos_gate_promotion_signal_or_data_collection": False,
        "template": TEMPLATE,
        "scope": {"artifact_id": coverage["scope_freeze"]["artifact_id"], "manifest_sha256": inputs["scope_hash"]},
        "formal_snapshot": {"snapshot_id": inputs["snapshot"]["snapshot_id"], "semantic_hash": inputs["snapshot"]["semantic_hash"], "manifest_sha256": inputs["snapshot_hash"]},
        "coverage": {
            "artifact_id": coverage["artifact_id"],
            "manifest_sha256": inputs["coverage_hash"],
            "files": coverage["files"],
            "stats": coverage["coverage"],
            "algorithm_hash": coverage["liquidity_algorithm"]["algorithm_hash"],
        },
        "source_adapter": coverage["source_adapter"],
        "suspension_evidence": {"artifact_id": inputs["evidence"]["artifact_id"], "manifest_sha256": inputs["evidence_hash"]},
        "lineage": {
            "b3": {"artifact_id": inputs["b3"]["artifact_id"], "manifest_sha256": inputs["b3_hash"], "authorization_scope": inputs["b3"]["authorization_scope"]},
            "lifecycle": {"successor_id": inputs["lifecycle"]["successor_id"], "manifest_sha256": inputs["lifecycle_hash"]},
            "membership": {"snapshot_id": inputs["membership"]["snapshot_id"], "manifest_sha256": inputs["membership_hash"], "records_sha256": inputs["membership_records_hash"]},
        },
        "execution_scope": coverage["execution_scope"],
        "source_scope": coverage["source_scope"],
        "source_inventory": {key: {"content_hash": value["content_hash"], "entry_count": value["entry_count"]} for key, value in coverage["sources"].items() if key in ("daily", "adj_factor", "suspend_d")},
    }
    successor_id = hashlib.sha256(_canonical(payload)).hexdigest()[:16]
    manifest = {**payload, "successor_id": successor_id}
    raw = _canonical(manifest)
    target = Path(output_root) / successor_id
    if target.exists():
        manifest_path = target / "manifest.json"
        sidecar = target / "manifest.json.sha256"
        if not manifest_path.exists() or not sidecar.exists() or manifest_path.read_bytes() != raw or sidecar.read_text(encoding="utf-8").split()[0] != _sha(manifest_path):
            raise ValueError("v3 successor write-once conflict")
        return {"status": "already_published", "successor_id": successor_id, "path": str(target), "manifest_sha256": _sha(manifest_path)}
    target.mkdir(parents=True, exist_ok=False)
    manifest_path = target / "manifest.json"
    manifest_path.write_bytes(raw)
    (target / "manifest.json.sha256").write_text(_sha(manifest_path) + "  manifest.json\n", encoding="utf-8")
    return {"status": "published", "successor_id": successor_id, "path": str(target), "manifest_sha256": _sha(manifest_path)}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--formal-snapshot-dir", type=Path, required=True)
    parser.add_argument("--coverage-dir", type=Path, default=COVERAGE_DIR)
    parser.add_argument("--scope-dir", type=Path, default=SCOPE_DIR)
    parser.add_argument("--evidence-dir", type=Path, default=EVIDENCE_DIR)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args()
    print(json.dumps(build_successor(formal_snapshot_dir=args.formal_snapshot_dir, coverage_dir=args.coverage_dir, scope_dir=args.scope_dir, evidence_dir=args.evidence_dir, output_root=args.output_root), sort_keys=True))
