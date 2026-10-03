"""Small, frozen payload contracts for the v3-only B5 bundle."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


RESULT_TYPES = (
    "base_transaction_cost",
    "stress_transaction_cost",
    "benchmark_comparison",
    "same_universe_control_comparison",
)
ResultType = Literal[
    "base_transaction_cost",
    "stress_transaction_cost",
    "benchmark_comparison",
    "same_universe_control_comparison",
]
HEX64 = re.compile(r"^[0-9a-f]{64}$")
HEX16 = re.compile(r"^[0-9a-f]{16}$")


def canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


class B5ResultPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["v3_b5_result.v1"]
    result_type: ResultType
    status: Literal["verified", "invalid"]
    authorized_for_bundle: bool
    lineage: dict[str, Any]
    result: dict[str, Any] = Field(min_length=1)
    producer_algorithm_hash: str
    cost_assumptions_hash: str
    daily_observation_hash: str | None = None
    payload_id: str
    canonical_payload_sha256: str

    @model_validator(mode="after")
    def validate_hashes(self) -> "B5ResultPayload":
        if not HEX64.fullmatch(self.producer_algorithm_hash):
            raise ValueError("producer_algorithm_hash must be a lowercase SHA-256")
        if not HEX64.fullmatch(self.cost_assumptions_hash):
            raise ValueError("cost_assumptions_hash must be a lowercase SHA-256")
        if self.daily_observation_hash is not None and not HEX64.fullmatch(self.daily_observation_hash):
            raise ValueError("daily_observation_hash must be a lowercase SHA-256")
        if self.result_type in {"benchmark_comparison", "same_universe_control_comparison"} and self.daily_observation_hash is None:
            raise ValueError("comparison result requires daily_observation_hash")
        if not HEX16.fullmatch(self.payload_id) or not HEX64.fullmatch(self.canonical_payload_sha256):
            raise ValueError("payload identity hash format invalid")
        return self


def _payload_without_identity(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key not in {"payload_id", "canonical_payload_sha256"}}


def build_result_payload(
    result_type: str,
    *,
    lineage: dict[str, Any],
    result: dict[str, Any],
    producer_algorithm_hash: str,
    cost_assumptions_hash: str,
    daily_observation_hash: str | None = None,
    status: str = "verified",
    authorized_for_bundle: bool = True,
) -> dict[str, Any]:
    draft = {
        "schema_version": "v3_b5_result.v1",
        "result_type": result_type,
        "status": status,
        "authorized_for_bundle": authorized_for_bundle,
        "lineage": lineage,
        "result": result,
        "producer_algorithm_hash": producer_algorithm_hash,
        "cost_assumptions_hash": cost_assumptions_hash,
        "daily_observation_hash": daily_observation_hash,
    }
    digest = sha256_bytes(canonical_json(draft))
    payload = {**draft, "payload_id": digest[:16], "canonical_payload_sha256": digest}
    return B5ResultPayload.model_validate(payload).model_dump(mode="json")


def validate_result_payload(
    payload: dict[str, Any], expected_type: str, expected_lineage: dict[str, Any]
) -> dict[str, Any]:
    model = B5ResultPayload.model_validate(payload)
    if model.result_type != expected_type:
        raise ValueError(f"result type mismatch: {model.result_type}")
    if model.lineage != expected_lineage:
        raise ValueError("result lineage mismatch")
    if model.status != "verified" or model.authorized_for_bundle is not True:
        raise ValueError(f"result not verified: {expected_type}")
    if model.result_type in {"benchmark_comparison", "same_universe_control_comparison"} and model.daily_observation_hash is None:
        raise ValueError(f"comparison result missing daily observation: {expected_type}")
    actual = sha256_bytes(canonical_json(_payload_without_identity(model.model_dump(mode="json"))))
    if actual != model.canonical_payload_sha256 or actual[:16] != model.payload_id:
        raise ValueError(f"result identity mismatch: {expected_type}")
    return model.model_dump(mode="json")
