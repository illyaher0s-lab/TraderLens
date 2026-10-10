from __future__ import annotations

import hashlib
import tempfile
from datetime import date
from pathlib import Path

import pytest

from backend.services.b3_execution_input_binding import (
    B3ExecutionInputBinding,
    ExecutionInputReference,
)
from backend.services.formal_pit_loader import FormalMembershipSource, FormalSnapshotLoader
from backend.services.point_in_time_universe import PointInTimeUniverseBuilder
from contracts.strategy import BacktestUniverseSpec


REPO_ROOT = Path(__file__).resolve().parents[1]


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _binding(root: Path, *, listing_available: bool, tamper_membership: bool = False):
    membership = root / "membership" / "manifest.json"
    membership.parent.mkdir(parents=True)
    membership.write_bytes(b"{}")

    def physical(name: str) -> ExecutionInputReference:
        path = root / f"{name}.bin"
        path.write_bytes(name.encode())
        return ExecutionInputReference(
            name=name,
            requirement="required",
            requirement_reason="test",
            availability="verified",
            path=path.relative_to(REPO_ROOT).as_posix(),
            content_hash=_hash(path),
            byte_size=path.stat().st_size,
        )

    membership_ref = ExecutionInputReference(
        name="membership",
        requirement="required",
        requirement_reason="test",
        availability="verified",
        path=membership.parent.relative_to(REPO_ROOT).as_posix(),
        content_hash="0" * 64 if tamper_membership else _hash(membership),
        byte_size=membership.stat().st_size,
    )
    if listing_available:
        listing = physical("listing_delisting")
    else:
        listing = ExecutionInputReference(
            name="listing_delisting",
            requirement="required",
            requirement_reason="frozen template",
            availability="unavailable",
            path="",
            content_hash="",
        )
    return B3ExecutionInputBinding(
        binding_id="b3_test",
        membership_ref=membership_ref,
        daily_ref=physical("daily"),
        daily_basic_ref=physical("daily_basic"),
        adj_factor_ref=physical("adj_factor"),
        stk_limit_ref=physical("stk_limit"),
        suspend_ref=physical("suspend_d"),
        stock_st_ref=physical("stock_st"),
        trade_cal_ref=physical("trade_cal"),
        listing_delisting_ref=listing,
        liquidity_ref=physical("liquidity"),
        announcement_ref=ExecutionInputReference(
            name="announcement",
            requirement="not_required",
            requirement_reason="forbidden by template",
            availability="unavailable",
            path="",
            content_hash="",
        ),
    )


def _builder() -> PointInTimeUniverseBuilder:
    snapshot = FormalSnapshotLoader(REPO_ROOT).load_snapshot(
        "pims_traderlens_v2_shsz_sw2021_pit_005"
    )
    return PointInTimeUniverseBuilder(FormalMembershipSource(snapshot))


def _spec() -> BacktestUniverseSpec:
    return BacktestUniverseSpec(
        universe_spec_id="sw2021_l1_pit",
        universe_rule_type="point_in_time_membership",
        membership_source="sw2021",
        membership_effective_from=date(2016, 1, 4),
        membership_effective_to=date(2016, 12, 31),
        snapshot_date=date(2016, 1, 4),
        membership_snapshot_ids=("pims_traderlens_v2_shsz_sw2021_pit_005",),
        quality_status="ok",
    )


def test_required_unavailable_input_blocks_before_adapter() -> None:
    with tempfile.TemporaryDirectory(dir=REPO_ROOT) as directory:
        binding = _binding(Path(directory), listing_available=False)
        with pytest.raises(ValueError, match="listing_delisting"):
            _builder().build_membership_snapshot(
                _spec(),
                date(2016, 1, 4),
                execution_input_binding=binding,
            )


def test_hash_mismatch_blocks_before_adapter() -> None:
    with tempfile.TemporaryDirectory(dir=REPO_ROOT) as directory:
        binding = _binding(
            Path(directory),
            listing_available=True,
            tamper_membership=True,
        )
        with pytest.raises(ValueError, match="hash mismatch"):
            _builder().build_membership_snapshot(
                _spec(),
                date(2016, 1, 4),
                execution_input_binding=binding,
            )


def test_not_required_unavailable_does_not_block() -> None:
    with tempfile.TemporaryDirectory(dir=REPO_ROOT) as directory:
        binding = _binding(Path(directory), listing_available=True)
        result = _builder().build_membership_snapshot(
            _spec(),
            date(2016, 1, 4),
            execution_input_binding=binding,
        )
        assert result.snapshot_date == date(2016, 1, 4)
