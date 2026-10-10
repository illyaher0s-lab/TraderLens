"""Run the approved v3 B4 Canary and one bounded IS event backtest."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path

import pyarrow.parquet as pq

from backend.services.b3_protocol_types import (
    DataSnapshotManifest,
    PointInTimeMembershipSnapshot,
    UniverseMembershipRecord,
)
from backend.services.backtest_engine_qualification import BacktestEngineQualification
from backend.services.formal_pit_partition_adapter import FormalPITPartitionAdapter
from contracts.strategy import ResearchProtocolSnapshot
from scripts.verify_v3_execution_semantics import verify_v3_execution_semantics
from strategy_core.backtest_engine import run_event_backtest
from strategy_core.v3_relative_strength_executor import V3RelativeStrengthExecutionSpec


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_ID = "8770c56c5a69ef128442c0f593f9e4b081a6b13c69744b27171b27cc8c8b7bbe"
REVISION_ID = "6440ffc03a742f4d4632078481cf3abf171eafb1a24f2bc69bc6f352d1b19ebc"
FORMAL_SNAPSHOT_ID = "v3ds_d73256081de82e8a"
FORMAL_SNAPSHOT_HASH = "d73256081de82e8a764ea2394d613af820fd1b82e773c48156ca2463a452c80e"
FORMAL_SNAPSHOT_MANIFEST_SHA256 = "57067e15e6ad1a92b23b42b48173b6cf1af2e7e23f3357320288fb7e109c2680"
SUPPLEMENT_ID = "d1134e96d6b2ec1b"
SUPPLEMENT_MANIFEST_SHA256 = "18e7fd2fb48c089019c9343512641de7ef4f90fd50415c868919ddcabd24c16b"
SUPPLEMENT_DIR = ROOT / "data/pit/v3_execution_semantics_supplements" / SUPPLEMENT_ID
IS_START = date(2025, 6, 27)
IS_END = date(2026, 3, 19)
OOS_START = date(2026, 3, 20)
DEFAULT_OUTPUT_ROOT = ROOT / "data/pit/v3_b4_is_results"
DEFAULT_AUDIT_PATH = ROOT / "docs/verification/task4_v3_b4_is_audit.json"
MEMBERSHIP_ID = "pims_traderlens_v2_shsz_sw2021_pit_005"


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


def _load_protocol(repo_root: Path) -> ResearchProtocolSnapshot:
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
    return protocol


def _load_manifest(repo_root: Path) -> tuple[DataSnapshotManifest, str, dict]:
    manifest_path = Path(repo_root) / "data/pit/v3_formal_data_snapshot_manifests" / FORMAL_SNAPSHOT_ID / "manifest.json"
    manifest_hash = _sidecar_hash(manifest_path)
    manifest_json = _read(manifest_path)
    if manifest_json.get("snapshot_id") != FORMAL_SNAPSHOT_ID:
        raise ValueError("v3 formal snapshot identity mismatch")
    manifest = DataSnapshotManifest.model_validate(manifest_json)
    if manifest.semantic_hash != FORMAL_SNAPSHOT_HASH or manifest.not_authorized_for_b6_oos_gate_promotion_signal is not False:
        raise ValueError("v3 formal snapshot authorization/hash mismatch")
    return manifest, manifest_hash, manifest_json


def _load_universe(repo_root: Path) -> PointInTimeMembershipSnapshot:
    directory = Path(repo_root) / "data/pit/pit_membership_snapshots" / MEMBERSHIP_ID
    manifest_path = directory / "manifest.json"
    manifest = _read(manifest_path)
    manifest_hash = _sidecar_hash(manifest_path)
    records_path = directory / "records.parquet"
    records_hash = _sidecar_hash(records_path)
    if manifest.get("snapshot_id") != MEMBERSHIP_ID or manifest.get("records_parquet_sha256") != records_hash:
        raise ValueError("v3 membership exact binding mismatch")
    records = tuple(
        UniverseMembershipRecord(
            symbol=row["symbol"], effective_from=row["effective_from"], effective_to=row["effective_to"],
            source=row["source"], snapshot_id=row["snapshot_id"],
        )
        for row in pq.read_table(records_path).to_pylist()
    )
    if len(records) != manifest.get("record_count") or any(record.snapshot_id != MEMBERSHIP_ID for record in records):
        raise ValueError("v3 membership records mismatch")
    universe = PointInTimeMembershipSnapshot(
        snapshot_id=manifest["snapshot_id"],
        snapshot_date=date.fromisoformat(manifest["snapshot_date"]),
        universe_rule_type=manifest["universe_rule_type"],
        membership_source=manifest["membership_source"],
        include_delisted=manifest["include_delisted"],
        records=records,
        quality_status=manifest["quality_status"],
        gaps=tuple(manifest["gaps"]),
    )
    if not universe.include_delisted or universe.quality_status != "ok":
        raise ValueError("v3 membership is not formal backtest eligible")
    return universe


class _ReadBoundDataSource:
    """Audit the public adapter reads and fail before any OOS access."""

    def __init__(self, raw, allowed_end: date, *, enable_batch_endpoints: bool = False):
        self._raw = raw
        self._allowed_end = allowed_end
        self._enable_batch_endpoints = enable_batch_endpoints
        self.operation_counts: dict[str, int] = {}
        self.max_requested_date: date | None = None

    def _record(self, operation: str, requested_date: date) -> None:
        self.operation_counts[operation] = self.operation_counts.get(operation, 0) + 1
        if self.max_requested_date is None or requested_date > self.max_requested_date:
            self.max_requested_date = requested_date
        if requested_date >= OOS_START or requested_date > self._allowed_end:
            raise ValueError(f"v3 IS attempted OOS/future read: {operation}/{requested_date}")

    def symbols_as_of(self, as_of: date):
        self._record("membership", as_of)
        return self._raw.symbols_as_of(as_of)

    def common_trading_dates(self, start: date, end: date):
        self._record("calendar", end)
        return self._raw.common_trading_dates(start, end)

    def get_daily_bars(self, symbol: str, end: date, n: int):
        self._record("daily_bars_end", end)
        bars = self._raw.get_daily_bars(symbol, end, n)
        for bar in bars:
            self._record("daily_bar", bar.date)
        return bars

    def get_bar(self, symbol: str, day: date):
        self._record("bar", day)
        return self._raw.get_bar(symbol, day)

    def get_daily_bar(self, symbol: str, day: date):
        return self.get_bar(symbol, day)

    def get_adjusted_momentum_endpoints(self, symbols, start_date: date, end_date: date):
        self._record("bar", start_date)
        self._record("bar", end_date)
        if not self._enable_batch_endpoints:
            return None
        reader = getattr(self._raw, "get_adjusted_momentum_endpoints", None)
        if reader is None:
            return None
        return reader(tuple(symbols), start_date, end_date)

    def get_status(self, symbol: str, day: date):
        self._record("status", day)
        return self._raw.get_status(symbol, day)

    def get_daily_status(self, symbol: str, day: date):
        return self.get_status(symbol, day)

    def derive_liquidity(self, symbol: str, execution_day: date):
        self._record("liquidity_execution_boundary", execution_day)
        return self._raw.derive_liquidity(symbol, execution_day)

    def market_regime_blocked(self, as_of: date) -> bool:
        self._record("market_regime", as_of)
        checker = getattr(self._raw, "market_regime_blocked", None)
        return bool(checker(as_of)) if checker is not None else False

    def audit(self) -> dict:
        return {
            "allowed_end": self._allowed_end.isoformat(),
            "oos_start": OOS_START.isoformat(),
            "oos_read_count": 0,
            "max_requested_date": self.max_requested_date.isoformat() if self.max_requested_date else None,
            "operation_counts": dict(sorted(self.operation_counts.items())),
        }


def _validate_canary(payload: dict) -> dict:
    result = payload.get("result")
    if result is None or result.qualification_status != "pass":
        raise ValueError("B4 Canary qualification did not pass")
    if len(result.canary_cases) != 6 or any(case.outcome != "blocked" for case in result.canary_cases):
        raise ValueError("B4 Canary requires all six cases blocked")
    return result.model_dump(mode="json")


def _build_artifact_payload(
    *, protocol: ResearchProtocolSnapshot, manifest: DataSnapshotManifest, manifest_hash: str,
    universe: PointInTimeMembershipSnapshot, supplement: dict, canary: dict, result, read_audit: dict,
    repo_root: Path,
) -> tuple[dict, dict]:
    event_result_json = result.model_dump(mode="json")
    event_result_raw = _canonical(event_result_json)
    event_result_hash = _sha_bytes(event_result_raw)
    payload = {
        "schema_version": "v3_b4_is_result.v1",
        "status": "valid",
        "strategy_revision_id": REVISION_ID,
        "protocol_snapshot_id": PROTOCOL_ID,
        "data_snapshot_hash": manifest.semantic_hash,
        "formal_snapshot": {"snapshot_id": FORMAL_SNAPSHOT_ID, "semantic_hash": manifest.semantic_hash, "manifest_sha256": manifest_hash},
        "supplement": {"supplement_id": supplement["supplement_id"], "manifest_sha256": supplement["manifest_sha256"]},
        "universe": {"snapshot_id": universe.snapshot_id, "universe_rule_type": universe.universe_rule_type, "record_count": len(universe.records)},
        "market_regime_owner_approval_id": "6170c11c8068f407",
        "is_range": {"start": IS_START.isoformat(), "end": IS_END.isoformat()},
        "canary": canary,
        "event_result": {"path": "event_result.json", "sha256": event_result_hash, "canonical_hash": event_result_hash},
        "read_audit": read_audit,
        "source_inventory": {
            "formal_snapshot_manifest": {"path": "data/pit/v3_formal_data_snapshot_manifests/v3ds_d73256081de82e8a/manifest.json", "sha256": manifest_hash},
            "supplement_source_bindings": supplement.get("source_bindings_verified"),
        },
    }
    return payload, event_result_json


def _write_once(output_root: Path, payload: dict, event_result_json: dict) -> dict:
    artifact_id = _sha_bytes(_canonical(payload))[:16]
    manifest = {**payload, "artifact_id": artifact_id}
    target = Path(output_root) / artifact_id
    manifest_path = target / "manifest.json"
    result_path = target / "event_result.json"
    manifest_raw = _canonical(manifest)
    result_raw = _canonical(event_result_json)
    if target.exists():
        if not manifest_path.exists() or not result_path.exists() or manifest_path.read_bytes() != manifest_raw or result_path.read_bytes() != result_raw:
            raise ValueError("v3 B4 IS artifact write-once conflict")
        if _sidecar_hash(manifest_path) != _sha(manifest_path) or _sidecar_hash(result_path) != _sha(result_path):
            raise ValueError("v3 B4 IS artifact sidecar mismatch")
        return {"status": "already_published", "artifact_id": artifact_id, "path": str(target), "manifest_sha256": _sha(manifest_path)}
    target.mkdir(parents=True, exist_ok=False)
    for path, raw in ((result_path, result_raw), (manifest_path, manifest_raw)):
        temp = path.with_name(path.name + ".tmp")
        temp.write_bytes(raw)
        os.replace(temp, path)
        path.with_name(path.name + ".sha256").write_text(_sha_bytes(raw) + f"  {path.name}\n", encoding="utf-8")
    return {"status": "published", "artifact_id": artifact_id, "path": str(target), "manifest_sha256": _sha(manifest_path)}


def _save_audit(path: Path, payload: dict) -> None:
    path = Path(path)
    raw = _canonical(payload)
    if path.exists():
        if path.is_file() and path.read_bytes() == raw:
            return
        raise ValueError("v3 B4 IS audit write-once conflict")
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_bytes(raw)
    os.replace(temp, path)


def _default_audit_path(repo_root: Path, artifact_id: str) -> Path:
    return Path(repo_root) / "docs/verification" / f"task4_v3_b4_is_audit_{artifact_id}.json"


def run_v3_b4_is_once(
    *, repo_root: Path = ROOT, output_root: Path = DEFAULT_OUTPUT_ROOT, audit_path: Path | None = None,
    data_source=None, supplement_dir: Path | None = None,
) -> dict:
    repo_root = Path(repo_root).resolve()
    if audit_path is not None and Path(audit_path).resolve().is_relative_to(repo_root / "docs/verification"):
        raise ValueError("focused B4 runner audit must use an isolated path outside docs/verification")
    protocol = _load_protocol(repo_root)
    manifest, manifest_hash, manifest_json = _load_manifest(repo_root)
    universe = _load_universe(repo_root)
    active_supplement_dir = Path(supplement_dir) if supplement_dir is not None else SUPPLEMENT_DIR
    supplement = verify_v3_execution_semantics(active_supplement_dir, repo_root=repo_root)
    if supplement.get("status") != "verified":
        raise ValueError("v3 execution supplement is not independently verified")
    active_supplement_id = supplement["supplement_id"]
    if active_supplement_id != SUPPLEMENT_ID or supplement.get("manifest_sha256") != SUPPLEMENT_MANIFEST_SHA256:
        raise ValueError("v3 execution supplement exact lineage mismatch")
    if protocol.data_snapshot_hash != manifest.semantic_hash or protocol.data_snapshot_id != FORMAL_SNAPSHOT_ID:
        raise ValueError("v3 protocol/formal snapshot mismatch")
    if protocol.strategy_revision_id != REVISION_ID:
        raise ValueError("v3 protocol/revision mismatch")

    qualification = BacktestEngineQualification().run_qualification_with_b3_protocol(
        protocol=protocol, manifest=manifest, universe_spec=universe, qualification_date=IS_END,
    )
    canary = _validate_canary(qualification)
    raw_source = data_source if data_source is not None else FormalPITPartitionAdapter(repo_root)
    audited_source = _ReadBoundDataSource(
        raw_source, IS_END, enable_batch_endpoints=False
    )
    spec = V3RelativeStrengthExecutionSpec(
        strategy_revision_id=REVISION_ID,
        protocol_snapshot_id=PROTOCOL_ID,
        data_snapshot_hash=manifest.semantic_hash,
        supplement_id=active_supplement_id,
        backtest_start=IS_START,
        backtest_end=IS_END,
    )
    frozen_supplement = {
        key: supplement[key]
        for key in (
            "status",
            "supplement_id",
            "manifest_sha256",
            "strategy_revision_id",
            "protocol_snapshot_id",
            "data_snapshot_hash",
        )
    }
    result = run_event_backtest(
        spec, audited_source, None, PROTOCOL_ID, manifest.semantic_hash,
        initial_capital=spec.initial_capital, verified_supplement=frozen_supplement,
    )
    if result.backtest_start != IS_START or result.backtest_end != IS_END:
        raise ValueError("v3 B4 result IS range mismatch")
    if result.strategy_revision_id != REVISION_ID or result.protocol_snapshot_id != PROTOCOL_ID:
        raise ValueError("v3 B4 result identity mismatch")
    if result.future_violations:
        raise ValueError("v3 B4 result contains future violations")
    if any(fill.fill_date > IS_END for fill in result.fills):
        raise ValueError("v3 B4 result contains post-IS fill")
    read_audit = audited_source.audit()
    if read_audit["oos_read_count"] != 0 or (read_audit["max_requested_date"] and read_audit["max_requested_date"] >= OOS_START.isoformat()):
        raise ValueError("v3 B4 runner read OOS")
    payload, event_result_json = _build_artifact_payload(
        protocol=protocol, manifest=manifest, manifest_hash=manifest_hash, universe=universe,
        supplement=supplement, canary=canary, result=result, read_audit=read_audit, repo_root=repo_root,
    )
    published = _write_once(output_root, payload, event_result_json)
    audit = {
        "status": published["status"], "artifact_id": published["artifact_id"], "artifact_path": published["path"],
        "is_range": {"start": IS_START.isoformat(), "end": IS_END.isoformat()},
        "canary": canary, "future_violations": len(result.future_violations),
        "fills": len(result.fills), "order_intents": len(result.order_intents), "rejections": len(result.rejected_orders),
        "read_audit": read_audit,
    }
    target_audit_path = (
        Path(audit_path)
        if audit_path is not None
        else _default_audit_path(repo_root, published["artifact_id"])
    )
    _save_audit(target_audit_path, audit)
    return {**published, **audit}


def verify_v3_b4_is_result(result_dir: Path, *, repo_root: Path = ROOT) -> dict:
    try:
        repo_root = Path(repo_root).resolve()
        result_dir = Path(result_dir)
        manifest_path = result_dir / "manifest.json"
        result_path = result_dir / "event_result.json"
        manifest_hash = _sidecar_hash(manifest_path)
        result_hash = _sidecar_hash(result_path)
        manifest = _read(manifest_path)
        event_json = _read(result_path)
        if manifest.get("schema_version") != "v3_b4_is_result.v1" or manifest.get("status") != "valid":
            raise ValueError("B4 IS artifact schema/status mismatch")
        if manifest["event_result"]["sha256"] != result_hash or manifest["event_result"]["canonical_hash"] != _sha_bytes(_canonical(event_json)):
            raise ValueError("B4 event result hash mismatch")
        from backend.services.b4_protocol_types import EventBacktestResult

        result = EventBacktestResult.model_validate(event_json)
        if result.strategy_revision_id != REVISION_ID or result.protocol_snapshot_id != PROTOCOL_ID or result.backtest_start != IS_START or result.backtest_end != IS_END or result.future_violations:
            raise ValueError("B4 event result binding mismatch")
        if manifest.get("strategy_revision_id") != REVISION_ID or manifest.get("protocol_snapshot_id") != PROTOCOL_ID:
            raise ValueError("B4 manifest protocol/revision binding mismatch")
        if manifest.get("data_snapshot_hash") != FORMAL_SNAPSHOT_HASH:
            raise ValueError("B4 manifest data snapshot binding mismatch")
        if manifest.get("formal_snapshot") != {
            "snapshot_id": FORMAL_SNAPSHOT_ID,
            "semantic_hash": FORMAL_SNAPSHOT_HASH,
            "manifest_sha256": FORMAL_SNAPSHOT_MANIFEST_SHA256,
        }:
            raise ValueError("B4 manifest formal snapshot binding mismatch")
        if manifest.get("supplement") != {
            "supplement_id": SUPPLEMENT_ID,
            "manifest_sha256": SUPPLEMENT_MANIFEST_SHA256,
        }:
            raise ValueError("B4 manifest supplement lineage mismatch")
        supplement_dir = repo_root / "data/pit/v3_execution_semantics_supplements" / SUPPLEMENT_ID
        supplement = verify_v3_execution_semantics(supplement_dir, repo_root=repo_root)
        if supplement.get("status") != "verified" or supplement.get("supplement_id") != SUPPLEMENT_ID or supplement.get("manifest_sha256") != SUPPLEMENT_MANIFEST_SHA256:
            raise ValueError("B4 supplement is not independently verified")
        if manifest.get("read_audit", {}).get("oos_read_count") != 0:
            raise ValueError("B4 artifact reports OOS reads")
        if manifest.get("canary", {}).get("qualification_status") != "pass" or len(manifest.get("canary", {}).get("canary_cases", [])) != 6 or any(case.get("outcome") != "blocked" for case in manifest["canary"]["canary_cases"]):
            raise ValueError("B4 Canary binding mismatch")
        payload = {key: value for key, value in manifest.items() if key != "artifact_id"}
        if manifest.get("artifact_id") != _sha_bytes(_canonical(payload))[:16]:
            raise ValueError("B4 artifact identity mismatch")
        return {"status": "verified", "artifact_id": manifest["artifact_id"], "manifest_sha256": manifest_hash, "event_result_sha256": result_hash}
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
        return {"status": "invalid", "reason": str(error)}


if __name__ == "__main__":
    print(json.dumps(run_v3_b4_is_once(), sort_keys=True))
