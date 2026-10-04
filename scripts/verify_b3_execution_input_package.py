#!/usr/bin/env python3
"""Independent verifier for an immutable B3 execution-input package."""

from __future__ import annotations

import argparse
import hashlib
import json
import stat
import sys
from pathlib import Path, PurePosixPath


ARTIFACT_ID = "b3eip_traderlens_v2_shsz_pit_001"
SCHEMA_VERSION = "b3_execution_input_package.v1"
INDEX_SCHEMA_VERSION = "b3_execution_input_index.v1"
AUTHORIZATION_SCOPE = "b3_execution_input_binding_only"
PHYSICAL_INTERFACES = (
    "daily",
    "daily_basic",
    "adj_factor",
    "stk_limit",
    "suspend_d",
    "stock_st",
    "trade_cal",
)
ALGORITHM = {
    "algorithm_id": "sha256_sorted_repo_relative_files_v1",
    "file_hash": "sha256(raw_bytes)",
    "interface_hash": "sha256(canonical_json(sorted_entries))",
    "index_hash": "sha256(canonical_json(index_without_input_index_hash))",
}
PRODUCTION_EXACT_BINDINGS = {
    "data_snapshot_id": "ds_traderlens_v2_shsz_pit_001",
    "data_snapshot_semantic_hash": (
        "da057716d4b4162b89fb89b7fd15864b4385d65cdee4e760a0743108cf1b135e"
    ),
    "data_snapshot_manifest_sha256": (
        "4c4552a86afa09c5936db85d0c65df85fe28445d87b2372783a5c3f7281b0736"
    ),
    "pit_membership_snapshot_id": "pims_traderlens_v2_shsz_sw2021_pit_005",
    "pit_membership_manifest_sha256": (
        "32f58adbca49fb89dfeb54ceeb4ac9b27b6a26c55e0c9cfeae7a8fcaf3683f10"
    ),
    "pit_membership_canonical_content_hash": (
        "8886dcfd32831c3c6f8a52da0a9b24c1426b1483adce0976a3c002ffd9cb5eea"
    ),
    "pit_membership_records_parquet_sha256": (
        "2e8c922de9f198ab18a6b38743a01f4343fbf52b876da84026389d3ffd11eec0"
    ),
    "coverage_package_id": "695245b51005e50b",
    "coverage_manifest_sha256": (
        "4e8b6163d4db11836e8a3aedc542d69ed6707bab566b6e0b16cb124d2b1e705f"
    ),
    "coverage_algorithm_hash": (
        "69a4342a3f382bdd2771256bea1b0ba250528184550783846659faf87a7ab919"
    ),
    "coverage_by_code_sha256": (
        "308b01eeecd007c0d7b13ce1717f12207857432d91c6fbb78ffa3e8ba7d05ab9"
    ),
    "coverage_by_date_sha256": (
        "7571f482559ef597af89ef640896ca45c747ecfbfc469a28ad38f93f6b4313f3"
    ),
    "coverage_unavailable_sha256": (
        "f6fe7ae02b1e8c20eb3530b636f6272e239e62140c9cd909af06e2ad6b451621"
    ),
}


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_link_or_junction(path: Path) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    return path.is_symlink() or bool(
        getattr(info, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


def _read_json(path: Path, errors: list[str]) -> dict | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"invalid JSON: {path.name}: {exc}")
        return None
    if not isinstance(value, dict):
        errors.append(f"JSON must be an object: {path.name}")
        return None
    return value


def _verify_sidecar(
    path: Path,
    errors: list[str],
    *,
    required: bool = True,
    include_filename: bool = True,
    actual_hash: str | None = None,
) -> None:
    sidecar = path.with_name(f"{path.name}.sha256")
    if not path.is_file():
        errors.append(f"missing file: {path.name}")
        return
    if not sidecar.is_file():
        if required:
            errors.append(f"missing sidecar: {sidecar.name}")
        return
    parts = sidecar.read_text(encoding="utf-8").strip().split()
    if include_filename:
        valid_format = len(parts) == 2 and parts[1] == path.name
    else:
        valid_format = len(parts) == 1
    if not valid_format:
        errors.append(f"invalid sidecar: {sidecar.name}")
        return
    actual = actual_hash if actual_hash is not None else _sha_file(path)
    if parts[0] != actual:
        errors.append(f"{path.name}.sha256 mismatch")


def _registered_to_physical(
    registered: str,
    registered_root: str,
    physical_root: Path,
) -> Path:
    path = PurePosixPath(registered)
    root = PurePosixPath(registered_root)
    if path.is_absolute() or ".." in path.parts or ".staging" in path.parts:
        raise ValueError(f"path escape: {registered}")
    try:
        suffix = path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"path escape: {registered}") from exc
    return physical_root.joinpath(*suffix.parts)


def _verify_index(
    index: dict,
    package_dir: Path,
    *,
    expected_artifact_id: str,
    errors: list[str],
) -> None:
    expected_root = (
        f"data/pit/b3_execution_input_packages/{expected_artifact_id}/inputs"
    )
    registered_root = index.get("formal_input_root_repo_relative")
    if registered_root != expected_root:
        errors.append("formal input root mismatch")
    if index.get("schema_version") != INDEX_SCHEMA_VERSION:
        errors.append("input-index schema mismatch")
    algorithm_hash = hashlib.sha256(_canonical(ALGORITHM)).hexdigest()
    if index.get("algorithm_id") != ALGORITHM["algorithm_id"]:
        errors.append("input-index algorithm id mismatch")
    if index.get("algorithm_hash") != algorithm_hash:
        errors.append("input-index algorithm hash mismatch")
    declared_interfaces = index.get("interfaces")
    if not isinstance(declared_interfaces, dict) or set(declared_interfaces) != set(
        PHYSICAL_INTERFACES
    ):
        errors.append("physical interface set mismatch")
        return

    physical_root = package_dir / "inputs"
    registered_files: set[Path] = set()
    for name in PHYSICAL_INTERFACES:
        declared = declared_interfaces[name]
        entries = declared.get("entries")
        if not isinstance(entries, list):
            errors.append(f"{name} entries are invalid")
            continue
        recomputed_entries = []
        previous = ""
        for entry in entries:
            if not isinstance(entry, dict):
                errors.append(f"{name} entry is invalid")
                continue
            registered = entry.get("path", "")
            if registered <= previous:
                errors.append(f"{name} entries are not strictly sorted")
            previous = registered
            try:
                physical = _registered_to_physical(
                    registered,
                    registered_root,
                    physical_root,
                )
            except (TypeError, ValueError) as exc:
                errors.append(str(exc))
                continue
            registered_files.add(physical)
            if _is_link_or_junction(physical):
                errors.append(f"symlink or junction is forbidden: {registered}")
                continue
            if not physical.is_file():
                errors.append(f"missing file: {registered}")
                continue
            actual_hash = _sha_file(physical)
            actual_size = physical.stat().st_size
            if entry.get("sha256") != actual_hash:
                errors.append(f"hash mismatch: {registered}")
            if physical.suffix == ".parquet":
                _verify_sidecar(
                    physical,
                    errors,
                    required=False,
                    include_filename=False,
                    actual_hash=actual_hash,
                )
            if entry.get("byte_size") != actual_size:
                errors.append(f"byte size mismatch: {registered}")
            recomputed_entries.append(
                {
                    "path": registered,
                    "sha256": actual_hash,
                    "byte_size": actual_size,
                }
            )
        expected_interface_hash = hashlib.sha256(
            _canonical(recomputed_entries)
        ).hexdigest()
        if declared.get("entry_count") != len(recomputed_entries):
            errors.append(f"{name} entry_count mismatch")
        if declared.get("total_bytes") != sum(
            entry["byte_size"] for entry in recomputed_entries
        ):
            errors.append(f"{name} total_bytes mismatch")
        if declared.get("interface_content_hash") != expected_interface_hash:
            errors.append(f"{name} interface_content_hash mismatch")

    if physical_root.is_dir():
        for path in physical_root.rglob("*"):
            if _is_link_or_junction(path):
                errors.append(f"symlink or junction is forbidden: {path}")
                continue
            if path.is_file() and path not in registered_files:
                errors.append(f"extra file: {path.relative_to(physical_root).as_posix()}")

    payload = {
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
    if index.get("input_index_hash") != hashlib.sha256(_canonical(payload)).hexdigest():
        errors.append("input_index_hash mismatch")


def _verify_manifest(
    manifest: dict,
    index: dict,
    *,
    expected_artifact_id: str,
    errors: list[str],
) -> None:
    required = {
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
    missing = sorted(required - manifest.keys())
    if missing:
        errors.append(f"manifest fields missing: {','.join(missing)}")
        return
    if manifest["artifact_id"] != expected_artifact_id:
        errors.append("artifact id mismatch")
    if manifest["schema_version"] != SCHEMA_VERSION:
        errors.append("package schema mismatch")
    if manifest["authorization_scope"] != AUTHORIZATION_SCOPE:
        errors.append("authorization scope mismatch")
    if manifest["frozen"] is not True:
        errors.append("package must be frozen")
    expected_root = (
        f"data/pit/b3_execution_input_packages/{expected_artifact_id}/inputs"
    )
    if manifest["formal_input_root_repo_relative"] != expected_root:
        errors.append("manifest formal input root mismatch")
    if manifest["exact_bindings"] != index.get("exact_bindings"):
        errors.append("manifest/index exact bindings mismatch")

    disclosures = manifest.get("source_authorization_disclosures")
    disclosure_flags = (
        (
            "data_snapshot",
            "not_authorized_for_b6_oos_gate_promotion_signal",
        ),
        (
            "pit_membership_snapshot",
            "not_authorized_for_b6_oos_gate_promotion_signal",
        ),
        (
            "qualification_successor",
            "not_authorized_for_b6_oos_gate_promotion_signal_or_data_collection",
        ),
    )
    if not isinstance(disclosures, dict) or any(
        not isinstance(disclosures.get(owner), dict)
        or disclosures[owner].get(flag) is not True
        for owner, flag in disclosure_flags
    ):
        errors.append("source authorization disclosure mismatch")

    interfaces = manifest.get("interfaces")
    expected_names = {"membership", *PHYSICAL_INTERFACES}
    expected_names.update({"listing_delisting", "liquidity", "announcement"})
    if not isinstance(interfaces, dict) or set(interfaces) != expected_names:
        errors.append("manifest interface set mismatch")
    else:
        expected_status = (
            "incomplete"
            if any(
                item.get("requirement") == "required"
                and item.get("availability") != "verified"
                for item in interfaces.values()
            )
            else "published"
        )
        if manifest["status"] != expected_status:
            errors.append("package status mismatch")
        for name, item in interfaces.items():
            if item.get("requirement") not in {"required", "not_required"}:
                errors.append(f"{name} requirement is invalid")
            if item.get("availability") not in {"verified", "unavailable"}:
                errors.append(f"{name} availability is invalid")
            if (
                item.get("requirement") == "not_required"
                and not str(item.get("reason", "")).strip()
            ):
                errors.append(f"{name} not_required reason is missing")

        policy = {
            name: {
                "requirement": item.get("requirement"),
                "reason": item.get("reason"),
            }
            for name, item in interfaces.items()
        }
        template = {
            "template_id": manifest["template_id"],
            "template_version": manifest["template_version"],
            "template_hash": manifest["template_hash"],
            "data_requirements_hash": manifest["data_requirements_hash"],
        }
        expected_policy_hash = hashlib.sha256(
            _canonical({"template": template, "interfaces": policy})
        ).hexdigest()
        if manifest["required_interface_policy_hash"] != expected_policy_hash:
            errors.append("required interface policy hash mismatch")

    semantic = {
        key: value
        for key, value in manifest.items()
        if key not in {"manifest_content_hash", "published_at"}
    }
    if manifest["manifest_content_hash"] != hashlib.sha256(
        _canonical(semantic)
    ).hexdigest():
        errors.append("manifest_content_hash mismatch")


def _verify_production_bindings(
    repo_root: Path,
    manifest: dict,
    errors: list[str],
) -> None:
    if manifest.get("exact_bindings") != PRODUCTION_EXACT_BINDINGS:
        errors.append("production exact bindings mismatch")
        return
    if (
        manifest.get("template_id")
        != "relative_strength_rotation_shsz_sw2021_v2"
        or manifest.get("template_version") != "v2_shsz_sw2021_pit_12m"
        or manifest.get("template_hash")
        != "867a47eeece1c0d208c591f35b5ca31d663ccda183c8721eef803483921238b6"
        or manifest.get("data_requirements_hash")
        != "1910d7a598b1008fb5ba6ee69833e174b5a9949f31a998e2fced436950d8df04"
    ):
        errors.append("production template identity mismatch")
    paths = {
        "data_snapshot_manifest_sha256": (
            repo_root
            / "data/pit/data_snapshot_manifests/ds_traderlens_v2_shsz_pit_001/manifest.json"
        ),
        "pit_membership_manifest_sha256": (
            repo_root
            / "data/pit/pit_membership_snapshots/"
            "pims_traderlens_v2_shsz_sw2021_pit_005/manifest.json"
        ),
        "pit_membership_records_parquet_sha256": (
            repo_root
            / "data/pit/pit_membership_snapshots/"
            "pims_traderlens_v2_shsz_sw2021_pit_005/records.parquet"
        ),
        "coverage_manifest_sha256": (
            repo_root
            / "data/pit/coverage_packages/695245b51005e50b/coverage_manifest.json"
        ),
        "coverage_by_code_sha256": (
            repo_root
            / "data/pit/coverage_packages/695245b51005e50b/coverage_by_code.parquet"
        ),
        "coverage_by_date_sha256": (
            repo_root
            / "data/pit/coverage_packages/695245b51005e50b/coverage_by_date.parquet"
        ),
        "coverage_unavailable_sha256": (
            repo_root
            / "data/pit/coverage_packages/695245b51005e50b/"
            "unavailable_security_dates.parquet"
        ),
    }
    for field, path in paths.items():
        if not path.is_file() or _sha_file(path) != PRODUCTION_EXACT_BINDINGS[field]:
            errors.append(f"production binding file mismatch: {field}")
    if errors:
        return

    try:
        data_manifest = json.loads(
            paths["data_snapshot_manifest_sha256"].read_text(encoding="utf-8")
        )
        membership_manifest = json.loads(
            paths["pit_membership_manifest_sha256"].read_text(encoding="utf-8")
        )
        coverage_manifest = json.loads(
            paths["coverage_manifest_sha256"].read_text(encoding="utf-8")
        )
        successor_manifest = json.loads(
            (
                repo_root
                / "data/pit/qualification_successors/e5100669ed247769/manifest.json"
            ).read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"production binding JSON invalid: {exc}")
        return
    if data_manifest.get("semantic_hash") != PRODUCTION_EXACT_BINDINGS[
        "data_snapshot_semantic_hash"
    ]:
        errors.append("production data snapshot semantic hash mismatch")
    if membership_manifest.get(
        "canonical_content_hash"
    ) != PRODUCTION_EXACT_BINDINGS["pit_membership_canonical_content_hash"]:
        errors.append("production membership canonical hash mismatch")
    if coverage_manifest.get("algorithm_hash") != PRODUCTION_EXACT_BINDINGS[
        "coverage_algorithm_hash"
    ]:
        errors.append("production coverage algorithm hash mismatch")

    actual_disclosures = {
        "data_snapshot": {
            "artifact_id": data_manifest.get("snapshot_id"),
            "not_authorized_for_b6_oos_gate_promotion_signal": data_manifest.get(
                "not_authorized_for_b6_oos_gate_promotion_signal"
            ),
        },
        "pit_membership_snapshot": {
            "artifact_id": membership_manifest.get("snapshot_id"),
            "not_authorized_for_b6_oos_gate_promotion_signal": membership_manifest.get(
                "not_authorized_for_b6_oos_gate_promotion_signal"
            ),
        },
        "qualification_successor": {
            "artifact_id": successor_manifest.get("successor_id"),
            "template_id": successor_manifest.get("template_id"),
            "template_hash": successor_manifest.get("template_hash"),
            "not_authorized_for_b6_oos_gate_promotion_signal_or_data_collection": (
                successor_manifest.get(
                    "not_authorized_for_b6_oos_gate_promotion_signal_or_data_collection"
                )
            ),
        },
    }
    if manifest.get("source_authorization_disclosures") != actual_disclosures:
        errors.append("production source authorization disclosure mismatch")


def verify_package(
    package_dir: Path,
    repo_root: Path,
    expected_artifact_id: str = ARTIFACT_ID,
    *,
    enforce_production_bindings: bool = False,
) -> dict:
    """Verify package bytes, semantic identities, path safety, and exact bindings."""

    package_dir = Path(package_dir)
    repo_root = Path(repo_root)
    errors: list[str] = []
    if not package_dir.is_dir():
        return {"is_valid": False, "errors": ["package not found"]}
    if _is_link_or_junction(package_dir):
        return {"is_valid": False, "errors": ["package root is a symlink or junction"]}
    expected_children = {
        "inputs",
        "manifest.json",
        "manifest.json.sha256",
        "input_index.json",
        "input_index.json.sha256",
    }
    actual_children = {path.name for path in package_dir.iterdir()}
    extra_children = sorted(actual_children - expected_children)
    if extra_children:
        errors.append(f"extra package-root entry: {','.join(extra_children)}")

    manifest_path = package_dir / "manifest.json"
    index_path = package_dir / "input_index.json"
    _verify_sidecar(manifest_path, errors)
    _verify_sidecar(index_path, errors)
    manifest = _read_json(manifest_path, errors)
    index = _read_json(index_path, errors)
    if manifest is None or index is None:
        return {"is_valid": False, "errors": errors}

    if manifest.get("input_index_sha256") != _sha_file(index_path):
        errors.append("manifest input_index_sha256 mismatch")
    algorithm_hash = hashlib.sha256(_canonical(ALGORITHM)).hexdigest()
    if manifest.get("input_index_algorithm_id") != ALGORITHM["algorithm_id"]:
        errors.append("manifest input-index algorithm id mismatch")
    if manifest.get("input_index_algorithm_hash") != algorithm_hash:
        errors.append("manifest input-index algorithm hash mismatch")

    _verify_index(
        index,
        package_dir,
        expected_artifact_id=expected_artifact_id,
        errors=errors,
    )
    _verify_manifest(
        manifest,
        index,
        expected_artifact_id=expected_artifact_id,
        errors=errors,
    )
    if enforce_production_bindings:
        _verify_production_bindings(repo_root, manifest, errors)
    return {"is_valid": not errors, "errors": errors}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact_id", nargs="?", default=ARTIFACT_ID)
    args = parser.parse_args(argv)
    repo_root = Path(__file__).resolve().parents[1]
    package_dir = (
        repo_root / "data/pit/b3_execution_input_packages" / args.artifact_id
    )
    result = verify_package(
        package_dir,
        repo_root,
        expected_artifact_id=args.artifact_id,
        enforce_production_bindings=True,
    )
    if not result["is_valid"]:
        print("[FAIL] " + "; ".join(result["errors"]))
        return 1
    manifest = json.loads((package_dir / "manifest.json").read_text(encoding="utf-8"))
    print(
        json.dumps(
            {
                "status": "verified",
                "artifact_id": args.artifact_id,
                "package_status": manifest["status"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
