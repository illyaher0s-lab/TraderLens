"""Independent verifier for the metadata-only formal v3 data snapshot."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from backend.services.b3_protocol_types import DataSnapshotManifest
from scripts.publish_v3_formal_snapshot import (
    B3_MANIFEST,
    COVERAGE_DIR,
    EVIDENCE_DIR,
    LIFECYCLE_MANIFEST,
    MEMBERSHIP_DIR,
    PROVIDER_PROBE,
    DIAGNOSTICS,
    SCOPE_DIR,
    TEMPLATE,
)
from scripts.publish_v3_historical_scope import verify_scope
from scripts.verify_v3_historical_coverage import verify_coverage
from scripts.verify_v3_historical_suspension_evidence import verify_evidence


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
    actual = _sha(path)
    if sidecar.read_text(encoding="utf-8").split()[0] != actual:
        raise ValueError(f"sidecar mismatch: {path}")
    return actual


def _expected_qualification(
    *,
    coverage: dict,
    coverage_hash: str,
    scope_hash: str,
    evidence: dict,
    evidence_hash: str,
    b3: dict,
    b3_hash: str,
    membership: dict,
    membership_hash: str,
    membership_records_hash: str,
    lifecycle: dict,
    lifecycle_hash: str,
    coverage_dir: Path,
) -> dict:
    files = {}
    for key, filename in {
        "coverage_by_code": "coverage_by_code.parquet",
        "coverage_by_date": "coverage_by_date.parquet",
        "unavailable": "unavailable_security_dates.parquet",
    }.items():
        path = coverage_dir / filename
        files[key] = {"path": filename, **coverage["files"][key]}
        if _sha(path) != files[key]["sha256"]:
            raise ValueError(f"coverage file hash mismatch: {filename}")
    source_inventory = {
        key: {"content_hash": coverage["sources"][key]["content_hash"], "entry_count": coverage["sources"][key]["entry_count"]}
        for key in ("daily", "adj_factor", "suspend_d")
    }
    source_inventory["formal_input_root"] = coverage["sources"]["formal_input_root"]
    return {
        "template": coverage["template"],
        "scope": {
            "artifact_id": coverage["scope_freeze"]["artifact_id"],
            "manifest_sha256": scope_hash,
            "execution_scope": coverage["execution_scope"],
            "source_scope": coverage["source_scope"],
        },
        "coverage": {
            "artifact_id": coverage["artifact_id"],
            "manifest_sha256": coverage_hash,
            "files": files,
            "stats": coverage["coverage"],
            "algorithm_hash": coverage["liquidity_algorithm"]["algorithm_hash"],
        },
        "calendar": coverage["calendar"],
        "membership": {
            "snapshot_id": membership["snapshot_id"],
            "manifest_sha256": membership_hash,
            "records_sha256": membership_records_hash,
        },
        "lifecycle": {"successor_id": lifecycle["successor_id"], "manifest_sha256": lifecycle_hash},
        "suspension_evidence": {
            "artifact_id": evidence["artifact_id"],
            "manifest_sha256": evidence_hash,
            "source_adapter": coverage["source_adapter"],
        },
        "source_adapter": coverage["source_adapter"],
        "source_inventory": source_inventory,
        "b3_execution_input": {
            "artifact_id": b3["artifact_id"],
            "manifest_sha256": b3_hash,
            "authorization_scope": b3["authorization_scope"],
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


def verify_formal_snapshot(
    snapshot_dir: Path,
    *,
    coverage_dir: Path = COVERAGE_DIR,
    scope_dir: Path = SCOPE_DIR,
    evidence_dir: Path = EVIDENCE_DIR,
    b3_manifest_path: Path = B3_MANIFEST,
    lifecycle_manifest_path: Path = LIFECYCLE_MANIFEST,
    membership_dir: Path = MEMBERSHIP_DIR,
) -> dict:
    snapshot_dir = Path(snapshot_dir)
    manifest_path = snapshot_dir / "manifest.json"
    manifest_hash = _sidecar_hash(manifest_path)
    manifest = _read(manifest_path)
    declared_content_hash = manifest.get("manifest_content_hash")
    content_payload = dict(manifest)
    content_payload["manifest_content_hash"] = ""
    if declared_content_hash != _sha_bytes(_canonical(content_payload)):
        raise ValueError("formal snapshot content hash mismatch")
    if manifest.get("schema_version") != "v3_formal_data_snapshot.v1":
        raise ValueError("formal snapshot schema mismatch")
    parsed = DataSnapshotManifest.model_validate(manifest)
    if parsed.not_authorized_for_b6_oos_gate_promotion_signal is not False:
        raise ValueError("v3 formal authorization disclosure mismatch")

    verify_scope(Path(scope_dir))
    coverage_result = verify_coverage(Path(coverage_dir), scope_dir=Path(scope_dir))
    evidence_result = verify_evidence(
        Path(evidence_dir), diagnostics_path=DIAGNOSTICS, provider_probe_path=PROVIDER_PROBE, scope_dir=Path(scope_dir)
    )
    if coverage_result.get("status") != "valid" or evidence_result.get("status") != "verified":
        raise ValueError("bound coverage/evidence verification failed")

    coverage_path = Path(coverage_dir) / "manifest.json"
    coverage = _read(coverage_path)
    coverage_hash = _sidecar_hash(coverage_path)
    scope_hash = _sidecar_hash(Path(scope_dir) / "manifest.json")
    evidence_path = Path(evidence_dir) / "manifest.json"
    evidence = _read(evidence_path)
    evidence_hash = _sidecar_hash(evidence_path)
    b3 = _read(Path(b3_manifest_path))
    b3_hash = _sidecar_hash(Path(b3_manifest_path))
    lifecycle = _read(Path(lifecycle_manifest_path))
    lifecycle_hash = _sidecar_hash(Path(lifecycle_manifest_path))
    membership_path = Path(membership_dir) / "manifest.json"
    membership = _read(membership_path)
    membership_hash = _sidecar_hash(membership_path)
    membership_records_hash = _sidecar_hash(Path(membership_dir) / "records.parquet")
    if membership.get("records_parquet_sha256") != membership_records_hash:
        raise ValueError("membership records hash mismatch")
    if coverage.get("template") != TEMPLATE or coverage.get("coverage", {}).get("data_fault_count") != 0:
        raise ValueError("coverage v3 binding mismatch")
    expected = _expected_qualification(
        coverage=coverage,
        coverage_hash=coverage_hash,
        scope_hash=scope_hash,
        evidence=evidence,
        evidence_hash=evidence_hash,
        b3=b3,
        b3_hash=b3_hash,
        membership=membership,
        membership_hash=membership_hash,
        membership_records_hash=membership_records_hash,
        lifecycle=lifecycle,
        lifecycle_hash=lifecycle_hash,
        coverage_dir=Path(coverage_dir),
    )
    if manifest.get("v3_qualification") != expected:
        raise ValueError("formal snapshot qualification binding mismatch")
    semantic_hash = _sha_bytes(_canonical(expected))
    if manifest.get("semantic_hash") != semantic_hash or manifest.get("snapshot_id") != f"v3ds_{semantic_hash[:16]}":
        raise ValueError("formal snapshot semantic identity mismatch")
    return {
        "status": "valid",
        "snapshot_id": manifest["snapshot_id"],
        "semantic_hash": semantic_hash,
        "manifest_sha256": manifest_hash,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot_dir", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify_formal_snapshot(args.snapshot_dir), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
