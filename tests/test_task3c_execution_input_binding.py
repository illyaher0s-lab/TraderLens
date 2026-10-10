from __future__ import annotations

import hashlib
from pathlib import Path

from backend.services.b3_execution_input_binding import (
    B3ExecutionInputBinding,
    ExecutionInputReference,
    validate_execution_input_binding,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture_files(root: Path) -> dict[str, tuple[str, str, int]]:
    membership = root / "membership" / "manifest.json"
    membership.parent.mkdir(parents=True)
    membership.write_bytes(b"{}")
    result = {
        "membership": (
            membership.parent.relative_to(root).as_posix(),
            _sha(membership),
            membership.stat().st_size,
        )
    }
    for name in (
        "daily",
        "daily_basic",
        "adj_factor",
        "stk_limit",
        "suspend_d",
        "stock_st",
        "trade_cal",
        "listing_delisting",
        "liquidity",
    ):
        path = root / "inputs" / f"{name}.bin"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(name.encode())
        result[name] = (
            path.relative_to(root).as_posix(),
            _sha(path),
            path.stat().st_size,
        )
    return result


def _ref(name: str, values: dict[str, tuple[str, str, int]]) -> ExecutionInputReference:
    path, content_hash, byte_size = values[name]
    return ExecutionInputReference(
        name=name,
        requirement="required",
        requirement_reason="test requirement",
        availability="verified",
        path=path,
        content_hash=content_hash,
        byte_size=byte_size,
    )


def _binding(root: Path, *, binding_id: str = "binding") -> B3ExecutionInputBinding:
    values = _fixture_files(root)
    return B3ExecutionInputBinding(
        binding_id=binding_id,
        membership_ref=_ref("membership", values),
        daily_ref=_ref("daily", values),
        daily_basic_ref=_ref("daily_basic", values),
        adj_factor_ref=_ref("adj_factor", values),
        stk_limit_ref=_ref("stk_limit", values),
        suspend_ref=_ref("suspend_d", values),
        stock_st_ref=_ref("stock_st", values),
        trade_cal_ref=_ref("trade_cal", values),
        listing_delisting_ref=_ref("listing_delisting", values),
        liquidity_ref=_ref("liquidity", values),
        announcement_ref=ExecutionInputReference(
            name="announcement",
            requirement="not_required",
            requirement_reason="forbidden by exact template",
            availability="unavailable",
            path="",
            content_hash="",
        ),
    )


def test_all_verified_required_inputs_construct_and_validate(tmp_path: Path) -> None:
    binding = _binding(tmp_path)
    result = validate_execution_input_binding(binding, tmp_path)
    assert result.is_valid, result.error
    assert "daily_basic_ref" in B3ExecutionInputBinding.model_fields


def test_required_unavailable_is_rejected(tmp_path: Path) -> None:
    binding = _binding(tmp_path).model_copy(
        update={
            "listing_delisting_ref": ExecutionInputReference(
                name="listing_delisting",
                requirement="required",
                requirement_reason="required by exact template",
                availability="unavailable",
                path="",
                content_hash="",
            )
        }
    )
    result = validate_execution_input_binding(binding, tmp_path)
    assert not result.is_valid
    assert "listing_delisting" in result.error


def test_hash_mismatch_is_rejected(tmp_path: Path) -> None:
    binding = _binding(tmp_path)
    binding = binding.model_copy(
        update={
            "membership_ref": binding.membership_ref.model_copy(
                update={"content_hash": "0" * 64}
            )
        }
    )
    result = validate_execution_input_binding(binding, tmp_path)
    assert not result.is_valid
    assert "hash mismatch" in result.error


def test_repo_external_path_is_rejected(tmp_path: Path) -> None:
    binding = _binding(tmp_path)
    binding = binding.model_copy(
        update={
            "daily_ref": binding.daily_ref.model_copy(
                update={"path": str((tmp_path.parent / "outside.bin").resolve())}
            )
        }
    )
    result = validate_execution_input_binding(binding, tmp_path)
    assert not result.is_valid
    assert "repo-relative" in result.error


def test_not_required_unavailable_is_not_file_validated(tmp_path: Path) -> None:
    binding = _binding(tmp_path)
    result = validate_execution_input_binding(binding, tmp_path)
    assert binding.announcement_ref.requirement == "not_required"
    assert binding.announcement_ref.availability == "unavailable"
    assert result.is_valid


def test_canonical_hash_is_deterministic_across_binding_ids(tmp_path: Path) -> None:
    first = _binding(tmp_path / "a", binding_id="first")
    second = _binding(tmp_path / "b", binding_id="second")
    assert first.canonical_hash == second.canonical_hash
