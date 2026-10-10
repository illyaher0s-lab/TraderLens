"""Run exactly one v3 IS event backtest with a read-only observation sink."""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from backend.services.backtest_engine_qualification import BacktestEngineQualification
from backend.services.formal_pit_partition_adapter import FormalPITPartitionAdapter
from backend.services.v3_b5_observation import (
    IS_END,
    IS_START,
    OOS_START,
    event_equivalence_projection,
    publish_instrumented_is_artifact,
    verify_instrumented_is_artifact,
)
from scripts.publish_v3_execution_semantics import _protocol_binding
from scripts.run_v3_b4_is_once import (
    MEMBERSHIP_ID,
    OOS_START as B4_OOS_START,
    PROTOCOL_ID,
    ROOT,
    REVISION_ID,
    _ReadBoundDataSource,
    _canonical,
    _load_manifest,
    _load_protocol,
    _load_universe,
    _read,
    _sidecar_hash,
    _validate_canary,
)
from scripts.verify_v3_execution_semantics import verify_v3_execution_semantics
from strategy_core.backtest_engine import run_event_backtest
from strategy_core.v3_relative_strength_executor import V3RelativeStrengthExecutionSpec


SUPPLEMENT_ID = "69866b713808aa74"
SUPPLEMENT_MANIFEST_SHA256 = "e507be510ac72627275b66aa611057071775db7731cec5080f33f4e40f99dceb"
SUPPLEMENT_PREDECESSOR_ID = "680cd55c91254667"
SUPPLEMENT_PREDECESSOR_MANIFEST_SHA256 = "c7bff428da948b54389c6c7415072de6ca5df4ebe777d251d1a06d08e6e8fb39"
FORMAL_SNAPSHOT_ID = "v3ds_d73256081de82e8a"
SCOPE_ID = "acbc49159d989a46"
SCOPE_MANIFEST_SHA256 = "cef48909b7b7bb05bc952a19ff8e50702540b427c58fd21eb1670afcaf675c67"
SOURCE_INVENTORY_ID = "2fe8321a5f644b9b"
SOURCE_INVENTORY_MANIFEST_SHA256 = "e23b94ac7294003a9b28db28f270bf2f19eaff40da9a03507adda87aad219a2c"
B4_PREDECESSOR_ID = "20960e9fd15cdb44"
B4_PREDECESSOR_MANIFEST_SHA256 = "7b76000efaa9d709095ccb5a0c424e71432b933404ca68d35e08383a1cd04d30"
B4_PREDECESSOR_EVENT_SHA256 = "dec8460a98c6ebea243f069643f662fa80fa58db64ae10b7a87d9e38345a801c"
FORMAL_SNAPSHOT_HASH = "d73256081de82e8a764ea2394d613af820fd1b82e773c48156ca2463a452c80e"
DEFAULT_OUTPUT_ROOT = ROOT / "data/pit/v3_b5_instrumented_is_results"
MEMBERSHIP_DIR = ROOT / "data/pit/pit_membership_snapshots" / MEMBERSHIP_ID
SUPPLEMENT_DIR = ROOT / "data/pit/v3_execution_semantics_supplements" / SUPPLEMENT_ID
REQUIRED_PRODUCER_SOURCE_PATHS = (
    "scripts/run_v3_b4_is_once.py",
    "backend/services/v3_b5_observation.py",
)


def _source_hashes(repo_root: Path) -> dict[str, str]:
    from backend.services.v3_b5_observation import _sha

    paths = (
        "backend/services/v3_b5_observation.py",
        "scripts/run_v3_b5_instrumented_is_once.py",
        "scripts/run_v3_b4_is_once.py",
        "scripts/verify_v3_execution_semantics.py",
        "strategy_core/v3_relative_strength_executor.py",
        "strategy_core/backtest_engine.py",
    )
    return {relative: _sha(Path(repo_root) / relative) for relative in paths}


def _validate_required_producer_source_hashes(
    manifest: dict[str, object], *, repo_root: Path = ROOT
) -> None:
    from backend.services.v3_b5_observation import _sha

    declared = manifest.get("producer_source_hashes")
    if not isinstance(declared, dict):
        raise ValueError("producer source hashes missing")
    for relative in REQUIRED_PRODUCER_SOURCE_PATHS:
        expected = declared.get(relative)
        if not isinstance(expected, str) or not expected:
            raise ValueError(f"required producer source hash missing: {relative}")
        actual = _sha(Path(repo_root) / relative)
        if expected != actual:
            raise ValueError(f"producer source hash mismatch: {relative}")


def verify_v3_b5_instrumented_artifact(
    artifact_dir: Path, *, repo_root: Path = ROOT
) -> dict[str, object]:
    manifest = _read(Path(artifact_dir) / "manifest.json")
    _validate_required_producer_source_hashes(manifest, repo_root=repo_root)
    return verify_instrumented_is_artifact(artifact_dir, repo_root=repo_root)


def _load_b4_predecessor(repo_root: Path) -> tuple[dict, dict, str, str]:
    directory = Path(repo_root) / "data/pit/v3_b4_is_results" / B4_PREDECESSOR_ID
    manifest_path = directory / "manifest.json"
    event_path = directory / "event_result.json"
    manifest_sha = _sidecar_hash(manifest_path)
    event_sha = _sidecar_hash(event_path)
    if manifest_sha != B4_PREDECESSOR_MANIFEST_SHA256 or event_sha != B4_PREDECESSOR_EVENT_SHA256:
        raise ValueError("B4 predecessor hash mismatch")
    manifest = _read(manifest_path)
    event = _read(event_path)
    if manifest.get("supplement", {}).get("supplement_id") != SUPPLEMENT_PREDECESSOR_ID:
        raise ValueError("B4 predecessor must remain bound to 680c")
    if manifest.get("is_range") != {"start": IS_START.isoformat(), "end": IS_END.isoformat()}:
        raise ValueError("B4 predecessor IS range mismatch")
    return manifest, event, manifest_sha, event_sha


def _build_lineage(
    *,
    repo_root: Path,
    protocol,
    formal_manifest,
    formal_manifest_sha: str,
    supplement_manifest: dict,
    supplement_manifest_sha: str,
    read_audit: dict,
) -> dict[str, object]:
    scope_path = Path(repo_root) / "data/pit/historical_scope_freezes" / SCOPE_ID / "manifest.json"
    inventory_path = Path(repo_root) / "data/pit/v3_b5_source_inventories" / SOURCE_INVENTORY_ID / "manifest.json"
    membership_manifest_path = Path(repo_root) / "data/pit/pit_membership_snapshots" / MEMBERSHIP_ID / "manifest.json"
    membership_records_path = membership_manifest_path.parent / "records.parquet"
    predecessor_manifest, predecessor_event, predecessor_manifest_sha, predecessor_event_sha = _load_b4_predecessor(repo_root)
    protocol_binding = _protocol_binding(repo_root)
    if _sidecar_hash(scope_path) != SCOPE_MANIFEST_SHA256:
        raise ValueError("historical scope binding mismatch")
    if _sidecar_hash(inventory_path) != SOURCE_INVENTORY_MANIFEST_SHA256:
        raise ValueError("B5 source inventory binding mismatch")
    membership_manifest_sha = _sidecar_hash(membership_manifest_path)
    membership_records_sha = _sidecar_hash(membership_records_path)
    if supplement_manifest.get("supplement_id") != SUPPLEMENT_ID or supplement_manifest_sha != SUPPLEMENT_MANIFEST_SHA256:
        raise ValueError("v3 observation supplement binding mismatch")
    return {
        "trading_result_predecessor": {
            "artifact_id": B4_PREDECESSOR_ID,
            "manifest_path": "data/pit/v3_b4_is_results/20960e9fd15cdb44/manifest.json",
            "manifest_sha256": predecessor_manifest_sha,
            "event_result_path": "data/pit/v3_b4_is_results/20960e9fd15cdb44/event_result.json",
            "event_result_sha256": predecessor_event_sha,
            "execution_supplement_id": SUPPLEMENT_PREDECESSOR_ID,
            "execution_supplement_manifest_sha256": SUPPLEMENT_PREDECESSOR_MANIFEST_SHA256,
        },
        "observation_seam": {
            "supplement_id": SUPPLEMENT_ID,
            "manifest_sha256": supplement_manifest_sha,
            "predecessor_supplement_id": SUPPLEMENT_PREDECESSOR_ID,
            "predecessor_manifest_sha256": SUPPLEMENT_PREDECESSOR_MANIFEST_SHA256,
        },
        "protocol": protocol_binding,
        "formal_snapshot": {
            "snapshot_id": FORMAL_SNAPSHOT_ID,
            "semantic_hash": formal_manifest.semantic_hash,
            "manifest_sha256": formal_manifest_sha,
        },
        "membership": {
            "snapshot_id": MEMBERSHIP_ID,
            "manifest_path": "data/pit/pit_membership_snapshots/pims_traderlens_v2_shsz_sw2021_pit_005/manifest.json",
            "manifest_sha256": membership_manifest_sha,
            "records_path": "data/pit/pit_membership_snapshots/pims_traderlens_v2_shsz_sw2021_pit_005/records.parquet",
            "records_sha256": membership_records_sha,
        },
        "calendar": dict(supplement_manifest["common_calendar"]),
        "scope": {
            "artifact_id": SCOPE_ID,
            "manifest_path": "data/pit/historical_scope_freezes/acbc49159d989a46/manifest.json",
            "manifest_sha256": SCOPE_MANIFEST_SHA256,
        },
        "source_inventory": {
            "artifact_id": SOURCE_INVENTORY_ID,
            "manifest_path": "data/pit/v3_b5_source_inventories/2fe8321a5f644b9b/manifest.json",
            "manifest_sha256": SOURCE_INVENTORY_MANIFEST_SHA256,
        },
        "is_range": {"start": IS_START.isoformat(), "end": IS_END.isoformat()},
        "oos_start": OOS_START.isoformat(),
    }


def _observation_rows(snapshots: list[object]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for snapshot in snapshots:
        values = {
            symbol: float(quantity) * float(last_price)
            for symbol, quantity, last_price in snapshot.positions
        }
        positions_value = sum(values.values())
        previous = rows[-1]["portfolio_value"] if rows else None
        daily_return = 0.0 if previous is None else float(snapshot.portfolio_value) / float(previous) - 1.0
        rows.append(
            {
                "date": snapshot.date.isoformat(),
                "cash": float(snapshot.cash),
                "portfolio_value": float(snapshot.portfolio_value),
                "gross_exposure": positions_value,
                "net_exposure": positions_value,
                "positions_value": positions_value,
                "daily_return": daily_return,
                "position_values_by_symbol": dict(sorted(values.items())),
            }
        )
    return rows


def run_v3_b5_instrumented_is_once(
    *,
    repo_root: Path = ROOT,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
) -> dict[str, object]:
    repo_root = Path(repo_root).resolve()
    supplement_dir = repo_root / "data/pit/v3_execution_semantics_supplements" / SUPPLEMENT_ID
    supplement = verify_v3_execution_semantics(supplement_dir)
    if supplement.get("status") != "verified" or supplement.get("supplement_id") != SUPPLEMENT_ID or supplement.get("manifest_sha256") != SUPPLEMENT_MANIFEST_SHA256:
        raise ValueError("v3 observation supplement is not independently verified")
    supplement_manifest = _read(supplement_dir / "manifest.json")
    protocol = _load_protocol(repo_root)
    formal_manifest, formal_manifest_sha, _ = _load_manifest(repo_root)
    universe = _load_universe(repo_root)
    if formal_manifest.semantic_hash != FORMAL_SNAPSHOT_HASH or protocol.protocol_snapshot_id != PROTOCOL_ID or protocol.strategy_revision_id != REVISION_ID:
        raise ValueError("v3 instrumented identity mismatch")
    qualification = BacktestEngineQualification().run_qualification_with_b3_protocol(
        protocol=protocol, manifest=formal_manifest, universe_spec=universe, qualification_date=IS_END,
    )
    canary = _validate_canary(qualification)
    raw_source = FormalPITPartitionAdapter(repo_root)
    expected_dates = tuple(raw_source.common_trading_dates(IS_START, IS_END))
    if not expected_dates:
        raise ValueError("v3 IS has no common trading dates")
    audited_source = _ReadBoundDataSource(
        raw_source, IS_END, enable_batch_endpoints=False
    )
    snapshots: list[object] = []
    spec = V3RelativeStrengthExecutionSpec(
        strategy_revision_id=REVISION_ID,
        protocol_snapshot_id=PROTOCOL_ID,
        data_snapshot_hash=formal_manifest.semantic_hash,
        supplement_id=SUPPLEMENT_ID,
        backtest_start=IS_START,
        backtest_end=IS_END,
    )
    result = run_event_backtest(
        spec,
        audited_source,
        None,
        PROTOCOL_ID,
        formal_manifest.semantic_hash,
        initial_capital=spec.initial_capital,
        supplement_path=supplement_dir,
        observation_sink=snapshots.append,
    )
    event_json = result.model_dump(mode="json")
    predecessor_manifest, predecessor_event, predecessor_manifest_sha, predecessor_event_sha = _load_b4_predecessor(repo_root)
    if event_equivalence_projection(event_json) != event_equivalence_projection(predecessor_event):
        raise ValueError("v3 instrumented trading result differs from 20960")
    if result.backtest_start != IS_START or result.backtest_end != IS_END or result.future_violations:
        raise ValueError("v3 instrumented result IS/future binding mismatch")
    rows = _observation_rows(snapshots)
    read_audit = audited_source.audit()
    if read_audit["oos_read_count"] != 0 or (read_audit["max_requested_date"] and read_audit["max_requested_date"] >= OOS_START.isoformat()):
        raise ValueError("v3 instrumented run read OOS")
    producer_source_hashes = _source_hashes(repo_root)
    _validate_required_producer_source_hashes(
        {"producer_source_hashes": producer_source_hashes}, repo_root=repo_root
    )
    lineage = _build_lineage(
        repo_root=repo_root,
        protocol=protocol,
        formal_manifest=formal_manifest,
        formal_manifest_sha=formal_manifest_sha,
        supplement_manifest=supplement_manifest,
        supplement_manifest_sha=SUPPLEMENT_MANIFEST_SHA256,
        read_audit=read_audit,
    )
    payload = {
        "identity": {
            "template_id": "relative_strength_rotation_shsz_sw2021_v3",
            "template_version": "v3_shsz_sw2021_pit_12m_liquidity20d",
            "template_hash": "f7c0fd8123f62f37118cb947e1735861374435f8707e01b06d788a8ec4df39c1",
            "requirements_hash": "ef2ab5b1dafe4349f305b52733a7dcb018a2961464dfbc6542a10e34805d041d",
            "strategy_revision_id": REVISION_ID,
            "protocol_snapshot_id": PROTOCOL_ID,
            "formal_snapshot_id": FORMAL_SNAPSHOT_ID,
        },
        "lineage": lineage,
        "canary": canary,
        "read_audit": read_audit,
        "equivalence": {
            "predecessor_artifact_id": B4_PREDECESSOR_ID,
            "fields": list(event_equivalence_projection(predecessor_event)),
            "excluded_fields": ["frozen_at"],
            "excluded_field_reason": "run freeze date is metadata; all trading fields are compared exactly",
        },
        "producer_source_hashes": producer_source_hashes,
    }
    published = publish_instrumented_is_artifact(
        output_root=Path(output_root),
        manifest_payload=payload,
        event_result=event_json,
        observations=rows,
        expected_dates=expected_dates,
    )
    return {
        **published,
        "is_range": {"start": IS_START.isoformat(), "end": IS_END.isoformat()},
        "observation_count": len(rows),
        "canary": canary,
        "fills": len(result.fills),
        "order_intents": len(result.order_intents),
        "rejections": len(result.rejected_orders),
        "future_violations": len(result.future_violations),
        "read_audit": read_audit,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", type=Path)
    args = parser.parse_args()
    if args.verify is not None:
        output = verify_v3_b5_instrumented_artifact(args.verify)
    else:
        output = run_v3_b5_instrumented_is_once()
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
