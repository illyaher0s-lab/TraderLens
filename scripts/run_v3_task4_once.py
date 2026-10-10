from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from pathlib import Path

import pyarrow.parquet as pq

from backend.db.strategy import ProtocolSnapshotLookupError, StrategyDB
from backend.services.daily_market_scout import DailyMarketScout
from backend.services.oos_budget_ledger import OOSBudgetLedger
from backend.services.strategy_revision_provenance import validate_strategy_revision_provenance
from backend.services.research_protocol_freezer import (
    CRITERIA_ENVELOPE_V2,
    ResearchProtocolFreezer,
    validate_v3_gate_1_4,
)
from backend.services.strategy_template_library import (
    _governance_map,
    convert_to_frozen_contract,
    get_template_by_id,
)
from contracts.strategy import (
    BacktestUniverseSpec,
    FrozenCriteriaReference,
    ProtocolFreezePreflightResult,
    StrategyDraft,
    StrategyLifecycleState,
    TemplateGovernanceProvenance,
)
from contracts.b6_task import B6ValidationTask, build_b6_task_id, build_b6_task_key
from scripts.run_v3_b4_is_once import (
    FORMAL_SNAPSHOT_HASH,
    FORMAL_SNAPSHOT_ID,
    IS_END,
    IS_START,
    PROTOCOL_ID,
    REVISION_ID,
    verify_v3_b4_is_result,
)
from scripts.verify_v3_b3_successor import verify_v3_b3_successor
from scripts.verify_v3_formal_snapshot import verify_formal_snapshot as verify_v3_snapshot
from scripts.verify_v3_b5_bundle import verify_verified_b5_bundle

B3_ID = "05f38a2884dc7e47"
LIFECYCLE_ID = "49b09326f35936c6"
LIQUIDITY_ID = "7c05ece4d3f01086"
MEMBERSHIP_ID = "pims_traderlens_v2_shsz_sw2021_pit_005"
TEMPLATE_ID = "relative_strength_rotation_shsz_sw2021_v3"
TEMPLATE_VERSION = "v3_shsz_sw2021_pit_12m_liquidity20d"
TEMPLATE_HASH = "f7c0fd8123f62f37118cb947e1735861374435f8707e01b06d788a8ec4df39c1"
DATA_REQUIREMENTS_HASH = "ef2ab5b1dafe4349f305b52733a7dcb018a2961464dfbc6542a10e34805d041d"
TEMPLATE_SOURCE_ID = "template_governance:source:relative_strength_rotation_shsz_sw2021_v3"
TEMPLATE_THEME_ID = "template_governance:theme:relative_strength_rotation_shsz_sw2021_v3"
TEMPLATE_HYPOTHESIS_ID = "template_governance:hypothesis:relative_strength_rotation_shsz_sw2021_v3"
V3_FORMAL_SNAPSHOT_ROOT = "data/pit/v3_formal_data_snapshot_manifests"
V3_SUCCESSOR_ROOT = "data/pit/v3_availability_bounded_qualification_successors"
V3_CRITERIA_ROOT = "data/pit/prototype_gate_v2_criteria"
V3_B5_BUNDLE_ROOT = "data/pit/v3_b5_validation_bundles"
TASK7_B4_ARTIFACT_ID = "958bb9717edd08a9"
TASK7_B4_MANIFEST_SHA256 = "af9ebfbcda0eff795efc4ef26688f57286886206e1e6dfe1699a90a197f8b7c2"
TASK7_B4_EVENT_RESULT_SHA256 = "374479e9df35c80c680adfe34fe95d10a78eb4d049a24fc6bc43cfb3aa0bf1cc"
TASK7_FORMAL_SNAPSHOT_MANIFEST_SHA256 = "57067e15e6ad1a92b23b42b48173b6cf1af2e7e23f3357320288fb7e109c2680"
TASK7_B5_SUPPLEMENT_ID = "d1134e96d6b2ec1b"
TASK7_B5_SUPPLEMENT_DIR = Path("data/pit/v3_execution_semantics_supplements") / TASK7_B5_SUPPLEMENT_ID
TASK7_B5_SUPPLEMENT_MANIFEST_SHA256 = "18e7fd2fb48c089019c9343512641de7ef4f90fd50415c868919ddcabd24c16b"
TASK7_B5_BUNDLE_ID = "e4b03db805ebbdee"
TASK7_B5_BUNDLE_MANIFEST_SHA256 = "fb5b0c3e2cea118f33257a0cc338fe768df7fce237bf8fdf1b8b93dbcc1416a5"
TASK7_B5_BUNDLE_DIR = Path(V3_B5_BUNDLE_ROOT) / TASK7_B5_BUNDLE_ID


class _B4DiscoveryError(ValueError):
    pass


class _V3AdmissionAmbiguous(ValueError):
    pass


def _audit_path(repo_root: Path) -> Path:
    return repo_root / "docs/verification/task4_v3_one_shot_audit.json"


def _save(repo_root: Path, payload: dict, audit_path: Path | None = None) -> dict:
    path = Path(audit_path) if audit_path is not None else _audit_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")
    return {"audit_path": str(path), **payload}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_manifest_with_verified_sidecar(manifest_path: Path) -> tuple[dict, str]:
    manifest_path = Path(manifest_path)
    raw = manifest_path.read_bytes()
    manifest_hash = hashlib.sha256(raw).hexdigest()
    sidecar_path = manifest_path.with_name(manifest_path.name + ".sha256")
    sidecar_tokens = sidecar_path.read_text(encoding="utf-8").split()
    if not sidecar_tokens or sidecar_tokens[0] != manifest_hash:
        raise ValueError(f"manifest sidecar mismatch: {manifest_path}")
    manifest = json.loads(raw)
    if not isinstance(manifest, dict):
        raise ValueError(f"manifest must contain a JSON object: {manifest_path}")
    return manifest, manifest_hash


def _successor_matches_current_v3_inputs(
    manifest: dict,
    *,
    b3_manifest_sha256: str,
    formal_manifest_sha256: str,
    membership_manifest_sha256: str,
    membership_records_sha256: str,
) -> bool:
    lineage = manifest.get("lineage")
    if not isinstance(lineage, dict):
        return False
    b3 = lineage.get("b3")
    formal = manifest.get("formal_snapshot")
    membership = lineage.get("membership")
    template = manifest.get("template")
    if not all(isinstance(value, dict) for value in (b3, formal, membership, template)):
        return False
    return (
        manifest.get("successor_schema_version")
        == "v3_availability_bounded_qualification_successor.v1"
        and manifest.get("status") == "availability_bounded_qualified"
        and manifest.get("authorization_scope") == "b6_coverage_bound"
        and manifest.get(
            "not_authorized_for_b6_oos_gate_promotion_signal_or_data_collection"
        ) is False
        and template.get("template_id") == TEMPLATE_ID
        and template.get("template_version") == TEMPLATE_VERSION
        and template.get("template_hash") == TEMPLATE_HASH
        and template.get("data_requirements_hash") == DATA_REQUIREMENTS_HASH
        and b3.get("artifact_id") == B3_ID
        and b3.get("manifest_sha256") == b3_manifest_sha256
        and formal.get("snapshot_id") == FORMAL_SNAPSHOT_ID
        and formal.get("semantic_hash") == FORMAL_SNAPSHOT_HASH
        and formal.get("manifest_sha256") == formal_manifest_sha256
        and membership.get("snapshot_id") == MEMBERSHIP_ID
        and membership.get("manifest_sha256") == membership_manifest_sha256
        and membership.get("records_sha256") == membership_records_sha256
    )


def _discover_verified_b5_bundle(*, repo_root: Path, bundle_dir: Path | None = None) -> dict:
    try:
        if bundle_dir is None:
            bundle_dir = repo_root / TASK7_B5_BUNDLE_DIR
            if not bundle_dir.is_dir():
                return {"status": "invalid", "reason": "current v3 B5 bundle directory missing"}
        bundle_dir = Path(bundle_dir)
        if not bundle_dir.is_dir():
            return {"status": "invalid", "reason": "v3 B5 bundle directory missing"}
        verification = verify_verified_b5_bundle(repo_root, bundle_dir)
        if verification.get("status") != "verified":
            return verification
        manifest = json.loads((bundle_dir / "manifest.json").read_text(encoding="utf-8"))
        manifest_sha256 = _sha256(bundle_dir / "manifest.json")
        if (
            manifest.get("bundle_id") != TASK7_B5_BUNDLE_ID
            or manifest_sha256 != TASK7_B5_BUNDLE_MANIFEST_SHA256
        ):
            return {"status": "invalid", "reason": "current v3 B5 bundle identity mismatch"}
        lineage = manifest["lineage"]
        return {
            **verification,
            "authorization_scope": manifest["authorization_scope"],
            "not_authorized_for_b6_oos_gate_promotion_signal": manifest[
                "not_authorized_for_b6_oos_gate_promotion_signal"
            ],
            "lineage": lineage,
            "is_range": lineage["is_range"],
            "source_inventory": lineage["source_inventory"],
        }
    except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError) as error:
        return {"status": "invalid", "reason": str(error)}


def _discover_verified_b4_artifact(*, repo_root: Path, result_root: Path | None = None) -> dict | None:
    server_owned_result_root = result_root is None
    result_root = Path(result_root) if result_root is not None else repo_root / "data/pit/v3_b4_is_results"
    if not result_root.exists():
        return None

    supplement_dir = repo_root / TASK7_B5_SUPPLEMENT_DIR
    supplement_manifest_path = supplement_dir / "manifest.json"
    supplement_sidecar_path = supplement_dir / "manifest.json.sha256"
    if not supplement_manifest_path.is_file() or not supplement_sidecar_path.is_file():
        raise _B4DiscoveryError("frozen v3 execution supplement manifest is incomplete")
    supplement_manifest_sha256 = _sha256(supplement_manifest_path)
    sidecar_tokens = supplement_sidecar_path.read_text(encoding="utf-8").split()
    if (
        supplement_manifest_sha256 != TASK7_B5_SUPPLEMENT_MANIFEST_SHA256
        or not sidecar_tokens
        or sidecar_tokens[0] != supplement_manifest_sha256
    ):
        raise _B4DiscoveryError("frozen v3 execution supplement manifest hash mismatch")
    supplement_manifest = json.loads(supplement_manifest_path.read_text(encoding="utf-8"))
    if supplement_manifest.get("supplement_id") != TASK7_B5_SUPPLEMENT_ID:
        raise _B4DiscoveryError("frozen v3 execution supplement identity mismatch")
    expected_supplement_manifest_hash = TASK7_B5_SUPPLEMENT_MANIFEST_SHA256
    candidates = []
    artifact_dirs = (
        [result_root / TASK7_B4_ARTIFACT_ID]
        if server_owned_result_root
        else sorted(path for path in result_root.iterdir() if path.is_dir())
    )
    for artifact_dir in artifact_dirs:
        if not artifact_dir.is_dir():
            continue
        manifest_path = artifact_dir / "manifest.json"
        if not manifest_path.is_file():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise _B4DiscoveryError(f"B4 artifact manifest unreadable: {artifact_dir}") from exc
        if manifest.get("supplement", {}).get("supplement_id") != TASK7_B5_SUPPLEMENT_ID:
            continue
        verified = verify_v3_b4_is_result(artifact_dir, repo_root=repo_root)
        if verified.get("status") != "verified":
            raise _B4DiscoveryError(f"B4 artifact verification failed: {verified.get('reason', 'unknown')}")
        if manifest.get("artifact_id") != artifact_dir.name:
            raise _B4DiscoveryError("B4 artifact path/identity mismatch")
        if (
            manifest.get("protocol_snapshot_id") != PROTOCOL_ID
            or manifest.get("strategy_revision_id") != REVISION_ID
            or manifest.get("data_snapshot_hash") != FORMAL_SNAPSHOT_HASH
            or manifest.get("formal_snapshot", {}).get("snapshot_id") != FORMAL_SNAPSHOT_ID
            or manifest.get("formal_snapshot", {}).get("semantic_hash") != FORMAL_SNAPSHOT_HASH
            or manifest.get("supplement", {}).get("manifest_sha256") != expected_supplement_manifest_hash
            or manifest.get("is_range") != {"start": IS_START.isoformat(), "end": IS_END.isoformat()}
        ):
            raise _B4DiscoveryError("B4 artifact latest supplement/protocol/revision/IS binding mismatch")
        canary = manifest.get("canary", {})
        read_audit = manifest.get("read_audit", {})
        max_requested_date = read_audit.get("max_requested_date")
        if max_requested_date is not None:
            try:
                max_requested_date = _parse_date(max_requested_date, "max_requested_date")
            except ValueError as exc:
                raise _B4DiscoveryError("B4 artifact read-audit date is invalid") from exc
        if (
            canary.get("qualification_status") != "pass"
            or len(canary.get("canary_cases", [])) != 6
            or any(case.get("outcome") != "blocked" for case in canary.get("canary_cases", []))
            or read_audit.get("oos_read_count") != 0
            or (max_requested_date is not None and max_requested_date > IS_END)
        ):
            raise _B4DiscoveryError("B4 artifact qualification/Canary/OOS binding mismatch")
        event_result = json.loads((artifact_dir / "event_result.json").read_text(encoding="utf-8"))
        future_violations = len(event_result.get("future_violations", []))
        if future_violations != 0:
            raise _B4DiscoveryError("B4 artifact reports future violations")
        candidate = {
            "artifact_id": manifest["artifact_id"],
            "path": str(artifact_dir.resolve()),
            "manifest_sha256": verified["manifest_sha256"],
            "event_result_sha256": verified["event_result_sha256"],
            "supplement_id": manifest["supplement"]["supplement_id"],
            "supplement_manifest_sha256": manifest["supplement"]["manifest_sha256"],
            "protocol_snapshot_id": manifest["protocol_snapshot_id"],
            "strategy_revision_id": manifest["strategy_revision_id"],
            "is_range": manifest["is_range"],
            "qualification_status": canary["qualification_status"],
            "canary_blocked_count": sum(case.get("outcome") == "blocked" for case in canary["canary_cases"]),
            "future_violations": future_violations,
            "oos_read_count": read_audit["oos_read_count"],
            "max_requested_date": read_audit["max_requested_date"],
        }
        if server_owned_result_root and (
            candidate["artifact_id"] != TASK7_B4_ARTIFACT_ID
            or candidate["manifest_sha256"] != TASK7_B4_MANIFEST_SHA256
            or candidate["event_result_sha256"] != TASK7_B4_EVENT_RESULT_SHA256
        ):
            raise _B4DiscoveryError("current v3 B4 artifact identity mismatch")
        candidates.append(candidate)

    unique_candidates = {(item["artifact_id"], item["manifest_sha256"], item["event_result_sha256"]): item for item in candidates}
    if len(unique_candidates) > 1:
        raise _B4DiscoveryError("multiple conflicting latest v3 B4 artifacts discovered")
    return next(iter(unique_candidates.values()), None)


def _parse_date(value: str, field: str) -> date:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        try:
            return datetime.strptime(str(value), "%Y%m%d").date()
        except (TypeError, ValueError):
            raise ValueError(f"invalid {field}: {value!r}") from exc


def _canonical_id(kind: str, payload: dict) -> str:
    canonical = json.dumps(
        {"kind": kind, "payload": payload},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _verify_membership_artifact(repo_root: Path) -> tuple[dict, str, str]:
    snapshot_dir = repo_root / "data/pit/pit_membership_snapshots" / MEMBERSHIP_ID
    manifest_path = snapshot_dir / "manifest.json"
    records_path = snapshot_dir / "records.parquet"
    manifest_sidecar = snapshot_dir / "manifest.json.sha256"
    records_sidecar = snapshot_dir / "records.parquet.sha256"
    if not all(path.is_file() for path in (manifest_path, records_path, manifest_sidecar, records_sidecar)):
        raise ValueError("membership artifact files or sidecars missing")

    manifest_hash = _sha256(manifest_path)
    if manifest_sidecar.read_text(encoding="utf-8").split()[0] != manifest_hash:
        raise ValueError("membership manifest sidecar mismatch")
    records_hash = _sha256(records_path)
    if records_sidecar.read_text(encoding="utf-8").split()[0] != records_hash:
        raise ValueError("membership records sidecar mismatch")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("snapshot_id") != MEMBERSHIP_ID or manifest.get("frozen") is not True:
        raise ValueError("membership snapshot identity/frozen binding mismatch")
    if manifest.get("records_parquet_sha256") != records_hash:
        raise ValueError("membership records manifest hash mismatch")
    if manifest.get("universe_rule_type") != "point_in_time_membership":
        raise ValueError("membership universe rule type mismatch")
    if not isinstance(manifest.get("quality_status"), str) or not isinstance(manifest.get("gaps"), list):
        raise ValueError("membership quality metadata missing")

    table = pq.read_table(records_path, columns=["snapshot_id", "effective_from", "effective_to"])
    if table.num_rows != manifest.get("record_count"):
        raise ValueError("membership record count mismatch")
    rows = table.to_pylist()
    if any(row["snapshot_id"] != MEMBERSHIP_ID for row in rows):
        raise ValueError("membership record snapshot binding mismatch")
    effective_from = min(row["effective_from"] for row in rows)
    effective_to_values = [row["effective_to"] for row in rows if row["effective_to"] is not None]
    effective_to = max(
        [row["effective_from"] for row in rows] + effective_to_values
    )
    if effective_from != _parse_date(manifest["date_range_min"], "date_range_min"):
        raise ValueError("membership effective_from does not match records")
    if effective_to != _parse_date(manifest["date_range_max"], "date_range_max"):
        raise ValueError("membership effective_to does not match records")
    return manifest, manifest_hash, records_hash


def _build_provenance_records(
    *,
    b3_manifest: dict,
    b3_manifest_hash: str,
    membership_manifest: dict,
    membership_manifest_hash: str,
    membership_records_hash: str,
) -> tuple[object, BacktestUniverseSpec, StrategyDraft, StrategyLifecycleState]:
    b3_template = b3_manifest.get("template")
    if b3_template != {
        "data_requirements_hash": DATA_REQUIREMENTS_HASH,
        "template_hash": TEMPLATE_HASH,
        "template_id": TEMPLATE_ID,
        "template_version": TEMPLATE_VERSION,
    }:
        raise ValueError("B3/template frozen input mismatch")

    template = get_template_by_id(TEMPLATE_ID)
    if template is None:
        raise ValueError("v3 template is not registered")
    created_at = datetime.combine(_parse_date(membership_manifest["snapshot_date"], "snapshot_date"), datetime.min.time())
    frozen_template = convert_to_frozen_contract(template, created_at=created_at)
    if (
        frozen_template.governance_status != "approved"
        or frozen_template.version != TEMPLATE_VERSION
        or frozen_template.template_hash != TEMPLATE_HASH
        or frozen_template.data_requirements_hash != DATA_REQUIREMENTS_HASH
    ):
        raise ValueError("approved v3 frozen template does not match B3")

    owner_auth = _governance_map()[TEMPLATE_ID]["owner_authorization"]
    provenance = TemplateGovernanceProvenance(
        kind="approved_template_governance",
        template_id=frozen_template.template_id,
        template_version=frozen_template.version,
        template_hash=frozen_template.template_hash,
        data_requirements_hash=frozen_template.data_requirements_hash,
        review_evidence_path=frozen_template.review_evidence_path,
        review_evidence_sha256=frozen_template.review_evidence_sha256,
        reviewer_id=frozen_template.reviewer_id,
        reviewer_kind=owner_auth["reviewer_kind"],
        review_decision=owner_auth["review_decision"],
        reviewed_at=frozen_template.reviewed_at,
        review_due_date=frozen_template.review_due_date,
        owner_authorization_hash=frozen_template.owner_authorization_hash,
        authorized_by=frozen_template.authorized_by,
        authorized_at=frozen_template.authorized_at,
    )

    b3_binding = {
        "artifact_id": B3_ID,
        "manifest_sha256": b3_manifest_hash,
        "listing_lifecycle_successor": b3_manifest["listing_lifecycle_successor"],
        "liquidity_ref": b3_manifest["liquidity_ref"],
    }
    membership_binding = {
        "snapshot_id": MEMBERSHIP_ID,
        "manifest_sha256": membership_manifest_hash,
        "records_sha256": membership_records_hash,
        "snapshot_date": membership_manifest["snapshot_date"],
        "date_range_min": membership_manifest["date_range_min"],
        "date_range_max": membership_manifest["date_range_max"],
        "quality_status": membership_manifest["quality_status"],
        "gaps": membership_manifest["gaps"],
    }
    universe_id = _canonical_id(
        "backtest_universe_spec",
        {
            "template_id": TEMPLATE_ID,
            "template_version": TEMPLATE_VERSION,
            "template_hash": TEMPLATE_HASH,
            "data_requirements_hash": DATA_REQUIREMENTS_HASH,
            "b3": b3_binding,
            "membership": membership_binding,
        },
    )
    universe = BacktestUniverseSpec(
        universe_spec_id=universe_id,
        universe_rule_type="point_in_time_membership",
        membership_source=f"B3:{B3_ID}:{membership_manifest['membership_source']}",
        membership_effective_from=_parse_date(membership_manifest["date_range_min"], "date_range_min"),
        membership_effective_to=_parse_date(membership_manifest["date_range_max"], "date_range_max"),
        snapshot_date=_parse_date(membership_manifest["snapshot_date"], "snapshot_date"),
        include_delisted=membership_manifest["include_delisted"],
        membership_snapshot_ids=(MEMBERSHIP_ID,),
        quality_status=membership_manifest["quality_status"],
        gaps=tuple(membership_manifest["gaps"]),
    )

    strategy_config = template._serialize_for_hash(template.strategy_config_payload)
    strategy_config_json = json.dumps(strategy_config, sort_keys=True, separators=(",", ":"))
    revision_payload = {
        "theme_id": TEMPLATE_THEME_ID,
        "hypothesis_id": TEMPLATE_HYPOTHESIS_ID,
        "template": frozen_template.model_dump(mode="json"),
        "provenance": provenance.model_dump(mode="json"),
        "backtest_universe_spec_id": universe.universe_spec_id,
        "strategy_config_json": strategy_config_json,
        "sample_split_rule_id": template.sample_split_rule_ids[0],
        "source_snapshot_id": TEMPLATE_SOURCE_ID,
    }
    revision_id = _canonical_id("strategy_revision", revision_payload)
    draft = StrategyDraft(
        strategy_revision_id=revision_id,
        theme_id=TEMPLATE_THEME_ID,
        hypothesis_id=TEMPLATE_HYPOTHESIS_ID,
        strategy_template_id=TEMPLATE_ID,
        strategy_template_version=TEMPLATE_VERSION,
        strategy_template_hash=TEMPLATE_HASH,
        hypothesis_source_snapshot_id=TEMPLATE_SOURCE_ID,
        backtest_universe_spec_id=universe.universe_spec_id,
        strategy_config_json=strategy_config_json,
        sample_split_rule_id=template.sample_split_rule_ids[0],
        created_at=created_at,
        provenance=provenance,
    )
    lifecycle_payload = {
        "strategy_revision_id": revision_id,
        "state_version": 1,
        "state": "draft",
        "source_record_id": TEMPLATE_SOURCE_ID,
        "recorded_by": frozen_template.authorized_by,
    }
    lifecycle_id = _canonical_id("strategy_lifecycle_state", lifecycle_payload)
    lifecycle = StrategyLifecycleState(
        lifecycle_state_id=lifecycle_id,
        strategy_revision_id=revision_id,
        state_version=1,
        state="draft",
        source_record_id=TEMPLATE_SOURCE_ID,
        recorded_at=created_at,
        recorded_by=frozen_template.authorized_by,
    )
    return frozen_template, universe, draft, lifecycle


def _materialize_and_preflight(
    *, repo_root: Path, db_path: Path, b3_manifest: dict, b3_manifest_hash: str, criteria_root: Path,
    b4_results_root: Path | None = None, b5_bundle_dir: Path | None = None,
) -> dict:
    membership_manifest, membership_manifest_hash, membership_records_hash = _verify_membership_artifact(repo_root)
    template, universe, draft, lifecycle = _build_provenance_records(
        b3_manifest=b3_manifest,
        b3_manifest_hash=b3_manifest_hash,
        membership_manifest=membership_manifest,
        membership_manifest_hash=membership_manifest_hash,
        membership_records_hash=membership_records_hash,
    )
    strategy_db = StrategyDB(str(db_path))
    try:
        ids = strategy_db.materialize_strategy_provenance(template, universe, draft, lifecycle)
        validation = validate_strategy_revision_provenance(strategy_db, None, draft.strategy_revision_id)
        validation_payload = {
            "is_valid": validation.is_valid,
            "reason_code": validation.reason_code,
            "detail": validation.detail,
        }
        if not validation.is_valid:
            return {
                **ids,
                "provenance_validation": validation_payload,
                "first_missing_prerequisite": "strategy_provenance",
                "reason": "hard_block:strategy_provenance_invalid",
            }
        formal_root = repo_root / V3_FORMAL_SNAPSHOT_ROOT
        successor_root = repo_root / V3_SUCCESSOR_ROOT
        formal_snapshot_dir = formal_root / FORMAL_SNAPSHOT_ID
        formal_manifest_path = formal_snapshot_dir / "manifest.json"
        formal_sidecar_path = formal_manifest_path.with_name(formal_manifest_path.name + ".sha256")
        if not formal_snapshot_dir.is_dir() or not formal_manifest_path.is_file() or not formal_sidecar_path.is_file():
            return {
                **ids,
                "provenance_validation": validation_payload,
                "first_missing_prerequisite": "b6_v3_admission",
                "reason": "hard_block:b6_v3_admission_missing",
                "gate1_4_validation": {"status": "invalid", "reason": "pinned formal snapshot or sidecar is missing"},
            }
        gate1_4 = None
        try:
            formal_manifest, formal_manifest_sha256 = _read_manifest_with_verified_sidecar(
                formal_manifest_path
            )
            if (
                formal_manifest.get("snapshot_id") != FORMAL_SNAPSHOT_ID
                or formal_manifest.get("semantic_hash") != FORMAL_SNAPSHOT_HASH
                or formal_manifest_sha256 != TASK7_FORMAL_SNAPSHOT_MANIFEST_SHA256
            ):
                raise ValueError("pinned formal snapshot identity/hash mismatch")

            formal_verification = verify_v3_snapshot(
                formal_snapshot_dir,
                coverage_dir=repo_root / "data/pit/v3_historical_coverage_packages/1e79d26460c0c109",
                scope_dir=repo_root / "data/pit/historical_scope_freezes/acbc49159d989a46",
            )
            if formal_verification.get("status") != "valid":
                raise ValueError(f"pinned formal snapshot verifier failed: {formal_verification}")
            if draft.strategy_revision_id != REVISION_ID:
                raise ValueError("current strategy revision does not match the pinned v3 identity")

            for other_formal_dir in sorted(
                path for path in formal_root.iterdir()
                if path.is_dir() and path != formal_snapshot_dir
            ) if formal_root.exists() else []:
                other_manifest_path = other_formal_dir / "manifest.json"
                if not other_manifest_path.is_file():
                    continue
                other_manifest, other_manifest_sha256 = _read_manifest_with_verified_sidecar(
                    other_manifest_path
                )
                if other_manifest.get("snapshot_id") == FORMAL_SNAPSHOT_ID:
                    if other_manifest_sha256 != formal_manifest_sha256:
                        raise _V3AdmissionAmbiguous(
                            "formal snapshot ID has conflicting manifest hashes"
                        )
                    raise _V3AdmissionAmbiguous(
                        "duplicate formal snapshot ID appears in multiple directories"
                    )

            successor_dirs = sorted(
                path for path in successor_root.iterdir()
                if path.is_dir() and (path / "manifest.json").is_file()
            ) if successor_root.exists() else []
            seen_successor_ids: dict[str, tuple[str, Path]] = {}
            successor_manifests: list[tuple[Path, dict, str]] = []
            for successor_dir in successor_dirs:
                successor_manifest_path = successor_dir / "manifest.json"
                successor_manifest, successor_manifest_sha256 = (
                    _read_manifest_with_verified_sidecar(successor_manifest_path)
                )
                successor_id = successor_manifest.get("successor_id")
                if not isinstance(successor_id, str) or not successor_id:
                    raise ValueError(f"successor ID is missing: {successor_manifest_path}")
                previous = seen_successor_ids.get(successor_id)
                if previous is not None:
                    if previous[0] != successor_manifest_sha256:
                        raise _V3AdmissionAmbiguous(
                            "successor ID has conflicting manifest hashes"
                        )
                    raise _V3AdmissionAmbiguous(
                        "duplicate successor ID appears in multiple directories"
                    )
                seen_successor_ids[successor_id] = (successor_manifest_sha256, successor_dir)
                if successor_dir.name != successor_id:
                    raise ValueError("successor path/manifest identity mismatch")
                successor_manifests.append(
                    (successor_dir, successor_manifest, successor_manifest_sha256)
                )

            verified_successors: list[tuple[Path, dict]] = []
            for successor_dir, successor_manifest, successor_manifest_sha256 in successor_manifests:
                successor_id = successor_manifest["successor_id"]
                if not _successor_matches_current_v3_inputs(
                    successor_manifest,
                    b3_manifest_sha256=b3_manifest_hash,
                    formal_manifest_sha256=formal_manifest_sha256,
                    membership_manifest_sha256=membership_manifest_hash,
                    membership_records_sha256=membership_records_hash,
                ):
                    continue

                gate_candidate = validate_v3_gate_1_4(
                    successor_dir=successor_dir,
                    predecessor_manifest_path=repo_root / "data/pit/b3_execution_input_packages" / B3_ID / "manifest.json",
                    coverage_manifest_path=repo_root / "data/pit/v3_historical_coverage_packages/1e79d26460c0c109/manifest.json",
                    coverage_sidecar_path=repo_root / "data/pit/v3_historical_coverage_packages/1e79d26460c0c109/manifest.json.sha256",
                    coverage_by_code_path=repo_root / "data/pit/v3_historical_coverage_packages/1e79d26460c0c109/coverage_by_code.parquet",
                    coverage_by_date_path=repo_root / "data/pit/v3_historical_coverage_packages/1e79d26460c0c109/coverage_by_date.parquet",
                    unavailable_path=repo_root / "data/pit/v3_historical_coverage_packages/1e79d26460c0c109/unavailable_security_dates.parquet",
                    formal_snapshot_dir=formal_snapshot_dir,
                    approved_template=template,
                    scope_freeze_path=repo_root / "data/pit/historical_scope_freezes/acbc49159d989a46/manifest.json",
                    strategy_draft=draft,
                )
                if (
                    gate_candidate.get("status") != "valid"
                    or gate_candidate.get("successor_id") != successor_id
                    or gate_candidate.get("successor_manifest_sha256") != successor_manifest_sha256
                    or gate_candidate.get("snapshot_id") != FORMAL_SNAPSHOT_ID
                    or gate_candidate.get("snapshot_manifest_sha256") != formal_manifest_sha256
                    or gate_candidate.get("snapshot_semantic_hash") != FORMAL_SNAPSHOT_HASH
                ):
                    raise ValueError("official v3 admission verifier returned a mismatched identity")
                verified_successors.append((successor_dir, gate_candidate))

            if len(verified_successors) > 1:
                raise _V3AdmissionAmbiguous(
                    "multiple verified successors match the current B3/formal/membership/template/revision"
                )
            if not verified_successors:
                return {
                    **ids,
                    "provenance_validation": validation_payload,
                    "first_missing_prerequisite": "b6_v3_admission",
                    "reason": "hard_block:b6_v3_admission_missing",
                    "gate1_4_validation": {"status": "invalid", "reason": "no verified successor matches current pinned inputs"},
                }
            selected_successor_dir, gate1_4 = verified_successors[0]
        except _V3AdmissionAmbiguous as exc:
            return {
                **ids,
                "provenance_validation": validation_payload,
                "first_missing_prerequisite": "b6_v3_admission",
                "reason": "hard_block:b6_v3_admission_ambiguous",
                "detail": str(exc),
                "gate1_4_validation": {"status": "invalid", "reason": str(exc)},
            }
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            return {
                **ids,
                "provenance_validation": validation_payload,
                "first_missing_prerequisite": "b6_v3_admission",
                "reason": "hard_block:b6_v3_admission_invalid",
                "detail": str(exc),
                "gate1_4_validation": {"status": "invalid", "reason": str(exc)},
            }
        criteria_root = Path(criteria_root)
        if gate1_4 is not None and criteria_root.exists():
            from scripts.verify_v3_gate_criteria import verify_criteria_pair

            criteria_validation = verify_criteria_pair(criteria_root)
            if criteria_validation.get("status") != "valid":
                return {
                    **ids,
                    "provenance_validation": validation_payload,
                    "first_missing_prerequisite": "b6_criteria",
                    "reason": "hard_block:b6_criteria_invalid",
                    "gate1_4_validation": gate1_4,
                    "gate5_validation": criteria_validation,
                }
            gate = criteria_validation["gate"]
            kill = criteria_validation["kill"]
            gate_ref = {
                "snapshot_id": gate["snapshot_id"],
                "criteria_content_hash": gate["criteria_content_hash"],
            }
            kill_ref = {
                "snapshot_id": kill["snapshot_id"],
                "criteria_content_hash": kill["criteria_content_hash"],
            }
            scope_path = repo_root / "data/pit/historical_scope_freezes" / gate1_4["scope_id"] / "manifest.json"
            scope = json.loads(scope_path.read_text(encoding="utf-8"))
            coverage_dir = repo_root / "data/pit/v3_historical_coverage_packages" / gate1_4["coverage_id"]

            try:
                b4_artifact = _discover_verified_b4_artifact(repo_root=repo_root, result_root=b4_results_root)
            except _B4DiscoveryError as exc:
                return {
                    **ids,
                    "provenance_validation": validation_payload,
                    "first_missing_prerequisite": "b4_event_backtest",
                    "status": "hard_block:b4_event_backtest_invalid",
                    "reason": "hard_block:b4_event_backtest_invalid",
                    "detail": str(exc),
                    "gate1_4_validation": gate1_4,
                    "gate5_validation": {
                        "status": "valid",
                        "gate": gate_ref,
                        "kill": kill_ref,
                        "envelope_hash": criteria_validation["envelope_hash"],
                    },
                }
            if b4_artifact is None:
                return {
                    **ids,
                    "provenance_validation": validation_payload,
                    "first_missing_prerequisite": "b4_event_backtest",
                    "reason": "hard_block:b4_event_backtest_missing",
                    "gate1_4_validation": gate1_4,
                    "gate5_validation": {
                        "status": "valid",
                        "gate": gate_ref,
                        "kill": kill_ref,
                        "envelope_hash": criteria_validation["envelope_hash"],
                    },
                    "deferred_missing_prerequisites": ["B4 event backtest"],
                }

            b5_bundle = _discover_verified_b5_bundle(repo_root=repo_root, bundle_dir=b5_bundle_dir)
            if b5_bundle.get("status") == "verified":
                expected_b4_lineage = {
                    "artifact_id": b4_artifact["artifact_id"],
                    "manifest_sha256": b4_artifact["manifest_sha256"],
                    "event_sha256": b4_artifact["event_result_sha256"],
                }
                if b5_bundle.get("lineage", {}).get("b4") != expected_b4_lineage:
                    b5_bundle = {
                        **b5_bundle,
                        "status": "invalid",
                        "reason": "B4/B5 lineage mismatch",
                    }
            if b5_bundle.get("status") != "verified":
                return {
                    **ids,
                    "provenance_validation": validation_payload,
                    "first_missing_prerequisite": "b5_validation_inputs",
                    "reason": "hard_block:b5_validation_inputs_missing",
                    "gate1_4_validation": gate1_4,
                    "gate5_validation": {
                        "status": "valid",
                        "gate": gate_ref,
                        "kill": kill_ref,
                        "envelope_hash": criteria_validation["envelope_hash"],
                    },
                    "b4_artifact": b4_artifact,
                    "b5_bundle": b5_bundle,
                    "missing_b5_validation_inputs": ["verified_b5_bundle"],
                    "deferred_missing_prerequisites": ["verified B5 bundle"],
                }

            existing_protocol = strategy_db.get_protocol_snapshot(PROTOCOL_ID)
            protocol_exists = existing_protocol is not None
            if protocol_exists:
                if (
                    existing_protocol.strategy_revision_id != draft.strategy_revision_id
                    or existing_protocol.protocol_profile != "b6_coverage_bound"
                ):
                    return {
                        **ids,
                        "provenance_validation": validation_payload,
                        "first_missing_prerequisite": "b6_protocol",
                        "reason": "hard_block:b6_protocol_invalid",
                        "gate1_4_validation": gate1_4,
                        "gate5_validation": {
                            "status": "valid",
                            "gate": gate_ref,
                            "kill": kill_ref,
                            "envelope_hash": criteria_validation["envelope_hash"],
                        },
                        "b4_artifact": b4_artifact,
                        "b5_bundle": b5_bundle,
                    }
                freezer_result = existing_protocol
            else:
                freezer_result = ResearchProtocolFreezer().freeze_b6_coverage_bound_protocol(
                    successor_dir=selected_successor_dir,
                    predecessor_manifest_path=repo_root / "data/pit/b3_execution_input_packages" / B3_ID / "manifest.json",
                    coverage_manifest_path=coverage_dir / "manifest.json",
                    coverage_sidecar_path=coverage_dir / "manifest.json.sha256",
                    coverage_by_code_path=coverage_dir / "coverage_by_code.parquet",
                    coverage_by_date_path=coverage_dir / "coverage_by_date.parquet",
                    unavailable_path=coverage_dir / "unavailable_security_dates.parquet",
                    formal_snapshot_dir=formal_snapshot_dir,
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
                    ledger=OOSBudgetLedger(strategy_db),
                    strategy_draft=draft,
                    universe=universe,
                    oos_window_rule_id=scope["split"]["rule_id"],
                    oos_window_start=_parse_date(scope["split"]["oos_start"], "oos_start"),
                    oos_window_end=_parse_date(scope["split"]["oos_end"], "oos_end"),
                    frozen_by=template.authorized_by,
                    backtest_start=_parse_date(scope["execution"]["start"], "backtest_start"),
                    scope_freeze_path=scope_path,
                    gate_criteria_hash=criteria_validation["envelope_hash"],
                    criteria_envelope_schema=CRITERIA_ENVELOPE_V2,
                )
            if isinstance(freezer_result, ProtocolFreezePreflightResult):
                return {
                    **ids,
                    "provenance_validation": validation_payload,
                    "first_missing_prerequisite": f"b6_{freezer_result.reason_code}",
                    "reason": f"hard_block:b6_{freezer_result.reason_code}_missing",
                    "gate1_4_validation": gate1_4,
                    "gate5_validation": {
                        "status": "valid",
                        "gate": gate_ref,
                        "kill": kill_ref,
                        "envelope_hash": criteria_validation["envelope_hash"],
                    },
                    "gate6_7_validation": freezer_result.model_dump(mode="json"),
                    "b4_artifact": b4_artifact,
                    "b5_bundle": b5_bundle,
                    "deferred_missing_prerequisites": ["B4 event backtest"],
                }
            persistence_status = strategy_db.store_protocol_snapshot_exact(freezer_result)
            ids_key = "created_ids" if persistence_status == "created" else "reused_ids"
            ids[ids_key]["protocol"] = freezer_result.protocol_snapshot_id
            if not protocol_exists:
                return {
                    **ids,
                    "provenance_validation": validation_payload,
                    "first_missing_prerequisite": "b6_protocol",
                    "reason": "hard_block:b6_protocol_missing",
                    "gate1_4_validation": gate1_4,
                    "gate5_validation": {
                        "status": "valid",
                        "gate": gate_ref,
                        "kill": kill_ref,
                        "envelope_hash": criteria_validation["envelope_hash"],
                    },
                    "b4_artifact": b4_artifact,
                    "b5_bundle": b5_bundle,
                    "deferred_missing_prerequisites": ["B4 event backtest"],
                }

            task_key = build_b6_task_key(
                strategy_revision_id=draft.strategy_revision_id,
                protocol_snapshot_id=freezer_result.protocol_snapshot_id,
                task_contract_version="v2",
                b5_bundle_id=b5_bundle["bundle_id"],
                b5_bundle_manifest_sha256=b5_bundle["manifest_sha256"],
            )
            task = B6ValidationTask(
                task_id=build_b6_task_id(task_key),
                task_key=task_key,
                task_type="b6_validation",
                task_contract_version="v2",
                strategy_revision_id=draft.strategy_revision_id,
                protocol_snapshot_id=freezer_result.protocol_snapshot_id,
                status="queued",
                created_at=datetime.now(),
                b5_bundle_id=b5_bundle["bundle_id"],
                b5_bundle_manifest_sha256=b5_bundle["manifest_sha256"],
            )
            winner, created = strategy_db.create_or_get_b6_task(task)
            return {
                **ids,
                "provenance_validation": validation_payload,
                "first_missing_prerequisite": None,
                "status": winner.status,
                "reason": "queued:b6_validation_task",
                "b6_task_created": created,
                "b6_task_reused": not created,
                "task_id": winner.task_id,
                "task_key": winner.task_key,
                "task_contract_version": winner.task_contract_version,
                "task_status": winner.status,
                "oos_authorized": False,
                "oos_consumed": False,
                "gate1_4_validation": gate1_4,
                "gate5_validation": {
                    "status": "valid",
                    "gate": gate_ref,
                    "kill": kill_ref,
                    "envelope_hash": criteria_validation["envelope_hash"],
                },
                "b4_artifact": b4_artifact,
                "b5_bundle": b5_bundle,
            }
            return {
                **ids,
                "provenance_validation": validation_payload,
                "first_missing_prerequisite": "b6_validation_task",
                "reason": "hard_block:b6_validation_task_missing",
                "gate1_4_validation": gate1_4,
                "gate5_validation": {
                    "status": "valid",
                    "gate": gate_ref,
                    "kill": kill_ref,
                    "envelope_hash": criteria_validation["envelope_hash"],
                },
                "b4_artifact": b4_artifact,
                "b5_bundle": b5_bundle,
            }
        if gate1_4 is not None:
            return {
                **ids,
                "provenance_validation": validation_payload,
                "first_missing_prerequisite": "b6_criteria",
                "reason": "hard_block:b6_criteria_missing",
                "gate1_4_validation": gate1_4,
                "v3_formal_snapshot": {"id": gate1_4["snapshot_id"], "manifest_sha256": gate1_4["snapshot_manifest_sha256"]},
                "v3_availability_successor": {"id": gate1_4["successor_id"], "manifest_sha256": gate1_4["successor_manifest_sha256"]},
                "deferred_missing_prerequisites": ["B4 event backtest"],
            }
        try:
            strategy_db.get_protocol_snapshot_by_revision_profile(
                draft.strategy_revision_id,
                "b6_coverage_bound",
            )
        except ProtocolSnapshotLookupError as exc:
            if exc.reason_code == "protocol_snapshot_ambiguous":
                return {
                    **ids,
                    "provenance_validation": validation_payload,
                    "first_missing_prerequisite": "b6_protocol",
                    "status": "hard_block:b6_protocol_ambiguous",
                    "reason": "hard_block:b6_protocol_ambiguous",
                    "detail": exc.reason_code,
                    "deferred_missing_prerequisites": ["explicit protocol snapshot ID"],
                }
            return {
                **ids,
                "provenance_validation": validation_payload,
                "first_missing_prerequisite": "b6_protocol",
                "reason": "hard_block:b6_protocol_missing",
                "deferred_missing_prerequisites": ["gate/kill criteria", "B4 event backtest"],
            }
        return {
            **ids,
            "provenance_validation": validation_payload,
            "first_missing_prerequisite": None,
            "reason": None,
        }
    finally:
        strategy_db.close()


def run_once(
    *,
    repo_root: Path,
    db_path: Path,
    audit_path: Path | None = None,
    criteria_root: Path | None = None,
    b4_results_root: Path | None = None,
    b5_bundle_dir: Path | None = None,
    current_snapshot_required: bool = True,
) -> dict:
    repo_root = Path(repo_root).resolve()
    chain = {
        "b3_id": B3_ID,
        "lifecycle_id": LIFECYCLE_ID,
        "liquidity_id": LIQUIDITY_ID,
        "membership_id": MEMBERSHIP_ID,
        "oos_consumed": False,
        "b6_task_created": False,
    }
    b3_artifact = repo_root / "data/pit/b3_execution_input_packages" / B3_ID
    b3 = verify_v3_b3_successor(b3_artifact, repo_root)
    if b3.get("status") != "verified":
        return _save(repo_root, {**chain, "status": "hard_block", "reason": "hard_block:b3_integrity", "b3": b3, "created_ids": {}, "reused_ids": {}}, audit_path)
    b3_manifest_path = b3_artifact / "manifest.json"
    b3_manifest = json.loads(b3_manifest_path.read_text(encoding="utf-8"))
    b3_manifest_hash = _sha256(b3_manifest_path)
    if current_snapshot_required:
        scout = DailyMarketScout(repo_root).scan()
        if scout.get("status") != "ok":
            return _save(repo_root, {**chain, "status": "hard_block", "reason": scout.get("reason", "hard_block:data_stale"), "preflight": scout, "created_ids": {}, "reused_ids": {}}, audit_path)
        chain["current_d"] = scout["as_of_date"]
        chain["current_snapshot_hash"] = scout["snapshot_hash"]

    try:
        materialization = _materialize_and_preflight(
            repo_root=repo_root,
            db_path=Path(db_path),
            b3_manifest=b3_manifest,
            b3_manifest_hash=b3_manifest_hash,
            criteria_root=Path(criteria_root) if criteria_root is not None else repo_root / V3_CRITERIA_ROOT,
            b4_results_root=Path(b4_results_root) if b4_results_root is not None else None,
            b5_bundle_dir=Path(b5_bundle_dir) if b5_bundle_dir is not None else None,
        )
    except ValueError as exc:
        reason = str(exc)
        status = "hard_block:strategy_provenance_conflict" if reason.startswith("strategy provenance conflict:") else "hard_block:strategy_provenance_artifact_invalid"
        return _save(repo_root, {**chain, "status": status, "reason": status, "detail": reason, "created_ids": {}, "reused_ids": {}}, audit_path)

    if materialization["first_missing_prerequisite"] is not None:
        status = materialization.get(
            "status",
            "hard_block:" + materialization["first_missing_prerequisite"] + "_missing",
        )
        return _save(
            repo_root,
            {
                **chain,
                **materialization,
                "status": status,
                "reason": materialization.get("reason", status),
                "created_ids": materialization["created_ids"],
                "reused_ids": materialization["reused_ids"],
            },
            audit_path,
        )
    if (
        materialization.get("first_missing_prerequisite") is None
        and materialization.get("task_id")
        and materialization.get("task_key")
        and materialization.get("b6_task_created") is not None
        and materialization.get("b6_task_reused") is not None
        and materialization.get("status") in {"queued", "running", "blocked", "completed", "failed"}
    ):
        winner_status = materialization["status"]
        return _save(
            repo_root,
            {
                **chain,
                **materialization,
                "status": winner_status,
                "reason": (
                    materialization["reason"]
                    if winner_status == "queued"
                    else f"{winner_status}:b6_validation_task"
                ),
                "created_ids": materialization["created_ids"],
                "reused_ids": materialization["reused_ids"],
            },
            audit_path,
        )
    return _save(repo_root, {**chain, **materialization, "status": "hard_block", "reason": "hard_block:entry_requires_existing_formal_b4_context"}, audit_path)


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    print(json.dumps(run_once(repo_root=root, db_path=root / "data/strategy.db"), sort_keys=True))
