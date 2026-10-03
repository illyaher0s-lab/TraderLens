"""Independently verify the immutable market-regime v1.2 owner approval."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scripts.market_regime_bounded_replay import ROOT, _load_config
from scripts.publish_market_regime_v12_owner_approval import (
    CONFIG_PATH,
    CONFIG_SEMANTIC_HASH,
    EVIDENCE_DIR,
    EVIDENCE_ID,
    EVIDENCE_MANIFEST_SHA256,
    INDEX_ID,
    INDEX_MANIFEST_SHA256,
    INDEX_SOURCE_DIR,
    QUALIFICATION_DIR,
    QUALIFICATION_ID,
    QUALIFICATION_MANIFEST_SHA256,
    SOURCE_MANIFEST_SHA256,
    VALIDATION_REPORT_SHA256,
    VALIDATION_SEMANTIC_HASH,
    _sidecar,
    approval_payload,
    canonical,
    sha256_bytes,
    sha256_file,
)
from scripts.market_regime_bounded_replay import verify_bounded_qualification


def verify_owner_approval(
    approval_dir: Path,
    *,
    config_path: Path = CONFIG_PATH,
    qualification_dir: Path = QUALIFICATION_DIR,
    evidence_dir: Path = EVIDENCE_DIR,
    index_source_dir: Path = INDEX_SOURCE_DIR,
) -> dict[str, Any]:
    approval_dir = Path(approval_dir)
    manifest_path = approval_dir / "manifest.json"
    _sidecar(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifact_id = manifest.get("artifact_id")
    payload = {key: value for key, value in manifest.items() if key != "artifact_id"}
    if manifest.get("schema_version") != "market_regime_v12_owner_approval.v1":
        raise ValueError("owner approval schema mismatch")
    if manifest.get("status") != "approved" or manifest.get("decision") != "approved":
        raise ValueError("owner approval decision mismatch")
    if manifest.get("authorized_by") != "illya":
        raise ValueError("owner approval owner authorization mismatch")
    if sha256_bytes(canonical(payload))[:16] != artifact_id:
        raise ValueError("owner approval artifact identity mismatch")
    if payload != approval_payload():
        raise ValueError("owner approval exact payload mismatch")

    config_path = Path(config_path)
    if sha256_file(config_path) != payload["config"]["sha256"]:
        raise ValueError("owner approval config file hash mismatch")
    _, semantic_hash = _load_config(config_path)
    if semantic_hash != CONFIG_SEMANTIC_HASH or semantic_hash != payload["config"]["semantic_hash"]:
        raise ValueError("owner approval config semantic hash mismatch")

    qualification_dir = Path(qualification_dir)
    qualification_manifest = qualification_dir / "manifest.json"
    qualification_report = qualification_dir / "validation_report.json"
    qualification_source = qualification_dir / "source_manifest.json"
    for path in (qualification_manifest, qualification_report, qualification_source):
        _sidecar(path)
    qualified = verify_bounded_qualification(qualification_dir)
    if qualified["artifact_id"] != QUALIFICATION_ID:
        raise ValueError("owner approval qualification identity mismatch")
    for path, expected in (
        (qualification_manifest, QUALIFICATION_MANIFEST_SHA256),
        (qualification_report, VALIDATION_REPORT_SHA256),
        (qualification_source, SOURCE_MANIFEST_SHA256),
    ):
        if sha256_file(path) != expected:
            raise ValueError(f"owner approval qualification file hash mismatch: {path.name}")
    report = json.loads(qualification_report.read_text(encoding="utf-8"))
    acceptance = payload["acceptance"]
    if report.get("zero_gap") is not True or acceptance["zero_gap"] is not True:
        raise ValueError("owner approval zero-gap acceptance mismatch")
    normal = report.get("windows", {}).get("normal", {})
    if float(normal.get("normal_block_ratio")) > float(acceptance["normal_window_block_ratio_max"]):
        raise ValueError("owner approval normal-window acceptance mismatch")
    stress_minimum = int(acceptance["stress_window_block_day_min"])
    if any(
        window_id != "normal" and int(window.get("blocked_day_count", 0)) < stress_minimum
        for window_id, window in report.get("windows", {}).items()
    ):
        raise ValueError("owner approval stress-window acceptance mismatch")
    if report.get("validation_semantic_hash") != VALIDATION_SEMANTIC_HASH:
        raise ValueError("owner approval validation semantic hash mismatch")

    for directory, expected_id, expected_hash, label in (
        (evidence_dir, EVIDENCE_ID, EVIDENCE_MANIFEST_SHA256, "evidence"),
        (index_source_dir, INDEX_ID, INDEX_MANIFEST_SHA256, "index"),
    ):
        manifest_path = Path(directory) / "manifest.json"
        _sidecar(manifest_path)
        source_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if source_manifest.get("artifact_id") != expected_id:
            raise ValueError(f"owner approval {label} identity mismatch")
        if sha256_file(manifest_path) != expected_hash:
            raise ValueError(f"owner approval {label} manifest hash mismatch")

    return {
        "status": "verified",
        "artifact_id": artifact_id,
        "path": str(approval_dir),
        "authorized_by": manifest["authorized_by"],
        "qualification_id": QUALIFICATION_ID,
        "evidence_id": EVIDENCE_ID,
        "index_id": INDEX_ID,
        "zero_gap": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("approval_dir", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify_owner_approval(args.approval_dir), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
