#!/usr/bin/env python3
"""Publish the immutable Task 3 B3 execution-input package."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.services.formal_input_index import (
    INPUT_INDEX_ALGORITHM,
    PHYSICAL_INTERFACES,
    build_input_index,
    canonical_json_bytes,
    finalize_input_index,
    input_index_algorithm_hash,
    is_link_or_junction,
    sha256_file,
)
from scripts.verify_b3_execution_input_package import verify_package


ARTIFACT_ID = "b3eip_traderlens_v2_shsz_pit_001"
SUCCESSOR_ARTIFACT_ID = "b3eip_traderlens_v2_shsz_pit_002"
SCHEMA_VERSION = "b3_execution_input_package.v1"
AUTHORIZATION_SCOPE = "b3_execution_input_binding_only"
FORMAL_SOURCE = Path(
    "data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal"
)
PACKAGE_ROOT = Path("data/pit/b3_execution_input_packages")

EXPECTED = {
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


class PackagePublicationError(RuntimeError):
    pass


def _load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PackagePublicationError(f"invalid JSON artifact: {path}") from exc
    if not isinstance(value, dict):
        raise PackagePublicationError(f"JSON artifact must be an object: {path}")
    return value


def _assert_file_hash(path: Path, expected: str) -> None:
    if not path.is_file():
        raise PackagePublicationError(f"required artifact is missing: {path}")
    actual = sha256_file(path)
    if actual != expected:
        raise PackagePublicationError(
            f"artifact hash mismatch: {path} expected={expected} actual={actual}"
        )


def build_production_spec(repo_root: Path) -> dict:
    """Resolve only fixed, machine-checked Task 3 package inputs."""

    from backend.services.strategy_template_library import (
        convert_to_frozen_contract,
        get_template_by_id,
        get_template_data_requirements_hash,
    )

    repo_root = Path(repo_root)
    template_id = "relative_strength_rotation_shsz_sw2021_v2"
    template = get_template_by_id(template_id)
    if template is None:
        raise PackagePublicationError("exact V2 template is not approved")
    frozen_contract = convert_to_frozen_contract(
        template,
        created_at=datetime.now(),
    )
    if frozen_contract.governance_status != "approved":
        raise PackagePublicationError("exact V2 template is not approved")

    template_hash = template.frozen_template_hash
    requirements_hash = get_template_data_requirements_hash(template)
    expected_template_hash = (
        "867a47eeece1c0d208c591f35b5ca31d663ccda183c8721eef803483921238b6"
    )
    expected_requirements_hash = (
        "1910d7a598b1008fb5ba6ee69833e174b5a9949f31a998e2fced436950d8df04"
    )
    if (template_hash, requirements_hash) != (
        expected_template_hash,
        expected_requirements_hash,
    ):
        raise PackagePublicationError("exact V2 template identity mismatch")

    data_manifest_path = (
        repo_root
        / "data/pit/data_snapshot_manifests"
        / EXPECTED["data_snapshot_id"]
        / "manifest.json"
    )
    membership_root = (
        repo_root
        / "data/pit/pit_membership_snapshots"
        / EXPECTED["pit_membership_snapshot_id"]
    )
    membership_manifest_path = membership_root / "manifest.json"
    membership_records_path = membership_root / "records.parquet"
    coverage_root = (
        repo_root
        / "data/pit/coverage_packages"
        / EXPECTED["coverage_package_id"]
    )
    coverage_manifest_path = coverage_root / "coverage_manifest.json"
    successor_manifest_path = (
        repo_root
        / "data/pit/qualification_successors/e5100669ed247769/manifest.json"
    )

    _assert_file_hash(
        data_manifest_path,
        EXPECTED["data_snapshot_manifest_sha256"],
    )
    _assert_file_hash(
        membership_manifest_path,
        EXPECTED["pit_membership_manifest_sha256"],
    )
    _assert_file_hash(
        membership_records_path,
        EXPECTED["pit_membership_records_parquet_sha256"],
    )
    _assert_file_hash(
        coverage_manifest_path,
        EXPECTED["coverage_manifest_sha256"],
    )
    _assert_file_hash(
        coverage_root / "coverage_by_code.parquet",
        EXPECTED["coverage_by_code_sha256"],
    )
    _assert_file_hash(
        coverage_root / "coverage_by_date.parquet",
        EXPECTED["coverage_by_date_sha256"],
    )
    _assert_file_hash(
        coverage_root / "unavailable_security_dates.parquet",
        EXPECTED["coverage_unavailable_sha256"],
    )

    data_manifest = _load_json(data_manifest_path)
    membership_manifest = _load_json(membership_manifest_path)
    coverage_manifest = _load_json(coverage_manifest_path)
    successor_manifest = _load_json(successor_manifest_path)
    if data_manifest.get("semantic_hash") != EXPECTED["data_snapshot_semantic_hash"]:
        raise PackagePublicationError("data snapshot semantic hash mismatch")
    if (
        membership_manifest.get("canonical_content_hash")
        != EXPECTED["pit_membership_canonical_content_hash"]
    ):
        raise PackagePublicationError("membership canonical hash mismatch")
    if coverage_manifest.get("algorithm_hash") != EXPECTED["coverage_algorithm_hash"]:
        raise PackagePublicationError("coverage algorithm hash mismatch")

    config = template.strategy_config_payload
    forbidden_market = set(template.forbidden_market)
    forbidden_evidence = set(template.forbidden_evidence_terms)
    if "min_avg_amount_20d" not in config["risk"]:
        raise PackagePublicationError("liquidity requirement is not frozen")
    if "delisting_risk" not in forbidden_market:
        raise PackagePublicationError("listing/delisting requirement is not frozen")
    if "announcement" not in forbidden_evidence:
        raise PackagePublicationError("announcement policy is not frozen")

    policy = {
        "membership": {"requirement": "required", "reason": "PIT ranking universe"},
        "daily": {"requirement": "required", "reason": "OHLCV and market-open fill"},
        "daily_basic": {
            "requirement": "required",
            "reason": "formal coverage and liquidity input",
        },
        "adj_factor": {"requirement": "required", "reason": "adjusted-close formula"},
        "stk_limit": {"requirement": "required", "reason": "limit-up fill guard"},
        "suspend_d": {"requirement": "required", "reason": "suspension fill guard"},
        "stock_st": {"requirement": "required", "reason": "ST exclusion"},
        "trade_cal": {"requirement": "required", "reason": "SH/SZ T+1 calendar"},
        "listing_delisting": {
            "requirement": "required",
            "reason": "template forbidden_market includes delisting_risk",
        },
        "liquidity": {
            "requirement": "required",
            "reason": "template risk freezes min_avg_amount_20d",
        },
        "announcement": {
            "requirement": "not_required",
            "reason": "template forbidden_evidence_terms includes announcement",
        },
    }
    disclosures = {
        "data_snapshot": {
            "artifact_id": EXPECTED["data_snapshot_id"],
            "not_authorized_for_b6_oos_gate_promotion_signal": data_manifest.get(
                "not_authorized_for_b6_oos_gate_promotion_signal"
            ),
        },
        "pit_membership_snapshot": {
            "artifact_id": EXPECTED["pit_membership_snapshot_id"],
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
    if not all(
        disclosure.get(key) is True
        for disclosure, key in (
            (
                disclosures["data_snapshot"],
                "not_authorized_for_b6_oos_gate_promotion_signal",
            ),
            (
                disclosures["pit_membership_snapshot"],
                "not_authorized_for_b6_oos_gate_promotion_signal",
            ),
            (
                disclosures["qualification_successor"],
                "not_authorized_for_b6_oos_gate_promotion_signal_or_data_collection",
            ),
        )
    ):
        raise PackagePublicationError("source authorization disclosure mismatch")

    return {
        "template": {
            "template_id": template.template_id,
            "template_version": template.version,
            "template_hash": template_hash,
            "data_requirements_hash": requirements_hash,
        },
        "exact_bindings": dict(EXPECTED),
        "source_authorization_disclosures": disclosures,
        "interface_policy": policy,
    }


def _copy_and_hash(
    source: Path,
    destination: Path,
    registered_path: str,
) -> dict:
    before = source.stat()
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    with source.open("rb") as reader, destination.open("xb") as writer:
        for chunk in iter(lambda: reader.read(1024 * 1024), b""):
            writer.write(chunk)
            digest.update(chunk)
    after = source.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise PackagePublicationError(f"source changed while copying: {source}")
    return {
        "path": registered_path,
        "sha256": digest.hexdigest(),
        "byte_size": before.st_size,
    }


def _copy_inputs(
    source_root: Path,
    staging_inputs: Path,
    *,
    final_input_root_repo_relative: str,
    copy_workers: int,
) -> dict[str, list[dict]]:
    jobs = []
    for name in PHYSICAL_INTERFACES:
        interface_root = source_root / name
        if not interface_root.is_dir():
            raise PackagePublicationError(f"missing required interface: {name}")
        files = []
        for source in sorted(interface_root.rglob("*")):
            if is_link_or_junction(source):
                raise PackagePublicationError(
                    f"source symlink or junction is forbidden: {source}"
                )
            if source.is_file():
                files.append(source)
        if not files:
            raise PackagePublicationError(f"required interface is empty: {name}")
        for source in files:
            relative = source.relative_to(interface_root)
            jobs.append(
                (
                    name,
                    source,
                    staging_inputs / name / relative,
                    (
                        f"{final_input_root_repo_relative}/{name}/"
                        f"{relative.as_posix()}"
                    ),
                )
            )

    entries = {name: [] for name in PHYSICAL_INTERFACES}
    with ThreadPoolExecutor(max_workers=max(1, copy_workers)) as executor:
        futures = [
            (
                name,
                executor.submit(_copy_and_hash, source, destination, registered),
            )
            for name, source, destination, registered in jobs
        ]
        for name, future in futures:
            entries[name].append(future.result())
    return entries


def _interfaces_manifest(index: dict, spec: dict) -> dict:
    interfaces = {}
    policy = spec["interface_policy"]
    membership_hash = spec["exact_bindings"][
        "pit_membership_canonical_content_hash"
    ]
    interfaces["membership"] = {
        **policy["membership"],
        "availability": "verified",
        "entry_count": 1,
        "total_bytes": 0,
        "interface_content_hash": membership_hash,
    }
    for name in PHYSICAL_INTERFACES:
        item = index["interfaces"][name]
        interfaces[name] = {
            **policy[name],
            "availability": "verified",
            "entry_count": item["entry_count"],
            "total_bytes": item["total_bytes"],
            "interface_content_hash": item["interface_content_hash"],
        }
    for name in ("listing_delisting", "liquidity", "announcement"):
        interfaces[name] = {
            **policy[name],
            "availability": "unavailable",
            "entry_count": 0,
            "total_bytes": 0,
            "interface_content_hash": "",
        }
    return interfaces


def _manifest(
    *,
    artifact_id: str,
    final_input_root_repo_relative: str,
    index: dict,
    input_index_sha256: str,
    spec: dict,
    published_at: str,
) -> dict:
    interfaces = _interfaces_manifest(index, spec)
    package_status = (
        "incomplete"
        if any(
            value["requirement"] == "required"
            and value["availability"] != "verified"
            for value in interfaces.values()
        )
        else "published"
    )
    template = spec["template"]
    payload = {
        "artifact_id": artifact_id,
        "schema_version": SCHEMA_VERSION,
        "status": package_status,
        "authorization_scope": AUTHORIZATION_SCOPE,
        "frozen": True,
        "formal_input_root_repo_relative": final_input_root_repo_relative,
        "input_index_sha256": input_index_sha256,
        "input_index_algorithm_id": INPUT_INDEX_ALGORITHM["algorithm_id"],
        "input_index_algorithm_hash": input_index_algorithm_hash(),
        "required_interface_policy_hash": hashlib.sha256(
            canonical_json_bytes(
                {
                    "template": template,
                    "interfaces": spec["interface_policy"],
                }
            )
        ).hexdigest(),
        "template_id": template["template_id"],
        "template_version": template["template_version"],
        "template_hash": template["template_hash"],
        "data_requirements_hash": template["data_requirements_hash"],
        "interfaces": interfaces,
        "exact_bindings": spec["exact_bindings"],
        "source_authorization_disclosures": spec[
            "source_authorization_disclosures"
        ],
    }
    return {
        **payload,
        "manifest_content_hash": hashlib.sha256(
            canonical_json_bytes(payload)
        ).hexdigest(),
        "published_at": published_at,
    }


def _write_json_with_sidecar(path: Path, value: dict) -> str:
    raw = canonical_json_bytes(value)
    path.write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    path.with_name(f"{path.name}.sha256").write_text(
        f"{digest}  {path.name}\n",
        encoding="utf-8",
    )
    return digest


def _safe_remove_staging(staging: Path, packages_root: Path) -> None:
    resolved_parent = staging.resolve().parent
    if resolved_parent != packages_root.resolve() or not staging.name.startswith(
        ".staging_"
    ):
        raise PackagePublicationError(f"unsafe staging cleanup target: {staging}")
    if staging.exists():
        shutil.rmtree(staging)


def _desired_from_source(
    *,
    source_root: Path,
    final_input_root_repo_relative: str,
    spec: dict,
    artifact_id: str,
    published_at: str,
) -> tuple[dict, dict, str]:
    index = build_input_index(
        source_root,
        formal_input_root_repo_relative=final_input_root_repo_relative,
        exact_bindings=spec["exact_bindings"],
    )
    index_raw = canonical_json_bytes(index)
    index_sha = hashlib.sha256(index_raw).hexdigest()
    return (
        index,
        _manifest(
            artifact_id=artifact_id,
            final_input_root_repo_relative=final_input_root_repo_relative,
            index=index,
            input_index_sha256=index_sha,
            spec=spec,
            published_at=published_at,
        ),
        index_sha,
    )


def publish_package(
    *,
    repo_root: Path,
    source_root: Path,
    packages_root: Path,
    artifact_id: str,
    spec: dict,
    published_at: str | None = None,
    copy_workers: int = 8,
) -> dict:
    """Copy, index, independently verify, then atomically publish one package."""

    if artifact_id not in {ARTIFACT_ID, SUCCESSOR_ARTIFACT_ID}:
        raise PackagePublicationError(f"unallocated artifact id: {artifact_id}")
    repo_root = Path(repo_root).resolve()
    source_root = Path(source_root).resolve()
    packages_root = Path(packages_root).resolve()
    target = packages_root / artifact_id
    final_input_root = (
        f"data/pit/b3_execution_input_packages/{artifact_id}/inputs"
    )
    now = published_at or datetime.now(timezone.utc).isoformat()

    if target.exists():
        existing_verification = verify_package(
            target,
            repo_root,
            expected_artifact_id=artifact_id,
        )
        if not existing_verification["is_valid"]:
            raise PackagePublicationError(
                "content_conflict: existing artifact does not verify"
            )
        desired_index, desired_manifest, _ = _desired_from_source(
            source_root=source_root,
            final_input_root_repo_relative=final_input_root,
            spec=spec,
            artifact_id=artifact_id,
            published_at=now,
        )
        existing_index = _load_json(target / "input_index.json")
        existing_manifest = _load_json(target / "manifest.json")
        if (
            desired_index["input_index_hash"]
            == existing_index.get("input_index_hash")
            and desired_manifest["manifest_content_hash"]
            == existing_manifest.get("manifest_content_hash")
        ):
            return {
                "status": "already_published",
                "artifact_id": artifact_id,
                "package_status": existing_manifest["status"],
            }
        raise PackagePublicationError("content_conflict: source or binding changed")

    packages_root.mkdir(parents=True, exist_ok=True)
    staging = packages_root / f".staging_{artifact_id}_{uuid.uuid4().hex}"
    try:
        staging.mkdir()
        entries = _copy_inputs(
            source_root,
            staging / "inputs",
            final_input_root_repo_relative=final_input_root,
            copy_workers=copy_workers,
        )
        index = finalize_input_index(
            entries,
            formal_input_root_repo_relative=final_input_root,
            exact_bindings=spec["exact_bindings"],
        )
        index_sha = _write_json_with_sidecar(staging / "input_index.json", index)
        manifest = _manifest(
            artifact_id=artifact_id,
            final_input_root_repo_relative=final_input_root,
            index=index,
            input_index_sha256=index_sha,
            spec=spec,
            published_at=now,
        )
        manifest_sha = _write_json_with_sidecar(staging / "manifest.json", manifest)
        result = verify_package(
            staging,
            repo_root,
            expected_artifact_id=artifact_id,
        )
        if not result["is_valid"]:
            raise PackagePublicationError(
                "pre-publication verification failed: " + "; ".join(result["errors"])
            )
        staging.rename(target)
        return {
            "status": "published",
            "artifact_id": artifact_id,
            "package_status": manifest["status"],
            "manifest_sha256": manifest_sha,
            "input_index_sha256": index_sha,
            "input_index_hash": index["input_index_hash"],
        }
    except Exception:
        _safe_remove_staging(staging, packages_root)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact_id", nargs="?", default=ARTIFACT_ID)
    parser.add_argument("--copy-workers", type=int, default=8)
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[1]
    try:
        result = publish_package(
            repo_root=repo_root,
            source_root=repo_root / FORMAL_SOURCE,
            packages_root=repo_root / PACKAGE_ROOT,
            artifact_id=args.artifact_id,
            spec=build_production_spec(repo_root),
            copy_workers=args.copy_workers,
        )
    except (OSError, ValueError, PackagePublicationError) as exc:
        print(f"[FAIL] {exc}")
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
