#!/usr/bin/env python3
"""Build the fixed Stock ST _004 candidate without publishing it."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import pyarrow.parquet as pq


FIXED_ID = "stacc_traderlens_v2_shsz_stock_st_004"
POLICY_ID = "stock_st_acceptance_policy_v1_corrective_003"
POLICY_SHA256 = "a0ce6f21b0986cec50bffe8884fdc41de0b1d66036a36c56d13fc31c2c8c947d"
POLICY_REL = "data/pit/stock_st_acceptance_policies/stock_st_acceptance_policy_v1_corrective_003"
CANDIDATE_REL = "data/pit/.staging/stacc_traderlens_v2_shsz_stock_st_004"
FORMAL_REL = "data/pit/stock_st_reconciled_acceptances/stacc_traderlens_v2_shsz_stock_st_004"
B3_REL = "data/pit/b3_execution_input_packages/b3eip_traderlens_v2_shsz_pit_001"
PROJECT_PYTHON = Path(r"D:\Codex\TraderLens\.venv\Scripts\python.exe")
STANDALONE = "scripts/verify_stock_st_reconciled_acceptance.py"
REQUIRED_COLUMNS = ["ts_code", "name", "trade_date", "type", "type_name"]


class BuildError(RuntimeError):
    pass


class RejectingArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise BuildError("invalid arguments")


def hash_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def file_hash(path: Path) -> str:
    return hash_bytes(path.read_bytes())


def canonical_hash(value: object) -> str:
    return hash_bytes(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise BuildError("invalid JSON object")
    return value


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def build_candidate(repo_root: Path) -> Path:
    repo_root = repo_root.resolve(strict=True)
    candidate = repo_root / Path(*CANDIDATE_REL.split("/"))
    formal = repo_root / Path(*FORMAL_REL.split("/"))
    if candidate.exists():
        raise BuildError("candidate exists")
    if formal.exists():
        raise BuildError("formal guard")

    policy_dir = repo_root / Path(*POLICY_REL.split("/"))
    policy_path = policy_dir / "policy.json"
    policy_raw = policy_path.read_bytes()
    if hash_bytes(policy_raw) != POLICY_SHA256:
        raise BuildError("policy trust root")
    policy = json.loads(policy_raw.decode("utf-8"))
    if policy.get("policy_id") != POLICY_ID:
        raise BuildError("policy trust root")

    b3_root = repo_root / Path(*B3_REL.split("/"))
    index_path = b3_root / "input_index.json"
    calendar_path = b3_root / "inputs/trade_cal/part.parquet"
    index = load_json(index_path)
    calendar = pq.read_table(calendar_path).to_pydict()
    dates = sorted(
        str(date)
        for date, exchange, opened in zip(calendar["cal_date"], calendar["exchange"], calendar["is_open"])
        if exchange == "SSE" and int(opened) == 1
    )
    expected_dates = policy["calendar_bindings"]
    if (len(dates) != expected_dates["expected_dates"]
            or dates[0] != expected_dates["first_date"]
            or dates[-1] != expected_dates["last_date"]
            or canonical_hash(dates) != expected_dates["canonical_date_set_sha256"]):
        raise BuildError("calendar binding")

    entries = {entry["path"]: entry for entry in index["interfaces"]["stock_st"]["entries"]}
    partitions = []
    empty_dates = []
    total_bytes = 0
    registered_root = policy["registered_stock_st_root"]
    for date in dates:
        relative = f"{registered_root}/trade_date={date}/part.parquet"
        side_relative = relative + ".sha256"
        parquet_path = repo_root / Path(*relative.split("/"))
        sidecar_path = repo_root / Path(*side_relative.split("/"))
        parquet_entry = entries.get(relative)
        sidecar_entry = entries.get(side_relative)
        if not isinstance(parquet_entry, dict) or not isinstance(sidecar_entry, dict):
            raise BuildError("B3 input binding")
        parquet_hash = file_hash(parquet_path)
        sidecar_hash = file_hash(sidecar_path)
        if (parquet_hash != parquet_entry["sha256"] or sidecar_hash != sidecar_entry["sha256"]
                or parquet_path.stat().st_size != parquet_entry["byte_size"]
                or sidecar_path.stat().st_size != sidecar_entry["byte_size"]
                or sidecar_path.read_text(encoding="ascii").strip() != parquet_hash):
            raise BuildError("B3 input binding")
        rows = pq.read_table(parquet_path).num_rows
        if rows == 0:
            empty_dates.append(date)
        total_bytes += parquet_path.stat().st_size
        partitions.append({
            "date": date,
            "repo_relative_path": relative,
            "sidecar_repo_relative_path": side_relative,
            "byte_size": parquet_path.stat().st_size,
            "file_sha256": parquet_hash,
            "sidecar_sha256": sidecar_hash,
            "row_count": rows,
            "empty": rows == 0,
        })

    outcome_rows = []
    for date in empty_dates:
        request_hash = canonical_hash({"endpoint": "stock_st", "params": {"trade_date": date}})
        response_hash = canonical_hash({
            "columns": REQUIRED_COLUMNS,
            "endpoint": "stock_st",
            "outcome": "success_empty",
            "request_trade_date": date,
            "rows": [],
        })
        outcome_rows.append({
            "request_trade_date": date,
            "request_sha256": request_hash,
            "response_sha256": response_hash,
            "outcome": "success_empty",
            "row_count": 0,
        })
    aggregate = {
        "algorithm_id": "stock_st_empty_outcomes_aggregate.v1",
        "items": outcome_rows,
        "item_fields": ["request_trade_date", "request_sha256", "response_sha256", "outcome", "row_count"],
        "sort_by": ["request_trade_date"],
    }
    outcomes = {
        "artifact_id": FIXED_ID,
        "policy_id": POLICY_ID,
        "schema_version": "stock_st_empty_outcomes.v2",
        "aggregate_sha256": canonical_hash(aggregate),
        "outcomes": outcome_rows,
    }
    candidate.mkdir(parents=True)
    outcomes_path = candidate / "empty_outcomes.json"
    write_json(outcomes_path, outcomes)
    (candidate / "empty_outcomes.json.sha256").write_text(file_hash(outcomes_path) + "\n", encoding="ascii")
    manifest = {
        "artifact_id": FIXED_ID,
        "policy_id": POLICY_ID,
        "policy_path": POLICY_REL,
        "policy_sha256": POLICY_SHA256,
        "schema_version": "stacc_stock_st_reconciled_acceptance.v2",
        "frozen": True,
        "registered_stock_st_root": registered_root,
        "b3_bindings": policy["b3_package_bindings"],
        "calendar_binding": policy["calendar_bindings"],
        "schema_binding": policy["schema_requirements"],
        "algorithm_binding": policy["canonical_algorithms"],
        "partitions": partitions,
        "coverage": {
            "total_dates": len(partitions),
            "nonempty_dates": len(partitions) - len(empty_dates),
            "empty_dates": len(empty_dates),
            "missing_dates": 0,
            "extra_dates": 0,
            "duplicate_dates": 0,
            "total_bytes": total_bytes,
        },
        "outcomes": {
            "path": "empty_outcomes.json",
            "sha256": file_hash(outcomes_path),
            "aggregate_sha256": outcomes["aggregate_sha256"],
        },
    }
    manifest_path = candidate / "manifest.json"
    write_json(manifest_path, manifest)
    (candidate / "manifest.json.sha256").write_text(file_hash(manifest_path) + "\n", encoding="ascii")

    result = subprocess.run(
        [str(PROJECT_PYTHON), str(repo_root / STANDALONE), "--repo-root", str(repo_root), "--artifact-root", CANDIDATE_REL],
        cwd=repo_root, capture_output=True, text=True, timeout=300,
    )
    if result.returncode != 0 or result.stderr or result.stdout.strip() != f"ACCEPTED: {FIXED_ID}":
        raise BuildError("candidate verifier rejected")
    print(f"STAGED: {CANDIDATE_REL}")
    print(result.stdout.strip())
    return candidate


def run_verifier(repo_root: Path, artifact_relative: str, formal_mode: bool = False):
    command = [
        str(PROJECT_PYTHON), str(repo_root / STANDALONE),
        "--repo-root", str(repo_root), "--artifact-root", artifact_relative,
    ]
    if formal_mode:
        command.append("--formal-mode")
    return subprocess.run(command, cwd=repo_root, capture_output=True, text=True, timeout=300)


def verifier_accepted(result) -> bool:
    return result.returncode == 0 and result.stderr == "" and result.stdout.strip() == f"ACCEPTED: {FIXED_ID}"


def publish_formal(repo_root: Path, verifier_runner=None) -> Path:
    repo_root = repo_root.resolve(strict=True)
    candidate = repo_root / Path(*CANDIDATE_REL.split("/"))
    formal = repo_root / Path(*FORMAL_REL.split("/"))
    if not candidate.is_dir() or candidate.is_symlink():
        raise BuildError("candidate missing")
    if formal.exists() or formal.is_symlink():
        raise BuildError("formal exists")
    formal.parent.mkdir(parents=True, exist_ok=True)
    runner = verifier_runner or run_verifier
    result = runner(repo_root, CANDIDATE_REL, False)
    if not verifier_accepted(result):
        raise BuildError("candidate verifier rejected")
    candidate.rename(formal)
    result = runner(repo_root, FORMAL_REL, True)
    if not verifier_accepted(result):
        raise BuildError("post-rename formal verifier rejected")
    print(f"PUBLISHED: {FORMAL_REL}")
    print(result.stdout.strip())
    return formal


def main(argv: list[str] | None = None) -> int:
    parser = RejectingArgumentParser(add_help=False)
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--publish-formal", action="store_true")
    try:
        args = parser.parse_args(argv)
        if args.publish_formal:
            publish_formal(Path(args.repo_root))
        else:
            build_candidate(Path(args.repo_root))
    except BuildError as exc:
        print(f"REJECTED: {exc}")
        return 1
    except BaseException:
        print("REJECTED: build error")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
