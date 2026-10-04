from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from scripts import verify_v3_b5_bundle as b5_verifier


CODE_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT = Path(
    os.environ.get("TRADERLENS_FORMAL_ARTIFACT_ROOT", CODE_ROOT)
)
requires_artifacts = pytest.mark.skipif(
    not (ARTIFACT_ROOT / "data/pit/strategy_scoped_universe_snapshots").is_dir(),
    reason="explicit formal artifact root is not available",
)


def _manifest(directory: Path) -> tuple[dict, str]:
    raw = (directory / "manifest.json").read_bytes()
    return json.loads(raw.decode("utf-8")), hashlib.sha256(raw).hexdigest()


def test_b5_verifier_identity_pins_formal_partition_adapter(monkeypatch):
    from backend.services import v3_b5_bundle

    adapter_path = "backend/services/formal_pit_partition_adapter.py"
    adapter_file = CODE_ROOT / Path(*adapter_path.split("/"))
    identity = v3_b5_bundle.independent_verifier_identity()
    assert identity["formal_pit_partition_adapter_path"] == adapter_path
    assert identity["formal_pit_partition_adapter_sha256"] == hashlib.sha256(
        adapter_file.read_bytes()
    ).hexdigest()

    original_sha = v3_b5_bundle._sha
    monkeypatch.setattr(
        v3_b5_bundle,
        "_sha",
        lambda path: "f" * 64
        if Path(path).resolve() == adapter_file.resolve()
        else original_sha(path),
    )
    changed_identity = v3_b5_bundle.independent_verifier_identity()

    assert changed_identity["formal_pit_partition_adapter_sha256"] == "f" * 64
    assert changed_identity != identity
    assert v3_b5_bundle._bundle_core({}, {}, identity) != v3_b5_bundle._bundle_core(
        {}, {}, changed_identity
    )


@requires_artifacts
def test_first_generation_scope_remains_bound_to_unavailable_legacy_source():
    directory = (
        ARTIFACT_ROOT
        / "data/pit/strategy_scoped_universe_snapshots/ssu_0f44212e732ab5fe7deb27d9"
    )
    manifest, manifest_sha256 = _manifest(directory)
    active_source_sha256 = hashlib.sha256(
        (CODE_ROOT / "backend/services/strategy_scoped_pit_universe.py").read_bytes()
    ).hexdigest()

    assert manifest_sha256 == "3fde1a273cdbed30f2ad83fa76a93565115f258466a5d328b6af5e259f39cb4f"
    assert manifest["algorithm"]["source_sha256"] == (
        "caf79df880e5d7ee606762caa9dd8a43e993cef427aa965aaf3192b11af11845"
    )
    assert manifest["algorithm"]["source_sha256"] != active_source_sha256


@requires_artifacts
def test_second_generation_b5_keeps_its_legacy_scope_identity_explicit():
    directory = ARTIFACT_ROOT / "data/pit/v3_b5_validation_bundles/2921eb33c975501f"
    manifest, manifest_sha256 = _manifest(directory)
    scope = manifest["lineage"]["strategy_scoped_universe"]

    assert manifest_sha256 == "18d0743384927e602e5d2243d31034850d3f44989a40930354ab841e2494ed89"
    assert scope["snapshot_id"] == "ssu_0f44212e732ab5fe7deb27d9"
    assert scope["manifest_sha256"] == (
        "3fde1a273cdbed30f2ad83fa76a93565115f258466a5d328b6af5e259f39cb4f"
    )


def test_b5_verifier_uses_explicit_roots_and_exact_bundle_identity(monkeypatch, tmp_path):
    code_root = CODE_ROOT
    artifact_root = tmp_path / "artifacts"
    bundle_dir = artifact_root / "data/pit/v3_b5_validation_bundles/bundle_exact"
    bundle_dir.mkdir(parents=True)
    manifest_path = bundle_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps({
            "bundle_id": bundle_dir.name,
            "lineage": {"strategy_scoped_universe": {
                "snapshot_id": "ssu_exact",
                "manifest_sha256": "a" * 64,
            }},
        }),
        encoding="utf-8",
    )
    expected_manifest_sha256 = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    calls = []

    monkeypatch.setattr(
        b5_verifier,
        "load_verified_results",
        lambda root, **kwargs: calls.append(("load", root, kwargs)) or {},
    )
    monkeypatch.setattr(
        b5_verifier,
        "verify_b5_bundle",
        lambda root, directory, **kwargs: calls.append(
            ("verify", root, directory, kwargs)
        ) or {"status": "invalid", "reason": "test boundary"},
    )

    result = b5_verifier.verify_verified_b5_bundle(
        artifact_root,
        bundle_dir,
        code_root=code_root,
        artifact_root=artifact_root,
        expected_bundle_id=bundle_dir.name,
        expected_bundle_manifest_sha256=expected_manifest_sha256,
        strategy_scope_root=artifact_root / "data/pit/strategy_scoped_universe_snapshots",
    )

    assert result == {"status": "invalid", "reason": "test boundary"}
    assert calls[0][0:2] == ("load", artifact_root)
    assert calls[0][2]["code_root"] == code_root
    assert calls[0][2]["artifact_root"] == artifact_root
    assert calls[0][2]["strategy_scope_root"] == artifact_root / "data/pit/strategy_scoped_universe_snapshots"
    assert calls[0][2]["expected_scope_id"] == "ssu_exact"
    assert calls[0][2]["expected_scope_manifest_sha256"] == "a" * 64
    assert calls[1][0:3] == ("verify", artifact_root, bundle_dir)
    assert calls[1][3]["expected_bundle_id"] == bundle_dir.name
    assert calls[1][3]["expected_bundle_manifest_sha256"] == expected_manifest_sha256


def test_b5_verifier_rejects_wrong_manifest_pin_before_loading_inputs(monkeypatch, tmp_path):
    artifact_root = tmp_path / "artifacts"
    bundle_dir = artifact_root / "bundle_wrong_pin"
    bundle_dir.mkdir(parents=True)
    (bundle_dir / "manifest.json").write_text(
        json.dumps({"bundle_id": bundle_dir.name}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        b5_verifier,
        "load_verified_results",
        lambda *_args, **_kwargs: pytest.fail("wrong pin must fail before source loading"),
    )

    result = b5_verifier.verify_verified_b5_bundle(
        artifact_root,
        bundle_dir,
        code_root=CODE_ROOT,
        expected_bundle_id="bundle_wrong_pin",
        expected_bundle_manifest_sha256="0" * 64,
    )

    assert result == {
        "status": "invalid",
        "reason": "bundle manifest hash does not match the requested hash",
    }
