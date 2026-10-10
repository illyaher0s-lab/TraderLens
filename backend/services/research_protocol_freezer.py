"""B3 Research Protocol Freezer - Freeze immutable research protocol snapshot."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

from backend.services.b3_protocol_types import (
    DataSnapshotManifest,
    OOSWindowSpec,
)
from backend.services.oos_budget_ledger import OOSBudgetLedger
from backend.services.oos_window_rules import OOSWindowRuleRegistry
from backend.services.time_consistency_guard import TimeConsistencyGuard
from contracts.strategy import (
    BacktestUniverseSpec,
    FrozenCriteriaReference,
    ProtocolFreezePreflightResult,
    ResearchProtocolSnapshot,
    StrategyDraft,
    StrategyTemplateDefinition,
    compute_b6_protocol_id_from_fields,
)
from scripts.publish_v3_formal_snapshot import TEMPLATE as V3_TEMPLATE
from scripts.verify_v3_availability_bounded_qualification_successor import (
    verify_successor as verify_v3_successor,
)
from scripts.verify_v3_formal_snapshot import verify_formal_snapshot as verify_v3_snapshot
from scripts.verify_v3_historical_coverage import verify_coverage as verify_v3_coverage
from scripts.verify_v2_availability_bounded_qualification_successor import verify_successor
from scripts.verify_v2_formal_snapshot import verify_data_snapshot


CRITERIA_ENVELOPE_V1 = "prototype_gate_v2_criteria_envelope.v1"
CRITERIA_ENVELOPE_V2 = "prototype_gate_v2_criteria_envelope.v2"


def _read_sidecar_hash(path: Path) -> str:
    sidecar = path.with_name(path.name + ".sha256")
    if not sidecar.exists():
        raise ValueError(f"sidecar missing: {sidecar}")
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if sidecar.read_text(encoding="utf-8").split()[0] != actual:
        raise ValueError(f"sidecar mismatch: {path}")
    return actual


def validate_v3_gate_1_4(
    *,
    successor_dir: Path,
    predecessor_manifest_path: Path,
    coverage_manifest_path: Path,
    coverage_sidecar_path: Path,
    coverage_by_code_path: Path,
    coverage_by_date_path: Path,
    unavailable_path: Path,
    formal_snapshot_dir: Path,
    approved_template: StrategyTemplateDefinition,
    scope_freeze_path: Path,
    strategy_draft: StrategyDraft,
) -> dict:
    """Validate only the exact v3 admission inputs for freezer Gates 1-4."""
    successor_dir = Path(successor_dir)
    formal_snapshot_dir = Path(formal_snapshot_dir)
    coverage_manifest_path = Path(coverage_manifest_path)
    scope_freeze_path = Path(scope_freeze_path)
    successor_manifest_path = successor_dir / "manifest.json"
    if not successor_manifest_path.exists():
        raise ValueError(f"Successor manifest not found: {successor_dir}")
    successor_hash = _read_sidecar_hash(successor_manifest_path)
    successor = json.loads(successor_manifest_path.read_text(encoding="utf-8"))
    if successor.get("successor_schema_version") != "v3_availability_bounded_qualification_successor.v1":
        raise ValueError("v3 successor schema mismatch")
    if successor.get("template") != V3_TEMPLATE or successor.get("status") != "availability_bounded_qualified":
        raise ValueError("v3 successor identity or status mismatch")
    if successor.get("authorization_scope") != "b6_coverage_bound" or successor.get(
        "not_authorized_for_b6_oos_gate_promotion_signal_or_data_collection"
    ) is not False:
        raise ValueError("v3 successor authorization mismatch")

    snapshot_manifest_path = formal_snapshot_dir / "manifest.json"
    snapshot_hash = _read_sidecar_hash(snapshot_manifest_path)
    snapshot = json.loads(snapshot_manifest_path.read_text(encoding="utf-8"))
    if successor.get("formal_snapshot", {}).get("manifest_sha256") != snapshot_hash:
        raise ValueError("v3 successor/formal snapshot hash mismatch")
    if successor.get("formal_snapshot", {}).get("semantic_hash") != snapshot.get("semantic_hash"):
        raise ValueError("v3 successor/formal snapshot semantic hash mismatch")

    coverage_manifest_path = coverage_manifest_path.resolve()
    required = (
        Path(predecessor_manifest_path),
        coverage_manifest_path,
        Path(coverage_sidecar_path),
        Path(coverage_by_code_path),
        Path(coverage_by_date_path),
        Path(unavailable_path),
        scope_freeze_path,
    )
    if any(not path.exists() for path in required):
        raise ValueError("v3 Gate 4 artifact unavailable")
    coverage_hash = _read_sidecar_hash(coverage_manifest_path)
    if successor.get("coverage", {}).get("manifest_sha256") != coverage_hash:
        raise ValueError("v3 successor/coverage hash mismatch")
    scope_hash = _read_sidecar_hash(scope_freeze_path)
    if successor.get("scope", {}).get("manifest_sha256") != scope_hash:
        raise ValueError("v3 successor/scope hash mismatch")
    predecessor_hash = hashlib.sha256(Path(predecessor_manifest_path).read_bytes()).hexdigest()
    if successor.get("lineage", {}).get("b3", {}).get("manifest_sha256") != predecessor_hash:
        raise ValueError("v3 successor/B3 predecessor hash mismatch")

    coverage = json.loads(coverage_manifest_path.read_text(encoding="utf-8"))
    stats = coverage.get("coverage", {})
    if coverage.get("template") != V3_TEMPLATE or stats.get("data_fault_count") != 0:
        raise ValueError("v3 coverage identity or data_fault mismatch")
    expected = stats.get("expected_stock_days")
    complete = stats.get("complete_stock_days")
    unavailable = stats.get("unavailable_stock_days")
    if complete + unavailable != expected:
        raise ValueError("v3 coverage arithmetic mismatch")
    if successor.get("coverage", {}).get("stats") != stats:
        raise ValueError("v3 successor/coverage stats mismatch")
    if successor.get("coverage", {}).get("files") != coverage.get("files"):
        raise ValueError("v3 successor/coverage file binding mismatch")
    if (
        strategy_draft.strategy_template_id != V3_TEMPLATE["template_id"]
        or strategy_draft.strategy_template_version != V3_TEMPLATE["template_version"]
        or strategy_draft.strategy_template_hash != V3_TEMPLATE["template_hash"]
        or approved_template.template_id != V3_TEMPLATE["template_id"]
        or approved_template.version != V3_TEMPLATE["template_version"]
        or approved_template.template_hash != V3_TEMPLATE["template_hash"]
        or approved_template.data_requirements_hash != V3_TEMPLATE["data_requirements_hash"]
    ):
        raise ValueError("v3 template binding mismatch")
    if approved_template.governance_status != "approved":
        raise ValueError("v3 template is not approved")

    successor_result = verify_v3_successor(
        successor_dir,
        formal_snapshot_dir=formal_snapshot_dir,
        coverage_dir=coverage_manifest_path.parent,
        scope_dir=scope_freeze_path.parent,
    )
    snapshot_result = verify_v3_snapshot(
        formal_snapshot_dir,
        coverage_dir=coverage_manifest_path.parent,
        scope_dir=scope_freeze_path.parent,
    )
    coverage_result = verify_v3_coverage(coverage_manifest_path.parent, scope_dir=scope_freeze_path.parent)
    if successor_result.get("status") != "valid":
        raise ValueError(f"v3 successor verification failed: {successor_result}")
    if snapshot_result.get("status") != "valid":
        raise ValueError(f"v3 snapshot verification failed: {snapshot_result}")
    if coverage_result.get("status") != "valid":
        raise ValueError(f"v3 coverage verification failed: {coverage_result}")
    return {
        "status": "valid",
        "successor_id": successor["successor_id"],
        "successor_manifest_sha256": successor_hash,
        "snapshot_id": snapshot["snapshot_id"],
        "snapshot_manifest_sha256": snapshot_hash,
        "snapshot_semantic_hash": snapshot["semantic_hash"],
        "coverage_id": coverage["artifact_id"],
        "coverage_manifest_sha256": coverage_hash,
        "coverage_stats": stats,
        "scope_id": coverage["scope_freeze"]["artifact_id"],
        "scope_manifest_sha256": scope_hash,
    }


def _validate_frozen_criteria(
    *,
    gate_reference: FrozenCriteriaReference,
    kill_reference: FrozenCriteriaReference,
    gate_criteria_hash: str,
    criteria_envelope_schema: str = CRITERIA_ENVELOPE_V1,
) -> dict | ProtocolFreezePreflightResult:
    """Recompute Gate 5 content and envelope hashes at the freezer boundary."""
    if criteria_envelope_schema not in {CRITERIA_ENVELOPE_V1, CRITERIA_ENVELOPE_V2}:
        return ProtocolFreezePreflightResult(
            status="validation_unavailable",
            reason_code="criteria_reference_unavailable",
            detail=f"Unsupported criteria envelope schema: {criteria_envelope_schema}",
        )
    if criteria_envelope_schema == CRITERIA_ENVELOPE_V2:
        if not gate_reference.snapshot_id.startswith("prototype_gate_v2_gate_v2_"):
            return ProtocolFreezePreflightResult(
                status="validation_unavailable",
                reason_code="criteria_reference_unavailable",
                detail="v2 envelope requires a v2 Gate snapshot ID",
            )
        if not kill_reference.snapshot_id.startswith("prototype_gate_v2_kill_v2_"):
            return ProtocolFreezePreflightResult(
                status="validation_unavailable",
                reason_code="criteria_reference_unavailable",
                detail="v2 envelope requires a v2 Kill snapshot ID",
            )
    elif (
        gate_reference.snapshot_id.startswith("prototype_gate_v2_gate_v2_")
        or kill_reference.snapshot_id.startswith("prototype_gate_v2_kill_v2_")
    ):
        return ProtocolFreezePreflightResult(
            status="validation_unavailable",
            reason_code="criteria_reference_unavailable",
            detail="v1 envelope cannot bind v2 criteria snapshot IDs",
        )
    references = (("Gate", gate_reference), ("Kill", kill_reference))
    parsed: dict[str, tuple[dict, str]] = {}
    for label, reference in references:
        if not reference.snapshot_id or not reference.snapshot_id.strip():
            return ProtocolFreezePreflightResult(
                status="validation_unavailable",
                reason_code="criteria_reference_unavailable",
                detail=f"{label} snapshot_id empty",
            )
        if not reference.criteria_json or reference.criteria_json.strip() in ("", "{}"):
            return ProtocolFreezePreflightResult(
                status="validation_unavailable",
                reason_code="criteria_reference_unavailable",
                detail=f"{label} criteria_json empty or {{}}",
            )
        try:
            criteria = json.loads(reference.criteria_json)
        except (json.JSONDecodeError, TypeError) as error:
            return ProtocolFreezePreflightResult(
                status="validation_unavailable",
                reason_code="criteria_reference_unavailable",
                detail=f"{label} criteria_json parse error: {error}",
            )
        if not isinstance(criteria, dict) or not criteria:
            return ProtocolFreezePreflightResult(
                status="validation_unavailable",
                reason_code="criteria_reference_unavailable",
                detail=f"{label} criteria_json not a non-empty object",
            )
        canonical = json.dumps(
            criteria,
            ensure_ascii=criteria_envelope_schema != CRITERIA_ENVELOPE_V2,
            sort_keys=True,
            separators=(",", ":"),
        )
        content_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        if content_hash != reference.declared_content_hash:
            return ProtocolFreezePreflightResult(
                status="validation_unavailable",
                reason_code="criteria_content_hash_mismatch",
                detail=f"{label}: computed {content_hash[:16]}... != declared {reference.declared_content_hash[:16]}...",
            )
        parsed[label.lower()] = (criteria, content_hash)

    envelope = {
        "schema_version": criteria_envelope_schema,
        **(
            {"criteria_contract_version": "v2"}
            if criteria_envelope_schema == CRITERIA_ENVELOPE_V2
            else {}
        ),
        "gate_content_hash": parsed["gate"][1],
        "gate_snapshot_id": gate_reference.snapshot_id,
        "kill_content_hash": parsed["kill"][1],
        "kill_snapshot_id": kill_reference.snapshot_id,
    }
    envelope_canonical = json.dumps(
        envelope,
        ensure_ascii=criteria_envelope_schema != CRITERIA_ENVELOPE_V2,
        sort_keys=True,
        separators=(",", ":"),
    )
    envelope_hash = hashlib.sha256(envelope_canonical.encode("utf-8")).hexdigest()
    if gate_criteria_hash != envelope_hash:
        return ProtocolFreezePreflightResult(
            status="validation_unavailable",
            reason_code="criteria_envelope_hash_mismatch",
            detail=f"Supplied {gate_criteria_hash[:16]}... != computed {envelope_hash[:16]}...",
        )
    return {
        "gate": parsed["gate"],
        "kill": parsed["kill"],
        "envelope_hash": envelope_hash,
        "envelope": envelope,
    }


class ResearchProtocolFreezer:
    """
    Freeze immutable research protocol snapshot.
    
    Only freezes after all inputs validated:
    - Valid StrategyDraft
    - Valid BacktestUniverseSpec
    - Point-in-time membership ok or allowed degraded
    - Data snapshot hash exists
    - OOS window generated by registered rule
    - Gate criteria hash exists
    - Strategy config hash exists
    
    No LLM, no DB write, no Gate/report/promotion.
    """
    
    def freeze_protocol(
        self,
        strategy_draft: StrategyDraft,
        universe: BacktestUniverseSpec,
        data_snapshot: DataSnapshotManifest,
        oos_window: OOSWindowSpec,
        gate_criteria_hash: str,
        frozen_by: str,
        backtest_start: __import__("datetime").date,
    ) -> ResearchProtocolSnapshot:
        """
        Freeze research protocol snapshot.
        
        Args:
            strategy_draft: Valid B2 strategy draft
            universe: Valid backtest universe spec
            data_snapshot: Data snapshot manifest with hash
            oos_window: OOS window from registered rule
            gate_criteria_hash: Gate criteria hash
            frozen_by: Agent/user who froze protocol
            backtest_start: Backtest start date for time consistency check
        
        Returns:
            Immutable ResearchProtocolSnapshot
        
        Raises:
            ValueError: If any validation fails
        """
        # Validate strategy_config_hash
        if not strategy_draft.strategy_config_json or strategy_draft.strategy_config_json.strip() == "":
            raise ValueError("Missing strategy_config. Cannot freeze protocol.")
        
        strategy_config_hash = self._compute_config_hash(strategy_draft.strategy_config_json)
        
        # ponytail: manifest uses semantic_hash
        if not data_snapshot.semantic_hash or data_snapshot.semantic_hash.strip() == "":
            raise ValueError("Missing semantic_hash. Cannot freeze protocol.")
        
        # Validate gate_criteria_hash
        if not gate_criteria_hash or gate_criteria_hash.strip() == "":
            raise ValueError("Missing gate_criteria_hash. Cannot freeze protocol.")
        
        # Validate OOS window rule is registered
        registry = OOSWindowRuleRegistry()
        if oos_window.oos_window_rule_id not in registry.REGISTERED_RULES:
            raise ValueError(
                f"OOS window rule '{oos_window.oos_window_rule_id}' is not registered. "
                "User/LLM-supplied OOS dates rejected."
            )
        
        # Validate data snapshot quality
        if data_snapshot.quality_status == "insufficient":
            raise ValueError(
                "Data snapshot quality is insufficient. Cannot freeze protocol with insufficient data."
            )
        
        # Validate universe quality
        if universe.quality_status == "insufficient":
            raise ValueError(
                "Universe quality is insufficient. Cannot freeze protocol with contaminated universe."
            )
        
        # Time consistency validation (P0-1: must integrate guard)
        guard = TimeConsistencyGuard()
        
        # Check universe snapshot time consistency
        universe_check = guard.validate_universe_snapshot(
            snapshot_date=universe.snapshot_date,
            backtest_start=backtest_start,
            universe_type=universe.universe_rule_type,
        )
        
        if universe_check.status == "fail":
            raise ValueError(
                f"Time consistency violation: {'; '.join(universe_check.blocking_violations)}"
            )
        
        # Check universe source type
        source_check = guard.validate_universe_source(
            source_type=universe.membership_source,
            source_snapshot_date=universe.snapshot_date,
            backtest_start=backtest_start,
        )
        
        if source_check.status == "fail":
            raise ValueError(
                f"Universe source violation: {'; '.join(source_check.blocking_violations)}"
            )
        
        # Compute shared_oos_window_id (deterministic)
        shared_oos_window_id = self._compute_shared_oos_window_id(
            oos_window.oos_window_rule_id,
            oos_window.oos_window_start,
            oos_window.oos_window_end,
        )
        
        # Generate protocol_snapshot_id (legacy)
        protocol_snapshot_id = self._generate_protocol_snapshot_id(
            strategy_draft.strategy_revision_id,
            data_snapshot.snapshot_id,  # ponytail: manifest field
        )
        
        # Freeze protocol snapshot
        return ResearchProtocolSnapshot(
            protocol_snapshot_id=protocol_snapshot_id,
            theme_id=strategy_draft.theme_id,
            hypothesis_source_snapshot_id=strategy_draft.hypothesis_source_snapshot_id,
            strategy_revision_id=strategy_draft.strategy_revision_id,
            sample_split_rule_id=strategy_draft.sample_split_rule_id,
            oos_window_rule_id=oos_window.oos_window_rule_id,
            oos_window_rule_params_json="{}",  # V1: no params
            oos_window_start=oos_window.oos_window_start,
            oos_window_end=oos_window.oos_window_end,
            shared_oos_window_id=shared_oos_window_id,
            backtest_universe_spec_id=strategy_draft.backtest_universe_spec_id,
            data_snapshot_id=data_snapshot.snapshot_id,  # ponytail: manifest field
            kill_criteria_snapshot_id="",  # V1: not implemented
            prototype_gate_thresholds_json="{}",  # V1: placeholder
            strategy_config_hash=strategy_config_hash,
            data_snapshot_hash=data_snapshot.semantic_hash,  # ponytail: manifest field
            gate_criteria_hash=gate_criteria_hash,
            frozen_at=datetime.now(),
            frozen_by=frozen_by,
        )
    
    def _compute_config_hash(self, config_json: str) -> str:
        """Compute hash from strategy config JSON."""
        return hashlib.sha256(config_json.encode("utf-8")).hexdigest()
    
    def _compute_shared_oos_window_id(
        self,
        rule_id: str,
        oos_start: __import__("datetime").date,
        oos_end: __import__("datetime").date,
    ) -> str:
        """Compute deterministic shared_oos_window_id."""
        fingerprint = {
            "rule_id": rule_id,
            "oos_start": str(oos_start),
            "oos_end": str(oos_end),
        }
        serialized = json.dumps(fingerprint, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]
    
    def _generate_protocol_snapshot_id(
        self,
        strategy_revision_id: str,
        snapshot_id: str,
    ) -> str:
        """Generate protocol_snapshot_id from inputs. ponytail: legacy B3 only."""
        return f"protocol_{strategy_revision_id}_{snapshot_id}"
    
    def freeze_b6_coverage_bound_protocol(
        self,
        *,
        successor_dir: Path,
        predecessor_manifest_path: Path,
        coverage_manifest_path: Path,
        coverage_sidecar_path: Path,
        coverage_by_code_path: Path,
        coverage_by_date_path: Path,
        unavailable_path: Path,
        formal_snapshot_dir: Path,
        approved_template: StrategyTemplateDefinition,
        gate_reference: FrozenCriteriaReference,
        kill_reference: FrozenCriteriaReference,
        ledger: OOSBudgetLedger,
        strategy_draft: StrategyDraft,
        universe: BacktestUniverseSpec,
        oos_window_rule_id: str,
        oos_window_start: __import__("datetime").date,
        oos_window_end: __import__("datetime").date,
        frozen_by: str,
        backtest_start: __import__("datetime").date,
        scope_freeze_path: Path,
        gate_criteria_hash: str,
        criteria_envelope_schema: str = CRITERIA_ENVELOPE_V1,
    ) -> ResearchProtocolSnapshot | ProtocolFreezePreflightResult:
        """
        B6 coverage-bound protocol freeze with 7 hard gates.
        
        Returns typed unavailable on missing/invalid prerequisites.
        Returns frozen protocol only when all gates pass.
        Never writes protocol, ledger, reservation, or audit.
        
        Order: successor → snapshot → template → artifact → criteria → ledger → safety.
        """
        successor_manifest_path = Path(successor_dir) / "manifest.json"
        successor_probe = None
        if successor_manifest_path.exists():
            try:
                successor_probe = json.loads(successor_manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                successor_probe = None
            if successor_probe is not None and successor_probe.get("successor_schema_version") == "v3_availability_bounded_qualification_successor.v1":
                try:
                    v3_admission = validate_v3_gate_1_4(
                        successor_dir=successor_dir,
                        predecessor_manifest_path=predecessor_manifest_path,
                        coverage_manifest_path=coverage_manifest_path,
                        coverage_sidecar_path=coverage_sidecar_path,
                        coverage_by_code_path=coverage_by_code_path,
                        coverage_by_date_path=coverage_by_date_path,
                        unavailable_path=unavailable_path,
                        formal_snapshot_dir=formal_snapshot_dir,
                        approved_template=approved_template,
                        scope_freeze_path=scope_freeze_path,
                        strategy_draft=strategy_draft,
                    )
                except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
                    raise ValueError(f"v3 Gate 1-4 verification failed: {error}") from error
                if not gate_reference.snapshot_id or gate_reference.snapshot_id.strip() == "":
                    return ProtocolFreezePreflightResult(
                        status="validation_unavailable",
                        reason_code="criteria_reference_unavailable",
                        detail="Gate snapshot_id empty",
                    )
                if not gate_reference.criteria_json or gate_reference.criteria_json.strip() in ("", "{}"):
                    return ProtocolFreezePreflightResult(
                        status="validation_unavailable",
                        reason_code="criteria_reference_unavailable",
                        detail="Gate criteria_json empty or {}",
                    )
                if not kill_reference.snapshot_id or kill_reference.snapshot_id.strip() == "":
                    return ProtocolFreezePreflightResult(
                        status="validation_unavailable",
                        reason_code="criteria_reference_unavailable",
                        detail="Kill snapshot_id empty",
                    )
                if not kill_reference.criteria_json or kill_reference.criteria_json.strip() in ("", "{}"): 
                    return ProtocolFreezePreflightResult(
                        status="validation_unavailable",
                        reason_code="criteria_reference_unavailable",
                        detail="Kill criteria_json empty or {}",
                    )

                criteria = _validate_frozen_criteria(
                    gate_reference=gate_reference,
                    kill_reference=kill_reference,
                    gate_criteria_hash=gate_criteria_hash,
                    criteria_envelope_schema=criteria_envelope_schema,
                )
                if isinstance(criteria, ProtocolFreezePreflightResult):
                    return criteria
                gate_canonical = json.dumps(criteria["gate"][0], sort_keys=True, separators=(",", ":"))
                kill_content_hash = criteria["kill"][1]

                # Gate 6 is deliberately read-only.  A file-backed ledger is the
                # durable owner; an empty database reports available/draw 1 without
                # creating budget state.
                main_path = ledger.db.conn.execute("PRAGMA database_list").fetchone()[2]
                if not main_path or not main_path.strip():
                    return ProtocolFreezePreflightResult(
                        status="validation_unavailable",
                        reason_code="ledger_owner_unavailable",
                        detail="Ledger is :memory:, not file-backed",
                    )
                try:
                    state = ledger.get_ledger_state(
                        theme_id=strategy_draft.theme_id,
                        hypothesis_source_snapshot_id=strategy_draft.hypothesis_source_snapshot_id,
                    )
                except Exception as error:
                    return ProtocolFreezePreflightResult(
                        status="validation_unavailable",
                        reason_code="ledger_owner_unavailable",
                        detail=f"Ledger state read error: {error}",
                    )
                if state["active_reservation_id"] is not None:
                    return ProtocolFreezePreflightResult(
                        status="validation_unavailable",
                        reason_code="ledger_active_reservation",
                        detail=f"Active reservation: {state['active_reservation_id']}",
                    )
                if state["budget_status"] != "available":
                    return ProtocolFreezePreflightResult(
                        status="validation_unavailable",
                        reason_code="ledger_budget_exhausted",
                        detail=f"Budget status: {state['budget_status']}",
                    )

                # Gate 7 uses only the immutable v3 scope contract for dates and
                # split identity.  In a PIT universe, the publication timestamp is
                # not the historical boundary; the effective interval is.
                try:
                    scope = json.loads(Path(scope_freeze_path).read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as error:
                    raise ValueError(f"v3 scope verification failed: {error}") from error
                if (
                    scope.get("schema_version") != "v3_historical_scope_freeze.v1"
                    or scope.get("artifact_id") != successor_probe.get("scope", {}).get("artifact_id")
                    or scope.get("frozen") is not True
                    or scope.get("status") != "published"
                    or scope.get("template") != V3_TEMPLATE
                ):
                    return ProtocolFreezePreflightResult(
                        status="validation_unavailable",
                        reason_code="split_or_time_consistency_invalid",
                        detail="v3 scope identity or publication state mismatch",
                    )
                try:
                    snapshot = json.loads(
                        (Path(formal_snapshot_dir) / "manifest.json").read_text(encoding="utf-8")
                    )
                except (OSError, json.JSONDecodeError) as error:
                    raise ValueError(f"v3 snapshot verification failed: {error}") from error
                split = scope.get("split", {})
                if (
                    split.get("rule_id") != oos_window_rule_id
                    or str(split.get("oos_start", "")).replace("-", "") != oos_window_start.strftime("%Y%m%d")
                    or str(split.get("oos_end", "")).replace("-", "") != oos_window_end.strftime("%Y%m%d")
                    or split.get("oos_consumed") is not False
                    or str(scope.get("execution", {}).get("start", "")).replace("-", "") != backtest_start.strftime("%Y%m%d")
                ):
                    return ProtocolFreezePreflightResult(
                        status="validation_unavailable",
                        reason_code="split_or_time_consistency_invalid",
                        detail="OOS split/window/backtest start is not the frozen v3 scope",
                    )
                if (
                    strategy_draft.sample_split_rule_id != split.get("rule_id")
                    or universe.universe_rule_type not in approved_template.supported_universe_rule_types
                    or universe.quality_status != "ok"
                    or snapshot.get("quality_status") != "ok"
                    or snapshot.get("authorization_scope") != "b6_coverage_bound"
                    or snapshot.get("not_authorized_for_b6_oos_gate_promotion_signal") is not False
                ):
                    return ProtocolFreezePreflightResult(
                        status="validation_unavailable",
                        reason_code="split_or_time_consistency_invalid",
                        detail="v3 template, universe, snapshot quality, or authorization binding is invalid",
                    )
                if oos_window_rule_id not in OOSWindowRuleRegistry.REGISTERED_RULES:
                    return ProtocolFreezePreflightResult(
                        status="validation_unavailable",
                        reason_code="split_or_time_consistency_invalid",
                        detail=f"OOS rule is not registered: {oos_window_rule_id}",
                    )
                guard = TimeConsistencyGuard()
                universe_check = guard.validate_universe_snapshot(
                    snapshot_date=universe.snapshot_date,
                    backtest_start=backtest_start,
                    universe_type=universe.universe_rule_type,
                    historical_effective_from=universe.membership_effective_from,
                    historical_effective_to=universe.membership_effective_to,
                )
                if universe_check.status == "fail":
                    return ProtocolFreezePreflightResult(
                        status="validation_unavailable",
                        reason_code="split_or_time_consistency_invalid",
                        detail=f"Time consistency: {'; '.join(universe_check.blocking_violations)}",
                    )
                source_check = guard.validate_universe_source(
                    source_type=universe.membership_source,
                    source_snapshot_date=universe.snapshot_date,
                    backtest_start=backtest_start,
                    historical_effective_from=universe.membership_effective_from,
                    historical_effective_to=universe.membership_effective_to,
                )
                if source_check.status == "fail":
                    return ProtocolFreezePreflightResult(
                        status="validation_unavailable",
                        reason_code="split_or_time_consistency_invalid",
                        detail=f"Universe source: {'; '.join(source_check.blocking_violations)}",
                    )

                coverage = json.loads(Path(coverage_manifest_path).read_text(encoding="utf-8"))
                coverage_stats = coverage.get("coverage", {})
                expected = coverage_stats.get("expected_stock_days")
                complete = coverage_stats.get("complete_stock_days")
                unavailable = coverage_stats.get("unavailable_stock_days")
                coverage_algorithm_hash = coverage.get("liquidity_algorithm", {}).get("algorithm_hash", "")
                if not coverage_algorithm_hash:
                    raise ValueError("v3 coverage algorithm hash missing")
                successor_id = v3_admission["successor_id"]
                successor_hash = v3_admission["successor_manifest_sha256"]
                snapshot_id = v3_admission["snapshot_id"]
                semantic_hash = v3_admission["snapshot_semantic_hash"]
                scope_hash = v3_admission["scope_manifest_sha256"]
                strategy_config_hash = self._compute_config_hash(strategy_draft.strategy_config_json)
                shared_oos_window_id = self._compute_shared_oos_window_id(
                    oos_window_rule_id, oos_window_start, oos_window_end
                )
                protocol_fields = {
                    "protocol_profile": "b6_coverage_bound",
                    "strategy_revision_id": strategy_draft.strategy_revision_id,
                    "theme_id": strategy_draft.theme_id,
                    "hypothesis_source_snapshot_id": strategy_draft.hypothesis_source_snapshot_id,
                    "backtest_universe_spec_id": strategy_draft.backtest_universe_spec_id,
                    "data_snapshot_id": snapshot_id,
                    "data_snapshot_hash": semantic_hash,
                    "sample_split_rule_id": strategy_draft.sample_split_rule_id,
                    "oos_window_rule_id": oos_window_rule_id,
                    "oos_window_rule_params_json": "{}",
                    "oos_window_start": oos_window_start,
                    "oos_window_end": oos_window_end,
                    "shared_oos_window_id": shared_oos_window_id,
                    "kill_criteria_snapshot_id": kill_reference.snapshot_id,
                    "prototype_gate_thresholds_json": gate_canonical,
                    "gate_criteria_hash": criteria["envelope_hash"],
                    "strategy_config_hash": strategy_config_hash,
                    "availability_successor_id": successor_id,
                    "availability_successor_manifest_hash": successor_hash,
                    "availability_successor_algorithm_hash": successor_probe["coverage"]["algorithm_hash"],
                    "predecessor_qualification_id": v3_admission["coverage_id"],
                    "predecessor_qualification_manifest_hash": v3_admission["coverage_manifest_sha256"],
                    "predecessor_qualification_status": successor_probe["status"],
                    "predecessor_qualification_algorithm_hash": coverage_algorithm_hash,
                    "coverage_package_id": v3_admission["coverage_id"],
                    "coverage_manifest_hash": v3_admission["coverage_manifest_sha256"],
                    "coverage_algorithm_hash": coverage_algorithm_hash,
                    "source_scope_hash": scope_hash,
                    "data_requirements_hash": approved_template.data_requirements_hash,
                    "expected_stock_days": expected,
                    "complete_stock_days": complete,
                    "unavailable_stock_days": unavailable,
                    "gate_snapshot_id": gate_reference.snapshot_id,
                    "gate_content_hash": criteria["gate"][1],
                    "kill_content_hash": kill_content_hash,
                }
                protocol_id = compute_b6_protocol_id_from_fields(**protocol_fields)
                return ResearchProtocolSnapshot(
                    protocol_snapshot_id=protocol_id,
                    protocol_profile="b6_coverage_bound",
                    theme_id=strategy_draft.theme_id,
                    hypothesis_source_snapshot_id=strategy_draft.hypothesis_source_snapshot_id,
                    strategy_revision_id=strategy_draft.strategy_revision_id,
                    sample_split_rule_id=strategy_draft.sample_split_rule_id,
                    oos_window_rule_id=oos_window_rule_id,
                    oos_window_rule_params_json="{}",
                    oos_window_start=oos_window_start,
                    oos_window_end=oos_window_end,
                    shared_oos_window_id=shared_oos_window_id,
                    backtest_universe_spec_id=strategy_draft.backtest_universe_spec_id,
                    data_snapshot_id=snapshot_id,
                    kill_criteria_snapshot_id=kill_reference.snapshot_id,
                    prototype_gate_thresholds_json=gate_canonical,
                    strategy_config_hash=strategy_config_hash,
                    data_snapshot_hash=semantic_hash,
                    gate_criteria_hash=criteria["envelope_hash"],
                    # The v3 protocol is replayed from immutable scope inputs;
                    # keep its full payload deterministic so exact persistence
                    # can reuse the same ID without a timestamp conflict.
                    frozen_at=datetime.combine(oos_window_end, datetime.min.time()),
                    frozen_by=frozen_by,
                    availability_successor_id=successor_id,
                    availability_successor_manifest_hash=successor_hash,
                    availability_successor_algorithm_hash=successor_probe["coverage"]["algorithm_hash"],
                    predecessor_qualification_id=v3_admission["coverage_id"],
                    predecessor_qualification_manifest_hash=v3_admission["coverage_manifest_sha256"],
                    predecessor_qualification_status=successor_probe["status"],
                    predecessor_qualification_algorithm_hash=coverage_algorithm_hash,
                    coverage_package_id=v3_admission["coverage_id"],
                    coverage_manifest_hash=v3_admission["coverage_manifest_sha256"],
                    coverage_algorithm_hash=coverage_algorithm_hash,
                    source_scope_hash=scope_hash,
                    data_requirements_hash=approved_template.data_requirements_hash,
                    expected_stock_days=expected,
                    complete_stock_days=complete,
                    unavailable_stock_days=unavailable,
                    gate_snapshot_id=gate_reference.snapshot_id,
                    gate_content_hash=criteria["gate"][1],
                    kill_content_hash=kill_content_hash,
                )

        # Gate 1: Availability-bounded qualification successor
        successor_manifest_path = successor_dir / "manifest.json"
        if not successor_manifest_path.exists():
            return ProtocolFreezePreflightResult(
                status="validation_unavailable",
                reason_code="availability_qualification_unavailable",
                detail=f"Successor manifest not found: {successor_dir}",
            )
        
        try:
            successor = json.loads(successor_manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"Successor verification failed: {error}") from error
        
        if successor.get("status") != "availability_bounded_qualified":
            return ProtocolFreezePreflightResult(
                status="validation_unavailable",
                reason_code="availability_qualification_unavailable",
                detail=f"Successor status: {successor.get('status')}",
            )
        
        successor_id = successor.get("successor_id", "")
        successor_sidecar = successor_dir / "manifest.json.sha256"
        if not successor_sidecar.exists():
            return ProtocolFreezePreflightResult(
                status="validation_unavailable",
                reason_code="availability_successor_binding_invalid",
                detail="Successor sidecar missing",
            )
        
        successor_hash = hashlib.sha256(successor_manifest_path.read_bytes()).hexdigest()
        if successor_sidecar.read_text(encoding="utf-8").strip() != successor_hash:
            raise ValueError("Successor verification failed: sidecar mismatch")
        
        # Gate 2: Formal DataSnapshotManifest
        formal_snapshot_manifest_path = formal_snapshot_dir / "manifest.json"
        formal_snapshot_sidecar_path = formal_snapshot_dir / "manifest.json.sha256"
        if not formal_snapshot_manifest_path.exists() or not formal_snapshot_sidecar_path.exists():
            return ProtocolFreezePreflightResult(
                status="validation_unavailable",
                reason_code="snapshot_manifest_unavailable",
                detail="Formal snapshot manifest not found",
            )
        
        try:
            snapshot = json.loads(formal_snapshot_manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"Snapshot verification failed: {error}") from error
        
        snapshot_id = snapshot.get("snapshot_id", "")
        if not snapshot_id or snapshot_id.strip() == "":
            return ProtocolFreezePreflightResult(
                status="validation_unavailable",
                reason_code="snapshot_manifest_unavailable",
                detail="snapshot_id is empty",
            )
        
        semantic_hash = snapshot.get("semantic_hash", "")
        pred_snapshot_hash = successor.get("predecessor_snapshot_hash", "")
        
        if semantic_hash != pred_snapshot_hash:
            return ProtocolFreezePreflightResult(
                status="validation_unavailable",
                reason_code="snapshot_manifest_unavailable",
                detail="semantic_hash mismatch with qualification",
            )

        try:
            data_snapshot = DataSnapshotManifest.model_validate(snapshot)
        except Exception as error:
            raise ValueError(f"Snapshot verification failed: {error}") from error
        
        # Gate 3: Approved template governance
        if approved_template.governance_status != "approved":
            return ProtocolFreezePreflightResult(
                status="validation_unavailable",
                reason_code="template_not_approved",
                detail=f"Template status: {approved_template.governance_status}",
            )

        if (
            strategy_draft.strategy_template_id != approved_template.template_id
            or strategy_draft.strategy_template_version != approved_template.version
            or strategy_draft.strategy_template_hash != approved_template.template_hash
            or successor.get("template_id") != approved_template.template_id
            or successor.get("template_version") != approved_template.version
            or successor.get("template_hash") != approved_template.template_hash
        ):
            return ProtocolFreezePreflightResult(
                status="validation_unavailable",
                reason_code="template_binding_mismatch",
                detail="Draft, approved template, and successor identity do not match",
            )
        
        pred_template_hash = successor.get("predecessor_template_hash", "")
        cov_template_hash = successor.get("coverage_template_hash", "")
        
        if approved_template.template_hash != pred_template_hash:
            return ProtocolFreezePreflightResult(
                status="validation_unavailable",
                reason_code="template_binding_mismatch",
                detail=f"Template hash {approved_template.template_hash[:16]}... != predecessor {pred_template_hash[:16]}...",
            )
        
        if approved_template.template_hash != cov_template_hash:
            return ProtocolFreezePreflightResult(
                status="validation_unavailable",
                reason_code="template_binding_mismatch",
                detail=f"Template hash {approved_template.template_hash[:16]}... != coverage {cov_template_hash[:16]}...",
            )
        
        # Gate 4: Artifact binding
        required_artifacts = (
            predecessor_manifest_path,
            coverage_manifest_path,
            coverage_sidecar_path,
            coverage_by_code_path,
            coverage_by_date_path,
            unavailable_path,
            scope_freeze_path,
        )
        if any(not path.exists() for path in required_artifacts):
            return ProtocolFreezePreflightResult(
                status="validation_unavailable",
                reason_code="artifact_binding_mismatch",
                detail="One or more explicitly bound artifacts are unavailable",
            )
        
        coverage_hash = hashlib.sha256(coverage_manifest_path.read_bytes()).hexdigest()
        if coverage_sidecar_path.read_text(encoding="utf-8").strip() != coverage_hash:
            raise ValueError("Coverage verification failed: sidecar mismatch")
        
        try:
            coverage = json.loads(coverage_manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"Coverage verification failed: {error}") from error
        
        if coverage.get("build_completion", {}).get("structural_validation") != "passed":
            return ProtocolFreezePreflightResult(
                status="validation_unavailable",
                reason_code="artifact_binding_mismatch",
                detail="Coverage structural_validation not passed",
            )
        
        expected = coverage.get("expected_stock_days", 0)
        complete = coverage.get("complete_stock_days", 0)
        unavailable = coverage.get("unavailable_stock_days", 0)
        
        if complete + unavailable != expected:
            return ProtocolFreezePreflightResult(
                status="validation_unavailable",
                reason_code="artifact_binding_mismatch",
                detail=f"Coverage arithmetic: {complete} + {unavailable} != {expected}",
            )

        predecessor_hash = hashlib.sha256(predecessor_manifest_path.read_bytes()).hexdigest()
        if successor.get("predecessor_manifest_sha256") != predecessor_hash:
            raise ValueError("Successor verification failed: predecessor hash claim mismatch")
        if successor.get("coverage_manifest_sha256") != coverage_hash:
            raise ValueError("Successor verification failed: coverage hash claim mismatch")
        scope_hash = hashlib.sha256(scope_freeze_path.read_bytes()).hexdigest()
        if successor.get("scope_freeze_sha256") != scope_hash:
            raise ValueError("Successor verification failed: scope hash claim mismatch")

        if (
            approved_template.data_requirements_hash != successor.get("predecessor_data_requirements_hash")
            or approved_template.data_requirements_hash != coverage.get("input_data_requirements_hash")
        ):
            return ProtocolFreezePreflightResult(
                status="validation_unavailable",
                reason_code="template_binding_mismatch",
                detail="Template data requirements do not match qualification and coverage",
            )
        if (
            successor.get("coverage_package_id") != coverage.get("coverage_hash")
            or successor.get("predecessor_qualification_package_id")
            != coverage.get("input_qualification_package_id")
            or successor.get("predecessor_scope_hash") != coverage.get("input_scope_hash")
            or successor.get("predecessor_snapshot_hash") != coverage.get("input_snapshot_hash")
            or semantic_hash != coverage.get("input_snapshot_hash")
            or successor.get("coverage_algorithm_hash") != coverage.get("algorithm_hash")
        ):
            return ProtocolFreezePreflightResult(
                status="validation_unavailable",
                reason_code="artifact_binding_mismatch",
                detail="Successor, coverage, predecessor, and snapshot bindings do not match",
            )

        successor_verification = verify_successor(
            successor_dir,
            predecessor_manifest_path=predecessor_manifest_path,
            coverage_manifest_path=coverage_manifest_path,
            coverage_sidecar_path=coverage_sidecar_path,
            coverage_by_code_path=coverage_by_code_path,
            coverage_by_date_path=coverage_by_date_path,
            unavailable_path=unavailable_path,
            scope_freeze_path=scope_freeze_path,
        )
        if successor_verification.get("status") != "valid":
            raise ValueError(
                "Successor verification failed: "
                + str(successor_verification.get("reason", "unknown verifier error"))
            )

        snapshot_verification = verify_data_snapshot(formal_snapshot_dir, semantic_hash)
        if snapshot_verification.get("status") != "valid":
            raise ValueError(
                "Snapshot verification failed: "
                + str(snapshot_verification.get("reason", "unknown verifier error"))
            )
        
        # Gate 5: Frozen criteria
        if not gate_reference.snapshot_id or gate_reference.snapshot_id.strip() == "":
            return ProtocolFreezePreflightResult(
                status="validation_unavailable",
                reason_code="criteria_reference_unavailable",
                detail="Gate snapshot_id empty",
            )
        
        if not gate_reference.criteria_json or gate_reference.criteria_json.strip() in ("", "{}"):
            return ProtocolFreezePreflightResult(
                status="validation_unavailable",
                reason_code="criteria_reference_unavailable",
                detail="Gate criteria_json empty or {}",
            )
        
        if not kill_reference.snapshot_id or kill_reference.snapshot_id.strip() == "":
            return ProtocolFreezePreflightResult(
                status="validation_unavailable",
                reason_code="criteria_reference_unavailable",
                detail="Kill snapshot_id empty",
            )
        
        if not kill_reference.criteria_json or kill_reference.criteria_json.strip() in ("", "{}"):
            return ProtocolFreezePreflightResult(
                status="validation_unavailable",
                reason_code="criteria_reference_unavailable",
                detail="Kill criteria_json empty or {}",
            )
        
        # Recompute canonical criteria hashes
        try:
            gate_obj = json.loads(gate_reference.criteria_json)
            if not gate_obj or not isinstance(gate_obj, dict):
                return ProtocolFreezePreflightResult(
                    status="validation_unavailable",
                    reason_code="criteria_reference_unavailable",
                    detail="Gate criteria_json not a non-empty object",
                )
            gate_canonical = json.dumps(gate_obj, sort_keys=True, separators=(",", ":"))
            gate_content_hash = hashlib.sha256(gate_canonical.encode("utf-8")).hexdigest()
        except (json.JSONDecodeError, TypeError) as e:
            return ProtocolFreezePreflightResult(
                status="validation_unavailable",
                reason_code="criteria_reference_unavailable",
                detail=f"Gate criteria_json parse error: {e}",
            )
        
        if gate_content_hash != gate_reference.declared_content_hash:
            return ProtocolFreezePreflightResult(
                status="validation_unavailable",
                reason_code="criteria_content_hash_mismatch",
                detail=f"Gate: computed {gate_content_hash[:16]}... != declared {gate_reference.declared_content_hash[:16]}...",
            )
        
        try:
            kill_obj = json.loads(kill_reference.criteria_json)
            if not kill_obj or not isinstance(kill_obj, dict):
                return ProtocolFreezePreflightResult(
                    status="validation_unavailable",
                    reason_code="criteria_reference_unavailable",
                    detail="Kill criteria_json not a non-empty object",
                )
            kill_canonical = json.dumps(kill_obj, sort_keys=True, separators=(",", ":"))
            kill_content_hash = hashlib.sha256(kill_canonical.encode("utf-8")).hexdigest()
        except (json.JSONDecodeError, TypeError) as e:
            return ProtocolFreezePreflightResult(
                status="validation_unavailable",
                reason_code="criteria_reference_unavailable",
                detail=f"Kill criteria_json parse error: {e}",
            )
        
        if kill_content_hash != kill_reference.declared_content_hash:
            return ProtocolFreezePreflightResult(
                status="validation_unavailable",
                reason_code="criteria_content_hash_mismatch",
                detail=f"Kill: computed {kill_content_hash[:16]}... != declared {kill_reference.declared_content_hash[:16]}...",
            )
        
        # Compute envelope hash
        envelope = {
            "gate_content_hash": gate_content_hash,
            "gate_snapshot_id": gate_reference.snapshot_id,
            "kill_content_hash": kill_content_hash,
            "kill_snapshot_id": kill_reference.snapshot_id,
        }
        envelope_canonical = json.dumps(envelope, sort_keys=True, separators=(",", ":"))
        computed_envelope_hash = hashlib.sha256(envelope_canonical.encode("utf-8")).hexdigest()
        
        # ponytail: compare supplied hash with computed envelope
        if gate_criteria_hash != computed_envelope_hash:
            return ProtocolFreezePreflightResult(
                status="validation_unavailable",
                reason_code="criteria_envelope_hash_mismatch",
                detail=f"Supplied {gate_criteria_hash[:16]}... != computed {computed_envelope_hash[:16]}...",
            )
        
        # Gate 6: Read-only durable budget
        # ponytail: :memory: DB has empty main path
        main_path = ledger.db.conn.execute("PRAGMA database_list").fetchone()[2]
        if not main_path or not main_path.strip():
            return ProtocolFreezePreflightResult(
                status="validation_unavailable",
                reason_code="ledger_owner_unavailable",
                detail="Ledger is :memory:, not file-backed",
            )
        
        try:
            state = ledger.get_ledger_state(
                theme_id=strategy_draft.theme_id,
                hypothesis_source_snapshot_id=strategy_draft.hypothesis_source_snapshot_id,
            )
        except Exception as e:
            return ProtocolFreezePreflightResult(
                status="validation_unavailable",
                reason_code="ledger_owner_unavailable",
                detail=f"Ledger state read error: {e}",
            )
        
        if state["active_reservation_id"] is not None:
            return ProtocolFreezePreflightResult(
                status="validation_unavailable",
                reason_code="ledger_active_reservation",
                detail=f"Active reservation: {state['active_reservation_id']}",
            )
        
        if state["budget_status"] != "available":
            return ProtocolFreezePreflightResult(
                status="validation_unavailable",
                reason_code="ledger_budget_exhausted",
                detail=f"Budget status: {state['budget_status']}",
            )
        
        # Gate 7: Existing safety checks
        oos_registry = OOSWindowRuleRegistry()
        if (
            oos_window_rule_id not in oos_registry.REGISTERED_RULES
            or strategy_draft.sample_split_rule_id not in approved_template.sample_split_rule_ids
            or strategy_draft.backtest_universe_spec_id != universe.universe_spec_id
            or universe.universe_rule_type not in approved_template.supported_universe_rule_types
            or universe.quality_status != "ok"
            or data_snapshot.quality_status != "ok"
            or oos_window_start > oos_window_end
            or oos_window_start < data_snapshot.market_data_start
            or oos_window_end > data_snapshot.market_data_end
        ):
            return ProtocolFreezePreflightResult(
                status="validation_unavailable",
                reason_code="split_or_time_consistency_invalid",
                detail="OOS rule, split, universe, quality, or window binding is invalid",
            )
        
        guard = TimeConsistencyGuard()
        universe_check = guard.validate_universe_snapshot(
            snapshot_date=universe.snapshot_date,
            backtest_start=backtest_start,
            universe_type=universe.universe_rule_type,
        )
        if universe_check.status == "fail":
            return ProtocolFreezePreflightResult(
                status="validation_unavailable",
                reason_code="split_or_time_consistency_invalid",
                detail=f"Time consistency: {'; '.join(universe_check.blocking_violations)}",
            )

        source_check = guard.validate_universe_source(
            source_type=universe.membership_source,
            source_snapshot_date=universe.snapshot_date,
            backtest_start=backtest_start,
        )
        if source_check.status == "fail":
            return ProtocolFreezePreflightResult(
                status="validation_unavailable",
                reason_code="split_or_time_consistency_invalid",
                detail=f"Universe source: {'; '.join(source_check.blocking_violations)}",
            )
        
        # All gates passed - compute ID from raw fields first
        strategy_config_hash = self._compute_config_hash(strategy_draft.strategy_config_json)
        shared_oos_window_id = self._compute_shared_oos_window_id(oos_window_rule_id, oos_window_start, oos_window_end)
        
        # ponytail: compute ID before construction to avoid validator loop
        protocol_id = compute_b6_protocol_id_from_fields(
            protocol_profile="b6_coverage_bound",
            strategy_revision_id=strategy_draft.strategy_revision_id,
            theme_id=strategy_draft.theme_id,
            hypothesis_source_snapshot_id=strategy_draft.hypothesis_source_snapshot_id,
            backtest_universe_spec_id=strategy_draft.backtest_universe_spec_id,
            data_snapshot_id=snapshot_id,
            data_snapshot_hash=semantic_hash,
            sample_split_rule_id=strategy_draft.sample_split_rule_id,
            oos_window_rule_id=oos_window_rule_id,
            oos_window_rule_params_json="{}",
            oos_window_start=oos_window_start,
            oos_window_end=oos_window_end,
            shared_oos_window_id=shared_oos_window_id,
            kill_criteria_snapshot_id=kill_reference.snapshot_id,
            prototype_gate_thresholds_json=gate_canonical,
            gate_criteria_hash=gate_criteria_hash,
            strategy_config_hash=strategy_config_hash,
            availability_successor_id=successor_id,
            availability_successor_manifest_hash=successor_hash,
            availability_successor_algorithm_hash=successor.get("coverage_algorithm_hash", ""),
            predecessor_qualification_id=successor.get("predecessor_qualification_package_id", ""),
            predecessor_qualification_manifest_hash=successor.get("predecessor_manifest_sha256", ""),
            predecessor_qualification_status=successor.get("predecessor_original_status", ""),
            predecessor_qualification_algorithm_hash=successor.get("predecessor_algorithm_hash", ""),
            coverage_package_id=successor.get("coverage_package_id", ""),
            coverage_manifest_hash=coverage_hash,
            coverage_algorithm_hash=coverage.get("algorithm_hash", ""),
            source_scope_hash=successor.get("predecessor_scope_hash", ""),
            data_requirements_hash=approved_template.data_requirements_hash,
            expected_stock_days=expected,
            complete_stock_days=complete,
            unavailable_stock_days=unavailable,
            gate_snapshot_id=gate_reference.snapshot_id,
            gate_content_hash=gate_content_hash,
            kill_content_hash=kill_content_hash,
        )
        
        # Now construct with correct ID - validator will verify it matches
        return ResearchProtocolSnapshot(
            protocol_snapshot_id=protocol_id,
            protocol_profile="b6_coverage_bound",
            theme_id=strategy_draft.theme_id,
            hypothesis_source_snapshot_id=strategy_draft.hypothesis_source_snapshot_id,
            strategy_revision_id=strategy_draft.strategy_revision_id,
            sample_split_rule_id=strategy_draft.sample_split_rule_id,
            oos_window_rule_id=oos_window_rule_id,
            oos_window_rule_params_json="{}",
            oos_window_start=oos_window_start,
            oos_window_end=oos_window_end,
            shared_oos_window_id=shared_oos_window_id,
            backtest_universe_spec_id=strategy_draft.backtest_universe_spec_id,
            data_snapshot_id=snapshot_id,
            kill_criteria_snapshot_id=kill_reference.snapshot_id,
            prototype_gate_thresholds_json=gate_canonical,
            strategy_config_hash=strategy_config_hash,
            data_snapshot_hash=semantic_hash,
            gate_criteria_hash=gate_criteria_hash,
            frozen_at=datetime.now(),
            frozen_by=frozen_by,
            # B6 bindings
            availability_successor_id=successor_id,
            availability_successor_manifest_hash=successor_hash,
            availability_successor_algorithm_hash=successor.get("coverage_algorithm_hash", ""),
            predecessor_qualification_id=successor.get("predecessor_qualification_package_id", ""),
            predecessor_qualification_manifest_hash=successor.get("predecessor_manifest_sha256", ""),
            predecessor_qualification_status=successor.get("predecessor_original_status", ""),
            predecessor_qualification_algorithm_hash=successor.get("predecessor_algorithm_hash", ""),
            coverage_package_id=successor.get("coverage_package_id", ""),
            coverage_manifest_hash=coverage_hash,
            coverage_algorithm_hash=coverage.get("algorithm_hash", ""),
            source_scope_hash=successor.get("predecessor_scope_hash", ""),
            data_requirements_hash=approved_template.data_requirements_hash,
            expected_stock_days=expected,
            complete_stock_days=complete,
            unavailable_stock_days=unavailable,
            gate_snapshot_id=gate_reference.snapshot_id,
            gate_content_hash=gate_content_hash,
            kill_content_hash=kill_content_hash,
        )
