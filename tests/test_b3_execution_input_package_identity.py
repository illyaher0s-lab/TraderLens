from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.publish_b3_execution_input_package import (
    ARTIFACT_ID,
    PackagePublicationError,
    publish_package,
)
from scripts.verify_b3_execution_input_package import verify_package


SUCCESSOR_ARTIFACT_ID = "b3eip_traderlens_v2_shsz_pit_002"
PHYSICAL_INTERFACES = (
    "daily",
    "daily_basic",
    "adj_factor",
    "stk_limit",
    "suspend_d",
    "stock_st",
    "trade_cal",
)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_with_sidecar(path: Path, raw: bytes) -> str:
    path.write_bytes(raw)
    digest = _sha(raw)
    path.with_name(f"{path.name}.sha256").write_text(
        f"{digest}  {path.name}\n",
        encoding="utf-8",
    )
    return digest


def _spec() -> dict:
    policy = {
        "membership": {"requirement": "required", "reason": "PIT universe"},
        **{
            name: {"requirement": "required", "reason": f"required {name}"}
            for name in PHYSICAL_INTERFACES
        },
        "listing_delisting": {
            "requirement": "required",
            "reason": "listing evidence required",
        },
        "liquidity": {
            "requirement": "required",
            "reason": "liquidity evidence required",
        },
        "announcement": {
            "requirement": "not_required",
            "reason": "announcement evidence is forbidden",
        },
    }
    return {
        "template": {
            "template_id": "relative_strength_rotation_shsz_sw2021_v2",
            "template_version": "v2_shsz_sw2021_pit_12m",
            "template_hash": "a" * 64,
            "data_requirements_hash": "b" * 64,
        },
        "exact_bindings": {
            "pit_membership_canonical_content_hash": "c" * 64,
        },
        "source_authorization_disclosures": {
            "data_snapshot": {
                "not_authorized_for_b6_oos_gate_promotion_signal": True,
            },
            "pit_membership_snapshot": {
                "not_authorized_for_b6_oos_gate_promotion_signal": True,
            },
            "qualification_successor": {
                "not_authorized_for_b6_oos_gate_promotion_signal_or_data_collection": True,
            },
        },
        "interface_policy": policy,
    }


def _write_source(root: Path) -> None:
    for name in PHYSICAL_INTERFACES:
        part = root / name / "trade_date=20240102" / "part.parquet"
        part.parent.mkdir(parents=True, exist_ok=True)
        part.write_bytes(f"{name}-test-data".encode())


def _publish(tmp_path: Path, artifact_id: str = ARTIFACT_ID) -> Path:
    source_root = tmp_path / "source"
    packages_root = tmp_path / "packages"
    _write_source(source_root)
    publish_package(
        repo_root=tmp_path,
        source_root=source_root,
        packages_root=packages_root,
        artifact_id=artifact_id,
        spec=_spec(),
        published_at="2026-10-04T00:00:00+08:00",
        copy_workers=2,
    )
    return packages_root / artifact_id


def _rebind_package_identity(
    package: Path,
    *,
    old_artifact_id: str,
    artifact_id: str,
    index_artifact_id: str | None = None,
) -> None:
    index_artifact_id = index_artifact_id or artifact_id
    old_root = f"data/pit/b3_execution_input_packages/{old_artifact_id}/inputs"
    index_root = f"data/pit/b3_execution_input_packages/{index_artifact_id}/inputs"
    manifest_root = f"data/pit/b3_execution_input_packages/{artifact_id}/inputs"
    index_path = package / "input_index.json"
    manifest_path = package / "manifest.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    index["formal_input_root_repo_relative"] = index_root
    for interface in index["interfaces"].values():
        interface["entries"] = [
            {
                **entry,
                "path": entry["path"].replace(old_root, index_root, 1),
            }
            for entry in interface["entries"]
        ]
        interface["entry_count"] = len(interface["entries"])
        interface["total_bytes"] = sum(
            entry["byte_size"] for entry in interface["entries"]
        )
        interface["interface_content_hash"] = _sha(
            _canonical(interface["entries"])
        )
    index_payload = {
        key: index.get(key)
        for key in (
            "schema_version",
            "algorithm_id",
            "algorithm_hash",
            "formal_input_root_repo_relative",
            "interfaces",
            "exact_bindings",
        )
    }
    index["input_index_hash"] = _sha(_canonical(index_payload))
    index_sha = _write_with_sidecar(index_path, _canonical(index))

    manifest["artifact_id"] = artifact_id
    manifest["formal_input_root_repo_relative"] = manifest_root
    manifest["input_index_sha256"] = index_sha
    for name in PHYSICAL_INTERFACES:
        for key in ("entry_count", "total_bytes", "interface_content_hash"):
            manifest["interfaces"][name][key] = index["interfaces"][name][key]
    semantic = {
        key: value
        for key, value in manifest.items()
        if key not in {"manifest_content_hash", "published_at"}
    }
    manifest["manifest_content_hash"] = _sha(_canonical(semantic))
    _write_with_sidecar(manifest_path, _canonical(manifest))


def test_legacy_artifact_id_remains_the_default(tmp_path: Path) -> None:
    package = _publish(tmp_path)

    assert package.is_dir()
    assert verify_package(package, tmp_path) == {"is_valid": True, "errors": []}


def test_successor_artifact_can_be_published_and_verified(tmp_path: Path) -> None:
    package = _publish(tmp_path, SUCCESSOR_ARTIFACT_ID)

    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    index = json.loads((package / "input_index.json").read_text(encoding="utf-8"))
    expected_root = (
        f"data/pit/b3_execution_input_packages/{SUCCESSOR_ARTIFACT_ID}/inputs"
    )

    assert manifest["artifact_id"] == SUCCESSOR_ARTIFACT_ID
    assert manifest["formal_input_root_repo_relative"] == expected_root
    assert index["formal_input_root_repo_relative"] == expected_root
    assert verify_package(
        package,
        tmp_path,
        expected_artifact_id=SUCCESSOR_ARTIFACT_ID,
    ) == {"is_valid": True, "errors": []}


def test_verifier_binds_index_root_to_explicit_successor_id(tmp_path: Path) -> None:
    package = _publish(tmp_path)
    _rebind_package_identity(
        package,
        old_artifact_id=ARTIFACT_ID,
        artifact_id=SUCCESSOR_ARTIFACT_ID,
    )

    result = verify_package(
        package,
        tmp_path,
        expected_artifact_id=SUCCESSOR_ARTIFACT_ID,
    )

    assert result == {"is_valid": True, "errors": []}


def test_verifier_rejects_wrong_id_root_and_input_hash(tmp_path: Path) -> None:
    package = _publish(tmp_path)
    _rebind_package_identity(
        package,
        old_artifact_id=ARTIFACT_ID,
        artifact_id=SUCCESSOR_ARTIFACT_ID,
    )

    wrong_id = verify_package(package, tmp_path)
    assert not wrong_id["is_valid"]
    assert any("artifact id mismatch" in error for error in wrong_id["errors"])

    _rebind_package_identity(
        package,
        old_artifact_id=SUCCESSOR_ARTIFACT_ID,
        artifact_id=SUCCESSOR_ARTIFACT_ID,
        index_artifact_id="b3eip_traderlens_v2_shsz_pit_003",
    )
    wrong_root = verify_package(
        package,
        tmp_path,
        expected_artifact_id=SUCCESSOR_ARTIFACT_ID,
    )
    assert not wrong_root["is_valid"]
    assert any("formal input root mismatch" in error for error in wrong_root["errors"])

    part = next((package / "inputs").rglob("*.parquet"))
    part.write_bytes(b"tampered")
    wrong_hash = verify_package(
        package,
        tmp_path,
        expected_artifact_id=SUCCESSOR_ARTIFACT_ID,
    )
    assert not wrong_hash["is_valid"]
    assert any("hash mismatch" in error for error in wrong_hash["errors"])


def test_publisher_rejects_unallocated_successor_id(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    _write_source(source_root)

    try:
        publish_package(
            repo_root=tmp_path,
            source_root=source_root,
            packages_root=tmp_path / "packages",
            artifact_id="b3eip_traderlens_v2_shsz_pit_003",
            spec=_spec(),
        )
    except PackagePublicationError as exc:
        assert "unallocated artifact id" in str(exc)
    else:
        raise AssertionError("unallocated artifact id should be rejected")



def _stub_production_spec_artifacts(monkeypatch, tmp_path: Path) -> None:
    from scripts import publish_b3_execution_input_package as publisher

    expected = publisher.EXPECTED
    data_manifest = (
        tmp_path
        / "data/pit/data_snapshot_manifests"
        / expected["data_snapshot_id"]
        / "manifest.json"
    )
    membership_root = (
        tmp_path
        / "data/pit/pit_membership_snapshots"
        / expected["pit_membership_snapshot_id"]
    )
    membership_manifest = membership_root / "manifest.json"
    coverage_root = tmp_path / "data/pit/coverage_packages" / expected["coverage_package_id"]
    coverage_manifest = coverage_root / "coverage_manifest.json"
    successor_manifest = (
        tmp_path / "data/pit/qualification_successors/e5100669ed247769/manifest.json"
    )
    artifacts = {
        data_manifest: {
            "semantic_hash": expected["data_snapshot_semantic_hash"],
            "not_authorized_for_b6_oos_gate_promotion_signal": True,
        },
        membership_manifest: {
            "canonical_content_hash": expected["pit_membership_canonical_content_hash"],
            "not_authorized_for_b6_oos_gate_promotion_signal": True,
        },
        coverage_manifest: {"algorithm_hash": expected["coverage_algorithm_hash"]},
        successor_manifest: {
            "successor_id": "test_successor",
            "template_id": "relative_strength_rotation_shsz_sw2021_v2",
            "template_hash": "test_template_hash",
            "not_authorized_for_b6_oos_gate_promotion_signal_or_data_collection": True,
        },
    }

    monkeypatch.setattr(publisher, "_assert_file_hash", lambda *_args: None)
    monkeypatch.setattr(publisher, "_load_json", lambda path: artifacts[Path(path)])


def test_production_spec_converts_only_the_exact_approved_template(
    monkeypatch, tmp_path: Path
) -> None:
    from backend.services import strategy_template_library as library
    from scripts.publish_b3_execution_input_package import build_production_spec

    _stub_production_spec_artifacts(monkeypatch, tmp_path)
    template_id = "relative_strength_rotation_shsz_sw2021_v2"
    real_convert = library.convert_to_frozen_contract
    converted = []

    def reject_unrelated_template(template, created_at):
        if template.template_id != template_id:
            raise RuntimeError("unrelated template conversion failed")
        result = real_convert(template, created_at)
        converted.append(result)
        return result

    monkeypatch.setattr(library, "convert_to_frozen_contract", reject_unrelated_template)

    spec = build_production_spec(tmp_path)

    assert len(converted) == 1
    assert converted[0].governance_status == "approved"
    assert converted[0].template_hash == (
        "867a47eeece1c0d208c591f35b5ca31d663ccda183c8721eef803483921238b6"
    )
    assert converted[0].data_requirements_hash == (
        "1910d7a598b1008fb5ba6ee69833e174b5a9949f31a998e2fced436950d8df04"
    )
    assert converted[0].review_evidence_sha256 == (
        "ab4391a42ade48c2319dc15bec6799a0280fbbe4ae75dc49bd1a51f403935194"
    )
    assert spec["template"]["template_hash"] == converted[0].template_hash
    assert spec["template"]["data_requirements_hash"] == converted[0].data_requirements_hash


def test_production_spec_rejects_nonapproved_template_contracts(
    monkeypatch, tmp_path: Path
) -> None:
    import pytest
    from backend.services import strategy_template_library as library
    from scripts.publish_b3_execution_input_package import (
        PackagePublicationError,
        build_production_spec,
    )

    _stub_production_spec_artifacts(monkeypatch, tmp_path)
    template = library.get_template_by_id("relative_strength_rotation_shsz_sw2021_v2")
    assert template is not None
    real_convert = library.convert_to_frozen_contract

    for status in ("candidate", "rejected"):
        def return_nonapproved(_template, created_at, *, forced_status=status):
            return real_convert(_template, created_at).model_copy(
                update={"governance_status": forced_status}
            )

        monkeypatch.setattr(library, "convert_to_frozen_contract", return_nonapproved)
        with pytest.raises(
            PackagePublicationError,
            match="exact V2 template is not approved",
        ):
            build_production_spec(tmp_path)
