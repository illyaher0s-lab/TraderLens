import hashlib
import json
from pathlib import Path

import pytest

from scripts.publish_market_regime_v12_owner_approval import (
    canonical,
    publish_owner_approval,
)
from scripts.verify_market_regime_v12_owner_approval import verify_owner_approval


def _write_sidecar(path: Path) -> None:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    path.with_name(path.name + ".sha256").write_text(f"{digest}  {path.name}\n", encoding="utf-8")


def test_publish_and_verify_exact_v12_owner_approval(tmp_path: Path) -> None:
    published = publish_owner_approval(output_root=tmp_path)
    assert published["status"] == "published"
    verified = verify_owner_approval(Path(published["path"]))
    assert verified["status"] == "verified"
    assert verified["artifact_id"] == published["artifact_id"]


def test_config_or_qualification_tamper_is_rejected(tmp_path: Path) -> None:
    published = publish_owner_approval(output_root=tmp_path / "approval")
    copied_config = tmp_path / "market_regime_thresholds.yaml"
    copied_config.write_bytes(
        Path(r"D:\Codex\TraderLens\backend\config\market_regime_thresholds.yaml").read_bytes()
        + b"\n# tampered\n"
    )
    with pytest.raises(ValueError, match="config.*hash"):
        verify_owner_approval(Path(published["path"]), config_path=copied_config)


def test_owner_or_decision_mismatch_is_rejected(tmp_path: Path) -> None:
    published = publish_owner_approval(output_root=tmp_path / "approval")
    manifest_path = Path(published["path"]) / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["authorized_by"] = "different-owner"
    payload = {key: value for key, value in manifest.items() if key != "artifact_id"}
    manifest["artifact_id"] = hashlib.sha256(canonical(payload)).hexdigest()[:16]
    manifest_path.write_bytes(canonical(manifest))
    _write_sidecar(manifest_path)
    with pytest.raises(ValueError, match="owner|authorization"):
        verify_owner_approval(Path(published["path"]))


def test_write_once_conflict_is_rejected(tmp_path: Path) -> None:
    first = publish_owner_approval(output_root=tmp_path / "approval")
    manifest_path = Path(first["path"]) / "manifest.json"
    manifest_path.write_bytes(manifest_path.read_bytes() + b"tamper")
    with pytest.raises(ValueError, match="write-once|sidecar"):
        publish_owner_approval(output_root=tmp_path / "approval")
