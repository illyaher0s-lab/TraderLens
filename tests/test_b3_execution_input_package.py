from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.services.b3_execution_input_binding import (
    B3ExecutionInputBinding,
    ExecutionInputReference,
    validate_execution_input_binding,
)
from scripts.publish_b3_execution_input_package import (
    ARTIFACT_ID,
    PackagePublicationError,
    publish_package,
)
from scripts.verify_b3_execution_input_package import verify_package


PHYSICAL_INTERFACES = (
    "daily",
    "daily_basic",
    "adj_factor",
    "stk_limit",
    "suspend_d",
    "stock_st",
    "trade_cal",
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_source(root: Path) -> None:
    for name in PHYSICAL_INTERFACES:
        part = root / name / "trade_date=20240102" / "part.parquet"
        part.parent.mkdir(parents=True, exist_ok=True)
        part.write_bytes(f"{name}-content".encode())
        sidecar = part.with_name("part.parquet.sha256")
        sidecar.write_text(f"{_sha(part.read_bytes())}  part.parquet\n", encoding="utf-8")


def _spec() -> dict:
    requirements = {
        "membership": {"requirement": "required", "reason": "PIT universe"},
        "daily": {"requirement": "required", "reason": "raw OHLCV"},
        "daily_basic": {"requirement": "required", "reason": "formal coverage input"},
        "adj_factor": {"requirement": "required", "reason": "adjusted close"},
        "stk_limit": {"requirement": "required", "reason": "open-limit fill guard"},
        "suspend_d": {"requirement": "required", "reason": "suspension fill guard"},
        "stock_st": {"requirement": "required", "reason": "ST exclusion"},
        "trade_cal": {"requirement": "required", "reason": "T+1 calendar"},
        "listing_delisting": {
            "requirement": "required",
            "reason": "delisting_risk is frozen",
        },
        "liquidity": {
            "requirement": "required",
            "reason": "min_avg_amount_20d is frozen",
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
            "data_snapshot_id": "ds_test",
            "data_snapshot_semantic_hash": "c" * 64,
            "data_snapshot_manifest_sha256": "d" * 64,
            "pit_membership_snapshot_id": "pims_test",
            "pit_membership_manifest_sha256": "e" * 64,
            "pit_membership_canonical_content_hash": "f" * 64,
            "pit_membership_records_parquet_sha256": "1" * 64,
            "coverage_package_id": "coverage_test",
            "coverage_manifest_sha256": "2" * 64,
            "coverage_algorithm_hash": "3" * 64,
            "coverage_by_code_sha256": "4" * 64,
            "coverage_by_date_sha256": "5" * 64,
            "coverage_unavailable_sha256": "6" * 64,
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
        "interface_policy": requirements,
    }


def _publish(tmp_path: Path, *, artifact_id: str = ARTIFACT_ID) -> tuple[Path, dict]:
    source = tmp_path / "source"
    packages = tmp_path / "packages"
    _write_source(source)
    result = publish_package(
        repo_root=tmp_path,
        source_root=source,
        packages_root=packages,
        artifact_id=artifact_id,
        spec=_spec(),
        published_at="2026-07-25T00:00:00+08:00",
        copy_workers=2,
    )
    return packages / artifact_id, result


def _verified_ref(name: str, path: str, content_hash: str) -> ExecutionInputReference:
    return ExecutionInputReference(
        name=name,
        requirement="required",
        requirement_reason="required by test",
        availability="verified",
        path=path,
        content_hash=content_hash,
        byte_size=1,
    )


def test_reference_contract_rejects_legacy_and_invalid_states() -> None:
    with pytest.raises(ValidationError):
        ExecutionInputReference(
            name="daily",
            requirement="required",
            availability="available",
            path="inputs/daily",
            content_hash="a" * 64,
            byte_size=1,
        )
    with pytest.raises(ValidationError):
        ExecutionInputReference(
            name="daily",
            requirement="required",
            availability="verified",
            path="inputs/daily",
            content_hash="placeholder",
            byte_size=1,
        )
    with pytest.raises(ValidationError):
        ExecutionInputReference(
            name="daily",
            requirement="not_required",
            requirement_reason="",
            availability="unavailable",
            path="",
            content_hash="",
        )


def test_required_unavailable_is_valid_but_binding_is_rejected(tmp_path: Path) -> None:
    unavailable = ExecutionInputReference(
        name="listing_delisting",
        requirement="required",
        requirement_reason="required by frozen template",
        availability="unavailable",
        path="",
        content_hash="",
    )
    membership_dir = tmp_path / "membership"
    membership_dir.mkdir()
    manifest = membership_dir / "manifest.json"
    manifest.write_bytes(b"{}")
    membership = _verified_ref(
        "membership",
        "membership",
        _sha(manifest.read_bytes()),
    )
    physical = _verified_ref("physical", "membership/manifest.json", _sha(b"{}"))
    binding = B3ExecutionInputBinding(
        binding_id="binding",
        membership_ref=membership,
        daily_ref=physical.model_copy(update={"name": "daily"}),
        daily_basic_ref=physical.model_copy(update={"name": "daily_basic"}),
        adj_factor_ref=physical.model_copy(update={"name": "adj_factor"}),
        stk_limit_ref=physical.model_copy(update={"name": "stk_limit"}),
        suspend_ref=physical.model_copy(update={"name": "suspend_d"}),
        stock_st_ref=physical.model_copy(update={"name": "stock_st"}),
        trade_cal_ref=physical.model_copy(update={"name": "trade_cal"}),
        listing_delisting_ref=unavailable,
        liquidity_ref=unavailable.model_copy(update={"name": "liquidity"}),
        announcement_ref=ExecutionInputReference(
            name="announcement",
            requirement="not_required",
            requirement_reason="forbidden by template",
            availability="unavailable",
            path="",
            content_hash="",
        ),
    )
    result = validate_execution_input_binding(binding, tmp_path)
    assert not result.is_valid
    assert "listing_delisting" in result.error


def test_publisher_builds_complete_canonical_package_in_temp_root(tmp_path: Path) -> None:
    package, result = _publish(tmp_path)
    assert result["status"] == "published"
    assert result["package_status"] == "incomplete"
    assert package.is_dir()

    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    index = json.loads((package / "input_index.json").read_text(encoding="utf-8"))

    required_manifest_keys = {
        "artifact_id",
        "schema_version",
        "status",
        "authorization_scope",
        "frozen",
        "formal_input_root_repo_relative",
        "input_index_sha256",
        "input_index_algorithm_id",
        "input_index_algorithm_hash",
        "required_interface_policy_hash",
        "template_id",
        "template_version",
        "template_hash",
        "data_requirements_hash",
        "interfaces",
        "exact_bindings",
        "source_authorization_disclosures",
        "manifest_content_hash",
        "published_at",
    }
    assert required_manifest_keys <= manifest.keys()
    assert set(index["interfaces"]) == set(PHYSICAL_INTERFACES)
    assert manifest["interfaces"]["daily_basic"]["availability"] == "verified"
    assert manifest["interfaces"]["listing_delisting"]["availability"] == "unavailable"
    assert manifest["interfaces"]["liquidity"]["availability"] == "unavailable"
    assert manifest["interfaces"]["announcement"]["requirement"] == "not_required"
    assert manifest["status"] == "incomplete"

    for interface in index["interfaces"].values():
        for entry in interface["entries"]:
            assert not Path(entry["path"]).is_absolute()
            assert ".staging" not in entry["path"]
            assert entry["path"].startswith(
                f"data/pit/b3_execution_input_packages/{ARTIFACT_ID}/inputs/"
            )
            assert len(entry["sha256"]) == 64

    verification = verify_package(package, tmp_path, expected_artifact_id=ARTIFACT_ID)
    assert verification == {"is_valid": True, "errors": []}


def test_publisher_verifies_before_atomic_publish_and_cleans_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    packages = tmp_path / "packages"
    _write_source(source)

    import scripts.publish_b3_execution_input_package as publisher

    monkeypatch.setattr(
        publisher,
        "verify_package",
        lambda *args, **kwargs: {"is_valid": False, "errors": ["forced"]},
    )
    with pytest.raises(PackagePublicationError, match="pre-publication verification"):
        publish_package(
            repo_root=tmp_path,
            source_root=source,
            packages_root=packages,
            artifact_id=ARTIFACT_ID,
            spec=_spec(),
            published_at="2026-07-25T00:00:00+08:00",
        )
    assert not (packages / ARTIFACT_ID).exists()
    assert not list(packages.glob(".staging_*"))


def test_write_once_recomputes_same_content_and_rejects_conflict(tmp_path: Path) -> None:
    package, first = _publish(tmp_path)
    source = tmp_path / "source"
    packages = tmp_path / "packages"
    second = publish_package(
        repo_root=tmp_path,
        source_root=source,
        packages_root=packages,
        artifact_id=ARTIFACT_ID,
        spec=_spec(),
        published_at="2099-01-01T00:00:00+00:00",
        copy_workers=2,
    )
    assert first["status"] == "published"
    assert second["status"] == "already_published"

    (source / "daily" / "trade_date=20240102" / "part.parquet").write_bytes(
        b"changed"
    )
    with pytest.raises(PackagePublicationError, match="content_conflict"):
        publish_package(
            repo_root=tmp_path,
            source_root=source,
            packages_root=packages,
            artifact_id=ARTIFACT_ID,
            spec=_spec(),
            published_at="2099-01-01T00:00:00+00:00",
            copy_workers=2,
        )
    assert verify_package(package, tmp_path, ARTIFACT_ID)["is_valid"]


@pytest.mark.parametrize(
    "tamper, expected",
    [
        ("input_file", "hash mismatch"),
        ("extra_file", "extra file"),
        ("input_index", "input_index.json.sha256 mismatch"),
        ("manifest", "manifest.json.sha256 mismatch"),
    ],
)
def test_verifier_fails_loud_on_tamper(
    tmp_path: Path, tamper: str, expected: str
) -> None:
    package, _ = _publish(tmp_path)
    if tamper == "input_file":
        next((package / "inputs").rglob("*.parquet")).write_bytes(b"tampered")
    elif tamper == "extra_file":
        (package / "inputs" / "daily" / "extra.parquet").write_bytes(b"extra")
    elif tamper == "input_index":
        (package / "input_index.json").write_text("{}", encoding="utf-8")
    else:
        (package / "manifest.json").write_text("{}", encoding="utf-8")

    result = verify_package(package, tmp_path, ARTIFACT_ID)
    assert not result["is_valid"]
    assert any(expected in error for error in result["errors"])


def test_verifier_rejects_registered_path_escape(tmp_path: Path) -> None:
    package, _ = _publish(tmp_path)
    index_path = package / "input_index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index["interfaces"]["daily"]["entries"][0]["path"] = "../escape.parquet"
    raw = json.dumps(index, sort_keys=True, separators=(",", ":")).encode()
    index_path.write_bytes(raw)
    (package / "input_index.json.sha256").write_text(
        f"{_sha(raw)}  input_index.json\n", encoding="utf-8"
    )
    result = verify_package(package, tmp_path, ARTIFACT_ID)
    assert not result["is_valid"]
    assert any("path escape" in error for error in result["errors"])


def test_verifier_rejects_authorization_disclosure_rewrite(tmp_path: Path) -> None:
    package, _ = _publish(tmp_path)
    manifest_path = package / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["source_authorization_disclosures"]["data_snapshot"][
        "not_authorized_for_b6_oos_gate_promotion_signal"
    ] = False
    semantic = {
        key: value
        for key, value in manifest.items()
        if key not in {"manifest_content_hash", "published_at"}
    }
    manifest["manifest_content_hash"] = _sha(
        json.dumps(
            semantic,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    )
    raw = json.dumps(
        manifest,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    manifest_path.write_bytes(raw)
    (package / "manifest.json.sha256").write_text(
        f"{_sha(raw)}  manifest.json\n",
        encoding="utf-8",
    )
    result = verify_package(package, tmp_path, ARTIFACT_ID)
    assert not result["is_valid"]
    assert any("authorization disclosure" in error for error in result["errors"])


def test_verifier_rejects_symlink_or_junction_input(tmp_path: Path) -> None:
    package, _ = _publish(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    link = package / "inputs" / "linked"
    if os.name == "nt":
        completed = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(outside)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
    else:
        link.symlink_to(outside, target_is_directory=True)

    result = verify_package(package, tmp_path, ARTIFACT_ID)
    assert not result["is_valid"]
    assert any("symlink" in error or "junction" in error for error in result["errors"])


def test_manifest_and_index_identity_are_deterministic(tmp_path: Path) -> None:
    package_a, _ = _publish(tmp_path / "a")
    package_b, _ = _publish(tmp_path / "b")
    manifest_a = json.loads((package_a / "manifest.json").read_text(encoding="utf-8"))
    manifest_b = json.loads((package_b / "manifest.json").read_text(encoding="utf-8"))
    index_a = json.loads((package_a / "input_index.json").read_text(encoding="utf-8"))
    index_b = json.loads((package_b / "input_index.json").read_text(encoding="utf-8"))
    assert index_a["input_index_hash"] == index_b["input_index_hash"]
    assert manifest_a["manifest_content_hash"] == manifest_b["manifest_content_hash"]
