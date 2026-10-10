#!/usr/bin/env python3
"""Publish Stock ST Acceptance Policy V1 Corrective 003 atomically."""
from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path


POLICY_ID = "stock_st_acceptance_policy_v1_corrective_003"
CANDIDATE_RELATIVE = Path("data/pit/.staging/stock_st_acceptance_policy_v1_corrective_003")
FORMAL_RELATIVE = Path("data/pit/stock_st_acceptance_policies/stock_st_acceptance_policy_v1_corrective_003")
TRANSPORT_RELATIVE = Path("data/pit/stock_st_acceptance_policies/.staging_stock_st_acceptance_policy_v1_corrective_003")
ST004_FORMAL_GUARD = Path("data/pit/stock_st_reconciled_acceptances/stacc_traderlens_v2_shsz_stock_st_004")
ST004_STAGING_GUARD = Path("data/pit/.staging/stacc_traderlens_v2_shsz_stock_st_004")
EXPECTED_POLICY_SHA256 = "a0ce6f21b0986cec50bffe8884fdc41de0b1d66036a36c56d13fc31c2c8c947d"
EXPECTED_FILES = frozenset(
    {
        "contract_evidence.json",
        "contract_evidence.json.sha256",
        "policy.json",
        "policy.json.sha256",
        "tushare_doc_397_raw_capture.html",
        "tushare_doc_397_raw_capture.html.sha256",
    }
)
UUID_RE = re.compile(r"(?i)(?<![0-9a-f])[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}(?![0-9a-f])")
TIMESTAMP_RE = re.compile(r"(?<!\d)(?:19|20)\d{2}(?:[-_]\d{2}[-_]\d{2}|\d{4})(?!\d)")


class PolicyPublicationError(RuntimeError):
    pass


def _fail(message: str) -> None:
    raise PolicyPublicationError(message)


def _is_reparse(path: Path) -> bool:
    metadata = path.lstat()
    return bool(getattr(metadata, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _require_plain(path: Path, label: str) -> None:
    if path.is_symlink() or _is_reparse(path):
        _fail(f"{label} is symlink/junction/reparse")


def _safe_fixed_path(repo_root: Path, relative: Path, label: str) -> Path:
    if relative.is_absolute() or ".." in relative.parts or any(part in ("", ".") for part in relative.parts):
        _fail(f"{label} path escape")
    for part in relative.parts:
        if any(token in part for token in ("*", "?", "[", "]")):
            _fail(f"{label} glob not allowed")
        if UUID_RE.search(part):
            _fail(f"{label} UUID not allowed")
        if TIMESTAMP_RE.search(part):
            _fail(f"{label} timestamp not allowed")
    physical = repo_root.joinpath(*relative.parts)
    cursor = repo_root
    for part in relative.parts:
        cursor /= part
        if cursor.exists() or cursor.is_symlink():
            _require_plain(cursor, label)
    try:
        physical.resolve(strict=False).relative_to(repo_root)
    except ValueError:
        _fail(f"{label} path escape")
    return physical


def _inventory(path: Path) -> dict[str, tuple[int, str]]:
    if not path.is_dir():
        _fail(f"{path.name} inventory requires directory")
    actual: dict[str, tuple[int, str]] = {}
    for entry in sorted(path.rglob("*")):
        _require_plain(entry, f"{path.name} inventory")
        relative = entry.relative_to(path).as_posix()
        if entry.is_dir():
            _fail(f"{path.name} inventory unexpected directory: {relative}")
        if not entry.is_file():
            _fail(f"{path.name} inventory unexpected entry: {relative}")
        raw = entry.read_bytes()
        actual[relative] = (len(raw), hashlib.sha256(raw).hexdigest())
    if set(actual) != EXPECTED_FILES:
        _fail(
            f"{path.name} inventory mismatch: missing={sorted(EXPECTED_FILES - set(actual))}, "
            f"extra={sorted(set(actual) - EXPECTED_FILES)}"
        )
    return actual


def _run_verifier(repo_root: Path, policy_dir: Path, *, candidate_mode: bool) -> subprocess.CompletedProcess[str]:
    args = [
        sys.executable,
        str(repo_root / "scripts" / "verify_stock_st_acceptance_policy.py"),
        "--repo-root",
        str(repo_root),
        "--policy-dir",
        str(policy_dir),
    ]
    if candidate_mode:
        args.append("--candidate-mode")
    return subprocess.run(args, capture_output=True, text=True, check=False)


def _copy_artifact(source: Path, destination: Path) -> None:
    shutil.copyfile(source, destination)


def _check_stock_st_004_guards(repo_root: Path) -> None:
    for relative in (ST004_FORMAL_GUARD, ST004_STAGING_GUARD):
        path = repo_root.joinpath(*relative.parts)
        if path.exists() or path.is_symlink():
            _fail(f"stock_st_004_guard_present: {relative.as_posix()}")


def _verified_candidate(repo_root: Path, candidate: Path) -> dict[str, tuple[int, str]]:
    result = _run_verifier(repo_root, candidate, candidate_mode=True)
    if result.returncode != 0:
        _fail(f"candidate verifier rejected: {(result.stdout + result.stderr).strip()}")
    inventory = _inventory(candidate)
    if inventory["policy.json"][1] != EXPECTED_POLICY_SHA256:
        _fail("candidate policy hash mismatch")
    return inventory


def _verify_formal(repo_root: Path, formal: Path, *, failure_prefix: str = "formal verifier rejected") -> None:
    result = _run_verifier(repo_root, formal, candidate_mode=False)
    if result.returncode != 0:
        _fail(f"{failure_prefix}: {(result.stdout + result.stderr).strip()}")


def publish_policy(repo_root: Path | str) -> str:
    root_input = Path(repo_root)
    if not root_input.is_absolute():
        _fail("repo_root must be absolute")
    _require_plain(root_input, "repo root")
    root = root_input.resolve(strict=True)
    _check_stock_st_004_guards(root)

    candidate = _safe_fixed_path(root, CANDIDATE_RELATIVE, "candidate")
    formal = _safe_fixed_path(root, FORMAL_RELATIVE, "formal")
    transport = _safe_fixed_path(root, TRANSPORT_RELATIVE, "transport")
    candidate_inventory = _verified_candidate(root, candidate)

    if transport.exists() or transport.is_symlink():
        _fail("transport already exists")

    if formal.exists() or formal.is_symlink():
        formal_inventory = _inventory(formal)
        if formal_inventory != candidate_inventory:
            _fail("formal content conflict")
        _verify_formal(root, formal)
        return "already_published"

    formal_parent = formal.parent
    if not formal_parent.is_dir():
        _fail("formal parent missing")
    _require_plain(formal_parent, "formal parent")
    transport.mkdir()
    for relative in sorted(EXPECTED_FILES):
        _copy_artifact(candidate / relative, transport / relative)
    if _inventory(transport) != candidate_inventory:
        _fail("transport inventory mismatch")

    try:
        transport.rename(formal)
    except OSError as exc:
        raise PolicyPublicationError(f"atomic rename failed: {exc}") from exc

    _verify_formal(root, formal, failure_prefix="post-rename formal verifier rejected")
    return "published"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        status = publish_policy(args.repo_root)
    except (OSError, PolicyPublicationError, ValueError) as exc:
        print(f"REJECTED: {exc}")
        return 1
    print(status)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
