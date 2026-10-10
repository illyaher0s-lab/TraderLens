from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest


ROOT = Path(__file__).parent.parent
COVERAGE_DIR = ROOT / "data/pit/v3_historical_coverage_packages/1e79d26460c0c109"
SCOPE_DIR = ROOT / "data/pit/historical_scope_freezes/acbc49159d989a46"
EVIDENCE_DIR = ROOT / "data/pit/v3_historical_suspension_evidence/4871f6ba56b40e93"
LEGACY_SNAPSHOT_DIR = ROOT / "data/pit/data_snapshot_manifests/ds_traderlens_v2_shsz_pit_001"


def test_v3_formal_snapshot_publishes_and_verifies_without_copying_data(tmp_path: Path):
    from scripts.publish_v3_formal_snapshot import publish_formal_snapshot
    from scripts.verify_v3_formal_snapshot import verify_formal_snapshot

    result = publish_formal_snapshot(output_root=tmp_path)
    snapshot_dir = Path(result["path"])
    assert result["status"] == "published"
    assert (snapshot_dir / "manifest.json").exists()
    assert not any(snapshot_dir.glob("*.parquet"))
    verified = verify_formal_snapshot(snapshot_dir)
    assert verified["status"] == "valid"
    assert verified["snapshot_id"] == result["snapshot_id"]


def test_v3_formal_snapshot_rejects_coverage_data_fault(tmp_path: Path):
    from scripts.publish_v3_formal_snapshot import publish_formal_snapshot

    coverage_dir = tmp_path / "coverage"
    shutil.copytree(COVERAGE_DIR, coverage_dir)
    manifest_path = coverage_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["coverage"]["data_fault_count"] = 1
    identity_payload = dict(manifest)
    identity_payload.pop("artifact_id", None)
    manifest["artifact_id"] = hashlib.sha256(json.dumps(identity_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()[:16]
    raw = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    manifest_path.write_bytes(raw)
    (coverage_dir / "manifest.json.sha256").write_text(hashlib.sha256(raw).hexdigest() + "  manifest.json\n", encoding="utf-8")

    with pytest.raises(ValueError, match="data_fault"):
        publish_formal_snapshot(output_root=tmp_path / "out", coverage_dir=coverage_dir)


def test_v3_formal_snapshot_rejects_tampered_scope_and_source(tmp_path: Path):
    from scripts.publish_v3_formal_snapshot import publish_formal_snapshot

    result = publish_formal_snapshot(output_root=tmp_path / "out")
    snapshot_dir = Path(result["path"])
    manifest_path = snapshot_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["v3_qualification"]["scope"]["manifest_sha256"] = "0" * 64
    manifest["manifest_content_hash"] = ""
    manifest["manifest_content_hash"] = hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    raw = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    manifest_path.write_bytes(raw)
    (snapshot_dir / "manifest.json.sha256").write_text(hashlib.sha256(raw).hexdigest() + "  manifest.json\n", encoding="utf-8")
    with pytest.raises(ValueError, match="qualification binding"):
        from scripts.verify_v3_formal_snapshot import verify_formal_snapshot

        verify_formal_snapshot(snapshot_dir)


def test_v3_false_authorization_requires_complete_qualification_fields():
    from backend.services.b3_protocol_types import DataSnapshotManifest

    with pytest.raises(ValueError, match="v3"):
        DataSnapshotManifest.model_validate(
            {
                "snapshot_id": "v3_snapshot",
                "provider": "traderlens_pit",
                "retrieval_date": None,
                "market_data_start": "2024-06-07",
                "market_data_end": "2026-07-10",
                "universe_snapshot_ids": ["pims_traderlens_v2_shsz_sw2021_pit_005"],
                "semantic_hash": "a" * 64,
                "quality_status": "ok",
                "gaps": ["availability_bounded"],
                "frozen": True,
                "not_authorized_for_b6_oos_gate_promotion_signal": False,
                "schema_version": "v3_formal_data_snapshot.v1",
            }
        )


def test_legacy_snapshot_still_parses_and_verifies():
    from backend.services.b3_protocol_types import DataSnapshotManifest
    from scripts.verify_v2_formal_snapshot import verify_data_snapshot

    manifest = json.loads((LEGACY_SNAPSHOT_DIR / "manifest.json").read_text(encoding="utf-8"))
    parsed = DataSnapshotManifest.model_validate(manifest)
    assert parsed.not_authorized_for_b6_oos_gate_promotion_signal is True
    assert verify_data_snapshot(LEGACY_SNAPSHOT_DIR, manifest["semantic_hash"])["status"] == "valid"


def test_v3_formal_snapshot_is_write_once(tmp_path: Path):
    from scripts.publish_v3_formal_snapshot import publish_formal_snapshot

    first = publish_formal_snapshot(output_root=tmp_path)
    second = publish_formal_snapshot(output_root=tmp_path)
    assert second["status"] == "already_published"
    manifest_path = Path(first["path"]) / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["snapshot_id"] = "tampered"
    raw = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    manifest_path.write_bytes(raw)
    with pytest.raises(ValueError, match="write-once"):
        publish_formal_snapshot(output_root=tmp_path)
