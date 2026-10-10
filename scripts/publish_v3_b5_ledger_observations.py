"""Publish v3 B5 daily observations by replaying the verified B4 fill ledger."""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
import os
import sqlite3
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

from backend.services.b3_protocol_types import DataSnapshotManifest
from backend.services.b4_protocol_types import EventBacktestResult
from backend.services.formal_pit_partition_adapter import FormalPITPartitionAdapter
from backend.services.v3_b5_ledger_observation import (
    OBSERVATION_SCHEMA,
    authoritative_final_match,
    canonical_bytes,
    replay_ledger,
    sha256_bytes,
    sha256_file,
    validate_observation_rows,
)
from contracts.strategy import ResearchProtocolSnapshot
from scripts.run_v3_b4_is_once import (
    DEFAULT_OUTPUT_ROOT as B4_ROOT,
    FORMAL_SNAPSHOT_HASH,
    FORMAL_SNAPSHOT_ID,
    IS_END,
    IS_START,
    MEMBERSHIP_ID,
    OOS_START,
    PROTOCOL_ID,
    REVISION_ID,
    _ReadBoundDataSource,
    _read,
    _sidecar_hash,
    verify_v3_b4_is_result,
)
from strategy_core.v3_relative_strength_executor import V3RelativeStrengthExecutionSpec


ROOT = Path(__file__).resolve().parents[1]
B4_ID = "958bb9717edd08a9"
B4_MANIFEST_SHA = "af9ebfbcda0eff795efc4ef26688f57286886206e1e6dfe1699a90a197f8b7c2"
B4_EVENT_SHA = "374479e9df35c80c680adfe34fe95d10a78eb4d049a24fc6bc43cfb3aa0bf1cc"
SUPPLEMENT_ID = "d1134e96d6b2ec1b"
SUPPLEMENT_MANIFEST_SHA = "18e7fd2fb48c089019c9343512641de7ef4f90fd50415c868919ddcabd24c16b"
SCOPE_ID = "acbc49159d989a46"
SCOPE_MANIFEST_SHA = "cef48909b7b7bb05bc952a19ff8e50702540b427c58fd21eb1670afcaf675c67"
INVENTORY_ID = "2fe8321a5f644b9b"
INVENTORY_MANIFEST_SHA = "e23b94ac7294003a9b28db28f270bf2f19eaff40da9a03507adda87aad219a2c"
MEMBERSHIP_MANIFEST_SHA = "32f58adbca49fb89dfeb54ceeb4ac9b27b6a26c55e0c9cfeae7a8fcaf3683f10"
MEMBERSHIP_RECORDS_SHA = "2e8c922de9f198ab18a6b38743a01f4343fbf52b876da84026389d3ffd11eec0"
CALENDAR_ID = "shsz_common_trade_calendar_v1"
CALENDAR_MANIFEST_SHA = "ae019cf45072d8274f915837a03d1824c02a69159df473512dbce2e925586785"
CALENDAR_PARQUET_SHA = "8b41168bcd1c39d52ed00f9717ba6fa5330e5b4e15de78068446abe8647f2364"
CALENDAR_DATE_SET_SHA = "62b6880c9acc381d273ceee40c900a486c3f83488600c042c43ce1d8f9cbb194"
OUTPUT_ROOT = ROOT / "data/pit/v3_b5_ledger_observations"
FEASIBILITY_PATH = ROOT / "docs/verification/v3_b5_ledger_observation_feasibility.json"
FEASIBILITY_SHA = "58515488e0c79e266137e679dce11aa1eb3248d809687e0c89aea3826a050777"


def _repo_path(path: Path, repo_root: Path = ROOT) -> str:
    return path.resolve().relative_to(Path(repo_root).resolve()).as_posix()


def _source(path: Path, expected: str | None = None, repo_root: Path = ROOT) -> dict[str, str]:
    actual = sha256_file(path)
    if expected is not None and actual != expected:
        raise ValueError(f"source hash mismatch: {path}")
    return {"path": _repo_path(path, repo_root), "sha256": actual}


def _load_protocol(repo_root: Path = ROOT) -> tuple[ResearchProtocolSnapshot, str]:
    repo_root = Path(repo_root).resolve()
    db_path = repo_root / "data/strategy.db"
    db_uri = f"{db_path.as_uri()}?mode=ro"
    with closing(sqlite3.connect(db_uri, uri=True)) as conn:
        row = conn.execute(
            "SELECT payload_json FROM research_protocol_snapshots WHERE protocol_snapshot_id = ?",
            (PROTOCOL_ID,),
        ).fetchone()
    if row is None:
        raise ValueError("v3 protocol snapshot missing")
    protocol = ResearchProtocolSnapshot.model_validate_json(row[0])
    if protocol.protocol_snapshot_id != PROTOCOL_ID or protocol.strategy_revision_id != REVISION_ID or protocol.protocol_profile != "b6_coverage_bound":
        raise ValueError("v3 protocol exact binding mismatch")
    return protocol, sha256_bytes(row[0].encode("utf-8"))


def _load_b4(repo_root: Path = ROOT) -> tuple[dict[str, Any], EventBacktestResult, str, str]:
    repo_root = Path(repo_root).resolve()
    directory = repo_root / "data/pit/v3_b4_is_results" / B4_ID
    verified = verify_v3_b4_is_result(directory, repo_root=repo_root)
    if verified.get("status") != "verified":
        raise ValueError(f"B4 predecessor is not verified: {verified}")
    manifest_path = directory / "manifest.json"
    event_path = directory / "event_result.json"
    manifest_sha = _sidecar_hash(manifest_path)
    event_sha = _sidecar_hash(event_path)
    if manifest_sha != B4_MANIFEST_SHA or event_sha != B4_EVENT_SHA:
        raise ValueError("B4 predecessor hash mismatch")
    manifest = _read(manifest_path)
    event_json = _read(event_path)
    event = EventBacktestResult.model_validate(event_json)
    if manifest.get("supplement", {}).get("supplement_id") != SUPPLEMENT_ID:
        raise ValueError("B4 predecessor does not bind current trading supplement")
    if event.backtest_start != IS_START or event.backtest_end != IS_END or event.future_violations:
        raise ValueError("B4 predecessor IS/event binding mismatch")
    return manifest, event, manifest_sha, event_sha


def _load_formal_manifest(repo_root: Path = ROOT) -> tuple[DataSnapshotManifest, dict[str, Any], str]:
    repo_root = Path(repo_root).resolve()
    path = repo_root / "data/pit/v3_formal_data_snapshot_manifests" / FORMAL_SNAPSHOT_ID / "manifest.json"
    manifest_sha = _sidecar_hash(path)
    payload = _read(path)
    manifest = DataSnapshotManifest.model_validate(payload)
    if manifest.semantic_hash != FORMAL_SNAPSHOT_HASH or payload.get("not_authorized_for_b6_oos_gate_promotion_signal") is not False:
        raise ValueError("formal snapshot authorization/hash mismatch")
    return manifest, payload, manifest_sha


def _load_immutable_trading_supplement(repo_root: Path = ROOT) -> dict[str, Any]:
    """Validate the immutable current trading supplement without rebinding it."""
    repo_root = Path(repo_root).resolve()
    path = repo_root / "data/pit/v3_execution_semantics_supplements" / SUPPLEMENT_ID / "manifest.json"
    manifest_sha = _sidecar_hash(path)
    if manifest_sha != SUPPLEMENT_MANIFEST_SHA:
        raise ValueError("current predecessor manifest hash mismatch")
    manifest = _read(path)
    if manifest.get("schema_version") != "v3_execution_semantics_supplement.v2" or manifest.get("supplement_id") != SUPPLEMENT_ID:
        raise ValueError("current predecessor identity mismatch")
    if manifest.get("status") != "published" or manifest.get("authorization_scope") != "v3_manual_trading_execution":
        raise ValueError("current predecessor status/authorization mismatch")
    if manifest.get("not_authorized_for_b6_oos_gate_promotion_signal") is not False:
        raise ValueError("current predecessor disclosure mismatch")
    payload = {key: value for key, value in manifest.items() if key != "supplement_id"}
    if sha256_bytes(canonical_bytes(payload))[:16] != SUPPLEMENT_ID:
        raise ValueError("current predecessor deterministic identity mismatch")
    template = manifest.get("template", {})
    if template.get("template_id") != "relative_strength_rotation_shsz_sw2021_v3" or template.get("template_version") != "v3_shsz_sw2021_pit_12m_liquidity20d":
        raise ValueError("current predecessor template mismatch")
    protocol = manifest.get("protocol", {})
    if protocol.get("protocol_snapshot_id") != PROTOCOL_ID or protocol.get("strategy_revision_id") != REVISION_ID:
        raise ValueError("current predecessor protocol/revision mismatch")
    return {
        "supplement_id": SUPPLEMENT_ID,
        "manifest_sha256": manifest_sha,
        "status": "immutable_predecessor_manifest_verified",
        "declared_source_bindings": manifest.get("source_bindings", {}),
        "manifest": manifest,
    }


def _load_lineage(protocol: ResearchProtocolSnapshot, protocol_payload_sha: str, b4_manifest: dict[str, Any], b4_manifest_sha: str, b4_event_sha: str, supplement: dict[str, Any], formal_payload: dict[str, Any], formal_manifest_sha: str, *, repo_root: Path = ROOT) -> dict[str, Any]:
    repo_root = Path(repo_root).resolve()
    scope_path = repo_root / "data/pit/historical_scope_freezes" / SCOPE_ID / "manifest.json"
    inventory_path = repo_root / "data/pit/v3_b5_source_inventories" / INVENTORY_ID / "manifest.json"
    membership_dir = repo_root / "data/pit/pit_membership_snapshots" / MEMBERSHIP_ID
    calendar_dir = repo_root / "data/pit/shsz_common_trade_calendars" / CALENDAR_ID
    scope_sha = _sidecar_hash(scope_path)
    inventory_sha = _sidecar_hash(inventory_path)
    membership_manifest_sha = _sidecar_hash(membership_dir / "manifest.json")
    membership_records_sha = _sidecar_hash(membership_dir / "records.parquet")
    calendar_manifest_sha = _sidecar_hash(calendar_dir / "manifest.json")
    calendar_parquet_sha = _sidecar_hash(calendar_dir / "szse_trade_cal.parquet")
    if scope_sha != SCOPE_MANIFEST_SHA or inventory_sha != INVENTORY_MANIFEST_SHA:
        raise ValueError("scope/source inventory binding mismatch")
    if membership_manifest_sha != MEMBERSHIP_MANIFEST_SHA or membership_records_sha != MEMBERSHIP_RECORDS_SHA:
        raise ValueError("membership binding mismatch")
    if calendar_manifest_sha != CALENDAR_MANIFEST_SHA or calendar_parquet_sha != CALENDAR_PARQUET_SHA:
        raise ValueError("calendar binding mismatch")
    return {
        "b4": {"artifact_id": B4_ID, "manifest_sha256": b4_manifest_sha, "event_sha256": b4_event_sha},
        "trading_supplement": {"supplement_id": SUPPLEMENT_ID, "manifest_sha256": SUPPLEMENT_MANIFEST_SHA},
        "protocol": {"snapshot_id": protocol.protocol_snapshot_id, "strategy_revision_id": protocol.strategy_revision_id, "payload_sha256": protocol_payload_sha},
        "formal_snapshot": {"snapshot_id": FORMAL_SNAPSHOT_ID, "semantic_hash": FORMAL_SNAPSHOT_HASH, "manifest_sha256": formal_manifest_sha},
        "scope": {"artifact_id": SCOPE_ID, "manifest_sha256": scope_sha, "path": _repo_path(scope_path, repo_root)},
        "source_inventory": {"artifact_id": INVENTORY_ID, "manifest_sha256": inventory_sha, "path": _repo_path(inventory_path, repo_root)},
        "membership": {"snapshot_id": MEMBERSHIP_ID, "manifest_sha256": membership_manifest_sha, "records_sha256": membership_records_sha, "path": _repo_path(membership_dir, repo_root)},
        "calendar": {"artifact_id": CALENDAR_ID, "manifest_sha256": calendar_manifest_sha, "parquet_sha256": calendar_parquet_sha, "date_set_sha256": CALENDAR_DATE_SET_SHA, "path": _repo_path(calendar_dir, repo_root)},
        "feasibility_design_evidence": {"path": _repo_path(repo_root / "docs/verification/v3_b5_ledger_observation_feasibility.json", repo_root), "sha256": FEASIBILITY_SHA},
        "b4_manifest_declared": {"data_snapshot_hash": b4_manifest.get("data_snapshot_hash"), "strategy_revision_id": b4_manifest.get("strategy_revision_id")},
        "formal_payload_semantic_hash": formal_payload.get("semantic_hash"),
        "supplement_status": supplement.get("status"),
        "supplement_declared_source_bindings": supplement.get("declared_source_bindings", {}),
    }


def _producer_source_bindings(repo_root: Path = ROOT) -> dict[str, dict[str, str]]:
    repo_root = Path(repo_root).resolve()
    paths = {
        "ledger_observation": repo_root / "backend/services/v3_b5_ledger_observation.py",
        "publisher": repo_root / "scripts/publish_v3_b5_ledger_observations.py",
        "b4_runner_read_bound": repo_root / "scripts/run_v3_b4_is_once.py",
        "formal_pit_adapter": repo_root / "backend/services/formal_pit_partition_adapter.py",
        "portfolio": repo_root / "strategy_core/portfolio.py",
        "transaction_costs": repo_root / "strategy_core/transaction_costs.py",
        "fill_simulator": repo_root / "strategy_core/fill_simulator.py",
    }
    return {name: _source(path, repo_root=repo_root) for name, path in paths.items()}


def _write_json(path: Path, value: Any) -> None:
    raw = canonical_bytes(value)
    temp = path.with_name(path.name + ".tmp")
    temp.write_bytes(raw)
    with temp.open("ab") as handle:
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)


def _write_sidecar(path: Path) -> None:
    sidecar = path.with_name(path.name + ".sha256")
    _write_json_text(sidecar, f"{sha256_file(path)}  {path.name}\n")


def _write_json_text(path: Path, text: str) -> None:
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(text, encoding="utf-8")
    with temp.open("ab") as handle:
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)


def _write_once(target: Path, manifest: dict[str, Any], observations: list[dict[str, Any]]) -> dict[str, Any]:
    manifest_raw = canonical_bytes(manifest)
    observations_raw = canonical_bytes(observations)
    paths = {"manifest.json": manifest_raw, "observations.json": observations_raw}
    if target.exists():
        for name, raw in paths.items():
            path = target / name
            sidecar = target / f"{name}.sha256"
            if not path.exists() or path.read_bytes() != raw or not sidecar.exists() or sidecar.read_text(encoding="utf-8").split()[0] != sha256_bytes(raw):
                raise ValueError("v3 B5 ledger observation write-once conflict")
        return {"status": "already_published", "artifact_id": manifest["artifact_id"], "path": str(target), "manifest_sha256": sha256_file(target / "manifest.json")}
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".artifact.staging-", dir=str(target.parent)))
    for name, raw in paths.items():
        path = staging / name
        temp = path.with_name(path.name + ".tmp")
        temp.write_bytes(raw)
        with temp.open("ab") as handle:
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
        _write_sidecar(path)
    os.replace(staging, target)
    return {"status": "published", "artifact_id": manifest["artifact_id"], "path": str(target), "manifest_sha256": sha256_file(target / "manifest.json")}


def build_and_publish(*, repo_root: Path = ROOT, output_root: Path = OUTPUT_ROOT) -> dict[str, Any]:
    repo_root = Path(repo_root).resolve()
    if repo_root != ROOT.resolve():
        raise ValueError("v3 B5 ledger publisher is bound to the repository root")
    protocol, protocol_payload_sha = _load_protocol(repo_root)
    b4_manifest, event, b4_manifest_sha, b4_event_sha = _load_b4(repo_root)
    formal_manifest, formal_payload, formal_manifest_sha = _load_formal_manifest(repo_root)
    supplement = _load_immutable_trading_supplement(repo_root)
    if protocol.data_snapshot_hash != formal_manifest.semantic_hash or protocol.data_snapshot_id != FORMAL_SNAPSHOT_ID:
        raise ValueError("protocol/formal snapshot mismatch")
    if protocol.strategy_revision_id != REVISION_ID:
        raise ValueError("protocol/revision mismatch")
    raw_source = FormalPITPartitionAdapter(repo_root)
    dates = raw_source.common_trading_dates(IS_START, IS_END)
    if dates[0] != IS_START or dates[-1] != IS_END or len(dates) != 176:
        raise ValueError("v3 IS common calendar mismatch")
    audited_source = _ReadBoundDataSource(raw_source, IS_END, enable_batch_endpoints=False)
    spec = V3RelativeStrengthExecutionSpec(
        strategy_revision_id=REVISION_ID,
        protocol_snapshot_id=PROTOCOL_ID,
        data_snapshot_hash=formal_manifest.semantic_hash,
        supplement_id=SUPPLEMENT_ID,
        backtest_start=IS_START,
        backtest_end=IS_END,
    )
    replay = replay_ledger(event, audited_source, dates, initial_capital=spec.initial_capital)
    validate_observation_rows(list(replay.observations), dates)
    final_match = authoritative_final_match(replay.portfolio, event.final_portfolio)
    if not final_match.get("all_equal"):
        raise ValueError(f"authoritative final portfolio mismatch: {final_match}")
    audit = audited_source.audit()
    if audit["oos_read_count"] != 0 or audit["max_requested_date"] is None or audit["max_requested_date"] >= OOS_START.isoformat():
        raise ValueError("ledger observation replay read OOS")
    cost_summary = {
        "fill_count": len(replay.cost_ledger),
        "gross_traded_notional": sum(item["gross_amount"] for item in replay.cost_ledger),
        "commission": sum(item["commission"] for item in replay.cost_ledger),
        "stamp_duty": sum(item["stamp_duty"] for item in replay.cost_ledger),
        "transfer_fee": sum(item["transfer_fee"] for item in replay.cost_ledger),
        "total_fee": sum(item["total_fee"] for item in replay.cost_ledger),
    }
    lineage = _load_lineage(protocol, protocol_payload_sha, b4_manifest, b4_manifest_sha, b4_event_sha, supplement, formal_payload, formal_manifest_sha, repo_root=repo_root)
    manifest_without_id: dict[str, Any] = {
        "schema_version": "v3_b5_ledger_observations.v1",
        "status": "valid",
        "not_authorized_for_b6_oos_gate_promotion_signal": True,
        "lineage": lineage,
        "is_range": {"start": IS_START.isoformat(), "end": IS_END.isoformat(), "count": len(dates), "oos_start": OOS_START.isoformat()},
        "initial_capital": spec.initial_capital,
        "fills": {"count": len(event.fills), "consumed_once": list(replay.consumed_fill_ids) == [fill.fill_id for fill in event.fills]},
        "order_intents": {"count": len(event.order_intents), "rejections": len(event.rejected_orders)},
        "cost_summary": cost_summary,
        "authoritative_final_match": final_match,
        "derived_position_details": replay.derived_position_details,
        "operation_counts": replay.operation_counts,
        "observations": {"path": "observations.json", "count": len(replay.observations), "sha256": sha256_bytes(canonical_bytes(list(replay.observations)))},
        "event_predecessor": {"artifact_id": B4_ID, "manifest_sha256": b4_manifest_sha, "event_sha256": b4_event_sha},
        "read_audit": audit,
        "producer_source_hashes": _producer_source_bindings(repo_root),
    }
    artifact_id = sha256_bytes(canonical_bytes(manifest_without_id))[:16]
    manifest = {**manifest_without_id, "artifact_id": artifact_id}
    return _write_once(Path(output_root) / artifact_id, manifest, list(replay.observations)) | {
        "observation_count": len(replay.observations), "fill_count": len(event.fills), "read_audit": audit,
        "authoritative_final_match": final_match, "cost_summary": cost_summary,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, default=OUTPUT_ROOT)
    args = parser.parse_args()
    print(json.dumps(build_and_publish(output_root=args.output_root), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
