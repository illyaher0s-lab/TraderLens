"""Publish the single v3 theoretical benchmark/control comparison artifact."""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from backend.services.formal_pit_partition_adapter import FormalPITPartitionAdapter
from backend.services.v3_b5_bundle import build_lineage
from backend.services.v3_b5_comparison import (
    BASE_COST_ID,
    BASE_COST_MANIFEST_SHA,
    BASE_COST_BPS,
    ComparisonError,
    IS_END,
    IS_START,
    INITIAL_NAV,
    INVENTORY_ID,
    INVENTORY_MANIFEST_SHA,
    OBSERVATION_ID,
    OBSERVATION_MANIFEST_SHA,
    OBSERVATION_SHA,
    OOS_START,
    ReadBoundAdapter,
    STRESS_COST_BPS,
    _FormalComparisonSource,
    build_weekly_schedule,
    canonical_json,
    run_fractional_index,
    sha256_bytes,
    sha256_file,
)
from backend.services.v3_b5_source_inventory import verify_source_inventory
from backend.services.v3_b5_types import build_result_payload
from scripts.qualify_v3_historical_coverage import DEFAULT_LIFECYCLE_MANIFEST, LIFECYCLE_ID, _load_lifecycle


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / "data/pit/v3_b5_comparisons"
COST_ROOT = ROOT / "data/pit/v3_b5_costs" / BASE_COST_ID
OBS_ROOT = ROOT / "data/pit/v3_b5_ledger_observations" / OBSERVATION_ID
SOURCE_ROOT = ROOT / "data/pit/v3_b5_source_inventories" / INVENTORY_ID
SCHEMA = "v3_b5_comparison_bundle.v1"
COVERAGE_ID = "1e79d26460c0c109"
COVERAGE_MANIFEST_SHA = "b009ae38cb87cf7c2adbfa0ce6d179d51225b08602ffcca431ed8d1a7135dfd6"
MISSING_MARK_DIAGNOSTIC_PATH = "docs/verification/v3_b5_comparison_missing_mark_diagnostic.json"
MISSING_MARK_DIAGNOSTIC_SHA = "ab0e788b69c245d0a405d4f63bd900eb98902a33f170ae060540fbe98325098f"


def _read(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _sidecar_hash(path: Path) -> str:
    actual = sha256_file(path)
    sidecar = path.with_name(path.name + ".sha256")
    if not sidecar.exists() or not sidecar.read_text(encoding="utf-8").split()[0] == actual:
        raise ComparisonError(f"sidecar mismatch: {path}")
    return actual


def _write_once(target: Path, files: dict[str, bytes]) -> str:
    expected_names = set(files) | {name + ".sha256" for name in files}
    if target.exists():
        if not target.is_dir() or {path.name for path in target.iterdir()} != expected_names:
            raise ComparisonError("comparison artifact write-once conflict")
        for name, raw in files.items():
            path = target / name
            sidecar = path.with_name(path.name + ".sha256")
            expected_sidecar = f"{sha256_bytes(raw)}  {name}\n".encode("utf-8")
            if not path.is_file() or path.read_bytes() != raw or not sidecar.is_file() or sidecar.read_bytes() != expected_sidecar:
                raise ComparisonError("comparison artifact write-once conflict")
        return "already_published"
    staging = Path(tempfile.mkdtemp(prefix=target.name + ".staging.", dir=target.parent))
    for name, raw in files.items():
        path = staging / name
        with tempfile.NamedTemporaryFile(dir=staging, prefix=name + ".", suffix=".tmp", delete=False) as handle:
            temp = Path(handle.name)
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
        sidecar = path.with_name(path.name + ".sha256")
        sidecar_raw = f"{sha256_bytes(raw)}  {name}\n".encode("utf-8")
        with tempfile.NamedTemporaryFile(dir=staging, prefix=name + ".sha256.", suffix=".tmp", delete=False) as handle:
            sidecar_temp = Path(handle.name)
            handle.write(sidecar_raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(sidecar_temp, sidecar)
    os.replace(staging, target)
    return "published"


def _load_cost_binding(repo_root: Path, cost_dir: Path | None = None) -> tuple[dict[str, Any], str]:
    directory = Path(cost_dir) if cost_dir is not None else COST_ROOT
    manifest_path = directory / "manifest.json"
    manifest_sha = _sidecar_hash(manifest_path)
    if manifest_sha != BASE_COST_MANIFEST_SHA:
        raise ComparisonError("verified cost manifest hash mismatch")
    manifest = _read(manifest_path)
    if manifest.get("artifact_id") != BASE_COST_ID or manifest.get("status") != "valid" or manifest.get("not_authorized_for_b6_oos_gate_promotion_signal") is not True:
        raise ComparisonError("cost artifact identity/authorization mismatch")
    if manifest.get("is_range") != {"start": IS_START.isoformat(), "end": IS_END.isoformat()} or manifest.get("fill_count") != 124:
        raise ComparisonError("cost artifact IS binding mismatch")
    for name in ("base_transaction_cost.json", "stress_transaction_cost.json"):
        _sidecar_hash(directory / name)
    return manifest, manifest["cost_assumptions_hash"]


def _load_observation_binding(observation_dir: Path | None = None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    directory = Path(observation_dir) if observation_dir is not None else OBS_ROOT
    manifest_path = directory / "manifest.json"
    observations_path = directory / "observations.json"
    if _sidecar_hash(manifest_path) != OBSERVATION_MANIFEST_SHA or _sidecar_hash(observations_path) != OBSERVATION_SHA:
        raise ComparisonError("ledger observation binding mismatch")
    manifest = _read(manifest_path)
    observations = _read(observations_path)
    if manifest.get("artifact_id") != OBSERVATION_ID or manifest.get("status") != "valid" or manifest.get("not_authorized_for_b6_oos_gate_promotion_signal") is not True:
        raise ComparisonError("ledger observation identity/status mismatch")
    if manifest.get("observations", {}).get("count") != 176 or manifest.get("observations", {}).get("sha256") != OBSERVATION_SHA:
        raise ComparisonError("ledger observation summary mismatch")
    if manifest.get("is_range", {}).get("start") != IS_START.isoformat() or manifest.get("is_range", {}).get("end") != IS_END.isoformat():
        raise ComparisonError("ledger observation IS range mismatch")
    return manifest, observations


def _load_industry_index(repo_root: Path) -> dict[str, list[dict[str, Any]]]:
    verification = verify_source_inventory(repo_root, SOURCE_ROOT)
    if verification.get("status") != "verified":
        raise ComparisonError(f"source inventory is not verified: {verification}")
    inventory = _read(SOURCE_ROOT / "manifest.json")
    source_manifest = repo_root / inventory["source_manifest_path"]
    if sha256_file(source_manifest) != inventory["source_manifest_sha256"]:
        raise ComparisonError("SW2021 source manifest hash mismatch")
    source_dir = source_manifest.parent
    index: dict[str, list[dict[str, Any]]] = {}
    for partition in inventory["partitions"]:
        path = source_dir / partition["name"]
        if sha256_file(path) != partition["sha256"]:
            raise ComparisonError(f"SW2021 partition hash mismatch: {partition['name']}")
        for row in pq.read_table(path).to_pylist():
            try:
                start = date(int(row["in_date"][:4]), int(row["in_date"][4:6]), int(row["in_date"][6:8]))
                raw_end = row.get("out_date")
                end = None if raw_end in (None, "") else date(int(raw_end[:4]), int(raw_end[4:6]), int(raw_end[6:8]))
            except (TypeError, ValueError, KeyError) as exc:
                raise ComparisonError(f"invalid SW2021 effective date: {partition['name']}") from exc
            index.setdefault(row["ts_code"], []).append({"l1_code": row["l1_code"], "l1_name": row["l1_name"], "in_date": start, "out_date": end})
    return index


def _load_coverage_binding(repo_root: Path) -> tuple[dict[tuple[str, str], dict[str, Any]], dict[str, Any]]:
    coverage_dir = repo_root / "data/pit/v3_historical_coverage_packages" / COVERAGE_ID
    manifest_path = coverage_dir / "manifest.json"
    manifest_sha = _sidecar_hash(manifest_path)
    if manifest_sha != COVERAGE_MANIFEST_SHA:
        raise ComparisonError("historical coverage manifest hash mismatch")
    manifest = _read(manifest_path)
    if manifest.get("artifact_id") != COVERAGE_ID or manifest.get("status") != "published":
        raise ComparisonError("historical coverage identity/status mismatch")
    if manifest.get("coverage", {}).get("data_fault_count") != 0:
        raise ComparisonError("historical coverage contains data faults")
    unavailable_path = coverage_dir / "unavailable_security_dates.parquet"
    unavailable_sha = sha256_file(unavailable_path)
    declared = manifest.get("files", {}).get("unavailable", {})
    if declared.get("sha256") != unavailable_sha:
        raise ComparisonError("historical coverage unavailable file hash mismatch")
    unavailable: dict[tuple[str, str], dict[str, Any]] = {}
    for row in pq.read_table(unavailable_path).to_pylist():
        execution = row.get("execution_date")
        symbol = row.get("symbol")
        status = row.get("status")
        if not isinstance(execution, str) or not isinstance(symbol, str) or status not in {"unavailable", "unavailable_ineligible"}:
            raise ComparisonError("invalid historical coverage unavailable row")
        unavailable[(execution, symbol)] = row
    return unavailable, {
        "artifact_id": COVERAGE_ID,
        "manifest_sha256": manifest_sha,
        "unavailable_sha256": unavailable_sha,
        "manifest_repo_relative_path": manifest_path.relative_to(repo_root).as_posix(),
        "unavailable_repo_relative_path": unavailable_path.relative_to(repo_root).as_posix(),
    }


def _load_missing_mark_diagnostic(repo_root: Path) -> dict[str, Any]:
    path = repo_root / MISSING_MARK_DIAGNOSTIC_PATH
    if sha256_file(path) != MISSING_MARK_DIAGNOSTIC_SHA:
        raise ComparisonError("missing-mark diagnostic hash mismatch")
    diagnostic = _read(path)
    if diagnostic.get("status") != "diagnostic_only" or diagnostic.get("not_authorized_for_b4_b5_b6_oos_gate_promotion_signal") is not True:
        raise ComparisonError("missing-mark diagnostic authorization/status mismatch")
    events = diagnostic.get("all_gap_events")
    if not isinstance(events, list) or len(events) != 14 or any(event.get("classification") != "B" for event in events):
        raise ComparisonError("missing-mark diagnostic event set mismatch")
    return {
        "path": MISSING_MARK_DIAGNOSTIC_PATH,
        "sha256": MISSING_MARK_DIAGNOSTIC_SHA,
        "event_count": len(events),
        "classification_counts": {"B": len(events)},
        "authorization": "audit_evidence_only",
    }


def _load_source(repo_root: Path) -> tuple[_FormalComparisonSource, tuple[date, ...], list[dict[str, Any]]]:
    raw = FormalPITPartitionAdapter(repo_root)
    guarded = ReadBoundAdapter(raw, IS_END)
    all_common_dates = tuple(guarded.common_trading_dates(date(1900, 1, 1), IS_END))
    dates = tuple(day for day in all_common_dates if IS_START <= day <= IS_END)
    if len(dates) != 176 or dates[0] != IS_START or dates[-1] != IS_END:
        raise ComparisonError("formal common calendar IS mismatch")
    lifecycle, lifecycle_binding = _load_lifecycle(raw.stock_basic_root, DEFAULT_LIFECYCLE_MANIFEST)
    coverage_unavailable, coverage_binding = _load_coverage_binding(repo_root)
    source = _FormalComparisonSource(
        guarded,
        _load_industry_index(repo_root),
        lifecycle=lifecycle,
        coverage_unavailable=coverage_unavailable,
    )
    source.lifecycle_binding = {"artifact_id": LIFECYCLE_ID, **lifecycle_binding}
    source.coverage_binding = coverage_binding
    return source, dates, build_weekly_schedule(all_common_dates, IS_START, IS_END)


def build_comparison_payloads(repo_root: Path = ROOT, *, cost_dir: Path | None = None, observation_dir: Path | None = None) -> dict[str, Any]:
    repo_root = Path(repo_root).resolve()
    lineage = build_lineage(repo_root)
    cost_manifest, cost_assumptions_hash = _load_cost_binding(repo_root, cost_dir)
    observation_manifest, observations = _load_observation_binding(observation_dir)
    missing_mark_diagnostic = _load_missing_mark_diagnostic(repo_root)
    source, dates, schedule = _load_source(repo_root)
    # Share the formal adapter/partition cache while keeping position marks
    # independent between benchmark and control runs.
    base_source = _FormalComparisonSource(
        source.adapter,
        source.industry_index,
        lifecycle=source.lifecycle,
        coverage_unavailable=source.coverage_unavailable,
    )
    cost_binding = {"artifact_id": cost_manifest["artifact_id"], "manifest_sha256": sha256_file(Path(cost_dir) / "manifest.json") if cost_dir is not None else BASE_COST_MANIFEST_SHA}
    observation_binding = {"artifact_id": observation_manifest["artifact_id"], "manifest_sha256": sha256_file(Path(observation_dir) / "manifest.json") if observation_dir is not None else OBSERVATION_MANIFEST_SHA, "observations_sha256": OBSERVATION_SHA}
    result_benchmark = run_fractional_index(kind="benchmark", source=source, dates=dates, schedule=schedule, strategy_observations=observations, cost_binding=cost_binding, observation_binding=observation_binding)
    result_control = run_fractional_index(kind="control", source=base_source, dates=dates, schedule=schedule, strategy_observations=observations, cost_binding=cost_binding, observation_binding=observation_binding)
    lineage = {
        **lineage,
        "cost_artifact": {"artifact_id": BASE_COST_ID, "manifest_sha256": BASE_COST_MANIFEST_SHA, "cost_assumptions_hash": cost_assumptions_hash},
        "ledger_observation": {"artifact_id": OBSERVATION_ID, "manifest_sha256": OBSERVATION_MANIFEST_SHA, "observations_sha256": OBSERVATION_SHA},
        "comparison_contract": {"schema_kind": "theoretical_fractional_comparison_index", "initial_nav": INITIAL_NAV, "base_cost_bps": BASE_COST_BPS, "stress_cost_bps": STRESS_COST_BPS},
        "lifecycle_successor": source.lifecycle_binding,
        "historical_coverage": source.coverage_binding,
        "missing_mark_diagnostic": missing_mark_diagnostic,
    }
    source_hashes = {
        "comparison_service": {"path": "backend/services/v3_b5_comparison.py", "sha256": sha256_file(repo_root / "backend/services/v3_b5_comparison.py")},
        "publisher": {"path": "scripts/publish_v3_b5_comparisons.py", "sha256": sha256_file(Path(__file__))},
        "verifier": {"path": "scripts/verify_v3_b5_comparisons.py", "sha256": sha256_file(repo_root / "scripts/verify_v3_b5_comparisons.py")},
    }
    benchmark_payload = build_result_payload(
        "benchmark_comparison", lineage=lineage, result=result_benchmark, producer_algorithm_hash=sha256_file(repo_root / "backend/services/v3_b5_comparison.py"), cost_assumptions_hash=cost_assumptions_hash, daily_observation_hash=OBSERVATION_SHA,
    )
    control_payload = build_result_payload(
        "same_universe_control_comparison", lineage=lineage, result=result_control, producer_algorithm_hash=sha256_file(repo_root / "backend/services/v3_b5_comparison.py"), cost_assumptions_hash=cost_assumptions_hash, daily_observation_hash=OBSERVATION_SHA,
    )
    refs = {
        "benchmark_comparison": {"payload_id": benchmark_payload["payload_id"], "canonical_payload_sha256": benchmark_payload["canonical_payload_sha256"], "path": "benchmark_comparison.json"},
        "same_universe_control_comparison": {"payload_id": control_payload["payload_id"], "canonical_payload_sha256": control_payload["canonical_payload_sha256"], "path": "same_universe_control.json"},
    }
    core = {
        "schema_version": SCHEMA,
        "status": "verified",
        "authorization_scope": "v3_b5_theoretical_fractional_comparison_only",
        "not_authorized_for_b6_oos_gate_promotion_signal": True,
        "schema_kind": "theoretical_fractional_comparison_index",
        "lineage": lineage,
        "results": refs,
        "source_hashes": source_hashes,
        "is_range": {"start": IS_START.isoformat(), "end": IS_END.isoformat(), "count": len(dates), "oos_start": OOS_START.isoformat()},
        "weekly_schedule_count": len(schedule),
        "non_executable": True,
    }
    artifact_id = sha256_bytes(canonical_json(core))[:16]
    manifest = {**core, "artifact_id": artifact_id}
    return {"manifest": manifest, "benchmark": benchmark_payload, "control": control_payload, "artifact_id": artifact_id, "source_hashes": source_hashes}


def publish(repo_root: Path = ROOT, output_root: Path = OUTPUT_ROOT, *, cost_dir: Path | None = None, observation_dir: Path | None = None) -> dict[str, Any]:
    built = build_comparison_payloads(repo_root, cost_dir=cost_dir, observation_dir=observation_dir)
    files = {
        "manifest.json": canonical_json(built["manifest"]),
        "benchmark_comparison.json": canonical_json(built["benchmark"]),
        "same_universe_control.json": canonical_json(built["control"]),
    }
    target = Path(output_root) / built["artifact_id"]
    status = _write_once(target, files)
    return {"status": status, "artifact_id": built["artifact_id"], "path": str(target), "manifest_sha256": sha256_file(target / "manifest.json"), "benchmark_payload_id": built["benchmark"]["payload_id"], "control_payload_id": built["control"]["payload_id"]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, default=OUTPUT_ROOT)
    args = parser.parse_args()
    print(json.dumps(publish(output_root=args.output_root), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
