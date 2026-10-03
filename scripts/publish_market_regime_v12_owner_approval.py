"""Publish the immutable owner approval for the verified market-regime v1.2 candidate."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from scripts.market_regime_bounded_replay import ROOT, _load_config, verify_bounded_qualification

CONFIG_PATH = ROOT / "backend/config/market_regime_thresholds.yaml"
QUALIFICATION_DIR = ROOT / "data/pit/market_regime_qualifications/be92ad203fc0f2cd"
EVIDENCE_DIR = ROOT / "data/pit/market_regime_suspension_evidence/adcfa06eebc44ceb"
INDEX_SOURCE_DIR = ROOT / "data/pit/market_regime_index_sources/b1208520d9b0c0b0"
DEFAULT_OUTPUT_ROOT = ROOT / "data/pit/market_regime_owner_approvals"

CONFIG_SHA256 = "65d4fa29e8a16f5c3e839fda44d26ae3c4c588d08d630a578b84859b32d26cfc"
CONFIG_SEMANTIC_HASH = "483c251850f6f6aeea63df059e2f8b8a81992ad71921176ec16ef8ff93918eec"
QUALIFICATION_ID = "be92ad203fc0f2cd"
QUALIFICATION_MANIFEST_SHA256 = "3a0a4330f517cd758a37de4a4c01e684211e6b6fd41eec9c5845f1639ce8aa9d"
VALIDATION_REPORT_SHA256 = "0dbae0397f4878cf4b4ac47af636ecc845403282eec45118ad6f2ac368021d35"
SOURCE_MANIFEST_SHA256 = "31ae3b30df723638faf60e90e502ac1e7e32e71db191976601fb4100e22d1ee8"
VALIDATION_SEMANTIC_HASH = "62889a54dde15376acc39fec01579059ab16ec35160755201e4651430be91999"
EVIDENCE_ID = "adcfa06eebc44ceb"
EVIDENCE_MANIFEST_SHA256 = "e1f6132b2a818dd2523a0da33fa393cc69b1aed22be1241f741fe4bdfeddaaeb"
INDEX_ID = "b1208520d9b0c0b0"
INDEX_MANIFEST_SHA256 = "efe435a732e60eab316db6d042f22383b051d6a4712e3d289027956adc6ade68"


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def _sidecar(path: Path) -> None:
    sidecar = path.with_name(path.name + ".sha256")
    if not path.exists() or not sidecar.exists():
        raise ValueError(f"owner approval sidecar missing: {path}")
    fields = sidecar.read_text(encoding="utf-8").split()
    if not fields or fields[0] != sha256_file(path):
        raise ValueError(f"owner approval sidecar mismatch: {path}")


def _write_sidecar(path: Path) -> None:
    path.with_name(path.name + ".sha256").write_text(
        f"{sha256_file(path)}  {path.name}\n", encoding="utf-8"
    )


def approval_payload() -> dict[str, Any]:
    return {
        "schema_version": "market_regime_v12_owner_approval.v1",
        "status": "approved",
        "decision": "approved",
        "authorized_by": "illya",
        "authorization_scope": "v3_manual_trading_market_regime_only",
        "config": {
            "path": "backend/config/market_regime_thresholds.yaml",
            "version": "1.2",
            "sha256": CONFIG_SHA256,
            "semantic_hash": CONFIG_SEMANTIC_HASH,
        },
        "qualification": {
            "artifact_id": QUALIFICATION_ID,
            "manifest_sha256": QUALIFICATION_MANIFEST_SHA256,
            "validation_report_sha256": VALIDATION_REPORT_SHA256,
            "source_manifest_sha256": SOURCE_MANIFEST_SHA256,
            "validation_semantic_hash": VALIDATION_SEMANTIC_HASH,
        },
        "evidence": {
            "artifact_id": EVIDENCE_ID,
            "manifest_sha256": EVIDENCE_MANIFEST_SHA256,
        },
        "index_source": {
            "artifact_id": INDEX_ID,
            "manifest_sha256": INDEX_MANIFEST_SHA256,
        },
        "acceptance": {
            "zero_gap": True,
            "stress_window_block_day_min": 1,
            "normal_window_block_ratio_max": 0.05,
        },
    }


def _assert_sources(
    payload: dict[str, Any],
    *,
    config_path: Path = CONFIG_PATH,
    qualification_dir: Path = QUALIFICATION_DIR,
    evidence_dir: Path = EVIDENCE_DIR,
    index_source_dir: Path = INDEX_SOURCE_DIR,
) -> None:
    config_path = Path(config_path)
    if sha256_file(config_path) != payload["config"]["sha256"]:
        raise ValueError("owner approval config file hash mismatch")
    _, semantic_hash = _load_config(config_path)
    if semantic_hash != payload["config"]["semantic_hash"]:
        raise ValueError("owner approval config semantic hash mismatch")

    qualification_dir = Path(qualification_dir)
    qualification_manifest = qualification_dir / "manifest.json"
    qualification_report = qualification_dir / "validation_report.json"
    qualification_source = qualification_dir / "source_manifest.json"
    for path in (qualification_manifest, qualification_report, qualification_source):
        _sidecar(path)
    verified = verify_bounded_qualification(qualification_dir)
    if verified["artifact_id"] != payload["qualification"]["artifact_id"]:
        raise ValueError("owner approval qualification identity mismatch")
    expected_files = {
        qualification_manifest: payload["qualification"]["manifest_sha256"],
        qualification_report: payload["qualification"]["validation_report_sha256"],
        qualification_source: payload["qualification"]["source_manifest_sha256"],
    }
    for path, expected in expected_files.items():
        if sha256_file(path) != expected:
            raise ValueError(f"owner approval qualification file hash mismatch: {path.name}")

    for directory, expected_id, expected_hash, label in (
        (evidence_dir, payload["evidence"]["artifact_id"], payload["evidence"]["manifest_sha256"], "evidence"),
        (index_source_dir, payload["index_source"]["artifact_id"], payload["index_source"]["manifest_sha256"], "index"),
    ):
        manifest_path = Path(directory) / "manifest.json"
        _sidecar(manifest_path)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("artifact_id") != expected_id or sha256_file(manifest_path) != expected_hash:
            raise ValueError(f"owner approval {label} manifest binding mismatch")


def publish_owner_approval(
    *,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    config_path: Path = CONFIG_PATH,
    qualification_dir: Path = QUALIFICATION_DIR,
    evidence_dir: Path = EVIDENCE_DIR,
    index_source_dir: Path = INDEX_SOURCE_DIR,
) -> dict[str, Any]:
    payload = approval_payload()
    _assert_sources(
        payload,
        config_path=config_path,
        qualification_dir=qualification_dir,
        evidence_dir=evidence_dir,
        index_source_dir=index_source_dir,
    )
    artifact_id = sha256_bytes(canonical(payload))[:16]
    target = Path(output_root) / artifact_id
    manifest = {**payload, "artifact_id": artifact_id}
    raw = canonical(manifest)
    if target.exists():
        manifest_path = target / "manifest.json"
        if not manifest_path.exists() or manifest_path.read_bytes() != raw:
            raise ValueError("owner approval write-once conflict")
        _sidecar(manifest_path)
        return {"status": "already_published", "artifact_id": artifact_id, "path": str(target)}

    target.parent.mkdir(parents=True, exist_ok=True)
    target.mkdir()
    manifest_path = target / "manifest.json"
    temp_path = target / "manifest.json.tmp"
    try:
        with open(temp_path, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, manifest_path)
        _write_sidecar(manifest_path)
    finally:
        if temp_path.exists():
            temp_path.unlink()
    return {"status": "published", "artifact_id": artifact_id, "path": str(target)}


if __name__ == "__main__":
    print(json.dumps(publish_owner_approval(), sort_keys=True))
