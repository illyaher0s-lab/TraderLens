"""
B6 Validation Task Contract

Defines the B6 validation task structure for persistence.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


B6_TASK_TYPE = "b6_validation"
B6_PROTOCOL_PROFILE = "b6_coverage_bound"
B6_TASK_CONTRACT_V1 = "v1"
B6_TASK_CONTRACT_V2 = "v2"
B6_TASK_CONTRACT_V3 = "v3"


def _validate_bundle_id(value: str) -> None:
    if (
        not value
        or value.strip() != value
        or value in {".", ".."}
        or any(separator in value for separator in ("/", "\\", ":"))
        or any(ord(character) < 32 for character in value)
    ):
        raise ValueError("b5_bundle_id must be a non-empty path-free identifier")


def _validate_b5_pair(bundle_id: str | None, manifest_sha256: str | None) -> None:
    if (bundle_id is None) != (manifest_sha256 is None):
        raise ValueError("b5_bundle_id and b5_bundle_manifest_sha256 must be provided together")
    if bundle_id is not None:
        _validate_bundle_id(bundle_id)
        if manifest_sha256 is None or not all(
            character in "0123456789abcdef" for character in manifest_sha256
        ) or len(manifest_sha256) != 64:
            raise ValueError("b5_bundle_manifest_sha256 must be 64 lowercase hexadecimal characters")


def _validate_task_reference(value: str, field_name: str) -> None:
    if (
        len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
        or value.strip() != value
        or any(separator in value for separator in ("/", "\\", ":"))
        or any(ord(character) < 32 for character in value)
    ):
        raise ValueError(f"{field_name} must be a 64-character lowercase SHA-256 identifier")


def build_b6_task_key(
    *,
    strategy_revision_id: str,
    protocol_snapshot_id: str,
    task_contract_version: Literal["v1", "v2"] = B6_TASK_CONTRACT_V1,
    b5_bundle_id: str | None = None,
    b5_bundle_manifest_sha256: str | None = None,
) -> str:
    """Build the exact v1 or v2 canonical B6 task key."""
    if task_contract_version == B6_TASK_CONTRACT_V1:
        _validate_b5_pair(b5_bundle_id, b5_bundle_manifest_sha256)
        if b5_bundle_id is not None:
            raise ValueError("v1 task keys cannot contain B5 binding fields")
        identity = {
            "protocol_profile": B6_PROTOCOL_PROFILE,
            "protocol_snapshot_id": protocol_snapshot_id,
            "strategy_revision_id": strategy_revision_id,
            "task_contract_version": B6_TASK_CONTRACT_V1,
            "task_type": B6_TASK_TYPE,
        }
    elif task_contract_version == B6_TASK_CONTRACT_V2:
        _validate_b5_pair(b5_bundle_id, b5_bundle_manifest_sha256)
        if b5_bundle_id is None or b5_bundle_manifest_sha256 is None:
            raise ValueError("v2 task keys require the complete B5 binding")
        identity = {
            "b5_bundle_id": b5_bundle_id,
            "b5_bundle_manifest_sha256": b5_bundle_manifest_sha256,
            "protocol_profile": B6_PROTOCOL_PROFILE,
            "protocol_snapshot_id": protocol_snapshot_id,
            "strategy_revision_id": strategy_revision_id,
            "task_contract_version": B6_TASK_CONTRACT_V2,
            "task_type": B6_TASK_TYPE,
        }
    else:
        raise ValueError(f"unsupported B6 task contract version: {task_contract_version}")

    canonical = json.dumps(
        identity,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_b6_successor_task_key(
    *,
    predecessor_task_id: str,
    predecessor_task_key: str,
    strategy_revision_id: str,
    protocol_snapshot_id: str,
    b5_bundle_id: str,
    b5_bundle_manifest_sha256: str,
    attempt_number: int = 1,
) -> str:
    """Build the exact canonical v3 successor-attempt task key."""
    _validate_task_reference(predecessor_task_id, "predecessor_task_id")
    _validate_task_reference(predecessor_task_key, "predecessor_task_key")
    _validate_b5_pair(b5_bundle_id, b5_bundle_manifest_sha256)
    if attempt_number != 1:
        raise ValueError("B6 successor attempt_number must be 1")
    expected_predecessor_key = build_b6_task_key(
        strategy_revision_id=strategy_revision_id,
        protocol_snapshot_id=protocol_snapshot_id,
        task_contract_version=B6_TASK_CONTRACT_V2,
        b5_bundle_id=b5_bundle_id,
        b5_bundle_manifest_sha256=b5_bundle_manifest_sha256,
    )
    if predecessor_task_key != expected_predecessor_key:
        raise ValueError("B6 successor predecessor_task_key does not match v2 identity")
    if predecessor_task_id != build_b6_task_id(predecessor_task_key):
        raise ValueError("B6 successor predecessor_task_id does not match canonical task key")
    identity = {
        "attempt_number": attempt_number,
        "b5_bundle_id": b5_bundle_id,
        "b5_bundle_manifest_sha256": b5_bundle_manifest_sha256,
        "predecessor_task_id": predecessor_task_id,
        "predecessor_task_key": predecessor_task_key,
        "protocol_profile": B6_PROTOCOL_PROFILE,
        "protocol_snapshot_id": protocol_snapshot_id,
        "strategy_revision_id": strategy_revision_id,
        "task_contract_version": B6_TASK_CONTRACT_V3,
        "task_type": B6_TASK_TYPE,
    }
    canonical = json.dumps(
        identity,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_b6_task_id(task_key: str) -> str:
    """Build the canonical B6 task ID from its task key."""
    canonical = json.dumps(
        {"kind": "b6_validation_task", "payload": {"task_key": task_key}},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class B6ValidationTask(BaseModel):
    """
    B6 validation task for durable task tracking.

    Fields:
    - task_id: Unique task identifier (UUID)
    - task_key: Deterministic SHA-256 hash of (revision, protocol, task_type, contract_version)
    - status: queued/running/blocked/completed/failed
    - blocking_reason_code: Typed reason for blocked/failed status
    - created_at: Task creation timestamp
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    task_id: str
    task_key: str
    task_type: Literal["b6_validation"]
    task_contract_version: Literal["v1", "v2", "v3"] = "v1"
    strategy_revision_id: str
    protocol_snapshot_id: str
    status: Literal["queued", "running", "blocked", "completed", "failed"]
    blocking_reason_code: str | None = None
    blocking_reason_detail: str | None = None
    created_at: datetime
    claimed_at: datetime | None = None
    completed_at: datetime | None = None
    b5_bundle_id: str | None = None
    b5_bundle_manifest_sha256: str | None = Field(
        default=None,
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    predecessor_task_id: str | None = None
    predecessor_task_key: str | None = None
    successor_attempt_number: int | None = None

    @model_validator(mode="after")
    def validate_contract_binding(self) -> "B6ValidationTask":
        _validate_b5_pair(self.b5_bundle_id, self.b5_bundle_manifest_sha256)
        if self.task_contract_version == B6_TASK_CONTRACT_V1 and self.b5_bundle_id is not None:
            raise ValueError("v1 tasks cannot contain B5 binding fields")
        if self.task_contract_version == B6_TASK_CONTRACT_V2 and self.b5_bundle_id is None:
            raise ValueError("v2 tasks require the complete B5 binding")
        successor_fields = (
            self.predecessor_task_id,
            self.predecessor_task_key,
            self.successor_attempt_number,
        )
        if self.task_contract_version in {B6_TASK_CONTRACT_V1, B6_TASK_CONTRACT_V2}:
            if any(value is not None for value in successor_fields):
                raise ValueError("v1/v2 tasks cannot contain successor binding fields")
        else:
            if any(value is None for value in successor_fields):
                raise ValueError("v3 tasks require complete predecessor binding and attempt number")
            _validate_task_reference(self.predecessor_task_id, "predecessor_task_id")
            _validate_task_reference(self.predecessor_task_key, "predecessor_task_key")
            if self.successor_attempt_number != 1:
                raise ValueError("v3 successor attempt number must be 1")
            expected_key = build_b6_successor_task_key(
                predecessor_task_id=self.predecessor_task_id,
                predecessor_task_key=self.predecessor_task_key,
                strategy_revision_id=self.strategy_revision_id,
                protocol_snapshot_id=self.protocol_snapshot_id,
                b5_bundle_id=self.b5_bundle_id,
                b5_bundle_manifest_sha256=self.b5_bundle_manifest_sha256,
                attempt_number=self.successor_attempt_number,
            )
            if self.task_key != expected_key:
                raise ValueError("v3 task key does not match frozen successor identity")
            if self.task_id != build_b6_task_id(self.task_key):
                raise ValueError("v3 task ID does not match canonical task key")
        return self
