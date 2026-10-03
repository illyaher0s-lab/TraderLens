"""Publish and independently verify the narrow v3 B5 SW2021 source binding."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

import pyarrow.parquet as pq


ROOT = Path(__file__).resolve().parents[2]
SOURCE_MANIFEST_REL = Path(
    "data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal/sw_l1_membership/manifest.json"
)
DEFAULT_OUTPUT_ROOT = ROOT / "data/pit/v3_b5_source_inventories"
SCHEMA = "v3_b5_source_inventory.v1"
EXPECTED_SOURCE_MANIFEST_SHA256 = "a38b3cc6be947b290078fe637466991ee8d13dee2794d398fb709d5c4c3826f3"
EXPECTED_PARTITION_COUNT = 61
REQUIRED_FIELDS = ("ts_code", "l1_code", "l1_name", "in_date", "out_date", "is_new")
TEMPLATE = {
    "template_id": "relative_strength_rotation_shsz_sw2021_v3",
    "template_version": "v3_shsz_sw2021_pit_12m_liquidity20d",
    "template_hash": "f7c0fd8123f62f37118cb947e1735861374435f8707e01b06d788a8ec4df39c1",
    "data_requirements_hash": "ef2ab5b1dafe4349f305b52733a7dcb018a2961464dfbc6542a10e34805d041d",
}
STRATEGY_REVISION_ID = "6440ffc03a742f4d4632078481cf3abf171eafb1a24f2bc69bc6f352d1b19ebc"
MEMBERSHIP = {
    "snapshot_id": "pims_traderlens_v2_shsz_sw2021_pit_005",
    "manifest_sha256": "32f58adbca49fb89dfeb54ceeb4ac9b27b6a26c55e0c9cfeae7a8fcaf3683f10",
    "records_sha256": "2e8c922de9f198ab18a6b38743a01f4343fbf52b876da84026389d3ffd11eec0",
}
CALENDAR = {
    "artifact_id": "shsz_common_trade_calendar_v1",
    "date_set_sha256": "62b6880c9acc381d273ceee40c900a486c3f83488600c042c43ce1d8f9cbb194",
}
SCOPE = {
    "scope_id": "acbc49159d989a46",
    "manifest_sha256": "cef48909b7b7bb05bc952a19ff8e50702540b427c58fd21eb1670afcaf675c67",
}


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha(path: Path) -> str:
    return _sha_bytes(Path(path).read_bytes())


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _read_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _parse_date(value: object, *, field: str, partition: str) -> int:
    if not isinstance(value, str) or not value:
        raise ValueError(f"missing effective date: {partition}:{field}")
    try:
        return int(datetime.strptime(value, "%Y%m%d").strftime("%Y%m%d"))
    except ValueError as error:
        raise ValueError(f"invalid effective date: {partition}:{field}={value!r}") from error


def _source_path(repo_root: Path, source_manifest_rel: Path) -> Path:
    path = (Path(repo_root) / source_manifest_rel).resolve()
    path.relative_to(Path(repo_root).resolve())
    return path


def _validate_source(
    repo_root: Path,
    *,
    source_manifest_rel: Path = SOURCE_MANIFEST_REL,
    expected_source_manifest_sha256: str = EXPECTED_SOURCE_MANIFEST_SHA256,
    expected_partition_count: int = EXPECTED_PARTITION_COUNT,
) -> tuple[dict, list[dict]]:
    repo_root = Path(repo_root).resolve()
    source_manifest_path = _source_path(repo_root, Path(source_manifest_rel))
    if not source_manifest_path.exists():
        raise ValueError(f"missing source manifest: {source_manifest_path}")
    source_manifest_sha256 = _sha(source_manifest_path)
    if source_manifest_sha256 != expected_source_manifest_sha256:
        raise ValueError("source manifest hash mismatch")
    source_manifest = _read_json(source_manifest_path)
    if source_manifest.get("status") != "collected_verified":
        raise ValueError("source manifest status mismatch")

    selected = []
    for partition in source_manifest.get("partitions", []):
        src = partition.get("src")
        name = partition.get("name")
        if src == "SW2021":
            if not isinstance(name, str) or not name.startswith("SW2021_"):
                raise ValueError("SW2021 partition identity mismatch")
            selected.append(partition)
    if len(selected) != expected_partition_count:
        raise ValueError(f"SW2021 partition count mismatch: {len(selected)} != {expected_partition_count}")

    source_dir = source_manifest_path.parent
    identities: set[tuple[object, ...]] = set()
    intervals: dict[str, list[tuple[int, int | None, str]]] = {}
    accepted = []
    for partition in sorted(selected, key=lambda item: item["name"]):
        name = partition.get("name")
        path = source_dir / name
        if not path.exists():
            raise ValueError(f"missing partition: {name}")
        actual_sha256 = _sha(path)
        if actual_sha256 != partition.get("sha256"):
            raise ValueError(f"partition hash mismatch: {name}")
        table = pq.read_table(path)
        if table.num_rows != partition.get("row_count"):
            raise ValueError(f"partition row count mismatch: {name}")
        missing = [field for field in REQUIRED_FIELDS if field not in table.column_names]
        if missing:
            raise ValueError(f"required fields missing in {name}: {','.join(missing)}")
        for row in table.to_pylist():
            for field in ("ts_code", "l1_code", "l1_name", "is_new"):
                if row.get(field) in (None, ""):
                    raise ValueError(f"required fields missing in {name}: {field}")
            start = _parse_date(row.get("in_date"), field="in_date", partition=name)
            end = None if row.get("out_date") in (None, "") else _parse_date(row.get("out_date"), field="out_date", partition=name)
            if end is not None and end < start:
                raise ValueError(f"invalid effective interval: {name}")
            if row.get("l1_code") != partition.get("l1_code"):
                raise ValueError(f"partition l1_code mismatch: {name}")
            identity = (row.get("ts_code"), row.get("in_date"), row.get("out_date"), row.get("l1_code"), row.get("is_new"))
            if identity in identities:
                raise ValueError(f"duplicate identity: {identity}")
            identities.add(identity)
            intervals.setdefault(row["ts_code"], []).append((start, end, row["l1_code"]))
        accepted.append({
            "name": name,
            "l1_code": partition.get("l1_code"),
            "l1_name": partition.get("l1_name"),
            "is_new": partition.get("is_new"),
            "row_count": table.num_rows,
            "sha256": actual_sha256,
        })

    for symbol, rows in intervals.items():
        rows.sort(key=lambda item: item[0])
        for index, (start, end, l1_code) in enumerate(rows):
            for other_start, other_end, other_l1_code in rows[index + 1:]:
                if other_l1_code == l1_code:
                    continue
                if end is None or other_start <= end:
                    raise ValueError(f"overlapping active l1 codes: {symbol}")

    bindings = {
        "source_manifest_path": Path(source_manifest_rel).as_posix(),
        "source_manifest_sha256": source_manifest_sha256,
        "accepted_source_taxonomy": "SW2021",
        "accepted_partition_count": expected_partition_count,
        "required_fields": list(REQUIRED_FIELDS),
        "pit_rule": "in_date <= as_of <= out_date; null out_date is open-ended",
    }
    return bindings, accepted


def build_source_inventory_payload(
    repo_root: Path = ROOT,
    *,
    source_manifest_rel: Path = SOURCE_MANIFEST_REL,
    expected_source_manifest_sha256: str = EXPECTED_SOURCE_MANIFEST_SHA256,
    expected_partition_count: int = EXPECTED_PARTITION_COUNT,
) -> dict:
    bindings, partitions = _validate_source(
        repo_root,
        source_manifest_rel=source_manifest_rel,
        expected_source_manifest_sha256=expected_source_manifest_sha256,
        expected_partition_count=expected_partition_count,
    )
    return {
        "schema_version": SCHEMA,
        "status": "published",
        "authorization_scope": "v3_b5_source_inventory_only",
        "not_authorized_for_b6_oos_gate_promotion_signal": True,
        "template": dict(TEMPLATE),
        "strategy_revision_id": STRATEGY_REVISION_ID,
        "membership": dict(MEMBERSHIP),
        "calendar": dict(CALENDAR),
        "scope": dict(SCOPE),
        **bindings,
        "partitions": partitions,
        "accepted_row_count": sum(part["row_count"] for part in partitions),
    }


def publish_source_inventory(repo_root: Path, output_root: Path, **kwargs) -> dict:
    payload = build_source_inventory_payload(Path(repo_root), **kwargs)
    artifact_id = _sha_bytes(_canonical(payload))[:16]
    manifest = {**payload, "artifact_id": artifact_id}
    raw = _canonical(manifest)
    target = Path(output_root) / artifact_id
    manifest_path = target / "manifest.json"
    sidecar_path = target / "manifest.json.sha256"
    if target.exists():
        if not manifest_path.exists() or not sidecar_path.exists() or manifest_path.read_bytes() != raw or sidecar_path.read_text(encoding="utf-8").split()[0] != _sha_bytes(raw):
            raise ValueError("source inventory write-once conflict")
        return {"status": "already_published", "artifact_id": artifact_id, "path": str(target), "manifest_sha256": _sha(manifest_path)}
    target.mkdir(parents=True, exist_ok=False)
    try:
        with tempfile.NamedTemporaryFile(dir=target, prefix="manifest.", suffix=".tmp", delete=False) as handle:
            temp_manifest = Path(handle.name)
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_manifest, manifest_path)
        with tempfile.NamedTemporaryFile(dir=target, prefix="manifest.sha256.", suffix=".tmp", mode="w", encoding="utf-8", delete=False) as handle:
            temp_sidecar = Path(handle.name)
            handle.write(f"{_sha_bytes(raw)}  manifest.json\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_sidecar, sidecar_path)
    except Exception:
        for path in (locals().get("temp_manifest"), locals().get("temp_sidecar")):
            if path and Path(path).exists():
                Path(path).unlink()
        raise
    return {"status": "published", "artifact_id": artifact_id, "path": str(target), "manifest_sha256": _sha(manifest_path)}


def verify_source_inventory(repo_root: Path, artifact_dir: Path, **kwargs) -> dict:
    try:
        artifact_dir = Path(artifact_dir)
        manifest_path = artifact_dir / "manifest.json"
        sidecar_path = artifact_dir / "manifest.json.sha256"
        if not manifest_path.exists() or not sidecar_path.exists():
            return {"status": "invalid", "reason": "manifest or sidecar missing"}
        actual_manifest_sha = _sha(manifest_path)
        if sidecar_path.read_text(encoding="utf-8").split()[0] != actual_manifest_sha:
            return {"status": "invalid", "reason": "manifest sidecar mismatch"}
        manifest = _read_json(manifest_path)
        if manifest.get("schema_version") != SCHEMA or manifest.get("status") != "published":
            return {"status": "invalid", "reason": "manifest schema or status mismatch"}
        artifact_id = manifest.get("artifact_id")
        payload = {key: value for key, value in manifest.items() if key != "artifact_id"}
        expected_payload = build_source_inventory_payload(Path(repo_root), **kwargs)
        if payload != expected_payload:
            return {"status": "invalid", "reason": "source binding or source hash mismatch"}
        expected_id = _sha_bytes(_canonical(expected_payload))[:16]
        if artifact_id != expected_id or artifact_dir.name != expected_id:
            return {"status": "invalid", "reason": "artifact identity mismatch"}
        if manifest.get("accepted_partition_count") != len(manifest.get("partitions", [])):
            return {"status": "invalid", "reason": "partition arithmetic mismatch"}
        return {
            "status": "verified",
            "artifact_id": expected_id,
            "path": str(artifact_dir),
            "manifest_sha256": actual_manifest_sha,
            "accepted_partition_count": len(manifest["partitions"]),
            "accepted_row_count": manifest["accepted_row_count"],
        }
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        return {"status": "invalid", "reason": str(error)}
