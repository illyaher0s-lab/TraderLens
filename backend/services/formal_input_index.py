"""Canonical file index for a B3 execution-input package."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path, PurePosixPath
from typing import Iterable


PHYSICAL_INTERFACES = (
    "daily",
    "daily_basic",
    "adj_factor",
    "stk_limit",
    "suspend_d",
    "stock_st",
    "trade_cal",
)
INPUT_INDEX_SCHEMA_VERSION = "b3_execution_input_index.v1"
INPUT_INDEX_ALGORITHM = {
    "algorithm_id": "sha256_sorted_repo_relative_files_v1",
    "file_hash": "sha256(raw_bytes)",
    "interface_hash": "sha256(canonical_json(sorted_entries))",
    "index_hash": "sha256(canonical_json(index_without_input_index_hash))",
}
LEGACY_BINDINGS = {
    "ds_traderlens_v2_shsz_pit_001": {
        "snapshot_id": "ds_traderlens_v2_shsz_pit_001",
        "semantic_hash": (
            "da057716d4b4162b89fb89b7fd15864b4385d65cdee4e760a0743108cf1b135e"
        ),
    },
    "pims_traderlens_v2_shsz_sw2021_pit_005": {
        "snapshot_id": "pims_traderlens_v2_shsz_sw2021_pit_005",
        "manifest_hash": (
            "32f58adbca49fb89dfeb54ceeb4ac9b27b6a26c55e0c9cfeae7a8fcaf3683f10"
        ),
    },
    "coverage_695245b51005e50b": {
        "package_id": "695245b51005e50b",
        "manifest_hash": (
            "4e8b6163d4db11836e8a3aedc542d69ed6707bab566b6e0b16cb124d2b1e705f"
        ),
    },
}


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def input_index_algorithm_hash() -> str:
    return hashlib.sha256(canonical_json_bytes(INPUT_INDEX_ALGORITHM)).hexdigest()


def is_link_or_junction(path: Path) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    return path.is_symlink() or bool(
        getattr(info, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


def _interface_payload(entries: list[dict]) -> dict:
    entries = sorted(entries, key=lambda item: item["path"])
    return {
        "entries": entries,
        "entry_count": len(entries),
        "total_bytes": sum(item["byte_size"] for item in entries),
        "interface_content_hash": hashlib.sha256(
            canonical_json_bytes(entries)
        ).hexdigest(),
    }


def finalize_input_index(
    interface_entries: dict[str, list[dict]],
    *,
    formal_input_root_repo_relative: str,
    exact_bindings: dict,
) -> dict:
    interfaces = {
        name: _interface_payload(interface_entries[name])
        for name in PHYSICAL_INTERFACES
    }
    payload = {
        "schema_version": INPUT_INDEX_SCHEMA_VERSION,
        "algorithm_id": INPUT_INDEX_ALGORITHM["algorithm_id"],
        "algorithm_hash": input_index_algorithm_hash(),
        "formal_input_root_repo_relative": formal_input_root_repo_relative,
        "interfaces": interfaces,
        "exact_bindings": exact_bindings,
    }
    return {
        **payload,
        "input_index_hash": hashlib.sha256(canonical_json_bytes(payload)).hexdigest(),
    }


def build_input_index(
    root: Path,
    *,
    formal_input_root_repo_relative: str | None = None,
    exact_bindings: dict | None = None,
) -> dict:
    """Hash every regular file under all seven required physical interfaces."""

    root = Path(root)
    legacy_mode = (
        formal_input_root_repo_relative is None and exact_bindings is None
    )
    final_root = "" if legacy_mode else str(formal_input_root_repo_relative)
    bindings = LEGACY_BINDINGS if legacy_mode else dict(exact_bindings or {})
    all_entries: dict[str, list[dict]] = {}
    missing = [name for name in PHYSICAL_INTERFACES if not (root / name).is_dir()]
    if missing:
        raise ValueError(f"missing required interface: {missing[0]}")
    for name in PHYSICAL_INTERFACES:
        interface_root = root / name
        entries = []
        for path in sorted(interface_root.rglob("*")):
            if is_link_or_junction(path):
                raise ValueError(f"symlink or junction is forbidden: {path}")
            if not path.is_file():
                continue
            relative = path.relative_to(interface_root).as_posix()
            entries.append(
                {
                        "path": (
                            f"{name}/{relative}"
                            if legacy_mode
                            else f"{final_root}/{name}/{relative}"
                        ),
                    "sha256": sha256_file(path),
                    "byte_size": path.stat().st_size,
                }
            )
        if not entries and not legacy_mode:
            raise ValueError(f"required interface is empty: {name}")
        all_entries[name] = entries
    result = finalize_input_index(
        all_entries,
        formal_input_root_repo_relative=final_root,
        exact_bindings=bindings,
    )
    if legacy_mode:
        result["bindings"] = bindings
    return result


def _entry_physical_path(
    entry_path: str,
    *,
    registered_root: str,
    physical_root: Path,
) -> Path:
    pure_entry = PurePosixPath(entry_path)
    pure_root = PurePosixPath(registered_root)
    if pure_entry.is_absolute() or ".." in pure_entry.parts or ".staging" in pure_entry.parts:
        raise ValueError(f"path escape: {entry_path}")
    if registered_root in {"", "."}:
        return physical_root.joinpath(*pure_entry.parts)
    try:
        suffix = pure_entry.relative_to(pure_root)
    except ValueError as exc:
        raise ValueError(f"path outside registered input root: {entry_path}") from exc
    return physical_root.joinpath(*suffix.parts)


def verify_input_index(index: dict, root: Path) -> dict:
    """Independently recompute an index against a physical package input root."""

    root = Path(root)
    errors: list[str] = []
    expected_names = set(PHYSICAL_INTERFACES)
    if set(index.get("interfaces", {})) != expected_names:
        errors.append("physical interface set mismatch")
        return {"is_valid": False, "errors": errors, "error": "; ".join(errors)}
    if index.get("algorithm_id") != INPUT_INDEX_ALGORITHM["algorithm_id"]:
        errors.append("input-index algorithm id mismatch")
    if index.get("algorithm_hash") != input_index_algorithm_hash():
        errors.append("input-index algorithm hash mismatch")

    registered_root = index.get("formal_input_root_repo_relative", "")
    registered_files: set[Path] = set()
    recomputed: dict[str, list[dict]] = {}
    for name in PHYSICAL_INTERFACES:
        declared = index["interfaces"][name]
        entries: list[dict] = []
        for entry in declared.get("entries", []):
            try:
                path = _entry_physical_path(
                    entry["path"],
                    registered_root=registered_root,
                    physical_root=root,
                )
            except (KeyError, TypeError, ValueError) as exc:
                errors.append(str(exc))
                continue
            registered_files.add(path)
            if is_link_or_junction(path):
                errors.append(f"symlink or junction is forbidden: {entry['path']}")
                continue
            if not path.is_file():
                errors.append(f"missing file: {entry['path']}")
                continue
            actual_hash = sha256_file(path)
            if actual_hash != entry.get("sha256"):
                errors.append(f"hash mismatch: {entry['path']}")
            actual_size = path.stat().st_size
            if actual_size != entry.get("byte_size"):
                errors.append(f"byte size mismatch: {entry['path']}")
            entries.append(
                {
                    "path": entry["path"],
                    "sha256": actual_hash,
                    "byte_size": actual_size,
                }
            )
        recomputed[name] = entries
        expected_interface = _interface_payload(entries)
        for key in ("entry_count", "total_bytes", "interface_content_hash"):
            if declared.get(key) != expected_interface[key]:
                errors.append(f"{name} {key} mismatch")

    scan_roots = (
        [root / name for name in PHYSICAL_INTERFACES]
        if "bindings" in index
        else [root]
    )
    for scan_root in scan_roots:
        if not scan_root.is_dir():
            continue
        for path in scan_root.rglob("*"):
            if is_link_or_junction(path):
                errors.append(f"symlink or junction is forbidden: {path}")
                continue
            if path.is_file() and path not in registered_files:
                errors.append(f"extra file: {path.relative_to(root).as_posix()}")

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
    expected_hash = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    if index.get("input_index_hash") != expected_hash:
        errors.append("input_index_hash mismatch")

    return {"is_valid": not errors, "errors": errors, "error": "; ".join(errors)}
