"""Publish the verified v3 B5 four-result bundle exactly once."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from backend.services.v3_b5_bundle import (
    BUNDLE_ONLY_LINEAGE_KEYS,
    IS_RANGE,
    build_lineage,
    publish_b5_bundle,
)
from backend.services.v3_b5_types import validate_result_payload


ROOT = Path(__file__).resolve().parents[1]
COST_ARTIFACT_ID = "991f167678ebb2e9"
COST_MANIFEST_SHA256 = "b89d701a6d5fc3cc36757f37823f6dfe29c61d704a6dd360ed321a373aff2564"
COMPARISON_ARTIFACT_ID = "8eec0787b345639a"
COMPARISON_MANIFEST_SHA256 = "e19d9f51ba9b1026e6463d7eabc11dfdcda1890f3d9ab8b283248aa9d654123a"
COST_SCHEMA = "v3_b5_costs.v1"
COMPARISON_SCHEMA = "v3_b5_comparison_bundle.v1"
OUTPUT_ROOT = ROOT / "data/pit/v3_b5_validation_bundles"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _check_sidecar(path: Path) -> str:
    sidecar = path.with_name(path.name + ".sha256")
    if not path.exists() or not sidecar.exists():
        raise ValueError(f"missing source file or sidecar: {path}")
    actual = _sha(path)
    if sidecar.read_text(encoding="utf-8").split()[0] != actual:
        raise ValueError(f"source sidecar mismatch: {path}")
    return actual


def _load_manifest(directory: Path, *, artifact_id: str, expected_sha: str, schema: str, status: str) -> dict[str, Any]:
    path = directory / "manifest.json"
    actual = _check_sidecar(path)
    if actual != expected_sha:
        raise ValueError(f"source manifest hash mismatch: {directory}")
    manifest = _read_json(path)
    if manifest.get("artifact_id") != artifact_id:
        raise ValueError(f"source identity mismatch: {directory}")
    if manifest.get("schema_version") != schema or manifest.get("status") != status:
        raise ValueError(f"source manifest status/schema mismatch: {directory}")
    return manifest


def _check_base_lineage(payload: dict[str, Any], base_lineage: dict[str, Any]) -> None:
    lineage = payload.get("lineage")
    if not isinstance(lineage, dict):
        raise ValueError("source result lineage is not an object")
    for key, expected in base_lineage.items():
        if key in BUNDLE_ONLY_LINEAGE_KEYS:
            continue
        if lineage.get(key) != expected:
            raise ValueError(f"source result base lineage mismatch: {key}")


def _load_source_payloads(
    directory: Path,
    manifest: dict[str, Any],
    result_types: tuple[str, ...],
    base_lineage: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    payloads: dict[str, dict[str, Any]] = {}
    refs = manifest.get("results")
    if not isinstance(refs, dict):
        raise ValueError(f"source result references missing: {directory}")
    for result_type in result_types:
        ref = refs.get(result_type)
        if not isinstance(ref, dict) or ref.get("path") is None:
            raise ValueError(f"source result reference missing: {result_type}")
        path = directory / str(ref["path"])
        _check_sidecar(path)
        payload = _read_json(path)
        if payload.get("lineage") != manifest.get("lineage"):
            raise ValueError(f"source result lineage/manifest mismatch: {result_type}")
        _check_base_lineage(payload, base_lineage)
        validate_result_payload(payload, result_type, payload["lineage"])
        expected_observation_hash = payload["lineage"].get("daily_observation_hash") or payload["lineage"].get("ledger_observation", {}).get("observations_sha256")
        if expected_observation_hash is not None and payload.get("daily_observation_hash") != expected_observation_hash:
            raise ValueError(f"source observation hash mismatch: {result_type}")
        if ref.get("payload_id") != payload.get("payload_id") or ref.get("canonical_payload_sha256") != payload.get("canonical_payload_sha256"):
            raise ValueError(f"source result identity/reference mismatch: {result_type}")
        payloads[result_type] = payload
    return payloads


def _validate_comparison_sequence(
    comparison_manifest: dict[str, Any],
    payloads: dict[str, dict[str, Any]],
    repo_root: Path,
) -> None:
    expected_range = comparison_manifest.get("is_range")
    calendar = pd.read_parquet(repo_root / "data/pit/shsz_common_trade_calendars/shsz_common_trade_calendar_v1/szse_trade_cal.parquet", columns=["cal_date", "is_open"])
    expected_dates = [
        str(day)[:4] + "-" + str(day)[4:6] + "-" + str(day)[6:8]
        for day in calendar.loc[
            (calendar["is_open"] == 1)
            & (calendar["cal_date"].astype(str) >= IS_RANGE["start"].replace("-", ""))
            & (calendar["cal_date"].astype(str) <= IS_RANGE["end"].replace("-", "")),
            "cal_date",
        ].tolist()
    ]
    for result_type in ("benchmark_comparison", "same_universe_control_comparison"):
        result = payloads[result_type]["result"]
        if result.get("is_range") != expected_range:
            raise ValueError(f"comparison range mismatch: {result_type}")
        daily_rows = result.get("daily_rows")
        if not isinstance(daily_rows, list) or len(daily_rows) != expected_range.get("count"):
            raise ValueError(f"comparison daily sequence gap or count mismatch: {result_type}")
        daily_dates = [row.get("date") for row in daily_rows if isinstance(row, dict)]
        if len(daily_dates) != len(daily_rows) or any(not isinstance(day, str) for day in daily_dates):
            raise ValueError(f"comparison daily date missing: {result_type}")
        if any(day < IS_RANGE["start"] or day > IS_RANGE["end"] for day in daily_dates):
            raise ValueError(f"comparison future or out-of-range date: {result_type}")
        if daily_dates != expected_dates:
            raise ValueError(f"comparison daily sequence gap or reorder: {result_type}")
        rebalances = result.get("rebalances")
        if not isinstance(rebalances, list) or len(rebalances) != comparison_manifest.get("weekly_schedule_count"):
            raise ValueError(f"comparison rebalance count mismatch: {result_type}")
        for rebalance in rebalances:
            if not isinstance(rebalance, dict):
                raise ValueError(f"comparison rebalance record invalid: {result_type}")
            for key in ("as_of_date", "execution_date", "formation_date"):
                value = rebalance.get(key)
                if value is None:
                    continue
                if value > IS_RANGE["end"] or (key != "as_of_date" and value < IS_RANGE["start"]):
                    raise ValueError(f"comparison rebalance future or out-of-range date: {result_type}")


def load_verified_results(
    repo_root: Path = ROOT,
    *,
    code_root: Path | None = None,
    artifact_root: Path | None = None,
    cost_dir: Path | None = None,
    comparison_dir: Path | None = None,
    strategy_scope_root: Path | None = None,
    include_strategy_scope: bool = True,
    expected_scope_id: str | None = None,
    expected_scope_manifest_sha256: str | None = None,
) -> dict[str, dict[str, Any]]:
    code_root = Path(code_root) if code_root is not None else Path(__file__).resolve().parents[1]
    repo_root = Path(artifact_root if artifact_root is not None else repo_root).resolve()
    cost_dir = Path(cost_dir) if cost_dir is not None else repo_root / "data/pit/v3_b5_costs" / COST_ARTIFACT_ID
    comparison_dir = Path(comparison_dir) if comparison_dir is not None else repo_root / "data/pit/v3_b5_comparisons" / COMPARISON_ARTIFACT_ID
    base_lineage = build_lineage(
        repo_root,
        code_root=code_root,
        artifact_root=repo_root,
        strategy_scope_root=strategy_scope_root,
        include_strategy_scope=include_strategy_scope,
        expected_scope_id=expected_scope_id,
        expected_scope_manifest_sha256=expected_scope_manifest_sha256,
    )
    cost_manifest = _load_manifest(cost_dir, artifact_id=COST_ARTIFACT_ID, expected_sha=COST_MANIFEST_SHA256, schema=COST_SCHEMA, status="valid")
    comparison_manifest = _load_manifest(comparison_dir, artifact_id=COMPARISON_ARTIFACT_ID, expected_sha=COMPARISON_MANIFEST_SHA256, schema=COMPARISON_SCHEMA, status="verified")
    cost_payloads = _load_source_payloads(cost_dir, cost_manifest, ("base_transaction_cost", "stress_transaction_cost"), base_lineage)
    comparison_payloads = _load_source_payloads(
        comparison_dir,
        comparison_manifest,
        ("benchmark_comparison", "same_universe_control_comparison"),
        base_lineage,
    )
    cost_assumptions_hash = cost_manifest.get("cost_assumptions_hash")
    if any(payload.get("cost_assumptions_hash") != cost_assumptions_hash for payload in cost_payloads.values()):
        raise ValueError("cost assumptions binding mismatch")
    if any(payload.get("cost_assumptions_hash") != cost_assumptions_hash for payload in comparison_payloads.values()):
        raise ValueError("comparison cost assumptions binding mismatch")
    if comparison_manifest.get("lineage", {}).get("cost_artifact") != {
        "artifact_id": COST_ARTIFACT_ID,
        "cost_assumptions_hash": cost_assumptions_hash,
        "manifest_sha256": COST_MANIFEST_SHA256,
    }:
        raise ValueError("comparison cost artifact lineage mismatch")
    _validate_comparison_sequence(comparison_manifest, comparison_payloads, repo_root)
    return {**cost_payloads, **comparison_payloads}


def _not_authorized(reason: str) -> dict[str, Any]:
    return {
        "status": "not_authorized",
        "not_authorized_for_b6_oos_gate_promotion_signal": True,
        "missing_or_invalid": [reason],
    }


def publish_verified_b5_bundle(
    repo_root: Path = ROOT,
    output_root: Path | None = None,
    *,
    code_root: Path | None = None,
    artifact_root: Path | None = None,
    cost_dir: Path | None = None,
    comparison_dir: Path | None = None,
    strategy_scope_root: Path | None = None,
    expected_scope_id: str | None = None,
    expected_scope_manifest_sha256: str | None = None,
) -> dict[str, Any]:
    code_root = Path(code_root) if code_root is not None else Path(__file__).resolve().parents[1]
    repo_root = Path(artifact_root if artifact_root is not None else repo_root).resolve()
    output_root = Path(output_root) if output_root is not None else repo_root / "data/pit/v3_b5_validation_bundles"
    try:
        results = load_verified_results(
            repo_root,
            code_root=code_root,
            artifact_root=repo_root,
            cost_dir=cost_dir,
            comparison_dir=comparison_dir,
            strategy_scope_root=strategy_scope_root,
        )
    except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError) as error:
        return _not_authorized(str(error))
    return publish_b5_bundle(
        Path(repo_root),
        results,
        Path(output_root),
        code_root=code_root,
        artifact_root=repo_root,
        strategy_scope_root=strategy_scope_root,
        expected_scope_id=expected_scope_id,
        expected_scope_manifest_sha256=expected_scope_manifest_sha256,
    )


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Publish one B5 bundle against explicitly bound roots")
    parser.add_argument("--code-root", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--strategy-scope-root", type=Path, required=True)
    parser.add_argument("--scope-id", required=True)
    parser.add_argument("--scope-manifest-sha256", required=True)
    args = parser.parse_args()
    response = publish_verified_b5_bundle(
        args.artifact_root,
        code_root=args.code_root,
        artifact_root=args.artifact_root,
        strategy_scope_root=args.strategy_scope_root,
        expected_scope_id=args.scope_id,
        expected_scope_manifest_sha256=args.scope_manifest_sha256,
    )
    print(json.dumps(response, ensure_ascii=False, sort_keys=True))
    if response.get("status") not in {"published", "already_published"}:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
