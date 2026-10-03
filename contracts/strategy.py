from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class FrozenStrategyContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _require_non_empty(value: str, field_name: str) -> str:
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")
    return value


def canonical_b6_protocol_payload(
    protocol_profile: str,
    strategy_revision_id: str,
    theme_id: str,
    hypothesis_source_snapshot_id: str,
    backtest_universe_spec_id: str,
    data_snapshot_id: str,
    data_snapshot_hash: str,
    sample_split_rule_id: str,
    oos_window_rule_id: str,
    oos_window_rule_params_json: str,
    oos_window_start: date,
    oos_window_end: date,
    shared_oos_window_id: str,
    kill_criteria_snapshot_id: str,
    prototype_gate_thresholds_json: str,
    gate_criteria_hash: str,
    strategy_config_hash: str,
    availability_successor_id: str | None,
    availability_successor_manifest_hash: str | None,
    availability_successor_algorithm_hash: str | None,
    predecessor_qualification_id: str | None,
    predecessor_qualification_manifest_hash: str | None,
    predecessor_qualification_status: str | None,
    predecessor_qualification_algorithm_hash: str | None,
    coverage_package_id: str | None,
    coverage_manifest_hash: str | None,
    coverage_algorithm_hash: str | None,
    source_scope_hash: str | None,
    data_requirements_hash: str | None,
    expected_stock_days: int | None,
    complete_stock_days: int | None,
    unavailable_stock_days: int | None,
    gate_snapshot_id: str | None,
    gate_content_hash: str | None,
    kill_content_hash: str | None,
) -> dict:
    """Canonical B6 protocol payload for deterministic ID. ponytail: legacy_b3 excluded."""
    canonical = {
        "protocol_profile": protocol_profile,
        "strategy_revision_id": strategy_revision_id,
        "theme_id": theme_id,
        "hypothesis_source_snapshot_id": hypothesis_source_snapshot_id,
        "backtest_universe_spec_id": backtest_universe_spec_id,
        "data_snapshot_id": data_snapshot_id,
        "data_snapshot_hash": data_snapshot_hash,
        "sample_split_rule_id": sample_split_rule_id,
        "oos_window_rule_id": oos_window_rule_id,
        "oos_window_rule_params_json": oos_window_rule_params_json,
        "oos_window_start": str(oos_window_start),
        "oos_window_end": str(oos_window_end),
        "shared_oos_window_id": shared_oos_window_id,
        "kill_criteria_snapshot_id": kill_criteria_snapshot_id,
        "prototype_gate_thresholds_json": prototype_gate_thresholds_json,
        "gate_criteria_hash": gate_criteria_hash,
        "strategy_config_hash": strategy_config_hash,
    }

    if protocol_profile == "b6_coverage_bound":
        canonical.update({
            "availability_successor_id": availability_successor_id,
            "availability_successor_manifest_hash": availability_successor_manifest_hash,
            "availability_successor_algorithm_hash": availability_successor_algorithm_hash,
            "predecessor_qualification_id": predecessor_qualification_id,
            "predecessor_qualification_manifest_hash": predecessor_qualification_manifest_hash,
            "predecessor_qualification_status": predecessor_qualification_status,
            "predecessor_qualification_algorithm_hash": predecessor_qualification_algorithm_hash,
            "coverage_package_id": coverage_package_id,
            "coverage_manifest_hash": coverage_manifest_hash,
            "coverage_algorithm_hash": coverage_algorithm_hash,
            "source_scope_hash": source_scope_hash,
            "data_requirements_hash": data_requirements_hash,
            "expected_stock_days": expected_stock_days,
            "complete_stock_days": complete_stock_days,
            "unavailable_stock_days": unavailable_stock_days,
            "gate_snapshot_id": gate_snapshot_id,
            "gate_content_hash": gate_content_hash,
            "kill_content_hash": kill_content_hash,
        })

    return canonical


def compute_b6_protocol_id_from_fields(**fields) -> str:
    """Compute B6 protocol ID from raw fields. ponytail: excludes frozen_at/frozen_by."""
    import hashlib
    import json

    canonical = canonical_b6_protocol_payload(**fields)
    serialized = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def compute_b6_protocol_id(protocol: "ResearchProtocolSnapshot") -> str:
    """Wrapper: extract fields from protocol object. ponytail: no duplicate logic."""
    return compute_b6_protocol_id_from_fields(
        protocol_profile=protocol.protocol_profile,
        strategy_revision_id=protocol.strategy_revision_id,
        theme_id=protocol.theme_id,
        hypothesis_source_snapshot_id=protocol.hypothesis_source_snapshot_id,
        backtest_universe_spec_id=protocol.backtest_universe_spec_id,
        data_snapshot_id=protocol.data_snapshot_id,
        data_snapshot_hash=protocol.data_snapshot_hash,
        sample_split_rule_id=protocol.sample_split_rule_id,
        oos_window_rule_id=protocol.oos_window_rule_id,
        oos_window_rule_params_json=protocol.oos_window_rule_params_json,
        oos_window_start=protocol.oos_window_start,
        oos_window_end=protocol.oos_window_end,
        shared_oos_window_id=protocol.shared_oos_window_id,
        kill_criteria_snapshot_id=protocol.kill_criteria_snapshot_id,
        prototype_gate_thresholds_json=protocol.prototype_gate_thresholds_json,
        gate_criteria_hash=protocol.gate_criteria_hash,
        strategy_config_hash=protocol.strategy_config_hash,
        availability_successor_id=protocol.availability_successor_id,
        availability_successor_manifest_hash=protocol.availability_successor_manifest_hash,
        availability_successor_algorithm_hash=protocol.availability_successor_algorithm_hash,
        predecessor_qualification_id=protocol.predecessor_qualification_id,
        predecessor_qualification_manifest_hash=protocol.predecessor_qualification_manifest_hash,
        predecessor_qualification_status=protocol.predecessor_qualification_status,
        predecessor_qualification_algorithm_hash=protocol.predecessor_qualification_algorithm_hash,
        coverage_package_id=protocol.coverage_package_id,
        coverage_manifest_hash=protocol.coverage_manifest_hash,
        coverage_algorithm_hash=protocol.coverage_algorithm_hash,
        source_scope_hash=protocol.source_scope_hash,
        data_requirements_hash=protocol.data_requirements_hash,
        expected_stock_days=protocol.expected_stock_days,
        complete_stock_days=protocol.complete_stock_days,
        unavailable_stock_days=protocol.unavailable_stock_days,
        gate_snapshot_id=protocol.gate_snapshot_id,
        gate_content_hash=protocol.gate_content_hash,
        kill_content_hash=protocol.kill_content_hash,
    )


class SourceRuleMapping(FrozenStrategyContract):
    """One source claim or explicit implementation constraint for a frozen rule."""

    source_claim_id: str
    source_locator: str | None = None
    frozen_rule_id: str
    mapping_kind: Literal["source_claim", "implementation_constraint"]
    rationale: str


class StrategyTemplateDefinition(FrozenStrategyContract):
    template_id: str
    version: str
    template_hash: str
    hypothesis_types: tuple[str, ...]
    core_entry_rule_id: str
    supported_universe_rule_types: tuple[
        Literal["sector_plus_tags", "point_in_time_membership"], ...
    ]
    sample_split_rule_ids: tuple[str, ...]
    benchmark_rule_id: str
    created_at: datetime
    frozen: Literal[True] = True

    # V2 governance fields (Task 1)
    governance_status: Literal["candidate", "approved", "retired"] = "candidate"  # ponytail: default candidate
    source_citation: str | None = None  # DOI or URL
    source_retrieval_date: date | None = None
    rule_mapping: str | None = None  # source claim → frozen rule mapping
    source_rule_mappings: tuple[SourceRuleMapping, ...] = ()
    market_scope_difference: str | None = None
    data_requirements_hash: str | None = None
    governance_evidence_hash: str | None = None
    reviewer_id: str | None = None
    reviewed_at: datetime | None = None
    review_due_date: date | None = None
    review_evidence_path: str | None = None
    review_evidence_sha256: str | None = None
    owner_authorization_hash: str | None = None
    authorized_by: str | None = None
    authorized_at: datetime | None = None

    @model_validator(mode="after")
    def approved_templates_require_complete_governance(self) -> "StrategyTemplateDefinition":
        if self.governance_status != "approved":
            return self

        required = {
            "source_citation": self.source_citation,
            "source_retrieval_date": self.source_retrieval_date,
            "market_scope_difference": self.market_scope_difference,
            "data_requirements_hash": self.data_requirements_hash,
            "governance_evidence_hash": self.governance_evidence_hash,
            "reviewer_id": self.reviewer_id,
            "reviewed_at": self.reviewed_at,
            "review_due_date": self.review_due_date,
            "review_evidence_path": self.review_evidence_path,
            "review_evidence_sha256": self.review_evidence_sha256,
            "owner_authorization_hash": self.owner_authorization_hash,
            "authorized_by": self.authorized_by,
            "authorized_at": self.authorized_at,
        }
        missing = [name for name, value in required.items() if value is None or value == ""]
        if missing or not self.source_rule_mappings:
            raise ValueError(
                "approved template requires complete governance evidence: "
                + ", ".join(missing + ([] if self.source_rule_mappings else ["source_rule_mappings"]))
            )
        if not any(mapping.mapping_kind == "source_claim" for mapping in self.source_rule_mappings):
            raise ValueError("approved template requires at least one source_claim mapping")
        if self.review_due_date <= self.reviewed_at.date():
            raise ValueError("review_due_date must be after reviewed_at for approved template")
        return self


class BacktestUniverseSpec(FrozenStrategyContract):
    universe_spec_id: str
    universe_rule_type: Literal["sector_plus_tags", "point_in_time_membership"]
    sector: str | None = None
    chain_layer_tags: tuple[str, ...] = ()
    membership_source: str
    membership_effective_from: date
    membership_effective_to: date
    snapshot_date: date
    include_delisted: Literal[True] = True
    membership_snapshot_ids: tuple[str, ...]
    quality_status: Literal["ok", "degraded", "insufficient"]
    gaps: tuple[str, ...] = ()
    frozen: Literal[True] = True

    @model_validator(mode="after")
    def validate_membership_window(self) -> "BacktestUniverseSpec":
        if self.membership_effective_from > self.membership_effective_to:
            raise ValueError("membership_effective_from cannot exceed membership_effective_to")
        if not self.membership_snapshot_ids and self.quality_status != "insufficient":
            raise ValueError("membership_snapshot_ids required unless quality is insufficient")
        return self


class ForwardWatchlistSnapshot(FrozenStrategyContract):
    watchlist_snapshot_id: str
    theme_id: str
    confirmed_candidate_ids: tuple[str, ...]
    symbols: tuple[str, ...]
    snapshot_date: date
    created_at: datetime
    forward_only: Literal[True] = True
    frozen: Literal[True] = True


class TemplateGovernanceProvenance(FrozenStrategyContract):
    kind: Literal["approved_template_governance"]
    template_id: str
    template_version: str
    template_hash: str
    data_requirements_hash: str
    review_evidence_path: str
    review_evidence_sha256: str
    reviewer_id: str
    reviewer_kind: str
    review_decision: Literal["approved"]
    reviewed_at: datetime
    review_due_date: date
    owner_authorization_hash: str
    authorized_by: str
    authorized_at: datetime


class StrategyDraft(FrozenStrategyContract):
    strategy_revision_id: str
    theme_id: str
    hypothesis_id: str
    strategy_template_id: str
    strategy_template_version: str
    strategy_template_hash: str
    hypothesis_source_snapshot_id: str
    backtest_universe_spec_id: str
    strategy_config_json: str
    sample_split_rule_id: str
    created_at: datetime
    frozen: Literal[True] = True
    # Task 2: B6 provenance binding (optional, legacy compatible)
    source_approval_card_id: str | None = None
    source_confirmed_candidate_id: str | None = None
    provenance: TemplateGovernanceProvenance | None = None

    @field_validator("strategy_revision_id")
    @classmethod
    def revision_id_must_be_non_empty(cls, value: str) -> str:
        return _require_non_empty(value, "strategy_revision_id")


class StrategyLifecycleState(FrozenStrategyContract):
    lifecycle_state_id: str
    strategy_revision_id: str
    state_version: int = Field(ge=1)
    state: Literal["draft", "prototype_passed"]
    source_record_id: str
    recorded_at: datetime
    recorded_by: str
    frozen: Literal[True] = True


class ProtocolFreezePreflightResult(FrozenStrategyContract):
    """Non-persistent B6 unavailable result."""
    status: Literal["validation_unavailable"]
    reason_code: Literal[
        "availability_qualification_unavailable",
        "availability_successor_binding_invalid",
        "snapshot_manifest_unavailable",
        "template_not_approved",
        "template_binding_mismatch",
        "artifact_binding_mismatch",
        "criteria_reference_unavailable",
        "criteria_content_hash_mismatch",
        "criteria_envelope_hash_mismatch",
        "ledger_owner_unavailable",
        "ledger_active_reservation",
        "ledger_budget_exhausted",
        "split_or_time_consistency_invalid",
    ]
    detail: str | None = None


class FrozenCriteriaReference(FrozenStrategyContract):
    """Frozen gate or kill criteria reference with snapshot ID, content, and hash."""
    snapshot_id: str
    criteria_json: str  # canonical JSON object
    declared_content_hash: str


class ResearchProtocolSnapshot(FrozenStrategyContract):
    protocol_snapshot_id: str
    theme_id: str
    hypothesis_source_snapshot_id: str
    strategy_revision_id: str
    sample_split_rule_id: str
    oos_window_rule_id: str
    oos_window_rule_params_json: str
    oos_window_start: date
    oos_window_end: date
    shared_oos_window_id: str
    backtest_universe_spec_id: str
    data_snapshot_id: str
    kill_criteria_snapshot_id: str
    prototype_gate_thresholds_json: str
    strategy_config_hash: str
    data_snapshot_hash: str
    gate_criteria_hash: str
    frozen_at: datetime
    frozen_by: str
    frozen: Literal[True] = True

    # B6 runtime extensions (migration 002)
    protocol_profile: Literal["legacy_b3", "b6_coverage_bound"] = "legacy_b3"

    # B6 optional bindings (Task 4B-2A)
    availability_successor_id: str | None = None
    availability_successor_manifest_hash: str | None = None
    availability_successor_algorithm_hash: str | None = None
    predecessor_qualification_id: str | None = None
    predecessor_qualification_manifest_hash: str | None = None
    predecessor_qualification_status: str | None = None
    predecessor_qualification_algorithm_hash: str | None = None
    coverage_package_id: str | None = None
    coverage_manifest_hash: str | None = None
    coverage_algorithm_hash: str | None = None
    source_scope_hash: str | None = None
    data_requirements_hash: str | None = None
    expected_stock_days: int | None = None
    complete_stock_days: int | None = None
    unavailable_stock_days: int | None = None
    gate_snapshot_id: str | None = None
    gate_content_hash: str | None = None
    kill_content_hash: str | None = None

    @model_validator(mode="after")
    def validate_protocol(self) -> "ResearchProtocolSnapshot":
        for name in (
            "strategy_config_hash",
            "data_snapshot_hash",
            "gate_criteria_hash",
        ):
            _require_non_empty(getattr(self, name), name)
        if self.oos_window_start > self.oos_window_end:
            raise ValueError("oos_window_start cannot exceed oos_window_end")

        # ponytail: b6_coverage_bound requires complete bindings + deterministic ID
        if self.protocol_profile == "b6_coverage_bound":
            b6_required = {
                "availability_successor_id": self.availability_successor_id,
                "availability_successor_manifest_hash": self.availability_successor_manifest_hash,
                "availability_successor_algorithm_hash": self.availability_successor_algorithm_hash,
                "predecessor_qualification_id": self.predecessor_qualification_id,
                "predecessor_qualification_manifest_hash": self.predecessor_qualification_manifest_hash,
                "predecessor_qualification_status": self.predecessor_qualification_status,
                "predecessor_qualification_algorithm_hash": self.predecessor_qualification_algorithm_hash,
                "coverage_package_id": self.coverage_package_id,
                "coverage_manifest_hash": self.coverage_manifest_hash,
                "coverage_algorithm_hash": self.coverage_algorithm_hash,
                "source_scope_hash": self.source_scope_hash,
                "data_requirements_hash": self.data_requirements_hash,
                "expected_stock_days": self.expected_stock_days,
                "complete_stock_days": self.complete_stock_days,
                "unavailable_stock_days": self.unavailable_stock_days,
                "gate_snapshot_id": self.gate_snapshot_id,
                "gate_content_hash": self.gate_content_hash,
                "kill_content_hash": self.kill_content_hash,
            }
            missing = [k for k, v in b6_required.items() if v is None or v == ""]
            if missing:
                raise ValueError(f"b6_coverage_bound requires: {', '.join(missing)}")

            # ponytail: coverage arithmetic
            if self.complete_stock_days + self.unavailable_stock_days != self.expected_stock_days:
                raise ValueError("coverage arithmetic: complete + unavailable must equal expected")

            # ponytail: no placeholder criteria
            if self.prototype_gate_thresholds_json.strip() in ("", "{}"):
                raise ValueError("b6_coverage_bound: gate criteria cannot be empty or {}")
            if self.kill_criteria_snapshot_id.strip() == "":
                raise ValueError("b6_coverage_bound: kill_criteria_snapshot_id cannot be empty")

            # ponytail: enforce deterministic ID from same-file function
            expected_id = compute_b6_protocol_id(self)
            if self.protocol_snapshot_id != expected_id:
                raise ValueError(f"b6_coverage_bound: protocol_snapshot_id must match computed ID (expected {expected_id[:16]}...)")

        return self


class OOSEvaluationLedger(FrozenStrategyContract):
    ledger_snapshot_id: str
    theme_id: str
    hypothesis_source_snapshot_id: str
    ledger_version: int = Field(ge=1)
    oos_evaluation_count: int = Field(ge=0, le=3)
    oos_budget_limit: Literal[3] = 3
    next_oos_draw_index: int = Field(ge=1, le=3)
    budget_status: Literal["available", "reserved", "oos_budget_exhausted"]
    completed_evaluation_ids: tuple[str, ...] = ()
    active_reservation_ids: tuple[str, ...] = ()
    report_ids: tuple[str, ...] = ()
    recorded_at: datetime
    frozen: Literal[True] = True


class ImmutableBacktestReport(FrozenStrategyContract):
    report_id: str
    theme_id: str
    strategy_revision_id: str
    protocol_snapshot_id: str
    strategy_config_hash: str
    data_snapshot_hash: str
    gate_criteria_hash: str
    evaluation_mode: Literal[
        "in_sample", "out_of_sample", "prototype_sanity_check_only"
    ]
    oos_draw_index: int | None = Field(default=None, ge=1, le=3)
    shared_oos_window_id: str | None = None
    multiple_comparison_flag: bool = False
    report_payload_json: str
    integrity_status: Literal["valid", "invalid"]
    generated_at: datetime
    report_hash: str
    frozen: Literal[True] = True


class PrototypeGateResultV2(FrozenStrategyContract):
    gate_result_id: str
    report_id: str
    strategy_revision_id: str
    protocol_snapshot_id: str
    verdict: Literal[
        "rejected",
        "needs_review",
        "candidate_for_prototype_passed",
    ]
    checks_json: str
    blocking_issues: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    strategy_config_hash: str
    data_snapshot_hash: str
    gate_criteria_hash: str
    oos_draw_index: int | None = Field(default=None, ge=1, le=3)
    shared_oos_window_id: str | None = None
    multiple_comparison_flag: bool = False
    generated_at: datetime
    gate_result_hash: str
    frozen: Literal[True] = True


class HumanPromotionConfirmation(FrozenStrategyContract):
    human_confirmation_id: str
    strategy_revision_id: str
    gate_result_id: str
    decision: Literal["approve", "reject"]
    confirmed_by: str
    confirmed_at: datetime
    frozen: Literal[True] = True


class HumanConfirmationConsumption(FrozenStrategyContract):
    consumption_id: str
    human_confirmation_id: str
    strategy_revision_id: str
    gate_result_id: str
    promotion_id: str
    consumed_at: datetime
    consumed_by: str
    frozen: Literal[True] = True


class StrategyPromotionRecord(FrozenStrategyContract):
    promotion_id: str
    strategy_revision_id: str
    gate_result_id: str
    report_id: str
    protocol_snapshot_id: str
    human_confirmation_id: str
    previous_state: Literal["draft"]
    new_state: Literal["prototype_passed"]
    promoted_by: str
    promoted_at: datetime
    frozen: Literal[True] = True


def admit_formal_backtest_universe(
    universe: BacktestUniverseSpec,
) -> BacktestUniverseSpec:
    if not isinstance(universe, BacktestUniverseSpec):
        raise TypeError("formal backtest requires BacktestUniverseSpec")
    return universe
