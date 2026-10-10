"""Independent verifier for the v3 theoretical benchmark/control artifact."""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from backend.services.v3_b5_comparison import ComparisonError, canonical_json, sha256_bytes, sha256_file, validate_daily_rows
from backend.services.v3_b5_types import validate_result_payload
from scripts.publish_v3_b5_comparisons import (
    ROOT,
    SCHEMA,
    build_comparison_payloads,
)


def _read(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _sidecar(path: Path) -> str:
    actual = sha256_file(path)
    sidecar = path.with_name(path.name + ".sha256")
    expected = f"{actual}  {path.name}\n".encode("utf-8")
    if not sidecar.is_file() or sidecar.read_bytes() != expected:
        raise ComparisonError(f"sidecar mismatch: {path}")
    return actual


def verify_artifact(
    artifact_dir: Path,
    repo_root: Path = ROOT,
    *,
    cost_dir: Path | None = None,
    observation_dir: Path | None = None,
) -> dict:
    directory = Path(artifact_dir)
    expected_names = {
        "manifest.json",
        "manifest.json.sha256",
        "benchmark_comparison.json",
        "benchmark_comparison.json.sha256",
        "same_universe_control.json",
        "same_universe_control.json.sha256",
    }
    if not directory.is_dir() or {path.name for path in directory.iterdir()} != expected_names:
        raise ComparisonError("comparison artifact file set mismatch")
    manifest_path = directory / "manifest.json"
    benchmark_path = directory / "benchmark_comparison.json"
    control_path = directory / "same_universe_control.json"
    manifest_sha = _sidecar(manifest_path)
    _sidecar(benchmark_path)
    _sidecar(control_path)
    manifest = _read(manifest_path)
    benchmark = _read(benchmark_path)
    control = _read(control_path)
    if manifest.get("schema_version") != SCHEMA or manifest.get("status") != "verified":
        raise ComparisonError("comparison manifest schema/status mismatch")
    if manifest.get("schema_kind") != "theoretical_fractional_comparison_index" or manifest.get("non_executable") is not True:
        raise ComparisonError("comparison executable disclosure mismatch")
    if manifest.get("not_authorized_for_b6_oos_gate_promotion_signal") is not True:
        raise ComparisonError("comparison authorization disclosure mismatch")
    if manifest.get("results", {}).get("benchmark_comparison", {}).get("path") != "benchmark_comparison.json":
        raise ComparisonError("benchmark result path mismatch")
    if manifest.get("results", {}).get("same_universe_control_comparison", {}).get("path") != "same_universe_control.json":
        raise ComparisonError("control result path mismatch")

    rebuilt = build_comparison_payloads(
        Path(repo_root),
        cost_dir=cost_dir,
        observation_dir=observation_dir,
    )
    if canonical_json(benchmark) != canonical_json(rebuilt["benchmark"]):
        raise ComparisonError("independently rebuilt benchmark differs")
    if canonical_json(control) != canonical_json(rebuilt["control"]):
        raise ComparisonError("independently rebuilt control differs")
    if canonical_json(manifest) != canonical_json(rebuilt["manifest"]):
        raise ComparisonError("independently rebuilt manifest differs")

    lineage = rebuilt["manifest"]["lineage"]
    validate_result_payload(benchmark, "benchmark_comparison", lineage)
    validate_result_payload(control, "same_universe_control_comparison", lineage)
    expected_id = sha256_bytes(canonical_json({key: value for key, value in manifest.items() if key != "artifact_id"}))[:16]
    if manifest.get("artifact_id") != expected_id or directory.name != expected_id:
        raise ComparisonError("comparison artifact identity mismatch")
    for payload in (benchmark, control):
        result = payload["result"]
        rows = result["daily_rows"]
        dates = [date.fromisoformat(item["date"]) for item in rows]
        if len(rows) != 176 or dates[0].isoformat() != "2025-06-27" or dates[-1].isoformat() != "2026-03-19":
            raise ComparisonError("comparison daily range/count mismatch")
        validate_daily_rows(rows, dates)
        if len(result.get("rebalances", [])) != 38:
            raise ComparisonError("comparison weekly rebalance count mismatch")
        if any(date >= date.fromisoformat("2026-03-20") for date in dates):
            raise ComparisonError("comparison result contains OOS date")
        if any(row.get("schema_kind") != "theoretical_fractional_comparison_index" for row in [result]):
            raise ComparisonError("comparison result schema kind mismatch")
    return {
        "status": "verified",
        "artifact_id": expected_id,
        "path": str(directory),
        "manifest_sha256": manifest_sha,
        "benchmark_payload_id": benchmark["payload_id"],
        "control_payload_id": control["payload_id"],
        "daily_count": 176,
        "rebalance_count": 38,
        "not_authorized_for_b6_oos_gate_promotion_signal": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact_dir", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify_artifact(args.artifact_dir), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
