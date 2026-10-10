"""Independent verifier for bounded vendor lifecycle successor metadata."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(artifact: Path, *, vendor_manifest: Path | None = None, candidate: Path | None = None, gap_audit: Path | None = None) -> dict:
    artifact = Path(artifact)
    manifest_path = artifact / "manifest.json"
    sidecar = artifact / "manifest.json.sha256"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if _sha(manifest_path) != sidecar.read_text(encoding="utf-8").strip():
        raise ValueError("manifest sidecar mismatch")
    if manifest.get("qualification_status") != "bounded_qualified_vendor_lifecycle":
        raise ValueError("invalid qualification status")
    if manifest.get("source_kind") != "vendor_lifecycle_evidence_not_official_source":
        raise ValueError("source kind disclosure mismatch")
    semantic = {key: value for key, value in manifest.items() if key != "successor_id"}
    if hashlib.sha256(_canonical(semantic)).hexdigest()[:16] != manifest.get("successor_id"):
        raise ValueError("successor id mismatch")
    if manifest.get("uncovered_formal_daily_dates") != 0 or manifest.get("errors") != []:
        raise ValueError("qualification contains unresolved gaps")
    for item in manifest.get("codes", []):
        if not item.get("gap_dates") or item["list_date"] > item["gap_dates"][0] or item["delist_date"] != item["gap_dates"][-1]:
            raise ValueError(f"{item.get('ts_code')}: lifecycle bounds mismatch")
    for path, field in ((vendor_manifest, "vendor_manifest_sha256"), (candidate, "candidate_sha256"), (gap_audit, "gap_audit_sha256")):
        if path is not None and _sha(Path(path)) != manifest.get(field):
            label = "candidate hash" if field == "candidate_sha256" else f"{field} mismatch"
            raise ValueError(label)
    return {"status": "verified", "successor_id": manifest["successor_id"]}