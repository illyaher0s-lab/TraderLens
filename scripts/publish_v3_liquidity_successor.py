from __future__ import annotations

import hashlib
import json
from pathlib import Path


def _raw_manifest(artifact: Path) -> tuple[bytes, dict]:
    path = Path(artifact) / "manifest.json"
    raw = path.read_bytes()
    sidecar = (Path(artifact) / "manifest.json.sha256").read_text(encoding="utf-8").split()[0]
    digest = hashlib.sha256(raw).hexdigest()
    if sidecar != digest:
        raise ValueError("manifest sidecar mismatch")
    manifest = json.loads(raw)
    if manifest.get("artifact_id") != Path(artifact).name:
        raise ValueError("artifact id mismatch")
    return raw, manifest


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def publish_successor(*, predecessor: Path, corrective_overlay: Path,
                      corrective_verification: dict, output_root: Path) -> dict:
    predecessor = Path(predecessor).resolve()
    overlay = Path(corrective_overlay).resolve()
    predecessor_raw, old = _raw_manifest(predecessor)
    overlay_raw, correction = _raw_manifest(overlay)
    if old.get("sources", {}).get("corrective_overlay") is not None:
        raise ValueError("predecessor already has overlay")
    if old.get("schema_version") != "v3_liquidity_qualification.v1":
        raise ValueError("predecessor schema mismatch")
    stats = old.get("scope", {}).get("stats", {})
    expected = {"expected_scope_count": 5522, "complete_count": 5519,
                "unavailable_ineligible_count": 3, "data_fault_count": 0}
    if any(stats.get(k) != v for k, v in expected.items()):
        raise ValueError("predecessor stats mismatch")
    if corrective_verification.get("status") != "verified" or corrective_verification.get("artifact_id") != correction.get("artifact_id"):
        raise ValueError("corrective verifier result mismatch")
    if correction.get("schema_version") != "v3_liquidity_suspend_corrective.v1" or correction.get("status") != "published":
        raise ValueError("corrective overlay schema/status mismatch")

    payload = dict(old)
    payload.pop("artifact_id", None)
    payload["schema_version"] = "v3_liquidity_qualification_successor.v1"
    payload["status"] = "published"
    payload["correction"] = {"type": "metadata binding correction only", "predecessor_overlay_binding": False}
    payload["predecessor"] = {"artifact_id": old["artifact_id"], "path": str(predecessor), "sha256": _file_sha(predecessor / "manifest.json")}
    payload["corrective_overlay"] = {"artifact_id": correction["artifact_id"], "path": str(overlay), "sha256": _file_sha(overlay / "manifest.json")}
    payload["sources"] = dict(old.get("sources", {}))
    payload["sources"]["corrective_overlay"] = {"path": str(overlay), "sha256": _file_sha(overlay / "manifest.json")}
    artifact_id = hashlib.sha256(_canonical(payload)).hexdigest()[:16]
    payload["artifact_id"] = artifact_id
    target = Path(output_root).resolve() / artifact_id
    if target.exists():
        raise ValueError("successor already exists")
    target.mkdir(parents=True)
    raw = _canonical(payload)
    (target / "manifest.json").write_bytes(raw)
    (target / "manifest.json.sha256").write_text(hashlib.sha256(raw).hexdigest() + "  manifest.json\n", encoding="utf-8")
    return {"status": "published", "artifact_id": artifact_id, "path": str(target)}
