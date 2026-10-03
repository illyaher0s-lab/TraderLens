"""Publish the immutable, v3-only execution-semantics supplement."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

if __package__ in {None, ""}:
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

from scripts.verify_v3_gate_criteria import verify_criteria_pair
from scripts.verify_market_regime_v12_owner_approval import verify_owner_approval
from scripts.verify_shsz_common_trade_calendar import (
    EXPECTED_COMMON_FIRST,
    EXPECTED_COMMON_LAST,
    EXPECTED_COMMON_OPEN_COUNT,
    EXPECTED_COMMON_SHA256,
    FORMAL_REL as COMMON_CALENDAR_REL,
    verify_candidate,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = ROOT / "data/pit/v3_execution_semantics_supplements"
SCHEMA = "v3_execution_semantics_supplement.v2"
PREDECESSOR_ID = "1aed70f1af38a191"
PREDECESSOR_MANIFEST_SHA256 = "70e4dfa09f11cbafd5aebf76903ecb95ca6a491635d1d94b3d713db5481beac0"
PROTOCOL_ID = "8770c56c5a69ef128442c0f593f9e4b081a6b13c69744b27171b27cc8c8b7bbe"
PROTOCOL_PAYLOAD_SHA256 = "2872d63578d66e6dfc02fd767c4061fd3e291bcb9bbd65f0f2409a4482f6e2a3"
REVISION_ID = "6440ffc03a742f4d4632078481cf3abf171eafb1a24f2bc69bc6f352d1b19ebc"
V2_GATE_ID = "prototype_gate_v2_gate_v2_2bd8670c2e0fe084"
V2_GATE_MANIFEST_SHA256 = "9a534c58da7634defc1b30dd7ff1bfb91302365f08bb0ef413fa64253997d113"
V2_KILL_ID = "prototype_gate_v2_kill_v2_ea47b0c73ed2476e"
V2_KILL_MANIFEST_SHA256 = "604a435ca7a3295f134e870dc8cc3b05239f58831176dec4c9fce60b984d914e"
V2_ENVELOPE_HASH = "94da0dda30af75d663a7d28deb0a15d64a4e068586a1295f3b4f52203a8c4738"
STABLE_CRITERIA_SOURCE_REL = "backend/services/prototype_gate_criteria_surface.py"
TEMPLATE = {
    "template_id": "relative_strength_rotation_shsz_sw2021_v3",
    "template_version": "v3_shsz_sw2021_pit_12m_liquidity20d",
    "template_hash": "f7c0fd8123f62f37118cb947e1735861374435f8707e01b06d788a8ec4df39c1",
    "data_requirements_hash": "ef2ab5b1dafe4349f305b52733a7dcb018a2961464dfbc6542a10e34805d041d",
}
CRITERIA_ROOT = ROOT / "data/pit/prototype_gate_v2_criteria"
OWNER_APPROVAL_DIR = ROOT / "data/pit/market_regime_owner_approvals/6170c11c8068f407"


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha(path: Path) -> str:
    return _sha_bytes(Path(path).read_bytes())


def _read(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _sidecar_hash(path: Path) -> str:
    path = Path(path)
    sidecar = path.with_name(path.name + ".sha256")
    actual = _sha(path)
    if not sidecar.exists() or sidecar.read_text(encoding="utf-8").split()[0] != actual:
        raise ValueError(f"sidecar mismatch: {path}")
    return actual


def _repo_path(path: Path, repo_root: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def _artifact(path: Path, *, expected_id: str, id_field: str, repo_root: Path) -> dict:
    manifest_hash = _sidecar_hash(path)
    manifest = _read(path)
    if manifest.get(id_field) != expected_id:
        raise ValueError(f"artifact identity mismatch: {path}")
    return {
        "artifact_id": expected_id,
        "path": _repo_path(path, repo_root),
        "manifest_sha256": manifest_hash,
        "manifest": manifest,
    }


def _protocol_binding(repo_root: Path) -> dict:
    db_path = repo_root / "data/strategy.db"
    if not db_path.exists():
        raise FileNotFoundError(db_path)
    db_uri = f"file:{db_path.as_posix()}?mode=ro"
    with closing(sqlite3.connect(db_uri, uri=True)) as conn:
        row = conn.execute(
            "SELECT payload_json, strategy_revision_id, protocol_profile "
            "FROM research_protocol_snapshots WHERE protocol_snapshot_id = ?",
            (PROTOCOL_ID,),
        ).fetchone()
    if row is None or row[1] != REVISION_ID or row[2] != "b6_coverage_bound":
        raise ValueError("approved v3 protocol binding missing")
    payload_sha256 = _sha_bytes(row[0].encode("utf-8"))
    if payload_sha256 != PROTOCOL_PAYLOAD_SHA256:
        raise ValueError("approved v3 protocol payload binding mismatch")
    return {
        "protocol_snapshot_id": PROTOCOL_ID,
        "protocol_profile": row[2],
        "strategy_revision_id": row[1],
        "payload_sha256": payload_sha256,
        "database_path": _repo_path(db_path, repo_root),
    }


def _source_bindings(repo_root: Path) -> dict:
    paths = {
        "formal_pit_adapter": "backend/services/formal_pit_partition_adapter.py",
        "v3_executor": "strategy_core/v3_relative_strength_executor.py",
        "backtest_engine_dispatch": "strategy_core/backtest_engine.py",
        "fill_simulator": "strategy_core/fill_simulator.py",
        "order_primitives": "strategy_core/orders.py",
        "transaction_costs": "strategy_core/transaction_costs.py",
        "portfolio": "strategy_core/portfolio.py",
    }
    bindings = {}
    for name, relative in paths.items():
        path = repo_root / relative
        if not path.exists():
            raise FileNotFoundError(path)
        bindings[name] = {"path": relative, "sha256": _sha(path)}
    return bindings


def _common_calendar_binding(repo_root: Path) -> dict:
    verify_candidate(repo_root, COMMON_CALENDAR_REL, formal_mode=True)
    calendar_dir = repo_root / Path(*COMMON_CALENDAR_REL.split("/"))
    manifest_path = calendar_dir / "manifest.json"
    parquet_path = calendar_dir / "szse_trade_cal.parquet"
    parquet_sidecar_path = parquet_path.with_name(parquet_path.name + ".sha256")
    manifest = _read(manifest_path)
    manifest_sha = _sidecar_hash(manifest_path)
    parquet_sha = _sidecar_hash(parquet_path)
    if manifest.get("artifact_id") != "shsz_common_trade_calendar_v1":
        raise ValueError("common calendar artifact identity mismatch")
    comparison = manifest.get("comparison", {})
    if comparison.get("common_open_count") != EXPECTED_COMMON_OPEN_COUNT or comparison.get("common_first_date") != EXPECTED_COMMON_FIRST or comparison.get("common_last_date") != EXPECTED_COMMON_LAST or comparison.get("common_open_dates_sha256") != EXPECTED_COMMON_SHA256:
        raise ValueError("common calendar date-set binding mismatch")
    return {
        "artifact_id": "shsz_common_trade_calendar_v1",
        "artifact_path": COMMON_CALENDAR_REL,
        "manifest_path": f"{COMMON_CALENDAR_REL}/manifest.json",
        "manifest_sha256": manifest_sha,
        "parquet_path": f"{COMMON_CALENDAR_REL}/szse_trade_cal.parquet",
        "parquet_sha256": parquet_sha,
        "parquet_sidecar_sha256": _sha(parquet_sidecar_path),
        "date_set_sha256": EXPECTED_COMMON_SHA256,
        "common_open_count": EXPECTED_COMMON_OPEN_COUNT,
        "first_date": EXPECTED_COMMON_FIRST,
        "last_date": EXPECTED_COMMON_LAST,
    }


def _predecessor_binding(repo_root: Path) -> dict:
    manifest_path = repo_root / "data/pit/v3_execution_semantics_supplements" / PREDECESSOR_ID / "manifest.json"
    manifest_sha = _sidecar_hash(manifest_path)
    if manifest_sha != PREDECESSOR_MANIFEST_SHA256:
        raise ValueError("v3 execution semantics predecessor mismatch")
    manifest = _read(manifest_path)
    if manifest.get("supplement_id") != PREDECESSOR_ID:
        raise ValueError("v3 execution semantics predecessor identity mismatch")
    return {"supplement_id": PREDECESSOR_ID, "manifest_sha256": manifest_sha}


def _semantics() -> dict:
    return {
        "schedule": {
            "execution_day": "first_shsz_common_open_day_of_iso_week",
            "as_of_day": "immediately_previous_completed_shsz_common_open_day",
        },
        "confirmation": {"independent_pit_days": 3, "entry_rank_percentile_max": 15},
        "exit": {
            "rank_percentile_min": 40,
            "max_holding_common_sessions": 15,
            "entry_session_counts_as_one": True,
            "stop_loss_pct": 8,
            "stop_reference": "completed_day_raw_close_vs_actual_average_fill_cost",
        },
        "portfolio": {
            "initial_capital_cny": 100000,
            "max_positions": 5,
            "target_weight": 0.20,
            "board_lot": 100,
            "residual_cash": "retain",
            "tie_break": "momentum_desc_symbol_asc",
        },
        "orders": {
            "same_symbol_conflict": "exit_wins",
            "blocked_exit": "retry_each_common_open_day",
            "blocked_entry": "expire_after_scheduled_execution_day",
            "market_regime": "block_new_entries_only",
        },
        "fill": {
            "price": "execution_day_open",
            "commission_rate": 0.0003,
            "minimum_commission": 5,
            "sell_stamp_duty": 0.001,
            "transfer_fee": 0,
            "slippage": 0,
            "maximum_participation": 0.10,
        },
    }


def build_payload(repo_root: Path = ROOT, *, source_root: Path | None = None) -> dict:
    repo_root = Path(repo_root).resolve()
    source_root = repo_root if source_root is None else Path(source_root).resolve()
    scope = _artifact(
        repo_root / "data/pit/historical_scope_freezes/acbc49159d989a46/manifest.json",
        expected_id="acbc49159d989a46", id_field="artifact_id", repo_root=repo_root,
    )
    coverage = _artifact(
        repo_root / "data/pit/v3_historical_coverage_packages/1e79d26460c0c109/manifest.json",
        expected_id="1e79d26460c0c109", id_field="artifact_id", repo_root=repo_root,
    )
    snapshot = _artifact(
        repo_root / "data/pit/v3_formal_data_snapshot_manifests/v3ds_d73256081de82e8a/manifest.json",
        expected_id="v3ds_d73256081de82e8a", id_field="snapshot_id", repo_root=repo_root,
    )
    successor = _artifact(
        repo_root / "data/pit/v3_availability_bounded_qualification_successors/12f1b9aac73dfcd4/manifest.json",
        expected_id="12f1b9aac73dfcd4", id_field="successor_id", repo_root=repo_root,
    )
    b3 = _artifact(
        repo_root / "data/pit/b3_execution_input_packages/05f38a2884dc7e47/manifest.json",
        expected_id="05f38a2884dc7e47", id_field="artifact_id", repo_root=repo_root,
    )
    lifecycle = _artifact(
        repo_root / "data/pit/qualification_successors/49b09326f35936c6/manifest.json",
        expected_id="49b09326f35936c6", id_field="successor_id", repo_root=repo_root,
    )
    liquidity = _artifact(
        repo_root / "data/pit/liquidity_qualification_successors/7c05ece4d3f01086/manifest.json",
        expected_id="7c05ece4d3f01086", id_field="artifact_id", repo_root=repo_root,
    )
    membership_manifest_path = repo_root / "data/pit/pit_membership_snapshots/pims_traderlens_v2_shsz_sw2021_pit_005/manifest.json"
    membership = _artifact(
        membership_manifest_path,
        expected_id="pims_traderlens_v2_shsz_sw2021_pit_005", id_field="snapshot_id", repo_root=repo_root,
    )
    membership_records = membership_manifest_path.parent / "records.parquet"
    records_hash = _sidecar_hash(membership_records)
    if membership["manifest"].get("records_parquet_sha256") != records_hash:
        raise ValueError("membership records binding mismatch")

    coverage_manifest = coverage["manifest"]
    snapshot_manifest = snapshot["manifest"]
    successor_manifest = successor["manifest"]
    if scope["manifest"].get("template") != TEMPLATE or coverage_manifest.get("template") != TEMPLATE:
        raise ValueError("v3 template binding mismatch")
    if coverage_manifest.get("coverage", {}).get("data_fault_count") != 0:
        raise ValueError("v3 coverage contains data faults")
    if snapshot_manifest.get("authorization_scope") != "b6_coverage_bound" or snapshot_manifest.get("availability_status") != "availability_bounded":
        raise ValueError("v3 formal snapshot authorization mismatch")
    if successor_manifest.get("authorization_scope") != "b6_coverage_bound" or successor_manifest.get("status") != "availability_bounded_qualified":
        raise ValueError("v3 availability successor authorization mismatch")
    if b3["manifest"].get("template") != TEMPLATE:
        raise ValueError("v3 B3 template binding mismatch")
    if b3["manifest"].get("authorization_scope") != "b3_execution_input_binding_only":
        raise ValueError("unexpected B3 authorization scope")

    criteria_root = repo_root / "data/pit/prototype_gate_v2_criteria"
    criteria = verify_criteria_pair(
        criteria_root,
        source_path=source_root / STABLE_CRITERIA_SOURCE_REL,
    )
    if criteria.get("status") != "valid" or criteria.get("envelope_hash") != V2_ENVELOPE_HASH:
        raise ValueError("v3 criteria envelope invalid")
    gate = criteria.get("gate", {})
    kill = criteria.get("kill", {})
    if (
        gate.get("snapshot_id") != V2_GATE_ID
        or gate.get("manifest_sha256") != V2_GATE_MANIFEST_SHA256
        or kill.get("snapshot_id") != V2_KILL_ID
        or kill.get("manifest_sha256") != V2_KILL_MANIFEST_SHA256
    ):
        raise ValueError("v3 criteria v2 identity mismatch")
    owner = verify_owner_approval(OWNER_APPROVAL_DIR)
    if owner.get("status") != "verified" or owner.get("artifact_id") != "6170c11c8068f407":
        raise ValueError("market-regime owner approval invalid")
    owner_manifest = _read(OWNER_APPROVAL_DIR / "manifest.json")

    chain = {
        "scope": {key: scope[key] for key in ("artifact_id", "path", "manifest_sha256")},
        "coverage": {key: coverage[key] for key in ("artifact_id", "path", "manifest_sha256")},
        "formal_snapshot": {
            "snapshot_id": snapshot["artifact_id"], "path": snapshot["path"],
            "manifest_sha256": snapshot["manifest_sha256"],
            "semantic_hash": snapshot_manifest.get("semantic_hash"),
        },
        "availability_successor": {key: successor[key] for key in ("artifact_id", "path", "manifest_sha256")},
        "b3": {key: b3[key] for key in ("artifact_id", "path", "manifest_sha256")},
        "lifecycle": {key: lifecycle[key] for key in ("artifact_id", "path", "manifest_sha256")},
        "liquidity": {key: liquidity[key] for key in ("artifact_id", "path", "manifest_sha256")},
        "membership": {
            "snapshot_id": membership["artifact_id"], "path": membership["path"],
            "manifest_sha256": membership["manifest_sha256"],
            "records_path": _repo_path(membership_records, repo_root), "records_sha256": records_hash,
        },
    }
    market_regime = {
        "owner_approval_id": "6170c11c8068f407",
        "owner_approval_manifest_sha256": _sidecar_hash(OWNER_APPROVAL_DIR / "manifest.json"),
        "authorization_scope": owner_manifest["authorization_scope"],
        "qualification": owner_manifest["qualification"],
        "evidence": owner_manifest["evidence"],
        "index_source": owner_manifest["index_source"],
    }
    gate_manifest_path = criteria_root / V2_GATE_ID / "manifest.json"
    kill_manifest_path = criteria_root / V2_KILL_ID / "manifest.json"
    gate_manifest = _read(gate_manifest_path)
    kill_manifest = _read(kill_manifest_path)
    return {
        "schema_version": SCHEMA,
        "status": "published",
        "authorization_scope": "v3_manual_trading_execution",
        "not_authorized_for_b6_oos_gate_promotion_signal": False,
        "template": TEMPLATE,
        "strategy": {"strategy_revision_id": REVISION_ID},
        "predecessor": _predecessor_binding(repo_root),
        "common_calendar": _common_calendar_binding(repo_root),
        "protocol": _protocol_binding(repo_root),
        "data_chain": chain,
        "criteria": {
            "gate_snapshot_id": gate_manifest["snapshot_id"],
            "gate_manifest_sha256": _sidecar_hash(gate_manifest_path),
            "gate_content_hash": gate_manifest["criteria_content_hash"],
            "kill_snapshot_id": kill_manifest["snapshot_id"],
            "kill_manifest_sha256": _sidecar_hash(kill_manifest_path),
            "kill_content_hash": kill_manifest["criteria_content_hash"],
            "envelope_hash": criteria["envelope_hash"],
        },
        "market_regime": market_regime,
        "source_bindings": _source_bindings(source_root),
        "semantics": _semantics(),
    }


def publish_v3_execution_semantics(*, output_root: Path = DEFAULT_OUTPUT_ROOT, repo_root: Path = ROOT) -> dict:
    payload = build_payload(Path(repo_root))
    supplement_id = _sha_bytes(_canonical(payload))[:16]
    manifest = {**payload, "supplement_id": supplement_id}
    raw = _canonical(manifest)
    target = Path(output_root) / supplement_id
    manifest_path = target / "manifest.json"
    sidecar_path = target / "manifest.json.sha256"
    if target.exists():
        if not manifest_path.exists() or not sidecar_path.exists() or manifest_path.read_bytes() != raw or sidecar_path.read_text(encoding="utf-8").split()[0] != _sha_bytes(raw):
            raise ValueError("v3 execution semantics write-once conflict")
        return {"status": "already_published", "supplement_id": supplement_id, "path": str(target), "manifest_sha256": _sha(manifest_path)}
    target.mkdir(parents=True, exist_ok=False)
    temp = target / "manifest.json.tmp"
    temp.write_bytes(raw)
    os.replace(temp, manifest_path)
    sidecar_path.write_text(_sha_bytes(raw) + "  manifest.json\n", encoding="utf-8")
    return {"status": "published", "supplement_id": supplement_id, "path": str(target), "manifest_sha256": _sha(manifest_path)}


if __name__ == "__main__":
    print(json.dumps(publish_v3_execution_semantics(), sort_keys=True))
