"""Stable production-only effective Gate/Kill criteria evaluator."""
from __future__ import annotations

import json
from typing import Literal

from pydantic import ConfigDict, Field, JsonValue, StrictInt, BaseModel, model_validator


CRITERIA_CONTRACT_VERSION = "v2"
EVALUATOR_SURFACE_ID = "prototype_gate_effective_criteria.v2"
EVALUATOR_ALGORITHM_ID = "b6_effective_criteria.v2"
EVALUATOR_REPO_RELATIVE_PATH = "backend/services/prototype_gate_criteria_surface.py"


class _FrozenCriteriaModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FrozenEffectiveCriteriaInput(_FrozenCriteriaModel):
    future_data_violation_count: StrictInt = Field(ge=0)
    integrity_status: Literal["valid", "invalid"]
    stress_cost_result: JsonValue | None
    control_comparison: JsonValue | None
    base_cost_result: JsonValue | None
    benchmark_comparison: JsonValue | None
    data_quality_status: str | None
    beta_dominated: bool | None
    single_symbol_concentration: JsonValue | None
    single_month_concentration: JsonValue | None

    @model_validator(mode="after")
    def validate_finite_json_values(self) -> "FrozenEffectiveCriteriaInput":
        for name in (
            "stress_cost_result",
            "control_comparison",
            "base_cost_result",
            "benchmark_comparison",
            "single_symbol_concentration",
            "single_month_concentration",
        ):
            value = getattr(self, name)
            try:
                json.dumps(value, ensure_ascii=False, allow_nan=False)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{name} must be finite JSON") from exc
        return self


class EffectiveCriteriaDecision(_FrozenCriteriaModel):
    blocking_issue_ids: tuple[str, ...]
    verdict: Literal["rejected", "candidate_for_prototype_passed"]


def is_failed_result(value: JsonValue | None) -> bool:
    """Return whether a result explicitly blocks candidacy."""
    if value is None:
        return False

    if isinstance(value, str):
        return value.lower() in {"fail", "failed", "rejected", "insufficient"}

    if isinstance(value, dict):
        status = str(value.get("status", "")).lower()
        if status in {"fail", "failed", "rejected", "insufficient"}:
            return True
        if value.get("can_candidate") is False:
            return True
        if value.get("passed") is False:
            return True

    return False


def evaluate_effective_criteria(
    inputs: FrozenEffectiveCriteriaInput,
) -> EffectiveCriteriaDecision:
    """Evaluate the six frozen effective blocking categories in stable order."""
    if not isinstance(inputs, FrozenEffectiveCriteriaInput):
        raise TypeError("inputs must be FrozenEffectiveCriteriaInput")

    blocking_issue_ids: list[str] = []
    if inputs.future_data_violation_count > 0:
        blocking_issue_ids.append("future_data_violation")

    if inputs.integrity_status != "valid":
        blocking_issue_ids.append("invalid_report_integrity")

    for value in (
        inputs.stress_cost_result,
        inputs.control_comparison,
        inputs.base_cost_result,
        inputs.benchmark_comparison,
    ):
        if value is None or value == "not_available_from_b4_result" or is_failed_result(value):
            if "missing_or_failed_b4_result" not in blocking_issue_ids:
                blocking_issue_ids.append("missing_or_failed_b4_result")
            break

    if inputs.data_quality_status in {"insufficient", "invalid"}:
        blocking_issue_ids.append("invalid_data_quality")

    if inputs.beta_dominated is True:
        blocking_issue_ids.append("beta_dominated")

    if is_failed_result(inputs.single_symbol_concentration) or is_failed_result(
        inputs.single_month_concentration
    ):
        blocking_issue_ids.append("concentration_risk")

    return EffectiveCriteriaDecision(
        blocking_issue_ids=tuple(blocking_issue_ids),
        verdict=(
            "rejected"
            if blocking_issue_ids
            else "candidate_for_prototype_passed"
        ),
    )
