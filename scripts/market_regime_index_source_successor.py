"""Publish and independently verify the bounded v1.2 000300.SH index successor."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from scripts.market_regime_bounded_replay import (
    CONFIG_PATH,
    FORMAL_ROOT,
    INDEX_SOURCE_ROOT,
    _canonical,
    _calendar_days,
    _day,
    _load_config,
    _normalize_index_rows,
    _prior_days,
    _sha_bytes,
    _sha_file,
    _sidecar,
    _window_days,
    verify_index_source,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PREDECESSOR = ROOT / "data/pit/market_regime_index_sources/17788491304db2ee"
DEFAULT_OUTPUT_ROOT = INDEX_SOURCE_ROOT


def _expected_dates(config_path: Path = CONFIG_PATH, formal_root: Path = FORMAL_ROOT) -> list[str]:
    config, _ = _load_config(Path(config_path))
    calendar = _calendar_days(Path(formal_root))
    windows = [
        {"start": _day(window["start"]), "end": _day(window["end"])}
        for window in config["stress_windows"]
    ]
    windows.append({"start": _day(config["normal_window"]["start"]), "end": _day(config["normal_window"]["end"])})
    dates = set()
    for window in windows:
        for day in _window_days(calendar, window["start"], window["end"]):
            dates.update(_prior_days(calendar, day, 4))
            dates.add(day)
    return sorted(dates)


def _write_sidecar(path: Path) -> None:
    path.with_name(path.name + ".sha256").write_text(f"{_sha_file(path)}  {path.name}\n", encoding="utf-8")


def _load_predecessor(predecessor_dir: Path) -> tuple[dict[str, Any], str]:
    manifest_path = Path(predecessor_dir) / "manifest.json"
    result = verify_index_source(Path(predecessor_dir))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return manifest, result["artifact_id"]


def publish_successor(
    rows: list[dict[str, Any]],
    requests: list[dict[str, str]],
    *,
    predecessor_dir: Path = DEFAULT_PREDECESSOR,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    expected_dates: list[str] | None = None,
    config_path: Path = CONFIG_PATH,
) -> dict[str, Any]:
    normalized = _normalize_index_rows(rows)
    dates = [row["trade_date"] for row in normalized]
    expected = sorted(expected_dates if expected_dates is not None else _expected_dates(config_path))
    if dates != expected:
        raise ValueError(f"index successor exact date set mismatch: expected {expected}, got {dates}")
    predecessor, predecessor_id = _load_predecessor(Path(predecessor_dir))
    _, config_hash = _load_config(Path(config_path))
    payload = {
        "schema_version": "market_regime_index_source_successor.v1",
        "provider": "tushare",
        "api": "index_daily",
        "ts_code": "000300.SH",
        "requests": sorted(requests, key=lambda request: (request.get("start_date", ""), request.get("end_date", ""))),
        "fields": ["ts_code", "trade_date", "close", "pre_close"],
        "row_count": len(normalized),
        "date_set": dates,
        "date_set_sha256": _sha_bytes(_canonical(dates)),
        "rows_sha256": _sha_bytes(_canonical(normalized)),
        "config": {"path": str(Path(config_path).resolve().relative_to(ROOT)).replace("\\", "/"), "semantic_hash": config_hash, "sha256": _sha_file(Path(config_path))},
        "lineage": {"predecessor": {"artifact_id": predecessor_id, "manifest_sha256": _sha_file(Path(predecessor_dir) / "manifest.json")}},
        "not_authorized_for_b3_b6_oos_gate_promotion_signal": True,
    }
    artifact_id = _sha_bytes(_canonical(payload))[:16]
    target = Path(output_root) / artifact_id
    if target.exists():
        existing = target / "manifest.json"
        if not existing.exists() or json.loads(existing.read_text(encoding="utf-8")) != {**payload, "artifact_id": artifact_id, "file": json.loads(existing.read_text(encoding="utf-8")).get("file")}:
            raise ValueError(f"index successor write-once conflict: {target}")
        return {"status": "already_published", "artifact_id": artifact_id, "path": str(target)}
    target.mkdir(parents=True, exist_ok=False)
    parquet_path = target / "index_daily_000300.parquet"
    import pyarrow as pa
    table = pa.Table.from_pylist(normalized, schema=pa.schema([
        pa.field("ts_code", pa.string()), pa.field("trade_date", pa.string()),
        pa.field("close", pa.float64()), pa.field("pre_close", pa.float64()),
    ]))
    pq.write_table(table, parquet_path, compression="snappy")
    manifest = {**payload, "artifact_id": artifact_id, "file": {"path": parquet_path.name, "sha256": _sha_file(parquet_path), "byte_size": parquet_path.stat().st_size}}
    manifest_path = target / "manifest.json"
    temp = target / "manifest.json.tmp"
    try:
        temp.write_bytes(_canonical(manifest))
        with open(temp, "rb+") as handle:
            handle.flush(); os.fsync(handle.fileno())
        os.replace(temp, manifest_path)
    finally:
        if temp.exists():
            temp.unlink()
    _write_sidecar(parquet_path)
    _write_sidecar(manifest_path)
    return {"status": "published", "artifact_id": artifact_id, "path": str(target), "row_count": len(normalized), "date_set": dates}


def verify_successor(
    source_dir: Path,
    *,
    predecessor_dir: Path = DEFAULT_PREDECESSOR,
    expected_dates: list[str] | None = None,
    config_path: Path = CONFIG_PATH,
    formal_root: Path = FORMAL_ROOT,
) -> dict[str, Any]:
    source_dir = Path(source_dir)
    manifest_path = source_dir / "manifest.json"
    parquet_path = source_dir / "index_daily_000300.parquet"
    _sidecar(manifest_path); _sidecar(parquet_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload = {key: value for key, value in manifest.items() if key not in {"artifact_id", "file"}}
    artifact_id = manifest.get("artifact_id")
    if manifest.get("schema_version") != "market_regime_index_source_successor.v1" or _sha_bytes(_canonical(payload))[:16] != artifact_id:
        raise ValueError("index successor identity mismatch")
    expected = sorted(expected_dates if expected_dates is not None else _expected_dates(config_path, formal_root))
    rows = _normalize_index_rows(pq.read_table(parquet_path).to_pylist())
    if [row["trade_date"] for row in rows] != expected or manifest.get("date_set") != expected:
        raise ValueError("index successor exact date set mismatch")
    if manifest.get("row_count") != len(rows) or manifest.get("rows_sha256") != _sha_bytes(_canonical(rows)) or manifest.get("file", {}).get("sha256") != _sha_file(parquet_path):
        raise ValueError("index successor row/file binding mismatch")
    predecessor = manifest.get("lineage", {}).get("predecessor", {})
    pred_path = Path(predecessor_dir)
    pred_manifest = pred_path / "manifest.json"
    pred_verified = verify_index_source(pred_path)
    if pred_verified["artifact_id"] != predecessor.get("artifact_id") or _sha_file(pred_manifest) != predecessor.get("manifest_sha256"):
        raise ValueError("index successor predecessor identity mismatch")
    if manifest.get("config", {}).get("sha256") != _sha_file(Path(config_path)):
        raise ValueError("index successor config source hash mismatch")
    _, config_hash = _load_config(Path(config_path))
    if manifest.get("config", {}).get("semantic_hash") != config_hash:
        raise ValueError("index successor config semantic binding mismatch")
    return {"status": "verified", "artifact_id": artifact_id, "path": str(source_dir), "row_count": len(rows), "date_set": expected}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_dir", type=Path, nargs="?")
    args = parser.parse_args()
    if args.source_dir:
        print(json.dumps(verify_successor(args.source_dir), sort_keys=True))
    else:
        raise SystemExit("publisher is called through publish_successor with bounded provider rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
