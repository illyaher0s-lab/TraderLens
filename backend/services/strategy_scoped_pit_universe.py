"""Immutable, strategy-scoped materialization of a verified raw PIT universe."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from typing import Any, Mapping

import pyarrow.parquet as pq


SCOPE_SCHEMA = "strategy_scoped_pit_universe.v2"
SCOPE_ALGORITHM_ID = "closed_inclusive_daily_membership_with_formal_lifecycle_and_verified_alias_correction.v3"
SCOPE_ALGORITHM_VERSION = "3"
SCOPE_SNAPSHOT_ROOT = Path("data/pit/strategy_scoped_universe_snapshots")
MEMBERSHIP_ID = "pims_traderlens_v2_shsz_sw2021_pit_005"
MEMBERSHIP_MANIFEST_SHA256 = "32f58adbca49fb89dfeb54ceeb4ac9b27b6a26c55e0c9cfeae7a8fcaf3683f10"
MEMBERSHIP_RECORDS_SHA256 = "2e8c922de9f198ab18a6b38743a01f4343fbf52b876da84026389d3ffd11eec0"
T00018_ALIAS_SOURCE_MANIFEST_SHA256 = "a38b3cc6be947b290078fe637466991ee8d13dee2794d398fb709d5c4c3826f3"
T00018_ALIAS_SOURCE_PARTITION_SHA256 = "bae438e80e62c946d46b58482646fa4ab9fc7f3e79aa39702222ff0ae8c5f991"
T00018_ALIAS_SOURCE_PARTITION_NAME = "SW2021_801170.SI_is_new_Y.parquet"
T00018_ALIAS_SOURCE_PARTITION_PATH = (
    "data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal/"
    "sw_l1_membership/SW2021_801170.SI_is_new_Y.parquet"
)
T00018_ALIAS_CORRECTION_RULE_ID = "sw2021_verified_alias.T00018_SH_to_600018_SH.v1"
LIFECYCLE_RULE_ID = "formal_stock_basic.list_date_lte_day_lt_delist_date.v1"
LIFECYCLE_RULE = {
    "rule_id": LIFECYCLE_RULE_ID,
    "eligible_when": "list_date <= day and (delist_date is null or day < delist_date)",
    "unknown_lifecycle": "retain_in_scope_and_fail_closed_in_b6",
}
TEMPLATE_BINDING = {
    "template_id": "relative_strength_rotation_shsz_sw2021_v3",
    "template_version": "v3_shsz_sw2021_pit_12m_liquidity20d",
    "template_hash": "f7c0fd8123f62f37118cb947e1735861374435f8707e01b06d788a8ec4df39c1",
    "data_requirements_hash": "ef2ab5b1dafe4349f305b52733a7dcb018a2961464dfbc6542a10e34805d041d",
}
PROTOCOL_BINDING = {
    "protocol_snapshot_id": "8770c56c5a69ef128442c0f593f9e4b081a6b13c69744b27171b27cc8c8b7bbe",
    "strategy_revision_id": "6440ffc03a742f4d4632078481cf3abf171eafb1a24f2bc69bc6f352d1b19ebc",
    "shared_oos_window_id": "58d07f5b2a348eb1",
    "protocol_profile": "b6_coverage_bound",
    "data_snapshot_id": "v3ds_d73256081de82e8a",
    "data_snapshot_hash": "d73256081de82e8a764ea2394d613af820fd1b82e773c48156ca2463a452c80e",
    "strategy_config_hash": "54b6f23f5558bd6f4b083e18c99364f98359945d5f7b6723f58cd72aaa2a79df",
    "data_requirements_hash": "ef2ab5b1dafe4349f305b52733a7dcb018a2961464dfbc6542a10e34805d041d",
    "oos_window": {"start": "2026-03-20", "end": "2026-07-10"},
}
CALENDAR_BINDING = {
    "artifact_id": "shsz_common_trade_calendar_v1",
    "path": "data/pit/shsz_common_trade_calendars/shsz_common_trade_calendar_v1",
    "manifest_sha256": "ae019cf45072d8274f915837a03d1824c02a69159df473512dbce2e925586785",
    "parquet_sha256": "8b41168bcd1c39d52ed00f9717ba6fa5330e5b4e15de78068446abe8647f2364",
    "date_set_sha256": "62b6880c9acc381d273ceee40c900a486c3f83488600c042c43ce1d8f9cbb194",
}
_MARKET_SUFFIXES = {"SH", "SZ", "BJ"}


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _sha_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _sha_file(path: Path) -> str:
    return _sha_bytes(Path(path).read_bytes())


def _parse_day(raw: Any, *, label: str) -> date:
    if isinstance(raw, datetime) or not isinstance(raw, (date, str)):
        raise ValueError(f"invalid {label}")
    if isinstance(raw, date):
        return raw
    try:
        if len(raw) == 8 and raw.isdigit():
            return date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))
        return date.fromisoformat(raw)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"invalid {label}") from exc


def _market(symbol: Any) -> str:
    if not isinstance(symbol, str) or symbol.count(".") != 1:
        raise ValueError(f"unsupported membership market: {symbol!r}")
    code, suffix = symbol.rsplit(".", 1)
    if len(code) != 6 or not code.isdigit() or suffix not in _MARKET_SUFFIXES:
        raise ValueError(f"unsupported membership market: {symbol!r}")
    return suffix


def _t00018_alias_manifest_entry() -> dict[str, Any]:
    return {
        "rule_id": T00018_ALIAS_CORRECTION_RULE_ID,
        "source_manifest_sha256": T00018_ALIAS_SOURCE_MANIFEST_SHA256,
        "source_partition_name": T00018_ALIAS_SOURCE_PARTITION_NAME,
        "source_partition_path": T00018_ALIAS_SOURCE_PARTITION_PATH,
        "source_partition_sha256": T00018_ALIAS_SOURCE_PARTITION_SHA256,
        "source_partition_row_count": 144,
        "source_symbol": "T00018.SH",
        "canonical_symbol": "600018.SH",
        "source_row_count": 1,
        "canonical_row_count": 1,
        "effective_from": "2000-07-19",
        "effective_to": None,
        "deduplicated_membership_rows": 1,
    }


def _apply_t00018_alias_correction(
    records: list[Mapping[str, Any]], evidence: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Apply one pinned alias correction after its source evidence is verified."""
    expected = _t00018_alias_manifest_entry()
    if not isinstance(records, list) or not isinstance(evidence, Mapping):
        raise ValueError("T00018 alias correction evidence is invalid")
    if (
        evidence.get("source_manifest_sha256")
        != T00018_ALIAS_SOURCE_MANIFEST_SHA256
        or evidence.get("source_partition_sha256")
        != T00018_ALIAS_SOURCE_PARTITION_SHA256
        or evidence.get("source_partition_row_count") != 144
    ):
        raise ValueError("T00018 alias source partition hash/manifest/row count mismatch")

    audit = evidence.get("source_partition_audit")
    expected_audit = {
        "partition_name": T00018_ALIAS_SOURCE_PARTITION_NAME,
        "source_manifest_sha256": T00018_ALIAS_SOURCE_PARTITION_SHA256,
        "source_file_sha256": T00018_ALIAS_SOURCE_PARTITION_SHA256,
        "source_record_count": 144,
        "source_file_row_count": 144,
        "published_record_count": 144,
        "taxonomy_status": "sw2021_accepted",
    }
    if not isinstance(audit, Mapping) or any(
        audit.get(key) != value for key, value in expected_audit.items()
    ):
        raise ValueError("T00018 alias source partition audit mismatch")

    partition_rows = evidence.get("partition_rows")
    if not isinstance(partition_rows, list):
        raise ValueError("T00018 alias source partition rows are missing")
    expected_source_rows = {
        "T00018.SH": {
            "l1_code": "801170.SI",
            "l2_code": "801992.SI",
            "l3_code": "851711.SI",
            "in_date": "20000719",
            "out_date": None,
            "is_new": "Y",
        },
        "600018.SH": {
            "l1_code": "801170.SI",
            "l2_code": "801992.SI",
            "l3_code": "851711.SI",
            "in_date": "20000719",
            "out_date": None,
            "is_new": "Y",
        },
    }
    selected_source_rows = [
        row for row in partition_rows
        if isinstance(row, Mapping) and row.get("ts_code") in expected_source_rows
    ]
    source_rows_by_symbol: dict[str, list[Mapping[str, Any]]] = {
        symbol: [row for row in selected_source_rows if row.get("ts_code") == symbol]
        for symbol in expected_source_rows
    }
    if any(len(rows) != 1 for rows in source_rows_by_symbol.values()):
        raise ValueError("T00018 alias rows are not unique in the bound source partition")
    for symbol, expected_fields in expected_source_rows.items():
        source_row = source_rows_by_symbol[symbol][0]
        if any(source_row.get(key) != value for key, value in expected_fields.items()):
            raise ValueError("T00018 alias source rows do not have the bound interval/taxonomy")

    t_records = [row for row in records if row.get("symbol") == "T00018.SH"]
    canonical_records = [
        row for row in records
        if row.get("symbol") == "600018.SH"
        and row.get("source") == "SW2021_801170.SI_is_new_Y"
    ]
    if len(t_records) != 1 or len(canonical_records) != 1:
        raise ValueError("T00018 alias membership rows are not unique")
    t_record = t_records[0]
    canonical_record = canonical_records[0]
    expected_interval = {
        "effective_from": date(2000, 7, 19),
        "effective_to": None,
    }
    for row in (t_record, canonical_record):
        normalized_start = _parse_day(
            row.get("effective_from"), label="T00018 alias effective_from"
        )
        raw_end = row.get("effective_to")
        normalized_end = (
            None if raw_end is None else _parse_day(raw_end, label="T00018 alias effective_to")
        )
        if (
            normalized_start != expected_interval["effective_from"]
            or normalized_end != expected_interval["effective_to"]
            or row.get("source") != "SW2021_801170.SI_is_new_Y"
            or row.get("snapshot_id") != MEMBERSHIP_ID
        ):
            raise ValueError("T00018 alias membership rows do not have the same source interval")

    corrected = [dict(row) for row in records if row is not t_record]
    return corrected, [expected]


@dataclass(frozen=True)
class MaterializedDailyMembership:
    members_by_date: dict[date, tuple[str, ...]]
    daily_summary: tuple[dict[str, Any], ...]


def _daily_hash(symbols: tuple[str, ...]) -> str:
    return _sha_bytes(_canonical(list(symbols)))


def materialize_daily_membership(
    records: list[Mapping[str, Any]],
    trading_dates: tuple[date, ...] | list[date],
    market_scope: list[str] | tuple[str, ...],
    *,
    lifecycle_dates: Mapping[str, tuple[date, date | None]] | None = None,
) -> MaterializedDailyMembership:
    """Materialize closed-inclusive membership intersected with formal lifecycle as-of."""
    scope = tuple(market_scope)
    if not scope or len(scope) != len(set(scope)) or any(market not in {"SH", "SZ"} for market in scope):
        raise ValueError("unsupported strategy market scope")
    if tuple(sorted(scope)) != scope:
        raise ValueError("strategy market scope must be sorted")
    days = tuple(trading_dates)
    if not days or any(not isinstance(day, date) or isinstance(day, datetime) for day in days):
        raise ValueError("trading dates must be non-empty dates")
    if days != tuple(sorted(set(days))):
        raise ValueError("trading dates must be sorted and unique")
    if lifecycle_dates is not None:
        if not isinstance(lifecycle_dates, Mapping):
            raise ValueError("formal stock lifecycle dates must be a mapping")
        for symbol, value in lifecycle_dates.items():
            if (
                not isinstance(symbol, str)
                or not isinstance(value, tuple)
                or len(value) != 2
                or not isinstance(value[0], date)
                or isinstance(value[0], datetime)
                or (value[1] is not None and (not isinstance(value[1], date) or isinstance(value[1], datetime)))
                or (value[1] is not None and value[1] < value[0])
            ):
                raise ValueError(f"invalid formal stock lifecycle dates: {symbol!r}")

    parsed_records: list[tuple[str, str, date, date | None]] = []
    for row in records:
        if not isinstance(row, Mapping):
            raise ValueError("membership record must be an object")
        symbol = row.get("symbol")
        market = _market(symbol)
        start = _parse_day(row.get("effective_from"), label="membership effective_from")
        raw_end = row.get("effective_to")
        end = None if raw_end is None else _parse_day(raw_end, label="membership effective_to")
        if end is not None and end < start:
            raise ValueError(f"invalid closed-inclusive membership interval: {symbol}")
        parsed_records.append((symbol, market, start, end))

    members_by_date: dict[date, tuple[str, ...]] = {}
    summaries: list[dict[str, Any]] = []
    for day in days:
        selected: set[str] = set()
        excluded: dict[str, set[str]] = {}
        excluded_by_lifecycle = {"delisted": set(), "not_yet_listed": set()}
        unresolved_lifecycle: set[str] = set()
        for symbol, market, start, end in parsed_records:
            if start <= day and (end is None or day <= end):
                if market not in scope:
                    excluded.setdefault(market, set()).add(symbol)
                    continue
                if lifecycle_dates is not None:
                    lifecycle = lifecycle_dates.get(symbol)
                    if lifecycle is None:
                        # Preserve the member so B6 reports the missing lifecycle
                        # evidence and blocks; never turn an unknown into an exclusion.
                        unresolved_lifecycle.add(symbol)
                    else:
                        list_date, delist_date = lifecycle
                        if day < list_date:
                            excluded_by_lifecycle["not_yet_listed"].add(symbol)
                            continue
                        if delist_date is not None and day >= delist_date:
                            excluded_by_lifecycle["delisted"].add(symbol)
                            continue
                selected.add(symbol)
        members = tuple(sorted(selected))
        members_by_date[day] = members
        summaries.append(
            {
                "date": day.isoformat(),
                "member_count": len(members),
                "members_sha256": _daily_hash(members),
                "excluded_by_market": {
                    market: len(symbols) for market, symbols in sorted(excluded.items())
                },
                "excluded_by_lifecycle": {
                    reason: len(symbols)
                    for reason, symbols in sorted(excluded_by_lifecycle.items())
                },
                "unresolved_lifecycle_symbols": sorted(unresolved_lifecycle),
            }
        )
    return MaterializedDailyMembership(members_by_date, tuple(summaries))


def canonical_daily_members_bytes(members_by_date: Mapping[date | str, tuple[str, ...] | list[str]]) -> bytes:
    normalized: dict[str, list[str]] = {}
    for raw_day, raw_members in members_by_date.items():
        day = _parse_day(raw_day, label="daily membership date")
        key = day.isoformat()
        if key in normalized:
            raise ValueError("duplicate daily membership date")
        if not isinstance(raw_members, (tuple, list)):
            raise ValueError("daily members must be a sequence")
        members = list(raw_members)
        if members != sorted(set(members)):
            raise ValueError("daily members must be sorted and unique")
        for symbol in members:
            if _market(symbol) not in {"SH", "SZ"}:
                raise ValueError("daily members contain an out-of-scope market")
        normalized[key] = members
    return _canonical(dict(sorted(normalized.items())))


def _scope_identity_core(manifest: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in manifest.items()
        if key not in {"snapshot_id", "scope_identity_sha256"}
    }


def _finalize_manifest(core: Mapping[str, Any]) -> dict[str, Any]:
    identity_sha = _sha_bytes(_canonical(dict(core)))
    return {
        **dict(core),
        "scope_identity_sha256": identity_sha,
        "snapshot_id": f"ssu_{identity_sha[:24]}",
    }


def build_scope_snapshot_manifest(
    *,
    template_binding: Mapping[str, Any],
    membership_binding: Mapping[str, Any],
    market_scope: list[str] | tuple[str, ...],
    oos_window: Mapping[str, Any],
    calendar_binding: Mapping[str, Any],
    stock_basic_lifecycle_binding: Mapping[str, Any],
    source_bindings: Mapping[str, Mapping[str, Any]],
    daily_summary: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...],
    daily_members_sha256: str,
    protocol_binding: Mapping[str, Any] | None = None,
    membership_corrections: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...] = (),
) -> dict[str, Any]:
    scope = list(market_scope)
    if scope != ["SH", "SZ"]:
        raise ValueError("frozen strategy market scope mismatch")
    if dict(template_binding) != TEMPLATE_BINDING:
        raise ValueError("frozen strategy template binding mismatch")
    lifecycle = dict(stock_basic_lifecycle_binding)
    if (
        not isinstance(lifecycle.get("artifact_id"), str)
        or not lifecycle.get("artifact_id")
        or not isinstance(lifecycle.get("manifest_repo_relative_path"), str)
        or not lifecycle["manifest_repo_relative_path"].endswith("/manifest.json")
        or not isinstance(lifecycle.get("root_repo_relative"), str)
        or not lifecycle["root_repo_relative"].startswith("data/pit/")
        or not isinstance(lifecycle.get("manifest_sha256"), str)
        or len(lifecycle["manifest_sha256"]) != 64
        or not isinstance(lifecycle.get("comparison_artifact_id"), str)
        or not isinstance(lifecycle.get("comparison_manifest_sha256"), str)
        or len(lifecycle["comparison_manifest_sha256"]) != 64
    ):
        raise ValueError("formal stock_basic lifecycle binding is invalid")
    life_files = lifecycle.get("stock_basic_files")
    expected_life_paths = {
        "list_status=D/part.parquet",
        "list_status=L/part.parquet",
        "list_status=P/part.parquet",
    }
    if (
        not isinstance(life_files, list)
        or {row.get("path") for row in life_files if isinstance(row, Mapping)} != expected_life_paths
        or len(life_files) != len(expected_life_paths)
        or any(
            not isinstance(row, Mapping)
            or not isinstance(row.get("sha256"), str)
            or len(row["sha256"]) != 64
            or any(char not in "0123456789abcdef" for char in row["sha256"])
            for row in life_files
        )
    ):
        raise ValueError("formal stock_basic lifecycle partition binding is invalid")
    if (
        set(membership_binding) != {"id", "manifest_sha256", "records_sha256"}
        or not isinstance(membership_binding.get("id"), str)
        or any(
            not isinstance(membership_binding.get(key), str)
            or len(membership_binding[key]) != 64
            or any(char not in "0123456789abcdef" for char in membership_binding[key])
            for key in ("manifest_sha256", "records_sha256")
        )
    ):
        raise ValueError("raw PIT membership binding is invalid")
    if not isinstance(daily_members_sha256, str) or len(daily_members_sha256) != 64:
        raise ValueError("daily membership file hash is invalid")
    bindings = {name: dict(value) for name, value in source_bindings.items()}
    required_sources = {
        "strategy_scoped_materializer",
        "formal_pit_partition_adapter",
        "b6_preflight_consumer",
        "b6_same_draw_consumer",
        "strategy_template_library",
    }
    if set(bindings) != required_sources:
        raise ValueError("strategy scope source bindings are incomplete")
    for name, binding in bindings.items():
        if (
            not isinstance(binding.get("path"), str)
            or not isinstance(binding.get("sha256"), str)
            or len(binding["sha256"]) != 64
        ):
            raise ValueError(f"invalid source binding: {name}")
    adapter_binding = bindings["formal_pit_partition_adapter"]
    if (
        adapter_binding["path"] != "backend/services/formal_pit_partition_adapter.py"
        or any(char not in "0123456789abcdef" for char in adapter_binding["sha256"])
    ):
        raise ValueError("formal PIT partition adapter source binding is invalid")
    normalized_window = {
        "start": _parse_day(oos_window.get("start"), label="OOS start").isoformat(),
        "end": _parse_day(oos_window.get("end"), label="OOS end").isoformat(),
    }
    if normalized_window["start"] > normalized_window["end"]:
        raise ValueError("invalid OOS window")
    summary = [dict(row) for row in daily_summary]
    if not summary or [row.get("date") for row in summary] != sorted(
        {row.get("date") for row in summary}
    ):
        raise ValueError("daily membership summary dates are invalid")
    if summary[0]["date"] < normalized_window["start"] or summary[-1]["date"] > normalized_window["end"]:
        raise ValueError("daily membership summary is outside the OOS window")
    if protocol_binding is not None and dict(protocol_binding) != PROTOCOL_BINDING:
        raise ValueError("frozen protocol binding mismatch")
    corrections = [dict(row) for row in membership_corrections]
    if corrections not in ([], [_t00018_alias_manifest_entry()]):
        raise ValueError("strategy membership correction is not an approved exact alias rule")
    core = {
        "schema_version": SCOPE_SCHEMA,
        "status": "published",
        "authorization_scope": "strategy_scoped_pit_universe_binding_only",
        "not_authorized_for_b6_oos_gate_promotion_signal": True,
        "algorithm": {
            "algorithm_id": SCOPE_ALGORITHM_ID,
            "version": SCOPE_ALGORITHM_VERSION,
            "source_path": bindings["strategy_scoped_materializer"]["path"],
            "source_sha256": bindings["strategy_scoped_materializer"]["sha256"],
            "interval_semantics": "closed_inclusive",
        },
        "template": dict(template_binding),
        "membership": dict(membership_binding),
        "membership_corrections": corrections,
        "stock_basic_lifecycle": lifecycle,
        "lifecycle_rule": dict(LIFECYCLE_RULE),
        "market_scope": scope,
        "protocol": None if protocol_binding is None else dict(protocol_binding),
        "oos_window": normalized_window,
        "calendar": dict(calendar_binding),
        "source_bindings": bindings,
        "daily_summary": summary,
        "daily_members_sha256": daily_members_sha256,
    }
    return _finalize_manifest(core)


def _manifest_bytes(manifest: Mapping[str, Any]) -> bytes:
    if dict(manifest) != _finalize_manifest(_scope_identity_core(manifest)):
        raise ValueError("scope manifest identity mismatch")
    return _canonical(dict(manifest))


def _write_once(target: Path, files: Mapping[str, bytes]) -> str:
    if target.exists():
        if not target.is_dir() or {entry.name for entry in target.iterdir()} != set(files):
            raise ValueError("strategy scope snapshot write-once conflict")
        for name, expected in files.items():
            entry = target / name
            if not entry.is_file() or entry.is_symlink() or entry.read_bytes() != expected:
                raise ValueError("strategy scope snapshot write-once conflict")
        return "already_published"
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}.staging-", dir=target.parent))
    try:
        for name, raw in files.items():
            path = staging / name
            with tempfile.NamedTemporaryFile(dir=staging, prefix=name + ".", suffix=".tmp", delete=False) as handle:
                temp = Path(handle.name)
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, path)
        os.replace(staging, target)
    except BaseException:
        if staging.exists():
            for entry in staging.iterdir():
                entry.unlink()
            staging.rmdir()
        raise
    return "published"


def publish_scope_snapshot(
    output_root: Path, manifest: Mapping[str, Any], daily_members: bytes
) -> dict[str, Any]:
    manifest_raw = _manifest_bytes(manifest)
    if _sha_bytes(daily_members) != manifest.get("daily_members_sha256"):
        raise ValueError("daily membership file hash does not match scope manifest")
    parsed = json.loads(daily_members.decode("utf-8"))
    if _canonical(parsed) != daily_members or not isinstance(parsed, dict):
        raise ValueError("daily membership file is not canonical JSON")
    target = Path(output_root) / str(manifest["snapshot_id"])
    files = {
        "manifest.json": manifest_raw,
        "manifest.json.sha256": f"{_sha_bytes(manifest_raw)}  manifest.json\n".encode("ascii"),
        "daily_members.json": daily_members,
        "daily_members.json.sha256": f"{_sha_bytes(daily_members)}  daily_members.json\n".encode("ascii"),
    }
    status = _write_once(target, files)
    manifest_sha = _sha_bytes(manifest_raw)
    binding = {
        "snapshot_id": manifest["snapshot_id"],
        "path": (SCOPE_SNAPSHOT_ROOT / str(manifest["snapshot_id"])).as_posix(),
        "manifest_sha256": manifest_sha,
        "scope_identity_sha256": manifest["scope_identity_sha256"],
        "daily_members_sha256": manifest["daily_members_sha256"],
        "market_scope": list(manifest["market_scope"]),
        "protocol_snapshot_id": (manifest.get("protocol") or {}).get("protocol_snapshot_id"),
        "oos_window": manifest["oos_window"],
    }
    return {
        "status": status,
        "snapshot_id": manifest["snapshot_id"],
        "path": str(target),
        "manifest_sha256": manifest_sha,
        "daily_members_sha256": manifest["daily_members_sha256"],
        "binding": binding,
    }


def _check_file_sidecar(path: Path, expected_hash: str, *, label: str) -> None:
    sidecar = path.with_name(path.name + ".sha256")
    if not path.is_file() or path.is_symlink() or not sidecar.is_file() or sidecar.is_symlink():
        raise ValueError(f"{label} or sidecar is missing")
    actual = _sha_file(path)
    if actual != expected_hash or sidecar.read_text(encoding="ascii") != f"{actual}  {path.name}\n":
        raise ValueError(f"{label} sidecar mismatch")


def _check_hash_only_partition_sidecar(path: Path, expected_hash: str) -> str:
    """Verify the hash-only sidecar format used by the pinned raw source partition."""
    source = Path(path)
    sidecar = source.with_name(source.name + ".sha256")
    if (
        not source.is_file()
        or source.is_symlink()
        or not sidecar.is_file()
        or sidecar.is_symlink()
    ):
        raise ValueError("T00018 alias source partition or sidecar is missing or unsafe")
    actual_hash = _sha_file(source)
    if (
        actual_hash != expected_hash
        or sidecar.read_text(encoding="ascii").strip() != expected_hash
    ):
        raise ValueError("T00018 alias source partition sidecar mismatch")
    return actual_hash


class StrategyScopedPITUniverse:
    """Expose only the verified, B5-bound daily universe to B6 consumers."""

    def __init__(
        self,
        raw_universe: Any,
        *,
        scope_snapshot_dir: Path,
        expected_binding: Mapping[str, Any],
    ) -> None:
        self._raw_universe = raw_universe
        self.scope_snapshot_dir = Path(scope_snapshot_dir).resolve()
        manifest_path = self.scope_snapshot_dir / "manifest.json"
        if not manifest_path.is_file() or manifest_path.is_symlink():
            raise ValueError("scope manifest is missing or unsafe")
        raw_manifest = manifest_path.read_bytes()
        manifest_sha = _sha_bytes(raw_manifest)
        sidecar = manifest_path.with_name("manifest.json.sha256")
        if not sidecar.is_file() or sidecar.read_text(encoding="ascii") != f"{manifest_sha}  manifest.json\n":
            raise ValueError("manifest sidecar mismatch")
        manifest = json.loads(raw_manifest.decode("utf-8"))
        if _canonical(manifest) != raw_manifest or manifest != _finalize_manifest(_scope_identity_core(manifest)):
            raise ValueError("scope manifest identity mismatch")
        if manifest.get("schema_version") != SCOPE_SCHEMA or manifest.get("status") != "published":
            raise ValueError("scope manifest schema/status mismatch")
        raw_input_binding = getattr(raw_universe, "formal_input_binding", None)
        if raw_input_binding is not None:
            if (
                getattr(raw_universe, "formal_binding_verified", False) is not True
                or manifest.get("stock_basic_lifecycle")
                != raw_input_binding.get("stock_basic_lifecycle")
                or manifest.get("lifecycle_rule") != LIFECYCLE_RULE
            ):
                raise ValueError("strategy scope lifecycle binding/rule mismatch")
        if manifest.get("authorization_scope") != "strategy_scoped_pit_universe_binding_only" or manifest.get("not_authorized_for_b6_oos_gate_promotion_signal") is not True:
            raise ValueError("scope snapshot authorization disclosure mismatch")
        members_path = self.scope_snapshot_dir / "daily_members.json"
        _check_file_sidecar(members_path, manifest.get("daily_members_sha256", ""), label="daily members")
        members_raw = members_path.read_bytes()
        if members_raw != _canonical(json.loads(members_raw.decode("utf-8"))):
            raise ValueError("daily members file is not canonical")
        if not isinstance(expected_binding, Mapping):
            raise ValueError("B5 strategy scope binding is missing")
        for key in (
            "snapshot_id", "manifest_sha256", "scope_identity_sha256", "daily_members_sha256",
            "market_scope", "protocol_snapshot_id", "oos_window",
        ):
            if expected_binding.get(key) != {
                "snapshot_id": manifest.get("snapshot_id"),
                "manifest_sha256": manifest_sha,
                "scope_identity_sha256": manifest.get("scope_identity_sha256"),
                "daily_members_sha256": manifest.get("daily_members_sha256"),
                "market_scope": manifest.get("market_scope"),
                "protocol_snapshot_id": (manifest.get("protocol") or {}).get("protocol_snapshot_id"),
                "oos_window": manifest.get("oos_window"),
            }[key]:
                raise ValueError(f"B5 strategy scope binding mismatch: {key}")
        raw_members = json.loads(members_raw.decode("utf-8"))
        if not isinstance(raw_members, dict):
            raise ValueError("daily members root must be an object")
        summary_by_day = {row["date"]: row for row in manifest.get("daily_summary", [])}
        if set(raw_members) != set(summary_by_day):
            raise ValueError("daily members dates do not match the manifest")
        self._members: dict[date, tuple[str, ...]] = {}
        self._daily_summary = summary_by_day
        scope = manifest.get("market_scope")
        if scope != ["SH", "SZ"]:
            raise ValueError("frozen strategy market scope mismatch")
        for raw_day, raw_symbols in raw_members.items():
            day = _parse_day(raw_day, label="daily members date")
            if not isinstance(raw_symbols, list) or raw_symbols != sorted(set(raw_symbols)):
                raise ValueError("daily members are not sorted and unique")
            symbols = tuple(raw_symbols)
            if any(_market(symbol) not in scope for symbol in symbols):
                raise ValueError("daily members contain an out-of-scope symbol")
            summary = summary_by_day[raw_day]
            if summary.get("member_count") != len(symbols) or summary.get("members_sha256") != _daily_hash(symbols):
                raise ValueError(f"daily members hash/count mismatch: {raw_day}")
            self._members[day] = symbols
        self.scope_binding = dict(expected_binding)
        self.manifest = manifest

    def __getattr__(self, name: str) -> Any:
        return getattr(self._raw_universe, name)

    @property
    def trading_dates(self) -> tuple[date, ...]:
        return tuple(sorted(self._members))

    def symbols_as_of(self, as_of_date: date) -> tuple[str, ...]:
        if not isinstance(as_of_date, date) or isinstance(as_of_date, datetime):
            raise TypeError("as_of_date must be a date")
        try:
            return self._members[as_of_date]
        except KeyError as exc:
            raise ValueError(f"date is outside the bound strategy scope snapshot: {as_of_date}") from exc

    def scope_audit(self, as_of_date: date) -> dict[str, Any]:
        self.symbols_as_of(as_of_date)
        summary = self._daily_summary[as_of_date.isoformat()]
        return {
            "snapshot_id": self.scope_binding["snapshot_id"],
            "daily_members_sha256": summary["members_sha256"],
            "member_count": summary["member_count"],
            "excluded_by_market": dict(summary.get("excluded_by_market", {})),
            "excluded_by_lifecycle": dict(summary.get("excluded_by_lifecycle", {})),
            "unresolved_lifecycle_symbols": list(
                summary.get("unresolved_lifecycle_symbols", [])
            ),
        }


def _resolve_code_root(code_root: Path) -> Path:
    requested = Path(code_root).resolve(strict=True)
    active = Path(__file__).resolve().parents[2]
    if requested != active:
        raise ValueError("code root does not match the active source tree")
    return active


def _source_bindings(code_root: Path) -> dict[str, dict[str, str]]:
    code_root = _resolve_code_root(code_root)
    paths = {
        "strategy_scoped_materializer": "backend/services/strategy_scoped_pit_universe.py",
        "formal_pit_partition_adapter": "backend/services/formal_pit_partition_adapter.py",
        "b6_preflight_consumer": "backend/services/b6_validation_worker.py",
        "b6_same_draw_consumer": "backend/services/b6_same_draw_executor.py",
        "strategy_template_library": "backend/services/strategy_template_library.py",
    }
    return {
        name: {"path": relative, "sha256": _sha_file(code_root / Path(*relative.split("/")))}
        for name, relative in paths.items()
    }


def _trusted_source_inputs(
    code_root: Path, *, artifact_root: Path | None = None
) -> dict[str, Any]:
    code_root = _resolve_code_root(code_root)
    root = Path(artifact_root if artifact_root is not None else code_root).resolve(strict=True)
    from scripts.verify_shsz_common_trade_calendar import (
        FORMAL_REL,
        verify_candidate,
    )
    from backend.services.v3_b5_bundle import resolve_formal_input_bindings
    from backend.services.formal_pit_partition_adapter import FormalPITPartitionAdapter
    from backend.services.v3_b5_source_inventory import TEMPLATE as SOURCE_INVENTORY_TEMPLATE

    if dict(SOURCE_INVENTORY_TEMPLATE) != TEMPLATE_BINDING:
        raise ValueError("frozen strategy identity differs from verified B5 source inventory")

    formal_input_binding = resolve_formal_input_bindings(root)
    lifecycle_adapter = FormalPITPartitionAdapter(
        root,
        formal_input_binding=formal_input_binding,
    )
    if lifecycle_adapter.formal_binding_verified is not True:
        raise ValueError("strategy scope requires verified formal stock_basic lifecycle")
    lifecycle_dates = dict(lifecycle_adapter._stock_basic)
    stock_basic_lifecycle_binding = formal_input_binding["stock_basic_lifecycle"]

    actual_template = dict(TEMPLATE_BINDING)

    membership_dir = root / "data/pit/pit_membership_snapshots" / MEMBERSHIP_ID
    membership_manifest_path = membership_dir / "manifest.json"
    membership_records_path = membership_dir / "records.parquet"
    _check_file_sidecar(membership_manifest_path, MEMBERSHIP_MANIFEST_SHA256, label="raw PIMS manifest")
    _check_file_sidecar(membership_records_path, MEMBERSHIP_RECORDS_SHA256, label="raw PIMS records")
    membership_manifest = json.loads(membership_manifest_path.read_text(encoding="utf-8"))
    if (
        membership_manifest.get("snapshot_id") != MEMBERSHIP_ID
        or membership_manifest.get("source_contract") != "tushare_sw_l1_member_v2"
        or membership_manifest.get("interval_semantics") != "closed_inclusive"
        or membership_manifest.get("records_parquet_sha256") != MEMBERSHIP_RECORDS_SHA256
    ):
        raise ValueError("raw PIMS source contract or manifest binding mismatch")
    table = pq.read_table(membership_records_path)
    if table.column_names != ["symbol", "effective_from", "effective_to", "source", "snapshot_id"]:
        raise ValueError("raw PIMS records schema mismatch")
    records = table.to_pylist()
    if not records or any(row.get("snapshot_id") != MEMBERSHIP_ID for row in records):
        raise ValueError("raw PIMS records identity mismatch")

    source_audits = [
        row
        for row in membership_manifest.get("source_partition_audit", [])
        if isinstance(row, Mapping)
        and row.get("partition_name") == T00018_ALIAS_SOURCE_PARTITION_NAME
    ]
    if len(source_audits) != 1:
        raise ValueError("T00018 alias source partition audit is missing or ambiguous")
    source_partition_path = root / Path(*T00018_ALIAS_SOURCE_PARTITION_PATH.split("/"))
    _check_hash_only_partition_sidecar(
        source_partition_path,
        T00018_ALIAS_SOURCE_PARTITION_SHA256,
    )
    source_partition = pq.read_table(source_partition_path)
    expected_partition_columns = [
        "l1_code", "l1_name", "l2_code", "l2_name", "l3_code", "l3_name",
        "ts_code", "name", "in_date", "out_date", "is_new",
    ]
    if (
        source_partition.column_names != expected_partition_columns
        or source_partition.num_rows != 144
    ):
        raise ValueError("T00018 alias source partition schema/row count mismatch")
    source_partition_rows = [
        row
        for row in source_partition.to_pylist()
        if row.get("ts_code") in {"T00018.SH", "600018.SH"}
    ]
    records, membership_corrections = _apply_t00018_alias_correction(
        records,
        {
            "source_manifest_sha256": membership_manifest.get(
                "sw2021_membership_manifest_sha256"
            ),
            "source_partition_sha256": _sha_file(source_partition_path),
            "source_partition_row_count": source_partition.num_rows,
            "source_partition_audit": source_audits[0],
            "partition_rows": source_partition_rows,
        },
    )

    calendar_dir = root / Path(*FORMAL_REL.split("/"))
    calendar_manifest = verify_candidate(root, FORMAL_REL, formal_mode=True)
    calendar_manifest_path = calendar_dir / "manifest.json"
    calendar_parquet = calendar_dir / "szse_trade_cal.parquet"
    calendar_binding = {
        "artifact_id": calendar_manifest.get("artifact_id"),
        "path": FORMAL_REL,
        "manifest_sha256": _sha_file(calendar_manifest_path),
        "parquet_sha256": _sha_file(calendar_parquet),
        "date_set_sha256": calendar_manifest.get("comparison", {}).get("common_open_dates_sha256"),
    }
    if calendar_binding != CALENDAR_BINDING:
        raise ValueError("verified common calendar binding mismatch")
    calendar_table = pq.read_table(calendar_parquet, columns=["cal_date", "is_open"])
    common_dates = tuple(
        date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))
        for raw in sorted(
            row["cal_date"]
            for row in calendar_table.to_pylist()
            if row["is_open"] == 1
        )
    )

    db_path = root / "data/strategy.db"
    if not db_path.is_file():
        raise FileNotFoundError("strategy protocol database is missing")
    uri = db_path.as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT payload_json FROM research_protocol_snapshots WHERE protocol_snapshot_id = ?",
            (PROTOCOL_BINDING["protocol_snapshot_id"],),
        ).fetchone()
        template_row = connection.execute(
            "SELECT template_id, version, payload_json, template_hash "
            "FROM strategy_template_definitions WHERE template_id = ? AND version = ?",
            (TEMPLATE_BINDING["template_id"], TEMPLATE_BINDING["template_version"]),
        ).fetchone()
        draft_row = connection.execute(
            "SELECT strategy_revision_id, payload_json FROM strategy_drafts "
            "WHERE strategy_revision_id = ?",
            (PROTOCOL_BINDING["strategy_revision_id"],),
        ).fetchone()
    if row is None:
        raise ValueError("bound B6 protocol snapshot is missing")
    protocol_payload = json.loads(row[0])
    actual_protocol = {
        "protocol_snapshot_id": protocol_payload.get("protocol_snapshot_id"),
        "strategy_revision_id": protocol_payload.get("strategy_revision_id"),
        "shared_oos_window_id": protocol_payload.get("shared_oos_window_id"),
        "protocol_profile": protocol_payload.get("protocol_profile"),
        "data_snapshot_id": protocol_payload.get("data_snapshot_id"),
        "data_snapshot_hash": protocol_payload.get("data_snapshot_hash"),
        "strategy_config_hash": protocol_payload.get("strategy_config_hash"),
        "data_requirements_hash": protocol_payload.get("data_requirements_hash"),
        "oos_window": {
            "start": protocol_payload.get("oos_window_start"),
            "end": protocol_payload.get("oos_window_end"),
        },
    }
    if protocol_payload.get("frozen") is not True or actual_protocol != PROTOCOL_BINDING:
        raise ValueError("frozen B6 protocol binding mismatch")
    if template_row is None or draft_row is None:
        raise ValueError("frozen strategy template or revision is missing")
    template_payload = json.loads(template_row["payload_json"])
    draft_payload = json.loads(draft_row["payload_json"])
    strategy_config_raw = draft_payload.get("strategy_config_json")
    if not isinstance(strategy_config_raw, str):
        raise ValueError("frozen strategy configuration is missing")
    strategy_config = json.loads(strategy_config_raw)
    if (
        template_row["template_id"] != TEMPLATE_BINDING["template_id"]
        or template_row["version"] != TEMPLATE_BINDING["template_version"]
        or template_row["template_hash"] != TEMPLATE_BINDING["template_hash"]
        or template_payload.get("frozen") is not True
        or template_payload.get("governance_status") != "approved"
        or template_payload.get("template_hash") != TEMPLATE_BINDING["template_hash"]
        or template_payload.get("data_requirements_hash")
        != TEMPLATE_BINDING["data_requirements_hash"]
        or draft_payload.get("frozen") is not True
        or draft_payload.get("strategy_revision_id")
        != PROTOCOL_BINDING["strategy_revision_id"]
        or draft_payload.get("strategy_template_id") != TEMPLATE_BINDING["template_id"]
        or draft_payload.get("strategy_template_version")
        != TEMPLATE_BINDING["template_version"]
        or draft_payload.get("strategy_template_hash")
        != TEMPLATE_BINDING["template_hash"]
        or hashlib.sha256(strategy_config_raw.encode("utf-8")).hexdigest()
        != PROTOCOL_BINDING["strategy_config_hash"]
        or draft_payload.get("provenance", {}).get("data_requirements_hash")
        != TEMPLATE_BINDING["data_requirements_hash"]
        or strategy_config.get("market_scope") != ["SH", "SZ"]
        or strategy_config.get("ranking_universe")
        != "formal_sw2021_pit_sh_sz_complete_252d_at_d"
    ):
        raise ValueError("frozen strategy template/revision configuration mismatch")
    start = date.fromisoformat(actual_protocol["oos_window"]["start"])
    end = date.fromisoformat(actual_protocol["oos_window"]["end"])
    trading_dates = tuple(day for day in common_dates if start <= day <= end)
    if not trading_dates or trading_dates[0] != start or trading_dates[-1] != end:
        raise ValueError("verified common calendar does not exactly cover the OOS window")

    return {
        "code_root": code_root,
        "artifact_root": root,
        "records": records,
        "membership_corrections": membership_corrections,
        "trading_dates": trading_dates,
        "template_binding": actual_template,
        "membership_binding": {
            "id": MEMBERSHIP_ID,
            "manifest_sha256": MEMBERSHIP_MANIFEST_SHA256,
            "records_sha256": MEMBERSHIP_RECORDS_SHA256,
        },
        "stock_basic_lifecycle_binding": stock_basic_lifecycle_binding,
        "lifecycle_dates": lifecycle_dates,
        "market_scope": ["SH", "SZ"],
        "protocol_binding": actual_protocol,
        "oos_window": actual_protocol["oos_window"],
        "calendar_binding": calendar_binding,
        "source_bindings": _source_bindings(code_root),
    }


def _build_from_trusted_inputs(inputs: Mapping[str, Any]) -> tuple[dict[str, Any], bytes]:
    materialized = materialize_daily_membership(
        inputs["records"],
        inputs["trading_dates"],
        inputs["market_scope"],
        lifecycle_dates=inputs["lifecycle_dates"],
    )
    members = canonical_daily_members_bytes(materialized.members_by_date)
    manifest = build_scope_snapshot_manifest(
        template_binding=inputs["template_binding"],
        membership_binding=inputs["membership_binding"],
        market_scope=inputs["market_scope"],
        protocol_binding=inputs["protocol_binding"],
        oos_window=inputs["oos_window"],
        calendar_binding=inputs["calendar_binding"],
        stock_basic_lifecycle_binding=inputs["stock_basic_lifecycle_binding"],
        source_bindings=inputs["source_bindings"],
        daily_summary=materialized.daily_summary,
        daily_members_sha256=_sha_bytes(members),
        membership_corrections=inputs["membership_corrections"],
    )
    return manifest, members


def publish_verified_scope_snapshot(
    code_root: Path,
    artifact_root: Path,
    *,
    output_root: Path | None = None,
) -> dict[str, Any]:
    code_root = _resolve_code_root(code_root)
    artifact_root = Path(artifact_root).resolve(strict=True)
    target_root = (
        Path(output_root).resolve()
        if output_root is not None
        else artifact_root / SCOPE_SNAPSHOT_ROOT
    )
    if target_root != (artifact_root / SCOPE_SNAPSHOT_ROOT).resolve():
        raise ValueError("scope output root must be the pinned strategy scope store")
    inputs = _trusted_source_inputs(code_root, artifact_root=artifact_root)
    manifest, members = _build_from_trusted_inputs(inputs)
    published = publish_scope_snapshot(target_root, manifest, members)
    verified = verify_scope_snapshot(
        code_root,
        target_root / manifest["snapshot_id"],
        artifact_root=artifact_root,
        expected_snapshot_id=manifest["snapshot_id"],
        expected_manifest_sha256=published["manifest_sha256"],
    )
    if verified.get("status") != "verified":
        raise ValueError("published strategy scope snapshot did not independently verify")
    return {**published, "verification": verified}


def verify_scope_snapshot(
    code_root: Path,
    scope_snapshot_dir: Path,
    *,
    artifact_root: Path | None = None,
    expected_snapshot_id: str | None = None,
    expected_manifest_sha256: str | None = None,
) -> dict[str, Any]:
    """Rebuild scope identity and daily members from verified source inputs."""
    try:
        code_root = _resolve_code_root(code_root)
        artifact_root = Path(
            artifact_root if artifact_root is not None else code_root
        ).resolve(strict=True)
        inputs = _trusted_source_inputs(code_root, artifact_root=artifact_root)
        directory = Path(scope_snapshot_dir)
        scope_store = (artifact_root / SCOPE_SNAPSHOT_ROOT).resolve(strict=True)
        try:
            directory.resolve(strict=True).relative_to(scope_store)
        except (OSError, ValueError) as exc:
            return {"status": "invalid", "reason": "scope snapshot is outside the explicit artifact root"}
        if expected_snapshot_id is not None and directory.name != expected_snapshot_id:
            return {"status": "invalid", "reason": "scope snapshot ID does not match the requested ID"}
        manifest_path = directory / "manifest.json"
        members_path = directory / "daily_members.json"
        if not manifest_path.is_file() or manifest_path.is_symlink():
            return {"status": "invalid", "reason": "scope manifest missing or unsafe"}
        raw_manifest = manifest_path.read_bytes()
        manifest_sha = _sha_bytes(raw_manifest)
        _check_file_sidecar(manifest_path, manifest_sha, label="scope manifest")
        if expected_manifest_sha256 is not None and manifest_sha != expected_manifest_sha256:
            return {"status": "invalid", "reason": "scope manifest hash does not match the requested hash"}
        manifest = json.loads(raw_manifest.decode("utf-8"))
        if _canonical(manifest) != raw_manifest:
            return {"status": "invalid", "reason": "scope manifest is not canonical"}
        if not members_path.is_file() or members_path.is_symlink():
            return {"status": "invalid", "reason": "daily members file missing or unsafe"}
        _check_file_sidecar(members_path, _sha_file(members_path), label="daily members")

        # Independent rebuild: this verification path does not consume the publisher's
        # member map, daily summary, or asserted member hashes.
        independent_by_date: dict[date, set[str]] = {day: set() for day in inputs["trading_dates"]}
        independent_excluded: dict[date, dict[str, set[str]]] = {
            day: {} for day in inputs["trading_dates"]
        }
        independent_lifecycle_excluded: dict[date, dict[str, set[str]]] = {
            day: {"delisted": set(), "not_yet_listed": set()}
            for day in inputs["trading_dates"]
        }
        independent_lifecycle_unknown: dict[date, set[str]] = {
            day: set() for day in inputs["trading_dates"]
        }
        for row in inputs["records"]:
            symbol = row.get("symbol")
            market = _market(symbol)
            start = _parse_day(row.get("effective_from"), label="membership effective_from")
            raw_end = row.get("effective_to")
            end = None if raw_end is None else _parse_day(raw_end, label="membership effective_to")
            if end is not None and end < start:
                return {"status": "invalid", "reason": f"invalid closed-inclusive interval: {symbol}"}
            first_index = 0
            last_index = len(inputs["trading_dates"])
            while first_index < last_index and inputs["trading_dates"][first_index] < start:
                first_index += 1
            active_end = last_index
            if end is not None:
                active_end = first_index
                while active_end < last_index and inputs["trading_dates"][active_end] <= end:
                    active_end += 1
            for index in range(first_index, active_end):
                day = inputs["trading_dates"][index]
                if market in inputs["market_scope"]:
                    lifecycle = inputs["lifecycle_dates"].get(symbol)
                    if lifecycle is None:
                        # Unknown is retained so B6 can reject the missing formal
                        # lifecycle evidence; it is never hidden by an inner join.
                        independent_by_date[day].add(symbol)
                        independent_lifecycle_unknown[day].add(symbol)
                    else:
                        list_date, delist_date = lifecycle
                        if day < list_date:
                            independent_lifecycle_excluded[day]["not_yet_listed"].add(symbol)
                        elif delist_date is not None and day >= delist_date:
                            independent_lifecycle_excluded[day]["delisted"].add(symbol)
                        else:
                            independent_by_date[day].add(symbol)
                else:
                    independent_excluded[day].setdefault(market, set()).add(symbol)

        independent_members = {
            day: tuple(sorted(symbols)) for day, symbols in independent_by_date.items()
        }
        independent_summary = [
            {
                "date": day.isoformat(),
                "member_count": len(independent_members[day]),
                "members_sha256": _daily_hash(independent_members[day]),
                "excluded_by_market": {
                    market: len(symbols)
                    for market, symbols in sorted(independent_excluded[day].items())
                },
                "excluded_by_lifecycle": {
                    reason: len(symbols)
                    for reason, symbols in sorted(independent_lifecycle_excluded[day].items())
                },
                "unresolved_lifecycle_symbols": sorted(independent_lifecycle_unknown[day]),
            }
            for day in inputs["trading_dates"]
        ]
        independent_bytes = canonical_daily_members_bytes(independent_members)
        expected_manifest = build_scope_snapshot_manifest(
            template_binding=inputs["template_binding"],
            membership_binding=inputs["membership_binding"],
            market_scope=inputs["market_scope"],
            protocol_binding=inputs["protocol_binding"],
            oos_window=inputs["oos_window"],
            calendar_binding=inputs["calendar_binding"],
            stock_basic_lifecycle_binding=inputs["stock_basic_lifecycle_binding"],
            source_bindings=inputs["source_bindings"],
            daily_summary=independent_summary,
            daily_members_sha256=_sha_bytes(independent_bytes),
            membership_corrections=inputs["membership_corrections"],
        )
        if members_path.read_bytes() != independent_bytes:
            return {"status": "invalid", "reason": "independently rebuilt daily members mismatch"}
        if manifest != expected_manifest or directory.name != expected_manifest["snapshot_id"]:
            return {"status": "invalid", "reason": "independently rebuilt scope identity mismatch"}
        return {
            "status": "verified",
            "snapshot_id": expected_manifest["snapshot_id"],
            "manifest_sha256": manifest_sha,
            "scope_identity_sha256": expected_manifest["scope_identity_sha256"],
            "daily_members_sha256": expected_manifest["daily_members_sha256"],
            "daily_date_count": len(independent_members),
            "daily_member_counts": [row["member_count"] for row in independent_summary],
        }
    except (OSError, TypeError, ValueError, KeyError, sqlite3.Error, json.JSONDecodeError) as exc:
        return {"status": "invalid", "reason": str(exc)}


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Publish or verify a strategy-scoped PIT universe")
    subparsers = parser.add_subparsers(dest="command", required=True)
    publish_parser = subparsers.add_parser("publish")
    publish_parser.add_argument("--code-root", type=Path, required=True)
    publish_parser.add_argument("--artifact-root", type=Path, required=True)
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--code-root", type=Path, required=True)
    verify_parser.add_argument("--artifact-root", type=Path, required=True)
    verify_parser.add_argument("--snapshot-id", required=True)
    verify_parser.add_argument("--manifest-sha256", required=True)
    args = parser.parse_args(argv)

    if args.command == "publish":
        result = publish_verified_scope_snapshot(args.code_root, args.artifact_root)
    else:
        scope_dir = args.artifact_root / SCOPE_SNAPSHOT_ROOT / args.snapshot_id
        result = verify_scope_snapshot(
            args.code_root,
            scope_dir,
            artifact_root=args.artifact_root,
            expected_snapshot_id=args.snapshot_id,
            expected_manifest_sha256=args.manifest_sha256,
        )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("status") in {"published", "already_published", "verified"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
