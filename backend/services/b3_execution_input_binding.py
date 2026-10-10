"""Frozen references for Task 3 B3 execution inputs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


_REF_FIELDS = (
    "membership_ref",
    "daily_ref",
    "daily_basic_ref",
    "adj_factor_ref",
    "stk_limit_ref",
    "suspend_ref",
    "stock_st_ref",
    "trade_cal_ref",
    "listing_delisting_ref",
    "liquidity_ref",
    "announcement_ref",
)


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _path_has_link(path: Path, stop: Path) -> bool:
    current = path
    while current != stop:
        if current.is_symlink():
            return True
        current = current.parent
    return False


class ExecutionInputReference(BaseModel):
    """One immutable input requirement and its verified availability."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    requirement: Literal["required", "not_required"]
    requirement_reason: str = ""
    availability: Literal["verified", "unavailable"]
    path: str
    content_hash: str = ""
    byte_size: int = Field(default=0, ge=0)

    @property
    def artifact_id(self) -> str:
        return self.name

    @model_validator(mode="after")
    def validate_state(self) -> "ExecutionInputReference":
        if not self.name.strip():
            raise ValueError("name must be non-empty")
        if self.requirement == "not_required" and not self.requirement_reason.strip():
            raise ValueError("not_required inputs require a stable reason")
        if self.availability == "verified":
            if not self.path.strip():
                raise ValueError("verified inputs require a path")
            if not _is_sha256(self.content_hash):
                raise ValueError("verified inputs require a 64-char lowercase SHA-256")
        elif self.path or self.content_hash or self.byte_size:
            raise ValueError("unavailable inputs cannot claim path, hash, or bytes")
        return self


class B3ExecutionInputBinding(BaseModel):
    """Frozen Task 3 execution-input references."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    binding_id: str
    membership_ref: ExecutionInputReference
    daily_ref: ExecutionInputReference
    daily_basic_ref: ExecutionInputReference
    adj_factor_ref: ExecutionInputReference
    stk_limit_ref: ExecutionInputReference
    suspend_ref: ExecutionInputReference
    stock_st_ref: ExecutionInputReference
    trade_cal_ref: ExecutionInputReference
    listing_delisting_ref: ExecutionInputReference
    liquidity_ref: ExecutionInputReference
    announcement_ref: ExecutionInputReference
    canonical_hash: str = ""
    frozen: Literal[True] = True

    @model_validator(mode="after")
    def validate_canonical_hash(self) -> "B3ExecutionInputBinding":
        refs = {
            field.removesuffix("_ref"): getattr(self, field).model_dump()
            for field in _REF_FIELDS
        }
        expected = hashlib.sha256(_canonical_bytes(refs)).hexdigest()
        if self.canonical_hash and self.canonical_hash != expected:
            raise ValueError("canonical_hash mismatch")
        if not self.canonical_hash:
            object.__setattr__(self, "canonical_hash", expected)
        return self


class ValidationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    is_valid: bool
    error: str = ""


def validate_execution_input_binding(
    binding: B3ExecutionInputBinding,
    repo_root: Path,
) -> ValidationResult:
    """Validate required availability and file-backed references without writes."""

    repo_root = Path(repo_root).resolve()
    for field in _REF_FIELDS:
        ref = getattr(binding, field)
        name = field.removesuffix("_ref")
        if ref.requirement == "required" and ref.availability != "verified":
            return ValidationResult(
                is_valid=False,
                error=f"{name}: required execution input is unavailable",
            )
        if ref.availability == "unavailable":
            continue

        relative = Path(ref.path)
        if relative.is_absolute() or ".staging" in relative.parts:
            return ValidationResult(
                is_valid=False,
                error=f"{name}: path must be canonical and repo-relative",
            )
        full_path = (repo_root / relative).resolve()
        try:
            full_path.relative_to(repo_root)
        except ValueError:
            return ValidationResult(
                is_valid=False,
                error=f"{name}: path outside repo",
            )
        if not full_path.exists():
            return ValidationResult(
                is_valid=False,
                error=f"{name}: path not found",
            )
        if _path_has_link(repo_root / relative, repo_root):
            return ValidationResult(
                is_valid=False,
                error=f"{name}: symlink path is not allowed",
            )

        hash_target = full_path
        if full_path.is_dir():
            hash_target = full_path / "manifest.json"
            if not hash_target.is_file():
                return ValidationResult(
                    is_valid=False,
                    error=f"{name}: directory reference requires manifest.json",
                )
        actual = hashlib.sha256(hash_target.read_bytes()).hexdigest()
        if actual != ref.content_hash:
            return ValidationResult(
                is_valid=False,
                error=f"{name}: hash mismatch",
            )

    return ValidationResult(is_valid=True)
