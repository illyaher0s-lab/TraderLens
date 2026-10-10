"""Focused v3 B4 production-boundary regression tests."""

import json
from datetime import date
from pathlib import Path

import pyarrow.parquet as pq

from backend.db.strategy import StrategyDB
from backend.services.b3_protocol_types import (
    DataSnapshotManifest,
    PointInTimeMembershipSnapshot,
    UniverseMembershipRecord,
)
from backend.services.backtest_engine_qualification import BacktestEngineQualification


REPO_ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_ID = "6f7cbdcdeb26f8cdd2611a5450dbab3ff22544b6a66ec8539f5cab9151329111"
FORMAL_DIR = REPO_ROOT / "data/pit/v3_formal_data_snapshot_manifests/v3ds_d73256081de82e8a"
MEMBERSHIP_DIR = (
    REPO_ROOT
    / "data/pit/pit_membership_snapshots/pims_traderlens_v2_shsz_sw2021_pit_005"
)


def _load_v3_inputs():
    db = StrategyDB(str(REPO_ROOT / "data/strategy.db"))
    try:
        protocol = db.get_protocol_snapshot(PROTOCOL_ID)
    finally:
        db.close()
    assert protocol is not None

    manifest = DataSnapshotManifest.model_validate(
        json.loads((FORMAL_DIR / "manifest.json").read_text(encoding="utf-8"))
    )
    membership_manifest = json.loads(
        (MEMBERSHIP_DIR / "manifest.json").read_text(encoding="utf-8")
    )
    records = tuple(
        UniverseMembershipRecord(
            symbol=row["symbol"],
            effective_from=row["effective_from"],
            effective_to=row["effective_to"],
            source=row["source"],
            snapshot_id=row["snapshot_id"],
        )
        for row in pq.read_table(MEMBERSHIP_DIR / "records.parquet").to_pylist()
    )
    universe = PointInTimeMembershipSnapshot(
        snapshot_id=membership_manifest["snapshot_id"],
        snapshot_date=date.fromisoformat(membership_manifest["snapshot_date"]),
        universe_rule_type=membership_manifest["universe_rule_type"],
        membership_source=membership_manifest["membership_source"],
        include_delisted=membership_manifest["include_delisted"],
        records=records,
        quality_status=membership_manifest["quality_status"],
        gaps=tuple(membership_manifest["gaps"]),
    )
    return protocol, manifest, universe


def test_official_b4_entrypoint_accepts_verified_v3_inputs_and_blocks_canaries():
    protocol, manifest, universe = _load_v3_inputs()
    result = BacktestEngineQualification().run_qualification_with_b3_protocol(
        protocol=protocol,
        manifest=manifest,
        universe_spec=universe,
        qualification_date=date(2026, 3, 19),
    )

    assert result["protocol_snapshot_id"] == PROTOCOL_ID
    assert result["data_snapshot_hash"] == manifest.semantic_hash
    assert result["universe_snapshot_id"] == universe.snapshot_id
    assert result["result"].qualification_status == "pass"
    assert all(case.outcome == "blocked" for case in result["result"].canary_cases)


def test_official_b4_entrypoint_rejects_tampered_v3_manifest_hash():
    protocol, manifest, universe = _load_v3_inputs()
    tampered = manifest.model_copy(update={"semantic_hash": "tampered"})

    try:
        BacktestEngineQualification().run_qualification_with_b3_protocol(
            protocol=protocol,
            manifest=tampered,
            universe_spec=universe,
            qualification_date=date(2026, 3, 19),
        )
    except ValueError as exc:
        assert "mismatch" in str(exc).lower()
    else:
        raise AssertionError("tampered v3 manifest hash must be rejected")
