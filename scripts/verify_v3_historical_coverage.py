"""Independently verify a published v3 historical coverage artifact."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pyarrow.parquet as pq

from scripts.publish_v3_historical_scope import (
    DATA_REQUIREMENTS_HASH,
    DEFAULT_CALENDAR_DIR,
    TEMPLATE_HASH,
    TEMPLATE_ID,
    TEMPLATE_VERSION,
    _canonical,
    verify_scope,
)
from scripts.publish_v3_historical_suspension_evidence import DEFAULT_DIAGNOSTICS, DEFAULT_PROVIDER_PROBE
from scripts.verify_v3_historical_suspension_evidence import verify_evidence
from scripts.v3_liquidity_source_adapter import SOURCE_ADAPTER_CONTRACT_HASH, SOURCE_ADAPTER_ID


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SCOPE_DIR = ROOT / "data/pit/historical_scope_freezes/acbc49159d989a46"
DEFAULT_COVERAGE_DIR = ROOT / "data/pit/v3_historical_coverage_packages/4d543215598370b5"


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _read_sidecar(path: Path) -> str:
    parts = path.read_text(encoding="utf-8").strip().split()
    if len(parts) not in (1, 2) or len(parts[0]) != 64:
        raise ValueError(f"invalid SHA-256 sidecar: {path}")
    int(parts[0], 16)
    return parts[0]


def _check_file(artifact_dir: Path, name: str, metadata: dict) -> Path:
    path = artifact_dir / name
    sidecar = artifact_dir / f"{name}.sha256"
    if not path.exists() or not sidecar.exists():
        raise ValueError(f"coverage parquet or sidecar is missing: {name}")
    actual_hash = _sha256_file(path)
    if _read_sidecar(sidecar) != actual_hash:
        raise ValueError(f"coverage parquet sidecar mismatch: {name}")
    if metadata.get("sha256") != actual_hash or metadata.get("byte_size") != path.stat().st_size:
        raise ValueError(f"coverage parquet manifest hash mismatch: {name}")
    return path


def verify_coverage(
    coverage_dir: Path,
    *,
    scope_dir: Path = DEFAULT_SCOPE_DIR,
    calendar_dir: Path = DEFAULT_CALENDAR_DIR,
) -> dict:
    coverage_dir = Path(coverage_dir)
    manifest_path = coverage_dir / "manifest.json"
    manifest_sidecar = coverage_dir / "manifest.json.sha256"
    if not manifest_path.exists() or not manifest_sidecar.exists():
        raise ValueError("coverage manifest or sidecar is missing")
    raw = manifest_path.read_bytes()
    if _read_sidecar(manifest_sidecar) != _sha256_bytes(raw):
        raise ValueError("coverage manifest sidecar mismatch")
    manifest = json.loads(raw.decode("utf-8"))
    artifact_id = manifest.pop("artifact_id", None)
    if not artifact_id or _sha256_bytes(_canonical(manifest))[:16] != artifact_id:
        raise ValueError("coverage artifact ID mismatch")
    if manifest.get("schema_version") != "v3_historical_coverage.v1" or manifest.get("status") != "published" or manifest.get("frozen") is not True:
        raise ValueError("coverage publication state mismatch")

    verify_scope(Path(scope_dir), calendar_dir=Path(calendar_dir))
    scope_manifest_path = Path(scope_dir) / "manifest.json"
    scope = json.loads(scope_manifest_path.read_text(encoding="utf-8"))
    template = manifest.get("template")
    if template != {
        "template_id": TEMPLATE_ID,
        "template_version": TEMPLATE_VERSION,
        "template_hash": TEMPLATE_HASH,
        "data_requirements_hash": DATA_REQUIREMENTS_HASH,
    }:
        raise ValueError("coverage template identity mismatch")
    scope_freeze = manifest.get("scope_freeze", {})
    if scope_freeze != {
        "artifact_id": scope["artifact_id"],
        "manifest_sha256": _sha256_file(scope_manifest_path),
        "path": Path(scope_dir).relative_to(ROOT).as_posix(),
    }:
        raise ValueError("coverage scope freeze binding mismatch")
    execution = scope["execution"]
    source = scope["source"]
    expected_execution = {
        "count": execution["count"],
        "start": execution["start"],
        "end": execution["end"],
        "ordered_date_set_sha256": execution["ordered_date_set_sha256"],
        "as_of_ordered_dates_sha256": _sha256_bytes(_canonical(execution["as_of_dates"])),
    }
    if manifest.get("execution_scope") != expected_execution:
        raise ValueError("coverage execution scope binding mismatch")
    expected_source = {
        "count": source["count"],
        "start": source["start"],
        "end": source["end"],
        "ordered_date_set_sha256": source["ordered_date_set_sha256"],
    }
    if manifest.get("source_scope") != expected_source:
        raise ValueError("coverage source scope binding mismatch")

    evidence_binding = manifest.get("lineage", {}).get("suspension_evidence")
    if not evidence_binding or manifest.get("source_adapter") != {"id": SOURCE_ADAPTER_ID, "contract_sha256": SOURCE_ADAPTER_CONTRACT_HASH}:
        raise ValueError("coverage source adapter binding missing")
    evidence_path = ROOT / evidence_binding["repo_relative_path"]
    evidence_result = verify_evidence(evidence_path.parent, diagnostics_path=DEFAULT_DIAGNOSTICS, provider_probe_path=DEFAULT_PROVIDER_PROBE, scope_dir=Path(scope_dir))
    if evidence_result["artifact_id"] != evidence_binding["artifact_id"] or evidence_binding["manifest_sha256"] != _sha256_file(evidence_path):
        raise ValueError("coverage suspension evidence binding mismatch")

    file_names = {
        "coverage_by_date": "coverage_by_date.parquet",
        "coverage_by_code": "coverage_by_code.parquet",
        "unavailable": "unavailable_security_dates.parquet",
    }
    file_metadata = manifest.get("files", {})
    if set(file_metadata) != set(file_names):
        raise ValueError("coverage output file inventory mismatch")
    coverage_by_date_path = _check_file(coverage_dir, file_names["coverage_by_date"], file_metadata["coverage_by_date"])
    _check_file(coverage_dir, file_names["coverage_by_code"], file_metadata["coverage_by_code"])
    _check_file(coverage_dir, file_names["unavailable"], file_metadata["unavailable"])

    required = {"expected_codes", "complete_codes", "unavailable_codes", "data_fault_codes"}
    rows = pq.read_table(coverage_by_date_path).to_pylist()
    if not rows or not required.issubset(rows[0]):
        raise ValueError("coverage_by_date schema mismatch")
    totals = {key: 0 for key in required}
    for row in rows:
        values = {key: int(row[key]) for key in required}
        if any(value < 0 for value in values.values()):
            raise ValueError("coverage_by_date contains negative counts")
        if values["expected_codes"] != values["complete_codes"] + values["unavailable_codes"] + values["data_fault_codes"]:
            raise ValueError("coverage_by_date arithmetic mismatch")
        for key, value in values.items():
            totals[key] += value
    if totals["expected_codes"] != totals["complete_codes"] + totals["unavailable_codes"] + totals["data_fault_codes"]:
        raise ValueError("coverage arithmetic mismatch")

    coverage = manifest.get("coverage", {})
    manifest_totals = {
        "expected_codes": coverage.get("expected_stock_days"),
        "complete_codes": coverage.get("complete_stock_days"),
        "unavailable_codes": coverage.get("unavailable_stock_days"),
        "data_fault_codes": coverage.get("data_fault_count"),
    }
    if manifest_totals != totals:
        raise ValueError("coverage manifest stats do not match coverage_by_date")
    if totals["data_fault_codes"] != 0:
        raise ValueError("coverage data_fault_count is not zero")
    if coverage.get("first_data_fault") is not None:
        raise ValueError("first_data_fault must be null when data_fault_count is zero")
    return {"status": "valid", "artifact_id": artifact_id, "stats": coverage}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--coverage-dir", type=Path, default=DEFAULT_COVERAGE_DIR)
    parser.add_argument("--scope-dir", type=Path, default=DEFAULT_SCOPE_DIR)
    parser.add_argument("--calendar-dir", type=Path, default=DEFAULT_CALENDAR_DIR)
    args = parser.parse_args()
    print(json.dumps(verify_coverage(args.coverage_dir, scope_dir=args.scope_dir, calendar_dir=args.calendar_dir), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
