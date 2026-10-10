from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

from backend.db.strategy import StrategyDB
from backend.services.oos_budget_ledger import OOSBudgetLedger
from backend.services.research_protocol_freezer import (
    CRITERIA_ENVELOPE_V2,
    ResearchProtocolFreezer,
    validate_v3_gate_1_4,
)
from contracts.strategy import (
    FrozenCriteriaReference,
    ProtocolFreezePreflightResult,
    ResearchProtocolSnapshot,
)
from scripts.run_v3_task4_once import (
    B3_ID,
    MEMBERSHIP_ID,
    V3_FORMAL_SNAPSHOT_ROOT,
    V3_SUCCESSOR_ROOT,
    _build_provenance_records,
    _parse_date,
    _sha256,
    _verify_membership_artifact,
)
from scripts.verify_v3_gate_criteria import verify_criteria_pair


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT / "data" / "strategy.db"
CRITERIA_ROOT = ROOT / "data" / "pit" / "prototype_gate_v2_criteria"
HISTORICAL_COVERAGE_ROOT = ROOT / "data" / "pit" / "v3_historical_coverage_packages" / "1e79d26460c0c109"
HISTORICAL_SCOPE_ROOT = ROOT / "data" / "pit" / "historical_scope_freezes"
B3_MANIFEST = ROOT / "data" / "pit" / "b3_execution_input_packages" / B3_ID / "manifest.json"

OLD_PROTOCOL_ID = "6f7cbdcdeb26f8cdd2611a5450dbab3ff22544b6a66ec8539f5cab9151329111"
OLD_REVISION_ID = "6440ffc03a742f4d4632078481cf3abf171eafb1a24f2bc69bc6f352d1b19ebc"
EXPECTED_PROTOCOL_ID = "8770c56c5a69ef128442c0f593f9e4b081a6b13c69744b27171b27cc8c8b7bbe"
EXPECTED_PAYLOAD_SHA256 = "2872d63578d66e6dfc02fd767c4061fd3e291bcb9bbd65f0f2409a4482f6e2a3"
EXPECTED_GATE_ID = "prototype_gate_v2_gate_v2_2bd8670c2e0fe084"
EXPECTED_KILL_ID = "prototype_gate_v2_kill_v2_ea47b0c73ed2476e"
EXPECTED_ENVELOPE_HASH = "94da0dda30af75d663a7d28deb0a15d64a4e068586a1295f3b4f52203a8c4738"
EXPECTED_DIFF_FIELDS = frozenset(
    {
        "protocol_snapshot_id",
        "gate_snapshot_id",
        "kill_criteria_snapshot_id",
        "gate_criteria_hash",
    }
)
TABLES = (
    "research_protocol_snapshots",
    "b6_validation_tasks",
    "oos_budget_reservations",
    "oos_budget_state",
    "oos_evaluation_ledgers",
    "immutable_backtest_reports",
    "prototype_gate_results_v2",
)


def _counts(db: StrategyDB) -> dict[str, int]:
    return {
        table: db.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in TABLES
    }


def _verify_v2_criteria(repo_root: Path) -> dict:
    criteria_root = Path(repo_root) / CRITERIA_ROOT.relative_to(ROOT)
    result = verify_criteria_pair(criteria_root)
    if result.get("status") != "valid":
        raise ValueError(f"criteria v2 verification failed: {result}")
    if result["gate"]["snapshot_id"] != EXPECTED_GATE_ID:
        raise ValueError("criteria v2 Gate identity mismatch")
    if result["kill"]["snapshot_id"] != EXPECTED_KILL_ID:
        raise ValueError("criteria v2 Kill identity mismatch")
    if result.get("envelope_hash") != EXPECTED_ENVELOPE_HASH:
        raise ValueError("criteria v2 envelope identity mismatch")
    return result


def _build_candidate(*, repo_root: Path, db: StrategyDB, criteria: dict) -> tuple[ResearchProtocolSnapshot, ResearchProtocolSnapshot]:
    repo_root = Path(repo_root)
    membership_manifest, membership_manifest_hash, membership_records_hash = _verify_membership_artifact(repo_root)
    b3_manifest_path = repo_root / B3_MANIFEST.relative_to(ROOT)
    b3_manifest = json.loads(b3_manifest_path.read_text(encoding="utf-8"))
    template, universe, draft, _ = _build_provenance_records(
        b3_manifest=b3_manifest,
        b3_manifest_hash=_sha256(b3_manifest_path),
        membership_manifest=membership_manifest,
        membership_manifest_hash=membership_manifest_hash,
        membership_records_hash=membership_records_hash,
    )

    old_protocol = db.get_protocol_snapshot(OLD_PROTOCOL_ID)
    if old_protocol is None:
        raise ValueError("authoritative old B6 protocol is missing")
    if (
        old_protocol.protocol_snapshot_id != OLD_PROTOCOL_ID
        or old_protocol.strategy_revision_id != OLD_REVISION_ID
        or old_protocol.protocol_profile != "b6_coverage_bound"
    ):
        raise ValueError("authoritative old B6 protocol identity mismatch")

    formal_root = repo_root / V3_FORMAL_SNAPSHOT_ROOT
    successor_root = repo_root / V3_SUCCESSOR_ROOT
    formal_dirs = sorted(path for path in formal_root.iterdir() if path.is_dir())
    successor_dirs = sorted(path for path in successor_root.iterdir() if path.is_dir())
    if len(formal_dirs) != 1 or len(successor_dirs) != 1:
        raise ValueError("expected exactly one formal snapshot and successor")

    gate1_4 = validate_v3_gate_1_4(
        successor_dir=successor_dirs[0],
        predecessor_manifest_path=b3_manifest_path,
        coverage_manifest_path=HISTORICAL_COVERAGE_ROOT / "manifest.json",
        coverage_sidecar_path=HISTORICAL_COVERAGE_ROOT / "manifest.json.sha256",
        coverage_by_code_path=HISTORICAL_COVERAGE_ROOT / "coverage_by_code.parquet",
        coverage_by_date_path=HISTORICAL_COVERAGE_ROOT / "coverage_by_date.parquet",
        unavailable_path=HISTORICAL_COVERAGE_ROOT / "unavailable_security_dates.parquet",
        formal_snapshot_dir=formal_dirs[0],
        approved_template=template,
        scope_freeze_path=HISTORICAL_SCOPE_ROOT / "acbc49159d989a46" / "manifest.json",
        strategy_draft=draft,
    )
    if gate1_4.get("status") != "valid":
        raise ValueError(f"v3 Gate 1-4 verification failed: {gate1_4}")

    scope_path = HISTORICAL_SCOPE_ROOT / gate1_4["scope_id"] / "manifest.json"
    scope = json.loads(scope_path.read_text(encoding="utf-8"))
    gate = criteria["gate"]
    kill = criteria["kill"]
    candidate = ResearchProtocolFreezer().freeze_b6_coverage_bound_protocol(
        successor_dir=successor_dirs[0],
        predecessor_manifest_path=b3_manifest_path,
        coverage_manifest_path=HISTORICAL_COVERAGE_ROOT / "manifest.json",
        coverage_sidecar_path=HISTORICAL_COVERAGE_ROOT / "manifest.json.sha256",
        coverage_by_code_path=HISTORICAL_COVERAGE_ROOT / "coverage_by_code.parquet",
        coverage_by_date_path=HISTORICAL_COVERAGE_ROOT / "coverage_by_date.parquet",
        unavailable_path=HISTORICAL_COVERAGE_ROOT / "unavailable_security_dates.parquet",
        formal_snapshot_dir=formal_dirs[0],
        approved_template=template,
        gate_reference=FrozenCriteriaReference(
            snapshot_id=gate["snapshot_id"],
            criteria_json=gate["criteria_json"],
            declared_content_hash=gate["criteria_content_hash"],
        ),
        kill_reference=FrozenCriteriaReference(
            snapshot_id=kill["snapshot_id"],
            criteria_json=kill["criteria_json"],
            declared_content_hash=kill["criteria_content_hash"],
        ),
        ledger=OOSBudgetLedger(db),
        strategy_draft=draft,
        universe=universe,
        oos_window_rule_id=scope["split"]["rule_id"],
        oos_window_start=_parse_date(scope["split"]["oos_start"], "oos_start"),
        oos_window_end=_parse_date(scope["split"]["oos_end"], "oos_end"),
        frozen_by=template.authorized_by,
        backtest_start=_parse_date(scope["execution"]["start"], "backtest_start"),
        scope_freeze_path=scope_path,
        gate_criteria_hash=criteria["envelope_hash"],
        criteria_envelope_schema=CRITERIA_ENVELOPE_V2,
    )
    if isinstance(candidate, ProtocolFreezePreflightResult):
        raise ValueError(f"v2 protocol freezer blocked: {candidate.model_dump(mode='json')}")
    if candidate.protocol_snapshot_id != EXPECTED_PROTOCOL_ID:
        raise ValueError("candidate protocol ID mismatch")
    payload_sha = hashlib.sha256(candidate.model_dump_json().encode("utf-8")).hexdigest()
    if payload_sha != EXPECTED_PAYLOAD_SHA256:
        raise ValueError("candidate protocol payload SHA mismatch")

    old_values = old_protocol.model_dump()
    candidate_values = candidate.model_dump()
    diff_fields = {key for key in old_values if old_values[key] != candidate_values[key]}
    if diff_fields != EXPECTED_DIFF_FIELDS:
        raise ValueError(f"old/new protocol diff mismatch: {sorted(diff_fields)}")
    return candidate, old_protocol


def _publish_v3_b6_protocol_v2(*, repo_root: Path, db_path: Path) -> dict:
    repo_root = Path(repo_root).resolve()
    db_path = Path(db_path).resolve()
    criteria = _verify_v2_criteria(repo_root)
    db = StrategyDB(str(db_path))
    try:
        before = _counts(db)
        candidate, old_protocol = _build_candidate(repo_root=repo_root, db=db, criteria=criteria)
        existing = db.get_protocol_snapshot(candidate.protocol_snapshot_id)
        if existing is not None and existing != candidate:
            raise ValueError("new protocol identity exists with conflicting payload")
        persistence_status = db.store_protocol_snapshot_exact(candidate)
        persisted = db.get_protocol_snapshot(candidate.protocol_snapshot_id)
        if persisted != candidate:
            raise ValueError("new protocol read-back mismatch")
        if db.get_protocol_snapshot(OLD_PROTOCOL_ID) != old_protocol:
            raise ValueError("old protocol changed during v2 publish")
        after = _counts(db)
        before_protocol_count = before["research_protocol_snapshots"]
        after_protocol_count = after["research_protocol_snapshots"]
        if persistence_status == "created":
            valid_protocol_counts = {before_protocol_count + 1}
        else:
            # A competing writer may commit the candidate between this
            # connection's pre-count and its exact-reuse read.
            valid_protocol_counts = {before_protocol_count, before_protocol_count + 1}
        if after_protocol_count not in valid_protocol_counts:
            raise ValueError("unexpected protocol row count after v2 publish")
        for table in TABLES:
            if table != "research_protocol_snapshots" and after[table] != before[table]:
                raise ValueError(f"unexpected side effect in {table}")
        return {
            "status": persistence_status,
            "protocol_snapshot_id": candidate.protocol_snapshot_id,
            "payload_sha256": EXPECTED_PAYLOAD_SHA256,
            "criteria_envelope_hash": EXPECTED_ENVELOPE_HASH,
            "changed_fields": sorted(EXPECTED_DIFF_FIELDS),
            "b6_task_created": False,
            "oos_touched": False,
        }
    finally:
        db.close()


def publish_v3_b6_protocol_v2() -> dict:
    """Publish or exactly reuse the server-owned v2 protocol on the default DB."""
    return _publish_v3_b6_protocol_v2(repo_root=ROOT, db_path=DEFAULT_DB_PATH)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args:
        print(json.dumps({"status": "invalid_invocation", "reason": "no arguments are accepted"}, sort_keys=True))
        return 2
    try:
        result = publish_v3_b6_protocol_v2()
    except Exception as error:
        print(json.dumps({"status": "blocked", "reason": str(error)}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
