from __future__ import annotations

from datetime import date
import hashlib
import json

import pytest

from backend.services import strategy_scoped_pit_universe as scope_module
from backend.services.strategy_scoped_pit_universe import (
    StrategyScopedPITUniverse,
    build_scope_snapshot_manifest,
    canonical_daily_members_bytes,
    materialize_daily_membership,
    publish_scope_snapshot,
)


TEMPLATE = {
    "template_id": "relative_strength_rotation_shsz_sw2021_v3",
    "template_version": "v3_shsz_sw2021_pit_12m_liquidity20d",
    "template_hash": "f7c0fd8123f62f37118cb947e1735861374435f8707e01b06d788a8ec4df39c1",
    "data_requirements_hash": "ef2ab5b1dafe4349f305b52733a7dcb018a2961464dfbc6542a10e34805d041d",
}
MEMBERSHIP = {
    "id": "pims_traderlens_v2_shsz_sw2021_pit_005",
    "manifest_sha256": "32f58adbca49fb89dfeb54ceeb4ac9b27b6a26c55e0c9cfeae7a8fcaf3683f10",
    "records_sha256": "2e8c922de9f198ab18a6b38743a01f4343fbf52b876da84026389d3ffd11eec0",
}
SOURCE_BINDINGS = {
    "strategy_scoped_materializer": {
        "path": "backend/services/strategy_scoped_pit_universe.py",
        "sha256": "1" * 64,
    },
    "b6_preflight_consumer": {
        "path": "backend/services/b6_validation_worker.py",
        "sha256": "2" * 64,
    },
    "b6_same_draw_consumer": {
        "path": "backend/services/b6_same_draw_executor.py",
        "sha256": "3" * 64,
    },
    "strategy_template_library": {
        "path": "backend/services/strategy_template_library.py",
        "sha256": "4" * 64,
    },
}
CALENDAR = {
    "artifact_id": "shsz_common_trade_calendar_v1",
    "date_set_sha256": "5" * 64,
}
LIFECYCLE_BINDING = {
    "artifact_id": "stock_basic_lifecycle_fixture",
    "manifest_repo_relative_path": "data/pit/qualification_successors/fixture/manifest.json",
    "manifest_sha256": "6" * 64,
    "root_repo_relative": "data/pit/stock_basic_fixture",
    "stock_basic_files": [
        {"path": f"list_status={status}/part.parquet", "sha256": str(index) * 64}
        for index, status in enumerate(("D", "L", "P"), start=7)
    ],
    "comparison_artifact_id": "comparison_fixture",
    "comparison_manifest_sha256": "8" * 64,
}


def test_daily_materialization_excludes_only_bj_and_keeps_closed_end_day():
    day1 = date(2026, 3, 20)
    day2 = date(2026, 3, 23)
    raw_records = [
        {"symbol": "600000.SH", "effective_from": day1, "effective_to": None},
        {"symbol": "000001.SZ", "effective_from": day1, "effective_to": None},
        {"symbol": "832317.BJ", "effective_from": day1, "effective_to": None},
        {"symbol": "920001.BJ", "effective_from": day1, "effective_to": day1},
    ]
    before = json.dumps(raw_records, default=str, sort_keys=True)

    materialized = materialize_daily_membership(raw_records, (day1, day2), ["SH", "SZ"])

    assert materialized.members_by_date[day1] == ("000001.SZ", "600000.SH")
    assert materialized.members_by_date[day2] == ("000001.SZ", "600000.SH")
    assert materialized.daily_summary[0]["excluded_by_market"] == {"BJ": 2}
    assert materialized.daily_summary[1]["excluded_by_market"] == {"BJ": 1}
    assert json.dumps(raw_records, default=str, sort_keys=True) == before


def test_scope_snapshot_identity_binds_template_source_membership_and_daily_hashes(tmp_path):
    day = date(2026, 3, 20)
    materialized = materialize_daily_membership(
        [
            {"symbol": "600000.SH", "effective_from": day, "effective_to": None},
            {"symbol": "000001.SZ", "effective_from": day, "effective_to": None},
            {"symbol": "832317.BJ", "effective_from": day, "effective_to": None},
        ],
        (day,),
        ["SH", "SZ"],
    )
    members_bytes = canonical_daily_members_bytes(materialized.members_by_date)
    members_sha = hashlib.sha256(members_bytes).hexdigest()
    common = dict(
        template_binding=TEMPLATE,
        membership_binding=MEMBERSHIP,
        market_scope=["SH", "SZ"],
        oos_window={"start": day.isoformat(), "end": day.isoformat()},
        calendar_binding=CALENDAR,
        stock_basic_lifecycle_binding=LIFECYCLE_BINDING,
        source_bindings=SOURCE_BINDINGS,
        daily_summary=materialized.daily_summary,
        daily_members_sha256=members_sha,
    )

    manifest = build_scope_snapshot_manifest(**common)
    same_manifest = build_scope_snapshot_manifest(**common)
    other_source = build_scope_snapshot_manifest(
        **{**common, "membership_binding": dict(MEMBERSHIP, records_sha256="a" * 64)}
    )
    artifact = publish_scope_snapshot(tmp_path, manifest, members_bytes)

    assert manifest == same_manifest
    assert manifest["snapshot_id"] == same_manifest["snapshot_id"]
    assert manifest["snapshot_id"] != other_source["snapshot_id"]
    assert artifact["status"] == "published"
    assert artifact["manifest_sha256"]
    assert artifact["daily_members_sha256"] == members_sha

    loaded = StrategyScopedPITUniverse(
        RawUniverse(),
        scope_snapshot_dir=tmp_path / manifest["snapshot_id"],
        expected_binding=artifact["binding"],
    )
    assert loaded.symbols_as_of(day) == ("000001.SZ", "600000.SH")


def test_daily_materialization_applies_formal_lifecycle_as_of_and_retains_unknowns():
    day1 = date(2026, 3, 20)
    day2 = date(2026, 3, 23)
    day3 = date(2026, 3, 24)
    records = [
        {"symbol": "600000.SH", "effective_from": day1, "effective_to": None},
        {"symbol": "600001.SH", "effective_from": day1, "effective_to": None},
        {"symbol": "600002.SH", "effective_from": day1, "effective_to": None},
        {"symbol": "600003.SH", "effective_from": day1, "effective_to": None},
    ]
    lifecycle_dates = {
        "600000.SH": (date(2000, 1, 1), day3),
        "600001.SH": (day2, None),
        "600002.SH": (date(2000, 1, 1), day2),
    }

    materialized = materialize_daily_membership(
        records,
        (day1, day2, day3),
        ["SH", "SZ"],
        lifecycle_dates=lifecycle_dates,
    )

    assert materialized.members_by_date[day1] == ("600000.SH", "600002.SH", "600003.SH")
    assert materialized.members_by_date[day2] == ("600000.SH", "600001.SH", "600003.SH")
    assert materialized.members_by_date[day3] == ("600001.SH", "600003.SH")
    assert materialized.daily_summary[0]["excluded_by_lifecycle"] == {
        "delisted": 0,
        "not_yet_listed": 1,
    }
    assert materialized.daily_summary[1]["excluded_by_lifecycle"] == {
        "delisted": 1,
        "not_yet_listed": 0,
    }
    assert materialized.daily_summary[0]["unresolved_lifecycle_symbols"] == ["600003.SH"]


class RawUniverse:
    def common_trading_dates(self, _start, _end):
        return ()


def test_scoped_universe_rejects_snapshot_manifest_tampering(tmp_path):
    day = date(2026, 3, 20)
    materialized = materialize_daily_membership(
        [{"symbol": "600000.SH", "effective_from": day, "effective_to": None}],
        (day,),
        ["SH", "SZ"],
    )
    members_bytes = canonical_daily_members_bytes(materialized.members_by_date)
    manifest = build_scope_snapshot_manifest(
        template_binding=TEMPLATE,
        membership_binding=MEMBERSHIP,
        market_scope=["SH", "SZ"],
        oos_window={"start": day.isoformat(), "end": day.isoformat()},
        calendar_binding=CALENDAR,
        stock_basic_lifecycle_binding=LIFECYCLE_BINDING,
        source_bindings=SOURCE_BINDINGS,
        daily_summary=materialized.daily_summary,
        daily_members_sha256=hashlib.sha256(members_bytes).hexdigest(),
    )
    artifact = publish_scope_snapshot(tmp_path, manifest, members_bytes)
    scope_dir = tmp_path / manifest["snapshot_id"]
    manifest_path = scope_dir / "manifest.json"
    tampered = json.loads(manifest_path.read_text(encoding="utf-8"))
    tampered["market_scope"] = ["SH", "SZ", "BJ"]
    manifest_path.write_text(json.dumps(tampered), encoding="utf-8")

    with pytest.raises(ValueError, match="manifest sidecar"):
        StrategyScopedPITUniverse(
            RawUniverse(),
            scope_snapshot_dir=scope_dir,
            expected_binding=artifact["binding"],
        )


def test_daily_materialization_fails_closed_on_unknown_market_suffix():
    day = date(2026, 3, 20)
    with pytest.raises(ValueError, match="unsupported membership market"):
        materialize_daily_membership(
            [{"symbol": "100001.XY", "effective_from": day, "effective_to": None}],
            (day,),
            ["SH", "SZ"],
        )


def _t00018_alias_fixture():
    day = date(2000, 7, 19)
    source = "SW2021_801170.SI_is_new_Y"
    pims_id = MEMBERSHIP["id"]
    records = [
        {"symbol": "T00018.SH", "effective_from": day, "effective_to": None, "source": source, "snapshot_id": pims_id},
        {"symbol": "600018.SH", "effective_from": day, "effective_to": None, "source": source, "snapshot_id": pims_id},
        {"symbol": "600000.SH", "effective_from": day, "effective_to": None, "source": "SW2021_801010.SI_is_new_Y", "snapshot_id": pims_id},
    ]
    shared_source_row = {
        "l1_code": "801170.SI",
        "l2_code": "801992.SI",
        "l3_code": "851711.SI",
        "in_date": "20000719",
        "out_date": None,
        "is_new": "Y",
    }
    partition_rows = [
        {**shared_source_row, "ts_code": "T00018.SH"},
        {**shared_source_row, "ts_code": "600018.SH"},
    ]
    partition_hash = "bae438e80e62c946d46b58482646fa4ab9fc7f3e79aa39702222ff0ae8c5f991"
    evidence = {
        "source_manifest_sha256": "a38b3cc6be947b290078fe637466991ee8d13dee2794d398fb709d5c4c3826f3",
        "source_partition_sha256": partition_hash,
        "source_partition_row_count": 144,
        "source_partition_audit": {
            "partition_name": "SW2021_801170.SI_is_new_Y.parquet",
            "source_manifest_sha256": partition_hash,
            "source_file_sha256": partition_hash,
            "source_record_count": 144,
            "source_file_row_count": 144,
            "published_record_count": 144,
            "taxonomy_status": "sw2021_accepted",
        },
        "partition_rows": partition_rows,
    }
    return records, evidence


def _apply_bound_t00018_alias(records, evidence):
    correction = getattr(scope_module, "_apply_t00018_alias_correction", None)
    assert callable(correction), "hash-bound T00018 alias correction is missing"
    return correction(records, evidence)


def test_bound_t00018_alias_correction_maps_one_duplicate_and_records_provenance():
    records, evidence = _t00018_alias_fixture()
    original = [dict(row) for row in records]

    corrected, corrections = _apply_bound_t00018_alias(records, evidence)
    assert len(corrections) == 1
    correction = corrections[0]

    assert [row["symbol"] for row in corrected].count("T00018.SH") == 0
    assert [row["symbol"] for row in corrected].count("600018.SH") == 1
    assert records[0]["symbol"] == "T00018.SH"  # Raw input remains untouched.
    assert correction["source_symbol"] == "T00018.SH"
    assert correction["canonical_symbol"] == "600018.SH"
    assert correction["source_partition_sha256"] == evidence["source_partition_sha256"]
    assert correction["source_manifest_sha256"] == evidence["source_manifest_sha256"]
    assert correction["deduplicated_membership_rows"] == 1
    assert records == original


def test_bound_t00018_alias_correction_fails_closed_when_partition_hash_changes():
    records, evidence = _t00018_alias_fixture()
    evidence["source_partition_sha256"] = "0" * 64

    with pytest.raises(ValueError, match="source partition hash"):
        _apply_bound_t00018_alias(records, evidence)


def test_hash_only_partition_sidecar_must_match_recomputed_hash(tmp_path):
    source = tmp_path / "source.parquet"
    content = b"bound source partition"
    source.write_bytes(content)
    expected_hash = hashlib.sha256(content).hexdigest()
    sidecar = source.with_name(source.name + ".sha256")
    sidecar.write_text(expected_hash, encoding="ascii")
    checker = getattr(scope_module, "_check_hash_only_partition_sidecar", None)
    assert callable(checker), "pinned hash-only partition sidecar checker is missing"

    assert checker(source, expected_hash) == expected_hash
    sidecar.write_text(expected_hash + "  source.parquet\n", encoding="ascii")
    with pytest.raises(ValueError, match="sidecar mismatch"):
        checker(source, expected_hash)


def test_bound_t00018_alias_correction_fails_closed_when_intervals_do_not_match():
    records, evidence = _t00018_alias_fixture()
    records[1]["effective_from"] = date(2006, 10, 26)

    with pytest.raises(ValueError, match="same source interval"):
        _apply_bound_t00018_alias(records, evidence)


def test_scope_snapshot_identity_binds_the_exact_alias_correction():
    day = date(2026, 3, 20)
    materialized = materialize_daily_membership(
        [{"symbol": "600018.SH", "effective_from": day, "effective_to": None}],
        (day,),
        ["SH", "SZ"],
    )
    members = canonical_daily_members_bytes(materialized.members_by_date)
    common = dict(
        template_binding=TEMPLATE,
        membership_binding=MEMBERSHIP,
        market_scope=["SH", "SZ"],
        oos_window={"start": day.isoformat(), "end": day.isoformat()},
        calendar_binding=CALENDAR,
        stock_basic_lifecycle_binding=LIFECYCLE_BINDING,
        source_bindings=SOURCE_BINDINGS,
        daily_summary=materialized.daily_summary,
        daily_members_sha256=hashlib.sha256(members).hexdigest(),
    )
    records, evidence = _t00018_alias_fixture()
    _, corrections = _apply_bound_t00018_alias(records, evidence)

    unchanged = build_scope_snapshot_manifest(**common)
    corrected = build_scope_snapshot_manifest(
        **common, membership_corrections=corrections
    )

    assert corrected["membership_corrections"] == corrections
    assert corrected["snapshot_id"] != unchanged["snapshot_id"]


def test_scope_snapshot_identity_binds_lifecycle_partitions_and_rule():
    day = date(2026, 3, 20)
    materialized = materialize_daily_membership(
        [{"symbol": "600018.SH", "effective_from": day, "effective_to": None}],
        (day,),
        ["SH", "SZ"],
    )
    members = canonical_daily_members_bytes(materialized.members_by_date)
    common = dict(
        template_binding=TEMPLATE,
        membership_binding=MEMBERSHIP,
        market_scope=["SH", "SZ"],
        oos_window={"start": day.isoformat(), "end": day.isoformat()},
        calendar_binding=CALENDAR,
        stock_basic_lifecycle_binding=LIFECYCLE_BINDING,
        source_bindings=SOURCE_BINDINGS,
        daily_summary=materialized.daily_summary,
        daily_members_sha256=hashlib.sha256(members).hexdigest(),
    )

    pinned = build_scope_snapshot_manifest(**common)
    changed_files = [dict(row) for row in LIFECYCLE_BINDING["stock_basic_files"]]
    changed_files[1]["sha256"] = "9" * 64
    different_partition = build_scope_snapshot_manifest(
        **{
            **common,
            "stock_basic_lifecycle_binding": {
                **LIFECYCLE_BINDING,
                "stock_basic_files": changed_files,
            },
        }
    )

    assert pinned["lifecycle_rule"]["rule_id"] == scope_module.LIFECYCLE_RULE_ID
    assert pinned["stock_basic_lifecycle"] == LIFECYCLE_BINDING
    assert pinned["snapshot_id"] != different_partition["snapshot_id"]


def test_scope_publication_uses_explicit_code_and_artifact_roots(monkeypatch, tmp_path):
    code_root = scope_module.Path(__file__).resolve().parents[1]
    artifact_root = tmp_path / "trusted-artifacts"
    artifact_root.mkdir()
    output_root = artifact_root / "data" / "pit" / "strategy_scoped_universe_snapshots"
    manifest = {"snapshot_id": "ssu_explicit_roots"}
    calls = []

    monkeypatch.setattr(
        scope_module,
        "_trusted_source_inputs",
        lambda source_root, *, artifact_root: calls.append(
            ("inputs", source_root, artifact_root)
        ) or {},
    )
    monkeypatch.setattr(
        scope_module,
        "_build_from_trusted_inputs",
        lambda _inputs: (manifest, b"members"),
    )
    monkeypatch.setattr(
        scope_module,
        "publish_scope_snapshot",
        lambda target_root, _manifest, _members: calls.append(
            ("publish", target_root)
        ) or {"status": "published", "manifest_sha256": "a" * 64},
    )
    monkeypatch.setattr(
        scope_module,
        "verify_scope_snapshot",
        lambda source_root, snapshot_dir, *, artifact_root, **_kwargs: calls.append(
            ("verify", source_root, artifact_root, snapshot_dir)
        ) or {"status": "verified", "snapshot_id": manifest["snapshot_id"]},
    )

    result = scope_module.publish_verified_scope_snapshot(
        code_root,
        artifact_root,
        output_root=output_root,
    )

    assert calls[0] == ("inputs", code_root, artifact_root)
    assert calls[1] == ("publish", output_root)
    assert calls[2] == (
        "verify",
        code_root,
        artifact_root,
        output_root / manifest["snapshot_id"],
    )
    assert result["verification"]["snapshot_id"] == manifest["snapshot_id"]
