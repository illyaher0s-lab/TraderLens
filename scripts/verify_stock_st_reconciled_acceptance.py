#!/usr/bin/env python3
"""Strict standalone verifier for the Stock ST acceptance candidate."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path, PurePosixPath

import pyarrow.parquet as pq


ARTIFACT_ID = "stacc_traderlens_v2_shsz_stock_st_004"
POLICY_ID = "stock_st_acceptance_policy_v1_corrective_003"
POLICY_SHA256 = "a0ce6f21b0986cec50bffe8884fdc41de0b1d66036a36c56d13fc31c2c8c947d"
POLICY_RELATIVE = "data/pit/stock_st_acceptance_policies/stock_st_acceptance_policy_v1_corrective_003"
CANDIDATE_RELATIVE = "data/pit/.staging/stacc_traderlens_v2_shsz_stock_st_004"
FORMAL_RELATIVE = "data/pit/stock_st_reconciled_acceptances/stacc_traderlens_v2_shsz_stock_st_004"
PROJECT_PYTHON = Path(r"D:\Codex\TraderLens\.venv\Scripts\python.exe")
POLICY_VERIFIER = "scripts/verify_stock_st_acceptance_policy.py"
POLICY_ACCEPTED = f"ACCEPTED: {POLICY_ID}"
REQUIRED_COLUMNS = ["ts_code", "name", "trade_date", "type", "type_name"]
ARTIFACT_FILES = {
    "manifest.json",
    "manifest.json.sha256",
    "empty_outcomes.json",
    "empty_outcomes.json.sha256",
}
MANIFEST_KEYS = {
    "artifact_id", "policy_id", "policy_path", "policy_sha256", "schema_version", "frozen",
    "registered_stock_st_root", "b3_bindings", "calendar_binding", "schema_binding",
    "algorithm_binding", "partitions", "coverage", "outcomes",
}
PARTITION_KEYS = {
    "date", "repo_relative_path", "sidecar_repo_relative_path", "byte_size", "file_sha256",
    "sidecar_sha256", "row_count", "empty",
}
COVERAGE_KEYS = {
    "total_dates", "nonempty_dates", "empty_dates", "missing_dates", "extra_dates",
    "duplicate_dates", "total_bytes",
}
OUTCOMES_KEYS = {"artifact_id", "policy_id", "schema_version", "aggregate_sha256", "outcomes"}
OUTCOME_KEYS = {"request_trade_date", "request_sha256", "response_sha256", "outcome", "row_count"}


class VerificationError(RuntimeError):
    pass


class RejectingArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise VerificationError("verification error")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def compute_hash(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_hash(value: object) -> str:
    return sha256_bytes(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def reject(reason: str) -> None:
    raise VerificationError(reason)


def is_reparse(path: Path) -> bool:
    metadata = path.lstat()
    return path.is_symlink() or bool(getattr(metadata, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def plain_components(repo_root: Path, path: Path, label: str) -> None:
    try:
        relative = path.absolute().relative_to(repo_root.absolute())
    except ValueError:
        reject(label)
    cursor = repo_root
    for part in relative.parts:
        cursor /= part
        if not cursor.exists() and not cursor.is_symlink():
            reject(label)
        if is_reparse(cursor):
            reject("reparse")


def safe_relative(repo_root: Path, value: str, label: str) -> Path:
    if not isinstance(value, str):
        reject(label)
    logical = PurePosixPath(value)
    if logical.is_absolute() or ".." in logical.parts or "." in logical.parts:
        reject(label)
    path = repo_root.joinpath(*logical.parts)
    plain_components(repo_root, path, label)
    return path


def read_json(path: Path, reason: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        reject(reason)
    if not isinstance(value, dict):
        reject(reason)
    return value


def read_sidecar(path: Path, reason: str) -> str:
    sidecar = Path(f"{path}.sha256")
    try:
        declared = sidecar.read_text(encoding="ascii").strip()
    except (OSError, UnicodeError):
        reject(reason)
    actual = compute_hash(path)
    if declared != actual:
        reject(reason)
    return actual


def run_trust_root(repo_root: Path) -> dict:
    policy_dir = repo_root.joinpath(*POLICY_RELATIVE.split("/"))
    command = [
        str(PROJECT_PYTHON), str(repo_root / POLICY_VERIFIER), "--repo-root", str(repo_root),
        "--policy-dir", str(policy_dir),
    ]
    try:
        result = subprocess.run(command, cwd=repo_root, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        reject("trust root")
    if result.returncode != 0 or result.stdout.strip() != POLICY_ACCEPTED or result.stderr:
        reject("trust root")
    try:
        raw = (policy_dir / "policy.json").read_bytes()
    except OSError:
        reject("trust root")
    if sha256_bytes(raw) != POLICY_SHA256:
        reject("trust root")
    try:
        policy = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        reject("trust root")
    if not isinstance(policy, dict):
        reject("trust root")
    return policy


def artifact_path(repo_root: Path, raw_path: str, *, formal_mode: bool = False) -> Path:
    legacy = {f"stacc_traderlens_v2_shsz_stock_st_{suffix}" for suffix in ("001", "002", "003")}
    raw = Path(raw_path)
    if raw.name in legacy:
        reject(f"unaccepted_invalid_publication: {raw.name}")
    if ".." in raw.parts:
        reject("artifact path")
    expected_relative = FORMAL_RELATIVE if formal_mode else CANDIDATE_RELATIVE
    expected = repo_root.joinpath(*expected_relative.split("/"))
    if raw.is_absolute() or raw.as_posix() != expected_relative:
        reject("artifact path")
    plain_components(repo_root, expected, "artifact path")
    return expected


def verify_inventory(root: Path) -> tuple[dict, dict]:
    try:
        entries = list(root.iterdir())
    except OSError:
        reject("inventory")
    if {entry.name for entry in entries} != ARTIFACT_FILES:
        reject("inventory")
    for entry in entries:
        if entry.is_dir() or is_reparse(entry) or not entry.is_file():
            reject("inventory")
    manifest_path = root / "manifest.json"
    outcomes_path = root / "empty_outcomes.json"
    read_sidecar(manifest_path, "manifest sidecar")
    read_sidecar(outcomes_path, "outcomes sidecar")
    return read_json(manifest_path, "manifest schema"), read_json(outcomes_path, "outcomes schema")


def calendar_dates(repo_root: Path, policy: dict) -> tuple[list[str], dict]:
    bindings = policy.get("b3_package_bindings")
    calendar = policy.get("calendar_bindings")
    if not isinstance(bindings, dict) or not isinstance(calendar, dict):
        reject("policy binding")
    try:
        index_path = safe_relative(repo_root, bindings["input_index_path"], "B3 input binding")
        manifest_path = safe_relative(repo_root, bindings["manifest_path"], "B3 input binding")
        cal_path = safe_relative(repo_root, bindings["trade_cal_path"], "B3 input binding")
        cal_sidecar = safe_relative(repo_root, bindings["trade_cal_sidecar_path"], "B3 input binding")
    except KeyError:
        reject("policy binding")
    for path, hash_key in ((index_path, "input_index_sha256"), (manifest_path, "manifest_sha256"),
                           (cal_path, "trade_cal_sha256"), (cal_sidecar, "trade_cal_sidecar_sha256")):
        if not isinstance(bindings.get(hash_key), str) or compute_hash(path) != bindings[hash_key]:
            reject("B3 input binding")
    try:
        if cal_sidecar.read_text(encoding="ascii").strip() != compute_hash(cal_path):
            reject("B3 input binding")
        index = read_json(index_path, "B3 input binding")
        table = pq.read_table(cal_path)
        values = table.to_pydict()
        dates = sorted(str(d) for d, exchange, opened in zip(values["cal_date"], values["exchange"], values["is_open"])
                       if exchange == calendar["exchange"] and int(opened) == calendar["is_open"])
    except (KeyError, OSError, ValueError, TypeError, Exception) as exc:
        if isinstance(exc, VerificationError):
            raise
        reject("calendar binding")
    if (len(dates) != calendar.get("expected_dates") or dates[0] != calendar.get("first_date")
            or dates[-1] != calendar.get("last_date") or canonical_hash(dates) != calendar.get("canonical_date_set_sha256")):
        reject("calendar binding")
    try:
        entries = index["interfaces"]["stock_st"]["entries"]
    except (KeyError, TypeError):
        reject("B3 input binding")
    if not isinstance(entries, list):
        reject("B3 input binding")
    return dates, {entry.get("path"): entry for entry in entries if isinstance(entry, dict)}


def expected_partition_path(registered_root: str, date: str) -> str:
    return f"{registered_root}/trade_date={date}/part.parquet"


def preflight_partitions(repo_root: Path, policy: dict, manifest: dict) -> tuple[list[str], list[str], dict[str, dict]]:
    registered_root = policy.get("registered_stock_st_root")
    if not isinstance(registered_root, str):
        reject("policy binding")
    dates, entries = calendar_dates(repo_root, policy)
    partitions = manifest.get("partitions")
    if not isinstance(partitions, list) or len(partitions) != len(dates):
        reject("date set")
    declared_empty_dates = []
    for date, partition in zip(dates, partitions):
        if not isinstance(partition, dict) or set(partition) != PARTITION_KEYS:
            reject("manifest schema")
        relative = expected_partition_path(registered_root, date)
        sidecar_relative = relative + ".sha256"
        if partition.get("date") != date or partition.get("repo_relative_path") != relative or partition.get("sidecar_repo_relative_path") != sidecar_relative:
            reject("date set")
        if (type(partition["byte_size"]) is not int or type(partition["row_count"]) is not int
                or type(partition["empty"]) is not bool):
            reject("manifest schema")
        parquet_entry, sidecar_entry = entries.get(relative), entries.get(sidecar_relative)
        if not isinstance(parquet_entry, dict) or not isinstance(sidecar_entry, dict):
            reject("B3 input binding")
        if (partition["file_sha256"] != parquet_entry.get("sha256")
                or partition["sidecar_sha256"] != sidecar_entry.get("sha256")
                or partition["byte_size"] != parquet_entry.get("byte_size")):
            reject("B3 input binding")
        if partition["empty"]:
            declared_empty_dates.append(date)
    return dates, declared_empty_dates, entries


def scan_partitions(repo_root: Path, policy: dict, manifest: dict, dates: list[str], entries: dict[str, dict], declared_empty_dates: list[str]) -> None:
    partitions = manifest["partitions"]
    actual_empty_dates, total_bytes = [], 0
    for date, partition in zip(dates, partitions):
        relative = partition["repo_relative_path"]
        sidecar_relative = partition["sidecar_repo_relative_path"]
        try:
            parquet_entry, sidecar_entry = entries[relative], entries[sidecar_relative]
            parquet_path = safe_relative(repo_root, relative, "B3 input binding")
            sidecar_path = safe_relative(repo_root, sidecar_relative, "B3 input binding")
            if (compute_hash(parquet_path) != parquet_entry["sha256"] or compute_hash(sidecar_path) != sidecar_entry["sha256"]
                    or parquet_path.stat().st_size != parquet_entry["byte_size"]
                    or parquet_path.stat().st_size != partition["byte_size"]
                    or sidecar_path.stat().st_size != sidecar_entry["byte_size"]
                    or sidecar_path.read_text(encoding="ascii").strip() != parquet_entry["sha256"]):
                reject("B3 input binding")
            table = pq.read_table(parquet_path)
        except Exception:
            if isinstance(sys.exc_info()[1], VerificationError):
                raise
            reject("B3 input binding")
        if table.column_names != REQUIRED_COLUMNS:
            reject("parquet schema")
        types = [str(field.type) for field in table.schema]
        rows = table.num_rows
        if rows:
            if types != policy.get("schema_requirements", {}).get("nonempty_types") or any(column.null_count for column in table.columns):
                reject("parquet schema")
            values = table.to_pydict()
            if any(str(value) != date for value in values["trade_date"]):
                reject("row date")
            codes = [str(value) for value in values["ts_code"]]
            if any(not code for code in codes) or len(codes) != len(set(codes)):
                reject("ts_code")
        elif any(value not in policy.get("schema_requirements", {}).get("empty_allowed_types", []) for value in types):
            reject("parquet schema")
        if partition["row_count"] != rows or partition["empty"] != (rows == 0):
            reject("B3 input binding")
        total_bytes += parquet_path.stat().st_size
        if rows == 0:
            actual_empty_dates.append(date)
    if actual_empty_dates != declared_empty_dates:
        reject("coverage")
    coverage = manifest.get("coverage")
    if (not isinstance(coverage, dict) or set(coverage) != COVERAGE_KEYS
            or any(type(coverage[key]) is not int for key in COVERAGE_KEYS)):
        reject("coverage")
    expected_coverage = {
        "total_dates": len(dates), "nonempty_dates": len(dates) - len(actual_empty_dates), "empty_dates": len(actual_empty_dates),
        "missing_dates": 0, "extra_dates": 0, "duplicate_dates": 0, "total_bytes": total_bytes,
    }
    if coverage != expected_coverage:
        reject("coverage")


def verify_outcomes(root: Path, manifest: dict, outcomes: dict, empty_dates: list[str]) -> None:
    if set(outcomes) != OUTCOMES_KEYS or outcomes.get("artifact_id") != ARTIFACT_ID or outcomes.get("policy_id") != POLICY_ID or outcomes.get("schema_version") != "stock_st_empty_outcomes.v2":
        reject("outcomes schema")
    rows = outcomes.get("outcomes")
    if not isinstance(rows, list) or len(rows) != len(empty_dates):
        reject("outcomes schema")
    for date, row in zip(empty_dates, rows):
        if (not isinstance(row, dict) or set(row) != OUTCOME_KEYS
                or row.get("request_trade_date") != date or type(row.get("row_count")) is not int):
            reject("outcomes schema")
        request = canonical_hash({"endpoint": "stock_st", "params": {"trade_date": date}})
        response = canonical_hash({"columns": REQUIRED_COLUMNS, "endpoint": "stock_st", "outcome": "success_empty", "request_trade_date": date, "rows": []})
        if row.get("request_sha256") != request or row.get("response_sha256") != response or row.get("outcome") != "success_empty" or row.get("row_count") != 0:
            reject("outcomes binding")
    aggregate = {
        "algorithm_id": "stock_st_empty_outcomes_aggregate.v1", "items": rows,
        "item_fields": ["request_trade_date", "request_sha256", "response_sha256", "outcome", "row_count"],
        "sort_by": ["request_trade_date"],
    }
    if outcomes.get("aggregate_sha256") != canonical_hash(aggregate):
        reject("outcomes aggregate")
    binding = manifest.get("outcomes")
    outcomes_path = root / "empty_outcomes.json"
    if (not isinstance(binding, dict) or set(binding) != {"path", "sha256", "aggregate_sha256"}
            or binding.get("path") != "empty_outcomes.json" or binding.get("sha256") != compute_hash(outcomes_path)
            or binding.get("aggregate_sha256") != outcomes["aggregate_sha256"]):
        reject("outcomes binding")


def verify(repo_root_raw: str, artifact_root_raw: str, *, formal_mode: bool = False) -> None:
    try:
        repo_root = Path(repo_root_raw).resolve(strict=True)
    except OSError:
        reject("repo root")
    artifact_root = artifact_path(repo_root, artifact_root_raw, formal_mode=formal_mode)
    policy = run_trust_root(repo_root)
    manifest, outcomes = verify_inventory(artifact_root)
    if set(manifest) != MANIFEST_KEYS:
        reject("manifest schema")
    if (manifest.get("artifact_id") != ARTIFACT_ID or manifest.get("policy_id") != POLICY_ID
            or manifest.get("policy_path") != POLICY_RELATIVE or manifest.get("policy_sha256") != POLICY_SHA256
            or manifest.get("schema_version") != "stacc_stock_st_reconciled_acceptance.v2" or manifest.get("frozen") is not True):
        reject("policy binding")
    if (manifest.get("registered_stock_st_root") != policy.get("registered_stock_st_root")
            or manifest.get("b3_bindings") != policy.get("b3_package_bindings")
            or manifest.get("calendar_binding") != policy.get("calendar_bindings")
            or manifest.get("schema_binding") != policy.get("schema_requirements")
            or manifest.get("algorithm_binding") != policy.get("canonical_algorithms")):
        reject("policy binding")
    dates, declared_empty_dates, entries = preflight_partitions(repo_root, policy, manifest)
    verify_outcomes(artifact_root, manifest, outcomes, declared_empty_dates)
    scan_partitions(repo_root, policy, manifest, dates, entries, declared_empty_dates)


def main(argv: list[str] | None = None) -> int:
    parser = RejectingArgumentParser(add_help=False)
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--artifact-root", required=True)
    parser.add_argument("--formal-mode", action="store_true")
    try:
        args = parser.parse_args(argv)
        verify(args.repo_root, args.artifact_root, formal_mode=args.formal_mode)
    except (VerificationError, OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        print("REJECTED: " + (sys.exc_info()[1].args[0] if isinstance(sys.exc_info()[1], VerificationError) else "verification error"))
        return 1
    except BaseException:
        print("REJECTED: verification error")
        return 1
    print(f"ACCEPTED: {ARTIFACT_ID}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
