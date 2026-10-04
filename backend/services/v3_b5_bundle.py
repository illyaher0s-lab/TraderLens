"""Lineage binding and metadata-only write-once bundle for v3 B5."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from backend.services.v3_b5_source_inventory import (
    ROOT,
    verify_source_inventory,
)
from backend.services.v3_b5_types import (
    RESULT_TYPES,
    canonical_json,
    sha256_bytes,
    validate_result_payload,
)


SCHEMA = "v3_b5_bundle.v1"
FORMAL_B6_PREFLIGHT_SCOPE = "v3_b5_formal_b6_preflight"
FIXTURE_B5_SCOPE = "v3_b5_contract_fixture_only"
INDEPENDENT_VERIFIER_ID = "v3_b5_formal_independent_verifier.v1"
INDEPENDENT_VERIFIER_ALGORITHM = "v3_b5_exact_sources_and_lineage.v1"
V3_B5_BUNDLE_ROOT = Path("data/pit/v3_b5_validation_bundles")
SOURCE_INVENTORY_ID = "2fe8321a5f644b9b"
SOURCE_INVENTORY_MANIFEST_SHA256 = "e23b94ac7294003a9b28db28f270bf2f19eaff40da9a03507adda87aad219a2c"
TEMPLATE = {
    "template_id": "relative_strength_rotation_shsz_sw2021_v3",
    "template_version": "v3_shsz_sw2021_pit_12m_liquidity20d",
    "template_hash": "f7c0fd8123f62f37118cb947e1735861374435f8707e01b06d788a8ec4df39c1",
    "data_requirements_hash": "ef2ab5b1dafe4349f305b52733a7dcb018a2961464dfbc6542a10e34805d041d",
}
REVISION_ID = "6440ffc03a742f4d4632078481cf3abf171eafb1a24f2bc69bc6f352d1b19ebc"
PROTOCOL_ID = "8770c56c5a69ef128442c0f593f9e4b081a6b13c69744b27171b27cc8c8b7bbe"
SUPPLEMENT_ID = "d1134e96d6b2ec1b"
SUPPLEMENT_MANIFEST_SHA256 = "18e7fd2fb48c089019c9343512641de7ef4f90fd50415c868919ddcabd24c16b"
FORMAL_SNAPSHOT_ID = "v3ds_d73256081de82e8a"
FORMAL_SNAPSHOT_MANIFEST_SHA256 = "57067e15e6ad1a92b23b42b48173b6cf1af2e7e23f3357320288fb7e109c2680"
FORMAL_SNAPSHOT_SEMANTIC_HASH = "d73256081de82e8a764ea2394d613af820fd1b82e773c48156ca2463a452c80e"
B3_EXECUTION_INPUT_ID = "05f38a2884dc7e47"
B3_EXECUTION_INPUT_MANIFEST_SHA256 = "741e511778ba7d520230c8378c952fd85dc407129d66cfb4366c7112530793a6"
B3_PREDECESSOR_PACKAGE_ID = "b3eip_traderlens_v2_shsz_pit_001"
B3_PREDECESSOR_MANIFEST_SHA256 = "ee21303e17b60f81947f40e172031421b88e53d3d79b0fdb95ba6c474a327786"
B3_INPUT_INDEX_SHA256 = "3b7ca54e7cfad3443f0442215ca38328cfe92dcf1f780d3a85ac65710cacc787"
B4_ID = "958bb9717edd08a9"
B4_MANIFEST_SHA256 = "af9ebfbcda0eff795efc4ef26688f57286886206e1e6dfe1699a90a197f8b7c2"
B4_EVENT_SHA256 = "374479e9df35c80c680adfe34fe95d10a78eb4d049a24fc6bc43cfb3aa0bf1cc"
COMPARISON_ARTIFACT_ID = "8eec0787b345639a"
COMPARISON_MANIFEST_SHA256 = "e19d9f51ba9b1026e6463d7eabc11dfdcda1890f3d9ab8b283248aa9d654123a"
MEMBERSHIP_ID = "pims_traderlens_v2_shsz_sw2021_pit_005"
MEMBERSHIP_MANIFEST_SHA256 = "32f58adbca49fb89dfeb54ceeb4ac9b27b6a26c55e0c9cfeae7a8fcaf3683f10"
MEMBERSHIP_RECORDS_SHA256 = "2e8c922de9f198ab18a6b38743a01f4343fbf52b876da84026389d3ffd11eec0"
CALENDAR_ID = "shsz_common_trade_calendar_v1"
CALENDAR_MANIFEST_SHA256 = "ae019cf45072d8274f915837a03d1824c02a69159df473512dbce2e925586785"
CALENDAR_DATE_SET_SHA256 = "62b6880c9acc381d273ceee40c900a486c3f83488600c042c43ce1d8f9cbb194"
SCOPE_ID = "acbc49159d989a46"
SCOPE_MANIFEST_SHA256 = "cef48909b7b7bb05bc952a19ff8e50702540b427c58fd21eb1670afcaf675c67"
GATE_ENVELOPE_HASH = "94da0dda30af75d663a7d28deb0a15d64a4e068586a1295f3b4f52203a8c4738"
IS_RANGE = {"start": "2025-06-27", "end": "2026-03-19"}
PAYLOAD_FILES = {
    "base_transaction_cost": "base_transaction_cost.json",
    "stress_transaction_cost": "stress_transaction_cost.json",
    "benchmark_comparison": "benchmark_comparison.json",
    "same_universe_control_comparison": "same_universe_control.json",
}
_COST_LINEAGE_EXTRAS = frozenset({"daily_observation_hash", "ledger_observation"})
_COMPARISON_LINEAGE_EXTRAS = frozenset(
    {
        "comparison_contract",
        "cost_artifact",
        "historical_coverage",
        "ledger_observation",
        "lifecycle_successor",
        "missing_mark_diagnostic",
    }
)
BUNDLE_ONLY_LINEAGE_KEYS = frozenset(
    {"b3_execution_input", "stock_basic_lifecycle", "strategy_scoped_universe"}
)
LEGACY_B5_BUNDLE_ID = "e4b03db805ebbdee"
LEGACY_B5_MANIFEST_SHA256 = "fb5b0c3e2cea118f33257a0cc338fe768df7fce237bf8fdf1b8b93dbcc1416a5"
LEGACY_B5_VERIFIER_IDENTITY = {
    "verifier_id": "v3_b5_formal_independent_verifier.v1",
    "algorithm_id": "v3_b5_exact_sources_and_lineage.v1",
    "source_path": "scripts/verify_v3_b5_bundle.py",
    "source_sha256": "2e868db4ffd99eb2ffdeff75b36ba17109b0f1ec3ae20fbeab2065ab3ddc787f",
    "source_loader_path": "scripts/publish_v3_b5_bundle.py",
    "source_loader_sha256": "221e94ec4c972464d8aa0e02adec1d7f3bc310f7bff572fe9f052f926bc204c4",
    "engine_source_path": "backend/services/v3_b5_bundle.py",
    "engine_source_sha256": "ddc2e3002cb2d355a954c3468ad124c441c399674f8f963c661e314350a9fbeb",
}


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _read(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _bound_manifest(repo_root: Path, relative: str, expected_id: str, id_field: str, expected_sha: str) -> dict:
    path = Path(repo_root) / relative / "manifest.json"
    sidecar = path.with_name(path.name + ".sha256")
    if not path.exists() or not sidecar.exists():
        raise ValueError(f"missing bound artifact: {relative}")
    actual_sha = _sha(path)
    if actual_sha != expected_sha or sidecar.read_text(encoding="utf-8").split()[0] != actual_sha:
        raise ValueError(f"bound artifact hash mismatch: {relative}")
    manifest = _read(path)
    if manifest.get(id_field) != expected_id:
        raise ValueError(f"bound artifact identity mismatch: {relative}")
    return manifest


def _bound_repo_path(repo_root: Path, raw_path: object, *, label: str) -> tuple[Path, str]:
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ValueError(f"{label} path is missing")
    normalized = raw_path.replace("\\", "/")
    posix = PurePosixPath(normalized)
    windows = PureWindowsPath(raw_path)
    if posix.is_absolute() or windows.is_absolute() or ".." in posix.parts or ":" in normalized:
        raise ValueError(f"{label} path is not repository-relative")
    root = Path(repo_root).resolve()
    candidate = root.joinpath(*posix.parts)
    current = root
    for part in posix.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"{label} path contains a symbolic link")
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{label} path escapes the repository") from exc
    return resolved, posix.as_posix()


def _b3_execution_input_binding(repo_root: Path, snapshot: dict) -> dict[str, Any]:
    qualification = snapshot.get("v3_qualification")
    if not isinstance(qualification, dict):
        raise ValueError("formal snapshot v3 qualification binding is missing")
    declared = qualification.get("b3_execution_input")
    if declared != {
        "artifact_id": B3_EXECUTION_INPUT_ID,
        "authorization_scope": "b3_execution_input_binding_only",
        "manifest_sha256": B3_EXECUTION_INPUT_MANIFEST_SHA256,
    }:
        raise ValueError("formal snapshot B3 execution-input binding changed")

    b3_dir = Path(repo_root) / "data/pit/b3_execution_input_packages" / B3_EXECUTION_INPUT_ID
    b3 = _bound_manifest(
        repo_root,
        f"data/pit/b3_execution_input_packages/{B3_EXECUTION_INPUT_ID}",
        B3_EXECUTION_INPUT_ID,
        "artifact_id",
        B3_EXECUTION_INPUT_MANIFEST_SHA256,
    )
    if (
        b3.get("schema_version") != "v3_b3_execution_input_package.v1"
        or b3.get("status") != "published"
        or b3.get("package_status") != "published"
        or b3.get("authorization_scope") != "b3_execution_input_binding_only"
    ):
        raise ValueError("B3 execution-input package is not the published bound package")
    from scripts.verify_v3_b3_successor import verify_v3_b3_successor

    verified = verify_v3_b3_successor(b3_dir, Path(repo_root))
    if verified.get("status") != "verified" or verified.get("artifact_id") != B3_EXECUTION_INPUT_ID:
        raise ValueError("B3 execution-input package verification failed")

    predecessor = b3.get("predecessor_package")
    if not isinstance(predecessor, dict) or predecessor.get("artifact_id") != B3_PREDECESSOR_PACKAGE_ID:
        raise ValueError("B3 predecessor package identity mismatch")
    predecessor_dir, predecessor_rel = _bound_repo_path(
        repo_root, predecessor.get("path"), label="B3 predecessor package"
    )
    if predecessor_rel != f"data/pit/b3_execution_input_packages/{B3_PREDECESSOR_PACKAGE_ID}":
        raise ValueError("B3 predecessor package path mismatch")
    predecessor_manifest_path = predecessor_dir / "manifest.json"
    predecessor_manifest_sha = _sha(predecessor_manifest_path)
    if (
        predecessor_manifest_sha != B3_PREDECESSOR_MANIFEST_SHA256
        or predecessor.get("manifest_sha256") != B3_PREDECESSOR_MANIFEST_SHA256
        or not predecessor_manifest_path.with_name("manifest.json.sha256").is_file()
        or predecessor_manifest_path.with_name("manifest.json.sha256").read_text(encoding="utf-8").split()[0]
        != predecessor_manifest_sha
    ):
        raise ValueError("B3 predecessor package manifest binding mismatch")
    predecessor_manifest = _read(predecessor_manifest_path)
    source_inventory = qualification.get("source_inventory")
    if not isinstance(source_inventory, dict):
        raise ValueError("formal snapshot source inventory is missing")
    input_root, input_root_rel = _bound_repo_path(
        repo_root,
        source_inventory.get("formal_input_root"),
        label="formal snapshot input root",
    )
    if (
        predecessor_manifest.get("artifact_id") != B3_PREDECESSOR_PACKAGE_ID
        or predecessor_manifest.get("input_index_sha256") != B3_INPUT_INDEX_SHA256
        or predecessor_manifest.get("formal_input_root_repo_relative") != input_root_rel
        or input_root_rel != f"data/pit/b3_execution_input_packages/{B3_PREDECESSOR_PACKAGE_ID}/inputs"
        or not input_root.is_dir()
    ):
        raise ValueError("B3 input root does not match the verified formal snapshot")
    index_path = predecessor_dir / "input_index.json"
    if (
        _sha(index_path) != B3_INPUT_INDEX_SHA256
        or not index_path.with_name("input_index.json.sha256").is_file()
        or index_path.with_name("input_index.json.sha256").read_text(encoding="utf-8").split()[0]
        != B3_INPUT_INDEX_SHA256
    ):
        raise ValueError("B3 input index manifest binding mismatch")
    if predecessor.get("input_index_sha256") != B3_INPUT_INDEX_SHA256:
        raise ValueError("B3 successor input-index binding mismatch")
    return {
        "artifact_id": B3_EXECUTION_INPUT_ID,
        "manifest_sha256": B3_EXECUTION_INPUT_MANIFEST_SHA256,
        "authorization_scope": "b3_execution_input_binding_only",
        "predecessor_package_id": B3_PREDECESSOR_PACKAGE_ID,
        "predecessor_manifest_sha256": B3_PREDECESSOR_MANIFEST_SHA256,
        "input_index_repo_relative_path": f"{predecessor_rel}/input_index.json",
        "input_index_sha256": B3_INPUT_INDEX_SHA256,
        "formal_input_root_repo_relative": input_root_rel,
    }


def _stock_basic_lifecycle_binding(repo_root: Path) -> dict[str, Any]:
    comparison = _bound_manifest(
        repo_root,
        f"data/pit/v3_b5_comparisons/{COMPARISON_ARTIFACT_ID}",
        COMPARISON_ARTIFACT_ID,
        "artifact_id",
        COMPARISON_MANIFEST_SHA256,
    )
    lineage = comparison.get("lineage")
    lifecycle = lineage.get("lifecycle_successor") if isinstance(lineage, dict) else None
    if not isinstance(lifecycle, dict):
        raise ValueError("verified comparison has no stock_basic lifecycle binding")
    manifest_rel = lifecycle.get("manifest_repo_relative_path")
    lifecycle_manifest_path, normalized_manifest_rel = _bound_repo_path(
        repo_root, manifest_rel, label="stock_basic lifecycle manifest"
    )
    if not normalized_manifest_rel.endswith("/manifest.json"):
        raise ValueError("stock_basic lifecycle manifest path is invalid")
    lifecycle_manifest_sha = _sha(lifecycle_manifest_path)
    if (
        lifecycle_manifest_sha != lifecycle.get("manifest_sha256")
        or lifecycle_manifest_path.with_name("manifest.json.sha256").read_text(encoding="utf-8").split()[0]
        != lifecycle_manifest_sha
    ):
        raise ValueError("stock_basic lifecycle manifest hash mismatch")
    lifecycle_manifest = _read(lifecycle_manifest_path)
    if lifecycle_manifest.get("successor_id") != lifecycle.get("artifact_id"):
        raise ValueError("stock_basic lifecycle successor identity mismatch")
    stock_basic_root, stock_basic_root_rel = _bound_repo_path(
        repo_root, lifecycle.get("stock_basic_root"), label="stock_basic lifecycle root"
    )
    files = lifecycle.get("stock_basic_files")
    if not isinstance(files, list) or {item.get("path") for item in files if isinstance(item, dict)} != {
        "list_status=D/part.parquet",
        "list_status=L/part.parquet",
        "list_status=P/part.parquet",
    }:
        raise ValueError("stock_basic lifecycle partition set mismatch")
    normalized_files = []
    for item in files:
        if not isinstance(item, dict) or not isinstance(item.get("sha256"), str):
            raise ValueError("stock_basic lifecycle partition binding is invalid")
        partition_path, partition_rel = _bound_repo_path(
            repo_root,
            f"{stock_basic_root_rel}/{item['path']}",
            label="stock_basic lifecycle partition",
        )
        if _sha(partition_path) != item["sha256"]:
            raise ValueError(f"stock_basic lifecycle partition hash mismatch: {item['path']}")
        normalized_files.append({"path": item["path"], "sha256": item["sha256"]})
    return {
        "artifact_id": lifecycle["artifact_id"],
        "manifest_repo_relative_path": normalized_manifest_rel,
        "manifest_sha256": lifecycle_manifest_sha,
        "root_repo_relative": stock_basic_root_rel,
        "stock_basic_files": sorted(normalized_files, key=lambda item: item["path"]),
        "comparison_artifact_id": COMPARISON_ARTIFACT_ID,
        "comparison_manifest_sha256": COMPARISON_MANIFEST_SHA256,
    }


def independent_verifier_identity() -> dict[str, str]:
    verifier_path = Path(__file__).resolve().parents[2] / "scripts/verify_v3_b5_bundle.py"
    source_loader_path = Path(__file__).resolve().parents[2] / "scripts/publish_v3_b5_bundle.py"
    engine_path = Path(__file__).resolve()
    return {
        "verifier_id": INDEPENDENT_VERIFIER_ID,
        "algorithm_id": "v3_b5_exact_sources_lineage_and_strategy_scope.v1",
        "source_path": "scripts/verify_v3_b5_bundle.py",
        "source_sha256": _sha(verifier_path),
        "source_loader_path": "scripts/publish_v3_b5_bundle.py",
        "source_loader_sha256": _sha(source_loader_path),
        "engine_source_path": "backend/services/v3_b5_bundle.py",
        "engine_source_sha256": _sha(engine_path),
        "scope_source_path": "backend/services/strategy_scoped_pit_universe.py",
        "scope_source_sha256": _sha(
            engine_path.parent / "strategy_scoped_pit_universe.py"
        ),
    }


def _resolve_code_root(code_root: Path | None) -> Path:
    active = Path(__file__).resolve().parents[2]
    if code_root is None:
        return active
    requested = Path(code_root).resolve(strict=True)
    if requested != active:
        raise ValueError("code root does not match the active source tree")
    return active


def _lineage_has_formal_b6_inputs(
    lineage: dict[str, Any], *, require_strategy_scope: bool = True
) -> bool:
    """Keep synthetic fixture bundles outside the formal B6 admission scope."""
    formal_snapshot = lineage.get("formal_snapshot")
    b3 = lineage.get("b3_execution_input")
    lifecycle = lineage.get("stock_basic_lifecycle")
    membership = lineage.get("membership")
    strategy_scope = lineage.get("strategy_scoped_universe")
    formal_inputs_match = (
        formal_snapshot
        == {
            "id": FORMAL_SNAPSHOT_ID,
            "semantic_hash": FORMAL_SNAPSHOT_SEMANTIC_HASH,
            "manifest_sha256": FORMAL_SNAPSHOT_MANIFEST_SHA256,
        }
        and isinstance(b3, dict)
        and b3.get("artifact_id") == B3_EXECUTION_INPUT_ID
        and b3.get("manifest_sha256") == B3_EXECUTION_INPUT_MANIFEST_SHA256
        and b3.get("authorization_scope") == "b3_execution_input_binding_only"
        and b3.get("predecessor_package_id") == B3_PREDECESSOR_PACKAGE_ID
        and b3.get("predecessor_manifest_sha256") == B3_PREDECESSOR_MANIFEST_SHA256
        and b3.get("input_index_repo_relative_path")
        == f"data/pit/b3_execution_input_packages/{B3_PREDECESSOR_PACKAGE_ID}/input_index.json"
        and b3.get("input_index_sha256") == B3_INPUT_INDEX_SHA256
        and b3.get("formal_input_root_repo_relative")
        == f"data/pit/b3_execution_input_packages/{B3_PREDECESSOR_PACKAGE_ID}/inputs"
        and isinstance(lifecycle, dict)
        and lifecycle.get("artifact_id") == "49b09326f35936c6"
        and lifecycle.get("manifest_sha256")
        == "3f25d5d1a23074d0c980c29503178d18f82e83ca6e844513805faf5163ea74b2"
        and lifecycle.get("comparison_artifact_id") == COMPARISON_ARTIFACT_ID
        and lifecycle.get("comparison_manifest_sha256") == COMPARISON_MANIFEST_SHA256
        and isinstance(membership, dict)
        and membership.get("id") == MEMBERSHIP_ID
        and membership.get("manifest_sha256") == MEMBERSHIP_MANIFEST_SHA256
        and membership.get("records_sha256") == MEMBERSHIP_RECORDS_SHA256
    )
    if not formal_inputs_match:
        return False
    if not require_strategy_scope:
        return True
    return (
        isinstance(strategy_scope, dict)
        and strategy_scope.get("snapshot_id", "").startswith("ssu_")
        and strategy_scope.get("manifest_sha256")
        and strategy_scope.get("scope_identity_sha256")
        and strategy_scope.get("daily_members_sha256")
        and strategy_scope.get("protocol_snapshot_id") == PROTOCOL_ID
        and strategy_scope.get("market_scope") == ["SH", "SZ"]
        and strategy_scope.get("path", "").startswith(
            "data/pit/strategy_scoped_universe_snapshots/ssu_"
        )
    )


def resolve_formal_input_bindings(repo_root: Path) -> dict[str, Any]:
    """Resolve the current B3 input and lifecycle roots from pinned formal artifacts."""
    repo_root = Path(repo_root).resolve()
    snapshot = _bound_manifest(
        repo_root,
        "data/pit/v3_formal_data_snapshot_manifests/" + FORMAL_SNAPSHOT_ID,
        FORMAL_SNAPSHOT_ID,
        "snapshot_id",
        FORMAL_SNAPSHOT_MANIFEST_SHA256,
    )
    return {
        "formal_snapshot": {
            "id": FORMAL_SNAPSHOT_ID,
            "semantic_hash": snapshot.get("semantic_hash"),
            "manifest_sha256": FORMAL_SNAPSHOT_MANIFEST_SHA256,
        },
        "b3_execution_input": _b3_execution_input_binding(repo_root, snapshot),
        "stock_basic_lifecycle": _stock_basic_lifecycle_binding(repo_root),
        "membership": {
            "id": MEMBERSHIP_ID,
            "manifest_sha256": MEMBERSHIP_MANIFEST_SHA256,
            "records_sha256": MEMBERSHIP_RECORDS_SHA256,
        },
    }


def build_lineage(
    repo_root: Path = ROOT,
    *,
    code_root: Path | None = None,
    artifact_root: Path | None = None,
    source_inventory_dir: Path | None = None,
    strategy_scope_root: Path | None = None,
    include_strategy_scope: bool = True,
    expected_scope_id: str | None = None,
    expected_scope_manifest_sha256: str | None = None,
) -> dict[str, Any]:
    code_root = _resolve_code_root(code_root)
    repo_root = Path(artifact_root if artifact_root is not None else repo_root).resolve(strict=True)
    source_inventory_dir = Path(source_inventory_dir) if source_inventory_dir is not None else repo_root / "data/pit/v3_b5_source_inventories" / SOURCE_INVENTORY_ID
    source_verified = verify_source_inventory(repo_root, source_inventory_dir)
    if source_verified.get("status") != "verified" or source_verified.get("artifact_id") != SOURCE_INVENTORY_ID or source_verified.get("manifest_sha256") != SOURCE_INVENTORY_MANIFEST_SHA256:
        raise ValueError("source_inventory is not the verified v3 B5 successor")

    supplement = _bound_manifest(repo_root, "data/pit/v3_execution_semantics_supplements/" + SUPPLEMENT_ID, SUPPLEMENT_ID, "supplement_id", SUPPLEMENT_MANIFEST_SHA256)
    snapshot = _bound_manifest(repo_root, "data/pit/v3_formal_data_snapshot_manifests/" + FORMAL_SNAPSHOT_ID, FORMAL_SNAPSHOT_ID, "snapshot_id", FORMAL_SNAPSHOT_MANIFEST_SHA256)
    formal_input_bindings = resolve_formal_input_bindings(repo_root)
    _bound_manifest(repo_root, "data/pit/v3_b4_is_results/" + B4_ID, B4_ID, "artifact_id", B4_MANIFEST_SHA256)
    membership = _bound_manifest(repo_root, "data/pit/pit_membership_snapshots/" + MEMBERSHIP_ID, MEMBERSHIP_ID, "snapshot_id", MEMBERSHIP_MANIFEST_SHA256)
    membership_records = repo_root / "data/pit/pit_membership_snapshots" / MEMBERSHIP_ID / "records.parquet"
    if not membership_records.exists() or _sha(membership_records) != MEMBERSHIP_RECORDS_SHA256:
        raise ValueError("membership records hash mismatch")
    if membership.get("records_parquet_sha256") != MEMBERSHIP_RECORDS_SHA256:
        raise ValueError("membership manifest records binding mismatch")
    _bound_manifest(repo_root, "data/pit/shsz_common_trade_calendars/" + CALENDAR_ID, CALENDAR_ID, "artifact_id", CALENDAR_MANIFEST_SHA256)
    _bound_manifest(repo_root, "data/pit/historical_scope_freezes/" + SCOPE_ID, SCOPE_ID, "artifact_id", SCOPE_MANIFEST_SHA256)
    event_path = repo_root / "data/pit/v3_b4_is_results" / B4_ID / "event_result.json"
    event_sidecar = event_path.with_name(event_path.name + ".sha256")
    if not event_path.exists() or not event_sidecar.exists() or _sha(event_path) != B4_EVENT_SHA256 or event_sidecar.read_text(encoding="utf-8").split()[0] != B4_EVENT_SHA256:
        raise ValueError("B4 event result hash mismatch")

    lineage = {
        "template": dict(TEMPLATE),
        "strategy_revision_id": REVISION_ID,
        "protocol_snapshot_id": PROTOCOL_ID,
        "execution_supplement": {"id": SUPPLEMENT_ID, "manifest_sha256": SUPPLEMENT_MANIFEST_SHA256},
        "formal_snapshot": {
            "id": FORMAL_SNAPSHOT_ID,
            "semantic_hash": snapshot.get("semantic_hash"),
            "manifest_sha256": FORMAL_SNAPSHOT_MANIFEST_SHA256,
        },
        "b3_execution_input": formal_input_bindings["b3_execution_input"],
        "stock_basic_lifecycle": formal_input_bindings["stock_basic_lifecycle"],
        "b4": {"artifact_id": B4_ID, "manifest_sha256": B4_MANIFEST_SHA256, "event_sha256": B4_EVENT_SHA256},
        "source_inventory": {"artifact_id": SOURCE_INVENTORY_ID, "manifest_sha256": SOURCE_INVENTORY_MANIFEST_SHA256},
        "membership": {"id": MEMBERSHIP_ID, "manifest_sha256": MEMBERSHIP_MANIFEST_SHA256, "records_sha256": MEMBERSHIP_RECORDS_SHA256},
        "calendar": {"id": CALENDAR_ID, "manifest_sha256": CALENDAR_MANIFEST_SHA256, "date_set_sha256": CALENDAR_DATE_SET_SHA256},
        "scope": {"id": SCOPE_ID, "manifest_sha256": SCOPE_MANIFEST_SHA256},
        "gate_criteria_envelope_hash": GATE_ENVELOPE_HASH,
        "is_range": dict(IS_RANGE),
    }
    if include_strategy_scope:
        from backend.services.strategy_scoped_pit_universe import (
            SCOPE_SNAPSHOT_ROOT,
            verify_scope_snapshot,
            _build_from_trusted_inputs,
            _trusted_source_inputs,
        )

        scope_root = (
            Path(strategy_scope_root)
            if strategy_scope_root is not None
            else repo_root / SCOPE_SNAPSHOT_ROOT
        )
        scope_root = scope_root.resolve(strict=True)
        expected_scope_root = (repo_root / SCOPE_SNAPSHOT_ROOT).resolve(strict=True)
        if scope_root != expected_scope_root:
            raise ValueError("strategy scope root is outside the explicit artifact root")
        expected_scope, _expected_members = _build_from_trusted_inputs(
            _trusted_source_inputs(code_root, artifact_root=repo_root)
        )
        if expected_scope_id is not None and expected_scope["snapshot_id"] != expected_scope_id:
            raise ValueError("strategy-scoped PIT universe does not match the bound snapshot ID")
        scope_dir = scope_root / expected_scope["snapshot_id"]
        verified_scope = verify_scope_snapshot(
            code_root,
            scope_dir,
            artifact_root=repo_root,
            expected_snapshot_id=expected_scope["snapshot_id"],
            expected_manifest_sha256=expected_scope_manifest_sha256,
        )
        if verified_scope.get("status") != "verified":
            raise ValueError(
                "strategy-scoped PIT universe verification failed: "
                + str(verified_scope.get("reason", verified_scope))
            )
        lineage["strategy_scoped_universe"] = {
            "snapshot_id": verified_scope["snapshot_id"],
            "path": (
                SCOPE_SNAPSHOT_ROOT / verified_scope["snapshot_id"]
            ).as_posix(),
            "manifest_sha256": verified_scope["manifest_sha256"],
            "scope_identity_sha256": verified_scope["scope_identity_sha256"],
            "daily_members_sha256": verified_scope["daily_members_sha256"],
            "market_scope": ["SH", "SZ"],
            "protocol_snapshot_id": PROTOCOL_ID,
            "oos_window": expected_scope["oos_window"],
        }
    return lineage


def _bundle_core(
    lineage: dict[str, Any],
    refs: dict[str, dict[str, str]],
    verifier_identity: dict[str, str],
    *,
    legacy_no_scope: bool = False,
) -> dict[str, Any]:
    formal_b6_scope = _lineage_has_formal_b6_inputs(
        lineage, require_strategy_scope=not legacy_no_scope
    )
    return {
        "schema_version": SCHEMA,
        "status": "verified",
        "authorization_scope": (
            FORMAL_B6_PREFLIGHT_SCOPE
            if formal_b6_scope
            else FIXTURE_B5_SCOPE
        ),
        "not_authorized_for_b6_oos_gate_promotion_signal": not formal_b6_scope,
        "verifier_identity": verifier_identity,
        "lineage": lineage,
        "results": refs,
    }


def _not_authorized(reasons: list[str]) -> dict[str, Any]:
    return {"status": "not_authorized", "not_authorized_for_b6_oos_gate_promotion_signal": True, "missing_or_invalid": sorted(set(reasons))}


def _expected_files(core: dict[str, Any], payloads: dict[str, dict[str, Any]]) -> dict[str, bytes]:
    bundle_id = sha256_bytes(canonical_json(core))[:16]
    manifest = {**core, "bundle_id": bundle_id}
    files = {"manifest.json": canonical_json(manifest)}
    for result_type, payload in payloads.items():
        files[PAYLOAD_FILES[result_type]] = canonical_json(payload)
    for name, raw in list(files.items()):
        files[name + ".sha256"] = f"{sha256_bytes(raw)}  {name}\n".encode("utf-8")
    return files


def _write_once(target: Path, files: dict[str, bytes]) -> str:
    if target.exists():
        if not target.is_dir() or {path.name for path in target.iterdir()} != set(files):
            raise ValueError("v3 B5 bundle write-once conflict")
        for name, expected in files.items():
            path = target / name
            if not path.is_file() or path.read_bytes() != expected:
                raise ValueError("v3 B5 bundle write-once conflict")
        return "already_published"
    output_root = target.parent
    output_root.mkdir(parents=True, exist_ok=True)
    staging_prefix = f".{target.name}.staging-"
    staging = Path(tempfile.mkdtemp(prefix=staging_prefix, dir=output_root))
    for name, raw in files.items():
        path = staging / name
        with tempfile.NamedTemporaryFile(dir=staging, prefix=name + ".", suffix=".tmp", delete=False) as handle:
            temp = Path(handle.name)
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    os.replace(staging, target)
    return "published"


def _validated_payloads(
    results: dict[str, dict[str, Any]], lineage: dict[str, Any]
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    payloads: dict[str, dict[str, Any]] = {}
    reasons: list[str] = []
    for result_type in RESULT_TYPES:
        if result_type not in results:
            reasons.append(result_type)
            continue
        try:
            payloads[result_type] = _validate_payload_for_bundle(results[result_type], result_type, lineage)
        except (TypeError, ValueError, KeyError) as error:
            reasons.extend((result_type, f"{result_type}: {error}"))
    return payloads, reasons


def _validate_payload_for_bundle(
    payload: dict[str, Any], result_type: str, lineage: dict[str, Any]
) -> dict[str, Any]:
    allowed_extras = (
        _COST_LINEAGE_EXTRAS
        if result_type in {"base_transaction_cost", "stress_transaction_cost"}
        else _COMPARISON_LINEAGE_EXTRAS
    )
    payload_lineage = payload.get("lineage")
    if not isinstance(payload_lineage, dict):
        raise ValueError("result lineage must be an object")
    for key, value in lineage.items():
        if key in BUNDLE_ONLY_LINEAGE_KEYS:
            continue
        if payload_lineage.get(key) != value:
            raise ValueError("result lineage base binding mismatch")
    unexpected = set(payload_lineage) - set(lineage) - allowed_extras
    if unexpected:
        raise ValueError(f"unsupported result lineage fields: {sorted(unexpected)}")
    return validate_result_payload(payload, result_type, payload_lineage)


def publish_b5_bundle(
    repo_root: Path,
    results: dict[str, dict[str, Any]],
    output_root: Path,
    *,
    code_root: Path | None = None,
    artifact_root: Path | None = None,
    source_inventory_dir: Path | None = None,
    strategy_scope_root: Path | None = None,
    expected_scope_id: str | None = None,
    expected_scope_manifest_sha256: str | None = None,
) -> dict[str, Any]:
    try:
        lineage = build_lineage(
            repo_root,
            code_root=code_root,
            artifact_root=artifact_root,
            source_inventory_dir=source_inventory_dir,
            strategy_scope_root=strategy_scope_root,
            expected_scope_id=expected_scope_id,
            expected_scope_manifest_sha256=expected_scope_manifest_sha256,
        )
    except (OSError, TypeError, ValueError, KeyError) as error:
        return _not_authorized([f"source_inventory: {error}"])
    payloads, reasons = _validated_payloads(results, lineage)
    if reasons:
        return _not_authorized(reasons)
    refs = {
        result_type: {
            "payload_id": payload["payload_id"],
            "canonical_payload_sha256": payload["canonical_payload_sha256"],
            "path": PAYLOAD_FILES[result_type],
        }
        for result_type, payload in payloads.items()
    }
    verifier_identity = independent_verifier_identity()
    core = _bundle_core(lineage, refs, verifier_identity)
    bundle_id = sha256_bytes(canonical_json(core))[:16]
    files = _expected_files(core, payloads)
    status = _write_once(Path(output_root) / bundle_id, files)
    return {
        "status": status,
        "bundle_id": bundle_id,
        "path": str(Path(output_root) / bundle_id),
        "authorization_scope": core["authorization_scope"],
        "verifier_identity": verifier_identity,
        "not_authorized_for_b6_oos_gate_promotion_signal": core[
            "not_authorized_for_b6_oos_gate_promotion_signal"
        ],
    }


def verify_b5_bundle(
    repo_root: Path,
    bundle_dir: Path,
    *,
    code_root: Path | None = None,
    artifact_root: Path | None = None,
    source_inventory_dir: Path | None = None,
    strategy_scope_root: Path | None = None,
    expected_bundle_id: str | None = None,
    expected_bundle_manifest_sha256: str | None = None,
) -> dict[str, Any]:
    try:
        code_root = _resolve_code_root(code_root)
        artifact_root = Path(artifact_root if artifact_root is not None else repo_root).resolve(strict=True)
        bundle_dir = Path(bundle_dir)
        expected_names = {
            "manifest.json",
            "manifest.json.sha256",
            *PAYLOAD_FILES.values(),
            *(f"{name}.sha256" for name in PAYLOAD_FILES.values()),
        }
        if not bundle_dir.is_dir() or {path.name for path in bundle_dir.iterdir()} != expected_names:
            return {"status": "invalid", "reason": "bundle file set mismatch"}
        manifest_path = bundle_dir / "manifest.json"
        sidecar_path = bundle_dir / "manifest.json.sha256"
        if not manifest_path.exists() or not sidecar_path.exists():
            return {"status": "invalid", "reason": "bundle manifest or sidecar missing"}
        actual_manifest_sha = _sha(manifest_path)
        if expected_bundle_id is not None and bundle_dir.name != expected_bundle_id:
            return {"status": "invalid", "reason": "bundle ID does not match the requested ID"}
        if expected_bundle_manifest_sha256 is not None and actual_manifest_sha != expected_bundle_manifest_sha256:
            return {"status": "invalid", "reason": "bundle manifest hash does not match the requested hash"}
        expected_manifest_sidecar = f"{actual_manifest_sha}  manifest.json\n".encode("utf-8")
        if sidecar_path.read_bytes() != expected_manifest_sidecar:
            return {"status": "invalid", "reason": "bundle manifest sidecar mismatch"}
        manifest = _read(manifest_path)
        if manifest.get("schema_version") != SCHEMA or manifest.get("status") != "verified":
            return {"status": "invalid", "reason": "bundle schema or status mismatch"}
        legacy_no_scope = "strategy_scoped_universe" not in manifest.get("lineage", {})
        if legacy_no_scope and (
            bundle_dir.name != LEGACY_B5_BUNDLE_ID
            or actual_manifest_sha != LEGACY_B5_MANIFEST_SHA256
        ):
            return {"status": "invalid", "reason": "unscoped B5 bundle is not the pinned legacy artifact"}
        bound_scope = manifest.get("lineage", {}).get("strategy_scoped_universe", {})
        lineage = build_lineage(
            artifact_root,
            code_root=code_root,
            artifact_root=artifact_root,
            source_inventory_dir=source_inventory_dir,
            strategy_scope_root=strategy_scope_root,
            include_strategy_scope=not legacy_no_scope,
            expected_scope_id=bound_scope.get("snapshot_id") if not legacy_no_scope else None,
            expected_scope_manifest_sha256=bound_scope.get("manifest_sha256") if not legacy_no_scope else None,
        )
        if manifest.get("lineage") != lineage:
            return {"status": "invalid", "reason": "bundle lineage mismatch"}
        refs = manifest.get("results")
        if not isinstance(refs, dict) or set(refs) != set(RESULT_TYPES):
            return {"status": "invalid", "reason": "bundle result references mismatch"}
        payloads: dict[str, dict[str, Any]] = {}
        for result_type in RESULT_TYPES:
            ref = refs[result_type]
            if not ref or ref.get("path") != PAYLOAD_FILES[result_type]:
                return {"status": "invalid", "reason": f"missing result reference: {result_type}"}
            path = bundle_dir / ref["path"]
            sidecar = path.with_name(path.name + ".sha256")
            if not path.exists() or not sidecar.exists():
                return {"status": "invalid", "reason": f"missing result file: {result_type}"}
            raw = path.read_bytes()
            actual = sha256_bytes(raw)
            expected_sidecar = f"{actual}  {path.name}\n".encode("utf-8")
            if sidecar.read_bytes() != expected_sidecar:
                return {"status": "invalid", "reason": f"result sidecar mismatch: {result_type}"}
            payload = json.loads(raw.decode("utf-8"))
            payloads[result_type] = _validate_payload_for_bundle(payload, result_type, lineage)
            if ref.get("payload_id") != payload["payload_id"] or ref.get("canonical_payload_sha256") != payload["canonical_payload_sha256"]:
                return {"status": "invalid", "reason": f"result reference mismatch: {result_type}"}
        verifier_identity = (
            LEGACY_B5_VERIFIER_IDENTITY
            if legacy_no_scope
            else independent_verifier_identity()
        )
        if manifest.get("verifier_identity") != verifier_identity:
            return {"status": "invalid", "reason": "independent verifier identity mismatch"}
        core = _bundle_core(
            lineage, refs, verifier_identity, legacy_no_scope=legacy_no_scope
        )
        expected_id = sha256_bytes(canonical_json(core))[:16]
        expected_manifest = {**core, "bundle_id": expected_id}
        if manifest != expected_manifest or bundle_dir.name != expected_id:
            return {"status": "invalid", "reason": "bundle identity mismatch"}
        return {
            "status": "verified",
            "bundle_id": expected_id,
            "manifest_sha256": actual_manifest_sha,
            "result_count": len(payloads),
            "authorization_scope": core["authorization_scope"],
            "verifier_identity": verifier_identity,
            "lineage": lineage,
            "not_authorized_for_b6_oos_gate_promotion_signal": core[
                "not_authorized_for_b6_oos_gate_promotion_signal"
            ],
        }
    except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError) as error:
        return {"status": "invalid", "reason": str(error)}
