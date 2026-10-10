"""Task 3A integrity and provenance regressions at the real B3 boundary."""
from __future__ import annotations

import hashlib
import json
import shutil
from datetime import date
from pathlib import Path

import pytest

from backend.services.formal_pit_loader import FormalMembershipSource, FormalSnapshotLoader
from backend.services.point_in_time_universe import PointInTimeUniverseBuilder
from tests.b1_fixtures import make_backtest_universe


REPO_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_ID = "pims_traderlens_v2_shsz_sw2021_pit_005"


def _canonical_hash(manifest: dict) -> str:
    payload = {
        key: value
        for key, value in manifest.items()
        if key not in {"canonical_content_hash", "manifest_published_at"}
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _copied_loader(tmp_path: Path) -> tuple[FormalSnapshotLoader, Path]:
    snapshots_root = tmp_path / "snapshots"
    source = REPO_ROOT / "data/pit/pit_membership_snapshots" / SNAPSHOT_ID
    shutil.copytree(source, snapshots_root / SNAPSHOT_ID)
    loader = FormalSnapshotLoader(REPO_ROOT)
    loader.snapshots_root = snapshots_root
    return loader, snapshots_root / SNAPSHOT_ID


def test_artifact_only_requires_manifest_and_records_sidecars(tmp_path):
    loader, snapshot_dir = _copied_loader(tmp_path)
    (snapshot_dir / "manifest.json.sha256").unlink()

    with pytest.raises(ValueError, match=r"manifest\.json\.sha256"):
        loader.load_snapshot(SNAPSHOT_ID)


def test_artifact_only_recomputes_canonical_hash(tmp_path):
    loader, snapshot_dir = _copied_loader(tmp_path)
    manifest_path = snapshot_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["membership_source"] = "tampered_membership_source"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    raw_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    (snapshot_dir / "manifest.json.sha256").write_text(
        f"{raw_hash}  manifest.json\n", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="(?i)canonical"):
        loader.load_snapshot(SNAPSHOT_ID)


def test_artifact_only_binds_to_published_formal_data_manifest(tmp_path):
    loader, snapshot_dir = _copied_loader(tmp_path)
    manifest_path = snapshot_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["formal_data_semantic_hash"] = "0" * 64
    manifest["canonical_content_hash"] = _canonical_hash(manifest)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    raw_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    (snapshot_dir / "manifest.json.sha256").write_text(
        f"{raw_hash}  manifest.json\n", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="(?i)formal data"):
        loader.load_snapshot(SNAPSHOT_ID)


def test_builder_preserves_verified_formal_snapshot_identity():
    loader = FormalSnapshotLoader(REPO_ROOT)
    formal_source = FormalMembershipSource(loader.load_snapshot(SNAPSHOT_ID))
    universe = make_backtest_universe().model_copy(
        update={"membership_snapshot_ids": (SNAPSHOT_ID,)}
    )

    result = PointInTimeUniverseBuilder(formal_source).build_membership_snapshot(
        universe, date(2020, 1, 1), date(2024, 12, 31)
    )

    assert result.snapshot_id == SNAPSHOT_ID
    assert result.membership_source == formal_source.snapshot.membership_source


def test_unknown_source_error_is_not_reclassified_as_coverage_gap():
    class BrokenSource:
        def records_for_universe(self, universe_spec, backtest_start, backtest_end):
            raise ValueError("snapshot_date parser failure")

    universe = make_backtest_universe()
    with pytest.raises(ValueError, match="parser failure"):
        PointInTimeUniverseBuilder(BrokenSource()).build_membership_snapshot(
            universe, date(2020, 1, 1), date(2020, 12, 31)
        )
